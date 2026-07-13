// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
// rebuild-sync: touch to build alongside frontend-proxy/cart/checkout/product-catalog/product-reviews/recommendation under one CI tag

using Confluent.Kafka;
using Microsoft.Extensions.Logging;
using Oteldemo;
using Microsoft.EntityFrameworkCore;
using System.Diagnostics;

namespace Accounting;

internal class DBContext : DbContext
{
    public DbSet<OrderEntity> Orders { get; set; }
    public DbSet<OrderItemEntity> CartItems { get; set; }
    public DbSet<ShippingEntity> Shipping { get; set; }

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        var connectionString = Environment.GetEnvironmentVariable("DB_CONNECTION_STRING");

        optionsBuilder.UseNpgsql(connectionString).UseSnakeCaseNamingConvention();
    }
}


internal class Consumer : IDisposable
{
    private const string TopicName = "orders";

    private ILogger _logger;
    private IConsumer<string, byte[]> _consumer;
    private bool _isListening;
    private DBContext? _dbContext;
    private static readonly ActivitySource MyActivitySource = new("Accounting.Consumer");

    public Consumer(ILogger<Consumer> logger)
    {
        _logger = logger;

        var servers = Environment.GetEnvironmentVariable("KAFKA_ADDR")
            ?? throw new InvalidOperationException("The KAFKA_ADDR environment variable is not set.");

        _consumer = BuildConsumer(servers);
        _consumer.Subscribe(TopicName);

       if (_logger.IsEnabled(LogLevel.Information))
       {
           _logger.LogInformation("Connecting to Kafka: {servers}", servers);
       }

        _dbContext = Environment.GetEnvironmentVariable("DB_CONNECTION_STRING") == null ? null : new DBContext();
    }

    public void StartListening()
    {
        _isListening = true;

        try
        {
            while (_isListening)
            {
                try
                {
                    using var activity = MyActivitySource.StartActivity("order-consumed",  ActivityKind.Internal);
                    var consumeResult = _consumer.Consume();
                    if (ProcessMessage(consumeResult.Message))
                    {
                        // REL-09: commit only AFTER the order is safely persisted.
                        // Previously EnableAutoCommit=true committed the offset before
                        // the DB write, so a crash or DB failure lost the order silently
                        // even though the customer had already been charged.
                        _consumer.Commit(consumeResult);
                    }
                    else
                    {
                        // Transient failure (e.g. Postgres down). Rewind to this offset
                        // and back off so the same message is retried, not skipped.
                        _consumer.Seek(consumeResult.TopicPartitionOffset);
                        Thread.Sleep(TimeSpan.FromSeconds(2));
                    }
                }
                catch (ConsumeException e)
                {
                    if (_logger.IsEnabled(LogLevel.Error))
                    {
                        _logger.LogError(e, "Consume error: {reason}", e.Error.Reason);
                    }
                }
            }
        }
        catch (OperationCanceledException)
        {
            _logger.LogInformation("Closing consumer");

            _consumer.Close();
        }
    }

    // Returns true when the offset is safe to commit (persisted, or a poison
    // message that can never succeed), false on a transient failure that should
    // be retried without committing.
    private bool ProcessMessage(Message<string, byte[]> message)
    {
        OrderResult order;
        try
        {
            order = OrderResult.Parser.ParseFrom(message.Value);
        }
        catch (Exception ex)
        {
            // Poison message: parsing will never succeed on retry. Skip it
            // (commit) so it doesn't block the partition forever. A dead-letter
            // topic would be the next improvement.
            _logger.LogError(ex, "Skipping unparseable order message");
            return true;
        }

        Log.OrderReceivedMessage(_logger, order);

        if (_dbContext == null)
        {
            return true;
        }

        try
        {
            var orderEntity = new OrderEntity
            {
                Id = order.OrderId
            };
            _dbContext.Add(orderEntity);
            foreach (var item in order.Items)
            {
                var orderItem = new OrderItemEntity
                {
                    ItemCostCurrencyCode = item.Cost.CurrencyCode,
                    ItemCostUnits = item.Cost.Units,
                    ItemCostNanos = item.Cost.Nanos,
                    ProductId = item.Item.ProductId,
                    Quantity = item.Item.Quantity,
                    OrderId = order.OrderId
                };

                _dbContext.Add(orderItem);
            }

            var shipping = new ShippingEntity
            {
                ShippingTrackingId = order.ShippingTrackingId,
                ShippingCostCurrencyCode = order.ShippingCost.CurrencyCode,
                ShippingCostUnits = order.ShippingCost.Units,
                ShippingCostNanos = order.ShippingCost.Nanos,
                StreetAddress = order.ShippingAddress.StreetAddress,
                City = order.ShippingAddress.City,
                State = order.ShippingAddress.State,
                Country = order.ShippingAddress.Country,
                ZipCode = order.ShippingAddress.ZipCode,
                OrderId = order.OrderId
            };
            _dbContext.Add(shipping);
            _dbContext.SaveChanges();
            return true;
        }
        catch (Exception ex)
        {
            // Transient persistence failure (e.g. Postgres unavailable). Do NOT
            // commit; clear the entities queued in this attempt so they don't leak
            // into the retry, then signal the caller to rewind and retry.
            _logger.LogError(ex, "Failed to persist order {OrderId}; will retry", order.OrderId);
            _dbContext.ChangeTracker.Clear();
            return false;
        }
    }

    private static IConsumer<string, byte[]> BuildConsumer(string servers)
    {
        var conf = new ConsumerConfig
        {
            GroupId = $"accounting",
            BootstrapServers = servers,
            // https://github.com/confluentinc/confluent-kafka-dotnet/tree/07de95ed647af80a0db39ce6a8891a630423b952#basic-consumer-example
            AutoOffsetReset = AutoOffsetReset.Earliest,
            // REL-09: commit offsets manually (after the order is persisted) so a
            // crash/DB failure mid-processing does not silently lose the order.
            EnableAutoCommit = false
        };

        return new ConsumerBuilder<string, byte[]>(conf)
            .Build();
    }

    public void Dispose()
    {
        _isListening = false;
        _consumer?.Dispose();
    }
}

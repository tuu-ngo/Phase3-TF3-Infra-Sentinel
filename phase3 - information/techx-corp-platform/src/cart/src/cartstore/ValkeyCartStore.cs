// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
using System;
using System.Linq;
using System.Threading.Tasks;
using Grpc.Core;
using StackExchange.Redis;
using Google.Protobuf;
using Microsoft.Extensions.Logging;
using System.Diagnostics.Metrics;
using System.Diagnostics;

namespace cart.cartstore;

public class ValkeyCartStore : ICartStore
{
    private readonly ILogger _logger;
    private const string CartFieldName = "cart";
    private const int RedisRetryNumber = 30;

    private volatile ConnectionMultiplexer _redis;
    private volatile bool _isRedisConnectionOpened;
    private volatile ConnectionMultiplexer _dualWriteRedis;
    private volatile bool _isDualWriteConnectionOpened;

    private readonly object _locker = new();
    private readonly object _dualWriteLocker = new();
    private readonly byte[] _emptyCartBytes;
    private readonly string _connectionString;
    private readonly string _dualWriteConnectionString;
    private readonly bool _isDualWriteEnabled;
    private const int DualWriteConnectRetry = 1;
    private const int DualWriteTimeoutMs = 1000;

    private static readonly ActivitySource CartActivitySource = new("OpenTelemetry.Demo.Cart");
    private static readonly Meter CartMeter = new Meter("OpenTelemetry.Demo.Cart");
    private static readonly Histogram<double> addItemHistogram = CartMeter.CreateHistogram(
        "app.cart.add_item.latency",
        unit: "s",
        advice: new InstrumentAdvice<double>
        {
            HistogramBucketBoundaries = [ 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10 ]
        });
    private static readonly Histogram<double> getCartHistogram = CartMeter.CreateHistogram(
        "app.cart.get_cart.latency",
        unit: "s",
        advice: new InstrumentAdvice<double>
        {
            HistogramBucketBoundaries = [ 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10 ]
        });
    private readonly ConfigurationOptions _redisConnectionOptions;
    private readonly ConfigurationOptions _dualWriteConnectionOptions;

    public ValkeyCartStore(
        ILogger<ValkeyCartStore> logger,
        string valkeyAddress,
        bool valkeyTls = false,
        string valkeyAuthToken = "",
        string dualWriteAddress = "",
        bool dualWriteTls = false,
        string dualWriteAuthToken = "")
    {
        _logger = logger;
        // Serialize empty cart into byte array.
        var cart = new Oteldemo.Cart();
        _emptyCartBytes = cart.ToByteArray();
        _connectionString = BuildSafeConnectionString(valkeyAddress, valkeyTls, valkeyAuthToken);
        _redisConnectionOptions = BuildConnectionOptions(valkeyAddress, valkeyTls, valkeyAuthToken);

        _isDualWriteEnabled = !string.IsNullOrWhiteSpace(dualWriteAddress);
        if (_isDualWriteEnabled)
        {
            _dualWriteConnectionString = BuildSafeConnectionString(dualWriteAddress, dualWriteTls, dualWriteAuthToken);
            _dualWriteConnectionOptions = BuildConnectionOptions(
                dualWriteAddress,
                dualWriteTls,
                dualWriteAuthToken,
                DualWriteConnectRetry,
                DualWriteTimeoutMs);
        }
        else
        {
            _dualWriteConnectionString = "";
            _dualWriteConnectionOptions = null;
        }
    }

    public ConnectionMultiplexer GetConnection()
    {
        EnsureRedisConnected();
        return _redis;
    }

    public void Initialize()
    {
        EnsureRedisConnected();
    }

    private void EnsureRedisConnected()
    {
        if (_isRedisConnectionOpened)
        {
            return;
        }

        // Connection is closed or failed - open a new one but only at the first thread
        lock (_locker)
        {
            if (_isRedisConnectionOpened)
            {
                return;
            }

            if (_logger.IsEnabled(LogLevel.Debug))
            {
                _logger.LogDebug("Connecting to Redis: {connectionString}", _connectionString);
            }

            _redis = ConnectionMultiplexer.Connect(_redisConnectionOptions);

            if (_redis == null || !_redis.IsConnected)
            {
                _logger.LogError("Wasn't able to connect to redis");

                // We weren't able to connect to Redis despite some retries with exponential backoff.
                throw new ApplicationException("Wasn't able to connect to redis");
            }

            _logger.LogInformation("Successfully connected to Redis");
            var cache = _redis.GetDatabase();

            _logger.LogDebug("Performing small test");
            cache.StringSet("cart", "OK" );
            object res = cache.StringGet("cart");

            if (_logger.IsEnabled(LogLevel.Debug))
            {
                _logger.LogDebug("Small test result: {result}", res);
            }

            _redis.InternalError += (_, e) => { Console.WriteLine(e.Exception); };
            _redis.ConnectionRestored += (_, _) =>
            {
                _isRedisConnectionOpened = true;
                _logger.LogInformation("Connection to redis was restored successfully.");
            };
            _redis.ConnectionFailed += (_, _) =>
            {
                _logger.LogInformation("Connection failed. Disposing the object");
                _isRedisConnectionOpened = false;
            };

            _isRedisConnectionOpened = true;
        }
    }

    public async Task AddItemAsync(string userId, string productId, int quantity)
    {
        var stopwatch = Stopwatch.StartNew();

        if (_logger.IsEnabled(LogLevel.Information))
        {
            _logger.LogInformation("AddItemAsync called with userId={userId}, productId={productId}, quantity={quantity}", userId, productId, quantity);
        }

        try
        {
            EnsureRedisConnected();

            var db = _redis.GetDatabase();

            // Access the cart from the cache
            var value = await db.HashGetAsync(userId, CartFieldName);

            Oteldemo.Cart cart;
            if (value.IsNull)
            {
                cart = new Oteldemo.Cart
                {
                    UserId = userId
                };
                cart.Items.Add(new Oteldemo.CartItem { ProductId = productId, Quantity = quantity });
            }
            else
            {
                cart = Oteldemo.Cart.Parser.ParseFrom(value);
                var existingItem = cart.Items.SingleOrDefault(i => i.ProductId == productId);
                if (existingItem == null)
                {
                    cart.Items.Add(new Oteldemo.CartItem { ProductId = productId, Quantity = quantity });
                }
                else
                {
                    existingItem.Quantity += quantity;
                }
            }

            await db.HashSetAsync(userId, new[]{ new HashEntry(CartFieldName, cart.ToByteArray()) });
            await db.KeyExpireAsync(userId, TimeSpan.FromMinutes(60));
            await TryDualWriteCartAsync(userId, cart.ToByteArray());
        }
        catch (Exception ex)
        {
            throw new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"));
        }
        finally
        {
            addItemHistogram.Record(stopwatch.Elapsed.TotalSeconds);
        }
    }

    public async Task EmptyCartAsync(string userId)
    {
        if (_logger.IsEnabled(LogLevel.Information))
        {
            _logger.LogInformation("EmptyCartAsync called with userId={userId}", userId);
        }
        try
        {
            EnsureRedisConnected();
            var db = _redis.GetDatabase();

            // Update the cache with empty cart for given user
            await db.HashSetAsync(userId, new[] { new HashEntry(CartFieldName, _emptyCartBytes) });
            await db.KeyExpireAsync(userId, TimeSpan.FromMinutes(60));
            await TryDualWriteCartAsync(userId, _emptyCartBytes);
        }
        catch (Exception ex)
        {
            throw new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"));
        }
    }

    public async Task<Oteldemo.Cart> GetCartAsync(string userId)
    {
        var stopwatch = Stopwatch.StartNew();

        if (_logger.IsEnabled(LogLevel.Information))
        {
            _logger.LogInformation("GetCartAsync called with userId={userId}", userId);
        }

        try
        {
            EnsureRedisConnected();

            var db = _redis.GetDatabase();

            // Access the cart from the cache
            var value = await db.HashGetAsync(userId, CartFieldName);

            if (!value.IsNull)
            {
                return Oteldemo.Cart.Parser.ParseFrom(value);
            }

            // We decided to return empty cart in cases when user wasn't in the cache before
            return new Oteldemo.Cart();
        }
        catch (Exception ex)
        {
            throw new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"));
        }
        finally
        {
            getCartHistogram.Record(stopwatch.Elapsed.TotalSeconds);
        }
    }

    public bool Ping()
    {
        try
        {
            var cache = _redis.GetDatabase();
            var res = cache.Ping();
            return res != TimeSpan.Zero;
        }
        catch (Exception)
        {
            return false;
        }
    }

    private static ConfigurationOptions BuildConnectionOptions(
        string address,
        bool useTls,
        string authToken,
        int connectRetry = RedisRetryNumber,
        int? timeoutMs = null)
    {
        var options = ConfigurationOptions.Parse(BuildBaseConnectionString(address, useTls));

        // Try to reconnect multiple times if the first retry fails.
        options.ConnectRetry = connectRetry;
        options.ReconnectRetryPolicy = new ExponentialRetry(1000);
        options.KeepAlive = 180;

        if (timeoutMs.HasValue)
        {
            options.ConnectTimeout = timeoutMs.Value;
            options.SyncTimeout = timeoutMs.Value;
            options.AsyncTimeout = timeoutMs.Value;
        }

        if (!string.IsNullOrWhiteSpace(authToken))
        {
            options.Password = authToken;
        }

        return options;
    }

    private static string BuildSafeConnectionString(string address, bool useTls, string authToken)
    {
        var connectionString = BuildBaseConnectionString(address, useTls);
        if (!string.IsNullOrWhiteSpace(authToken))
        {
            connectionString += ",password=***";
        }

        return connectionString;
    }

    private static string BuildBaseConnectionString(string address, bool useTls)
    {
        return $"{address},ssl={useTls.ToString().ToLowerInvariant()},allowAdmin=true,abortConnect=false";
    }

    private async Task TryDualWriteCartAsync(string userId, byte[] cartBytes)
    {
        if (!_isDualWriteEnabled)
        {
            return;
        }

        try
        {
            EnsureDualWriteRedisConnected();
            var db = _dualWriteRedis.GetDatabase();
            await db.HashSetAsync(userId, new[] { new HashEntry(CartFieldName, cartBytes) });
            await db.KeyExpireAsync(userId, TimeSpan.FromMinutes(60));
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Dual-write to Valkey target failed for userId={userId}. Primary cart write already succeeded.", userId);
        }
    }

    private void EnsureDualWriteRedisConnected()
    {
        if (_isDualWriteConnectionOpened)
        {
            return;
        }

        lock (_dualWriteLocker)
        {
            if (_isDualWriteConnectionOpened)
            {
                return;
            }

            if (_logger.IsEnabled(LogLevel.Debug))
            {
                _logger.LogDebug("Connecting to dual-write Redis target: {connectionString}", _dualWriteConnectionString);
            }

            _dualWriteRedis = ConnectionMultiplexer.Connect(_dualWriteConnectionOptions);

            if (_dualWriteRedis == null || !_dualWriteRedis.IsConnected)
            {
                throw new ApplicationException("Wasn't able to connect to dual-write redis target");
            }

            _dualWriteRedis.InternalError += (_, e) => { Console.WriteLine(e.Exception); };
            _dualWriteRedis.ConnectionRestored += (_, _) =>
            {
                _isDualWriteConnectionOpened = true;
                _logger.LogInformation("Connection to dual-write redis target was restored successfully.");
            };
            _dualWriteRedis.ConnectionFailed += (_, _) =>
            {
                _logger.LogWarning("Connection to dual-write redis target failed. Disposing the object");
                _isDualWriteConnectionOpened = false;
            };

            _isDualWriteConnectionOpened = true;
            _logger.LogInformation("Successfully connected to dual-write Redis target");
        }
    }
}

// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
package kafka

import (
	"fmt"
	"log/slog"
	"time"

	"github.com/IBM/sarama"
)

var (
	Topic           = "orders"
	ProtocolVersion = sarama.V3_0_0_0
)

type saramaLogger struct {
	logger *slog.Logger
}

func (l *saramaLogger) Printf(format string, v ...interface{}) {
	l.logger.Info(fmt.Sprintf(format, v...))
}
func (l *saramaLogger) Println(v ...interface{}) {
	l.logger.Info(fmt.Sprint(v...))
}
func (l *saramaLogger) Print(v ...interface{}) {
	l.logger.Info(fmt.Sprint(v...))
}

func CreateKafkaProducer(brokers []string, logger *slog.Logger) (sarama.SyncProducer, error) {
	// Set the logger for sarama to use.
	sarama.Logger = &saramaLogger{logger: logger}

	saramaConfig := sarama.NewConfig()
	saramaConfig.Producer.Return.Successes = true
	saramaConfig.Producer.Return.Errors = true

	// REL-09: order events are financial data - do NOT fire-and-forget.
	// The previous RequiredAcks=NoResponse silently swallowed failed messages,
	// so an order could be charged but never recorded (order lost with no trace).
	// WaitForAll makes the broker acknowledge before we consider the send done;
	// Idempotent + MaxOpenRequests=1 lets us retry safely without producing
	// duplicate order events.
	saramaConfig.Producer.RequiredAcks = sarama.WaitForAll
	saramaConfig.Producer.Retry.Max = 3
	saramaConfig.Producer.Idempotent = true
	saramaConfig.Net.MaxOpenRequests = 1

	// Bound how long a single produce call can block - fail fast instead of
	// hanging until the caller's context is cancelled (PlaceOrder awaits this
	// synchronously, so an unbounded wait here becomes checkout latency).
	saramaConfig.Producer.Timeout = 5 * time.Second

	saramaConfig.Version = ProtocolVersion

	// SyncProducer instead of AsyncProducer: PlaceOrder already awaits the
	// result of every publish synchronously (sendToPostProcessor has no `go`),
	// so there is no async benefit here - only risk. AsyncProducer's
	// Successes()/Errors() are channels shared by the WHOLE producer instance
	// (one per pod, reused by every concurrent PlaceOrder call); waiting on
	// them per-request races across goroutines, since Go delivers each value
	// to exactly one receiver with no correlation to which request produced
	// it. Under concurrent checkout traffic, a request's own ack can be
	// received by a *different* concurrent request's select (or lost to the
	// idle Errors()-draining goroutine below), leaving the original request
	// blocked until ctx.Done() - in practice until the caller's ~15s timeout,
	// which is exactly the symptom this was causing. SyncProducer.SendMessage
	// returns the result of that specific call directly, so there's nothing
	// to race on.
	producer, err := sarama.NewSyncProducer(brokers, saramaConfig)
	if err != nil {
		return nil, err
	}
	return producer, nil
}

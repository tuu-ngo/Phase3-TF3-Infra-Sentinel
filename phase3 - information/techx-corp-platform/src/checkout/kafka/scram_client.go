// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
package kafka

// SCRAM client cho sarama — Mandate #8: MSK dùng SASL/SCRAM-SHA-512.
// sarama KHÔNG có sẵn SCRAMClient, phải tự implement interface sarama.SCRAMClient
// bằng github.com/xdg-go/scram. Đây là pattern chuẩn từ example chính thức của sarama.
// Chỉ được dùng khi KAFKA_SECURITY_PROTOCOL bật SASL (xem producer.go) — mặc định tắt,
// nên file này không đổi hành vi hiện tại.

import (
	"crypto/sha512"

	"github.com/xdg-go/scram"
)

// SHA512 là hàm sinh hash cho SCRAM-SHA-512 (MSK mặc định dùng SHA-512).
var SHA512 scram.HashGeneratorFcn = sha512.New

// XDGSCRAMClient bọc scram.Client để thỏa interface sarama.SCRAMClient
// (Begin/Step/Done) mà sarama gọi trong quá trình SASL handshake.
type XDGSCRAMClient struct {
	*scram.Client
	*scram.ClientConversation
	scram.HashGeneratorFcn
}

// Begin khởi tạo hội thoại SCRAM với credential.
func (x *XDGSCRAMClient) Begin(userName, password, authzID string) (err error) {
	x.Client, err = x.HashGeneratorFcn.NewClient(userName, password, authzID)
	if err != nil {
		return err
	}
	x.ClientConversation = x.Client.NewConversation()
	return nil
}

// Step xử lý một bước challenge/response của SCRAM.
func (x *XDGSCRAMClient) Step(challenge string) (response string, err error) {
	response, err = x.ClientConversation.Step(challenge)
	return
}

// Done báo hội thoại SCRAM đã hoàn tất.
func (x *XDGSCRAMClient) Done() bool {
	return x.ClientConversation.Done()
}

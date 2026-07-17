#!/usr/bin/env bash
# Build product-reviews app image multi-arch (amd64+arm64) từ source và push
# lên Docker Hub: nghiadaulau/techx-corp:1.0-product-reviews  (PUBLIC).
# Prereq: docker + buildx + QEMU; đã: docker login -u nghiadaulau
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../techx-corp-platform"
[ -f .env.override ] || { echo "missing .env.override"; exit 1; }

# Đọc cấu hình từ .env.override hoặc mặc định
IMAGE_NAME=$(grep -E "^IMAGE_NAME=" .env.override | cut -d'=' -f2 | tr -d '"' | tr -d "'")
DEMO_VERSION=$(grep -E "^DEMO_VERSION=" .env.override | cut -d'=' -f2 | tr -d '"' | tr -d "'")

IMAGE_NAME=${IMAGE_NAME:-nghiadaulau/techx-corp}
DEMO_VERSION=${DEMO_VERSION:-1.0}

TARGET_IMAGE="${IMAGE_NAME}:${DEMO_VERSION}-product-reviews"

echo ">> TARGET_IMAGE: ${TARGET_IMAGE}"

# builder multi-arch (one-time)
docker buildx create --name techx-corp-builder --bootstrap --use --driver docker-container || true

# build + push multi-arch cho duy nhất product-reviews
echo ">> Build and push multi-arch image (amd64+arm64) for product-reviews"
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "${TARGET_IMAGE}" \
  -f src/product-reviews/Dockerfile \
  --push .

echo "done -> ${TARGET_IMAGE}"

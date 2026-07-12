#!/usr/bin/env bash
set -euo pipefail

# Build every service image and push to a registry so another machine can
# pull-and-run with deploy/docker-compose.yml (no source needed on the target).
#
# Usage (from anywhere):
#   IMAGE_PREFIX=ghcr.io/phdwight IMAGE_TAG=latest ./deploy/push-images.sh
#
# Optional:
#   PLATFORMS=linux/amd64,linux/arm64   # default: linux/amd64 (typical cloud VM)
#
# Prereq: log in to the registry first, e.g.
#   echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin

IMAGE_PREFIX="${IMAGE_PREFIX:-ghcr.io/phdwight}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64}"

# repo root = parent of this script's directory
cd "$(dirname "$0")/.."

builder="insurance-builder"
docker buildx inspect "$builder" >/dev/null 2>&1 || docker buildx create --name "$builder" --use
docker buildx use "$builder"

# Python services all share Dockerfile.python via the SERVICE build-arg.
# 'migrate' is the db package (runs Alembic migrations).
py_services="migrate:db api:api agent:agent mcp-server:mcp-server ingestion:ingestion"

for pair in $py_services; do
  name="${pair%%:*}"
  svc="${pair##*:}"
  extra=()
  [ "$name" = "ingestion" ] && extra=(--build-arg APT_PACKAGES="libgl1 libglib2.0-0")
  echo "==> building $name (SERVICE=$svc) for $PLATFORMS"
  docker buildx build \
    --platform "$PLATFORMS" \
    -f Dockerfile.python \
    --build-arg SERVICE="$svc" \
    "${extra[@]}" \
    -t "$IMAGE_PREFIX/insurance-$name:$IMAGE_TAG" \
    --push .
done

echo "==> building pwa for $PLATFORMS"
docker buildx build \
  --platform "$PLATFORMS" \
  -f pwa/Dockerfile \
  -t "$IMAGE_PREFIX/insurance-pwa:$IMAGE_TAG" \
  --push ./pwa

echo "Done. Pushed ${IMAGE_PREFIX}/insurance-{migrate,api,agent,mcp-server,ingestion,pwa}:${IMAGE_TAG} ($PLATFORMS)"

#!/usr/bin/env bash
set -euo pipefail

# Build every service image and push to a registry so another machine can
# pull-and-run with docker-compose.prod.yml (no source needed on the target).
#
# CI publishes these automatically on merge to main
# (.github/workflows/publish-images.yml); this script is the manual/local
# alternative (e.g. to publish from a feature branch or without Actions).
#
# Usage (from anywhere):
#   IMAGE_PREFIX=ghcr.io/phdwight IMAGE_TAG=latest ./deploy/push-images.sh
#
# Optional:
#   PLATFORMS=linux/amd64   # override to build a single arch (faster)
#     default: linux/amd64,linux/arm64 — covers x86 cloud VMs and ARM hosts
#     (Apple Silicon, ARM NAS like Synology, Raspberry Pi, Ampere/Graviton).
#
# Prereq: log in to the registry first, e.g.
#   echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin

IMAGE_PREFIX="${IMAGE_PREFIX:-ghcr.io/phdwight}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

# repo root = parent of this script's directory
cd "$(dirname "$0")/.."

# Preflight: these images are PUBLIC. A local build sends the working tree as
# the build context, so a .dockerignore that stops excluding secrets would bake
# a real .env into every published image (this happened once, before
# .dockerignore existed — the images were public with live keys). Refuse to
# publish unless the context genuinely excludes it.
if [ -f .env ]; then
  probe=$(mktemp -d)
  printf 'FROM busybox\nCOPY . /ctx\nRUN test ! -e /ctx/.env\n' > "$probe/Dockerfile"
  if ! docker build -q -f "$probe/Dockerfile" -t insurance-secret-probe . >/dev/null 2>&1; then
    rm -rf "$probe"
    echo "ABORT: .env is reachable in the Docker build context — it would be baked" >&2
    echo "       into published images. Fix .dockerignore before publishing." >&2
    exit 1
  fi
  docker rmi -f insurance-secret-probe >/dev/null 2>&1 || true
  rm -rf "$probe"
  echo "==> preflight OK: .env is excluded from the build context"
fi

# Same stamp CI bakes, so a manually published image is identifiable too.
date -u +%Y%m%d%H%M > BUILD_ID
trap 'rm -f BUILD_ID' EXIT

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
    "${extra[@]+"${extra[@]}"}" \
    -t "$IMAGE_PREFIX/insurance-$name:$IMAGE_TAG" \
    --push .
done

# pwa ships the production image (static build served by nginx), NOT the dev
# Dockerfile (Vite dev server).
echo "==> building pwa for $PLATFORMS"
docker buildx build \
  --platform "$PLATFORMS" \
  -f pwa/Dockerfile.prod \
  -t "$IMAGE_PREFIX/insurance-pwa:$IMAGE_TAG" \
  --push ./pwa

echo "Done. Pushed ${IMAGE_PREFIX}/insurance-{migrate,api,agent,mcp-server,ingestion,pwa}:${IMAGE_TAG} ($PLATFORMS)"

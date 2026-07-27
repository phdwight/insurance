#!/bin/sh
# Rendered by nginx's own entrypoint (files in /docker-entrypoint.d/ run before
# nginx starts). Writes the per-host API URL into config.js so one built image
# serves any environment — the browser reads window.__APP_CONFIG__ before the
# app bundle loads.
set -eu

: "${VITE_API_URL:=http://localhost:8000}"
: "${VITE_INGESTION_URL:=}"  # public ingestion base for brochure images; empty = feature off
# The release this container was deployed as (compose passes $IMAGE_TAG). The
# bundle has a version compiled in at BUILD time, but selective rebuilds mean an
# unchanged pwa image gets re-tagged into later releases — so the baked number
# goes stale while the tag moves on. config.js is rendered per-container and is
# excluded from the service-worker precache, so it is the one channel that can
# tell a static bundle which release it is actually running.
: "${APP_VERSION:=}"
root="/usr/share/nginx/html"
target="$root/config.js"

cat > "$target" <<EOF
window.__APP_CONFIG__ = { API_URL: "${VITE_API_URL}", INGESTION_URL: "${VITE_INGESTION_URL}", APP_VERSION: "${APP_VERSION}" };
EOF

# Keep GET /VERSION consistent with what the footer shows.
if [ -n "$APP_VERSION" ]; then
  printf '%s' "$APP_VERSION" > "$root/VERSION"
fi

echo "[pwa] rendered ${target} -> API_URL=${VITE_API_URL} INGESTION_URL=${VITE_INGESTION_URL} APP_VERSION=${APP_VERSION:-<baked>}"

#!/bin/sh
# Rendered by nginx's own entrypoint (files in /docker-entrypoint.d/ run before
# nginx starts). Writes the per-host API URL into config.js so one built image
# serves any environment — the browser reads window.__APP_CONFIG__ before the
# app bundle loads.
set -eu

: "${VITE_API_URL:=http://localhost:8000}"
target="/usr/share/nginx/html/config.js"

cat > "$target" <<EOF
window.__APP_CONFIG__ = { API_URL: "${VITE_API_URL}" };
EOF

echo "[pwa] rendered ${target} -> API_URL=${VITE_API_URL}"

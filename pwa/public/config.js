// Runtime configuration, loaded before the app bundle.
//
// Local dev + the build output ship this empty default, so the app falls back
// to import.meta.env.VITE_API_URL (dev) or the localhost default (api.ts).
//
// In production this file is REGENERATED at container start from $VITE_API_URL
// by pwa/docker-entrypoint.sh, which is why it is excluded from the service
// worker precache (vite.config.ts globIgnores) and served no-store (nginx.conf)
// — a rebuilt image must never be pinned to a stale API URL.
window.__APP_CONFIG__ = {};

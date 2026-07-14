import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// Build stamp: YYYYMMDDHHmm, 24-hour UTC, computed when `vite build` runs and
// injected as the __BUILD_ID__ global (shown in the app footer). UTC so a local
// build and a CI build read consistently.
const p = (n: number) => String(n).padStart(2, "0");
const d = new Date();
const buildId =
  `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}` +
  `${p(d.getUTCHours())}${p(d.getUTCMinutes())}`;

export default defineConfig({
  define: {
    __BUILD_ID__: JSON.stringify(buildId),
  },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["apple-touch-icon.png"],
      manifest: {
        name: "Safe Harbor — Insurance Concierge",
        short_name: "Safe Harbor",
        description:
          "Describe what you want to protect — get matching insurance policies, compared and explained.",
        theme_color: "#1f4b3a",
        background_color: "#e9ece8",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        // config.js is rendered per-host at container start — never precache it,
        // or the SW would pin the app to a stale API URL.
        globIgnores: ["config.js", "**/config.js"],
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
  },
});

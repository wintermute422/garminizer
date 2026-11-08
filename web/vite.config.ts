/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const API = process.env.GARMINIZER_API ?? "http://127.0.0.1:8420";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5180,
    strictPort: true,
    watch: { ignored: ["**/playwright-report/**", "**/test-results/**", "**/e2e/**"] },
    proxy: { "/api": { target: API, changeOrigin: false } },
  },
  worker: { format: "es" },
  preview: { port: 5181, strictPort: true, proxy: { "/api": API } },
  build: {
    target: "es2022",
    sourcemap: true,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes("node_modules/echarts") || id.includes("node_modules/zrender"))
            return "echarts";
          if (id.includes("node_modules/maplibre-gl")) return "maplibre";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/compras_crawler/web/static", emptyOutDir: true },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        configure: (proxy) =>
          proxy.on("proxyReq", (request) =>
            request.setHeader("Origin", "http://127.0.0.1:8000"),
          ),
      },
    },
  },
});

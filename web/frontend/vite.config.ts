import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// 前端作为后端静态产物挂载：base 用相对路径，适配任意托管前缀。
export default defineConfig({
  base: "./",
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8300",
        changeOrigin: true,
      },
      "/openapi.json": {
        target: "http://127.0.0.1:8300",
        changeOrigin: true,
      },
    },
  },
});
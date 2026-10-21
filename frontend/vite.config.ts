import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 관리자 SPA의 직접 진입/새로고침도 관리자 HTML을 사용한다.
// 별도 문서로 열어 Tailwind reset·전역 테마가 고객 화면에 섞이지 않게 한다.
const adminEntry: Plugin = {
  name: "admin-entry",
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      const url = new URL(req.url || "/", "http://localhost");
      if (url.pathname === "/admin" || url.pathname.startsWith("/admin/")) {
        req.url = "/admin/index.html" + url.search;
      }
      next();
    });
  },
  configurePreviewServer(server) {
    server.middlewares.use((req, _res, next) => {
      const url = new URL(req.url || "/", "http://localhost");
      if (url.pathname === "/admin" || url.pathname.startsWith("/admin/")) {
        req.url = "/admin/index.html" + url.search;
      }
      next();
    });
  },
};

// 개발 중에는 /api 요청을 로컬 FastAPI(8000)로 넘긴다. 배포에서는 Nginx가 같은 일을 한다.
export default defineConfig({
  plugins: [adminEntry, react(), tailwindcss()],
  resolve: {
    alias: { "@admin": fileURLToPath(new URL("./src/admin", import.meta.url)) },
  },
  build: {
    rollupOptions: {
      input: {
        customer: fileURLToPath(new URL("./index.html", import.meta.url)),
        admin: fileURLToPath(new URL("./admin/index.html", import.meta.url)),
      },
    },
  },
  server: { proxy: { "/api": "http://localhost:8000" } },
});

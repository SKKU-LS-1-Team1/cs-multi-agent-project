import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv, type Plugin } from "vite";
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

// 개발 중에는 /api 요청을 VITE_API_TARGET(기본 로컬 FastAPI 8000)으로 넘긴다. 배포에서는 Nginx가 같은 일을 한다.
// GCP에 올린 백엔드로 화면만 로컬에서 띄울 때: frontend/.env.local 에 VITE_API_TARGET=http://<VM 외부 IP> (frontend/.env.example 참고)
// 요청은 Vite 개발 서버가 대신 보내므로 브라우저 입장에서는 같은 출처라 CORS 설정이 필요 없다.
export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), "VITE_").VITE_API_TARGET || "http://localhost:8000";
  return {
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
    server: { proxy: { "/api": { target, changeOrigin: true } } },
  };
});

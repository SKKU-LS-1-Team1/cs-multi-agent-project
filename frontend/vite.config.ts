import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 개발 중에는 /api 요청을 VITE_API_TARGET(기본 로컬 FastAPI 8000)으로 넘긴다. 배포에서는 Nginx가 같은 일을 한다.
// GCP에 올린 백엔드로 화면만 로컬에서 띄울 때: frontend/.env.local 에 VITE_API_TARGET=http://<VM 외부 IP> (frontend/.env.example 참고)
// 요청은 Vite 개발 서버가 대신 보내므로 브라우저 입장에서는 같은 출처라 CORS 설정이 필요 없다.
export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), "VITE_").VITE_API_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    server: { proxy: { "/api": { target, changeOrigin: true } } },
  };
});

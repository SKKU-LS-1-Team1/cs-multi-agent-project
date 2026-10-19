import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 중에는 /api 요청을 로컬 FastAPI(8000)로 넘긴다. 배포에서는 Nginx가 같은 일을 한다.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});

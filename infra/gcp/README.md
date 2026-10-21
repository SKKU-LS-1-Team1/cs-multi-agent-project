# GCP VM · 도메인 · HTTPS (CSA-46 · 김동규)

기획서 9.1: Compute Engine VM 1대 + Docker Compose. 고객과 상담원은 HTTPS로 같은 도메인에 접속한다.

## 1. VM
- e2-standard-4 (4 vCPU, 16GB) · Ubuntu 24.04 · 디스크 50GB
- 방화벽: 80, 443 허용
- Docker, Docker Compose 설치 후 저장소 clone, `.env` 작성

## 2. 도메인
- 고정 외부 IP 예약 → 도메인 A 레코드 연결

## 3. HTTPS
- TODO: certbot(webroot)으로 인증서 발급, `infra/nginx/nginx.conf`에 443 블록 추가, 자동 갱신 cron

## 4. 배포
- `.github/workflows/deploy.yml` (CSA-47): 저장소 Variables `DEPLOY_ENABLED=true`,
  Secrets `GCP_VM_HOST`, `GCP_VM_USER`, `GCP_VM_SSH_KEY` 를 넣으면 main 머지마다 배포된다.

## 5. 화면만 로컬에서 띄워 GCP 백엔드로 시험하기
- `cp frontend/.env.example frontend/.env.local` 후 `VITE_API_TARGET=http://<VM 외부 IP>` (도메인이 붙으면 `https://도메인`)
- `cd frontend && npm install && npm run dev` → http://localhost:5173 . `/api` 요청은 Vite가 VM의 Nginx(80)로 넘긴다.
- 브라우저는 localhost:5173 하고만 통신하므로 CORS 설정은 필요 없다. 바꾼 화면 코드는 바로 반영되고, VM은 다시 배포하지 않아도 된다.
- 아직 API에 로그인이 없으므로 상담원 API(`/api/tickets` 등)가 인터넷에 열린다. 시험 기간에는 VM 방화벽의 80 포트를 팀원 IP로만 열어 둔다.

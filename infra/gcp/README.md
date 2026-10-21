# GCP VM · 도메인 · HTTPS (CSA-46 · 김동규)

기획서 9.1: Compute Engine VM 1대 + Docker Compose. 고객과 상담원은 HTTPS로 같은 도메인에 접속한다.

## 1. VM
- e2-standard-4 (4 vCPU, 16GB) · Ubuntu 24.04 · 디스크 50GB
- 방화벽: 80, 443 허용
- Docker, Docker Compose 설치 후 저장소 clone, `.env` 작성

## 2. 도메인 (`luckystar-global-cs.com`, Namecheap)
- VM 외부 IP를 고정으로 바꾼다: VPC 네트워크 → IP 주소 → VM의 외부 IP → "정적 IP 주소로 승격"
- Namecheap → Domain List → Manage → Advanced DNS
  - 기본으로 들어 있는 `CNAME www → parkingpage...`, `URL Redirect @` 레코드 삭제
  - `A Record` / Host `@` / Value `<고정 IP>` / TTL Automatic
  - `A Record` / Host `www` / Value `<고정 IP>` / TTL Automatic
- 확인: `nslookup luckystar-global-cs.com` 이 고정 IP를 돌려주면 된다 (보통 5~30분)

## 3. HTTPS (Caddy 자동 인증서)
- 바깥 요청은 `caddy` 컨테이너가 80/443으로 받아 `nginx`로 넘긴다 (`infra/caddy/Caddyfile`).
- VM의 `.env`에 `DOMAIN=luckystar-global-cs.com www.luckystar-global-cs.com` 을 넣고 `docker compose up -d --build`.
  Caddy가 Let's Encrypt 인증서를 받고, 갱신과 http→https 이동도 알아서 한다. certbot·cron 은 필요 없다.
- 인증서를 받으려면 80, 443 포트가 **모든 IP(0.0.0.0/0)** 에 열려 있어야 한다. 팀원 IP로만 막아 두면 발급이 실패한다.
- 잘 안 되면 `docker compose logs caddy` 를 본다. 인증서는 `caddy_data` 볼륨에 저장되니 볼륨을 지우지 않는다.
- 로컬은 `DOMAIN` 을 비워 두면 지금처럼 http://localhost 로 뜬다.

## 4. 배포
- `.github/workflows/deploy.yml` (CSA-47): 저장소 Variables `DEPLOY_ENABLED=true`,
  Secrets `GCP_VM_HOST`, `GCP_VM_USER`, `GCP_VM_SSH_KEY` 를 넣으면 main 머지마다 배포된다.

## 5. 화면만 로컬에서 띄워 GCP 백엔드로 시험하기
- `cp frontend/.env.example frontend/.env.local` 후 `VITE_API_TARGET=https://luckystar-global-cs.com` (도메인 전에는 `http://<VM 외부 IP>`)
- `cd frontend && npm install && npm run dev` → http://localhost:5173 . `/api` 요청은 Vite가 VM의 Nginx(80)로 넘긴다.
- 브라우저는 localhost:5173 하고만 통신하므로 CORS 설정은 필요 없다. 바꾼 화면 코드는 바로 반영되고, VM은 다시 배포하지 않아도 된다.
- 아직 API에 로그인이 없으므로 상담원 API(`/api/tickets` 등)가 인터넷에 열린다. HTTPS 인증서 때문에 80/443은 모두에게 열어야 하니, 도메인 주소를 외부에 공유하지 않는다.

# GCP VM · 도메인 · HTTPS (CSA-46 · 김동규)

기획서 9.1: Compute Engine VM 1대 + Docker Compose. 고객과 상담원은 HTTPS로 같은 도메인에 접속한다.

## 1. VM
- e2-standard-4 (4 vCPU, 16GB) · Ubuntu 24.04 · 디스크 50GB
- 방화벽: 80, 443 허용
- Docker, Docker Compose 설치 후 저장소 clone, `.env` 작성

## 2. 도메인 — `luckystar-global-cs.com` (Namecheap)
- VM 외부 IP 를 **고정 IP 로 예약**한다 (VPC 네트워크 → IP 주소). 기본 IP 는 재시작하면 바뀔 수 있다.
- Namecheap → Domain List → Manage → Advanced DNS 에 A 레코드 2개 (값 = 고정 IP)

  | Host | 주소 | 화면 |
  |---|---|---|
  | `@` | `https://luckystar-global-cs.com` | 고객 (챗봇·제품·문의하기·내 문의 내역) |
  | `admin` | `https://admin.luckystar-global-cs.com` | 관리자 (Basic Auth) |

- 확인: `dig +short luckystar-global-cs.com admin.luckystar-global-cs.com` 가 고정 IP 를 돌려준다

## 3. HTTPS (Let's Encrypt)
VM 의 저장소 폴더에서 한 번:
```bash
echo "DOMAIN=luckystar-global-cs.com" >> .env
bash infra/gcp/admin-password.sh <아이디>      # 관리자 화면 Basic Auth (비밀번호는 팀에만 공유)
bash infra/gcp/issue-cert.sh <이메일>          # 인증서 발급 → nginx 가 HTTPS 로 바뀐다
```
- nginx 는 시작할 때 설정을 고른다 (`infra/nginx/select-conf.sh`): `DOMAIN` 과 인증서가 있으면 HTTPS,
  없으면 HTTP (로컬 개발과 첫 발급 전). HTTP 모드는 예전처럼 한 주소에서 `/` 고객, `/admin/` 관리자.
- HTTPS 모드
  - 고객 도메인은 고객 API 만 연다: `/api/chat` · `/api/products` · `/api/inquiries` · `/api/health`.
    `/api/tickets`(작업 목록·승인·배정)·`/api/agents`·`/api/dashboard` 는 404 — 로그인이 아직 없어서
    상담원 API 를 공개 주소에 열면 누구나 부를 수 있다. 고객 화면은 문의·회신을 `/api/inquiries` 로 보낸다.
  - 관리자 도메인은 전체가 Basic Auth 뒤에 있고 모든 API 를 쓴다. `/` 는 `/admin/` 으로.
  - 고객 도메인의 `/admin` 은 관리자 도메인으로 넘긴다. 80 포트는 HTTPS 로 넘긴다.
- 갱신: `certbot` 컨테이너가 12시간마다 `certbot renew`, nginx 는 6시간마다 인증서를 다시 읽는다.
- 인증서·비밀번호(`infra/certbot/`, `infra/nginx/auth/`)는 git 에 올리지 않는다. 배포(`git reset --hard`)
  해도 지워지지 않는다.
- 방화벽: 80(발급·갱신 확인, HTTPS 로 넘김)·443 을 연다.

## 4. 배포
- `.github/workflows/deploy.yml` (CSA-47): 저장소 Variables `DEPLOY_ENABLED=true`,
  Secrets `GCP_VM_HOST`, `GCP_VM_USER`, `GCP_VM_SSH_KEY` 를 넣으면 main 머지마다 배포된다.

## 5. 화면만 로컬에서 띄워 GCP 백엔드로 시험하기
- `cp frontend/.env.example frontend/.env.local` 후 `VITE_API_TARGET=http://<VM 외부 IP>` (도메인이 붙으면 `https://도메인`)
- `cd frontend && npm install && npm run dev` → http://localhost:5173 . `/api` 요청은 Vite가 VM의 Nginx(80)로 넘긴다.
- 브라우저는 localhost:5173 하고만 통신하므로 CORS 설정은 필요 없다. 바꾼 화면 코드는 바로 반영되고, VM은 다시 배포하지 않아도 된다.
- 아직 API에 로그인이 없으므로 상담원 API(`/api/tickets` 등)가 인터넷에 열린다. 시험 기간에는 VM 방화벽의 80 포트를 팀원 IP로만 열어 둔다.

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

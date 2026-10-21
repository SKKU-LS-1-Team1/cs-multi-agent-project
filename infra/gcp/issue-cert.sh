#!/usr/bin/env bash
# 첫 HTTPS 인증서 발급 (CSA-46). VM 의 저장소 폴더에서 한 번:
#   bash infra/gcp/issue-cert.sh <만료 알림 받을 이메일>
# 먼저: .env 에 DOMAIN, DNS A 레코드(@ · admin → VM 고정 IP), 관리자 비밀번호(admin-password.sh)
# 이후 갱신은 docker compose 의 certbot 컨테이너가 12시간마다 확인한다.
set -euo pipefail
EMAIL=${1:?"사용법: bash infra/gcp/issue-cert.sh <이메일>"}
DOMAIN=$(grep -E '^DOMAIN=' .env | tail -1 | cut -d= -f2- | tr -d '"' || true)
[ -n "$DOMAIN" ] || { echo ".env 에 DOMAIN=<도메인> 을 넣는다" >&2; exit 1; }
[ -s infra/nginx/auth/admin.htpasswd ] || {
    echo "관리자 비밀번호를 먼저 만든다: bash infra/gcp/admin-password.sh <아이디>" >&2; exit 1; }
mkdir -p infra/certbot/conf infra/certbot/www

docker compose up -d --build nginx  # 인증서가 없으니 HTTP 모드 (발급 확인 파일을 내준다)
docker compose run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
    -d "$DOMAIN" -d "admin.$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email --non-interactive
docker compose up -d certbot
docker compose restart nginx        # 인증서가 생겼으니 HTTPS 모드
docker compose logs --tail 3 nginx
echo "고객: https://$DOMAIN   관리자: https://admin.$DOMAIN"

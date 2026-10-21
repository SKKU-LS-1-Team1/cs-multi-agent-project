#!/bin/sh
# nginx 설정 고르기 (CSA-46). 공식 이미지가 nginx 를 띄우기 전에 /docker-entrypoint.d 에서 실행한다.
# - DOMAIN 이 있고 그 인증서가 있으면 HTTPS 설정 (고객/관리자 도메인 분리, 관리자 Basic Auth)
# - 아니면 HTTP 설정 (로컬 개발, 첫 인증서 발급 전)
# 인증서를 처음 받은 뒤에는 `docker compose restart nginx` 로 HTTPS 로 바뀐다.
set -e
SRC=/etc/nginx/cs-agent
CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

if [ -n "$DOMAIN" ] && [ -f "$CERT" ]; then
    if [ ! -s /etc/nginx/auth/admin.htpasswd ]; then
        echo "nginx: 관리자 비밀번호 파일이 없다 — bash infra/gcp/admin-password.sh <아이디>" >&2
        exit 1
    fi
    envsubst '${DOMAIN}' < "$SRC/https.conf.template" > /etc/nginx/conf.d/default.conf
    echo "nginx: HTTPS (${DOMAIN}, admin.${DOMAIN})"
    # certbot 컨테이너가 갱신한 인증서를 6시간마다 다시 읽는다
    (while :; do sleep 21600; nginx -s reload; done) &
else
    cp "$SRC/http.conf.template" /etc/nginx/conf.d/default.conf
    echo "nginx: HTTP (인증서 없음${DOMAIN:+ — ${DOMAIN}})"
fi

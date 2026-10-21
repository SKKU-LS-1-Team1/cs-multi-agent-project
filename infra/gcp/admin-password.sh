#!/usr/bin/env bash
# 관리자 화면(admin.<도메인>) Basic Auth 계정 만들기 (CSA-46). VM 의 저장소 폴더에서:
#   bash infra/gcp/admin-password.sh <아이디>      → 비밀번호를 묻는다
# infra/nginx/auth/admin.htpasswd 에 저장한다 (git 에 올리지 않음). 바꾼 뒤 docker compose restart nginx
set -euo pipefail
ADMIN_USER=${1:?"사용법: bash infra/gcp/admin-password.sh <아이디>"}
read -rsp "비밀번호: " PASSWORD; echo
[ -n "$PASSWORD" ] || { echo "비밀번호가 비었다" >&2; exit 1; }
mkdir -p infra/nginx/auth
printf '%s' "$PASSWORD" | docker run --rm -i httpd:2.4-alpine htpasswd -niB "$ADMIN_USER" \
  > infra/nginx/auth/admin.htpasswd
echo "저장: infra/nginx/auth/admin.htpasswd ($ADMIN_USER)"

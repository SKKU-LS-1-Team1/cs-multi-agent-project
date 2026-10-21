# React 빌드 + Nginx (CSA-44 · CSA-46). 화면 요청은 React 정적 파일로, /api 는 FastAPI로 넘긴다.
# 설정은 시작할 때 select-conf.sh 가 고른다 (인증서 있으면 HTTPS, 없으면 HTTP).
FROM node:22-alpine AS build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine
RUN rm -f /etc/nginx/conf.d/default.conf
COPY infra/nginx/conf/api-proxy.conf /etc/nginx/snippets/api-proxy.conf
COPY infra/nginx/conf/http.conf.template infra/nginx/conf/https.conf.template /etc/nginx/cs-agent/
COPY --chmod=755 infra/nginx/select-conf.sh /docker-entrypoint.d/40-select-conf.sh
COPY --from=build /web/dist /usr/share/nginx/html

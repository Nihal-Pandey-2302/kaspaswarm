# KaspaSwarm frontend — build the Vite app, serve it with nginx which also
# reverse-proxies /api and /ws to the backend (so the app works same-origin,
# no build-time URL config needed).
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

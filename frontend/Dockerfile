# syntax=docker/dockerfile:1
# Workbench UI. Built by .github/workflows/build-images.yml with frontend/ as context.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Runs as uid 101 on 8080; writable paths are /tmp only (the chart mounts an emptyDir).
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/40-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh
COPY --from=build /src/dist /usr/share/nginx/html
# The image's public/config.js is the dev stub; nginx serves /tmp/config.js instead.
RUN rm -f /usr/share/nginx/html/config.js
EXPOSE 8080

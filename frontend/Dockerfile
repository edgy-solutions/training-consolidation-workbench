# syntax=docker/dockerfile:1
# Workbench UI. Built by .github/workflows/build-images.yml with frontend/ as context.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# public/config.js is the dev stub; in the image nginx serves /tmp/config.js instead.
RUN npm run build && rm -f dist/config.js

# Runs as uid 101 on 8080; writable paths are /tmp only (the chart mounts an emptyDir).
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/40-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080

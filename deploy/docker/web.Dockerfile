# syntax=docker/dockerfile:1

ARG NODE_IMAGE=node:22-slim
ARG NGINX_IMAGE=nginx:1.27-alpine

FROM ${NODE_IMAGE} AS build
RUN npm install -g pnpm@12.3.4
WORKDIR /src
COPY web-next/package.json web-next/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY web-next/ ./
RUN pnpm build

FROM ${NGINX_IMAGE} AS runtime
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80

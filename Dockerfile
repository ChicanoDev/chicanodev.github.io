# syntax=docker/dockerfile:1

# ---- Build stage -----------------------------------------------------------
# Node exists here only to compile the site. It never reaches the final image.
# Pinned to the same version as .node-version, by digest, so a rebuild next
# year produces the same toolchain.
FROM node:24.14.1-alpine@sha256:8510330d3eb72c804231a834b1a8ebb55cb3796c3e4431297a24d246b8add4d5 AS build
WORKDIR /app

# Dependencies first: this layer is cached until the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY astro.config.ts tsconfig.json ./
COPY public ./public
COPY src ./src

ARG REF=dev
ARG COMMIT=unknown
# Which posts are published is decided by BUILD_NOW (see src/lib/publishing.ts).
# CI passes it explicitly so a build is repeatable; with no value the build
# stamps the current time once, so /version.json always says what was used.
ARG BUILD_NOW=""
RUN export BUILD_NOW="${BUILD_NOW:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}" \
 && npm run build \
 && node -e ' \
      const fs = require("node:fs"); \
      const published = fs.readdirSync("dist/posts", { withFileTypes: true }) \
        .filter((e) => e.isDirectory()).map((e) => e.name).sort(); \
      const { REF, COMMIT, BUILD_NOW } = process.env; \
      fs.writeFileSync("dist/version.json", JSON.stringify({ ref: REF, commit: COMMIT, buildNow: BUILD_NOW, published }) + "\n"); \
    ' \
 && rm -f dist/CNAME dist/.nojekyll

# ---- Runtime stage ---------------------------------------------------------
# nginx-unprivileged: official nginx build that runs as uid 101 on port 8080
# and keeps its pid/temp files in /tmp, so the root filesystem can be read-only.
FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03

# Links the GHCR package to this repository, so the workflows' GITHUB_TOKEN may push it.
LABEL org.opencontainers.image.source="https://github.com/ChicanoDev/chicanodev.github.io" \
      org.opencontainers.image.description="ChicanoDev static site (nginx-unprivileged)" \
      org.opencontainers.image.licenses="MIT"

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY deploy/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html

USER 101
EXPOSE 8080

# Docker-only convenience; Kubernetes uses its own probes (see deploy/k8s).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO /dev/null http://127.0.0.1:8080/healthz || exit 1

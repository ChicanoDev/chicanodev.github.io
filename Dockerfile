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

# Everything in the site that depends on "what time is it" (which posts are
# published yet) reads BUILD_NOW. Passing it in, instead of calling the clock
# inside the build, makes a build repeatable and testable.
ARG BUILD_NOW=""
ENV BUILD_NOW=${BUILD_NOW}
RUN npm run build

# Build provenance, served at /version.json. Written after the build so a new
# commit hash does not invalidate the (slow) build layer above.
ARG REF=dev
ARG COMMIT=unknown
RUN printf '{"ref":"%s","commit":"%s","buildNow":"%s"}\n' "$REF" "$COMMIT" "$BUILD_NOW" > dist/version.json \
 && rm -f dist/CNAME dist/.nojekyll

# ---- Runtime stage ---------------------------------------------------------
# nginx-unprivileged: official nginx build that runs as uid 101 on port 8080
# and keeps its pid/temp files in /tmp, so the root filesystem can be read-only.
FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY deploy/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html

USER 101
EXPOSE 8080

# Docker-only convenience; Kubernetes uses its own probes (see deploy/k8s).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO /dev/null http://127.0.0.1:8080/healthz || exit 1

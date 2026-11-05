# Migration decision log

Running record of decisions and surprises while moving chicanodev.com from
GitHub Pages to the k3s cluster. It is source material for the blog series, so
it records what actually happened, including the mistakes. Newest at the bottom.

## 2026-11-04: Discovery

- **Pages already worked, and had two real problems:** `https://www.chicanodev.com`
  fails TLS (no certificate for `www`) and plain `http://` does not redirect to
  HTTPS. Both DNS records are DNS-only (not proxied by Cloudflare).
- **No future-date filtering existed.** `getPosts()` (`src/lib/posts.ts`) only
  dropped `draft: true`, and only in production builds. A future `date` alone
  did nothing. Series Part 5 material.
- **Convention in this cluster:** each app keeps its own manifests and Argo CD
  `Application` in its own repo (`deploy/k8s`, Kustomize). `gv5-k8s` holds only
  platform pieces and templates. We follow that.
- **AOP is opt-in per Ingress**, not global. Annotation
  `traefik.ingress.kubernetes.io/router.tls.options: default-cloudflare-aop@kubernetescrd`
  is what enforces it, so it must be verified, not assumed.
- **No monitoring stack in the cluster.** Deferred on purpose; it will be a
  cluster-wide project, not a chicanodev-only one.
- **ARC runners are not used.** They are scoped to the `GV5-Tech` org, run
  Docker-in-Docker (privileged), and this repo is in the `ChicanoDev` org.
  GitHub-hosted runners keep untrusted PR code away from the cluster.

## 2026-11-04: Decisions (confirmed by Dave)

- Manifests live in this repo under `deploy/k8s` (base + staging + production).
- CI commits digest bumps straight to `main`. Staging follows `main`;
  production follows `vX.Y.Z` tags.
- Argo CD does all reconciling. CI never talks to the Argo API.
- Scheduled publishing in production rebuilds the *released ref* with a new
  `BUILD_NOW`; it is a content rebuild, not a release.
- Staging at `staging.chicanodev.com`, basic auth + `X-Robots-Tag: noindex`.
- Resources: requests 25m/64Mi, limits 500m/256Mi, 2 replicas.
- NetworkPolicy: investigate enforcement first, show findings, then decide.

## 2026-11-04: Container

- **Server: `nginxinc/nginx-unprivileged` 1.30.6 (stable line), pinned by digest.**
  Alternatives considered: Caddy (nicer config, but another thing to learn and
  patch) and plain `nginx` (needs root to bind port 80). The unprivileged build
  listens on 8080 as uid 101 and keeps pid/temp files in `/tmp`, which is what
  makes `readOnlyRootFilesystem` workable.
- **Build stage pinned to the Node version in `.node-version`** (24.14.1), by digest.
- **`.dockerignore` is an allowlist** (`*` then `!path`). Safer than a denylist
  for a repo that also holds videos, zips and local `.venv`s.
- **Test-first result:** the container test failed first with
  `open Dockerfile: no such file or directory` (expected). After the first
  Dockerfile, 8 of 9 passed.
- **Surprise: duplicate URLs.** My first `try_files $uri $uri/index.html $uri/ =404`
  served `/posts/welcome` with 200 instead of redirecting to `/posts/welcome/`,
  so every page existed at two URLs. The test caught it. Fix: remove
  `$uri/index.html` and let nginx's directory handling issue the 301.
  Worth a section in Part 2.
- **nginx gotcha:** `add_header` is not additive across levels; a location with
  its own `add_header` loses the server-level ones. Security headers are an
  include re-applied in every location.
- `Location` headers are relative (`absolute_redirect off`) because the pod
  cannot know its public scheme/host behind Cloudflare and Traefik.
- `/version.json` (ref, commit, buildNow) is baked in so humans and CI can ask a
  running pod what it is serving.

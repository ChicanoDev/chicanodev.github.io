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

## 2026-11-05: Scheduled publishing

- **The core problem is that a static site has no "request time".** What is
  visible is fixed when the build runs, so "publish at 9:00" really means "rebuild
  after 9:00". Everything else follows from that.
- **One function decides: `isPublished(post, now)`** (`src/lib/publishing.ts`).
  Draft or `date > now` means hidden. `now` is an argument, never read inside, so
  tests use fixed instants. `BUILD_NOW` pins it per build; one value per build so
  every page, feed and sitemap agrees.
- **Dates are instants, not wall-clock strings.** Front matter carries its offset
  (`-0600`/`-0500`), so DST needs no timezone library; a test pins the CST/CDT edge.
- **Tests that mattered:** a *non-draft* fixture dated 2099 (the draft fixture
  alone proved nothing about dates); a build at `17:59:59Z` vs `18:00:00Z` either
  side of the fixture's instant; and a scan of every html/xml/js/json/css file in
  `dist` for the fixture's markers. No search index or related-posts exist, so
  those two requirements are vacuously met today (noted, not claimed).
- **Tagged production vs. scheduled posts (the design conflict).** If production
  only changes on tags, a post dated after the tag's build would never appear; if
  the cron rebuilt `main`, it would ship unreleased code. Resolution: keep two
  inputs apart. *Source* = the Git ref production already runs; *cutoff* =
  `BUILD_NOW`. The cron rebuilds the recorded commit with a fresh cutoff. That is a
  **content rebuild, not a release**. State lives in `release.json` next to the
  digest, in Git, no database.
- **Concurrency without a lock.** GitHub keeps only one *pending* run per group and
  cancels older ones, so one shared group could let a cron run silently cancel a
  pending release. Instead: per-workflow groups to avoid duplicate builds, and
  *correctness* from Git: `promote.sh` re-reads fresh `main`, re-checks the rules,
  and a rejected non-fast-forward push means "start over". Tested against a real
  bare remote, including a forced push rejection.
- **Late or duplicate workflows can't win** (unit-tested in `deploy-state`): older
  release tag, content rebuild of a source that was superseded, older staging commit.
- **Prediction vs. reality.** The cron predicts "what should be public" from front
  matter without building; `_build.yml` then checks the built image lists exactly
  that. Without the check, any disagreement would trigger a rebuild every hour.
- **No Cloudflare purge token in CI.** HTML/RSS/sitemap are served
  `max-age=0, must-revalidate` and Cloudflare does not cache HTML by default, so
  there is nothing to purge. One fewer secret.

## 2026-11-05: Kubernetes and GitOps

- **Namespaces `chicanodev-staging` and `chicanodev`**, not one shared namespace:
  matches the cluster's `old-town-staging` pattern, avoids name clashes, keeps
  future policies and RBAC separate.
- **Manifests in this repo (`deploy/k8s`)**, following gv5tech-website. `gv5-k8s`
  turned out to hold only platform pieces; "bump gv5-k8s" does not exist.
- **Trade-off made explicit:** both Argo apps track `main`, so a *manifest* change
  (probes, resources) reaches production when merged, while *application code*
  reaches production only through a tag. A release gates the image, not config.
- **`ScheduleAnyway` topology spread** instead of a hard rule: a soft preference
  can never wedge a rollout; with 6 nodes it spreads anyway.
- **Policy test over rendered manifests** (`manifests.test.mjs`): asserts digest
  images, probes, read-only root, dropped capabilities, no Secrets/RBAC, AOP
  annotation on *every* Ingress. Written after the manifests (not strictly
  test-first); verified it can fail by flipping `readOnlyRootFilesystem`.
- **Server-side dry-run needs the namespace to exist**; it does not until Argo
  creates it, so the dry-run was done with the namespace rewritten to `default`
  (validates schemas and CRDs, persists nothing).
- **Repo is public**, so Argo needs no credentials and the GHCR package can be
  public with no pull secret. `main` has no branch protection, so the bot commit
  needs no ruleset exception today.
- **ARC runners rejected** for this repo: org-scoped to a different org, and
  Docker-in-Docker (privileged). GitHub-hosted runners keep PR code off the cluster.

## 2026-11-05: NetworkPolicy

- Flannel does not enforce policy; k3s bundles a separate controller. No node had
  it disabled, but I did not trust "no flag" and tested enforcement in disposable
  namespaces. Result: ingress and egress are enforced; kubelet probes are
  unaffected by default-deny; the namespace-AND-label selector works. See
  [networkpolicy.md](networkpolicy.md). Not applied; awaiting approval.

## Surprises and mistakes (series material)

- `try_files $uri $uri/index.html $uri/` served every page at two URLs (see above).
- I wrote `substr()` in a workflow expression; GitHub Actions has no such function.
  `actionlint` caught it before it ever ran.
- YAML anchors do not cross `---` document boundaries in a multi-document file;
  `kubectl apply` failed on the probe pods.
- A freshly created bare Git repo on this machine had no `hooks/` directory, which
  broke the rejected-push test's setup (not the logic under test).
- Two live problems on the old site: `www` has no TLS certificate on GitHub Pages,
  and `http://` does not redirect.
- Cloudflare token behind cert-manager, checked read-only: valid, no expiry,
  account-owned, sees `chicanodev.com` and reads its DNS. Two things stay
  unproven: that it can *edit* DNS there (only a write would prove it; the first
  staging certificate will) and the zone's SSL mode / Authenticated Origin Pulls
  (the token is DNS-only and cannot read settings, so that is a dashboard check).
  Also found: MX and DKIM/SPF records share the zone, so the cutover must leave
  them alone. *Resolved later:* the staging certificate proved `DNS:Edit`, and
  Dave confirmed Full (strict) and AOP in the dashboard.
- **Staging sat broken for a week and nobody noticed.** The basic-auth Secret was
  never created, so Traefik dropped the route and staging answered 404. Fail-closed
  did its job (nothing leaked), but "Synced/Healthy" in Argo and 2/2 Ready pods
  said nothing about whether the site was *reachable*. That is the clearest
  argument so far for the deferred monitoring: one external HTTP check would have
  caught it the same day.
- **GitHub skips scheduled runs.** The hourly `publish.yml` cron actually ran about
  every 8 hours. "Hourly" in a workflow file is a request, not a promise.
- **The `http://` gap at cutover.** Pointing proxied DNS at the cluster before
  turning on Always Use HTTPS made every `http://` URL return 404 for a few
  minutes (Traefik's port-80 entrypoint has no router for the site), including
  `chicanodev.github.io` links, which Pages redirects to `http://`. Flip the zone
  setting first.

## 2026-11-12: Production cutover

- **Order mattered:** release first (`v1.0.0`), then apply the production Argo app,
  then DNS. Applying the app before a release would have deployed the placeholder
  digest and sat in `ImagePullBackOff`.
- **Certificates before DNS.** DNS-01 lets cert-manager issue the apex and `www`
  certificates while DNS still points at GitHub Pages, so there was no window with
  a missing certificate.
- **Proving parity without DNS:** a `kubectl port-forward` to the production Service
  and a diff against the live Pages site (sitemap URLs, RSS links, a post's
  `<article>` hash). All identical.
- **DNS changed through the API with cert-manager's token** (Dave's explicit OK),
  patching the 4 apex A records and the `www` CNAME in place and saving the
  before-state first. That token cannot change zone settings, so Always Use HTTPS
  was a dashboard toggle. Using a cert-manager credential for a one-off is a
  shortcut, not a pattern; a separate, scoped token would be the clean way.
- **Both old-site problems are fixed:** `www` now has a certificate (and redirects
  to the apex) and `http://` redirects to `https://`.
- Pages is left deployed as the fallback; see [cutover.md](cutover.md).

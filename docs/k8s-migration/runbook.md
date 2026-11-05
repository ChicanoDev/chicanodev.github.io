# Runbook: chicanodev on Kubernetes

Short operating guide for a small static site. Architecture and the reasons behind
it: [architecture.md](architecture.md), [decisions.md](decisions.md).
**Monitoring is deliberately deferred** to a cluster-wide project; until then,
"is it up" means the `curl`/`kubectl` checks below.

## Repository map

| Path | What |
|---|---|
| `Dockerfile`, `deploy/nginx/` | Multi-stage image; nginx config and security headers |
| `deploy/k8s/base/` | Deployment, Service, PDB, ServiceAccount |
| `deploy/k8s/overlays/{staging,production}/` | Ingress, middlewares, **image digest**, `release.json` (what that digest was built from) |
| `deploy/argocd/` | Argo CD `Application`s (applied by hand, never by CI) |
| `deploy/k8s/proposed/` | NetworkPolicy proposal, **not applied** |
| `.github/workflows/` | `staging.yml`, `release.yml`, `publish.yml`, reusable `_build.yml`/`_publish-env.yml`, `deploy.yml` (Pages fallback) |
| `scripts/deploy-state.mjs`, `scripts/ci/promote.sh` | The "should this image win?" logic and the commit-with-retry step |

## Bring up staging (first time)

Nothing below happens automatically. Steps marked **you** need your Cloudflare or cluster access.

**0. Prechecks (you)**
- Cloudflare zone `chicanodev.com`: SSL/TLS mode **Full (strict)**, and **Authenticated Origin Pulls ON** (SSL/TLS > Origin Server). Without the zone-level toggle Cloudflare presents no client certificate and Traefik rejects every request.
- **cert-manager's Cloudflare token** (`cloudflare-api-token-secret`, namespace `cert-manager`). Checked read-only on 2026-11-05 (token value never printed):
  - Valid and active, no expiry. It is an account-owned token (`/user/tokens/verify` rejects it; `/accounts/<id>/tokens/verify` accepts it).
  - It can see `chicanodev.com` (one of six zones: aihtx.church, chicanodev.com, cindiebakesstuff.com, cindiemakesstuff.com, dgvigil.dev, gv5tech.com) and read its DNS records.
  - **Not proven:** that it has `DNS:Edit` here. Proving that needs a write, which I did not do. The first staging certificate is the real test: if `Certificate chicanodev-staging-tls-cert` stays `False` with a Cloudflare permission error (step 7), edit the token in Cloudflare > My Profile/Account > API Tokens and add `Zone:DNS:Edit` for `chicanodev.com`.
  - It cannot read zone *settings* (SSL mode, Authenticated Origin Pulls, Always Use HTTPS all returned "Authentication error"). That is appropriate for a DNS-only token, so do not widen it. These three settings can only be confirmed in the dashboard (the first bullet).
- **Email lives in this zone.** `chicanodev.com` has 3 MX records and DKIM/SPF TXT records, all DNS-only. Staging adds only `staging` A records. The production cutover must change **only** the 4 apex `A` records and the `www` `CNAME`, and leave MX/TXT alone (mail records must stay DNS-only).
- Repo Settings > Actions > General > Workflow permissions: explicit per-job `permissions:` in the workflows are enough, but an org policy capping the token to read-only would block the digest commit and the image push.

**1. Merge to `main`** (open a PR from `feat/k8s-container`; `deploy.yml` runs the tests). The merge starts `staging.yml`: full tests, image build, container test, push to `ghcr.io/chicanodev/chicanodev-site`, then a bot commit that sets the staging digest.

**2. Make the package public (you), once.** GitHub > ChicanoDev org > Packages > `chicanodev-site` > Package settings > Change visibility > Public. (New packages start private; the cluster has no pull secret on purpose, because the site is public.)

**3. Pull the bot commit:** `git pull`. `deploy/k8s/overlays/staging/release.json` now has a real `ref`, `commit` and `digest`.

**4. DNS (you).** Cloudflare, zone `chicanodev.com`: `staging` A records, **Proxied**, to the same four node IPs `n8n.gv5tech.com` uses: `64.44.157.71`, `173.249.203.146`, `108.171.195.102`, `64.44.157.43`.

**5. Apply the Argo CD Application (needs your OK, it changes the cluster):**
```sh
kubectl apply -n argocd -f deploy/argocd/chicanodev-staging-app.yaml
argocd app get chicanodev-staging        # or: kubectl -n argocd get application chicanodev-staging
```
Argo creates `chicanodev-staging` (with the `restricted` Pod Security label), the Deployment, Service, PDB, Ingress and middlewares.

**6. Create the basic-auth Secret (you; it is never in Git).** Until it exists Traefik refuses the route (the site is closed, not open):
```sh
htpasswd -nbB <user> '<password>' | \
  kubectl -n chicanodev-staging create secret generic chicanodev-staging-basic-auth --from-file=users=/dev/stdin
```

**7. Wait for the certificate:**
```sh
kubectl -n chicanodev-staging get certificate,certificaterequest,order,challenge
kubectl -n chicanodev-staging describe certificate chicanodev-staging-tls-cert
```

**8. Verify**
```sh
kubectl -n chicanodev-staging get deploy,pods,pdb,ingress -o wide        # 2/2 Ready, on different nodes
curl -sI https://staging.chicanodev.com/                                  # 401: auth required
curl -s -u '<user>:<password>' https://staging.chicanodev.com/version.json
curl -sI -u '<user>:<password>' https://staging.chicanodev.com/ | grep -i -E 'x-robots-tag|cache-control|server'
# AOP really enforced? Bypass Cloudflare and connect to a node directly with no client certificate.
# The TLS handshake must FAIL, not return a page:
curl -sk --resolve staging.chicanodev.com:443:64.44.157.71 https://staging.chicanodev.com/ -o /dev/null -w '%{http_code}\n'
kubectl -n chicanodev-staging top pod                                      # compare with 25m/64Mi requests
```

## Day to day

| I want to... | Do this |
|---|---|
| Deploy to staging | Merge to `main`. Within minutes `/version.json` shows the new `commit`. |
| Release to production | `scripts/release.sh v1.2.0` (checks staging built OK, asks, tags, pushes). Watch `gh run list --workflow release.yml`. |
| Publish a post on a date | Write it with the future `date:` (with offset, e.g. `2026-11-09 09:00:00 -0600`) and `draft: false`. Merge. **Cut a release that contains it** before that date. At the date, the hourly `publish.yml` rebuilds the *released* source and it goes live (up to ~1h late plus ~5 min build). Posts merged to `main` but not yet released are never published to production. |
| Publish right now / retry | Actions > *Publish scheduled posts* > Run workflow. Safe to run any time; it exits quickly if nothing is due. |
| See what is live | `curl -s https://chicanodev.com/version.json` (`ref`, `commit`, `buildNow`, `published`). |

How the pieces decide (details in architecture.md): staging follows `main`; production follows `vX.Y.Z` tags; a **content rebuild** rebuilds the same source with a newer `BUILD_NOW` and is *not* a release.

## Rollback

Production's desired state is two files under `deploy/k8s/overlays/production/` and every change is a commit, so rolling back is Git.

1. **Fastest (no build):** find the bot commit (`git log --oneline -- deploy/k8s/overlays/production`), `git revert <sha>`, push to `main`. Argo CD syncs the previous digest (still in GHCR). Check with `/version.json`.
2. **Rebuild an older tag:** Actions > *Release* > Run workflow > tag `v1.1.0`, **rollback: true**. (Without the flag the workflow refuses to go backwards on purpose.)
3. Do not use `argocd app rollback`: with automated sync on, Argo re-applies Git within seconds.

Rollback and scheduled posts: going back to `v1.1.0` hides posts that exist only in newer releases; every post in `v1.1.0` that is already due stays visible. The next hourly run keeps `v1.1.0`'s own posts current.

Staging rolls back the same way (revert the staging bot commit), but the next merge to `main` replaces it.

## Troubleshooting

**A change is on `main` but the site did not change**
```sh
gh run list --limit 8                                   # did staging.yml / release.yml succeed?
git log --oneline -3 -- deploy/k8s/overlays/production  # did the bot commit land?
argocd app get chicanodev-production                    # Synced? Healthy? last sync error?
argocd app diff chicanodev-production
argocd app sync chicanodev-production                   # only if auto-sync is stuck
```
**"Not promoting: ..." in a workflow summary** is a decision, not an error: older release, superseded content rebuild, or nothing new. The reason is printed.

**Pods not Ready**
```sh
kubectl -n chicanodev get pods -o wide
kubectl -n chicanodev describe pod -l app.kubernetes.io/name=chicanodev | tail -30
kubectl -n chicanodev logs -l app.kubernetes.io/name=chicanodev --tail=50   # nginx access and error log
kubectl -n chicanodev get events --sort-by=.lastTimestamp | tail
```
`ImagePullBackOff`: package still private (step 2), or the digest in the overlay does not exist. `CreateContainerConfigError` / pod rejected: a Pod Security `restricted` violation; the event names the field.

**Site down, pods healthy**
```sh
kubectl -n chicanodev get ingress,certificate
kubectl -n kube-system logs deploy/traefik --tail=50
curl -sI https://chicanodev.com/         # 525/526 = Cloudflare cannot complete TLS to the origin; 404 = no matching router
```
If AOP is on for the Ingress but Cloudflare's zone toggle is off, every request fails at the handshake. If a NetworkPolicy is later adopted and Traefik's labels change, pods stay Ready but unreachable.

**Certificate stuck**
```sh
kubectl describe certificate,order,challenge -n chicanodev
kubectl -n cert-manager logs deploy/cert-manager --tail=40    # DNS-01 / Cloudflare token errors show here
```

**Scheduled post did not appear**
1. Is it in the *released* source? Compare `curl -s .../version.json` `commit` against `git log` for the post.
2. Is `draft: false` and the date's offset right? `node scripts/published-posts.mjs --now 2026-11-09T15:00:00Z` prints what would be public at that instant.
3. `gh run list --workflow publish.yml` and open the latest run's summary: `due=`, `reason=`.
4. A delayed cron run is normal (GitHub may start it late). Re-run it by hand.

**The promote step failed to push to main**: a ruleset is blocking the Actions bot. `main` currently has no branch protection or rulesets. If you add one, the bot (`github-actions[bot]`) needs a bypass, and the change must be your explicit decision.

## Security notes

- Workflows run on GitHub-hosted runners, never on the cluster's ARC runners (org-scoped to `GV5-Tech`, Docker-in-Docker = privileged). Pull-request code gets read-only permissions and no secrets; `staging`/`release`/`publish` never run on `pull_request`.
- No secrets in Git. CI uses the short-lived `GITHUB_TOKEN` only (`contents: write` solely in the promote job, `packages: write` solely in the build job). CI holds no kubeconfig and no Argo token; Argo CD pulls from the public repo.
- Images are referenced by digest; base images are pinned by digest. Pod: non-root (uid 101), read-only root filesystem, all capabilities dropped, no service-account token, seccomp `RuntimeDefault`, namespace enforces Pod Security `restricted`.
- Origin protection is Cloudflare Authenticated Origin Pulls via the Ingress annotation (opt-in per Ingress in this cluster). Verify with the direct-to-origin `curl` in staging step 8.
- Staging: basic auth (Secret created by hand) plus `X-Robots-Tag: noindex`.
- NetworkPolicy: proposal only, see [networkpolicy.md](networkpolicy.md).

## Operational responsibilities (what self-hosting adds)

Cert renewal (cert-manager; watch for failures), node and k3s upgrades, Traefik being a single replica, image/base-image updates (pinned digests do not update themselves), GHCR package visibility, the Cloudflare token's scope, and checking after cluster upgrades that NetworkPolicy still enforces (if adopted). GitHub Pages remains deployable as a fallback (`deploy.yml`) until you retire it.

## Monitoring (deferred)

Not implemented here by decision: no uptime checks, Prometheus, Loki or dashboards. Kubernetes readiness/liveness probes are in place (`/healthz`). The manual checks above are the interim answer.

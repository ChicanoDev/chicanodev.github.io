# Production cutover: GitHub Pages to k3s (2026-11-12)

What was done, in order, with the checks that passed. Production is
`chicanodev.com`, served by the `chicanodev` namespace through Cloudflare. GitHub
Pages is still deployed and is the fallback.

## 1. Staging verified first

| Check | Result |
|---|---|
| No credentials / wrong password | 401 with `WWW-Authenticate` |
| `/`, `/posts/welcome/`, `/rss.xml`, `/sitemap-index.xml`, `/version.json` (with credentials) | 200; `/nope/` 404 |
| `/posts/welcome` | 301, `Location: /posts/welcome/` (relative) |
| Headers | `X-Robots-Tag: noindex, nofollow, noarchive`; HTML `public, max-age=0, must-revalidate`; `/_astro/*` `max-age=31536000, immutable`; nosniff, `X-Frame-Options: DENY`, referrer policy |
| Direct to a node, no Cloudflare client certificate | TLS handshake refused (curl exit 56) |
| `kubectl rollout restart` with a curl loop through Cloudflare | 63/63 requests 200 |
| `kubectl top pod` | ~1m CPU, 3-4Mi memory per pod (requests are 25m/64Mi) |

Staging had been returning 404 for a week before this: the basic-auth Secret was
never created, and Traefik drops the route rather than serve it unprotected.

## 2. First release

```sh
scripts/release.sh v1.0.0        # tags c0a0844, the commit staging built
```
`release.yml` built the image and committed
`chore(deploy): production -> v1.0.0 [release] sha256:37ae1e599517`. The production
Argo app was applied only after this, because before it the overlay held a
placeholder digest that would have failed to pull.

## 3. Production in the cluster, DNS untouched

```sh
kubectl apply -n argocd -f deploy/argocd/chicanodev-production-app.yaml
```
- Argo `chicanodev-production` Synced/Healthy; namespace `chicanodev` labelled Pod Security `restricted`; 2 pods on different nodes.
- `chicanodev-tls-cert` and `chicanodev-www-tls-cert` issued by DNS-01 in about a minute, before DNS pointed at the cluster. Traefik logged "secret does not exist" only until then.
- Checked through `kubectl -n chicanodev port-forward svc/chicanodev 18080:80`: same routes and redirect as staging, **no** `X-Robots-Tag`, `/version.json` = `v1.0.0`.
- Parity with Pages: identical sitemap URL list (13), identical RSS links, byte-identical `<article>` of `/posts/welcome/`.

## 4. DNS (Cloudflare, zone `chicanodev.com`)

Changed with the Cloudflare API, using cert-manager's DNS token with explicit approval
(records patched in place, same record IDs). **Only these five records changed:**

| Record | Before | After |
|---|---|---|
| `chicanodev.com` A ×4 | `185.199.108.153`, `.109.153`, `.110.153`, `.111.153`, DNS-only | `64.44.157.71`, `173.249.203.146`, `108.171.195.102`, `64.44.157.43`, **proxied** |
| `www` CNAME | `chicanodev.github.io`, DNS-only | `chicanodev.com`, **proxied** |

MX (route1/2/3.mx.cloudflare.net), SPF and DKIM were not touched and still resolve.
Then **Always Use HTTPS** was turned on in the dashboard (the DNS token cannot change
zone settings).

**Gotcha:** between the DNS change and the Always Use HTTPS toggle, every `http://`
URL returned **404**. Cloudflare forwarded plain HTTP to Traefik's port 80 entrypoint,
where no router exists for this site. That includes `chicanodev.github.io/...`,
because Pages redirects it to `http://chicanodev.com/...`. Next time: turn on Always
Use HTTPS **before** switching the records. It was harmless while DNS still pointed
at Pages.

## 5. After the switch (through Cloudflare)

| Check | Result |
|---|---|
| `https://chicanodev.com/` + main routes | 200; `/version.json` = `v1.0.0` |
| `https://www.chicanodev.com/posts/welcome/` | 301 to `https://chicanodev.com/posts/welcome/` (the old `www` certificate error is gone) |
| `http://chicanodev.com/posts/welcome/` | 301 to https, then 200 |
| `http://www.chicanodev.com/...` | https, then apex (2 hops) |
| `https://chicanodev.github.io/posts/welcome/` | ends at 200 on `https://chicanodev.com/posts/welcome/` |
| Direct to a node, no client certificate | refused |
| 60-request loop | 60/60 200 |
| Traefik errors for `namespace=chicanodev` | none |

## Rollback to GitHub Pages

Pages is still deployed (`deploy.yml` keeps running). To switch back, set the records
in the table above to their **Before** values (DNS-only, not proxied) in Cloudflare.
Always Use HTTPS can stay on. Expect a few minutes for caches.

Rolling back the *application* instead (bad release, cluster stays) is in
[runbook.md](runbook.md#rollback).

## Not done (deliberately)

- GitHub Pages is not disabled. Retire it only after the cluster has run for a while.
- Pages' **Enforce HTTPS** can no longer be turned on (the domain no longer points at Pages). This doesn't matter while it is only a fallback.
- NetworkPolicy is still a proposal ([networkpolicy.md](networkpolicy.md)).
- Monitoring is still deferred.

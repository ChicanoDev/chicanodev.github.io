# NetworkPolicy: findings and proposal

Status: **investigated, proposal awaiting approval. Nothing is applied to chicanodev.**
Proposed manifest: [`deploy/k8s/proposed/networkpolicy.yaml`](../../deploy/k8s/proposed/networkpolicy.yaml)
(not referenced by any kustomization, so Argo CD ignores it).

## Question

The cluster runs k3s with Flannel. Flannel itself does not enforce NetworkPolicy;
k3s bundles a separate policy controller (kube-router's). Does it run here, and
would a default-deny policy break Traefik or the kubelet probes?

## What I checked, read-only first

| Check | Result |
|---|---|
| Node args (`k3s.io/node-args`, all 6 nodes) | No `--disable-network-policy`. The server (`ext06`) runs only kubelet args, so the embedded controller is on by default. |
| Existing policies in the cluster | One: `cattle-fleet-local-system/default-allow-all`. No application namespace uses policies, so nothing else depends on the controller behaving a certain way. |
| Traefik | One replica, `kube-system`, pod IP on the pod network, **not** host-networked, label `app.kubernetes.io/name=traefik`. It opens its own connection to backends, so a chicanodev pod sees the *Traefik pod IP* as the source, not the visitor's and not the node's. |
| Entry point | k3s ServiceLB (`svclb-traefik` DaemonSet) forwards node ports 80/443 to the Traefik Service. It never talks to backend pods directly. |

"No flag disables it" is not proof it enforces, so I tested.

## Empirical test (disposable, since deleted)

Two namespaces labelled `purpose=netpol-probe` (`netpol-probe`, `netpol-probe-edge`),
created and deleted by me on 2026-11-05. A backend using the real site's nginx image,
hardened like the Deployment, with a Deployment readiness and liveness probe; a
"stranger" pod beside it; and two pods in the other namespace, one carrying the
Traefik label and one without. No existing workload was touched. Afterwards
`kubectl get ns` showed no `netpol-probe*` and the only NetworkPolicy left was Fleet's.

| Scenario | Expected | Observed |
|---|---|---|
| No policy: all three clients -> backend | allowed | allowed |
| Policy on: pod labelled `traefik` in the allowed namespace | allowed | **allowed** |
| Policy on: stranger in the backend's own namespace | denied | **denied** |
| Policy on: right namespace, wrong pod label | denied | **denied** (proves the namespace AND pod-label combination) |
| Backend stays Ready for 25+ s under default-deny (kubelet probes) | Ready, 0 restarts | **Ready, 0 restarts** |
| Delete the backend pod; replacement starts under the policy | becomes Ready | **became Ready** (probes work from a cold start) |
| Egress from the backend: DNS | blocked | **blocked** (timed out) |
| Egress from the backend: direct IP | blocked | **blocked** (connection refused; kube-router rejects instead of dropping) |

Conclusions:

- **The controller enforces, for both ingress and egress.**
- **Kubelet probes are unaffected.** Kubernetes lets a node reach pods on that node regardless of policy, and the test confirms it here. No `ipBlock` for node addresses is needed.
- **DNS or other egress exceptions are not needed** for a static nginx pod: it never makes outbound calls. If a future feature needs one, add it deliberately.
- **Existing apps are unaffected**: policies are namespaced and select only chicanodev pods.

## Proposed policy

Two policies, applied to both `chicanodev-staging` and `chicanodev`:

1. `default-deny-all`: no ingress, no egress for any pod in the namespace.
2. `allow-ingress-from-traefik`: web pods accept TCP 8080 only from pods labelled
   `app.kubernetes.io/name=traefik` in `kube-system`.

Full YAML: `deploy/k8s/proposed/networkpolicy.yaml`.

## Risks and limits (what this does NOT prove)

- **The real Traefik path is not yet tested.** I simulated Traefik with a labelled pod. The real proof is staging: apply the policy there first and confirm `https://staging...` still answers.
- **Fail-closed coupling to Traefik's labels.** If a k3s or Helm upgrade changes the Traefik pod labels or moves it out of `kube-system`, the site goes dark until the selector is updated. Same with a second ingress controller. This is the price of a tight allow rule; the runbook lists the symptom (Traefik 502/504, pods Ready but unreachable).
- **Single Traefik replica** already means the site has a single point of failure at the ingress, regardless of policy.
- **Isolation is only as good as the controller.** If k3s is ever started with `--disable-network-policy`, these manifests would silently stop isolating anything. The staging runbook includes a one-minute enforcement check to repeat after cluster upgrades.
- Rollback: delete the two policies (remove from Git, Argo prunes them).

## Decision needed

Approve adding the two policies to `deploy/k8s/base/`, rolling out to staging first.

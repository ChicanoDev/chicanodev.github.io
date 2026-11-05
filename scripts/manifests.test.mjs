// Policy checks on the RENDERED manifests (what Argo CD will actually apply),
// for both environments. These guard the properties that bite in production:
// immutable images, least privilege, and Cloudflare origin authentication.
// Skipped when kubectl is not installed (it is on GitHub-hosted runners).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync, spawnSync } from 'node:child_process';
import { parseAllDocuments } from 'yaml';

const hasKubectl = spawnSync('kubectl', ['version', '--client'], { stdio: 'ignore' }).status === 0;

function render(env) {
  const out = execFileSync('kubectl', ['kustomize', `deploy/k8s/overlays/${env}`], { encoding: 'utf8' });
  return parseAllDocuments(out).map((doc) => doc.toJS());
}

const NAMESPACES = { staging: 'chicanodev-staging', production: 'chicanodev' };

for (const env of ['staging', 'production']) {
  test(`${env}: workload is pinned, unprivileged and read-only`, { skip: !hasKubectl && 'kubectl not installed' }, () => {
    const docs = render(env);
    const kind = (k) => docs.filter((d) => d.kind === k);

    for (const doc of docs) assert.equal(doc.metadata.namespace, NAMESPACES[env], `${doc.kind}/${doc.metadata.name} namespace`);

    const [deploy] = kind('Deployment');
    const pod = deploy.spec.template.spec;
    const [container] = pod.containers;

    assert.equal(deploy.spec.replicas, 2);
    assert.match(container.image, /^ghcr\.io\/chicanodev\/chicanodev-site@sha256:[0-9a-f]{64}$/, 'image must be a digest, never a tag');

    assert.deepEqual(container.resources, {
      requests: { cpu: '25m', memory: '64Mi' },
      limits: { cpu: '500m', memory: '256Mi' },
    });
    assert.equal(pod.securityContext.runAsNonRoot, true);
    assert.equal(pod.securityContext.seccompProfile.type, 'RuntimeDefault');
    assert.equal(container.securityContext.readOnlyRootFilesystem, true);
    assert.equal(container.securityContext.allowPrivilegeEscalation, false);
    assert.deepEqual(container.securityContext.capabilities.drop, ['ALL']);
    assert.equal(pod.automountServiceAccountToken, false);
    assert.equal(pod.serviceAccountName, 'chicanodev');
    assert.ok(container.readinessProbe && container.livenessProbe, 'probes required');
    assert.ok(!pod.hostNetwork && !pod.hostPID, 'no host namespaces');
    assert.equal(deploy.spec.strategy.rollingUpdate.maxUnavailable, 0);
    assert.ok(pod.volumes.every((v) => v.emptyDir), 'only emptyDir volumes: no persistent state');

    const [pdb] = kind('PodDisruptionBudget');
    assert.equal(pdb.spec.minAvailable, 1);
    assert.deepEqual(pdb.spec.selector.matchLabels, deploy.spec.selector.matchLabels);

    assert.equal(kind('Role').length + kind('ClusterRole').length + kind('RoleBinding').length, 0, 'ServiceAccount needs no RBAC');
    assert.equal(kind('Secret').length, 0, 'no Secret may be committed');
  });

  test(`${env}: every Ingress enforces TLS and Cloudflare origin auth`, { skip: !hasKubectl && 'kubectl not installed' }, () => {
    const ingresses = render(env).filter((d) => d.kind === 'Ingress');
    assert.ok(ingresses.length >= 1);
    for (const ing of ingresses) {
      const a = ing.metadata.annotations;
      const label = `${env}/${ing.metadata.name}`;
      assert.equal(ing.spec.ingressClassName, 'traefik', label);
      assert.equal(a['cert-manager.io/cluster-issuer'], 'letsencrypt-prod', label);
      assert.equal(a['traefik.ingress.kubernetes.io/router.entrypoints'], 'websecure', label);
      assert.equal(a['traefik.ingress.kubernetes.io/router.tls'], 'true', label);
      assert.equal(a['traefik.ingress.kubernetes.io/router.tls.options'], 'default-cloudflare-aop@kubernetescrd', `${label}: AOP is opt-in per Ingress here`);
      assert.ok(ing.spec.tls?.[0]?.secretName, `${label}: tls secretName`);
    }
  });
}

test('staging is behind basic auth + noindex; production is not', { skip: !hasKubectl && 'kubectl not installed' }, () => {
  const mw = (a) => a?.['traefik.ingress.kubernetes.io/router.middlewares'] ?? '';
  const [stagingIngress] = render('staging').filter((d) => d.kind === 'Ingress');
  assert.match(mw(stagingIngress.metadata.annotations), /chicanodev-staging-basic-auth@kubernetescrd/);
  assert.match(mw(stagingIngress.metadata.annotations), /chicanodev-staging-noindex@kubernetescrd/);
  assert.equal(stagingIngress.spec.rules[0].host, 'staging.chicanodev.com');

  const prod = render('production').filter((d) => d.kind === 'Ingress');
  const hosts = prod.flatMap((i) => i.spec.rules.map((r) => r.host)).sort();
  assert.deepEqual(hosts, ['chicanodev.com', 'www.chicanodev.com']);
  const apex = prod.find((i) => i.spec.rules[0].host === 'chicanodev.com');
  assert.doesNotMatch(mw(apex.metadata.annotations), /basic-auth/, 'production must be public');
  const www = prod.find((i) => i.spec.rules[0].host === 'www.chicanodev.com');
  assert.match(mw(www.metadata.annotations), /chicanodev-www-to-apex@kubernetescrd/);

  const [redirect] = render('production').filter((d) => d.metadata?.name === 'www-to-apex');
  assert.equal(redirect.spec.redirectRegex.permanent, true);
  assert.equal(redirect.spec.redirectRegex.replacement, 'https://chicanodev.com/${1}');
});

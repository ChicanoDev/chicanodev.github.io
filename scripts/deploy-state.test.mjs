import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  applyPromotion,
  compareSemver,
  decidePromotion,
  needsContentRebuild,
  parseSemver,
  readState,
} from './deploy-state.mjs';

const D1 = `sha256:${'a'.repeat(64)}`;
const D2 = `sha256:${'b'.repeat(64)}`;
const state = (over = {}) => ({ ref: 'v1.2.0', commit: 'c120', buildNow: '2026-11-10T00:00:00Z', published: ['welcome'], ...over });

test('semver: only strict vX.Y.Z tags are releases, compared numerically', () => {
  assert.deepEqual(parseSemver('v1.2.3'), [1, 2, 3]);
  for (const bad of ['1.2.3', 'v1.2', 'v1.2.3-rc1', 'main', 'v1.2.3.4', '', null]) assert.equal(parseSemver(bad), null, String(bad));
  assert.ok(compareSemver('v1.10.0', 'v1.9.0') > 0, '10 > 9, not string order');
  assert.ok(compareSemver('v2.0.0', 'v1.99.99') > 0);
  assert.equal(compareSemver('v1.2.3', 'v1.2.3'), 0);
});

test('release: a newer tag is promoted', () => {
  const r = decidePromotion({ kind: 'release', current: state(), incoming: state({ ref: 'v1.3.0' }) });
  assert.equal(r.promote, true);
});

test('release: an OLDER workflow finishing late must not roll production back', () => {
  const r = decidePromotion({ kind: 'release', current: state({ ref: 'v1.3.0' }), incoming: state({ ref: 'v1.2.0' }) });
  assert.equal(r.promote, false);
  assert.match(r.reason, /older|already/i);
});

test('release: same tag again is a no-op; explicit rollback may go backwards', () => {
  assert.equal(decidePromotion({ kind: 'release', current: state(), incoming: state() }).promote, false);
  const back = decidePromotion({ kind: 'release', current: state({ ref: 'v1.3.0' }), incoming: state({ ref: 'v1.2.0' }), rollback: true });
  assert.equal(back.promote, true);
});

test('release: refuses refs that are not vX.Y.Z; first release always promotes', () => {
  assert.equal(decidePromotion({ kind: 'release', current: state(), incoming: state({ ref: 'main' }) }).promote, false);
  assert.equal(decidePromotion({ kind: 'release', current: state({ ref: null, commit: '' }), incoming: state({ ref: 'v1.0.0' }) }).promote, true);
});

test('content rebuild: only for the exact source that is deployed', () => {
  const current = state({ published: ['welcome'] });
  const ok = decidePromotion({ kind: 'content', current, incoming: state({ published: ['welcome', 'next'] }) });
  assert.equal(ok.promote, true);

  const released = decidePromotion({ kind: 'content', current: state({ ref: 'v1.3.0', commit: 'c130' }), incoming: state({ published: ['welcome', 'next'] }) });
  assert.equal(released.promote, false, 'a release landed while this rebuild ran');
  assert.match(released.reason, /superseded|changed/i);

  const moved = decidePromotion({ kind: 'content', current: state({ commit: 'other' }), incoming: state({ published: ['x'] }) });
  assert.equal(moved.promote, false, 'same ref name but different commit (moved tag)');
});

test('content rebuild: identical publication set is a no-op (idempotent retry)', () => {
  const r = decidePromotion({ kind: 'content', current: state(), incoming: state({ buildNow: '2026-11-10T01:00:00Z' }) });
  assert.equal(r.promote, false);
  assert.match(r.reason, /nothing|unchanged|already/i);
});

test('staging: newest main commit wins; stale or duplicate commits are skipped', () => {
  const current = state({ ref: 'main', commit: 'new' });
  assert.equal(decidePromotion({ kind: 'staging', current, incoming: state({ ref: 'main', commit: 'newer' }), incomingIsAncestorOfCurrent: false }).promote, true);
  assert.equal(decidePromotion({ kind: 'staging', current, incoming: state({ ref: 'main', commit: 'old' }), incomingIsAncestorOfCurrent: true }).promote, false);
  assert.equal(decidePromotion({ kind: 'staging', current, incoming: state({ ref: 'main', commit: 'new' }) }).promote, false);
});

test('needsContentRebuild compares sets, not order', () => {
  assert.equal(needsContentRebuild(state({ published: ['a', 'b'] }), ['b', 'a']), false);
  assert.equal(needsContentRebuild(state({ published: ['a'] }), ['a', 'b']), true);
  assert.equal(needsContentRebuild(state({ ref: null, published: [] }), ['a']), false, 'nothing deployed yet: nothing to rebuild');
});

test('applyPromotion rewrites release.json and ONLY the digest line of the overlay', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'overlay-'));
  const kustomization = `# keep this comment\nresources:\n  - ../../base\nimages:\n  - name: ghcr.io/chicanodev/chicanodev-site\n    digest: ${D1}\n`;
  fs.writeFileSync(path.join(dir, 'kustomization.yaml'), kustomization);
  fs.writeFileSync(path.join(dir, 'release.json'), JSON.stringify(state()));

  applyPromotion(dir, { digest: D2, ...state({ ref: 'v1.3.0', commit: 'c130', published: ['welcome', 'next'] }) });

  assert.equal(fs.readFileSync(path.join(dir, 'kustomization.yaml'), 'utf8'), kustomization.replace(D1, D2));
  const written = readState(dir);
  assert.equal(written.ref, 'v1.3.0');
  assert.equal(written.digest, D2);
  assert.deepEqual(written.published, ['next', 'welcome'], 'stored sorted so Git diffs stay small and stable');

  assert.throws(() => applyPromotion(dir, { digest: 'latest', ...state() }), /digest/i);
  assert.throws(() => applyPromotion(dir, { digest: 'sha256:abc', ...state() }), /digest/i);
});

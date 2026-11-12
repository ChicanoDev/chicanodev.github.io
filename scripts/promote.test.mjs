// Integration test: scripts/ci/promote.sh against a real (local, bare) Git
// remote, the way the workflows use it. Covers the races that matter:
// late older releases, superseded content rebuilds, and rejected pushes.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const repoRoot = path.resolve('.');
const D = (c) => `sha256:${c.repeat(64)}`;
const git = (cwd, ...args) => execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();

function copy(from, to) {
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.cpSync(path.join(repoRoot, from), to, { recursive: true });
}

/** A bare "GitHub" plus a working clone that already contains our scripts and overlays. */
function sandbox() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'promote-'));
  const remote = path.join(root, 'remote.git');
  const work = path.join(root, 'work');
  git(root, 'init', '--bare', '--initial-branch=main', remote);
  git(root, 'clone', '-q', remote, work);
  git(work, 'config', 'user.name', 'test');
  git(work, 'config', 'user.email', 'test@example.invalid');
  for (const p of ['scripts/deploy-state.mjs', 'scripts/published-posts.mjs', 'scripts/ci/promote.sh', 'src/lib/publishing.ts', 'deploy/k8s/overlays']) {
    copy(p, path.join(work, p));
  }
  // Start from "nothing deployed", whatever the real overlays hold today. The
  // tests must not depend on live state: the first real release made this
  // repo's production release.json non-empty and broke the plan test.
  for (const env of ['staging', 'production']) {
    const empty = { ref: null, commit: '', buildNow: '', digest: D('0'), published: [] };
    fs.writeFileSync(path.join(work, 'deploy/k8s/overlays', env, 'release.json'), `${JSON.stringify(empty, null, 2)}\n`);
  }
  git(work, 'add', '-A');
  git(work, 'commit', '-q', '-m', 'seed');
  git(work, 'push', '-q', 'origin', 'HEAD:main');
  return { root, remote, work };
}

function promote(work, ...args) {
  return execFileSync('bash', ['scripts/ci/promote.sh', ...args], {
    cwd: work,
    encoding: 'utf8',
    env: { ...process.env, GITHUB_STEP_SUMMARY: '/dev/null' },
  });
}

const remoteFile = (s, rel) => {
  git(s.work, 'fetch', '-q', 'origin', 'main');
  return git(s.work, 'show', `origin/main:${rel}`);
};
const remoteState = (s, env) => JSON.parse(remoteFile(s, `deploy/k8s/overlays/${env}/release.json`));
const remoteHead = (s) => git(s.work, 'ls-remote', 'origin', 'refs/heads/main').split('\t')[0];

test('staging: a new main commit is committed and pushed as the desired state', () => {
  const s = sandbox();
  const out = promote(s.work, 'staging', 'staging', D('a'), 'main', 'c1', '2026-11-10T00:00:00Z', '["welcome"]');
  assert.match(out, /promote=true/);
  const state = remoteState(s, 'staging');
  assert.equal(state.digest, D('a'));
  assert.equal(state.commit, 'c1');
  assert.match(remoteFile(s, 'deploy/k8s/overlays/staging/kustomization.yaml'), new RegExp(`digest: ${D('a')}`));
  assert.match(git(s.work, 'log', '-1', '--format=%s', 'origin/main'), /^chore\(deploy\): staging -> main/);
});

test('production: a late OLDER release never rolls production back', () => {
  const s = sandbox();
  promote(s.work, 'production', 'release', D('1'), 'v1.3.0', 'c130', '2026-11-10T00:00:00Z', '["welcome"]');
  const before = remoteHead(s);

  const late = promote(s.work, 'production', 'release', D('2'), 'v1.2.0', 'c120', '2026-11-10T00:05:00Z', '["welcome"]');
  assert.match(late, /promote=false/);
  assert.match(late, /older than deployed v1\.3\.0/);
  assert.equal(remoteHead(s), before, 'remote must not change');
  assert.equal(remoteState(s, 'production').ref, 'v1.3.0');

  // ...but a deliberate rollback is allowed.
  promote(s.work, 'production', 'release', D('2'), 'v1.2.0', 'c120', '2026-11-10T00:10:00Z', '["welcome"]', '--rollback');
  assert.equal(remoteState(s, 'production').ref, 'v1.2.0');
});

test('content rebuild publishes new posts for the SAME release, and is skipped if a release landed first', () => {
  const s = sandbox();
  promote(s.work, 'production', 'release', D('1'), 'v1.2.0', 'c120', '2026-11-10T00:00:00Z', '["welcome"]');

  const ok = promote(s.work, 'production', 'content', D('3'), 'v1.2.0', 'c120', '2026-11-11T00:00:00Z', '["next","welcome"]');
  assert.match(ok, /promote=true/);
  const state = remoteState(s, 'production');
  assert.equal(state.ref, 'v1.2.0', 'still the same release: a content rebuild is not a release');
  assert.equal(state.commit, 'c120');
  assert.deepEqual(state.published, ['next', 'welcome']);

  // A content rebuild of v1.2.0 that finishes AFTER v1.3.0 shipped must not undo it.
  promote(s.work, 'production', 'release', D('4'), 'v1.3.0', 'c130', '2026-11-12T00:00:00Z', '["welcome"]');
  const stale = promote(s.work, 'production', 'content', D('5'), 'v1.2.0', 'c120', '2026-11-12T00:01:00Z', '["later","next","welcome"]');
  assert.match(stale, /promote=false/);
  assert.match(stale, /superseded/);
  assert.equal(remoteState(s, 'production').ref, 'v1.3.0');
  assert.equal(remoteState(s, 'production').digest, D('4'));
});

test('a rejected push is retried from fresh state, and the retry still wins', () => {
  const s = sandbox();
  // The remote refuses the first push it ever sees (as if someone pushed first), then behaves.
  const marker = path.join(s.root, 'rejected-once');
  const hook = path.join(s.remote, 'hooks', 'pre-receive');
  fs.mkdirSync(path.dirname(hook), { recursive: true });
  fs.writeFileSync(hook, `#!/bin/sh\nif [ ! -f '${marker}' ]; then touch '${marker}'; echo 'simulated race' >&2; exit 1; fi\n`);
  fs.chmodSync(hook, 0o755);

  const out = promote(s.work, 'staging', 'staging', D('a'), 'main', 'c1', '2026-11-10T00:00:00Z', '[]');
  assert.ok(fs.existsSync(marker), 'the first push really was rejected');
  assert.match(out, /promote=true/);
  assert.equal(remoteState(s, 'staging').digest, D('a'));
});

test('plan: due only when the deployed source has posts that became visible', () => {
  const s = sandbox();
  const posts = path.join(s.root, 'posts');
  fs.mkdirSync(posts);
  const post = (name, date) => fs.writeFileSync(path.join(posts, name), `---\ndate: ${date}\n---\nbody\n`);
  post('welcome.md', '2026-10-28 09:00:00 -0600');
  post('next.md', '2026-11-09 09:00:00 -0600');

  const plan = (now) => execFileSync('node', ['scripts/deploy-state.mjs', 'plan', '--env', 'production', '--now', now, '--posts-dir', posts], { cwd: s.work, encoding: 'utf8' });

  assert.match(plan('2026-11-20T00:00:00Z'), /due=false/, 'nothing deployed yet: nothing to rebuild');

  promote(s.work, 'production', 'release', D('1'), 'v1.2.0', 'c120', '2026-11-01T00:00:00Z', '["welcome"]');
  git(s.work, 'pull', '-q', 'origin', 'main');
  assert.match(plan('2026-11-09T14:59:00Z'), /due=false/, 'one minute early');
  assert.match(plan('2026-11-09T15:00:00Z'), /due=true/, 'at the scheduled instant');
  assert.match(plan('2026-12-25T00:00:00Z'), /due=true/, 'a run that was delayed for weeks still catches up');
});

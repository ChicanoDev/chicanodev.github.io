import assert from 'node:assert/strict';
import { test } from 'node:test';
import { classifyChanges, dueAt, isDue, nextPatch, releasable } from './blog-schedule.mjs';

const post = (date, extra = '') => `---\ntitle: "T"\ndate: ${date}\ndescription: "d"\n${extra}---\n\nBody\n`;

// --- what a scheduled blog PR may touch -------------------------------------

test('classify: posts and their assets are allowed, posts are listed', () => {
  const r = classifyChanges([
    'src/content/posts/new-post.md',
    'src/content/posts/series/part-1.mdx',
    'public/images/new-post/diagram.png',
    'public/recordings/demo.mp4',
  ]);
  assert.deepEqual(r.posts, ['src/content/posts/new-post.md', 'src/content/posts/series/part-1.mdx']);
  assert.deepEqual(r.disallowed, []);
});

test('classify: code, config, workflows and other public files are not blog content', () => {
  const r = classifyChanges([
    'src/content/posts/new-post.md',
    'src/lib/posts.ts',
    '.github/workflows/deploy.yml',
    'package.json',
    'public/CNAME',
    'src/content/posts/notes.txt',
  ]);
  assert.deepEqual(r.posts, ['src/content/posts/new-post.md']);
  assert.deepEqual(r.disallowed, ['src/lib/posts.ts', '.github/workflows/deploy.yml', 'package.json', 'public/CNAME', 'src/content/posts/notes.txt']);
});

// --- when is a PR due --------------------------------------------------------

test('dueAt: the latest date across the PR posts, as an instant', () => {
  const d = dueAt([post('2026-11-20 09:00:00 -0600'), post('2026-11-21 09:00:00 -0600')]);
  assert.equal(d.toISOString(), '2026-11-21T15:00:00.000Z');
});

test('dueAt: a draft can never be scheduled', () => {
  assert.throws(() => dueAt([post('2026-11-20 09:00:00 -0600', 'draft: true\n')]), /draft/i);
});

test('dueAt: a date without an explicit offset is ambiguous and rejected', () => {
  assert.throws(() => dueAt([post('2026-11-20 09:00:00')]), /offset/i);
  assert.throws(() => dueAt([post('2026-11-20')]), /offset/i);
  // Z and +hh:mm are explicit
  assert.equal(dueAt([post('2026-11-20T15:00:00Z')]).toISOString(), '2026-11-20T15:00:00.000Z');
  assert.equal(dueAt([post('2026-11-20T09:00:00-06:00')]).toISOString(), '2026-11-20T15:00:00.000Z');
});

test('dueAt: a PR with no posts has nothing to schedule', () => {
  assert.throws(() => dueAt([]), /no post/i);
});

test('isDue: the same rule as isPublished, the exact instant counts', () => {
  const due = new Date('2026-11-20T15:00:00Z');
  assert.equal(isDue(due, new Date('2026-11-20T14:59:59Z')), false);
  assert.equal(isDue(due, new Date('2026-11-20T15:00:00Z')), true);
  assert.equal(isDue(due, new Date('2026-11-21T00:00:00Z')), true);
});

// --- may main be released automatically --------------------------------------

test('releasable: content, docs and bot overlay commits only', () => {
  const r = releasable([
    'src/content/posts/new-post.md',
    'public/images/x.png',
    'docs/k8s-migration/runbook.md',
    'deploy/k8s/overlays/production/release.json',
    'deploy/k8s/overlays/staging/kustomization.yaml',
  ]);
  assert.deepEqual(r, { ok: true, blocking: [] });
});

test('releasable: any unreleased code or config blocks the automatic release', () => {
  const r = releasable(['src/content/posts/new-post.md', 'src/components/Header.astro', 'deploy/k8s/base/deployment.yaml', 'README.md']);
  assert.equal(r.ok, false);
  assert.deepEqual(r.blocking, ['src/components/Header.astro', 'deploy/k8s/base/deployment.yaml', 'README.md']);
});

// --- the next release tag ----------------------------------------------------

test('nextPatch: highest strict vX.Y.Z wins, numerically, others ignored', () => {
  assert.equal(nextPatch(['v1.0.0']), 'v1.0.1');
  assert.equal(nextPatch(['v1.0.9', 'v1.0.10', 'v1.2.0-rc1', 'latest', 'v0.9.0']), 'v1.0.11');
  assert.equal(nextPatch(['v1.9.3', 'v1.10.0']), 'v1.10.1');
});

test('nextPatch: no release yet means there is nothing to patch', () => {
  assert.throws(() => nextPatch(['latest']), /no release/i);
});

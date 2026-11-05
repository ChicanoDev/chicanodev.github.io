// Builds the site at pinned instants (BUILD_NOW) and checks that publication
// follows the clock, not the code. This is the deterministic-time test for
// scheduled publishing: no waiting for a date to arrive.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { publishedSlugs } from './published-posts.mjs';

const POSTS = 'src/content/posts';

function buildAt(buildNow) {
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'chicanodev-dist-'));
  execFileSync('npx', ['astro', 'build', '--outDir', outDir], {
    env: { ...process.env, BUILD_NOW: buildNow },
    stdio: 'pipe',
  });
  return outDir;
}

function builtSlugs(outDir) {
  return fs
    .readdirSync(path.join(outDir, 'posts'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

const read = (outDir, rel) => fs.readFileSync(path.join(outDir, rel), 'utf8');

test('just before the fixture date it is absent everywhere; just after, it appears everywhere', () => {
  const before = '2099-01-01T17:59:59Z'; // 12:00 -0600 is 18:00Z
  const after = '2099-01-01T18:00:00Z';

  const early = buildAt(before);
  assert.equal(fs.existsSync(path.join(early, 'posts/scheduled-preview/index.html')), false);
  for (const rel of ['index.html', 'posts/index.html', 'archives/index.html', 'rss.xml', 'feed.xml', 'sitemap-0.xml']) {
    assert.doesNotMatch(read(early, rel), /scheduled-preview/, `${rel} leaked the future post`);
  }

  const late = buildAt(after);
  assert.ok(fs.existsSync(path.join(late, 'posts/scheduled-preview/index.html')));
  assert.match(read(late, 'posts/scheduled-preview/index.html'), /__CHICANODEV_FUTURE_FIXTURE__/);
  for (const rel of ['posts/index.html', 'archives/index.html', 'rss.xml', 'sitemap-0.xml', 'tags/future-fixture/index.html', 'categories/future-fixture/index.html']) {
    assert.match(read(late, rel), /scheduled-preview|future-fixture/, `${rel} missed the now-published post`);
  }

  // Drafts stay hidden no matter how late the clock is.
  assert.equal(fs.existsSync(path.join(late, 'posts/draft-preview/index.html')), false);
  assert.doesNotMatch(read(late, 'rss.xml'), /__CHICANODEV_DRAFT_FIXTURE__|draft-preview/);

  // CI predicts "what will be published" without building. The prediction must
  // equal what the real build produced, or scheduled rebuilds would loop.
  assert.deepEqual(builtSlugs(early), publishedSlugs(POSTS, new Date(before)));
  assert.deepEqual(builtSlugs(late), publishedSlugs(POSTS, new Date(after)));
});

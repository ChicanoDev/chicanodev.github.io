import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { isPublished, resolveNow } from '../src/lib/publishing.ts';
import { publishedSlugs, parseFrontmatter } from './published-posts.mjs';

const at = (iso) => new Date(iso);

test('drafts are never published, even when their date has passed', () => {
  const draft = { draft: true, date: at('2020-01-01T00:00:00Z') };
  assert.equal(isPublished(draft, at('2030-01-01T00:00:00Z')), false);
});

test('future-dated posts are hidden until their publication instant', () => {
  const post = { draft: false, date: at('2026-11-09T15:00:00Z') };
  assert.equal(isPublished(post, at('2026-11-09T14:59:59.999Z')), false);
  assert.equal(isPublished(post, at('2026-11-09T15:00:00Z')), true, 'exactly now is published');
  assert.equal(isPublished(post, at('2026-11-10T00:00:00Z')), true);
});

test('the offset in front matter decides the instant (America/Chicago, CST vs CDT)', () => {
  // CST (-0600): 09:00 local is 15:00Z.
  const winter = { draft: false, date: new Date('2026-11-09 09:00:00 -0600') };
  assert.equal(isPublished(winter, at('2026-11-09T14:59:59Z')), false);
  assert.equal(isPublished(winter, at('2026-11-09T15:00:00Z')), true);
  // CDT (-0500), after the March change: 09:00 local is 14:00Z.
  const summer = { draft: false, date: new Date('2027-03-15 09:00:00 -0500') };
  assert.equal(isPublished(summer, at('2027-03-15T13:59:59Z')), false);
  assert.equal(isPublished(summer, at('2027-03-15T14:00:00Z')), true);
});

test('resolveNow: BUILD_NOW wins, empty means the real clock, garbage fails loudly', () => {
  assert.equal(resolveNow('2026-11-09T15:00:00Z').toISOString(), '2026-11-09T15:00:00.000Z');
  const before = Date.now();
  const clock = resolveNow('').valueOf();
  assert.ok(clock >= before && clock <= Date.now() + 1000, 'empty falls back to the clock');
  assert.ok(Math.abs(resolveNow(undefined).valueOf() - Date.now()) < 5000);
  assert.throws(() => resolveNow('next tuesday-ish'), /BUILD_NOW/);
});

test('parseFrontmatter reads the fields publishing depends on', () => {
  const fm = parseFrontmatter('---\ntitle: "A: b"\ndate: 2026-11-09 09:00:00 -0600\ndraft: true\n---\nbody');
  assert.equal(fm.draft, true);
  assert.equal(fm.date.toISOString(), '2026-11-09T15:00:00.000Z');
  const quoted = parseFrontmatter("---\ndate: '2026-11-09T09:00:00-06:00'\n---\n");
  assert.equal(quoted.draft, false, 'draft defaults to false like the schema');
  assert.equal(quoted.date.toISOString(), '2026-11-09T15:00:00.000Z');
});

test('publishedSlugs lists exactly the posts visible at a given instant', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'posts-'));
  const write = (name, fm) => fs.writeFileSync(path.join(dir, name), `---\n${fm}\n---\nbody\n`);
  write('old.md', 'date: 2026-01-01 09:00:00 -0600');
  write('later.mdx', 'date: 2026-11-09 09:00:00 -0600');
  write('draft.md', 'date: 2026-01-01 09:00:00 -0600\ndraft: true');
  assert.deepEqual(publishedSlugs(dir, at('2026-06-01T00:00:00Z')), ['old']);
  assert.deepEqual(publishedSlugs(dir, at('2026-11-09T15:00:00Z')), ['later', 'old']);
});

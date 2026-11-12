// Which posts are public at a given instant? Used by CI to decide whether a
// scheduled rebuild is due, without building anything.
//
//   node scripts/published-posts.mjs [--dir src/content/posts] [--now ISO]
//
// Prints a sorted JSON array of post ids. It mirrors what the Astro build
// publishes (src/lib/publishing.ts); the release workflow compares this
// prediction with the built site and fails if they ever disagree.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { isPublished, resolveNow } from '../src/lib/publishing.ts';

/** Minimal front matter reader: only `date` and `draft` matter for publishing. */
export function parseFrontmatter(text) {
  const block = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!block) throw new Error('missing front matter');
  const field = (name) => {
    const m = block[1].match(new RegExp(`^${name}:\\s*(.*?)\\s*$`, 'm'));
    return m ? m[1].replace(/^(['"])(.*)\1$/, '$2') : undefined;
  };
  const rawDate = field('date');
  if (!rawDate) throw new Error('front matter has no date');
  const date = new Date(rawDate);
  if (Number.isNaN(date.valueOf())) throw new Error(`unparseable date: ${rawDate}`);
  return { date, rawDate, draft: field('draft') === 'true' };
}

function* postFiles(dir, prefix = '') {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) yield* postFiles(path.join(dir, entry.name), `${prefix}${entry.name}/`);
    else if (/\.(md|mdx)$/.test(entry.name)) yield `${prefix}${entry.name}`;
  }
}

export function publishedSlugs(dir, now) {
  const slugs = [];
  for (const rel of postFiles(dir)) {
    const post = parseFrontmatter(fs.readFileSync(path.join(dir, rel), 'utf8'));
    if (isPublished(post, now)) slugs.push(rel.replace(/\.(md|mdx)$/, ''));
  }
  return slugs.sort();
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const opt = (name, fallback) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : fallback;
  };
  const now = resolveNow(opt('--now', process.env.BUILD_NOW));
  console.log(JSON.stringify(publishedSlugs(opt('--dir', 'src/content/posts'), now)));
}

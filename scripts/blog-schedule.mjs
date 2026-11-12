// Scheduled blog PRs: a PR labelled `blog:scheduled` is merged and released
// automatically once every post in it is due (its front matter `date`).
// The workflows (.github/workflows/blog-pr-check.yml, blog-ship.yml) call the
// CLI below; the rules themselves are the pure functions, unit-tested in
// blog-schedule.test.mjs.
//
//   node scripts/blog-schedule.mjs check [--now ISO] <post.md>...  # validate, print {dueAt, due}
//   node scripts/blog-schedule.mjs classify   < paths.txt    # print {posts, disallowed}
//   node scripts/blog-schedule.mjs releasable < paths.txt    # print {ok, blocking}
//   node scripts/blog-schedule.mjs next-tag   < tags.txt     # print vX.Y.Z+1
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseFrontmatter } from './published-posts.mjs';
import { compareSemver, parseSemver } from './deploy-state.mjs';
import { isPublished } from '../src/lib/publishing.ts';

const POST = /^src\/content\/posts\/.+\.(md|mdx)$/;
const ASSET = /^public\/(images|recordings)\/./;
// Changes that cannot alter how the site behaves: posts, their assets, docs, and
// the CI bot's own digest commits. Anything else needs a human release.
const RELEASABLE = [POST, ASSET, /^docs\//, /^deploy\/k8s\/overlays\//];
const EXPLICIT_OFFSET = /(Z|[+-]\d{2}:?\d{2})$/;

/** Split a PR's changed paths into posts and anything a blog PR must not touch. */
export function classifyChanges(paths) {
  const posts = [];
  const disallowed = [];
  for (const p of paths) {
    if (POST.test(p)) posts.push(p);
    else if (!ASSET.test(p)) disallowed.push(p);
  }
  return { posts, disallowed };
}

/** When the PR may ship: the latest date of its posts. Throws on anything ambiguous. */
export function dueAt(postTexts) {
  if (postTexts.length === 0) throw new Error('no post in this PR');
  let latest = null;
  for (const text of postTexts) {
    const { date, rawDate, draft } = parseFrontmatter(text);
    if (draft) throw new Error('a draft cannot be scheduled; set draft: false');
    if (!EXPLICIT_OFFSET.test(rawDate.trim())) {
      throw new Error(`date "${rawDate}" has no UTC offset; write e.g. 2026-11-20 09:00:00 -0600`);
    }
    if (!latest || date > latest) latest = date;
  }
  return latest;
}

/** Same rule the build uses: due at the exact instant. */
export function isDue(due, now) {
  return isPublished({ date: due, draft: false }, now);
}

/** May main be tagged without a human? Only if nothing but content changed. */
export function releasable(paths) {
  const blocking = paths.filter((p) => !RELEASABLE.some((re) => re.test(p)));
  return { ok: blocking.length === 0, blocking };
}

/** Next patch after the highest strict vX.Y.Z tag. */
export function nextPatch(tags) {
  const releases = tags.filter((t) => parseSemver(t)).sort(compareSemver);
  if (releases.length === 0) throw new Error('no release tag yet; cut the first one with scripts/release.sh');
  const [major, minor, patch] = parseSemver(releases.at(-1));
  return `v${major}.${minor}.${patch + 1}`;
}

const stdinLines = () =>
  fs
    .readFileSync(0, 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

function main([command, ...args]) {
  switch (command) {
    case 'check': {
      const i = args.indexOf('--now');
      const now = i >= 0 ? new Date(args[i + 1]) : new Date();
      const files = i >= 0 ? args.filter((_, j) => j !== i && j !== i + 1) : args;
      const due = dueAt(files.map((f) => fs.readFileSync(f, 'utf8')));
      return { dueAt: due.toISOString(), due: isDue(due, now) };
    }
    case 'classify':
      return classifyChanges(stdinLines());
    case 'releasable':
      return releasable(stdinLines());
    case 'next-tag':
      return nextPatch(stdinLines());
    default:
      throw new Error('usage: blog-schedule.mjs check <files...> | classify | releasable | next-tag');
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const out = main(process.argv.slice(2));
    console.log(typeof out === 'string' ? out : JSON.stringify(out));
  } catch (error) {
    console.error(`blog-schedule: ${error.message}`);
    process.exit(1);
  }
}

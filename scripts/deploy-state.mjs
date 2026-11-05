// Deployment state lives in Git, one pair of files per environment:
//
//   deploy/k8s/overlays/<env>/kustomization.yaml   image digest (what Argo CD syncs)
//   deploy/k8s/overlays/<env>/release.json         what that digest was built from
//
// CI never talks to Argo CD or the cluster. It builds an image, then calls
// `promote` here, which decides whether the new image should become the
// desired state and rewrites those two files. A workflow commits the result.
//
// Three kinds of change reach an environment:
//   release  production: a new vX.Y.Z tag (new application code)
//   staging  staging:    a new commit on main (new application code)
//   content  either:     the SAME source rebuilt later, so posts whose date has
//                        passed become visible. Not a release: no new code.
//
//   node scripts/deploy-state.mjs plan    --env <env> --now ISO [--posts-dir DIR]
//   node scripts/deploy-state.mjs promote --env <env> --kind <kind> --digest sha256:… \
//        --ref <ref> --commit <sha> --build-now ISO --published '["slug",…]' [--rollback]
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DIGEST = /^sha256:[0-9a-f]{64}$/;

export function parseSemver(tag) {
  const m = typeof tag === 'string' ? tag.match(/^v(\d+)\.(\d+)\.(\d+)$/) : null;
  return m ? m.slice(1).map(Number) : null;
}

export function compareSemver(a, b) {
  const [x, y] = [parseSemver(a), parseSemver(b)];
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i];
  return 0;
}

const sameSet = (a, b) => a.length === b.length && [...a].sort().every((v, i) => v === [...b].sort()[i]);

/** Does the deployed source have posts that became due since it was built? */
export function needsContentRebuild(current, eligible) {
  if (!current.ref) return false; // nothing deployed yet
  return !sameSet(current.published ?? [], eligible);
}

/**
 * Should `incoming` replace `current` as the desired state?
 * Pure function: every "late workflow must not win" rule is here, under test.
 */
export function decidePromotion({ kind, current, incoming, rollback = false, incomingIsAncestorOfCurrent = false }) {
  const no = (reason) => ({ promote: false, reason });
  const yes = (reason) => ({ promote: true, reason });

  if (kind === 'release') {
    if (!parseSemver(incoming.ref)) return no(`'${incoming.ref}' is not a vX.Y.Z release tag`);
    if (!parseSemver(current.ref)) return yes('first release');
    const order = compareSemver(incoming.ref, current.ref);
    if (order === 0) return no(`${incoming.ref} is already deployed`);
    if (order < 0 && !rollback) return no(`${incoming.ref} is older than deployed ${current.ref} (late workflow? pass rollback to go back on purpose)`);
    return yes(order < 0 ? `rollback to ${incoming.ref}` : `release ${incoming.ref}`);
  }

  if (kind === 'content') {
    if (incoming.ref !== current.ref || incoming.commit !== current.commit) {
      return no(`superseded: deployed source changed to ${current.ref}@${current.commit} while this rebuild ran`);
    }
    if (sameSet(incoming.published ?? [], current.published ?? [])) return no('nothing new to publish: publication set unchanged');
    return yes('content rebuild of the deployed source');
  }

  if (kind === 'staging') {
    if (incoming.commit === current.commit) return no(`${incoming.commit} is already deployed`);
    if (incomingIsAncestorOfCurrent) return no(`${incoming.commit} is older than deployed ${current.commit}`);
    return yes('newer commit on main');
  }

  return no(`unknown kind '${kind}'`);
}

export const overlayDir = (env, root = 'deploy/k8s/overlays') => path.join(root, env);

export function readState(dir) {
  return JSON.parse(fs.readFileSync(path.join(dir, 'release.json'), 'utf8'));
}

/** Rewrite release.json and only the digest line of kustomization.yaml. */
export function applyPromotion(dir, next) {
  if (!DIGEST.test(next.digest ?? '')) throw new Error(`digest must look like sha256:<64 hex>, got ${JSON.stringify(next.digest)}`);

  const kfile = path.join(dir, 'kustomization.yaml');
  const text = fs.readFileSync(kfile, 'utf8');
  if (!/digest:\s*sha256:[0-9a-f]{64}/.test(text)) throw new Error(`${kfile} has no digest: line to update`);
  fs.writeFileSync(kfile, text.replace(/(digest:\s*)sha256:[0-9a-f]{64}/, `$1${next.digest}`));

  const { digest, ref, commit, buildNow, published } = next;
  fs.writeFileSync(path.join(dir, 'release.json'), `${JSON.stringify({ ref, commit, buildNow, digest, published: [...published].sort() }, null, 2)}\n`);
}

// ---------------------------------------------------------------- CLI ----

function isAncestor(older, newer) {
  try {
    execFileSync('git', ['merge-base', '--is-ancestor', older, newer], { stdio: 'ignore' });
    return true;
  } catch {
    return false; // not an ancestor, or an object is missing: treat as not stale
  }
}

function emit(values) {
  for (const [key, value] of Object.entries(values)) {
    console.log(`${key}=${value}`);
    if (process.env.GITHUB_OUTPUT) fs.appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${value}\n`);
  }
}

async function main(argv) {
  const [command, ...rest] = argv;
  const opt = (name, fallback) => {
    const i = rest.indexOf(`--${name}`);
    return i >= 0 ? rest[i + 1] : fallback;
  };
  const env = opt('env');
  if (!env) throw new Error('--env is required');
  const dir = overlayDir(env);
  const current = readState(dir);

  if (command === 'plan') {
    const { publishedSlugs } = await import('./published-posts.mjs');
    const { resolveNow } = await import('../src/lib/publishing.ts');
    const eligible = publishedSlugs(opt('posts-dir', 'src/content/posts'), resolveNow(opt('now')));
    const due = needsContentRebuild(current, eligible);
    emit({
      due,
      ref: current.ref ?? '',
      commit: current.commit ?? '',
      eligible: JSON.stringify(eligible),
      reason: !current.ref ? 'nothing deployed yet' : due ? 'posts became due' : 'publication set unchanged',
    });
    return;
  }

  if (command === 'promote') {
    const kind = opt('kind');
    const incoming = {
      digest: opt('digest'),
      ref: opt('ref'),
      commit: opt('commit'),
      buildNow: opt('build-now'),
      published: JSON.parse(opt('published', '[]')),
    };
    const verdict = decidePromotion({
      kind,
      current,
      incoming,
      rollback: rest.includes('--rollback'),
      incomingIsAncestorOfCurrent: kind === 'staging' && current.commit ? isAncestor(incoming.commit, current.commit) : false,
    });
    if (verdict.promote) applyPromotion(dir, incoming);
    emit({ promote: verdict.promote, reason: verdict.reason });
    return;
  }

  throw new Error(`unknown command '${command}' (expected plan or promote)`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch((error) => {
    console.error(`deploy-state: ${error.message}`);
    process.exit(1);
  });
}

// Container acceptance test. Builds the production image and checks it the way
// Kubernetes will run it: read-only root, no capabilities, non-root user.
//
// Run with `npm run test:container`. It needs Docker, so it is not part of
// `npm test` (which has to work on a laptop without a container runtime).
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { execFileSync } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const IMAGE = process.env.CONTAINER_TEST_IMAGE ?? 'chicanodev-site:container-test';
const NAME = `chicanodev-container-test-${process.pid}`;
let base;

function docker(...args) {
  return execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}

async function get(path, init = {}) {
  return fetch(`${base}${path}`, { redirect: 'manual', ...init });
}

before(async () => {
  if (!process.env.CONTAINER_TEST_IMAGE) docker('build', '--tag', IMAGE, '.');

  // Same restrictions the Deployment applies: read-only root, writable /tmp
  // only, every capability dropped, no privilege escalation.
  docker(
    'run', '--detach', '--rm', '--name', NAME,
    '--read-only', '--tmpfs', '/tmp',
    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
    '--publish', '127.0.0.1::8080',
    IMAGE,
  );
  const port = docker('port', NAME, '8080/tcp').split(':').pop();
  base = `http://127.0.0.1:${port}`;

  for (let attempt = 0; attempt < 50; attempt++) {
    try {
      if ((await get('/healthz')).status === 200) return;
    } catch {
      // not listening yet
    }
    await sleep(200);
  }
  assert.fail(`container never became healthy:\n${docker('logs', NAME)}`);
});

after(() => {
  try {
    docker('rm', '--force', NAME);
  } catch {
    // already gone (--rm)
  }
});

test('health endpoint answers 200 and is never cached', async () => {
  const res = await get('/healthz');
  assert.equal(res.status, 200);
  assert.match(res.headers.get('cache-control') ?? '', /no-store/);
});

test('clean URLs: directory index served, missing slash redirects relatively', async () => {
  const page = await get('/posts/welcome/');
  assert.equal(page.status, 200);
  assert.match(await page.text(), /<h1>Welcome to ChicanoDev<\/h1>/);

  const redirect = await get('/posts/welcome');
  assert.equal(redirect.status, 301);
  // Relative Location: behind Cloudflare and Traefik the container does not
  // know its public host or scheme, so it must not invent one.
  assert.equal(redirect.headers.get('location'), '/posts/welcome/');
});

test('HTML, feeds and sitemaps revalidate on every request', async () => {
  for (const path of ['/', '/posts/welcome/', '/rss.xml', '/sitemap-index.xml']) {
    const res = await get(path);
    assert.equal(res.status, 200, path);
    assert.match(res.headers.get('cache-control') ?? '', /max-age=0/, path);
    assert.match(res.headers.get('cache-control') ?? '', /must-revalidate/, path);
  }
});

test('fingerprinted /_astro assets are immutable for a year', async () => {
  const html = await (await get('/')).text();
  const asset = html.match(/\/_astro\/[^"')\s]+\.css/)?.[0];
  assert.ok(asset, 'home page references no /_astro css file');
  const res = await get(asset);
  assert.equal(res.status, 200);
  assert.match(res.headers.get('cache-control') ?? '', /max-age=31536000/);
  assert.match(res.headers.get('cache-control') ?? '', /immutable/);
});

test('unknown paths get the site 404 page with a 404 status', async () => {
  const res = await get('/definitely/not/here/');
  assert.equal(res.status, 404);
  assert.match(await res.text(), /<html/i);
});

test('security headers are present', async () => {
  const res = await get('/');
  assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(res.headers.get('x-frame-options'), 'DENY');
  assert.equal(res.headers.get('referrer-policy'), 'strict-origin-when-cross-origin');
  assert.equal(res.headers.get('server'), 'nginx', 'server_tokens should be off');
});

test('/version.json reports what was built', async () => {
  const res = await get('/version.json');
  assert.equal(res.status, 200);
  const body = await res.json();
  for (const key of ['ref', 'commit', 'buildNow']) assert.ok(key in body, `version.json missing ${key}`);
});

test('runs as an unprivileged user on a read-only root', () => {
  const uid = Number(docker('exec', NAME, 'id', '-u'));
  assert.notEqual(uid, 0, 'container runs as root');
  assert.notEqual(docker('inspect', '--format', '{{.Config.User}}', IMAGE), '', 'image has no USER set');

  assert.throws(() => docker('exec', NAME, 'touch', '/should-fail'), /Read-only file system/);
  docker('exec', NAME, 'touch', '/tmp/should-work');
});

test('image contains only the compiled site', () => {
  const stray = docker(
    'exec', NAME, 'sh', '-c',
    'find / -xdev \\( -name node_modules -o -name package.json -o -name "*.astro" -o -name .git \\) -not -path "/proc/*" 2>/dev/null | head',
  );
  assert.equal(stray, '', `build leftovers in the image:\n${stray}`);
});

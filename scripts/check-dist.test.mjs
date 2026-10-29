import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';

const dist = path.resolve('dist');
const site = 'https://chicanodev.github.io';

function walk(dir) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...walk(full));
    else files.push(full);
  }
  return files;
}

function readPage(urlPath) {
  const rel = urlPath.replace(/^\//, '');
  const file = rel.endsWith('/') || rel === ''
    ? path.join(dist, rel, 'index.html')
    : path.join(dist, rel);
  assert.ok(fs.existsSync(file), `missing ${urlPath} (${file})`);
  return fs.readFileSync(file, 'utf8');
}

function pageFile(urlPath) {
  const [pathname] = urlPath.split('#');
  const rel = pathname.replace(/^\//, '');
  if (rel === '') return path.join(dist, 'index.html');
  if (path.extname(rel)) return path.join(dist, rel);
  if (rel === '404' || rel === '404/') return path.join(dist, '404.html');
  return path.join(dist, rel, 'index.html');
}

test('required pages and preserved copy', () => {
  const home = readPage('/');
  const about = readPage('/about/');
  const welcome = readPage('/posts/welcome/');
  const source = fs.readFileSync('src/content/posts/welcome.md', 'utf8');

  assert.match(home, /Engineering knowledge belongs to everyone/);
  assert.match(home, /\$ ls ~\/knowledge/);
  assert.match(home, /No recordings yet/);
  assert.equal((home.match(/<h1[\s>]/g) || []).length, 1);

  const inclusion =
    'ChicanoDev is a welcoming space for people of all backgrounds, identities, and experience levels. Racism, sexism, homophobia, and transphobia have no place here.';
  assert.ok(about.includes(inclusion));
  assert.match(about, /Built on experience\. Shared with everyone\./);

  for (const phrase of [
    'Compaq Portable',
    'DOS 3.1',
    'Slackware',
    'LGBTQIA+',
    'University of New Mexico',
    "Knowledge isn't something we should hoard.",
    "Welcome to ChicanoDev. Let's share what we know.",
  ]) {
    assert.ok(source.includes(phrase), `source missing ${phrase}`);
    assert.ok(welcome.includes(phrase), `html missing ${phrase}`);
  }
  assert.doesNotMatch(source, /^# Welcome to ChicanoDev$/m);
  assert.equal((welcome.match(/<h1[\s>]/g) || []).length, 1);
  assert.match(welcome, /<h1>Welcome to ChicanoDev<\/h1>/);
  assert.match(welcome, /October 28, 2026/);
  assert.match(welcome, new RegExp(`rel="canonical" href="${site}/posts/welcome/"`));
  assert.match(welcome, /property="og:title"/);
  assert.match(welcome, /name="description"/);
  assert.match(welcome, /application\/ld\+json/);

  for (const urlPath of [
    '/posts/',
    '/archives/',
    '/categories/',
    '/categories/welcome/',
    '/categories/introduction/',
    '/tags/',
    '/tags/linux/',
    '/tags/devops/',
    '/tags/programming/',
    '/tags/chicanodev/',
    '/rss.xml',
    '/feed.xml',
    '/robots.txt',
  ]) {
    assert.ok(fs.existsSync(pageFile(urlPath)), `missing ${urlPath}`);
  }

  const robots = fs.readFileSync(path.join(dist, 'robots.txt'), 'utf8');
  assert.match(robots, new RegExp(`Sitemap: ${site}/sitemap-index\\.xml`));
  assert.ok(fs.existsSync(path.join(dist, 'sitemap-index.xml')));

  const feed = fs.readFileSync(path.join(dist, 'rss.xml'), 'utf8');
  const legacyFeed = fs.readFileSync(path.join(dist, 'feed.xml'), 'utf8');
  assert.match(feed, /Welcome to ChicanoDev/);
  assert.equal(feed, legacyFeed);

  const css = walk(dist).filter((file) => file.endsWith('.css')).map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  assert.match(css, /prefers-reduced-motion/);

  const jsBytes = walk(dist)
    .filter((file) => file.endsWith('.js'))
    .reduce((total, file) => total + fs.statSync(file).size, 0);
  assert.ok(jsBytes < 5000, `local JavaScript is ${jsBytes} bytes`);
});

test('internal links resolve', () => {
  const htmlFiles = walk(dist).filter((file) => file.endsWith('.html'));
  const missing = [];

  for (const file of htmlFiles) {
    const html = fs.readFileSync(file, 'utf8');
    const urls = [];
    for (const match of html.matchAll(/\s(?:href|src)="([^"]+)"/g)) urls.push(match[1]);
    for (const match of html.matchAll(/\ssrcset="([^"]+)"/g)) {
      for (const part of match[1].split(',')) {
        const url = part.trim().split(/\s+/)[0];
        if (url) urls.push(url);
      }
    }

    for (const raw of urls) {
      if (raw.startsWith('mailto:') || raw.startsWith('javascript:')) continue;
      let url = raw;
      if (url.startsWith(site)) url = url.slice(site.length) || '/';
      if (/^[a-z]+:/i.test(url)) continue;

      const hashIndex = url.indexOf('#');
      const hash = hashIndex >= 0 ? url.slice(hashIndex + 1) : '';
      const pathname = hashIndex >= 0 ? url.slice(0, hashIndex) : url;
      const target = pathname === '' ? file : pageFile(pathname.startsWith('/') ? pathname : new URL(pathname, `https://local${file.slice(dist.length).replace(/index\.html$/, '')}`).pathname);
      if (!fs.existsSync(target)) {
        missing.push(`${path.relative(dist, file)} -> ${raw}`);
        continue;
      }
      if (hash && fs.existsSync(target) && target.endsWith('.html')) {
        const targetHtml = fs.readFileSync(target, 'utf8');
        if (!targetHtml.includes(`id="${hash}"`)) {
          missing.push(`${path.relative(dist, file)} -> ${raw}`);
        }
      }
    }
  }

  assert.deepEqual(missing, []);
});

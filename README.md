# ChicanoDev

**Built on experience. Shared with everyone.**

Practical Linux, DevOps, programming, and AI automation tutorials. The site is published at [chicanodev.com](https://chicanodev.com/).

## Requirements

Node.js 24. The exact version is in `.node-version`.

```sh
nvm use 24
npm install
```

`package.json` allows `>=24 <25`.

## Commands

```sh
npm run dev       # local site at http://localhost:4321
npm run build     # static site in dist/
npm run preview   # serve dist/
npm run check     # Astro and TypeScript
npm test          # check, production build, link and content checks, browser tests
```

Browser tests use Playwright with Chromium. The first run needs:

```sh
npx playwright install chromium
```

## New article

Add `src/content/posts/your-slug.md`. The filename is the URL slug. This file is served at `/posts/your-slug/`.

```md
---
title: "Post title"
date: 2026-11-01 09:00:00 -0500
description: "One or two sentences."
categories: [linux]
tags: [shell]
---

## First section

Write the article here. Do not add an H1. The title field is the page heading.
```

`updatedDate` and `draft: true` are optional. Drafts are omitted from production builds, including pages, RSS, and the sitemap. `src/content/posts/draft-preview.md` is a fixture used by the production checks to prove that filtering.

For a YouTube embed or a local terminal recording, use MDX (`your-slug.mdx`) and the same front matter:

```mdx
import YouTube from '../../components/YouTube.astro';
import TerminalRecording from '../../components/TerminalRecording.astro';

## Demo

<YouTube id="videoId" title="What the recording shows" />

<TerminalRecording src="/recordings/demo.mp4" title="Installing the tool" />
```

Put local videos in `public/recordings/`. `src` must be a site path such as `/recordings/demo.mp4`. YouTube uses the privacy-enhanced embed and does not add a player script of our own.

## Theme

Dark uses the Dracula palette and is the signature theme. Light uses Alucard, Dracula's light variant. The first visit follows the system preference. The header control saves an explicit choice in `localStorage` under `chicanodev-theme`.

## Analytics

Production builds load Google Analytics `G-VK281QV7N1`, the measurement ID already set on the Jekyll site. No other tracker is included. Set `analyticsId` to `''` in `src/data/site.ts` to turn it off. Local `dev` does not load it. `preview` serves the production build, so it does.

## GitHub Pages

The site is a static export for `https://chicanodev.com` with `base: '/'`. Canonical URLs, Open Graph, RSS, and the sitemap use that origin. `public/CNAME` keeps the GitHub Pages custom domain set to `chicanodev.com`.

GitHub Pages already redirects `https://chicanodev.github.io/...` to the custom domain while preserving the path (for example `/posts/welcome/`). After HTTPS finishes provisioning, turn on **Settings → Pages → Enforce HTTPS** so those redirects land on `https://chicanodev.com` instead of `http://`.

`.github/workflows/deploy.yml` runs the full check and test suite on the commit being published, then uploads `dist` and deploys. That job runs only for pushes to `main` and for manual runs on `main`. Pull requests and other branches run the same tests and do not deploy. A green check on a different workflow is not what gates the deploy. The publish job runs the tests itself.

Repository settings that must stay as they are:
- **Settings → Pages → Build and deployment → Source: GitHub Actions**
- **Custom domain:** `chicanodev.com`

`public/.nojekyll` is copied into the build so GitHub Pages will not run Jekyll on the artifact.

## Fonts

Atkinson Hyperlegible and IBM Plex Mono are vendored at build time and used under the SIL Open Font License. See `NOTICE`.

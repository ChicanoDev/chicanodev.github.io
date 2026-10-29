import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import { satteri } from '@astrojs/markdown-satteri';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://chicanodev.com',
  base: '/',
  trailingSlash: 'always',
  output: 'static',
  integrations: [mdx(), sitemap()],
  markdown: {
    processor: satteri({ features: { smartPunctuation: false } }),
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'dracula',
      },
      defaultColor: false,
    },
  },
});

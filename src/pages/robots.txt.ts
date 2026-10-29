import type { APIContext } from 'astro';
import { site } from '../data/site';

export function GET(context: APIContext): Response {
  const origin = context.site ?? site.url;
  const body = `User-agent: *\nAllow: /\n\nSitemap: ${origin}sitemap-index.xml\n`;
  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}

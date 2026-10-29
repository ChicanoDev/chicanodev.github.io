import type { APIContext } from 'astro';
import { buildFeed } from '../lib/feed';

export async function GET(context: APIContext): Promise<Response> {
  return buildFeed(context);
}

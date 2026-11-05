import { getCollection, type CollectionEntry } from 'astro:content';
import { site } from '../data/site';
import { isPublished, resolveNow } from './publishing';

export type Post = CollectionEntry<'posts'>;

// One cutoff per build. Resolved once so every page, feed and sitemap in the
// same build agrees on what "published" means, even if the build straddles a
// minute boundary. CI pins it with BUILD_NOW; otherwise it is the real clock.
let buildNow: Date | undefined;
function cutoff(): Date {
  buildNow ??= resolveNow(process.env.BUILD_NOW);
  return buildNow;
}

export async function getPosts(): Promise<Post[]> {
  const posts = await getCollection('posts', ({ data }) => {
    // `astro dev` shows drafts and scheduled posts so they can be previewed.
    if (!import.meta.env.PROD) return true;
    return isPublished(data, cutoff());
  });
  return posts.sort((a, b) => b.data.date.valueOf() - a.data.date.valueOf());
}

export function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/\+/g, ' plus ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

export function readingMinutes(body: string | undefined): number {
  const words = (body ?? '').trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}

export function formatDate(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'long',
    timeZone: site.timezone,
  }).format(date);
}

export interface TermGroup {
  name: string;
  slug: string;
  posts: Post[];
}

export function groupBy(posts: Post[], key: 'categories' | 'tags'): TermGroup[] {
  const groups = new Map<string, TermGroup>();
  for (const post of posts) {
    for (const name of post.data[key]) {
      const slug = slugify(name);
      const existing = groups.get(slug);
      if (existing) {
        existing.posts.push(post);
      } else {
        groups.set(slug, { name, slug, posts: [post] });
      }
    }
  }
  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
}

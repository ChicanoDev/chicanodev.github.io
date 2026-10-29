import { getCollection, type CollectionEntry } from 'astro:content';
import { site } from '../data/site';

export type Post = CollectionEntry<'posts'>;

export async function getPosts(): Promise<Post[]> {
  const posts = await getCollection('posts', ({ data }) => {
    if (import.meta.env.PROD) return !data.draft;
    return true;
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

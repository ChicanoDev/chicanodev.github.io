// The one place that decides whether a post is public.
//
// A static site has no "request time": whatever is visible is decided when the
// site is built. So "scheduled publishing" means "rebuild after the post's
// date has passed". These functions take `now` as an argument instead of
// reading the clock, which keeps them deterministic and testable.
//
// Keep this file free of Astro imports: scripts/published-posts.mjs runs it
// under plain Node (CI uses it to decide whether a rebuild is due).

export interface Publishable {
  draft: boolean;
  date: Date;
}

/** Published = not a draft AND its date (an exact instant) is not in the future. */
export function isPublished(post: Publishable, now: Date): boolean {
  return !post.draft && post.date.valueOf() <= now.valueOf();
}

/**
 * The publication cutoff for a build. `BUILD_NOW` (an ISO-8601 instant) pins it
 * for tests and for CI, which stamps every build; unset or empty means the real
 * clock. A malformed value throws rather than silently publishing everything.
 */
export function resolveNow(value?: string): Date {
  if (value === undefined || value.trim() === '') return new Date();
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    throw new Error(`BUILD_NOW is not a valid date: ${JSON.stringify(value)}`);
  }
  return parsed;
}

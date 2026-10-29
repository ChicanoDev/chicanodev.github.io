export const site = {
  title: 'ChicanoDev',
  tagline: 'Built on experience. Shared with everyone.',
  description:
    'Practical Linux, DevOps, programming, and AI automation tutorials. Sharing decades of engineering experience to make technology more accessible, especially to Chicanos, Latinx people, LGBTQIA+ folks, and other underrepresented communities.',
  url: 'https://chicanodev.github.io',
  author: 'Dave Vigil',
  timezone: 'America/Chicago',
  github: 'https://github.com/chicanodev',
  youtube: '',
  instagram: '',
  analyticsId: 'G-VK281QV7N1',
} as const;

export const socialLinks = [
  { label: 'GitHub', href: site.github },
  { label: 'YouTube', href: site.youtube },
  { label: 'Instagram', href: site.instagram },
].filter((link) => link.href.length > 0);

import { defineConfig } from 'astro/config';

// Fully static output. For GitHub Pages project sites set SITE_BASE=/ipl-auction-arena
// (and optionally SITE_URL); Cloudflare Pages / root domains need nothing.
export default defineConfig({
  output: 'static',
  site: process.env.SITE_URL || undefined,
  base: process.env.SITE_BASE || '/',
  trailingSlash: 'always',
});

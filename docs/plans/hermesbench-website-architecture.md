# HermesBench website architecture decision

## Decision
Keep the website as a small static site for v0.1. It builds with `pnpm build`, has no framework dependency, reads checked-in JSON demo data, and can later switch to API-backed data without changing the public information architecture.

## Criteria
- **Vercel deploy speed:** static output from `website/dist` deploys quickly.
- **Static demo mode:** checked-in JSON files let releases preview leaderboard/result pages before the hosted API exists.
- **API-backed mode:** the client data model mirrors future API submissions and can fetch `HERMESBENCH_API_URL` later.
- **Route count:** landing, methodology, tasks, leaderboard, result, submissions, and why pages are simple enough for static generation.
- **Dependency footprint:** no Next/Astro dependency until dynamic routes, authentication, or server-side rendering are necessary.
- **CI build time:** `node build.js` copies static assets and validates JSON quickly.

## Migration trigger
Move to Astro or Next.js only when live API-backed result detail pages, search, or authenticated submission flows justify the added dependencies.

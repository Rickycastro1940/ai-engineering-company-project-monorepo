# Brasaland public website

Public-facing corporate site for **Brasaland** (see root [`CONTEXT.md`](../../CONTEXT.md)).

**Location:** `uis/website/` — matches the monorepo template’s `uis/website` slot (Marketing / Camila Ospina).  
`uis/web/` remains the separate incident-analysis HTML tool; do not conflate the two.

## Stack

- React 19 + TypeScript + Vite
- **Tailwind CSS v4** (`@tailwindcss/vite`) with Brasaland theme tokens in `src/styles/index.css`
- React Router: `/` (home), `/locations`, `/brasa-points`
- Copy/facts in `src/content/brand.ts` and location roster in `src/content/locations.ts` (aligned with `CONTEXT.md`)

## Run

```bash
cd uis/website
npm install
npm run dev
```

Open the printed local URL (default `http://localhost:5173/`).

```bash
npm run build   # production build → dist/
npm run preview # serve dist/
```

## Routes

| Path | Purpose |
| --- | --- |
| `/` | Corporate home — brand hero, commitments, markets, Brasa Points teaser |
| `/locations` | 14 company-owned sites (Colombia COP / Florida USD) |
| `/brasa-points` | Loyalty programme status (physical stamp cards today) |

## Structure

```text
src/
  components/   # SiteHeader, Hero, BrandPillars, Markets, LoyaltyTeaser, SiteFooter
  content/      # brand.ts, locations.ts — CONTEXT-aligned facts
  pages/        # HomePage, LocationsPage, BrasaPointsPage
  styles/       # index.css — Tailwind + @theme brand tokens
```

## Tailwind notes (Web UI Fundamentals)

- Theme colors and fonts live under `@theme` in `src/styles/index.css` (`brasa-*` utilities).
- Layout and typography use utility classes; grill-atmosphere gradients stay in `@layer components` (`.hero-glow`, `.hero-grill`).
- Motion: `animate-ember-pulse`, `animate-fade-up`, `animate-fade-in` (respects `prefers-reduced-motion`).

## Academy checklist — Web UI Fundamentals with Tailwind

| Checkpoint | Evidence |
| --- | --- |
| Tailwind installed | `package.json` → `tailwindcss`, `@tailwindcss/vite` |
| Vite plugin wired | `vite.config.ts` |
| Theme / design tokens | `@theme` in `src/styles/index.css` |
| Utility-first components | Header, Hero, pillars, markets, loyalty, footer |
| Multi-page routing | `/`, `/locations`, `/brasa-points` |
| Responsive layout | `sm:` / `md:` / `lg:` grids; mobile nav hides links |
| Build green | `npm run build` |
| Screenshots | `docs/screenshots/website-tailwind-*.png` |

After this branch is merged (or the PR is submitted to graders), refresh the 4Geeks academy progress row for **Web UI Fundamentals with Tailwind** until it shows 100% delivered.

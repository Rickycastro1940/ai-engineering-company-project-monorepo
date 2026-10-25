# Brasaland public website

Later Vite experiment for **Brasaland** (Camila Ospina / Marketing). Production publishes [`../website-classic/`](../website-classic/README.md), the photo menu site restored from commit `2465196`. This folder is not the build Vercel serves.

**Location:** `uis/website/` — not `uis/web/` (incident HTML tool).

## Stack

- React 19 + TypeScript + Vite
- **Tailwind CSS v4** (`@tailwindcss/vite`) with Brasaland `@theme` tokens
- React Router: `/`, `/locations`, `/brasa-points`, `/join`
- Header **EN / ES** toggle (`localStorage` key `brasaland-lang`). English is the default and keeps the BRIEFING error strings.
- System fonts and an inline story graphic (no Google Fonts, no remote photo) so the first load stays on this origin.

## Run (local or Codespaces)

```bash
cd uis/website
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Forward port **5173** as **Public** in Codespaces so graders can open the preview URL.

```bash
npm run build
npm run preview -- --host 0.0.0.0 --port 4173
```

Codespaces-friendly static preview of a production build:

```bash
cd uis/website && npm run build && npx --yes serve dist -l 3000
```

## Routes

| Path | Purpose |
| --- | --- |
| `/` | Landing — hero, story, pillars, markets, Brasa Points, contact + Schema.org |
| `/locations` | 14 sites (Colombia 10 / Florida 4) |
| `/brasa-points` | Loyalty programme overview |
| `/join` | Brasa Points registration form (BRIEFING fields + validation) |

## Form validation (`/join`)

Matches BRIEFING: full name (2+ words), email, phone `+57`/`+1`, country → city → favorite location, dietary optional, how found, DOB 18+, terms required, offers optional. Clear + success states included. Online ordering disclaimer is visible on the form and contact section.

## Academy checklist

| Checkpoint | Evidence |
| --- | --- |
| Tailwind | `package.json`, `vite.config.ts`, `src/styles/index.css` |
| Landing sections | `HomePage.tsx` |
| Signup form | `pages/JoinPage.tsx` + `lib/validateLoyaltyForm.ts` |
| Schema.org Restaurant | `components/SchemaOrg.tsx` |
| Responsive + a11y | Tailwind `md:`/`lg:`, labels, `aria-*`, story SVG `aria-label` |
| ES/EN | Header toggle in `SiteHeader.tsx`, copy in `src/i18n/LanguageContext.tsx` |
| Public Codespaces URL | Forward Vite/serve port as Public; paste URL in the PR |

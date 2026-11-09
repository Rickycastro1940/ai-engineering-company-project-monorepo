# Advantage AI Solutions site

Visual redesign of [advantageaisolutions.pro](https://advantageaisolutions.pro). The layout follows the structure of a large enterprise infrastructure homepage: announcement bar, oversized headline, product console, problem grid, module cards, dark principles band, and a four-step path.

Copy, offers, phone, email, and Miramar location stay Advantage’s. Graphics are original. Nothing is copied from NetApp trademarks, product names, photography, or page source.

The assistant still calls Advantage’s curated retrieval API through `/api/chat`. The evaluation form posts to `/api/contact`, which forwards to the current production endpoint until this folder is the deployment that owns the domain.

## Run

```bash
node uis/advantage-ai/server.mjs
```

Open `http://127.0.0.1:4173`. Routes: `/`, `/services`, `/contact`.

This folder is not the Brasaland public site (`uis/website-classic/`).

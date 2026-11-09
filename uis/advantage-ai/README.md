# Advantage AI Solutions site

Visual redesign of [advantageaisolutions.pro](https://advantageaisolutions.pro). The layout follows the structure of a large enterprise infrastructure homepage: announcement bar, oversized headline, product console, problem grid, module cards, dark principles band, and a four-step path.

Copy, offers, phone, email, and Miramar location stay Advantage’s. Graphics are original. Nothing is copied from NetApp trademarks, product names, photography, or page source.

The assistant still calls Advantage’s curated retrieval API through `/api/chat`. The evaluation form posts to `/api/contact`, which sends mail through the Hostinger mailbox for `info@advantageaisolutions.pro`.

## Contact email

The recipient and sender are fixed in the project as `info@advantageaisolutions.pro`. Hostinger’s server is `smtp.hostinger.com` on port 465. The only deployment value left is `SMTP_PASS`, the password for that mailbox.

Until that password is set, `/api/contact` delivers the same JSON to the current live contact endpoint, which already emails that inbox. A filled honeypot returns success and sends nothing. Set `CONTACT_UPSTREAM=off` to refuse delivery instead of using the live endpoint.

## Run

```bash
node uis/advantage-ai/build.mjs
node uis/advantage-ai/server.mjs
```

`build.mjs` runs the contact tests, checks that every page includes `info@advantageaisolutions.pro`, and writes `dist/`. The dev server reads the source folder. Serve `dist/` with `PORT=4174 node dist/server.mjs` after a build.

Open `http://127.0.0.1:4173`. Routes: `/`, `/services`, `/contact`. The contact tests use a local mail sink and do not send a message to the mailbox.

This folder is not the Brasaland public site (`uis/website-classic/`).

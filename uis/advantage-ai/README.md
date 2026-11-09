# Advantage AI Solutions site

Visual redesign of [advantageaisolutions.pro](https://advantageaisolutions.pro). The layout follows the structure of a large enterprise infrastructure homepage: announcement bar, oversized headline, product console, problem grid, module cards, dark principles band, and a four-step path.

Copy, offers, phone, email, and Miramar location stay Advantage’s. Graphics are original. Nothing is copied from NetApp trademarks, product names, photography, or page source.

The assistant still calls Advantage’s curated retrieval API through `/api/chat`. The evaluation form posts to `/api/contact`, which sends mail through the Hostinger mailbox for `info@advantageaisolutions.pro`.

## Contact email

Set these on the deployment. `SMTP_USER` and `SMTP_PASS` are the mailbox login, not values to put in the repo.

```bash
SMTP_HOST=smtp.hostinger.com
SMTP_PORT=465
SMTP_USER=info@advantageaisolutions.pro
SMTP_PASS=
CONTACT_TO=info@advantageaisolutions.pro
```

The message is sent from `SMTP_USER`, with the visitor’s address as Reply-To. Hostinger accepts mail from the authenticated mailbox. A filled honeypot field returns success and sends nothing. Without `SMTP_USER` and `SMTP_PASS`, the form responds that delivery is not configured. Set `CONTACT_UPSTREAM` only when a different contact endpoint should receive the JSON instead.

## Run

```bash
node --test uis/advantage-ai/api/contact.test.mjs
node uis/advantage-ai/server.mjs
```

Open `http://127.0.0.1:4173`. Routes: `/`, `/services`, `/contact`. The contact tests use a local mail sink and do not send a message to the mailbox.

This folder is not the Brasaland public site (`uis/website-classic/`).

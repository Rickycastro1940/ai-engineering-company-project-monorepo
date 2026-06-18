# Backoffice UI

Authenticated internal backoffice for the company monorepo.

## Run locally

Start the API from the repository root:

```bash
uvicorn api.app:app --reload
```

Start the Next.js app:

```bash
cd uis/backoffice
npm install
npm run dev
```

The frontend calls `http://127.0.0.1:8000` by default. Override with:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Authentication

- `login` and `register` call the API and store the returned JWT in `localStorage`.
- Protected API calls attach `Authorization: Bearer <token>`.
- Protected routes redirect unauthenticated users to `/login`.
- Logout removes the token and redirects to `/login`.

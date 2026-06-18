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
- `/account/profile` displays the current user and updates the name through `PUT /users/{id}`.
- `/account/change-password` validates password confirmation before calling the API.
- Logout removes the token and redirects to `/login`.

## Route protection inventory

Protected views in this Next.js app:

- `/` — operations dashboard with protected inventory data.
- `/account/profile` — account profile, current user data, and profile editing.
- `/account/change-password` — password change form.
- `/profile` — compatibility redirect to `/account/profile`.

Public views in this Next.js app:

- `/login`
- `/register`

The public website in `uis/web` remains outside this Next.js app and has no token check or login redirect.

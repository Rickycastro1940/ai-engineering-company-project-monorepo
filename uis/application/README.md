# Brasaland application UI

This static frontend provides the Brasaland supplier directory.

## Features

- Application menu link to the supplier directory.
- Supplier table with name, country, categories, current rate, and status.
- Client-side controls that call the `/suppliers` API without reloading the page.
- Supplier registration form using `POST /suppliers`.
- Inline rate updates using `PATCH /suppliers/{id}/rate`.
- Inline active/suspended status updates using `PATCH /suppliers/{id}/status`.
- Visual badges and row styling for active vs suspended suppliers.

## Run locally

From the repository root:

```bash
uv run seed
uvicorn api.app:app --reload
```

Then open `http://127.0.0.1:8000/`.

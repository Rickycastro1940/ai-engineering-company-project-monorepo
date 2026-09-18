# testing.md — Brasaland auth API

**Company:** Brasaland (`CONTEXT.md`).  
**Department served:** Technology (Nicolás Park) — JWT staff auth so Operations/Executive consoles can trust login, register, and location/stock reads.

Tests assert **what the application decides** (who is admin, whether a session starts, whether a password still works), not HTTP envelope fields (`token_type`, `code`, `detail.loc`) or FastAPI/Pydantic internals.

## How to run

```bash
# Python (repo root)
uv sync
uv pip install -r requirements.txt
uv run pytest
uv run pytest --cov

# TypeScript staff-console helpers
cd uis/backoffice
npm install
npx jest --coverage
```

`.coveragerc` measures `services/api/auth.py` and `services/api/users.py` and fails below **70%**.  
`tests/pipelines/` is ignored by default (needs `supabase`/`prefect`).

Last verified on this branch:

- `uv run pytest` → 75 passed
- `uv run pytest --cov` → auth.py 98%, users.py 94%, TOTAL 95%
- `npx jest --coverage` (uis/backoffice) → 12 passed, authUtils.ts 100% statements (threshold 70)

## AI-assisted workflow

Prompt used against `services/api/users.py` + `locations.py` vs `inventory.py`: *which staff routes require a session, and which cases does `tests/test_users_api.py` miss?*

That review produced the per-endpoint happy / edge / failure modules under `test/` (inactive login, mixed-case email, duplicate PUT email, blank profile name, JWT with the wrong secret) and the Jest cases for client token/password policy.

## AI-found bug (caught by this suite)

**Finding:** kitchen stock (`GET /inventory` and the other inventory routes) did not require a staff session.

**How we found it:** `/locations` uses `Depends(get_current_user)`; `services/api/inventory.py` did not. `test_anonymous_cannot_read_kitchen_stock` showed an anonymous `GET /inventory` returned the product list.

**Fix:** inventory router now has `dependencies=[Depends(get_current_user)]`.

**Regression test:** `test/test_users.py::test_anonymous_cannot_read_kitchen_stock`.

## What each `test/` module asserts

| Module | Happy | Edge | Failure |
| --- | --- | --- | --- |
| `test_register.py` | Named staff + hashed password | Lowercased email; only first user is admin | Duplicate mailbox; short password creates no row |
| `test_login.py` | Known password starts a session | Case-insensitive email | Unknown mailbox and wrong password both refuse; inactive staff |
| `test_token.py` | Form login is that account | Mixed-case username | Wrong password; inactive staff |
| `test_me.py` | Session identity matches stored user | JWT `sub` is the user id | Expired, forged, malformed, or inactive session |
| `test_profiles.py` | Contact fields persist | Partial update; blank name stored empty | Anonymous write refused; extra `is_admin` does not escalate |
| `test_users.py` | Admin can list/read others; password change | — | Duplicate email on update; member cannot delete others; short password; anonymous stock |
| `test_auth.py` | Hash/verify; JWT subject round-trip | Secret from environment | Token without a user subject |

Comments in those files call out non-obvious rules (first user is admin, unknown email looks like a wrong password, profile cannot self-promote).

Jest (`uis/backoffice/src/auth/authUtils.test.ts`) covers token store, JWT shape, email/password policy, and that empty matching strings are not a password change.

**Not tested here:** OpenAPI schema shape, `token_type: bearer`, error JSON `code`/`detail` lists (covered in `tests/test_error_handling.py` as a separate error-envelope audit).

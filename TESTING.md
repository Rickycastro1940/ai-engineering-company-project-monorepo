# TESTING.md — Brasaland auth API

**Company:** Brasaland (`CONTEXT.md`).  
**Department served:** Technology (Nicolás Park) — JWT staff auth so Operations/Executive consoles can trust login, register, and location/stock reads.

Tests assert **what the application decides** (who is admin, whether a session starts, whether a password still works), not HTTP envelope fields (`token_type`, `code`, `detail.loc`) or FastAPI/Pydantic internals.

## How to run

```bash
uv sync
uv pip install -r requirements.txt   # python-multipart for /auth/token
uv run pytest
uv run pytest --cov
```

`.coveragerc` measures `services/api/auth.py` and `services/api/users.py` and fails below **70%**.  
`tests/pipelines/` is ignored by default (needs `supabase`/`prefect`).

## AI-found bug (caught by this suite)

**Finding:** kitchen stock (`GET /inventory`, and the other inventory routes) did not require a staff session.

**How we found it:** reviewing `/auth/*` vs `/locations` showed locations use `Depends(get_current_user)`, while `services/api/inventory.py` did not. A generated case `test_anonymous_cannot_read_kitchen_stock` then proved an anonymous `GET /inventory` returned the product list instead of refusing a session.

**Fix:** inventory router now has `dependencies=[Depends(get_current_user)]`, same as locations. Staff can still list stock with a Bearer token.

**Regression test:** `test/test_users.py::test_anonymous_cannot_read_kitchen_stock`.

## What each `test/` module asserts

| Module | Decision under test |
| --- | --- |
| `test_register.py` | First account is admin; email is unique and lowercased; blank name is stored empty; short password does not create a row; password is hashed |
| `test_login.py` | Known password starts a session; email is case-insensitive; unknown mailbox and wrong password both refuse a session; inactive staff cannot log in |
| `test_token.py` | Form `username` is the same email account; inactive/wrong password refuse a session |
| `test_me.py` | Token subject is that user id; expired, forged, malformed, or inactive sessions are not trusted |
| `test_profiles.py` | Contact fields persist; omitted fields stay; extra `is_admin` does not escalate |
| `test_users.py` | Admin can read others; password change replaces the credential; duplicate email on update is refused; members cannot delete others |
| `test_auth.py` | Hash/verify; JWT subject round-trip; secret from environment |

**Not tested here:** OpenAPI schema shape, `token_type: bearer`, error JSON `code`/`detail` lists (covered in `tests/test_error_handling.py` as a separate error-envelope audit).

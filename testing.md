# TESTING.md — Brasaland auth API

**Company:** Brasaland (`CONTEXT.md`).  
**Department served:** Technology (Nicolás Park) — JWT staff auth so Operations/Executive consoles can trust login, register, and location/stock reads.

The FastAPI auth surface lives under `services/api/` (`auth.py`, `users.py`) and is loaded by `api.app:app`. New pytest modules for that surface are in `test/` (collected with the existing `tests/` tree).

## What the suite is for

Tests assert **staff-session decisions**, not HTTP envelopes (`token_type`, `code`, `detail.loc`) and not FastAPI/Pydantic internals.

Each case exists because a kitchen or HQ operator would notice the wrong outcome:

- Who gets the first admin account, and who stays a member.
- Whether a known password starts a session (including mixed-case email).
- Whether unknown mailbox, wrong password, or inactive staff all refuse a session — without leaking which mailbox exists.
- Whether a token still names that person after expiry, a wrong secret, or deactivation.
- Whether a member can self-promote or take another mailbox.
- Whether anonymous callers can read kitchen stock.

Coverage is a **floor, not a score**. `.coveragerc` fails below **70%** on `services/api/auth.py` and `services/api/users.py` so a hollow suite cannot ship. Lines left uncovered are unused CRUD helpers and error branches that do not change those decisions. We do not add cases only to raise the percentage.

`tests/pipelines/` is ignored by default (needs `supabase`/`prefect`).

## How to run

```bash
# Required: Python auth model (repo root)
uv sync
uv pip install -r requirements.txt
uv run pytest
uv run pytest --cov

# Optional extra: staff-console helpers (recognised if present and passing)
cd uis/backoffice
npm install
npx jest
```

Last verified on this branch: `uv run pytest` green; `uv run pytest --cov` above the 70% floor; `npx jest` 12 passing (optional).

## AI-assisted workflow

Prompt used against `services/api/users.py` + `locations.py` vs `inventory.py`: *which staff routes require a session, and which cases does `tests/test_users_api.py` miss?*

That review produced the per-endpoint happy / edge / failure modules under `test/` (inactive login, mixed-case email, duplicate PUT email, blank profile name, JWT with the wrong secret). Those were gaps in **who may act**, not missing lines in a coverage report.

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

## Optional: backoffice Jest

Not required to pass the auth-API evaluation. Present so the staff console (`uis/backoffice/src/auth/authUtils.ts`) will not store a malformed JWT or accept an empty password confirmation. Run with `npx jest` from `uis/backoffice`. Coverage threshold there is also a 70% floor, not a 100% target.

**Not tested in `test/`:** OpenAPI schema shape, `token_type: bearer`, error JSON `code`/`detail` lists (covered in `tests/test_error_handling.py` as a separate error-envelope audit).

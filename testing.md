# Testing plan — Brasaland auth API

**Company:** Brasaland (`CONTEXT.md`).  
**Department served:** Technology (Nicolás Park) — JWT staff auth so Operations/Executive consoles can trust login, register, and location reads.

This file is the plan for the bullet-proof auth suite on this **existing fork**. Tests target `uvicorn api.app:app`.

## How to run

From the repository root:

```bash
uv sync
uv run pytest
uv run pytest --cov
```

`.coveragerc` measures `services/api/auth.py` and `services/api/users.py` and fails below **70%**.  
`tests/pipelines/` needs `supabase`/`prefect` and is ignored by default so collection stays green.

Live API is optional (`TestClient` does not need uvicorn):

```bash
uv run uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

## Existing suites

| Suite | Covers |
| --- | --- |
| `tests/test_users_api.py` | Register/login/JWT, RBAC on `/users`, `/profiles/me`, locations overview |
| `test/test_*.py` | Per-endpoint happy / edge / failure, including cases the agent review found missing |
| `tests/test_error_handling.py` | HTTP envelopes, inventory I/O |
| `tests/test_scripts_io.py` | `scripts/analyze.py` |
| `tests/test_async_api_endpoints.py` / `tests/test_celery_async.py` | Weekly pipeline enqueue + DLQ |

## AI-assisted review (endpoint logic → missed cases)

Prompt used against `services/api/users.py` + `services/api/auth.py`: *for each route, list happy path, validation edges, and auth/RBAC failures that `tests/test_users_api.py` does not assert.*

### `POST /auth/register`

Logic: `create_user` with `is_admin=count_users()==0`, then JWT. Email is lowercased. Duplicate email → 409. Optional contact fields strip to `None`.

| Already covered | Missed (now in `test/test_register.py`) |
| --- | --- |
| 201 + token + public user | Second registrant is **not** admin |
| | Duplicate email on **this** route (not only `POST /users`) |
| | Whitespace-only `name` stored as `null` |
| | Password shorter than 8 → 422 |

### `POST /auth/login`

Logic: `authenticate_user` then reject inactive. Same 401 copy for wrong password and missing user.

| Already covered | Missed (now in `test/test_login.py`) |
| --- | --- |
| Valid JSON credentials | Mixed-case email |
| Wrong password → 401 | Unknown email → 401 (same shape) |
| | Inactive user → 401 |
| | Empty / invalid email → 422 |

### `POST /auth/token`

Logic: OAuth2 form; `username` is email. Inactive treated as bad credentials.

| Already covered | Missed (now in `test/test_token.py`) |
| --- | --- |
| Helper uses the route | Explicit form happy path |
| | Mixed-case `username` |
| | Wrong password → 401 |
| | Missing password field → 422 |
| | Inactive user → 401 |

### `GET /auth/me`

Logic: Bearer → `decode_access_token` → `int(sub)` → active user.

| Already covered | Missed (now in `test/test_me.py`) |
| --- | --- |
| Valid token, no token, malformed, expired | Non-numeric `sub` → 401 |
| | Token signed with a **wrong secret** → 401 |
| | Inactive user still holding a token → 401 |
| | JWT `sub` is the user id string |

### `PUT /profiles/me`

Logic: only `name`/`phone`/`address`; omitted fields stay `UNSET`. Extra keys ignored.

| Already covered | Missed (now in `test/test_profiles.py`) |
| --- | --- |
| Full contact update + anonymous 401 | Partial update (phone only; name preserved) |
| | Blank name → `null` |
| | `is_admin` in body ignored (cannot escalate) |

### `POST /users` and `/users/{id}`

Logic: first user admin; self-or-admin; members cannot set `is_active`/`is_admin`; duplicate email 409 on create **and** update.

| Already covered | Missed (now in `test/test_users.py`) |
| --- | --- |
| Duplicate create, RBAC, admin delete → 404 | Short password on create → 422 |
| | Login with the **new** password after self-update |
| | Duplicate email on **PUT** → 409 |
| | Member cannot delete another user → 403 |

### JWT helpers (`auth.py`)

| Already covered | Missed (now in `test/test_auth.py`) |
| --- | --- |
| Secret/expiry from env | Hash/verify round-trip and wrong password |
| | Encode/decode round-trip |
| | Empty/`null` `sub` rejected |

**Skipped on purpose:** menus/sales/customers/suppliers (not built); hashing-oracle timing tests; live Redis.

## Implementation order

1. Record this review in this file.  
2. Add `test/` modules for every missed row above.  
3. `uv run pytest` then `uv run pytest --cov` (≥70% on auth model).

# TESTING.md — Brasaland auth API (Building Bullet-Proof Applications)

**Company:** Brasaland (`CONTEXT.md`).  
**Department served:** Technology (Nicolás Park) — JWT staff auth so Operations/Executive consoles can trust register, login, and token sessions.  
**Ticket:** AUTH-088 — unit test coverage for the authentication API.

The FastAPI auth surface lives under `services/api/` (`auth.py`, `users.py`) and is loaded by `api.app:app`. Endpoint suites for this milestone are:

| Module | Endpoint / focus |
| --- | --- |
| `tests/test_register.py` | `POST /auth/register` |
| `tests/test_login.py` | `POST /auth/login` |
| `tests/test_token.py` | `POST /auth/token` + JWT decode decisions |

Shared fixtures: `tests/conftest.py`. Helpers: `tests/auth_helpers.py`. Broader staff CRUD coverage also lives in `tests/test_users_api.py`.

---

## Test plan (happy / edge / failure)

Decided **before** writing assertions. Each case is a staff-session decision Felipe’s or Ashley’s teams would notice — not HTTP envelope shape (`token_type`, `detail.loc`).

### `POST /auth/register` (`test_register.py`)

| Tier | Case | Why |
| --- | --- | --- |
| Happy | Valid email + password ≥ 8 chars → session + hashed password; first user is admin | Onboarding must work; HQ needs a bootstrap admin |
| Edge | Mixed-case email is stored lowercased; second user is not admin | Avoid duplicate mailboxes by case; privilege escalation |
| Failure | Duplicate mailbox → no new session; password under 8 chars → no row | Store integrity |

### `POST /auth/login` (`test_login.py`)

| Tier | Case | Why |
| --- | --- | --- |
| Happy | Known password starts a session for that mailbox | Staff can open the backoffice |
| Edge | Mixed-case email still authenticates | Operators type emails inconsistently |
| Failure | Unknown email and wrong password both refuse the same way; inactive staff denied | No mailbox enumeration; deactivated accounts stay out |

### `POST /auth/token` + JWT (`test_token.py`)

| Tier | Case | Why |
| --- | --- | --- |
| Happy | Form login token’s `sub` is the user id and `/auth/me` matches | OAuth2 clients and docs share one session model |
| Edge | Mixed-case form `username` | Same normalisation as JSON login |
| Failure | Wrong password; **expired JWT**; JWT signed with wrong secret; inactive staff | Catches the AUTH-088 regression (expired tokens locking people out / being accepted) |

Coverage is a **floor, not a score**. `.coveragerc` fails below **70%** on `services/api/auth.py` and `services/api/users.py`. We do not add cases only to raise the percentage.

`tests/pipelines/` is ignored by default in `pytest.ini` (Prefect/Supabase-heavy).

---

## How to run

```bash
# From repository root
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest pytest-cov 'uvicorn[standard]' python-multipart \
  'passlib[bcrypt]' 'bcrypt>=4.0.0,<5.0.0' 'python-jose[cryptography]' prefect

# Collect + run auth suites (and the rest of tests/)
pytest
# or only the AUTH-088 modules:
pytest tests/test_register.py tests/test_login.py tests/test_token.py -v

# Coverage floor on the authentication modules
pytest tests/test_register.py tests/test_login.py tests/test_token.py tests/test_users_api.py --cov
```

With `uv` (when available on the machine):

```bash
uv sync
uv pip install pytest-cov
uv run pytest
uv run pytest --cov
```

`pytest --cov` reads `.coveragerc` (include `auth.py` + `users.py`, `fail_under = 70`).

---

## AI-assisted workflow (concrete case)

**Prompt used** against `services/api/users.py` (`authenticate_user`, `login`, `login_for_access_token`):

> Which failure modes let an attacker or a deactivated teammate learn whether a Brasaland staff mailbox exists, or keep a session after HR deactivates them? Which cases does a minimal happy-path suite miss?

**Concrete case added from that review:**  
`test_login_denies_unknown_email_and_wrong_password_the_same_way` — assert that unknown email and wrong password both return no `access_token`, and that `authenticate_user` returns `None` for both. That is a **who may act / what we reveal** decision, not a missing line in a coverage report.

A second AI-suggested gap, also covered: inactive staff still pass `authenticate_user` (password hash is valid) but `POST /auth/login` and `POST /auth/token` must refuse a session (`test_login_denies_inactive_staff`, `test_token_rejects_inactive_staff_on_form_login`).

No production auth bug required a code change in this redo; the prior submission failed evaluation because the three modules had **syntax errors** (unclosed dict literals) and `TESTING.md` was empty, so pytest could not collect or measure coverage.

---

## What we assert (and what we do not)

**Assert:** session grant/refusal, email normalisation, first-admin rule, password hashing, JWT subject = user id, expired/forged token rejection, inactive staff blocked.

**Do not assert here:** OpenAPI schema shape, `token_type: "bearer"` as the main claim, Pydantic `detail.loc` lists (those belong to `tests/test_error_handling.py`).

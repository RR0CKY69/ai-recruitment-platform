# Project Diagnostic

## Summary

The reported login failure was not caused by a React/backend payload mismatch. The frontend sends the request shape required by FastAPI, and local CORS preflight succeeds. During the initial check the backend was not listening on its configured port, so a browser login could not reach it. The API is now listening and responds to health and preflight checks. No authorized account credentials were provided, so no real login was submitted and no credential-dependent result can be claimed.

Several separate application issues were reproduced and repaired in the React/API and ORM paths. No PostgreSQL data or users were changed, and no migration was applied.

## Login Diagnosis

| Item | Finding |
|---|---|
| Login URL | `http://localhost:8000/auth/login` (frontend default base URL plus `/auth/login`) |
| Request | `POST`, JSON object with `email` and `password`; no other fields are required. The password is not recorded here. |
| Expected success body | `{"access_token": "...", "token_type": "bearer", "expires_in": 900}` (the expiry value follows configured access-token lifetime) |
| Cookie | Success also sets an HttpOnly refresh-token cookie. The refresh token is not in the JSON body. |
| Expected status | `200` for valid active credentials; invalid credentials produce generic `401`. |
| Actual login status/body | Not available: no real login request was submitted because no authorized credentials were supplied. |
| Backend login exception/log | None available: no login request reached the backend during the initial unavailable-server check. |
| Initial runtime condition | No API listener was present on port 8000, so the browser request failed at the connection layer rather than receiving an HTTP status. |
| Current runtime checks | API `GET /health`: `200`; frontend `GET /`: `200`; `OPTIONS /auth/login` from `http://localhost:5173`: `200`, with credentials allowed and the requested origin/method/headers accepted. |

The React request in `frontend/src/features/auth/api.ts` is `{ email, password }`. The backend `LoginRequest` schema accepts exactly those fields, normalizes email, and rejects extras. A successful response matches the frontend `TokenResponse` type. There is no evidence of a request-schema mismatch.

The frontend default `VITE_API_BASE_URL` is `http://localhost:8000`; the backend's port is 8000. The backend CORS configuration allows both `http://localhost:5173` and `http://127.0.0.1:5173`. The real preflight returned HTTP 200. In the initial failure state, the concrete cause was that the API process was not running at the frontend's configured target. The API is responding now; actual credential acceptance remains unverified.

`AuthContext` now displays the backend's safe `detail` or HTTP status, and identifies a network failure with the configured API URL instead of always showing “Login failed.” This preserves generic backend handling for incorrect credentials.

## Confirmed Findings and Repairs

1. **Jobs and candidates API relationship loading** — endpoints eagerly loaded ORM relationships that were not declared on the mapped classes, causing request failures. Added the missing relationships and resolved relationship foreign-key ambiguity. Jobs/candidates API tests and the full Python suite pass.
2. **Evaluation-note ORM relationship** — evaluation responses needed the `EvaluationLabel.notes` relationship. Added the mapping needed by the API path and its tests.
3. **Workspace data integrity in ORM metadata** — added the constraints and composite relationship mappings exercised by database tests, including workspace role/label validation, case-insensitive candidate email uniqueness, and workspace-scoped job/candidate pairs.
4. **React job/candidate identifiers** — API responses use `id`; matching and shortlist pages expected `job_id`/`candidate_id`. The dashboard API adapter now normalizes those IDs, with regression tests.
5. **Evaluation selector ambiguity** — rendering the real workspace selector alongside the label selector made an existing test's generic combobox query ambiguous. The relevance selector now has an accessible name and its tests select it explicitly.
6. **Unsupported or fabricated frontend content** — removed fabricated dashboard metrics/workspace identity and clarified that Boolean Search and Settings do not yet have backend workflows. Streamlit no longer displays a fabricated workspace name.
7. **Rate-limit documentation** — corrected the README to state that failed credential checks, rather than successful logins, count toward the login limit.

## Database and Migration Safety

- Read-only inspection found 18 public PostgreSQL tables and an applied revision of `3c5e7a1b2d4f`; source Alembic head is `75d22e4b57a5`.
- No migrations were run against PostgreSQL. No rows, users, passwords, or refresh sessions were modified.
- The pending `75d22e4b57a5` migration deletes duplicate refresh-session token hashes before creating a unique index. A read-only query found zero duplicate hash groups, but the migration remains unapplied; do not apply it without explicit authorization and a reviewed backup/rollout plan.
- `alembic check` against the real database stopped because the database is behind the migration head, so it did not provide a complete schema-drift comparison. A disposable SQLite migration/check run also reported ORM-versus-migration differences; SQLite cannot fully reflect the expression-based indexes used by this project, so that result is not proof of PostgreSQL drift. Schema alignment remains an open follow-up.

## Validation

| Check | Result |
|---|---|
| Full Python suite | `276 passed` (60 warnings) |
| Focused backend/Streamlit authentication tests | `61 passed` (5 warnings) |
| Full frontend suite | `23 passed` |
| Focused frontend authentication tests | `5 passed` |
| Frontend production build (includes TypeScript build) | Passed; Vite reports a generated JavaScript chunk over 500 kB |
| Full Ruff check | Failed: 48 lint findings across the repository; no broad lint cleanup was made as part of this repair |
| Live API health / CORS preflight | `200` / `200` |

Warnings include existing deprecation, SQLAlchemy reflection, React `act(...)`, and list-key warnings. The relevant tests pass despite those warnings.

## Remaining Limitations

- No real credentials were supplied. A successful login, the real account's HTTP status, and any protected live workflow cannot be confirmed without an authorized user attempting sign-in.
- No request-specific backend login log or exception exists to report because the failed attempt occurred while the API was unavailable; the app's health check and CORS preflight do not exercise authentication or the database.
- The actual PostgreSQL database remains behind the source migration head, and complete production-schema comparison is pending.
- Streamlit's authenticated workflows were validated through tests, not a live authenticated session.

# Fix Log

## Repairs

- Added missing SQLAlchemy relationships and clarified foreign-key paths used by job, candidate, and evaluation API queries.
- Added ORM constraints and workspace-scoped composite relationships required by database integrity tests.
- Normalized backend job/candidate `id` values to the identifiers expected by React matching and shortlist screens; added adapter tests and aligned page fixtures.
- Made the evaluation label selector accessible by name and updated its tests to disambiguate it from the workspace selector.
- Replaced fabricated login-page metrics and hard-coded workspace names with supported, workspace-backed content.
- Clarified unsupported React Boolean Search and Settings workflows and removed the fabricated Streamlit settings workspace name.
- Corrected README text describing which login attempts consume the rate limit.
- Improved login failure feedback to show a safe backend detail/status or a connection message containing the configured API base URL.

## Validation Results

- Python: `276 passed`; authentication-specific backend/Streamlit tests: `61 passed`.
- Frontend: `23 passed`; authentication-focused tests: `5 passed`.
- TypeScript and production frontend build: passed; Vite emitted a bundle-size advisory.
- Ruff: failed with 48 repository findings. No unrelated repository-wide lint changes were made.
- Live health and CORS preflight: both returned HTTP 200.

## Safety and Follow-Up

- No PostgreSQL data, user records, credentials, or refresh sessions were changed.
- No Alembic migration was applied to the configured PostgreSQL database.
- The actual database is at revision `3c5e7a1b2d4f` while source head is `75d22e4b57a5`. The head migration includes duplicate refresh-token cleanup before making the token-hash index unique; it must be reviewed and explicitly authorized before application.
- A real login could not be attempted because no authorized credentials were supplied. The request contract matches the backend; initial diagnosis found the API was not listening on the configured port. Current health and CORS checks pass.

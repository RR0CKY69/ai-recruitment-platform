# Migration Safety and Live Verification

**Scope:** Read-only review of the PostgreSQL database at the current Alembic revision, pending migrations, model metadata, and the live API/UI. No migration was applied and no database records were changed.

## Migration Safety Report

### Revisions and pending migrations

- **Current PostgreSQL revision:** `3c5e7a1b2d4f`
- **Source Alembic head:** `75d22e4b57a5`
- **Pending chain:**

| Revision | Operation | Data/schema effect |
|---|---|---|
| `ebf570f17769` | Add non-unique `ix_refresh_sessions_token_hash` index. | Adds an index; does not change rows. |
| `75d22e4b57a5` | Delete duplicate token-hash rows, drop the non-unique index, and create unique `uq_refresh_sessions_token_hash`. | May delete refresh-session rows if duplicate hashes exist; then replaces the index with a unique one. |

These are the only revisions between the live database revision and source head. `alembic current`, `alembic heads`, and `alembic history --verbose` were run read-only and confirmed this chain.

### Exact cleanup impact at inspection time

The migration partitions `refresh_sessions` by the exact `token_hash` value, orders each partition by `created_at`, and deletes rows with `row_number() > 1`. It therefore retains one earliest-created row per hash. The query has no secondary tie-breaker, so duplicate rows with equal `created_at` would not have a deterministic retained ID.

Read-only PostgreSQL results:

- `refresh_sessions` rows: **5**
- Duplicate token-hash groups: **0**
- Rows selected by the migration's delete query at inspection time: **0**
- Null hashes: **0**; observed hash lengths: **64**
- Unrevoked and unexpired sessions: **2**
- Existing token-hash indexes: **0**
- Foreign keys referencing `refresh_sessions`: **0**

Thus, at the inspected snapshot the cleanup would delete **no records**. It is nevertheless written as unconditional deletion logic; if duplicates appear before migration execution, it can remove active, unexpired sessions without considering their owner, family, revocation, or expiry. The table's only relevant FK is from refresh sessions to users, not from other tables to a refresh session.

### Database/model compatibility

The refresh-session table and columns needed by the two migrations exist, and the token-hash column is non-null `varchar(255)`. There is currently no token-hash index, consistent with revision `3c5e7a1b2d4f`; the first pending revision can create its index. The 64-character stored values are indexable in PostgreSQL.

There is a **target metadata mismatch**: current SQLAlchemy metadata declares a non-unique index named `ix_refresh_sessions_token_hash`; revision `75d22e4b57a5` instead leaves a **unique** index named `uq_refresh_sessions_token_hash`. Applying the pending chain would enforce uniqueness in the database, but the model would still describe a differently named, non-unique index. That contract must be reconciled before treating the target schema as aligned.

A separate read-only `compare_metadata` against the live PostgreSQL schema returned **41 differences**. One is the pending `ix_refresh_sessions_token_hash` index; the other **40** are pre-existing schema/model differences not addressed by these pending revisions:

- **Column definitions:** live `audit_logs.workspace_id` is non-nullable while the model permits null; `audit_logs.action` is `varchar(150)` vs model length 100. Live `evaluation_labels.relevance_label` is non-nullable vs nullable in the model, and `review_status` is length 20 vs model length 30. Live `search_queries.name` and `query_text` are non-nullable vs nullable in the model, and `query_type` is length 40 vs model length 20. Live `sourcing_tasks.source_provider` is non-nullable `varchar(150)` vs nullable length 100 in the model; `status` is length 20 vs 30; `progress_percent` is non-nullable vs nullable.
- **Unique constraints present in the database but absent from model metadata:** `candidate_skills(candidate_id, normalized_name)`, `candidate_sources(candidate_id, provider, source_record_id)`, `candidates(workspace_id, legacy_candidate_id)`, and `jobs(workspace_id, legacy_job_id)`.
- **Foreign-key semantics:** live reviewer/author FKs on evaluations use `RESTRICT`, while the model declares `CASCADE`. Live `search_queries` and `sourcing_tasks` use workspace/job composite FKs with `CASCADE`; the model describes separate job FKs with `SET NULL`.
- **Indexes:** 18 live indexes are not represented in model metadata: `audit_logs.ix_audit_logs_workspace_created`; `candidate_skills.ix_candidate_skills_candidate_id`; `candidate_sources.ix_candidate_sources_candidate_id`; `evaluation_labels.ix_evaluation_labels_job_candidate_id` and `ix_evaluation_labels_reviewer_id`; `evaluation_notes.ix_evaluation_notes_author_id` and `ix_evaluation_notes_evaluation_label_id`; `job_candidates.ix_job_candidates_candidate_id` and `ix_job_candidates_job_id`; `job_requirements.ix_job_requirements_job_id`; `search_queries.ix_search_queries_job_id` and `ix_search_queries_workspace_id`; `shortlists.ix_shortlists_job_candidate_id`; `sourcing_tasks.ix_sourcing_tasks_job_id` and `ix_sourcing_tasks_workspace_id`; `users.uq_users_email_ci`; and `workspace_members.ix_workspace_members_user_id` and `ix_workspace_members_workspace_id`. Do not drop these merely to make autogeneration agree.

`alembic check` returned `Target database is not up to date` and did not perform a full check. The separate metadata comparison above is observational only; it is not a migration plan. Blindly generating/applying a migration from all 41 differences could alter nullability/types and FK deletion behavior, or drop existing indexes and constraints.

### Risks and recommended safe sequence

**Risks**

1. The pending head's unique-index definition disagrees with current ORM metadata.
2. The 40 other model/schema differences remain after the pending chain and require intentional reconciliation.
3. If duplicates appear, the cleanup can delete refresh sessions; equal `created_at` values make survivor selection nondeterministic.
4. The migrations assume the preceding non-unique index exists. Their broad `except: pass` around `DROP INDEX` can hide an error; PostgreSQL may still mark the transaction failed if a drop statement errors.
5. Active API login/refresh traffic during deployment could contend with the index replacement and undermine a preflight snapshot.

**Recommended sequence**

1. Do not apply migrations yet. Review and reconcile the token-hash uniqueness contract between migration and ORM metadata; separately review the 40 existing differences and decide which are intentional.
2. Prepare and verify a restorable PostgreSQL backup; schedule a brief maintenance window and pause API writes/refreshes.
3. Immediately before migration, rerun read-only duplicate detection using the migration's exact partition/order logic. If any duplicate group exists, stop and explicitly review affected session state; do not rely on the current zero count if data changes before deployment.
4. After explicit approval, apply only the reviewed revision chain from `3c5e7a1b2d4f` to the approved head. Do not use autogeneration as a substitute for review.
5. Verify the Alembic revision, unique index definition, refresh-session row count and active-session behavior; then compare ORM metadata again and run focused authentication tests before restoring traffic.

## Live Application Verification

No owner-supplied credentials were available. No login request was submitted, no credential was guessed, and no password/token was logged. Protected route probes used real workspace/job identifiers from the database but sent **no Authorization header**. Therefore the following 401 responses verify authentication gating, not successful access to real data.

The read-only database inventory at the time of the probes was: 1 workspace, 1 membership, 5 jobs, 12 candidates, 22 evaluation labels, 6 shortlists, and 5 refresh sessions.

| Check | Actual status/result | Verification |
|---|---|---|
| `GET /health` | **200** — `{"status":"ok"}` | Live API process responds. |
| `POST /auth/login` | **Not attempted** | Owner credentials were not supplied. No actual login response or backend login traceback is available. |
| Workspace discovery / selection (`GET /workspaces`) | **401** — `Invalid or expired access token.` | No authorized workspace list or selection could be exercised. |
| `GET /jobs?workspace_id=<real workspace>` | **401** — `Invalid or expired access token.` | No job records were returned by the endpoint. |
| `GET /candidates?workspace_id=<real workspace>` | **401** — `Invalid or expired access token.` | No candidate records were returned by the endpoint. |
| `GET /evaluations?workspace_id=<real workspace>` | **401** — `Invalid or expired access token.` | No evaluation records were returned by the endpoint. |
| `GET /shortlists?workspace_id=<real workspace>` | **401** — `Invalid or expired access token.` | No shortlist records were returned by the endpoint. |
| `POST /matching/run` using a real workspace/job pair, without auth | **401** — `Invalid or expired access token.` | No match was run. An authorized request would create/update job-candidate associations, match results, and an audit record, so executing it successfully would violate the instruction not to modify existing database data. |
| React `GET /` and `GET /dashboard` | **200** — Vite serves the frontend HTML shell. | The protected dashboard's data loading was not verified; it requires successful authentication and workspace selection. |
| Streamlit `GET /` | **200** — Streamlit HTML shell. |
| Streamlit `GET /_stcore/health` | **200** — `ok`. | App server started and served its unauthenticated entry point. The dashboard renders its login screen before workspace navigation; authenticated dashboard pages/tabs and real-record loading could not be exercised. The temporary Streamlit process was stopped after this check. |

**Live verification conclusion:** the API, React shell, and Streamlit server are reachable. The requested authenticated workspace/data workflows remain **unverified**, not successful, because credentials were unavailable. The matching write operation was not executed successfully to preserve the existing database.

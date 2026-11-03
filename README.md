# AI-Powered Recruitment Sourcing and Candidate–Job Matching System

A recruitment workflow prototype with a React + TypeScript frontend, a FastAPI backend, and PostgreSQL persistence. Its current candidate ranking baseline uses TF-IDF and cosine similarity. Human review supports evaluation labels and reviewer feedback; matching results are decision-support information, not hiring decisions.

## Current implementation status

### Implemented

- React + TypeScript + Vite frontend and FastAPI backend.
- PostgreSQL persistence through SQLAlchemy, with Alembic migrations.
- JWT authentication, refresh-session rotation, logout, and current-user lookup.
- Workspace membership checks on workspace-scoped API operations. Both `ADMIN` and `RECRUITER` members are accepted; the current API does not provide separate operation permissions for those roles.
- Workspace-scoped job and candidate retrieval, matching runs and results, evaluation records, and shortlists.
- Reviewer-owned evaluation labels and notes, with audit/concurrency handling.
- TF-IDF/cosine candidate ranking, plus separately reported skill, experience, and location signals. An experimental combined score is also calculated and persisted by the API, but the ranking order remains based on TF-IDF and the combined score is not a validated hiring model.
- CSV validation and transactional import tooling, including dry-run reports and legacy-ID mapping.
- Human-reviewed ranking metrics in the standalone evaluation workflow.

### Incomplete

- There are no general job or candidate create/edit API endpoints.
- The application has no workspace or membership administration API. A user must already belong to a workspace to use workspace-scoped features. The admin bootstrap command creates a user, not a workspace.
- The Boolean Search interface builds a query in the frontend; it does not persist searches or connect to sourcing providers.
- There are no active source connectors or background sourcing jobs.

### Inactive, experimental, or future work

- Semantic matching is not active. The optional semantic dependency group is not part of the current ranking workflow.
- The API's combined score is experimental; it is not a validated hiring model or the candidate ranking signal.
- The `modeling.py` classification example is separate from the recruitment matching flow; it is not used to rank candidates.
- Login rate limiting is in-memory and per process, so it is not shared across multiple backend workers.

## Architecture and API

- **Frontend:** `frontend/` — React, TypeScript, Vite.
- **Backend:** `src/ml_project/api/` — FastAPI application and routers.
- **Persistence:** `src/ml_project/models.py` and `migrations/` — SQLAlchemy models and Alembic migration history.
- **Matching baseline:** `src/ml_project/matching.py` — TF-IDF/cosine ranking for the standalone workflow; API matching is implemented in the API matching router.
- **CSV tooling:** `src/ml_project/csv_migration.py` and `src/ml_project/dataset_validation.py`.

The API includes:

| Area | Available operations |
|---|---|
| Authentication | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Workspaces | `GET /workspaces` lists workspaces available to the signed-in user |
| Jobs and candidates | `GET /jobs`, `GET /candidates`, and `GET /candidates/{candidate_id}` |
| Matching | `POST /matching/run`, `GET /matching`, and `GET /matching/score-distribution` |
| Evaluations | `GET /evaluations` and `PUT /evaluations` for reviewer labels and notes |
| Shortlists | `GET /shortlists`, `POST /shortlists`, and `DELETE /shortlists/{shortlist_id}` |
| Health | `GET /health` |

Workspace-scoped endpoints require an authenticated active user and workspace membership. The backend checks membership for the requested workspace; workspace access is not inferred from a client-supplied workspace ID alone. The API does not currently expose general workspace/member management or job/candidate CRUD.

Authentication uses short-lived HS256 access JWTs (15 minutes by default) and refresh sessions stored as hashes in the database. Refresh tokens are sent in an HttpOnly cookie and rotated when refreshed; logout revokes the refresh session. Login rate limiting is configurable but currently process-local.

## Local development

### Requirements

- Python version allowed by `pyproject.toml`.
- Node.js and npm.
- A local PostgreSQL instance configured to listen on port **1234**.

### Configure PostgreSQL and Python

Create a development database and user in PostgreSQL, then make sure the server is listening on port `1234`. Set `DATABASE_URL` in the local environment (do not commit credentials):

```text
postgresql+psycopg://recruitment_app:<url-encoded-password>@localhost:1234/recruitment_db
```

From the project root, activate the existing virtual environment and install the project requirements:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use the environment's Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you do not already have a local `.env`, create one from the example. Do not overwrite an existing local settings file:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

In particular, set `DATABASE_URL` and a `JWT_SECRET_KEY` of at least 32 bytes. Do not copy real credentials into source control.

Apply database migrations:

```powershell
alembic upgrade head
```

The admin bootstrap command creates a user only. Workspace-scoped API functionality also requires an existing workspace membership; the application does not currently provide workspace/member administration endpoints.

### Start backend and frontend separately

The repository includes a combined `npm run dev` launcher, but its reliability on Windows has not been verified. It may be tried as a convenience; if it fails, use the following separate-terminal workflow.

```powershell
npm run dev
```

In the first PowerShell terminal, from the project root, start the API on port `8000`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn ml_project.api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, install frontend dependencies and start Vite on port `5173`:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open the frontend at `http://127.0.0.1:5173`. The API is at `http://127.0.0.1:8000`; its OpenAPI documentation is available at `/docs`.

## CSV data and migration

The bundled sample files are `data/jobs.csv` and `data/candidates.csv`; they contain fictional examples. Replace or extend them only with data you are authorized to use, and do not commit personal or confidential candidate information.

Validate the sample datasets:

```powershell
.\.venv\Scripts\python.exe -m ml_project.dataset_validation
```

The validator checks required columns, missing values, and unique job/candidate IDs. The CSV migration tool supports validation/dry-run and transactional execution. Dry-run does not write to the database:

```powershell
.\.venv\Scripts\python.exe -m ml_project.csv_migration --help
```

Execution requires explicitly selected workspace and reviewer information when preserving review data. Review the dry-run report and migration options before using `--execute`; do not run it against production data without an approved backup and import plan.

## Matching and evaluation

The standalone baseline ranks candidates using TF-IDF vectors and cosine similarity. The API also calculates skill, experience, and location evidence and persists an experimental combined score, but those additional fields do not replace the TF-IDF ordering. None of these scores is a calibrated probability or hiring recommendation.

The evaluator uses human-reviewed labels: `0` not relevant, `1` partially relevant, and `2` relevant. Jobs with incomplete labels remain unevaluated. Run the standalone ranking and evaluation commands from the project root:

```powershell
.\.venv\Scripts\python.exe -m ml_project.matching --job-id J002
.\.venv\Scripts\python.exe -m ml_project.evaluation
```

The evaluator reports Precision@5, Recall@10, and NDCG@5 for fully labeled jobs and writes `reports/baseline_evaluation.csv`.

## Tests and checks

Run backend tests and lint:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

Run frontend tests, TypeScript validation, and a production build:

```powershell
npm --prefix frontend test
npm --prefix frontend run build
```

The production build runs `tsc -b` before Vite builds the frontend.

Use authorized, de-identified data and independently reviewed labels when measuring ranking quality. Do not treat a score or shortlist as an automated hiring decision.

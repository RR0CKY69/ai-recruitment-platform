# Apex Recruit frontend API contracts

This document distinguishes implemented backend routes from proposed Stage 2 routes. The frontend uses the existing Axios client, so authentication and refresh handling remain centralized. Every record request is scoped to the currently selected workspace; the backend must independently authorize that workspace.

## Confirmed backend routes used

| Method | Route | Frontend use |
|---|---|---|
| `GET` | `/jobs?workspace_id={id}` | Workspace job listing and details |
| `GET` | `/candidates?workspace_id={id}` | Workspace candidate profiles |
| `GET` | `/candidates/{candidate_id}?workspace_id={id}` | Candidate profile and current associated jobs |
| `GET` | `/matching?workspace_id={id}&job_id={id}` | Existing stored matching results |
| `GET` | `/jobs/{job_id}/candidates?workspace_id={id}` | Pipeline: candidates explicitly assigned to a job |
| `POST` | `/jobs/{job_id}/candidates` | Assign a candidate to a job |
| `DELETE` | `/jobs/{job_id}/candidates/{candidate_id}?workspace_id={id}` | Remove a job-candidate association |
| `PATCH` | `/jobs/{job_id}/candidates/{candidate_id}?workspace_id={id}` | Pipeline: update a candidate's recruitment stage |
| `POST` | `/jobs` | Create a workspace-scoped job |
| `PUT` | `/jobs/{job_id}?workspace_id={id}` | Update a workspace-scoped job |
| `POST` | `/candidates` | Create a workspace-scoped candidate profile |
| `PUT` | `/candidates/{candidate_id}?workspace_id={id}` | Update a workspace-scoped candidate profile |
| `POST` | `/candidates/resume` | Upload and parse a resume PDF/DOCX |

The current job response includes `id`, `title`, `description`, `required_skills`, `minimum_experience_years`, `location`, `employment_type`, `status`, and `candidate_count`. `candidate_count` counts current job-candidate associations.

Candidate list/detail responses include name, current title, summary, skills, sources, experience, location, email, and (on detail) associated jobs.

## Implemented job-candidate assignment routes

### `GET /jobs/{job_id}/candidates?workspace_id={id}`

Return an array of assigned candidate cards, each containing `candidate_id`, `full_name`, `email` (if available), `current_title`, `experience_years`, `location`, `summary`, `skills`, `sources`, and `stage`. Return only candidates explicitly associated with that job in that workspace.

### `POST /jobs/{job_id}/candidates`

JSON body:

```json
{
  "workspace_id": "workspace UUID",
  "candidate_id": "candidate UUID"
}
```

Return the assignment/card shape above. Validate both records belong to the requested workspace and return HTTP `409` for duplicate associations.

### `DELETE /jobs/{job_id}/candidates/{candidate_id}?workspace_id={id}`

Remove only the association; return HTTP `204` on success. Return HTTP `409` if the association has existing historical recruitment data (MatchResult, Shortlist, EvaluationLabel, or EvaluationNote records) — in that case the assignment cannot be removed without deleting history. Do not delete the candidate profile.

### `PATCH /jobs/{job_id}/candidates/{candidate_id}?workspace_id={id}`

JSON body:

```json
{
  "stage": "SOURCED | REVIEWING | SHORTLISTED | REJECTED | HIRED"
}
```

Returns the updated `JobCandidateAssignmentResponse` (the assignment/card shape with the new `stage`). The frontend updates the candidate's stage optimistically, invalidates the job-candidates query cache, rolls back on error, and never creates Shortlist records as a side effect of a stage change.

## Implemented job CRUD routes

### `POST /jobs`

JSON body:

```json
{
  "workspace_id": "workspace UUID",
  "title": "Platform Engineer",
  "description": "Role description",
  "required_skills": ["Python", "PostgreSQL"],
  "employment_type": "Full-time",
  "location": "Remote",
  "minimum_experience_years": 4,
  "status": "OPEN"
}
```

Query parameter: `workspace_id` is included in the JSON request body. Returns `JobResponse` with HTTP `201 Created`. Creates required-skill `JobRequirement` entries from `required_skills`.

### `PUT /jobs/{job_id}`

Query parameter: `workspace_id`. JSON body accepts the same fields as `POST /jobs`. Returns the job response shape used by `GET /jobs`. Supported statuses: `DRAFT`, `OPEN`, `ON_HOLD`, and `CLOSED`. Replaces all required-skill requirements on update.

## Implemented candidate CRUD routes

### `POST /candidates`

JSON body:

```json
{
  "workspace_id": "workspace UUID",
  "full_name": "Candidate Name",
  "email": "candidate@example.test",
  "current_title": "Platform Engineer",
  "summary": "Professional summary",
  "experience_years": 6,
  "location": "Remote",
  "skills": ["Python", "PostgreSQL"],
  "sources": [
    {
      "provider": "candidate_provided",
      "source_record_id": null,
      "source_url": null,
      "authorized_basis": "Candidate provided profile"
    }
  ]
}
```

Query parameter: `workspace_id` is included in the JSON request body. Returns `CandidateProfileResponse` with HTTP `201 Created`. Enforces workspace-scoped duplicate email validation (HTTP `409`).

### `PUT /candidates/{candidate_id}`

Query parameter: `workspace_id`. Accepts the same profile fields. Returns the saved profile with HTTP `200 OK`. Enforces workspace-scoped duplicate email validation (HTTP `409`).

## Implemented job-candidate assignment routes

These routes are implemented by the current backend and consumed by the Pipeline page. A workspace candidate profile is reusable; an assignment adds only the job-candidate association.

### `GET /jobs/{job_id}/candidates?workspace_id={id}`

Return an array of assigned candidate cards, each containing `candidate_id`, `full_name`, `email` (if available), `current_title`, `experience_years`, `location`, `summary`, `skills`, `sources`, and `stage`. Return only candidates explicitly associated with that job in that workspace.

### `POST /jobs/{job_id}/candidates`

JSON body:

```json
{
  "workspace_id": "workspace UUID",
  "candidate_id": "candidate UUID"
}
```

Return the assignment/card shape above. Validate both records belong to the requested workspace and return HTTP `409` for duplicate associations.

### `DELETE /jobs/{job_id}/candidates/{candidate_id}?workspace_id={id}`

Remove only the association; return HTTP `204` on success. Return HTTP `409` if the association has existing historical recruitment data (MatchResult, Shortlist, EvaluationLabel, or EvaluationNote records) — in that case the assignment cannot be removed without deleting history. Do not delete the candidate profile.

## Implemented resume upload route

### `POST /candidates/resume`

Multipart form fields: `workspace_id` (form field) and `file` (file upload). Accept PDF/DOCX up to 10 MiB. The endpoint validates file extension, MIME type, and file signature. It does not silently save a candidate; it returns a reviewable draft:

```json
{
  "parsed_candidate": {
    "full_name": "Candidate Name",
    "email": "candidate@example.test",
    "current_title": "Platform Engineer",
    "summary": "Professional summary",
    "experience_years": 6,
    "location": "Remote",
    "skills": ["Python"],
    "sources": []
  }
}
```

`parsed_candidate` may be `null` when parsing yields no reviewable profile. The recruiter must be able to edit and explicitly save a complete draft through `POST /candidates`; the frontend does not fabricate parsed information.

## Matching behavior

`POST /matching/run` processes only candidates with an existing `job_candidates` association for the requested job and workspace. Unassigned workspace candidates do not block a run, and candidates assigned to other jobs are excluded. Running matching never creates or modifies job-candidate associations; it only upserts `MatchResult` records against existing associations.

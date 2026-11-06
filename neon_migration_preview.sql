BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0073db67417d

CREATE TABLE users (
    id UUID NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    full_name VARCHAR(200) NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE UNIQUE INDEX uq_users_email_ci ON users (lower(email)) WHERE email IS NOT NULL;

CREATE TABLE workspaces (
    id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    slug VARCHAR(120) NOT NULL, 
    created_by_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_workspaces PRIMARY KEY (id), 
    CONSTRAINT fk_workspaces_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT uq_workspaces_slug UNIQUE (slug)
);

CREATE TABLE audit_logs (
    id UUID NOT NULL, 
    workspace_id UUID NOT NULL, 
    actor_id UUID, 
    action VARCHAR(150) NOT NULL, 
    entity_type VARCHAR(100) NOT NULL, 
    entity_id UUID, 
    details JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id), 
    CONSTRAINT fk_audit_logs_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_audit_logs_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
);

CREATE INDEX ix_audit_logs_workspace_created ON audit_logs (workspace_id, created_at);

CREATE INDEX ix_audit_logs_workspace_id ON audit_logs (workspace_id);

CREATE TABLE candidates (
    id UUID NOT NULL, 
    workspace_id UUID NOT NULL, 
    created_by_id UUID, 
    legacy_candidate_id VARCHAR(100), 
    full_name VARCHAR(200) NOT NULL, 
    email VARCHAR(320), 
    current_title VARCHAR(250), 
    summary TEXT NOT NULL, 
    experience_years INTEGER, 
    location VARCHAR(250), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_candidates PRIMARY KEY (id), 
    CONSTRAINT fk_candidates_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_candidates_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    CONSTRAINT uq_candidates_workspace_email UNIQUE (workspace_id, email), 
    CONSTRAINT uq_candidates_workspace_id_id UNIQUE (workspace_id, id)
);

CREATE UNIQUE INDEX uq_candidates_workspace_email_ci ON candidates (workspace_id, lower(email)) WHERE email IS NOT NULL;

CREATE INDEX ix_candidates_workspace_id ON candidates (workspace_id);

CREATE INDEX ix_candidates_workspace_name ON candidates (workspace_id, full_name);

CREATE TABLE jobs (
    id UUID NOT NULL, 
    workspace_id UUID NOT NULL, 
    created_by_id UUID, 
    legacy_job_id VARCHAR(100), 
    title VARCHAR(250) NOT NULL, 
    description TEXT NOT NULL, 
    employment_type VARCHAR(100), 
    location VARCHAR(250), 
    minimum_experience_years INTEGER, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_jobs PRIMARY KEY (id), 
    CONSTRAINT ck_jobs_status_valid CHECK (status IN ('DRAFT', 'OPEN', 'ON_HOLD', 'CLOSED')), 
    CONSTRAINT fk_jobs_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_jobs_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    CONSTRAINT uq_jobs_workspace_id_id UNIQUE (workspace_id, id)
);

CREATE INDEX ix_jobs_workspace_id ON jobs (workspace_id);

CREATE TABLE workspace_members (
    id UUID NOT NULL, 
    workspace_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_workspace_members PRIMARY KEY (id), 
    CONSTRAINT ck_workspace_members_role_valid CHECK (role IN ('ADMIN', 'RECRUITER')), 
    CONSTRAINT fk_workspace_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT fk_workspace_members_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    CONSTRAINT uq_workspace_members_workspace_user UNIQUE (workspace_id, user_id)
);

CREATE INDEX ix_workspace_members_user_id ON workspace_members (user_id);

CREATE INDEX ix_workspace_members_workspace_id ON workspace_members (workspace_id);

CREATE TABLE candidate_skills (
    id UUID NOT NULL, 
    candidate_id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    normalized_name VARCHAR(200) NOT NULL, 
    years_experience INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_candidate_skills PRIMARY KEY (id), 
    CONSTRAINT fk_candidate_skills_candidate_id_candidates FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE, 
    CONSTRAINT uq_candidate_skills_candidate_name UNIQUE (candidate_id, normalized_name)
);

CREATE INDEX ix_candidate_skills_candidate_id ON candidate_skills (candidate_id);

CREATE TABLE candidate_sources (
    id UUID NOT NULL, 
    candidate_id UUID NOT NULL, 
    provider VARCHAR(150) NOT NULL, 
    source_record_id VARCHAR(300), 
    source_url TEXT, 
    authorized_basis VARCHAR(300), 
    source_metadata JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_candidate_sources PRIMARY KEY (id), 
    CONSTRAINT fk_candidate_sources_candidate_id_candidates FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE, 
    CONSTRAINT uq_candidate_sources_record UNIQUE (candidate_id, provider, source_record_id)
);

CREATE INDEX ix_candidate_sources_candidate_id ON candidate_sources (candidate_id);

CREATE TABLE job_candidates (
    id UUID NOT NULL, 
    workspace_id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    candidate_id UUID NOT NULL, 
    created_by_id UUID, 
    stage VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_job_candidates PRIMARY KEY (id), 
    CONSTRAINT ck_job_candidates_stage_valid CHECK (stage IN ('SOURCED', 'REVIEWING', 'SHORTLISTED', 'REJECTED', 'HIRED')), 
    CONSTRAINT fk_job_candidates_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_job_candidates_workspace_candidate FOREIGN KEY(workspace_id, candidate_id) REFERENCES candidates (workspace_id, id) ON DELETE CASCADE, 
    CONSTRAINT fk_job_candidates_workspace_job FOREIGN KEY(workspace_id, job_id) REFERENCES jobs (workspace_id, id) ON DELETE CASCADE, 
    CONSTRAINT fk_job_candidates_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    CONSTRAINT uq_job_candidates_job_candidate UNIQUE (job_id, candidate_id)
);

CREATE INDEX ix_job_candidates_candidate_id ON job_candidates (candidate_id);

CREATE INDEX ix_job_candidates_job_id ON job_candidates (job_id);

CREATE INDEX ix_job_candidates_workspace_id ON job_candidates (workspace_id);

CREATE TABLE job_requirements (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    requirement_type VARCHAR(30) NOT NULL, 
    description TEXT NOT NULL, 
    normalized_value VARCHAR(300), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_job_requirements PRIMARY KEY (id), 
    CONSTRAINT ck_job_requirements_type_valid CHECK (requirement_type IN ('REQUIRED_SKILL', 'PREFERRED_SKILL', 'QUALIFICATION', 'RESPONSIBILITY')), 
    CONSTRAINT fk_job_requirements_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
);

CREATE INDEX ix_job_requirements_job_id ON job_requirements (job_id);

CREATE TABLE search_queries (
    id UUID NOT NULL, 
    workspace_id UUID NOT NULL, 
    job_id UUID, 
    created_by_id UUID, 
    name VARCHAR(200) NOT NULL, 
    query_text TEXT NOT NULL, 
    query_type VARCHAR(40) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_search_queries PRIMARY KEY (id), 
    CONSTRAINT fk_search_queries_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_search_queries_workspace_job FOREIGN KEY(workspace_id, job_id) REFERENCES jobs (workspace_id, id) ON DELETE CASCADE, 
    CONSTRAINT fk_search_queries_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
);

CREATE INDEX ix_search_queries_job_id ON search_queries (job_id);

CREATE INDEX ix_search_queries_workspace_id ON search_queries (workspace_id);

CREATE TABLE sourcing_tasks (
    id UUID NOT NULL, 
    workspace_id UUID NOT NULL, 
    job_id UUID, 
    requested_by_id UUID, 
    source_provider VARCHAR(150) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    progress_percent INTEGER NOT NULL, 
    parameters JSON NOT NULL, 
    result_summary JSON NOT NULL, 
    error_message TEXT, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_sourcing_tasks PRIMARY KEY (id), 
    CONSTRAINT ck_sourcing_tasks_status_valid CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')), 
    CONSTRAINT ck_sourcing_tasks_progress_valid CHECK (progress_percent BETWEEN 0 AND 100), 
    CONSTRAINT fk_sourcing_tasks_requested_by_id_users FOREIGN KEY(requested_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_sourcing_tasks_workspace_job FOREIGN KEY(workspace_id, job_id) REFERENCES jobs (workspace_id, id) ON DELETE CASCADE, 
    CONSTRAINT fk_sourcing_tasks_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
);

CREATE INDEX ix_sourcing_tasks_job_id ON sourcing_tasks (job_id);

CREATE INDEX ix_sourcing_tasks_workspace_id ON sourcing_tasks (workspace_id);

CREATE TABLE evaluation_labels (
    id UUID NOT NULL, 
    job_candidate_id UUID NOT NULL, 
    reviewer_id UUID NOT NULL, 
    relevance_label INTEGER NOT NULL, 
    review_status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_evaluation_labels PRIMARY KEY (id), 
    CONSTRAINT ck_evaluation_labels_label_valid CHECK (relevance_label IN (0, 1, 2)), 
    CONSTRAINT fk_evaluation_labels_job_candidate_id_job_candidates FOREIGN KEY(job_candidate_id) REFERENCES job_candidates (id) ON DELETE CASCADE, 
    CONSTRAINT fk_evaluation_labels_reviewer_id_users FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_evaluation_labels_pair_reviewer UNIQUE (job_candidate_id, reviewer_id)
);

CREATE INDEX ix_evaluation_labels_job_candidate_id ON evaluation_labels (job_candidate_id);

CREATE INDEX ix_evaluation_labels_reviewer_id ON evaluation_labels (reviewer_id);

CREATE TABLE match_results (
    id UUID NOT NULL, 
    job_candidate_id UUID NOT NULL, 
    model_name VARCHAR(100) NOT NULL, 
    model_version VARCHAR(100) NOT NULL, 
    tfidf_similarity DOUBLE PRECISION, 
    skill_coverage DOUBLE PRECISION, 
    experience_compatibility VARCHAR(40), 
    location_compatibility VARCHAR(40), 
    semantic_similarity DOUBLE PRECISION, 
    hybrid_score DOUBLE PRECISION, 
    explanation JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_match_results PRIMARY KEY (id), 
    CONSTRAINT fk_match_results_job_candidate_id_job_candidates FOREIGN KEY(job_candidate_id) REFERENCES job_candidates (id) ON DELETE CASCADE, 
    CONSTRAINT uq_match_results_model_version UNIQUE (job_candidate_id, model_name, model_version)
);

CREATE INDEX ix_match_results_job_candidate_id ON match_results (job_candidate_id);

CREATE TABLE shortlists (
    id UUID NOT NULL, 
    job_candidate_id UUID NOT NULL, 
    added_by_id UUID, 
    status VARCHAR(20) NOT NULL, 
    notes TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_shortlists PRIMARY KEY (id), 
    CONSTRAINT ck_shortlists_status_valid CHECK (status IN ('ACTIVE', 'REMOVED', 'HIRED')), 
    CONSTRAINT fk_shortlists_added_by_id_users FOREIGN KEY(added_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_shortlists_job_candidate_id_job_candidates FOREIGN KEY(job_candidate_id) REFERENCES job_candidates (id) ON DELETE CASCADE, 
    CONSTRAINT uq_shortlists_job_candidate UNIQUE (job_candidate_id)
);

CREATE INDEX ix_shortlists_job_candidate_id ON shortlists (job_candidate_id);

CREATE TABLE evaluation_notes (
    id UUID NOT NULL, 
    evaluation_label_id UUID NOT NULL, 
    author_id UUID NOT NULL, 
    note TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_evaluation_notes PRIMARY KEY (id), 
    CONSTRAINT fk_evaluation_notes_author_id_users FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_evaluation_notes_evaluation_label_id_evaluation_labels FOREIGN KEY(evaluation_label_id) REFERENCES evaluation_labels (id) ON DELETE CASCADE
);

CREATE INDEX ix_evaluation_notes_author_id ON evaluation_notes (author_id);

CREATE INDEX ix_evaluation_notes_evaluation_label_id ON evaluation_notes (evaluation_label_id);

INSERT INTO alembic_version (version_num) VALUES ('0073db67417d') RETURNING alembic_version.version_num;

-- Running upgrade 0073db67417d -> 2b4d7f0a91c3

ALTER TABLE jobs ADD CONSTRAINT uq_jobs_workspace_legacy_job_id UNIQUE (workspace_id, legacy_job_id);

ALTER TABLE candidates ADD CONSTRAINT uq_candidates_workspace_legacy_candidate_id UNIQUE (workspace_id, legacy_candidate_id);

UPDATE alembic_version SET version_num='2b4d7f0a91c3' WHERE alembic_version.version_num = '0073db67417d';

-- Running upgrade 2b4d7f0a91c3 -> 3c5e7a1b2d4f

CREATE TABLE refresh_sessions (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(255) NOT NULL, 
    family_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_refresh_sessions_user_id ON refresh_sessions (user_id);

CREATE INDEX ix_refresh_sessions_family_id ON refresh_sessions (family_id);

CREATE INDEX ix_refresh_sessions_expires_at ON refresh_sessions (expires_at);

UPDATE alembic_version SET version_num='3c5e7a1b2d4f' WHERE alembic_version.version_num = '2b4d7f0a91c3';

-- Running upgrade 3c5e7a1b2d4f -> ebf570f17769

CREATE INDEX ix_refresh_sessions_token_hash ON refresh_sessions (token_hash);

UPDATE alembic_version SET version_num='ebf570f17769' WHERE alembic_version.version_num = '3c5e7a1b2d4f';

-- Running upgrade ebf570f17769 -> 75d22e4b57a5

DELETE FROM refresh_sessions
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY token_hash ORDER BY created_at) as rn
                FROM refresh_sessions
            ) t WHERE t.rn > 1
        );

DROP INDEX ix_refresh_sessions_token_hash;

CREATE UNIQUE INDEX uq_refresh_sessions_token_hash ON refresh_sessions (token_hash);

UPDATE alembic_version SET version_num='75d22e4b57a5' WHERE alembic_version.version_num = 'ebf570f17769';

COMMIT;


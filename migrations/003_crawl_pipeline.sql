-- Phase 4: production crawl pipeline tables (SQLite)

CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'full'
        CHECK (mode IN ('full', 'incremental')),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
    config_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crawl_branch_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    branch_id INTEGER,
    place_id TEXT NOT NULL DEFAULT '',
    branch_name TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'deleted')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    reviews_found INTEGER NOT NULL DEFAULT 0,
    reviews_new INTEGER NOT NULL DEFAULT 0,
    reviews_updated INTEGER NOT NULL DEFAULT 0,
    discovered_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY(run_id) REFERENCES crawl_runs(id),
    FOREIGN KEY(branch_id) REFERENCES branches(id)
);

CREATE TABLE IF NOT EXISTS crawl_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
);

CREATE TABLE IF NOT EXISTS crawl_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL UNIQUE,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
);

CREATE TABLE IF NOT EXISTS crawl_checkpoints (
    run_id INTEGER PRIMARY KEY,
    cursor_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_crawl_runs_status ON crawl_runs(status);
CREATE INDEX IF NOT EXISTS idx_crawl_branch_tasks_run_status ON crawl_branch_tasks(run_id, status);
CREATE INDEX IF NOT EXISTS idx_crawl_stats_run_metric ON crawl_stats(run_id, metric);

-- Soft-delete support for branches discovered as missing.
-- SQLite ignores ADD COLUMN if already present when applied carefully via app migration helper.
-- ALTER TABLE branches ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
-- ALTER TABLE branches ADD COLUMN last_seen_at TEXT;

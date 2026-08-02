-- Phase 2.1 AI foundation schema migration (SQLite)
-- Refines review_analyses to the approved extraction contract.
-- Safe to run after Phase 1 / early Phase 2 draft schema.

PRAGMA foreign_keys = OFF;

ALTER TABLE review_analyses RENAME TO review_analyses_legacy;

CREATE TABLE review_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL UNIQUE,
    sentiment TEXT NOT NULL DEFAULT 'Neutral'
        CHECK (sentiment IN ('Positive', 'Neutral', 'Negative')),
    complaint_categories TEXT NOT NULL DEFAULT '[]',
    positive_categories TEXT NOT NULL DEFAULT '[]',
    delivery_speed TEXT
        CHECK (
            delivery_speed IS NULL
            OR delivery_speed IN ('fast', 'normal', 'slow')
        ),
    customer_service TEXT
        CHECK (
            customer_service IS NULL
            OR customer_service IN ('good', 'average', 'bad')
        ),
    staff_behavior TEXT
        CHECK (
            staff_behavior IS NULL
            OR staff_behavior IN ('good', 'average', 'bad')
        ),
    package_damage INTEGER
        CHECK (package_damage IS NULL OR package_damage IN (0, 1)),
    pricing TEXT
        CHECK (
            pricing IS NULL
            OR pricing IN ('cheap', 'fair', 'expensive')
        ),
    tracking TEXT
        CHECK (
            tracking IS NULL
            OR tracking IN ('good', 'average', 'bad')
        ),
    professionalism TEXT
        CHECK (
            professionalism IS NULL
            OR professionalism IN ('good', 'average', 'bad')
        ),
    mentioned_employees TEXT NOT NULL DEFAULT '[]',
    mentioned_city TEXT,
    mentioned_branch TEXT,
    urgency TEXT NOT NULL DEFAULT 'low'
        CHECK (urgency IN ('low', 'medium', 'high')),
    evidence_spans TEXT NOT NULL DEFAULT '{}',
    confidence_overall REAL NOT NULL DEFAULT 0
        CHECK (confidence_overall >= 0.0 AND confidence_overall <= 1.0),
    confidence_by_field TEXT NOT NULL DEFAULT '{}',
    language TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'succeeded', 'failed', 'skipped')),
    error TEXT,
    provider TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '',
    input_hash TEXT NOT NULL DEFAULT '',
    raw_response TEXT NOT NULL DEFAULT '{}',
    analyzed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(review_id) REFERENCES reviews(id)
);

CREATE INDEX IF NOT EXISTS idx_review_analyses_status ON review_analyses(status);
CREATE INDEX IF NOT EXISTS idx_review_analyses_sentiment ON review_analyses(sentiment);
CREATE INDEX IF NOT EXISTS idx_review_analyses_input_hash ON review_analyses(input_hash);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);

DROP TABLE IF EXISTS review_analyses_legacy;

PRAGMA foreign_keys = ON;

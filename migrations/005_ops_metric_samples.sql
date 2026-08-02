-- Durable ops metric samples (also applied by Database._ensure_ops_metric_samples).
CREATE TABLE IF NOT EXISTS ops_metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    labels_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ops_metric_samples_name_time
    ON ops_metric_samples(name, recorded_at);

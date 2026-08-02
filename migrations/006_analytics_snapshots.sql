-- Phase 7: precomputed executive analytics snapshots
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    snapshot_kind TEXT NOT NULL,
    filter_hash TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE(entity_type, entity_id, snapshot_kind, filter_hash)
);
CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_entity
    ON analytics_snapshots(entity_type, entity_id, snapshot_kind);

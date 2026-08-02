-- Phase 6 production data collection schema extensions
-- Applied automatically via Database._ensure_phase6_collection_columns

-- branches metadata
-- phone, latitude, longitude, city, province, metadata_json, last_success_at

-- reviews enrichment
-- owner_response, owner_response_at, is_deleted, content_hash, last_seen_at

-- Note: SQLite ALTER is handled in Python for IF NOT EXISTS semantics.
SELECT 1;

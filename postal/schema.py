"""SQLite schema for the Postal Intelligence Platform (separate from review warehouse)."""

from __future__ import annotations

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pi_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    name_fa TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    founded_year INTEGER,
    headquarters TEXT NOT NULL DEFAULT '',
    ownership TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    description_fa TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pi_official_profiles (
    company_id INTEGER NOT NULL UNIQUE,
    profile_json TEXT NOT NULL DEFAULT '{}',
    services_json TEXT NOT NULL DEFAULT '[]',
    domestic_services_json TEXT NOT NULL DEFAULT '[]',
    international_json TEXT NOT NULL DEFAULT '{}',
    insurance_json TEXT NOT NULL DEFAULT '{}',
    cod_json TEXT NOT NULL DEFAULT '{}',
    tracking_json TEXT NOT NULL DEFAULT '{}',
    packaging_json TEXT NOT NULL DEFAULT '{}',
    working_hours_json TEXT NOT NULL DEFAULT '{}',
    support_json TEXT NOT NULL DEFAULT '{}',
    branch_count_official INTEGER NOT NULL DEFAULT 0,
    cities_covered_official INTEGER NOT NULL DEFAULT 0,
    provinces_covered_official INTEGER NOT NULL DEFAULT 0,
    pricing_json TEXT NOT NULL DEFAULT '{}',
    delivery_times_json TEXT NOT NULL DEFAULT '{}',
    weight_limits_json TEXT NOT NULL DEFAULT '{}',
    size_limits_json TEXT NOT NULL DEFAULT '{}',
    data_quality TEXT NOT NULL DEFAULT 'curated_v1',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(company_id) REFERENCES pi_companies(id)
);

CREATE TABLE IF NOT EXISTS pi_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    external_key TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    province TEXT NOT NULL DEFAULT '',
    latitude REAL,
    longitude REAL,
    phone TEXT NOT NULL DEFAULT '',
    maps_url TEXT NOT NULL DEFAULT '',
    place_id TEXT NOT NULL DEFAULT '',
    source_db TEXT NOT NULL DEFAULT '',
    source_branch_id INTEGER,
    google_rating REAL NOT NULL DEFAULT 0,
    google_review_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(company_id, name, address),
    FOREIGN KEY(company_id) REFERENCES pi_companies(id)
);

CREATE TABLE IF NOT EXISTS pi_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    rating REAL NOT NULL DEFAULT 0,
    text TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'google_maps',
    external_id TEXT NOT NULL DEFAULT '',
    sentiment TEXT NOT NULL DEFAULT 'Neutral',
    complaint_category TEXT NOT NULL DEFAULT 'other',
    emotion TEXT NOT NULL DEFAULT '',
    urgency TEXT NOT NULL DEFAULT 'Low',
    nlp_confidence INTEGER NOT NULL DEFAULT 0,
    collected_at TEXT NOT NULL DEFAULT '',
    UNIQUE(branch_id, external_id),
    FOREIGN KEY(branch_id) REFERENCES pi_branches(id),
    FOREIGN KEY(company_id) REFERENCES pi_companies(id)
);

CREATE INDEX IF NOT EXISTS idx_pi_reviews_company ON pi_reviews(company_id);
CREATE INDEX IF NOT EXISTS idx_pi_reviews_branch ON pi_reviews(branch_id);
CREATE INDEX IF NOT EXISTS idx_pi_branches_company ON pi_branches(company_id);
CREATE INDEX IF NOT EXISTS idx_pi_branches_geo ON pi_branches(province, city);

CREATE TABLE IF NOT EXISTS pi_company_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
    dimensions_json TEXT NOT NULL DEFAULT '{}',
    weights_json TEXT NOT NULL DEFAULT '{}',
    explanation_json TEXT NOT NULL DEFAULT '{}',
    algorithm_version TEXT NOT NULL DEFAULT 'postal_score_v1',
    calculated_at TEXT NOT NULL,
    FOREIGN KEY(company_id) REFERENCES pi_companies(id)
);

CREATE TABLE IF NOT EXISTS pi_branch_intelligence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL UNIQUE,
    company_id INTEGER NOT NULL,
    overall_rating REAL NOT NULL DEFAULT 0,
    review_count INTEGER NOT NULL DEFAULT 0,
    complaint_categories_json TEXT NOT NULL DEFAULT '{}',
    sentiment_json TEXT NOT NULL DEFAULT '{}',
    review_trend_json TEXT NOT NULL DEFAULT '[]',
    last_activity TEXT NOT NULL DEFAULT '',
    branch_score REAL NOT NULL DEFAULT 0,
    explanation_json TEXT NOT NULL DEFAULT '{}',
    algorithm_version TEXT NOT NULL DEFAULT 'postal_score_v1',
    calculated_at TEXT NOT NULL,
    FOREIGN KEY(branch_id) REFERENCES pi_branches(id),
    FOREIGN KEY(company_id) REFERENCES pi_companies(id)
);

CREATE TABLE IF NOT EXISTS pi_geo_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    geo_level TEXT NOT NULL CHECK (geo_level IN ('province', 'city')),
    geo_name TEXT NOT NULL,
    province TEXT NOT NULL DEFAULT '',
    company_id INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    review_count INTEGER NOT NULL DEFAULT 0,
    branch_count INTEGER NOT NULL DEFAULT 0,
    avg_rating REAL NOT NULL DEFAULT 0,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    calculated_at TEXT NOT NULL,
    UNIQUE(geo_level, geo_name, province, company_id),
    FOREIGN KEY(company_id) REFERENCES pi_companies(id)
);

CREATE TABLE IF NOT EXISTS pi_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comparison_kind TEXT NOT NULL DEFAULT 'all_companies',
    payload_json TEXT NOT NULL,
    calculated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pi_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

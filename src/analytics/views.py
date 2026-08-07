"""SQL convenience views over anl_* tables (instant analytical questions)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# SQLite / Postgres compatible view definitions.
# These read precomputed anl_* tables — no heavy recalculation at query time.

VIEW_SQL: list[tuple[str, str]] = [
    (
        "anl_v_best_horses_season",
        """
        CREATE VIEW anl_v_best_horses_season AS
        SELECT rank, entity_name AS horse, season_key, segment AS breed_or_segment,
               score AS performance_rating, wins, win_rate, place_rate, avg_finish,
               consistency_score, form_score, earnings_total, why_text, why_json, metrics_json
        FROM anl_rankings
        WHERE category IN ('best_season', 'best_career')
          AND entity_type = 'horse'
          AND scope = 'season'
          AND segment = '*'
        """,
    ),
    (
        "anl_v_most_successful_horses",
        """
        CREATE VIEW anl_v_most_successful_horses AS
        SELECT rank, entity_name AS horse, scope, season_key,
               wins, win_rate, place_rate, avg_finish, earnings_total,
               performance_rating, why_text, why_json
        FROM anl_rankings
        WHERE category = 'most_successful' AND entity_type = 'horse' AND segment = '*'
        """,
    ),
    (
        "anl_v_most_consistent_horses",
        """
        CREATE VIEW anl_v_most_consistent_horses AS
        SELECT rank, entity_name AS horse, scope, season_key,
               consistency_score, starts, avg_finish, win_rate, why_text, why_json
        FROM anl_rankings
        WHERE category = 'most_consistent' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_by_breed",
        """
        CREATE VIEW anl_v_best_by_breed AS
        SELECT rank, entity_name AS horse, segment AS breed, scope, season_key,
               performance_rating, wins, win_rate, place_rate, avg_finish,
               why_text, why_json, metrics_json
        FROM anl_rankings
        WHERE category = 'best_by_breed' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_turkmen",
        """
        CREATE VIEW anl_v_best_turkmen AS
        SELECT rank, entity_name AS horse, scope, season_key,
               performance_rating, wins, win_rate, place_rate, avg_finish,
               why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_breed'
          AND entity_type = 'horse'
          AND segment = 'ترکمن'
        """,
    ),
    (
        "anl_v_best_dokhoon",
        """
        CREATE VIEW anl_v_best_dokhoon AS
        SELECT rank, entity_name AS horse, scope, season_key,
               performance_rating, wins, win_rate, place_rate, avg_finish,
               why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_breed'
          AND entity_type = 'horse'
          AND segment = 'دوخون'
        """,
    ),
    (
        "anl_v_best_thoroughbred",
        """
        CREATE VIEW anl_v_best_thoroughbred AS
        SELECT rank, entity_name AS horse, scope, season_key,
               performance_rating, wins, win_rate, place_rate, avg_finish,
               why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_breed'
          AND entity_type = 'horse'
          AND segment = 'تروبرد'
        """,
    ),
    (
        "anl_v_best_trainers",
        """
        CREATE VIEW anl_v_best_trainers AS
        SELECT rank, entity_name AS trainer, scope, season_key,
               wins, starts, win_rate, place_rate, earnings_total, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_trainer' AND entity_type = 'trainer'
        """,
    ),
    (
        "anl_v_best_jockeys",
        """
        CREATE VIEW anl_v_best_jockeys AS
        SELECT rank, entity_name AS jockey, scope, season_key,
               wins, starts, win_rate, place_rate, earnings_total, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_jockey' AND entity_type = 'jockey'
        """,
    ),
    (
        "anl_v_best_owners",
        """
        CREATE VIEW anl_v_best_owners AS
        SELECT rank, entity_name AS owner, scope, season_key,
               wins, starts, win_rate, place_rate, earnings_total, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_owner' AND entity_type = 'owner'
        """,
    ),
    (
        "anl_v_best_sires",
        """
        CREATE VIEW anl_v_best_sires AS
        SELECT rank, entity_name AS sire, scope, season_key,
               wins, starts, win_rate, place_rate, earnings_total, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_sire' AND entity_type = 'sire'
        """,
    ),
    (
        "anl_v_improving_horses",
        """
        CREATE VIEW anl_v_improving_horses AS
        SELECT rank, entity_name AS horse, scope, season_key,
               score AS improvement_trend, form_score, performance_rating,
               why_text, why_json
        FROM anl_rankings
        WHERE category = 'improving' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_declining_horses",
        """
        CREATE VIEW anl_v_declining_horses AS
        SELECT rank, entity_name AS horse, scope, season_key,
               score AS decline_trend, form_score, performance_rating,
               why_text, why_json
        FROM anl_rankings
        WHERE category = 'declining' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_by_distance",
        """
        CREATE VIEW anl_v_best_by_distance AS
        SELECT rank, entity_name AS horse, segment AS distance_bucket, scope, season_key,
               performance_rating, wins, win_rate, avg_finish, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_distance' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_by_track_condition",
        """
        CREATE VIEW anl_v_best_by_track_condition AS
        SELECT rank, entity_name AS horse, segment AS track_condition, scope, season_key,
               performance_rating, wins, win_rate, avg_finish, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_track_condition' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_by_weather",
        """
        CREATE VIEW anl_v_best_by_weather AS
        SELECT rank, entity_name AS horse, segment AS weather_category, scope, season_key,
               performance_rating, wins, win_rate, avg_finish, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_weather' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_by_class",
        """
        CREATE VIEW anl_v_best_by_class AS
        SELECT rank, entity_name AS horse, segment AS race_class, scope, season_key,
               performance_rating, wins, win_rate, avg_finish, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_class' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_by_age",
        """
        CREATE VIEW anl_v_best_by_age AS
        SELECT rank, entity_name AS horse, segment AS age_band, scope, season_key,
               performance_rating, wins, win_rate, avg_finish, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_by_age' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_best_young_horses",
        """
        CREATE VIEW anl_v_best_young_horses AS
        SELECT rank, entity_name AS horse, scope, season_key,
               performance_rating, wins, win_rate, avg_finish, why_text, why_json
        FROM anl_rankings
        WHERE category = 'best_young' AND entity_type = 'horse'
        """,
    ),
    (
        "anl_v_horse_metrics_ml",
        """
        CREATE VIEW anl_v_horse_metrics_ml AS
        SELECT
            horse_id, horse_name, scope, season_key, breed,
            starts, wins, places, win_rate, place_rate, avg_finish,
            performance_rating, consistency_score,
            form_score_3, form_score_5, form_score_10,
            speed_index, earnings_index, earnings_total, difficulty_index,
            track_preference, track_preference_score,
            distance_preference, distance_preference_score,
            weather_preference, weather_preference_score,
            track_condition_preference, track_condition_preference_score,
            jockey_combination_score, trainer_combination_score,
            fatigue_score, improvement_trend, decline_trend,
            is_improving, is_declining,
            age_years, age_band, primary_class, sire_name,
            season_ranking, career_ranking, breed_ranking,
            explain_json, features_json
        FROM anl_horse_metrics
        """,
    ),
    (
        "anl_v_latest_completed_seasons",
        """
        CREATE VIEW anl_v_latest_completed_seasons AS
        SELECT season_key, racecourse_code, label, start_date, end_date,
               race_days, heats, is_completed, is_latest_completed
        FROM anl_seasons
        WHERE is_latest_completed = 1 OR is_latest_completed = true
        """,
    ),
]


def create_analytics_views(session: Session) -> list[str]:
    """Drop+create analytics views. Safe to re-run after each build."""
    created: list[str] = []
    bind = session.get_bind()
    dialect = bind.dialect.name if bind is not None else "sqlite"
    for name, ddl in VIEW_SQL:
        session.execute(text(f"DROP VIEW IF EXISTS {name}"))
        sql = ddl
        # Postgres boolean true; SQLite uses 1 — keep filter portable
        if dialect == "postgresql" and "is_latest_completed = 1" in sql:
            sql = sql.replace("is_latest_completed = 1 OR is_latest_completed = true", "is_latest_completed = true")
        session.execute(text(sql))
        created.append(name)
    session.flush()
    return created

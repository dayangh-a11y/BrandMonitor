"""SQL views for prediction-market NL queries + dashboards."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

VIEW_SQL: list[tuple[str, str]] = [
    (
        "anl_v_pred_top_surprises",
        """
        CREATE VIEW anl_v_pred_top_surprises AS
        SELECT entity_name AS horse, starts, surprise_frequency, unpredictability_score,
               underrated_score, overrated_score, prediction_gap, avg_prediction_rank,
               avg_actual_rank, metrics_json
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'horse'
        """,
    ),
    (
        "anl_v_pred_most_overrated",
        """
        CREATE VIEW anl_v_pred_most_overrated AS
        SELECT entity_name AS horse, starts, overrated_score, public_popularity_score,
               favorite_failure_frequency, prediction_gap, avg_prediction_rank, avg_actual_rank
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'horse'
        """,
    ),
    (
        "anl_v_pred_most_underrated",
        """
        CREATE VIEW anl_v_pred_most_underrated AS
        SELECT entity_name AS horse, starts, underrated_score, prediction_gap,
               upset_victory_frequency, avg_prediction_rank, avg_actual_rank
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'horse'
        """,
    ),
    (
        "anl_v_pred_most_predictable",
        """
        CREATE VIEW anl_v_pred_most_predictable AS
        SELECT entity_name AS horse, starts, unpredictability_score, surprise_frequency,
               public_trust_score, prediction_gap
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'horse'
        """,
    ),
    (
        "anl_v_pred_least_predictable",
        """
        CREATE VIEW anl_v_pred_least_predictable AS
        SELECT entity_name AS horse, starts, unpredictability_score, surprise_frequency,
               upset_victory_frequency, prediction_gap
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'horse'
        """,
    ),
    (
        "anl_v_pred_accuracy_timeline",
        """
        CREATE VIEW anl_v_pred_accuracy_timeline AS
        SELECT race_date, track_name, event_id, crowd_accuracy, prediction_accuracy,
               shock_score, surprise_index, upset_score, crowd_confidence,
               crowd_favorite_name, favorite_failed, total_prize_pool
        FROM anl_prediction_race_metrics
        """,
    ),
    (
        "anl_v_pred_crowd_intelligence",
        """
        CREATE VIEW anl_v_pred_crowd_intelligence AS
        SELECT race_date, track_name, crowd_favorite_name, crowd_confidence,
               crowd_win_probability, crowd_accuracy, crowd_bias, prediction_difficulty,
               participants, winning_prediction_pct, features_json, explain_json
        FROM anl_prediction_race_metrics
        """,
    ),
    (
        "anl_v_pred_race_shock",
        """
        CREATE VIEW anl_v_pred_race_shock AS
        SELECT event_id, race_date, track_name, shock_score, upset_score, surprise_index,
               favorite_failure_score, crowd_accuracy, crowd_favorite_name,
               prediction_difficulty, total_prize_pool, features_json
        FROM anl_prediction_race_metrics
        """,
    ),
    (
        "anl_v_pred_trainers_beat_market",
        """
        CREATE VIEW anl_v_pred_trainers_beat_market AS
        SELECT entity_name AS trainer, starts, prediction_gap, underrated_score,
               upset_victory_frequency, avg_prediction_rank, avg_actual_rank
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'trainer'
        """,
    ),
    (
        "anl_v_pred_underestimated_jockeys",
        """
        CREATE VIEW anl_v_pred_underestimated_jockeys AS
        SELECT entity_name AS jockey, starts, underrated_score, prediction_gap,
               avg_prediction_rank, avg_actual_rank, upset_victory_frequency
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'jockey'
        """,
    ),
    (
        "anl_v_pred_unpredictable_sires",
        """
        CREATE VIEW anl_v_pred_unpredictable_sires AS
        SELECT entity_name AS sire, starts, unpredictability_score, surprise_frequency,
               upset_victory_frequency, prediction_gap
        FROM anl_prediction_entity_metrics
        WHERE entity_type = 'sire'
        """,
    ),
    (
        "anl_v_pred_ml_features",
        """
        CREATE VIEW anl_v_pred_ml_features AS
        SELECT event_id, race_date, track_name,
               crowd_confidence, crowd_probability, prediction_gap, surprise_index,
               public_bias, favorite_rank, favorite_failed, upset_score,
               prediction_entropy, prediction_variance, features_json
        FROM anl_prediction_race_metrics
        """,
    ),
]


QUESTION_MAP: dict[str, tuple[str, str]] = {
    "most_surprising": (
        "anl_v_pred_top_surprises",
        "surprise_frequency DESC, unpredictability_score DESC",
    ),
    "biggest_upset": (
        "anl_v_pred_race_shock",
        "upset_score DESC, shock_score DESC",
    ),
    "most_overrated": (
        "anl_v_pred_most_overrated",
        "overrated_score DESC, favorite_failure_frequency DESC",
    ),
    "most_underrated": (
        "anl_v_pred_most_underrated",
        "underrated_score DESC, prediction_gap DESC",
    ),
    "outperform_public": (
        "anl_v_pred_most_underrated",
        "prediction_gap DESC, underrated_score DESC",
    ),
    "disappoint": (
        "anl_v_pred_most_overrated",
        "prediction_gap ASC, overrated_score DESC",
    ),
    "hardest_race": (
        "anl_v_pred_race_shock",
        "prediction_difficulty DESC, shock_score DESC",
    ),
    "easiest_race": (
        "anl_v_pred_accuracy_timeline",
        "prediction_difficulty ASC, crowd_accuracy DESC",
    ),
    "trainer_beats_market": (
        "anl_v_pred_trainers_beat_market",
        "prediction_gap DESC, underrated_score DESC",
    ),
    "jockey_underestimated": (
        "anl_v_pred_underestimated_jockeys",
        "underrated_score DESC, prediction_gap DESC",
    ),
    "sire_unpredictable": (
        "anl_v_pred_unpredictable_sires",
        "unpredictability_score DESC, surprise_frequency DESC",
    ),
    "shock_rankings": (
        "anl_v_pred_race_shock",
        "shock_score DESC",
    ),
    "crowd_intelligence": (
        "anl_v_pred_crowd_intelligence",
        "race_date DESC",
    ),
    "accuracy_timeline": (
        "anl_v_pred_accuracy_timeline",
        "race_date ASC",
    ),
}


def create_prediction_views(session: Session) -> list[str]:
    created: list[str] = []
    for name, ddl in VIEW_SQL:
        session.execute(text(f"DROP VIEW IF EXISTS {name}"))
        session.execute(text(ddl))
        created.append(name)
    session.flush()
    return created

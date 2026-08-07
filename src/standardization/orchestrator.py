"""Orchestrator — run all standardization modules and produce a roadmap report."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.standardization.ai_layers import ai_readiness_report
from src.standardization.benchmarks import build_benchmarks
from src.standardization.constants import MODULES, PLATFORM_VERSION
from src.standardization.data_quality import run_warehouse_quality_checks
from src.standardization.entities import build_entity_registry
from src.standardization.feature_store import materialize_horse_features
from src.standardization.metrics_catalog import metric_catalog
from src.standardization.race_classification import build_race_classifications
from src.standardization.ranking_contracts import list_contracts
from src.standardization.seasons import sync_standardized_seasons
from src.standardization.validation import validate_rankings
from src.standardization.versions import seed_version_registry


@dataclass
class StandardizationReport:
    platform_version: str = PLATFORM_VERSION
    modules: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_version": self.platform_version,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "modules": self.modules,
        }

    def to_text(self) -> str:
        lines = [
            "=== Standardization Roadmap Report ===",
            f"Platform version: {self.platform_version}",
            f"Status:           {self.status}",
            f"Duration:         {self.duration_seconds:.3f}s",
            "",
        ]
        for key, meta in MODULES.items():
            mod = self.modules.get(key) or {}
            st = mod.get("status", "skipped")
            lines.append(f"[{meta['id']}] {meta['name']} v{meta['version']}: {st}")
            detail = mod.get("summary")
            if isinstance(detail, str) and detail:
                lines.append(f"    {detail}")
            elif isinstance(detail, dict):
                brief = ", ".join(f"{k}={v}" for k, v in list(detail.items())[:6])
                if brief:
                    lines.append(f"    {brief}")
        return "\n".join(lines)


def run_standardization(
    session: Session,
    *,
    racecourse_code: str | None = None,
    skip_benchmarks: bool = False,
    skip_features: bool = False,
    force_features: bool = False,
) -> StandardizationReport:
    started = time.perf_counter()
    report = StandardizationReport()

    def _ok(key: str, summary: Any) -> None:
        report.modules[key] = {"status": "ok", "summary": summary}

    def _err(key: str, exc: Exception) -> None:
        report.modules[key] = {"status": "error", "summary": str(exc)}
        report.status = "error"
        logger.exception("Module {} failed: {}", key, exc)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass

    # M01 Data Quality
    try:
        dq = run_warehouse_quality_checks(session)
        session.commit()
        _ok("data_quality", {"status": dq.get("status"), "issues": dq.get("issues_total")})
        if dq.get("status") == "error" and report.status == "ok":
            report.status = "warning"
    except Exception as exc:  # noqa: BLE001
        _err("data_quality", exc)

    # M02 Entity Resolution
    try:
        ent = build_entity_registry(session)
        session.commit()
        _ok("entity_resolution", ent)
    except Exception as exc:  # noqa: BLE001
        _err("entity_resolution", exc)

    # M03 Season Engine
    try:
        seasons = sync_standardized_seasons(session, racecourse_code=racecourse_code)
        session.commit()
        _ok("season_engine", {"seasons": len(seasons)})
    except Exception as exc:  # noqa: BLE001
        _err("season_engine", exc)

    # M04 Race Classification
    try:
        rc = build_race_classifications(session, racecourse_code=racecourse_code)
        session.commit()
        _ok("race_classification", rc)
    except Exception as exc:  # noqa: BLE001
        _err("race_classification", exc)

    # M05 Performance Metrics (catalog — always available)
    try:
        cats = metric_catalog()
        _ok("performance_metrics", {"metrics_documented": len(cats)})
    except Exception as exc:  # noqa: BLE001
        _err("performance_metrics", exc)

    # M06 Ranking Engine contracts
    try:
        contracts = list_contracts()
        _ok("ranking_engine", {"contracts": len(contracts)})
    except Exception as exc:  # noqa: BLE001
        _err("ranking_engine", exc)

    # M07 Explainability — capability registered
    _ok(
        "explainability",
        {"schema": ["rule", "formula", "metrics", "rows_analyzed", "confidence", "missing_data", "warnings"]},
    )

    # M08 Confidence Engine
    _ok(
        "confidence_engine",
        {"bands": ["very_high", "high", "medium", "low", "very_low"]},
    )

    # M09 Question Engine
    from src.standardization.questions import list_question_rules

    try:
        rules = list_question_rules()
        _ok("question_engine", {"rules": len(rules)})
    except Exception as exc:  # noqa: BLE001
        _err("question_engine", exc)

    # M10 Validation Engine
    try:
        val = validate_rankings(session)
        _ok(
            "validation_engine",
            {
                "status": val.get("status"),
                "warnings": val.get("warnings_total"),
                "rows_analyzed": val.get("rows_analyzed"),
            },
        )
        if val.get("status") == "error" and report.status == "ok":
            report.status = "warning"
    except Exception as exc:  # noqa: BLE001
        _err("validation_engine", exc)

    # M11 Benchmark Engine
    if not skip_benchmarks:
        try:
            bm = build_benchmarks(session, scope="season")
            bm_c = build_benchmarks(session, scope="career", season_key="*")
            session.commit()
            _ok(
                "benchmark_engine",
                {"season_written": bm.get("written"), "career_written": bm_c.get("written")},
            )
        except Exception as exc:  # noqa: BLE001
            _err("benchmark_engine", exc)
    else:
        report.modules["benchmark_engine"] = {"status": "skipped", "summary": {}}

    # M12 Version Control
    try:
        vers = seed_version_registry(session)
        session.commit()
        _ok("version_control", vers)
    except Exception as exc:  # noqa: BLE001
        _err("version_control", exc)

    # M13 Audit Log — table ready; sample write
    try:
        from src.standardization.audit import write_audit

        write_audit(
            session,
            question="standardization.run",
            rule_id="STD_ORCHESTRATOR",
            rows_analyzed=0,
            execution_time_ms=0,
            result_summary="standardization pass",
            payload={"racecourse_code": racecourse_code},
        )
        session.commit()
        _ok("audit_log", {"writable": True})
    except Exception as exc:  # noqa: BLE001
        _err("audit_log", exc)

    # M14 Feature Store
    if not skip_features:
        try:
            fs = materialize_horse_features(session, force=force_features)
            session.commit()
            _ok("feature_store", fs)
        except Exception as exc:  # noqa: BLE001
            _err("feature_store", exc)
    else:
        report.modules["feature_store"] = {"status": "skipped", "summary": {}}

    # M15 AI Readiness
    try:
        ai = ai_readiness_report(session)
        _ok("ai_readiness", {"ready": ai.get("ready"), "counts": ai.get("counts")})
    except Exception as exc:  # noqa: BLE001
        _err("ai_readiness", exc)

    report.duration_seconds = round(time.perf_counter() - started, 4)
    logger.info("Standardization complete status={}", report.status)
    return report

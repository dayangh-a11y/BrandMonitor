"""Typer CLI — collector + warehouse / quality / crawler platform."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from src.collectors import RaceCollector
from src.datasources import list_datasources
from src.utils.logging import setup_logging
from src.utils.settings import get_settings

app = typer.Typer(
    name="horse-racing-collector",
    help="Horse racing data platform (collector + warehouse + quality).",
    add_completion=False,
    no_args_is_help=True,
)

features_app = typer.Typer(help="Feature recalculation (never writes Raw).")
warehouse_app = typer.Typer(help="Normalized warehouse ETL + entity resolution.")
crawler_app = typer.Typer(help="Crawl queue manager.")
weather_app = typer.Typer(help="Historical weather backfill + race attach.")
analytics_app = typer.Typer(help="Analytics layer — rankings & standardized metrics.")
prediction_app = typer.Typer(help="Prediction market (mosharekat) collect + analytics.")
std_app = typer.Typer(help="Standardization roadmap (DQ → AI readiness, modules 1–15).")
markets_app = typer.Typer(help="Market-specific analytics (Win/Place/H2H/Value/…).")
prerace_app = typer.Typer(help="Pre-race decision engine — race-card intelligence reports.")
identity_app = typer.Typer(help="Horse Identity Resolution — permanent horse_id.")
app.add_typer(features_app, name="features")
app.add_typer(warehouse_app, name="warehouse")
app.add_typer(crawler_app, name="crawler")
app.add_typer(weather_app, name="weather")
app.add_typer(analytics_app, name="analytics")
app.add_typer(prediction_app, name="prediction")
app.add_typer(std_app, name="std")
app.add_typer(markets_app, name="markets")
app.add_typer(prerace_app, name="prerace")
app.add_typer(identity_app, name="identity")


@app.command("collect")
def collect(
    url: str = typer.Option(..., "--url", help="Race URL to collect"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default: output/)",
    ),
    datasource: Optional[str] = typer.Option(
        None,
        "--datasource",
        "-d",
        help="Datasource name (default from settings / asbdavani)",
    ),
    skip_history: bool = typer.Option(
        False,
        "--skip-history",
        help="Only write Race.json; do not visit horse profile pages",
    ),
    persist: bool = typer.Option(
        False,
        "--persist",
        help="Append into Raw tables (never overwrites prior versions; never writes Features)",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Log level (DEBUG, INFO, WARNING, ERROR)",
    ),
) -> None:
    """Collect a race and optional horse histories into JSON (+ optional Raw DB)."""
    settings = get_settings()
    setup_logging(settings.log_dir, log_level or settings.log_level)

    available = list_datasources()
    logger.info("Available datasources: {}", ", ".join(available))

    collector = RaceCollector(
        datasource_name=datasource,
        settings=settings,
        output_dir=output,
        collect_histories=not skip_history,
        persist_to_db=persist,
    )
    try:
        paths = collector.collect(url)
        for name, path in paths.items():
            typer.echo(f"Wrote {name} -> {path.resolve()}")
        if persist:
            typer.echo("Appended Raw versions (Features unchanged).")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Collection failed: {}", exc)
        raise typer.Exit(code=1) from exc
    finally:
        collector.close()


@app.command("datasources")
def datasources_cmd() -> None:
    """List registered datasources."""
    setup_logging(get_settings().log_dir, get_settings().log_level)
    for name in list_datasources():
        typer.echo(name)


@app.command("init-db")
def init_db_cmd() -> None:
    """Create Raw + Warehouse + Features + Quality + Crawler tables."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db

    init_db(settings)
    typer.echo("Platform tables created (raw_/wh_/feat_/anl_/quality_/crawl_/std_).")


@app.command("quality-report")
def quality_report_cmd() -> None:
    """Run data-quality checks and print a platform health report."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.quality import format_quality_report, run_quality_checks
    from src.standardization.data_quality import run_warehouse_quality_checks
    from src.warehouse import run_entity_resolution

    try:
        with session_scope(settings) as session:
            run_entity_resolution(session)
            summary = run_quality_checks(session)
            wh_summary = run_warehouse_quality_checks(session)
        typer.echo(format_quality_report(summary))
        typer.echo("")
        typer.echo(wh_summary.get("report_text") or "")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Quality report failed: {}", exc)
        raise typer.Exit(code=1) from exc


@warehouse_app.command("build")
def warehouse_build() -> None:
    """Build normalized warehouse tables from current Raw versions."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.warehouse import build_warehouse, run_entity_resolution

    with session_scope(settings) as session:
        stats = build_warehouse(session)
        matches = run_entity_resolution(session)
    typer.echo(f"Warehouse: {stats}")
    typer.echo(f"Entity matches: {matches}")


@features_app.command("list")
def features_list() -> None:
    """List legacy feature pipelines (optional) + empty feature shells."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.pipelines import list_pipelines

    typer.echo("Empty feature tables: HorseFeatures, RaceFeatures, TrainerFeatures, JockeyFeatures")
    typer.echo("Legacy pipelines:")
    for name in list_pipelines():
        typer.echo(f"  - {name}")


@features_app.command("build")
def features_build(
    pipeline: Optional[str] = typer.Option(
        None,
        "--pipeline",
        "-p",
        help="Legacy pipeline name (default: all). Prefer `features recalc` for empty shells.",
    ),
) -> None:
    """Run legacy feature pipelines (Raw → feat_* stats tables)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.pipelines.runner import build_features

    names = [pipeline] if pipeline else None
    try:
        with session_scope(settings) as session:
            runs = build_features(session, pipeline_names=names)
        for run in runs:
            typer.echo(
                f"{run.pipeline_name}@{run.pipeline_version} "
                f"status={run.status} rows={run.rows_upserted}"
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Feature build failed: {}", exc)
        raise typer.Exit(code=1) from exc


@features_app.command("recalc")
def features_recalc() -> None:
    """Recreate empty Horse/Race/Trainer/Jockey feature shells (no statistics)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.features import recalculate_all_features

    with session_scope(settings) as session:
        run = recalculate_all_features(session)
    typer.echo(f"Feature recalc status={run.status} rows={run.rows_touched}")


@crawler_app.command("enqueue")
def crawler_enqueue(
    url: str = typer.Option(..., "--url"),
    job_type: str = typer.Option(
        "race", "--type", help="race_list|week|race|refresh_race"
    ),
    force: bool = typer.Option(False, "--force", help="Re-queue even if previously successful"),
) -> None:
    """Add a URL to the crawl queue (duplicate-safe)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import CrawlerManager
    from src.database import session_scope

    with session_scope(settings) as session:
        job = CrawlerManager(session, max_attempts=settings.crawl_max_attempts).enqueue(
            job_type=job_type, url=url, force=force
        )
        typer.echo(f"job id={job.id} status={job.status} key={job.dedupe_key}")


@crawler_app.command("discover")
def crawler_discover() -> None:
    """Seed discovery of all race weeks from the racecards index."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import seed_discovery
    from src.database import session_scope

    with session_scope(settings) as session:
        info = seed_discovery(session, settings=settings)
    typer.echo(f"Seeded discovery job: {info}")


@crawler_app.command("run")
def crawler_run(
    workers: Optional[int] = typer.Option(
        None, "--workers", "-w", help="Parallel workers (default from settings)"
    ),
    no_seed: bool = typer.Option(
        False, "--no-seed", help="Do not auto-enqueue race_list discovery"
    ),
    max_runtime: Optional[float] = typer.Option(
        None, "--max-runtime", help="Optional max runtime in seconds"
    ),
) -> None:
    """Run the production mass crawler until the queue is drained."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import run_mass_crawl

    summary = run_mass_crawl(
        settings=settings,
        workers=workers,
        seed=not no_seed,
        max_runtime_seconds=max_runtime,
    )
    typer.echo(summary)


@crawler_app.command("refresh")
def crawler_refresh() -> None:
    """Re-queue successful races to detect updates (unchanged pages are skipped)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import refresh_successful_races
    from src.database import session_scope

    with session_scope(settings) as session:
        count = refresh_successful_races(session, settings=settings)
    typer.echo(f"Re-queued {count} race jobs for update detection")


@crawler_app.command("progress")
def crawler_progress() -> None:
    """Show crawl queue progress by status."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import CrawlerManager
    from src.database import session_scope

    with session_scope(settings) as session:
        progress = CrawlerManager(session).progress()
    for status, count in sorted(progress.items()):
        typer.echo(f"{status}: {count}")


@crawler_app.command("resume")
def crawler_resume() -> None:
    """Re-queue failed crawl jobs."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import CrawlerManager
    from src.database import session_scope

    with session_scope(settings) as session:
        count = CrawlerManager(session).resume_failed()
    typer.echo(f"Resumed {count} failed jobs")


@crawler_app.command("dashboard")
def crawler_dashboard() -> None:
    """Print crawler dashboard metrics."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import collect_dashboard_metrics, format_dashboard
    from src.database import session_scope

    with session_scope(settings) as session:
        metrics = collect_dashboard_metrics(session)
    typer.echo(format_dashboard(metrics))


@crawler_app.command("daily-report")
def crawler_daily_report() -> None:
    """Generate and persist today's crawl report."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import generate_daily_report
    from src.database import session_scope

    with session_scope(settings) as session:
        _, text = generate_daily_report(session, settings=settings)
    typer.echo(text)


@weather_app.command("backfill")
def weather_backfill(
    date_from: Optional[str] = typer.Option(
        None, "--from", help="Inclusive start date YYYY-MM-DD (default: all race dates)"
    ),
    date_to: Optional[str] = typer.Option(
        None, "--to", help="Inclusive end date YYYY-MM-DD"
    ),
    courses: Optional[str] = typer.Option(
        None,
        "--courses",
        help="Comma-separated racecourse codes (default: all races in warehouse)",
    ),
) -> None:
    """Fetch Open-Meteo archive weather into raw_weather_observations (append-only)."""
    from datetime import date as date_cls

    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.weather import backfill_race_weather

    codes = {c.strip() for c in courses.split(",")} if courses else None
    d0 = date_cls.fromisoformat(date_from) if date_from else None
    d1 = date_cls.fromisoformat(date_to) if date_to else None
    with session_scope(settings) as session:
        stats = backfill_race_weather(
            session,
            settings=settings,
            racecourse_codes=codes,
            date_from=d0,
            date_to=d1,
        )
    typer.echo(stats)


@weather_app.command("attach")
def weather_attach() -> None:
    """Upsert wh_race_weather snapshots from current raw weather observations."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.weather import attach_weather_to_warehouse

    with session_scope(settings) as session:
        stats = attach_weather_to_warehouse(session, settings=settings)
    typer.echo(stats)


@analytics_app.command("build")
def analytics_build(
    course: Optional[str] = typer.Option(
        None, "--course", help="Limit to racecourse code (e.g. gonbad-kavous)"
    ),
    top: int = typer.Option(25, "--top", help="Leaderboard depth"),
    min_starts: int = typer.Option(
        5,
        "--min-starts",
        help="Minimum starts to qualify for Season Best / success / win-rate / consistency boards",
    ),
) -> None:
    """Rebuild anl_* metrics, rankings, and SQL views from warehouse data."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.analytics import build_analytics
    from src.database import session_scope

    with session_scope(settings) as session:
        stats = build_analytics(
            session,
            racecourse_code=course,
            top_n=top,
            minimum_starts=min_starts,
        )
    typer.echo(stats)


@analytics_app.command("query")
def analytics_query(
    question: str = typer.Option(
        "best_season",
        "--question",
        "-q",
        help=(
            "best_season|most_successful|highest_earnings|highest_win_rate|best_form|"
            "most_consistent|best_turkmen|best_dokhoon|best_thoroughbred|best_trainer|"
            "best_jockey|best_owner|best_sire|improving|declining|best_by_distance|"
            "best_by_weather|best_by_track_condition|best_by_class|best_young|"
            "season_best_status|best_mare|best_stallion|best_mixed_race_performer|"
            "best_female_against_males|most_dominant_male"
        ),
    ),
    limit: int = typer.Option(10, "--limit", "-n"),
    scope: str = typer.Option(
        "season",
        "--scope",
        help="season|career|all — filter leaderboard scope when the view has it",
    ),
) -> None:
    """Print a precomputed leaderboard (with qualification + confidence)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from sqlalchemy import text

    from src.database import session_scope

    view_map = {
        "best_season": "anl_v_best_horses_season",
        "season_best_status": "anl_v_season_best_status",
        "most_successful": "anl_v_most_successful_horses",
        "highest_earnings": "anl_v_highest_earnings_horses",
        "highest_win_rate": "anl_v_highest_win_rate_horses",
        "best_form": "anl_v_best_form_horses",
        "most_consistent": "anl_v_most_consistent_horses",
        "best_turkmen": "anl_v_best_turkmen",
        "best_dokhoon": "anl_v_best_dokhoon",
        "best_thoroughbred": "anl_v_best_thoroughbred",
        "best_trainer": "anl_v_best_trainers",
        "best_jockey": "anl_v_best_jockeys",
        "best_owner": "anl_v_best_owners",
        "best_sire": "anl_v_best_sires",
        "improving": "anl_v_improving_horses",
        "declining": "anl_v_declining_horses",
        "best_by_distance": "anl_v_best_by_distance",
        "best_by_weather": "anl_v_best_by_weather",
        "best_by_track_condition": "anl_v_best_by_track_condition",
        "best_by_class": "anl_v_best_by_class",
        "best_young": "anl_v_best_young_horses",
        "best_mare": "anl_v_best_mare",
        "best_stallion": "anl_v_best_stallion",
        "best_mixed_race_performer": "anl_v_best_mixed_race_performer",
        "best_female_against_males": "anl_v_best_female_against_males",
        "most_dominant_male": "anl_v_most_dominant_male",
    }
    view = view_map.get(question)
    if not view:
        typer.echo(f"Unknown question. Choose from: {', '.join(sorted(view_map))}")
        raise typer.Exit(code=2)

    with session_scope(settings) as session:
        # Always surface Season Best gate first when asking best_season
        if question == "best_season":
            status_rows = session.execute(
                text("SELECT why_text, why_json FROM anl_v_season_best_status")
            ).mappings().all()
            for srow in status_rows:
                typer.echo(srow.get("why_text") or "INSUFFICIENT DATA")
                typer.echo("---")

        sql = f"SELECT * FROM {view}"
        params: dict = {"n": limit}
        if (
            scope in {"season", "career"}
            and question not in {"best_season", "season_best_status"}
        ):
            sql += " WHERE scope = :scope"
            params["scope"] = scope
        if question != "season_best_status":
            sql += " ORDER BY rank LIMIT :n"
        rows = session.execute(text(sql), params).mappings().all()

    if not rows:
        if question == "best_season":
            typer.echo(
                "INSUFFICIENT DATA — no qualified Season Best rows "
                "(check season_best_status / raise sample size or lower --min-starts)."
            )
            raise typer.Exit(code=1)
        typer.echo("No rows — run `python main.py analytics build` first.")
        raise typer.Exit(code=1)

    for row in rows:
        if question == "season_best_status":
            typer.echo(row.get("why_text") or row.get("status") or "INSUFFICIENT DATA")
            continue
        why_json = row.get("why_json") or {}
        if isinstance(why_json, str):
            import json

            try:
                why_json = json.loads(why_json)
            except Exception:  # noqa: BLE001
                why_json = {}
        name = (
            row.get("horse")
            or row.get("trainer")
            or row.get("jockey")
            or row.get("owner")
            or row.get("sire")
            or row.get("status")
        )
        starts = why_json.get("starts", row.get("starts"))
        conf = why_json.get("confidence")
        conf_score = why_json.get("confidence_score")
        qstatus = why_json.get("qualification_status")
        rq = why_json.get("reason_for_qualification")
        rexc = why_json.get("reason_for_exclusion")
        typer.echo(
            f"#{row.get('rank')} {name} | starts={starts} | "
            f"confidence={conf}({conf_score}) | status={qstatus}"
        )
        if rq:
            typer.echo(f"  qualified: {rq}")
        if rexc:
            typer.echo(f"  excluded: {rexc}")
        typer.echo(f"  {row.get('why_text') or ''}")


@analytics_app.command("race-intel")
def analytics_race_intel(
    race_id: Optional[int] = typer.Option(
        None, "--race-id", help="Warehouse race id; omit with --rebuild to rebuild all"
    ),
    course: Optional[str] = typer.Option(
        None, "--course", help="Limit rebuild to racecourse code"
    ),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Rebuild anl_race_intelligence before printing"
    ),
    shockiest: bool = typer.Option(
        False, "--shockiest", help="Print top shock races instead of a single card"
    ),
    limit: int = typer.Option(10, "--limit", "-n"),
) -> None:
    """Print a Race Intelligence card (Difficulty / Crowd / Surprise / Shock)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from sqlalchemy import select, text

    from src.analytics.models import AnlRaceIntelligence
    from src.analytics.race_intel_build import (
        build_race_intelligence,
        get_race_intelligence_report,
    )
    from src.database import session_scope

    with session_scope(settings) as session:
        if rebuild:
            stats = build_race_intelligence(
                session,
                racecourse_code=course,
                race_ids=[race_id] if race_id is not None else None,
            )
            typer.echo(f"rebuild={stats}")

        if shockiest:
            sql = """
                SELECT race_id, race_date, racecourse_code, race_name, breed,
                       shock_score, crowd_accuracy_pct, biggest_surprise_horse,
                       most_overrated_horse, most_underrated_horse, report_text
                FROM anl_v_high_shock_races
            """
            params: dict = {"n": limit}
            if course:
                sql += " WHERE racecourse_code = :course"
                params["course"] = course
            sql += " ORDER BY shock_score DESC LIMIT :n"
            rows = session.execute(text(sql), params).mappings().all()
            if not rows:
                # Fallback if view missing or no high-shock threshold hits
                q = select(AnlRaceIntelligence).order_by(
                    AnlRaceIntelligence.shock_score.desc()
                )
                if course:
                    q = q.where(AnlRaceIntelligence.racecourse_code == course)
                rows = [
                    {
                        "race_id": r.race_id,
                        "race_date": r.race_date,
                        "racecourse_code": r.racecourse_code,
                        "shock_score": r.shock_score,
                        "crowd_accuracy_pct": r.crowd_accuracy_pct,
                        "biggest_surprise_horse": r.biggest_surprise_horse,
                        "report_text": r.report_text,
                    }
                    for r in session.scalars(q.limit(limit)).all()
                ]
            if not rows:
                typer.echo("No race intelligence rows — run with --rebuild first.")
                raise typer.Exit(code=1)
            for row in rows:
                typer.echo(
                    f"race={row.get('race_id')} {row.get('race_date')} "
                    f"shock={row.get('shock_score')} "
                    f"crowd={row.get('crowd_accuracy_pct')}% "
                    f"surprise={row.get('biggest_surprise_horse')}"
                )
                if row.get("report_text"):
                    typer.echo(row["report_text"])
                    typer.echo("---")
            return

        if race_id is None:
            typer.echo("Provide --race-id or use --shockiest / --rebuild.")
            raise typer.Exit(code=2)

        report = get_race_intelligence_report(session, race_id)
        if not report:
            # Compute on the fly if not persisted
            from src.analytics.race_intel import compute_race_intelligence
            from src.analytics.metrics import parse_race_class
            from src.warehouse.models import WhHorse, WhRace, WhRaceResult

            race = session.get(WhRace, race_id)
            if race is None:
                typer.echo(f"Race {race_id} not found.")
                raise typer.Exit(code=1)
            horses = {h.id: h.name for h in session.scalars(select(WhHorse)).all()}
            runners = []
            for res in session.scalars(
                select(WhRaceResult).where(WhRaceResult.race_id == race_id)
            ).all():
                if res.finish_position is None or res.finish_position <= 0 or res.horse_id is None:
                    continue
                runners.append(
                    {
                        "horse_id": res.horse_id,
                        "horse_name": horses.get(res.horse_id, f"horse#{res.horse_id}"),
                        "finish": int(res.finish_position),
                        "rating": float(res.source_rating)
                        if res.source_rating is not None
                        else None,
                        "cloth": res.number,
                    }
                )
            intel = compute_race_intelligence(
                race_id=race_id,
                runners=runners,
                race_class=parse_race_class(race.name),
            )
            if intel is None:
                typer.echo("Not enough finishers for race intelligence.")
                raise typer.Exit(code=1)
            typer.echo(intel.as_report())
            return
        typer.echo(report)


@prediction_app.command("discover")
def prediction_discover(
    day_sample: int = typer.Option(2, "--day-sample"),
    race_sample: int = typer.Option(2, "--race-sample"),
    output: Optional[Path] = typer.Option(
        Path("docs/prediction_market"), "--output", "-o"
    ),
) -> None:
    """Discover every public prediction-market field (no hardcoded names)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.prediction_market.discover import discover_prediction_fields

    report = discover_prediction_fields(
        day_sample=day_sample, race_sample=race_sample, output_dir=output
    )
    typer.echo(
        {
            "field_count": report["field_count"],
            "race_days_available": report["race_days_available"],
            "output": str(output),
        }
    )


@prediction_app.command("collect")
def prediction_collect(
    limit_days: Optional[int] = typer.Option(
        None, "--limit-days", help="Limit number of race days (default: all)"
    ),
    day_id: Optional[list[int]] = typer.Option(
        None, "--day-id", help="Specific day id(s); repeatable"
    ),
    skip_odds: bool = typer.Option(False, "--skip-odds"),
    skip_survey: bool = typer.Option(False, "--skip-survey"),
    skip_warehouse: bool = typer.Option(False, "--skip-warehouse"),
) -> None:
    """Collect historical mosharekat prediction snapshots into Raw (+ warehouse)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.prediction_market.collect import collect_prediction_history

    init_db(settings)
    with session_scope(settings) as session:
        stats = collect_prediction_history(
            session,
            limit_days=limit_days,
            day_ids=list(day_id) if day_id else None,
            include_odds=not skip_odds,
            include_survey=not skip_survey,
            build_warehouse=not skip_warehouse,
        )
    typer.echo(stats)


@prediction_app.command("build")
def prediction_build() -> None:
    """Rebuild warehouse (from Raw) + prediction analytics tables/views."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.prediction_market.build import build_prediction_analytics
    from src.prediction_market.warehouse import build_prediction_warehouse

    init_db(settings)
    with session_scope(settings) as session:
        wh = build_prediction_warehouse(session)
        anl = build_prediction_analytics(session)
    typer.echo({"warehouse": wh, "analytics": anl})


@prediction_app.command("query")
def prediction_query(
    question: str = typer.Option(
        "most_surprising",
        "--question",
        "-q",
        help=(
            "most_surprising|biggest_upset|most_overrated|most_underrated|"
            "outperform_public|disappoint|hardest_race|easiest_race|"
            "trainer_beats_market|jockey_underestimated|sire_unpredictable|"
            "shock_rankings|crowd_intelligence|accuracy_timeline"
        ),
    ),
    limit: int = typer.Option(10, "--limit", "-n"),
) -> None:
    """Answer natural-language style prediction-market questions via SQL views."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from sqlalchemy import text

    from src.database import session_scope
    from src.prediction_market.views import QUESTION_MAP

    mapped = QUESTION_MAP.get(question)
    if not mapped:
        typer.echo(f"Unknown question. Choose from: {', '.join(sorted(QUESTION_MAP))}")
        raise typer.Exit(code=2)
    view, order = mapped
    sql = f"SELECT * FROM {view} ORDER BY {order} LIMIT :n"
    with session_scope(settings) as session:
        rows = session.execute(text(sql), {"n": limit}).mappings().all()
    if not rows:
        typer.echo("No rows — run `python main.py prediction collect` then `build`.")
        raise typer.Exit(code=1)
    for i, row in enumerate(rows, 1):
        label = (
            row.get("horse")
            or row.get("trainer")
            or row.get("jockey")
            or row.get("sire")
            or row.get("crowd_favorite_name")
            or row.get("track_name")
            or row.get("event_id")
        )
        extras = []
        for key in (
            "surprise_frequency",
            "overrated_score",
            "underrated_score",
            "shock_score",
            "upset_score",
            "prediction_gap",
            "crowd_accuracy",
            "unpredictability_score",
            "prediction_difficulty",
        ):
            if key in row and row[key] is not None:
                extras.append(f"{key}={row[key]}")
        typer.echo(f"#{i} {label} — " + ", ".join(extras))


@std_app.command("build")
def std_build(
    course: Optional[str] = typer.Option(
        None, "--course", help="Limit season/race classification to racecourse code"
    ),
    skip_benchmarks: bool = typer.Option(False, "--skip-benchmarks"),
    skip_features: bool = typer.Option(False, "--skip-features"),
    force_features: bool = typer.Option(
        False, "--force-features", help="Rewrite feature store even if version matches"
    ),
) -> None:
    """Run Modules 1–15: DQ, entities, seasons, classification, versions, features, …"""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.standardization import run_standardization

    init_db(settings)
    with session_scope(settings) as session:
        report = run_standardization(
            session,
            racecourse_code=course,
            skip_benchmarks=skip_benchmarks,
            skip_features=skip_features,
            force_features=force_features,
        )
    typer.echo(report.to_text())


@std_app.command("report")
def std_report() -> None:
    """Print module catalog + current version ledger."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.standardization.constants import MODULES, PLATFORM_VERSION
    from src.standardization.metrics_catalog import metric_catalog
    from src.standardization.ranking_contracts import list_contracts
    from src.standardization.versions import current_versions

    typer.echo(f"Platform {PLATFORM_VERSION}")
    for key, meta in MODULES.items():
        typer.echo(f"  [{meta['id']}] {meta['name']} v{meta['version']}")
    typer.echo(f"Metrics documented: {len(metric_catalog())}")
    typer.echo(f"Ranking contracts:  {len(list_contracts())}")
    with session_scope(settings) as session:
        try:
            vers = current_versions(session)
        except Exception:  # noqa: BLE001
            vers = []
    typer.echo(f"Version registry current artifacts: {len(vers)}")
    for v in vers[:30]:
        typer.echo(f"  {v['artifact_type']}/{v['artifact_name']}@{v['version']}")


@std_app.command("ask")
def std_ask(
    question: str = typer.Option(..., "--question", "-q", help="Natural language or slug"),
    limit: int = typer.Option(10, "--limit", "-n"),
) -> None:
    """Question Engine: question → rule → SQL → metrics → explanation (never direct)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.standardization.questions import answer_question

    with session_scope(settings) as session:
        result = answer_question(session, question, limit=limit)
    typer.echo(result.get("explanation_text") or "")
    typer.echo(f"rule={result.get('rule_id')} status={result.get('status')}")
    if result.get("sql"):
        typer.echo(f"sql={result['sql']}")
    expl = result.get("explanation") or {}
    conf = expl.get("confidence") or {}
    typer.echo(
        f"confidence={conf.get('confidence_label') or conf.get('confidence')} "
        f"rows={expl.get('rows_analyzed')}"
    )
    if expl.get("warnings"):
        typer.echo("warnings: " + "; ".join(expl["warnings"]))
    if expl.get("missing_data"):
        typer.echo("missing: " + ", ".join(expl["missing_data"]))
    for i, row in enumerate(result.get("rows") or [], 1):
        name = (
            row.get("horse")
            or row.get("trainer")
            or row.get("jockey")
            or row.get("owner")
            or row.get("status")
            or row.get("why_text")
        )
        typer.echo(f"  #{i} {name}")


@std_app.command("validate")
def std_validate(
    scope: str = typer.Option("season", "--scope"),
) -> None:
    """Validation Engine — suspicious ranking warnings."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.standardization.validation import validate_rankings

    with session_scope(settings) as session:
        result = validate_rankings(session, scope=scope)
    typer.echo(
        f"status={result['status']} warnings={result['warnings_total']} "
        f"rows={result['rows_analyzed']}"
    )
    for code, n in (result.get("warnings_by_code") or {}).items():
        typer.echo(f"  {code}: {n}")
    for w in (result.get("warnings") or [])[:20]:
        typer.echo(f"  [{w['severity']}] {w['code']}: {w['message']}")


@std_app.command("dq")
def std_dq() -> None:
    """Module 1 — warehouse Data Quality Report only."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.standardization.data_quality import run_warehouse_quality_checks

    init_db(settings)
    with session_scope(settings) as session:
        summary = run_warehouse_quality_checks(session)
    typer.echo(summary.get("report_text") or "")


@std_app.command("metrics")
def std_metrics() -> None:
    """Module 5 — print mathematical metric catalog."""
    from src.standardization.metrics_catalog import metric_catalog

    for m in metric_catalog():
        typer.echo(f"{m['name']} ({m['symbol']}): {m['formula']}")
        typer.echo(f"  domain={m['domain']} — {m['notes']}")


@std_app.command("contracts")
def std_contracts() -> None:
    """Module 6 — print ranking contracts."""
    from src.standardization.ranking_contracts import list_contracts

    for c in list_contracts():
        typer.echo(f"{c['board']} v{c['version']}: {c['title']}")
        typer.echo(f"  eligibility: {c['eligibility']}")
        typer.echo(f"  formula:     {c['ranking_formula']}")
        typer.echo(f"  tie_break:   {c['tie_break']}")
        typer.echo(
            f"  min_starts={c['minimum_starts']} min_confidence={c['minimum_confidence']}"
        )


@markets_app.command("analyze")
def markets_analyze(
    race_id: int = typer.Option(..., "--race-id", help="Warehouse race id"),
    market: Optional[str] = typer.Option(
        None,
        "--market",
        "-m",
        help="win|place|h2h|without_favorite|value|risk|surprise (omit = all)",
    ),
    no_h2h: bool = typer.Option(False, "--no-h2h", help="Skip pairwise matrix"),
) -> None:
    """Run market-specific models for one race (never one ranking for all markets)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.markets.answer import format_market_answer
    from src.markets.build import analyze_race_markets, analyze_single_market

    init_db(settings)
    with session_scope(settings) as session:
        if market:
            ans = analyze_single_market(session, race_id, market)
            typer.echo(format_market_answer(ans))
            return
        answers = analyze_race_markets(
            session, race_id, persist=True, include_h2h=not no_h2h
        )
    for key, ans in answers.items():
        typer.echo(format_market_answer(ans))
        typer.echo("---")


@markets_app.command("build")
def markets_build(
    course: Optional[str] = typer.Option(None, "--course"),
    limit: int = typer.Option(30, "--limit", "-n"),
    no_h2h: bool = typer.Option(False, "--no-h2h"),
) -> None:
    """Persist market snapshots (+ optional pairwise matrices) for recent races."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.markets.build import build_markets_for_course

    init_db(settings)
    with session_scope(settings) as session:
        stats = build_markets_for_course(
            session,
            racecourse_code=course,
            limit=limit,
            include_h2h=not no_h2h,
        )
    typer.echo(stats)


@markets_app.command("matchup")
def markets_matchup(
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help='Direct matchup e.g. "دنزی بوی یا لیدی سانگ" or "A vs B"',
    ),
) -> None:
    """Direct A vs B matchup — does NOT use season ranking."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.markets.answer import format_market_answer
    from src.markets.build import run_matchup_query

    init_db(settings)
    with session_scope(settings) as session:
        ans = run_matchup_query(session, query, persist=True)
    typer.echo(format_market_answer(ans))
    pred = ans.prediction or {}
    if isinstance(pred, dict) and pred.get("factors"):
        typer.echo("Factors:")
        for f in pred["factors"]:
            edge = f.get("edge_for_a")
            typer.echo(
                f"  {f['factor']}: A={f.get('a')} B={f.get('b')} "
                f"edge_A={edge} — {f.get('note')}"
            )


@markets_app.command("list")
def markets_list() -> None:
    """List supported betting markets and score models."""
    from src.markets.constants import MARKET_TYPES

    for key, meta in MARKET_TYPES.items():
        typer.echo(f"{meta['id']}: {meta['title']} — model={meta['score_model']}")
        typer.echo(f"  {meta['description']}")


@prerace_app.command("report")
def prerace_report_cmd(
    race_id: int = typer.Option(..., "--race-id", help="Warehouse race id (race card)"),
    no_h2h: bool = typer.Option(False, "--no-h2h", help="Skip pairwise H2H matrix"),
) -> None:
    """Complete pre-race intelligence report for one race (never unexplained)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.prerace import build_prerace_report

    init_db(settings)
    with session_scope(settings) as session:
        payload = build_prerace_report(
            session, race_id, persist=True, include_h2h=not no_h2h
        )
    typer.echo(payload.get("report_text") or "")
    if not payload.get("publishable"):
        raise typer.Exit(code=2)


@prerace_app.command("card")
def prerace_card_cmd(
    date: Optional[str] = typer.Option(
        None, "--date", help="Race card date YYYY-MM-DD (default: latest day)"
    ),
    course: Optional[str] = typer.Option(None, "--course", help="Racecourse code"),
    limit: int = typer.Option(12, "--limit", "-n"),
) -> None:
    """Build pre-race reports for an entire race-card day."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.prerace.engine import build_prerace_for_card_day

    init_db(settings)
    with session_scope(settings) as session:
        stats = build_prerace_for_card_day(
            session, race_date=date, racecourse_code=course, limit=limit
        )
    typer.echo(f"race_date={stats.get('race_date')} races={stats.get('races')}")
    for rep in stats.get("reports") or []:
        race = rep.get("race") or {}
        win = (rep.get("reports") or {}).get("best_win_candidate") or {}
        typer.echo(
            f"  #{race.get('race_id')} {race.get('race_name')}: "
            f"best_win={win.get('horse')} conf={win.get('confidence')} "
            f"publishable={rep.get('publishable')}"
        )


@identity_app.command("build")
def identity_build_cmd() -> None:
    """Assign permanent horse_id to every warehouse horse (multi-signal merge)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.identity import build_horse_identity

    init_db(settings)
    with session_scope(settings) as session:
        stats = build_horse_identity(session)
    typer.echo(stats)


@identity_app.command("report")
def identity_report_cmd(
    limit: int = typer.Option(100, "--limit", "-n"),
    json_out: bool = typer.Option(False, "--json", help="Print JSON instead of text"),
) -> None:
    """Duplicate horses and possible merges report."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.identity import duplicate_merge_report, format_duplicate_report

    init_db(settings)
    with session_scope(settings) as session:
        report = duplicate_merge_report(session, limit=limit)
    if json_out:
        import json

        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_duplicate_report(report))


@identity_app.command("resolve")
def identity_resolve_cmd(
    name: Optional[str] = typer.Option(None, "--name"),
    sire: Optional[str] = typer.Option(None, "--sire"),
    dam: Optional[str] = typer.Option(None, "--dam"),
    age: Optional[int] = typer.Option(None, "--age"),
    sex: Optional[str] = typer.Option(None, "--sex"),
    owner: Optional[str] = typer.Option(None, "--owner"),
    trainer: Optional[str] = typer.Option(None, "--trainer"),
    source_horse_id: Optional[str] = typer.Option(None, "--source-id"),
    limit: int = typer.Option(5, "--limit", "-n"),
) -> None:
    """Resolve race-card attributes → permanent horse_id (never name-only joins)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db, session_scope
    from src.identity import HorseQuery, resolve_horse

    init_db(settings)
    with session_scope(settings) as session:
        hits = resolve_horse(
            session,
            HorseQuery(
                name=name,
                sire=sire,
                dam=dam,
                age=age,
                sex=sex,
                owner=owner,
                trainer=trainer,
                source_horse_id=source_horse_id,
            ),
            limit=limit,
        )
    if not hits:
        typer.echo("NO_MATCH")
        raise typer.Exit(code=2)
    for h in hits:
        typer.echo(
            f"horse_id={h.horse_id}  name={h.display_name!r}  "
            f"score={h.score:.3f}  decision={h.decision}  "
            f"warehouse_id={h.warehouse_horse_id}"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()

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
app.add_typer(features_app, name="features")
app.add_typer(warehouse_app, name="warehouse")
app.add_typer(crawler_app, name="crawler")
app.add_typer(weather_app, name="weather")
app.add_typer(analytics_app, name="analytics")


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
    typer.echo("Platform tables created (raw_/wh_/feat_/anl_/quality_/crawl_).")


@app.command("quality-report")
def quality_report_cmd() -> None:
    """Run data-quality checks and print a platform health report."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import session_scope
    from src.quality import format_quality_report, run_quality_checks
    from src.warehouse import run_entity_resolution

    try:
        with session_scope(settings) as session:
            run_entity_resolution(session)
            summary = run_quality_checks(session)
        typer.echo(format_quality_report(summary))
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
) -> None:
    """Rebuild anl_* metrics, rankings, and SQL views from warehouse data."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.analytics import build_analytics
    from src.database import session_scope

    with session_scope(settings) as session:
        stats = build_analytics(session, racecourse_code=course, top_n=top)
    typer.echo(stats)


@analytics_app.command("query")
def analytics_query(
    question: str = typer.Option(
        "best_season",
        "--question",
        "-q",
        help=(
            "best_season|most_successful|most_consistent|best_turkmen|"
            "best_dokhoon|best_thoroughbred|best_trainer|best_jockey|"
            "best_owner|best_sire|improving|declining|best_by_distance|"
            "best_by_weather|best_by_track_condition|best_by_class|best_young"
        ),
    ),
    limit: int = typer.Option(10, "--limit", "-n"),
    scope: str = typer.Option(
        "season",
        "--scope",
        help="season|career|all — filter leaderboard scope when the view has it",
    ),
) -> None:
    """Print a precomputed leaderboard (with why_text explanations)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from sqlalchemy import text

    from src.database import session_scope

    view_map = {
        "best_season": "anl_v_best_horses_season",
        "most_successful": "anl_v_most_successful_horses",
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
    }
    view = view_map.get(question)
    if not view:
        typer.echo(f"Unknown question. Choose from: {', '.join(sorted(view_map))}")
        raise typer.Exit(code=2)
    sql = f"SELECT * FROM {view}"
    params: dict = {"n": limit}
    if scope in {"season", "career"} and question != "best_season":
        sql += " WHERE scope = :scope"
        params["scope"] = scope
    sql += " ORDER BY rank LIMIT :n"
    with session_scope(settings) as session:
        rows = session.execute(text(sql), params).mappings().all()
    if not rows:
        typer.echo("No rows — run `python main.py analytics build` first.")
        raise typer.Exit(code=1)
    for row in rows:
        why = row.get("why_text") or ""
        name = (
            row.get("horse")
            or row.get("trainer")
            or row.get("jockey")
            or row.get("owner")
            or row.get("sire")
        )
        typer.echo(f"#{row.get('rank')} {name} — {why}")


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

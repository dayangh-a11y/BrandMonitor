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
app.add_typer(features_app, name="features")
app.add_typer(warehouse_app, name="warehouse")
app.add_typer(crawler_app, name="crawler")


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
    typer.echo("Platform tables created (raw_/wh_/feat_/quality_/crawl_).")


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
    job_type: str = typer.Option("race", "--type", help="race|horse|race_list"),
) -> None:
    """Add a URL to the crawl queue (duplicate-safe)."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.crawler import CrawlerManager
    from src.database import session_scope

    with session_scope(settings) as session:
        job = CrawlerManager(session).enqueue(job_type=job_type, url=url)
        typer.echo(f"job id={job.id} status={job.status} key={job.dedupe_key}")


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

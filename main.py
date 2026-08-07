"""Typer CLI entrypoint for the horse racing data collector / warehouse."""

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
    help="Horse racing data collector + Raw/Features warehouse (no ML predictions).",
    add_completion=False,
    no_args_is_help=True,
)

features_app = typer.Typer(help="Feature pipelines (compute Features from Raw only).")
app.add_typer(features_app, name="features")


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
        help="Also ingest into Raw warehouse tables (never writes Features)",
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
            typer.echo("Persisted Raw tables (Features unchanged; run `features build`).")
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
    """Create Raw + Features warehouse tables."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.database import init_db

    init_db(settings)
    typer.echo("Warehouse tables created (raw_* + feat_*).")


@features_app.command("list")
def features_list() -> None:
    """List registered feature pipelines."""
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    from src.pipelines import list_pipelines

    for name in list_pipelines():
        typer.echo(name)


@features_app.command("build")
def features_build(
    pipeline: Optional[str] = typer.Option(
        None,
        "--pipeline",
        "-p",
        help="Pipeline name (default: all registered pipelines)",
    ),
) -> None:
    """Recompute feature tables from Raw data via pipelines."""
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

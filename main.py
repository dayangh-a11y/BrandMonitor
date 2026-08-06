"""Typer CLI entrypoint for the horse racing data collector."""

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
    help="Professional horse racing data collector (no ML / predictions).",
    add_completion=False,
    no_args_is_help=True,
)


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
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Log level (DEBUG, INFO, WARNING, ERROR)",
    ),
) -> None:
    """Collect a race and optional horse histories into JSON files."""
    settings = get_settings()
    setup_logging(settings.log_dir, log_level or settings.log_level)

    available = list_datasources()
    logger.info("Available datasources: {}", ", ".join(available))

    collector = RaceCollector(
        datasource_name=datasource,
        settings=settings,
        output_dir=output,
        collect_histories=not skip_history,
    )
    try:
        paths = collector.collect(url)
        for name, path in paths.items():
            typer.echo(f"Wrote {name} -> {path.resolve()}")
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

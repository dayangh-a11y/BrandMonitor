"""High-level race collector orchestrating DataSource + file / Raw warehouse output."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.datasources import DataSource, get_datasource
from src.models import HorseHistory, Race
from src.utils.json_io import ensure_dir, write_json
from src.utils.settings import Settings, get_settings


class RaceCollector:
    """
    Orchestrates collection:

    1. collect race from URL via DataSource
    2. write Race.json
    3. optionally collect horse histories → HorseHistory.json
    4. optionally persist Raw tables only (never Features)
    """

    def __init__(
        self,
        datasource: DataSource | None = None,
        *,
        datasource_name: str | None = None,
        settings: Settings | None = None,
        output_dir: Path | str | None = None,
        collect_histories: bool = True,
        persist_to_db: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or self.settings.output_dir)
        self.collect_histories = collect_histories
        self.persist_to_db = persist_to_db
        self._owns_datasource = datasource is None
        if datasource is not None:
            self.datasource = datasource
        else:
            name = datasource_name or self.settings.default_datasource
            self.datasource = get_datasource(name)

    def collect(self, url: str) -> dict[str, Path]:
        """
        Collect race (+ optional horse histories) and write JSON files.

        Returns a mapping of logical name → output path.
        """
        ensure_dir(self.output_dir)
        race = self.datasource.collect_race(url)
        self._enforce_racecourse_scope(race)
        race_path = self._write_race(race)

        result: dict[str, Path] = {"Race.json": race_path}
        histories: list[HorseHistory] = []
        if self.collect_histories:
            histories = self._collect_horse_histories(race)
            history_path = self._write_horse_histories(histories)
            result["HorseHistory.json"] = history_path

        if self.persist_to_db:
            self._persist_raw(url, race, histories)

        return result

    def _enforce_racecourse_scope(self, race: Race) -> None:
        from src.racecourses import ensure_track_in_scope

        ensure_track_in_scope(
            race.track,
            settings=self.settings,
            racecourse_code=race.racecourse_code,
        )

    def _write_race(self, race: Race) -> Path:
        path = self.output_dir / "Race.json"
        write_json(path, race)
        return path

    def _collect_horse_histories(self, race: Race) -> list[HorseHistory]:
        histories: list[HorseHistory] = []
        seen_urls: set[str] = set()

        for horse in race.horses:
            profile_url = horse.horse_profile_url
            if not profile_url:
                logger.warning("Horse {!r} has no profile URL; skipping history", horse.name)
                continue
            if profile_url in seen_urls:
                continue
            seen_urls.add(profile_url)
            try:
                history = self.datasource.collect_horse_history(profile_url)
                histories.append(history)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed collecting history for {!r} ({}): {}",
                    horse.name,
                    profile_url,
                    exc,
                )
        return histories

    def _write_horse_histories(self, histories: list[HorseHistory]) -> Path:
        path = self.output_dir / "HorseHistory.json"
        payload = [h.model_dump(mode="json", by_alias=True) for h in histories]
        write_json(path, payload)
        return path

    def _persist_raw(
        self,
        url: str,
        race: Race,
        histories: list[HorseHistory],
    ) -> None:
        """Write collected documents into Raw tables only."""
        from src.database import (
            finish_ingest_run,
            ingest_horse_history,
            ingest_race,
            session_scope,
            start_ingest_run,
        )

        source = getattr(self.datasource, "name", self.settings.default_datasource)
        with session_scope(self.settings) as session:
            run = start_ingest_run(session, source=source, input_url=url)
            try:
                ingest_race(session, race, source=source, ingest_run=run)
                for history in histories:
                    try:
                        ingest_horse_history(session, history, source=source)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Raw ingest failed for horse history: {}", exc)
                finish_ingest_run(session, run, status="success")
            except Exception as exc:
                finish_ingest_run(session, run, status="failed", notes=str(exc)[:500])
                raise

    def close(self) -> None:
        if self._owns_datasource:
            self.datasource.close()

    def __enter__(self) -> RaceCollector:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

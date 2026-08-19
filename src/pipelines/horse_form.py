"""Recent-form feature pipeline (Raw → feat_horse_form)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import mean

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.database.features import FeatHorseForm
from src.database.raw import RawHorse, RawHorseStart, RawRace, RawRaceEntry
from src.pipelines.base import FeaturePipeline
from src.pipelines.registry import register_pipeline

DEFAULT_WINDOW = 5


def _dated_finishes(session: Session, horse_id: int) -> list[tuple[object, int]]:
    rows: list[tuple[object, int]] = []
    for finish, race_date in session.execute(
        select(RawRaceEntry.finish_position, RawRace.race_date)
        .join(RawRace, RawRace.id == RawRaceEntry.race_id)
        .where(RawRaceEntry.horse_id == horse_id)
    ):
        if finish is not None and finish > 0:
            rows.append((race_date, finish))
    for finish, race_date in session.execute(
        select(RawHorseStart.finish_position, RawHorseStart.race_date).where(
            RawHorseStart.horse_id == horse_id
        )
    ):
        if finish is not None and finish > 0:
            rows.append((race_date, finish))
    # sort newest first; None dates last
    rows.sort(key=lambda x: x[0] or date.min, reverse=True)
    # dedupe
    seen: set[tuple[object, int]] = set()
    out: list[tuple[object, int]] = []
    for item in rows:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class HorseFormPipeline(FeaturePipeline):
    name = "horse_form"
    version = "1"

    def __init__(self, window_size: int = DEFAULT_WINDOW) -> None:
        self.window_size = window_size

    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        session.execute(delete(FeatHorseForm))
        session.flush()
        count = 0
        for horse in session.scalars(select(RawHorse)).all():
            finishes = _dated_finishes(session, horse.id)[: self.window_size]
            positions = [f for _, f in finishes]
            form_string = "-".join(str(p) for p in positions) if positions else None
            session.add(
                FeatHorseForm(
                    horse_id=horse.id,
                    window_size=self.window_size,
                    pipeline_run_id=pipeline_run_id,
                    computed_at=datetime.now(timezone.utc),
                    recent_starts=len(positions),
                    recent_wins=sum(1 for p in positions if p == 1),
                    recent_avg_finish=mean(positions) if positions else None,
                    form_string=form_string,
                )
            )
            count += 1
        session.flush()
        return count


def register() -> None:
    register_pipeline("horse_form", HorseFormPipeline)

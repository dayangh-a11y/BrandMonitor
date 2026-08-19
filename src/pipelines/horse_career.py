"""Horse career feature pipeline (Raw → feat_horse_career)."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.database.features import FeatHorseCareer
from src.database.raw import RawHorse, RawHorseStart, RawRace, RawRaceEntry
from src.database.types_util import rate
from src.pipelines.base import FeaturePipeline
from src.pipelines.registry import register_pipeline


def _collect_finishes(
    session: Session, horse_id: int
) -> list[tuple[object, int | None, float | None]]:
    """Merge finishes from race entries + historical starts."""
    rows: list[tuple[object, int | None, float | None]] = []

    for finish, margin, race_date in session.execute(
        select(
            RawRaceEntry.finish_position,
            RawRaceEntry.margin,
            RawRace.race_date,
        )
        .join(RawRace, RawRace.id == RawRaceEntry.race_id)
        .where(RawRaceEntry.horse_id == horse_id)
    ):
        rows.append((race_date, finish, margin))

    for finish, margin, race_date in session.execute(
        select(
            RawHorseStart.finish_position,
            RawHorseStart.margin,
            RawHorseStart.race_date,
        ).where(RawHorseStart.horse_id == horse_id)
    ):
        rows.append((race_date, finish, margin))

    return rows


class HorseCareerPipeline(FeaturePipeline):
    name = "horse_career"
    version = "1"

    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        session.execute(delete(FeatHorseCareer))
        session.flush()

        horses = session.scalars(select(RawHorse)).all()
        today = datetime.now(timezone.utc).date()
        count = 0

        for horse in horses:
            finishes = _collect_finishes(session, horse.id)
            uniq = list({(d, f, m) for d, f, m in finishes})
            scored = [(d, f, m) for d, f, m in uniq if f is not None and f > 0]
            starts = len(scored)
            wins = sum(1 for _, f, _ in scored if f == 1)
            places = sum(1 for _, f, _ in scored if f in (1, 2, 3))
            avg_finish = mean([f for _, f, _ in scored]) if scored else None
            margins = [m for _, _, m in scored if m is not None]
            avg_margin = mean(margins) if margins else None
            dates = [d for d, _, _ in scored if d is not None]
            last_race = max(dates) if dates else None
            days_since = (today - last_race).days if last_race else None

            session.add(
                FeatHorseCareer(
                    horse_id=horse.id,
                    pipeline_run_id=pipeline_run_id,
                    computed_at=datetime.now(timezone.utc),
                    starts=starts,
                    wins=wins,
                    places=places,
                    win_rate=rate(wins, starts),
                    place_rate=rate(places, starts),
                    avg_finish=avg_finish,
                    avg_margin=avg_margin,
                    last_race_date=last_race,
                    days_since_last_race=days_since,
                )
            )
            count += 1

        session.flush()
        return count


def register() -> None:
    register_pipeline("horse_career", HorseCareerPipeline)

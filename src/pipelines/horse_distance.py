"""Distance-bucket feature pipeline (Raw → feat_horse_distance)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.database.features import FeatHorseDistance
from src.database.raw import RawHorse, RawHorseStart, RawRace, RawRaceEntry
from src.pipelines.base import FeaturePipeline
from src.pipelines.registry import register_pipeline


class HorseDistancePipeline(FeaturePipeline):
    name = "horse_distance"
    version = "1"

    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        session.execute(delete(FeatHorseDistance))
        session.flush()

        # horse_id -> distance -> list[finish]
        bucket: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))

        for horse_id, distance, finish in session.execute(
            select(
                RawRaceEntry.horse_id,
                RawRace.distance,
                RawRaceEntry.finish_position,
            )
            .join(RawRace, RawRace.id == RawRaceEntry.race_id)
            .where(RawRaceEntry.horse_id.is_not(None))
        ):
            if horse_id and distance and finish and finish > 0:
                bucket[int(horse_id)][int(distance)].append(int(finish))

        for horse_id, distance, finish in session.execute(
            select(
                RawHorseStart.horse_id,
                RawHorseStart.distance,
                RawHorseStart.finish_position,
            ).where(RawHorseStart.horse_id.is_not(None))
        ):
            if horse_id and distance and finish and finish > 0:
                bucket[int(horse_id)][int(distance)].append(int(finish))

        # Ensure we only reference existing horses
        valid_ids = set(session.scalars(select(RawHorse.id)).all())
        count = 0
        for horse_id, distances in bucket.items():
            if horse_id not in valid_ids:
                continue
            for distance, finishes in distances.items():
                # dedupe identical finish lists is unnecessary; use all observations
                uniq = finishes  # keep multiplicity if same distance raced multiple times
                session.add(
                    FeatHorseDistance(
                        horse_id=horse_id,
                        distance=distance,
                        pipeline_run_id=pipeline_run_id,
                        computed_at=datetime.now(timezone.utc),
                        starts=len(uniq),
                        wins=sum(1 for f in uniq if f == 1),
                        avg_finish=mean(uniq) if uniq else None,
                    )
                )
                count += 1
        session.flush()
        return count


def register() -> None:
    register_pipeline("horse_distance", HorseDistancePipeline)

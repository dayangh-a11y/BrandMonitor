"""Jockey / trainer feature pipelines (Raw → feat_*_stats)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.database.features import FeatJockeyStats, FeatTrainerStats
from src.database.raw import RawHorseStart, RawRaceEntry
from src.database.types_util import rate
from src.pipelines.base import FeaturePipeline
from src.pipelines.registry import register_pipeline


def _accumulate(
    session: Session,
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    jockeys: dict[str, list[int]] = defaultdict(list)
    trainers: dict[str, list[int]] = defaultdict(list)

    for jockey, trainer, finish in session.execute(
        select(RawRaceEntry.jockey, RawRaceEntry.trainer, RawRaceEntry.finish_position)
    ):
        if finish is None or finish <= 0:
            continue
        if jockey:
            jockeys[jockey.strip()].append(int(finish))
        if trainer:
            trainers[trainer.strip()].append(int(finish))

    for jockey, trainer, finish in session.execute(
        select(RawHorseStart.jockey, RawHorseStart.trainer, RawHorseStart.finish_position)
    ):
        if finish is None or finish <= 0:
            continue
        if jockey:
            jockeys[jockey.strip()].append(int(finish))
        if trainer:
            trainers[trainer.strip()].append(int(finish))

    return jockeys, trainers


class JockeyStatsPipeline(FeaturePipeline):
    name = "jockey_stats"
    version = "1"

    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        session.execute(delete(FeatJockeyStats))
        session.flush()
        jockeys, _ = _accumulate(session)
        count = 0
        now = datetime.now(timezone.utc)
        for name, finishes in jockeys.items():
            if not name:
                continue
            starts = len(finishes)
            wins = sum(1 for f in finishes if f == 1)
            session.add(
                FeatJockeyStats(
                    jockey=name,
                    pipeline_run_id=pipeline_run_id,
                    computed_at=now,
                    starts=starts,
                    wins=wins,
                    win_rate=rate(wins, starts),
                )
            )
            count += 1
        session.flush()
        return count


class TrainerStatsPipeline(FeaturePipeline):
    name = "trainer_stats"
    version = "1"

    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        session.execute(delete(FeatTrainerStats))
        session.flush()
        _, trainers = _accumulate(session)
        count = 0
        now = datetime.now(timezone.utc)
        for name, finishes in trainers.items():
            if not name:
                continue
            starts = len(finishes)
            wins = sum(1 for f in finishes if f == 1)
            session.add(
                FeatTrainerStats(
                    trainer=name,
                    pipeline_run_id=pipeline_run_id,
                    computed_at=now,
                    starts=starts,
                    wins=wins,
                    win_rate=rate(wins, starts),
                )
            )
            count += 1
        session.flush()
        return count


def register() -> None:
    register_pipeline("jockey_stats", JockeyStatsPipeline)
    register_pipeline("trainer_stats", TrainerStatsPipeline)

"""Infer racing seasons from warehouse race dates (no hardcoded calendars)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analytics.metrics import as_date
from src.warehouse.models import WhRace


@dataclass(frozen=True, slots=True)
class SeasonCluster:
    racecourse_code: str | None
    start_date: date
    end_date: date
    race_days: int
    heats: int
    is_completed: bool
    is_latest_completed: bool

    @property
    def season_key(self) -> str:
        course = self.racecourse_code or "all"
        return f"{course}:{self.start_date.isoformat()}:{self.end_date.isoformat()}"

    @property
    def label(self) -> str:
        course = self.racecourse_code or "all"
        if self.start_date == self.end_date:
            return f"{course} {self.start_date.isoformat()}"
        return f"{course} {self.start_date.isoformat()} → {self.end_date.isoformat()}"


def discover_seasons(
    session: Session,
    *,
    racecourse_code: str | None = None,
) -> list[SeasonCluster]:
    """
    Cluster distinct race dates per racecourse.

    Break threshold = max(45, median(gap)/2) from that course's own spacing.
    A cluster is completed if a later cluster exists for the same course.
    """
    q = select(WhRace.racecourse_code, WhRace.race_date, func.count()).where(
        WhRace.race_date.is_not(None)
    )
    if racecourse_code:
        q = q.where(WhRace.racecourse_code == racecourse_code)
    q = q.group_by(WhRace.racecourse_code, WhRace.race_date).order_by(
        WhRace.racecourse_code, WhRace.race_date
    )

    by_course: dict[str | None, list[tuple[date, int]]] = {}
    for code, race_date, heats in session.execute(q):
        d = as_date(race_date)
        if d is None:
            continue
        by_course.setdefault(code, []).append((d, int(heats)))

    seasons: list[SeasonCluster] = []
    for code, day_rows in by_course.items():
        dates = [d for d, _ in day_rows]
        heats_map = {d: h for d, h in day_rows}
        if len(dates) == 1:
            clusters = [[dates[0]]]
        else:
            gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
            threshold = max(45, int(median(gaps) / 2)) if gaps else 45
            clusters = [[dates[0]]]
            for d in dates[1:]:
                if (d - clusters[-1][-1]).days > threshold:
                    clusters.append([d])
                else:
                    clusters[-1].append(d)

        for i, cluster in enumerate(clusters):
            is_latest = i == len(clusters) - 1
            is_completed = i < len(clusters) - 1
            seasons.append(
                SeasonCluster(
                    racecourse_code=code,
                    start_date=cluster[0],
                    end_date=cluster[-1],
                    race_days=len(cluster),
                    heats=sum(heats_map.get(d, 0) for d in cluster),
                    is_completed=is_completed,
                    is_latest_completed=is_completed and i == len(clusters) - 2,
                )
            )

    # Ensure exactly one latest_completed flag per course when possible
    by_c: dict[str | None, list[SeasonCluster]] = {}
    for s in seasons:
        by_c.setdefault(s.racecourse_code, []).append(s)
    fixed: list[SeasonCluster] = []
    for code, items in by_c.items():
        completed = [s for s in items if s.is_completed]
        latest_key = completed[-1].season_key if completed else None
        for s in items:
            fixed.append(
                SeasonCluster(
                    racecourse_code=s.racecourse_code,
                    start_date=s.start_date,
                    end_date=s.end_date,
                    race_days=s.race_days,
                    heats=s.heats,
                    is_completed=s.is_completed,
                    is_latest_completed=(s.season_key == latest_key),
                )
            )
    return sorted(fixed, key=lambda s: (s.racecourse_code or "", s.start_date))

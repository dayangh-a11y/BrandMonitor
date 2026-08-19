"""Load horse identity profiles from warehouse + raw signals."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.raw import RawHorse
from src.identity.profile import HorseProfile
from src.warehouse.models import (
    WhHorse,
    WhHorsePedigree,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhTrainer,
)


def _parse_payload(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _age_from_birthdate(birth: date | None, as_of: date | None = None) -> int | None:
    if birth is None:
        return None
    ref = as_of or date.today()
    years = ref.year - birth.year
    if (ref.month, ref.day) < (birth.month, birth.day):
        years -= 1
    return max(0, years)


def load_horse_profiles(session: Session) -> list[HorseProfile]:
    """
    Build identity profiles for every warehouse horse.

    Signals:
    - name / sex / birthdate / source ids from wh_horses
    - sire / dam from wh_horse_pedigree (and raw payload when present)
    - age from birthdate or raw payload age
    - owner / trainer from race-result frequency
    """
    horses = list(session.scalars(select(WhHorse)).all())
    if not horses:
        return []

    pedigrees = {
        p.horse_id: p
        for p in session.scalars(select(WhHorsePedigree)).all()
    }
    trainers = {t.id: t.name for t in session.scalars(select(WhTrainer)).all()}
    owners = {o.id: o.name for o in session.scalars(select(WhOwner)).all()}

    owner_counts: dict[int, Counter[str]] = defaultdict(Counter)
    trainer_counts: dict[int, Counter[str]] = defaultdict(Counter)
    start_counts: Counter[int] = Counter()
    race_dates: dict[int, list[date]] = defaultdict(list)
    race_courses: dict[int, list[str]] = defaultdict(list)

    races = {r.id: r for r in session.scalars(select(WhRace)).all()}
    for res in session.scalars(select(WhRaceResult)).all():
        if res.horse_id is None:
            continue
        start_counts[res.horse_id] += 1
        if res.owner_id and res.owner_id in owners:
            owner_counts[res.horse_id][owners[res.owner_id]] += 1
        if res.trainer_id and res.trainer_id in trainers:
            trainer_counts[res.horse_id][trainers[res.trainer_id]] += 1
        race = races.get(res.race_id) if res.race_id is not None else None
        if race is not None:
            if race.race_date is not None:
                d = race.race_date
                if hasattr(d, "date"):
                    d = d.date()
                if isinstance(d, date):
                    race_dates[res.horse_id].append(d)
            if race.racecourse_code:
                race_courses[res.horse_id].append(str(race.racecourse_code))

    # Raw payload age / pedigree enrichment keyed by source_horse_id
    raw_by_source: dict[str, dict[str, Any]] = {}
    for rh in session.scalars(
        select(RawHorse).where(RawHorse.is_current.is_(True))
    ).all():
        if not rh.source_horse_id:
            continue
        payload = _parse_payload(rh.payload_json)
        raw_by_source[str(rh.source_horse_id)] = {
            "sire": rh.sire or payload.get("sire") or payload.get("father"),
            "dam": rh.dam or payload.get("dam") or payload.get("mother"),
            "age": payload.get("age"),
            "sex": rh.sex or payload.get("sex"),
            "name": rh.name,
        }

    profiles: list[HorseProfile] = []
    for h in horses:
        ped = pedigrees.get(h.id)
        raw = raw_by_source.get(str(h.source_horse_id or ""), {})
        sire = (ped.sire_name if ped else None) or raw.get("sire")
        dam = (ped.dam_name if ped else None) or raw.get("dam")
        age = _age_from_birthdate(h.birthdate)
        if age is None:
            try:
                age = int(raw["age"]) if raw.get("age") is not None else None
            except (TypeError, ValueError):
                age = None

        own = [n for n, _ in owner_counts[h.id].most_common(5)]
        trn = [n for n, _ in trainer_counts[h.id].most_common(5)]
        dates = sorted(set(race_dates[h.id]))
        birth_year = h.birthdate.year if h.birthdate else None
        if birth_year is None and age is not None and dates:
            # Approximate birth year from age at latest observed start
            birth_year = dates[-1].year - int(age)

        profiles.append(
            HorseProfile(
                warehouse_horse_id=h.id,
                name=h.name,
                source=h.source,
                source_horse_id=h.source_horse_id,
                sex=h.sex or raw.get("sex"),
                birthdate=h.birthdate,
                birth_year=birth_year,
                age_years=age,
                sire=str(sire).strip() if sire else None,
                dam=str(dam).strip() if dam else None,
                owners=own,
                trainers=trn,
                starts=int(start_counts[h.id]),
                race_dates=dates,
                racecourse_codes=list(dict.fromkeys(race_courses[h.id])),
            )
        )
    return profiles

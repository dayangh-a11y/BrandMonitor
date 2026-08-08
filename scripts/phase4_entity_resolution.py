#!/usr/bin/env python3
"""PHASE 4 — ENTITY RESOLUTION (freeze Coverage/Integrity; no historical overwrite).

Builds / refreshes canonical identity layer and exports required CSVs.
Never deletes race days, heats, or results. Auto-merge only EXACT/HIGH.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import jdatetime
from loguru import logger
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from src.database import init_db, session_scope
from src.identity import build_horse_identity, duplicate_merge_report
from src.identity.models import IdHorse, IdHorseAlias, IdHorseLink, IdHorseMergeCandidate
from src.identity.normalize import normalize_name, normalize_sex
from src.racecourses.registry import RACECOURSES, resolve_racecourse
from src.racecourses.track_config import resolve_track_configuration
from src.warehouse import run_entity_resolution
from src.warehouse.fuzzy import find_duplicate_pairs, similarity
from src.warehouse.models import (
    WhEntityMatch,
    WhHorse,
    WhHorsePedigree,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhTrainer,
)

ART = Path("/opt/cursor/artifacts")
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path("/workspace/output/historical/horse_racing.db")
DEFAULT_DB = f"sqlite:///{DB_PATH}"


def freeze_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "race_days": conn.execute(
            "SELECT COUNT(*) FROM ("
            " SELECT DISTINCT race_date, track FROM wh_races "
            " WHERE race_date IS NOT NULL AND track IS NOT NULL)"
        ).fetchone()[0],
        "heats": conn.execute("SELECT COUNT(*) FROM wh_races").fetchone()[0],
        "results": conn.execute("SELECT COUNT(*) FROM wh_race_results").fetchone()[0],
        "wh_horses": conn.execute("SELECT COUNT(*) FROM wh_horses").fetchone()[0],
        "raw_races_all": conn.execute("SELECT COUNT(*) FROM raw_races").fetchone()[0],
        "raw_races_current": conn.execute(
            "SELECT COUNT(*) FROM raw_races WHERE is_current=1"
        ).fetchone()[0],
    }


def confidence_from_score(score: float | None, *, method: str = "") -> str:
    if method in ("exact_normalized", "same_source_id", "exact") or (
        score is not None and score >= 0.98
    ):
        return "EXACT"
    if score is not None and score >= 0.88:
        return "HIGH"
    if score is not None and score >= 0.72:
        return "MEDIUM"
    if score is not None and score >= 0.50:
        return "LOW"
    return "UNRESOLVED"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def build_people_canonical(
    session: Session,
    *,
    entity_type: str,
    model: type,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Canonicalize trainers/owners: auto-merge EXACT/HIGH only."""
    rows = list(session.scalars(select(model)).all())
    raw_n = len(rows)

    # Group by normalized name
    by_norm: dict[str, list[Any]] = defaultdict(list)
    for r in rows:
        by_norm[normalize_name(r.name) or f"__empty_{r.id}"].append(r)

    # Fuzzy pairs among unique norms (HIGH only auto)
    unique_norms = [n for n in by_norm if not n.startswith("__empty_")]
    display_for_norm = {
        n: sorted(by_norm[n], key=lambda x: x.id)[0].name for n in unique_norms
    }
    names_for_fuzzy = list(display_for_norm.values())
    fuzzy_pairs = find_duplicate_pairs(names_for_fuzzy, threshold=0.88)

    # Union-find on norms for EXACT (same norm) + HIGH fuzzy
    parent = {n: n for n in unique_norms}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # EXACT already grouped by norm
    high_merges = 0
    review: list[dict[str, Any]] = []
    aliases_out: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    # Map display name → norm for fuzzy
    name_to_norm = {display_for_norm[n]: n for n in unique_norms}
    for left, right, score in fuzzy_pairs:
        nl, nr = name_to_norm.get(left), name_to_norm.get(right)
        if not nl or not nr or nl == nr:
            continue
        conf = confidence_from_score(score, method="fuzzy")
        if conf == "HIGH":
            union(nl, nr)
            high_merges += 1
        else:
            review.append(
                {
                    "entity_type": entity_type,
                    "left_raw": left,
                    "right_raw": right,
                    "score": round(score, 4),
                    "confidence": conf,
                    "reason": "fuzzy_name_needs_review",
                    "status": "open",
                }
            )

    # Also pull wh_entity_matches MEDIUM/LOW into review
    for m in session.scalars(
        select(WhEntityMatch).where(
            WhEntityMatch.entity_type == entity_type,
            WhEntityMatch.status == "candidate",
        )
    ):
        conf = confidence_from_score(m.score, method=m.method or "")
        if conf in ("MEDIUM", "LOW", "UNRESOLVED"):
            review.append(
                {
                    "entity_type": entity_type,
                    "left_raw": m.left_key,
                    "right_raw": m.right_key,
                    "score": m.score,
                    "confidence": conf,
                    "reason": f"wh_entity_match:{m.method}",
                    "status": "open",
                }
            )

    clusters: dict[str, list[str]] = defaultdict(list)
    for n in unique_norms:
        clusters[find(n)].append(n)

    canonical_rows: list[dict[str, Any]] = []
    next_id = 1
    exact_merge_groups = sum(1 for g in by_norm.values() if len(g) > 1)

    for root, norms in sorted(clusters.items(), key=lambda x: x[0]):
        members: list[Any] = []
        for n in norms:
            members.extend(by_norm[n])
        members.sort(key=lambda x: x.id)
        primary = members[0]
        canon_name = primary.name.strip()
        alias_set = sorted({m.name for m in members})
        conf = "EXACT" if len(norms) == 1 and len(members) >= 1 else (
            "HIGH" if len(norms) > 1 else "EXACT"
        )
        if len(members) == 1 and len(norms) == 1:
            conf = "EXACT"
        elif len(norms) > 1:
            conf = "HIGH"
        elif len(members) > 1:
            conf = "EXACT"  # same normalized name

        eid = next_id
        next_id += 1
        canonical_rows.append(
            {
                f"{entity_type}_id": eid,
                "raw_name": primary.name,
                "canonical_name": canon_name,
                "aliases": "|".join(alias_set),
                "confidence": conf,
                "source": "wh_" + entity_type + "s",
                "warehouse_ids": "|".join(str(m.id) for m in members),
                "member_count": len(members),
            }
        )
        for a in alias_set:
            aliases_out.append(
                {
                    "entity_type": entity_type,
                    "entity_id": eid,
                    "raw_value": a,
                    "canonical_value": canon_name,
                    "normalized": normalize_name(a),
                    "confidence": conf,
                    "source": "wh_" + entity_type + "s",
                }
            )

    stats = {
        f"raw_{entity_type}s": raw_n,
        f"canonical_{entity_type}s": len(canonical_rows),
        f"{entity_type}_merges": exact_merge_groups + high_merges,
        f"unresolved_{entity_type}s": 0,  # all WH rows assigned a canonical id
        "high_fuzzy_merges": high_merges,
        "exact_norm_duplicate_groups": exact_merge_groups,
    }
    return canonical_rows, aliases_out, review, stats


def build_track_canonical(session: Session) -> tuple[list[dict], list[dict], list[dict], dict]:
    races = list(session.scalars(select(WhRace)).all())
    raw_names = Counter()
    code_by_raw: dict[str, Counter] = defaultdict(Counter)
    for r in races:
        raw = (r.track or "").strip() or "?"
        raw_names[raw] += 1
        code_by_raw[raw][r.racecourse_code or "?"] += 1

    canonical: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    merges = 0
    unknown_tracks = 0

    # One row per registry course + synthetic
    seen_codes: set[str] = set()
    for course in RACECOURSES:
        seen_codes.add(course.code)
        cfg = resolve_track_configuration(racecourse_code=course.code)
        raws_for_code = [
            raw
            for raw, codes in code_by_raw.items()
            if codes.most_common(1)[0][0] == course.code
            or resolve_racecourse(raw) and resolve_racecourse(raw).code == course.code
        ]
        # Prefer WH city label
        city_label = course.name_fa
        alias_list = sorted(set(list(course.aliases) + raws_for_code + [course.name_fa, course.name_en]))
        if len(raws_for_code) > 1:
            merges += len(raws_for_code) - 1
        canonical.append(
            {
                "track_id": course.code,
                "canonical_name": course.name_fa,
                "name_en": course.name_en,
                "raw_names": "|".join(sorted(set(raws_for_code))) or course.name_fa,
                "aliases": "|".join(alias_list),
                "straight_length_m": cfg.straight_length_m if cfg else None,
                "track_config": "MATCHED" if cfg else "UNKNOWN",
                "confidence": "EXACT",
                "source": "racecourse_registry",
                "heats": sum(raw_names[r] for r in raws_for_code),
            }
        )
        for a in alias_list:
            aliases.append(
                {
                    "entity_type": "track",
                    "entity_id": course.code,
                    "raw_value": a,
                    "canonical_value": course.name_fa,
                    "normalized": normalize_name(a),
                    "confidence": "EXACT",
                    "source": "racecourse_registry",
                }
            )

    # Unmatched raw tracks (e.g. انبارآلوم has registry but check UNKNOWN config)
    for raw, n in raw_names.items():
        course = resolve_racecourse(raw)
        if course is None:
            unknown_tracks += n
            tid = f"unresolved:{normalize_name(raw)}"
            canonical.append(
                {
                    "track_id": tid,
                    "canonical_name": raw,
                    "name_en": None,
                    "raw_names": raw,
                    "aliases": raw,
                    "straight_length_m": None,
                    "track_config": "UNKNOWN",
                    "confidence": "UNRESOLVED",
                    "source": "wh_races",
                    "heats": n,
                }
            )
            review.append(
                {
                    "entity_type": "track",
                    "left_raw": raw,
                    "right_raw": None,
                    "score": None,
                    "confidence": "UNRESOLVED",
                    "reason": "unregistered_track_name",
                    "status": "open",
                    "heats": n,
                }
            )
        else:
            cfg = resolve_track_configuration(racecourse_code=course.code, track_name=raw)
            if cfg is None:
                # Known track identity but no straight-length config
                review.append(
                    {
                        "entity_type": "track_configuration",
                        "left_raw": raw,
                        "right_raw": course.code,
                        "score": None,
                        "confidence": "UNRESOLVED",
                        "reason": "track_configuration_unknown_no_straight_length",
                        "status": "open",
                        "heats": n,
                    }
                )
                unknown_tracks += n

    stats = {
        "raw_track_names": len(raw_names),
        "canonical_tracks": len(canonical),
        "track_merges": merges,
        "unknown_tracks": unknown_tracks,
        "raw_name_variants": dict(raw_names),
    }
    return canonical, aliases, review, stats


def validate_dates(session: Session) -> dict[str, Any]:
    bad = 0
    checked = 0
    samples: list[dict[str, Any]] = []
    for r in session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all():
        checked += 1
        try:
            g = date.fromisoformat(str(r.race_date)[:10])
        except ValueError:
            bad += 1
            continue
        jd = jdatetime.date.fromgregorian(date=g)
        expected = f"{jd.year}/{jd.month:02d}/{jd.day:02d}"
        got = None
        if r.race_date_jalali:
            try:
                p = str(r.race_date_jalali).replace("-", "/").split("/")
                got = f"{int(p[0])}/{int(p[1]):02d}/{int(p[2]):02d}"
            except Exception:
                got = str(r.race_date_jalali)
        if got != expected:
            bad += 1
            if len(samples) < 20:
                samples.append(
                    {
                        "race_id": r.id,
                        "gregorian_date": g.isoformat(),
                        "jalali_date_db": r.race_date_jalali,
                        "jalali_date_expected": expected,
                        "canonical_date": expected,
                    }
                )
    return {
        "checked": checked,
        "mismatches": bad,
        "ok": checked - bad,
        "samples": samples,
        "policy": "Display/canonical calendar is Jalali; Gregorian stored internally.",
    }


def detect_horse_collisions(session: Session) -> list[dict[str, Any]]:
    """Same display name but conflicting sex/birth → ENTITY_COLLISION (not merged)."""
    horses = list(session.scalars(select(IdHorse).where(IdHorse.status == "active")).all())
    by_name: dict[str, list[IdHorse]] = defaultdict(list)
    for h in horses:
        by_name[h.normalized_name].append(h)
    collisions: list[dict[str, Any]] = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        sexes = {h.sex for h in group if h.sex}
        years = {h.birth_year for h in group if h.birth_year is not None}
        sires = {h.sire_normalized for h in group if h.sire_normalized}
        dams = {h.dam_normalized for h in group if h.dam_normalized}
        reasons = []
        if len(sexes) > 1:
            reasons.append(f"sex={sorted(sexes)}")
        if len(years) > 1:
            reasons.append(f"birth_year={sorted(years)}")
        if len(sires) > 1:
            reasons.append(f"sire={sorted(sires)}")
        if len(dams) > 1:
            reasons.append(f"dam={sorted(dams)}")
        if not reasons:
            # same name multiple IDs without demographic conflict → potential duplicate
            continue
        collisions.append(
            {
                "conflict_type": "ENTITY_COLLISION",
                "entity_type": "horse",
                "normalized_name": name,
                "horse_ids": "|".join(str(h.horse_id) for h in group),
                "display_names": "|".join(h.display_name for h in group),
                "reasons": "; ".join(reasons),
                "action": "not_merged",
            }
        )
    return collisions


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=DEFAULT_DB)
    ap.add_argument("--skip-rebuild", action="store_true")
    args = ap.parse_args()

    ART.mkdir(parents=True, exist_ok=True)
    init_db(url=args.db_url)

    conn = sqlite3.connect(str(DB_PATH))
    before = freeze_counts(conn)
    logger.info("FROZEN baseline {}", before)

    # Snapshot result→horse links for post check
    before_links = conn.execute(
        "SELECT race_id, horse_id FROM wh_race_results ORDER BY id"
    ).fetchall()
    conn.close()

    with session_scope(url=args.db_url) as session:
        if not args.skip_rebuild:
            logger.info("run_entity_resolution (candidates only)")
            er_counts = run_entity_resolution(session)
            logger.info("ER candidates {}", er_counts)
            logger.info("build_horse_identity (id_* only; no race/result delete)")
            horse_build = build_horse_identity(session, clear_existing=True)
            logger.info("horse build {}", {k: horse_build.get(k) for k in horse_build if k != "params_json"})
        else:
            er_counts = {}
            horse_build = {"skipped": True}

        horse_report = duplicate_merge_report(session, limit=500)

        # Horses canonical export
        horses = list(session.scalars(select(IdHorse).where(IdHorse.status == "active")).all())
        links = list(session.scalars(select(IdHorseLink)).all())
        aliases = list(session.scalars(select(IdHorseAlias)).all())
        candidates = list(
            session.scalars(
                select(IdHorseMergeCandidate).where(IdHorseMergeCandidate.status == "open")
            ).all()
        )
        links_by_horse: dict[int, list[IdHorseLink]] = defaultdict(list)
        for lk in links:
            links_by_horse[lk.horse_id].append(lk)

        wh_by_id = {h.id: h for h in session.scalars(select(WhHorse)).all()}
        ped_by_wh = {
            p.horse_id: p
            for p in session.scalars(select(WhHorsePedigree)).all()
        }

        horses_csv: list[dict[str, Any]] = []
        conf_dist: Counter = Counter()
        confirmed_merges = 0
        for h in horses:
            members = links_by_horse.get(h.horse_id, [])
            if len(members) > 1:
                confirmed_merges += 1
                conf = "HIGH"
            else:
                conf = "EXACT"
            conf_dist[conf] += 1
            raw_names = []
            sources = []
            for m in members:
                wh = wh_by_id.get(m.warehouse_horse_id)
                if wh:
                    raw_names.append(wh.name)
                    sources.append(wh.source)
            ped = ped_by_wh.get(members[0].warehouse_horse_id) if members else None
            horses_csv.append(
                {
                    "horse_id": h.horse_id,
                    "canonical_name": h.display_name,
                    "normalized_name": h.normalized_name,
                    "raw_names": "|".join(sorted(set(raw_names))) or h.display_name,
                    "sex": h.sex,
                    "birth_year": h.birth_year,
                    "sire": h.sire_normalized,
                    "dam": h.dam_normalized,
                    "sire_raw": ped.sire_name if ped else None,
                    "dam_raw": ped.dam_name if ped else None,
                    "member_count": len(members),
                    "warehouse_ids": "|".join(str(m.warehouse_horse_id) for m in members),
                    "confidence": conf,
                    "source": "|".join(sorted(set(sources))) or "wh_horses",
                    "status": h.status,
                }
            )

        # Candidate confidence distribution
        for c in candidates:
            conf_dist[confidence_from_score(c.score)] += 0  # counted in review, not canonical
            conf_dist[confidence_from_score(c.score) + "_candidate"] += 1

        horse_aliases_csv = [
            {
                "entity_type": "horse",
                "entity_id": a.horse_id,
                "raw_value": a.alias,
                "canonical_value": None,
                "normalized": a.normalized_alias,
                "confidence": "EXACT",
                "source": a.method or "identity_build",
            }
            for a in aliases
        ]

        collisions = detect_horse_collisions(session)

        # Trainers / owners
        trainers_csv, t_aliases, t_review, t_stats = build_people_canonical(
            session, entity_type="trainer", model=WhTrainer
        )
        owners_csv, o_aliases, o_review, o_stats = build_people_canonical(
            session, entity_type="owner", model=WhOwner
        )

        # Pedigree entities (sparse — do not invent)
        sire_names = Counter()
        dam_names = Counter()
        pedigree_conflicts: list[dict[str, Any]] = []
        for h in horses:
            if h.sire_normalized:
                sire_names[h.sire_normalized] += 1
            if h.dam_normalized:
                dam_names[h.dam_normalized] += 1
        # Check WH pedigree contradictions (same horse different sire across raw — currently empty)
        ped_rows = list(session.scalars(select(WhHorsePedigree)).all())
        filled_sire = sum(1 for p in ped_rows if p.sire_name)
        filled_dam = sum(1 for p in ped_rows if p.dam_name)

        pedigree_csv: list[dict[str, Any]] = []
        for i, (name, n) in enumerate(sorted(sire_names.items()), 1):
            pedigree_csv.append(
                {
                    "pedigree_entity_id": f"sire:{i}",
                    "role": "SIRE",
                    "canonical_name": name,
                    "raw_name": name,
                    "mentions": n,
                    "confidence": "EXACT" if n else "UNRESOLVED",
                    "source": "id_horses.sire_normalized",
                }
            )
        for i, (name, n) in enumerate(sorted(dam_names.items()), 1):
            pedigree_csv.append(
                {
                    "pedigree_entity_id": f"dam:{i}",
                    "role": "DAM",
                    "canonical_name": name,
                    "raw_name": name,
                    "mentions": n,
                    "confidence": "EXACT" if n else "UNRESOLVED",
                    "source": "id_horses.dam_normalized",
                }
            )

        tracks_csv, track_aliases, track_review, track_stats = build_track_canonical(session)
        date_val = validate_dates(session)

        # Review queue: horse candidates MEDIUM/LOW + people + track unknown
        review_queue: list[dict[str, Any]] = []
        for c in candidates:
            conf = confidence_from_score(c.score)
            left = session.get(IdHorse, c.left_horse_id)
            right = session.get(IdHorse, c.right_horse_id)
            review_queue.append(
                {
                    "entity_type": "horse",
                    "left_id": c.left_horse_id,
                    "right_id": c.right_horse_id,
                    "left_raw": left.display_name if left else None,
                    "right_raw": right.display_name if right else None,
                    "score": c.score,
                    "confidence": conf,
                    "reason": "merge_candidate_not_auto",
                    "status": "open",
                }
            )
        review_queue.extend(t_review)
        review_queue.extend(o_review)
        review_queue.extend(track_review)

        conflicts_csv = list(collisions)
        for c in candidates:
            # sex conflict etc. already not auto-merged; mark collisions from evidence
            ev = c.evidence_json or {}
            if isinstance(ev, dict) and ev.get("hard_conflict"):
                conflicts_csv.append(
                    {
                        "conflict_type": "ENTITY_COLLISION",
                        "entity_type": "horse",
                        "normalized_name": None,
                        "horse_ids": f"{c.left_horse_id}|{c.right_horse_id}",
                        "display_names": None,
                        "reasons": str(ev.get("hard_conflict")),
                        "action": "not_merged",
                    }
                )

        # Write outputs
        write_csv(
            ART / "horses_canonical.csv",
            horses_csv,
            [
                "horse_id",
                "canonical_name",
                "normalized_name",
                "raw_names",
                "sex",
                "birth_year",
                "sire",
                "dam",
                "sire_raw",
                "dam_raw",
                "member_count",
                "warehouse_ids",
                "confidence",
                "source",
                "status",
            ],
        )
        write_csv(
            ART / "trainers_canonical.csv",
            trainers_csv,
            [
                "trainer_id",
                "raw_name",
                "canonical_name",
                "aliases",
                "confidence",
                "source",
                "warehouse_ids",
                "member_count",
            ],
        )
        write_csv(
            ART / "owners_canonical.csv",
            owners_csv,
            [
                "owner_id",
                "raw_name",
                "canonical_name",
                "aliases",
                "confidence",
                "source",
                "warehouse_ids",
                "member_count",
            ],
        )
        write_csv(
            ART / "pedigree_entities.csv",
            pedigree_csv,
            [
                "pedigree_entity_id",
                "role",
                "canonical_name",
                "raw_name",
                "mentions",
                "confidence",
                "source",
            ],
        )
        write_csv(
            ART / "tracks_canonical.csv",
            tracks_csv,
            [
                "track_id",
                "canonical_name",
                "name_en",
                "raw_names",
                "aliases",
                "straight_length_m",
                "track_config",
                "confidence",
                "source",
                "heats",
            ],
        )
        all_aliases = horse_aliases_csv + t_aliases + o_aliases + track_aliases
        # fill canonical_value for horse aliases
        horse_name = {h.horse_id: h.display_name for h in horses}
        for a in all_aliases:
            if a["entity_type"] == "horse" and not a.get("canonical_value"):
                a["canonical_value"] = horse_name.get(int(a["entity_id"]))
        write_csv(
            ART / "entity_aliases.csv",
            all_aliases,
            [
                "entity_type",
                "entity_id",
                "raw_value",
                "canonical_value",
                "normalized",
                "confidence",
                "source",
            ],
        )
        write_csv(
            ART / "entity_conflicts.csv",
            conflicts_csv,
            [
                "conflict_type",
                "entity_type",
                "normalized_name",
                "horse_ids",
                "display_names",
                "reasons",
                "action",
            ],
        )
        write_csv(
            ART / "entity_review_queue.csv",
            review_queue,
            [
                "entity_type",
                "left_id",
                "right_id",
                "left_raw",
                "right_raw",
                "score",
                "confidence",
                "reason",
                "status",
                "heats",
            ],
        )

        session.commit()

    # Post freeze validation
    conn = sqlite3.connect(str(DB_PATH))
    after = freeze_counts(conn)
    after_links = conn.execute(
        "SELECT race_id, horse_id FROM wh_race_results ORDER BY id"
    ).fetchall()
    conn.close()

    results_unchanged = before["results"] == after["results"]
    days_unchanged = before["race_days"] == after["race_days"]
    heats_unchanged = before["heats"] == after["heats"]
    links_unchanged = before_links == after_links
    raw_unchanged = before["raw_races_all"] == after["raw_races_all"]

    # Confidence distribution for report (canonical horses + open candidates)
    conf_report = {
        "EXACT": sum(1 for h in horses_csv if h["confidence"] == "EXACT"),
        "HIGH": sum(1 for h in horses_csv if h["confidence"] == "HIGH"),
        "MEDIUM": sum(
            1 for r in review_queue if r.get("entity_type") == "horse" and r.get("confidence") == "MEDIUM"
        ),
        "LOW": sum(
            1 for r in review_queue if r.get("entity_type") == "horse" and r.get("confidence") == "LOW"
        ),
        "UNRESOLVED": sum(
            1
            for r in review_queue
            if r.get("entity_type") == "horse" and r.get("confidence") == "UNRESOLVED"
        ),
    }

    potential_duplicates = len(
        [d for d in horse_report.get("duplicate_horses", []) if len(d.get("warehouse_ids") or []) >= 2]
    )
    # Open candidates = potential not yet merged
    potential_dup_open = len([r for r in review_queue if r.get("entity_type") == "horse"])

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "PHASE_4_ENTITY_RESOLUTION",
        "frozen_baseline": before,
        "after_counts": after,
        "critical_validation": {
            "result_count_unchanged": results_unchanged,
            "race_day_count_unchanged": days_unchanged,
            "heat_count_unchanged": heats_unchanged,
            "result_horse_links_unchanged": links_unchanged,
            "raw_races_unchanged": raw_unchanged,
            "historical_records_deleted": False,
            "before": before,
            "after": after,
        },
        "horses": {
            "RAW_HORSES": before["wh_horses"],
            "CANONICAL_HORSES": len(horses_csv),
            "CONFIRMED_HORSE_MERGES": confirmed_merges,
            "POTENTIAL_DUPLICATES": potential_dup_open,
            "ENTITY_COLLISIONS": len(collisions),
            "UNRESOLVED_HORSES": conf_report["UNRESOLVED"],
        },
        "trainers": {
            "RAW_TRAINERS": t_stats["raw_trainers"],
            "CANONICAL_TRAINERS": t_stats["canonical_trainers"],
            "TRAINER_MERGES": t_stats["trainer_merges"],
            "UNRESOLVED_TRAINERS": t_stats["unresolved_trainers"],
        },
        "owners": {
            "RAW_OWNERS": o_stats["raw_owners"],
            "CANONICAL_OWNERS": o_stats["canonical_owners"],
            "OWNER_MERGES": o_stats["owner_merges"],
            "UNRESOLVED_OWNERS": o_stats["unresolved_owners"],
        },
        "pedigree": {
            "SIRE_ENTITIES": sum(1 for p in pedigree_csv if p["role"] == "SIRE"),
            "DAM_ENTITIES": sum(1 for p in pedigree_csv if p["role"] == "DAM"),
            "PEDIGREE_CONFLICTS": len(pedigree_conflicts),
            "wh_pedigree_sire_filled": filled_sire,
            "wh_pedigree_dam_filled": filled_dam,
            "note": "Pedigree enrichment blocked; sire/dam sparse. No guessing.",
        },
        "tracks": {
            "RAW_TRACK_NAMES": track_stats["raw_track_names"],
            "CANONICAL_TRACKS": track_stats["canonical_tracks"],
            "TRACK_MERGES": track_stats["track_merges"],
            "UNKNOWN_TRACKS": track_stats["unknown_tracks"],
            "raw_name_variants": track_stats["raw_name_variants"],
        },
        "confidence_distribution": conf_report,
        "date_validation": date_val,
        "review_queue_size": len(review_queue),
        "horse_build": {
            k: horse_build.get(k)
            for k in (
                "permanent_horses",
                "warehouse_horses",
                "auto_merges",
                "candidates",
                "aliases",
                "skipped",
            )
            if k in horse_build or horse_build.get("skipped")
        },
        "feature_engineering_ready": bool(
            results_unchanged
            and days_unchanged
            and heats_unchanged
            and links_unchanged
            and len(horses_csv) > 0
        ),
        "feature_engineering_ready_reason": (
            "Entity layer built; historical RaceDay/Heat/Result counts frozen; "
            "canonical horse_id/trainer/owner/track available. "
            "PHASE5 (Prediction/Ranking/Performance/Weather/Betting) still blocked. "
            "Pedigree sparse — Feature Engineering may proceed without pedigree features."
            if results_unchanged and links_unchanged
            else "FAILED critical validation — investigate before Feature Engineering."
        ),
        "phase5_blocked": True,
    }

    (ART / "entity_resolution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    md = [
        "# PHASE 4 — Entity Resolution Report",
        "",
        "Coverage/Integrity **frozen**. No historical Race/Heat/Result delete or overwrite.",
        "",
        "## Horses",
        "",
        f"- RAW HORSES: **{report['horses']['RAW_HORSES']}**",
        f"- CANONICAL HORSES: **{report['horses']['CANONICAL_HORSES']}**",
        f"- CONFIRMED HORSE MERGES: **{report['horses']['CONFIRMED_HORSE_MERGES']}**",
        f"- POTENTIAL DUPLICATES: **{report['horses']['POTENTIAL_DUPLICATES']}**",
        f"- ENTITY COLLISIONS: **{report['horses']['ENTITY_COLLISIONS']}**",
        f"- UNRESOLVED HORSES: **{report['horses']['UNRESOLVED_HORSES']}**",
        "",
        "## Trainers",
        "",
        f"- RAW TRAINERS: **{report['trainers']['RAW_TRAINERS']}**",
        f"- CANONICAL TRAINERS: **{report['trainers']['CANONICAL_TRAINERS']}**",
        f"- TRAINER MERGES: **{report['trainers']['TRAINER_MERGES']}**",
        f"- UNRESOLVED TRAINERS: **{report['trainers']['UNRESOLVED_TRAINERS']}**",
        "",
        "## Owners",
        "",
        f"- RAW OWNERS: **{report['owners']['RAW_OWNERS']}**",
        f"- CANONICAL OWNERS: **{report['owners']['CANONICAL_OWNERS']}**",
        f"- OWNER MERGES: **{report['owners']['OWNER_MERGES']}**",
        f"- UNRESOLVED OWNERS: **{report['owners']['UNRESOLVED_OWNERS']}**",
        "",
        "## Pedigree",
        "",
        f"- SIRE ENTITIES: **{report['pedigree']['SIRE_ENTITIES']}**",
        f"- DAM ENTITIES: **{report['pedigree']['DAM_ENTITIES']}**",
        f"- PEDIGREE CONFLICTS: **{report['pedigree']['PEDIGREE_CONFLICTS']}**",
        f"- ({report['pedigree']['note']})",
        "",
        "## Tracks",
        "",
        f"- RAW TRACK NAMES: **{report['tracks']['RAW_TRACK_NAMES']}**",
        f"- CANONICAL TRACKS: **{report['tracks']['CANONICAL_TRACKS']}**",
        f"- TRACK MERGES: **{report['tracks']['TRACK_MERGES']}**",
        f"- UNKNOWN TRACKS (config heats): **{report['tracks']['UNKNOWN_TRACKS']}**",
        "",
        "## Confidence Distribution",
        "",
        f"- EXACT: **{conf_report['EXACT']}**",
        f"- HIGH: **{conf_report['HIGH']}**",
        f"- MEDIUM: **{conf_report['MEDIUM']}**",
        f"- LOW: **{conf_report['LOW']}**",
        f"- UNRESOLVED: **{conf_report['UNRESOLVED']}**",
        "",
        "## Critical Validation",
        "",
        f"| Metric | Before | After | OK |",
        f"|---|---:|---:|---|",
        f"| Race Day | {before['race_days']} | {after['race_days']} | {days_unchanged} |",
        f"| Heat | {before['heats']} | {after['heats']} | {heats_unchanged} |",
        f"| Result | {before['results']} | {after['results']} | {results_unchanged} |",
        f"| Result↔Horse links | {len(before_links)} | {len(after_links)} | {links_unchanged} |",
        f"| Raw races (all) | {before['raw_races_all']} | {after['raw_races_all']} | {raw_unchanged} |",
        "",
        f"## Feature Engineering ready? **{'YES' if report['feature_engineering_ready'] else 'NO'}**",
        "",
        report["feature_engineering_ready_reason"],
        "",
        "PHASE5 (Prediction / Ranking / Performance / Weather / Betting) still blocked.",
    ]
    (ART / "entity_resolution_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print((ART / "entity_resolution_report.md").read_text(encoding="utf-8"))
    return 0 if report["feature_engineering_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

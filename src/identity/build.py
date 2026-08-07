"""Build permanent horse_ids via multi-signal clustering."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.identity.load import load_horse_profiles
from src.identity.models import (
    IdHorse,
    IdHorseAlias,
    IdHorseBuildRun,
    IdHorseLink,
    IdHorseMergeCandidate,
)
from src.identity.normalize import normalize_name, normalize_sex
from src.identity.profile import HorseProfile
from src.identity.score import (
    AUTO_MERGE_THRESHOLD,
    CANDIDATE_THRESHOLD,
    MatchResult,
    score_profiles,
)
from src.warehouse.models import WhHorse


class UnionFind:
    def __init__(self, items: list[int]) -> None:
        self.parent = {i: i for i in items}
        self.rank = {i: 0 for i in items}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def _blocking_key(p: HorseProfile) -> str:
    """
    Cheap blocking to avoid O(n²) over the full catalog.

    Uses first normalized name token + sex (when known).
    """
    name = p.normalized_name()
    token = name.split(" ")[0] if name else ""
    sex = p.normalized_sex() or "?"
    # Also block by compact name prefix for short names
    prefix = name.replace(" ", "")[:3] if name else ""
    return f"{sex}|{token}|{prefix}"


def _pair_candidates(profiles: list[HorseProfile]) -> list[tuple[HorseProfile, HorseProfile]]:
    by_block: dict[str, list[HorseProfile]] = defaultdict(list)
    by_source: dict[str, list[HorseProfile]] = defaultdict(list)
    for p in profiles:
        by_block[_blocking_key(p)].append(p)
        if p.source and p.source_horse_id:
            by_source[f"{p.source}:{p.source_horse_id}"].append(p)

    pairs: list[tuple[HorseProfile, HorseProfile]] = []
    seen: set[tuple[int, int]] = set()

    def add(a: HorseProfile, b: HorseProfile) -> None:
        i, j = sorted([a.warehouse_horse_id, b.warehouse_horse_id])
        if i == j or (i, j) in seen:
            return
        seen.add((i, j))
        pairs.append((a, b) if a.warehouse_horse_id == i else (b, a))

    for group in by_source.values():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                add(a, b)

    for group in by_block.values():
        if len(group) > 80:
            # Oversized block — compare only within same compact name
            sub: dict[str, list[HorseProfile]] = defaultdict(list)
            for p in group:
                sub[p.normalized_name()].append(p)
            for g in sub.values():
                for i, a in enumerate(g):
                    for b in g[i + 1 :]:
                        add(a, b)
            continue
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                add(a, b)

    # Cross-block: same normalized name (different sex/? blocks)
    by_name: dict[str, list[HorseProfile]] = defaultdict(list)
    for p in profiles:
        key = p.normalized_name()
        if key:
            by_name[key].append(p)
    for group in by_name.values():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                add(a, b)

    return pairs


def discover_matches(profiles: list[HorseProfile]) -> tuple[list[MatchResult], list[MatchResult]]:
    """Return (auto_merge matches, candidate matches)."""
    auto: list[MatchResult] = []
    candidates: list[MatchResult] = []
    for a, b in _pair_candidates(profiles):
        result = score_profiles(a, b)
        if result.decision == "auto_merge":
            auto.append(result)
        elif result.decision == "candidate":
            candidates.append(result)
    return auto, candidates


def build_horse_identity(
    session: Session,
    *,
    clear_existing: bool = True,
) -> dict[str, Any]:
    """
    Assign every warehouse horse a permanent horse_id.

    Auto-merges high-confidence duplicates into one permanent ID.
    Lower-confidence pairs are stored as merge candidates for review.
    """
    run = IdHorseBuildRun(status="running", params_json={"clear_existing": clear_existing})
    session.add(run)
    session.flush()

    profiles = load_horse_profiles(session)
    by_wh = {p.warehouse_horse_id: p for p in profiles}
    uf = UnionFind([p.warehouse_horse_id for p in profiles])

    auto, candidates = discover_matches(profiles)
    for m in auto:
        if m.left_id is not None and m.right_id is not None:
            uf.union(m.left_id, m.right_id)

    clusters: dict[int, list[int]] = defaultdict(list)
    for p in profiles:
        clusters[uf.find(p.warehouse_horse_id)].append(p.warehouse_horse_id)

    if clear_existing:
        session.execute(delete(IdHorseMergeCandidate))
        session.execute(delete(IdHorseAlias))
        session.execute(delete(IdHorseLink))
        session.execute(delete(IdHorse))
        session.flush()

    permanent_count = 0
    wh_to_permanent: dict[int, int] = {}

    for root, members in clusters.items():
        member_profiles = [by_wh[i] for i in members]
        # Prefer most starts, then longest name display
        member_profiles.sort(key=lambda p: (-p.starts, -len(p.name), p.warehouse_horse_id))
        primary = member_profiles[0]
        sex = primary.normalized_sex()
        birth_year = primary.effective_birth_year()
        if birth_year is None:
            for p in member_profiles[1:]:
                birth_year = p.effective_birth_year()
                if birth_year is not None:
                    break

        horse = IdHorse(
            display_name=primary.name.strip(),
            normalized_name=primary.normalized_name(),
            sex=sex,
            birth_year=birth_year,
            sire_normalized=normalize_name(primary.sire) or None,
            dam_normalized=normalize_name(primary.dam) or None,
            meta_json={
                "member_warehouse_ids": members,
                "member_names": [p.name for p in member_profiles],
                "auto_merged": len(members) > 1,
                "ages": [p.age_years for p in member_profiles if p.age_years is not None],
                "birth_years": [
                    p.effective_birth_year()
                    for p in member_profiles
                    if p.effective_birth_year() is not None
                ],
                "cities": sorted(
                    {
                        c
                        for p in member_profiles
                        for c in (p.racecourse_codes or [])
                    }
                ),
            },
            status="active",
        )
        session.add(horse)
        session.flush()
        permanent_count += 1

        aliases_seen: set[str] = set()
        for p in member_profiles:
            conf = 1.0 if p.warehouse_horse_id == primary.warehouse_horse_id else 0.95
            session.add(
                IdHorseLink(
                    horse_id=horse.horse_id,
                    warehouse_horse_id=p.warehouse_horse_id,
                    source_horse_id=p.source_horse_id,
                    confidence=conf,
                    method="auto_merge" if len(members) > 1 else "singleton",
                )
            )
            wh_to_permanent[p.warehouse_horse_id] = horse.horse_id
            norm = p.normalized_name()
            if norm and norm not in aliases_seen:
                aliases_seen.add(norm)
                session.add(
                    IdHorseAlias(
                        horse_id=horse.horse_id,
                        alias=p.name.strip(),
                        normalized_alias=norm,
                        method="observed",
                    )
                )

        # Sync warehouse canonical pointer to permanent horse_id
        for wid in members:
            wh = session.get(WhHorse, wid)
            if wh is not None:
                wh.canonical_entity_id = horse.horse_id

    # Persist open merge candidates only (auto-merges already share one horse_id).
    cand_written = 0
    seen_perm_pairs: set[tuple[int, int]] = set()
    for m in candidates:
        if m.left_id is None or m.right_id is None:
            continue
        lp = wh_to_permanent.get(m.left_id)
        rp = wh_to_permanent.get(m.right_id)
        if lp is None or rp is None or lp == rp:
            continue
        a, b = sorted([lp, rp])
        if (a, b) in seen_perm_pairs:
            continue
        seen_perm_pairs.add((a, b))
        session.add(
            IdHorseMergeCandidate(
                left_horse_id=a,
                right_horse_id=b,
                left_warehouse_id=m.left_id,
                right_warehouse_id=m.right_id,
                score=m.total_score,
                decision=m.decision,
                evidence_json=m.to_dict(),
                status="open",
            )
        )
        cand_written += 1

    auto_pairs = len(auto)
    merged_clusters = sum(1 for members in clusters.values() if len(members) > 1)

    run.status = "ok"
    run.profiles_loaded = len(profiles)
    run.permanent_ids = permanent_count
    run.auto_merges = auto_pairs
    run.candidates = cand_written
    run.finished_at = datetime.now(timezone.utc)
    session.flush()

    stats = {
        "build_run_id": run.id,
        "profiles_loaded": len(profiles),
        "permanent_horse_ids": permanent_count,
        "auto_merge_pairs": auto_pairs,
        "merged_clusters": merged_clusters,
        "open_merge_candidates": cand_written,
        "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
        "candidate_threshold": CANDIDATE_THRESHOLD,
    }
    logger.info("Horse identity build complete: {}", stats)
    return stats

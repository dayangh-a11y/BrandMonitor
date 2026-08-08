"""Build pedigree entities + relationships from harvested source records.

Rules:
- Pedigree must come from source records (never inferred).
- Normalization ≠ identity merge.
- Merge only when source_id evidence supports it (same asbdavani horse id).
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.identity.normalize import normalize_name


def load_harvest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_identity_maps(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    source_to_horse: dict[str, int] = {}
    for r in conn.execute(
        """
        SELECT source_horse_id, horse_id
        FROM id_horse_links
        WHERE source_horse_id IS NOT NULL AND TRIM(source_horse_id) != ''
        """
    ):
        source_to_horse[str(r["source_horse_id"])] = int(r["horse_id"])

    horses: dict[int, dict[str, Any]] = {}
    for r in conn.execute(
        """
        SELECT horse_id, display_name, normalized_name, sex, birth_year, status, meta_json
        FROM id_horses
        WHERE status = 'active' OR status IS NULL
        """
    ):
        meta = {}
        if r["meta_json"]:
            try:
                meta = json.loads(r["meta_json"]) if isinstance(r["meta_json"], str) else r["meta_json"]
            except (json.JSONDecodeError, TypeError):
                meta = {}
        horses[int(r["horse_id"])] = {
            "horse_id": int(r["horse_id"]),
            "display_name": r["display_name"],
            "normalized_name": r["normalized_name"],
            "sex": r["sex"],
            "birth_year": r["birth_year"],
            "meta": meta or {},
        }

    # Career starts for network stats (static descriptive)
    # Prefer warehouse results (raw_horse_starts may be empty in historical DB).
    starts: dict[int, list[dict[str, Any]]] = defaultdict(list)
    wh_map = {
        int(r["warehouse_horse_id"]): int(r["horse_id"])
        for r in conn.execute(
            "SELECT warehouse_horse_id, horse_id FROM id_horse_links"
        )
    }
    for r in conn.execute(
        """
        SELECT rr.horse_id AS wh_horse_id,
               rr.finish_position AS finish_position,
               ra.race_date AS race_date,
               ra.track AS track
        FROM wh_race_results rr
        JOIN wh_races ra ON ra.id = rr.race_id
        """
    ):
        hid = wh_map.get(int(r["wh_horse_id"]))
        if hid is None:
            continue
        starts[hid].append(
            {
                "race_date": r["race_date"],
                "finish_position": r["finish_position"],
                "track": r["track"],
            }
        )

    conn.close()
    return {
        "source_to_horse": source_to_horse,
        "horses": horses,
        "starts": starts,
        "wh_map": wh_map,
    }


def _entity_key(source_id: str | None, name: str | None, role: str) -> str | None:
    if source_id:
        return f"src:{source_id}"
    if name and name.strip():
        norm = normalize_name(name) or name.strip()
        # Name-only keys are NOT merged across roles automatically; keep role suffix
        # only when no source id — still one entity per normalized name globally
        # for the same spelling cluster, but we create separate pending entities
        # keyed by normalized name without forcing cross-role merge evidence.
        return f"name:{norm}"
    return None


def _quality(
    *,
    has_source_id: bool,
    has_conflict: bool,
    named: bool,
    external: bool,
) -> str:
    if not named:
        return "MISSING"
    if has_conflict:
        return "LOW"
    if has_source_id:
        return "HIGH"
    if external:
        return "MEDIUM"
    return "MEDIUM"


def build_entities_and_relationships(
    harvest: list[dict[str, Any]],
    identity: dict[str, Any],
) -> dict[str, Any]:
    source_to_horse: dict[str, int] = identity["source_to_horse"]
    horses: dict[int, dict[str, Any]] = identity["horses"]

    entities: dict[str, dict[str, Any]] = {}
    # horse_id -> list of parent assertions
    assertions: dict[int, list[dict[str, Any]]] = defaultdict(list)

    def upsert_entity(
        *,
        role: str,
        name: str | None,
        source_id: str | None,
        sex_hint: str | None,
        external_url: str | None,
        source: str,
    ) -> str | None:
        key = _entity_key(source_id, name, role)
        if key is None:
            return None
        ent = entities.get(key)
        if ent is None:
            horse_id = source_to_horse.get(source_id) if source_id else None
            canon = None
            birth_year = None
            sex = sex_hint
            if horse_id and horse_id in horses:
                canon = horses[horse_id]["display_name"]
                birth_year = horses[horse_id]["birth_year"]
                sex = horses[horse_id]["sex"] or sex_hint
            entities[key] = {
                "entity_id": key,
                "role_hints": {role},
                "canonical_name": canon or (name.strip() if name else None),
                "raw_names": set([name.strip()]) if name and name.strip() else set(),
                "source_ids": set([source_id]) if source_id else set(),
                "breed": None,
                "birth_year": birth_year,
                "sex": sex,
                "source": source,
                "external_urls": set([external_url]) if external_url else set(),
                "confidence": "HIGH" if source_id else "MEDIUM",
                "linked_horse_id": horse_id,
            }
        else:
            ent["role_hints"].add(role)
            if name and name.strip():
                ent["raw_names"].add(name.strip())
            if source_id:
                ent["source_ids"].add(source_id)
                ent["confidence"] = "HIGH"
            if external_url:
                ent["external_urls"].add(external_url)
            if sex_hint and not ent.get("sex"):
                ent["sex"] = sex_hint
        return key

    for row in harvest:
        sub_sid = row.get("subject_source_id")
        if not sub_sid:
            continue
        horse_id = source_to_horse.get(str(sub_sid))
        if horse_id is None:
            # Subject not in identity layer — skip relationship but still register parents
            horse_id = -1  # placeholder bucket ignored later
        source = row.get("source") or "asbdavani_pedigree_page"
        for field, role in (("sire", "SIRE"), ("dam", "DAM")):
            parent = row.get(field)
            if not parent:
                if horse_id != -1:
                    assertions[horse_id].append(
                        {
                            "horse_id": horse_id,
                            "field": field,
                            "parent_entity_id": None,
                            "parent_name": None,
                            "parent_source_id": None,
                            "source": source,
                            "source_url": row.get("source_url"),
                            "confidence": "MISSING",
                            "evidence": {"parse_status": row.get("parse_status")},
                        }
                    )
                continue
            eid = upsert_entity(
                role=role,
                name=parent.get("name"),
                source_id=parent.get("source_id"),
                sex_hint=parent.get("sex_hint"),
                external_url=parent.get("external_url"),
                source=source,
            )
            # Also register deeper ancestors as entities (network depth)
            if horse_id != -1:
                assertions[horse_id].append(
                    {
                        "horse_id": horse_id,
                        "field": field,
                        "parent_entity_id": eid,
                        "parent_name": parent.get("name"),
                        "parent_source_id": parent.get("source_id"),
                        "source": source,
                        "source_url": row.get("source_url"),
                        "confidence": "HIGH" if parent.get("source_id") else "MEDIUM",
                        "evidence": {
                            "subject_source_id": sub_sid,
                            "subject_name": row.get("subject_name"),
                            "sex_hint": parent.get("sex_hint"),
                            "external_url": parent.get("external_url"),
                            "parse_status": row.get("parse_status"),
                        },
                    }
                )
        for field, role in (
            ("sire_sire", "SIRE"),
            ("sire_dam", "DAM"),
            ("dam_sire", "SIRE"),
            ("dam_dam", "DAM"),
        ):
            anc = row.get(field)
            if not anc:
                continue
            upsert_entity(
                role=role,
                name=anc.get("name"),
                source_id=anc.get("source_id"),
                sex_hint=anc.get("sex_hint"),
                external_url=anc.get("external_url"),
                source=source,
            )

    # Resolve primary sire/dam per horse + conflicts
    relationships: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    horse_parents: dict[int, dict[str, Any]] = {}

    for horse_id, rows in assertions.items():
        if horse_id == -1:
            continue
        by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for a in rows:
            if a.get("parent_entity_id") or a.get("confidence") == "MISSING":
                by_field[a["field"]].append(a)

        resolved: dict[str, Any] = {"horse_id": horse_id, "sire_id": None, "dam_id": None}
        hmeta = horses.get(horse_id, {})
        for field in ("sire", "dam"):
            filled = [a for a in by_field.get(field, []) if a.get("parent_entity_id")]
            if not filled:
                continue
            # Group by entity id
            by_ent: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for a in filled:
                by_ent[str(a["parent_entity_id"])].append(a)
            if len(by_ent) > 1:
                ents = list(by_ent.items())
                a0, rows0 = ents[0]
                a1, rows1 = ents[1]
                conflicts.append(
                    {
                        "horse_id": horse_id,
                        "horse": hmeta.get("display_name"),
                        "field": field,
                        "value_A": rows0[0].get("parent_name"),
                        "value_B": rows1[0].get("parent_name"),
                        "source_A": rows0[0].get("source"),
                        "source_B": rows1[0].get("source"),
                        "entity_A": a0,
                        "entity_B": a1,
                        "severity": "HIGH",
                    }
                )
                # Do not auto-resolve: leave null relationship for serious conflicts
                continue
            ent_id, evid = next(iter(by_ent.items()))
            conf = evid[0]["confidence"]
            q = _quality(
                has_source_id=bool(evid[0].get("parent_source_id")),
                has_conflict=False,
                named=True,
                external=bool((evid[0].get("evidence") or {}).get("external_url")),
            )
            rel = {
                "horse_id": horse_id,
                "horse": hmeta.get("display_name"),
                "sire_id": ent_id if field == "sire" else None,
                "dam_id": ent_id if field == "dam" else None,
                "field": field,
                "parent_entity_id": ent_id,
                "parent_name": evid[0].get("parent_name"),
                "source": evid[0].get("source"),
                "confidence": conf,
                "quality": q,
                "evidence": evid[0].get("evidence"),
            }
            relationships.append(rel)
            if field == "sire":
                resolved["sire_id"] = ent_id
            else:
                resolved["dam_id"] = ent_id
        horse_parents[horse_id] = resolved

    # Serialize entities
    entity_list = []
    for key, ent in sorted(entities.items(), key=lambda kv: kv[0]):
        roles = sorted(ent["role_hints"])
        primary_role = "SIRE" if roles == ["SIRE"] else ("DAM" if roles == ["DAM"] else "MIXED")
        entity_list.append(
            {
                "entity_id": ent["entity_id"],
                "role": primary_role,
                "role_hints": roles,
                "canonical_name": ent["canonical_name"],
                "raw_names": sorted(ent["raw_names"]),
                "source_ids": sorted(ent["source_ids"]),
                "breed": ent["breed"],
                "birth_year": ent["birth_year"],
                "sex": ent["sex"],
                "source": ent["source"],
                "external_urls": sorted(ent["external_urls"]),
                "confidence": ent["confidence"],
                "linked_horse_id": ent["linked_horse_id"],
            }
        )

    return {
        "entities": entity_list,
        "relationships": relationships,
        "conflicts": conflicts,
        "horse_parents": horse_parents,
        "harvest_rows": len(harvest),
    }


def depth_for_horse(
    horse_id: int,
    horse_parents: dict[int, dict[str, Any]],
    entity_to_horse: dict[str, int],
    harvest_by_source: dict[str, dict[str, Any]],
    horse_to_source: dict[int, str],
) -> dict[str, Any]:
    """Compute pedigree depth using harvested chart fields when available."""
    sid = horse_to_source.get(horse_id)
    chart = harvest_by_source.get(sid or "", {})
    parents = horse_parents.get(horse_id, {})
    sire = chart.get("sire") or (
        {"name": None, "entity_id": parents.get("sire_id")} if parents.get("sire_id") else None
    )
    dam = chart.get("dam") or (
        {"name": None, "entity_id": parents.get("dam_id")} if parents.get("dam_id") else None
    )
    nodes = {
        "sire": chart.get("sire"),
        "dam": chart.get("dam"),
        "sire_sire": chart.get("sire_sire"),
        "sire_dam": chart.get("sire_dam"),
        "dam_sire": chart.get("dam_sire"),
        "dam_dam": chart.get("dam_dam"),
    }
    has_p = bool(nodes["sire"] or nodes["dam"])
    has_gp = any(nodes[k] for k in ("sire_sire", "sire_dam", "dam_sire", "dam_dam"))
    # Depth 3+ would require following parent charts; for static phase use chart gens only
    if has_gp:
        depth = 2
    elif has_p:
        depth = 1
    else:
        depth = 0
    return {"horse_id": horse_id, "depth": depth, "nodes": nodes}

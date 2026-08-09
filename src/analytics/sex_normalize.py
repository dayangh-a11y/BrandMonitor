"""
Sex Normalization Engine.

Normalize biological sex, describe race sex composition, estimate Sex Strength
Factor from historical mixed races only (never hardcode), and compute
Sex Adjusted Performance Rating so mares are not penalized for racing
stronger male fields.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from statistics import mean
from typing import Any, Literal

from src.analytics.metrics import (
    StartRec,
    age_years,
    clamp,
    consistency_score,
    performance_rating,
    safe_rate,
)

SexLabel = Literal["Colt", "Filly", "Stallion", "Mare", "Gelding", "Unknown"]
SexGroup = Literal["male", "female", "unknown"]

MALE_SEXES = frozenset({"Colt", "Stallion", "Gelding"})
FEMALE_SEXES = frozenset({"Filly", "Mare"})

# Age threshold (years) for Colt/Filly vs Stallion/Mare when source is binary.
COLT_FILLY_MAX_AGE = 4.999

# Map raw source labels → coarse binary / gelding before age refinement.
_RAW_SEX_MAP: dict[str, str] = {
    "نر": "male",
    "ماده": "female",
    "اخته": "gelding",
    "male": "male",
    "female": "female",
    "gelding": "gelding",
    "colt": "colt",
    "filly": "filly",
    "stallion": "stallion",
    "mare": "mare",
    "نریان": "male",
    "مادیان": "female",
}


def finish_quality(position: int) -> float:
    """Map finish position to 0..100 quality (1st best)."""
    if position <= 0:
        return 0.0
    return clamp(120.0 - 20.0 * float(position), 0.0, 100.0)


def normalize_biological_sex(
    raw_sex: str | None,
    *,
    age_years_value: float | None = None,
) -> SexLabel:
    """
    Normalize to Colt | Filly | Stallion | Mare | Gelding.

    Binary IR labels (نر/ماده) are refined by age when available.
    Missing age defaults adults: Stallion / Mare.
    """
    if not raw_sex or not str(raw_sex).strip():
        return "Unknown"
    key = str(raw_sex).strip().lower()
    # Persian stays as-is for map lookup (casefold won't help); try both
    coarse = _RAW_SEX_MAP.get(str(raw_sex).strip()) or _RAW_SEX_MAP.get(key)
    if coarse is None:
        upper = str(raw_sex).strip().upper()
        coarse = _RAW_SEX_MAP.get(upper.lower())
    if coarse is None:
        return "Unknown"

    if coarse == "gelding" or coarse == "gelding".lower():
        return "Gelding"
    if coarse == "colt":
        return "Colt"
    if coarse == "filly":
        return "Filly"
    if coarse == "stallion":
        return "Stallion"
    if coarse == "mare":
        return "Mare"

    age = age_years_value
    if coarse == "male":
        if age is not None and age < COLT_FILLY_MAX_AGE:
            return "Colt"
        return "Stallion"
    if coarse == "female":
        if age is not None and age < COLT_FILLY_MAX_AGE:
            return "Filly"
        return "Mare"
    return "Unknown"


def sex_group(label: SexLabel | str) -> SexGroup:
    if label in MALE_SEXES:
        return "male"
    if label in FEMALE_SEXES:
        return "female"
    return "unknown"


@dataclass(frozen=True, slots=True)
class RaceSexComposition:
    race_id: int
    males: int
    females: int
    unknown: int
    field_size: int
    mixed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "race_id": self.race_id,
            "males": self.males,
            "females": self.females,
            "unknown": self.unknown,
            "field_size": self.field_size,
            "mixed_race": self.mixed,
        }


@dataclass(frozen=True, slots=True)
class SexStrengthFactor:
    """
    Historical expected performance gap (quality points) males − females
    in mixed races. Positive ⇒ males outperform females on average.
    Computed only from data — never hardcoded.
    """

    factor: float
    mixed_races_used: int
    male_starts: int
    female_starts: int
    male_mean_quality: float | None
    female_mean_quality: float | None
    male_mean_finish: float | None
    female_mean_finish: float | None
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sex_strength_factor": round(self.factor, 6),
            "mixed_races_used": self.mixed_races_used,
            "male_starts": self.male_starts,
            "female_starts": self.female_starts,
            "male_mean_quality": self.male_mean_quality,
            "female_mean_quality": self.female_mean_quality,
            "male_mean_finish": self.male_mean_finish,
            "female_mean_finish": self.female_mean_finish,
            "method": self.method,
        }


@dataclass
class AnnotatedStart:
    start: StartRec
    sex: SexLabel
    group: SexGroup
    composition: RaceSexComposition
    raw_quality: float
    adjusted_quality: float
    adjusted_finish: float


@dataclass
class HorseSexMetrics:
    horse_id: int
    horse_name: str
    sex: SexLabel
    sex_group: SexGroup
    scope: str
    season_key: str

    starts: int = 0
    starts_male_only: int = 0
    starts_female_only: int = 0
    starts_mixed: int = 0

    male_only_performance: float | None = None
    female_only_performance: float | None = None
    mixed_race_performance: float | None = None

    performance_vs_males: float | None = None
    performance_vs_females: float | None = None

    avg_finish_vs_males: float | None = None
    avg_finish_vs_females: float | None = None
    win_rate_vs_males: float | None = None
    win_rate_vs_females: float | None = None
    podium_rate_vs_males: float | None = None
    podium_rate_vs_females: float | None = None

    sex_adjusted_performance_rating: float | None = None
    raw_performance_rating: float | None = None
    sex_strength_factor: float | None = None

    explain: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "horse_id": self.horse_id,
            "horse_name": self.horse_name,
            "sex": self.sex,
            "sex_group": self.sex_group,
            "scope": self.scope,
            "season_key": self.season_key,
            "starts": self.starts,
            "starts_male_only": self.starts_male_only,
            "starts_female_only": self.starts_female_only,
            "starts_mixed": self.starts_mixed,
            "male_only_performance": self.male_only_performance,
            "female_only_performance": self.female_only_performance,
            "mixed_race_performance": self.mixed_race_performance,
            "performance_vs_males": self.performance_vs_males,
            "performance_vs_females": self.performance_vs_females,
            "avg_finish_vs_males": self.avg_finish_vs_males,
            "avg_finish_vs_females": self.avg_finish_vs_females,
            "win_rate_vs_males": self.win_rate_vs_males,
            "win_rate_vs_females": self.win_rate_vs_females,
            "podium_rate_vs_males": self.podium_rate_vs_males,
            "podium_rate_vs_females": self.podium_rate_vs_females,
            "sex_adjusted_performance_rating": self.sex_adjusted_performance_rating,
            "raw_performance_rating": self.raw_performance_rating,
            "sex_strength_factor": self.sex_strength_factor,
            "explain": self.explain,
        }


def resolve_sex_for_start(start: StartRec, raw_sex: str | None) -> SexLabel:
    age = age_years(start.birthdate, start.race_date)
    return normalize_biological_sex(raw_sex, age_years_value=age)


def build_race_compositions(
    starts: list[StartRec],
    sex_by_horse_race: dict[tuple[int, int], SexLabel],
) -> dict[int, RaceSexComposition]:
    by_race: dict[int, list[SexLabel]] = defaultdict(list)
    for s in starts:
        label = sex_by_horse_race.get((s.horse_id, s.race_id), "Unknown")
        by_race[s.race_id].append(label)

    out: dict[int, RaceSexComposition] = {}
    for rid, labels in by_race.items():
        males = sum(1 for x in labels if x in MALE_SEXES)
        females = sum(1 for x in labels if x in FEMALE_SEXES)
        unknown = len(labels) - males - females
        out[rid] = RaceSexComposition(
            race_id=rid,
            males=males,
            females=females,
            unknown=unknown,
            field_size=len(labels),
            mixed=males > 0 and females > 0,
        )
    return out


def estimate_sex_strength_factor(
    starts: list[StartRec],
    sex_by_horse_race: dict[tuple[int, int], SexLabel],
    compositions: dict[int, RaceSexComposition],
    *,
    min_mixed_races: int = 5,
) -> SexStrengthFactor:
    """
    Estimate expected quality gap (males − females) from historical mixed races.

    Uses finish-quality means across all mixed-race starts. No hardcoded coeffs.
    """
    male_q: list[float] = []
    female_q: list[float] = []
    male_f: list[float] = []
    female_f: list[float] = []
    mixed_ids: set[int] = set()

    for s in starts:
        comp = compositions.get(s.race_id)
        if comp is None or not comp.mixed:
            continue
        if comp.males < 1 or comp.females < 1:
            continue
        label = sex_by_horse_race.get((s.horse_id, s.race_id), "Unknown")
        g = sex_group(label)
        q = finish_quality(s.finish)
        if g == "male":
            male_q.append(q)
            male_f.append(float(s.finish))
            mixed_ids.add(s.race_id)
        elif g == "female":
            female_q.append(q)
            female_f.append(float(s.finish))
            mixed_ids.add(s.race_id)

    if len(mixed_ids) < min_mixed_races or not male_q or not female_q:
        # Insufficient mixed history — neutral factor (no adjustment)
        return SexStrengthFactor(
            factor=0.0,
            mixed_races_used=len(mixed_ids),
            male_starts=len(male_q),
            female_starts=len(female_q),
            male_mean_quality=mean(male_q) if male_q else None,
            female_mean_quality=mean(female_q) if female_q else None,
            male_mean_finish=mean(male_f) if male_f else None,
            female_mean_finish=mean(female_f) if female_f else None,
            method="insufficient_mixed_history_neutral",
        )

    mq = mean(male_q)
    fq = mean(female_q)
    factor = mq - fq  # positive ⇒ males stronger historically
    return SexStrengthFactor(
        factor=float(factor),
        mixed_races_used=len(mixed_ids),
        male_starts=len(male_q),
        female_starts=len(female_q),
        male_mean_quality=round(mq, 6),
        female_mean_quality=round(fq, 6),
        male_mean_finish=round(mean(male_f), 6),
        female_mean_finish=round(mean(female_f), 6),
        method="mixed_race_mean_quality_gap",
    )


def adjust_start_quality(
    *,
    raw_quality: float,
    group: SexGroup,
    composition: RaceSexComposition,
    ssf: SexStrengthFactor,
) -> tuple[float, float]:
    """
    Return (adjusted_quality, adjusted_finish_proxy).

    Females facing males receive a credit equal to
    ``SSF * (males / field_size)`` so they are not penalized for stronger
    male fields. Males are not boosted for racing females.
    """
    adj = raw_quality
    if (
        group == "female"
        and composition.males > 0
        and composition.field_size > 0
        and ssf.factor != 0.0
    ):
        male_share = composition.males / composition.field_size
        adj = clamp(raw_quality + ssf.factor * male_share, 0.0, 100.0)
    # Invert quality ≈ finish proxy for reporting (1≈100, softer mapping)
    # finish_proxy such that quality = clamp(120 - 20*f) ⇒ f = (120-q)/20
    finish_proxy = max(1.0, (120.0 - adj) / 20.0)
    return round(adj, 4), round(finish_proxy, 4)


def annotate_starts(
    starts: list[StartRec],
    raw_sex_by_horse: dict[int, str | None],
    ssf: SexStrengthFactor,
) -> tuple[list[AnnotatedStart], dict[int, RaceSexComposition], dict[tuple[int, int], SexLabel]]:
    sex_by_horse_race: dict[tuple[int, int], SexLabel] = {}
    for s in starts:
        sex_by_horse_race[(s.horse_id, s.race_id)] = resolve_sex_for_start(
            s, raw_sex_by_horse.get(s.horse_id)
        )
    compositions = build_race_compositions(starts, sex_by_horse_race)
    annotated: list[AnnotatedStart] = []
    for s in starts:
        label = sex_by_horse_race[(s.horse_id, s.race_id)]
        g = sex_group(label)
        comp = compositions[s.race_id]
        raw_q = finish_quality(s.finish)
        adj_q, adj_f = adjust_start_quality(
            raw_quality=raw_q, group=g, composition=comp, ssf=ssf
        )
        annotated.append(
            AnnotatedStart(
                start=s,
                sex=label,
                group=g,
                composition=comp,
                raw_quality=raw_q,
                adjusted_quality=adj_q,
                adjusted_finish=adj_f,
            )
        )
    return annotated, compositions, sex_by_horse_race


def _bucket_performance(annotated: list[AnnotatedStart]) -> float | None:
    if not annotated:
        return None
    finishes = [a.start.finish for a in annotated]
    wins = sum(1 for f in finishes if f == 1)
    seconds = sum(1 for f in finishes if f == 2)
    thirds = sum(1 for f in finishes if f == 3)
    places = wins + seconds + thirds
    n = len(finishes)
    avg_fin = mean(finishes)
    cons = consistency_score(finishes)
    # Use adjusted qualities mapped into a PR-like score
    adj_mean = mean(a.adjusted_quality for a in annotated)
    raw_pr = performance_rating(
        starts=n,
        wins=wins,
        seconds=seconds,
        thirds=thirds,
        place_rate=safe_rate(places, n),
        avg_finish=avg_fin,
        consistency=cons,
        include_earnings=False,
    )
    if raw_pr is None:
        return round(adj_mean, 4)
    # Blend observed PR with adjusted quality so sex credit flows through
    return round(0.65 * raw_pr + 0.35 * adj_mean, 4)


def _vs_stats(annotated: list[AnnotatedStart]) -> dict[str, float | None]:
    if not annotated:
        return {
            "performance": None,
            "avg_finish": None,
            "win_rate": None,
            "podium_rate": None,
        }
    finishes = [a.start.finish for a in annotated]
    n = len(finishes)
    wins = sum(1 for f in finishes if f == 1)
    podium = sum(1 for f in finishes if f <= 3)
    return {
        "performance": _bucket_performance(annotated),
        "avg_finish": round(mean(finishes), 4),
        "win_rate": safe_rate(wins, n),
        "podium_rate": safe_rate(podium, n),
    }


def compute_horse_sex_metrics(
    horse_id: int,
    annotated: list[AnnotatedStart],
    *,
    scope: str,
    season_key: str,
    ssf: SexStrengthFactor,
    raw_pr: float | None = None,
) -> HorseSexMetrics | None:
    if not annotated:
        return None
    annotated = sorted(
        annotated,
        key=lambda a: a.start.race_date or date.min,
        reverse=True,
    )
    sex = annotated[0].sex
    group = annotated[0].group
    name = annotated[0].start.horse_name

    male_only = [a for a in annotated if a.composition.males > 0 and a.composition.females == 0]
    female_only = [a for a in annotated if a.composition.females > 0 and a.composition.males == 0]
    mixed = [a for a in annotated if a.composition.mixed]

    # vs males: races containing at least one male opponent
    vs_males: list[AnnotatedStart] = []
    vs_females: list[AnnotatedStart] = []
    for a in annotated:
        males = a.composition.males
        females = a.composition.females
        # Exclude self from opponent counts
        if a.group == "male":
            male_opponents = males - 1
            female_opponents = females
        elif a.group == "female":
            male_opponents = males
            female_opponents = females - 1
        else:
            male_opponents = males
            female_opponents = females
        if male_opponents > 0:
            vs_males.append(a)
        if female_opponents > 0:
            vs_females.append(a)

    vs_m = _vs_stats(vs_males)
    vs_f = _vs_stats(vs_females)

    # Sex Adjusted PR from all starts using adjusted qualities
    finishes = [a.start.finish for a in annotated]
    wins = sum(1 for f in finishes if f == 1)
    seconds = sum(1 for f in finishes if f == 2)
    thirds = sum(1 for f in finishes if f == 3)
    places = wins + seconds + thirds
    n = len(finishes)
    avg_fin = mean(finishes)
    cons = consistency_score(finishes)
    base_pr = performance_rating(
        starts=n,
        wins=wins,
        seconds=seconds,
        thirds=thirds,
        place_rate=safe_rate(places, n),
        avg_finish=avg_fin,
        consistency=cons,
        include_earnings=False,
    )
    adj_mean = mean(a.adjusted_quality for a in annotated)
    raw_mean = mean(a.raw_quality for a in annotated)
    # Credit = lift from sex adjustment; applied on top of raw PR
    credit = adj_mean - raw_mean
    if base_pr is not None:
        sex_adj_pr = round(clamp(base_pr + credit), 4)
    else:
        sex_adj_pr = round(adj_mean, 4)

    return HorseSexMetrics(
        horse_id=horse_id,
        horse_name=name,
        sex=sex,
        sex_group=group,
        scope=scope,
        season_key=season_key,
        starts=n,
        starts_male_only=len(male_only),
        starts_female_only=len(female_only),
        starts_mixed=len(mixed),
        male_only_performance=_bucket_performance(male_only),
        female_only_performance=_bucket_performance(female_only),
        mixed_race_performance=_bucket_performance(mixed),
        performance_vs_males=vs_m["performance"],
        performance_vs_females=vs_f["performance"],
        avg_finish_vs_males=vs_m["avg_finish"],
        avg_finish_vs_females=vs_f["avg_finish"],
        win_rate_vs_males=vs_m["win_rate"],
        win_rate_vs_females=vs_f["win_rate"],
        podium_rate_vs_males=vs_m["podium_rate"],
        podium_rate_vs_females=vs_f["podium_rate"],
        sex_adjusted_performance_rating=sex_adj_pr,
        raw_performance_rating=raw_pr if raw_pr is not None else base_pr,
        sex_strength_factor=ssf.factor,
        explain={
            "sex_strength_factor": ssf.to_dict(),
            "adjusted_quality_mean": round(adj_mean, 4),
            "raw_quality_mean": round(raw_mean, 4),
            "sex_credit": round(credit, 4),
            "rule": (
                "Females facing males receive historical SSF * male_share credit; "
                "Sex Adjusted PR = raw PR + credit"
            ),
        },
    )


def compute_all_sex_metrics(
    starts: list[StartRec],
    raw_sex_by_horse: dict[int, str | None],
    *,
    scope: str,
    season_key: str,
    ssf: SexStrengthFactor | None = None,
) -> tuple[SexStrengthFactor, dict[int, RaceSexComposition], list[HorseSexMetrics]]:
    """
    Full pipeline for a scope: estimate SSF (if not provided), annotate, per-horse metrics.
    When ``ssf`` is None, estimate from the provided starts (usually full career history).
    """
    # Always need compositions / sexes first for SSF estimation
    sex_by_horse_race: dict[tuple[int, int], SexLabel] = {}
    for s in starts:
        sex_by_horse_race[(s.horse_id, s.race_id)] = resolve_sex_for_start(
            s, raw_sex_by_horse.get(s.horse_id)
        )
    compositions = build_race_compositions(starts, sex_by_horse_race)
    if ssf is None:
        ssf = estimate_sex_strength_factor(starts, sex_by_horse_race, compositions)

    annotated, compositions, _ = annotate_starts(starts, raw_sex_by_horse, ssf)
    by_horse: dict[int, list[AnnotatedStart]] = defaultdict(list)
    for a in annotated:
        by_horse[a.start.horse_id].append(a)

    metrics: list[HorseSexMetrics] = []
    for hid, rows in by_horse.items():
        m = compute_horse_sex_metrics(
            hid, rows, scope=scope, season_key=season_key, ssf=ssf
        )
        if m is not None:
            metrics.append(m)
    return ssf, compositions, metrics

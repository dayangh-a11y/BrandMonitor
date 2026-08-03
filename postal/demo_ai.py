"""Deterministic AI insight / compare / search for the Postal Intelligence demo.

Never invents facts. Every claim is grounded in the loaded snapshot.
Insufficient evidence is stated explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from postal.demo_data import IntelDemoData, utcnow


DIM_LABELS = {
    "customer_satisfaction": "Customer satisfaction",
    "delivery_speed": "Delivery speed",
    "service_coverage": "Service coverage",
    "pricing": "Pricing",
    "service_variety": "Service variety",
    "transparency": "Transparency",
    "complaint_rate": "Complaint resilience",
    "branch_quality": "Branch quality",
}


def _conf_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


INSUFFICIENT_PHRASE = "I don't have enough data."


def _insight(
    text: str,
    *,
    sources: list[str],
    confidence: float,
    last_updated: str,
    evidence: list[str] | None = None,
    insufficient: bool = False,
) -> dict[str, Any]:
    body = (text or "").strip()
    if insufficient and INSUFFICIENT_PHRASE not in body:
        body = f"{body} {INSUFFICIENT_PHRASE}".strip() if body else INSUFFICIENT_PHRASE
    return {
        "text": body,
        "data_sources": sources,
        "confidence_level": _conf_label(confidence),
        "confidence_score": round(float(confidence), 3),
        "last_updated": last_updated,
        "evidence": evidence or [],
        "insufficient_evidence": insufficient,
    }


@dataclass
class DemoAI:
    data: IntelDemoData

    def _meta_time(self) -> str:
        snap = self.data.snapshot()
        return snap["meta"]["built_at"]

    def company_executive_summary(self, company: dict[str, Any]) -> dict[str, Any]:
        n = int(company.get("review_count") or 0)
        conf = float(company.get("confidence", {}).get("overall_dataset_confidence") or 0)
        sources = [
            "pi_company_scores (postal_score_v1)",
            "pi_reviews",
            "pi_branches / pi_branch_intelligence",
            "pi_official_profiles",
        ]
        updated = company.get("score_calculated_at") or self._meta_time()

        if company.get("score") is None:
            return _insight(
                f"Insufficient evidence to summarize {company['name']}: no postal_score_v1 "
                "has been calculated for this company in the current warehouse.",
                sources=sources,
                confidence=0.05,
                last_updated=updated,
                insufficient=True,
            )

        if n < 30:
            return _insight(
                f"{company['name']} currently ranks #{company['rank']} with postal_score_v1 "
                f"{company['score']:.2f}/100, but only {n} analyzed reviews are available. "
                "Evidence is insufficient for a reliable executive narrative; treat the score "
                "as provisional until review coverage improves.",
                sources=sources,
                confidence=min(conf, 0.35),
                last_updated=updated,
                evidence=[
                    f"rank={company['rank']}",
                    f"score={company['score']}",
                    f"reviews={n}",
                    f"branches={company.get('branch_count')}",
                ],
                insufficient=True,
            )

        dims = company.get("dimensions") or {}
        ranked_dims = sorted(
            ((k, float((v or {}).get("score") or 0)) for k, v in dims.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        top = ranked_dims[:2]
        bottom = list(reversed(ranked_dims[-2:])) if len(ranked_dims) >= 2 else []
        sentiments = company.get("sentiments") or {}
        pos = int(sentiments.get("Positive") or 0)
        neg = int(sentiments.get("Negative") or 0)
        neu = int(sentiments.get("Neutral") or 0)
        complaints = company.get("complaints") or {}
        top_complaint = None
        if complaints:
            top_complaint = max(complaints.items(), key=lambda x: int(x[1] or 0))

        strength_bits = ", ".join(
            f"{DIM_LABELS.get(k, k)} ({v:.1f})" for k, v in top
        )
        weakness_bits = ", ".join(
            f"{DIM_LABELS.get(k, k)} ({v:.1f})" for k, v in bottom
        )
        complaint_bit = (
            f" Leading negative theme among labeled complaints: {top_complaint[0]} "
            f"({top_complaint[1]} reviews)."
            if top_complaint and top_complaint[0] and top_complaint[0] != "other"
            else (
                f" {top_complaint[1]} negative reviews lack a specific category label."
                if top_complaint
                else ""
            )
        )

        text = (
            f"{company['name']} ranks #{company['rank']} of "
            f"{len(self.data.snapshot()['companies'])} scored carriers with "
            f"postal_score_v1 = {company['score']:.2f}/100. "
            f"Observed coverage: {company.get('branch_count', 0)} branches across "
            f"{company.get('province_count', 0)} provinces; {n} analyzed reviews "
            f"(avg rating {company.get('avg_rating', 0):.2f}/5; sentiment "
            f"{pos} positive / {neu} neutral / {neg} negative). "
            f"Strongest scored dimensions: {strength_bits}. "
            f"Weakest scored dimensions: {weakness_bits}.{complaint_bit} "
            f"Dataset confidence for this company is {_conf_label(conf)} "
            f"({conf:.0%})."
        )
        return _insight(
            text,
            sources=sources,
            confidence=conf,
            last_updated=updated,
            evidence=[
                f"score={company['score']}",
                f"rank={company['rank']}",
                f"reviews={n}",
                f"avg_rating={company.get('avg_rating')}",
                f"top_dims={strength_bits}",
                f"weak_dims={weakness_bits}",
            ],
        )

    def company_strengths_weaknesses(
        self, company: dict[str, Any]
    ) -> dict[str, list[dict[str, Any]]]:
        dims = company.get("dimensions") or {}
        weights = company.get("weights") or {}
        conf = float(company.get("confidence", {}).get("overall_dataset_confidence") or 0)
        updated = company.get("score_calculated_at") or self._meta_time()
        sources = ["pi_company_scores.dimensions", "postal_score_v1 weights"]

        if not dims:
            empty = _insight(
                "Insufficient evidence: dimension breakdown is not available for this company.",
                sources=sources,
                confidence=0.05,
                last_updated=updated,
                insufficient=True,
            )
            return {"strengths": [empty], "weaknesses": [empty]}

        ranked = sorted(
            (
                (
                    k,
                    float((v or {}).get("score") or 0),
                    float(weights.get(k) or 0),
                    (v or {}).get("explanation") or "",
                )
                for k, v in dims.items()
            ),
            key=lambda x: x[1],
            reverse=True,
        )
        strengths = []
        for k, score, w, expl in ranked[:3]:
            if score < 55:
                strengths.append(
                    _insight(
                        f"No strong dimension above 55 for {company['name']}; "
                        f"highest observed is {DIM_LABELS.get(k, k)} at {score:.1f}.",
                        sources=sources,
                        confidence=conf,
                        last_updated=updated,
                        evidence=[f"{k}={score}"],
                        insufficient=score < 40,
                    )
                )
                break
            strengths.append(
                _insight(
                    f"{DIM_LABELS.get(k, k)} scores {score:.1f}/100 "
                    f"(weight {w:.0%} of postal_score_v1). {expl}",
                    sources=sources + [f"dimension:{k}"],
                    confidence=conf,
                    last_updated=updated,
                    evidence=[f"{k}={score}", f"weight={w}"],
                )
            )

        weaknesses = []
        for k, score, w, expl in ranked[-3:][::-1]:
            weaknesses.append(
                _insight(
                    f"{DIM_LABELS.get(k, k)} scores {score:.1f}/100 "
                    f"(weight {w:.0%}). {expl}",
                    sources=sources + [f"dimension:{k}"],
                    confidence=conf,
                    last_updated=updated,
                    evidence=[f"{k}={score}", f"weight={w}"],
                )
            )
        return {"strengths": strengths, "weaknesses": weaknesses}

    def company_insights(self, slug: str) -> dict[str, Any]:
        company = self.data.company_by_slug(slug)
        if not company:
            return {
                "error": "company_not_found",
                "summary": _insight(
                    f"No company matching '{slug}' in the postal intelligence warehouse.",
                    sources=["pi_companies"],
                    confidence=1.0,
                    last_updated=self._meta_time(),
                    insufficient=True,
                ),
            }
        sw = self.company_strengths_weaknesses(company)
        return {
            "company": {
                "id": company["id"],
                "slug": company["slug"],
                "name": company["name"],
                "rank": company["rank"],
                "score": company["score"],
            },
            "executive_summary": self.company_executive_summary(company),
            "strengths": sw["strengths"],
            "weaknesses": sw["weaknesses"],
            "market_context": self._market_context(company),
        }

    def _market_context(self, company: dict[str, Any]) -> dict[str, Any]:
        companies = self.data.snapshot()["companies"]
        if not companies:
            return _insight(
                "Insufficient evidence: company ranking table is empty.",
                sources=["pi_company_scores"],
                confidence=0.05,
                last_updated=self._meta_time(),
                insufficient=True,
            )
        leader = companies[0]
        conf = min(
            float(company.get("confidence", {}).get("overall_dataset_confidence") or 0),
            float(leader.get("confidence", {}).get("overall_dataset_confidence") or 0),
        )
        if company["id"] == leader["id"]:
            text = (
                f"{company['name']} leads the current scored set with "
                f"{company['score']:.2f}. Next ranked carrier is "
                f"{companies[1]['name']} at {companies[1]['score']:.2f} "
                f"(gap {float(company['score']) - float(companies[1]['score']):.2f} pts)."
                if len(companies) > 1
                else f"{company['name']} is the only scored carrier in the warehouse."
            )
        else:
            gap = float(leader["score"]) - float(company["score"] or 0)
            text = (
                f"{company['name']} trails the current leader {leader['name']} by "
                f"{gap:.2f} postal_score_v1 points "
                f"({company['score']:.2f} vs {leader['score']:.2f})."
            )
        return _insight(
            text,
            sources=["pi_company_scores ranking"],
            confidence=conf,
            last_updated=self._meta_time(),
            evidence=[
                f"leader={leader['name']}:{leader['score']}",
                f"subject={company['name']}:{company['score']}",
            ],
        )

    def home_insights(self) -> list[dict[str, Any]]:
        snap = self.data.snapshot()
        companies = snap["companies"]
        out: list[dict[str, Any]] = []
        if not companies:
            return [
                _insight(
                    "Insufficient evidence: no scored companies in the warehouse.",
                    sources=["pi_company_scores"],
                    confidence=0.05,
                    last_updated=self._meta_time(),
                    insufficient=True,
                )
            ]

        leader = companies[0]
        out.append(
            _insight(
                f"Market leader by postal_score_v1 is {leader['name']} "
                f"({leader['score']:.2f}), ahead of "
                + (
                    f"{companies[1]['name']} ({companies[1]['score']:.2f})."
                    if len(companies) > 1
                    else "no other scored peers."
                ),
                sources=["pi_company_scores"],
                confidence=float(
                    leader.get("confidence", {}).get("overall_dataset_confidence") or 0
                ),
                last_updated=self._meta_time(),
                evidence=[f"{c['name']}={c['score']}" for c in companies[:3]],
            )
        )

        # Best CSI among companies with enough reviews
        eligible = [
            c
            for c in companies
            if int(c.get("review_count") or 0) >= 30
            and "customer_satisfaction" in (c.get("dimensions") or {})
        ]
        if not eligible:
            out.append(
                _insight(
                    "Insufficient evidence to name a satisfaction leader: "
                    "fewer than 30 analyzed reviews for every carrier.",
                    sources=["pi_reviews", "dimension:customer_satisfaction"],
                    confidence=0.2,
                    last_updated=self._meta_time(),
                    insufficient=True,
                )
            )
        else:
            best = max(
                eligible,
                key=lambda c: float(
                    c["dimensions"]["customer_satisfaction"].get("score") or 0
                ),
            )
            csi = best["dimensions"]["customer_satisfaction"]
            out.append(
                _insight(
                    f"Among carriers with ≥30 reviews, {best['name']} has the highest "
                    f"customer_satisfaction dimension ({float(csi.get('score') or 0):.1f}/100; "
                    f"CSI={csi.get('inputs', {}).get('csi')}, n={csi.get('inputs', {}).get('n')}).",
                    sources=["pi_reviews", "postal_score_v1 customer_satisfaction"],
                    confidence=float(
                        best.get("confidence", {}).get("overall_dataset_confidence") or 0
                    ),
                    last_updated=self._meta_time(),
                    evidence=[
                        f"{c['name']}={c['dimensions']['customer_satisfaction'].get('score')}"
                        for c in eligible
                    ],
                )
            )

        # Coverage leader by observed branches
        cov = max(companies, key=lambda c: int(c.get("branch_count") or 0))
        out.append(
            _insight(
                f"Broadest observed branch footprint in this warehouse: {cov['name']} "
                f"with {cov['branch_count']} branches across {cov['province_count']} provinces "
                f"and {cov['review_count']} reviews.",
                sources=["pi_branches", "pi_reviews"],
                confidence=float(
                    cov.get("confidence", {}).get("overall_dataset_confidence") or 0
                ),
                last_updated=self._meta_time(),
                evidence=[
                    f"branches={cov['branch_count']}",
                    f"provinces={cov['province_count']}",
                    f"reviews={cov['review_count']}",
                ],
            )
        )

        low_conf = [c for c in companies if float(c.get("confidence", {}).get("overall_dataset_confidence") or 0) < 0.45]
        if low_conf:
            names = ", ".join(c["name"] for c in low_conf)
            out.append(
                _insight(
                    f"Low dataset confidence (<45%) for: {names}. Rankings involving these "
                    "carriers should be treated cautiously until review and branch coverage improve.",
                    sources=["metric_confidence_bundle"],
                    confidence=0.9,
                    last_updated=self._meta_time(),
                    evidence=[
                        f"{c['name']}={c['confidence']['overall_dataset_confidence']}"
                        for c in low_conf
                    ],
                )
            )
        return out

    def compare(self, slug_a: str, slug_b: str) -> dict[str, Any]:
        a = self.data.company_by_slug(slug_a)
        b = self.data.company_by_slug(slug_b)
        updated = self._meta_time()
        if not a or not b:
            missing = slug_a if not a else slug_b
            return {
                "error": "company_not_found",
                "summary": _insight(
                    f"Cannot compare: company '{missing}' not found in warehouse.",
                    sources=["pi_companies"],
                    confidence=1.0,
                    last_updated=updated,
                    insufficient=True,
                ),
            }
        if a["id"] == b["id"]:
            return {
                "error": "same_company",
                "summary": _insight(
                    "Select two different companies to compare.",
                    sources=["ui"],
                    confidence=1.0,
                    last_updated=updated,
                    insufficient=True,
                ),
            }

        conf = min(
            float(a.get("confidence", {}).get("overall_dataset_confidence") or 0),
            float(b.get("confidence", {}).get("overall_dataset_confidence") or 0),
        )
        sources = [
            "pi_company_scores (postal_score_v1)",
            "pi_reviews",
            "pi_branches",
            "pi_official_profiles",
        ]

        score_gap = float(a["score"] or 0) - float(b["score"] or 0)
        leader, trailer = (a, b) if score_gap >= 0 else (b, a)
        abs_gap = abs(score_gap)

        dim_deltas = []
        for key in DIM_LABELS:
            sa = float(((a.get("dimensions") or {}).get(key) or {}).get("score") or 0)
            sb = float(((b.get("dimensions") or {}).get(key) or {}).get("score") or 0)
            wa = float((a.get("weights") or {}).get(key) or 0)
            dim_deltas.append(
                {
                    "dimension": key,
                    "label": DIM_LABELS[key],
                    "a": sa,
                    "b": sb,
                    "delta": round(sa - sb, 2),
                    "weighted_delta": round((sa - sb) * wa, 2),
                    "weight": wa,
                }
            )
        dim_deltas.sort(key=lambda d: abs(d["weighted_delta"]), reverse=True)

        evidence_lines = []
        for d in dim_deltas[:4]:
            better = a["name"] if d["delta"] > 0 else b["name"]
            evidence_lines.append(
                f"{d['label']}: {a['name']} {d['a']:.1f} vs {b['name']} {d['b']:.1f} "
                f"(Δ {d['delta']:+.1f}; weighted ≈ {d['weighted_delta']:+.2f})"
                + (f" — favors {better}" if d["delta"] else "")
            )

        # Sample-size caveat
        caveat = ""
        if int(a["review_count"]) < 30 or int(b["review_count"]) < 30:
            weak = []
            if int(a["review_count"]) < 30:
                weak.append(f"{a['name']} (n={a['review_count']})")
            if int(b["review_count"]) < 30:
                weak.append(f"{b['name']} (n={b['review_count']})")
            caveat = (
                " Evidence warning: review samples below 30 for "
                + ", ".join(weak)
                + "; satisfaction and complaint comparisons are provisional."
            )
            conf = min(conf, 0.4)

        summary_text = (
            f"{leader['name']} ranks higher than {trailer['name']} "
            f"(#{leader['rank']} at {leader['score']:.2f} vs #{trailer['rank']} at "
            f"{trailer['score']:.2f}; gap {abs_gap:.2f} postal_score_v1 points). "
            f"Largest weighted dimension differences: "
            + "; ".join(evidence_lines[:3])
            + "."
            + caveat
        )

        bullets = []
        bullets.append(
            _insight(
                summary_text,
                sources=sources,
                confidence=conf,
                last_updated=updated,
                evidence=[
                    f"{a['name']} score={a['score']} rank={a['rank']} reviews={a['review_count']}",
                    f"{b['name']} score={b['score']} rank={b['rank']} reviews={b['review_count']}",
                    *evidence_lines,
                ],
                insufficient=bool(caveat),
            )
        )

        # Coverage comparison (observed)
        bullets.append(
            _insight(
                f"Observed warehouse coverage — {a['name']}: {a['branch_count']} branches / "
                f"{a['province_count']} provinces / {a['review_count']} reviews; "
                f"{b['name']}: {b['branch_count']} branches / {b['province_count']} provinces / "
                f"{b['review_count']} reviews. "
                "Official claimed coverage may differ from observed Maps-derived counts.",
                sources=["pi_branches", "pi_reviews", "pi_official_profiles"],
                confidence=conf,
                last_updated=updated,
                evidence=[
                    f"{a['name']} branches={a['branch_count']}",
                    f"{b['name']} branches={b['branch_count']}",
                ],
            )
        )

        # CSI if both eligible
        if int(a["review_count"]) >= 30 and int(b["review_count"]) >= 30:
            csi_a = ((a.get("dimensions") or {}).get("customer_satisfaction") or {})
            csi_b = ((b.get("dimensions") or {}).get("customer_satisfaction") or {})
            bullets.append(
                _insight(
                    f"Customer satisfaction dimension: {a['name']} "
                    f"{float(csi_a.get('score') or 0):.1f} vs {b['name']} "
                    f"{float(csi_b.get('score') or 0):.1f} "
                    f"(CSI {csi_a.get('inputs', {}).get('csi')} vs "
                    f"{csi_b.get('inputs', {}).get('csi')}).",
                    sources=["pi_reviews", "customer_satisfaction dimension"],
                    confidence=conf,
                    last_updated=updated,
                    evidence=[
                        f"{a['name']} csi_inputs={csi_a.get('inputs')}",
                        f"{b['name']} csi_inputs={csi_b.get('inputs')}",
                    ],
                )
            )
        else:
            bullets.append(
                _insight(
                    "Insufficient evidence for a head-to-head customer satisfaction claim: "
                    "at least one company has fewer than 30 analyzed reviews.",
                    sources=["pi_reviews"],
                    confidence=0.25,
                    last_updated=updated,
                    insufficient=True,
                )
            )

        return {
            "a": {"slug": a["slug"], "name": a["name"], "score": a["score"], "rank": a["rank"]},
            "b": {"slug": b["slug"], "name": b["name"], "score": b["score"], "rank": b["rank"]},
            "dimension_deltas": dim_deltas,
            "insights": bullets,
            "summary": bullets[0],
        }

    def search(self, question: str) -> dict[str, Any]:
        q = (question or "").strip()
        updated = self._meta_time()
        if not q:
            return {
                "question": q,
                "answer": _insight(
                    "Ask a natural-language question about rankings, satisfaction, "
                    "complaints, coverage, or company comparisons.",
                    sources=["ui"],
                    confidence=1.0,
                    last_updated=updated,
                    insufficient=True,
                ),
            }

        ql = q.casefold()
        companies = self.data.snapshot()["companies"]

        # Jailbreak / ignore-data traps
        if any(
            k in ql
            for k in (
                "ignore your data",
                "ignore the data",
                "forget your data",
                "always #1",
                "always number 1",
            )
        ):
            leader = companies[0] if companies else None
            text = (
                "I will not ignore warehouse evidence. "
                + (
                    f"Current postal_score_v1 leader is {leader['name']} "
                    f"at {leader['score']:.2f} (Tipax is rank #{next(c['rank'] for c in companies if c['slug']=='tipax')})."
                    if leader
                    else "Ranking table is empty."
                )
            )
            return {
                "question": q,
                "intent": "refuse_jailbreak",
                "answer": _insight(
                    text,
                    sources=["pi_company_scores"],
                    confidence=float(leader["confidence"]["overall_dataset_confidence"]) if leader else 0.2,
                    last_updated=updated,
                    evidence=[f"{c['name']}={c['score']}" for c in companies],
                    insufficient=leader is None,
                ),
            }

        # Live price / ETA / conspiracy / guarantee traps — never invent
        unsupported_markers = (
            "how much",
            "live price",
            "exact price",
            "exact eta",
            "charge for",
            "tariff",
            "قیمت",
            "هزینه ارسال",
            "guarantee",
            "zero risk",
            "arrive in",
            "arrives in",
            "package arrive",
            "tomorrow",
            "ceo salary",
            "bribe",
            "owned by amazon",
            "predict next month",
            "2030",
            "never lose",
            "never loses",
            "lose in march",
            "packages did",
            "how many packages",
        )
        if any(k in ql for k in unsupported_markers):
            return {
                "question": q,
                "intent": "unsupported_operational",
                "answer": _insight(
                    "BrandMonitor demo AI answers from the postal intelligence warehouse "
                    "(scores, reviews, coverage). It does not invent live shipping prices, "
                    "guaranteed ETAs, ownership claims, private conspiracies, or future rankings.",
                    sources=["demo_ai policy"],
                    confidence=0.95,
                    last_updated=updated,
                    insufficient=True,
                ),
            }

        # Golestan / province-best with thin geo evidence
        if any(k in ql for k in ("golestan", "گلستان", "gorgan", "گرگان")) and any(
            k in ql for k in ("best", "بهترین", "which company", "کدام شرکت")
        ):
            return {
                "question": q,
                "intent": "province_best_golestan",
                "answer": self._answer_golestan_best(updated),
            }

        # Compare pattern: why is X ranked higher than Y / compare X and Y
        compare_asked = any(
            k in ql
            for k in (
                "why",
                "higher",
                "better",
                "vs",
                "versus",
                "compare",
                "difference",
                "ranked",
                "چرا",
                "بیشتر",
                "امتیاز",
                "بهتر",
            )
        )
        pair = self._extract_company_pair(ql, companies)
        if compare_asked:
            # Fake / unknown peer in a compare question
            known_hits = self._extract_all_companies(ql, companies)
            if "compare" in ql or "vs" in ql or "versus" in ql:
                # Tipax vs Tipax
                if len(known_hits) == 1 and known_hits[0]["name"].casefold() in ql and ql.count(known_hits[0]["name"].casefold()) >= 2:
                    return {
                        "question": q,
                        "intent": "compare",
                        "answer": _insight(
                            "Select two different companies to compare.",
                            sources=["ui"],
                            confidence=1.0,
                            last_updated=updated,
                            insufficient=True,
                        ),
                    }
                if len(known_hits) == 1 and any(
                    tok in ql
                    for tok in ("fakecourier", "fake", "xyz", "acme", "unknown")
                ):
                    return {
                        "question": q,
                        "intent": "compare",
                        "answer": _insight(
                            f"Cannot compare: peer company in the question is not in the "
                            f"postal intelligence warehouse (known hit: {known_hits[0]['name']}).",
                            sources=["pi_companies"],
                            confidence=1.0,
                            last_updated=updated,
                            insufficient=True,
                        ),
                    }
                if len(known_hits) == 0:
                    return {
                        "question": q,
                        "intent": "compare",
                        "answer": _insight(
                            "Cannot compare: no supported companies recognized in the question.",
                            sources=["pi_companies"],
                            confidence=1.0,
                            last_updated=updated,
                            insufficient=True,
                        ),
                    }
            if pair:
                result = self.compare(pair[0]["slug"], pair[1]["slug"])
                return {
                    "question": q,
                    "intent": "compare",
                    "answer": result.get("summary")
                    or result.get("insights", [None])[0],
                    "payload": result,
                }

        if any(
            k in ql
            for k in (
                "best customer satisfaction",
                "highest satisfaction",
                "best satisfaction",
                "customer satisfaction",
                "happiest",
                "most positive",
                "رضایت مشتری",
                "بهترین رضایت",
            )
        ):
            return {
                "question": q,
                "intent": "best_satisfaction",
                "answer": self._answer_best_satisfaction(updated),
            }

        if any(
            k in ql
            for k in (
                "complaint rate",
                "highest complaint",
                "most complaints",
                "province",
                "provinces",
            )
        ) and ("province" in ql or "complaint" in ql or "شکایت" in ql):
            return {
                "question": q,
                "intent": "province_complaints",
                "answer": self._answer_province_complaints(updated),
            }

        if any(
            k in ql
            for k in (
                "leader",
                "best company",
                "top rank",
                "highest score",
                "who leads",
                "#1",
                "number 1",
                "market leader",
                "بهترین شرکت",
                "رتبه یک",
            )
        ) and "گلستان" not in ql and "golestan" not in ql:
            leader = companies[0] if companies else None
            if not leader:
                ans = _insight(
                    "Insufficient evidence: ranking table is empty.",
                    sources=["pi_company_scores"],
                    confidence=0.05,
                    last_updated=updated,
                    insufficient=True,
                )
            else:
                # Correct false premise "is Tipax the leader?"
                tipax = next((c for c in companies if c["slug"] == "tipax"), None)
                premise = ""
                if tipax and "tipax" in ql and tipax["id"] != leader["id"]:
                    premise = (
                        f" No. Tipax is rank #{tipax['rank']} at {tipax['score']:.2f}, "
                        f"behind {leader['name']}."
                    )
                ans = _insight(
                    f"By postal_score_v1, {leader['name']} currently leads at "
                    f"{leader['score']:.2f} (rank #1 of {len(companies)}). "
                    f"Dataset confidence: {_conf_label(float(leader['confidence']['overall_dataset_confidence']))} "
                    f"({leader['confidence']['overall_dataset_confidence']:.0%})."
                    + premise,
                    sources=["pi_company_scores", "metric_confidence_bundle"],
                    confidence=float(leader["confidence"]["overall_dataset_confidence"]),
                    last_updated=updated,
                    evidence=[f"{c['name']}={c['score']}" for c in companies],
                )
            return {"question": q, "intent": "leader", "answer": ans}

        if any(
            k in ql
            for k in (
                "coverage",
                "most branches",
                "branch footprint",
                "widest",
                "بیشترین شعبه",
                "بیشترین شعبه را دارد",
            )
        ):
            cov = max(companies, key=lambda c: int(c.get("branch_count") or 0))
            return {
                "question": q,
                "intent": "coverage",
                "answer": _insight(
                    f"In observed Maps-derived warehouse data, {cov['name']} has the most "
                    f"branches ({cov['branch_count']}) spanning {cov['province_count']} provinces. "
                    "This is observed coverage, not necessarily official claimed network size.",
                    sources=["pi_branches"],
                    confidence=float(cov["confidence"]["overall_dataset_confidence"]),
                    last_updated=updated,
                    evidence=[
                        f"{c['name']} branches={c['branch_count']}" for c in companies
                    ],
                ),
            }

        # Damage / lost absolute claims
        if any(
            k in ql
            for k in (
                "never loses",
                "never lose",
                "damages packages the most",
                "lowest package_damage",
                "package_damage rate",
                "zero risk",
            )
        ):
            return {
                "question": q,
                "intent": "risk_claim",
                "answer": _insight(
                    "The warehouse has labeled complaint counts (including package_damage / "
                    "lost_package) but not audited loss rates or guarantees. Absolute safety "
                    "or 'never loses' claims are not supported.",
                    sources=["pi_reviews complaint_category"],
                    confidence=0.4,
                    last_updated=updated,
                    insufficient=True,
                ),
            }

        # Single company lookup
        one = self._extract_one_company(ql, companies)
        if one:
            return {
                "question": q,
                "intent": "company_summary",
                "answer": self.company_executive_summary(one),
            }

        return {
            "question": q,
            "intent": "unknown",
            "answer": _insight(
                "I can answer from warehouse evidence about: overall rankings, "
                "customer satisfaction leaders (≥30 reviews), province complaint rates, "
                "branch coverage, and pairwise company comparisons (e.g. "
                "'Why is Tipax ranked higher than Chapar?'). "
                "This question did not match a supported evidence pattern, so no claim was generated.",
                sources=["demo_ai intent router"],
                confidence=0.8,
                last_updated=updated,
                insufficient=True,
            ),
            "suggestions": [
                "Which company has the best customer satisfaction?",
                "Why is Tipax ranked higher than Chapar?",
                "Which provinces have the highest complaint rate?",
                "Who leads the postal_score_v1 ranking?",
                "Which company has the widest branch coverage?",
            ],
        }

    def _answer_golestan_best(self, updated: str) -> dict[str, Any]:
        companies = self.data.snapshot()["companies"]
        rows = []
        for company in companies:
            for p in self.data.province_performance(int(company["id"])):
                name = str(p.get("geo_name") or "")
                if "golestan" in name.casefold() or "گلستان" in name:
                    rows.append((company, p))
        if not rows:
            return _insight(
                "No Golestan province rows exist in pi_geo_rankings for any company.",
                sources=["pi_geo_rankings"],
                confidence=0.2,
                last_updated=updated,
                insufficient=True,
            )
        if len(rows) == 1:
            company, p = rows[0]
            return _insight(
                f"Only {company['name']} has a Golestan province geo-ranking in this warehouse "
                f"(score={p.get('score')}, reviews={p.get('review_count')}, "
                f"branches={p.get('branch_count')}, avg_rating={p.get('avg_rating')}). "
                "A quality ranking among all carriers for Golestan is not supported because "
                "peers lack Golestan province rows here.",
                sources=["pi_geo_rankings", "pi_companies"],
                confidence=0.35,
                last_updated=updated,
                evidence=[f"{company['name']}:{p}"],
                insufficient=True,
            )
        # multiple — rank by score but caveat sample sizes
        rows.sort(key=lambda x: float(x[1].get("score") or 0), reverse=True)
        top_c, top_p = rows[0]
        listing = "; ".join(
            f"{c['name']} score={p.get('score')} n={p.get('review_count')}" for c, p in rows
        )
        weak = any(int(p.get("review_count") or 0) < 30 for _, p in rows)
        return _insight(
            f"Among companies with Golestan geo rows, {top_c['name']} has the highest "
            f"province score ({top_p.get('score')}). Full set: {listing}."
            + (" Several samples are below 30 reviews." if weak else ""),
            sources=["pi_geo_rankings"],
            confidence=0.4 if weak else 0.55,
            last_updated=updated,
            evidence=[listing],
            insufficient=weak,
        )

    def _extract_company_pair(
        self, ql: str, companies: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        found = []
        for c in companies:
            names = {c["name"].casefold(), c["slug"].casefold()}
            if c.get("name_fa"):
                names.add(str(c["name_fa"]).casefold())
            if any(n and n in ql for n in names):
                found.append(c)
        # stable unique by id
        uniq = []
        seen = set()
        for c in found:
            if c["id"] not in seen:
                uniq.append(c)
                seen.add(c["id"])
        if len(uniq) >= 2:
            return uniq[0], uniq[1]
        return None

    def _extract_all_companies(
        self, ql: str, companies: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        hits = []
        seen = set()
        for c in companies:
            names = {c["name"].casefold(), c["slug"].casefold()}
            if c.get("name_fa"):
                names.add(str(c["name_fa"]).casefold())
            if any(n and n in ql for n in names) and c["id"] not in seen:
                hits.append(c)
                seen.add(c["id"])
        return hits

    def _extract_one_company(
        self, ql: str, companies: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        hits = self._extract_all_companies(ql, companies)
        return hits[0] if len(hits) == 1 else None

    def _answer_best_satisfaction(self, updated: str) -> dict[str, Any]:
        companies = self.data.snapshot()["companies"]
        eligible = [
            c
            for c in companies
            if int(c.get("review_count") or 0) >= 30
            and "customer_satisfaction" in (c.get("dimensions") or {})
        ]
        if not eligible:
            return _insight(
                "Insufficient evidence: no company has ≥30 analyzed reviews required "
                "for a reliable customer satisfaction comparison.",
                sources=["pi_reviews", "customer_satisfaction"],
                confidence=0.15,
                last_updated=updated,
                insufficient=True,
            )
        best = max(
            eligible,
            key=lambda c: float(c["dimensions"]["customer_satisfaction"].get("score") or 0),
        )
        score = float(best["dimensions"]["customer_satisfaction"].get("score") or 0)
        inputs = best["dimensions"]["customer_satisfaction"].get("inputs") or {}
        table = ", ".join(
            f"{c['name']}={float(c['dimensions']['customer_satisfaction'].get('score') or 0):.1f}"
            for c in sorted(
                eligible,
                key=lambda c: float(c["dimensions"]["customer_satisfaction"].get("score") or 0),
                reverse=True,
            )
        )
        return _insight(
            f"Among carriers with ≥30 reviews, {best['name']} has the best "
            f"customer_satisfaction dimension score ({score:.1f}/100; "
            f"CSI={inputs.get('csi')}, avg rating={inputs.get('avg_rating')}, "
            f"n={inputs.get('n')}). Full eligible set: {table}. "
            "Note: overall postal_score_v1 also includes coverage, pricing, and other dimensions, "
            "so the satisfaction leader may differ from the overall rank leader.",
            sources=["pi_reviews", "postal_score_v1 customer_satisfaction"],
            confidence=float(best["confidence"]["overall_dataset_confidence"]),
            last_updated=updated,
            evidence=[table],
        )

    @staticmethod
    def _looks_like_province(name: str) -> bool:
        """Filter street/city noise that sometimes lands in province geo rows."""
        n = (name or "").strip()
        if not n or n.casefold() in {"iran"}:
            return False
        bad_markers = (
            " st",
            "st،",
            " blvd",
            " boulevard",
            " rd",
            " alley",
            " خیابان",
            "بلوار",
            "کوچه",
            "جنب ",
            "ده متری",
            "روبه روی",
            "شهرک",
        )
        low = f" {n.casefold()} "
        if any(m in n.casefold() or m in low for m in bad_markers):
            return False
        # Known province tokens (EN + FA) — allow if matched; otherwise keep short
        # title-case tokens without street punctuation when they appear in warehouse.
        known = {
            "alborz",
            "ardabil",
            "bushehr",
            "chaharmahal and bakhtiari",
            "east azerbaijan",
            "fars",
            "gilan",
            "golestan",
            "hamadan",
            "hormozgan",
            "ilam",
            "isfahan",
            "isfahan province",
            "kerman",
            "kermanshah",
            "khuzestan",
            "kohgiluyeh and boyer-ahmad",
            "kurdistan",
            "lorestan",
            "markazi",
            "mazandaran",
            "north khorasan",
            "qazvin",
            "qom",
            "razavi khorasan",
            "semnan",
            "sistan and baluchestan",
            "south khorasan",
            "tehran",
            "west azerbaijan",
            "yazd",
            "zanjan",
            "تهران",
            "اصفهان",
            "فارس",
            "خراسان رضوی",
            "خوزستان",
            "مازندران",
            "گیلان",
            "آذربایجان شرقی",
            "آذربایجان غربی",
            "کرمان",
            "کرمانشاه",
            "همدان",
            "هرمزگان",
            "یزد",
            "قم",
            "قزوین",
            "مرکزی",
            "لرستان",
            "کردستان",
            "گلستان",
            "سمنان",
            "سیستان و بلوچستان",
            "چهارمحال و بختیاری",
            "کهگیلویه و بویراحمد",
            "البرز",
            "اردبیل",
            "بوشهر",
            "ایلام",
            "زنجان",
            "خراسان شمالی",
            "خراسان جنوبی",
        }
        if n.casefold() in known or n in known:
            return True
        # Reject obvious city-only leftovers that are not in the known set
        cityish = {
            "ahvaz",
            "bandar abbas",
            "basmenj",
            "jalq",
            "kahrizak",
            "saman",
            "fowqani",
            "rasht - pirbazar rd",
        }
        if n.casefold() in cityish:
            return False
        # Conservative: only emit known provinces for investor demo answers
        return False

    def _answer_province_complaints(self, updated: str) -> dict[str, Any]:
        """Aggregate negative share by province across geo rankings / branch intel."""
        c = self.data._c()
        rows = c.execute(
            """
            SELECT geo_name,
                   SUM(review_count) AS reviews,
                   SUM(branch_count) AS branches,
                   AVG(avg_rating) AS avg_rating
            FROM pi_geo_rankings
            WHERE geo_level='province'
            GROUP BY geo_name
            """
        ).fetchall()
        # Prefer metrics_json negative counts when present
        detailed = c.execute(
            """
            SELECT geo_name, company_id, review_count, metrics_json
            FROM pi_geo_rankings
            WHERE geo_level='province'
            """
        ).fetchall()
        import json

        neg_by_prov: dict[str, int] = {}
        rev_by_prov: dict[str, int] = {}
        for r in detailed:
            name = str(r["geo_name"] or "")
            if not self._looks_like_province(name):
                continue
            metrics = json.loads(r["metrics_json"] or "{}")
            sentiments = metrics.get("sentiments") or {}
            neg = int(sentiments.get("Negative") or 0)
            # If sentiments missing, cannot invent — skip contribution
            if not sentiments and int(r["review_count"] or 0) > 0:
                continue
            neg_by_prov[name] = neg_by_prov.get(name, 0) + neg
            rev_by_prov[name] = rev_by_prov.get(name, 0) + int(r["review_count"] or 0)

        rates = []
        for name, reviews in rev_by_prov.items():
            if reviews < 10:
                continue
            neg = neg_by_prov.get(name, 0)
            rates.append(
                {
                    "province": name,
                    "reviews": reviews,
                    "negative": neg,
                    "complaint_rate": round(neg / reviews, 3),
                }
            )
        rates.sort(key=lambda x: x["complaint_rate"], reverse=True)

        if not rates:
            # fallback message with row existence
            if not rows:
                return _insight(
                    "Insufficient evidence: province geo rankings are not present in the warehouse.",
                    sources=["pi_geo_rankings"],
                    confidence=0.1,
                    last_updated=updated,
                    insufficient=True,
                )
            return _insight(
                "Insufficient evidence to compute province complaint rates: "
                "sentiment metrics are missing or sample sizes are below 10 reviews per province.",
                sources=["pi_geo_rankings.metrics_json"],
                confidence=0.2,
                last_updated=updated,
                insufficient=True,
            )

        top = rates[:5]
        listing = "; ".join(
            f"{t['province']} {t['complaint_rate']:.0%} "
            f"({t['negative']}/{t['reviews']} negative)"
            for t in top
        )
        return _insight(
            f"Among provinces with ≥10 analyzed reviews, the highest negative-review "
            f"(complaint) rates are: {listing}. "
            "Rates are negative-sentiment share from Maps-derived reviews, not official "
            "regulator complaint filings.",
            sources=["pi_geo_rankings", "pi_reviews sentiment"],
            confidence=0.65,
            last_updated=updated,
            evidence=[str(t) for t in top],
        )

    def branch_insight(self, branch: dict[str, Any]) -> dict[str, Any]:
        updated = branch.get("calculated_at") or self._meta_time()
        n = int(branch.get("review_count") or 0)
        conf = min(1.0, n / 40.0) if n else 0.05
        if n < 5:
            return _insight(
                f"Insufficient evidence for branch '{branch.get('branch_name')}': "
                f"only {n} reviews in the warehouse.",
                sources=["pi_branch_intelligence", "pi_reviews"],
                confidence=conf,
                last_updated=updated,
                insufficient=True,
            )
        sent = branch.get("sentiment") or {}
        complaints = branch.get("complaint_categories") or {}
        top_c = None
        if complaints:
            top_c = max(complaints.items(), key=lambda x: int(x[1] or 0))
        text = (
            f"{branch.get('branch_name')} ({branch.get('company_name')}, "
            f"{branch.get('city') or 'unknown city'}) scores "
            f"{float(branch.get('branch_score') or 0):.1f}/100 from {n} reviews "
            f"(overall rating {branch.get('overall_rating')}). "
            f"Sentiment mix: {sent}. "
        )
        if top_c:
            text += f"Top complaint category: {top_c[0]} ({top_c[1]})."
        return _insight(
            text,
            sources=["pi_branch_intelligence", "pi_reviews"],
            confidence=conf,
            last_updated=updated,
            evidence=[
                f"branch_score={branch.get('branch_score')}",
                f"reviews={n}",
                f"sentiment={sent}",
                f"complaints={complaints}",
            ],
        )

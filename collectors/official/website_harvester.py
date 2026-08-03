"""Harvest structured official company fields from official websites only.

Provenance: every field records source_url(s) and fetched_at.
Does not invent tariffs; marks fields missing when not published as plain text.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

UA = {"User-Agent": "Mozilla/5.0 (compatible; BrandMonitorCoverage/1.0; research)"}


SITE_PLANS: dict[str, dict[str, Any]] = {
    "tipax": {
        "website": "https://tipaxco.com",
        "verify_ssl": True,
        "pages": {
            "home": "/",
            "services": "/services",
            "domestic_express": "/services/domestic-express",
            "intercity": "/services/intercity",
            "same_day": "/services/same-day",
            "tracking": "/tracking",
            "branches": "/branches/standardpoint",
            "contact": "/contactus",
            "about": "/abouttipax",
            "insurance": "/value-added-services/compensation",
            "packaging": "/value-added-services/packingexpress",
            "cod": "/value-added-services/payexpress",
        },
    },
    "chapar": {
        "website": "https://chaparnet.com",
        "verify_ssl": True,
        "pages": {
            "home": "/",
            "about": "/about-us",
            "branches": "/agencies",
            "contact": "/contact-us",
            "tracking": "/track",
            "pricing": "/shipping-cost",
            "delivery_times": "/shipping-time",
            "domestic": "/services/internal-shipping",
            "international": "/services/international-shipping",
            "cod": "/services/cash-on-delivery",
            "packaging": "/services/packaging",
            "forbidden": "/forbidden-items",
        },
    },
    "mahex": {
        "website": "https://mahex.com",
        "verify_ssl": True,
        "pages": {
            "home": "/",
            "about": "/about-mahex",
            "branches": "/agents",
            "services": "/services",
            "cod": "/cash-on-delivery",
            "support": "/customer-support",
            "insurance": "/%D8%A8%DB%8C%D9%85%D9%87",
            "packaging": "/%D8%A8%D8%B3%D8%AA%D9%87-%D8%A8%D9%86%D8%AF%DB%8C",
            "domestic": "/%D9%BE%D8%B3%D8%AA-%D8%AF%D8%A7%D8%AE%D9%84%DB%8C",
            "express": "/%D9%BE%D8%B3%D8%AA-%D8%B3%D8%B1%DB%8C%D8%B9-%D9%81%D9%84%D8%B4",
        },
    },
    "alopeyk": {
        "website": "https://alopeyk.com",
        "verify_ssl": False,
        "pages": {
            "home": "/",
            "about": "/about-us",
            "contact": "/contact-us",
            "service_courier": "/services/alopeyk",
            "service_post": "/services/alopost",
            "terms": "/terms",
        },
    },
    "pishro": {
        "website": "https://pishro.net",
        "verify_ssl": True,
        "pages": {"home": "/"},
    },
    "post": {
        "website": "https://post.ir",
        "verify_ssl": True,
        "pages": {"home": "/", "www": "https://www.post.ir"},
    },
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()


def fetch_url(url: str, *, verify_ssl: bool = True, timeout: int = 30) -> dict[str, Any]:
    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", "ignore")
        return {
            "url": url,
            "status": resp.status,
            "html": text,
            "text": strip_html(text),
            "fetched_at": utcnow(),
            "error": None,
        }


def safe_fetch(url: str, *, verify_ssl: bool = True) -> dict[str, Any]:
    try:
        return fetch_url(url, verify_ssl=verify_ssl)
    except Exception as exc:  # noqa: BLE001 — harvest must continue
        return {
            "url": url,
            "status": None,
            "html": "",
            "text": "",
            "fetched_at": utcnow(),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _phones(text: str) -> list[str]:
    found = re.findall(r"(?:\+98|0)\d{2,3}[-\s]?\d{3,8}", text)
    cleaned = []
    for p in found:
        p2 = re.sub(r"\s+", "", p)
        if p2.count("0") >= 6:
            continue
        if len(re.sub(r"\D", "", p2)) < 8:
            continue
        cleaned.append(p2)
    return sorted(set(cleaned))


def _emails(text: str) -> list[str]:
    found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return sorted({e for e in found if "example" not in e.lower()})


def _hours_snippet(text: str) -> str | None:
    m = re.search(
        r"(شنبه[^.،]{0,40}\d{1,2}\s*(?:تا|:)?\s*\d{1,2}[^.،]{0,30})",
        text,
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"(از ساعت\s*\d{1,2}\s*تا\s*\d{1,2})", text)
    return m.group(1).strip() if m else None


@dataclass
class FieldEvidence:
    value: Any
    present: bool
    source_urls: list[str] = field(default_factory=list)
    notes: str = ""


def harvest_company(slug: str, *, out_dir: Path) -> dict[str, Any]:
    plan = SITE_PLANS[slug]
    base = plan["website"].rstrip("/")
    verify = bool(plan.get("verify_ssl", True))
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    pages: dict[str, dict[str, Any]] = {}
    for name, path in plan["pages"].items():
        url = path if str(path).startswith("http") else f"{base}{path}"
        page = safe_fetch(url, verify_ssl=verify)
        pages[name] = page
        stem = re.sub(r"[^a-zA-Z0-9]+", "_", url.replace("https://", "").replace("http://", ""))[:120]
        (raw_dir / f"{slug}__{stem}.json").write_text(
            json.dumps(
                {
                    "url": page["url"],
                    "status": page["status"],
                    "fetched_at": page["fetched_at"],
                    "error": page["error"],
                    "text": (page["text"] or "")[:50000],
                    "html_len": len(page.get("html") or ""),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    ok_pages = {k: v for k, v in pages.items() if not v.get("error") and v.get("text")}
    all_text = "\n".join(v["text"] for v in ok_pages.values())
    all_urls = [v["url"] for v in ok_pages.values()]

    def evidence(value: Any, present: bool, urls: list[str] | None = None, notes: str = "") -> dict:
        return {
            "value": value,
            "present": present,
            "source_urls": urls or all_urls[:3],
            "notes": notes,
        }

    services_found: list[str] = []
    service_map = [
        ("domestic_express", ["ارسال بین‌شهری", "پست داخلی", "domestic", "express", "سریع", "بین شهری"]),
        ("same_day", ["همان روز", "same-day", "same day", "ارسال روزانه"]),
        ("international", ["بین‌الملل", "بین الملل", "international"]),
        ("cod", ["پرداخت در محل", "پس‌کرایه", "پس کرایه", "cash on delivery", "COD"]),
        ("insurance", ["بیمه", "جبران خسارت", "غرامت", "insurance"]),
        ("packaging", ["بسته بندی", "بسته‌بندی", "packaging"]),
        ("tracking", ["پیگیری", "رهگیری", "tracking", "track"]),
        ("pickup", ["جمع‌آوری", "پیکاپ", "pickup", "از درب"]),
        ("door_to_door", ["درب به درب", "درب‌به‌درب", "پلاک‌به‌پلاک", "door"]),
        ("branch_to_branch", ["نمایندگی", "شعبه", "agency", "agent"]),
        ("urban_ondemand", ["الوپیک", "پیک موتوری", "on-demand", "همان ساعت"]),
    ]
    for code, needles in service_map:
        if any(n.lower() in all_text.lower() for n in needles):
            services_found.append(code)

    phones = _phones(all_text)
    emails = _emails(all_text)
    hours = _hours_snippet(all_text)

    # Tipax-specific insurance bounds from compensation page
    weight_limits: dict[str, Any] = {}
    size_limits: dict[str, Any] = {}
    delivery_times: dict[str, Any] = {}
    pricing: dict[str, Any] = {"calculator_available": False, "published_base_rates": False}

    if "pricing" in ok_pages or "shipping-cost" in (ok_pages.get("pricing", {}).get("url") or ""):
        pricing["calculator_available"] = True
    if any("تعرفه" in (p.get("text") or "") for p in ok_pages.values()):
        pricing["mentions_tariff_word"] = True
    if "pricing" in ok_pages or any("shipping-cost" in (p.get("url") or "") for p in ok_pages.values()):
        pricing["calculator_available"] = True
        pricing["source_urls"] = [ok_pages["pricing"]["url"]] if "pricing" in ok_pages else all_urls

    # Delivery cues
    if slug == "chapar" and "domestic" in ok_pages:
        t = ok_pages["domestic"]["text"]
        if "48" in t or "72" in t:
            delivery_times["mentions_48_72_hours"] = True
            delivery_times["notes"] = "Page mentions 48/72 hour windows; interactive ETA tool on /shipping-time"
            delivery_times["source_urls"] = [ok_pages["domestic"]["url"], pages.get("delivery_times", {}).get("url")]
    if slug == "tipax" and "intercity" in ok_pages:
        t = ok_pages["intercity"]["text"]
        if "24 ساعت" in t:
            delivery_times["mentions_24h_air_lanes"] = True
            delivery_times["notes"] = "Intercity page mentions select 24h air lanes (e.g. Mashhad–Kish)"
            delivery_times["source_urls"] = [ok_pages["intercity"]["url"]]
    if slug == "tipax" and "same_day" in ok_pages:
        delivery_times["same_day_service_page"] = True

    # Insurance amounts Tipax
    insurance: dict[str, Any] = {"available": "insurance" in services_found}
    if slug == "tipax" and "insurance" in ok_pages:
        t = ok_pages["insurance"]["text"]
        insurance["available"] = True
        if "400 هزار" in t or "400,000" in t:
            insurance["min_coverage_note"] = "from ~400 thousand toman stated on compensation page"
        if "100 میلیون" in t:
            insurance["max_coverage_note"] = "up to ~100 million toman stated on compensation page"
        insurance["source_urls"] = [ok_pages["insurance"]["url"]]

    if slug == "mahex" and "insurance" in ok_pages and not ok_pages["insurance"].get("error"):
        insurance["available"] = True
        insurance["source_urls"] = [ok_pages["insurance"]["url"]]
        insurance["notes"] = "Dedicated insurance page present on mahex.com"

    tracking = {
        "available": "tracking" in services_found or "tracking" in ok_pages or "track" in (pages.get("tracking", {}).get("url") or ""),
        "channels": [],
        "source_urls": [],
    }
    if "tracking" in ok_pages:
        tracking["channels"].append("website")
        tracking["source_urls"].append(ok_pages["tracking"]["url"])
        tracking["available"] = True

    packaging = {"available": "packaging" in services_found}
    if "packaging" in ok_pages:
        packaging["available"] = True
        packaging["source_urls"] = [ok_pages["packaging"]["url"]]

    cod = {"available": "cod" in services_found}
    if "cod" in ok_pages:
        cod["available"] = True
        cod["source_urls"] = [ok_pages["cod"]["url"]]

    branches_page = ok_pages.get("branches")
    branch_info = {
        "locator_page": bool(branches_page),
        "source_urls": [branches_page["url"]] if branches_page else [],
        "branch_list_extracted": False,
        "notes": "Agency/branch locator page present; structured branch dump not always in static HTML (JS apps).",
    }

    support = {
        "phone": phones[:5],
        "email": emails[:5],
        "website_chat": False,
        "source_urls": all_urls[:1],
    }
    if "contact" in ok_pages:
        support["source_urls"] = [ok_pages["contact"]["url"]]
    elif "support" in ok_pages:
        support["source_urls"] = [ok_pages["support"]["url"]]

    working_hours = {
        "raw_snippet": hours,
        "present": bool(hours),
        "source_urls": all_urls[:2] if hours else [],
    }

    # Explicit missing list for report
    required_topics = [
        "branches",
        "services",
        "coverage",
        "official_delivery_times",
        "official_pricing",
        "weight_limits",
        "size_limits",
        "insurance",
        "tracking",
        "working_hours",
        "customer_support",
    ]
    missing = []
    if not branch_info["locator_page"]:
        missing.append("branches")
    if not services_found:
        missing.append("services")
    missing.append("coverage")  # city/province counts rarely published as countable HTML
    if not delivery_times:
        missing.append("official_delivery_times")
    if not pricing.get("calculator_available") and not pricing.get("published_base_rates"):
        missing.append("official_pricing")
    if not weight_limits:
        missing.append("weight_limits")
    if not size_limits:
        missing.append("size_limits")
    if not insurance.get("available"):
        missing.append("insurance")
    if not tracking.get("available"):
        missing.append("tracking")
    if not working_hours.get("present"):
        missing.append("working_hours")
    if not support["phone"] and not support["email"]:
        missing.append("customer_support")

    reachable = len(ok_pages) > 0
    profile = {
        "slug": slug,
        "website": base,
        "harvested_at": utcnow(),
        "pages_fetched": len(pages),
        "pages_ok": len(ok_pages),
        "page_errors": {k: v.get("error") for k, v in pages.items() if v.get("error")},
        "reachable": reachable,
        "source": "official_website",
        "services": {
            "value": services_found,
            "present": bool(services_found),
            "source_urls": all_urls[:5],
        },
        "branches": branch_info,
        "coverage": {
            "present": False,
            "value": None,
            "notes": "Numeric nationwide coverage counts not extractable as static HTML from official sites in this harvest.",
            "source_urls": [],
        },
        "official_delivery_times": {
            "present": bool(delivery_times),
            "value": delivery_times or None,
            "source_urls": delivery_times.get("source_urls", []) if delivery_times else [],
            "notes": delivery_times.get("notes", "No explicit numeric SLA table parsed from HTML."),
        },
        "official_pricing": {
            "present": bool(pricing.get("calculator_available") or pricing.get("published_base_rates")),
            "value": pricing,
            "notes": "Interactive calculators detected where present; fixed public unit prices rarely listed as plain text.",
            "source_urls": pricing.get("source_urls", []),
        },
        "weight_limits": {
            "present": False,
            "value": weight_limits or None,
            "notes": "No clear max kg table extracted from static HTML.",
            "source_urls": [],
        },
        "size_limits": {
            "present": False,
            "value": size_limits or None,
            "notes": "No clear max dimensions table extracted from static HTML.",
            "source_urls": [],
        },
        "insurance": {
            "present": bool(insurance.get("available")),
            "value": insurance,
            "source_urls": insurance.get("source_urls", []),
        },
        "tracking": {
            "present": bool(tracking.get("available")),
            "value": tracking,
            "source_urls": tracking.get("source_urls", []),
        },
        "working_hours": {
            "present": working_hours["present"],
            "value": working_hours,
            "source_urls": working_hours.get("source_urls", []),
        },
        "customer_support": {
            "present": bool(support["phone"] or support["email"]),
            "value": support,
            "source_urls": support.get("source_urls", []),
        },
        "packaging": packaging,
        "cod": cod,
        "missing_official_information": missing,
        "required_topics": required_topics,
        "completeness_ratio": round((len(required_topics) - len(missing)) / len(required_topics), 3),
    }

    (out_dir / f"{slug}_official_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return profile


def harvest_all(out_dir: str | Path = "data/official_harvest") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    profiles = {}
    for slug in SITE_PLANS:
        profiles[slug] = harvest_company(slug, out_dir=out)
    summary = {
        "harvested_at": utcnow(),
        "companies": {
            slug: {
                "reachable": p["reachable"],
                "pages_ok": p["pages_ok"],
                "completeness_ratio": p["completeness_ratio"],
                "missing": p["missing_official_information"],
                "services": p["services"]["value"],
                "support_phones": (p["customer_support"]["value"] or {}).get("phone"),
            }
            for slug, p in profiles.items()
        },
    }
    (out / "harvest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary

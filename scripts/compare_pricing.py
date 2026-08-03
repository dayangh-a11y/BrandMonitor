#!/usr/bin/env python3
"""CLI: compare carrier quotes via the unified Pricing & ETA Engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from postal.pricing import PricingEngine
from postal.pricing.types import Dimensions, Location, QuoteRequest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origin", required=True, help="Origin city name or code")
    p.add_argument("--destination", required=True, help="Destination city name or code")
    p.add_argument("--weight-kg", type=float, required=True)
    p.add_argument("--length-cm", type=float, default=None)
    p.add_argument("--width-cm", type=float, default=None)
    p.add_argument("--height-cm", type=float, default=None)
    p.add_argument("--package-type", default="parcel")
    p.add_argument("--declared-value", type=float, default=None)
    p.add_argument("--cod", action="store_true")
    p.add_argument("--insurance", action="store_true")
    p.add_argument("--origin-lat", type=float, default=None)
    p.add_argument("--origin-lng", type=float, default=None)
    p.add_argument("--dest-lat", type=float, default=None)
    p.add_argument("--dest-lng", type=float, default=None)
    p.add_argument("--providers", default="", help="Comma-separated slugs (default: all)")
    p.add_argument("--json-out", default="", help="Optional path to write full JSON")
    args = p.parse_args()

    def loc(value: str, lat: float | None, lng: float | None) -> Location:
        if value.isdigit() or value.upper().startswith("IR-"):
            return Location(city_code=value, lat=lat, lng=lng)
        return Location(city_name=value, city_code=value if value.isdigit() else None, lat=lat, lng=lng)

    req = QuoteRequest(
        origin=loc(args.origin, args.origin_lat, args.origin_lng),
        destination=loc(args.destination, args.dest_lat, args.dest_lng),
        weight_kg=args.weight_kg,
        dimensions=Dimensions(
            length_cm=args.length_cm,
            width_cm=args.width_cm,
            height_cm=args.height_cm,
        ),
        package_type=args.package_type,
        cod=args.cod,
        insurance=args.insurance,
        declared_value=args.declared_value,
    )
    slugs = [s.strip() for s in args.providers.split(",") if s.strip()] or None
    result = PricingEngine().compare(req, slugs=slugs)
    print(result["markdown_table"])
    print()
    print(
        f"Available: {result['summary']['providers_available']}/"
        f"{result['summary']['providers_total']} · "
        f"cheapest={result['summary']['cheapest_company']} "
        f"({result['summary']['cheapest_price']})"
    )
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

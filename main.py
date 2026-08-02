import asyncio
import os
from pathlib import Path

from collectors.google_maps.collector import GoogleMapsCollector
from core.csv_exporter import CsvExporter
from core.db import Database


def _load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


async def main() -> None:
    _load_dotenv()

    brand = os.getenv("SEARCH_QUERY", "تیپاکس")
    db_path = os.getenv("DB_PATH", "data/brandmonitor.db")

    collector = GoogleMapsCollector()
    exporter = CsvExporter()
    db = Database(db_path)

    await db.connect()
    await collector.start()

    try:
        branches, reviews = await collector.collect(brand, with_reviews=True)

        company_id = await db.upsert_company(brand)
        for branch in branches:
            branch_id = await db.upsert_branch(company_id, branch)
            branch_reviews = [r for r in reviews if r.branch_name == branch.name]
            for review in branch_reviews:
                await db.upsert_review(branch_id, review)

        exporter.export_branches(branches)
        exporter.export_reviews(reviews)

        stats = await db.stats()
        print("\n=== Collection Summary ===")
        print(f"Brand: {brand}")
        print(f"Branches collected: {len(branches)}")
        print(f"Reviews collected: {len(reviews)}")
        print(f"DB stats: {stats}")
        print(f"DB path: {db_path}")
    finally:
        await collector.stop()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

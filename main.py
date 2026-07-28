import asyncio

from collectors.google_maps.collector import GoogleMapsCollector
from core.csv_exporter import CsvExporter


async def main():

    collector = GoogleMapsCollector()

    exporter = CsvExporter()

    await collector.start()

    await collector.search("تیپاکس")

    branches = await collector.collect()

    exporter.export(branches)

    await collector.stop()


if __name__ == "__main__":
    asyncio.run(main())
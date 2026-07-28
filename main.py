import asyncio

from collectors.google_maps.collector import GoogleMapsCollector


async def main():

    collector = GoogleMapsCollector()

    await collector.start()

    await collector.search("تیپاکس")

    branches = await collector.collect()

    print("\n====================")
    print("Collected Branches")
    print("====================\n")

    for branch in branches:
        print(branch)

    await collector.stop()


if __name__ == "__main__":
    asyncio.run(main())
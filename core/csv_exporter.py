import csv
import os


class CsvExporter:

    def export(self, branches, filename="output/branches.csv"):

        os.makedirs("output", exist_ok=True)

        with open(
            filename,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as file:

            writer = csv.writer(file)

            writer.writerow([
                "Name",
                "Rating",
                "Review Count",
                "Address"
            ])

            for branch in branches:

                writer.writerow([
                    branch.name,
                    branch.rating,
                    branch.review_count,
                    branch.address
                ])

        print(f"\nCSV Saved -> {filename}")
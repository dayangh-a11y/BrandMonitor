import csv
import os
from pathlib import Path

from models.branch import Branch
from models.review import Review


class CsvExporter:
    def export_branches(
        self,
        branches: list[Branch],
        filename: str = "output/branches.csv",
    ) -> str:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with open(filename, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(
                ["Name", "Rating", "Review Count", "Address", "Maps URL", "Place ID"]
            )
            for branch in branches:
                writer.writerow(
                    [
                        branch.name,
                        branch.rating,
                        branch.review_count,
                        branch.address,
                        branch.maps_url,
                        branch.place_id,
                    ]
                )
        print(f"CSV Saved -> {filename}")
        return filename

    def export_reviews(
        self,
        reviews: list[Review],
        filename: str = "output/reviews.csv",
    ) -> str:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with open(filename, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "Branch",
                    "Author",
                    "Rating",
                    "Published At",
                    "Text",
                    "External ID",
                    "Source",
                ]
            )
            for review in reviews:
                writer.writerow(
                    [
                        review.branch_name,
                        review.author,
                        review.rating,
                        review.published_at,
                        review.text,
                        review.external_id,
                        review.source,
                    ]
                )
        print(f"CSV Saved -> {filename}")
        return filename

    # Backward-compatible alias used by older entrypoints.
    def export(self, branches, filename="output/branches.csv"):
        return self.export_branches(branches, filename=filename)

"""Explicit CI-only seed of three real publisher records; no provider network calls."""

import csv
import json
import os
from pathlib import Path
from sqlalchemy import select, update
from harmonygraph.catalog import analyze_batch, import_catalog
from harmonygraph.db import CatalogRecord, Job, factory, make_engine


def main():
    if os.environ.get("HARMONY_TEST_FIXTURES") != "1":
        raise SystemExit("This test-only seeder requires HARMONY_TEST_FIXTURES=1. Use catalog start for real imports.")
    fixture = json.loads(Path("tests/fixtures/chordonomicon-real.json").read_text(encoding="utf-8"))
    path = Path("data/local/catalog-browser-fixture.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fixture["records"][0]["raw"].keys())
        writer.writeheader()
        writer.writerows(r["raw"] for r in fixture["records"])
    with factory(make_engine())() as session:
        imported = import_catalog(session, path, {}, lambda _: None)
        for source in fixture["records"]:
            row = session.scalar(
                select(CatalogRecord).where(
                    CatalogRecord.dataset_id == imported["dataset_id"], CatalogRecord.source_id == source["raw"]["id"]
                )
            )
            row.title, row.artist, row.artwork = source["title"], source["artist"], source["artwork"]
            row.metadata_status = "resolved"
        session.execute(
            update(Job)
            .where(Job.kind.in_(["catalog_metadata", "catalog_analyze"]), Job.status == "queued")
            .values(status="cancelled")
        )
        session.commit()
        analyze_batch(session, {}, lambda _: None)
    print("Three real publisher records loaded into the explicitly selected test environment.")


if __name__ == "__main__":
    main()

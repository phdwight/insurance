"""Seed the catalog from seed_data.yaml.

Usage:
    uv run --package insurance-db python db/seed.py            # local
    docker compose run --rm migrate python db/seed.py          # via compose

Idempotent: existing slugs are skipped. If VOYAGE_API_KEY is set, embeddings
are generated (model voyage-3.5, 1024 dims); otherwise skipped — search then
falls back to SQL-only ranking.
"""

import json
import os
import sys
from pathlib import Path

import yaml
from shared.embeddings import embed_documents, embedding_model, embeddings_enabled
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://insurance:insurance@localhost:5432/insurance",
)
SEED_FILE = Path(__file__).parent / "seed_data.yaml"


def main() -> None:
    data = yaml.safe_load(SEED_FILE.read_text())
    engine = create_engine(DATABASE_URL)
    embed = embeddings_enabled()
    seeded, skipped = 0, 0

    with engine.begin() as conn:
        for insurer in data["insurers"]:
            conn.execute(
                text(
                    """
                    INSERT INTO catalog.insurers (name, slug, website)
                    VALUES (:name, :slug, :website)
                    ON CONFLICT (slug) DO NOTHING
                    """
                ),
                insurer,
            )

        for entry in data["policies"]:
            exists = conn.execute(
                text("SELECT 1 FROM catalog.policies WHERE slug = :slug"),
                {"slug": entry["slug"]},
            ).first()
            if exists:
                skipped += 1
                continue

            version = entry["version"]
            policy_id = conn.execute(
                text(
                    """
                    INSERT INTO catalog.policies
                        (insurer_id, product_line_id, name, slug, status)
                    SELECT i.id, pl.id, :name, :slug, 'published'
                    FROM catalog.insurers i, catalog.product_lines pl
                    WHERE i.slug = :insurer_slug AND pl.code = :line
                    RETURNING id
                    """
                ),
                {
                    "name": entry["name"],
                    "slug": entry["slug"],
                    "insurer_slug": entry["insurer"],
                    "line": entry["product_line"],
                },
            ).scalar_one()

            version_id = conn.execute(
                text(
                    """
                    INSERT INTO catalog.policy_versions
                        (policy_id, version, summary, premium_min, premium_max,
                         premium_frequency, eligibility, coverage, exclusions,
                         riders, verified_at, published_at)
                    VALUES
                        (:policy_id, 1, :summary, :premium_min, :premium_max,
                         :premium_frequency, :eligibility, :coverage, :exclusions,
                         :riders, now(), now())
                    RETURNING id
                    """
                ),
                {
                    "policy_id": policy_id,
                    "summary": " ".join(version["summary"].split()),
                    "premium_min": version.get("premium_min"),
                    "premium_max": version.get("premium_max"),
                    "premium_frequency": version.get("premium_frequency"),
                    "eligibility": json.dumps(version.get("eligibility", {})),
                    "coverage": json.dumps(version["coverage"]),
                    "exclusions": json.dumps(version.get("exclusions", [])),
                    "riders": json.dumps(version.get("riders", [])),
                },
            ).scalar_one()

            if embed:
                text_used = f"{entry['name']}. {' '.join(version['summary'].split())}"
                [embedding] = embed_documents([text_used])
                conn.execute(
                    text(
                        """
                        INSERT INTO catalog.policy_embeddings
                            (policy_version_id, embedding, model, text_used)
                        VALUES (:vid, :embedding, :model, :text_used)
                        """
                    ),
                    {
                        "vid": version_id,
                        "embedding": str(embedding),
                        "model": embedding_model(),
                        "text_used": text_used,
                    },
                )
            seeded += 1

    mode = "with embeddings" if embed else "WITHOUT embeddings (no VOYAGE_API_KEY)"
    print(f"Seeded {seeded} policies ({skipped} already present) {mode}.")


if __name__ == "__main__":
    sys.exit(main())

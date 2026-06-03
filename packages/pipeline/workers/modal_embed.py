"""
Modal GPU worker — BGE-M3 embedding backfill.

Runs BGE-M3 (BAAI/bge-m3) on a Modal A10G GPU to embed all incidents
in ~10 minutes instead of ~4 hours on CPU.

Usage:
    pip install modal
    modal run packages/pipeline/workers/modal_embed.py

    # With specific batch size:
    modal run packages/pipeline/workers/modal_embed.py::embed_all --batch-size 128

Environment variables required (set via modal secret or .env):
    DATABASE_URL — Neon/Postgres connection string

The function reads incidents with no embedding, encodes in batches on GPU,
and writes embedding + embedding_model + embedded_at back to the database.
"""

from __future__ import annotations

try:
    import modal  # type: ignore[import]
    _MODAL_AVAILABLE = True
except ImportError:
    _MODAL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Modal image — BGE-M3 pre-installed
# ---------------------------------------------------------------------------

if _MODAL_AVAILABLE:
    _image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "sentence-transformers>=3.0.0",
            "torch>=2.2.0",
            "psycopg2-binary>=2.9.9",
            "pgvector>=0.3.0",
        )
        .env({"TOKENIZERS_PARALLELISM": "false"})
    )

    _app = modal.App("racejudge-embed")
    _vol = modal.Volume.from_name("racejudge-models", create_if_missing=True)

    @_app.function(
        image=_image,
        gpu="A10G",
        timeout=3600,
        secrets=[modal.Secret.from_name("racejudge-secrets")],
        volumes={"/models": _vol},
    )
    def embed_all(batch_size: int = 128) -> dict:
        """
        GPU function: embed all unembedded incidents in the database.
        Returns a summary dict: {embedded: int, skipped: int, errors: int}.
        """
        import logging
        import os
        import time

        import psycopg2
        from sentence_transformers import SentenceTransformer

        logging.basicConfig(level=logging.INFO)
        log = logging.getLogger("modal_embed")

        MODEL_NAME  = "BAAI/bge-m3"
        CACHE_DIR   = "/models/bge-m3"
        DB_URL      = os.environ["DATABASE_URL"]

        log.info("Loading BGE-M3 from %s (or downloading to %s)", MODEL_NAME, CACHE_DIR)
        t0 = time.time()
        model = SentenceTransformer(MODEL_NAME, cache_folder=CACHE_DIR, device="cuda")
        log.info("Model loaded in %.1fs", time.time() - t0)

        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()

        # Fetch incidents with no embedding
        cur.execute("""
            SELECT incident_id, infraction_category, reasoning_text, article_cited
            FROM incidents
            WHERE embedding IS NULL
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        log.info("Found %d incidents to embed", len(rows))

        embedded = 0
        errors   = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            ids   = [r[0] for r in batch]

            texts: list[str] = []
            for _, infraction, reasoning, articles in batch:
                parts: list[str] = []
                if infraction:
                    parts.append(infraction.replace("_", " "))
                if articles:
                    parts.append("Articles: " + ", ".join(articles))
                if reasoning:
                    parts.append(reasoning[:512])
                texts.append(" | ".join(parts) if parts else "F1 stewards incident")

            try:
                vecs = model.encode(
                    texts,
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            except Exception as exc:
                log.error("Encode error on batch %d: %s", i // batch_size, exc)
                errors += len(batch)
                continue

            for incident_id, vec in zip(ids, vecs, strict=True):
                try:
                    cur.execute(
                        """
                        UPDATE incidents
                        SET embedding = %s::vector,
                            embedding_model = %s,
                            embedded_at = NOW()
                        WHERE incident_id = %s
                        """,
                        (vec.tolist(), MODEL_NAME, incident_id),
                    )
                    embedded += 1
                except Exception as exc:
                    log.error("DB write error for %s: %s", incident_id, exc)
                    errors += 1

            conn.commit()
            log.info(
                "Batch %d/%d — embedded so far: %d",
                i // batch_size + 1,
                (len(rows) + batch_size - 1) // batch_size,
                embedded,
            )

        cur.close()
        conn.close()
        log.info("Done. embedded=%d errors=%d", embedded, errors)
        return {"embedded": embedded, "skipped": len(rows) - embedded - errors, "errors": errors}


    @_app.function(
        image=_image,
        gpu="A10G",
        timeout=3600,
        secrets=[modal.Secret.from_name("racejudge-secrets")],
        volumes={"/models": _vol},
    )
    def refresh_precedent_links(top_k: int = 20) -> dict:
        """
        After embedding backfill, refresh the precedent_links table using
        pgvector cosine similarity. Runs entirely inside Postgres via SQL.
        """
        import logging
        import os

        import psycopg2

        log = logging.getLogger("modal_embed")
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()

        cur.execute("DELETE FROM precedent_links")
        cur.execute(f"""
            INSERT INTO precedent_links (incident_id, similar_incident_id, similarity_score, rank)
            SELECT
                i.incident_id,
                n.incident_id AS similar_incident_id,
                1 - (i.embedding <=> n.embedding) AS similarity_score,
                ROW_NUMBER() OVER (
                    PARTITION BY i.incident_id
                    ORDER BY i.embedding <=> n.embedding
                ) AS rank
            FROM incidents i
            CROSS JOIN LATERAL (
                SELECT incident_id, embedding
                FROM incidents
                WHERE incident_id != i.incident_id
                  AND embedding IS NOT NULL
                ORDER BY i.embedding <=> embedding
                LIMIT {top_k}
            ) n
            WHERE i.embedding IS NOT NULL
        """)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM precedent_links")
        total = cur.fetchone()[0]
        cur.close()
        conn.close()
        log.info("Refreshed precedent_links: %d rows", total)
        return {"precedent_links": total}


# ---------------------------------------------------------------------------
# Local entrypoint — deploy or run
# ---------------------------------------------------------------------------

def main() -> None:
    if not _MODAL_AVAILABLE:
        print("modal not installed. Run: pip install modal")
        print("Then: modal run packages/pipeline/workers/modal_embed.py")
        return

    import sys
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 128
    print(f"Submitting embed_all(batch_size={batch_size}) to Modal A10G...")
    with _app.run():
        result = embed_all.remote(batch_size=batch_size)
        print(f"Embedding complete: {result}")
        result2 = refresh_precedent_links.remote()
        print(f"Precedent links refreshed: {result2}")


if __name__ == "__main__":
    main()

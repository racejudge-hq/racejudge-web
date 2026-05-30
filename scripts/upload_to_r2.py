"""
Upload scraped PDFs to Cloudflare R2.

Requires:
  - R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY env vars
  - R2_BUCKET_RAW env var (default: racejudge-raw)
  - boto3 installed (pip install boto3)

Objects are keyed as: pdfs/{season}/{filename}
Idempotent: skips files that already exist in R2 (by etag check).

Usage:
    R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... \
      python scripts/upload_to_r2.py
    python scripts/upload_to_r2.py --season 2024 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw_pdfs"


def _require_boto3():
    try:
        import boto3
        return boto3
    except ImportError:
        print("boto3 not installed. Run: pip install boto3")
        sys.exit(1)


def get_r2_client():
    boto3 = _require_boto3()
    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")

    if not all([account_id, access_key, secret_key]):
        print("Error: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY must be set")
        sys.exit(1)

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def md5_hex(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_season(
    client,
    bucket: str,
    season: int,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Upload all PDFs for a season. Returns (uploaded, skipped) counts."""
    season_dir = DATA_DIR / str(season)
    if not season_dir.exists():
        print(f"  Season dir not found: {season_dir}")
        return 0, 0

    pdfs = sorted(season_dir.glob("*.pdf"))
    uploaded = 0
    skipped = 0

    for pdf in pdfs:
        key = f"pdfs/{season}/{pdf.name}"

        # Check if already uploaded (etag comparison)
        if not dry_run:
            try:
                head = client.head_object(Bucket=bucket, Key=key)
                remote_etag = head["ETag"].strip('"')
                local_md5 = md5_hex(pdf)
                if remote_etag == local_md5:
                    skipped += 1
                    continue
            except Exception:
                pass  # Object doesn't exist, proceed with upload

        if dry_run:
            print(f"  [DRY RUN] Would upload: {key}")
        else:
            print(f"  Uploading: {key}")
            with open(pdf, "rb") as f:
                client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="application/pdf",
                    Metadata={"season": str(season)},
                )
        uploaded += 1

    return uploaded, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload PDFs to Cloudflare R2")
    parser.add_argument("--season", type=int, help="Upload specific season only")
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET_RAW", "racejudge-raw"))
    parser.add_argument("--dry-run", action="store_true", help="Print actions without uploading")
    args = parser.parse_args()

    client = None if args.dry_run else get_r2_client()

    seasons = [args.season] if args.season else [2019, 2020, 2021, 2022, 2023, 2024, 2025]
    total_uploaded = 0
    total_skipped = 0

    for season in seasons:
        print(f"\nSeason {season}:")
        u, s = upload_season(client, args.bucket, season, dry_run=args.dry_run)
        print(f"  Uploaded: {u}, Skipped: {s}")
        total_uploaded += u
        total_skipped += s

    print(f"\nDone. Total uploaded: {total_uploaded}, skipped: {total_skipped}")


if __name__ == "__main__":
    main()

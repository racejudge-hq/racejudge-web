"""
Team radio fetcher — Phase 3.

Fetches the 3 nearest team_radio clips within ±60s of an incident timestamp
from the OpenF1 API, downloads them to audio_cache/, and returns local paths.

Implementation plan reference: pipeline/audio/radio_fetcher.py
  - Fetch 3 nearest clips within ±60 seconds of incident timestamp
  - Cache mp3s keyed by session_key/driver/clip_id
  - Celery task wrapper for async execution

Usage:
    from packages.pipeline.audio.radio_fetcher import RadioFetcher
    fetcher = RadioFetcher()
    clips = fetcher.fetch_incident_clips(
        session_key=9158, driver_number=44,
        incident_time="2024-07-07T15:32:10", window_seconds=60
    )
    # clips = [{"path": "...", "recording_url": "...", "date": "..."}]
"""

from __future__ import annotations

import hashlib
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

AUDIO_CACHE_DIR = Path(__file__).resolve().parents[3] / "audio_cache"
AUDIO_CACHE_DIR.mkdir(exist_ok=True)


def _parse_dt(s: str) -> datetime:
    """Parse OpenF1 ISO datetime string → timezone-aware datetime."""
    s = s.rstrip("Z")
    if "." in s:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
    else:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def _cache_path(session_key: int, driver_number: int, url: str) -> Path:
    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    suffix = Path(urlparse(url).path).suffix or ".mp3"
    return AUDIO_CACHE_DIR / f"{session_key}_{driver_number}_{url_hash}{suffix}"


class RadioFetcher:
    """
    Fetches team radio clips from OpenF1 for a given incident window.
    Downloads and caches mp3s locally.
    """

    def __init__(self):
        from packages.pipeline.linkers.openf1_client import OpenF1Client
        self._client = OpenF1Client()

    def fetch_incident_clips(
        self,
        session_key: int,
        driver_number: int,
        incident_time: str | datetime,
        window_seconds: int = 60,
        max_clips: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Return up to max_clips team radio clips closest to incident_time
        within ±window_seconds.

        Returns list of dicts:
          - recording_url: original URL
          - date: clip timestamp
          - path: local cached file path (str)
          - driver_number: int
          - session_key: int
        """
        if isinstance(incident_time, str):
            incident_dt = _parse_dt(incident_time)
        else:
            incident_dt = incident_time

        window_start = incident_dt - timedelta(seconds=window_seconds)
        window_end = incident_dt + timedelta(seconds=window_seconds)

        all_radio = self._client.team_radio(
            session_key=session_key,
            driver_number=driver_number,
        )

        # Filter to window and sort by distance to incident_time
        windowed = []
        for clip in all_radio:
            date_str = clip.get("date")
            if not date_str:
                continue
            try:
                clip_dt = _parse_dt(date_str)
            except ValueError:
                continue
            if window_start <= clip_dt <= window_end:
                dist = abs((clip_dt - incident_dt).total_seconds())
                windowed.append((dist, clip))

        windowed.sort(key=lambda x: x[0])
        nearest = [clip for _, clip in windowed[:max_clips]]

        results = []
        for clip in nearest:
            url = clip.get("recording_url") or clip.get("clip_identifier")
            if not url:
                continue
            cached = self._download(url, session_key, driver_number)
            results.append({
                "recording_url": url,
                "date": clip.get("date"),
                "path": str(cached) if cached else None,
                "driver_number": driver_number,
                "session_key": session_key,
            })

        log.info(
            "Fetched %d/%d clips for driver %d session %d within ±%ds of incident",
            len(results), len(all_radio), driver_number, session_key, window_seconds,
        )
        return results

    def _download(
        self,
        url: str,
        session_key: int,
        driver_number: int,
    ) -> Path | None:
        """Download a clip to cache. Returns local path or None on failure."""
        dest = _cache_path(session_key, driver_number, url)
        if dest.exists():
            log.debug("Cache hit: %s", dest.name)
            return dest
        try:
            log.info("Downloading radio clip: %s", url)
            urllib.request.urlretrieve(url, dest)
            return dest
        except Exception as exc:
            log.warning("Failed to download %s: %s", url, exc)
            return None

    def fetch_all_driver_clips(
        self,
        session_key: int,
        driver_number: int,
        download: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Fetch all team radio clips for a driver in a session.
        Used for full-session backfill transcription.
        """
        all_radio = self._client.team_radio(
            session_key=session_key,
            driver_number=driver_number,
        )
        results = []
        for clip in all_radio:
            url = clip.get("recording_url") or clip.get("clip_identifier")
            if not url:
                continue
            path = None
            if download:
                path = self._download(url, session_key, driver_number)
            results.append({
                "recording_url": url,
                "date": clip.get("date"),
                "path": str(path) if path else None,
                "driver_number": driver_number,
                "session_key": session_key,
            })
        return results


# ---------------------------------------------------------------------------
# Celery / Prefect task wrappers
# ---------------------------------------------------------------------------

try:
    from prefect import task as prefect_task

    @prefect_task(name="fetch-radio-clips", retries=2, retry_delay_seconds=30)
    def fetch_radio_clips_task(
        session_key: int,
        driver_number: int,
        incident_time: str,
        window_seconds: int = 60,
        max_clips: int = 3,
    ) -> list[dict]:
        fetcher = RadioFetcher()
        return fetcher.fetch_incident_clips(
            session_key=session_key,
            driver_number=driver_number,
            incident_time=incident_time,
            window_seconds=window_seconds,
            max_clips=max_clips,
        )

except ImportError:
    def fetch_radio_clips_task(session_key, driver_number, incident_time,
                               window_seconds=60, max_clips=3):
        fetcher = RadioFetcher()
        return fetcher.fetch_incident_clips(
            session_key=session_key,
            driver_number=driver_number,
            incident_time=incident_time,
            window_seconds=window_seconds,
            max_clips=max_clips,
        )

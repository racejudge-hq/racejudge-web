"""
Part 3 — Team-radio ASR backfill into team_radio_clips (real audio only).

For every incident that has a live race-control timestamp (its real moment on
track), fetch the involved driver's OpenF1 team-radio clips around that moment,
transcribe them with Whisper, score sentiment + urgency, and link each clip to
the incident.

Real data only:
  - audio comes straight from OpenF1 recording_url (no synthetic clips)
  - transcripts from faster-whisper (base, int8 CPU) with an F1 domain prompt
  - sentiment from a real distilBERT SST-2 model; urgency from a lexical signal
Speaker diarisation (pyannote) is deferred — it needs a free HF_TOKEN.

Idempotent: clips already in team_radio_clips (by recording_url) are skipped.
Bounded: only clips within RADIO_WINDOW_MIN of an incident's RC time are taken.
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.request
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
import psycopg2  # noqa: E402
from psycopg2.extras import execute_batch  # noqa: E402

from packages.pipeline.linkers.openf1_client import OpenF1Client  # noqa: E402

DB = os.environ["DATABASE_URL"]
RADIO_WINDOW_MIN = 8          # ± minutes around an incident's RC time
WHISPER_MODEL = os.environ.get("WHISPER_MODEL_SIZE", "base")
CACHE = Path("audio_cache")
CACHE.mkdir(exist_ok=True)

F1_PROMPT = (
    "F1 team radio. Drivers: Verstappen, Norris, Hamilton, Leclerc, Sainz, "
    "Russell, Alonso, Piastri, Gasly, Albon, Tsunoda, Perez, Stroll, Ocon. "
    "Terms: box box, undercut, delta, DRS, pit lane, safety car, virtual "
    "safety car, yellow flag, blue flag, sector, tyre, soft medium hard."
)

# Lexical urgency signal — fraction-weighted presence of high-urgency cues.
URGENCY_CUES = [
    "box box", "box now", "now now", "issue", "problem", "go go", "push push",
    "safety car", "yellow", "red flag", "stop", "damage", "puncture", "engine",
    "hurry", "quick", "immediately", "abort", "danger", "crash", "off",
]


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except Exception:
        return None


def urgency_score(text: str) -> float:
    """0..1 lexical urgency: cue hits + exclamation/caps density, squashed."""
    if not text:
        return 0.0
    low = text.lower()
    hits = sum(1 for c in URGENCY_CUES if c in low)
    excl = text.count("!")
    caps_words = sum(1 for w in text.split() if len(w) > 2 and w.isupper())
    raw = hits + 0.5 * excl + 0.3 * caps_words
    return round(min(1.0, raw / 4.0), 3)


def load_models():
    from faster_whisper import WhisperModel
    from transformers import pipeline
    print(f"loading whisper={WHISPER_MODEL} (int8 cpu) + distilbert sentiment...", flush=True)
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    sentiment = pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        device=-1,
    )
    return whisper, sentiment


def transcribe(whisper, url: str) -> str | None:
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    suffix = Path(url.split("?")[0]).suffix or ".mp3"
    path = CACHE / f"{url_hash}{suffix}"
    if not path.exists():
        try:
            urllib.request.urlretrieve(url, path)
        except Exception:
            return None
    try:
        segs, _ = whisper.transcribe(str(path), language="en", beam_size=5,
                                     vad_filter=True, initial_prompt=F1_PROMPT)
        return " ".join(s.text.strip() for s in segs).strip()
    except Exception:
        return None


def sentiment_score(sentiment, text: str) -> float | None:
    if not text or len(text.strip()) < 2:
        return None
    try:
        r = sentiment(text[:512])[0]
        s = float(r["score"])
        return round(s if r["label"] == "POSITIVE" else -s, 3)
    except Exception:
        return None


def main() -> None:
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    # Incidents with a real race-control time + the involved driver numbers.
    cur.execute("""
        SELECT i.incident_id, i.session_key, i.drivers,
               (SELECT min(r.date) FROM incident_race_control l
                JOIN race_control_messages r USING (message_id)
                WHERE l.incident_id = i.incident_id) AS rc_time
        FROM incidents i
        WHERE i.session_key IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.execute("SELECT recording_url FROM team_radio_clips")
    seen_urls = {r[0] for r in cur.fetchall()}
    conn.close()

    # (session_key, driver_number) -> list of (incident_id, rc_time)
    anchors: dict[tuple[int, int], list[tuple[str, datetime]]] = {}
    for iid, sk, drivers, rc_time in rows:
        if rc_time is None:
            continue
        if rc_time.tzinfo is None:
            rc_time = rc_time.replace(tzinfo=UTC)
        for d in drivers or []:
            num = d.get("number")
            if not isinstance(num, int):
                continue
            anchors.setdefault((sk, num), []).append((iid, rc_time))

    print(f"incident-anchored (session, driver) pairs: {len(anchors)}", flush=True)

    cli = OpenF1Client()
    whisper, sentiment = load_models()
    win = timedelta(minutes=RADIO_WINDOW_MIN)

    insert_rows: list[tuple] = []
    pairs = ok = clips_seen = 0
    for (sk, num), inc_list in sorted(anchors.items()):
        pairs += 1
        try:
            clips = cli.team_radio(session_key=sk, driver_number=num)
        except Exception:
            continue
        for clip in clips:
            url = clip.get("recording_url")
            cdt = _parse_dt(clip.get("date", ""))
            if not url or cdt is None or url in seen_urls:
                continue
            # nearest incident within the window
            near = [(abs((cdt - t).total_seconds()), iid) for iid, t in inc_list
                    if abs(cdt - t) <= win]
            if not near:
                continue
            seen_urls.add(url)
            clips_seen += 1
            incident_id = min(near)[1]
            text = transcribe(whisper, url)
            sent = sentiment_score(sentiment, text or "")
            urg = urgency_score(text or "")
            insert_rows.append((
                str(uuid.uuid4()), sk, num, cdt, url,
                text or None, None, sent, urg, incident_id,
            ))
            if text:
                ok += 1
        if pairs % 25 == 0:
            print(f"  {pairs}/{len(anchors)} pairs · {clips_seen} clips · {ok} transcribed", flush=True)

    if insert_rows:
        w = psycopg2.connect(DB)
        wc = w.cursor()
        execute_batch(wc, """
            INSERT INTO team_radio_clips
              (clip_id, session_key, driver_number, date, recording_url,
               transcript, speaker_label, sentiment_score, urgency_score, incident_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, insert_rows, page_size=200)
        w.commit()
        w.close()

    print(f"DONE — {clips_seen} incident-radio clips, {ok} transcribed, "
          f"{len(insert_rows)} rows inserted", flush=True)


if __name__ == "__main__":
    main()

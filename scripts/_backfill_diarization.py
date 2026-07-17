"""
Part 3b — Speaker diarisation backfill: fill team_radio_clips.speaker_label
with real driver / race-engineer labels.

Approach (real, no guessing of identities we can't support):
  1. pyannote/speaker-diarization-3.1 diarises each radio clip into speaker
     turns AND returns a voice embedding per speaker.
  2. Per driver, every one of *their* clips contains the driver's own voice, so
     that voice recurs across clips. We cluster all speaker embeddings for a
     driver into two groups; the group present in the most distinct clips is the
     driver, the other is the race engineer. This also resolves single-speaker
     clips (match the lone voice to the driver/engineer cluster).
  3. speaker_label per clip = "driver", "engineer", or "driver+engineer".

Requires HF_TOKEN (free) with access to:
  - pyannote/speaker-diarization-3.1
  - pyannote/segmentation-3.0
Reuses the audio already cached by the Part 3 ASR run. Idempotent.
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
import psycopg2  # noqa: E402
from psycopg2.extras import execute_batch  # noqa: E402

DB = os.environ["DATABASE_URL"]
TOKEN = os.environ.get("HF_TOKEN", "")
CACHE = Path("audio_cache")
CACHE.mkdir(exist_ok=True)


def cached_path(url: str) -> Path:
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    suffix = Path(url.split("?")[0]).suffix or ".mp3"
    return CACHE / f"{h}{suffix}"


def _load_waveform(path: Path):
    """Decode an mp3 to a 16 kHz mono waveform tensor via PyAV (bypasses the
    pyannote-4 torchcodec/FFmpeg decoder, which is broken in this env)."""
    import av
    import numpy as np
    import torch
    container = av.open(str(path))
    res = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    for frame in container.decode(audio=0):
        for rf in res.resample(frame):
            chunks.append(rf.to_ndarray())
    container.close()
    if not chunks:
        return None
    data = np.concatenate(chunks, axis=1).astype(np.float32) / 32768.0  # (1, N)
    return torch.from_numpy(data)


def diarise_clip(pipe, path: Path):
    """Return list of (speaker_label, embedding|None, talk_seconds) for a clip."""
    wav = _load_waveform(path)
    if wav is None:
        return []
    # pyannote 4.x returns a DiarizeOutput object (not a tuple).
    result = pipe({"waveform": wav, "sample_rate": 16000}, return_embeddings=True)
    diar = result.speaker_diarization
    emb = result.speaker_embeddings           # ndarray [n_speakers, dim], aligned to labels()
    labels = diar.labels()
    rows = []
    for j, lbl in enumerate(labels):
        e = emb[j] if emb is not None and j < len(emb) else None
        if e is not None and np.isnan(e).any():
            e = None
        rows.append((lbl, e, float(diar.label_duration(lbl))))
    return rows


def main() -> None:
    if not TOKEN:
        print("HF_TOKEN not set. Add HF_TOKEN=hf_... to .env after accepting the "
              "pyannote/speaker-diarization-3.1 + pyannote/segmentation-3.0 terms.")
        return

    from pyannote.audio import Pipeline
    try:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=TOKEN)
    except TypeError:  # older pyannote uses use_auth_token
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                                        use_auth_token=TOKEN)
    if pipe is None:
        print("Pipeline load returned None — token invalid OR model terms not "
              "accepted for BOTH pyannote/speaker-diarization-3.1 and "
              "pyannote/segmentation-3.0.")
        return

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute("""SELECT clip_id, driver_number, recording_url
                   FROM team_radio_clips WHERE transcript IS NOT NULL
                   ORDER BY driver_number, date""")
    clips = cur.fetchall()
    conn.close()
    print(f"diarising {len(clips)} clips...", flush=True)

    # Resumable: cache the (expensive) per-clip diarisation to disk so a kill
    # mid-run doesn't lose work. Embeddings are small numpy arrays.
    import pickle
    cache_f = Path("data/linked/_diar_cache.pkl")
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    clip_specs: dict[str, list] = {}     # clip_id -> [(label, emb, dur)]
    if cache_f.exists():
        try:
            clip_specs = pickle.loads(cache_f.read_bytes())
        except Exception:
            clip_specs = {}
    if clip_specs:
        print(f"  resuming: {len(clip_specs)} clips already diarised (cached)", flush=True)

    for i, (cid, dnum, url) in enumerate(clips, 1):
        if cid in clip_specs:
            continue
        path = cached_path(url)
        if not path.exists():
            try:
                urllib.request.urlretrieve(url, path)
            except Exception:
                clip_specs[cid] = []
                continue
        try:
            clip_specs[cid] = diarise_clip(pipe, path)
        except Exception as exc:  # noqa: BLE001
            clip_specs[cid] = []
            if i <= 3:
                print(f"  diarise fail {cid}: {type(exc).__name__}: {exc}", flush=True)
        if i % 25 == 0:
            cache_f.write_bytes(pickle.dumps(clip_specs))
            print(f"  {i}/{len(clips)} diarised (cached)", flush=True)
    cache_f.write_bytes(pickle.dumps(clip_specs))

    by_driver: dict[int, list[str]] = defaultdict(list)
    for cid, dnum, url in clips:
        if clip_specs.get(cid):
            by_driver[dnum].append(cid)

    # Cross-clip clustering per driver -> role for each (clip_id, label).
    from sklearn.cluster import AgglomerativeClustering
    role: dict[tuple[str, str], str] = {}
    for dnum, cids in by_driver.items():
        items = [(cid, lbl, e)
                 for cid in cids for (lbl, e, _) in clip_specs[cid] if e is not None]
        distinct_clips = {c for c, _, _ in items}
        if len(items) < 2 or len(distinct_clips) < 2:
            continue
        X = np.vstack([e for _, _, e in items])
        try:
            lab = AgglomerativeClustering(
                n_clusters=2, metric="cosine", linkage="average").fit(X).labels_
        except Exception:
            continue
        clips_in = {0: set(), 1: set()}
        for (cid, _, _), c in zip(items, lab):
            clips_in[int(c)].add(cid)
        driver_cluster = 0 if len(clips_in[0]) >= len(clips_in[1]) else 1
        for (cid, lbl, _), c in zip(items, lab):
            role[(cid, lbl)] = "driver" if int(c) == driver_cluster else "engineer"

    # Decide a single speaker_label per clip.
    updates: list[tuple[str, str]] = []
    for cid, dnum, url in clips:
        specs = clip_specs.get(cid, [])
        if not specs:
            continue
        present = set()
        for (lbl, e, dur) in specs:
            r = role.get((cid, lbl))
            present.add(r)
        present.discard(None)
        if not present:
            # Fallback: 2-speaker clip -> shorter talk-time = driver; else single.
            if len(specs) >= 2:
                label = "driver+engineer"
            else:
                label = "single_speaker"
        elif present == {"driver", "engineer"}:
            label = "driver+engineer"
        else:
            label = present.pop()
        updates.append((label, cid))

    if updates:
        w = psycopg2.connect(DB)
        wc = w.cursor()
        execute_batch(wc, "UPDATE team_radio_clips SET speaker_label=%s WHERE clip_id=%s",
                      updates, page_size=200)
        w.commit()
        wc.execute("""SELECT speaker_label, count(*) FROM team_radio_clips
                      WHERE speaker_label IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""")
        print("speaker_label distribution:", wc.fetchall(), flush=True)
        w.close()
    print(f"DONE — {len(updates)} clips labelled", flush=True)


if __name__ == "__main__":
    main()

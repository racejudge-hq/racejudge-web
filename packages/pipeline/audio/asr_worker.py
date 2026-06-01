"""
ASR Worker — Phase 3.

Celery task: transcribe a team radio clip using faster-whisper (CTranslate2).

Model: faster-whisper Large-V3 with F1 vocabulary boosting.
Target WER: < 12% on F1 radio test set.

F1 vocabulary additions (injected as hotwords/initial_prompt):
  - Driver surnames (Verstappen, Norris, Hamilton, etc.)
  - Common F1 phrases: "box box", "blue flag", "undercut", "delta", "DRS",
    "safety car", "virtual safety car", "pit lane", "sector"
  - Circuit corner names: "Eau Rouge", "Raidillon", "Copse", "Maggotts"

Usage:
    from packages.pipeline.audio.asr_worker import transcribe_clip_task
    result = transcribe_clip_task.delay(clip_id="...", audio_path="/path/to/clip.mp3")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from packages.pipeline.workers.celery_app import app

log = logging.getLogger(__name__)

MODEL_SIZE   = os.environ.get("WHISPER_MODEL_SIZE", "large-v3")
DEVICE       = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

# F1 domain vocabulary — injected as initial_prompt to boost recognition
F1_INITIAL_PROMPT = (
    "F1 team radio. Drivers: Verstappen, Norris, Hamilton, Leclerc, Sainz, "
    "Russell, Alonso, Piastri, Gasly, Albon, Tsunoda, Lawson, Antonelli. "
    "Terms: box box, undercut, delta, DRS, ERS, MGU-K, pit lane, safety car, "
    "virtual safety car, yellow flag, blue flag, sector, lap time, tire compound, "
    "soft medium hard intermediate wet."
)


def _load_model():
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
        log.info("Whisper %s loaded (device=%s, compute=%s)", MODEL_SIZE, DEVICE, COMPUTE_TYPE)
        return model
    except ImportError as exc:
        raise RuntimeError("faster-whisper not installed. pip install faster-whisper") from exc


_model = None


def _get_model():
    global _model
    if _model is None:
        _model = _load_model()
    return _model


def transcribe_audio(audio_path: str | Path) -> dict:
    """
    Transcribe an audio file.

    Returns:
        {text, language, segments: [{start, end, text, speaker}], duration_s}
    """
    model = _get_model()
    path  = Path(audio_path)

    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    segments_iter, info = model.transcribe(
        str(path),
        language="en",
        beam_size=5,
        vad_filter=True,
        initial_prompt=F1_INITIAL_PROMPT,
        word_timestamps=False,
    )

    segments = []
    full_text_parts = []
    for seg in segments_iter:
        text = seg.text.strip()
        segments.append({
            "start": round(seg.start, 2),
            "end":   round(seg.end, 2),
            "text":  text,
        })
        full_text_parts.append(text)

    return {
        "text":       " ".join(full_text_parts),
        "language":   info.language,
        "segments":   segments,
        "duration_s": round(info.duration, 1),
    }


@app.task(
    name="packages.pipeline.audio.asr_worker.transcribe_clip_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="default",
    time_limit=600,
    soft_time_limit=540,
)
def transcribe_clip_task(self, clip_id: str, audio_path: str) -> dict:
    """
    Celery task: transcribe a team radio clip and update the DB record.

    Args:
        clip_id:    UUID from team_radio_clips table.
        audio_path: Local path to the audio file.

    Returns:
        {clip_id, transcript, language, duration_s, status}
    """
    log.info("Transcribing clip %s: %s", clip_id, audio_path)

    try:
        result = transcribe_audio(audio_path)
    except Exception as exc:
        log.error("Transcription failed for clip %s: %s", clip_id, exc)
        raise self.retry(exc=exc) from exc

    transcript = result["text"]
    log.info("Clip %s transcribed: %d chars", clip_id, len(transcript))

    # Update DB if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        _update_db_transcript(clip_id, transcript, database_url)

    return {
        "clip_id":    clip_id,
        "transcript": transcript,
        "language":   result["language"],
        "duration_s": result["duration_s"],
        "status":     "complete",
    }


def _update_db_transcript(clip_id: str, transcript: str, database_url: str) -> None:
    """Sync DB update for transcript (uses psycopg2 for simplicity in Celery context)."""
    try:
        import psycopg2
        conn = psycopg2.connect(database_url)
        cur  = conn.cursor()
        cur.execute(
            "UPDATE team_radio_clips SET transcript = %s WHERE clip_id = %s",
            (transcript, clip_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        log.error("DB update failed for clip %s: %s", clip_id, exc)


@app.task(
    name="packages.pipeline.audio.asr_worker.batch_transcribe_session_task",
    bind=True,
    queue="bulk",
    max_retries=1,
)
def batch_transcribe_session_task(self, session_key: int) -> dict:
    """
    Batch transcribe all un-transcribed clips for a session.
    Spawns individual transcribe_clip_task per clip.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    try:
        import psycopg2
        conn = psycopg2.connect(database_url)
        cur  = conn.cursor()
        cur.execute(
            "SELECT clip_id, r2_key FROM team_radio_clips "
            "WHERE session_key = %s AND transcript IS NULL",
            (session_key,),
        )
        clips = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as exc:
        log.error("Batch transcribe DB query failed: %s", exc)
        return {"error": str(exc)}

    log.info("Queuing %d clips for session %d", len(clips), session_key)
    for clip_id, r2_key in clips:
        audio_cache = Path(__file__).resolve().parents[3] / "audio_cache"
        local_path  = audio_cache / Path(r2_key or clip_id).name if r2_key else None
        if local_path and local_path.exists():
            transcribe_clip_task.apply_async(
                args=[str(clip_id), str(local_path)],
                queue="default",
            )
        else:
            log.warning("Audio file not cached for clip %s — skipping", clip_id)

    return {"session_key": session_key, "queued": len(clips)}

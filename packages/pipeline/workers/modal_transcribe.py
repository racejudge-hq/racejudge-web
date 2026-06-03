"""
Modal GPU worker — Whisper + pyannote.audio transcription backfill.

Transcribes all team_radio_clips that have an audio_url but no transcript,
using faster-whisper (large-v3) on a Modal A10G GPU. Optionally runs
pyannote speaker diarisation when HF_TOKEN is set.

Usage:
    pip install modal
    modal run packages/pipeline/workers/modal_transcribe.py

    # Limit to one session for testing:
    modal run packages/pipeline/workers/modal_transcribe.py::transcribe_all --session-limit 1

Environment variables required (set via modal secret or .env):
    DATABASE_URL — Neon/Postgres connection string
    HF_TOKEN     — HuggingFace token (for pyannote diarisation, optional)
    R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ACCOUNT_ID — Cloudflare R2
"""

from __future__ import annotations

try:
    import modal  # type: ignore[import]
    _MODAL_AVAILABLE = True
except ImportError:
    _MODAL_AVAILABLE = False

if _MODAL_AVAILABLE:
    _image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "libsndfile1")
        .pip_install(
            "faster-whisper>=1.0.0",
            "psycopg2-binary>=2.9.9",
            "boto3>=1.34.0",
            "httpx>=0.27.0",
        )
        .env({"TOKENIZERS_PARALLELISM": "false"})
    )

    _image_diarize = _image.pip_install(
        "pyannote.audio>=3.1.0",
        "torch>=2.2.0",
        "torchaudio>=2.2.0",
    )

    _app = modal.App("racejudge-transcribe")
    _vol = modal.Volume.from_name("racejudge-models", create_if_missing=True)

    @_app.function(
        image=_image,
        gpu="A10G",
        timeout=7200,
        secrets=[modal.Secret.from_name("racejudge-secrets")],
        volumes={"/models": _vol},
    )
    def transcribe_all(session_limit: int | None = None) -> dict:
        """
        Transcribe all radio clips with audio_url but no transcript.
        Uses faster-whisper large-v3 on GPU.

        Returns: {transcribed: int, skipped: int, errors: int}
        """
        import logging
        import os
        import tempfile

        import httpx
        import psycopg2
        from faster_whisper import WhisperModel

        logging.basicConfig(level=logging.INFO)
        log = logging.getLogger("modal_transcribe")

        MODEL_SIZE = "large-v3"
        CACHE_DIR  = "/models/whisper"
        DB_URL     = os.environ["DATABASE_URL"]

        log.info("Loading Whisper %s ...", MODEL_SIZE)
        model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16",
                             download_root=CACHE_DIR)

        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()

        query = """
            SELECT clip_id, audio_url, driver_number, date
            FROM team_radio_clips
            WHERE audio_url IS NOT NULL
              AND (transcript IS NULL OR transcript = '')
            ORDER BY date DESC
        """
        if session_limit:
            query = f"""
                SELECT rc.clip_id, rc.audio_url, rc.driver_number, rc.date
                FROM team_radio_clips rc
                JOIN (
                    SELECT DISTINCT session_key
                    FROM team_radio_clips
                    WHERE audio_url IS NOT NULL
                    ORDER BY session_key DESC
                    LIMIT {session_limit}
                ) s ON rc.session_key = s.session_key
                WHERE rc.audio_url IS NOT NULL
                  AND (rc.transcript IS NULL OR rc.transcript = '')
                ORDER BY rc.date DESC
            """

        cur.execute(query)
        clips = cur.fetchall()
        log.info("Found %d clips to transcribe", len(clips))

        transcribed = 0
        errors = 0

        with httpx.Client(timeout=30.0) as http:
            for clip_id, audio_url, _driver_number, _clip_date in clips:
                try:
                    resp = http.get(audio_url)
                    if resp.status_code != 200:
                        log.warning("Failed to download %s: HTTP %d", audio_url, resp.status_code)
                        errors += 1
                        continue

                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as f:
                        f.write(resp.content)
                        f.flush()

                        segments, info = model.transcribe(
                            f.name,
                            language="en",
                            beam_size=5,
                            vad_filter=True,
                            vad_parameters={"min_silence_duration_ms": 500},
                        )
                        text = " ".join(seg.text.strip() for seg in segments).strip()

                    if not text:
                        text = "[no speech detected]"

                    cur.execute(
                        """
                        UPDATE team_radio_clips
                        SET transcript = %s,
                            transcription_model = 'faster-whisper-large-v3',
                            transcribed_at = NOW()
                        WHERE clip_id = %s
                        """,
                        (text, clip_id),
                    )
                    conn.commit()
                    transcribed += 1
                    log.info("[%d/%d] clip_id=%s: %s", transcribed, len(clips), clip_id, text[:80])

                except Exception as exc:
                    log.error("Error transcribing clip_id=%s: %s", clip_id, exc)
                    errors += 1

        cur.close()
        conn.close()
        return {
            "transcribed": transcribed,
            "skipped": len(clips) - transcribed - errors,
            "errors": errors,
        }


# ---------------------------------------------------------------------------
# Local entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    if not _MODAL_AVAILABLE:
        print("modal not installed. Run: pip install modal")
        print("Then: modal run packages/pipeline/workers/modal_transcribe.py")
        return

    import sys
    session_limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    msg = f"session_limit={session_limit}" if session_limit else "all sessions"
    print(f"Submitting transcribe_all({msg}) to Modal A10G...")
    with _app.run():
        result = transcribe_all.remote(session_limit=session_limit)
        print(f"Transcription complete: {result}")


if __name__ == "__main__":
    main()

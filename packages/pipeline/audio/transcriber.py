"""
Audio transcription pipeline — Phase 3.

Transcribes team radio audio using Faster-Whisper (CTranslate2 backend)
with optional pyannote speaker diarization.

Audio sources:
  - OpenF1 /team_radio endpoint returns clip_identifier URLs
  - Files are downloaded to audio_cache/ (gitignored)

Usage:
    from packages.pipeline.audio.transcriber import Transcriber
    t = Transcriber(model_size="base")
    result = t.transcribe_clip("path/to/clip.mp3")
    # result = {"text": "...", "segments": [...], "language": "en"}

Dependencies (uncomment in requirements.txt when starting Phase 3):
    faster-whisper>=1.0.0
    pyannote.audio>=3.1.0   # requires HF token: HF_TOKEN env var
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
AUDIO_CACHE_DIR = ROOT / "audio_cache"
AUDIO_CACHE_DIR.mkdir(exist_ok=True)

log = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass
class TranscriptResult:
    clip_path: str
    language: str
    text: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration_s: float = 0.0


def _require_faster_whisper():
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except ImportError as exc:
        raise ImportError(
            "faster-whisper not installed. Uncomment faster-whisper>=1.0.0 "
            "in requirements.txt and run: pip install -r requirements.txt"
        ) from exc


def _require_pyannote():
    try:
        from pyannote.audio import Pipeline
        return Pipeline
    except ImportError as exc:
        raise ImportError(
            "pyannote.audio not installed. Uncomment pyannote.audio>=3.1.0 "
            "in requirements.txt and run: pip install -r requirements.txt\n"
            "Also set HF_TOKEN env var (requires pyannote model access on HuggingFace)"
        ) from exc


class Transcriber:
    """
    Whisper-based transcriber for F1 team radio clips.

    model_size: "tiny", "base", "small", "medium", "large-v3"
    device: "cpu" or "cuda" (auto-detected if not specified)
    compute_type: "int8" (CPU), "float16" (GPU), "float32"
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "int8",
        cache_dir: Path = AUDIO_CACHE_DIR,
    ):
        WhisperModel = _require_faster_whisper()
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        log.info("Loading Whisper model=%s device=%s compute_type=%s", model_size, device, compute_type)
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._cache_dir = cache_dir
        self._diarizer: Any = None

    def enable_diarization(self, hf_token: str | None = None) -> None:
        """
        Load pyannote speaker diarization pipeline.
        Requires HuggingFace token with access to pyannote/speaker-diarization-3.1.
        """
        Pipeline = _require_pyannote()
        token = hf_token or os.environ.get("HF_TOKEN")
        if not token:
            raise ValueError("HF_TOKEN env var required for pyannote diarization")
        self._diarizer = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
        log.info("Pyannote diarization pipeline loaded")

    def transcribe_clip(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> TranscriptResult:
        """
        Transcribe a single audio clip.
        Returns TranscriptResult with text + per-segment detail.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        segments_raw, info = self._model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []

        for seg in segments_raw:
            segments.append(TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                avg_logprob=seg.avg_logprob,
                no_speech_prob=seg.no_speech_prob,
            ))
            full_text_parts.append(seg.text.strip())

        result = TranscriptResult(
            clip_path=str(audio_path),
            language=info.language,
            text=" ".join(full_text_parts),
            segments=segments,
            duration_s=info.duration,
        )

        if self._diarizer is not None:
            result = self._apply_diarization(result, audio_path)

        return result

    def _apply_diarization(self, result: TranscriptResult, audio_path: Path) -> TranscriptResult:
        """Assign speaker labels to transcript segments via pyannote."""
        diarization = self._diarizer(str(audio_path))

        # Build (start, end, speaker) timeline from pyannote
        speaker_timeline: list[tuple[float, float, str]] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_timeline.append((turn.start, turn.end, speaker))

        for seg in result.segments:
            (seg.start + seg.end) / 2.0
            best_speaker = None
            best_overlap = 0.0
            for s_start, s_end, speaker in speaker_timeline:
                overlap = min(seg.end, s_end) - max(seg.start, s_start)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker
            seg.speaker = best_speaker

        return result

    def transcribe_url(
        self,
        url: str,
        *,
        session_key: int | None = None,
        driver_number: int | None = None,
        **kwargs,
    ) -> TranscriptResult:
        """
        Download and transcribe an audio clip from a URL.
        Caches downloaded files by URL hash to avoid re-downloading.
        """
        import hashlib
        import urllib.request

        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        suffix = Path(urlparse(url).path).suffix or ".mp3"
        cached_path = self._cache_dir / f"{url_hash}{suffix}"

        if not cached_path.exists():
            log.info("Downloading audio: %s", url)
            urllib.request.urlretrieve(url, cached_path)
            log.info("Saved: %s", cached_path.name)
        else:
            log.debug("Cache hit: %s", cached_path.name)

        return self.transcribe_clip(cached_path, **kwargs)


def batch_transcribe_session(
    session_key: int,
    model_size: str = "base",
    *,
    limit: int | None = None,
    hf_token: str | None = None,
) -> list[dict]:
    """
    Transcribe all team radio clips for an OpenF1 session.
    Requires openf1_client to be importable.
    Returns list of dicts with driver, time, text, segments.
    """
    from packages.pipeline.linkers.openf1_client import OpenF1Client

    client = OpenF1Client()
    radios = client.team_radio(session_key=session_key)

    if limit:
        radios = radios[:limit]

    transcriber = Transcriber(model_size=model_size)
    if hf_token or os.environ.get("HF_TOKEN"):
        transcriber.enable_diarization(hf_token)

    results = []
    for radio in radios:
        url = radio.get("recording_url") or radio.get("clip_identifier")
        if not url:
            continue
        try:
            result = transcriber.transcribe_url(
                url,
                session_key=session_key,
                driver_number=radio.get("driver_number"),
            )
            results.append({
                "session_key": session_key,
                "driver_number": radio.get("driver_number"),
                "date": radio.get("date"),
                "recording_url": url,
                "language": result.language,
                "text": result.text,
                "duration_s": result.duration_s,
                "segments": [
                    {
                        "start": s.start,
                        "end": s.end,
                        "text": s.text,
                        "speaker": s.speaker,
                    }
                    for s in result.segments
                ],
            })
        except Exception as exc:
            log.warning("Failed to transcribe %s: %s", url, exc)

    return results

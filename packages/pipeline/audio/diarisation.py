"""
Speaker Diarisation — Phase 3.

Uses pyannote.audio v3 to label each speaker turn in team radio clips as:
  driver | engineer | other

Architecture:
  - pyannote/speaker-diarization-3.1 (requires HF_TOKEN)
  - Post-processing: 2-speaker assumption (driver + engineer)
  - Label assignment: shorter speech turns = driver (radio side); longer = engineer

Integrated with ASR: run diarisation after Whisper, then align segments.

Usage:
    diariser = Diariser()
    result = diariser.diarise(audio_path)
    # result = [{start, end, speaker: 'SPEAKER_00'}, ...]

    # Full pipeline: transcribe + diarise + label
    labelled = diariser.transcribe_and_label(audio_path, transcript_segments)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

HF_TOKEN = os.environ.get("HF_TOKEN", "")


class Diariser:
    """
    pyannote.audio v3 speaker diarisation.

    Lazy-loads pipeline on first use. Falls back gracefully if HF_TOKEN
    is absent or pyannote is not installed.
    """

    def __init__(self, hf_token: str | None = None, num_speakers: int = 2):
        self._token       = hf_token or HF_TOKEN
        self._num_speakers = num_speakers
        # Typed Any: pyannote is an optional dep, so its symbols resolve to Any
        # when it is absent. Annotating here keeps mypy consistent whether or
        # not pyannote is installed (CI does not install it).
        self._pipeline: Any = None

    def _load(self) -> bool:
        if self._pipeline is not None:
            return True
        if not self._token:
            log.info(
                "HF_TOKEN not set — diarisation disabled. "
                "Set HF_TOKEN=hf_... in .env (requires pyannote/speaker-diarization-3.1 access)."
            )
            return False
        try:
            from pyannote.audio import Pipeline

            # pyannote 4.x renamed `use_auth_token` → `token`; 3.x only accepts
            # the old name. Try the current spelling first, fall back for 3.x.
            try:
                self._pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=self._token,
                )
            except TypeError:
                self._pipeline = Pipeline.from_pretrained(  # type: ignore[call-arg]
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self._token,
                )
            log.info("pyannote diarisation pipeline loaded")
            return True
        except ImportError:
            log.warning("pyannote.audio not installed — pip install pyannote.audio")
            return False
        except Exception as exc:
            log.error("Diarisation pipeline load failed: %s", exc)
            return False

    def diarise(self, audio_path: str | Path) -> list[dict]:
        """
        Run speaker diarisation on an audio file.

        Returns:
            List of {start, end, speaker} dicts. Empty list if unavailable.
        """
        if not self._load():
            return []

        path = Path(audio_path)
        if not path.exists():
            log.warning("Diarisation: audio not found: %s", path)
            return []

        try:
            diarization = self._pipeline(  # type: ignore[misc]
                str(path),
                num_speakers=self._num_speakers,
            )
            return [
                {
                    "start":   round(turn.start, 3),
                    "end":     round(turn.end, 3),
                    "speaker": str(speaker),
                }
                for turn, _, speaker in diarization.itertracks(yield_label=True)
            ]
        except Exception as exc:
            log.error("Diarisation failed for %s: %s", path.name, exc)
            return []

    def assign_labels(self, diar_segments: list[dict]) -> dict[str, str]:
        """
        Map SPEAKER_00/SPEAKER_01 to driver/engineer.

        Heuristic: in F1 team radio, the driver speaks less (shorter turns,
        one side of the radio). Engineer speaks more (longer, more turns).

        Returns: {"SPEAKER_00": "driver", "SPEAKER_01": "engineer"}
        """
        if not diar_segments:
            return {}

        duration_by_speaker: dict[str, float] = {}
        for seg in diar_segments:
            spk = seg["speaker"]
            dur = seg["end"] - seg["start"]
            duration_by_speaker[spk] = duration_by_speaker.get(spk, 0) + dur

        # Speaker with less total speech = driver (driver is on the radio, shorter)
        speakers = sorted(duration_by_speaker.items(), key=lambda x: x[1])
        labels: dict[str, str] = {}
        for i, (spk, _) in enumerate(speakers):
            if i == 0:
                labels[spk] = "driver"
            elif i == 1:
                labels[spk] = "engineer"
            else:
                labels[spk] = "other"
        return labels

    def transcribe_and_label(
        self,
        audio_path: str | Path,
        transcript_segments: list[dict],
    ) -> list[dict]:
        """
        Align diarisation output with Whisper transcript segments.

        Args:
            audio_path:           Path to audio file.
            transcript_segments:  List of {start, end, text} from Whisper.

        Returns:
            List of {start, end, text, speaker_label} — 'driver'/'engineer'/'other'/None.
        """
        diar_segs = self.diarise(audio_path)
        if not diar_segs:
            return [
                {**seg, "speaker_label": None}
                for seg in transcript_segments
            ]

        speaker_map = self.assign_labels(diar_segs)

        def _find_speaker(start: float, end: float) -> str | None:
            mid = (start + end) / 2
            best_overlap = 0.0
            best_speaker = None
            for d in diar_segs:
                overlap_start = max(mid - 0.5, d["start"])
                overlap_end   = min(mid + 0.5, d["end"])
                overlap = max(0.0, overlap_end - overlap_start)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = d["speaker"]
            return speaker_map.get(best_speaker) if best_speaker else None

        return [
            {
                **seg,
                "speaker_label": _find_speaker(seg["start"], seg["end"]),
            }
            for seg in transcript_segments
        ]

    def is_available(self) -> bool:
        return self._pipeline is not None or self._load()

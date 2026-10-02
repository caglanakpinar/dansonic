from __future__ import annotations

from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


class MoveSoundboard:
    """Plays the sound mapped to a matched move, at a rate that reflects how
    much faster/slower the move was performed versus its recorded template
    (so a snappier repeat of the move plays a snappier sound), clamped to
    stay recognizable.
    """

    def __init__(self, min_rate: float = 0.7, max_rate: float = 1.5):
        self._min_rate = min_rate
        self._max_rate = max_rate
        self._cache: dict[Path, tuple[np.ndarray, int]] = {}

    def _load(self, path: Path) -> tuple[np.ndarray, int]:
        if path not in self._cache:
            self._cache[path] = sf.read(str(path), dtype="float32", always_2d=True)
        return self._cache[path]

    def play(self, sound_path: Path, duration_ratio: float = 1.0) -> None:
        audio, samplerate = self._load(sound_path)
        rate = float(np.clip(duration_ratio, self._min_rate, self._max_rate))
        sd.stop()
        sd.play(audio, samplerate=samplerate * rate)

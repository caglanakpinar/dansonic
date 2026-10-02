from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


class ReactiveClipPlayer:
    """Loops a reference clip continuously, with playback speed (and
    therefore pitch, turntable style) driven live by the current motion
    signal: call `update()` as often as new motion comes in and the sound
    just follows it, no trigger or threshold needed.
    """

    def __init__(
        self,
        clip_path: str | Path,
        base_rate: float = 1.0,
        min_rate: float = 0.5,
        max_rate: float = 2.0,
        velocity_to_rate: float = 1.0,
    ):
        audio, samplerate = sf.read(str(clip_path), dtype="float32", always_2d=True)
        self._audio = audio
        self._samplerate = samplerate
        self._base_rate = base_rate
        self._min_rate = min_rate
        self._max_rate = max_rate
        self._velocity_to_rate = velocity_to_rate

        self._lock = threading.Lock()
        self._rate = base_rate
        self._read_pos = 0.0
        self._stream: sd.OutputStream | None = None

    def rate_for_velocity(self, velocity: float) -> float:
        rate = self._base_rate + velocity * self._velocity_to_rate
        return float(np.clip(rate, self._min_rate, self._max_rate))

    def update(self, velocity: float) -> None:
        """Feed in the latest motion sample; the stream's playback rate
        picks it up on its very next audio callback."""
        with self._lock:
            self._rate = self.rate_for_velocity(velocity)

    def _callback(self, outdata, frames, time_info, status) -> None:
        with self._lock:
            rate = self._rate
        n = len(self._audio)
        idx = (self._read_pos + np.arange(frames) * rate) % n
        idx_floor = idx.astype(np.int64)
        idx_ceil = (idx_floor + 1) % n
        frac = (idx - idx_floor)[:, None]
        outdata[:] = (1 - frac) * self._audio[idx_floor] + frac * self._audio[idx_ceil]
        self._read_pos = (self._read_pos + frames * rate) % n

    def start(self) -> None:
        self._stream = sd.OutputStream(
            samplerate=self._samplerate,
            channels=self._audio.shape[1],
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from moviepy.editor import VideoFileClip


@dataclass
class VideoAudio:
    """A video's audio track, plus the source clip's fps/duration so
    segment boundaries found in the video's frame timeline can be mapped
    onto audio sample indices.
    """

    samples: np.ndarray  # shape (n_samples, n_channels), float32
    samplerate: int
    fps: float
    duration: float

    def slice(self, start: float, end: float) -> np.ndarray:
        start_idx = max(0, int(start * self.samplerate))
        end_idx = min(len(self.samples), int(end * self.samplerate))
        return self.samples[start_idx:end_idx]


def load_video_audio(video_path: str | Path) -> VideoAudio:
    """Loads the audio track embedded in `video_path` (e.g. a dance clip
    filmed with music playing) as float32 samples.
    """
    with VideoFileClip(str(video_path)) as clip:
        if clip.audio is None:
            raise ValueError(f"{video_path} has no audio track")
        samplerate = int(clip.audio.fps)
        duration = clip.duration
        fps = clip.fps
        # moviepy 1.0.3's to_soundarray passes a generator to np.vstack when
        # the clip is longer than its internal buffer, which recent numpy
        # rejects; a buffer sized to cover the whole clip skips that path.
        buffersize = int(samplerate * (duration + 1))
        samples = clip.audio.to_soundarray(fps=samplerate, buffersize=buffersize).astype("float32")
    return VideoAudio(samples=samples, samplerate=samplerate, fps=fps, duration=duration)

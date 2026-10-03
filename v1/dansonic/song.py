"""Song metadata and beat grid helpers."""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SongInfo:
    sr: int
    duration: float
    bpm: float
    beat_offset: float          # seconds of an arbitrary beat on the grid
    downbeat_index: int = 0     # which beat (mod 4) counting from beat_offset is a downbeat
    stems: dict = field(default_factory=dict)   # name -> wav path
    samples: dict = field(default_factory=dict) # name -> wav path

    @property
    def beat_period(self) -> float:
        return 60.0 / self.bpm

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text())
        return cls(**data)

    def save(self, path):
        Path(path).write_text(json.dumps(self.__dict__, indent=2))


class BeatGrid:
    """Maps sample positions to a fixed-tempo grid."""

    def __init__(self, sr: int, bpm: float, beat_offset: float, downbeat_index: int = 0):
        self.sr = sr
        self.beat_frames = sr * 60.0 / bpm
        self.offset_frames = beat_offset * sr
        self.downbeat_index = downbeat_index

    def next_grid_frame(self, pos: int, subdivision: int) -> int:
        """First grid point (subdivision per beat) at or after pos."""
        if subdivision <= 0:
            return pos
        period = self.beat_frames / subdivision
        k = math.ceil((pos - self.offset_frames) / period)
        return int(round(self.offset_frames + k * period))

    def beat_index(self, pos: int) -> int:
        """Beat count from offset, may be negative before the first beat."""
        return math.floor((pos - self.offset_frames) / self.beat_frames)

    def beat_in_bar(self, pos: int) -> int:
        return (self.beat_index(pos) - self.downbeat_index) % 4

    def beat_phase(self, pos: int) -> float:
        """0.0 on the beat, growing to 1.0 just before the next beat."""
        return ((pos - self.offset_frames) / self.beat_frames) % 1.0

    def beats_to_frames(self, beats: float) -> int:
        return int(round(beats * self.beat_frames))

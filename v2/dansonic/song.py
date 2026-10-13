"""Beat grid helpers."""
import math


class BeatGrid:
    """Maps sample positions to a fixed-tempo grid."""

    def __init__(self, sr: int, bpm: float, beat_offset: float, downbeat_index: int = 0):
        self.sr = sr
        self.beat_frames = sr * 60.0 / bpm
        self.offset_frames = beat_offset * sr
        self.downbeat_index = downbeat_index

    def next_grid_frame(self, pos: int, subdivision: int) -> int:
        """First grid point (subdivision per beat) at or after pos. A negative subdivision is a number of beats
        instead: -4 is the start of the next bar."""
        if subdivision == 0:
            return pos
        period = self.beat_frames * -subdivision if subdivision < 0 else self.beat_frames / subdivision
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

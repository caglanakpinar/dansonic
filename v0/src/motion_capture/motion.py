from collections import deque
from dataclasses import dataclass


@dataclass
class MotionSample:
    velocity: float  # normalized frame-heights per second, positive = rising
    y: float
    timestamp: float


class VerticalMotionTracker:
    """Tracks the vertical velocity of a point (e.g. a hand landmark) across
    frames, in normalized image-coordinate units per second.

    MediaPipe's y grows downward, so a rising hand produces a negative dy;
    we flip the sign so "rising" is always a positive velocity.
    """

    def __init__(self, history: int = 5):
        self._history: deque[tuple[float, float]] = deque(maxlen=history)

    def update(self, y: float, timestamp: float) -> MotionSample:
        self._history.append((timestamp, y))
        velocity = 0.0
        if len(self._history) >= 2:
            t0, y0 = self._history[0]
            t1, y1 = self._history[-1]
            dt = t1 - t0
            if dt > 0:
                velocity = -(y1 - y0) / dt
        return MotionSample(velocity=velocity, y=y, timestamp=timestamp)

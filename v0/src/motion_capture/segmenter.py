from __future__ import annotations

from dataclasses import dataclass, field

from motion_capture.hand_tracker import HandLandmark
from motion_capture.motion import MotionSample, VerticalMotionTracker


@dataclass
class MotionSegment:
    index: int
    start: float
    end: float
    peak_velocity: float
    samples: list[MotionSample] = field(default_factory=list)


def segment_motion(
    landmarks: list[HandLandmark],
    velocity_threshold: float = 0.4,
    min_gap: float = 0.15,
) -> list[MotionSegment]:
    """Splits a full hand-position timeline into discrete rising-hand
    figures: a segment starts the moment upward velocity crosses
    `velocity_threshold` and ends once it drops back below threshold and
    stays there for at least `min_gap` seconds, so a single raise doesn't
    get chopped into several segments by frame-to-frame noise.
    """
    tracker = VerticalMotionTracker()
    samples = [tracker.update(lm.y, lm.timestamp) for lm in landmarks]

    segments: list[MotionSegment] = []
    active: MotionSegment | None = None
    last_above = -float("inf")

    for sample in samples:
        rising = sample.velocity >= velocity_threshold
        if rising:
            if active is None:
                active = MotionSegment(
                    index=len(segments),
                    start=sample.timestamp,
                    end=sample.timestamp,
                    peak_velocity=sample.velocity,
                )
            active.end = sample.timestamp
            active.peak_velocity = max(active.peak_velocity, sample.velocity)
            active.samples.append(sample)
            last_above = sample.timestamp
        elif active is not None:
            active.samples.append(sample)
            if sample.timestamp - last_above >= min_gap:
                segments.append(active)
                active = None

    if active is not None:
        segments.append(active)

    return segments

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from motion_capture.move_library import MoveLibrary
from motion_capture.pose_tracker import PoseFrame

_RESAMPLE_STEPS = 20


def _resample(frames: list[PoseFrame], steps: int = _RESAMPLE_STEPS) -> np.ndarray:
    """Resamples a variable-length pose sequence to a fixed number of time
    steps (evenly spaced across its own duration) so a template recorded at
    one speed can be compared against a live buffer recorded at another.
    """
    timestamps = np.array([f.timestamp for f in frames])
    vectors = np.stack([f.vector for f in frames])  # (n, 33, 2)
    target_t = np.linspace(timestamps[0], timestamps[-1], steps)
    out = np.empty((steps, *vectors.shape[1:]), dtype=vectors.dtype)
    for landmark in range(vectors.shape[1]):
        for axis in range(vectors.shape[2]):
            out[:, landmark, axis] = np.interp(target_t, timestamps, vectors[:, landmark, axis])
    return out


@dataclass
class MoveTemplate:
    name: str
    duration: float
    resampled: np.ndarray  # (_RESAMPLE_STEPS, 33, 2)


def load_templates(library: MoveLibrary) -> dict[str, MoveTemplate]:
    templates: dict[str, MoveTemplate] = {}
    for name, asset in library.moves.items():
        if not asset.has_template:
            continue
        payload = json.loads(asset.template_path.read_text())
        frames = [
            PoseFrame(vector=np.array(f["vector"]), timestamp=f["timestamp"])
            for f in payload["frames"]
        ]
        if len(frames) < 2:
            continue
        templates[name] = MoveTemplate(
            name=name,
            duration=payload["duration"],
            resampled=_resample(frames),
        )
    return templates


@dataclass
class MoveMatch:
    name: str
    distance: float
    duration_ratio: float  # template_duration / performed_duration; >1 = performed faster than the template


class MoveMatcher:
    """Compares a rolling buffer of recently observed pose frames against
    each recorded template and reports the closest match under
    `max_distance`, so performing any of the loaded moves in front of the
    camera resolves to a move name rather than raw landmark data.

    The cooldown is tracked per move name, not globally: holding a pose
    that still resembles the move you just triggered won't keep re-firing
    it every `cooldown_seconds`, but it also doesn't block a *different*
    move from matching immediately after.
    """

    def __init__(
        self,
        templates: dict[str, MoveTemplate],
        max_distance: float = 0.8,
        cooldown_seconds: float = 1.0,
    ):
        self._templates = templates
        self._max_distance = max_distance
        self._cooldown = cooldown_seconds
        self._last_trigger: dict[str, float] = {}

    def check(self, buffer: list[PoseFrame], now: float) -> MoveMatch | None:
        if not self._templates or len(buffer) < 2:
            return None

        live = _resample(buffer)
        best: MoveMatch | None = None
        for template in self._templates.values():
            distance = float(np.mean(np.linalg.norm(live - template.resampled, axis=-1)))
            if best is None or distance < best.distance:
                performed_duration = buffer[-1].timestamp - buffer[0].timestamp
                ratio = template.duration / performed_duration if performed_duration > 0 else 1.0
                best = MoveMatch(name=template.name, distance=distance, duration_ratio=ratio)

        if best is None or best.distance > self._max_distance:
            return None

        last = self._last_trigger.get(best.name, -float("inf"))
        if now - last < self._cooldown:
            return None

        self._last_trigger[best.name] = now
        return best

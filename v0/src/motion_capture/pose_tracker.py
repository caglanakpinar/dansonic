from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np

_LANDMARK = mp.solutions.pose.PoseLandmark


@dataclass
class PoseFrame:
    vector: np.ndarray  # (33, 2) x,y, recentered/rescaled — see PoseTracker
    timestamp: float


class PoseTracker:
    """Wraps MediaPipe Pose (full body, unlike HandTracker) and normalizes
    landmarks to be invariant to where the person stands in frame and how
    close they are to the camera: positions are recentered on the hip
    midpoint and rescaled by torso length, so the same move compares the
    same regardless of position or distance from the camera.
    """

    def __init__(
        self,
        static_image_mode: bool = False,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        model_complexity: int = 0,
    ):
        # model_complexity: 0 (lite, fastest), 1 (default), 2 (heaviest,
        # most accurate). Lower means each frame processes faster, which
        # matters for `live_moves`'s fixed-tick scheduling - the tick can
        # only be checked once per frame, so a faster model means less
        # overshoot past the scheduled tick time. Templates should be
        # recorded with the same model_complexity used for live matching,
        # since different complexities produce slightly different landmark
        # positions.
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=static_image_mode,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            model_complexity=model_complexity,
        )

    def process(self, frame_bgr, timestamp: float | None = None) -> PoseFrame | None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        if not result.pose_landmarks:
            return None
        points = np.array([[lm.x, lm.y] for lm in result.pose_landmarks.landmark])
        hip_center = (points[_LANDMARK.LEFT_HIP] + points[_LANDMARK.RIGHT_HIP]) / 2
        shoulder_center = (points[_LANDMARK.LEFT_SHOULDER] + points[_LANDMARK.RIGHT_SHOULDER]) / 2
        torso = np.linalg.norm(shoulder_center - hip_center) or 1.0
        normalized = (points - hip_center) / torso
        return PoseFrame(
            vector=normalized,
            timestamp=timestamp if timestamp is not None else time.time(),
        )

    def close(self) -> None:
        self._pose.close()

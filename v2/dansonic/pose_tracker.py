"""Thin wrapper around the MediaPipe PoseLandmarker (multi-person, CPU)."""
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

# (start, end) landmark index pairs for drawing
CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (25, 27), (24, 26), (26, 28),
    (15, 17), (15, 19), (16, 18), (16, 20), (0, 11), (0, 12),
]


class PoseTracker:
    def __init__(self, model_path: str, num_poses: int = 5, min_detection: float = 0.5,
                 min_presence: float = 0.5, min_tracking: float = 0.5):
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_poses=num_poses,
            min_pose_detection_confidence=min_detection,
            min_pose_presence_confidence=min_presence,
            min_tracking_confidence=min_tracking,
        )
        self.landmarker = PoseLandmarker.create_from_options(options)
        self.last_ts = -1

    def detect(self, rgb: np.ndarray, timestamp_ms: int) -> list:
        """Returns one (33, 3) array per person: normalized x, y and visibility."""
        if timestamp_ms <= self.last_ts:
            timestamp_ms = self.last_ts + 1
        self.last_ts = timestamp_ms
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self.landmarker.detect_for_video(image, timestamp_ms)
        poses = []
        for landmarks in result.pose_landmarks:
            poses.append(np.array([[l.x, l.y, l.visibility] for l in landmarks], dtype=np.float32))
        return poses

    def close(self):
        self.landmarker.close()

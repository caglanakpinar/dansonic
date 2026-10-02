import time
from dataclasses import dataclass

import cv2
import mediapipe as mp


@dataclass
class HandLandmark:
    x: float
    y: float
    timestamp: float


class HandTracker:
    """Wraps MediaPipe Hands to return the wrist position for the most
    prominent detected hand in a BGR frame (as read by OpenCV).
    """

    def __init__(
        self,
        max_num_hands: int = 1,
        min_detection_confidence: float = 0.6,
        min_tracking_confidence: float = 0.6,
    ):
        self._hands = mp.solutions.hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def process(self, frame_bgr) -> HandLandmark | None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)
        if not result.multi_hand_landmarks:
            return None
        wrist = result.multi_hand_landmarks[0].landmark[mp.solutions.hands.HandLandmark.WRIST]
        return HandLandmark(x=wrist.x, y=wrist.y, timestamp=time.time())

    def close(self) -> None:
        self._hands.close()

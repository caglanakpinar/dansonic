from __future__ import annotations

from collections.abc import Iterator

import cv2

from motion_capture.hand_tracker import HandTracker
from motion_capture.motion import MotionSample, VerticalMotionTracker


def watch_motion(
    camera_index: int = 0,
    show_preview: bool = True,
) -> Iterator[MotionSample]:
    """Opens the webcam and continuously yields the hand's vertical motion,
    frame by frame - no threshold or trigger, just a live feed of how the
    hand is moving so a listener can keep sound in sync with it directly.
    """
    cap = cv2.VideoCapture(camera_index)
    tracker = HandTracker()
    motion = VerticalMotionTracker()
    try:
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            landmark = tracker.process(frame)
            if landmark is not None:
                sample = motion.update(landmark.y, landmark.timestamp)
                if show_preview:
                    cx = int(landmark.x * frame.shape[1])
                    cy = int(landmark.y * frame.shape[0])
                    cv2.circle(frame, (cx, cy), 10, (0, 255, 0), -1)
                    cv2.putText(
                        frame,
                        f"velocity: {sample.velocity:+.2f}",
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 0),
                        2,
                    )
                yield sample
            if show_preview:
                cv2.imshow("dansonic - motion capture", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        tracker.close()
        cap.release()
        if show_preview:
            cv2.destroyAllWindows()

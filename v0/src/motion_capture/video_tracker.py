from __future__ import annotations

from pathlib import Path

import cv2

from motion_capture.hand_tracker import HandLandmark, HandTracker


def track_video(video_path: str | Path) -> list[HandLandmark]:
    """Runs hand tracking over every frame of a video file (as opposed to
    `watch_for_raises`, which tracks a live webcam feed) and returns the
    full per-frame timeline of wrist positions, timestamped from the
    video's own frame rate so it lines up with the video's audio track.
    """
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    tracker = HandTracker()
    landmarks: list[HandLandmark] = []
    try:
        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            landmark = tracker.process(frame)
            if landmark is not None:
                landmark.timestamp = frame_idx / fps
                landmarks.append(landmark)
            frame_idx += 1
    finally:
        tracker.close()
        cap.release()
    return landmarks

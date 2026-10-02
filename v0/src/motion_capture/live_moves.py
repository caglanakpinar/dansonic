from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterator

import cv2

from motion_capture.move_matcher import MoveMatch, MoveMatcher, MoveTemplate
from motion_capture.pose_tracker import PoseFrame, PoseTracker


def watch_for_moves(
    templates: dict[str, MoveTemplate],
    camera_index: int = 0,
    show_preview: bool = True,
    max_distance: float = 0.8,
    cooldown_seconds: float = 1.0,
    buffer_seconds: float = 2.0,
    tick_seconds: float = 1.0,
    model_complexity: int = 0,
) -> Iterator[MoveMatch]:
    """Opens the webcam and yields a MoveMatch each time the live pose
    buffer resembles one of `templates` closely enough.

    When `tick_seconds` is positive (the default), detection runs on a
    fixed clock instead of checking every single frame: the buffer only
    gets compared against the templates once per tick, and is cleared at
    every tick boundary regardless of whether it matched. This is what
    makes triggers land on a steady beat (e.g. once a second) for driving
    music, rather than firing asynchronously at whatever moment mid-motion
    happens to cross the match threshold. Pass `tick_seconds=0` to go back
    to continuous per-frame checking, using `buffer_seconds` as a rolling
    window instead (should comfortably cover the slowest recorded move).

    In continuous mode, the buffer is also cleared right after every match
    so the next move starts from a clean slate instead of waiting for the
    matched move's tail frames to age out of the window.
    """
    cap = cv2.VideoCapture(camera_index)
    tracker = PoseTracker(model_complexity=model_complexity)
    matcher = MoveMatcher(templates, max_distance=max_distance, cooldown_seconds=cooldown_seconds)
    buffer: deque[PoseFrame] = deque()
    start: float | None = None
    next_tick: float | None = None
    try:
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            now = time.time()
            if start is None:
                start = now
                next_tick = tick_seconds
            elapsed = now - start
            pose = tracker.process(frame, timestamp=elapsed)
            if pose is not None:
                buffer.append(pose)

            # The tick/continuous check below runs every frame regardless of
            # whether this particular frame detected a pose - gating it on
            # `pose is not None` was the bug: a single missed detection
            # (motion blur, limb briefly out of frame - common during fast
            # moves) silently skipped that tick, so the beat landed whenever
            # detection next happened to succeed instead of on schedule.
            match: MoveMatch | None = None
            if tick_seconds <= 0:
                if pose is not None:
                    while buffer and pose.timestamp - buffer[0].timestamp > buffer_seconds:
                        buffer.popleft()
                    match = matcher.check(list(buffer), elapsed)
                    if match is not None:
                        buffer.clear()
                        yield match
            elif elapsed >= next_tick:
                if len(buffer) >= 2:
                    match = matcher.check(list(buffer), elapsed)
                buffer.clear()
                # Anchor to the fixed grid rather than `elapsed + tick_seconds`,
                # so a late tick (e.g. a slow frame) doesn't drag every
                # following tick later too - it snaps back to schedule.
                while next_tick <= elapsed:
                    next_tick += tick_seconds
                if match is not None:
                    yield match

            if show_preview:
                label = f"match: {match.name}" if match else ""
                if label:
                    cv2.putText(frame, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                cv2.imshow("dansonic - move matching", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        tracker.close()
        cap.release()
        if show_preview:
            cv2.destroyAllWindows()

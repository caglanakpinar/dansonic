"""Demo: raise or lower your hand in front of the webcam and the reference
clip's playback speed follows your motion live - no threshold, no trigger,
the sound just tracks the motion as it happens. Press "q" in the preview
window to quit.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from motion_capture.capture import watch_motion
from music.player import ReactiveClipPlayer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", type=Path, help="Path to the reference audio clip")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--no-preview", action="store_true")
    args = parser.parse_args()

    player = ReactiveClipPlayer(args.clip)
    player.start()
    try:
        for sample in watch_motion(camera_index=args.camera, show_preview=not args.no_preview):
            player.update(sample.velocity)
    finally:
        player.stop()


if __name__ == "__main__":
    main()

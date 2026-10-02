"""Live demo: start video capture, and whenever a recorded move is
performed in front of the camera, play that move's mapped sound. Moves and
sounds are read straight from dansonic_move/ and dansonic_sounds/ (paired
by filename), so adding a move means dropping in a new sketch + mp3 with a
matching name and recording its template.

Run `poetry run python -m motion_capture.template_recorder <move>` first
for every move that doesn't have one yet — this script refuses to start
until every move discovered in the folders has a recorded template.

Usage: poetry run python -m motion_capture.live_cli
"""

from __future__ import annotations

import argparse
from datetime import datetime

from motion_capture.live_moves import watch_for_moves
from motion_capture.move_library import MoveLibrary
from motion_capture.move_matcher import load_templates
from music.move_sounds import MoveSoundboard


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--max-distance", type=float, default=0.8, help="Lower = stricter match")
    parser.add_argument("--cooldown", type=float, default=1.0)
    parser.add_argument(
        "--tick",
        type=float,
        default=1.0,
        help="Fixed interval (seconds) between detection checks, so triggers land on a steady beat "
        "instead of firing asynchronously whenever a match is found mid-motion. Use 0 for continuous per-frame checking.",
    )
    parser.add_argument(
        "--model-complexity",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="MediaPipe Pose model complexity (0=fastest, 2=most accurate). Must match whatever templates were recorded with.",
    )
    args = parser.parse_args()

    library = MoveLibrary()
    missing = library.missing_templates()
    if missing:
        raise SystemExit(
            "missing recorded templates for: "
            + ", ".join(missing)
            + "\nrecord each with: poetry run python -m motion_capture.template_recorder <move>"
        )

    templates = load_templates(library)
    soundboard = MoveSoundboard()

    for match in watch_for_moves(
        templates,
        camera_index=args.camera,
        show_preview=not args.no_preview,
        max_distance=args.max_distance,
        cooldown_seconds=args.cooldown,
        tick_seconds=args.tick,
        model_complexity=args.model_complexity,
    ):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] matched move={match.name!r} distance={match.distance:.3f} duration_ratio={match.duration_ratio:.2f}")
        soundboard.play(library.moves[match.name].sound_path)


if __name__ == "__main__":
    main()

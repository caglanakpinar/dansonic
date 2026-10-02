"""Records a short live performance of one or more named moves and saves
each as that move's matching template. The dansonic_move/*.jpeg sketches
are for humans to read ("what does 'ab' look like") — MediaPipe's pose
model can't detect a person in a hand-drawn sketch, so the actual
comparison data used by `live_moves` has to come from a real recording,
keyed to the same move name.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2

from motion_capture.move_library import MoveAsset, MoveLibrary
from motion_capture.pose_tracker import PoseFrame, PoseTracker
from music.move_sounds import MoveSoundboard


def _record_one(
    cap: cv2.VideoCapture,
    tracker: PoseTracker,
    move_name: str,
    seconds: float,
    countdown: float,
    show_preview: bool,
    sound_path: Path | None,
    soundboard: MoveSoundboard | None,
) -> list[PoseFrame]:
    frames: list[PoseFrame] = []
    start = time.time()
    recording_start: float | None = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        elapsed = time.time() - start

        if elapsed < countdown:
            label = f"get ready: {move_name!r} in {countdown - elapsed:.1f}s"
        else:
            if recording_start is None:
                recording_start = time.time()
                if soundboard is not None and sound_path is not None:
                    soundboard.play(sound_path)
            rec_elapsed = time.time() - recording_start
            if rec_elapsed > seconds:
                break
            pose = tracker.process(frame, timestamp=rec_elapsed)
            if pose is not None:
                frames.append(pose)
            label = f"recording {move_name!r}: {rec_elapsed:.1f}/{seconds:.1f}s"

        if show_preview:
            cv2.putText(frame, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            cv2.imshow("dansonic - record move", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    return frames


def _save(asset: MoveAsset, frames: list[PoseFrame]) -> Path:
    if len(frames) < 2:
        raise RuntimeError(f"no pose detected while recording {asset.name!r} — try again, closer to the camera")
    asset.template_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": asset.name,
        "duration": frames[-1].timestamp,
        "frames": [{"timestamp": f.timestamp, "vector": f.vector.tolist()} for f in frames],
    }
    asset.template_path.write_text(json.dumps(payload))
    return asset.template_path


def record_template(
    move_name: str,
    library: MoveLibrary,
    camera_index: int = 0,
    seconds: float = 2.0,
    countdown: float = 5.0,
    show_preview: bool = True,
    play_sound: bool = True,
    model_complexity: int = 0,
) -> Path:
    """Records a single move, opening and releasing the camera around it."""
    results = record_templates(
        [move_name],
        library,
        camera_index=camera_index,
        seconds=seconds,
        countdown=countdown,
        show_preview=show_preview,
        play_sound=play_sound,
        model_complexity=model_complexity,
    )
    return results[move_name]


def record_templates(
    move_names: list[str],
    library: MoveLibrary,
    camera_index: int = 0,
    seconds: float = 2.0,
    countdown: float = 5.0,
    show_preview: bool = True,
    play_sound: bool = True,
    model_complexity: int = 0,
) -> dict[str, Path]:
    """Records several moves back-to-back in a single webcam session: get
    ready for move 1, record, get ready for move 2, record, and so on —
    instead of reopening the camera once per move.

    When `play_sound` is set, each move's own mapped sound plays the moment
    its recording window starts, so you can perform the motion along with
    the sound it's meant to trigger instead of guessing the timing.

    `model_complexity` should match whatever `live_moves.watch_for_moves`
    will use for live matching — different complexities produce slightly
    different landmark positions, so a mismatch would compare live poses
    against templates built on a different model.
    """
    unknown = [name for name in move_names if name not in library.moves]
    if unknown:
        raise KeyError(f"unknown move(s) {unknown}; known moves: {sorted(library.moves)}")

    cap = cv2.VideoCapture(camera_index)
    tracker = PoseTracker(model_complexity=model_complexity)
    soundboard = MoveSoundboard() if play_sound else None
    saved: dict[str, Path] = {}
    try:
        for move_name in move_names:
            asset = library.moves[move_name]
            if asset.has_template:
                asset.template_path.unlink()
            frames = _record_one(
                cap, tracker, move_name, seconds, countdown, show_preview,
                sound_path=asset.sound_path, soundboard=soundboard,
            )
            saved[move_name] = _save(asset, frames)
            print(f"saved template for {move_name!r} -> {saved[move_name]}")
    finally:
        tracker.close()
        cap.release()
        if show_preview:
            cv2.destroyAllWindows()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "moves",
        nargs="*",
        help="Move name(s) to record, in order (one camera session covers all of them)",
    )
    parser.add_argument(
        "--missing",
        action="store_true",
        help="Record every move that doesn't have a template yet, instead of passing names explicitly",
    )
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=2.0, help="How long to record each move once its countdown ends")
    parser.add_argument("--countdown", type=float, default=5.0)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--no-sound", action="store_true", help="Don't play the move's sound when its recording window starts")
    parser.add_argument(
        "--model-complexity",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="MediaPipe Pose model complexity (0=fastest, 2=most accurate). Must match live_cli's setting.",
    )
    args = parser.parse_args()

    library = MoveLibrary()
    move_names = library.missing_templates() if args.missing else args.moves
    if not move_names:
        raise SystemExit("no moves given — pass one or more move names, or use --missing to record everything missing")

    saved = record_templates(
        move_names,
        library,
        camera_index=args.camera,
        seconds=args.seconds,
        countdown=args.countdown,
        show_preview=not args.no_preview,
        play_sound=not args.no_sound,
        model_complexity=args.model_complexity,
    )
    print(f"recorded {len(saved)} template(s)")


if __name__ == "__main__":
    main()

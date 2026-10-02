"""Offline pipeline: given a video of a dancer moving to music, split it
into discrete rising-hand figures and save each one alongside the slice of
the video's own soundtrack that played under it - a small paired dataset
of "this motion sounds like this".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import soundfile as sf

from motion_capture.segmenter import segment_motion
from motion_capture.video_tracker import track_video
from music.video_source import load_video_audio


def split_video_into_motion_sound_pairs(
    video_path: str | Path,
    output_dir: str | Path = "src/motion_capture/output",
    velocity_threshold: float = 0.4,
    min_gap: float = 0.15,
    padding: float = 0.1,
) -> Path:
    video_path = Path(video_path)
    landmarks = track_video(video_path)
    segments = segment_motion(landmarks, velocity_threshold=velocity_threshold, min_gap=min_gap)
    audio = load_video_audio(video_path)

    out_root = Path(output_dir) / video_path.stem
    out_root.mkdir(parents=True, exist_ok=True)

    manifest = []
    for segment in segments:
        seg_dir = out_root / f"segment_{segment.index:03d}"
        seg_dir.mkdir(parents=True, exist_ok=True)

        start = max(0.0, segment.start - padding)
        end = min(audio.duration, segment.end + padding)
        sf.write(str(seg_dir / "sound.wav"), audio.slice(start, end), audio.samplerate)

        motion_record = {
            "index": segment.index,
            "start": start,
            "end": end,
            "peak_velocity": segment.peak_velocity,
            "samples": [
                {"timestamp": s.timestamp, "y": s.y, "velocity": s.velocity}
                for s in segment.samples
            ],
        }
        (seg_dir / "motion.json").write_text(json.dumps(motion_record, indent=2))

        manifest.append(
            {
                "index": segment.index,
                "start": start,
                "end": end,
                "peak_velocity": segment.peak_velocity,
                "motion_file": str(seg_dir / "motion.json"),
                "sound_file": str(seg_dir / "sound.wav"),
            }
        )

    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return out_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Path to the source video (e.g. a dance clip filmed with music playing)")
    parser.add_argument("--output-dir", type=Path, default=Path("src/motion_capture/output"))
    parser.add_argument("--velocity-threshold", type=float, default=0.4)
    parser.add_argument("--min-gap", type=float, default=0.15)
    parser.add_argument("--padding", type=float, default=0.1)
    args = parser.parse_args()

    out_root = split_video_into_motion_sound_pairs(
        args.video,
        output_dir=args.output_dir,
        velocity_threshold=args.velocity_threshold,
        min_gap=args.min_gap,
        padding=args.padding,
    )
    manifest = json.loads((out_root / "manifest.json").read_text())
    print(f"{len(manifest)} motion/sound segment(s) written to {out_root}")
    for entry in manifest:
        print(f"  segment_{entry['index']:03d}: {entry['start']:.2f}s-{entry['end']:.2f}s peak_velocity={entry['peak_velocity']:.2f}")


if __name__ == "__main__":
    main()

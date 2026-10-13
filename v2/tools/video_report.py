"""What would a video play? Runs a recording through the same pose tracking, motions and sound mapping as the
app (no audio) and lists every motion with the sound it triggers, so the motions can be checked without a camera.

  python tools/video_report.py ~/Downloads/dansonic.mp4
  python tools/video_report.py clip.mp4 --sheet report.png      # also a picture of the frame behind each sound
  python tools/video_report.py clip.mp4 --audio preview.wav     # also the sound the app would make (drum loop + sounds)
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dansonic import motions as M                       # noqa: E402
from dansonic.dancers import SingleDancer               # noqa: E402
from dansonic.mapper import SoundMapper, resolve        # noqa: E402
from dansonic.pose_tracker import CONNECTIONS, PoseTracker  # noqa: E402
from run import SR, build_engine                        # noqa: E402


class NoEngine:
    def trigger(self, name, quantize, gain, restart_loop=False):
        pass


def tile(frame, lm, title, size=(170, 300)):
    h, w = frame.shape[:2]
    pts = lm[:, :2] * (w, h)
    seen = lm[:, 2] > 0.5
    x0, y0 = pts[seen].min(axis=0)
    x1, y1 = pts[seen].max(axis=0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ch = max(y1 - y0, (x1 - x0) * size[1] / size[0]) * 1.25
    cw = ch * size[0] / size[1]
    pad = int(max(cw, ch))
    padded = cv2.copyMakeBorder(frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT)
    for a, b in CONNECTIONS:
        if lm[a, 2] > 0.5 and lm[b, 2] > 0.5:
            cv2.line(padded, (int(pts[a][0]) + pad, int(pts[a][1]) + pad), (int(pts[b][0]) + pad, int(pts[b][1]) + pad),
                     (0, 255, 0), 3)
    X0, Y0 = int(cx - cw / 2) + pad, int(cy - ch / 2) + pad
    out = cv2.resize(padded[Y0:Y0 + int(ch), X0:X0 + int(cw)], size)
    cv2.rectangle(out, (0, 0), (size[0], 16), (0, 0, 0), -1)
    cv2.putText(out, title, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
    return out


def render(path, cfg, timeline, seconds):
    """Mixes the drum loop and the sounds with the app's own engine, block by block, as the video would play them."""
    import soundfile as sf
    engine = build_engine(cfg)
    engine.playing = True
    engine.trigger_log = []
    clock = [0.0]
    mapper = SoundMapper(engine, cfg["sounds"], cfg["audio"].get("quantize", 4), cfg.get("cooldown", 0.2),
                         clock=lambda: clock[0])
    block, chunks, pending = engine.blocksize, [], list(timeline)
    for k in range(int(seconds * SR / block)):
        clock[0] = k * block / SR
        while pending and pending[0][0] <= clock[0]:
            _, name, kind = pending.pop(0)
            mapper.handle(0, name, kind)
        out = np.zeros((block, 2), np.float32)
        engine._callback(out, block, None, None)
        chunks.append(out)
    mix = np.concatenate(chunks)
    sf.write(path, (np.clip(mix, -1, 1) * 32767).astype(np.int16), SR, subtype="PCM_16")
    print(f"Ses: {path} ({len(mix) / SR:.1f} sn, {len(engine.trigger_log)} ses davulun ustunde)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--sheet", help="write a picture of the frame behind every sound to this png")
    parser.add_argument("--audio", help="render the drum loop plus the sounds the video would play to this wav")
    parser.add_argument("--all", action="store_true", help="also list motions that no sound is written for (swipes ...)")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text())
    for path in sorted((ROOT / "poses").glob("*.json")):
        if path.stem not in M.MOTIONS:
            M.register_pose(path.stem, json.loads(path.read_text()))
    by_motion, problems = resolve(cfg["sounds"])
    if problems:
        sys.exit("\n".join(problems))

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit(f"Video acilamadi: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    pose_cfg = cfg["pose"]
    tracker = PoseTracker(str(ROOT / pose_cfg["model"]), pose_cfg.get("detect_people", 3),
                          pose_cfg.get("min_detection", 0.5), pose_cfg.get("min_detection", 0.5),
                          pose_cfg.get("min_tracking", 0.5))
    single = SingleDancer(pose_cfg.get("select", "center"))
    detector = M.MotionDetector(**cfg.get("detector", {}))
    clock = [0.0]
    mapper = SoundMapper(NoEngine(), cfg["sounds"], cfg["audio"].get("quantize", 4), cfg.get("cooldown", 0.2),
                         clock=lambda: clock[0])

    rows, tiles, with_dancer, i = [], [], 0, 0
    timeline = []                   # (time, motion, kind) of every start/hit, for --audio
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = clock[0] = i / fps
        i += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        assigned, _, _ = single.assign(tracker.detect(rgb, int(t * 1000)), t, False, rgb)
        if not assigned:
            continue
        with_dancer += 1
        lm = assigned[0]
        for name, kind in detector.update(M.Features(lm, frame.shape[1] / frame.shape[0]), t):
            if kind not in ("start", "hit"):
                continue
            timeline.append((t, name, kind))
            played = mapper.handle(0, name, kind)
            sound = by_motion.get(name)
            rows.append((t, name, sound, bool(played)))
            if played and args.sheet:
                tiles.append(tile(frame, lm, f"{played[0][:14]} {t:.1f}s"))
    tracker.close()

    seconds = i / fps
    print(f"{args.video}: {seconds:.1f} s, dancer found in {with_dancer} of {i} frames")
    print(f"\n{'sn':>6}  {'hareket':26s} {'ses':22s}")
    for t, name, sound, played in rows:
        if sound is None and not args.all:
            continue
        mark = "" if played else ("  (cooldown/protect: calmadi)" if sound else "  (hicbir sese yazilmamis)")
        print(f"{t:6.2f}  {name:26s} {sound or '-':22s}{mark}")
    print("\nSes basina calma sayisi:")
    plays = Counter(sound for _, _, sound, played in rows if played)
    for sound in cfg["sounds"]:
        motions = Counter(name for _, name, s, played in rows if played and s == sound)
        print(f"  {sound:22s} {plays[sound]:3d}   {dict(motions)}")
    print(f"  toplam {sum(plays.values())} ses, saniyede {sum(plays.values()) / max(seconds, 1e-6):.2f}")

    if args.audio:
        render(args.audio, cfg, timeline, seconds)

    if args.sheet and tiles:
        per_row = 8
        while len(tiles) % per_row:
            tiles.append(np.zeros_like(tiles[0]))
        cv2.imwrite(args.sheet, np.concatenate([np.concatenate(tiles[k:k + per_row], axis=1)
                                                for k in range(0, len(tiles), per_row)], axis=0))
        print(f"Resim: {args.sheet}")


if __name__ == "__main__":
    main()

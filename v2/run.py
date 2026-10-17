"""Dansonic v2: camera -> pose -> motions -> sounds over a looping drum track.

Usage:
  python run.py                      live performance
  python run.py --no-camera          keyboard only (the number keys play the sounds)
  python run.py --source clip.mp4    use a video file instead of the camera
  python run.py --motions            list every motion and which sound it plays
  python run.py --record NAME        record the pose you hold as motion NAME
Keys: SPACE play/pause, R restart loop, G quantize on/off, M mirror, T switch tracked dancer, D show how close
      each motion is to firing, Q quit, number keys play the sounds.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from dansonic import motions as M
from dansonic.audio_engine import AudioEngine
from dansonic.dancers import DancerAssigner, SingleDancer
from dansonic.mapper import SoundMapper, resolve
from dansonic.song import BeatGrid
from dansonic.sounds import load_loop, load_sounds
from dansonic.ui import COLORS, draw_banner, draw_dancer_label, draw_panel, draw_skeleton

ROOT = Path(__file__).parent
SR = 44100
POSES_DIR = ROOT / "poses"


def load_poses():
    """Registers the recorded poses in poses/ as motions."""
    for path in sorted(POSES_DIR.glob("*.json")):
        if path.stem in M.all_motions():
            sys.exit(f"Kayitli poz adi yerlesik bir hareketle cakisiyor: {path.stem}")
        M.register_pose(path.stem, json.loads(path.read_text()))


def build_engine(cfg: dict) -> AudioEngine:
    loop_cfg, audio = cfg["loop"], cfg["audio"]
    grid = BeatGrid(SR, loop_cfg["bpm"], loop_cfg["beat_offset"])
    loop = load_loop(ROOT / loop_cfg["file"], SR, grid.beat_frames)
    engine = AudioEngine(loop, SR, grid, blocksize=audio.get("blocksize", 256),
                         device=audio.get("device"), master_gain=audio.get("master_gain", 0.9),
                         loop_gain=loop_cfg.get("gain", 0.8), choke=audio.get("choke", True))
    engine.samples = load_sounds(ROOT / cfg["sounds_dir"], list(cfg["sounds"]), SR, trim=False)   # whole clips keep their own beat position
    return engine


def number_keys(n: int) -> str:
    """The keys that play the n sounds of the config: '1' or '1-3'."""
    return "1" if n == 1 else f"1-{n}"


def listed_motions(cfg: dict) -> dict:
    """sound -> the motion names as written in the config."""
    return {name: list((opts or {}).get("motions") or []) for name, opts in cfg["sounds"].items()}


def print_motions(cfg: dict):
    by_motion, _ = resolve(cfg["sounds"])
    for name, words in listed_motions(cfg).items():
        print(f"\n{name}")
        for word in words:
            for m in M.expand(word):
                print(f"  {m:26s} {M.DOCS.get(m, '')}")
    unused = [m for m in M.all_motions() if m not in by_motion]
    print("\nHicbir sese yazilmamis hareketler (config.yaml > sounds > motions icine eklenebilir):")
    for m in unused:
        print(f"  {m:26s} {M.DOCS.get(m, '')}")


class Recorder:
    """Captures the pose held by the first dancer after a countdown."""

    def __init__(self, name: str, with_legs: bool, threshold: float, mirror: bool, countdown=5.0, seconds=1.5):
        self.name = name
        self.joints = M.ARM_JOINTS + (M.LEG_JOINTS if with_legs else [])
        self.threshold = threshold
        self.mirror = mirror
        self.countdown = countdown
        self.seconds = seconds
        self.vectors = []
        self.done = False

    def banner(self, t: float) -> str:
        if t < self.countdown:
            return f"'{self.name}' pozuna gec: {self.countdown - t:.1f}"
        return f"KAYIT '{self.name}' - pozu tut"

    def update(self, features, t: float):
        if t < self.countdown or self.done:
            return
        if t > self.countdown + self.seconds:
            self.save()
            return
        if features is not None and features.ok(*self.joints):
            self.vectors.append(M.pose_vector(features, self.joints))

    def save(self):
        self.done = True
        if len(self.vectors) < 5:
            sys.exit("Poz algilanamadi: kol (ve secildiyse bacak) eklemleri kadrajda gorunmeli.")
        vector = np.median(np.stack(self.vectors), axis=0)
        POSES_DIR.mkdir(exist_ok=True)
        path = POSES_DIR / f"{self.name}.json"
        path.write_text(json.dumps({"name": self.name, "joints": self.joints, "threshold": self.threshold,
                                    "mirror": self.mirror, "vector": vector.tolist()}, indent=1))
        print(f"Kaydedildi: {path} ({len(self.vectors)} kare). "
              f"config.yaml icinde bir sesin motions listesine '{self.name}' ekleyin.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--source", help="camera index or video path (overri    des config)")
    parser.add_argument("--no-camera", action="store_true")
    parser.add_argument("--motions", action="store_true", help="list the motions and what plays them, then exit")
    parser.add_argument("--record", metavar="NAME", help="record a held pose as a new motion")
    parser.add_argument("--legs", action="store_true", help="with --record: include knees and ankles")
    parser.add_argument("--mirror", action="store_true", help="with --record: the other side does the same pose too")
    parser.add_argument("--threshold", type=float, default=0.3, help="with --record: match tolerance")
    parser.add_argument("--headless", type=float, default=0.0, help="run N seconds without a window")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text())
    if args.record and args.record in M.all_motions():
        sys.exit(f"'{args.record}' yerlesik bir hareket adi, baska bir ad secin.")
    if not args.record:
        load_poses()
        _, problems = resolve(cfg["sounds"])
        if problems:
            sys.exit("\n".join(problems))
    if args.motions:
        print_motions(cfg)
        return

    recorder = Recorder(args.record, args.legs, args.threshold, args.mirror) if args.record else None
    engine = mapper = None
    listed, words_for = {}, {}
    if recorder is None:
        try:
            engine = build_engine(cfg)
        except FileNotFoundError as err:
            sys.exit(f"{err}. config.yaml > sounds_dir ve sounds adlarina bakin.")
        mapper = SoundMapper(engine, cfg["sounds"], cfg["audio"].get("quantize", 4), cfg.get("cooldown", 0.2))
        listed = listed_motions(cfg)
        for sound, words in listed.items():
            for word in words:
                for m in M.expand(word):
                    words_for.setdefault(m, []).append(word)

    cam = tracker = None
    mirror = cfg["camera"].get("mirror", True)
    if not args.no_camera:
        from dansonic.camera import Camera, resolve_source
        from dansonic.pose_tracker import PoseTracker
        source = args.source if args.source is not None else cfg["camera"].get("source", 0)
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        source = resolve_source(source)
        cam = Camera(source, cfg["camera"].get("width", 1280), cfg["camera"].get("height", 720))
        pose_cfg = cfg["pose"]
        single_mode = pose_cfg.get("mode", "single") == "single"
        num_poses = pose_cfg.get("detect_people", 3) if single_mode else pose_cfg.get("max_dancers", 5)
        tracker = PoseTracker(str(ROOT / pose_cfg["model"]), num_poses,
                              pose_cfg.get("min_detection", 0.5), pose_cfg.get("min_detection", 0.5),
                              pose_cfg.get("min_tracking", 0.5))
    elif recorder is not None:
        sys.exit("--record kamera gerektirir.")
    single = assigner = None
    if cfg["pose"].get("mode", "single") == "single":
        single = SingleDancer(cfg["pose"].get("select", "center"))
    else:
        assigner = DancerAssigner(cfg["pose"].get("max_dancers", 5), cfg["pose"].get("assignment", "zones"))
    detectors = {}

    if engine is not None:
        engine.start()
        engine.play()
        print(f"Baslatildi. SPACE dur/devam, R bastan, G kuantalama, M ayna, T dansci, Q cikis, "
              f"{number_keys(len(cfg['sounds']))} sesler")

    process_w = cfg["camera"].get("process_width", 640)
    last_frame_id = -1
    video_generation = 0
    t_start = time.time()
    mono_start = time.monotonic()
    fps, fps_t, fps_n = 0.0, time.time(), 0
    last_view = None
    recent = {}                     # motion name as written in the config -> time it last fired
    debug = False                   # D: show the motions closest to firing
    stats = {"frames": 0, "fired": [], "dancers": set()}
    window = "Dansonic"
    if not args.headless:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    try:
        while True:
            now = time.time()
            t = now - t_start
            if cam is not None:
                frame, frame_id = cam.latest()
                if frame is not None and frame_id != last_frame_id:
                    last_frame_id = frame_id
                    h, w = frame.shape[:2]
                    if cam.generation != video_generation:      # the video started over: no motion across the jump
                        video_generation = cam.generation
                        for det in detectors.values():
                            det.reset()
                    pw = min(process_w, w)      # never upscale: a small video gains nothing and runs slower
                    small = cv2.resize(frame, (pw, int(h * pw / w))) if pw != w else frame
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    poses = tracker.detect(rgb, int(t * 1000))
                    if single is not None:
                        assigned, lost, ignored = single.assign(poses, t, mirror, rgb)
                    else:
                        assigned, lost = assigner.assign(poses, t, mirror)
                        ignored = []
                    for slot in lost:
                        detectors.pop(slot, None)
                    features = {slot: M.Features(lm, w / h) for slot, lm in assigned.items()}
                    if recorder is not None:
                        recorder.update(features.get(min(features)) if features else None, t)
                    else:
                        for slot, f in features.items():
                            det = detectors.get(slot)
                            if det is None:
                                det = detectors[slot] = M.MotionDetector(**cfg.get("detector", {}))
                            for name, kind in det.update(f, t):
                                if kind in ("start", "hit"):
                                    for word in words_for.get(name, []):
                                        recent[word] = now
                                played = mapper.handle(slot, name, kind)
                                stats["fired"] += played
                                for sound in played:
                                    print(f"{t:7.2f} s  {sound:8s} <- {name}")
                    stats["frames"] += 1
                    stats["dancers"] |= set(assigned)
                    last_view = (frame, assigned, ignored)
                    fps_n += 1
                    if now - fps_t >= 1.0:
                        fps, fps_t, fps_n = fps_n / (now - fps_t), now, 0
                elif frame is None:
                    time.sleep(0.005)
            if recorder is not None and recorder.done:
                break

            if last_view is not None:
                frame, assigned, ignored = last_view
                canvas = cv2.flip(frame, 1) if mirror else frame.copy()
                for lm in ignored:
                    draw_skeleton(canvas, lm, (110, 110, 110), mirror)
                for slot, lm in assigned.items():
                    color = COLORS[slot % len(COLORS)]
                    pts = draw_skeleton(canvas, lm, color, mirror)
                    active = detectors[slot].active if slot in detectors else set()
                    draw_dancer_label(canvas, pts, slot, active, color)
            else:
                canvas = np.full((720, 960, 3), 30, dtype=np.uint8)
                text = "Kamera yok - klavye test modu" if cam is None else "Kamera bekleniyor"
                cv2.putText(canvas, text, (40, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2, cv2.LINE_AA)
            if recorder is not None:
                draw_banner(canvas, recorder.banner(t))
                view = canvas
            else:
                footer = ["SPACE dur/devam  R bastan  G kuantalama", "M ayna  T dansci  D yakinlik  Q cikis",
                          f"{number_keys(len(cfg['sounds']))} sesleri calar"]
                margins = None
                if debug and detectors:
                    shown = list(words_for) + ["hop nose", "hop shoulders", "hop hips", "hop (rise)", "arms_to_sides",
                                               "thin cross", "thin height", "thin other arm", "thin facing",
                                               "leg lift", "leg other knee"]
                    have = detectors[min(detectors)].margins
                    margins = [(name, have[name]) for name in shown if name in have]
                view = draw_panel(canvas, engine, engine.grid, cfg["sounds"], listed, recent, now, fps, footer,
                                  margins)

            if args.headless:
                if t >= args.headless:
                    cv2.imwrite(str(ROOT / "headless_last_frame.png"), view)
                    print(f"Headless ozet: {stats['frames']} kare, {fps:.1f} fps, "
                          f"slotlar {sorted(stats['dancers'])}, tetiklenen {stats['fired']}")
                    print("Tetikleme gunlugu (sn, ses, hareket):")
                    for when, motion, sound in (mapper.log if mapper else []):
                        print(f"  {when - mono_start:6.2f}  {sound:22s} {motion}")
                    break
                time.sleep(0.005)
                continue

            cv2.imshow(window, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("m"):
                mirror = not mirror
            if key == ord("d"):
                debug = not debug
            if key == ord("t") and single is not None:
                single.switch()
            if engine is None:
                continue
            if key == ord(" "):
                engine.toggle()
            elif key == ord("r"):
                engine.seek(0.0)
                engine.play()
            elif key == ord("g"):
                engine.quantize_enabled = not engine.quantize_enabled
            elif ord("1") <= key <= ord("9") and key - ord("1") < len(cfg["sounds"]):
                mapper.fire(list(cfg["sounds"])[key - ord("1")])
    finally:
        if engine is not None:
            engine.close()
        if cam is not None:
            cam.close()
        if tracker is not None:
            tracker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

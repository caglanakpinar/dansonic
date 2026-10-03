"""Dansonic v1: camera -> pose -> gestures -> sounds over a looping drum track.

Usage:
  python run.py                      live performance
  python run.py --no-camera          keyboard only (keys 1-7 fire the sounds)
  python run.py --source clip.mp4    use a video file instead of the camera
  python run.py --record NAME        record the pose you hold as gesture NAME
Keys: SPACE play/pause, R restart loop, G quantize on/off, M mirror, T switch tracked dancer,
      Q quit, 1-7 sounds.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from dansonic import gestures as G
from dansonic.actions import ActionMapper
from dansonic.audio_engine import AudioEngine
from dansonic.dancers import DancerAssigner, SingleDancer
from dansonic.song import BeatGrid
from dansonic.sounds import load_loop, load_sounds
from dansonic.ui import COLORS, draw_banner, draw_dancer_label, draw_panel, draw_skeleton

ROOT = Path(__file__).parent
SR = 44100
POSES_DIR = ROOT / "poses"


def load_poses():
    for path in sorted(POSES_DIR.glob("*.json")):
        template = json.loads(path.read_text())
        if path.stem in G.STATIC or path.stem in G.IMPULSE:
            sys.exit(f"Kayitli poz adi yerlesik bir hareketle cakisiyor: {path.stem}")
        G.register_pose(path.stem, template)


def build_engine(cfg: dict) -> AudioEngine:
    loop_cfg, audio = cfg["loop"], cfg["audio"]
    grid = BeatGrid(SR, loop_cfg["bpm"], loop_cfg["beat_offset"])
    loop = load_loop(ROOT / loop_cfg["file"], SR, grid.beat_frames)
    engine = AudioEngine(loop, SR, grid, blocksize=audio.get("blocksize", 256),
                         device=audio.get("device"), master_gain=audio.get("master_gain", 0.9),
                         loop_gain=loop_cfg.get("gain", 0.8), choke=audio.get("choke", True))
    names = [m["sound"] for m in cfg["mappings"]]
    engine.samples = load_sounds(ROOT / cfg["sounds_dir"], names, SR)
    return engine


class Recorder:
    """Captures the pose held by the first dancer after a countdown."""

    def __init__(self, name: str, with_legs: bool, threshold: float, countdown=5.0, seconds=1.5):
        self.name = name
        self.joints = G.ARM_JOINTS + (G.LEG_JOINTS if with_legs else [])
        self.threshold = threshold
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
            self.vectors.append(G.pose_vector(features, self.joints))

    def save(self):
        self.done = True
        if len(self.vectors) < 5:
            sys.exit("Poz algilanamadi: kol (ve secildiyse bacak) eklemleri kadrajda gorunmeli.")
        vector = np.median(np.stack(self.vectors), axis=0)
        POSES_DIR.mkdir(exist_ok=True)
        path = POSES_DIR / f"{self.name}.json"
        path.write_text(json.dumps({"name": self.name, "joints": self.joints,
                                    "threshold": self.threshold, "vector": vector.tolist()}, indent=1))
        print(f"Kaydedildi: {path} ({len(self.vectors)} kare). "
              f"config.yaml icinde bir sesin gestures listesine '{self.name}' ekleyin.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--source", help="camera index or video path (overrides config)")
    parser.add_argument("--no-camera", action="store_true")
    parser.add_argument("--record", metavar="NAME", help="record a held pose as a new gesture")
    parser.add_argument("--legs", action="store_true", help="with --record: include knees and ankles")
    parser.add_argument("--threshold", type=float, default=0.3, help="with --record: match tolerance")
    parser.add_argument("--headless", type=float, default=0.0, help="run N seconds without a window")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text())
    if args.record and (args.record in G.STATIC or args.record in G.IMPULSE):
        sys.exit(f"'{args.record}' yerlesik bir hareket adi, baska bir ad secin.")
    if not args.record:
        load_poses()
        known = G.all_gestures()
        for m in cfg["mappings"]:
            for g in m["gestures"]:
                if g not in known:
                    sys.exit(f"Bilinmeyen hareket '{g}' (ses: {m['sound']}). Yerlesik ad degilse "
                             f"once kaydedin: python run.py --record {g}")

    recorder = Recorder(args.record, args.legs, args.threshold) if args.record else None
    engine = None
    mapper = None
    if recorder is None:
        engine = build_engine(cfg)
        mapper = ActionMapper(engine, cfg["mappings"], cfg["audio"].get("quantize", 4))

    cam = tracker = None
    mirror = cfg["camera"].get("mirror", True)
    if not args.no_camera:
        from dansonic.camera import Camera
        from dansonic.pose_tracker import PoseTracker
        source = args.source if args.source is not None else cfg["camera"].get("source", 0)
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        cam = Camera(source, cfg["camera"].get("width", 1280), cfg["camera"].get("height", 720))
        pose_cfg = cfg["pose"]
        single_mode = pose_cfg.get("mode", "single") == "single"
        num_poses = pose_cfg.get("detect_people", 3) if single_mode else pose_cfg.get("max_dancers", 5)
        tracker = PoseTracker(str(ROOT / pose_cfg["model"]), num_poses,
                              pose_cfg.get("min_detection", 0.5), pose_cfg.get("min_detection", 0.5),
                              pose_cfg.get("min_tracking", 0.5))
    elif recorder is not None:
        sys.exit("--record kamera gerektirir.")
    single = None
    if cfg["pose"].get("mode", "single") == "single":
        single = SingleDancer(cfg["pose"].get("select", "center"))
    else:
        assigner = DancerAssigner(cfg["pose"].get("max_dancers", 5), cfg["pose"].get("assignment", "zones"))
    detectors = {}

    if engine is not None:
        engine.start()
        engine.play()
        print("Baslatildi. SPACE dur/devam, R bastan, G kuantalama, M ayna, Q cikis, 1-7 sesler")

    process_w = cfg["camera"].get("process_width", 640)
    last_frame_id = -1
    t_start = time.time()
    fps, fps_t, fps_n = 0.0, time.time(), 0
    last_view = None
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
                    small = cv2.resize(frame, (process_w, int(h * process_w / w)))
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    poses = tracker.detect(rgb, int(t * 1000))
                    if single is not None:
                        assigned, lost, ignored = single.assign(poses, t, mirror, rgb)
                    else:
                        assigned, lost = assigner.assign(poses, t, mirror)
                        ignored = []
                    for slot in lost:
                        detectors.pop(slot, None)
                    features = {slot: G.Features(lm, w / h) for slot, lm in assigned.items()}
                    if recorder is not None:
                        recorder.update(features.get(min(features)) if features else None, t)
                    else:
                        for slot, f in features.items():
                            det = detectors.get(slot)
                            if det is None:
                                det = detectors[slot] = G.GestureDetector(**cfg.get("gestures", {}))
                            for name, kind in det.update(f, t):
                                stats["fired"] += mapper.handle(slot, name, kind)
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
                footer = ["SPACE dur/devam  R bastan  G kuantalama", "M ayna  T dansci degistir  Q cikis", "1-7 sesleri calar"]
                view = draw_panel(canvas, engine, engine.grid, cfg["mappings"], fps, footer)

            if args.headless:
                if t >= args.headless:
                    cv2.imwrite(str(ROOT / "headless_last_frame.png"), view)
                    print(f"Headless ozet: {stats['frames']} kare, {fps:.1f} fps, "
                          f"slotlar {sorted(stats['dancers'])}, tetiklenen {stats['fired']}")
                    break
                time.sleep(0.005)
                continue

            cv2.imshow(window, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("m"):
                mirror = not mirror
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
            elif ord("1") <= key <= ord("9") and key - ord("1") < len(cfg["mappings"]):
                mapper.fire(cfg["mappings"][key - ord("1")])
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

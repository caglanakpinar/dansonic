"""Dansonic v1: camera -> pose -> gestures -> sounds over a looping drum track.

Usage:
  python run.py                      live performance
  python run.py --no-camera          keyboard only (keys 1-8 fire the sounds)
  python run.py --source clip.mp4    use a video file instead of the camera
  python run.py --record NAME        record the pose you hold as gesture NAME
Keys: SPACE play/pause, R restart loop, G quantize on/off, M mirror, T switch tracked dancer,
      B the nearest beat is beat 1, O start now (when the opening ab-ab is awaited), K teach the app your ab-ab,
      Q quit, 1-8 sounds.
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
from dansonic.motion import SceneMotion
from dansonic.song import BeatGrid
from dansonic.sounds import load_loop, load_sounds
from dansonic.ui import COLORS, draw_banner, draw_dancer_label, draw_panel, draw_skeleton

ROOT = Path(__file__).parent
SR = 44100
POSES_DIR = ROOT / "poses"


def load_poses():
    for path in sorted(POSES_DIR.glob("*.json")):
        template = json.loads(path.read_text())
        if path.stem in G.all_gestures():
            sys.exit(f"Kayitli poz adi yerlesik bir hareketle cakisiyor: {path.stem}")
        G.register_pose(path.stem, template)


def build_engine(cfg: dict) -> AudioEngine:
    loop_cfg, audio = cfg["loop"], cfg["audio"]
    grid = BeatGrid(SR, loop_cfg["bpm"], loop_cfg["beat_offset"], loop_cfg.get("downbeat_index", 0))
    loop = load_loop(ROOT / loop_cfg["file"], SR, grid.beat_frames)
    engine = AudioEngine(loop, SR, grid, blocksize=audio.get("blocksize", 256),
                         device=audio.get("device"), master_gain=audio.get("master_gain", 0.9),
                         loop_gain=loop_cfg.get("gain", 0.8), choke=audio.get("choke", True))
    names = [m["sound"] for m in cfg["mappings"]]
    engine.samples = load_sounds(ROOT / cfg["sounds_dir"], names, SR)
    return engine


def video_sync(cfg: dict, source, args) -> tuple:
    """(speed, downbeat) for a video file: how much faster to play it, and the video second where
    its bar 1 starts. The config lists known videos by file name; --speed and --downbeat override."""
    entry = {}
    if isinstance(source, str):
        entry = (cfg.get("video_sync") or {}).get(Path(source).name) or {}
    speed = args.speed if args.speed else entry.get("speed", 1.0)
    downbeat = args.downbeat if args.downbeat is not None else entry.get("downbeat")
    return float(speed), downbeat


def loop_phase(grid: BeatGrid, downbeat: float, speed: float) -> float:
    """Loop position (seconds) to start from so that a bar of the loop begins when the video
    reaches its second `downbeat`: the video's bars then line up with the loop's."""
    beat_s = grid.beat_frames / SR
    start = grid.offset_frames / SR + grid.downbeat_index * beat_s
    return (start - downbeat / speed) % (4 * beat_s)


def taught_openings() -> list:
    """Poses the dancer taught the app as their ab ab (poses/ab_ab*.json, the K key): they open the dance too."""
    return sorted(p.stem for p in POSES_DIR.glob("ab_ab*.json"))


class OpeningTeacher:
    """The K key: counts down, records the pose the first dancer holds and saves it as poses/ab_ab_N.json, the
    dancer's own ab ab. From then on that pose opens the dance at once."""

    COUNTDOWN, SECONDS, THRESHOLD = 3.0, 1.2, 0.25

    def __init__(self):
        self.t0 = None
        self.vectors = []
        self.message, self.message_until = "", 0.0

    @property
    def active(self) -> bool:
        return self.t0 is not None

    def start(self, t: float):
        self.t0, self.vectors, self.message = t, [], ""

    def banner(self, t: float) -> str:
        e = t - self.t0
        return f"ab-ab hareketini yap: {self.COUNTDOWN - e:.0f}" if e < self.COUNTDOWN else "TUT - ogreniyorum"

    def update(self, features, t: float):
        """Returns (name, template) once the pose has been learned."""
        e = t - self.t0
        if e < self.COUNTDOWN:
            return None
        if e <= self.COUNTDOWN + self.SECONDS:
            if features is not None and features.ok(*G.ARM_JOINTS):
                self.vectors.append(G.pose_vector(features, G.ARM_JOINTS))
            return None
        vectors, self.t0 = self.vectors, None
        self.message_until = t + 4.0
        if len(vectors) < 5:
            self.message = "Poz algilanamadi: kollar kadrajda olmali. Tekrar: K"
            return None
        POSES_DIR.mkdir(exist_ok=True)
        n = 1
        while (POSES_DIR / f"ab_ab_{n}.json").exists():
            n += 1
        name = f"ab_ab_{n}"
        template = {"name": name, "joints": G.ARM_JOINTS, "threshold": self.THRESHOLD,
                    "note": "ogretilen ab-ab hareketi", "vector": np.median(np.stack(vectors), axis=0).tolist()}
        (POSES_DIR / f"{name}.json").write_text(json.dumps(template, indent=1))
        self.message = f"Ogrenildi: {name} ({len(vectors)} kare). Artik bu pozla acilir."
        return name, template


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
    parser.add_argument("--speed", type=float, help="with --source <video>: play it this many times faster")
    parser.add_argument("--downbeat", type=float, help="with --source <video>: video second where bar 1 starts "
                                                       "(the loop's bars are lined up with it)")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text())
    if args.record and args.record in G.all_gestures():
        sys.exit(f"'{args.record}' yerlesik bir hareket adi, baska bir ad secin.")
    if not args.record:
        load_poses()
        known = G.all_gestures()
        for m in cfg["mappings"]:
            for g in m.get("gestures", []):
                if g not in known:
                    sys.exit(f"Bilinmeyen hareket '{g}' (ses: {m['sound']}). Yerlesik ad degilse "
                             f"once kaydedin: python run.py --record {g}")
            if "beat" in m and int(m["beat"]) not in (1, 2, 3, 4):
                sys.exit(f"'{m['sound']}': beat 1-4 arasinda olmali.")
        for g in (cfg.get("beats") or {}).get("hits", []):
            if g not in known:
                sys.exit(f"Bilinmeyen vurus hareketi '{g}' (beats > hits).")
        plain = [int(m["beat"]) for m in cfg["mappings"] if "beat" in m and not m.get("both_arms")]
        double = [int(m["beat"]) for m in cfg["mappings"] if "beat" in m and m.get("both_arms")]
        if len(plain) != len(set(plain)) or len(double) != len(set(double)):
            sys.exit("Ayni vurusa birden fazla ses atanmis (mappings > beat).")
        if set(double) - set(plain):
            sys.exit("both_arms olan bir sesin ayni vurusta sade bir sesi de olmali (mappings > beat).")
        for m in cfg["mappings"]:
            if m.get("both_arms") and int(m.get("span", 2)) < 2:
                sys.exit(f"'{m['sound']}': both_arms olan sesin span degeri en az 2 olmali (mappings > span).")
        opening = cfg.get("opening")
        if opening:
            for name in taught_openings():                      # the dancer's own ab ab opens the dance as well
                if name not in (opening.get("motions") or []):
                    opening["motions"] = (opening.get("motions") or []) + [name]
            for key in ("motions", "loose"):
                for g in opening.get(key) or []:
                    if g not in known:
                        sys.exit(f"Bilinmeyen acilis hareketi '{g}' (opening > {key}).")
            for key in ("margin", "hold", "grace"):
                if key in opening and not isinstance(opening[key], (int, float)):
                    sys.exit(f"opening > {key} bir sayi olmali.")
            first_double = [m["sound"] for m in cfg["mappings"] if m.get("both_arms") and int(m.get("beat", 0)) == 1]
            if not (opening.get("motions") or opening.get("loose")) or opening.get("sound") not in first_double:
                sys.exit("opening icin 'motions' (ya da 'loose') listesi ve 1. vurusun both_arms sesi ('sound') gerekir (opening).")
        senkron = cfg.get("senkron")
        if senkron and (not isinstance(senkron.get("bars"), int) or senkron["bars"] < 1):
            sys.exit("senkron > bars: senkronun kac olcu surdugu, 1 ya da daha buyuk bir tam sayi olmali.")
        sounds = {m["sound"] for m in cfg["mappings"]}
        seen = {}
        for m in cfg.get("individual") or []:
            if m.get("sound") not in sounds:
                sys.exit(f"individual: '{m.get('sound')}' mappings icinde bir ses degil.")
            if not m.get("gestures"):
                sys.exit(f"individual: '{m['sound']}' icin gestures listesi bos.")
            for g in m["gestures"]:
                if g not in known:
                    sys.exit(f"Bilinmeyen tek hareket '{g}' (individual > {m['sound']}).")
                if g in ((opening or {}).get("motions") or []) or g in ((opening or {}).get("loose") or []):
                    sys.exit(f"'{g}' hem acilis hem tek hareket: tek hareket senkronu baslatmaz (individual).")
                if g in seen:
                    sys.exit(f"'{g}' hem '{seen[g]}' hem '{m['sound']}' icin tek hareket olarak yazilmis (individual).")
                seen[g] = m["sound"]

    recorder = Recorder(args.record, args.legs, args.threshold) if args.record else None
    engine = None
    mapper = None
    if recorder is None:
        engine = build_engine(cfg)
        mapper = ActionMapper(engine, cfg["mappings"], cfg["audio"].get("quantize", 4), beats=cfg.get("beats"),
                              opening=cfg.get("opening"), individual=cfg.get("individual"),
                              senkron=cfg.get("senkron"))
        if (cfg.get("individual") or cfg.get("senkron")) and not mapper.gated:
            print("Not: opening bolumu yok, dans hep senkronda; tek hareketler calmaz ve senkron bitmez.")

    teacher = OpeningTeacher() if mapper is not None and mapper.gated and not args.no_camera else None
    cam = tracker = None
    phase = None            # loop position the video's bar 1 is lined up with (video files only)
    mirror = cfg["camera"].get("mirror", True)
    if not args.no_camera:
        from dansonic.camera import Camera
        from dansonic.pose_tracker import PoseTracker
        source = args.source if args.source is not None else cfg["camera"].get("source", 0)
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        speed, downbeat = video_sync(cfg, source, args)
        phase = loop_phase(engine.grid, downbeat, speed) if engine is not None and downbeat is not None else None
        cam = Camera(source, cfg["camera"].get("width", 1280), cfg["camera"].get("height", 720), speed=speed,
                     on_loop=(lambda: engine.seek(phase)) if phase is not None else None)
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
        if phase is not None:
            engine.seek(phase)
            cam.restart()
            print(f"Video {speed:g}x hizda, 1. olcusu {downbeat:g}. saniyede; loop bu olcuye hizalandi.")
        print(f"Baslatildi. SPACE dur/devam, R bastan, G kuantalama, M ayna, B 1. vurus, Q cikis, 1-{len(cfg['mappings'])} sesler")

    process_w = cfg["camera"].get("process_width", 640)
    motion_level = (cfg.get("beats") or {}).get("motion") or 0
    scene = SceneMotion(float(motion_level)) if motion_level and mapper is not None else None
    last_frame_id = -1
    video_generation = 0
    mapper_generation = [0]

    def mapper_follows_video():
        """The video started over: the loop was moved, so the dance has to open again. This is checked just before
        every update too, because the loop is moved a moment before the next frame arrives."""
        if mapper is not None and cam is not None and cam.generation != mapper_generation[0]:
            mapper_generation[0] = cam.generation
            mapper.reset()

    t_start = time.time()
    mono_start = time.monotonic()
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
                    if cam.generation != video_generation:      # the video restarted or looped: no motion across the jump
                        video_generation = cam.generation
                        if scene is not None:
                            scene.reset()
                    mapper_follows_video()
                    moving = scene.update(frame, t) if scene is not None else False
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
                    features = {slot: G.Features(lm, w / h) for slot, lm in assigned.items()}
                    if recorder is not None:
                        recorder.update(features.get(min(features)) if features else None, t)
                    else:
                        if teacher is not None and teacher.active:
                            learned = teacher.update(features.get(min(features)) if features else None, t)
                            if learned:
                                G.register_pose(*learned)
                                mapper.add_opening_motion(learned[0])
                        for slot, f in features.items():
                            det = detectors.get(slot)
                            if det is None:
                                det = detectors[slot] = G.GestureDetector(**cfg.get("gestures", {}))
                            for name, kind in det.update(f, t):
                                stats["fired"] += mapper.handle(slot, name, kind)
                            stats["fired"] += mapper.tick(slot, det.active, det.margins)
                        stats["fired"] += mapper.motion(moving)
                    stats["frames"] += 1
                    stats["dancers"] |= set(assigned)
                    last_view = (frame, assigned, ignored)
                    fps_n += 1
                    if now - fps_t >= 1.0:
                        fps, fps_t, fps_n = fps_n / (now - fps_t), now, 0
                elif frame is None:
                    time.sleep(0.005)
            if mapper is not None:
                mapper_follows_video()
                stats["fired"] += mapper.update()       # both arms on beat 1 add the double's second beat
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
                footer = ["SPACE dur/devam  R bastan  G kuantalama", "M ayna  T dansci  B 1. vurus",
                          "O basla  K ab-ab ogret  Q cikis", f"1-{len(cfg['mappings'])} sesleri calar"]
                if mapper is not None and mapper.waiting():
                    banner = "bitti: ab-ab bekleniyor" if mapper.ended else "ab-ab bekleniyor  (O: basla)"
                    draw_banner(canvas, teacher.banner(t) if teacher is not None and teacher.active else banner)
                    footer = (["Senkron bitti."] if mapper.ended else []) + [f"Acilis hareketi: {mapper.waiting()}"] + \
                             ([f"Yakin: {', '.join(mapper.opening_loose)}"] if mapper.opening_loose else []) + \
                             [f"Tek: {', '.join(m['gestures'])} -> {m['sound']}" for m in cfg.get("individual") or []] + footer
                elif teacher is not None and teacher.active:
                    draw_banner(canvas, teacher.banner(t))
                if teacher is not None and teacher.message and t < teacher.message_until:
                    footer.insert(0, teacher.message[:46])
                view = draw_panel(canvas, engine, engine.grid, cfg["mappings"], fps, footer)

            if args.headless:
                if t >= args.headless:
                    cv2.imwrite(str(ROOT / "headless_last_frame.png"), view)
                    print(f"Headless ozet: {stats['frames']} kare, {fps:.1f} fps, "
                          f"slotlar {sorted(stats['dancers'])}, tetiklenen {stats['fired']}")
                    if mapper is not None and mapper.gated:
                        print("Acilis (ab-ab): " + (f"{mapper.opened_at - mono_start:.2f} sn" if mapper.opened
                                                    else ("senkron bitti, " if mapper.ended else "gorulmedi, ")
                                                    + f"bekleniyor: {mapper.waiting()}"))
                    print("Tetikleme gunlugu (sn, ses, vurus veya hareket):")
                    for when, gesture, sound, bar_beat in (mapper.log if mapper else []):
                        print(f"  {when - mono_start:6.2f}  {sound:22s} " +
                              (f"vurus {bar_beat}  ({gesture})" if bar_beat else gesture))
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
                engine.seek(phase if phase is not None else 0.0)
                mapper.reset()
                engine.play()
                if phase is not None:
                    cam.restart()
            elif key == ord("g"):
                engine.quantize_enabled = not engine.quantize_enabled
            elif key == ord("o"):
                if mapper.waiting():
                    mapper.open_now()
            elif key == ord("k"):
                if teacher is not None and not teacher.active:
                    teacher.start(t)
            elif key == ord("b"):
                grid = engine.grid
                grid.downbeat_index = int(round((engine.pos - grid.offset_frames) / grid.beat_frames)) % 4
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

"""OpenCV overlay: skeletons, gesture labels and the sound panel."""
import cv2
import numpy as np

from .pose_tracker import CONNECTIONS

COLORS = [(80, 220, 120), (80, 160, 255), (255, 140, 60), (200, 80, 255), (60, 220, 255)]
PANEL_W = 360
FONT = cv2.FONT_HERSHEY_SIMPLEX
HIGHLIGHT = (60, 230, 255)


def draw_skeleton(frame, lm, color, mirror):
    h, w = frame.shape[:2]
    pts = []
    for x, y, vis in lm:
        if mirror:
            x = 1.0 - x
        pts.append((int(x * w), int(y * h), vis))
    for a, b in CONNECTIONS:
        if pts[a][2] > 0.5 and pts[b][2] > 0.5:
            cv2.line(frame, pts[a][:2], pts[b][:2], color, 2, cv2.LINE_AA)
    for x, y, vis in pts:
        if vis > 0.5:
            cv2.circle(frame, (x, y), 3, color, -1, cv2.LINE_AA)
    return pts


def draw_dancer_label(frame, pts, slot, active, color):
    xs = [p[0] for p in pts if p[2] > 0.5]
    ys = [p[1] for p in pts if p[2] > 0.5]
    if not xs:
        return
    x, y = min(xs), max(20, min(ys) - 12)
    cv2.putText(frame, f"D{slot + 1}", (x, y), FONT, 0.7, color, 2, cv2.LINE_AA)
    for i, g in enumerate(sorted(active)):
        cv2.putText(frame, g, (x, y + 22 * (i + 1)), FONT, 0.55, (255, 255, 255), 2, cv2.LINE_AA)


def draw_banner(frame, text):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 54), (0, 0, 0), -1)
    cv2.putText(frame, text, (16, 36), FONT, 0.9, HIGHLIGHT, 2, cv2.LINE_AA)


def draw_panel(frame, engine, grid, mappings, fps, footer):
    h, w = frame.shape[:2]
    panel = np.full((h, PANEL_W, 3), 24, dtype=np.uint8)
    pos = engine.pos
    y = 30
    cv2.putText(panel, "DANSONIC", (14, y), FONT, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    y += 28
    state = "CALIYOR" if engine.playing else "DURDU"
    secs = pos / engine.sr
    cv2.putText(panel, f"{state}  {int(secs // 60):02d}:{int(secs % 60):02d}  {fps:4.1f} fps",
                (14, y), FONT, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
    y += 30

    beat = grid.beat_in_bar(pos)
    phase = grid.beat_phase(pos)
    for i in range(4):
        on = engine.playing and i == beat and phase < 0.35
        cv2.circle(panel, (30 + i * 36, y), 12 if on else 9, HIGHLIGHT if on else (70, 70, 70), -1, cv2.LINE_AA)
    quant = "kuantalama ACIK" if engine.quantize_enabled else "kuantalama KAPALI"
    cv2.putText(panel, f"{60.0 * engine.sr / grid.beat_frames:.1f} bpm", (185, y - 4), FONT, 0.5,
                (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(panel, quant, (185, y + 14), FONT, 0.4, (150, 150, 150), 1, cv2.LINE_AA)
    y += 40

    cv2.putText(panel, "SESLER", (14, y), FONT, 0.55, (180, 180, 180), 1, cv2.LINE_AA)
    y += 8
    for i, m in enumerate(mappings):
        y += 26
        last = engine.last_trigger.get(m["sound"])
        age = (engine.clock - last) / engine.sr if last is not None else 99.0
        lit = 0 <= age < 0.4
        color = HIGHLIGHT if lit else (230, 230, 230)
        if lit:
            cv2.rectangle(panel, (8, y - 17), (PANEL_W - 8, y + 21), (60, 60, 60), -1)
        cv2.putText(panel, f"{(i + 1) % 10}  {m['sound']}", (14, y), FONT, 0.55, color, 1 + lit, cv2.LINE_AA)
        y += 17
        cv2.putText(panel, "   " + ", ".join(m["gestures"]), (14, y), FONT, 0.4, (140, 140, 140), 1, cv2.LINE_AA)

    y = h - 14 - 18 * (len(footer) - 1)
    for line in footer:
        cv2.putText(panel, line, (14, y), FONT, 0.42, (160, 160, 160), 1, cv2.LINE_AA)
        y += 18
    return np.concatenate([frame, panel], axis=1)

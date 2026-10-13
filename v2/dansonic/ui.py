"""OpenCV overlay: skeletons, active motions and the sound panel."""
import cv2
import numpy as np

from .pose_tracker import CONNECTIONS

COLORS = [(80, 220, 120), (80, 160, 255), (255, 140, 60), (200, 80, 255), (60, 220, 255)]
PANEL_W = 380
FONT = cv2.FONT_HERSHEY_SIMPLEX
HIGHLIGHT = (60, 230, 255)
GREY = (140, 140, 140)


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


def _tokens(panel, words, y, lit):
    """Draws the motion names left to right, wrapping at the panel edge. Returns the next free y."""
    x = 28
    for word in words:
        label = word + "  "
        (w, _), _ = cv2.getTextSize(label, FONT, 0.4, 1)
        if x + w > PANEL_W - 10:
            x, y = 28, y + 16
        cv2.putText(panel, label, (x, y), FONT, 0.4, HIGHLIGHT if word in lit else GREY, 1, cv2.LINE_AA)
        x += w
    return y


def draw_panel(frame, engine, grid, sounds, listed, recent, now, fps, footer, margins=None):
    """sounds: config name -> options, listed: sound -> motion names as written in the config,
    recent: motion family -> time it last fired."""
    h, w = frame.shape[:2]
    panel = np.full((h, PANEL_W, 3), 24, dtype=np.uint8)
    pos = engine.pos
    y = 30
    cv2.putText(panel, "DANSONIC v2", (14, y), FONT, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
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
    cv2.putText(panel, f"{60.0 * engine.sr / grid.beat_frames:.1f} bpm", (195, y - 4), FONT, 0.5,
                (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(panel, quant, (195, y + 14), FONT, 0.4, (150, 150, 150), 1, cv2.LINE_AA)
    y += 36

    cv2.putText(panel, "SESLER VE HAREKETLERI", (14, y), FONT, 0.5, (180, 180, 180), 1, cv2.LINE_AA)
    y += 6
    for i, name in enumerate(sounds):
        y += 24
        last = engine.last_trigger.get(name)
        age = (engine.clock - last) / engine.sr if last is not None else 99.0
        lit = 0 <= age < 0.4
        words = listed.get(name, [])
        recent_words = {m for m in words if now - recent.get(m, -99.0) < 0.6}
        if lit:
            rows = 1 + (len(" ".join(words)) // 38 + 1)
            cv2.rectangle(panel, (8, y - 17), (PANEL_W - 8, y + 4 + 16 * rows), (60, 60, 60), -1)
        cv2.putText(panel, f"{(i + 1) % 10}  {name}", (14, y), FONT, 0.55, HIGHLIGHT if lit else (230, 230, 230),
                    1 + lit, cv2.LINE_AA)
        y = _tokens(panel, words, y + 17, recent_words)
        y += 6

    if margins:
        y = h - 14 - 18 * len(footer) - 16 * len(margins) - 22
        cv2.putText(panel, "YAKINLIK (ne kadar tetiklemeye yakin)", (14, y), FONT, 0.42, (180, 180, 180), 1, cv2.LINE_AA)
        for name, value in margins:
            y += 16
            held = value > 0
            cv2.putText(panel, f"{name[:24]:24s} {value:+.2f}", (14, y), FONT, 0.4, HIGHLIGHT if held else GREY, 1,
                        cv2.LINE_AA)
            cv2.rectangle(panel, (250, y - 8), (250 + int(np.clip(value + 0.5, 0, 1) * 110), y - 2),
                          HIGHLIGHT if held else (90, 90, 90), -1)
    y = h - 14 - 18 * (len(footer) - 1)
    for line in footer:
        cv2.putText(panel, line, (14, y), FONT, 0.42, (160, 160, 160), 1, cv2.LINE_AA)
        y += 18
    return np.concatenate([frame, panel], axis=1)

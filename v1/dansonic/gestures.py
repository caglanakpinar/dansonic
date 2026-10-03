"""Rule-based gesture recognition on 2D pose landmarks.

Every static gesture is a function returning a margin in torso units:
> 0 means the pose is held, and the detector adds hysteresis and hold/release
frame counts. Impulse gestures (swipes) fire once per motion with a cooldown.
Sides refer to the dancer's own left and right.
"""
from collections import deque

import numpy as np

NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 0, 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 23, 24, 25, 26, 27, 28

VIS = 0.5


class Features:
    """Landmark geometry normalized by torso length and expressed in the dancer's frame."""

    def __init__(self, lm: np.ndarray, aspect: float):
        # scale x by the frame aspect ratio so distances are isotropic
        pts = lm[:, :2].copy()
        pts[:, 0] *= aspect
        self.vis = lm[:, 2]
        self.sh_c = (pts[L_SH] + pts[R_SH]) / 2
        self.hip_c = (pts[L_HIP] + pts[R_HIP]) / 2
        self.torso = max(1e-3, float(np.linalg.norm(self.sh_c - self.hip_c)))
        self.shoulder_w = float(np.linalg.norm(pts[L_SH] - pts[R_SH])) / self.torso
        right_dir = pts[R_SH] - pts[L_SH]
        norm = np.linalg.norm(right_dir)
        self.right_dir = right_dir / norm if norm > 1e-6 else np.array([-1.0, 0.0])
        self.p = (pts - self.sh_c) / self.torso      # torso units, origin at shoulder center
        self.hip_y = float(self.p[L_HIP][1] + self.p[R_HIP][1]) / 2

    def ok(self, *idx) -> bool:
        return all(self.vis[i] > VIS for i in idx)

    def side(self, i) -> float:
        """Signed lateral offset of landmark i toward the dancer's right."""
        return float(np.dot(self.p[i], self.right_dir))

    def y(self, i) -> float:
        return float(self.p[i][1])

    def frame(self, i) -> np.ndarray:
        """Landmark i in the dancer's frame: (offset toward own right, height)."""
        return np.array([self.side(i), self.y(i)])


def _hand_up(f, wr):
    if not f.ok(NOSE, wr):
        return -1.0
    return f.y(NOSE) - f.y(wr) - 0.05


def _arm_out(f, sh, wr, sign):
    if not f.ok(sh, wr):
        return -1.0
    ext = sign * (f.side(wr) - f.side(sh))
    level = 0.35 - abs(f.y(wr) - f.y(sh))
    return min(ext - 0.75, level)


def right_hand_up(f):
    return _hand_up(f, R_WR)


def left_hand_up(f):
    return _hand_up(f, L_WR)


def both_hands_up(f):
    return min(_hand_up(f, R_WR), _hand_up(f, L_WR))


def right_arm_out(f):
    return _arm_out(f, R_SH, R_WR, 1.0)


def left_arm_out(f):
    return _arm_out(f, L_SH, L_WR, -1.0)


def t_pose(f):
    return min(right_arm_out(f), left_arm_out(f))


def arms_crossed(f):
    if not f.ok(L_WR, R_WR, L_HIP, R_HIP):
        return -1.0
    chest = min(f.hip_y - f.y(R_WR), f.hip_y - f.y(L_WR), f.y(R_WR) + 0.3, f.y(L_WR) + 0.3)
    crossed = min(-f.side(R_WR) - 0.1, f.side(L_WR) - 0.1)
    return min(chest, crossed)


def hands_together(f):
    if not f.ok(L_WR, R_WR, L_HIP, R_HIP):
        return -1.0
    dist = float(np.linalg.norm(f.p[L_WR] - f.p[R_WR]))
    above_hip = f.hip_y - 0.1 - max(f.y(L_WR), f.y(R_WR))
    return min(0.35 - dist, above_hip)


def squat(f):
    if not f.ok(L_HIP, R_HIP, L_KNEE, R_KNEE):
        return -1.0
    knee_y = (f.y(L_KNEE) + f.y(R_KNEE)) / 2
    return 0.55 - (knee_y - f.hip_y)


def lean_right(f):
    if not f.ok(L_SH, R_SH, L_HIP, R_HIP):
        return -1.0
    return float(np.dot(-(f.hip_c - f.sh_c) / f.torso, f.right_dir)) - 0.3


def lean_left(f):
    if not f.ok(L_SH, R_SH, L_HIP, R_HIP):
        return -1.0
    return float(np.dot((f.hip_c - f.sh_c) / f.torso, f.right_dir)) - 0.3


def _hand_on_chest(f, sh, wr, sign):
    """Bent arm with the hand resting on the same-side shoulder/chest ("ab" sketch)."""
    if not f.ok(sh, wr):
        return -1.0
    near = 0.5 - float(np.linalg.norm(f.p[wr] - f.p[sh]))
    own_side = sign * f.side(wr) - 0.1
    return min(near, own_side)


def right_hand_chest(f):
    return _hand_on_chest(f, R_SH, R_WR, 1.0)


def left_hand_chest(f):
    return _hand_on_chest(f, L_SH, L_WR, -1.0)


def _forearm_front(f, wr, other_wr, sign):
    """Forearm held across the body at chest height, other arm hanging ("wha" sketch)."""
    if not f.ok(wr, other_wr, L_HIP, R_HIP):
        return -1.0
    across = -sign * f.side(wr) + 0.05
    height = min(f.y(wr) - 0.1, f.hip_y - 0.2 - f.y(wr))
    other_down = f.y(other_wr) - (f.hip_y - 0.3)
    return min(across, height, other_down)


def right_forearm_front(f):
    return _forearm_front(f, R_WR, L_WR, 1.0)


def left_forearm_front(f):
    return _forearm_front(f, L_WR, R_WR, -1.0)


def hands_on_hips(f):
    """Both hands on the hips with elbows pointing out ("thin" sketch)."""
    if not f.ok(L_WR, R_WR, L_EL, R_EL, L_HIP, R_HIP):
        return -1.0
    margins = []
    for sh, el, wr, hip, sign in ((R_SH, R_EL, R_WR, R_HIP, 1.0), (L_SH, L_EL, L_WR, L_HIP, -1.0)):
        margins.append(0.45 - float(np.linalg.norm(f.p[wr] - f.p[hip])))
        margins.append(sign * (f.side(el) - f.side(sh)) - 0.22)
    return min(margins)


def _foot_up(f, ank, other_ank):
    """One foot lifted clearly above the other ("been" leg sketch)."""
    if not f.ok(ank, other_ank):
        return -1.0
    return (f.y(other_ank) - f.y(ank)) - 0.45


def right_foot_up(f):
    return _foot_up(f, R_ANK, L_ANK)


def left_foot_up(f):
    return _foot_up(f, L_ANK, R_ANK)


STATIC = {
    "right_hand_up": right_hand_up,
    "left_hand_up": left_hand_up,
    "both_hands_up": both_hands_up,
    "right_arm_out": right_arm_out,
    "left_arm_out": left_arm_out,
    "t_pose": t_pose,
    "arms_crossed": arms_crossed,
    "hands_together": hands_together,
    "squat": squat,
    "lean_left": lean_left,
    "lean_right": lean_right,
    "right_hand_chest": right_hand_chest,
    "left_hand_chest": left_hand_chest,
    "right_forearm_front": right_forearm_front,
    "left_forearm_front": left_forearm_front,
    "hands_on_hips": hands_on_hips,
    "right_foot_up": right_foot_up,
    "left_foot_up": left_foot_up,
}

# impulse gestures: (wrist index, direction sign: +1 down / -1 up)
IMPULSE = {
    "right_swipe_down": (R_WR, 1.0),
    "left_swipe_down": (L_WR, 1.0),
    "right_swipe_up": (R_WR, -1.0),
    "left_swipe_up": (L_WR, -1.0),
}


# ---- recorded poses -----------------------------------------------------------
ARM_JOINTS = [L_EL, R_EL, L_WR, R_WR]
LEG_JOINTS = [L_KNEE, R_KNEE, L_ANK, R_ANK]


def pose_vector(f: Features, joints: list) -> np.ndarray:
    return np.stack([f.frame(i) for i in joints])


def make_pose_gesture(template: dict):
    """Gesture rule from a recorded pose: mean joint distance under a threshold."""
    joints = template["joints"]
    target = np.array(template["vector"], dtype=np.float32)
    threshold = float(template.get("threshold", 0.3))

    def rule(f):
        if not f.ok(*joints):
            return -1.0
        dist = float(np.mean(np.linalg.norm(pose_vector(f, joints) - target, axis=1)))
        return threshold - dist

    return rule


def register_pose(name: str, template: dict):
    STATIC[name] = make_pose_gesture(template)


def all_gestures() -> list:
    return list(STATIC) + list(IMPULSE)


class GestureDetector:
    """Per-dancer state machine producing start/end/hit events."""

    def __init__(self, hysteresis=0.15, hold_frames=2, release_frames=3,
                 swipe_speed=4.0, swipe_cooldown=0.3, window=0.1):
        self.hysteresis = hysteresis
        self.hold_frames = hold_frames
        self.release_frames = release_frames
        self.swipe_speed = swipe_speed
        self.swipe_cooldown = swipe_cooldown
        self.window = window
        self.active = set()
        self.counters = {}
        self.history = {R_WR: deque(), L_WR: deque()}
        self.last_hit = {n: -1e9 for n in IMPULSE}
        self.margins = {}

    def reset(self):
        events = [(n, "end") for n in self.active]
        self.active.clear()
        self.counters = {}
        for h in self.history.values():
            h.clear()
        return events

    def update(self, f: Features, t: float) -> list:
        events = []
        for name, fn in STATIC.items():
            m = fn(f)
            self.margins[name] = m
            self.counters.setdefault(name, 0)
            if name in self.active:
                if m < -self.hysteresis:
                    self.counters[name] += 1
                    if self.counters[name] >= self.release_frames:
                        self.active.discard(name)
                        self.counters[name] = 0
                        events.append((name, "end"))
                else:
                    self.counters[name] = 0
            else:
                if m > 0:
                    self.counters[name] += 1
                    if self.counters[name] >= self.hold_frames:
                        self.active.add(name)
                        self.counters[name] = 0
                        events.append((name, "start"))
                else:
                    self.counters[name] = 0

        for wr, hist in self.history.items():
            if f.ok(wr):
                hist.append((t, f.y(wr)))
            while hist and t - hist[0][0] > self.window:
                hist.popleft()
        for name, (wr, sign) in IMPULSE.items():
            hist = self.history[wr]
            if len(hist) < 2 or t - self.last_hit[name] < self.swipe_cooldown:
                continue
            (t0, y0), (t1, y1) = hist[0], hist[-1]
            dt = t1 - t0
            if dt <= 0:
                continue
            vel = sign * (y1 - y0) / dt
            if vel > self.swipe_speed:
                self.last_hit[name] = t
                events.append((name, "hit"))
        return events

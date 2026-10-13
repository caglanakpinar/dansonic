"""Motion recognition on 2D pose landmarks (MediaPipe, 33 points).

A motion is a rule on one pose, measured in torso units (the shoulder-to-hip distance, origin at the
shoulder centre, y pointing down). The rule returns a margin: above 0 the pose is held. The detector turns
that into start/end events with hysteresis and a few frames of hold, so a motion fires once when it begins
and has to be left and entered again to fire again. Impulses (swipes, clap) fire once per fast movement.

Sides are the dancer's own left and right. A one-sided motion is registered twice, as `left_<name>` and
`right_<name>`; the bare `<name>` stands for either, see `expand`.

Rules that name one arm also need the other arm down, so a two-armed pose never fires the one-armed motion
of the same family. That keeps the motions of different sounds apart.
"""
from collections import deque, namedtuple

import numpy as np

NOSE = 0
L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 23, 24, 25, 26, 27, 28

VIS = 0.5           # landmarks less visible than this are not trusted
HANG = 0.5          # a wrist this far below the shoulder line is a hanging arm (a hanging wrist is at about 0.9)
FACING = 0.5        # shoulder width (torso units) below which the dancer is turned away: sideways rules switch off
FACING_ACROSS = 0.42    # the sweep across the chest twists the body (the dancers' shoulders drop to 0.5), so this one is looser
ACROSS_REACH = 0.0      # how far over the centre line the hand has to get for arm_across (0: touching it is enough)
ACROSS_HYSTERESIS = 0.05    # the sweep comes and goes fast: it ends as soon as the hand leaves, so the next sweep counts again
ACROSS_SURE = 0.8       # arm_across fires on the first frame it is seen when the wrist and the elbow are visible this clearly
CROSS_REACH = 0.1       # chest_cross (an arm held across, no sweep): the hand this far past the centre line, so touching hands do not count
LEG_UP_DEGREES = 75.0   # leg_up: the thigh has to be lifted at least this far from hanging straight down (90: horizontal)
LEAN_DEGREES = 8.0      # lean_across: the torso (hips to shoulders) has to be tilted at least this far from upright ...
LEAN_MAX_DEGREES = 50.0     # ... and not further: a dancer on the floor or upside down is not leaning
LEAN_HYSTERESIS = 0.04      # ends 3.6 degrees under the limit, so a lean to the other side starts it again

Side = namedtuple("Side", "name sh el wr knee ank o_sh o_el o_wr o_knee o_ank sign")
RIGHT = Side("right", R_SH, R_EL, R_WR, R_KNEE, R_ANK, L_SH, L_EL, L_WR, L_KNEE, L_ANK, 1.0)
LEFT = Side("left", L_SH, L_EL, L_WR, L_KNEE, L_ANK, R_SH, R_EL, R_WR, R_KNEE, R_ANK, -1.0)
SWAP = {L_SH: R_SH, R_SH: L_SH, L_EL: R_EL, R_EL: L_EL, L_WR: R_WR, R_WR: L_WR, L_HIP: R_HIP, R_HIP: L_HIP,
        L_KNEE: R_KNEE, R_KNEE: L_KNEE, L_ANK: R_ANK, R_ANK: L_ANK}


class Features:
    """Landmark geometry normalized by torso length and expressed in the dancer's frame."""

    def __init__(self, lm: np.ndarray, aspect: float, torso: float = None):
        # scale x by the frame aspect ratio so distances are isotropic
        self.lm, self.aspect = lm, aspect
        pts = lm[:, :2].copy()
        pts[:, 0] *= aspect
        self.pts = pts                                  # absolute, frame units
        self.vis = lm[:, 2]
        self.sh_c = (pts[L_SH] + pts[R_SH]) / 2
        self.hip_c = (pts[L_HIP] + pts[R_HIP]) / 2
        # the unit of every distance; the detector passes a steadier one than this frame's own (see MotionDetector)
        self.torso = torso if torso else max(1e-3, float(np.linalg.norm(self.sh_c - self.hip_c)))
        self.shoulder_w = float(np.linalg.norm(pts[L_SH] - pts[R_SH])) / self.torso
        right_dir = pts[R_SH] - pts[L_SH]
        norm = np.linalg.norm(right_dir)
        self.right_dir = right_dir / norm if norm > 1e-6 else np.array([-1.0, 0.0])
        self.p = (pts - self.sh_c) / self.torso      # torso units, origin at shoulder center
        self.hip_y = float(self.p[L_HIP][1] + self.p[R_HIP][1]) / 2

    def rescaled(self, torso: float) -> "Features":
        """The same landmarks measured in another torso length."""
        return Features(self.lm, self.aspect, torso)

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

    def out(self, i, s: Side) -> float:
        """How far landmark i is from the body's centre line, on the outer side of arm/leg `s` (negative: crossed over)."""
        return s.sign * self.side(i)

    def dist(self, i, j) -> float:
        return float(np.linalg.norm(self.p[i] - self.p[j]))

    @property
    def facing(self) -> float:
        """Above 0 while the dancer faces the camera. A turned torso makes arms look crossed or out when they are not."""
        return self.shoulder_w - FACING


# ---- the motion catalogue ---------------------------------------------------------
MOTIONS = {}        # name -> rule(f) -> margin
DOCS = {}           # name -> one line for --motions
FAMILY = {}         # name -> bare name (the one config files use)
IMPULSE = {}        # name -> (wrist index, direction sign: +1 down / -1 up)
HYSTERESIS = {}     # name -> how far past its limit a pose must fall before it ends (default: the detector's)
SURE = {}           # name -> sure(f): while it is true a start fires on the first frame (default: after hold_frames frames)
CLAP = "clap"
FLAIL = "arms_flail"
JUMP_ARMS = "jump_arms_out"


def _one_sided(doc, hysteresis=None, sure=None):
    def register(fn):
        for s in (LEFT, RIGHT):
            name = f"{s.name}_{fn.__name__}"
            MOTIONS[name] = (lambda f, s=s: fn(f, s))
            DOCS[name] = doc
            FAMILY[name] = fn.__name__
            if hysteresis is not None:
                HYSTERESIS[name] = hysteresis
            if sure is not None:
                SURE[name] = (lambda f, s=s: sure(f, s))
        return fn
    return register


def _two_sided(doc, hysteresis=None, sure=None):
    def register(fn):
        MOTIONS[fn.__name__] = fn
        DOCS[fn.__name__] = doc
        FAMILY[fn.__name__] = fn.__name__
        if hysteresis is not None:
            HYSTERESIS[fn.__name__] = hysteresis
        if sure is not None:
            SURE[fn.__name__] = sure
        return fn
    return register


def _forearm(f, s):
    """The geometry of an upright forearm with the hand between chest and chin (no other-arm condition)."""
    rise = f.y(s.el) - f.y(s.wr)
    return min(rise - 0.28,                                 # the forearm points up
               0.6 * rise - abs(f.side(s.wr) - f.side(s.el)),   # and is roughly upright
               f.y(s.wr) - (f.y(NOSE) + 0.05),              # hand below the nose
               0.45 - f.y(s.wr),                            # above the belly
               f.y(s.el) - 0.1,                             # elbow below the shoulder line
               f.out(s.wr, s) + 0.1)                        # hand has not crossed the centre line


@_one_sided("bent arm, forearm upright, hand between chest and chin, other arm down (ab sketches)")
def forearm_up(f, s):
    if not f.ok(NOSE, s.sh, s.el, s.wr, s.o_wr):
        return -1.0
    return min(_forearm(f, s), f.y(s.o_wr) - HANG)


@_one_sided("hand beside the head or face, other arm down (ab sketch with the up arrow)")
def hand_to_head(f, s):
    if not f.ok(NOSE, s.sh, s.wr, s.o_wr):
        return -1.0
    return min(0.6 - f.dist(s.wr, NOSE),                    # near the face
               -0.1 - f.y(s.wr),                            # above the shoulder line
               f.y(s.o_wr) - HANG)


@_one_sided("hand raised above the nose, either arm, the other arm does not matter (v1's hand up)")
def hand_up(f, s):
    if not f.ok(NOSE, s.wr):
        return -1.0
    return f.y(NOSE) - f.y(s.wr) - 0.05


@_one_sided("one arm straight up above the head, other arm down (video: right arm up on the diagonal)")
def arm_up(f, s):
    if not f.ok(NOSE, s.sh, s.wr, s.o_wr):
        return -1.0
    return min(f.y(NOSE) - f.y(s.wr) - 0.15,                # hand above the head
               f.dist(s.sh, s.wr) - 0.7,                    # arm fairly straight
               f.y(s.o_wr) - HANG)


def _across_terms(f, s) -> dict:
    """The conditions of arm_across, each as a margin (above 0: met). The D key shows them."""
    if not f.ok(s.sh, s.wr):
        return {"cross": -1.0, "height": -1.0, "other arm": -1.0, "facing": -1.0}
    y = f.y(s.wr)
    return {"cross": -f.out(s.wr, s) - ACROSS_REACH,                    # the hand reached the other side
            "height": min(y + 0.3, 0.85 - y),                           # between the collar and the belly
            "other arm": f.y(s.o_wr) - HANG if f.ok(s.o_wr) else 1.0,   # down (out of the picture counts as down)
            "facing": f.shoulder_w - FACING_ACROSS}                     # not turned away


def _seen_clearly(f, s) -> bool:
    """The wrist and the elbow of arm s are tracked with confidence: a start of this arm is no one-frame glitch."""
    return bool(f.vis[s.wr] >= ACROSS_SURE and f.vis[s.el] >= ACROSS_SURE)


@_one_sided("forearm across the chest, hand over on the other side, other arm down (thin sketch)",
            hysteresis=ACROSS_HYSTERESIS, sure=_seen_clearly)
def arm_across(f, s):
    return min(_across_terms(f, s).values())


def _lean_degrees(f):
    """How far the torso is tilted sideways from upright, in degrees (0: upright), or None while the hips are not seen."""
    if not f.ok(L_SH, R_SH, L_HIP, R_HIP):
        return None
    v = f.sh_c - f.hip_c                                        # hips to shoulders, y pointing down
    if v[1] >= 0:
        return 180.0
    return float(np.degrees(np.arctan2(abs(v[0]), -v[1])))


def _lean_terms(f) -> dict:
    """The conditions of lean_across, each as a margin (above 0: met). The D key shows them."""
    tilt = _lean_degrees(f)
    if tilt is None:
        return {"tilt": -1.0, "arm over": -1.0}
    return {"tilt": min(tilt - LEAN_DEGREES, LEAN_MAX_DEGREES - tilt) / 90.0,       # every 0.1 is 9 degrees
            "arm over": _arm_over(f)}                           # an arm (or both) over the chest; the other may be anywhere


@_two_sided("leaning sideways, to the left or to the right, with an arm (or both) across the chest (thin)",
            hysteresis=LEAN_HYSTERESIS)
def lean_across(f):
    return min(_lean_terms(f).values())


def _arm_over(f, reach=0.0) -> float:
    """Margin of the better arm to be over the chest: the hand past the centre line (by `reach`) and between the collar
    and the belly. The other arm may be anywhere."""
    return max(min(t["cross"] - reach, t["height"]) for t in (_across_terms(f, s) for s in (LEFT, RIGHT)))


def _over_seen_clearly(f) -> bool:
    """An arm that is over the chest is tracked with confidence (see _seen_clearly)."""
    for s in (LEFT, RIGHT):
        t = _across_terms(f, s)
        if _seen_clearly(f, s) and min(t["cross"] - CROSS_REACH, t["height"]) > 0:
            return True
    return False


@_two_sided("an arm (or both, an X) held across the chest, no sweep needed: the hand past the centre line, the other arm "
            "anywhere (thin)", hysteresis=ACROSS_HYSTERESIS, sure=_over_seen_clearly)
def chest_cross(f):
    return min(_arm_over(f, CROSS_REACH), f.shoulder_w - FACING_ACROSS)       # a turned dancer's arms only look crossed


def _arm_out(f, s):
    return min(f.out(s.wr, s) - f.out(s.sh, s) - 0.55,      # hand well beyond the shoulder
               0.4 - abs(f.y(s.wr) - f.y(s.sh)))            # at about shoulder height


@_one_sided("one arm held out to the side at shoulder height, other arm down (wha sketch)")
def arm_out(f, s):
    if not f.ok(s.sh, s.wr, s.o_wr):
        return -1.0
    return min(_arm_out(f, s), f.y(s.o_wr) - HANG, f.facing)


@_two_sided("both arms held out to the sides")
def t_pose(f):
    if not f.ok(L_SH, R_SH, L_WR, R_WR):
        return -1.0
    return min(_arm_out(f, RIGHT), _arm_out(f, LEFT), f.facing)


@_two_sided("both forearms upright, hands apart between chest and chin (the ab sketches with both arms)")
def both_forearms_up(f):
    if not f.ok(NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR):
        return -1.0
    return min(_forearm(f, RIGHT), _forearm(f, LEFT), f.dist(L_WR, R_WR) - 0.45)


@_two_sided("both arms out to the sides, hands at chest height or higher (a hanging arm never counts)")
def arms_to_sides(f):
    """Arms only: each hand clearly out from its own shoulder and well above the hanging height (a hanging wrist is at
    about 0.9 to 1.1), the hands far apart. The body may be turned (the twist), so the facing is not checked."""
    if not f.ok(L_SH, R_SH, L_WR, R_WR):
        return -1.0
    return min(f.dist(L_WR, R_WR) - 1.2,
               0.6 - f.y(L_WR), 0.6 - f.y(R_WR),                      # not hanging
               f.y(L_WR) + 0.4, f.y(R_WR) + 0.4,                      # not above the head
               f.out(L_WR, LEFT) - f.out(L_SH, LEFT) - 0.2,           # each hand away from its own shoulder
               f.out(R_WR, RIGHT) - f.out(R_SH, RIGHT) - 0.2)


@_two_sided("both hands on the chest, not crossed (video bar 1)")
def hands_chest(f):
    if not f.ok(L_WR, R_WR):
        return -1.0
    chest = np.array([0.0, 0.4])
    return min(0.4 - float(np.linalg.norm(f.frame(L_WR) - chest)),
               0.4 - float(np.linalg.norm(f.frame(R_WR) - chest)),
               f.out(R_WR, RIGHT) + 0.05, f.out(L_WR, LEFT) + 0.05, f.facing)


@_two_sided("hands together in front, above the hips")
def hands_together(f):
    if not f.ok(L_WR, R_WR, L_HIP, R_HIP):
        return -1.0
    return min(0.35 - f.dist(L_WR, R_WR), f.hip_y - 0.1 - max(f.y(L_WR), f.y(R_WR)))


@_two_sided("both hands on the hips, elbows out (thin sketch)")
def hands_on_hips(f):
    if not f.ok(L_WR, R_WR, L_EL, R_EL, L_HIP, R_HIP, L_SH, R_SH):
        return -1.0
    margins = []
    for s, hip in ((RIGHT, R_HIP), (LEFT, L_HIP)):
        margins.append(0.45 - f.dist(s.wr, hip))
        margins.append(f.out(s.el, s) - f.out(s.sh, s) - 0.22)
    return min(margins + [f.facing])


@_two_sided("both hands above the head")
def both_hands_up(f):
    if not f.ok(NOSE, L_WR, R_WR):
        return -1.0
    return min(f.y(NOSE) - f.y(R_WR) - 0.05, f.y(NOSE) - f.y(L_WR) - 0.05)


@_two_sided("arms crossed over the chest, hands on the opposite shoulders")
def arms_crossed(f):
    if not f.ok(L_WR, R_WR, L_HIP, R_HIP):
        return -1.0
    chest = min(f.hip_y - f.y(R_WR), f.hip_y - f.y(L_WR), f.y(R_WR) + 0.3, f.y(L_WR) + 0.3)
    crossed = min(-f.out(R_WR, RIGHT) - 0.1, -f.out(L_WR, LEFT) - 0.1)
    return min(chest, crossed, f.facing)


@_two_sided("both arms open, away from the body and low (an open A shape)")
def arms_open(f):
    if not f.ok(L_SH, R_SH, L_WR, R_WR):
        return -1.0
    margins = [f.facing]
    for s in (RIGHT, LEFT):
        margins += [f.out(s.wr, s) - f.out(s.sh, s) - 0.6,      # hand well away from the body
                    f.y(s.wr) - 0.4,                            # below the shoulder line ...
                    1.05 - f.y(s.wr)]                           # ... but not hanging straight down
    return min(margins)


@_one_sided("one foot lifted clearly above the other (leg kick, step)")
def foot_up(f, s):
    if not f.ok(s.ank, s.o_ank):
        return -1.0
    return (f.y(s.o_ank) - f.y(s.ank)) - 0.45


@_one_sided("one knee lifted clearly above the other")
def knee_up(f, s):
    if not f.ok(s.knee, s.o_knee):
        return -1.0
    return (f.y(s.o_knee) - f.y(s.knee)) - 0.4


def _leg_terms(f, s) -> dict:
    """The conditions of leg_up, each as a margin (above 0: met). The D key shows them.

    How far the thigh is lifted is read from the knee's height under the hip (the angle whose cosine is that drop over
    the thigh's length), so a knee brought towards the camera counts as much as one lifted sideways: a foreshortened
    thigh still shows how high the knee is. The standing leg's thigh gives the length to measure against."""
    hip, o_hip = (L_HIP, R_HIP) if s is LEFT else (R_HIP, L_HIP)
    if not f.ok(hip, s.knee, o_hip, s.o_knee):
        return {"lift": -1.0, "other knee": -1.0}
    thigh = float(np.clip(f.dist(o_hip, s.o_knee), 0.5, 1.1))
    drop = f.y(s.knee) - f.y(hip)                               # knee below the hip: positive; above it: negative
    degrees = float(np.degrees(np.arccos(np.clip(drop / thigh, -1.0, 1.0))))   # 0: hanging, 90: level with the hip
    return {"lift": (degrees - LEG_UP_DEGREES) / 90.0,          # every 0.1 is 9 degrees past (or short of) the limit
            "other knee": (f.y(s.o_knee) - f.y(s.knee)) / thigh - 0.4}   # the other leg stands: a squat has both up


@_one_sided("one leg lifted: the thigh at least 75 degrees up from hanging (the knee near hip height), the other leg standing")
def leg_up(f, s):
    return min(_leg_terms(f, s).values())


# impulses: fast hand movements, fired once each (wrist index, direction sign: +1 down / -1 up)
for _side, _wr in (("left", L_WR), ("right", R_WR)):
    IMPULSE[f"{_side}_swipe_down"] = (_wr, 1.0)
    IMPULSE[f"{_side}_swipe_up"] = (_wr, -1.0)
    DOCS[f"{_side}_swipe_down"] = "hand swiped down fast"
    DOCS[f"{_side}_swipe_up"] = "hand swiped up fast"
    FAMILY[f"{_side}_swipe_down"] = "swipe_down"
    FAMILY[f"{_side}_swipe_up"] = "swipe_up"
DOCS[CLAP] = "hands clapped together"
DOCS[FLAIL] = "arms swiping up and down in turn (a burst of swipes)"
FAMILY[CLAP] = CLAP
FAMILY[FLAIL] = FLAIL
DOCS[JUMP_ARMS] = "a little jump and both arms out to the sides (in either order, within 1 s)"
FAMILY[JUMP_ARMS] = JUMP_ARMS


# ---- recorded poses -----------------------------------------------------------------
ARM_JOINTS = [L_EL, R_EL, L_WR, R_WR]
LEG_JOINTS = [L_KNEE, R_KNEE, L_ANK, R_ANK]


def pose_vector(f: Features, joints: list) -> np.ndarray:
    return np.stack([f.frame(i) for i in joints])


def make_pose_rule(template: dict, mirror: bool = False):
    """Rule from a recorded pose: mean joint distance under a threshold. `mirror` swaps left and right."""
    joints = list(template["joints"])
    rows = {j: np.array(v, dtype=np.float32) for j, v in zip(joints, template["vector"])}
    if mirror:
        target = np.stack([rows[SWAP[j]] * np.array([-1.0, 1.0], dtype=np.float32) for j in joints])
    else:
        target = np.stack([rows[j] for j in joints])
    threshold = float(template.get("threshold", 0.3))

    def rule(f):
        if not f.ok(*joints):
            return -1.0
        return threshold - float(np.mean(np.linalg.norm(pose_vector(f, joints) - target, axis=1)))

    return rule


def mirror_name(name: str) -> str:
    if "left_" in name:
        return name.replace("left_", "right_", 1)
    if "right_" in name:
        return name.replace("right_", "left_", 1)
    return f"{name}_mirror"


def register_pose(name: str, template: dict) -> list:
    """Adds a recorded pose, and its mirror image if the template says `"mirror": true`. Returns the names added."""
    added = [name]
    MOTIONS[name] = make_pose_rule(template)
    DOCS[name] = template.get("note", "recorded pose")
    FAMILY[name] = name
    if template.get("mirror"):
        other = mirror_name(name)
        MOTIONS[other] = make_pose_rule(template, mirror=True)
        DOCS[other] = f"{DOCS[name]} (mirrored)"
        FAMILY[other] = other
        added.append(other)
    return added


def all_motions() -> list:
    return list(MOTIONS) + list(IMPULSE) + [CLAP, FLAIL, JUMP_ARMS]


def expand(name: str) -> list:
    """The concrete motions a config name stands for: `forearm_up` is the left and the right one."""
    known = all_motions()
    if name in known:
        return [name]
    return [m for m in known if FAMILY.get(m) == name]


class MotionDetector:
    """Per-dancer state machine producing start/end events for poses and hit events for impulses."""

    def __init__(self, hysteresis=0.15, hold_frames=2, release_frames=3, swipe_speed=4.0, swipe_cooldown=0.3,
                 window=0.1, flail_hits=9, flail_window=1.5, flail_cooldown=2.0,
                 clap_speed=3.0, clap_cooldown=0.35, hop_rise=0.12, hop_hip_rise=0.08, hop_window=0.5, hop_arms_window=1.0,
                 hop_cooldown=1.0, scale_window=1.5):
        self.hysteresis = hysteresis
        self.hold_frames = hold_frames
        self.release_frames = release_frames
        self.swipe_speed = swipe_speed
        self.swipe_cooldown = swipe_cooldown
        self.window = window
        self.flail_hits = flail_hits
        self.flail_window = flail_window
        self.flail_cooldown = flail_cooldown
        self.clap_speed = clap_speed
        self.clap_cooldown = clap_cooldown
        self.hop_rise = hop_rise                # torso lengths the head and the shoulders must both rise within hop_window s
        self.hop_hip_rise = hop_hip_rise        # ... and the hips too when they are seen
        self.hop_window = hop_window
        self.hop_arms_window = hop_arms_window  # the arms must be out this soon after (or during) the hop
        self.hop_cooldown = hop_cooldown
        self.scale_window = scale_window        # the torso length is the median of this many seconds (hips are inferred and wobble)
        self.margins = {}
        self.reset()

    def reset(self):
        events = [(n, "end") for n in getattr(self, "active", ())]
        self.active = set()
        self.counters = {}
        self.history = {R_WR: deque(), L_WR: deque()}
        self.gap_history = deque()
        self.last_hit = {n: -1e9 for n in IMPULSE}
        self.last_clap = -1e9
        self.swipe_times = deque()
        self.last_flail = -1e9
        self.height_history = deque()
        self.torso_history = deque()
        self.last_hop = -1e9
        self.jump_was_on = False
        self.last_jump_arms = -1e9
        return events

    def update(self, f: Features, t: float) -> list:
        events = []
        # One frame's shoulder-to-hip distance wobbles whenever an arm moves (the hips are inferred, not seen), and it
        # is the unit of everything else. Measure with the median of the last scale_window seconds instead.
        self.torso_history.append((t, f.torso))
        while self.torso_history and t - self.torso_history[0][0] > self.scale_window:
            self.torso_history.popleft()
        f = f.rescaled(float(np.median([x for _, x in self.torso_history])))
        for name, fn in MOTIONS.items():
            m = fn(f)
            self.margins[name] = m
            c = self.counters.get(name, 0)
            if name in self.active:
                if m < -HYSTERESIS.get(name, self.hysteresis):
                    c += 1
                    if c >= self.release_frames:
                        self.active.discard(name)
                        c = 0
                        events.append((name, "end"))
                else:
                    c = 0
            elif m > 0:
                c += 1
                sure = SURE.get(name)
                if c >= (1 if sure is not None and sure(f) else self.hold_frames):
                    self.active.add(name)
                    c = 0
                    events.append((name, "start"))
            else:
                c = 0
            self.counters[name] = c

        best = max((_across_terms(f, side) for side in (LEFT, RIGHT)), key=lambda terms: min(terms.values()))
        for term, value in best.items():                         # for the D key: which condition of thin is missing
            self.margins[f"thin {term}"] = value
        best = max((_leg_terms(f, side) for side in (LEFT, RIGHT)), key=lambda terms: min(terms.values()))
        for term, value in best.items():                         # ... and of wha-been
            self.margins[f"leg {term}"] = value
        for term, value in _lean_terms(f).items():               # ... and of the lean of thin
            self.margins[f"lean {term}"] = value

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
            if t1 - t0 <= 0:
                continue
            if sign * (y1 - y0) / (t1 - t0) > self.swipe_speed:
                self.last_hit[name] = t
                events.append((name, "hit"))
                self.swipe_times.append(t)

        while self.swipe_times and t - self.swipe_times[0] > self.flail_window:
            self.swipe_times.popleft()
        if len(self.swipe_times) >= self.flail_hits and t - self.last_flail > self.flail_cooldown:
            self.last_flail = t
            self.swipe_times.clear()
            events.append((FLAIL, "hit"))

        # clap: the hands come together fast while they are in front of the body
        if f.ok(L_WR, R_WR, L_HIP, R_HIP):
            self.gap_history.append((t, f.dist(L_WR, R_WR)))
            while self.gap_history and t - self.gap_history[0][0] > 0.2:
                self.gap_history.popleft()
            if len(self.gap_history) >= 2 and t - self.last_clap >= self.clap_cooldown:
                (t0, g0), (t1, g1) = self.gap_history[0], self.gap_history[-1]
                if (t1 > t0 and g1 < 0.25 and (g0 - g1) / (t1 - t0) > self.clap_speed
                        and max(f.y(L_WR), f.y(R_WR)) < f.hip_y):
                    self.last_clap = t
                    self.gap_history.clear()
                    events.append((CLAP, "hit"))

        # little jump: the head, the shoulders and (when seen) the hips all bob up together within hop_window seconds.
        # Raising an arm moves the shoulders a little, never the head: that alone is not a jump.
        heights = {"nose": float(f.pts[NOSE][1]) if f.vis[NOSE] > 0.4 else None,
                   "shoulders": float(f.sh_c[1]) if f.ok(L_SH, R_SH) else None,
                   "hips": float(f.hip_c[1]) if f.ok(L_HIP, R_HIP) else None}
        self.height_history.append((t, heights))
        while self.height_history and t - self.height_history[0][0] > self.hop_window:
            self.height_history.popleft()
        need = {"nose": self.hop_rise, "shoulders": self.hop_rise, "hips": self.hop_hip_rise}
        hop = {}
        for part, now in heights.items():
            if now is not None:
                top = max(h[part] for _, h in self.height_history if h[part] is not None)   # image y grows downwards
                hop[part] = (top - now) / f.torso - need[part]
                self.margins[f"hop {part}"] = hop[part]
        hop_margin = min(hop.values()) if "nose" in hop and "shoulders" in hop else -1.0
        self.margins["hop (rise)"] = hop_margin                  # for the D key: above 0 while the whole body bobs up
        if hop_margin >= 0:
            self.last_hop = t
        # jump_arms_out: a little jump and both arms out to the sides, in either order within hop_arms_window
        arms_out = "arms_to_sides" in self.active                # held for hold_frames, kept through small dropouts
        on = arms_out and t - self.last_hop <= self.hop_arms_window
        self.margins[JUMP_ARMS] = 0.1 if on else min(self.margins.get("arms_to_sides", -1.0), hop_margin)
        if on and not self.jump_was_on and t - self.last_jump_arms >= self.hop_cooldown:
            self.last_jump_arms = t
            events.append((JUMP_ARMS, "hit"))
        self.jump_was_on = on
        return events

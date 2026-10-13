"""Synthetic stick figures for testing the gesture rules.

A pose is described in the dancer's frame, in torso units (shoulder-to-hip distance = 1, origin at the shoulder
centre, y pointing down). Arms are given in *outward* coordinates, (out, y), so the same numbers describe the left
and the right arm; out is the distance from the body's centre line, negative once the arm crosses it.
"""
import numpy as np

SHOULDER = 0.33         # half the shoulder width
HIP = 0.2
NOSE_Y = -0.55

ARM_DOWN = ((0.40, 0.50), (0.42, 0.98))             # (elbow, wrist)
LEG_STAND = ((0.20, 1.76), (0.20, 2.45))            # (knee, ankle)


def make_pose(R=ARM_DOWN, L=ARM_DOWN, right_leg=LEG_STAND, left_leg=LEG_STAND, nose=(0.0, NOSE_Y),
              noise=0.0, rng=None, scale=0.2, centre=(0.5, 0.35), aspect=0.56, shoulder=SHOULDER, tilt=0.0):
    """33 landmarks (x, y, visibility) as MediaPipe would give them for a dancer facing the camera.

    aspect is width / height of the frame, scale the torso length as a share of the frame height. noise adds
    gaussian jitter (torso units); shoulder changes the shoulder width; tilt rotates the whole body (radians)."""
    rng = rng or np.random.default_rng(0)
    pts = {}                                        # landmark -> (x toward own right, y down), torso units

    def arm(side_sign, spec, sh, el, wr):
        (eo, ey), (wo, wy) = spec
        pts[sh] = (side_sign * shoulder, 0.0)
        pts[el] = (side_sign * eo, ey)
        pts[wr] = (side_sign * wo, wy)

    arm(+1.0, R, 12, 14, 16)
    arm(-1.0, L, 11, 13, 15)
    pts[0] = nose
    pts[24], pts[23] = (HIP, 1.0), (-HIP, 1.0)
    for sign, leg, knee, ank in ((+1.0, right_leg, 26, 28), (-1.0, left_leg, 25, 27)):
        (ko, ky), (ao, ay) = leg
        pts[knee] = (sign * ko, ky)
        pts[ank] = (sign * ao, ay)
    lm = np.zeros((33, 3), dtype=np.float32)
    lm[:, 2] = 1.0
    c, s = np.cos(tilt), np.sin(tilt)
    for i in range(33):
        x, y = pts.get(i, pts[0] if i < 11 else (0.0, 1.0))
        x, y = c * x - s * y, s * x + c * y
        x += rng.normal(0, noise) if noise else 0.0
        y += rng.normal(0, noise) if noise else 0.0
        # a dancer facing the camera: their right is the left of the image
        lm[i, 0] = centre[0] - x * scale / aspect
        lm[i, 1] = centre[1] + y * scale
    return lm


# ---- arms (elbow, wrist) in outward coordinates ------------------------------------------------------------------
HANDS_CHEST = ((0.30, 0.60), (0.15, 0.40))          # both hands on the chest, elbows in
HANDS_CHEST_WIDE = ((0.45, 0.60), (0.22, 0.45))     # a looser version, hands further apart
HANDS_CHEST_HIGH = ((0.30, 0.45), (0.12, 0.25))     # hands high on the chest
CROSSED = ((0.20, 0.45), (-0.25, 0.15))             # arms crossed, hands on the opposite shoulders
HANDS_BELLY = ((0.30, 0.55), (0.12, 0.85))          # hands clasped low in front of the belly
HANDS_SOLAR = ((0.25, 0.70), (0.04, 0.65))          # hands clasped just below the chest
HANDS_SHOULDERS = ((0.28, 0.45), (0.26, 0.0))       # forearms up, hands at the shoulders
HANDS_FACE = ((0.40, 0.25), (0.15, -0.45))          # hands at the face
HANDS_HIPS = ((0.62, 0.55), (0.22, 0.95))
ARM_OUT = ((0.80, 0.05), (1.28, 0.05))
ARM_UP = ((0.55, -0.30), (0.62, -0.95))
HAND_CLASP_CENTRE = ((0.20, 0.60), (0.04, 0.58))    # hands joined in the middle, at the lower edge of the chest
HANDS_LOW = ((0.28, 0.70), (0.12, 0.62))            # hands low on the chest, apart
HANDS_OVERLAP = ((0.25, 0.60), (-0.06, 0.38))       # hands over each other in the middle of the chest
HANDS_CROSSED_LITTLE = ((0.25, 0.55), (-0.12, 0.36))
FOREARMS_UP_SIDE = ((0.50, 0.45), (0.50, -0.02))    # forearms upright, hands beside the shoulders
ARMS_FOLDED = ((0.20, 0.45), (-0.45, 0.15))         # arms folded: each hand on the other shoulder
HANDS_POCKETS = ((0.38, 0.55), (0.22, 0.92))        # hands in the trouser pockets
HANDS_BEHIND_HEAD = ((0.55, -0.35), (0.12, -0.60))  # fingers laced behind the head, elbows out

OPENING_POSES = {            # the strict rule (hands_on_chest) takes these at once
    "hands_chest": dict(R=HANDS_CHEST, L=HANDS_CHEST),
    "hands_chest_wide": dict(R=HANDS_CHEST_WIDE, L=HANDS_CHEST_WIDE),
    "hands_chest_high": dict(R=HANDS_CHEST_HIGH, L=HANDS_CHEST_HIGH),
}
LOOSE_OPENING_POSES = {      # ab ab done more freely: only the loose rules take these, and only when held
    "hands_low": dict(R=HANDS_LOW, L=HANDS_LOW),
    "hands_overlap": dict(R=HANDS_OVERLAP, L=HANDS_OVERLAP),
    "hands_crossed_a_little": dict(R=HANDS_CROSSED_LITTLE, L=HANDS_CROSSED_LITTLE),
    "forearms_up_side": dict(R=FOREARMS_UP_SIDE, L=FOREARMS_UP_SIDE),
}
NOT_EVEN_LOOSE = {           # no version of the opening, however forgiving
    "neutral": dict(),
    "arms_folded": dict(R=ARMS_FOLDED, L=ARMS_FOLDED),
    "hands_belly": dict(R=HANDS_BELLY, L=HANDS_BELLY),
    "hands_pockets": dict(R=HANDS_POCKETS, L=HANDS_POCKETS),
    "hands_behind_head": dict(R=HANDS_BEHIND_HEAD, L=HANDS_BEHIND_HEAD),
    "hands_face": dict(R=HANDS_FACE, L=HANDS_FACE),
    "hands_on_hips": dict(R=HANDS_HIPS, L=HANDS_HIPS),
    "t_pose": dict(R=ARM_OUT, L=ARM_OUT),
    "both_hands_up": dict(R=ARM_UP, L=ARM_UP),
    "one_hand_on_chest": dict(R=HANDS_CHEST),
    "right_arm_up": dict(R=ARM_UP),
}
NOT_THE_OPENING = {
    "neutral": dict(),
    "arms_crossed": dict(R=CROSSED, L=CROSSED),
    "hands_belly": dict(R=HANDS_BELLY, L=HANDS_BELLY),
    "hands_shoulders": dict(R=HANDS_SHOULDERS, L=HANDS_SHOULDERS),
    "hands_face": dict(R=HANDS_FACE, L=HANDS_FACE),
    "hands_on_hips": dict(R=HANDS_HIPS, L=HANDS_HIPS),
    "t_pose": dict(R=ARM_OUT, L=ARM_OUT),
    "both_hands_up": dict(R=ARM_UP, L=ARM_UP),
    "one_hand_on_chest": dict(R=HANDS_CHEST),
    "right_arm_up": dict(R=ARM_UP),
    "hands_clasped_below": dict(R=HAND_CLASP_CENTRE, L=HAND_CLASP_CENTRE),
    "hands_solar_plexus": dict(R=HANDS_SOLAR, L=HANDS_SOLAR),
}


def pose(name: str, **kw) -> np.ndarray:
    spec = OPENING_POSES.get(name) or LOOSE_OPENING_POSES.get(name) or NOT_THE_OPENING.get(name) or NOT_EVEN_LOOSE[name]
    return make_pose(**spec, **kw)

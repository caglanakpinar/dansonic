"""Synthetic stick figures for testing the motion rules.

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


# ---- arms (elbow, wrist) in outward coordinates --------------------------------------------------
FOREARM_TUCKED = ((0.28, 0.45), (0.26, 0.0))        # ab sketch 1: hand at the chin/shoulder, elbow tucked
FOREARM_SIDE = ((0.50, 0.45), (0.50, -0.02))        # ab sketch 2: forearm upright at the side
HAND_CHEEK = ((0.40, 0.25), (0.15, -0.45))          # ab sketch 3: hand beside the cheek
ARM_UP_DIAG = ((0.55, -0.30), (0.75, -0.95))        # video: right arm straight up on the diagonal
ARM_UP_STRAIGHT = ((0.40, -0.45), (0.45, -1.20))
HANDS_CHEST = ((0.30, 0.60), (0.15, 0.40))
HANDS_HIPS = ((0.62, 0.55), (0.22, 0.95))
ARM_ACROSS = ((0.15, 0.45), (-0.25, 0.10))          # teen sketch 2: hand at the other shoulder
ARM_ACROSS_REACH = ((0.05, 0.40), (-0.70, 0.30))    # across the chest and out past the other side
ARM_OUT = ((0.80, 0.05), (1.28, 0.05))              # wha sketch: straight out to the side
ARM_OUT_DROOP = ((0.75, 0.20), (1.12, 0.33))        # out and a little below the shoulder
ARM_OPEN = ((0.70, 0.45), (1.02, 0.78))            # an open A shape
ARM_SWAY = ((0.55, 0.40), (0.85, 0.70))             # a relaxed swing, not a move
ARM_CROSS_X = ((0.20, 0.45), (-0.25, 0.15))
ARM_V = ((0.55, -0.30), (0.62, -0.95))              # arm up for both_hands_up
LEG_LIFTED = ((0.45, 1.10), (0.40, 1.85))           # video 1:17 and 1:48: thigh near level with the hip, shin hanging
SQUAT_LEG = ((0.45, 1.25), (0.60, 2.00))            # a deep squat: both knees high, not a lifted leg


POSES = {
    # one arm up (the ab sketches)
    "forearm_tucked": dict(R=FOREARM_TUCKED),
    "forearm_side": dict(R=FOREARM_SIDE),
    "forearm_side_left": dict(L=FOREARM_SIDE),
    "hand_cheek": dict(R=HAND_CHEEK),
    "hand_cheek_left": dict(L=HAND_CHEEK),
    "arm_up_diag": dict(R=ARM_UP_DIAG),
    "arm_up_straight_left": dict(L=ARM_UP_STRAIGHT),
    # both arms: the motions that play ab-ab
    "both_forearms_tucked": dict(R=FOREARM_TUCKED, L=FOREARM_TUCKED),
    "both_forearms_side": dict(R=FOREARM_SIDE, L=FOREARM_SIDE),
    "hands_chest": dict(R=HANDS_CHEST, L=HANDS_CHEST),
    # hips and across the chest (the teen sketches)
    "hands_on_hips": dict(R=HANDS_HIPS, L=HANDS_HIPS),
    "arm_across": dict(R=ARM_ACROSS),
    "arm_across_left": dict(L=ARM_ACROSS),
    "arm_across_reach": dict(R=ARM_ACROSS_REACH),
    "lean_arm_across": dict(R=ARM_ACROSS, tilt=0.3),            # leaning ~17 degrees with the forearm across
    # legs (the been sketches)
    "foot_up_right": dict(right_leg=((0.25, 1.76), (0.20, 1.75))),
    "foot_up_left": dict(left_leg=((0.25, 1.76), (0.20, 1.75))),
    "knee_up_right": dict(right_leg=((0.25, 1.30), (0.25, 2.0))),
    "knee_up_left": dict(left_leg=((0.25, 1.30), (0.25, 2.0))),
    "leg_up_right": dict(right_leg=LEG_LIFTED),
    "leg_up_left": dict(left_leg=LEG_LIFTED),
    # one or both arms out to the side (the wha sketch)
    "arm_out": dict(R=ARM_OUT),
    "arm_out_left": dict(L=ARM_OUT),
    "arm_out_droop": dict(R=ARM_OUT_DROOP),
    "t_pose": dict(R=ARM_OUT, L=ARM_OUT),
    "arms_open": dict(R=ARM_OPEN, L=ARM_OPEN),
    # big two-arm moves
    "both_hands_up": dict(R=ARM_V, L=ARM_V),
    "arms_crossed": dict(R=ARM_CROSS_X, L=ARM_CROSS_X),
    # not moves: nothing may fire
    "neutral": dict(),
    "arm_sway": dict(R=ARM_SWAY),
    "arms_sway": dict(R=ARM_SWAY, L=ARM_SWAY),
    "step_forward": dict(right_leg=((0.20, 1.80), (0.20, 2.30))),
    "hands_low_front": dict(R=((0.30, 0.55), (0.12, 0.85)), L=((0.30, 0.55), (0.12, 0.85))),
    "lean": dict(tilt=0.2),
    "squat_deep": dict(right_leg=SQUAT_LEG, left_leg=SQUAT_LEG),
}

# The motion library in families, a fixture for the tests (labels only, no sound files). The live config plays one
# sound, ab-ab, with the motions of the "ab-ab" family; the other families are motions it does not use.
LIBRARY = {
    "one_arm_up": {"motions": ["forearm_up", "hand_to_head", "arm_up"]},
    "ab-ab": {"motions": ["both_forearms_up", "hands_chest", "clap"]},
    "hips_across": {"motions": ["hands_on_hips", "arm_across", "lean_across", "squat_wide"]},
    "legs": {"motions": ["foot_up", "knee_up", "leg_up", "arm_sweep"]},
    "arm_out": {"motions": ["arm_out", "t_pose", "arms_open"]},
    "big_arms": {"motions": ["both_hands_up", "arms_crossed", "arms_flail"], "cooldown": 1.4, "protect": 1.3},
}

# which family each pose belongs to (None: not a move, nothing may fire)
EXPECTED = {
    "forearm_tucked": "one_arm_up", "forearm_side": "one_arm_up", "forearm_side_left": "one_arm_up",
    "hand_cheek": "one_arm_up", "hand_cheek_left": "one_arm_up", "arm_up_diag": "one_arm_up",
    "arm_up_straight_left": "one_arm_up",
    "both_forearms_tucked": "ab-ab", "both_forearms_side": "ab-ab", "hands_chest": "ab-ab",
    "hands_on_hips": "hips_across", "arm_across": "hips_across", "arm_across_left": "hips_across",
    "arm_across_reach": "hips_across", "lean_arm_across": "hips_across",
    "foot_up_right": "legs", "foot_up_left": "legs", "knee_up_right": "legs", "knee_up_left": "legs",
    "leg_up_right": "legs", "leg_up_left": "legs",
    "arm_out": "arm_out", "arm_out_left": "arm_out", "arm_out_droop": "arm_out", "t_pose": "arm_out",
    "arms_open": "arm_out",
    "both_hands_up": "big_arms", "arms_crossed": "big_arms",
    "neutral": None, "arm_sway": None, "arms_sway": None, "step_forward": None, "hands_low_front": None, "lean": None,
    "squat_deep": None,
}


def pose(name: str, **kw) -> np.ndarray:
    return make_pose(**POSES[name], **kw)

"""The motion rules against synthetic stick figures drawn from the sketches (see skeleton.py).

Run from v2/:  python -m unittest discover -s tests
"""
import json
import pathlib
import sys
import unittest

import numpy as np
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import skeleton as S                                    # noqa: E402
from dansonic import motions as M                       # noqa: E402
from dansonic.mapper import resolve                     # noqa: E402

ASPECT = 0.56
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
for _path in sorted((ROOT / "poses").glob("*.json")):
    if _path.stem not in M.MOTIONS:
        M.register_pose(_path.stem, json.loads(_path.read_text()))
BY_MOTION, PROBLEMS = resolve(S.LIBRARY)                 # the motion library in families (labels, no sound files)
LIVE_BY_MOTION, LIVE_PROBLEMS = resolve(CFG["sounds"])   # what config.yaml really plays


def firing(lm) -> set:
    """Motions held in this pose."""
    f = M.Features(lm, ASPECT)
    return {name for name, rule in M.MOTIONS.items() if rule(f) > 0}


def sounds_of(lm) -> set:
    """The families whose motions are held in this pose."""
    return {BY_MOTION[m] for m in firing(lm) if m in BY_MOTION}


def live_sounds_of(lm) -> set:
    """The sounds config.yaml would play for this pose."""
    return {LIVE_BY_MOTION[m] for m in firing(lm) if m in LIVE_BY_MOTION}


class MovesPlayTheirSound(unittest.TestCase):
    """Every pose fires the motions of its own family and of no other."""

    def test_config_is_consistent(self):
        self.assertEqual(PROBLEMS, [])
        self.assertEqual(LIVE_PROBLEMS, [])

    def test_every_sketch_pose_fires_its_family_and_nothing_else(self):
        for name in S.POSES:
            expected = S.EXPECTED[name]
            with self.subTest(pose=name):
                self.assertEqual(sounds_of(S.pose(name)), {expected} if expected else set(), firing(S.pose(name)))

    def test_robust_to_jitter_body_size_and_distance(self):
        rng = np.random.default_rng(1)
        for name, expected in S.EXPECTED.items():
            hits, wrong, runs = 0, 0, 40
            for _ in range(runs):
                kw = dict(noise=0.012, rng=rng, scale=rng.uniform(0.14, 0.3), shoulder=rng.uniform(0.29, 0.38),
                          centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
                got = sounds_of(S.pose(name, **kw))
                hits += expected in got
                wrong += bool(got - {expected})
            with self.subTest(pose=name):
                if expected:
                    self.assertGreaterEqual(hits / runs, 0.8, f"{name} fired in only {hits} of {runs} noisy poses")
                self.assertLessEqual(wrong / runs, 0.1, f"{name} played another sound in {wrong} of {runs} noisy poses")

    def test_left_and_right_are_mirror_images(self):
        pairs = [("forearm_side", "forearm_side_left"), ("hand_cheek", "hand_cheek_left"),
                 ("arm_across", "arm_across_left"), ("arm_out", "arm_out_left"),
                 ("foot_up_right", "foot_up_left"), ("knee_up_right", "knee_up_left"),
                 ("leg_up_right", "leg_up_left")]
        for right, left in pairs:
            with self.subTest(pair=right):
                self.assertEqual(sounds_of(S.pose(right)), sounds_of(S.pose(left)))
                self.assertEqual({m.replace("right_", "left_") for m in firing(S.pose(right))}, firing(S.pose(left)))

    def test_a_turned_dancer_does_not_cross_or_spread_the_arms(self):
        # shoulders foreshortened to 0.4 of the torso: the sideways rules must stay off
        for name in ("arm_across", "arm_out", "t_pose", "hands_on_hips", "hands_chest", "arms_crossed", "arms_open"):
            with self.subTest(pose=name):
                self.assertEqual(sounds_of(S.pose(name, shoulder=0.2)), set())

    def test_every_family_has_several_motions(self):
        for sound, options in S.LIBRARY.items():
            with self.subTest(family=sound):
                self.assertGreaterEqual(len(options["motions"]), 3)


class TheGivenSound(unittest.TestCase):
    """config.yaml plays ab-ab only. The motions it lists have to be real ones the rules can see, and one arm must
    never play the double (README: only both arms up play ab-ab)."""

    def test_every_listed_motion_can_be_seen(self):
        seen = set().union(*(firing(S.pose(name)) for name in S.POSES))
        for sound, options in CFG["sounds"].items():
            for word in options["motions"]:
                for motion in M.expand(word):
                    with self.subTest(sound=sound, motion=motion):
                        self.assertTrue(motion in seen or motion in M.IMPULSE or motion in (M.CLAP, M.FLAIL, M.JUMP_ARMS))

    def test_one_arm_never_plays_the_double(self):
        for name in ("forearm_tucked", "forearm_side", "forearm_side_left", "hand_cheek", "arm_up_diag"):
            with self.subTest(pose=name):
                self.assertNotIn("ab-ab", live_sounds_of(S.pose(name)))

    def test_the_ab_ab_motions_do_not_fire_on_other_poses_even_when_noisy(self):
        rng = np.random.default_rng(2)
        runs = 60
        mine = {m for word in S.LIBRARY["ab-ab"]["motions"] for m in M.expand(word)}
        for name in S.POSES:
            if S.EXPECTED[name] == "ab-ab":
                continue
            wrong = 0
            for _ in range(runs):
                kw = dict(noise=0.012, rng=rng, scale=rng.uniform(0.14, 0.3), shoulder=rng.uniform(0.29, 0.38),
                          centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
                wrong += bool(firing(S.pose(name, **kw)) & mine)
            with self.subTest(pose=name):
                self.assertEqual(wrong, 0, f"{name} fired an ab-ab motion in {wrong} of {runs} noisy poses")


class Detector(unittest.TestCase):
    def feed(self, det, lm, frames, t0=0.0, fps=30.0):
        events = []
        for i in range(frames):
            events += det.update(M.Features(lm, ASPECT), t0 + i / fps)
        return events

    def test_a_pose_fires_once_then_ends_and_can_fire_again(self):
        det = M.MotionDetector()
        up, down = S.pose("both_hands_up"), S.pose("neutral")
        first = self.feed(det, up, 12)
        self.assertEqual([e for e in first if e[0] == "both_hands_up"], [("both_hands_up", "start")])
        second = self.feed(det, down, 12, t0=1.0)
        self.assertIn(("both_hands_up", "end"), second)
        third = self.feed(det, up, 12, t0=2.0)
        self.assertIn(("both_hands_up", "start"), third)

    def test_hold_frames_filter_a_single_noisy_frame(self):
        det = M.MotionDetector(hold_frames=2)
        events = self.feed(det, S.pose("both_hands_up"), 1) + self.feed(det, S.pose("neutral"), 6, t0=0.1)
        self.assertEqual([e for e in events if e[1] == "start"], [])

    def test_fast_hand_swipe_down_hits_once(self):
        det = M.MotionDetector()
        events = []
        for i in range(8):                       # right wrist from above the head down past the hip in 8 frames
            lm = S.make_pose(R=((0.4, 0.2), (0.45, -1.0 + i * 0.28)))
            events += det.update(M.Features(lm, ASPECT), i / 30)
        self.assertEqual([e for e in events if e == ("right_swipe_down", "hit")], [("right_swipe_down", "hit")])

    def test_clap_fires_when_the_hands_close_fast(self):
        det = M.MotionDetector()
        events = []
        for i, gap in enumerate([0.9, 0.9, 0.9, 0.62, 0.3, 0.12, 0.1, 0.1]):
            arm = ((0.3, 0.55), (gap / 2, 0.35))
            events += det.update(M.Features(S.make_pose(R=arm, L=arm), ASPECT), i / 30)
        self.assertIn(("clap", "hit"), events)

    def test_hands_drifting_together_slowly_is_no_clap(self):
        det = M.MotionDetector()
        events = []
        for i in range(30):
            gap = 0.9 - i * 0.027
            arm = ((0.3, 0.55), (gap / 2, 0.35))
            events += det.update(M.Features(S.make_pose(R=arm, L=arm), ASPECT), i / 30)
        self.assertNotIn(("clap", "hit"), events)


class Names(unittest.TestCase):
    def test_a_bare_name_means_either_side(self):
        self.assertEqual(sorted(M.expand("forearm_up")), ["left_forearm_up", "right_forearm_up"])
        self.assertEqual(M.expand("both_hands_up"), ["both_hands_up"])
        self.assertEqual(sorted(M.expand("swipe_down")), ["left_swipe_down", "right_swipe_down"])
        self.assertEqual(M.expand("no_such_motion"), [])

    def test_recorded_pose_matches_itself_and_mirrors_only_when_asked(self):
        lm = S.pose("arm_across")
        f = M.Features(lm, ASPECT)
        joints = M.ARM_JOINTS
        template = {"joints": joints, "vector": M.pose_vector(f, joints).tolist(), "threshold": 0.2}
        self.assertGreater(M.make_pose_rule(template)(f), 0.19)
        mirrored = M.Features(S.pose("arm_across_left"), ASPECT)
        self.assertGreater(M.make_pose_rule(template, mirror=True)(mirrored), 0.19)
        self.assertLess(M.make_pose_rule(template)(mirrored), 0.0)
        names = M.register_pose("test_pose_plain", template)
        self.assertEqual(names, ["test_pose_plain"])
        names = M.register_pose("right_test_pose", dict(template, mirror=True))
        self.assertEqual(names, ["right_test_pose", "left_test_pose"])
        for n in names + ["test_pose_plain"]:
            M.MOTIONS.pop(n)


class JumpArmsOut(unittest.TestCase):
    """The ab-ab move: a little jump and both arms out to the sides. Arms alone must never start it."""

    def run_frames(self, frames):
        det, fired = M.MotionDetector(), []
        for i, lm in enumerate(frames):
            fired += [n for n, k in det.update(M.Features(lm, 0.56), i / 30.0) if n == M.JUMP_ARMS]
        return fired

    def test_arms_out_without_a_jump_does_not_fire(self):
        rng = np.random.default_rng(1)
        frames = [S.make_pose(noise=0.01, rng=rng) for _ in range(30)]
        frames += [S.make_pose(**S.POSES["t_pose"], noise=0.01, rng=rng) for _ in range(60)]
        self.assertEqual(self.run_frames(frames), [])

    def test_a_jump_with_the_arms_out_fires_once(self):
        arms = S.POSES["t_pose"]
        frames = [S.make_pose(noise=0.01) for _ in range(30)]
        for dy in (0.0, 0.015, 0.03, 0.0, -0.03, -0.04, -0.02, 0.0):       # dip, then up, then back (frame height share)
            frames.append(S.make_pose(**arms, centre=(0.5, 0.35 + dy)))
        frames += [S.make_pose(**arms) for _ in range(20)]
        self.assertEqual(self.run_frames(frames), [M.JUMP_ARMS])

    # The tracker wobbles when an arm moves: the shoulders creep up and the inferred hips drift, which changes the
    # shoulder-to-hip distance every frame. None of that, without a real jump, may start the sound.
    HANG = ((0.40, 0.5), (0.42, 0.98))
    OUT = ((0.9, 0.3), (1.5, 0.3))

    def arm_sequence(self, seed, right, left, arm_t, hop_t=None, shrug=0.0, hip_wobble=0.0, hips_vis=1.0):
        rng = np.random.default_rng(seed)
        frames = []
        for i in range(210):
            t = i / 30.0
            k = float(np.clip((t - arm_t) / 0.3, 0.0, 1.0))
            arm = lambda a, b: tuple(tuple(np.array(x) * (1 - k) + np.array(y) * k for x, y in zip(p, q)) for p, q in zip(a, b))
            dy = 0.0
            if hop_t is not None and 0 <= t - hop_t < 0.45:
                dy = float(np.interp((t - hop_t) / 0.45, [0, 0.25, 0.6, 1.0], [0, 0.4, -1.0, 0])) * 0.2    # dip, up, down
            lm = S.make_pose(R=arm(self.HANG, right), L=arm(self.HANG, left), noise=0.015, rng=rng,
                             centre=(0.5, 0.35 + dy * 0.2))
            lm[[11, 12], 1] -= shrug * k * 0.2
            lm[[23, 24], 1] += hip_wobble * np.sin(2 * np.pi * 1.3 * t) * 0.2
            lm[[23, 24], 2] = hips_vis
            frames.append(lm)
        return frames

    def test_moving_one_arm_never_fires_however_the_tracker_wobbles(self):
        for seed in range(6):
            for shrug, wobble in ((0.0, 0.0), (0.3, 0.3)):
                with self.subTest(seed=seed, shrug=shrug, wobble=wobble):
                    frames = self.arm_sequence(seed, self.OUT, self.HANG, 2.0, shrug=shrug, hip_wobble=wobble)
                    self.assertEqual(self.run_frames(frames), [])

    def test_both_arms_out_without_a_jump_never_fires_however_the_tracker_wobbles(self):
        for seed in range(6):
            for hips_vis in (1.0, 0.2):
                with self.subTest(seed=seed, hips_vis=hips_vis):
                    frames = self.arm_sequence(seed, self.OUT, self.OUT, 2.0, shrug=0.3, hip_wobble=0.4, hips_vis=hips_vis)
                    self.assertEqual(self.run_frames(frames), [])

    def test_a_jump_and_then_both_arms_out_fires_even_with_the_wobble(self):
        for seed in range(6):
            for hips_vis in (1.0, 0.2):
                with self.subTest(seed=seed, hips_vis=hips_vis):
                    frames = self.arm_sequence(seed, self.OUT, self.OUT, 2.5, hop_t=2.0, shrug=0.3, hip_wobble=0.15,
                                               hips_vis=hips_vis)
                    self.assertEqual(self.run_frames(frames), [M.JUMP_ARMS])

    def test_a_hop_with_only_one_arm_out_does_not_fire(self):
        frames = self.arm_sequence(0, self.OUT, self.HANG, 1.0, hop_t=2.0)
        self.assertEqual(self.run_frames(frames), [])

    def test_a_jump_with_the_arms_down_does_not_fire(self):
        frames = [S.make_pose() for _ in range(30)]
        for dy in (0.0, 0.015, 0.03, 0.0, -0.03, -0.04, -0.02, 0.0):
            frames.append(S.make_pose(centre=(0.5, 0.35 + dy)))
        self.assertEqual(self.run_frames(frames), [])


if __name__ == "__main__":
    unittest.main()

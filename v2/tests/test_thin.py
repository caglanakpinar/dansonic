"""thin: the forearm across the chest, either arm. The real thing is the dancers' move at 1:29-1:31 of the
WhatsApp video; tests/fixtures/dancers_1m29.npz holds the tracker's landmarks of both dancers for 88-92 s.

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
from dansonic.mapper import SoundMapper, resolve       # noqa: E402

CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
for _path in sorted((ROOT / "poses").glob("*.json")):
    if _path.stem not in M.MOTIONS:
        M.register_pose(_path.stem, json.loads(_path.read_text()))
LIVE_BY_MOTION, _ = resolve(CFG["sounds"])
VIDEO = np.load(ROOT / "tests" / "fixtures" / "dancers_1m29.npz")
LEAN_VIDEO = np.load(ROOT / "tests" / "fixtures" / "dancers_lean.npz")      # 12.4-14.8 s: the blue dancer leans, an arm over
CROSSED = dict(R=S.ARM_CROSS_X, L=S.ARM_CROSS_X)        # both forearms across the chest, an X


class FakeEngine:
    def __init__(self):
        self.played = []

    def trigger(self, name, quantize, gain, restart_loop=False):
        self.played.append(name)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def live_sounds_of(lm) -> set:
    f = M.Features(lm, 0.56)
    return {LIVE_BY_MOTION[m] for m, rule in M.MOTIONS.items() if m in LIVE_BY_MOTION and rule(f) > 0}


def replay(dancer: str) -> list:
    """(video second, sound) for everything the app would play for one dancer of the video."""
    clock, engine = Clock(), FakeEngine()
    mapper = SoundMapper(engine, CFG["sounds"], 4, CFG.get("cooldown", 0.2), clock=clock)
    det, played = M.MotionDetector(), []
    for t, lm in zip(VIDEO["t"], VIDEO[dancer]):
        if np.isnan(lm[0, 0]):
            continue
        clock.t = float(t)
        for name, kind in det.update(M.Features(lm, float(VIDEO["aspect"])), float(t)):
            played += [(round(float(t), 2), s) for s in mapper.handle(0, name, kind)]
    return played


class Thin(unittest.TestCase):
    def test_the_forearm_across_the_chest_plays_thin_with_either_arm(self):
        for name in ("arm_across", "arm_across_left"):
            with self.subTest(pose=name):
                self.assertEqual(live_sounds_of(S.pose(name)), {"thin"})

    def test_no_other_move_plays_thin(self):
        for name, family in S.EXPECTED.items():
            if family == "hips_across" or name == "arms_crossed":      # the across-the-chest sketch; crossed arms play thin
                continue
            with self.subTest(pose=name):
                self.assertNotIn("thin", live_sounds_of(S.pose(name)))

    def test_it_survives_jitter_body_size_and_distance(self):
        rng = np.random.default_rng(3)
        hits = 0
        for _ in range(40):
            lm = S.pose("arm_across", noise=0.012, rng=rng, scale=rng.uniform(0.14, 0.3),
                        shoulder=rng.uniform(0.29, 0.38), centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
            hits += "thin" in live_sounds_of(lm)
        self.assertGreaterEqual(hits / 40, 0.8)

    def test_both_dancers_of_the_video_play_thin_on_their_first_sweep_and_not_before(self):
        for dancer in ("white", "blue"):
            with self.subTest(dancer=dancer):
                thin = [t for t, sound in replay(dancer) if sound == "thin"]
                self.assertTrue(thin, "no thin at all")
                self.assertGreaterEqual(thin[0], 89.4, "thin before the move")
                self.assertLessEqual(thin[0], 90.2, "thin too late for the move")

    # The move has to be easy to catch, so these were not enough for the first, stricter rule:
    def test_the_other_hand_and_the_hips_out_of_the_picture_do_not_stop_it(self):
        lm = S.pose("arm_across")
        lm[15, 2] = 0.1                 # the hanging wrist is below the frame (a close camera)
        lm[[23, 24], 2] = 0.1
        self.assertEqual(live_sounds_of(lm), {"thin"})

    def test_a_hand_resting_high_on_the_other_shoulder_plays_thin(self):
        self.assertEqual(live_sounds_of(S.make_pose(R=((0.15, 0.30), (-0.25, -0.20)))), {"thin"})

    def test_a_hand_that_only_reaches_the_middle_of_the_chest_plays_thin(self):
        self.assertEqual(live_sounds_of(S.make_pose(R=((0.20, 0.45), (-0.02, 0.20)))), {"thin"})

    def test_a_quick_sweep_of_two_frames_is_enough_and_the_next_sweep_counts_again(self):
        det, starts = M.MotionDetector(), []
        across, out = S.pose("arm_across"), S.pose("arm_out")
        t = 0.0
        for lm, frames in ((S.pose("neutral"), 6), (across, 2), (out, 6), (across, 2), (S.pose("neutral"), 6)):
            for _ in range(frames):
                starts += [(round(t, 2), n) for n, kind in det.update(M.Features(lm, 0.56), t)
                           if kind == "start" and n.endswith("arm_across")]
                t += 1 / 30.0
        self.assertEqual([n for _, n in starts], ["right_arm_across", "right_arm_across"])

    # Leaning to the left or the right with an arm (or both) across the chest also plays thin:
    def test_leaning_either_way_with_the_arms_crossed_plays_thin(self):
        for tilt in (0.3, -0.3):
            with self.subTest(tilt=tilt):
                self.assertEqual(live_sounds_of(S.make_pose(**CROSSED, tilt=tilt)), {"thin"})

    def test_a_lean_alone_plays_nothing(self):
        self.assertEqual(live_sounds_of(S.make_pose(tilt=0.3)), set())
        self.assertEqual(live_sounds_of(S.make_pose(tilt=-0.3)), set())

    def test_a_small_lean_is_not_enough_and_a_dancer_on_the_floor_is_not_leaning(self):
        # the lean rule itself: crossed arms play thin without any lean (chest_cross), so ask the rule, not the sound
        lean = M.MOTIONS["lean_across"]
        self.assertLess(lean(M.Features(S.make_pose(**CROSSED, tilt=0.08), 0.56)), 0)       # 4.6 degrees
        self.assertLess(lean(M.Features(S.make_pose(**CROSSED, tilt=1.3), 0.56)), 0)        # 74 degrees
        self.assertGreater(lean(M.Features(S.make_pose(**CROSSED, tilt=0.3), 0.56)), 0)

    def test_the_lean_needs_the_hips_to_be_seen(self):
        lm = S.make_pose(**CROSSED, tilt=0.3)
        lm[[23, 24], 2] = 0.1
        self.assertLess(M.MOTIONS["lean_across"](M.Features(lm, 0.56)), 0)

    def test_a_lean_with_one_arm_across_survives_jitter_body_size_and_distance(self):
        rng = np.random.default_rng(4)
        hits = 0
        for i in range(40):
            lm = S.make_pose(R=S.ARM_CROSS_X, L=S.ARM_DOWN, tilt=(0.3 if i % 2 else -0.3), noise=0.012, rng=rng,
                             scale=rng.uniform(0.14, 0.3), shoulder=rng.uniform(0.29, 0.38),
                             centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
            hits += "thin" in live_sounds_of(lm)
        self.assertGreaterEqual(hits / 40, 0.8)

    def test_leaning_to_the_other_side_starts_thin_again(self):
        det, starts, t = M.MotionDetector(), [], 0.0
        for tilt, frames in ((0.0, 6), (0.3, 8), (0.0, 8), (-0.3, 8), (0.0, 6)):
            lm = S.make_pose(**CROSSED, tilt=tilt)
            for _ in range(frames):
                starts += [kind for name, kind in det.update(M.Features(lm, 0.56), t) if name == "lean_across"]
                t += 1 / 30.0
        self.assertEqual(starts.count("start"), 2)

    def test_the_blue_dancer_of_the_video_leans_into_an_arm_over_at_13_5_s(self):
        clock, engine = Clock(), FakeEngine()
        mapper = SoundMapper(engine, CFG["sounds"], 4, CFG.get("cooldown", 0.2), clock=clock)
        det, motions = M.MotionDetector(), []
        for t, lm in zip(LEAN_VIDEO["t"], LEAN_VIDEO["blue"]):
            if np.isnan(lm[0, 0]):
                continue
            clock.t = float(t)
            for name, kind in det.update(M.Features(lm, float(LEAN_VIDEO["aspect"])), float(t)):
                motions += [(round(float(t), 2), name, s) for s in mapper.handle(0, name, kind)]
        self.assertTrue([m for m in motions if m[1] == "lean_across" and 13.2 <= m[0] <= 14.0], motions)

    # The sound came after the move was over: thin plays at once and starts on the first clear frame of the sweep.
    def test_thin_plays_at_once_while_the_other_sounds_keep_the_grid(self):
        class Recording:
            def __init__(self):
                self.calls = {}

            def trigger(self, name, quantize, gain, restart_loop=False):
                self.calls[name] = quantize

        grid = CFG["audio"].get("quantize", 4)
        engine = Recording()
        mapper = SoundMapper(engine, CFG["sounds"], grid, CFG.get("cooldown", 0.2), clock=Clock())
        for motion in ("right_arm_across", "lean_across", "right_hand_up", "left_leg_up"):
            mapper.last_fired.clear()
            mapper.handle(0, motion, "start")
        self.assertEqual(engine.calls["thin"], 0)
        self.assertEqual(engine.calls["ab"], grid, "ab moved off its grid")
        self.assertEqual(engine.calls["wha-been"], grid, "wha-been moved off its grid")

    def sweep(self, lm, frames, vis=None):
        """Events of a detector that has seen a neutral dancer, then `frames` frames of lm."""
        det, events, t = M.MotionDetector(), [], 0.0
        for _ in range(6):
            det.update(M.Features(S.pose("neutral"), 0.56), t)
            t += 1 / 30.0
        for _ in range(frames):
            lm = lm.copy()
            if vis is not None:
                lm[[14, 16], 2] = vis                       # the right elbow and wrist
            events += [(round(t, 3), e) for e in det.update(M.Features(lm, 0.56), t)]
            t += 1 / 30.0
        return events

    def test_a_clearly_seen_sweep_starts_on_its_first_frame(self):
        events = self.sweep(S.pose("arm_across"), 1)
        self.assertIn(("right_arm_across", "start"), [e for _, e in events])

    def test_an_unclear_sweep_still_waits_for_a_second_frame(self):
        one = self.sweep(S.pose("arm_across"), 1, vis=0.6)
        self.assertNotIn(("right_arm_across", "start"), [e for _, e in one], "a one-frame glitch played thin")
        two = self.sweep(S.pose("arm_across"), 2, vis=0.6)
        self.assertIn(("right_arm_across", "start"), [e for _, e in two])

    def test_only_the_across_the_chest_moves_of_thin_have_a_first_frame_start(self):
        self.assertTrue(M.SURE)
        self.assertEqual({M.FAMILY[name] for name in M.SURE}, {"arm_across", "chest_cross"})
        for name in M.SURE:
            self.assertEqual(LIVE_BY_MOTION[name], "thin", f"{name} is not a move of thin")

    def test_the_dancers_first_sweep_starts_as_the_hand_crosses_not_a_frame_later(self):
        # the stricter limits: with two frames of hold the video's starts were 89.81 (white) and 89.65 (blue)
        first = {dancer: min(t for t, sound in replay(dancer) if sound == "thin") for dancer in ("white", "blue")}
        self.assertLess(first["white"], 89.80)
        self.assertLess(first["blue"], 89.64)

    # An arm across the chest plays thin on sight: no sweep, no lean, the other arm may be anywhere.
    def test_crossed_arms_play_thin_without_a_lean_or_a_sweep(self):
        self.assertEqual(live_sounds_of(S.make_pose(**CROSSED)), {"thin"})
        self.assertEqual(live_sounds_of(S.pose("arms_crossed")), {"thin"})

    def test_an_arm_across_plays_thin_whatever_the_other_arm_does(self):
        for other in (S.ARM_DOWN, S.ARM_UP_STRAIGHT, S.ARM_OUT, S.HANDS_CHEST):
            with self.subTest(other_arm=other):
                # (a hand raised above the nose plays ab too: that is hand_up, unchanged)
                self.assertIn("thin", live_sounds_of(S.make_pose(R=S.ARM_ACROSS, L=other)))
                self.assertIn("thin", live_sounds_of(S.make_pose(L=S.ARM_ACROSS, R=other)))

    def test_a_held_cross_plays_once_the_moment_it_is_seen_and_not_again_until_it_is_left(self):
        det, starts, t = M.MotionDetector(), [], 0.0
        for lm, frames in ((S.make_pose(**CROSSED), 30), (S.pose("neutral"), 8), (S.make_pose(**CROSSED), 10)):
            for _ in range(frames):
                starts += [(round(t, 2), name) for name, kind in det.update(M.Features(lm, 0.56), t)
                           if kind == "start" and name == "chest_cross"]
                t += 1 / 30.0
        self.assertEqual([name for _, name in starts], ["chest_cross", "chest_cross"])
        self.assertEqual(starts[0][0], 0.0, "the held cross waited for something")

    def test_hands_together_on_the_chest_and_a_turned_dancer_do_not_play_thin(self):
        prayer = ((0.30, 0.60), (0.02, 0.40))
        self.assertEqual(live_sounds_of(S.make_pose(R=prayer, L=prayer)), set())
        self.assertEqual(live_sounds_of(S.make_pose(**CROSSED, shoulder=0.2)), set())     # turned: arms only look crossed

    def test_a_cross_survives_jitter_body_size_and_distance(self):
        rng = np.random.default_rng(5)
        hits = 0
        for _ in range(40):
            lm = S.make_pose(**CROSSED, noise=0.012, rng=rng, scale=rng.uniform(0.14, 0.3),
                             shoulder=rng.uniform(0.29, 0.38), centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
            hits += "thin" in live_sounds_of(lm)
        self.assertGreaterEqual(hits / 40, 0.8)

    def test_a_clearly_seen_cross_starts_on_its_first_frame(self):
        det = M.MotionDetector()
        events = det.update(M.Features(S.make_pose(**CROSSED), 0.56), 0.0)
        self.assertIn(("chest_cross", "start"), events)

    def test_thin_is_silent_while_ab_ab_plays(self):
        clock, engine = Clock(), FakeEngine()
        mapper = SoundMapper(engine, CFG["sounds"], 4, CFG.get("cooldown", 0.2), clock=clock)
        self.assertEqual(mapper.handle(0, M.JUMP_ARMS, "hit"), ["ab-ab"])
        clock.t = 3.0
        self.assertEqual(mapper.handle(0, "right_arm_across", "start"), [])
        clock.t = CFG["sounds"]["ab-ab"]["protect"] + 0.5
        self.assertEqual(mapper.handle(0, "right_arm_across", "start"), ["thin"])


if __name__ == "__main__":
    unittest.main()

"""wha-been: one leg lifted at least 75 degrees from hanging, left or right (the knee near hip height).
Real examples: the dancers of the WhatsApp video lift a leg that high at about 1:17, 1:47-1:48, 1:52-1:53 and 1:57-1:58;
tests/fixtures/dancers_legs.npz holds the tracker's landmarks for 75.8-79.0 s and 112.2-114.0 s.

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
VIDEO = np.load(ROOT / "tests" / "fixtures" / "dancers_legs.npz")
THIGH = 0.76        # the synthetic dancer's thigh: hip at 1.0, standing knee at 1.76


class FakeEngine:
    def __init__(self):
        self.played = []

    def trigger(self, name, quantize, gain, restart_loop=False):
        self.played.append(name)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def knee_at(degrees: float) -> tuple:
    """A lifted right leg whose thigh is `degrees` up from hanging (the knee's height under the hip is THIGH * cos)."""
    y = 1.0 + THIGH * np.cos(np.radians(degrees))
    return (0.45, float(y)), (0.40, float(y) + 0.75)


def live_sounds_of(lm) -> set:
    f = M.Features(lm, 0.56)
    return {LIVE_BY_MOTION[m] for m, rule in M.MOTIONS.items() if m in LIVE_BY_MOTION and rule(f) > 0}


def replay(window: str, dancer: str) -> list:
    clock, engine = Clock(), FakeEngine()
    mapper = SoundMapper(engine, CFG["sounds"], 4, CFG.get("cooldown", 0.2), clock=clock)
    det, played = M.MotionDetector(), []
    for t, lm in zip(VIDEO[f"{window}_t"], VIDEO[f"{window}_{dancer}"]):
        if np.isnan(lm[0, 0]):
            continue
        clock.t = float(t)
        for name, kind in det.update(M.Features(lm, float(VIDEO["aspect"])), float(t)):
            played += [(round(float(t), 2), s) for s in mapper.handle(0, name, kind)]
    return played


class LegUp(unittest.TestCase):
    def test_either_leg_lifted_to_the_hip_plays_wha_been(self):
        for name in ("leg_up_right", "leg_up_left"):
            with self.subTest(pose=name):
                self.assertEqual(live_sounds_of(S.pose(name)), {"wha-been"})

    def test_the_limit_is_75_degrees(self):
        for degrees, plays in ((60, False), (70, False), (73, False), (78, True), (85, True), (100, True)):
            with self.subTest(degrees=degrees):
                lm = S.make_pose(right_leg=knee_at(degrees))
                self.assertEqual("wha-been" in live_sounds_of(lm), plays)

    def test_the_other_leg_can_be_the_one(self):
        (knee, ankle) = knee_at(85)
        self.assertEqual(live_sounds_of(S.make_pose(left_leg=(knee, ankle))), {"wha-been"})

    def test_nothing_else_plays_wha_been(self):
        for name, family in S.EXPECTED.items():
            if family == "legs":
                continue
            with self.subTest(pose=name):
                self.assertNotIn("wha-been", live_sounds_of(S.pose(name)))

    def test_a_deep_squat_or_both_knees_up_is_not_a_lifted_leg(self):
        self.assertNotIn("wha-been", live_sounds_of(S.pose("squat_deep")))
        both = S.make_pose(right_leg=knee_at(85), left_leg=knee_at(85))
        self.assertNotIn("wha-been", live_sounds_of(both))

    def test_a_standing_dancer_never_plays_it_whatever_the_jitter(self):
        rng = np.random.default_rng(5)
        wrong = sum("wha-been" in live_sounds_of(S.pose("neutral", noise=0.02, rng=rng)) for _ in range(200))
        self.assertEqual(wrong, 0)

    def test_it_survives_jitter_body_size_and_distance(self):
        rng = np.random.default_rng(6)
        hits = 0
        for _ in range(40):
            lm = S.make_pose(right_leg=knee_at(85), noise=0.012, rng=rng, scale=rng.uniform(0.14, 0.3),
                             shoulder=rng.uniform(0.29, 0.38), centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
            hits += "wha-been" in live_sounds_of(lm)
        self.assertGreaterEqual(hits / 40, 0.8)

    def test_a_leg_out_of_the_picture_plays_nothing(self):
        lm = S.pose("leg_up_right")
        lm[[23, 24, 25, 26, 27, 28], 2] = 0.1           # close camera: hips and legs below the frame
        self.assertEqual(live_sounds_of(lm), set())

    def test_the_dancers_of_the_video_play_it_when_they_lift_a_leg(self):
        for window in ("a", "b"):
            for dancer in ("white", "blue"):
                with self.subTest(window=window, dancer=dancer):
                    played = [t for t, sound in replay(window, dancer) if sound == "wha-been"]
                    self.assertTrue(played, "no wha-been")

    def test_the_dancers_standing_before_the_lift_play_nothing(self):
        # the first 0.4 s of window a: both dancers stand
        for dancer in ("white", "blue"):
            with self.subTest(dancer=dancer):
                start = float(VIDEO["a_t"][0])
                self.assertEqual([t for t, s in replay("a", dancer) if s == "wha-been" and t < start + 0.4], [])


if __name__ == "__main__":
    unittest.main()

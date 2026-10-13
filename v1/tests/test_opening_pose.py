"""How precise is the opening move? hands_on_chest against poses a dancer might hold before the dance starts.

Run from v1/:  python -m unittest discover -s tests
"""
import pathlib
import sys
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import skeleton as S                                    # noqa: E402
from dansonic import gestures as G                      # noqa: E402

ASPECT = 0.56
MARGIN = 0.03           # opening.margin in config.yaml
LOOSE = ("hands_near_chest", "both_forearms_up")         # opening.loose in config.yaml


def margin(lm) -> float:
    return G.STATIC["hands_on_chest"](G.Features(lm, ASPECT))


def loose_margin(lm) -> float:
    f = G.Features(lm, ASPECT)
    return max(G.STATIC[name](f) for name in LOOSE)


def jittered(name, rng, **extra):
    kw = dict(noise=0.012, rng=rng, scale=rng.uniform(0.14, 0.3), shoulder=rng.uniform(0.29, 0.38),
              centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
    return S.pose(name, **kw, **extra)


class HandsOnChest(unittest.TestCase):
    def test_the_opening_is_reached_clearly(self):
        for name in S.OPENING_POSES:
            with self.subTest(pose=name):
                self.assertGreater(margin(S.pose(name)), 0.1)

    def test_nothing_else_comes_close(self):
        for name in S.NOT_THE_OPENING:
            with self.subTest(pose=name):
                self.assertLess(margin(S.pose(name)), 0.0)

    def test_precise_under_jitter_body_size_and_distance(self):
        rng = np.random.default_rng(3)
        for name in list(S.OPENING_POSES) + list(S.NOT_THE_OPENING):
            opening = name in S.OPENING_POSES
            clear = 0
            runs = 60
            for _ in range(runs):
                kw = dict(noise=0.012, rng=rng, scale=rng.uniform(0.14, 0.3), shoulder=rng.uniform(0.29, 0.38),
                          centre=(rng.uniform(0.35, 0.65), rng.uniform(0.2, 0.4)))
                clear += margin(S.pose(name, **kw)) >= MARGIN
            with self.subTest(pose=name):
                if opening:
                    self.assertGreaterEqual(clear / runs, 0.9, f"{name}: reached clearly in only {clear} of {runs}")
                else:
                    self.assertEqual(clear, 0, f"{name} passed as the opening in {clear} of {runs} noisy poses")

    def test_a_turned_dancer_is_not_the_opening(self):
        self.assertLess(margin(S.pose("hands_chest", shoulder=0.2)), 0.0)

    def test_a_left_or_a_right_hand_alone_is_not_enough(self):
        self.assertLess(margin(S.pose("one_hand_on_chest")), 0.0)

    def test_it_is_a_registered_two_armed_gesture(self):
        from dansonic.actions import TWO_ARMED
        self.assertIn("hands_on_chest", G.STATIC)
        self.assertIn("hands_on_chest", TWO_ARMED)


class LooseOpening(unittest.TestCase):
    """The loose rules take the ways of doing ab ab the strict rule refuses (the opening holds them for a moment)."""

    def test_the_strict_opening_poses_are_loose_ones_too(self):
        for name in S.OPENING_POSES:
            with self.subTest(pose=name):
                self.assertGreater(loose_margin(S.pose(name)), 0.0)

    def test_freer_versions_of_ab_ab_reach_a_loose_rule_but_not_the_strict_one(self):
        for name in S.LOOSE_OPENING_POSES:
            with self.subTest(pose=name):
                self.assertGreater(loose_margin(S.pose(name)), 0.0)
        for name in ("hands_low", "hands_overlap", "hands_crossed_a_little"):
            with self.subTest(pose=name):
                self.assertLess(margin(S.pose(name)), MARGIN)

    def test_idle_and_other_poses_are_not_even_loosely_the_opening(self):
        for name in S.NOT_EVEN_LOOSE:
            with self.subTest(pose=name):
                self.assertLess(loose_margin(S.pose(name)), 0.0)

    def test_precise_under_jitter_body_size_and_distance(self):
        rng = np.random.default_rng(5)
        runs = 80
        for name in list(S.LOOSE_OPENING_POSES) + list(S.NOT_EVEN_LOOSE):
            wanted = name in S.LOOSE_OPENING_POSES
            held = sum(loose_margin(jittered(name, rng)) >= 0 for _ in range(runs))
            with self.subTest(pose=name):
                if wanted:
                    self.assertGreaterEqual(held / runs, 0.85, f"{name}: held in only {held} of {runs} noisy frames")
                else:
                    self.assertEqual(held, 0, f"{name} passed as a loose opening in {held} of {runs} noisy frames")

    def test_a_turned_dancer_still_counts_but_a_sideways_one_does_not(self):
        self.assertGreater(loose_margin(S.pose("hands_chest", shoulder=0.2)), 0.0)         # shoulders 0.4 wide
        self.assertLess(loose_margin(S.pose("hands_chest", shoulder=0.1)), 0.0)            # shoulders 0.2 wide

    def test_hands_half_hidden_over_the_chest_still_count(self):
        lm = S.pose("hands_chest")
        lm[[15, 16], 2] = 0.4                                   # the tracker is unsure of the wrists
        self.assertGreater(loose_margin(lm), 0.0)
        self.assertLess(margin(lm), 0.0)                        # the strict rule wants clearly visible wrists
        lm[[15, 16], 2] = 0.1                                   # but not lost altogether
        self.assertLess(loose_margin(lm), 0.0)

    def test_hands_joined_at_the_chest_open_it_when_held(self):
        # by design: the opening cannot tell hands joined in the middle of the chest from ab ab done with joined hands
        for name in ("hands_clasped_below", "hands_solar_plexus"):
            with self.subTest(pose=name):
                self.assertGreater(loose_margin(S.pose(name)), 0.0)

    def test_the_loose_rules_are_registered_two_armed_gestures(self):
        from dansonic.actions import TWO_ARMED
        for name in LOOSE:
            self.assertIn(name, G.STATIC)
            self.assertIn(name, TWO_ARMED)


if __name__ == "__main__":
    unittest.main()

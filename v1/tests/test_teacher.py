"""The K key: the app learns the dancer's own ab ab, saves it and opens the dance with it.

Run from v1/:  python -m unittest discover -s tests
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import skeleton as S                                    # noqa: E402
import run as app                                       # noqa: E402
from dansonic import gestures as G                      # noqa: E402

ASPECT = 0.56
OPENING_MARGIN = 0.03           # opening.margin in config.yaml


def features(name, rng=None, noise=0.0, **kw):
    return G.Features(S.pose(name, noise=noise, rng=rng or np.random.default_rng(0), **kw), ASPECT)


class Teaching(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        mock.patch.object(app, "POSES_DIR", pathlib.Path(self.dir.name)).start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(self.dir.cleanup)
        self.registered = []
        self.addCleanup(lambda: [G.STATIC.pop(n, None) for n in self.registered])

    def lesson(self, pose="hands_chest", fps=20, seed=0, lost=()):
        """One run of the K key with the dancer holding `pose`. Returns the teacher and what it learned."""
        teacher, rng = app.OpeningTeacher(), np.random.default_rng(seed)
        teacher.start(0.0)
        t, learned = 0.0, None
        while teacher.active and t < teacher.COUNTDOWN + teacher.SECONDS + 0.5:        # the app only feeds it while it is on
            f = None if lost and lost[0] <= t < lost[1] else features(pose, rng=rng, noise=0.01)
            learned = teacher.update(f, t)
            t += 1.0 / fps
        if learned:
            self.registered.append(learned[0])
        return teacher, learned

    def test_the_pose_is_learned_saved_and_listed(self):
        teacher, learned = self.lesson()
        name, template = learned
        self.assertEqual(name, "ab_ab_1")
        saved = json.loads((pathlib.Path(self.dir.name) / "ab_ab_1.json").read_text())
        self.assertEqual(saved["joints"], G.ARM_JOINTS)
        self.assertEqual(np.array(saved["vector"]).shape, (len(G.ARM_JOINTS), 2))
        self.assertEqual(app.taught_openings(), ["ab_ab_1"])
        self.assertFalse(teacher.active)
        self.assertIn("ab_ab_1", teacher.message)

    def test_the_next_lesson_gets_the_next_number(self):
        self.lesson()
        _, learned = self.lesson(pose="hands_chest_high", seed=1)
        self.assertEqual(learned[0], "ab_ab_2")
        self.assertEqual(app.taught_openings(), ["ab_ab_1", "ab_ab_2"])

    def test_the_countdown_comes_first_and_the_banner_says_what_to_do(self):
        teacher = app.OpeningTeacher()
        teacher.start(10.0)
        self.assertIn("3", teacher.banner(10.0))
        self.assertIsNone(teacher.update(features("hands_chest"), 11.0))        # nothing is recorded yet
        self.assertTrue(teacher.active)
        self.assertIn("TUT", teacher.banner(10.0 + teacher.COUNTDOWN + 0.1))

    def test_a_dancer_the_camera_lost_teaches_nothing(self):
        teacher, learned = self.lesson(lost=(0.0, 99.0))
        self.assertIsNone(learned)
        self.assertIn("algilanamadi", teacher.message)
        self.assertEqual(app.taught_openings(), [])
        self.assertFalse(teacher.active)

    def test_a_few_lost_frames_do_not_matter(self):
        _, learned = self.lesson(lost=(3.3, 3.6))
        self.assertIsNotNone(learned)

    def test_the_taught_pose_is_recognised_again_and_idle_poses_are_not(self):
        _, learned = self.lesson(pose="hands_chest")
        G.register_pose(*learned)
        rule = G.STATIC[learned[0]]
        rng = np.random.default_rng(9)
        again = [rule(features("hands_chest", rng=rng, noise=0.012, scale=rng.uniform(0.14, 0.3),
                               shoulder=rng.uniform(0.29, 0.38))) for _ in range(60)]
        self.assertGreaterEqual(np.mean([m >= OPENING_MARGIN for m in again]), 0.9)
        for name in S.NOT_EVEN_LOOSE:
            if name == "one_hand_on_chest":          # one arm of the same pose: the other hangs, a long way off
                continue
            with self.subTest(pose=name):
                self.assertLess(rule(features(name)), OPENING_MARGIN)

    def test_a_pose_the_strict_rule_refuses_is_learned_all_the_same(self):
        _, learned = self.lesson(pose="hands_low")                      # ab ab with the hands low: not hands_on_chest
        G.register_pose(*learned)
        self.assertLess(G.STATIC["hands_on_chest"](features("hands_low")), 0.0)
        self.assertGreater(G.STATIC[learned[0]](features("hands_low")), OPENING_MARGIN)

    def test_the_taught_pose_opens_the_dance_at_once(self):
        from dansonic.actions import ActionMapper
        _, learned = self.lesson(pose="hands_low")
        G.register_pose(*learned)
        engine = mock.Mock()
        engine.grid.downbeat_index = 0
        engine.beat_target.return_value = (5, 1, 5)
        engine.seconds_to_beat.return_value = 0.0
        engine.beat_landing.return_value = 5
        engine.loop_beats = 64
        mapper = ActionMapper(engine, [{"sound": "ab", "beat": 1}, {"sound": "ab-ab", "beat": 1, "both_arms": True, "span": 2}],
                              4, clock=lambda: 1.0, beats={"lookahead": 0.4, "hits": []},
                              opening={"sound": "ab-ab", "motions": ["hands_chest"], "loose": ["hands_near_chest"]})
        mapper.add_opening_motion(learned[0])
        self.assertIn(learned[0], mapper.waiting())
        f = features("hands_low")
        det = G.GestureDetector()
        det.update(f, 0.0)
        det.update(f, 0.05)
        self.assertGreater(det.margins[learned[0]], OPENING_MARGIN)
        mapper.tick(0, det.active, det.margins)
        self.assertTrue(mapper.opened)

    def test_the_run_script_finds_the_taught_poses_by_their_names(self):
        for name in ("ab_ab_1", "ab_ab_7", "hands_chest"):
            (pathlib.Path(self.dir.name) / f"{name}.json").write_text("{}")
        self.assertEqual(app.taught_openings(), ["ab_ab_1", "ab_ab_7"])


if __name__ == "__main__":
    unittest.main()

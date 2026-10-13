"""Motions -> sounds: cooldown, protect, dancer filter and the config checks.

The mapper rules run on the motion library (skeleton.LIBRARY, labels only); the live config.yaml is checked on its own.

Run from v2/:  python -m unittest discover -s tests
"""
import json
import pathlib
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import skeleton as S                                    # noqa: E402
from dansonic import motions as M                       # noqa: E402
from dansonic.mapper import SoundMapper, resolve        # noqa: E402

LIVE = yaml.safe_load((ROOT / "config.yaml").read_text())
LIB = S.LIBRARY
for _path in sorted((ROOT / "poses").glob("*.json")):
    if _path.stem not in M.MOTIONS:
        M.register_pose(_path.stem, json.loads(_path.read_text()))


class FakeEngine:
    def __init__(self):
        self.played = []

    def trigger(self, name, quantize, gain, restart_loop=False):
        self.played.append((name, quantize, gain))


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(sounds=None, cooldown=0.2):
    clock, engine = Clock(), FakeEngine()
    return SoundMapper(engine, sounds or LIB, 4, cooldown, clock=clock), engine, clock


class Mapper(unittest.TestCase):
    def test_while_the_long_sound_plays_no_other_sound_starts_but_its_own_move_always_does(self):
        sounds = {"long": {"motions": ["both_hands_up"], "protect": 5.0, "cooldown": 6.0},
                  "short": {"motions": ["left_hand_up", "right_hand_up"]}}
        mapper, engine, clock = make(sounds)
        mapper.handle(0, "left_hand_up", "start")                   # a short sound is playing ...
        clock.t = 0.1
        self.assertEqual(mapper.handle(0, "both_hands_up", "start"), ["long"])   # ... the long one still starts
        clock.t = 1.0
        self.assertEqual(mapper.handle(0, "right_hand_up", "start"), [])         # nothing else while it plays
        clock.t = 5.2
        self.assertEqual(mapper.handle(0, "right_hand_up", "start"), ["short"])  # and again once it is over
        self.assertEqual([p[0] for p in engine.played], ["short", "long", "short"])

    def test_every_motion_of_a_sound_plays_it(self):
        for sound, options in LIB.items():
            for word in options["motions"]:
                for motion in M.expand(word):
                    with self.subTest(sound=sound, motion=motion):
                        mapper, engine, clock = make()
                        kind = "hit" if motion in M.IMPULSE or motion in (M.CLAP, M.FLAIL) else "start"
                        self.assertEqual(mapper.handle(0, motion, kind), [sound])
                        self.assertEqual(engine.played[0][0], sound)

    def test_ends_and_unknown_motions_play_nothing(self):
        mapper, engine, _ = make()
        self.assertEqual(mapper.handle(0, "left_forearm_up", "end"), [])
        self.assertEqual(mapper.handle(0, "no_such_motion", "start"), [])
        self.assertEqual(engine.played, [])

    def test_two_motions_of_one_sound_at_once_play_it_once(self):
        mapper, engine, clock = make()
        mapper.handle(0, "right_forearm_up", "start")
        clock.t = 0.05
        mapper.handle(0, "right_hand_to_head", "start")
        self.assertEqual(len(engine.played), 1)
        clock.t = 0.3
        mapper.handle(0, "left_forearm_up", "start")
        self.assertEqual(len(engine.played), 2)

    def test_different_sounds_do_not_wait_for_each_other(self):
        mapper, engine, clock = make()
        mapper.handle(0, "right_forearm_up", "start")
        mapper.handle(0, "left_foot_up", "start")
        self.assertEqual([p[0] for p in engine.played], ["one_arm_up", "legs"])

    def test_a_long_sound_is_protected_and_not_restarted(self):
        mapper, engine, clock = make()
        mapper.handle(0, "both_hands_up", "start")
        clock.t = 0.4
        self.assertEqual(mapper.handle(0, "right_forearm_up", "start"), [])      # another sound: protected
        self.assertEqual(mapper.handle(0, "arms_crossed", "start"), [])          # the same sound again: cooling down
        clock.t = 1.25
        self.assertEqual(mapper.handle(0, "right_forearm_up", "start"), [])      # still inside protect (1.3 s)
        self.assertEqual([p[0] for p in engine.played], ["big_arms"])

    def test_other_sounds_come_back_after_the_protected_one(self):
        mapper, engine, clock = make()
        mapper.handle(0, "both_hands_up", "start")
        clock.t = 1.4
        self.assertEqual(mapper.handle(0, "right_forearm_up", "start"), ["one_arm_up"])

    def test_sound_options_reach_the_engine(self):
        mapper, engine, _ = make({"a": {"motions": ["forearm_up"], "gain": 0.5, "quantize": 2}})
        mapper.handle(0, "right_forearm_up", "start")
        self.assertEqual(engine.played, [("a", 2, 0.5)])

    def test_a_sound_can_belong_to_one_dancer(self):
        mapper, engine, _ = make({"a": {"motions": ["forearm_up"], "dancer": 1}})
        self.assertEqual(mapper.handle(0, "right_forearm_up", "start"), [])
        self.assertEqual(mapper.handle(1, "right_forearm_up", "start"), ["a"])

    def test_the_number_keys_play_by_hand(self):
        mapper, engine, _ = make()
        mapper.fire("legs")
        self.assertEqual(engine.played[0][0], "legs")
        self.assertEqual(mapper.log[0][1:], ("tus", "legs"))


class ConfigChecks(unittest.TestCase):
    def test_the_default_config_is_valid(self):
        by_motion, problems = resolve(LIVE["sounds"])
        self.assertEqual(problems, [])
        self.assertEqual(set(by_motion.values()), set(LIVE["sounds"]))

    def test_the_library_is_valid(self):
        _, problems = resolve(LIB)
        self.assertEqual(problems, [])

    def test_ab_ab_is_the_sound_and_its_file_is_there(self):
        self.assertIn("ab-ab", LIVE["sounds"])
        for sound in LIVE["sounds"]:
            self.assertTrue((ROOT / LIVE["sounds_dir"] / f"{sound}.wav").exists(), sound)

    def test_no_sound_file_lies_around_unused(self):
        folder = ROOT / LIVE["sounds_dir"]
        loop = (ROOT / LIVE["loop"]["file"]).name
        files = {p.stem for p in folder.iterdir() if p.suffix in (".wav", ".mp3") and p.name != loop}
        self.assertEqual(files - set(LIVE["sounds"]), set())

    def test_an_unknown_motion_is_reported(self):
        _, problems = resolve({"a": {"motions": ["forearm_up", "no_such_motion"]}})
        self.assertEqual(len(problems), 1)
        self.assertIn("no_such_motion", problems[0])

    def test_one_motion_cannot_play_two_sounds(self):
        _, problems = resolve({"a": {"motions": ["forearm_up"]}, "b": {"motions": ["left_forearm_up"]}})
        self.assertEqual(len(problems), 1)
        self.assertIn("left_forearm_up", problems[0])

    def test_a_sound_without_motions_is_reported(self):
        _, problems = resolve({"a": {"motions": []}})
        self.assertEqual(len(problems), 1)


if __name__ == "__main__":
    unittest.main()

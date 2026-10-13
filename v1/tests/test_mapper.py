"""The beat mapper (single and double ab, phrases) and the opening gate.

Run from v1/:  python -m unittest discover -s tests
"""
import pathlib
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dansonic import audio_engine                       # noqa: E402
from dansonic.actions import ActionMapper               # noqa: E402
from dansonic.song import BeatGrid                      # noqa: E402

MAPS = [
    {"sound": "ab", "beat": 1},
    {"sound": "ab-ab", "beat": 1, "both_arms": True, "span": 2},
    {"sound": "been", "beat": 2},
    {"sound": "thin", "beat": 3},
    {"sound": "wha-been", "beat": 4},
    {"sound": "ab-ow-ab-ow-thin", "gestures": ["arms_flail", "both_hands_up"], "cooldown": 1.4, "protect": 1.3},
]
BEATS = {"lookahead": 0.4, "sustain": True, "motion": 0.0003, "min_gap": 0.1, "group": 0.2,
         "hits": ["right_swipe_down", "left_swipe_down", "hands_chest", "right_hand_up", "left_hand_up",
                  "right_hand_chest"]}
OPENING = {"sound": "ab-ab", "motions": ["hands_chest", "hands_on_chest"], "margin": 0.05,
           "loose": ["hands_near_chest", "both_forearms_up"], "hold": 0.3, "grace": 0.15}
INDIVIDUAL = [{"sound": "ab", "gestures": ["left_hand_up", "right_hand_up"]},
              {"sound": "been", "gestures": ["right_foot_up"], "cooldown": 1.0}]


# ---- a fake engine with a simple grid: beat i starts at i * 0.45 s ---------------------------------------------
class FakeEngine:
    def __init__(self, clock):
        self.clock = clock
        self.played = []
        self.grid = mock.Mock(downbeat_index=0)

    def beat_target(self, lookahead, quantize):
        t = self.clock()
        beat = int(t // 0.45)
        if (t - beat * 0.45) / 0.45 > 1 - lookahead:
            beat += 1
        return beat, (beat - self.grid.downbeat_index) % 4, beat

    def beat_landing(self, beat, quantize):
        return beat

    def seconds_to_beat(self, beat):
        return beat * 0.45 - self.clock()

    def current_beat(self):
        return int(self.clock() // 0.45)

    loop_beats = 10 ** 6

    def trigger(self, name, quantize, gain, at=None, skip_beats=0):
        self.played.append((round(self.clock(), 3), name, at, skip_beats))


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(**kw):
    clock = Clock()
    engine = FakeEngine(clock)
    return clock, engine, ActionMapper(engine, MAPS, 4, clock=clock, beats=BEATS, **kw)


def run_until(clock, mapper, t):
    """Advance in 10 ms steps, calling update like the main loop does."""
    while clock.t < t:
        clock.t = round(clock.t + 0.01, 3)
        mapper.update()


def names(engine):
    return [p[1] for p in engine.played]


class BeatMapper(unittest.TestCase):
    def test_one_arm_on_beat_1_plays_ab_at_once_and_nothing_follows(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "right_swipe_down", "hit")
        self.assertEqual(names(e), ["ab"])
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab"])

    def test_both_arms_add_the_second_ab_on_beat_2(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "right_swipe_down", "hit")
        run_until(c, m, c.t + 0.08)
        m.handle(1, "left_swipe_down", "hit")
        self.assertEqual(names(e), ["ab"])
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab", "ab-ab"])
        self.assertEqual((e.played[1][2], e.played[1][3]), (5, 1))            # on beat 2, one beat into the sound

    def test_a_two_armed_pose_start_is_a_double(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "hands_chest", "start")
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab", "ab-ab"])

    def test_the_double_covers_beat_2(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "hands_chest", "start")
        run_until(c, m, c.t + 0.4)
        c.t = 2.30
        self.assertEqual(m.handle(0, "right_swipe_down", "hit"), [])          # beat 2 is covered by the double
        c.t = 2.80
        self.assertEqual(m.handle(0, "right_swipe_down", "hit"), ["thin"])

    def test_a_single_ab_leaves_beat_2_to_been(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "right_swipe_down", "hit")
        run_until(c, m, c.t + 0.4)
        c.t = 2.30
        self.assertEqual(m.handle(0, "right_swipe_down", "hit"), ["been"])

    def test_a_phrase_in_the_window_leaves_no_tail(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "right_swipe_down", "hit")
        run_until(c, m, c.t + 0.05)
        m.handle(0, "both_hands_up", "start")
        run_until(c, m, c.t + 0.5)
        self.assertEqual(names(e), ["ab", "ab-ow-ab-ow-thin"])

    def test_a_phrase_before_beat_2_cancels_a_waiting_tail(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "right_swipe_down", "hit")
        m.handle(0, "left_swipe_down", "hit")
        run_until(c, m, c.t + 0.3)
        self.assertIsNotNone(m.tail)
        m.handle(0, "both_hands_up", "start")
        run_until(c, m, c.t + 0.5)
        self.assertEqual(names(e), ["ab", "ab-ow-ab-ow-thin"])
        self.assertIsNone(m.tail)

    def test_a_second_arm_after_the_window_is_no_double(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "right_swipe_down", "hit")
        run_until(c, m, c.t + 0.3)
        c.t = 2.0
        m.handle(0, "left_swipe_down", "hit")
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab"])

    def test_movement_alone_is_a_single_ab(self):
        c, e, m = make()
        c.t = 1.82
        m.motion(True)
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab"])

    def test_a_held_two_armed_pose_is_a_double_but_two_one_arm_poses_are_not(self):
        c, e, m = make()
        c.t = 1.82
        m.tick(0, {"hands_chest"})
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab", "ab-ab"])
        c, e, m = make()
        c.t = 1.82
        m.tick(0, {"left_hand_up", "right_hand_up"})
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab"])

    def test_a_hit_in_the_window_only_adds_its_arm(self):
        c, e, m = make()
        c.t = 1.95
        m.handle(0, "right_swipe_down", "hit")
        c.t = 2.15
        self.assertEqual(m.handle(0, "left_swipe_down", "hit"), [])
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab", "ab-ab"])

    def test_other_beats_play_at_once_and_open_no_window(self):
        c, e, m = make()
        c.t = 2.30
        self.assertEqual(m.handle(0, "right_swipe_down", "hit"), ["been"])
        self.assertIsNone(m.pending)

    def test_reset_drops_a_waiting_window_and_tail(self):
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "hands_chest", "start")
        self.assertIsNotNone(m.pending)
        m.reset()
        run_until(c, m, c.t + 0.5)
        self.assertEqual(names(e), ["ab"])
        c, e, m = make()
        c.t = 1.82
        m.handle(0, "hands_chest", "start")
        run_until(c, m, c.t + 0.28)
        self.assertIsNotNone(m.tail)
        m.reset()
        run_until(c, m, c.t + 0.4)
        self.assertEqual(names(e), ["ab"])


# ---- the opening gate, on the real engine (sound device stubbed) ---------------------------------------------------
SR = 44100
OFFSET = 0.055
BEAT = 60.0 / 132.905


def beat_time(n: float) -> float:
    return OFFSET + n * BEAT


class Rig:
    """The real AudioEngine and ActionMapper, with a clock that also moves the loop position."""

    def __init__(self, opening=OPENING, downbeat_index=0, individual=None, senkron=None, loop_beats=64):
        grid = BeatGrid(SR, 132.905, OFFSET, downbeat_index)
        loop = np.zeros((int(grid.beat_frames * loop_beats), 2), dtype=np.int16)
        with mock.patch.object(audio_engine.sd, "OutputStream"):
            self.engine = audio_engine.AudioEngine(loop, SR, grid)
        tone = np.ones((SR // 2, 2), dtype=np.float32) * 0.3
        self.engine.samples = {m["sound"]: tone for m in MAPS}
        self.engine.trigger_log = []
        self.engine.playing = True
        self.t = 0.0
        self.mapper = ActionMapper(self.engine, MAPS, 4, clock=lambda: self.t, beats=BEATS, opening=opening,
                                   individual=individual, senkron=senkron)

    def at(self, t):
        self.t = t
        self.engine.pos = int(t * SR)

    def run_until(self, t, step=0.01):
        while self.t < t:
            self.at(round(self.t + step, 4))
            self.mapper.update()

    def sounds(self):
        return [name for name, _ in self.engine.trigger_log]


class Opening(unittest.TestCase):
    def test_nothing_plays_until_the_opening_move_is_seen(self):
        r = Rig()
        r.at(beat_time(5.3))
        m = r.mapper
        self.assertEqual(m.waiting(), "hands_chest / hands_on_chest")
        m.handle(0, "right_swipe_down", "hit")
        m.handle(0, "left_swipe_down", "hit")
        m.handle(0, "both_hands_up", "start")                   # a phrase
        m.handle(0, "arms_flail", "hit")
        m.tick(0, {"right_hand_up", "t_pose"}, {"right_hand_up": 0.4, "t_pose": 0.4})
        m.motion(True)
        r.run_until(r.t + 2.0)
        self.assertEqual(r.sounds(), [])
        self.assertFalse(m.opened)

    def test_the_opening_move_must_be_clearly_reached(self):
        r = Rig()
        r.at(beat_time(5.3))
        self.assertEqual(r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.03}), [])       # held, but only just
        self.assertFalse(r.mapper.opened)
        r.at(beat_time(5.36))
        self.assertEqual(r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.07}), ["ab"])   # now it is clear
        self.assertTrue(r.mapper.opened)

    def test_one_clear_frame_is_enough(self):
        r = Rig()
        r.at(beat_time(5.3))
        self.assertEqual(r.mapper.tick(0, set(), {"hands_chest": 0.3}), ["ab"])      # no waiting for hold frames
        self.assertTrue(r.mapper.opened)

    def test_a_weak_pose_never_opens_however_long_it_is_held(self):
        r = Rig()
        for i in range(200):
            r.at(beat_time(5.3) + i * 0.03)
            r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.04})
        self.assertFalse(r.mapper.opened)

    def test_the_margin_and_hold_default_to_forgiving_values(self):
        r = Rig(opening={"sound": "ab-ab", "motions": ["hands_chest"]})
        self.assertEqual((r.mapper.opening_margin, r.mapper.opening_hold), (0.03, 0.3))

    def test_a_pose_that_was_left_starts_over(self):
        r = Rig()
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.03})
        r.mapper.tick(0, set(), {"hands_chest": -0.2})                                      # let go
        r.at(beat_time(5.5))
        self.assertEqual(r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.04}), [])       # a new try, still weak
        self.assertFalse(r.mapper.opened)

    def test_the_opening_is_ab_then_the_second_ab_on_the_next_beat(self):
        r = Rig()
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        self.assertEqual(r.sounds(), ["ab"])
        r.run_until(beat_time(6.0))
        self.assertEqual(r.sounds(), ["ab", "ab-ab"])
        self.assertEqual(r.engine.trigger_log[1][1], int(round(beat_time(6.0) * SR)))        # exactly on the beat

    def test_the_second_ab_does_not_wait_for_a_second_arm(self):
        r = Rig()
        r.at(beat_time(5.55))                               # late in the beat: a 0.25 s wait would pass beat 6
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        r.run_until(beat_time(6.0))
        self.assertEqual(r.sounds(), ["ab", "ab-ab"])
        self.assertEqual(r.engine.trigger_log[1][1], int(round(beat_time(6.0) * SR)))

    def test_the_beat_in_progress_becomes_beat_1(self):
        r = Rig()
        r.at(beat_time(5.3))                                # the loop's beat 5: beat 2 of its bar by default
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        self.assertEqual(r.engine.grid.downbeat_index, 5 % 4)
        self.assertEqual(r.sounds(), ["ab"])                # beat 1 of the new bar, not been
        r.run_until(beat_time(6.9))
        r.at(beat_time(7.7))                                # late in beat 7: the hit belongs to beat 8, the 4th of the bar
        r.mapper.handle(0, "right_swipe_down", "hit")
        self.assertEqual(r.sounds()[-1], "wha-been")

    def test_it_is_a_double_even_when_the_opening_move_uses_one_arm(self):
        r = Rig(opening={"sound": "ab-ab", "motions": ["right_hand_chest"], "margin": 0.05})
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"right_hand_chest"}, {"right_hand_chest": 0.1})
        r.run_until(beat_time(6.0))
        self.assertEqual(r.sounds(), ["ab", "ab-ab"])

    def test_the_held_pose_does_not_play_the_opening_again(self):
        r = Rig()
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        for _ in range(10):
            r.at(r.t + 0.02)
            r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
            r.mapper.update()
        r.run_until(beat_time(6.4))
        self.assertEqual(r.sounds(), ["ab", "ab-ab"])

    def test_beat_sounds_work_normally_once_open(self):
        r = Rig()
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        r.run_until(beat_time(6.0) + 0.05)
        r.at(beat_time(7.1))                                # beat 3 of the bar (beats 5, 6 were ab, ab)
        r.mapper.handle(0, "right_swipe_down", "hit")
        self.assertEqual(r.sounds()[-1], "thin")

    def test_reset_closes_the_gate_again_and_restores_the_bar(self):
        r = Rig(downbeat_index=0)
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        self.assertEqual(r.engine.grid.downbeat_index, 1)
        r.mapper.reset()
        self.assertEqual(r.engine.grid.downbeat_index, 0)
        self.assertFalse(r.mapper.opened)
        n = len(r.sounds())
        r.at(beat_time(9.3))
        r.mapper.handle(0, "right_swipe_down", "hit")
        r.mapper.motion(True)
        self.assertEqual(len(r.sounds()), n)

    def test_the_o_key_opens_without_a_sound_and_aligns_the_bar(self):
        r = Rig()
        r.at(beat_time(6.4))
        r.mapper.open_now()
        self.assertTrue(r.mapper.opened)
        self.assertEqual(r.sounds(), [])
        self.assertEqual(r.engine.grid.downbeat_index, 6 % 4)
        self.assertIsNone(r.mapper.waiting())

    def test_without_an_opening_section_nothing_is_gated(self):
        r = Rig(opening=None)
        self.assertTrue(r.mapper.opened)
        r.at(beat_time(5.3))
        r.mapper.handle(0, "right_swipe_down", "hit")
        self.assertEqual(r.sounds(), ["been"])
        self.assertEqual(r.engine.grid.downbeat_index, 0)

    def test_the_margin_defaults_to_clear_when_the_detector_gives_none(self):
        r = Rig()
        r.at(beat_time(5.3))
        self.assertEqual(r.mapper.tick(0, {"hands_chest"}), ["ab"])


class LooseOpening(unittest.TestCase):
    """The loose versions of the opening move open the gate when they are held for a moment."""

    def rig(self):
        r = Rig()
        r.at(beat_time(5.3))
        return r

    def hold(self, r, gesture, seconds, margin=0.1, step=0.033):
        end = r.t + seconds
        out = []
        while r.t < end:
            out = r.mapper.tick(0, {gesture}, {gesture: margin})
            r.at(r.t + step)
        return out

    def test_a_loose_version_opens_only_once_it_has_been_held(self):
        r = self.rig()
        self.hold(r, "hands_near_chest", 0.2)
        self.assertFalse(r.mapper.opened)
        self.hold(r, "hands_near_chest", 0.2)
        self.assertTrue(r.mapper.opened)
        self.assertEqual(r.mapper.log[0][1], "acilis: hands_near_chest")
        self.assertEqual(r.sounds()[0], "ab")

    def test_both_forearms_up_is_a_loose_version_too(self):
        r = self.rig()
        self.hold(r, "both_forearms_up", 0.4)
        self.assertTrue(r.mapper.opened)

    def release(self, r, gesture, seconds, step=0.033):
        end = r.t + seconds
        while r.t < end:
            r.mapper.tick(0, set(), {gesture: -0.2})
            r.at(r.t + step)

    def test_a_loose_pose_that_is_let_go_starts_over(self):
        r = self.rig()
        self.hold(r, "hands_near_chest", 0.2)
        self.release(r, "hands_near_chest", 0.2)
        self.hold(r, "hands_near_chest", 0.2)
        self.assertFalse(r.mapper.opened)
        self.hold(r, "hands_near_chest", 0.2)
        self.assertTrue(r.mapper.opened)

    def test_a_dropout_shorter_than_the_grace_does_not_start_the_count_over(self):
        r = self.rig()
        self.hold(r, "hands_near_chest", 0.2)
        self.release(r, "hands_near_chest", 0.07)                         # two frames in which the tracker lost the hands
        self.hold(r, "hands_near_chest", 0.15)
        self.assertTrue(r.mapper.opened)

    def test_a_pose_that_keeps_dropping_out_for_long_stretches_never_opens(self):
        r = self.rig()
        for _ in range(12):
            self.hold(r, "hands_near_chest", 0.2)
            self.release(r, "hands_near_chest", 0.2)
        self.assertFalse(r.mapper.opened)

    def test_a_loose_pose_that_just_passes_through_does_not_open(self):
        r = self.rig()
        self.hold(r, "hands_near_chest", 0.23)                            # the longest the lead's dance ever holds one
        self.release(r, "hands_near_chest", 0.5)
        self.assertFalse(r.mapper.opened)

    def test_a_pose_that_only_just_holds_counts_for_a_loose_version(self):
        r = self.rig()
        self.hold(r, "hands_near_chest", 0.5, margin=0.001)
        self.assertTrue(r.mapper.opened)

    def test_the_loose_version_opens_the_gate_as_a_double_like_the_move_itself(self):
        r = self.rig()
        self.hold(r, "hands_near_chest", 0.4)
        r.run_until(r.t + 0.6)
        self.assertEqual(r.sounds(), ["ab", "ab-ab"])

    def test_a_loose_pose_still_held_when_the_senkron_stops_is_not_a_new_first_move(self):
        r = Rig(senkron={"bars": 2})
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.2})            # the first move opens it
        for _ in range(3000):                                              # then a loose pose is held on and on
            r.at(r.t + 0.005)
            r.mapper.tick(0, {"hands_near_chest"}, {"hands_near_chest": 0.2})
            r.mapper.update()
            if r.t > beat_time(14.5):
                break
        self.assertFalse(r.mapper.opened)

    def test_a_taught_pose_is_the_opening_move_at_once(self):
        r = self.rig()
        r.mapper.add_opening_motion("ab_ab_1")
        self.assertIn("ab_ab_1", r.mapper.waiting())
        self.assertEqual(r.mapper.tick(0, {"ab_ab_1"}, {"ab_ab_1": 0.06}), ["ab"])

    def test_a_pose_that_is_both_listed_and_loose_is_not_loose(self):
        r = Rig(opening={"sound": "ab-ab", "motions": ["hands_chest"], "loose": ["hands_chest", "hands_near_chest"]})
        self.assertEqual(r.mapper.opening_loose, ["hands_near_chest"])

    def test_only_loose_motions_are_enough_to_have_a_gate(self):
        r = Rig(opening={"sound": "ab-ab", "loose": ["hands_near_chest"]})
        self.assertTrue(r.mapper.gated)


class IndividualMotions(unittest.TestCase):
    """Before the senkron starts a motion plays its own sound; once it has started they are silent."""

    def rig(self, **kw):
        r = Rig(individual=INDIVIDUAL, **kw)
        r.at(beat_time(5.3))
        return r

    def open(self, r):
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        self.assertTrue(r.mapper.opened)

    def test_a_hand_up_plays_ab_before_the_senkron_starts(self):
        r = self.rig()
        self.assertEqual(r.mapper.handle(0, "right_hand_up", "start"), ["ab"])
        self.assertEqual(r.sounds(), ["ab"])
        r.at(r.t + 0.5)
        self.assertEqual(r.mapper.handle(0, "left_hand_up", "start"), ["ab"])
        self.assertEqual(r.sounds(), ["ab", "ab"])

    def test_both_hands_at_once_play_it_once(self):
        r = self.rig()
        r.mapper.handle(0, "right_hand_up", "start")
        r.at(r.t + 0.04)
        r.mapper.handle(0, "left_hand_up", "start")
        self.assertEqual(r.sounds(), ["ab"])

    def test_an_individual_motion_does_not_start_the_senkron(self):
        r = self.rig()
        r.mapper.handle(0, "right_hand_up", "start")
        self.assertFalse(r.mapper.opened)
        self.assertIsNotNone(r.mapper.waiting())
        self.assertEqual(r.engine.grid.downbeat_index, 0)
        r.mapper.handle(0, "right_swipe_down", "hit")           # the dance itself is still locked
        r.mapper.motion(True)
        self.assertEqual(r.sounds(), ["ab"])

    def test_a_motion_that_is_not_listed_stays_silent(self):
        r = self.rig()
        for gesture in ("right_swipe_down", "both_hands_up", "t_pose", "arms_flail"):
            self.assertEqual(r.mapper.handle(0, gesture, "start"), [])
        self.assertEqual(r.mapper.tick(0, {"right_hand_up"}, {"right_hand_up": 0.5}), [])    # a held pose is no start
        self.assertEqual(r.sounds(), [])

    def test_they_are_silent_once_the_senkron_has_started(self):
        r = self.rig()
        self.open(r)
        n = len(r.sounds())
        r.run_until(beat_time(6.5))
        self.assertEqual(r.mapper.handle(0, "right_foot_up", "start"), [])      # a listed motion that is no beat hit
        self.assertEqual(len(r.sounds()), n + 1)                                # only the opening's second ab came since

    def test_a_hand_up_in_the_senkron_is_a_beat_hit_not_ab(self):
        r = self.rig()
        self.open(r)
        r.run_until(beat_time(6.9))
        r.at(beat_time(7.1))                                    # beat 3 of the bar the opening started
        r.mapper.handle(0, "right_hand_up", "start")
        self.assertEqual(r.sounds()[-1], "thin")
        self.assertNotIn("tek", r.mapper.log[-1][1])

    def test_they_are_alive_again_after_a_reset(self):
        r = self.rig()
        self.open(r)
        r.mapper.reset()
        r.at(beat_time(30.3))
        self.assertEqual(r.mapper.handle(0, "right_foot_up", "start"), ["been"])

    def test_the_senkron_still_starts_after_individual_motions(self):
        r = self.rig()
        r.mapper.handle(0, "right_hand_up", "start")
        r.at(r.t + 0.6)
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        self.assertTrue(r.mapper.opened)
        self.assertEqual(r.sounds(), ["ab", "ab"])              # the individual ab, then the opening's first ab

    def test_cooldown_and_dancer_come_from_the_entry(self):
        r = self.rig()
        r.mapper.handle(0, "right_foot_up", "start")
        r.at(r.t + 0.5)
        self.assertEqual(r.mapper.handle(0, "right_foot_up", "start"), [])      # cooldown 1.0
        r.at(r.t + 0.6)
        self.assertEqual(r.mapper.handle(0, "right_foot_up", "start"), ["been"])
        r2 = Rig(individual=[{"sound": "ab", "gestures": ["right_hand_up"], "dancer": 1}])
        r2.at(beat_time(5.3))
        self.assertEqual(r2.mapper.handle(0, "right_hand_up", "start"), [])
        self.assertEqual(r2.mapper.handle(1, "right_hand_up", "start"), ["ab"])

    def test_without_an_opening_the_dance_is_always_on_and_they_never_play(self):
        r = Rig(opening=None, individual=INDIVIDUAL)
        r.at(beat_time(5.3))
        self.assertEqual(r.mapper.handle(0, "right_foot_up", "start"), [])
        self.assertEqual(r.sounds(), [])

    def test_the_log_says_which_motion_it_was(self):
        r = self.rig()
        r.mapper.handle(0, "left_hand_up", "start")
        self.assertEqual(r.mapper.log[-1][1:], ("tek: left_hand_up", "ab", None))


class SenkronEnd(unittest.TestCase):
    """The senkron stops with its last sound and waits for the first move again. Two bars (8 beats) keep the tests short."""

    BARS = {"bars": 2}

    def rig(self, **kw):
        r = Rig(individual=INDIVIDUAL, senkron=self.BARS, **kw)
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})        # the first move: beat 5 is beat 1 of the senkron
        self.assertTrue(r.mapper.opened)
        r.mapper.tick(0, set(), {"hands_chest": -0.4})                  # the pose is over a moment later
        return r

    def test_the_last_beat_plays_and_then_the_senkron_stops(self):
        r = self.rig()
        r.run_until(beat_time(12.2))                            # inside beat 12, the 8th and last one
        self.assertTrue(r.mapper.opened)
        n = len(r.sounds())
        r.mapper.handle(0, "right_swipe_down", "hit")           # a hit on the last beat still plays
        self.assertEqual(len(r.sounds()), n + 1)
        r.run_until(beat_time(13.05))
        self.assertFalse(r.mapper.opened)
        self.assertTrue(r.mapper.ended)
        self.assertEqual(r.mapper.log[-1][1:], ("senkron bitti", "", None))

    def test_nothing_of_the_dance_plays_after_the_last_beat(self):
        r = self.rig()
        r.run_until(beat_time(13.05))
        n = len(r.sounds())
        r.at(beat_time(14.3))
        m = r.mapper
        m.handle(0, "right_swipe_down", "hit")
        m.handle(0, "both_hands_up", "start")
        m.handle(0, "arms_flail", "hit")
        m.tick(0, {"right_hand_up", "t_pose"}, {"right_hand_up": 0.5, "t_pose": 0.5})
        m.motion(True)
        r.run_until(r.t + 2.0)
        self.assertEqual(len(r.sounds()), n)

    def test_a_hit_that_is_for_the_beat_after_the_last_one_is_dropped(self):
        r = self.rig()
        r.run_until(beat_time(12.0))
        n = len(r.sounds())
        r.at(beat_time(12.8))                                   # late in the last beat: the hit belongs to beat 13
        r.mapper.handle(0, "right_swipe_down", "hit")
        self.assertEqual(len(r.sounds()), n)

    def test_the_stop_does_not_cut_a_sound_that_is_still_playing(self):
        r = self.rig()
        r.run_until(beat_time(12.5))
        r.mapper.handle(0, "right_swipe_down", "hit")
        voices = len(r.engine.voices)
        r.run_until(beat_time(13.05))
        self.assertFalse(r.mapper.opened)
        self.assertEqual(len(r.engine.voices), voices)

    def test_it_waits_for_the_first_move_and_then_starts_a_new_senkron(self):
        r = self.rig()
        r.run_until(beat_time(13.05))
        self.assertEqual(r.mapper.waiting(), "hands_chest / hands_on_chest")
        r.at(beat_time(15.3))
        r.mapper.handle(0, "right_swipe_down", "hit")
        self.assertFalse(r.mapper.opened)
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})             # the first move, made again
        self.assertTrue(r.mapper.opened)
        self.assertFalse(r.mapper.ended)
        self.assertEqual(r.engine.grid.downbeat_index, 15 % 4)
        r.run_until(beat_time(15.0 + 8.05))                                 # and that one lasts two bars as well
        self.assertFalse(r.mapper.opened)

    def test_a_pose_still_held_from_before_is_not_a_new_first_move(self):
        r = self.rig()
        for _ in range(3000):                                   # the dancer keeps holding the opening pose
            r.at(r.t + 0.005)
            r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.3})
            r.mapper.update()
            if r.t > beat_time(14.0):
                break
        self.assertFalse(r.mapper.opened)                       # the stop at beat 13 was not undone
        r.mapper.tick(0, set(), {"hands_chest": -0.3})          # let go ...
        r.at(r.t + 0.2)
        r.mapper.tick(0, set(), {"hands_chest": -0.3})
        r.at(r.t + 0.05)
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.3})  # ... and make it again
        self.assertTrue(r.mapper.opened)

    def test_a_dropout_in_a_pose_held_through_the_stop_is_not_letting_go(self):
        r = self.rig()
        for _ in range(3000):                                   # the opening pose is held through the stop ...
            r.at(r.t + 0.005)
            r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.3})
            r.mapper.update()
            if r.t > beat_time(14.0):
                break
        self.assertFalse(r.mapper.opened)
        r.mapper.tick(0, set(), {"hands_chest": 0.0})           # ... one frame it dips under the margin
        r.at(r.t + 0.033)
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.3})
        self.assertFalse(r.mapper.opened)                       # the dancer never let go

    def test_the_individual_motions_sound_again_after_the_stop(self):
        r = self.rig()
        self.assertEqual(r.mapper.handle(0, "right_foot_up", "start"), [])        # silent inside the senkron
        r.run_until(beat_time(13.05))
        r.at(r.t + 0.5)
        self.assertEqual(r.mapper.handle(0, "right_foot_up", "start"), ["been"])

    def test_it_is_counted_from_the_opening_beat_even_when_the_move_came_late_in_it(self):
        r = Rig(senkron=self.BARS)
        r.at(beat_time(5.9))                                    # seen late in beat 5
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        r.run_until(beat_time(12.95))
        self.assertTrue(r.mapper.opened)
        r.run_until(beat_time(13.05))
        self.assertFalse(r.mapper.opened)

    def test_it_stops_when_the_loop_wraps_during_the_senkron(self):
        r = Rig(senkron=self.BARS, loop_beats=16)
        r.at(beat_time(14.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        self.assertEqual(r.mapper.open_beat, 14)
        r.at(beat_time(16.0 + 5.5))                             # wrapped: the engine is at beat 5 of the next round
        r.engine.pos = int(beat_time(5.5) * SR)
        r.mapper.update()
        self.assertTrue(r.mapper.opened)                        # beat 21 of the senkron's counting is not yet 14 + 8
        r.engine.pos = int(beat_time(6.1) * SR)
        r.mapper.update()
        self.assertFalse(r.mapper.opened)

    def test_a_paused_loop_does_not_run_the_senkron_out(self):
        r = self.rig()
        r.t += 60.0                                             # a minute passes on the clock, the loop is paused
        r.mapper.update()
        self.assertTrue(r.mapper.opened)

    def test_without_a_senkron_section_it_never_ends(self):
        r = Rig(senkron=None)
        r.at(beat_time(5.3))
        r.mapper.tick(0, {"hands_chest"}, {"hands_chest": 0.1})
        r.at(beat_time(5.3 + 30))
        r.mapper.update()
        self.assertTrue(r.mapper.opened)

    def test_reset_clears_the_ended_state(self):
        r = self.rig()
        r.run_until(beat_time(13.05))
        self.assertTrue(r.mapper.ended)
        r.mapper.reset()
        self.assertFalse(r.mapper.ended)
        self.assertFalse(r.mapper.opened)


if __name__ == "__main__":
    unittest.main()

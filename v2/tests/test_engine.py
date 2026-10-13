"""The audio engine: quantizing, choking and mixing, with the sound device stubbed out.

Run from v2/:  python -m unittest discover -s tests
"""
import pathlib
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dansonic import audio_engine                       # noqa: E402
from dansonic.song import BeatGrid                      # noqa: E402

SR = 44100
BPM = 132.905


def make_engine():
    grid = BeatGrid(SR, BPM, 0.055)
    loop = np.zeros((int(grid.beat_frames * 8), 2), dtype=np.int16)
    with mock.patch.object(audio_engine.sd, "OutputStream"):
        engine = audio_engine.AudioEngine(loop, SR, grid)
    tone = np.ones((SR // 2, 2), dtype=np.float32) * 0.5          # half a second of constant level
    engine.samples = {"a": tone, "b": tone * 0.5}
    engine.playing = True
    engine.trigger_log = []
    return engine


def render(engine, blocks):
    out = []
    for _ in range(blocks):
        buf = np.zeros((engine.blocksize, 2), np.float32)
        engine._callback(buf, engine.blocksize, None, None)
        out.append(buf)
    return np.concatenate(out)


class Engine(unittest.TestCase):
    def test_a_trigger_waits_for_the_next_sixteenth(self):
        engine = make_engine()
        engine.pos = 1000
        engine.trigger("a", quantize=4)
        wait = engine.voices[0]["wait"]
        self.assertGreater(wait, 0)
        self.assertLessEqual(wait, engine.grid.beat_frames / 4 + 1)
        self.assertEqual(engine.grid.next_grid_frame(1000, 4), 1000 + wait)

    def test_quantize_zero_plays_now(self):
        engine = make_engine()
        engine.pos = 1000
        engine.trigger("a", quantize=0)
        self.assertEqual(engine.voices[0]["wait"], 0)

    def test_the_sound_starts_on_its_frame(self):
        engine = make_engine()
        engine.pos = 0
        engine.trigger("a", quantize=0)
        out = render(engine, 4)
        self.assertAlmostEqual(float(out[0, 0]), 0.5 * 0.9, places=3)         # master gain 0.9

    def test_the_later_sound_replaces_one_still_waiting_for_the_same_slot(self):
        engine = make_engine()
        engine.pos = 1000
        engine.trigger("a", quantize=4)
        engine.pos = 1500                                       # later, still before that grid point
        engine.trigger("b", quantize=4)
        self.assertEqual([name for name, _ in engine.trigger_log], ["b"])
        out = render(engine, 120)
        self.assertTrue(np.all(out <= 0.25 * 0.9 + 1e-3))       # only b (level 0.25) is ever heard

    def test_a_new_sound_chokes_one_that_is_playing(self):
        engine = make_engine()
        engine.pos = 0
        engine.trigger("a", quantize=0)
        render(engine, 20)                                      # a has been playing for a while
        engine.trigger("b", quantize=0)
        out = render(engine, 12)
        self.assertAlmostEqual(float(out[-1, 0]), 0.25 * 0.9, places=3)         # a is gone, b remains

    def test_choke_can_be_switched_off(self):
        engine = make_engine()
        engine.choke = False
        engine.pos = 0
        engine.trigger("a", quantize=0)
        engine.trigger("b", quantize=0)
        out = render(engine, 4)
        self.assertAlmostEqual(float(out[-1, 0]), (0.5 + 0.25) * 0.9, places=3)

    def test_unknown_sounds_and_a_stopped_loop(self):
        engine = make_engine()
        engine.trigger("no_such_sound", quantize=4)
        self.assertEqual(engine.voices, [])
        engine.playing = False
        pos = engine.pos
        render(engine, 3)
        self.assertEqual(engine.pos, pos)

    def test_output_never_clips(self):
        engine = make_engine()
        engine.choke = False
        for _ in range(8):
            engine.trigger("a", quantize=0)
        self.assertLessEqual(float(np.abs(render(engine, 10)).max()), 1.0)


if __name__ == "__main__":
    unittest.main()

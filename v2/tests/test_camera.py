"""Picking the camera by name: the iPhone comes and goes, so a fixed index can land on the wrong camera.

Run from v2/:  python -m unittest discover -s tests
"""
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dansonic import camera as C                        # noqa: E402

BOTH = ["Caglan iPhone Camera", "FaceTime HD Camera"]    # OpenCV order: sorted by uniqueID, the iPhone first
BUILT_IN_ONLY = ["FaceTime HD Camera"]


class PickCameraTest(unittest.TestCase):
    def test_finds_the_name_wherever_it_sits(self):
        self.assertEqual(C.pick_camera(BOTH, "iphone"), 0)
        self.assertEqual(C.pick_camera(list(reversed(BOTH)), "iphone"), 1)

    def test_ignores_case(self):
        self.assertEqual(C.pick_camera(BOTH, "FACETIME"), 1)

    def test_none_when_the_camera_is_not_there(self):
        self.assertIsNone(C.pick_camera(BUILT_IN_ONLY, "iphone"))


class ResolveSourceTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("builtins.print")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_numbers_and_video_paths_pass_through(self):
        for source in (0, 1, "1", "clip.mp4", "videos/clip", "/tmp/clip"):
            self.assertEqual(C.resolve_source(source), source)

    def test_name_becomes_its_index(self):
        with mock.patch.object(C, "camera_names", return_value=BOTH):
            self.assertEqual(C.resolve_source("iphone"), 0)

    def test_waits_for_the_phone_then_takes_it(self):
        with mock.patch.object(C, "camera_names", side_effect=[BUILT_IN_ONLY, BUILT_IN_ONLY, BOTH]), \
                mock.patch.object(C.time, "sleep"):
            self.assertEqual(C.resolve_source("iphone"), 0)

    def test_falls_back_to_camera_0_when_the_phone_never_shows_up(self):
        with mock.patch.object(C, "camera_names", return_value=BUILT_IN_ONLY), \
                mock.patch.object(C.time, "sleep"), \
                mock.patch.object(C.time, "monotonic", side_effect=[0.0, 1.0, 7.0]):
            self.assertEqual(C.resolve_source("iphone"), 0)


if __name__ == "__main__":
    unittest.main()

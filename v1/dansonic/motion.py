"""Movement anywhere in the picture, found by frame differencing (no pose needed).

Pose tracking follows one dancer and can miss a small or low-contrast one. This just asks:
is something in view moving right now? While it is, the sung line keeps going on the beat.
"""
import cv2
import numpy as np


class SceneMotion:
    """True while the share of pixels that change between frames stays above `threshold`."""

    def __init__(self, threshold=0.0006, width=160, pixel_diff=12, hold=0.15, cut=0.25):
        self.threshold = threshold
        self.width = width              # frames are shrunk to this width first (fast, and ignores noise)
        self.pixel_diff = pixel_diff    # grey levels a pixel must change to count
        self.hold = hold                # seconds the state stays on after the last movement
        self.cut = cut                  # more than this share changing is a cut or an exposure jump, not a dancer
        self.prev = None
        self.level = 0.0                # smoothed share of changed pixels, for tuning
        self.moving_until = -1e9

    def update(self, frame, t: float) -> bool:
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (self.width, max(1, int(h * self.width / w))), interpolation=cv2.INTER_AREA)
        grey = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
        grey -= grey.mean()             # a change of overall brightness is not movement
        share = 0.0
        if self.prev is not None and self.prev.shape == grey.shape:
            share = float(np.mean(np.abs(grey - self.prev) > self.pixel_diff))
            if share > self.cut:
                share = 0.0
        self.prev = grey
        self.level = 0.5 * self.level + 0.5 * share
        if self.level > self.threshold:
            self.moving_until = t + self.hold
        return t < self.moving_until

    def reset(self):
        self.prev = None
        self.level = 0.0
        self.moving_until = -1e9

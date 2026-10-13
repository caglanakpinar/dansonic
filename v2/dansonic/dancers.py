"""Assigns detected poses to stable dancer slots."""
import numpy as np


class DancerAssigner:
    """zones: slot = rank of hip x on screen (left to right).
    track: nearest-neighbour matching against last known positions."""

    def __init__(self, max_dancers=5, mode="zones", lost_after=0.6, max_jump=0.25):
        self.max_dancers = max_dancers
        self.mode = mode
        self.lost_after = lost_after
        self.max_jump = max_jump
        self.last_pos = {}      # slot -> (x, y)
        self.last_seen = {}     # slot -> t

    @staticmethod
    def _center(lm, mirror):
        c = (lm[23, :2] + lm[24, :2]) / 2
        return (1.0 - c[0], c[1]) if mirror else (float(c[0]), float(c[1]))

    def assign(self, poses: list, t: float, mirror: bool) -> tuple:
        """Returns ({slot: landmarks}, [lost slots])."""
        centers = [self._center(lm, mirror) for lm in poses]
        assigned = {}
        if self.mode == "zones":
            order = np.argsort([c[0] for c in centers])[: self.max_dancers]
            for slot, i in enumerate(order):
                assigned[slot] = poses[i]
        else:
            free = set(range(len(poses)))
            for slot, pos in sorted(self.last_pos.items()):
                if not free:
                    break
                best = min(free, key=lambda i: np.hypot(centers[i][0] - pos[0], centers[i][1] - pos[1]))
                if np.hypot(centers[best][0] - pos[0], centers[best][1] - pos[1]) < self.max_jump:
                    assigned[slot] = poses[best]
                    free.discard(best)
            for i in sorted(free, key=lambda i: centers[i][0]):
                slot = next(s for s in range(self.max_dancers + len(poses)) if s not in assigned)
                if slot >= self.max_dancers:
                    break
                assigned[slot] = poses[i]

        for slot, lm in assigned.items():
            self.last_pos[slot] = self._center(lm, mirror)
            self.last_seen[slot] = t
        lost = [s for s, ts in list(self.last_seen.items())
                if s not in assigned and t - ts > self.lost_after]
        for s in lost:
            del self.last_seen[s]
            self.last_pos.pop(s, None)
        return assigned, lost


class SingleDancer:
    """Locks onto one person and ignores everyone else in frame.

    The first pick follows `select` (center, largest, left, right on screen).
    After that the same body is followed by position and by the colour of its
    torso clothing, so the lock survives dancers crossing or briefly hiding
    each other. If the locked dancer is gone for `lost_after` seconds, the
    person whose clothing matches is picked again, falling back to `select`.
    """

    COLOR_WEIGHT = 1.5      # how strongly clothing colour outweighs position
    MIN_SIMILARITY = 0.55   # clothing match needed to re-acquire without position

    def __init__(self, select="center", lost_after=1.0, max_jump=0.25):
        self.select = select
        self.lost_after = lost_after
        self.max_jump = max_jump
        self.pos = None
        self.signature = None
        self.last_seen = -1e9
        self.switch_requested = False

    @staticmethod
    def _center(lm, mirror):
        c = (lm[11, :2] + lm[12, :2] + lm[23, :2] + lm[24, :2]) / 4
        return np.array([1.0 - c[0] if mirror else c[0], c[1]])

    @staticmethod
    def _size(lm):
        return float(np.linalg.norm((lm[11, :2] + lm[12, :2]) / 2 - (lm[23, :2] + lm[24, :2]) / 2))

    @staticmethod
    def _signature(lm, rgb):
        """Hue/saturation histogram of the torso area, or None if it is too small."""
        import cv2
        h, w = rgb.shape[:2]
        quad = lm[[11, 12, 24, 23], :2] * (w, h)
        quad = quad.mean(axis=0) + (quad - quad.mean(axis=0)) * 0.75
        x0, y0 = np.clip(quad.min(axis=0), 0, (w - 1, h - 1)).astype(int)
        x1, y1 = np.clip(quad.max(axis=0), 0, (w, h)).astype(int)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        hsv = cv2.cvtColor(np.ascontiguousarray(rgb[y0:y1, x0:x1]), cv2.COLOR_RGB2HSV)
        # brightness is included coarsely so black, grey and white clothes differ
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 3], [0, 180, 0, 256, 0, 256]).flatten()
        total = hist.sum()
        return hist / total if total > 0 else None

    def _similarity(self, sig) -> float:
        if sig is None or self.signature is None:
            return 0.5
        return float(np.minimum(sig, self.signature).sum())

    def _pick(self, poses, centers):
        if self.select == "largest":
            return int(np.argmax([self._size(lm) for lm in poses]))
        if self.select == "left":
            return int(np.argmin([c[0] for c in centers]))
        if self.select == "right":
            return int(np.argmax([c[0] for c in centers]))
        return int(np.argmin([abs(c[0] - 0.5) for c in centers]))

    def switch(self):
        """Move the lock to another person on the next frame."""
        self.switch_requested = True

    def _lock(self, chosen, centers, sigs, t, reset=False):
        self.pos = centers[chosen]
        self.last_seen = t
        sig = sigs[chosen]
        if sig is not None:
            # learn slowly, and not while another body is close enough to bleed into the torso box
            crowded = any(np.linalg.norm(c - self.pos) < 0.12 for i, c in enumerate(centers) if i != chosen)
            if reset or self.signature is None:
                self.signature = sig
            elif not crowded:
                self.signature = 0.95 * self.signature + 0.05 * sig

    def assign(self, poses: list, t: float, mirror: bool, rgb=None) -> tuple:
        """Returns ({0: landmarks} or {}, [lost slots], [ignored poses])."""
        expired = self.pos is not None and t - self.last_seen > self.lost_after
        if not poses:
            if expired:
                self.pos = None
            return {}, [0] if expired else [], []
        centers = [self._center(lm, mirror) for lm in poses]
        sigs = [self._signature(lm, rgb) if rgb is not None else None for lm in poses]
        others = lambda k: [p for i, p in enumerate(poses) if i != k]

        if self.switch_requested and len(poses) > 1 and self.pos is not None:
            self.switch_requested = False
            dists = [float(np.linalg.norm(c - self.pos)) for c in centers]
            chosen = int(np.argsort(dists)[1])
            self._lock(chosen, centers, sigs, t, reset=True)
            return {0: poses[chosen]}, [], others(chosen)
        self.switch_requested = False

        if self.pos is not None and not expired:
            dists = [float(np.linalg.norm(c - self.pos)) for c in centers]
            sims = [self._similarity(sg) for sg in sigs]
            cost = [d / self.max_jump + self.COLOR_WEIGHT * (1.0 - sm) for d, sm in zip(dists, sims)]
            chosen = int(np.argmin(cost))
            near = dists[chosen] < self.max_jump and sims[chosen] >= 0.3
            if near or sims[chosen] >= self.MIN_SIMILARITY:
                self._lock(chosen, centers, sigs, t)
                return {0: poses[chosen]}, [], others(chosen)
            return {}, [], list(poses)      # locked dancer hidden for a moment: wait

        lost = [0] if self.pos is not None else []
        chosen = None
        if self.signature is not None:
            sims = [self._similarity(sg) for sg in sigs]
            if max(sims) >= self.MIN_SIMILARITY:
                chosen = int(np.argmax(sims))
        if chosen is None:
            chosen = self._pick(poses, centers)
            self._lock(chosen, centers, sigs, t, reset=True)
        else:
            self._lock(chosen, centers, sigs, t)
        return {0: poses[chosen]}, lost, others(chosen)

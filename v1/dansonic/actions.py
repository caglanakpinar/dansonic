"""Turns gesture events into sound triggers according to the config mapping.

Two ways to trigger a sound:
  - a mapping entry lists `gestures`: those moves play that sound, whenever they happen;
  - the `beats` section lists `hits`: any of those moves plays the sound whose `beat` (1-4)
    is the beat of the bar the hit lands on, at most one per beat. So the dancer only has to
    hit on the beat and the sung line (beat 1, 2, 3, 4) comes out in order.
    With `sustain`, a held pose that is a hit keeps the line going, one sound per beat.
    With `motion`, so does any movement in view (see motion.py), even a dancer the pose
    tracker does not see or a move that is no known gesture.
    A second entry for the same beat with `both_arms: true` is the double (in the song beat 1 is
    sometimes one ab and sometimes two: ab ab). The plain sound plays at once as always; if both arms
    hit within `group` seconds of it (both hands to the chest, both arms up, a left and a right swipe
    together) the rest of the double, its second beat, follows on beat 2 in place of that beat's sound.
A gesture that has its own mapping entry is not also a hit.

The dance opens with ab ab. With an `opening` section nothing plays, not even a hit, a held pose, movement in
view or a phrase, until the opening move has been seen: one of the opening motions held and clearly reached
(its margin at least `margin`). That moment then becomes beat 1 of the bar and the opening plays as a double,
so it always comes out as ab ab. Restarting the loop or the video closes the gate again.

The dance that starts with the opening is the senkron. Until it starts, the `individual` motions are alive: each
plays its own sound right away (a hand up plays ab) and does not start the senkron. Once the senkron has
started they are silent; the beat sounds take over.

The opening is forgiving. Its `motions` open the gate the moment one of them is clearly reached (margin at least
`margin`, one frame is enough); the `loose` motions are looser versions of the same move (hands near the chest,
both forearms up) and open it when held for `hold` seconds (a dropout shorter than `grace` seconds, a frame the
pose tracker lost the hands, does not start the count over). Poses the dancer has taught the app
(poses/ab_ab_*.json, the K key) are added to `motions`.

The senkron stops with its last sound. With a `senkron` section it lasts `bars` bars from the opening (the song's
sung line is 10 bars): the last beat plays, then the gate closes again. Nothing of the dance plays after that,
whatever the dancers do, until the opening move has been seen again: a pose that is still held from before does
not count, it has to be made anew. Meanwhile the individual motions sound again.
"""
import time

# moves that use both arms at once; left_* and right_* gestures are one arm
TWO_ARMED = {"hands_chest", "hands_on_chest", "hands_near_chest", "both_forearms_up", "both_hands_up",
             "hands_together", "t_pose", "hands_on_hips", "arms_crossed"}


class ActionMapper:
    def __init__(self, engine, mappings: list, default_quantize: int, clock=time.monotonic, beats=None, opening=None,
                 individual=None, senkron=None):
        self.engine = engine
        self.default_quantize = default_quantize
        self.clock = clock
        self.last_fired = {}    # sound -> time of its last gesture trigger
        self.protected_sound = None
        self.protected_until = -1e9
        self.by_gesture = {}
        for m in mappings:
            for gesture in m.get("gestures", []):
                self.by_gesture.setdefault(gesture, []).append(m)
        beats = beats or {}
        self.hits = set(beats.get("hits", [])) - set(self.by_gesture)
        self.lookahead = float(beats.get("lookahead", 0.25))
        self.sustain = bool(beats.get("sustain", False))
        self.min_gap = float(beats.get("min_gap", 0.1))     # seconds: two hits this close are one
        self.use_motion = bool(beats.get("motion"))
        self.group = float(beats.get("group", 0.25))       # seconds a beat with a double watches for the second arm
        self.two_armed = TWO_ARMED | set(beats.get("two_armed", []))
        self.bar_sounds = {}     # beat of the bar (0-3) -> the sound a hit plays
        self.double_sounds = {}  # beat of the bar -> the sound a hit with both arms plays
        for m in mappings:
            if "beat" in m:
                if m.get("both_arms"):
                    self.double_sounds[int(m["beat"]) - 1] = m
                else:
                    self.bar_sounds[int(m["beat"]) - 1] = m
        self.claimed = (None, None)     # the beats the last beat sound covers (a double covers two)
        self.last_beat_time = -1e9
        self.pending = None     # the beat just played whose arms are still being counted (see `group`)
        self.tail = None        # the double's second beat, waiting for its beat to come
        self.lead = 0.07        # seconds before its beat that a tail is started
        self.log = []           # (time, gesture, sound, beat of the bar or None)
        opening = opening or {}
        self.opening_motions = list(opening.get("motions") or [])   # the move itself: one clear frame opens the gate
        self.opening_loose = [g for g in (opening.get("loose") or []) if g not in self.opening_motions]
        self.opening_margin = float(opening.get("margin", 0.03))    # how clearly the move must be reached
        self.opening_hold = float(opening.get("hold", 0.3))         # seconds a loose version must be held
        self.opening_grace = float(opening.get("grace", 0.15))      # seconds a held pose may drop out without starting over
        self.gated = bool(opening.get("sound") and (self.opening_motions or self.opening_loose))
        self.opened = not self.gated
        self.opened_at = None
        self.held_since = {}    # loose opening motion -> when it started being held
        self.lost_since = {}    # opening motion -> when it was last seen going out of reach
        self.last_margins = {}  # how clearly each pose was held on the last frame
        self.first_downbeat = engine.grid.downbeat_index
        self.senkron_beats = int((senkron or {}).get("bars", 0)) * 4    # beats from the opening to the last sound (0: no end)
        self.open_beat = None   # the beat the opening started on: beat 1 of the senkron
        self.ended = False      # the senkron has played its last sound and is waiting for the opening again
        self.last_active = set()    # the poses seen on the last frame
        self.stale = set()      # opening motions still held when the gate closed: they are not a new first move
        self.individual_by_gesture = {}     # gesture -> its entry in `individual`
        for m in individual or []:
            for gesture in m.get("gestures", []):
                self.individual_by_gesture[gesture] = m
        self.last_individual = {}           # sound -> time an individual motion last played it

    def reset(self):
        """The loop was moved (restart, the video looped): beats are numbered from the start again, and the
        dance has to open with ab ab again."""
        self.pending = self.tail = None
        self.claimed = (None, None)
        if self.gated:
            self.close()
            self.ended = False
            self.engine.grid.downbeat_index = self.first_downbeat

    def close(self):
        """Closes the gate: the opening move has to be seen (made anew) before the dance plays again."""
        self.opened, self.opened_at, self.open_beat = False, None, None
        self.held_since, self.lost_since = {}, {}
        self.stale = {g for g in self.opening_motions + self.opening_loose
                      if self.reached(g, self.last_active, self.last_margins)}

    def stop(self):
        """The last sound has played: the senkron is over."""
        self.pending = self.tail = None
        self.claimed = (None, None)
        self.close()
        self.ended = True
        self.log.append((self.clock(), "senkron bitti", "", None))

    def is_past_the_end(self, beat: int) -> bool:
        """Is this beat after the senkron's last one?"""
        if not self.senkron_beats or self.open_beat is None:
            return False
        return (beat - self.open_beat) % self.engine.loop_beats >= self.senkron_beats

    def watch_end(self):
        if self.opened and self.is_past_the_end(self.engine.current_beat()):
            self.stop()

    def waiting(self):
        """What the gate is waiting for, or None once the dance has opened."""
        return None if self.opened else " / ".join(self.opening_motions)

    def margin_of(self, gesture, active, margins) -> float:
        """How clearly a pose is held: its margin, or (for a detector that gives none) clear when held."""
        if margins and gesture in margins:
            return margins[gesture]
        return 1.0 if gesture in active else -1.0

    def reached(self, gesture, active, margins) -> bool:
        threshold = self.opening_margin if gesture in self.opening_motions else 0.0
        return self.margin_of(gesture, active, margins) >= threshold

    def add_opening_motion(self, gesture):
        """A pose the dancer taught the app is the opening move too."""
        if self.gated and gesture not in self.opening_motions:
            self.opening_motions.append(gesture)
            if gesture in self.opening_loose:
                self.opening_loose.remove(gesture)

    def watch_opening(self, slot, active, margins) -> list:
        """Opens the gate when the opening move is seen: one of `opening_motions` clearly reached (one frame is
        enough), or one of the loose versions held for `opening_hold` seconds. A pose still held from before the gate
        closed does not count until it has been let go; letting go means out of reach for `opening_grace` seconds,
        so a frame in which the tracker lost the hands changes neither that nor a count in progress."""
        now = self.clock()
        for gesture in self.opening_motions + self.opening_loose:
            if not self.reached(gesture, active, margins):
                if now - self.lost_since.setdefault(gesture, now) >= self.opening_grace:
                    self.stale.discard(gesture)
                    self.held_since.pop(gesture, None)
                continue
            self.lost_since.pop(gesture, None)
            if gesture in self.stale:
                continue
            if gesture in self.opening_motions:
                return self.open(slot, gesture)
            since = self.held_since.setdefault(gesture, now)
            if now - since >= self.opening_hold:
                return self.open(slot, gesture)
        return []

    def open(self, slot, gesture) -> list:
        """The opening move was seen: its beat is beat 1 of the bar and it plays as a double, ab ab."""
        self.open_now()
        fired = self.fire_on_beat(slot, {"L", "R"}, f"acilis: {gesture}", lookahead=0.0)
        if self.pending is not None:            # both arms are known: the second ab need not wait for a second arm
            self.pending["t0"] = self.clock() - self.group
        return fired

    def open_now(self):
        """Opens the gate without a sound (the O key). The beat in progress becomes beat 1."""
        self.opened, self.opened_at, self.ended = True, self.clock(), False
        beat, _, _ = self.engine.beat_target(0.0, self.default_quantize)
        self.open_beat = beat
        self.engine.grid.downbeat_index = beat % 4

    def is_claimed(self, beat: int) -> bool:
        lo, hi = self.claimed
        return lo is not None and lo <= beat <= hi

    def arms_of(self, gesture: str) -> set:
        """Which arms a move uses: 'L', 'R', both or neither (an unknown recorded pose)."""
        if gesture in self.two_armed:
            return {"L", "R"}
        if gesture.startswith("left_"):
            return {"L"}
        if gesture.startswith("right_"):
            return {"R"}
        return set()

    def handle(self, slot: int, gesture: str, kind: str) -> list:
        """Returns the names of the sounds that were triggered."""
        if kind not in ("start", "hit"):
            return []
        if not self.opened:                                 # the senkron has not started: only individual motions sound
            return self.handle_individual(slot, gesture)
        fired = []
        for m in self.by_gesture.get(gesture, []):
            target = m.get("dancer", "any")
            if target != "any" and int(target) != slot:
                continue
            now = self.clock()
            # `protect` (seconds): while this phrase plays, gestures for other sounds do not cut it
            if now < self.protected_until and m["sound"] != self.protected_sound:
                continue
            # `cooldown` (seconds): a long phrase is not restarted by the next gesture while it still plays
            if now - self.last_fired.get(m["sound"], -1e9) < m.get("cooldown", 0.0):
                continue
            self.last_fired[m["sound"]] = now
            if m.get("protect"):
                self.protected_sound, self.protected_until = m["sound"], now + m["protect"]
            self.fire(m)
            self.log.append((now, gesture, m["sound"], None))
            fired.append(m["sound"])
        if gesture in self.hits:
            fired += self.hit(slot, gesture)
        return fired

    def handle_individual(self, slot: int, gesture: str) -> list:
        """An individual motion plays its own sound at once. It does not open the gate, so it does not start the dance."""
        m = self.individual_by_gesture.get(gesture)
        if m is None:
            return []
        target = m.get("dancer", "any")
        if target != "any" and int(target) != slot:
            return []
        now = self.clock()
        if now - self.last_individual.get(m["sound"], -1e9) < m.get("cooldown", 0.3):
            return []
        self.last_individual[m["sound"]] = now
        self.fire(m)
        self.log.append((now, f"tek: {gesture}", m["sound"], None))
        return [m["sound"]]

    def tick(self, slot: int, active, margins=None) -> list:
        """Call every frame with the poses the dancer is holding (see `sustain`) and how clearly each is held."""
        self.last_active, self.last_margins = set(active), dict(margins or {})
        if not self.opened:
            return self.watch_opening(slot, active, margins)
        if not self.sustain:
            return []
        held = sorted(set(active) & self.hits)
        if not held:
            return []
        # only a pose that is itself two-armed counts as both arms: two one-arm poses held at once are not a double
        arms = set().union(*(self.arms_of(g) for g in held if g in self.two_armed))
        return self.fire_on_beat(slot, arms, f"{held[0]} (tutma)")

    def motion(self, moving: bool) -> list:
        """Call every frame: while something in view moves, the line goes on, one sound per beat."""
        return self.fire_on_beat(None, set(), "hareket") if self.use_motion and moving and self.opened else []

    def update(self) -> list:
        """Call every loop: stops the senkron after its last beat, closes the `group` window of the beat just played,
        and starts a due double."""
        self.watch_end()
        now = self.clock()
        p = self.pending
        if p is not None and now - p["t0"] >= self.group:
            self.pending = None
            if len(p["arms"]) == 2:                         # both arms: the double's second beat is next
                m = self.double_sounds[p["bar_beat"]]
                self.claimed = (p["beat"], p["beat"] + int(m.get("span", 2)) - 1)
                self.tail = {"slot": p["slot"], "m": m, "label": p["label"] + " (iki kol)",
                             "beat": p["beat"] + 1, "bar_beat": (p["bar_beat"] + 1) % 4}
        t = self.tail
        if t is None:
            return []
        if now < self.protected_until:                      # a phrase started meanwhile
            self.tail = None
            return []
        ahead = self.engine.seconds_to_beat(t["beat"])
        if ahead > self.lead:                               # start it just before its beat, so a phrase can still win
            if ahead > 2.0:                                 # the loop wrapped under it
                self.tail = None
            return []
        self.tail = None
        return self.play(t["slot"], t["label"], t["m"], t["beat"], t["bar_beat"],
                         self.engine.beat_landing(t["beat"], self.default_quantize), tail=True)

    def hit(self, slot, gesture: str) -> list:
        """A hit plays the sound of the beat it lands on (see the module docstring)."""
        return self.fire_on_beat(slot, self.arms_of(gesture), gesture)

    def fire_on_beat(self, slot, arms: set, label: str, lookahead=None) -> list:
        """`arms` are the arms the hit used (none known for movement in view), `label` is what the log shows.
        `lookahead` replaces the usual one (0 = the beat in progress, whatever the phase)."""
        if not self.bar_sounds:
            return []
        if self.pending is not None:                        # the beat just played: these arms count for it
            self.pending["arms"] |= arms
            return []
        now = self.clock()
        if now < self.protected_until:                      # a phrase is playing
            return []
        beat, bar_beat, target = self.engine.beat_target(self.lookahead if lookahead is None else lookahead,
                                                         self.default_quantize)
        if self.is_past_the_end(beat):                      # that beat comes after the last sound
            return []
        m = self.bar_sounds.get(bar_beat)
        if m is None or self.is_claimed(beat) or now - self.last_beat_time < self.min_gap:
            return []
        fired = self.play(slot, label, m, beat, bar_beat, target)
        if fired and bar_beat in self.double_sounds and not self.is_past_the_end(beat + 1):   # one arm or both?
            self.pending = {"slot": slot, "t0": now, "beat": beat, "bar_beat": bar_beat,
                            "arms": set(arms), "label": label}
        return fired

    def play(self, slot, label: str, m: dict, beat: int, bar_beat: int, target: int, tail=False) -> list:
        """`tail`: the beat before already played the plain sound, so only the rest of `m` plays, from `beat`."""
        dancer = m.get("dancer", "any")
        if dancer != "any" and slot is not None and int(dancer) != slot:
            return []
        now = self.clock()
        first = beat - 1 if tail else beat
        span = int(m.get("span", 2 if tail else 1))         # a double covers its beat and the next
        self.claimed, self.last_beat_time = (first, first + span - 1), now
        self.last_fired[m["sound"]] = now
        if m.get("protect"):
            self.protected_sound, self.protected_until = m["sound"], now + m["protect"]
        self.fire(m, at=target, skip_beats=1 if tail else 0)
        self.log.append((now, label, m["sound"], bar_beat + 1))
        return [m["sound"]]

    def fire(self, m: dict, at=None, skip_beats=0):
        self.engine.trigger(m["sound"], m.get("quantize", self.default_quantize), m.get("gain", 1.0),
                            at=at, skip_beats=skip_beats)

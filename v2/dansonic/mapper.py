"""Turns motion events into sounds. Every sound lists the motions that play it:

    ab:
      motions: [forearm_up, hand_to_head]

A motion plays the sound it is listed under, once, when it starts (poses) or happens (swipes, clap).
Optional per sound:
  cooldown  seconds before the sound can play again (default: `default_cooldown`)
  protect   seconds during which the moves of other sounds do not cut it (for the long phrase)
  quantize, gain, dancer
  restart_loop  the sound starts at once and the loop jumps to its first beat, so both are in time
"""
import time

from . import motions as M


def resolve(sounds: dict) -> tuple:
    """Config names -> concrete motions. Returns ({motion: sound}, [problems])."""
    by_motion, problems = {}, []
    for sound, cfg in sounds.items():
        listed = (cfg or {}).get("motions") or []
        if not listed:
            problems.append(f"'{sound}' icin hareket yazilmamis (sounds > {sound} > motions).")
        for name in listed:
            concrete = M.expand(name)
            if not concrete:
                problems.append(f"Bilinmeyen hareket '{name}' (ses: {sound}). python run.py --motions listeyi gosterir; "
                                f"yoksa once kaydedin: python run.py --record {name}")
            for m in concrete:
                if m in by_motion and by_motion[m] != sound:
                    problems.append(f"'{m}' hem '{by_motion[m]}' hem '{sound}' sesine yazilmis; bir hareket tek sesi calar.")
                by_motion.setdefault(m, sound)
    return by_motion, problems


class SoundMapper:
    def __init__(self, engine, sounds: dict, default_quantize: int, default_cooldown: float = 0.2,
                 clock=time.monotonic):
        self.engine = engine
        self.sounds = {k: (v or {}) for k, v in sounds.items()}
        self.default_quantize = default_quantize
        self.default_cooldown = default_cooldown
        self.clock = clock
        self.by_motion, _ = resolve(self.sounds)
        self.last_fired = {}            # sound -> time it last played
        self.protected_sound = None
        self.protected_until = -1e9
        self.log = []                   # (time, motion, sound)

    def handle(self, slot: int, motion: str, kind: str) -> list:
        """Returns the names of the sounds that were triggered."""
        if kind not in ("start", "hit"):
            return []
        sound = self.by_motion.get(motion)
        if sound is None:
            return []
        cfg = self.sounds[sound]
        dancer = cfg.get("dancer", "any")
        if dancer != "any" and int(dancer) != slot:
            return []
        now = self.clock()
        if now < self.protected_until and sound != self.protected_sound:
            return []
        if now - self.last_fired.get(sound, -1e9) < cfg.get("cooldown", self.default_cooldown):
            return []
        self.play(sound, motion, now)
        return [sound]

    def play(self, sound: str, motion: str, now=None):
        cfg = self.sounds[sound]
        now = self.clock() if now is None else now
        self.last_fired[sound] = now
        if cfg.get("protect"):
            self.protected_sound, self.protected_until = sound, now + cfg["protect"]
        self.engine.trigger(sound, cfg.get("quantize", self.default_quantize), cfg.get("gain", 1.0), cfg.get("restart_loop", False))
        self.log.append((now, motion, sound))

    def fire(self, sound: str):
        """Plays a sound by hand (the number keys)."""
        self.play(sound, "tus")

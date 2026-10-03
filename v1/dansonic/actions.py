"""Turns gesture events into sound triggers according to the config mapping."""


class ActionMapper:
    def __init__(self, engine, mappings: list, default_quantize: int):
        self.engine = engine
        self.default_quantize = default_quantize
        self.by_gesture = {}
        for m in mappings:
            for gesture in m["gestures"]:
                self.by_gesture.setdefault(gesture, []).append(m)

    def handle(self, slot: int, gesture: str, kind: str) -> list:
        """Returns the names of the sounds that were triggered."""
        if kind not in ("start", "hit"):
            return []
        fired = []
        for m in self.by_gesture.get(gesture, []):
            target = m.get("dancer", "any")
            if target != "any" and int(target) != slot:
                continue
            self.fire(m)
            fired.append(m["sound"])
        return fired

    def fire(self, m: dict):
        self.engine.trigger(m["sound"], m.get("quantize", self.default_quantize), m.get("gain", 1.0))

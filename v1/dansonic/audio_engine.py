"""Low-latency mixer: one looping backing track plus gesture-triggered one-shots.

The backing loop is held in memory as int16 stereo. The main thread only
mutates small pieces of state under a lock; the audio callback renders blocks.
"""
import threading

import numpy as np
import sounddevice as sd

from .song import BeatGrid

INT16_SCALE = 1.0 / 32768.0


class AudioEngine:
    def __init__(self, loop_audio: np.ndarray, sr: int, grid: BeatGrid, blocksize: int = 256,
                 device=None, master_gain: float = 0.9, loop_gain: float = 0.8,
                 choke: bool = True, choke_ms: float = 8.0):
        self.loop_audio = loop_audio
        self.length = len(loop_audio)
        self.sr = sr
        self.grid = grid
        self.blocksize = blocksize
        self.master_gain = master_gain
        self.loop_gain = loop_gain
        self.choke = choke
        self.choke_frames = max(1, int(sr * choke_ms / 1000.0))

        self.lock = threading.Lock()
        self.pos = 0
        self.playing = False
        self.quantize_enabled = True
        self.samples = {}
        self.sample_gains = {}
        # each voice: dict(data, wait (frames until it starts), cursor, gain, fade (remaining choke frames or -1))
        self.voices = []
        self.peak = 0.0
        self.last_trigger = {}          # sample name -> absolute frame counter of its start
        self.clock = 0                  # monotonically increasing frame counter (never wraps)

        self.stream = sd.OutputStream(samplerate=sr, channels=2, dtype="float32",
                                      blocksize=blocksize, latency="low",
                                      device=device, callback=self._callback)

    # ---- transport ---------------------------------------------------------
    def start(self):
        self.stream.start()

    def close(self):
        self.stream.stop()
        self.stream.close()

    def play(self):
        with self.lock:
            self.playing = True

    def toggle(self):
        with self.lock:
            self.playing = not self.playing

    def seek(self, seconds: float):
        with self.lock:
            self.pos = int(seconds * self.sr) % self.length
            self.voices.clear()

    def position(self) -> float:
        return self.pos / self.sr

    # ---- triggers ------------------------------------------------------------
    def trigger(self, name: str, quantize: int = 0, gain: float = 1.0):
        """Schedules a one-shot at the next grid point (quantize per beat, 0 = now)."""
        data = self.samples.get(name)
        if data is None:
            return
        with self.lock:
            q = quantize if self.quantize_enabled else 0
            target = self.grid.next_grid_frame(self.pos, q)
            wait = max(0, target - self.pos)
            if self.choke:
                for v in self.voices:
                    if v["fade"] < 0:
                        v["stop_in"] = wait
            self.voices.append(dict(data=data, wait=wait, cursor=0, fade=-1, stop_in=-1,
                                    gain=gain * self.sample_gains.get(name, 1.0)))
            self.last_trigger[name] = self.clock + wait

    # ---- rendering -------------------------------------------------------------
    def _render_voice(self, v, out, frames):
        off = 0
        if v["wait"] > 0:
            if v["wait"] >= frames:
                v["wait"] -= frames
                return
            off, v["wait"] = v["wait"], 0
        n = min(frames - off, len(v["data"]) - v["cursor"])
        if n <= 0:
            return
        cursor = v["cursor"]
        v["cursor"] = cursor + n
        env = np.full(n, v["gain"], dtype=np.float32)
        if v["stop_in"] >= 0 and v["fade"] < 0:
            # choke starts stop_in frames from the top of this block
            rel = v["stop_in"] - off
            if rel < n:
                v["fade"] = self.choke_frames
                start = max(0, rel)
                self._apply_fade(v, env, start)
            else:
                v["stop_in"] -= frames
        elif v["fade"] >= 0:
            self._apply_fade(v, env, 0)
        out[off:off + n] += v["data"][cursor:cursor + n] * env[:, None]

    def _apply_fade(self, v, env, start):
        n = len(env) - start
        ramp = (v["fade"] - np.arange(n, dtype=np.float32)) / self.choke_frames
        env[start:] *= np.clip(ramp, 0.0, 1.0)
        v["fade"] = max(0, v["fade"] - n)
        if v["fade"] == 0:
            v["cursor"] = len(v["data"])    # finished after this block

    def _callback(self, outdata, frames, time_info, status):
        out = np.zeros((frames, 2), dtype=np.float32)
        with self.lock:
            playing = self.playing
            pos = self.pos
            if playing:
                self.pos = (pos + frames) % self.length
            voices = list(self.voices)

        if playing:
            end = pos + frames
            if end <= self.length:
                chunk = self.loop_audio[pos:end]
            else:
                chunk = np.concatenate([self.loop_audio[pos:], self.loop_audio[:end - self.length]])
            out += chunk.astype(np.float32) * (INT16_SCALE * self.loop_gain)
        for v in voices:
            self._render_voice(v, out, frames)
        with self.lock:
            self.voices = [v for v in self.voices if v["cursor"] < len(v["data"])]
            self.clock += frames

        out *= self.master_gain
        np.clip(out, -1.0, 1.0, out=out)
        self.peak = float(np.abs(out).max())
        outdata[:] = out

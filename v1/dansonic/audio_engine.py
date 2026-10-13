"""Low-latency mixer: one looping backing track plus gesture-triggered one-shots.

The backing loop is held in memory as int16 stereo. The main thread only
mutates small pieces of state under a lock; the audio callback renders blocks.
"""
import math
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
        self.trigger_log = None         # set to a list to record (sample name, start frame in the loop)

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
    def beat_target(self, lookahead: float = 0.25, quantize: int = 4) -> tuple:
        """The beat a hit made right now belongs to: (beat index, beat of the bar 0-3, start frame).

        A hit in the last `lookahead` of a beat counts for the next beat and waits for it;
        any other hit counts for the current beat and starts on the next grid point."""
        with self.lock:
            pos, grid = self.pos, self.grid
            phase = (pos - grid.offset_frames) / grid.beat_frames
            beat = math.floor(phase + lookahead)
            if self.quantize_enabled and beat > math.floor(phase):
                target = int(round(grid.offset_frames + beat * grid.beat_frames))
            else:
                target = grid.next_grid_frame(pos, quantize if self.quantize_enabled else 0)
            return beat, (beat - grid.downbeat_index) % 4, target

    def beat_landing(self, beat: int, quantize: int = 4) -> int:
        """Start frame for a sound of `beat` decided a moment after the hit: on the beat if it is
        still ahead, otherwise on the next grid point."""
        with self.lock:
            pos, grid = self.pos, self.grid
            beat_frame = int(round(grid.offset_frames + beat * grid.beat_frames))
            if self.quantize_enabled and beat_frame >= pos:
                return beat_frame
            return grid.next_grid_frame(pos, quantize if self.quantize_enabled else 0)

    def current_beat(self) -> int:
        """Index of the beat in progress, counted from the loop's first beat."""
        with self.lock:
            return self.grid.beat_index(self.pos)

    @property
    def loop_beats(self) -> int:
        """How many beats the loop has: beat numbers start over after this many."""
        return max(1, round(self.length / self.grid.beat_frames))

    def seconds_to_beat(self, beat: int) -> float:
        """Seconds until `beat` starts, negative once it has passed."""
        with self.lock:
            return (self.grid.offset_frames + beat * self.grid.beat_frames - self.pos) / self.sr

    def trigger(self, name: str, quantize: int = 0, gain: float = 1.0, at=None, skip_beats: float = 0.0):
        """Schedules a one-shot at the next grid point (quantize per beat, 0 = now), or at frame `at`.
        With `skip_beats` it starts that many beats into the sound, for the second half of a double."""
        data = self.samples.get(name)
        if data is None:
            return
        if skip_beats:
            skip = int(round(skip_beats * self.grid.beat_frames))
            if skip >= len(data):
                return
            data = data[skip:].copy()
            ramp = min(len(data), int(0.003 * self.sr))      # a start part-way in must not click
            data[:ramp] *= np.linspace(0.0, 1.0, ramp, dtype=np.float32)[:, None]
        with self.lock:
            if at is not None:
                target = at
            else:
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
            if self.trigger_log is not None:
                self.trigger_log.append((name, self.pos + wait))

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

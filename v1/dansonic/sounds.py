"""Loading of the backing loop and the one-shot sound files."""
from pathlib import Path

import numpy as np
import soundfile as sf


def _read_stereo(path, sr: int) -> np.ndarray:
    data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
    if file_sr != sr:
        raise ValueError(f"{path}: ornekleme hizi {file_sr}, beklenen {sr}")
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    return np.ascontiguousarray(data[:, :2])


def load_loop(path, sr: int, beat_frames: float) -> np.ndarray:
    """Backing loop as int16, cut to a whole number of beats so it wraps on the grid."""
    data = _read_stereo(path, sr)
    beats = int(len(data) / beat_frames)
    data = data[: int(round(beats * beat_frames))]
    return (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)


def load_sound(path, sr: int, trim_threshold: float = 0.02, normalize: bool = True) -> np.ndarray:
    """One-shot with leading silence removed, so the hit lands exactly on its trigger."""
    data = _read_stereo(path, sr)
    level = np.abs(data).max(axis=1)
    peak = float(level.max())
    loud = np.where(level > trim_threshold * max(peak, 1e-6))[0]
    if len(loud):
        data = data[max(0, loud[0] - int(0.002 * sr)):]
    if normalize and peak > 0:
        data = data * (0.9 / peak)
    fade = min(len(data), int(0.005 * sr))
    data[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
    return np.ascontiguousarray(data, dtype=np.float32)


def load_sounds(directory, names: list, sr: int) -> dict:
    sounds = {}
    for name in names:
        path = Path(directory) / f"{name}.mp3"
        if not path.exists():
            path = path.with_suffix(".wav")
        if not path.exists():
            raise FileNotFoundError(f"Ses dosyasi yok: {directory}/{name}.mp3")
        sounds[name] = load_sound(path, sr)
    return sounds

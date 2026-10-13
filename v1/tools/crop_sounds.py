"""Cuts the one-shot sounds listed in sounds/video/cuts.json out of the vocal track.

The cut times are positions in the full-speed vocal stem the dance video was
made with (Dansonic_blablabla_vocals.mp3). Every cut starts on a syllable
attack and ends just before the next one, so each file is a whole number of
beats long at the original tempo (132.9 bpm) and lines up with drums-loop.mp3.

  python tools/crop_sounds.py --vocals ~/Downloads/Dansonic_blablabla_vocals.mp3
"""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sounds" / "video"
SR = 44100
FADE_IN, FADE_OUT = 0.003, 0.006


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vocals", required=True, help="path to the full vocal track (mp3 or wav, 44.1 kHz)")
    parser.add_argument("--cuts", default=str(OUT / "cuts.json"))
    args = parser.parse_args()

    data, sr = sf.read(args.vocals, dtype="float32", always_2d=True)
    if sr != SR:
        raise SystemExit(f"{args.vocals}: sample rate {sr}, expected {SR}")
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    cuts = json.loads(Path(args.cuts).read_text())
    for cut in cuts["cuts"]:
        clip = np.array(data[int(cut["start"] * SR):int(cut["end"] * SR), :2])
        clip *= 0.89 / max(float(np.abs(clip).max()), 1e-6)
        n_in, n_out = int(FADE_IN * SR), int(FADE_OUT * SR)
        clip[:n_in] *= np.linspace(0, 1, n_in, dtype=np.float32)[:, None]
        clip[-n_out:] *= np.linspace(1, 0, n_out, dtype=np.float32)[:, None]
        path = OUT / f"{cut['name']}.wav"
        sf.write(str(path), clip, SR, subtype="PCM_16")
        print(f"{path.name:28s} {len(clip) / SR:.3f}s  from {cut['start']:.3f}s")


if __name__ == "__main__":
    main()

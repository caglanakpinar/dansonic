"""Makes a test clip for the individual motions: the lead dancer raises her right hand (dansonic.mp4, 4.0-5.6 s),
then the whole video plays from its start. Before the dance opens that hand-up plays ab on its own; later, inside
the senkron, the same raised hands are only beat hits.

  python tools/make_handup_clip.py ~/Downloads/dansonic.mp4 handup_then_dance.mp4
  python run.py --source handup_then_dance.mp4
"""
import sys

import cv2

CLIP = (4.0, 5.6)        # seconds of dansonic.mp4: the right hand goes up at 4.2 s and down at 5.3 s


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src = cv2.VideoCapture(sys.argv[1])
    if not src.isOpened():
        sys.exit(f"Video acilamadi: {sys.argv[1]}")
    fps = src.get(cv2.CAP_PROP_FPS) or 30.0
    size = (int(src.get(cv2.CAP_PROP_FRAME_WIDTH)), int(src.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    frames = []
    while True:
        ok, frame = src.read()
        if not ok:
            break
        frames.append(frame)
    if len(frames) < int(CLIP[1] * fps):
        sys.exit("Video bu klip icin cok kisa: dansonic.mp4 beklenir.")
    out = cv2.VideoWriter(sys.argv[2], cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for frame in frames[int(CLIP[0] * fps):int(CLIP[1] * fps)] + frames:
        out.write(frame)
    out.release()
    print(f"Yazildi: {sys.argv[2]} ({CLIP[1] - CLIP[0]:.1f} sn el kaldirma + {len(frames) / fps:.1f} sn dans)")


if __name__ == "__main__":
    main()

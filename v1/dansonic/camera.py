"""Threaded frame grabber that always exposes the newest frame."""
import threading
import time
from pathlib import Path

import cv2


class Camera:
    def __init__(self, source=0, width=1280, height=720, fps=30, speed=1.0, on_loop=None):
        self.is_file = isinstance(source, str)
        self.speed = speed                  # video files only: 1.1 plays 10% faster
        self.on_loop = on_loop              # video files only: called each time the video starts over
        self._restart = threading.Event()
        self.generation = 0                 # video files: counts restarts and loops, so users can drop the frame before a jump
        if self.is_file:
            self.cap = cv2.VideoCapture(source)
        else:
            self.cap = cv2.VideoCapture(source, cv2.CAP_AVFOUNDATION)
        if not self.cap.isOpened():
            if not self.is_file:
                hint = (" macOS kamera izni gerekir: Sistem Ayarlari > Gizlilik ve Guvenlik > Kamera "
                        "altinda kullandiginiz terminal uygulamasini acin veya komutu Terminal.app'ten "
                        "calistirin. Kamerasiz deneme icin --no-camera.")
            elif not Path(source).exists():
                hint = " Dosya bulunamadi."
            else:
                hint = (" Dosya video olarak okunamadi. --source goruntulu bir video ister (mp4, mov); "
                        "ses dosyasi (mp3, wav) olmaz. Sesleri denemek icin --no-camera kullanin.")
            raise RuntimeError(f"Kamera/video acilamadi: {source}.{hint}")
        if not self.is_file:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.file_fps = self.cap.get(cv2.CAP_PROP_FPS) or fps
        self.frame = None
        self.frame_id = 0
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def restart(self):
        """Video files: start again from the first frame now."""
        self._restart.set()

    def _loop(self):
        period = 1.0 / (self.file_fps * self.speed) if self.is_file else 0.0
        due = time.monotonic()
        while self.running:
            if self._restart.is_set():
                self._restart.clear()
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.generation += 1
                due = time.monotonic()
            ok, frame = self.cap.read()
            if not ok:
                if self.is_file:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.generation += 1
                    if self.on_loop:
                        self.on_loop()
                    continue
                time.sleep(0.01)
                continue
            with self.lock:
                self.frame = frame
                self.frame_id += 1
            if period:
                due += period
                delay = due - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    due = time.monotonic()      # fell behind: do not burst to catch up

    def latest(self):
        with self.lock:
            return self.frame, self.frame_id

    def close(self):
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()

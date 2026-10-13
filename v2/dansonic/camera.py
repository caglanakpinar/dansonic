"""Threaded frame grabber that always exposes the newest frame."""
import threading
import time
from pathlib import Path

import cv2


class Camera:
    def __init__(self, source=0, width=1280, height=720, fps=30):
        self.is_file = isinstance(source, str)
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
        self.generation = 0                 # video files: counts loops, so users can drop state across the jump
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        period = 1.0 / self.file_fps if self.is_file else 0.0
        due = time.monotonic()
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                if self.is_file:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.generation += 1
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

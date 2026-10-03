"""Threaded frame grabber that always exposes the newest frame."""
import threading
import time

import cv2


class Camera:
    def __init__(self, source=0, width=1280, height=720, fps=30):
        self.is_file = isinstance(source, str)
        if self.is_file:
            self.cap = cv2.VideoCapture(source)
        else:
            self.cap = cv2.VideoCapture(source, cv2.CAP_AVFOUNDATION)
        if not self.cap.isOpened():
            hint = ("" if self.is_file else
                    " macOS kamera izni gerekir: Sistem Ayarlari > Gizlilik ve Guvenlik > Kamera "
                    "altinda kullandiginiz terminal uygulamasini acin veya komutu Terminal.app'ten "
                    "calistirin. Kamerasiz deneme icin --no-camera.")
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

    def _loop(self):
        period = 1.0 / self.file_fps if self.is_file else 0.0
        while self.running:
            t0 = time.time()
            ok, frame = self.cap.read()
            if not ok:
                if self.is_file:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.01)
                continue
            with self.lock:
                self.frame = frame
                self.frame_id += 1
            if period:
                time.sleep(max(0.0, period - (time.time() - t0)))

    def latest(self):
        with self.lock:
            return self.frame, self.frame_id

    def close(self):
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()

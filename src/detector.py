# detector.py
import time
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
from playsound3 import playsound


@dataclass
class RuntimeParams:
    threshold: float
    cooldown: float
    sleep_time: float
    hit_sound: str


class Detector:
    def __init__(self, params: RuntimeParams, log_callback=None):
        self.params = params
        self.log_callback = log_callback or (lambda msg: None)

        self.stop_event = threading.Event()
        self.thread = None

        self._last_trigger = 0.0
        self._sound_thread = None
        self._sound_is_active = False
        self._lock = threading.Lock()

    def update_params(self, params: RuntimeParams):
        with self._lock:
            self.params = params

    def _get_params(self):
        with self._lock:
            return self.params

    def _on_hit(self, level: float):
        p = self._get_params()
        self.log_callback(f"HIT detected! level: {level}")

        try:
            if self._sound_is_active and self._sound_thread:
                self._sound_thread.stop()
        except Exception:
            pass

        try:
            self._sound_thread = playsound(p.hit_sound, block=False)
            self._sound_is_active = getattr(self._sound_thread, "is_alive", lambda: False)()
        except Exception as e:
            self.log_callback(f"Error playing sound: {e}")

    def _callback(self, indata, frames, time_info, status):
        if self.stop_event.is_set():
            return

        p = self._get_params()
        peak = float(np.max(np.abs(indata)))
        now = time.time()

        if peak > p.threshold and (now - self._last_trigger) > p.cooldown:
            self._last_trigger = now
            self._on_hit(peak)

    def _run(self):
        self.log_callback("Listening for chassis taps...")
        try:
            with sd.InputStream(
                channels=1,
                samplerate=44100,
                blocksize=1024,
                callback=self._callback,
            ):
                while not self.stop_event.is_set():
                    p = self._get_params()
                    self.stop_event.wait(timeout=max(0.01, p.sleep_time))
        except Exception as e:
            self.log_callback(f"Audio stream error: {e}")

    def start(self):
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        try:
            if self._sound_thread:
                self._sound_thread.stop()
        except Exception:
            pass
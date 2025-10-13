# modules/microphone.py
import numpy as np
import sounddevice as sd
from collections import deque
from PyQt6.QtWidgets import QLabel
from module_base import ModuleWindow

class Microphone(ModuleWindow):
    """Microphone input module; volume and mute handled by fader."""

    def __init__(self, mixer_callback, close_callback):
        # --- Audio state ---
        self.fs = 44100
        self.channels = 1           # mono input
        self.volume = -60.0         # dB, controlled by fader
        self.pan = 0.0
        self.muted = False
        self.running = True

        # Buffer to store incoming audio
        self.buffer = deque(maxlen=44100*5)  # 5 seconds buffer

        # Initialize base class (registers with mixer)
        super().__init__("Microphone", mixer_callback, close_callback)

        # --- UI ---
        self.content_layout.addWidget(QLabel("Microphone active"))

        # --- Start microphone input ---
        try:
            self.stream = sd.InputStream(
                samplerate=self.fs,
                channels=self.channels,
                callback=self.audio_callback,
                blocksize=1024
            )
            self.stream.start()
        except Exception as e:
            self.content_layout.addWidget(QLabel(f"Error: {e}"))

    # --- InputStream callback ---
    def audio_callback(self, indata, frames, time, status):
        """Called in audio thread; append incoming audio to buffer if not muted."""
        if status:
            print(f"[Microphone] InputStream status: {status}")
        if self.muted:
            return  # discard all incoming audio while muted

        samples = indata.copy()
        # Ensure stereo for mixer
        if self.channels == 1:
            samples = np.tile(samples, (1, 2))
        self.buffer.extend(samples)

    # --- Mixer interface ---
    def get_samples(self, frames: int):
        """Provide requested frames to mixer with volume and pan applied."""
        if not self.running:
            return np.zeros((frames, 2), dtype=np.float32)

        out = []
        for _ in range(frames):
            if self.buffer:
                out.append(self.buffer.popleft())
            else:
                out.append([0.0, 0.0])
        out = np.array(out, dtype=np.float32)

        # Apply fader volume (dB → linear)
        gain = 10 ** (self.volume / 20.0)
        left_gain = gain * (1 - max(0, self.pan))
        right_gain = gain * (1 - max(0, -self.pan))
        out[:, 0] *= left_gain
        out[:, 1] *= right_gain

        return out

    # --- Cleanup ---
    def closeEvent(self, event):
        """Stop microphone and notify mixer."""
        self.running = False
        if hasattr(self, "stream"):
            self.stream.stop()
            self.stream.close()
        super().closeEvent(event)

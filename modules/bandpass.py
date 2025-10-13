# modules/bandpass.py
import numpy as np
from audio_module import AudioModule

class Bandpass(AudioModule):
    """Simple one-pole bandpass filter"""
    def __init__(self, freq=1000.0, q=0.707, sample_rate=44100):
        super().__init__(has_input=True, has_output=True)
        self.sample_rate = sample_rate
        self.freq = freq
        self.q = q
        self.prev = np.zeros(2)
        self.prev_out = np.zeros(2)

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)
        x = self.input_node.send(frames)
        # Simple one-pole bandpass approximation
        w0 = 2 * np.pi * self.freq / self.sample_rate
        alpha = np.sin(w0) / (2 * self.q)
        a0 = 1 + alpha
        b0 = alpha / a0
        y = b0 * x + (1 - b0) * self.prev_out
        self.prev_out = y[-1, :]
        return y

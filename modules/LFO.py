# modules/lfo.py
import numpy as np
from audio_module import AudioModule
from nodes import OutputNode

class LFO(AudioModule):
    """Simple sine LFO source"""
    def __init__(self, frequency=1.0, amplitude=0.5, sample_rate=44100):
        super().__init__(has_input=False, has_output=True)
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.frequency = frequency
        self.amplitude = amplitude
        self.output_node = OutputNode(self)

    def generate(self, frames: int) -> np.ndarray:
        t = np.arange(frames) / self.sample_rate
        wave = self.amplitude * np.sin(2 * np.pi * self.frequency * t + self.phase)
        self.phase += 2 * np.pi * self.frequency * frames / self.sample_rate
        return np.column_stack((wave, wave)).astype(np.float32)

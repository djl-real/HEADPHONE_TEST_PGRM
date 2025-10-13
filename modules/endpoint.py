# modules/endpoint.py
import numpy as np
from audio_module import AudioModule

class EndpointModule(AudioModule):
    """Final output module with volume fader"""
    def __init__(self, volume_db=0.0):
        super().__init__(has_input=True, has_output=False)
        self.volume_db = volume_db

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)
        data = self.input_node.receive(frames)
        gain = 10 ** (self.volume_db / 20.0)
        return data * gain

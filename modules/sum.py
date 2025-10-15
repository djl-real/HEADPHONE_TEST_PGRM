# modules/sum.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from audio_module import AudioModule
from nodes import OutputNode


class Sum(AudioModule):
    """Sum up to four input signals into one output."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=4, output_count=1)
        self.sample_rate = sample_rate

    def generate(self, frames: int) -> np.ndarray:
        # Start with silence
        out = np.zeros((frames, 2), dtype=np.float32)

        # Add all available inputs
        for i in range(4):
            if self.input_nodes[i]:
                inp = self.input_nodes[i].receive(frames)
                out += inp

        # Normalize if needed to prevent clipping (optional)
        # out = np.clip(out, -1.0, 1.0)

        return out

    def get_ui(self) -> QWidget:
        """Simple label showing that this module sums 4 inputs."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel("4:1")
        layout.addWidget(label)

        return widget

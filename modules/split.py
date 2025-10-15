# modules/split.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from audio_module import AudioModule
from nodes import OutputNode


class Split(AudioModule):
    """Split one input signal into multiple identical outputs, with buffered refresh control."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=1, output_count=2)
        self.sample_rate = sample_rate
        self.buffer = None
        self.generate_count = 0  # Counts how many times generate() was called since last refresh

    def generate(self, frames: int) -> np.ndarray:
        """Return a copy of the buffered input, refreshing it every n generates."""
        connected_outputs = sum(1 for out in self.output_nodes if out.connection is not None)
        n = connected_outputs if connected_outputs > 0 else 1  # Avoid divide-by-zero

        # Refresh buffer every n generate calls
        if self.buffer is None or self.generate_count % n == 0:
            if self.input_nodes[0]:
                self.buffer = self.input_nodes[0].receive(frames)
            else:
                self.buffer = np.zeros((frames, 2), dtype=np.float32)
            self.generate_count = 0  # Reset after refresh

        self.generate_count += 1

        # Return a copy of the buffer to avoid shared references
        return np.copy(self.buffer)

    def get_ui(self) -> QWidget:
        """Simple label indicating split behavior."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel("1:2")
        layout.addWidget(label)

        return widget

# modules/crossfade.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import OutputNode


class Crossfade(AudioModule):
    """Crossfade between two input signals with a slider (0 = input 1, 1 = input 2)."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=2, output_count=1)
        self.sample_rate = sample_rate
        self.crossfade = 0.5  # 0 = full input 1, 1 = full input 2

    def generate(self, frames: int) -> np.ndarray:
        # Receive inputs
        x1 = self.input_nodes[0].receive(frames) if self.input_nodes[0] else np.zeros((frames, 2))
        x2 = self.input_nodes[1].receive(frames) if self.input_nodes[1] else np.zeros((frames, 2))

        # Linear crossfade
        out = (1.0 - self.crossfade) * x1 + self.crossfade * x2
        return out.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return a slider to control crossfade amount."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel(f"Crossfade: {self.crossfade:.2f}")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(1000)
        slider.setValue(int(self.crossfade * 1000))
        layout.addWidget(slider)

        def on_slider(val):
            self.crossfade = val / 1000.0
            label.setText(f"Crossfade: {self.crossfade:.2f}")

        slider.valueChanged.connect(on_slider)

        from PyQt6.QtWidgets import QPushButton
        flip_button = QPushButton("Flip")
        layout.addWidget(flip_button)

        def on_flip():
            self.crossfade = 1.0 - self.crossfade
            slider.setValue(int(self.crossfade * 1000))

        flip_button.clicked.connect(on_flip)

        return widget
    
    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "sample_rate": self.sample_rate,
            "crossfade": self.crossfade,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.sample_rate = state.get("sample_rate", 44100)
        self.crossfade = state.get("crossfade", 0.5)
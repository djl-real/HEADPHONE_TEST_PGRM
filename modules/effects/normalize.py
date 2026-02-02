# modules/normalize.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import InputNode, OutputNode


class Normalize(AudioModule):
    """Normalizes audio to a target peak level."""

    def __init__(self, target=1.0):
        super().__init__(input_count=1, output_count=1)
        self.target = target  # Target peak level (0.0 to 1.0)

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        peak = np.max(np.abs(x))
        
        if peak > 0:
            y = x * (self.target / peak)
        else:
            y = x
        
        return y.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return a QWidget with a target level slider."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel(f"Target: {self.target:.2f}")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(int(self.target * 100))
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(25)
        layout.addWidget(slider)

        def on_target_change(val):
            self.target = val / 100.0
            label.setText(f"Target: {self.target:.2f}")

        slider.valueChanged.connect(on_target_change)
        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "target": self.target,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.target = state.get("target", 1.0)
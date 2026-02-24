# modules/pan.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule

class Pan(AudioModule):
    """Simple stereo panning module."""

    def __init__(self, pan=0.0):
        super().__init__(input_count=1, output_count=1)
        self.pan = pan  # -1.0 (full left) to 1.0 (full right)

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        left_gain = np.cos((self.pan + 1) * np.pi / 4)  # convert -1..1 to 0..pi/2
        right_gain = np.sin((self.pan + 1) * np.pi / 4)
        y = np.zeros_like(x)
        y[:, 0] = x[:, 0] * left_gain
        y[:, 1] = x[:, 1] * right_gain
        return y.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return a QWidget with a pan slider."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel(f"Pan: {self.pan:.2f}")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(-100)
        slider.setMaximum(100)
        slider.setValue(int(self.pan * 100))
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(25)
        layout.addWidget(slider)

        def on_pan_change(val):
            self.pan = val / 100.0
            label.setText(f"Pan: {self.pan:.2f}")

        slider.valueChanged.connect(on_pan_change)
        return widget
    
    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()  # include input/output node info
        data.update({
            "pan": self.pan,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.pan = state.get("pan", 0.0)

# modules/const.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QDoubleSpinBox
from PyQt6.QtCore import Qt
from audio_module import AudioModule


class Const(AudioModule):
    """Constant value generator that outputs a float."""

    def __init__(self, value=0.0):
        super().__init__(
            input_count=0,
            output_count=1,
            output_types=["control"],
            output_colors=["#FFFF00"],
            output_positions=["bottom"],
            output_labels=["Float"]
        )
        self.value = value

    def generate(self, frames: int) -> float:
        """Return the constant value."""
        return self.value

    def get_ui(self) -> QWidget:
        """Return a QWidget with a number input."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel("Constant Value:")
        layout.addWidget(label)

        # Value display label
        value_label = QLabel(f"{self.value:.3f}")
        value_label.setStyleSheet("color: #FFFF00; font-size: 14px; font-weight: bold;")
        layout.addWidget(value_label)

        # Double spin box for precise input
        spin_box = QDoubleSpinBox()
        spin_box.setMinimum(-1000.0)
        spin_box.setMaximum(1000.0)
        spin_box.setDecimals(3)
        spin_box.setSingleStep(0.1)
        spin_box.setValue(self.value)
        layout.addWidget(spin_box)

        def on_value_change(val):
            self.value = val
            value_label.setText(f"{self.value:.3f}")

        spin_box.valueChanged.connect(on_value_change)

        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "value": self.value,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.value = state.get("value", 0.0)
# modules/bitcrusher.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule


class Bitcrusher(AudioModule):
    """Bitcrusher effect: reduces bit depth and sample rate for lo-fi distortion."""

    def __init__(self, bit_depth=8, sample_rate_reduction=8000, sample_rate=44100):
        super().__init__(input_count=1, output_count=1)
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        self.sample_rate_reduction = sample_rate_reduction
        self.prev_sample = np.zeros(2, dtype=np.float32)
        self.phase = 0.0

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        y = np.zeros_like(x)

        # --- Bit depth reduction ---
        levels = 2 ** self.bit_depth
        crushed = np.round(x * levels) / levels

        # --- Sample rate reduction (vectorized) ---
        step = max(1, int(self.sample_rate / self.sample_rate_reduction))
        start_phase = int(self.phase)
        indices = (np.arange(frames) + start_phase) // step

        # take first sample in each step
        unique_idx, first_indices = np.unique(indices, return_index=True)
        hold_samples = crushed[first_indices]

        # Clip indices to avoid out-of-bounds
        indices = np.clip(indices, 0, len(hold_samples) - 1)

        y = hold_samples[indices.astype(int)]

        # Save state
        self.prev_sample = y[-1]
        self.phase = (start_phase + frames) % step

        return y.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return QWidget with sliders for bit depth and sample rate reduction."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Bit depth slider ---
        bit_label = QLabel(f"Bit Depth: {self.bit_depth}")
        layout.addWidget(bit_label)

        bit_slider = QSlider(Qt.Orientation.Horizontal)
        bit_slider.setMinimum(1)
        bit_slider.setMaximum(16)
        bit_slider.setValue(self.bit_depth)
        bit_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        bit_slider.setTickInterval(1)
        layout.addWidget(bit_slider)

        def on_bit_change(val):
            self.bit_depth = val
            bit_label.setText(f"Bit Depth: {self.bit_depth}")

        bit_slider.valueChanged.connect(on_bit_change)

        # --- Sample rate reduction slider ---
        rate_label = QLabel(f"Downsample: {self.sample_rate_reduction} Hz")
        layout.addWidget(rate_label)

        rate_slider = QSlider(Qt.Orientation.Horizontal)
        rate_slider.setMinimum(500)
        rate_slider.setMaximum(self.sample_rate)
        rate_slider.setValue(self.sample_rate_reduction)
        rate_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        rate_slider.setTickInterval(4000)
        layout.addWidget(rate_slider)

        def on_rate_change(val):
            self.sample_rate_reduction = max(1, val)
            rate_label.setText(f"Downsample: {self.sample_rate_reduction} Hz")

        rate_slider.valueChanged.connect(on_rate_change)

        return widget

        # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "sample_rate": self.sample_rate,
            "bit_depth": self.bit_depth,
            "sample_rate_reduction": self.sample_rate_reduction,
            "prev_sample": self.prev_sample.tolist(),
            "phase": self.phase,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.sample_rate = state.get("sample_rate", 44100)
        self.bit_depth = state.get("bit_depth", 8)
        self.sample_rate_reduction = state.get("sample_rate_reduction", 8000)
        prev_sample = state.get("prev_sample", [0.0, 0.0])
        self.prev_sample = np.array(prev_sample, dtype=np.float32)
        self.phase = state.get("phase", 0.0)

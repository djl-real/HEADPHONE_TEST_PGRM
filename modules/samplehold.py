# modules/sample_hold_pitch.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import InputNode, OutputNode

class SampleHoldMod(AudioModule):
    """
    Sample & Hold Pitch Modulation
    Produces random pitch jumps at a fixed rate.
    """

    def __init__(self, rate_hz=2.0, depth=12.0, sample_rate=48000):
        super().__init__(input_count=1, output_count=1)
        self.rate_hz = rate_hz        # how often the pitch changes (Hz)
        self.depth = depth            # max pitch modulation in semitones (+/-)
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.current_pitch_shift = 1.0  # current playback rate multiplier

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        if x is None or len(x) == 0:
            return np.zeros((frames, 2), dtype=np.float32)

        output = np.zeros_like(x)
        input_len = len(x)

        for i in range(frames):
            # Update phase and pick a new random pitch every cycle
            self.phase += self.rate_hz / self.sample_rate
            if self.phase >= 1.0:
                self.phase -= 1.0
                semitone_offset = (np.random.rand() - 0.5) * self.depth
                self.current_pitch_shift = 2 ** (semitone_offset / 12.0)

            # Compute source index with fractional part
            src_idx = i * self.current_pitch_shift

            # Clamp src_idx to last sample
            if src_idx >= input_len - 1:
                src_idx = input_len - 1.001  # slightly less than last index to allow interpolation

            idx0 = int(np.floor(src_idx))
            idx1 = idx0 + 1
            frac = src_idx - idx0

            # Linear interpolation
            output[i] = x[idx0] * (1 - frac) + x[idx1] * frac

        return output.astype(np.float32)



    def get_ui(self) -> QWidget:
        """Return a QWidget for rate and depth sliders."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label_rate = QLabel(f"Rate: {self.rate_hz:.2f} Hz")
        layout.addWidget(label_rate)
        slider_rate = QSlider(Qt.Orientation.Horizontal)
        slider_rate.setMinimum(1)
        slider_rate.setMaximum(200)
        slider_rate.setValue(int(self.rate_hz * 10))
        layout.addWidget(slider_rate)

        label_depth = QLabel(f"Depth: {self.depth:.1f} semitones")
        layout.addWidget(label_depth)
        slider_depth = QSlider(Qt.Orientation.Horizontal)
        slider_depth.setMinimum(0)
        slider_depth.setMaximum(240)
        slider_depth.setValue(int(self.depth * 10))
        layout.addWidget(slider_depth)

        def on_rate_change(val):
            self.rate_hz = val / 10.0
            label_rate.setText(f"Rate: {self.rate_hz:.2f} Hz")

        def on_depth_change(val):
            self.depth = val / 10.0
            label_depth.setText(f"Depth: {self.depth:.1f} semitones")

        slider_rate.valueChanged.connect(on_rate_change)
        slider_depth.valueChanged.connect(on_depth_change)

        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "rate_hz": self.rate_hz,
            "depth": self.depth,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.rate_hz = state.get("rate_hz", 2.0)
        self.depth = state.get("depth", 12.0)

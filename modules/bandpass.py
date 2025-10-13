# modules/bandpass.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import OutputNode


class Bandpass(AudioModule):
    """Simple one-pole bandpass filter with adjustable low and high cutoff frequencies."""

    def __init__(self, sample_rate=44100, lp_freq=20000.0, hp_freq=20.0):
        super().__init__(has_input=True, has_output=True)
        self.sample_rate = sample_rate
        self.lp_freq = lp_freq
        self.hp_freq = hp_freq
        self.prev_x = np.zeros(2)  # previous input for HP
        self.prev_hp = np.zeros(2) # previous HP output
        self.prev_lp = np.zeros(2) # previous LP output
        self.output_node = OutputNode(self)

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        y = np.zeros_like(x)

        # Precompute stable filter coefficients
        hp_alpha = self.hp_freq / (self.hp_freq + self.sample_rate / (2 * np.pi))
        lp_alpha = self.sample_rate / (2 * np.pi) / (self.sample_rate / (2 * np.pi) + self.lp_freq)

        for n in range(frames):
            # High-pass (one-pole)
            hp_out = hp_alpha * (self.prev_hp + x[n] - self.prev_x)
            self.prev_x = x[n]
            self.prev_hp = hp_out

            # Low-pass (one-pole)
            lp_out = lp_alpha * hp_out + (1 - lp_alpha) * self.prev_lp
            self.prev_lp = lp_out

            y[n] = lp_out

        return y.astype(np.float32)


    def get_ui(self) -> QWidget:
        """Return QWidget with low-pass and high-pass sliders."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Low-pass slider
        lp_label = QLabel(f"Low-pass Frequency: {self.lp_freq:.0f} Hz")
        layout.addWidget(lp_label)

        lp_slider = QSlider(Qt.Orientation.Horizontal)
        lp_slider.setMinimum(20)
        lp_slider.setMaximum(20000)
        lp_slider.setValue(int(self.lp_freq))
        layout.addWidget(lp_slider)

        def on_lp_change(val):
            self.lp_freq = float(val)
            lp_label.setText(f"Low-pass Frequency: {self.lp_freq:.0f} Hz")
        lp_slider.valueChanged.connect(on_lp_change)

        # High-pass slider
        hp_label = QLabel(f"High-pass Frequency: {self.hp_freq:.0f} Hz")
        layout.addWidget(hp_label)

        hp_slider = QSlider(Qt.Orientation.Horizontal)
        hp_slider.setMinimum(20)
        hp_slider.setMaximum(20000)
        hp_slider.setValue(int(self.hp_freq))
        layout.addWidget(hp_slider)

        def on_hp_change(val):
            self.hp_freq = float(val)
            hp_label.setText(f"High-pass Frequency: {self.hp_freq:.0f} Hz")
        hp_slider.valueChanged.connect(on_hp_change)

        return widget

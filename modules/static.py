# modules/static.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import OutputNode


class Static(AudioModule):
    """White noise generator module with amplitude control."""

    def __init__(self, amplitude=0.5, sample_rate=44100):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate
        self.amplitude = amplitude

    def generate(self, frames: int) -> np.ndarray:
        """Generate stereo white noise."""
        wave = np.random.uniform(low=-1.0, high=1.0, size=(frames, 2)).astype(np.float32)
        return self.amplitude * wave

    def get_ui(self) -> QWidget:
        """Return QWidget with amplitude slider."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        amp_label = QLabel(f"Amplitude: {self.amplitude:.2f}")
        layout.addWidget(amp_label)

        amp_slider = QSlider(Qt.Orientation.Horizontal)
        amp_slider.setMinimum(0)
        amp_slider.setMaximum(100)
        amp_slider.setValue(int(self.amplitude * 100))
        amp_slider.setTickInterval(10)
        layout.addWidget(amp_slider)

        def on_amp_change(val):
            self.amplitude = val / 100.0
            amp_label.setText(f"Amplitude: {self.amplitude:.2f}")

        amp_slider.valueChanged.connect(on_amp_change)

        return widget

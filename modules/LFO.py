# modules/lfo.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout
from PyQt6.QtCore import Qt, QSize
from audio_module import AudioModule
from nodes import OutputNode

DB_MIN = -80.0
DB_MAX = 10.0

def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)

class LFO(AudioModule):
    """Sine LFO source module with frequency and amplitude control"""
    def __init__(self, frequency=1.0, amplitude=0.5, sample_rate=44100):
        super().__init__(has_input=False, has_output=True)
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.frequency = frequency
        self.amplitude = amplitude
        self.output_node = OutputNode(self)

    def generate(self, frames: int) -> np.ndarray:
        """Return stereo sine wave LFO"""
        # Compute phase increment
        phase_inc = 2 * np.pi * self.frequency / self.sample_rate
        # Generate sample indices relative to current phase
        indices = np.arange(frames)
        wave = self.amplitude * np.sin(self.phase + phase_inc * indices)
        # Update cumulative phase and wrap around 2π
        self.phase += phase_inc * frames
        self.phase %= 2 * np.pi
        # Stereo output
        return np.column_stack((wave, wave)).astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return a QWidget for controlling frequency and amplitude"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Frequency slider
        freq_label = QLabel(f"Frequency: {self.frequency:.2f} Hz")
        layout.addWidget(freq_label)
        freq_slider = QSlider(Qt.Orientation.Horizontal)
        freq_slider.setMinimum(1)
        freq_slider.setMaximum(20)  # LFOs typically up to 20 Hz
        freq_slider.setValue(int(self.frequency))
        freq_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        freq_slider.setTickInterval(1)
        layout.addWidget(freq_slider)

        freq_slider.valueChanged.connect(lambda val: freq_label.setText(f"Frequency: {val:.2f} Hz") or setattr(self, "frequency", val))

        # Amplitude slider
        amp_label = QLabel(f"Amplitude: {self.amplitude:.2f}")
        layout.addWidget(amp_label)
        amp_slider = QSlider(Qt.Orientation.Horizontal)
        amp_slider.setMinimum(0)
        amp_slider.setMaximum(100)
        amp_slider.setValue(int(self.amplitude * 100))
        amp_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        amp_slider.setTickInterval(10)
        layout.addWidget(amp_slider)

        amp_slider.valueChanged.connect(lambda val: amp_label.setText(f"Amplitude: {val/100:.2f}") or setattr(self, "amplitude", val/100))

        return widget

    def sizeHint(self):
        """Return custom width/height for the fader."""
        return QSize(500, 250)  # width x height
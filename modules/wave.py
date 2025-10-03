# modules/wave.py
import numpy as np
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QPushButton, QDial
from module_base import ModuleWindow


class WaveGenerator(ModuleWindow):
    """wave noise generator module compatible with central mixer."""

    def __init__(self, mixer_callback, close_callback):
        # --- Initialize audio state FIRST ---
        self.fs = 44100
        self.phase = 0.0
        self.freq = 440
        self.channels = 2
        self.volume = -60.0       # dB, default muted
        self.pan = 0.0          # -1 left → +1 right
        self.muted = False
        self.running = True

        # Call base class after attributes exist
        super().__init__("Wave", mixer_callback, close_callback)

        # --- UI Setup ---
        label = QLabel(f"Wave Generator: {self.name}")

        # On/Off toggle
        self.toggle_button = QPushButton("ON")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.toggled.connect(self.toggle_running)

        # Sample rate knob
        self.fs_knob = QDial()
        self.fs_knob.setMinimum(22050)  # 22 kHz
        self.fs_knob.setMaximum(96000)  # 96 kHz
        self.fs_knob.setValue(self.fs)
        self.fs_knob.setNotchesVisible(True)
        self.fs_knob.valueChanged.connect(self.update_fs)
        fs_label = QLabel("Sample Rate (Hz)")

        # Layout: add all widgets to content_layout from ModuleWindow
        self.content_layout.addWidget(label)
        self.content_layout.addWidget(self.toggle_button)
        self.content_layout.addWidget(fs_label)
        self.content_layout.addWidget(self.fs_knob)

    # --- UI callbacks ---
    def toggle_running(self, on):
        """Enable or disable audio generation."""
        self.running = on
        self.toggle_button.setText("ON" if on else "OFF")

    def update_fs(self, value):
        """Update sample rate from knob"""
        self.fs = value

    # --- Audio interface for central mixer ---
    def get_samples(self, frames: int):
        """Return stereo samples for mixer"""
        if not self.running or self.muted:
            return np.zeros((frames, self.channels), dtype=np.float32)

        t = np.arange(frames) / self.fs
        samples = np.sin(2 * np.pi * self.freq * t + self.phase)
        self.phase += 2 * np.pi * self.freq * frames / self.fs
        self.phase = self.phase % (2 * np.pi)

        samples = np.tile(samples[:, None], (1, 2))  # stereo
        samples *= 10 ** (self.volume / 20)          # apply dB volume

        # apply pan
        left_gain = np.sqrt(0.5 * (1 - self.pan))
        right_gain = np.sqrt(0.5 * (1 + self.pan))
        samples[:, 0] *= left_gain
        samples[:, 1] *= right_gain

        return samples

    def closeEvent(self, event):
        """Notify mixer and cleanup."""
        super().closeEvent(event)
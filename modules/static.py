# modules/static.py
import numpy as np
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QSlider
from PyQt6.QtCore import Qt
from module_base import ModuleWindow


class StaticGenerator(ModuleWindow):
    """Static noise generator module compatible with central mixer.
    Two sliders control high-pass and low-pass filtering of the white noise.
    """

    def __init__(self, mixer_callback, close_callback):
        # --- Initialize audio state FIRST ---
        self.fs = 44100
        self.channels = 2
        self.volume = -60.0       # dB, default muted
        self.pan = 0.0            # -1 left → +1 right
        self.muted = False
        self.running = True

        # Filter states for stateful IIR
        self.prev_input_hp = np.zeros(self.channels)
        self.prev_output_hp = np.zeros(self.channels)
        self.prev_output_lp = np.zeros(self.channels)

        # Filter parameters (normalized 0–1)
        self.hp_alpha = 0.0
        self.lp_alpha = 1.0

        super().__init__("Static", mixer_callback, close_callback)

        # --- UI Setup ---
        label = QLabel(f"Static Generator: {self.name}")
        self.content_layout.addWidget(label)

        # On/Off toggle
        self.toggle_button = QPushButton("ON")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.toggled.connect(self.toggle_running)
        self.content_layout.addWidget(self.toggle_button)

        # High-pass slider
        hp_layout = QHBoxLayout()
        hp_label = QLabel("High-pass")
        self.hp_slider = QSlider(Qt.Orientation.Horizontal)
        self.hp_slider.setMinimum(0)
        self.hp_slider.setMaximum(100)
        self.hp_slider.setValue(0)
        self.hp_slider.valueChanged.connect(self.update_hp)
        hp_layout.addWidget(hp_label)
        hp_layout.addWidget(self.hp_slider)
        self.content_layout.addLayout(hp_layout)

        # Low-pass slider
        lp_layout = QHBoxLayout()
        lp_label = QLabel("Low-pass")
        self.lp_slider = QSlider(Qt.Orientation.Horizontal)
        self.lp_slider.setMinimum(0)
        self.lp_slider.setMaximum(100)
        self.lp_slider.setValue(100)
        self.lp_slider.valueChanged.connect(self.update_lp)
        lp_layout.addWidget(lp_label)
        lp_layout.addWidget(self.lp_slider)
        self.content_layout.addLayout(lp_layout)

    # --- UI callbacks ---
    def toggle_running(self, on):
        self.running = on
        self.toggle_button.setText("ON" if on else "OFF")

    def update_hp(self, value):
        """Update high-pass filter alpha (0 = off, 1 = max)."""
        # Map slider 0–100 → 0.0–0.99
        self.hp_alpha = value / 100 * 0.99

    def update_lp(self, value):
        """Update low-pass filter alpha (0 = min, 1 = off)."""
        # Map slider 0–100 → 0.01–1.0
        self.lp_alpha = 0.01 + value / 100 * 0.99

    # --- Audio interface ---
    def get_samples(self, frames: int):
        if not self.running or self.muted:
            return np.zeros((frames, self.channels), dtype=np.float32)

        samples = np.random.uniform(-1, 1, size=(frames, self.channels))

        # Apply high-pass filter
        for ch in range(self.channels):
            for n in range(frames):
                x = samples[n, ch]
                y = self.hp_alpha * (self.prev_output_hp[ch] + x - self.prev_input_hp[ch])
                self.prev_input_hp[ch] = x
                self.prev_output_hp[ch] = y
                samples[n, ch] = y

        # Apply low-pass filter
        for ch in range(self.channels):
            for n in range(frames):
                x = samples[n, ch]
                y = self.lp_alpha * x + (1 - self.lp_alpha) * self.prev_output_lp[ch]
                self.prev_output_lp[ch] = y
                samples[n, ch] = y

        # Apply volume
        gain = 10 ** (self.volume / 20)
        samples *= gain

        # Apply pan
        left_gain = np.sqrt(0.5 * (1 - self.pan))
        right_gain = np.sqrt(0.5 * (1 + self.pan))
        samples[:, 0] *= left_gain
        samples[:, 1] *= right_gain

        return samples

    def closeEvent(self, event):
        super().closeEvent(event)

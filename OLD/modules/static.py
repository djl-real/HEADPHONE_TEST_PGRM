# modules/static.py
import numpy as np
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QComboBox
)
from PyQt6.QtCore import Qt
from module_base import ModuleWindow
from audio_module import AudioModule


class StaticGenerator(AudioModule):
    """Static noise generator compatible with the modular patch/mixer system."""

    def __init__(self, name="Static"):
        super().__init__(name)
        self.running = True
        self.channels = 2

        # HP/LP filter state
        self.hp_alpha = 0.0
        self.lp_alpha = 1.0
        self.prev_input_hp = np.zeros(self.channels)
        self.prev_output_hp = np.zeros(self.channels)
        self.prev_output_lp = np.zeros(self.channels)

        # Patch routing
        self.output_target = None  # Will be set by StaticWindow dropdown

    def process(self, frames: int) -> np.ndarray:
        """Generate static noise and apply simple filters."""
        if not self.running or self.muted:
            return np.zeros((frames, self.channels), dtype=np.float32)

        # --- Generate white noise ---
        samples = np.random.uniform(-1, 1, size=(frames, self.channels)).astype(np.float32)

        # --- High-pass filter ---
        for ch in range(self.channels):
            for n in range(frames):
                x = samples[n, ch]
                y = self.hp_alpha * (self.prev_output_hp[ch] + x - self.prev_input_hp[ch])
                self.prev_input_hp[ch] = x
                self.prev_output_hp[ch] = y
                samples[n, ch] = y

        # --- Low-pass filter ---
        for ch in range(self.channels):
            for n in range(frames):
                x = samples[n, ch]
                y = self.lp_alpha * x + (1 - self.lp_alpha) * self.prev_output_lp[ch]
                self.prev_output_lp[ch] = y
                samples[n, ch] = y

        # --- Apply volume & pan ---
        samples = self._apply_mixer_controls(samples)

        # --- Forward to routed output target, if any ---
        if self.output_target:
            self.output_target.receive_input(samples)

        return samples

    # Backward compatibility (so old mixer code calling get_samples still works)
    def get_samples(self, frames: int) -> np.ndarray:
        return self.process(frames)


class StaticWindow(ModuleWindow):
    """Qt UI for StaticGenerator — adds HP/LP sliders, toggle, and patch output selector."""

    def __init__(self, mixer_callback, close_callback, available_outputs=None):
        super().__init__("Static", mixer_callback, close_callback)

        # --- Backend ---
        self.generator = StaticGenerator()
        self.available_outputs = available_outputs or []

        # --- UI ---
        self.content_layout.addWidget(QLabel("Static Generator"))

        # --- Output routing dropdown ---
        self.output_selector = QComboBox()
        self.content_layout.addWidget(QLabel("Output Patch"))
        self.content_layout.addWidget(self.output_selector)
        self.update_output_options(self.available_outputs)
        self.output_selector.currentIndexChanged.connect(self.change_output)

        # --- Power toggle ---
        self.toggle_button = QPushButton("ON")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.toggled.connect(self.toggle_running)
        self.content_layout.addWidget(self.toggle_button)

        # --- High-pass slider ---
        hp_layout = QHBoxLayout()
        hp_label = QLabel("High-pass")
        self.hp_slider = QSlider(Qt.Orientation.Horizontal)
        self.hp_slider.setRange(0, 100)
        self.hp_slider.setValue(0)
        self.hp_slider.valueChanged.connect(self.update_hp)
        hp_layout.addWidget(hp_label)
        hp_layout.addWidget(self.hp_slider)
        self.content_layout.addLayout(hp_layout)

        # --- Low-pass slider ---
        lp_layout = QHBoxLayout()
        lp_label = QLabel("Low-pass")
        self.lp_slider = QSlider(Qt.Orientation.Horizontal)
        self.lp_slider.setRange(0, 100)
        self.lp_slider.setValue(100)
        self.lp_slider.valueChanged.connect(self.update_lp)
        lp_layout.addWidget(lp_label)
        lp_layout.addWidget(self.lp_slider)
        self.content_layout.addLayout(lp_layout)

    # --- UI Callbacks ---
    def toggle_running(self, on: bool):
        self.generator.running = on
        self.toggle_button.setText("ON" if on else "OFF")

    def update_hp(self, value: int):
        """Set high-pass filter strength (0–0.99)."""
        self.generator.hp_alpha = value / 100 * 0.99

    def update_lp(self, value: int):
        """Set low-pass filter strength (0.01–1.0)."""
        self.generator.lp_alpha = 0.01 + value / 100 * 0.99

    def update_output_options(self, outputs):
        """Refresh dropdown with available output modules (e.g., mixer or filters)."""
        self.output_selector.clear()
        for mod in outputs:
            self.output_selector.addItem(mod.name, mod)

        # Default to first output if available
        if outputs:
            self.generator.output_target = outputs[0]

    def change_output(self, index: int):
        """When dropdown changes, reroute static generator output."""
        self.generator.output_target = self.output_selector.itemData(index)

    # --- Audio Compatibility ---
    def get_samples(self, frames: int):
        return self.generator.process(frames)

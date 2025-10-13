# modules/envelope.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import OutputNode


class EnvelopeGenerator(AudioModule):
    """ADSR envelope generator module."""

    def __init__(self, sample_rate=44100):
        super().__init__(has_input=True, has_output=True)
        self.sample_rate = sample_rate

        # ADSR parameters (seconds / linear)
        self.attack = 0.01
        self.decay = 0.1
        self.sustain = 0.7
        self.release = 0.2

        # Internal state
        self.state = "idle"
        self.level = 0.0
        self.time = 0
        self.note_on = False

        self.output_node = OutputNode(self)

    def trigger(self):
        """Start the envelope (key pressed)."""
        self.state = "attack"
        self.time = 0
        self.note_on = True

    def release_note(self):
        """Release the envelope (key released)."""
        self.state = "release"
        self.time = 0
        self.note_on = False

    def generate(self, frames: int) -> np.ndarray:
        """Generate ADSR envelope samples."""
        if self.input_node.connection is not None:
            out = self.input_node.receive(frames)
        else:
            out = np.zeros((frames, 2), dtype=np.float32)

        for n in range(frames):
            if self.state == "idle":
                self.level = 0.0
            elif self.state == "attack":
                self.level += 1.0 / (self.attack * self.sample_rate)
                if self.level >= 1.0:
                    self.level = 1.0
                    self.state = "decay"
            elif self.state == "decay":
                self.level -= (1.0 - self.sustain) / (self.decay * self.sample_rate)
                if self.level <= self.sustain:
                    self.level = self.sustain
                    self.state = "sustain"
            elif self.state == "sustain":
                self.level = self.sustain
                # sustain lasts until release_note() is called
            elif self.state == "release":
                self.level -= self.sustain / (self.release * self.sample_rate)
                if self.level <= 0.0:
                    self.level = 0.0
                    self.state = "idle"

            out[n] = [self.level, self.level]

        return out.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return QWidget with ADSR sliders."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Attack ---
        attack_label = QLabel(f"Attack: {self.attack:.2f} s")
        layout.addWidget(attack_label)
        attack_slider = QSlider(Qt.Orientation.Horizontal)
        attack_slider.setMinimum(1)
        attack_slider.setMaximum(5000)  # milliseconds
        attack_slider.setValue(int(self.attack * 1000))
        layout.addWidget(attack_slider)
        attack_slider.valueChanged.connect(
            lambda val: (setattr(self, "attack", val / 1000), attack_label.setText(f"Attack: {val / 1000:.2f} s"))
        )

        # --- Decay ---
        decay_label = QLabel(f"Decay: {self.decay:.2f} s")
        layout.addWidget(decay_label)
        decay_slider = QSlider(Qt.Orientation.Horizontal)
        decay_slider.setMinimum(1)
        decay_slider.setMaximum(5000)
        decay_slider.setValue(int(self.decay * 1000))
        layout.addWidget(decay_slider)
        decay_slider.valueChanged.connect(
            lambda val: (setattr(self, "decay", val / 1000), decay_label.setText(f"Decay: {val / 1000:.2f} s"))
        )

        # --- Sustain ---
        sustain_label = QLabel(f"Sustain: {self.sustain:.2f}")
        layout.addWidget(sustain_label)
        sustain_slider = QSlider(Qt.Orientation.Horizontal)
        sustain_slider.setMinimum(0)
        sustain_slider.setMaximum(100)
        sustain_slider.setValue(int(self.sustain * 100))
        layout.addWidget(sustain_slider)
        sustain_slider.valueChanged.connect(
            lambda val: (setattr(self, "sustain", val / 100), sustain_label.setText(f"Sustain: {val / 100:.2f}"))
        )

        # --- Release ---
        release_label = QLabel(f"Release: {self.release:.2f} s")
        layout.addWidget(release_label)
        release_slider = QSlider(Qt.Orientation.Horizontal)
        release_slider.setMinimum(1)
        release_slider.setMaximum(5000)
        release_slider.setValue(int(self.release * 1000))
        layout.addWidget(release_slider)
        release_slider.valueChanged.connect(
            lambda val: (setattr(self, "release", val / 1000), release_label.setText(f"Release: {val / 1000:.2f} s"))
        )

        return widget

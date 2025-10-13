# modules/vco.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout, QButtonGroup, QRadioButton
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import OutputNode


class VCO(AudioModule):
    """Voltage Controlled Oscillator with selectable waveform and smooth pitch control."""

    def __init__(self, frequency=440.0, amplitude=0.5, sample_rate=44100):
        super().__init__(has_input=False, has_output=True)
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.frequency = frequency
        self.target_frequency = frequency  # for smoothing pitch changes
        self.amplitude = amplitude
        self.wave_type = "Sine"
        self.output_node = OutputNode(self)

        # smoothing parameters
        self.freq_smooth_factor = 0.02  # smaller = smoother, adjust for responsiveness

    def generate(self, frames: int) -> np.ndarray:
        """Return stereo waveform with phase-continuous frequency and selectable waveform."""
        # Smooth frequency towards target
        self.frequency += (self.target_frequency - self.frequency) * self.freq_smooth_factor

        phase_inc = self.frequency / self.sample_rate
        phases = (self.phase + np.arange(frames) * phase_inc) % 1.0
        self.phase = (self.phase + frames * phase_inc) % 1.0

        # Generate waveform based on type
        if self.wave_type == "Sine":
            wave = np.sin(2 * np.pi * phases)
        elif self.wave_type == "Triangle":
            wave = 2 * np.abs(2 * phases - 1) - 1
        elif self.wave_type == "Square":
            wave = np.sign(2 * phases - 1)
        elif self.wave_type == "Sawtooth":
            wave = 2 * phases - 1
        else:
            wave = np.zeros(frames)

        wave *= self.amplitude
        return np.column_stack((wave, wave)).astype(np.float32)  # stereo

    def get_ui(self) -> QWidget:
        """Return QWidget with touchscreen-friendly pitch, waveform, and smoothing controls."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Pitch slider (logarithmic) ---
        pitch_label = QLabel(f"Pitch: {self.frequency:.1f} Hz")
        layout.addWidget(pitch_label)

        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setMinimum(0)
        pitch_slider.setMaximum(100)
        min_freq, max_freq = 20.0, 20000.0
        slider_val = int(100 * np.log(self.frequency / min_freq) / np.log(max_freq / min_freq))
        pitch_slider.setValue(slider_val)
        pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        pitch_slider.setTickInterval(10)
        layout.addWidget(pitch_slider)

        def on_pitch_change(val):
            self.target_frequency = min_freq * (max_freq / min_freq) ** (val / 100)
            pitch_label.setText(f"Pitch: {self.target_frequency:.1f} Hz")

        pitch_slider.valueChanged.connect(on_pitch_change)

        # --- Waveform selector using four radio buttons ---
        waveform_label = QLabel(f"Waveform: {self.wave_type}")
        layout.addWidget(waveform_label)

        waveform_layout = QHBoxLayout()
        waveform_group = QButtonGroup(widget)
        for wave in ["Sine", "Triangle", "Square", "Sawtooth"]:
            btn = QRadioButton(wave)
            if wave == self.wave_type:
                btn.setChecked(True)
            waveform_group.addButton(btn)
            waveform_layout.addWidget(btn)

        layout.addLayout(waveform_layout)

        def on_waveform_change():
            checked_btn = waveform_group.checkedButton()
            if checked_btn:
                self.wave_type = checked_btn.text()
                waveform_label.setText(f"Waveform: {self.wave_type}")

        waveform_group.buttonClicked.connect(on_waveform_change)

        # --- Smooth factor slider ---
        smooth_label = QLabel(f"Freq Smooth: {self.freq_smooth_factor:.3f}")
        layout.addWidget(smooth_label)

        smooth_slider = QSlider(Qt.Orientation.Horizontal)
        smooth_slider.setMinimum(0)
        smooth_slider.setMaximum(200)  # maps to 0..0.1
        smooth_slider.setValue(int(self.freq_smooth_factor * 1000))
        smooth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        smooth_slider.setTickInterval(5)
        layout.addWidget(smooth_slider)

        def on_smooth_change(val):
            self.freq_smooth_factor = val / 1000.0
            smooth_label.setText(f"Freq Smooth: {self.freq_smooth_factor:.3f}")

        smooth_slider.valueChanged.connect(on_smooth_change)

        # --- Optional widget sizing hint ---
        widget.setMinimumWidth(240)
        widget.setMinimumHeight(140)

        return widget

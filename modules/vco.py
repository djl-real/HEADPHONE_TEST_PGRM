# modules/vco.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout, QComboBox
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import OutputNode

def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)

class VCO(AudioModule):
    """Voltage Controlled Oscillator with selectable waveform and pitch control."""

    def __init__(self, frequency=440.0, amplitude=0.5, sample_rate=44100):
        super().__init__(has_input=False, has_output=True)
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.frequency = frequency  # in Hz
        self.amplitude = amplitude
        self.wave_type = "Sine"  # default waveform
        self.output_node = OutputNode(self)

    def generate(self, frames: int) -> np.ndarray:
        """Return stereo waveform based on current frequency, amplitude, and waveform type."""
        t = np.arange(frames) / self.sample_rate
        phase_inc = 2 * np.pi * self.frequency / self.sample_rate
        self.phase += phase_inc * frames
        self.phase %= 2 * np.pi

        if self.wave_type == "Sine":
            wave = np.sin(2 * np.pi * self.frequency * t + self.phase)
        elif self.wave_type == "Triangle":
            wave = 2 * np.abs(2 * ((self.frequency * t + self.phase/(2*np.pi)) % 1) - 1) - 1
        elif self.wave_type == "Square":
            wave = np.sign(np.sin(2 * np.pi * self.frequency * t + self.phase))
        elif self.wave_type == "Sawtooth":
            wave = 2 * ((self.frequency * t + self.phase/(2*np.pi)) % 1) - 1
        else:
            wave = np.zeros(frames)

        wave *= self.amplitude
        return np.column_stack((wave, wave)).astype(np.float32)  # stereo output

    def get_ui(self) -> QWidget:
        """Return QWidget with pitch slider and waveform selector."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Pitch slider
        pitch_label = QLabel(f"Pitch: {self.frequency:.1f} Hz")
        layout.addWidget(pitch_label)
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setMinimum(20)      # 20 Hz
        pitch_slider.setMaximum(2000)    # 2 kHz
        pitch_slider.setValue(int(self.frequency))
        pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        pitch_slider.setTickInterval(100)
        layout.addWidget(pitch_slider)

        def on_pitch_change(val):
            self.frequency = float(val)
            pitch_label.setText(f"Pitch: {self.frequency:.1f} Hz")
        pitch_slider.valueChanged.connect(on_pitch_change)

        # Waveform selector
        waveform_label = QLabel(f"Waveform: {self.wave_type}")
        layout.addWidget(waveform_label)
        waveform_combo = QComboBox()
        waveform_combo.addItems(["Sine", "Triangle", "Square", "Sawtooth"])
        waveform_combo.setCurrentText(self.wave_type)
        layout.addWidget(waveform_combo)

        def on_waveform_change(val):
            self.wave_type = val
            waveform_label.setText(f"Waveform: {self.wave_type}")
        waveform_combo.currentTextChanged.connect(on_waveform_change)

        # Amplitude slider (optional)
        amp_label = QLabel(f"Amplitude: {self.amplitude:.2f}")
        layout.addWidget(amp_label)
        amp_slider = QSlider(Qt.Orientation.Horizontal)
        amp_slider.setMinimum(0)
        amp_slider.setMaximum(100)
        amp_slider.setValue(int(self.amplitude * 100))
        amp_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        amp_slider.setTickInterval(10)
        layout.addWidget(amp_slider)

        def on_amp_change(val):
            self.amplitude = val / 100.0
            amp_label.setText(f"Amplitude: {self.amplitude:.2f}")
        amp_slider.valueChanged.connect(on_amp_change)

        return widget

    # def sizeHint(self):
    #     """Custom size hint for ModuleItem."""
    #     return widget.sizeHint()  # optional: set a fixed size if needed

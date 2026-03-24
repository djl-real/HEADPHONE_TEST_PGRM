# modules/note_wave.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt
from source.audio_module import AudioModule

# 12-TET note names within one octave
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# MIDI note range: 24 (C1) to 108 (C8) covers a musically useful span
MIDI_MIN = 24   # C1
MIDI_MAX = 108  # C8


def midi_to_freq(midi_note: int) -> float:
    """Convert a MIDI note number to frequency in Hz (A4 = MIDI 69 = 440 Hz)."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def midi_to_name(midi_note: int) -> str:
    """Convert a MIDI note number to a human-readable name like 'A4' or 'C#3'."""
    octave = (midi_note // 12) - 1
    name = NOTE_NAMES[midi_note % 12]
    return f"{name}{octave}"


class NoteWave(AudioModule):
    """Oscillator locked to the 12-tone equal temperament scale.

    Instead of a continuous frequency slider, pitch is selected by MIDI note
    number so every position maps to a real musical note.  The current note
    name and frequency are displayed in the UI.
    """

    def __init__(self, midi_note=69, amplitude=0.5, sample_rate=44100):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.midi_note = midi_note
        self.frequency = midi_to_freq(midi_note)
        self.target_frequency = self.frequency
        self.amplitude = amplitude
        self.wave_type = "Sine"
        self.freq_smooth_factor = 0.02

    def generate(self, frames: int) -> np.ndarray:
        # Smooth frequency towards target
        self.frequency += (self.target_frequency - self.frequency) * self.freq_smooth_factor

        phase_inc = self.frequency / self.sample_rate
        phases = (self.phase + np.arange(frames) * phase_inc) % 1.0
        self.phase = (self.phase + frames * phase_inc) % 1.0

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
        return np.column_stack((wave, wave)).astype(np.float32)

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Note display ---
        self._note_label = QLabel(self._note_text())
        self._note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self._note_label)

        # --- Frequency readout ---
        self._freq_label = QLabel(f"{self.frequency:.2f} Hz")
        self._freq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._freq_label)

        # --- Note slider (MIDI note number) ---
        pitch_row = QHBoxLayout()
        pitch_lbl = QLabel("Note")
        note_slider = QSlider(Qt.Orientation.Horizontal)
        note_slider.setMinimum(MIDI_MIN)
        note_slider.setMaximum(MIDI_MAX)
        note_slider.setValue(self.midi_note)
        note_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        note_slider.setTickInterval(12)  # one tick per octave
        pitch_row.addWidget(pitch_lbl)
        pitch_row.addWidget(note_slider)
        layout.addLayout(pitch_row)

        def on_note_change(val):
            self.midi_note = val
            self.target_frequency = midi_to_freq(val)
            self._note_label.setText(self._note_text())
            self._freq_label.setText(f"{self.target_frequency:.2f} Hz")

        note_slider.valueChanged.connect(on_note_change)

        # --- Amplitude slider (0 – 100 → 0.0 – 1.0) ---
        amp_row = QHBoxLayout()
        amp_lbl = QLabel("Amp")
        self._amp_val = QLabel(f"{self.amplitude:.2f}")
        amp_slider = QSlider(Qt.Orientation.Horizontal)
        amp_slider.setMinimum(0)
        amp_slider.setMaximum(100)
        amp_slider.setValue(int(self.amplitude * 100))
        amp_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        amp_slider.setTickInterval(25)
        amp_row.addWidget(amp_lbl)
        amp_row.addWidget(amp_slider)
        amp_row.addWidget(self._amp_val)
        layout.addLayout(amp_row)

        def on_amp_change(val):
            self.amplitude = val / 100.0
            self._amp_val.setText(f"{self.amplitude:.2f}")

        amp_slider.valueChanged.connect(on_amp_change)

        # --- Waveform selector ---
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

        # --- Frequency smoothing ---
        smooth_row = QHBoxLayout()
        smooth_lbl = QLabel("Glide")
        self._smooth_val = QLabel(f"{self.freq_smooth_factor:.3f}")
        smooth_slider = QSlider(Qt.Orientation.Horizontal)
        smooth_slider.setMinimum(0)
        smooth_slider.setMaximum(200)
        smooth_slider.setValue(int(self.freq_smooth_factor * 1000))
        smooth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        smooth_slider.setTickInterval(50)
        smooth_row.addWidget(smooth_lbl)
        smooth_row.addWidget(smooth_slider)
        smooth_row.addWidget(self._smooth_val)
        layout.addLayout(smooth_row)

        def on_smooth_change(val):
            self.freq_smooth_factor = val / 1000.0
            self._smooth_val.setText(f"{self.freq_smooth_factor:.3f}")

        smooth_slider.valueChanged.connect(on_smooth_change)

        widget.setMinimumWidth(280)
        widget.setMinimumHeight(180)
        return widget

    def _note_text(self) -> str:
        return midi_to_name(self.midi_note)

    # -------------------------------------------------------- serialization
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "midi_note": self.midi_note,
            "frequency": self.frequency,
            "target_frequency": self.target_frequency,
            "amplitude": self.amplitude,
            "wave_type": self.wave_type,
            "freq_smooth_factor": self.freq_smooth_factor,
            "phase": self.phase,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.midi_note = state.get("midi_note", 69)
        self.frequency = state.get("frequency", midi_to_freq(self.midi_note))
        self.target_frequency = state.get("target_frequency", self.frequency)
        self.amplitude = state.get("amplitude", 0.5)
        self.wave_type = state.get("wave_type", "Sine")
        self.freq_smooth_factor = state.get("freq_smooth_factor", 0.02)
        self.phase = state.get("phase", 0.0)
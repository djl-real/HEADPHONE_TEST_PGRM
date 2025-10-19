import numpy as np
import soundfile as sf
import tempfile
import pyttsx3
import gc
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QComboBox, QSlider, QSizePolicy
)
from PyQt6.QtCore import Qt
from audio_module import AudioModule


from PyQt6.QtWidgets import QCheckBox, QHBoxLayout

class TTS(AudioModule):
    """Text-to-speech generator module with voice, pitch, and loop control."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate
        self.voices = pyttsx3.init().getProperty("voices")
        print(self.voices)
        self.current_voice = self.voices[0].id if self.voices else None

        self.buffer = np.zeros((0, 2), dtype=np.float32)
        self.playing = False
        self.pos = 0
        self.text = ""
        self.pitch = 1.0  # Normal pitch
        self.loop = False  # Loop enabled/disabled

    def generate_tts_audio(self, text: str):
        """Generate TTS audio for given text and store as stereo buffer."""
        if not text.strip():
            return

        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            path = tmpfile.name

        engine = pyttsx3.init()
        if self.current_voice:
            engine.setProperty("voice", self.current_voice)
        engine.save_to_file(text, path)

        try:
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass
            del engine
            gc.collect()

        try:
            data, fs = sf.read(path, dtype="float32")
            if data.ndim == 1:
                data = np.column_stack((data, data))

            # Apply pitch shifting by resampling
            if self.pitch != 1.0:
                new_len = int(len(data) / self.pitch)
                old_indices = np.linspace(0, len(data) - 1, num=new_len)
                data = np.array([
                    np.interp(old_indices, np.arange(len(data)), data[:, 0]),
                    np.interp(old_indices, np.arange(len(data)), data[:, 1])
                ]).T

            # Resample to match output sample rate if necessary
            if fs != self.sample_rate:
                ratio = self.sample_rate / fs
                idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
                idx = idx[idx < len(data)]
                data = data[idx]

            self.buffer = data
            self.playing = True
            self.pos = 0
        except Exception as e:
            print(f"[TTS] Failed to load audio: {e}")
            self.buffer = np.zeros((0, 2), dtype=np.float32)
            self.playing = False

    def generate(self, frames: int):
        """Output current TTS buffer with optional looping."""
        out = np.zeros((frames, 2), dtype=np.float32)
        if not self.playing or len(self.buffer) == 0:
            return out

        remaining = len(self.buffer) - self.pos
        to_copy = min(frames, remaining)
        out[:to_copy] = self.buffer[self.pos:self.pos + to_copy]
        self.pos += to_copy

        if self.pos >= len(self.buffer):
            if self.loop:
                self.pos = 0  # restart playback
            else:
                self.playing = False

        return out

    def get_ui(self) -> QWidget:
        """Return UI with text entry, play/stop buttons, voice, pitch, and loop."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Text box ---
        layout.addWidget(QLabel("Enter text to speak:"))
        text_input = QTextEdit()
        text_input.setFixedHeight(80)
        layout.addWidget(text_input)

        # --- Voice selection ---
        layout.addWidget(QLabel("Select voice:"))
        voice_dropdown = QComboBox()
        for v in self.voices:
            voice_dropdown.addItem(v.name)
        voice_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        voice_dropdown.setMinimumHeight(30)
        layout.addWidget(voice_dropdown)

        # Update current voice when dropdown changes
        def on_voice_change(idx):
            self.current_voice = self.voices[idx].id
        voice_dropdown.currentIndexChanged.connect(on_voice_change)


        # --- Pitch slider ---
        layout.addWidget(QLabel("Pitch"))
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setMinimum(0)
        pitch_slider.setMaximum(100)

        def slider_to_pitch(val):
            s = val / 100.0
            return 0.5 * (4 ** s)

        def pitch_to_slider(pitch):
            s = np.log2(pitch / 0.5) / 2
            return int(s * 100)

        pitch_slider.setValue(pitch_to_slider(self.pitch))
        pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        pitch_slider.setTickInterval(25)
        pitch_slider.valueChanged.connect(lambda val: setattr(self, "pitch", slider_to_pitch(val)))
        layout.addWidget(pitch_slider)

        # --- Play / Stop buttons + Loop checkbox ---
        controls_layout = QHBoxLayout()
        play_btn = QPushButton("▶ Play")
        stop_btn = QPushButton("■ Stop")
        loop_checkbox = QCheckBox("Loop")

        controls_layout.addWidget(play_btn)
        controls_layout.addWidget(stop_btn)
        controls_layout.addWidget(loop_checkbox)
        layout.addLayout(controls_layout)

        # Connect buttons
        def on_play():
            self.text = text_input.toPlainText().strip()
            self.generate_tts_audio(self.text)

        def on_stop():
            self.playing = False
            self.pos = 0

        play_btn.clicked.connect(on_play)
        stop_btn.clicked.connect(on_stop)
        loop_checkbox.stateChanged.connect(lambda state: setattr(self, "loop", state))

        return widget

    
    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()  # includes input/output node counts
        data.update({
            "text": self.text,
            "current_voice": self.current_voice,
            "pitch": self.pitch,
            "playing": self.playing,
            "pos": self.pos,
            # Note: buffer is transient; not serialized
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.text = state.get("text", "")
        self.current_voice = state.get("current_voice", self.voices[0].id if self.voices else None)
        self.pitch = state.get("pitch", 1.0)
        self.playing = state.get("playing", False)
        self.pos = state.get("pos", 0)


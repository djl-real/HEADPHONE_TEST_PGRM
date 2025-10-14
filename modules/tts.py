import numpy as np
import soundfile as sf
import tempfile
import pyttsx3
import gc
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QSlider
)
from PyQt6.QtCore import Qt
from audio_module import AudioModule


class TextToSpeech(AudioModule):
    """Text-to-speech generator module with voice and pitch control."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate
        self.voices = pyttsx3.init().getProperty("voices")
        self.current_voice = self.voices[0].id if self.voices else None

        self.buffer = np.zeros((0, 2), dtype=np.float32)
        self.playing = False
        self.pos = 0
        self.text = ""
        self.pitch = 1.0  # Normal pitch

    # ---------------------------
    # AUDIO GENERATION
    # ---------------------------
    def generate_tts_audio(self, text: str):
        """Generate TTS audio for given text and store as stereo buffer."""
        if not text.strip():
            return

        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            path = tmpfile.name

        # Create a short-lived TTS engine
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

        # Load generated audio
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
        """Output current TTS buffer."""
        out = np.zeros((frames, 2), dtype=np.float32)

        if not self.playing or self.pos >= len(self.buffer):
            return out

        end = min(self.pos + frames, len(self.buffer))
        chunk = self.buffer[self.pos:end]
        out[:len(chunk)] = chunk
        self.pos = end

        if self.pos >= len(self.buffer):
            self.playing = False

        return out

    # ---------------------------
    # UI
    # ---------------------------
    def get_ui(self) -> QWidget:
        """Return UI with text entry, play button, voice selection, and pitch slider."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Text box ---
        layout.addWidget(QLabel("Enter text to speak:"))
        text_input = QLineEdit()
        layout.addWidget(text_input)

        # --- Voice selection ---
        layout.addWidget(QLabel("Select voice:"))
        voice_dropdown = QComboBox()
        for v in self.voices:
            voice_dropdown.addItem(v.name)
        layout.addWidget(voice_dropdown)

        def on_voice_change(idx):
            self.current_voice = self.voices[idx].id
        voice_dropdown.currentIndexChanged.connect(on_voice_change)

        # --- Pitch slider (logarithmic mapping) ---
        layout.addWidget(QLabel("Pitch"))
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setMinimum(0)
        pitch_slider.setMaximum(100)

        def slider_to_pitch(val):
            s = val / 100.0
            return 0.5 * (4 ** s)  # 0.5x – 2x pitch range

        def pitch_to_slider(pitch):
            s = np.log2(pitch / 0.5) / 2
            return int(s * 100)

        pitch_slider.setValue(pitch_to_slider(self.pitch))
        pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        pitch_slider.setTickInterval(25)
        layout.addWidget(pitch_slider)
        pitch_slider.valueChanged.connect(lambda val: setattr(self, "pitch", slider_to_pitch(val)))

        # --- Play button ---
        play_btn = QPushButton("▶ Play")
        play_btn.setFixedHeight(40)
        layout.addWidget(play_btn)

        def on_play():
            self.text = text_input.text().strip()
            self.generate_tts_audio(self.text)

        play_btn.clicked.connect(on_play)

        return widget

import os
import numpy as np
import soundfile as sf
import tempfile
import pyttsx3
import gc
import platform

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QComboBox, QSlider,
    QSizePolicy, QListWidget, QHBoxLayout, QCheckBox
)
from PyQt6.QtCore import Qt

from audio_module import AudioModule


class TTS(AudioModule):
    """Text-to-speech generator module with voice, pitch, loop, and file presets."""

    def __init__(self, sample_rate=44100, tts_folder="TTS"):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate

        engine = pyttsx3.init()
        all_voices = engine.getProperty("voices")

        if platform.system().lower() == "linux":
            # Linux has MANY voices — filter to only English ones
            self.voices = [
                v for v in all_voices 
                if "english" in v.name.lower() or "en_" in v.id.lower()
            ]
        else:
            # Windows/macOS keep full list
            self.voices = all_voices

        self.current_voice = self.voices[0].id if self.voices else None

        self.buffer = np.zeros((0, 2), dtype=np.float32)
        self.playing = False
        self.pos = 0
        self.text = ""
        self.pitch = 1.0
        self.loop = False

        self.tts_folder = tts_folder
        self.tts_files = []
        self.selected_file_lines = []

        self._scan_tts_folder()

    # --------------------------------------------------------------------------
    # NEW: Load .txt files from /TTS/
    # --------------------------------------------------------------------------
    def _scan_tts_folder(self):
        if not os.path.exists(self.tts_folder):
            os.makedirs(self.tts_folder)

        self.tts_files = [
            f for f in os.listdir(self.tts_folder)
            if f.lower().endswith(".txt")
        ]

    def _load_file_lines(self, filename):
        path = os.path.join(self.tts_folder, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            self.selected_file_lines = lines
        except Exception as e:
            print("[TTS] Failed reading file:", e)
            self.selected_file_lines = []

    # --------------------------------------------------------------------------
    # Audio
    # --------------------------------------------------------------------------
    def generate_tts_audio(self, text: str):
        if not text.strip():
            return

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
            except:
                pass
            del engine
            gc.collect()

        try:
            data, fs = sf.read(path, dtype="float32")

            if data.ndim == 1:
                data = np.column_stack((data, data))

            # Pitch shifting
            if self.pitch != 1.0:
                new_len = int(len(data) / self.pitch)
                idx = np.linspace(0, len(data) - 1, num=new_len)
                data = np.array([
                    np.interp(idx, np.arange(len(data)), data[:, 0]),
                    np.interp(idx, np.arange(len(data)), data[:, 1])
                ]).T

            # Resample
            if fs != self.sample_rate:
                ratio = self.sample_rate / fs
                idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
                idx = idx[idx < len(data)]
                data = data[idx]

            self.buffer = data
            self.playing = True
            self.pos = 0

        except Exception as e:
            print("[TTS] Load audio error:", e)

    def generate(self, frames: int):
        out = np.zeros((frames, 2), dtype=np.float32)
        if not self.playing or len(self.buffer) == 0:
            return out

        remaining = len(self.buffer) - self.pos
        to_copy = min(frames, remaining)
        out[:to_copy] = self.buffer[self.pos:self.pos + to_copy]
        self.pos += to_copy

        if self.pos >= len(self.buffer):
            if self.loop:
                self.pos = 0
            else:
                self.playing = False

        return out

    # --------------------------------------------------------------------------
    # UI
    # --------------------------------------------------------------------------
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ---------------- Text Input ----------------
        layout.addWidget(QLabel("Enter text to speak:"))
        text_input = QTextEdit()
        text_input.setFixedHeight(80)
        layout.addWidget(text_input)

        # ---------------- Voice Dropdown ----------------

        layout.addWidget(QLabel("Select voice:"))
        voice_dropdown = QComboBox()

        # Fill with filtered voices
        for v in self.voices:
            voice_dropdown.addItem(v.name)

        def on_voice_changed(i):
            if 0 <= i < len(self.voices):
                self.current_voice = self.voices[i].id

        voice_dropdown.currentIndexChanged.connect(on_voice_changed)
        layout.addWidget(voice_dropdown)
        layout.addWidget(voice_dropdown)

        # ---------------- Pitch Slider ----------------
        layout.addWidget(QLabel("Pitch"))
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setMinimum(0)
        pitch_slider.setMaximum(100)

        def slider_to_pitch(val):
            s = val / 100.0
            return 0.5 * (4 ** s)

        pitch_slider.setValue(50)
        pitch_slider.valueChanged.connect(
            lambda v: setattr(self, "pitch", slider_to_pitch(v))
        )
        layout.addWidget(pitch_slider)

        # ---------------- Play / Stop / Loop ----------------
        ctl = QHBoxLayout()
        play_btn = QPushButton("▶ Play")
        stop_btn = QPushButton("■ Stop")
        loop_box = QCheckBox("Loop")

        play_btn.clicked.connect(lambda: self._play(text_input))
        stop_btn.clicked.connect(self._stop)
        loop_box.stateChanged.connect(lambda s: setattr(self, "loop", bool(s)))

        ctl.addWidget(play_btn)
        ctl.addWidget(stop_btn)
        ctl.addWidget(loop_box)
        layout.addLayout(ctl)

        # ======================================================================
        # NEW SECTION: TTS PRESET FILES
        # ======================================================================
        layout.addWidget(QLabel("Preset Files (from /TTS/):"))
        file_list = QListWidget()
        file_list.addItems(self.tts_files)
        layout.addWidget(file_list)

        line_list_label = QLabel("Lines:")
        line_list_label.setVisible(False)
        layout.addWidget(line_list_label)

        line_list = QListWidget()
        line_list.setVisible(False)
        layout.addWidget(line_list)

        # --- Click a file → load its lines ---
        def on_file_clicked():
            fname = file_list.currentItem().text()
            self._load_file_lines(fname)

            # update UI
            line_list.clear()
            line_list.addItems(self.selected_file_lines)
            line_list.setVisible(True)
            line_list_label.setVisible(True)

        file_list.itemClicked.connect(lambda _: on_file_clicked())

        # --- Click a line → insert into text box ---
        def on_line_clicked():
            if line_list.currentItem():
                text_input.setText(line_list.currentItem().text())

        line_list.itemClicked.connect(lambda _: on_line_clicked())

        return widget

    # ----------------------------------------------------------------------
    # Play/Stop helpers
    # ----------------------------------------------------------------------
    def _play(self, text_input):
        self.text = text_input.toPlainText().strip()
        self.generate_tts_audio(self.text)

    def _stop(self):
        self.playing = False
        self.pos = 0

    # ----------------------------------------------------------------------
    # Serialization
    # ----------------------------------------------------------------------
    def serialize(self):
        data = super().serialize()
        data.update({
            "text": self.text,
            "current_voice": self.current_voice,
            "pitch": self.pitch,
            "loop": self.loop,
        })
        return data

    def deserialize(self, state):
        super().deserialize(state)
        self.text = state.get("text", "")
        self.current_voice = state.get("current_voice", self.current_voice)
        self.pitch = state.get("pitch", 1.0)
        self.loop = state.get("loop", False)

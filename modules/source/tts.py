import os
import numpy as np
import soundfile as sf
import tempfile
import gc
import subprocess
import platform

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QComboBox, QSlider,
    QListWidget, QHBoxLayout, QCheckBox, QGroupBox
)
from PyQt6.QtCore import Qt

from audio_module import AudioModule


class TTS(AudioModule):
    """Unified Text-to-speech generator module supporting both pyttsx3 (default) and Mycroft Mimic engines."""

    ENGINE_DEFAULT = "default"
    ENGINE_MIMIC = "mimic"

    def __init__(self, sample_rate=44100, tts_folder="TTS"):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate
        self.tts_folder = tts_folder

        # Current engine selection
        self.current_engine = self.ENGINE_DEFAULT

        # Audio state
        self.buffer = np.zeros((0, 2), dtype=np.float32)
        self.playing = False
        self.pos = 0
        self.text = ""
        self.pitch = 1.0
        self.loop = False
        self.speaking_rate = 1.0  # Used by Mimic

        # Preset files
        self.tts_files = []
        self.selected_file_lines = []

        # Initialize engines
        self._init_default_engine()
        self._init_mimic_engine()
        self._scan_tts_folder()

    # ==========================================================================
    # Engine Initialization
    # ==========================================================================
    def _init_default_engine(self):
        """Initialize pyttsx3 voices."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            all_voices = engine.getProperty("voices")

            if platform.system().lower() == "linux":
                # Linux has MANY voices — filter to only English ones
                self.default_voices = [
                    v for v in all_voices
                    if "english" in v.name.lower() or "en_" in v.id.lower()
                ]
            else:
                # Windows/macOS keep full list
                self.default_voices = all_voices

            self.default_voice = self.default_voices[0].id if self.default_voices else None
            engine.stop()
            del engine
            self.default_available = True
        except Exception as e:
            print(f"[TTS] pyttsx3 initialization failed: {e}")
            self.default_voices = []
            self.default_voice = None
            self.default_available = False

    def _init_mimic_engine(self):
        """Initialize Mimic voices."""
        # Mimic built-in voices
        self.mimic_voices = {
            "ap": "Alan Pope (male, British)",
            "slt": "Scottish female",
            "rms": "US male",
            "awb": "Scottish male",
        }
        self.mimic_voice_codes = list(self.mimic_voices.keys())
        self.mimic_voice = "ap"  # Default voice

    # ==========================================================================
    # Preset File Management
    # ==========================================================================
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

    # ==========================================================================
    # Audio Generation
    # ==========================================================================
    def generate_tts_audio(self, text: str):
        """Generate TTS audio using the currently selected engine."""
        if not text.strip():
            return

        if self.current_engine == self.ENGINE_MIMIC:
            self._generate_mimic_audio(text)
        else:
            self._generate_default_audio(text)

    def _generate_default_audio(self, text: str):
        """Generate audio using pyttsx3."""
        import pyttsx3

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            path = tmpfile.name

        engine = pyttsx3.init()
        if self.default_voice:
            engine.setProperty("voice", self.default_voice)
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

        self._load_and_process_audio(path)

    def _generate_mimic_audio(self, text: str):
        """Generate audio using Mycroft Mimic."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            wav_path = tmpfile.name

        try:
            # Build mimic command
            cmd = [
                "mimic",
                "-t", text,
                "-voice", self.mimic_voice,
                "-o", wav_path
            ]

            # Run mimic
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"[TTS] Mimic error: {result.stderr}")
                return

            self._load_and_process_audio(wav_path, apply_speaking_rate=True)

        except subprocess.TimeoutExpired:
            print("[TTS] Mimic command timed out")
        except FileNotFoundError:
            print("[TTS] ERROR: mimic command not found")
        except Exception as e:
            print("[TTS] Mimic audio generation error:", e)
            import traceback
            traceback.print_exc()
        finally:
            try:
                if os.path.exists(wav_path):
                    os.remove(wav_path)
            except:
                pass
            gc.collect()

    def _load_and_process_audio(self, path: str, apply_speaking_rate: bool = False):
        """Load audio file and apply pitch/rate transformations."""
        try:
            data, fs = sf.read(path, dtype="float32")

            # Convert to stereo if mono
            if data.ndim == 1:
                data = np.column_stack((data, data))

            # Speaking rate adjustment (for Mimic)
            if apply_speaking_rate and self.speaking_rate != 1.0:
                new_len = int(len(data) / self.speaking_rate)
                if new_len > 0:
                    idx = np.linspace(0, len(data) - 1, num=new_len)
                    data = np.array([
                        np.interp(idx, np.arange(len(data)), data[:, 0]),
                        np.interp(idx, np.arange(len(data)), data[:, 1])
                    ]).T

            # Pitch shifting
            if self.pitch != 1.0:
                new_len = int(len(data) / self.pitch)
                if new_len > 0:
                    idx = np.linspace(0, len(data) - 1, num=new_len)
                    data = np.array([
                        np.interp(idx, np.arange(len(data)), data[:, 0]),
                        np.interp(idx, np.arange(len(data)), data[:, 1])
                    ]).T

            # Resample to target sample rate
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
        finally:
            # Clean up temp file
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

    def generate(self, frames: int):
        """Generate audio frames for playback."""
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

    # ==========================================================================
    # UI
    # ==========================================================================
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ================== Engine Selection ==================
        engine_group = QGroupBox("TTS Engine")
        engine_layout = QHBoxLayout(engine_group)

        engine_dropdown = QComboBox()
        engine_dropdown.addItem("Default (pyttsx3)", self.ENGINE_DEFAULT)
        engine_dropdown.addItem("Mycroft Mimic", self.ENGINE_MIMIC)

        engine_layout.addWidget(engine_dropdown)
        layout.addWidget(engine_group)

        # ================== Text Input ==================
        layout.addWidget(QLabel("Enter text to speak:"))
        text_input = QTextEdit()
        text_input.setFixedHeight(50)
        layout.addWidget(text_input)

        # ================== Voice Selection (stacked widget approach) ==================
        voice_label = QLabel("Select voice:")
        layout.addWidget(voice_label)

        # Default engine voices
        default_voice_dropdown = QComboBox()
        for v in self.default_voices:
            default_voice_dropdown.addItem(v.name)

        def on_default_voice_changed(i):
            if 0 <= i < len(self.default_voices):
                self.default_voice = self.default_voices[i].id

        default_voice_dropdown.currentIndexChanged.connect(on_default_voice_changed)
        layout.addWidget(default_voice_dropdown)

        # Mimic engine voices
        mimic_voice_dropdown = QComboBox()
        for code in self.mimic_voice_codes:
            voice_name = self.mimic_voices[code]
            mimic_voice_dropdown.addItem(f"{voice_name} ({code})", code)

        def on_mimic_voice_changed(i):
            self.mimic_voice = mimic_voice_dropdown.itemData(i)

        mimic_voice_dropdown.currentIndexChanged.connect(on_mimic_voice_changed)
        mimic_voice_dropdown.setVisible(False)
        layout.addWidget(mimic_voice_dropdown)

        # ================== Speaking Rate (Mimic only) ==================
        rate_label = QLabel(f"Speaking Rate: {self.speaking_rate:.2f}x")
        layout.addWidget(rate_label)

        rate_slider = QSlider(Qt.Orientation.Horizontal)
        rate_slider.setMinimum(50)   # 0.5x
        rate_slider.setMaximum(200)  # 2.0x
        rate_slider.setValue(int(self.speaking_rate * 100))

        def on_rate_change(val):
            self.speaking_rate = val / 100.0
            rate_label.setText(f"Speaking Rate: {self.speaking_rate:.2f}x")

        rate_slider.valueChanged.connect(on_rate_change)
        layout.addWidget(rate_slider)

        # Initially hide rate controls (default engine doesn't use them)
        rate_label.setVisible(False)
        rate_slider.setVisible(False)

        # ================== Pitch Slider ==================
        pitch_label = QLabel(f"Pitch: {self.pitch:.2f}x")
        layout.addWidget(pitch_label)

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

        def on_pitch_change(val):
            self.pitch = slider_to_pitch(val)
            pitch_label.setText(f"Pitch: {self.pitch:.2f}x")

        pitch_slider.valueChanged.connect(on_pitch_change)
        layout.addWidget(pitch_slider)

        # ================== Play / Stop / Loop ==================
        ctl = QHBoxLayout()
        play_btn = QPushButton("▶ Play")
        stop_btn = QPushButton("■ Stop")
        loop_box = QCheckBox("Loop")

        play_btn.clicked.connect(lambda: self._play(text_input))
        stop_btn.clicked.connect(self._stop)
        loop_box.stateChanged.connect(lambda s: setattr(self, "loop", bool(s)))
        loop_box.setChecked(self.loop)

        ctl.addWidget(play_btn)
        ctl.addWidget(stop_btn)
        ctl.addWidget(loop_box)
        layout.addLayout(ctl)

        # ================== Engine Switch Handler ==================
        def on_engine_changed(i):
            engine_code = engine_dropdown.itemData(i)
            self.current_engine = engine_code

            is_mimic = (engine_code == self.ENGINE_MIMIC)

            # Toggle voice dropdowns
            default_voice_dropdown.setVisible(not is_mimic)
            mimic_voice_dropdown.setVisible(is_mimic)

            # Toggle speaking rate controls (Mimic only)
            rate_label.setVisible(is_mimic)
            rate_slider.setVisible(is_mimic)

        engine_dropdown.currentIndexChanged.connect(on_engine_changed)

        # ================== Preset Files ==================
        layout.addWidget(QLabel("Preset Files (from /TTS/):"))
        file_list = QListWidget()
        file_list.addItems(self.tts_files)
        file_list.setMinimumHeight(80)
        layout.addWidget(file_list)

        line_list_label = QLabel("Lines:")
        line_list_label.setVisible(False)
        layout.addWidget(line_list_label)

        line_list = QListWidget()
        line_list.setVisible(False)
        line_list.setMinimumHeight(120)
        layout.addWidget(line_list, 1)  # stretch factor to take remaining space

        # --- Click a file → load its lines ---
        def on_file_clicked():
            if file_list.currentItem():
                fname = file_list.currentItem().text()
                self._load_file_lines(fname)

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

    # ==========================================================================
    # Play/Stop helpers
    # ==========================================================================
    def _play(self, text_input):
        self.text = text_input.toPlainText().strip()
        self.generate_tts_audio(self.text)

    def _stop(self):
        self.playing = False
        self.pos = 0

    # ==========================================================================
    # Serialization
    # ==========================================================================
    def serialize(self):
        data = super().serialize()
        data.update({
            "text": self.text,
            "current_engine": self.current_engine,
            "default_voice": self.default_voice,
            "mimic_voice": self.mimic_voice,
            "pitch": self.pitch,
            "speaking_rate": self.speaking_rate,
            "loop": self.loop,
        })
        return data

    def deserialize(self, state):
        super().deserialize(state)
        self.text = state.get("text", "")
        self.current_engine = state.get("current_engine", self.ENGINE_DEFAULT)
        self.default_voice = state.get("default_voice", self.default_voice)
        self.mimic_voice = state.get("mimic_voice", "ap")
        self.pitch = state.get("pitch", 1.0)
        self.speaking_rate = state.get("speaking_rate", 1.0)
        self.loop = state.get("loop", False)
import os
import numpy as np
import soundfile as sf
import tempfile
import gc
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QComboBox, QSlider,
    QSizePolicy, QListWidget, QHBoxLayout, QCheckBox
)
from PyQt6.QtCore import Qt

from audio_module import AudioModule


class GoogleTTS(AudioModule):
    """Mycroft Mimic Text-to-speech generator module with voice selection, pitch, loop, and file presets."""

    def __init__(self, sample_rate=44100, tts_folder="TTS"):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate

        # Mimic voices - these are the built-in voices
        # You can add more if you have custom voice files
        self.voices = {
            "ap": "Alan Pope (male, British)",
            "slt": "Scottish female",
            "rms": "US male",
            "awb": "Scottish male",
        }
        self.voice_codes = list(self.voices.keys())
        self.current_voice = "ap"  # Default voice

        self.buffer = np.zeros((0, 2), dtype=np.float32)
        self.playing = False
        self.pos = 0
        self.text = ""
        self.pitch = 1.0
        self.loop = False
        
        # Mimic-specific parameters
        self.speaking_rate = 1.0  # Speech rate multiplier

        self.tts_folder = tts_folder
        self.tts_files = []
        self.selected_file_lines = []

        self._scan_tts_folder()
        self._check_mimic_installed()

    def _check_mimic_installed(self):
        """Check if mimic is installed and accessible."""
        try:
            result = subprocess.run(
                ["mimic", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"[MimicTTS] Mimic found: {result.stdout.strip()}")
            else:
                print("[MimicTTS] Warning: mimic command not working properly")
        except FileNotFoundError:
            print("[MimicTTS] ERROR: mimic not found. Please install Mycroft Mimic.")
            print("Installation: https://github.com/MycroftAI/mimic1")
        except Exception as e:
            print(f"[MimicTTS] Error checking mimic: {e}")

    # --------------------------------------------------------------------------
    # Load .txt files from /TTS/
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
            print("[MimicTTS] Failed reading file:", e)
            self.selected_file_lines = []

    # --------------------------------------------------------------------------
    # Audio Generation
    # --------------------------------------------------------------------------
    def generate_tts_audio(self, text: str):
        if not text.strip():
            return

        # Create temporary file for mimic output
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            wav_path = tmpfile.name

        try:
            # Build mimic command
            # mimic -t "text" -voice <voice> -o output.wav
            cmd = [
                "../mimic1/mimic",
                "-t", text,
                "-voice", self.current_voice,
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
                print(f"[MimicTTS] Mimic error: {result.stderr}")
                return
            
            # Load the generated audio
            data, fs = sf.read(wav_path, dtype="float32")

            # Convert to stereo if mono
            if data.ndim == 1:
                data = np.column_stack((data, data))

            # Speaking rate adjustment (time stretching)
            if self.speaking_rate != 1.0:
                new_len = int(len(data) / self.speaking_rate)
                idx = np.linspace(0, len(data) - 1, num=new_len)
                data = np.array([
                    np.interp(idx, np.arange(len(data)), data[:, 0]),
                    np.interp(idx, np.arange(len(data)), data[:, 1])
                ]).T

            # Pitch shifting
            if self.pitch != 1.0:
                new_len = int(len(data) / self.pitch)
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

        except subprocess.TimeoutExpired:
            print("[MimicTTS] Mimic command timed out")
        except FileNotFoundError:
            print("[MimicTTS] ERROR: mimic command not found")
        except Exception as e:
            print("[MimicTTS] Audio generation error:", e)
            import traceback
            traceback.print_exc()
        finally:
            # Clean up temporary file
            try:
                if os.path.exists(wav_path):
                    os.remove(wav_path)
            except:
                pass
            gc.collect()

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

        # ---------------- Voice Selection ----------------
        layout.addWidget(QLabel("Select voice:"))
        voice_dropdown = QComboBox()

        # Fill with available voices
        for code in self.voice_codes:
            voice_name = self.voices[code]
            voice_dropdown.addItem(f"{voice_name} ({code})", code)
        
        # Set current selection
        current_index = self.voice_codes.index(self.current_voice) if self.current_voice in self.voice_codes else 0
        voice_dropdown.setCurrentIndex(current_index)

        def on_voice_changed(i):
            self.current_voice = voice_dropdown.itemData(i)

        voice_dropdown.currentIndexChanged.connect(on_voice_changed)
        layout.addWidget(voice_dropdown)

        # ---------------- Speaking Rate Slider ----------------
        layout.addWidget(QLabel(f"Speaking Rate: {self.speaking_rate:.2f}x"))
        rate_label = layout.itemAt(layout.count() - 1).widget()
        
        rate_slider = QSlider(Qt.Orientation.Horizontal)
        rate_slider.setMinimum(50)   # 0.5x
        rate_slider.setMaximum(200)  # 2.0x
        rate_slider.setValue(int(self.speaking_rate * 100))
        
        def on_rate_change(val):
            self.speaking_rate = val / 100.0
            rate_label.setText(f"Speaking Rate: {self.speaking_rate:.2f}x")
        
        rate_slider.valueChanged.connect(on_rate_change)
        layout.addWidget(rate_slider)

        # Rate tick marks
        rate_tick_layout = QHBoxLayout()
        for lbl in ["0.5x", "", "1.0x", "", "2.0x"]:
            l = QLabel(lbl)
            l.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            rate_tick_layout.addWidget(l)
        layout.addLayout(rate_tick_layout)

        # ---------------- Pitch Slider ----------------
        layout.addWidget(QLabel(f"Pitch: {self.pitch:.2f}x"))
        pitch_label = layout.itemAt(layout.count() - 1).widget()
        
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

        # Pitch tick marks
        tick_layout = QHBoxLayout()
        for lbl in ["0.5x", "", "", "", "1.0x", "", "", "", "2.0x"]:
            l = QLabel(lbl)
            l.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            tick_layout.addWidget(l)
        layout.addLayout(tick_layout)

        # ---------------- Play / Stop / Loop ----------------
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

        # ======================================================================
        # TTS PRESET FILES
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
            if file_list.currentItem():
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
            "speaking_rate": self.speaking_rate,
            "loop": self.loop,
        })
        return data

    def deserialize(self, state):
        super().deserialize(state)
        self.text = state.get("text", "")
        self.current_voice = state.get("current_voice", "ap")
        self.pitch = state.get("pitch", 1.0)
        self.speaking_rate = state.get("speaking_rate", 1.0)
        self.loop = state.get("loop", False)
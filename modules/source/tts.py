import os
import numpy as np
import soundfile as sf
import tempfile
import gc
import subprocess
import platform

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, 
    QComboBox, QSlider, QListWidget, QCheckBox, QGroupBox, QSplitter,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt

from audio_module import AudioModule


class TTS(AudioModule):
    """Unified Text-to-speech generator module supporting pyttsx3 (default), Mycroft Mimic, and Festival engines."""

    ENGINE_DEFAULT = "default"
    ENGINE_MIMIC = "mimic"
    ENGINE_FESTIVAL = "festival"

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
        self.speaking_rate = 1.0

        # Preset files
        self.tts_files = []
        self.selected_file_lines = []

        # Initialize engines
        self._init_default_engine()
        self._init_mimic_engine()
        self._init_festival_engine()
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
                self.default_voices = [
                    v for v in all_voices
                    if "english" in v.name.lower() or "en_" in v.id.lower()
                ]
            else:
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
        self.mimic_voices = {
            "ap": "Alan Pope (male, British)",
            "slt": "Scottish female",
            "rms": "US male",
            "awb": "Scottish male",
        }
        self.mimic_voice_codes = list(self.mimic_voices.keys())
        self.mimic_voice = "ap"

    def _init_festival_engine(self):
        """Initialize Festival voices."""
        self.festival_voices = {}
        self.festival_voice_codes = []
        self.festival_voice = None
        self.festival_available = False

        # Only available on Linux
        if platform.system().lower() != "linux":
            return

        try:
            # Query available voices from Festival
            result = subprocess.run(
                ["festival", "--pipe"],
                input="(voice.list)",
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # Parse the voice list from Festival output
                # Output format is like: (kal_diphone cmu_us_slt_arctic_hts ...)
                output = result.stdout.strip()
                # Find the list in parentheses
                import re
                match = re.search(r'\(([^)]+)\)', output)
                if match:
                    voices = match.group(1).split()
                    for voice in voices:
                        voice = voice.strip()
                        if voice:
                            # Create friendly names
                            friendly = voice.replace('_', ' ').title()
                            self.festival_voices[voice] = friendly
                    
                    self.festival_voice_codes = list(self.festival_voices.keys())
                    if self.festival_voice_codes:
                        self.festival_voice = self.festival_voice_codes[0]
                        self.festival_available = True

        except FileNotFoundError:
            print("[TTS] Festival not found")
        except subprocess.TimeoutExpired:
            print("[TTS] Festival voice query timed out")
        except Exception as e:
            print(f"[TTS] Festival initialization failed: {e}")

        # Fallback: add common default voices if detection failed but festival exists
        if not self.festival_voices:
            try:
                # Check if festival command exists
                result = subprocess.run(
                    ["which", "festival"],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    # Add common default voices
                    self.festival_voices = {
                        "kal_diphone": "Kal Diphone (US male)",
                        "ked_diphone": "Ked Diphone (US male)",
                        "cmu_us_slt_arctic_hts": "CMU SLT (US female, HTS)",
                        "cmu_us_awb_arctic_hts": "CMU AWB (Scottish male, HTS)",
                        "cmu_us_rms_arctic_hts": "CMU RMS (US male, HTS)",
                    }
                    self.festival_voice_codes = list(self.festival_voices.keys())
                    self.festival_voice = "kal_diphone"
                    self.festival_available = True
            except:
                pass

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
        elif self.current_engine == self.ENGINE_FESTIVAL:
            self._generate_festival_audio(text)
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
            cmd = [
                "mimic",
                "-t", text,
                "-voice", self.mimic_voice,
                "-o", wav_path
            ]

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

    def _generate_festival_audio(self, text: str):
        """Generate audio using Festival TTS."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            wav_path = tmpfile.name

        try:
            # Escape special characters in text for Scheme
            escaped_text = text.replace('\\', '\\\\').replace('"', '\\"')
            
            # Build Festival Scheme script
            voice_cmd = f'(voice_{self.festival_voice})' if self.festival_voice else ''
            scheme_script = f'''
{voice_cmd}
(set! utt (Utterance Text "{escaped_text}"))
(utt.synth utt)
(utt.save.wave utt "{wav_path}")
'''

            # Run Festival with the script
            result = subprocess.run(
                ["festival", "--pipe"],
                input=scheme_script,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"[TTS] Festival error: {result.stderr}")
                return

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
                print("[TTS] Festival did not produce output file")
                return

            self._load_and_process_audio(wav_path, apply_speaking_rate=True)

        except subprocess.TimeoutExpired:
            print("[TTS] Festival command timed out")
        except FileNotFoundError:
            print("[TTS] ERROR: festival command not found. Install with: sudo apt install festival")
        except Exception as e:
            print("[TTS] Festival audio generation error:", e)
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

            if data.ndim == 1:
                data = np.column_stack((data, data))

            if apply_speaking_rate and self.speaking_rate != 1.0:
                new_len = int(len(data) / self.speaking_rate)
                if new_len > 0:
                    idx = np.linspace(0, len(data) - 1, num=new_len)
                    data = np.array([
                        np.interp(idx, np.arange(len(data)), data[:, 0]),
                        np.interp(idx, np.arange(len(data)), data[:, 1])
                    ]).T

            if self.pitch != 1.0:
                new_len = int(len(data) / self.pitch)
                if new_len > 0:
                    idx = np.linspace(0, len(data) - 1, num=new_len)
                    data = np.array([
                        np.interp(idx, np.arange(len(data)), data[:, 0]),
                        np.interp(idx, np.arange(len(data)), data[:, 1])
                    ]).T

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
    # UI - Redesigned
    # ==========================================================================
    def get_ui(self) -> QWidget:
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # =====================================================================
        # TOP SECTION: Text Input + Playback Controls (Primary Workflow)
        # =====================================================================
        input_frame = QFrame()
        input_frame.setFrameShape(QFrame.Shape.StyledPanel)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(6, 6, 6, 6)
        input_layout.setSpacing(4)

        # Text input - slightly taller for better visibility
        text_input = QTextEdit()
        text_input.setPlaceholderText("Enter text to speak, or select from presets below...")
        text_input.setFixedHeight(60)
        input_layout.addWidget(text_input)

        # Playback controls - horizontal, compact
        playback_row = QHBoxLayout()
        playback_row.setSpacing(4)

        play_btn = QPushButton("▶ Play")
        play_btn.setFixedWidth(70)
        stop_btn = QPushButton("■ Stop")
        stop_btn.setFixedWidth(70)
        loop_box = QCheckBox("Loop")

        play_btn.clicked.connect(lambda: self._play(text_input))
        stop_btn.clicked.connect(self._stop)
        loop_box.stateChanged.connect(lambda s: setattr(self, "loop", bool(s)))
        loop_box.setChecked(self.loop)

        playback_row.addWidget(play_btn)
        playback_row.addWidget(stop_btn)
        playback_row.addWidget(loop_box)
        playback_row.addStretch()

        input_layout.addLayout(playback_row)
        main_layout.addWidget(input_frame)

        # =====================================================================
        # MIDDLE SECTION: Collapsible Voice Settings
        # =====================================================================
        settings_group = QGroupBox("Voice Settings")
        settings_group.setCheckable(True)
        settings_group.setChecked(True)
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setContentsMargins(6, 8, 6, 6)
        settings_layout.setSpacing(4)

        # Engine + Voice row (horizontal to save space)
        engine_voice_row = QHBoxLayout()
        engine_voice_row.setSpacing(8)

        # Engine selector
        engine_col = QVBoxLayout()
        engine_col.setSpacing(2)
        engine_label = QLabel("Engine:")
        engine_label.setStyleSheet("font-size: 10px; color: #888;")
        engine_dropdown = QComboBox()
        engine_dropdown.addItem("pyttsx3", self.ENGINE_DEFAULT)
        engine_dropdown.addItem("Mimic", self.ENGINE_MIMIC)
        if platform.system().lower() == "linux":
            engine_dropdown.addItem("Festival", self.ENGINE_FESTIVAL)
        engine_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        engine_col.addWidget(engine_label)
        engine_col.addWidget(engine_dropdown)
        engine_voice_row.addLayout(engine_col)

        # Voice selector
        voice_col = QVBoxLayout()
        voice_col.setSpacing(2)
        voice_label = QLabel("Voice:")
        voice_label.setStyleSheet("font-size: 10px; color: #888;")
        
        # Stacked voice dropdowns (only one visible at a time)
        default_voice_dropdown = QComboBox()
        for v in self.default_voices:
            default_voice_dropdown.addItem(v.name)
        default_voice_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        mimic_voice_dropdown = QComboBox()
        for code in self.mimic_voice_codes:
            voice_name = self.mimic_voices[code]
            mimic_voice_dropdown.addItem(f"{voice_name}", code)
        mimic_voice_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        mimic_voice_dropdown.setVisible(False)

        # Festival voice dropdown
        festival_voice_dropdown = QComboBox()
        for code in self.festival_voice_codes:
            voice_name = self.festival_voices.get(code, code)
            festival_voice_dropdown.addItem(f"{voice_name}", code)
        festival_voice_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        festival_voice_dropdown.setVisible(False)

        def on_default_voice_changed(i):
            if 0 <= i < len(self.default_voices):
                self.default_voice = self.default_voices[i].id

        def on_mimic_voice_changed(i):
            self.mimic_voice = mimic_voice_dropdown.itemData(i)

        def on_festival_voice_changed(i):
            self.festival_voice = festival_voice_dropdown.itemData(i)

        default_voice_dropdown.currentIndexChanged.connect(on_default_voice_changed)
        mimic_voice_dropdown.currentIndexChanged.connect(on_mimic_voice_changed)
        festival_voice_dropdown.currentIndexChanged.connect(on_festival_voice_changed)

        voice_col.addWidget(voice_label)
        voice_col.addWidget(default_voice_dropdown)
        voice_col.addWidget(mimic_voice_dropdown)
        voice_col.addWidget(festival_voice_dropdown)
        engine_voice_row.addLayout(voice_col, stretch=2)

        settings_layout.addLayout(engine_voice_row)

        # Pitch + Rate sliders (horizontal)
        sliders_row = QHBoxLayout()
        sliders_row.setSpacing(12)

        # Pitch slider
        pitch_col = QVBoxLayout()
        pitch_col.setSpacing(2)
        pitch_label = QLabel(f"Pitch: {self.pitch:.2f}x")
        pitch_label.setStyleSheet("font-size: 10px;")
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
        pitch_col.addWidget(pitch_label)
        pitch_col.addWidget(pitch_slider)
        sliders_row.addLayout(pitch_col)

        # Speaking rate slider (Mimic only)
        rate_col = QVBoxLayout()
        rate_col.setSpacing(2)
        rate_label = QLabel(f"Rate: {self.speaking_rate:.2f}x")
        rate_label.setStyleSheet("font-size: 10px;")
        rate_slider = QSlider(Qt.Orientation.Horizontal)
        rate_slider.setMinimum(50)
        rate_slider.setMaximum(200)
        rate_slider.setValue(int(self.speaking_rate * 100))

        def on_rate_change(val):
            self.speaking_rate = val / 100.0
            rate_label.setText(f"Rate: {self.speaking_rate:.2f}x")

        rate_slider.valueChanged.connect(on_rate_change)
        rate_col.addWidget(rate_label)
        rate_col.addWidget(rate_slider)
        sliders_row.addLayout(rate_col)

        # Initially hide rate controls
        rate_label.setVisible(False)
        rate_slider.setVisible(False)

        settings_layout.addLayout(sliders_row)

        # Engine switch handler
        def on_engine_changed(i):
            engine_code = engine_dropdown.itemData(i)
            self.current_engine = engine_code
            
            is_mimic = (engine_code == self.ENGINE_MIMIC)
            is_festival = (engine_code == self.ENGINE_FESTIVAL)
            is_default = (engine_code == self.ENGINE_DEFAULT)

            # Toggle voice dropdowns
            default_voice_dropdown.setVisible(is_default)
            mimic_voice_dropdown.setVisible(is_mimic)
            festival_voice_dropdown.setVisible(is_festival)

            # Toggle speaking rate controls (Mimic and Festival support rate adjustment)
            rate_label.setVisible(is_mimic or is_festival)
            rate_slider.setVisible(is_mimic or is_festival)

        engine_dropdown.currentIndexChanged.connect(on_engine_changed)

        # Collapse/expand handling
        settings_content = QWidget()
        settings_content_layout = QVBoxLayout(settings_content)
        settings_content_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addWidget(settings_group)

        # =====================================================================
        # BOTTOM SECTION: File Browser (Priority Area - Gets Remaining Space)
        # =====================================================================
        browser_group = QGroupBox("Preset Text Files")
        browser_layout = QVBoxLayout(browser_group)
        browser_layout.setContentsMargins(6, 8, 6, 6)
        browser_layout.setSpacing(4)

        # Use a splitter for resizable file/line lists
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: File list
        file_container = QWidget()
        file_layout = QVBoxLayout(file_container)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(2)

        file_header = QLabel("Files:")
        file_header.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        file_layout.addWidget(file_header)

        file_list = QListWidget()
        file_list.addItems(self.tts_files)
        file_layout.addWidget(file_list)

        # Refresh button
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setFixedHeight(24)
        
        def refresh_files():
            self._scan_tts_folder()
            file_list.clear()
            file_list.addItems(self.tts_files)
        
        refresh_btn.clicked.connect(refresh_files)
        file_layout.addWidget(refresh_btn)

        splitter.addWidget(file_container)

        # Right: Line list
        line_container = QWidget()
        line_layout = QVBoxLayout(line_container)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(2)

        line_header = QLabel("Lines (click to use):")
        line_header.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        line_layout.addWidget(line_header)

        line_list = QListWidget()
        line_layout.addWidget(line_list)

        # Quick play button for selected line
        quick_play_btn = QPushButton("▶ Play Selected")
        quick_play_btn.setFixedHeight(24)
        
        def quick_play():
            if line_list.currentItem():
                text = line_list.currentItem().text()
                text_input.setText(text)
                self._play(text_input)
        
        quick_play_btn.clicked.connect(quick_play)
        line_layout.addWidget(quick_play_btn)

        splitter.addWidget(line_container)

        # Set initial splitter sizes (40% files, 60% lines)
        splitter.setSizes([150, 250])

        browser_layout.addWidget(splitter)

        # File click handler
        def on_file_clicked():
            if file_list.currentItem():
                fname = file_list.currentItem().text()
                self._load_file_lines(fname)
                line_list.clear()
                line_list.addItems(self.selected_file_lines)

        file_list.itemClicked.connect(lambda _: on_file_clicked())

        # Line click handler - insert into text box
        def on_line_clicked():
            if line_list.currentItem():
                text_input.setText(line_list.currentItem().text())

        line_list.itemClicked.connect(lambda _: on_line_clicked())

        # Double-click to play immediately
        def on_line_double_clicked():
            if line_list.currentItem():
                text_input.setText(line_list.currentItem().text())
                self._play(text_input)

        line_list.itemDoubleClicked.connect(lambda _: on_line_double_clicked())

        # Add browser group with stretch so it takes remaining space
        main_layout.addWidget(browser_group, stretch=1)

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
            "festival_voice": self.festival_voice,
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
        self.festival_voice = state.get("festival_voice", self.festival_voice)
        self.pitch = state.get("pitch", 1.0)
        self.speaking_rate = state.get("speaking_rate", 1.0)
        self.loop = state.get("loop", False)
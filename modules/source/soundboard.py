# modules/soundboard.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel,
    QGridLayout, QStackedWidget, QHBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from audio_module import AudioModule


class Soundboard(AudioModule):
    """Soundboard module with category-based browsing and playback."""

    SUPPORTED_EXTENSIONS = (".wav", ".flac", ".ogg", ".aiff", ".aif", ".mp3")

    def __init__(self, available_outputs=None):
        super().__init__(input_count=0, output_count=1)
        self.fs = 44100
        self.active_sounds = []
        self.sounds = {}  # {category: {filename: np.array}}
        self.available_outputs = available_outputs or []
        self.categories = []
        self.load_all_sounds()

    # ---------------------------
    # SOUND LOADING
    # ---------------------------
    def load_all_sounds(self):
        """Scan /sounds directory and load all supported audio files."""
        base_dir = os.path.join(os.path.dirname(__file__), "../..", "sounds")
        base_dir = os.path.abspath(base_dir)

        if not os.path.isdir(base_dir):
            print(f"[Soundboard] No sounds directory at {base_dir}")
            return

        for category in sorted(os.listdir(base_dir)):
            cat_path = os.path.join(base_dir, category)
            if not os.path.isdir(cat_path):
                continue

            cat_sounds = {}
            for fname in os.listdir(cat_path):
                if not fname.lower().endswith(self.SUPPORTED_EXTENSIONS):
                    continue

                path = os.path.join(cat_path, fname)
                try:
                    data, fs = sf.read(path, dtype="float32")

                    # Convert to stereo if mono
                    if data.ndim == 1:
                        data = np.column_stack((data, data))

                    # Resample to target sample rate
                    if fs != self.fs:
                        ratio = self.fs / fs
                        idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
                        idx = idx[idx < len(data)]
                        data = data[idx]

                    cat_sounds[fname] = data
                except RuntimeError:
                    # skip unsupported files
                    continue
                except Exception as e:
                    print(f"[Soundboard] Failed to load {fname}: {e}")

            if cat_sounds:
                self.sounds[category] = cat_sounds
                self.categories.append(category)

        if not self.categories:
            print("[Soundboard] No sound categories found.")

    # ---------------------------
    # AUDIO PROCESSING
    # ---------------------------
    def queue_sound(self, category, name):
        """Queue a sound from the specified category for playback."""
        if category not in self.sounds or name not in self.sounds[category]:
            return
        data = self.sounds[category][name].copy()
        self.active_sounds.append({"data": data, "pos": 0})

    def apply_effect(self, frames: int):
        """Mix active sounds into the output buffer."""
        out = np.zeros((frames, 2), dtype=np.float32)
        new_active = []

        for sound in self.active_sounds:
            start = sound["pos"]
            end = min(start + frames, len(sound["data"]))
            chunk = sound["data"][start:end]
            out[:len(chunk)] += chunk

            if end < len(sound["data"]):
                sound["pos"] = end
                new_active.append(sound)

        self.active_sounds = new_active
        return np.clip(out, -1.0, 1.0)

    def generate(self, frames: int):
        """Return the current mixed output."""
        return self.apply_effect(frames)

    # ---------------------------
    # UI
    # ---------------------------
    def get_ui(self) -> QWidget:
        """Return a UI with category list and category detail views."""
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # --- Category List Screen ---
        cat_screen = QWidget()
        cat_layout = QVBoxLayout()
        cat_screen.setLayout(cat_layout)

        title = QLabel("Select a Sound Category:")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        cat_layout.addWidget(title)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        cat_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_content.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_content)

        # Category buttons as vertical list
        for category in self.categories:
            btn = QPushButton(category.capitalize())
            btn.setFixedHeight(50)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #333;
                    color: white;
                    font-size: 16px;
                    border-radius: 8px;
                    text-align: left;
                    padding-left: 20px;
                }
                QPushButton:hover {
                    background-color: #555;
                }
            """)
            btn.clicked.connect(lambda _, c=category: self.show_category(c))
            scroll_layout.addWidget(btn)

        scroll_layout.addStretch()
        self.stack.addWidget(cat_screen)

        # Store built category screens
        self.category_views = {}

        # Fixed default size for 4x4 layout
        main_widget.setMinimumSize(QSize(480, 480))

        return main_widget

    def show_category(self, category):
        """Display sound buttons for the selected category."""
        if category in self.category_views:
            self.stack.setCurrentWidget(self.category_views[category])
            return

        cat_widget = QWidget()
        cat_layout = QVBoxLayout()
        cat_widget.setLayout(cat_layout)

        # Header with back button
        header = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(80)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        title = QLabel(f"{category.capitalize()} Sounds")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(back_btn)
        header.addWidget(title, 1)
        cat_layout.addLayout(header)

        # Scrollable 4x4 sound grid
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        cat_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        grid = QGridLayout()
        scroll_content.setLayout(grid)
        scroll_area.setWidget(scroll_content)

        row, col, max_cols = 0, 0, 4
        for fname in sorted(self.sounds[category].keys()):
            label = os.path.splitext(fname)[0]
            btn = QPushButton(label)
            btn.setFixedSize(100, 100)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #222;
                    color: white;
                    font-size: 14px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #444;
                }
            """)
            btn.clicked.connect(lambda _, c=category, n=fname: self.queue_sound(c, n))
            grid.addWidget(btn, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        # Ensure it supports more than 16 sounds with scrolling
        grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.stack.addWidget(cat_widget)
        self.category_views[category] = cat_widget
        self.stack.setCurrentWidget(cat_widget)

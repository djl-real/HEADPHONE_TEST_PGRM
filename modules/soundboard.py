# modules/soundboard.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel, QGridLayout, QComboBox
)
from audio_module import AudioModule


class Soundboard(AudioModule):
    """Soundboard generator compatible with modular patch system."""

    def __init__(self, available_outputs=None):
        super().__init__(has_input=False, has_output=True)
        self.fs = 44100
        self.active_sounds = []  # queued playback
        self.sounds = {}          # preloaded sounds
        self.available_outputs = available_outputs or []  # list of AudioModule targets

        self.output_node = getattr(self, "output_node", None) or None

        self.load_sounds()

    def load_sounds(self):
        """Preload WAV files from /sounds directory."""
        sounds_dir = os.path.join(os.path.dirname(__file__), "..", "sounds")
        sounds_dir = os.path.abspath(sounds_dir)

        if not os.path.isdir(sounds_dir):
            print(f"[Soundboard] No sounds directory at {sounds_dir}")
            return

        for fname in os.listdir(sounds_dir):
            if fname.lower().endswith(".wav"):
                path = os.path.join(sounds_dir, fname)
                try:
                    data, fs = sf.read(path, dtype="float32")
                    # Convert mono → stereo
                    if data.ndim == 1:
                        data = np.column_stack((data, data))
                    # Resample if needed
                    if fs != self.fs:
                        ratio = self.fs / fs
                        idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
                        idx = idx[idx < len(data)]
                        data = data[idx]
                    self.sounds[fname] = data
                except Exception as e:
                    print(f"[Soundboard] Failed to load {fname}: {e}")

    def queue_sound(self, name):
        """Queue sound for playback."""
        if name not in self.sounds:
            return
        data = self.sounds[name].copy()
        self.active_sounds.append({"data": data, "pos": 0})

    def apply_effect(self, frames: int):
        """Mix active sounds into output buffer."""
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
        """Module-compatible output for patch system."""
        return self.apply_effect(frames)

    def get_ui(self) -> QWidget:
        """Return QWidget with scrollable buttons for all sounds."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Scrollable area for buttons
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        container = QWidget()
        grid = QGridLayout()
        container.setLayout(grid)
        scroll_area.setWidget(container)

        # Add sound buttons
        row, col, max_cols = 0, 0, 4
        for fname in self.sounds.keys():
            label = os.path.splitext(fname)[0]
            btn = QPushButton(label)
            btn.setFixedSize(100, 100)
            btn.clicked.connect(lambda _, name=fname: self.queue_sound(name))
            grid.addWidget(btn, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        return widget

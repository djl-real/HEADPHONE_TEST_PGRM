# modules/soundboard.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea, QGridLayout, QComboBox
)
from module_base import ModuleWindow
from audio_module import AudioModule


class Soundboard(AudioModule):
    """Soundboard backend generator compatible with modular patch system."""

    def __init__(self, available_outputs=None):
        super().__init__("Soundboard")
        self.fs = 44100
        self.active_sounds = []  # queued playback
        self.sounds = {}
        self.available_outputs = available_outputs or []  # list of AudioModule targets

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
                    self.sounds[fname] = (data, fs)
                except Exception as e:
                    print(f"[Soundboard] Failed to load {fname}: {e}")

    def queue_sound(self, name):
        """Queue sound for playback."""
        if name not in self.sounds:
            return
        data, fs = self.sounds[name]

        # Resample if needed
        if fs != self.fs:
            ratio = self.fs / fs
            idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
            idx = idx[idx < len(data)]
            data = data[idx]

        # Ensure stereo
        if data.ndim == 1:
            data = np.column_stack((data, data))

        # Copy to avoid mutating original
        self.active_sounds.append({
            "data": data.copy(),
            "pos": 0,
            "channels": data.shape[1]
        })

    def apply_effect(self, input_signal: np.ndarray, frames: int) -> np.ndarray:
        """Mix all active sounds and apply volume/pan."""
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

        # Apply volume/pan
        out = self._apply_mixer_controls(out)
        return out


class SoundboardWindow(ModuleWindow):
    """Qt window for the Soundboard module with patch selection."""

    def __init__(self, mixer_callback, close_callback, available_outputs=None):
        super().__init__("Soundboard", mixer_callback, close_callback)

        # Backend generator
        self.soundboard = Soundboard(available_outputs)

        # --- UI ---
        self.content_layout.addWidget(QLabel("Soundboard"))

        # Patch selection
        self.output_combo = QComboBox()
        outputs = available_outputs or ["Main Output"]
        self.output_combo.addItems([out.name if hasattr(out, "name") else str(out) for out in outputs])
        self.content_layout.addWidget(QLabel("Patch Output"))
        self.content_layout.addWidget(self.output_combo)

        # Scroll area for sound buttons
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.content_layout.addWidget(scroll_area)

        container = QWidget()
        self.button_layout = QGridLayout()
        container.setLayout(self.button_layout)
        scroll_area.setWidget(container)

        self.populate_buttons()

    def populate_buttons(self):
        """Create buttons for each sound."""
        row, col, max_cols = 0, 0, 4
        for fname in self.soundboard.sounds.keys():
            label = os.path.splitext(fname)[0]
            btn = QPushButton(label)
            btn.setFixedSize(100, 100)
            btn.clicked.connect(lambda _, name=fname: self.soundboard.queue_sound(name))
            self.button_layout.addWidget(btn, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def get_samples(self, frames: int):
        """Delegate to backend Soundboard generator."""
        return self.soundboard.apply_effect(np.zeros((frames, 2)), frames)

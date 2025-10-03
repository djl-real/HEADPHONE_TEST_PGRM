# modules/soundboard.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QScrollArea, QGridLayout

from module_base import ModuleWindow

class Soundboard(ModuleWindow):
    """Soundboard module with low-latency playback, integrated with mixer."""

    def __init__(self, mixer_callback, close_callback):
        # --- Mixer/audio params ---
        self.volume = -60.0       # dB (muted)
        self.pan = 0.0            # -1 left → +1 right
        self.fs = 44100           # default sample rate

        # Active playback list
        self.active_sounds = []

        super().__init__("Soundboard", mixer_callback, close_callback)

        # --- UI ---
        self.content_layout.addWidget(QLabel("Soundboard"))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.content_layout.addWidget(scroll_area)

        container = QWidget()
        self.button_layout = QGridLayout()  # use grid layout
        container.setLayout(self.button_layout)
        scroll_area.setWidget(container)

        # Load sounds from /sounds folder
        self.sounds = {}
        self.load_sounds()

    def load_sounds(self):
        """Scan /sounds folder and preload WAVs into memory."""
        sounds_dir = os.path.join(os.path.dirname(__file__), "..", "sounds")
        sounds_dir = os.path.abspath(sounds_dir)

        if not os.path.isdir(sounds_dir):
            print(f"[Soundboard] No sounds directory found at {sounds_dir}")
            return

        row = 0
        col = 0
        max_cols = 4  # 4x? grid

        for fname in os.listdir(sounds_dir):
            if fname.lower().endswith(".wav"):
                path = os.path.join(sounds_dir, fname)
                try:
                    data, fs = sf.read(path, dtype="float32")
                    self.sounds[fname] = (data, fs)

                    # Remove .wav from label
                    label = os.path.splitext(fname)[0]
                    btn = QPushButton(label)
                    btn.setFixedSize(100, 100)  # square buttons
                    btn.clicked.connect(lambda _, name=fname: self.queue_sound(name))

                    self.button_layout.addWidget(btn, row, col)
                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1

                except Exception as e:
                    print(f"[Soundboard] Failed to load {fname}: {e}")

    def queue_sound(self, name):
        """Queue a sound for playback (non-blocking)."""
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

        # Apply gain (volume in dB) and pan
        gain_linear = 10 ** (self.volume / 20.0)
        left_gain = gain_linear * (1 - max(0, self.pan))
        right_gain = gain_linear * (1 - max(0, -self.pan))
        data = data.copy()
        data[:, 0] *= left_gain
        data[:, 1] *= right_gain

        # Add to active sounds
        self.active_sounds.append({
            "data": data,
            "pos": 0,
            "channels": data.shape[1]
        })

    def get_samples(self, frames: int):
        """Called by mixer; mix all active sounds into buffer."""
        out = np.zeros((frames, 2), dtype=np.float32)
        new_active = []

        for sound in self.active_sounds:
            start = sound["pos"]
            end = min(start + frames, len(sound["data"]))
            chunk = sound["data"][start:end]

            # Mix chunk into output buffer
            out[:len(chunk)] += chunk

            # Update position
            if end < len(sound["data"]):
                sound["pos"] = end
                new_active.append(sound)  # still playing

        self.active_sounds = new_active

        # Clip to [-1, 1]
        np.clip(out, -1.0, 1.0, out=out)
        return out

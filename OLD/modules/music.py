# modules/music.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QLabel, QSlider
)
from PyQt6.QtCore import Qt
from module_base import ModuleWindow

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg")


class Music(ModuleWindow):
    def __init__(self, mixer_callback, close_callback):
        # Mixer parameters
        self.volume = -60.0  # dB
        self.pan = 0.0       # -1 left → +1 right

        # Playback state
        self.playing = False
        self.current_index = None
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0       # float index into current track
        self.pitch = 1.0          # speed factor (1.0 = normal)
        self.songs = []

        super().__init__("Music", mixer_callback, close_callback)

        # --- UI ---
        self.content_layout.addWidget(QLabel("Music Player"))

        self.list_widget = QListWidget()
        self.content_layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.toggle_play)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_playback)
        btn_layout.addWidget(self.play_btn)
        btn_layout.addWidget(self.stop_btn)
        self.content_layout.addLayout(btn_layout)

        # Pitch slider
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setMinimum(50)   # 0.5x
        self.pitch_slider.setMaximum(200)  # 2x
        self.pitch_slider.setValue(100)    # 1x
        self.pitch_slider.valueChanged.connect(self.update_pitch)
        self.content_layout.addWidget(QLabel("Pitch"))
        self.content_layout.addWidget(self.pitch_slider)

        # Load playlist
        self.load_playlist()

    def load_playlist(self):
        playlist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playlist"))
        if not os.path.exists(playlist_dir):
            os.makedirs(playlist_dir)

        for fname in os.listdir(playlist_dir):
            if fname.lower().endswith(AUDIO_EXTENSIONS):
                path = os.path.join(playlist_dir, fname)
                self.list_widget.addItem(fname)
                try:
                    data, fs = sf.read(path, dtype="float32")
                    if data.ndim == 1:
                        data = np.column_stack((data, data))  # stereo
                    # resample to module sample rate if needed
                    if fs != 44100:
                        ratio = 44100 / fs
                        idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
                        idx = idx[idx < len(data)]
                        data = data[idx]
                    self.songs.append(data)
                except Exception as e:
                    print(f"[Music] Failed to load {fname}: {e}")

    def toggle_play(self):
        if self.playing:
            self.playing = False
            self.play_btn.setText("Play")
        else:
            self.playing = True
            self.play_btn.setText("Pause")
            self.current_index = self.list_widget.currentRow()
            if self.current_index >= 0:
                self.playhead = 0.0
                self.play_buffer = self.songs[self.current_index]

    def stop_playback(self):
        self.playing = False
        self.play_btn.setText("Play")
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0

    def update_pitch(self, value):
        self.pitch = value / 100.0  # slider 50–200 → 0.5x–2x

    def get_samples(self, frames: int):
        if not self.playing or self.current_index is None:
            return np.zeros((frames, 2), dtype=np.float32)

        track = self.songs[self.current_index]
        out = np.zeros((frames, 2), dtype=np.float32)

        for i in range(frames):
            idx = int(self.playhead)
            if idx >= len(track) - 1:
                self.playing = False
                self.play_btn.setText("Play")
                break

            # linear interpolation for fractional index
            next_idx = idx + 1
            frac = self.playhead - idx
            sample = (1 - frac) * track[idx] + frac * track[next_idx]
            out[i] = sample
            self.playhead += self.pitch

        # Apply module volume and pan
        gain = 10 ** (self.volume / 20.0)
        left_gain = gain * (1 - max(0, self.pan))
        right_gain = gain * (1 - max(0, -self.pan))
        out[:, 0] *= left_gain
        out[:, 1] *= right_gain

        return out

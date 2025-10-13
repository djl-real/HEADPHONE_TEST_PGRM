# modules/music.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QLabel, QSlider
)
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import OutputNode

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg")


class Music(AudioModule):
    """Music player module with pitch, pan, and selectable track."""

    def __init__(self, sample_rate=44100):
        super().__init__(has_input=False, has_output=True)
        self.sample_rate = sample_rate
        self.output_node = OutputNode(self)

        # Playback state
        self.playing = False
        self.current_index = None
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0
        self.pitch = 1.0      # speed factor
        self.pan = 0.0        # -1 left → +1 right
        self.volume = -6.0    # dB
        self.songs = []
        self.song_names = []

        # Load playlist
        self.load_playlist()

    def load_playlist(self):
        playlist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playlist"))
        if not os.path.exists(playlist_dir):
            os.makedirs(playlist_dir)

        self.songs.clear()
        self.song_names.clear()

        for fname in os.listdir(playlist_dir):
            if fname.lower().endswith(AUDIO_EXTENSIONS):
                path = os.path.join(playlist_dir, fname)
                try:
                    data, fs = sf.read(path, dtype="float32")
                    if data.ndim == 1:
                        data = np.column_stack((data, data))
                    if fs != self.sample_rate:
                        # simple resample by linear interpolation
                        ratio = self.sample_rate / fs
                        idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
                        idx = idx[idx < len(data)]
                        data = data[idx]
                    self.songs.append(data)
                    self.song_names.append(fname)
                except Exception as e:
                    print(f"[Music] Failed to load {fname}: {e}")

    def toggle_play(self, index: int):
        if self.playing and self.current_index == index:
            self.playing = False
        else:
            self.playing = True
            self.current_index = index
            self.playhead = 0.0
            if index < len(self.songs):
                self.play_buffer = self.songs[index]

    def stop_playback(self):
        self.playing = False
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0

    def generate(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)
        if not self.playing or self.current_index is None or self.current_index >= len(self.songs):
            return out

        track = self.play_buffer
        for i in range(frames):
            idx = int(self.playhead)
            if idx >= len(track) - 1:
                self.playing = False
                break
            next_idx = idx + 1
            frac = self.playhead - idx
            sample = (1 - frac) * track[idx] + frac * track[next_idx]
            out[i] = sample
            self.playhead += self.pitch

        # Apply volume and pan
        gain = 10 ** (self.volume / 20.0)
        left_gain = gain * (1 - max(0, self.pan))
        right_gain = gain * (1 - max(0, -self.pan))
        out[:, 0] *= left_gain
        out[:, 1] *= right_gain
        return out.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return a QWidget with playlist, pitch, and pan controls."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Playlist
        self.list_widget = QListWidget()
        for name in self.song_names:
            self.list_widget.addItem(name)
        layout.addWidget(self.list_widget)

        # Play / Stop buttons
        btn_layout = QHBoxLayout()
        play_btn = QPushButton("Play/Pause")
        stop_btn = QPushButton("Stop")
        btn_layout.addWidget(play_btn)
        btn_layout.addWidget(stop_btn)
        layout.addLayout(btn_layout)

        def on_play():
            idx = self.list_widget.currentRow()
            if idx >= 0:
                self.toggle_play(idx)
        play_btn.clicked.connect(on_play)
        stop_btn.clicked.connect(self.stop_playback)

        # Pitch slider
        layout.addWidget(QLabel("Pitch"))
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setMinimum(50)
        pitch_slider.setMaximum(200)
        pitch_slider.setValue(int(self.pitch * 100))
        layout.addWidget(pitch_slider)

        def on_pitch_change(val):
            self.pitch = val / 100.0
        pitch_slider.valueChanged.connect(on_pitch_change)

        return widget

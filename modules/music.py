# modules/music.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QLabel, QSlider, QCheckBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer
from audio_module import AudioModule
from nodes import OutputNode

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg")


class Music(AudioModule):
    """Music player module with playlist, scrubbing, reverse, and automix support."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate

        # Playback state
        self.playing = False
        self.current_index = None
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0
        self.pitch = 1.0
        self.pan = 0.0
        self.volume = -6.0
        self.reverse = False
        self.automix = False
        self.crossfade_time = 2.0  # seconds

        # Data
        self.songs = []
        self.song_names = []

        self.load_playlist()

    # --- Playlist Management ---
    def load_playlist(self):
        playlist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playlist"))
        os.makedirs(playlist_dir, exist_ok=True)

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
                        ratio = self.sample_rate / fs
                        idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
                        idx = idx[idx < len(data)]
                        data = data[idx]
                    self.songs.append(data)
                    self.song_names.append(fname)
                except Exception as e:
                    print(f"[Music] Failed to load {fname}: {e}")

    # --- Playback Logic ---
    def toggle_play(self, index: int):
        """Play or pause; reset only when switching tracks."""
        if self.current_index == index:
            self.playing = not self.playing
        else:
            self.current_index = index
            self.play_buffer = self.songs[index]
            self.playhead = 0.0 if not self.reverse else len(self.play_buffer) - 1
            self.playing = True

    def stop_playback(self):
        self.playing = False
        self.playhead = 0.0

    def next_track(self):
        if self.current_index is not None and self.current_index + 1 < len(self.songs):
            self.toggle_play(self.current_index + 1)

    def generate(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)
        if not self.playing or self.current_index is None or self.current_index >= len(self.songs):
            return out

        track = self.play_buffer
        for i in range(frames):
            idx = int(self.playhead)
            if idx < 0 or idx >= len(track) - 1:
                self.playing = False
                if self.automix:
                    self.next_track()
                break

            next_idx = idx + (1 if not self.reverse else -1)
            frac = abs(self.playhead - idx)
            sample = (1 - frac) * track[idx] + frac * track[next_idx]
            out[i] = sample
            self.playhead += self.pitch * (-1 if self.reverse else 1)

        # Apply volume and pan
        gain = 10 ** (self.volume / 20.0)
        left_gain = gain * (1 - max(0, self.pan))
        right_gain = gain * (1 - max(0, -self.pan))
        out[:, 0] *= left_gain
        out[:, 1] *= right_gain
        return out.astype(np.float32)

    # --- UI ---
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Playlist (drag reorder)
        self.list_widget = QListWidget()
        for name in self.song_names:
            self.list_widget.addItem(name)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        layout.addWidget(self.list_widget)

        # Buttons: Play/Pause, Stop, Reverse
        btn_layout = QHBoxLayout()
        play_btn = QPushButton("Play/Pause")
        stop_btn = QPushButton("Stop")
        reverse_btn = QPushButton("Reverse")
        btn_layout.addWidget(play_btn)
        btn_layout.addWidget(stop_btn)
        btn_layout.addWidget(reverse_btn)
        layout.addLayout(btn_layout)

        play_btn.clicked.connect(lambda: self.toggle_play(self.list_widget.currentRow()))
        stop_btn.clicked.connect(self.stop_playback)
        reverse_btn.clicked.connect(lambda: setattr(self, "reverse", not self.reverse))

        # Pitch slider
        layout.addWidget(QLabel("Pitch"))
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setMinimum(50)
        pitch_slider.setMaximum(200)
        pitch_slider.setValue(int(self.pitch * 100))
        layout.addWidget(pitch_slider)
        pitch_slider.valueChanged.connect(lambda val: setattr(self, "pitch", val / 100.0))

        # --- Scrub slider (live playhead + auto update) ---
        layout.addWidget(QLabel("Scrub"))
        self.scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setMinimum(0)
        self.scrub_slider.setMaximum(1000)
        layout.addWidget(self.scrub_slider)

        self.scrubbing_user = False

        def on_scrub_start():
            self.scrubbing_user = True

        def on_scrub_end():
            self.scrubbing_user = False
            on_scrub(self.scrub_slider.value())

        def on_scrub(val):
            if self.current_index is not None and self.current_index < len(self.songs):
                track_len = len(self.songs[self.current_index])
                self.playhead = (val / 1000.0) * track_len

        self.scrub_slider.sliderPressed.connect(on_scrub_start)
        self.scrub_slider.sliderReleased.connect(on_scrub_end)
        self.scrub_slider.valueChanged.connect(lambda val: on_scrub(val) if self.scrubbing_user else None)

        # --- Timer for updating scrub slider ---
        self.update_timer = QTimer()
        self.update_timer.setInterval(50)  # 20 updates per second
        self.update_timer.timeout.connect(self.update_scrub_slider)
        self.update_timer.start()

        # Automix controls
        layout.addWidget(QLabel("Automix"))
        automix_check = QCheckBox("Enable Automix")
        layout.addWidget(automix_check)
        automix_check.stateChanged.connect(lambda s: setattr(self, "automix", s == Qt.CheckState.Checked))

        self.crossfade_label = QLabel(f"Crossfade: {self.crossfade_time:.1f}s")
        layout.addWidget(self.crossfade_label)
        crossfade_slider = QSlider(Qt.Orientation.Horizontal)
        crossfade_slider.setMinimum(0)
        crossfade_slider.setMaximum(10)
        crossfade_slider.setValue(int(self.crossfade_time))
        layout.addWidget(crossfade_slider)
        crossfade_slider.valueChanged.connect(self.on_crossfade_change)

        return widget


    # --- Helper method to update scrub position ---
    def update_scrub_slider(self):
        if not hasattr(self, "scrub_slider") or self.scrub_slider is None:
            return
        if not self.scrubbing_user and self.playing and self.current_index is not None:
            track = self.songs[self.current_index]
            if len(track) > 0:
                progress = np.clip(self.playhead / len(track), 0.0, 1.0)
                self.scrub_slider.blockSignals(True)
                self.scrub_slider.setValue(int(progress * 1000))
                self.scrub_slider.blockSignals(False)


    # --- Helper method for crossfade label ---
    def on_crossfade_change(self, val):
        self.crossfade_time = float(val)
        self.crossfade_label.setText(f"Crossfade: {val:.1f}s")

    def cleanup(self):
            # Stop the timer to avoid calling a deleted slider
        if hasattr(self, "update_timer") and self.update_timer.isActive():
            self.update_timer.stop()
        self.update_timer = None
        self.cleanup()
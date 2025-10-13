# modules/music.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel,
    QSlider, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer
from audio_module import AudioModule

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg")
MAX_BLOCK_HOLD = 15  # Maximum number of blocks to store for hold


class Music(AudioModule):
    """Music player module with playlist, scrubbing, reverse, and hold buffer support."""

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
        self.hold_active = False

        # Hold buffer
        self.block_hold = 10
        self.hold_buffer = [np.zeros((512, 2), dtype=np.float32) for _ in range(MAX_BLOCK_HOLD)]
        self.hold_pointer = 0

        # Scrub user flag
        self.scrubbing_user = False

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
        if self.current_index == index:
            self.playing = not self.playing
        else:
            self.current_index = index
            self.play_buffer = self.songs[index]
            self.playhead = 0.0 if not self.reverse else len(self.play_buffer) - 1
            self.playing = True
            self.hold_buffer = [np.zeros_like(self.hold_buffer[0]) for _ in range(MAX_BLOCK_HOLD)]
            self.hold_pointer = 0

    def stop_playback(self):
        self.playing = False
        self.playhead = 0.0
        self.hold_buffer = [np.zeros_like(self.hold_buffer[0]) for _ in range(MAX_BLOCK_HOLD)]
        self.hold_pointer = 0

    def generate(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)
        if self.current_index is None or self.current_index >= len(self.songs):
            return out

        if self.hold_active:
            # Replay last block_hold blocks
            for i in range(frames):
                sample_idx = i % self.hold_buffer[0].shape[0]
                out[i] = self.hold_buffer[self.hold_pointer][sample_idx]
            self.hold_pointer = (self.hold_pointer + 1) % self.block_hold
            return out.astype(np.float32)

        if not self.playing:
            return out

        track = self.play_buffer
        block = np.zeros((frames, 2), dtype=np.float32)

        for i in range(frames):
            idx = int(self.playhead)
            if idx < 0 or idx >= len(track) - 1:
                self.playing = False
                break
            next_idx = idx + (1 if not self.reverse else -1)
            frac = abs(self.playhead - idx)
            sample = (1 - frac) * track[idx] + frac * track[next_idx]
            block[i] = sample
            self.playhead += self.pitch * (-1 if self.reverse else 1)

        # Apply volume and pan
        gain = 10 ** (self.volume / 20.0)
        left_gain = gain * (1 - max(0, self.pan))
        right_gain = gain * (1 - max(0, -self.pan))
        block[:, 0] *= left_gain
        block[:, 1] *= right_gain

        # Add block to hold buffer, cycling pointer
        self.hold_buffer[self.hold_pointer % MAX_BLOCK_HOLD] = block.copy()
        self.hold_pointer = (self.hold_pointer + 1) % MAX_BLOCK_HOLD

        return block.astype(np.float32)

    # --- UI ---
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Playlist
        self.list_widget = QListWidget()
        for name in self.song_names:
            self.list_widget.addItem(name)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        layout.addWidget(QLabel("Playlist"))
        layout.addWidget(self.list_widget)

        # Buttons
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

        # Scrub slider
        layout.addWidget(QLabel("Scrub"))
        self.scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setMinimum(0)
        self.scrub_slider.setMaximum(1000)
        layout.addWidget(self.scrub_slider)

        def on_scrub_start():
            self.scrubbing_user = True

        def on_scrub_end():
            self.scrubbing_user = False
            self.update_playhead_from_scrub(self.scrub_slider.value())

        def on_scrub(val):
            if self.scrubbing_user:
                self.update_playhead_from_scrub(val)

        self.scrub_slider.sliderPressed.connect(on_scrub_start)
        self.scrub_slider.sliderReleased.connect(on_scrub_end)
        self.scrub_slider.valueChanged.connect(on_scrub)

        # Hold slider + button
        hold_layout = QHBoxLayout()
        self.hold_slider = QSlider(Qt.Orientation.Vertical)
        self.hold_slider.setMinimum(0)
        self.hold_slider.setMaximum(MAX_BLOCK_HOLD)
        self.hold_slider.setValue(self.block_hold)
        self.hold_slider.setToolTip("Number of blocks to hold")
        hold_layout.addWidget(self.hold_slider)

        self.hold_button = QPushButton("Hold")
        self.hold_button.setCheckable(True)
        self.hold_button.setFixedSize(50, 50)
        self.hold_button.setStyleSheet("""
            QPushButton {
                border-radius: 25px;
                background-color: #3498db;
                color: white;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #2ecc71;
            }
        """)
        hold_layout.addWidget(self.hold_button)

        layout.addLayout(hold_layout)

        self.hold_slider.valueChanged.connect(lambda val: setattr(self, "block_hold", val))
        self.hold_button.toggled.connect(lambda state: setattr(self, "hold_active", state))

        # Timer for scrub slider
        self.update_timer = QTimer(widget)
        self.update_timer.setInterval(50)
        self.update_timer.timeout.connect(self.update_scrub_slider)
        self.update_timer.start()

        return widget

    def update_playhead_from_scrub(self, val):
        if self.current_index is not None and 0 <= self.current_index < len(self.songs):
            track_len = len(self.songs[self.current_index])
            self.playhead = (val / 1000.0) * track_len

    def update_scrub_slider(self):
        if not hasattr(self, "scrub_slider") or self.scrub_slider is None:
            return
        if not self.scrubbing_user and self.playing and self.current_index is not None:
            track = self.songs[self.current_index]
            if len(track) > 0:
                progress = min(max(self.playhead / len(track), 0.0), 1.0)
                self.scrub_slider.blockSignals(True)
                self.scrub_slider.setValue(int(progress * 1000))
                self.scrub_slider.blockSignals(False)

    def cleanup(self):
        if hasattr(self, "update_timer") and self.update_timer is not None:
            self.update_timer.stop()
            self.update_timer.deleteLater()
            self.update_timer = None

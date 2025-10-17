# modules/music.py
import os
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel,
    QSlider, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontDatabase
from audio_module import AudioModule
import mutagen

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg")


class Music(AudioModule):
    """Music player module with playlist, scrubbing, reverse, and pitch control."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate

        # Playback state
        self.playing = False
        self.current_index = None
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0
        self.pitch = 1.0
        self.reverse = False
        self.scrubbing_user = False

        # Data
        self.songs = []               # Will hold np.ndarray or None (lazy)
        self.song_names = []          # Filenames
        self.song_display_texts = []  # Monospace display
        self.list_widget = None       # Will be created in get_ui()

        # Load playlist immediately
        self.load_playlist()

    # --- Playlist scanning ---
    def load_playlist(self):
        """Scan playlist folder, load metadata only for responsiveness."""
        playlist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playlist"))
        os.makedirs(playlist_dir, exist_ok=True)

        self.songs.clear()
        self.song_names.clear()
        self.song_display_texts.clear()

        MAX_TITLE_LEN = 15
        MAX_ARTIST_LEN = 15

        for fname in os.listdir(playlist_dir):
            if fname.lower().endswith(AUDIO_EXTENSIONS):
                path = os.path.join(playlist_dir, fname)
                try:
                    # --- Metadata ---
                    title = os.path.splitext(fname)[0]
                    artist = "Unknown Artist"
                    length_seconds = 0
                    try:
                        meta = mutagen.File(path, easy=True)
                        if meta:
                            title = meta.get("title", [title])[0]
                            artist = meta.get("artist", [artist])[0]
                            if hasattr(meta, "info") and hasattr(meta.info, "length"):
                                length_seconds = int(meta.info.length)
                    except Exception:
                        pass

                    # Clean and pad
                    title = (title.strip()[:MAX_TITLE_LEN-1] + "…") if len(title) > MAX_TITLE_LEN else title.ljust(MAX_TITLE_LEN)
                    artist = (artist.strip()[:MAX_ARTIST_LEN-1] + "…") if len(artist) > MAX_ARTIST_LEN else artist.ljust(MAX_ARTIST_LEN)

                    mins, secs = divmod(length_seconds, 60)
                    duration = f"{mins:02d}:{secs:02d}"

                    display_text = f"{title} {artist} {duration}"
                    self.song_display_texts.append(display_text)
                    self.song_names.append(fname)
                    self.songs.append(None)  # Placeholder for lazy loading

                except Exception as e:
                    print(f"[Music] Failed to scan {fname}: {e}")

        # Populate UI list if it exists
        self.populate_list_widget()

    def populate_list_widget(self):
        """Populate the QListWidget with song display texts."""
        if self.list_widget is not None:
            self.list_widget.clear()
            for display_text in self.song_display_texts:
                self.list_widget.addItem(display_text)

    # --- Lazy audio loading ---
    def load_audio_file(self, index):
        """Load audio data into memory only when needed."""
        if self.songs[index] is not None:
            return self.songs[index]

        fname = self.song_names[index]
        path = os.path.join(os.path.dirname(__file__), "..", "playlist", fname)
        data, fs = sf.read(path, dtype="float32")
        if data.ndim == 1:
            data = np.column_stack((data, data))
        if fs != self.sample_rate:
            ratio = self.sample_rate / fs
            idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
            idx = idx[idx < len(data)]
            data = data[idx]
        self.songs[index] = data
        return data

    # --- Playback ---
    def toggle_play(self, index: int):
        if index < 0 or index >= len(self.songs):
            return

        if self.current_index == index and self.play_buffer is not None:
            self.playing = not self.playing
        else:
            self.current_index = index
            self.play_buffer = self.load_audio_file(index)
            self.playhead = 0.0 if not self.reverse else len(self.play_buffer) - 1
            self.playing = True

    def stop_playback(self):
        self.playing = False
        self.playhead = 0.0

    def generate(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)
        if self.current_index is None or not self.playing:
            return out

        track = self.play_buffer
        n_samples = len(track)
        if n_samples < 2:
            return out

        # Compute all fractional indices for this block
        step = self.pitch * (-1 if self.reverse else 1)
        indices = self.playhead + step * np.arange(frames)
        
        # Clamp indices to track boundaries
        valid_mask = (indices >= 0) & (indices < n_samples - 1)
        indices_clamped = np.clip(indices, 0, n_samples - 2)

        # Vectorized linear interpolation
        idx_floor = np.floor(indices_clamped).astype(int)
        frac = indices_clamped - idx_floor
        out[valid_mask] = (1 - frac[valid_mask, None]) * track[idx_floor[valid_mask]] + \
                        frac[valid_mask, None] * track[idx_floor[valid_mask] + 1]

        # Update playhead for next block
        self.playhead += step * frames

        # Stop if reached end or beginning
        if self.playhead >= n_samples - 1 or self.playhead <= 0:
            self.playing = False
            self.playhead = max(0, min(self.playhead, n_samples - 1))

        return out


    # --- UI ---
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Playlist
        self.list_widget = QListWidget()
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(11)
        self.list_widget.setFont(mono_font)
        self.list_widget.setMinimumWidth(350)
        # self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        layout.addWidget(QLabel("Playlist"))
        layout.addWidget(self.list_widget)

        # Populate list now that the widget exists
        self.populate_list_widget()

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
        pitch_slider.setMinimum(0)
        pitch_slider.setMaximum(100)

        def slider_to_pitch(val):
            s = val / 100.0
            return 0.5 * (4 ** s)

        def pitch_to_slider(pitch):
            s = np.log2(pitch / 0.5) / 2
            return int(s * 100)

        pitch_slider.setValue(pitch_to_slider(self.pitch))
        pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        pitch_slider.setTickInterval(25)
        layout.addWidget(pitch_slider)
        pitch_slider.valueChanged.connect(lambda val: setattr(self, "pitch", slider_to_pitch(val)))

        tick_layout = QHBoxLayout()
        for lbl in ["0.5", "", "", "", "1.0", "", "", "", "2.0"]:
            l = QLabel(lbl)
            l.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            tick_layout.addWidget(l)
        layout.addLayout(tick_layout)

        # Scrub slider + label
        self.scrub_label = QLabel("Remaining: 00:00")
        layout.addWidget(self.scrub_label)
        self.scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setMinimum(0)
        self.scrub_slider.setMaximum(1000)
        layout.addWidget(self.scrub_slider)

        def on_scrub_start(): self.scrubbing_user = True
        def on_scrub_end():
            self.scrubbing_user = False
            self.update_playhead_from_scrub(self.scrub_slider.value())
        def on_scrub(val):
            if self.scrubbing_user:
                self.update_playhead_from_scrub(val)

        self.scrub_slider.sliderPressed.connect(on_scrub_start)
        self.scrub_slider.sliderReleased.connect(on_scrub_end)
        self.scrub_slider.valueChanged.connect(on_scrub)

        # Timer for UI updates
        self.update_timer = QTimer(widget)
        self.update_timer.setInterval(50)

        def update_scrub_and_countdown():
            if not self.scrubbing_user and self.playing and self.current_index is not None:
                track = self.play_buffer
                if track is not None and len(track) > 0:
                    progress = min(max(self.playhead / len(track), 0.0), 1.0)
                    self.scrub_slider.blockSignals(True)
                    self.scrub_slider.setValue(int(progress * 1000))
                    self.scrub_slider.blockSignals(False)

                    remaining_samples = len(track) - int(self.playhead)
                    remaining_seconds = remaining_samples / self.sample_rate
                    mins, secs = divmod(int(remaining_seconds), 60)
                    self.scrub_label.setText(f"Remaining: {mins:02d}:{secs:02d}")

        self.update_timer.timeout.connect(update_scrub_and_countdown)
        self.update_timer.start()

        return widget

    # --- Helpers ---
    def update_playhead_from_scrub(self, val):
        if self.current_index is not None and 0 <= self.current_index < len(self.songs):
            track = self.songs[self.current_index]
            if track is not None:
                self.playhead = (val / 1000.0) * len(track)

    def cleanup(self):
        if hasattr(self, "update_timer") and self.update_timer is not None:
            self.update_timer.stop()
            self.update_timer.deleteLater()
            self.update_timer = None

import os
import re
import numpy as np
import soundfile as sf
import librosa
import threading
import traceback
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QStackedWidget, QDoubleSpinBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage
from audio_module import AudioModule
import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC, Picture

# Import custom widgets
from modules.source.music.cue_waveform_visualizer import CueWaveformVisualizer
from modules.source.music.record import Record
from modules.source.music.playlist import Playlist

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a")

def detect_bpm(path):
    """Fast BPM detector using onset envelope autocorrelation."""
    try:
        y, sr = librosa.load(path, mono=True, sr=8000, duration=30)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr, aggregate=None)
        return int(tempo[0]) if len(tempo) > 0 else None
    except Exception as e:
        traceback.print_exc()
        return None

def extract_album_art(path):
    """Extract album art from audio file."""
    try:
        audio = mutagen.File(path)
        
        if isinstance(audio, ID3) or hasattr(audio, 'tags') and isinstance(audio.tags, ID3):
            # MP3 files
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    image_data = tag.data
                    image = QImage.fromData(image_data)
                    return QPixmap.fromImage(image)
        
        elif isinstance(audio, MP4):
            # M4A/MP4 files
            if 'covr' in audio.tags:
                cover_data = audio.tags['covr'][0]
                image = QImage.fromData(cover_data)
                return QPixmap.fromImage(image)
        
        elif isinstance(audio, FLAC):
            # FLAC files
            if audio.pictures:
                pic_data = audio.pictures[0].data
                image = QImage.fromData(pic_data)
                return QPixmap.fromImage(image)
        
    except Exception as e:
        pass
    
    return None


class Music(AudioModule):
    """VirtualDJ-style music player with vinyl interface and cue system."""

    def __init__(self, sample_rate=44100):
        super().__init__(
            input_count=1,
            output_count=2,
            input_types=["cue"],
            output_types=["audio", "cue"],
            input_colors=["#B8860B"],
            output_colors=[None, "#FFFF00"],
            input_positions=["left"],
            output_positions=[None, "right"],
            input_labels=["Cue In"],
            output_labels=["Audio", "Cue Out"]
        )
        self.sample_rate = sample_rate

        # Playback state
        self.playing = False
        self.current_index = None
        self.selected_index = None  # Currently selected (not necessarily playing)
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0
        self.pitch = 1.0
        self.reverse = False
        self.loop = False
        self.scrubbing_user = False
        self.song_bpm = None

        # Cue system
        self.cue_time = -5.0
        self.cue_sent = False
        self.current_cue_out = None
        
        # Crossfade system
        self.crossfade_duration = 0.0  # 0 = disabled
        self.crossfade_active = False
        self.crossfade_progress = 0.0  # 0.0 to 1.0
        self.fade_in_mode = False  # True if this module is fading IN (was cued by another)

        # Tap tempo
        self.tap_times = []
        self.tapped_bpm = None
        self.tap_reset_timer = None

        # Audio cache
        self.audio_cache = {}

        # Playlist widget will be created in get_ui()
        self.playlist_widget = None
        self.playlists_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "playlists"))

    def load_playlist(self, folder_name):
        """Load a playlist folder into the playlist widget."""
        # This method is no longer needed since Playlist handles its own navigation
        # Keeping for backward compatibility
        pass

    def select_song(self, index):
        """Select a song (without auto-playing). Called when song is dropped onto vinyl."""
        if not self.playlist_widget:
            return
            
        if index < 0 or index >= len(self.playlist_widget.song_metadata):
            return

        self.selected_index = index
        metadata = self.playlist_widget.get_song_metadata(index)
        
        if not metadata:
            return
        
        # Update vinyl record display
        if hasattr(self, 'vinyl_widget'):
            # Load album art
            album_art = extract_album_art(metadata['path'])
            if album_art:
                self.vinyl_widget.set_album_art(album_art)
            else:
                self.vinyl_widget.set_album_art(None)
            
            # Update text
            self.vinyl_widget.set_song_info(metadata['title'], metadata['artist'])
        
        # Load audio data (lazy loading) - store in cache
        if index not in self.audio_cache:
            self.load_audio_file(index)
        
        # Update cue slider and spinbox range
        song_length = metadata['length']
        if hasattr(self, 'cue_slider'):
            self.cue_slider.setMinimum(int(-song_length * 100))
            self.cue_slider.setMaximum(0)
        if hasattr(self, 'cue_spinbox'):
            self.cue_spinbox.setRange(-float(song_length), 0.0)
        
        # Update visualizer
        self.update_cue_visualizer()
        
        # Update scrub slider range based on loaded audio
        if index in self.audio_cache:
            track = self.audio_cache[index]
            if hasattr(self, 'scrub_slider') and len(track) > 0:
                self.scrub_slider.setValue(0)

    def load_audio_file(self, index):
        """Load audio file into memory."""
        if index in self.audio_cache:
            return self.audio_cache[index]

        path = self.playlist_widget.get_song_path(index)
        if not path:
            return None
        
        data, fs = sf.read(path, dtype="float32")

        if data.ndim == 1:
            data = np.column_stack((data, data))

        if fs != self.sample_rate:
            ratio = self.sample_rate / fs
            idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
            idx = idx[idx < len(data)]
            data = data[idx]

        self.audio_cache[index] = data
        self.start_bpm_thread(path)
        return data

    def start_bpm_thread(self, path):
        """Start background BPM detection."""
        self.song_bpm = None
        def worker():
            try:
                bpm = detect_bpm(path)
            except Exception:
                bpm = 0.0
            self.song_bpm = bpm
        threading.Thread(target=worker, daemon=True).start()

    def toggle_play(self):
        """Toggle playback of selected song."""
        if self.selected_index is None:
            return

        if self.current_index == self.selected_index and self.play_buffer is not None and len(self.play_buffer) > 0:
            # Toggle play/pause on current song
            self.playing = not self.playing
        else:
            # Load and start playing new song
            self.current_index = self.selected_index
            self.play_buffer = self.load_audio_file(self.selected_index)
            if self.play_buffer is None or len(self.play_buffer) == 0:
                return
            self.playhead = 0.0 if not self.reverse else len(self.play_buffer) - 1
            self.playing = True
            self.cue_sent = False

        # Update vinyl animation
        if hasattr(self, 'vinyl_widget'):
            self.vinyl_widget.set_playing(self.playing)

    def generate(self, frames: int) -> np.ndarray:
        """Generate audio and cue output."""
        cue_out = np.zeros((frames, 1), dtype=np.float32)
        audio_out = np.zeros((frames, 2), dtype=np.float32)
        
        # Check for incoming cue (starts this track, possibly with fade-in)
        if not self.playing and self.input_nodes and len(self.input_nodes) > 0:
            try:
                cue_in = self.input_nodes[0].receive(frames)
                if isinstance(cue_in, np.ndarray) and cue_in.size > 0:
                    if np.any(cue_in >= 0.5):
                        # Check if the sender has crossfade enabled
                        sender_crossfade = 0.0
                        if len(self.input_nodes) > 0:
                            sender = self.input_nodes[0].get_connected()
                            if sender and hasattr(sender, 'crossfade_duration'):
                                sender_crossfade = sender.crossfade_duration
                        
                        if sender_crossfade > 0:
                            # Start with fade-in
                            self.fade_in_mode = True
                            self.crossfade_active = True
                            self.crossfade_progress = 0.0
                            self.crossfade_duration = sender_crossfade  # Match sender's duration
                        else:
                            self.fade_in_mode = False
                            self.crossfade_active = False
                        
                        self.toggle_play()
            except Exception:
                pass
        
        if self.current_index is None or not self.playing:
            self.current_cue_out = cue_out
            return audio_out

        track = self.play_buffer
        if track is None:
            self.current_cue_out = cue_out
            return audio_out
            
        n_samples = len(track)
        if n_samples < 2:
            self.current_cue_out = cue_out
            return audio_out

        step = self.pitch * (-1 if self.reverse else 1)
        indices = self.playhead + step * np.arange(frames)
        valid_mask = (indices >= 0) & (indices < n_samples - 1)
        indices_clamped = np.clip(indices, 0, n_samples - 2)

        idx_floor = np.floor(indices_clamped).astype(int)
        frac = indices_clamped - idx_floor
        audio_out[valid_mask] = (1 - frac[valid_mask, None]) * track[idx_floor[valid_mask]] + \
                                 frac[valid_mask, None] * track[idx_floor[valid_mask] + 1]

        # Cue logic - fires when remaining time crosses the threshold
        # cue_time is negative (e.g., -5.0 means 5 seconds before end)
        # cue_time = 0 means fire exactly when song ends
        remaining_samples = n_samples - indices
        remaining_seconds = (remaining_samples / self.sample_rate) / self.pitch
        
        if not self.cue_sent and self.cue_time <= 0:
            cue_threshold = -self.cue_time  # Convert to positive threshold
            crossed = (remaining_seconds[:-1] > cue_threshold) & (remaining_seconds[1:] <= cue_threshold)
            if np.any(crossed):
                cue_idx = np.where(crossed)[0][0] + 1
                cue_out[cue_idx, 0] = 1.0
                self.cue_sent = True
                
                # Start crossfade (fade-out) if enabled
                if self.crossfade_duration > 0:
                    self.crossfade_active = True
                    self.crossfade_progress = 0.0
                    self.fade_in_mode = False  # This track is fading OUT

        # Apply crossfade envelope
        if self.crossfade_active and self.crossfade_duration > 0:
            # Calculate progress increment per frame
            progress_per_frame = 1.0 / (self.crossfade_duration * self.sample_rate)
            
            # Create envelope for this buffer
            start_progress = self.crossfade_progress
            end_progress = min(1.0, start_progress + progress_per_frame * frames)
            
            # Linear ramp from start to end progress
            envelope = np.linspace(start_progress, end_progress, frames)
            
            if self.fade_in_mode:
                # Fading IN: envelope goes 0 -> 1
                gain = envelope
            else:
                # Fading OUT: envelope goes 1 -> 0
                gain = 1.0 - envelope
            
            # Apply gain to audio
            audio_out *= gain[:, np.newaxis]
            
            # Update progress
            self.crossfade_progress = end_progress
            
            # Check if crossfade complete
            if self.crossfade_progress >= 1.0:
                self.crossfade_active = False
                if not self.fade_in_mode:
                    # Fade-out complete, stop playback
                    self.playing = False
                    if hasattr(self, 'vinyl_widget'):
                        self.vinyl_widget.set_playing(False)

        self.playhead += step * frames

        if self.playhead >= n_samples - 1 or self.playhead <= 0:
            if not self.loop:
                self.playing = False
                self.playhead = max(0, min(self.playhead, n_samples - 1))
                if hasattr(self, 'vinyl_widget'):
                    self.vinyl_widget.set_playing(False)
            else:
                self.playhead = 0.0
                self.cue_sent = False
                self.crossfade_active = False

        self.current_cue_out = cue_out
        return audio_out

    # Tap tempo
    def on_tap(self):
        current_time = time.time()
        if self.tap_reset_timer is not None:
            self.tap_reset_timer.stop()
            self.tap_reset_timer.deleteLater()
            self.tap_reset_timer = None
        self.tap_times.append(current_time)
        self.tap_times = [t for t in self.tap_times if current_time - t < 2.0]
        if len(self.tap_times) >= 2:
            intervals = [self.tap_times[i] - self.tap_times[i-1] for i in range(1, len(self.tap_times))]
            avg_interval = sum(intervals) / len(intervals)
            self.tapped_bpm = 60.0 / avg_interval
        self.tap_reset_timer = QTimer()
        self.tap_reset_timer.setSingleShot(True)
        self.tap_reset_timer.timeout.connect(self.reset_tap_tempo)
        self.tap_reset_timer.start(2000)
    
    def reset_tap_tempo(self):
        self.tap_times.clear()
        self.tapped_bpm = None
        if self.tap_reset_timer is not None:
            self.tap_reset_timer.stop()
            self.tap_reset_timer.deleteLater()
            self.tap_reset_timer = None

    def make_circle_button(self, icon_char, diameter=48, bg="#444", fg="white", tooltip=""):
        btn = QPushButton(icon_char)
        btn.setFixedSize(diameter, diameter)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                font-size: 20px;
                border-radius: {diameter//2}px;
                border: 2px solid #222;
            }}
            QPushButton:hover {{ background-color: #666; }}
            QPushButton:pressed {{ background-color: #555; }}
        """)
        return btn

    def update_cue_tick_labels(self, song_length):
        """Update cue slider tick labels dynamically."""
        if not hasattr(self, 'cue_tick_layout'):
            return
        
        # Clear existing labels
        while self.cue_tick_layout.count():
            item = self.cue_tick_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Create new labels
        num_ticks = 5
        for i in range(num_ticks):
            seconds = -song_length * (1 - i / (num_ticks - 1))
            l = QLabel(f"{seconds:.0f}s")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet("color: #888; font-size: 10px;")
            self.cue_tick_layout.addWidget(l)

    def update_cue_visualizer(self):
        """Update cue waveform visualizer."""
        if not hasattr(self, 'cue_visualizer') or not self.playlist_widget:
            return
        
        current_track = None
        if self.selected_index is not None:
            current_track = self.audio_cache.get(self.selected_index)
        
        next_track = None
        pitch_b = 1.0
        if len(self.output_nodes) > 1:
            connected_module = self.output_nodes[1].get_connected()
            if connected_module and isinstance(connected_module, Music):
                # Get pitch from connected module
                pitch_b = connected_module.pitch
                if connected_module.selected_index is not None:
                    if not hasattr(connected_module, 'audio_cache'):
                        connected_module.audio_cache = {}
                    next_track = connected_module.audio_cache.get(connected_module.selected_index)
                    if next_track is None:
                        next_track = connected_module.load_audio_file(connected_module.selected_index)
        
        self.cue_visualizer.set_tracks(current_track, next_track, self.cue_time, self.sample_rate, self.pitch, pitch_b)

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Vinyl record widget
        self.vinyl_widget = Record()
        self.vinyl_widget.on_song_dropped = self.select_song
        self.vinyl_widget.on_play_clicked = self.toggle_play
        layout.addWidget(self.vinyl_widget)

        # Scrub/seek slider + remaining time (above playlist)
        scrub_section = QVBoxLayout()
        scrub_section.setSpacing(1)
        
        # Remaining time + BPM row
        bpm_layout = QHBoxLayout()
        bpm_layout.setSpacing(4)
        self.scrub_label = QLabel("Remaining: 00:00  |  BPM: ---")
        self.scrub_label.setStyleSheet("color: #888; font-size: 10px;")
        
        self.tap_btn = QPushButton("TAP")
        self.tap_btn.setFixedSize(40, 20)
        self.tap_btn.setToolTip("Tap to detect BPM manually")
        self.tap_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                font-weight: bold;
                font-size: 9px;
                border-radius: 4px;
                border: 1px solid #666;
            }
            QPushButton:hover { background-color: #5a5a5a; }
            QPushButton:pressed { background-color: #3a3a3a; }
        """)
        self.tap_btn.clicked.connect(self.on_tap)
        
        # Copy song info button
        self.copy_btn = QPushButton("\u2398")  # ⎘ copy symbol
        self.copy_btn.setFixedSize(20, 20)
        self.copy_btn.setToolTip("Copy song title and artist to clipboard")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #aaa;
                font-size: 12px;
                border-radius: 4px;
                border: 1px solid #555;
            }
            QPushButton:hover { background-color: #4a4a4a; color: white; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """)
        self.copy_btn.clicked.connect(self._copy_song_info)
        
        bpm_layout.addWidget(self.scrub_label)
        bpm_layout.addWidget(self.tap_btn)
        bpm_layout.addWidget(self.copy_btn)
        scrub_section.addLayout(bpm_layout)
        
        # Scrub slider
        self.scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setMinimum(0)
        self.scrub_slider.setMaximum(1000)
        self.scrub_slider.setFixedHeight(14)
        self.scrub_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #2ecc71;
                width: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #2ecc71;
                border-radius: 2px;
            }
        """)
        
        # Scrub slider seeking functionality
        self.scrub_slider.sliderPressed.connect(self._on_scrub_pressed)
        self.scrub_slider.sliderReleased.connect(self._on_scrub_released)
        self.scrub_slider.sliderMoved.connect(self._on_scrub_moved)
        
        scrub_section.addWidget(self.scrub_slider)
        layout.addLayout(scrub_section)

        # Playlist (handles its own folder/song navigation)
        self.playlist_widget = Playlist(self.playlists_base_dir)
        layout.addWidget(self.playlist_widget)

        # Control buttons row (reverse + loop)
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)
        
        # Better unicode symbols for reverse and loop
        self.reverse_btn = self.make_circle_button("\u23EA", 28, tooltip="Reverse playback")  # ⏪
        self.loop_btn = self.make_circle_button("\u21BB", 28, tooltip="Loop track")  # ↻
        
        # Toggle styling for buttons
        def toggle_reverse():
            self.reverse = not self.reverse
            self.reverse_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {'#4a90e2' if self.reverse else '#444'};
                    color: white;
                    font-size: 14px;
                    border-radius: 14px;
                    border: 2px solid #222;
                }}
                QPushButton:hover {{ background-color: {'#5aa0f2' if self.reverse else '#666'}; }}
            """)
        
        def toggle_loop():
            self.loop = not self.loop
            self.loop_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {'#4a90e2' if self.loop else '#444'};
                    color: white;
                    font-size: 14px;
                    border-radius: 14px;
                    border: 2px solid #222;
                }}
                QPushButton:hover {{ background-color: {'#5aa0f2' if self.loop else '#666'}; }}
            """)
        
        self.reverse_btn.clicked.connect(toggle_reverse)
        self.loop_btn.clicked.connect(toggle_loop)
        
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.reverse_btn)
        ctrl_layout.addWidget(self.loop_btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Cue section container (hidden by default, shown when cue_out connected)
        self.cue_section_widget = QWidget()
        cue_section_layout = QVBoxLayout(self.cue_section_widget)
        cue_section_layout.setContentsMargins(0, 0, 0, 0)
        cue_section_layout.setSpacing(2)
        
        # Cue visualizer
        self.cue_visualizer = CueWaveformVisualizer()
        self.cue_visualizer.setMaximumHeight(80)
        cue_section_layout.addWidget(self.cue_visualizer)

        # Cue control row: label + spinbox + fine tune buttons + crossfade
        cue_control_row = QHBoxLayout()
        cue_control_row.setSpacing(2)
        cue_control_row.setContentsMargins(0, 0, 0, 0)
        
        cue_label = QLabel("Cue:")
        cue_label.setStyleSheet("color: #FFFF00; font-size: 9px; font-weight: bold;")
        cue_control_row.addWidget(cue_label)
        
        # Spin box for precise cue value (in seconds) - no arrows
        self.cue_spinbox = QDoubleSpinBox()
        self.cue_spinbox.setRange(-300.0, 0.0)
        self.cue_spinbox.setValue(self.cue_time)
        self.cue_spinbox.setSingleStep(0.1)
        self.cue_spinbox.setDecimals(2)
        self.cue_spinbox.setSuffix("s")
        self.cue_spinbox.setFixedWidth(62)
        self.cue_spinbox.setFixedHeight(18)
        self.cue_spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.cue_spinbox.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #2a2a2a;
                color: #FFFF00;
                border: 1px solid #555;
                border-radius: 2px;
                padding: 1px 2px;
                font-size: 10px;
            }
        """)
        cue_control_row.addWidget(self.cue_spinbox)
        
        # Fine tune buttons (-1s, -0.1s, +0.1s, +1s)
        def make_cue_btn(text, delta):
            btn = QPushButton(text)
            btn.setFixedSize(22, 16)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: #ccc;
                    font-size: 8px;
                    border-radius: 2px;
                    border: 1px solid #555;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    color: white;
                }
                QPushButton:pressed {
                    background-color: #2a2a2a;
                }
            """)
            btn.clicked.connect(lambda: self._adjust_cue(delta))
            return btn
        
        cue_control_row.addWidget(make_cue_btn("-1", -1.0))
        cue_control_row.addWidget(make_cue_btn("-.1", -0.1))
        cue_control_row.addWidget(make_cue_btn("+.1", 0.1))
        cue_control_row.addWidget(make_cue_btn("+1", 1.0))
        
        # Spacer
        cue_control_row.addSpacing(4)
        
        # Crossfade control (0 = disabled) - with arrows
        xfade_label = QLabel("Fade:")
        xfade_label.setStyleSheet("color: #aaa; font-size: 9px;")
        cue_control_row.addWidget(xfade_label)
        
        self.crossfade_spinbox = QDoubleSpinBox()
        self.crossfade_spinbox.setRange(0.0, 30.0)
        self.crossfade_spinbox.setValue(self.crossfade_duration)
        self.crossfade_spinbox.setSingleStep(0.5)
        self.crossfade_spinbox.setDecimals(1)
        self.crossfade_spinbox.setSuffix("s")
        self.crossfade_spinbox.setFixedWidth(58)
        self.crossfade_spinbox.setFixedHeight(18)
        self.crossfade_spinbox.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #2a2a2a;
                color: #aaa;
                border: 1px solid #555;
                border-radius: 2px;
                padding: 1px 2px;
                font-size: 9px;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #3a3a3a;
                border: none;
                width: 12px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #4a4a4a;
            }
        """)
        self.crossfade_spinbox.setToolTip("Crossfade duration (0 = disabled)")
        
        def on_crossfade_change(val):
            self.crossfade_duration = val
        
        self.crossfade_spinbox.valueChanged.connect(on_crossfade_change)
        cue_control_row.addWidget(self.crossfade_spinbox)
        
        cue_control_row.addStretch()
        cue_section_layout.addLayout(cue_control_row)

        # Cue slider for coarse positioning (full song range)
        self.cue_slider = QSlider(Qt.Orientation.Horizontal)
        self.cue_slider.setMinimum(-20000)  # -20 seconds default, updated per song
        self.cue_slider.setMaximum(0)
        self.cue_slider.setValue(int(self.cue_time * 100))  # 100 units per second for slider
        self.cue_slider.setFixedHeight(16)
        self.cue_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFF00;
                width: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #666;
                border-radius: 2px;
            }
        """)
        cue_section_layout.addWidget(self.cue_slider)
        
        # Sync between slider and spinbox
        self._cue_updating = False
        
        def on_cue_slider_change(val):
            if self._cue_updating:
                return
            self._cue_updating = True
            self.cue_time = val / 100.0
            self.cue_spinbox.setValue(self.cue_time)
            self.cue_sent = False
            self.update_cue_visualizer()
            self._cue_updating = False
        
        def on_cue_spinbox_change(val):
            if self._cue_updating:
                return
            self._cue_updating = True
            self.cue_time = val
            # Clamp slider to its range
            slider_val = max(self.cue_slider.minimum(), min(0, int(val * 100)))
            self.cue_slider.setValue(slider_val)
            self.cue_sent = False
            self.update_cue_visualizer()
            self._cue_updating = False
        
        self.cue_slider.valueChanged.connect(on_cue_slider_change)
        self.cue_spinbox.valueChanged.connect(on_cue_spinbox_change)
        
        # Hide cue section by default
        self.cue_section_widget.hide()
        layout.addWidget(self.cue_section_widget)

        # Pitch slider section with reset button
        pitch_section = QVBoxLayout()
        pitch_section.setSpacing(1)
        
        pitch_header = QHBoxLayout()
        pitch_header.setSpacing(4)
        
        self.pitch_label = QLabel(f"Pitch: {self.pitch:.2f}x")
        self.pitch_label.setStyleSheet("color: #aaa; font-size: 10px;")
        pitch_header.addWidget(self.pitch_label)
        
        # Pitch reset button
        self.pitch_reset_btn = QPushButton("1x")
        self.pitch_reset_btn.setFixedSize(24, 16)
        self.pitch_reset_btn.setToolTip("Reset pitch to 1.00x")
        self.pitch_reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #aaa;
                font-size: 9px;
                font-weight: bold;
                border-radius: 3px;
                border: 1px solid #555;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: white;
                border-color: #4a90e2;
            }
        """)
        pitch_header.addWidget(self.pitch_reset_btn)
        pitch_header.addStretch()
        
        pitch_section.addLayout(pitch_header)
        
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setMinimum(0)
        self.pitch_slider.setMaximum(100)
        self.pitch_slider.setValue(50)
        self.pitch_slider.setFixedHeight(18)
        self.pitch_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333;
                height: 5px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #4a90e2;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
        """)
        pitch_section.addWidget(self.pitch_slider)
        
        def on_pitch_change(val):
            s = val / 100.0
            self.pitch = 0.5 * (4 ** s)
            self.pitch_label.setText(f"Pitch: {self.pitch:.2f}x")
            # Update vinyl spin speed
            if hasattr(self, 'vinyl_widget'):
                self.vinyl_widget.set_pitch(self.pitch)
            # Update cue visualizer with new pitch
            self.update_cue_visualizer()
        
        def reset_pitch():
            self.pitch_slider.setValue(50)  # 50 corresponds to 1.0x
        
        self.pitch_slider.valueChanged.connect(on_pitch_change)
        self.pitch_reset_btn.clicked.connect(reset_pitch)
        layout.addLayout(pitch_section)

        # Track connected module's pitch for visualizer updates
        self._last_connected_pitch = 1.0
        
        # Timer for UI updates
        self.update_timer = QTimer()
        self.update_timer.setInterval(50)
        
        def update_ui():
            # Safety check - if widget was deleted, stop
            try:
                if not self.cue_section_widget or not self.scrub_slider:
                    return
            except RuntimeError:
                # Widget was deleted
                return
            
            # Check cue_out connection status and show/hide cue section
            cue_connected = False
            connected_pitch = 1.0
            if len(self.output_nodes) > 1:
                connected_module = self.output_nodes[1].get_connected()
                if connected_module is not None:
                    cue_connected = True
                    # Check if connected module has a pitch attribute
                    if hasattr(connected_module, 'pitch'):
                        connected_pitch = connected_module.pitch
            
            try:
                if cue_connected and not self.cue_section_widget.isVisible():
                    self.cue_section_widget.show()
                    self.update_cue_visualizer()
                elif not cue_connected and self.cue_section_widget.isVisible():
                    self.cue_section_widget.hide()
                
                # Update visualizer if connected module's pitch changed
                if cue_connected and connected_pitch != self._last_connected_pitch:
                    self._last_connected_pitch = connected_pitch
                    self.update_cue_visualizer()
                    
            except RuntimeError:
                return
            
            # Update playback UI
            if self.playing and self.current_index is not None and not self.scrubbing_user:
                track = self.play_buffer
                if track is not None and len(track) > 0:
                    progress = min(max(self.playhead / len(track), 0.0), 1.0)
                    try:
                        self.scrub_slider.blockSignals(True)
                        self.scrub_slider.setValue(int(progress * 1000))
                        self.scrub_slider.blockSignals(False)

                        remaining_samples = len(track) - int(self.playhead)
                        remaining_seconds = (remaining_samples / self.sample_rate) / self.pitch
                        mins, secs = divmod(int(remaining_seconds), 60)

                        auto_bpm = "---" if self.song_bpm is None else f"{self.song_bpm * self.pitch:06.2f}"
                        bpm_display = f"BPM: {auto_bpm}"
                        if self.tapped_bpm:
                            bpm_display = f"Auto: {auto_bpm} | Tap: {self.tapped_bpm:06.2f}"

                        self.scrub_label.setText(f"Remaining: {mins:02d}:{secs:02d}  |  {bpm_display}")
                    except RuntimeError:
                        return
        
        self.update_timer.timeout.connect(update_ui)
        self.update_timer.start()

        return widget
    
    def _on_scrub_pressed(self):
        """Called when user starts dragging scrub slider."""
        self.scrubbing_user = True
    
    def _on_scrub_released(self):
        """Called when user releases scrub slider."""
        self.scrubbing_user = False
    
    def _on_scrub_moved(self, value):
        """Called when user moves scrub slider - seek to position."""
        if self.current_index is not None and self.play_buffer is not None:
            track = self.play_buffer
            if len(track) > 0:
                # Convert slider value (0-1000) to playhead position
                progress = value / 1000.0
                self.playhead = progress * len(track)
                self.cue_sent = False  # Reset cue so it can trigger again
    
    def _adjust_cue(self, delta):
        """Adjust cue time by delta seconds."""
        new_val = self.cue_time + delta
        # Clamp to valid range (can't be positive, and not beyond song length)
        min_val = self.cue_spinbox.minimum() if hasattr(self, 'cue_spinbox') else -300.0
        new_val = max(min_val, min(0.0, new_val))
        self.cue_spinbox.setValue(new_val)
    
    def _copy_song_info(self):
        """Copy song title and artist to clipboard."""
        if self.selected_index is None or not self.playlist_widget:
            return
        
        metadata = self.playlist_widget.get_song_metadata(self.selected_index)
        if not metadata:
            return
        
        title = metadata.get('title', '')
        artist = metadata.get('artist', '')
        filename = metadata.get('filename', '')
        
        # Check if we have valid title/artist (not default values)
        if title and artist and title != 'Unknown' and artist != 'Unknown':
            text = f"{title} - {artist}"
        elif title and title != 'Unknown':
            text = title
        else:
            # Fall back to filename, clean it up
            text = filename
            # Remove file extension
            text = os.path.splitext(text)[0]
            # Remove leading numbers (e.g., "01 - ", "01. ", "1-", "01_")
            text = re.sub(r'^[\d]+[\s\-_.]*', '', text)
            # Clean up any remaining leading/trailing whitespace or dashes
            text = text.strip(' -_.')
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        if clipboard and text:
            clipboard.setText(text)

    def cleanup(self):
        # Stop timers first to prevent callbacks after widget deletion
        if hasattr(self, "update_timer") and self.update_timer:
            self.update_timer.stop()
            self.update_timer.deleteLater()
            self.update_timer = None
        if hasattr(self, "tap_reset_timer") and self.tap_reset_timer:
            self.tap_reset_timer.stop()
            self.tap_reset_timer.deleteLater()
            self.tap_reset_timer = None
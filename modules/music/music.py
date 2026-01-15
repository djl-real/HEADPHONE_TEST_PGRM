import os
import numpy as np
import soundfile as sf
import librosa
import threading
import traceback
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel,
    QSlider, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontDatabase, QFont
from audio_module import AudioModule
import mutagen

# Import the visualizer
from modules.music.cue_waveform_visualizer import CueWaveformVisualizer

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg")

def detect_bpm(path):
    """Fast BPM detector using onset envelope autocorrelation."""
    try:
        # Load only 30 seconds, downsampled to 8 kHz
        y, sr = librosa.load(path, mono=True, sr=8000, duration=30)

        # Onset envelope
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)

        # Fast tempo estimation from onset autocorrelation
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr, aggregate=None)

        return int(tempo[0]) if len(tempo) > 0 else None

    except Exception as e:
        traceback.print_exc()
        return None

class Music(AudioModule):
    """Music player module with playlist, scrubbing, reverse, pitch control, and cue system."""

    def __init__(self, sample_rate=44100):
        super().__init__(
            input_count=1,
            output_count=2,
            input_types=["cue"],
            output_types=["audio", "cue"],
            input_colors=["#B8860B"],  # Dark yellow
            output_colors=[None, "#FFFF00"],  # Default for audio, bright yellow for cue
            input_positions=["left"],
            output_positions=[None, "right"],  # Default (right) for audio, right for cue
            input_labels=["Cue In"],
            output_labels=["Audio", "Cue Out"]
        )
        self.sample_rate = sample_rate

        # Playback state
        self.playing = False
        self.current_index = None
        self.play_buffer = np.zeros((0, 2), dtype=np.float32)
        self.playhead = 0.0
        self.pitch = 1.0
        self.reverse = False
        self.loop = False
        self.scrubbing_user = False
        self.song_bpm = None

        # Cue system
        self.cue_time = -5.0  # Seconds before end to send cue (negative value)
        self.cue_sent = False  # Track if we've sent the cue for this playback
        self.current_cue_out = None  # Store current cue output data

        # Tap tempo state
        self.tap_times = []
        self.tapped_bpm = None
        self.tap_reset_timer = None

        # Data
        self.songs = []               # Will hold np.ndarray or None (lazy)
        self.song_names = []          # Filenames
        self.song_display_texts = []  # Monospace display
        self.list_widget = None       # Will be created in get_ui()

        # Load playlist immediately
        self.load_playlist()


    # --- Playlist scanning ---
    def load_playlist(self, folder_name=None):
        """Scan playlist folder, load metadata only for responsiveness."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "playlists"))
        if folder_name:
            playlist_dir = os.path.join(base_dir, folder_name)
        else:
            playlist_dir = base_dir
        os.makedirs(playlist_dir, exist_ok=True)

        self.current_playlist_path = playlist_dir  # store path for audio loading

        self.songs.clear()
        self.song_names.clear()
        self.song_display_texts.clear()

        MAX_TITLE_LEN = 15
        MAX_ARTIST_LEN = 15

        total_time = 0

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

                            # Metadata duration
                            if hasattr(meta, "info") and hasattr(meta.info, "length"):
                                length_seconds = int(meta.info.length)
                    except Exception:
                        pass

                    # ---------------------------------------------------------
                    # Fallback: compute actual audio duration if metadata fails
                    # ---------------------------------------------------------
                    if length_seconds == 0:
                        try:
                            import soundfile as sf
                            with sf.SoundFile(path) as f:
                                    length_seconds = int(len(f) / f.samplerate)
                        except Exception:
                            length_seconds = 0

                    # Clean and pad
                    title = (title.strip()[:MAX_TITLE_LEN-1] + "…") if len(title) > MAX_TITLE_LEN else title.ljust(MAX_TITLE_LEN)
                    artist = (artist.strip()[:MAX_ARTIST_LEN-1] + "…") if len(artist) > MAX_ARTIST_LEN else artist.ljust(MAX_ARTIST_LEN)

                    mins, secs = divmod(length_seconds, 60)
                    duration = f"{mins:02d}:{secs:02d}"

                    display_text = f"{title} {artist} {duration}"
                    self.song_display_texts.append(display_text)
                    self.song_names.append(fname)
                    self.songs.append(None)  # Placeholder for lazy loading
                    total_time += length_seconds

                except Exception as e:
                    print(f"[Music] Failed to scan {fname}: {e}")


        # Populate UI list
        self.populate_list_widget()

        # Switch to the songs playback screen
        if hasattr(self, "stack") and hasattr(self, "song_screen"):
            self.stack.setCurrentWidget(self.song_screen)

        # Print playlist length
        mins, secs = divmod(total_time, 60)
        duration = f"{mins:02d}:{secs:02d}"
        print("Playlist length: " + duration)

    def populate_list_widget(self):
        """Populate the QListWidget with song display texts."""
        if self.list_widget is not None:
            self.list_widget.clear()
            for display_text in self.song_display_texts:
                self.list_widget.addItem(display_text)
        
    def start_bpm_thread(self, path):
        self.song_bpm = None  # mark as "not ready"

        def worker():
            try:
                bpm = detect_bpm(path)
            except Exception as e:
                print("BPM thread error:", e)
                bpm = 0.0

            # Assign *on the class* (not returned!)
            self.song_bpm = bpm

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def load_audio_file(self, index):
        if self.songs[index] is not None:
            return self.songs[index]

        fname = self.song_names[index]
        path = os.path.join(self.current_playlist_path, fname)
        data, fs = sf.read(path, dtype="float32")

        if data.ndim == 1:
            data = np.column_stack((data, data))

        if fs != self.sample_rate:
            ratio = self.sample_rate / fs
            idx = np.round(np.arange(0, len(data) * ratio) / ratio).astype(int)
            idx = idx[idx < len(data)]
            data = data[idx]

        self.songs[index] = data

        # Start BPM detection thread
        self.start_bpm_thread(path)

        return data

    # --- Tap Tempo ---
    def on_tap(self):
        """Handle tap button press for manual BPM detection."""
        current_time = time.time()
        
        # Cancel any existing reset timer
        if self.tap_reset_timer is not None:
            self.tap_reset_timer.stop()
            self.tap_reset_timer.deleteLater()
            self.tap_reset_timer = None
        
        # Add current tap time
        self.tap_times.append(current_time)
        
        # Keep only recent taps (within 2 seconds of most recent)
        self.tap_times = [t for t in self.tap_times if current_time - t < 2.0]
        
        # Calculate BPM if we have at least 2 taps
        if len(self.tap_times) >= 2:
            intervals = [self.tap_times[i] - self.tap_times[i-1] 
                        for i in range(1, len(self.tap_times))]
            avg_interval = sum(intervals) / len(intervals)
            self.tapped_bpm = 60.0 / avg_interval
        
        # Set up auto-reset timer (2 seconds)
        self.tap_reset_timer = QTimer()
        self.tap_reset_timer.setSingleShot(True)
        self.tap_reset_timer.timeout.connect(self.reset_tap_tempo)
        self.tap_reset_timer.start(2000)
    
    def reset_tap_tempo(self):
        """Reset tap tempo data after timeout."""
        self.tap_times.clear()
        self.tapped_bpm = None
        if self.tap_reset_timer is not None:
            self.tap_reset_timer.stop()
            self.tap_reset_timer.deleteLater()
            self.tap_reset_timer = None

    # --- Playback ---
    def toggle_play(self, index: int = None):
        if index is None:
            index = self.current_index if self.current_index is not None else -1
        
        if index < 0 or index >= len(self.songs):
            return

        if self.current_index == index and self.play_buffer is not None:
            self.playing = not self.playing
        else:
            self.current_index = index
            self.play_buffer = self.load_audio_file(index)
            self.playhead = 0.0 if not self.reverse else len(self.play_buffer) - 1
            self.playing = True
            self.cue_sent = False  # Reset cue flag for new song

    def generate(self, frames: int) -> np.ndarray:
        # Check which type of node is requesting data
        # This is a workaround - we'll generate everything and store cue separately
        
        # Cue output - always initialize
        cue_out = np.zeros((frames, 1), dtype=np.float32)
        
        # Audio output
        audio_out = np.zeros((frames, 2), dtype=np.float32)
        
        # Check for incoming cue (Cue In)
        if not self.playing and self.input_nodes and len(self.input_nodes) > 0:
            try:
                cue_in = self.input_nodes[0].receive(frames)
                if isinstance(cue_in, np.ndarray) and cue_in.size > 0:
                    # Check if any 1s in the cue signal
                    if np.any(cue_in >= 0.5):  # Using 0.5 threshold for robustness
                        # Find the first index where cue triggers
                        trigger_idx = np.where(cue_in >= 0.5)[0][0]
                        # Start playing from the selected song
                        if self.current_index is not None:
                            self.toggle_play(self.current_index)
                        elif self.list_widget and self.list_widget.currentRow() >= 0:
                            self.toggle_play(self.list_widget.currentRow())
            except Exception as e:
                pass  # Ignore cue input errors
        
        # If not playing, store cue and return silence
        if self.current_index is None or not self.playing:
            self.current_cue_out = cue_out
            return audio_out

        track = self.play_buffer
        n_samples = len(track)
        if n_samples < 2:
            self.current_cue_out = cue_out
            return audio_out

        # Compute all fractional indices for this block
        step = self.pitch * (-1 if self.reverse else 1)
        indices = self.playhead + step * np.arange(frames)
        
        # Clamp indices to track boundaries
        valid_mask = (indices >= 0) & (indices < n_samples - 1)
        indices_clamped = np.clip(indices, 0, n_samples - 2)

        # Vectorized linear interpolation
        idx_floor = np.floor(indices_clamped).astype(int)
        frac = indices_clamped - idx_floor
        audio_out[valid_mask] = (1 - frac[valid_mask, None]) * track[idx_floor[valid_mask]] + \
                        frac[valid_mask, None] * track[idx_floor[valid_mask] + 1]

        # --- Cue Out Logic ---
        # Calculate remaining time in seconds at each sample
        remaining_samples = n_samples - indices
        remaining_seconds = (remaining_samples / self.sample_rate) / self.pitch
        
        # Check if we cross the cue point in this block
        if not self.cue_sent and self.cue_time < 0:
            cue_threshold = -self.cue_time  # Convert to positive
            # Find where remaining time crosses the threshold
            crossed = (remaining_seconds[:-1] > cue_threshold) & (remaining_seconds[1:] <= cue_threshold)
            if np.any(crossed):
                # Set cue signal at the crossing point
                cue_idx = np.where(crossed)[0][0] + 1
                cue_out[cue_idx, 0] = 1.0
                self.cue_sent = True

        # Update playhead for next block
        self.playhead += step * frames

        # Stop if reached end or beginning
        if self.playhead >= n_samples - 1 or self.playhead <= 0:
            if not self.loop:
                self.playing = False
                self.playhead = max(0, min(self.playhead, n_samples - 1))
            else:
                self.playhead = 0.0
                self.cue_sent = False  # Reset cue when looping

        # Store current cue output
        self.current_cue_out = cue_out
        
        return audio_out

    # --- Helpers ---

    def make_circle_button(self, icon_char, diameter=48, bg="#444", fg="white"):
        btn = QPushButton(icon_char)
        btn.setFixedSize(diameter, diameter)
        btn.setFont(QFont("Segoe MDL2 Assets"))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                font-size: 20px;
                border-radius: {diameter//2}px;
                border: 2px solid #222;
            }}
            QPushButton:hover {{
                background-color: #666;
            }}
        """)
        return btn

    def update_control_icons(self):
        # Play/Pause icon
        if self.playing:
            self.play_btn.setText("\uE769")               # pause icon
            self.play_btn.setStyleSheet(self.play_active_style)
        else:
            self.play_btn.setText("▶")               # play icon
            self.play_btn.setStyleSheet(self.play_idle_style)

        # Reverse icon
        if self.reverse:
            self.reverse_btn.setText("⮂")           # "reverse" symbol
            self.reverse_btn.setStyleSheet(self.reverse_active_style)
        else:
            self.reverse_btn.setText("⮀")           # "forward" symbol
            self.reverse_btn.setStyleSheet(self.reverse_idle_style)

        # Loop icon
        if self.loop:
            self.loop_btn.setText("\uE8EE")              # loop enabled
            self.loop_btn.setStyleSheet(self.loop_active_style)
        else:
            self.loop_btn.setText("⟳")               # loop off
            self.loop_btn.setStyleSheet(self.loop_idle_style)


    def get_ui(self) -> QWidget:

        # Styles for stateful circular buttons
        self.play_idle_style = """
        QPushButton {
            background-color: #444;
            color: white;
            font-size: 20px;
            border-radius: 24px;
            border: 2px solid #222;
        }
        QPushButton:hover { background-color: #666; }
        """

        self.play_active_style = """
        QPushButton {
            background-color: #2ecc71;
            color: black;
            font-size: 20px;
            border-radius: 24px;
            border: 2px solid #1e8c4a;
        }
        """

        self.reverse_idle_style = """
        QPushButton {
            background-color: #444;
            color: white;
            font-size: 20px;
            border-radius: 16px;
            border: 2px solid #222;
        }
        QPushButton:hover { background-color: #666; }
        """

        self.reverse_active_style = """
        QPushButton {
            background-color: #e67e22;
            color: black;
            font-size: 20px;
            border-radius: 16px;
            border: 2px solid #a34f00;
        }
        """

        self.loop_idle_style = """
        QPushButton {
            background-color: #444;
            color: white;
            font-size: 20px;
            border-radius: 16px;
            border: 2px solid #222;
        }
        QPushButton:hover { background-color: #666; }
        """

        self.loop_active_style = """
        QPushButton {
            background-color: #3498db;
            color: black;
            font-size: 20px;
            border-radius: 16px;
            border: 2px solid #1f5e8c;
        }
        """
        widget = QWidget()
        main_layout = QVBoxLayout(widget)

        # --- Stacked widget for playlist selection + songs ---
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # --- Playlist folder selection screen ---
        playlists_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "playlists"))
        os.makedirs(playlists_dir, exist_ok=True)
        playlists = [f for f in sorted(os.listdir(playlists_dir)) if os.path.isdir(os.path.join(playlists_dir, f))]

        playlist_screen = QWidget()
        playlist_layout = QVBoxLayout()
        playlist_screen.setLayout(playlist_layout)
        playlist_layout.addWidget(QLabel("Select a Playlist:"))

        for folder in playlists:
            btn = QPushButton(folder)
            btn.setFixedHeight(50)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #333;
                    color: white;
                    font-size: 16px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #555;
                }
            """)
            btn.clicked.connect(lambda _, f=folder: self.load_playlist(f))
            playlist_layout.addWidget(btn)

        playlist_layout.addStretch()
        self.stack.addWidget(playlist_screen)

        # --- Songs playback screen (current UI) ---
        song_screen = QWidget()
        layout = QVBoxLayout(song_screen)

        # Back button
        back_btn = QPushButton("←")
        back_btn.setFixedHeight(20)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        layout.addWidget(back_btn)

        # Playlist QListWidget
        self.list_widget = QListWidget()
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(11)
        self.list_widget.setFont(mono_font)
        self.list_widget.setMinimumWidth(350)
        layout.addWidget(QLabel("Playlist"))
        layout.addWidget(self.list_widget)

        # Buttons
        btn_layout = QHBoxLayout()

        # Circle buttons
        self.reverse_btn = self.make_circle_button("⮀", 32)
        self.play_btn = self.make_circle_button("▶")
        self.loop_btn = self.make_circle_button("⟳", 32)

        btn_layout.addWidget(self.reverse_btn)
        btn_layout.addWidget(self.play_btn)
        btn_layout.addWidget(self.loop_btn)
        layout.addLayout(btn_layout)

        # Connect actions
        self.play_btn.clicked.connect(lambda: (self.toggle_play(self.list_widget.currentRow()), self.update_control_icons()))
        self.reverse_btn.clicked.connect(lambda: (setattr(self, "reverse", not self.reverse), self.update_control_icons()))
        self.loop_btn.clicked.connect(lambda: (setattr(self, "loop", not self.loop), self.update_control_icons()))

        # Initialize icons
        self.update_control_icons()

        # Cue waveform visualizer
        self.cue_visualizer = CueWaveformVisualizer()
        layout.addWidget(self.cue_visualizer)

        # Cue label
        self.cue_label = QLabel(f"Cue: {self.cue_time:.2f}s")
        layout.addWidget(self.cue_label)

        # Cue slider
        cue_slider = QSlider(Qt.Orientation.Horizontal)

        # Determine track length if a track is loaded, fallback to 20s
        track_length_seconds = getattr(self, "current_track_length", 20.0)

        cue_slider.setMinimum(int(-track_length_seconds * 100))  # negative full track
        cue_slider.setMaximum(0)  # 0 = end of track
        cue_slider.setValue(0)     # initialize at 0
        cue_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        cue_slider.setTickInterval(int(track_length_seconds * 100 / 4))  # 4 ticks
        layout.addWidget(cue_slider)

        def on_cue_change(val):
            self.cue_time = val / 100.0
            self.cue_label.setText(f"Cue: {self.cue_time:.2f}s")
            self.cue_sent = False
            self.update_cue_visualizer()

        cue_slider.valueChanged.connect(on_cue_change)

        # Dynamic tick labels
        cue_tick_layout = QHBoxLayout()
        num_ticks = 5
        for i in range(num_ticks):
            seconds = -track_length_seconds * (1 - i / (num_ticks - 1))
            l = QLabel(f"{seconds:.0f}s")
            l.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cue_tick_layout.addWidget(l)
        layout.addLayout(cue_tick_layout)

        # Pitch slider
        self.pitch_label = QLabel(f"Pitch: {self.pitch:.2f}x")
        layout.addWidget(self.pitch_label)
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
        
        def on_pitch_change(val):
            self.pitch = slider_to_pitch(val)
            self.pitch_label.setText(f"Pitch: {self.pitch:.2f}x")
        
        pitch_slider.valueChanged.connect(on_pitch_change)

        tick_layout = QHBoxLayout()
        for lbl in ["0.5", "", "", "", "1.0", "", "", "", "2.0"]:
            l = QLabel(lbl)
            l.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            tick_layout.addWidget(l)
        layout.addLayout(tick_layout)

        # Scrub slider + label with TAP button
        bpm_layout = QHBoxLayout()
        self.scrub_label = QLabel("Remaining: 00:00  |  BPM: ---")
        bpm_layout.addWidget(self.scrub_label)
        
        # TAP button
        self.tap_btn = QPushButton("TAP")
        self.tap_btn.setFixedSize(60, 30)
        self.tap_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 4px;
                border: 2px solid #6c3483;
            }
            QPushButton:hover {
                background-color: #af7ac5;
            }
            QPushButton:pressed {
                background-color: #7d3c98;
            }
        """)
        self.tap_btn.clicked.connect(self.on_tap)
        bpm_layout.addWidget(self.tap_btn)
        
        layout.addLayout(bpm_layout)
        
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
        self.update_timer = QTimer(song_screen)
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
                    remaining_seconds = (remaining_samples / self.sample_rate) / self.pitch
                    mins, secs = divmod(int(remaining_seconds), 60)

                    # Build BPM display with both auto-detected and tapped
                    if self.song_bpm is None:
                        auto_bpm_text = "---"
                    else:
                        auto_bpm_text = f"{self.song_bpm * self.pitch:06.2f}"
                    
                    if self.tapped_bpm is not None:
                        tap_bpm_text = f"{self.tapped_bpm:06.2f}"
                        bpm_display = f"Auto: {auto_bpm_text} | Tap: {tap_bpm_text}"
                    else:
                        bpm_display = f"BPM: {auto_bpm_text}"

                    self.scrub_label.setText(
                        f"Remaining: {mins:02d}:{secs:02d}  |  {bpm_display}"
                    )
            
            # dont Update visualizer periodically, only updates upon change
            # self.update_cue_visualizer()

        self.update_timer.timeout.connect(update_scrub_and_countdown)
        self.update_timer.start()

        # Add the songs playback screen to the stack
        self.stack.addWidget(song_screen)

        # Keep reference for switching to songs UI after playlist selection
        self.song_screen = song_screen

        return widget

    # --- Helpers ---
    def update_cue_visualizer(self):
        """Update the cue waveform visualizer with current and next track data."""
        if not hasattr(self, 'cue_visualizer'):
            return
        
        # Get current track data
        current_track = None
        if self.current_index is not None and 0 <= self.current_index < len(self.songs):
            current_track = self.play_buffer if self.play_buffer is not None else None
        
        # Get next track data from connected module
        next_track = None
        if len(self.output_nodes) > 1:  # output_nodes[1] is the cue out
            connected_module = self.output_nodes[1].get_connected()
            if connected_module and isinstance(connected_module, Music):
                # Get the next track's data
                if connected_module.current_index is not None:
                    if 0 <= connected_module.current_index < len(connected_module.songs):
                        next_track = connected_module.songs[connected_module.current_index]
                        # Load if not yet loaded
                        if next_track is None:
                            next_track = connected_module.load_audio_file(connected_module.current_index)
        
        # Update visualizer
        self.cue_visualizer.set_tracks(
            current_track,
            next_track,
            self.cue_time,
            self.sample_rate
        )
    
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
        
        if hasattr(self, "tap_reset_timer") and self.tap_reset_timer is not None:
            self.tap_reset_timer.stop()
            self.tap_reset_timer.deleteLater()
            self.tap_reset_timer = None
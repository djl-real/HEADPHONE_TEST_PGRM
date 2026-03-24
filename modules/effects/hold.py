# modules/hold.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt
from source.audio_module import AudioModule

MIN_HOLD_SAMPLES = 256
MAX_HOLD_SAMPLES = 65536
# Power-of-2 steps: 256, 512, 1024, ..., 65536
HOLD_STEPS = [2**i for i in range(
    int(np.log2(MIN_HOLD_SAMPLES)),
    int(np.log2(MAX_HOLD_SAMPLES)) + 1
)]


class Hold(AudioModule):
    """Effect that replays the last N samples when active."""

    def __init__(self):
        super().__init__(input_count=1, output_count=1)
        self.hold_active = False
        self.halt_enabled = True
        self.hold_samples = 1024  # default hold length in samples
        # Circular sample buffer (stereo)
        self.buffer = np.zeros((MAX_HOLD_SAMPLES, 2), dtype=np.float32)
        self.write_pos = 0  # next write position in circular buffer
        self.play_pos = 0   # playback position within the held region

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        if self.hold_active:
            if not self.halt_enabled:
                # Consume upstream even though we discard it
                _ = self.input_node.receive(frames)

            # Build output by looping over the held region
            held = self._get_held_region()
            held_len = len(held)
            out = np.empty((frames, 2), dtype=np.float32)
            written = 0
            while written < frames:
                chunk = min(frames - written, held_len - self.play_pos)
                out[written:written + chunk] = held[self.play_pos:self.play_pos + chunk]
                self.play_pos = (self.play_pos + chunk) % held_len
                written += chunk
            return out

        # Pass-through: record into circular buffer and forward
        x = self.input_node.receive(frames)
        self._write_to_buffer(x)
        return x.astype(np.float32)

    def _write_to_buffer(self, data: np.ndarray):
        """Write incoming samples into the circular buffer."""
        n = len(data)
        end = self.write_pos + n
        if end <= MAX_HOLD_SAMPLES:
            self.buffer[self.write_pos:end] = data
        else:
            first = MAX_HOLD_SAMPLES - self.write_pos
            self.buffer[self.write_pos:] = data[:first]
            self.buffer[:n - first] = data[first:]
        self.write_pos = end % MAX_HOLD_SAMPLES

    def _get_held_region(self) -> np.ndarray:
        """Return the most recent `hold_samples` samples as a contiguous array."""
        n = self.hold_samples
        start = (self.write_pos - n) % MAX_HOLD_SAMPLES
        if start + n <= MAX_HOLD_SAMPLES:
            return self.buffer[start:start + n]
        else:
            return np.concatenate([
                self.buffer[start:],
                self.buffer[:n - (MAX_HOLD_SAMPLES - start)]
            ])

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        title = QLabel("Hold Effect")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # --- Hold amount slider (steps are indices into HOLD_STEPS) ---
        slider_layout = QHBoxLayout()
        self.hold_slider = QSlider(Qt.Orientation.Vertical)
        self.hold_slider.setMinimum(0)
        self.hold_slider.setMaximum(len(HOLD_STEPS) - 1)
        # Set initial position to match default hold_samples
        default_idx = HOLD_STEPS.index(self.hold_samples) if self.hold_samples in HOLD_STEPS else 0
        self.hold_slider.setValue(default_idx)
        slider_layout.addWidget(self.hold_slider)

        # --- Round Hold button ---
        self.hold_button = QPushButton("Hold")
        self.hold_button.setCheckable(True)
        self.hold_button.setFixedSize(60, 60)
        self.hold_button.setStyleSheet("""
            QPushButton {
                border-radius: 30px;
                background-color: #3498db;
                color: white;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #2ecc71;
            }
        """)
        slider_layout.addWidget(self.hold_button)
        layout.addLayout(slider_layout)

        # --- Halt checkbox ---
        self.halt_checkbox = QCheckBox("Halt")
        self.halt_checkbox.setChecked(True)
        layout.addWidget(self.halt_checkbox, alignment=Qt.AlignmentFlag.AlignCenter)

        # Label under controls
        self.value_label = QLabel(f"Hold: {self.hold_samples} samples")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label)

        # Connect signals
        self.hold_slider.valueChanged.connect(self._on_slider_change)
        self.hold_button.toggled.connect(self._on_hold_toggle)
        self.halt_checkbox.toggled.connect(self._on_halt_toggle)

        return widget

    def _on_slider_change(self, index):
        self.hold_samples = HOLD_STEPS[index]
        self.value_label.setText(f"Hold: {self.hold_samples} samples")

    def _on_hold_toggle(self, state):
        self.hold_active = state
        if state:
            # Reset playback to start of held region
            self.play_pos = 0

    def _on_halt_toggle(self, state):
        self.halt_enabled = state

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "hold_active": self.hold_active,
            "halt_enabled": self.halt_enabled,
            "hold_samples": self.hold_samples,
            "write_pos": self.write_pos,
            "play_pos": self.play_pos,
            "buffer": self.buffer.tolist(),
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.hold_active = state.get("hold_active", False)
        self.halt_enabled = state.get("halt_enabled", True)
        self.hold_samples = state.get("hold_samples", 1024)
        self.write_pos = state.get("write_pos", 0)
        self.play_pos = state.get("play_pos", 0)
        buffer_data = state.get("buffer", None)
        if buffer_data is not None:
            self.buffer = np.array(buffer_data, dtype=np.float32)
        else:
            self.buffer = np.zeros((MAX_HOLD_SAMPLES, 2), dtype=np.float32)
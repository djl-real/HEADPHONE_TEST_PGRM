# modules/hold.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt
from audio_module import AudioModule

MAX_BLOCK_HOLD = 25  # maximum history depth


class Hold(AudioModule):
    """Effect that replays the last N audio blocks when active."""

    def __init__(self):
        super().__init__(input_count=1, output_count=1)
        self.hold_active = False
        self.halt_enabled = True  # checkbox state
        self.block_hold = 10  # how many recent blocks to store
        self.buffer = [np.zeros((512, 2), dtype=np.float32) for _ in range(MAX_BLOCK_HOLD)]
        self.pointer = 0
        self.play_index = 0

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        # When hold is active
        if self.hold_active:
            if not self.halt_enabled:
                # Still call receive even though we won't use it
                _ = self.input_node.receive(frames)

            # Loop over last n held blocks
            block = self.buffer[self.play_index % self.block_hold]
            self.play_index = (self.play_index + 1) % self.block_hold
            return block.copy().astype(np.float32)

        # Otherwise pass-through and record
        x = self.input_node.receive(frames)
        self.buffer[self.pointer % MAX_BLOCK_HOLD] = x.copy()
        self.pointer = (self.pointer + 1) % MAX_BLOCK_HOLD
        self.play_index = self.pointer - self.block_hold
        return x.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Creates UI for controlling hold length and activation."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        title = QLabel("Hold Effect")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # --- Hold amount slider ---
        slider_layout = QHBoxLayout()
        self.hold_slider = QSlider(Qt.Orientation.Vertical)
        self.hold_slider.setMinimum(1)
        self.hold_slider.setMaximum(MAX_BLOCK_HOLD)
        self.hold_slider.setValue(self.block_hold)
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
        self.value_label = QLabel(f"Blocks: {self.block_hold}")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label)

        # Connect signals
        self.hold_slider.valueChanged.connect(self._on_slider_change)
        self.hold_button.toggled.connect(self._on_hold_toggle)
        self.halt_checkbox.toggled.connect(self._on_halt_toggle)

        return widget

    def _on_slider_change(self, value):
        self.block_hold = value
        self.value_label.setText(f"Blocks: {value}")

    def _on_hold_toggle(self, state):
        self.hold_active = state
        if not state:
            # Reset playback pointer when exiting hold
            self.play_index = self.pointer - self.block_hold

    def _on_halt_toggle(self, state):
        self.halt_enabled = state

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "hold_active": self.hold_active,
            "halt_enabled": self.halt_enabled,
            "block_hold": self.block_hold,
            "pointer": self.pointer,
            "play_index": self.play_index,
            # Buffers can be stored as a list of lists for serialization
            "buffer": [buf.tolist() for buf in self.buffer],
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.hold_active = state.get("hold_active", False)
        self.halt_enabled = state.get("halt_enabled", True)
        self.block_hold = state.get("block_hold", 10)
        self.pointer = state.get("pointer", 0)
        self.play_index = state.get("play_index", 0)
        buffer_data = state.get("buffer", None)
        if buffer_data is not None:
            # Convert lists back to numpy arrays
            self.buffer = [np.array(b, dtype=np.float32) for b in buffer_data]
        else:
            # Fallback to empty buffers
            self.buffer = [np.zeros((512, 2), dtype=np.float32) for _ in range(MAX_BLOCK_HOLD)]

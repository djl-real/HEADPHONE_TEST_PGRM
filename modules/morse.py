# modules/morse.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QLineEdit, QCheckBox
)
from PyQt6.QtCore import Qt
from audio_module import AudioModule

# Morse timing constants
DOT_UNITS = 1
DASH_UNITS = 3
INTRA_CHAR_UNITS = 1
INTER_CHAR_UNITS = 3
INTER_WORD_UNITS = 7
END_GAP_UNITS = 10  # silence gap after a full message before repeating

MORSE_DICT = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..",
    "E": ".", "F": "..-.", "G": "--.", "H": "....",
    "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.",
    "Q": "--.-", "R": ".-.", "S": "...", "T": "-",
    "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--",
    "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
    " ": " "
}

DEFAULT_BLOCK_SIZE = 512


class Morse(AudioModule):
    """Morse code sequencer module."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=1, output_count=1)
        self.sample_rate = sample_rate

        # UI parameters
        self.text = ""
        self.speed_units_per_sec = 20  # doubled again for faster default
        self.applied = False  # no transmission yet
        self.halt_enabled = True  # new checkbox default

        # Sequencer state
        self.sequence = []   # list of (is_on, duration_in_blocks)
        self.seq_index = 0
        self.block_progress = 0

    # --- Generate output ---
    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        # Silence output until "Apply" is used
        if not self.applied:
            if not self.halt_enabled:
                _ = self.input_node.receive(frames)
            return np.zeros((frames, 2), dtype=np.float32)

        out = np.zeros((frames, 2), dtype=np.float32)
        if not self.sequence:
            if not self.halt_enabled:
                _ = self.input_node.receive(frames)
            return out

        i = 0
        while i < frames:
            if self.seq_index >= len(self.sequence):
                # Restart after full message
                self.seq_index = 0
                self.block_progress = 0

            is_on, duration_blocks = self.sequence[self.seq_index]
            remaining = duration_blocks * DEFAULT_BLOCK_SIZE - self.block_progress
            chunk = min(frames - i, remaining)

            if is_on:
                chunk_data = self.input_node.receive(chunk)
                out[i:i + chunk] = chunk_data
            else:
                # Silence, but still call receive if halt disabled
                if not self.halt_enabled:
                    _ = self.input_node.receive(chunk)

            i += chunk
            self.block_progress += chunk

            if self.block_progress >= duration_blocks * DEFAULT_BLOCK_SIZE:
                self.seq_index += 1
                self.block_progress = 0

        return out.astype(np.float32)

    # --- UI ---
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("Morse Code Text:"))
        self.text_input = QLineEdit()
        layout.addWidget(self.text_input)

        layout.addWidget(QLabel("Speed"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(40)
        self.speed_slider.setValue(20)
        layout.addWidget(self.speed_slider)

        # Halt checkbox
        self.halt_checkbox = QCheckBox("Halt")
        self.halt_checkbox.setChecked(True)
        layout.addWidget(self.halt_checkbox)

        self.apply_button = QPushButton("Apply")
        layout.addWidget(self.apply_button)

        self.apply_button.clicked.connect(self._on_apply)
        self.halt_checkbox.toggled.connect(self._on_halt_toggle)

        return widget

    # --- Apply button callback ---
    def _on_apply(self):
        self.text = self.text_input.text().upper()
        self.speed_units_per_sec = self.speed_slider.value()
        self.sequence = self._text_to_sequence(self.text)
        self.seq_index = 0
        self.block_progress = 0
        self.applied = True

    def _on_halt_toggle(self, state):
        self.halt_enabled = state

    # --- Convert text to Morse sequence ---
    def _text_to_sequence(self, text):
        seq = []
        for idx, char in enumerate(text):
            morse = MORSE_DICT.get(char, "")
            for j, symbol in enumerate(morse):
                if symbol == ".":
                    seq.append((True, DOT_UNITS))
                elif symbol == "-":
                    seq.append((True, DASH_UNITS))
                if j < len(morse) - 1:
                    seq.append((False, INTRA_CHAR_UNITS))
            if char != " " and idx < len(text) - 1:
                seq.append((False, INTER_CHAR_UNITS))
            if char == " ":
                seq.append((False, INTER_WORD_UNITS))

        # Add a final gap after full message
        seq.append((False, END_GAP_UNITS))

        # Convert units → blocks
        blocks_per_unit = max(1, int(self.sample_rate / DEFAULT_BLOCK_SIZE / self.speed_units_per_sec))
        seq_scaled = [(on, max(1, int(duration * blocks_per_unit))) for on, duration in seq]
        return seq_scaled

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "text": self.text,
            "speed_units_per_sec": self.speed_units_per_sec,
            "sequence": self.sequence,
            "seq_index": self.seq_index,
            "block_progress": self.block_progress,
            "applied": self.applied,
            "halt_enabled": self.halt_enabled,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.text = state.get("text", "")
        self.speed_units_per_sec = state.get("speed_units_per_sec", 20)
        self.sequence = state.get("sequence", [])
        self.seq_index = state.get("seq_index", 0)
        self.block_progress = state.get("block_progress", 0)
        self.applied = state.get("applied", False)
        self.halt_enabled = state.get("halt_enabled", True)

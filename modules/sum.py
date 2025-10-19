# modules/sum.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QSlider, QPushButton, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt
from audio_module import AudioModule

DB_MIN = -80.0
DB_MAX = 10.0


def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)


class Sum(AudioModule):
    """4:1 mixer with per-input faders, mutes, and a master fader."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=4, output_count=1)
        self.sample_rate = sample_rate

        # Default dB and mute states
        self.input_db = [-6.0, -6.0, -6.0, -6.0]
        self.master_db = 0.0
        self.input_muted = [False, False, False, False]
        self.master_muted = False

    def generate(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)

        # Mix all inputs
        for i in range(4):
            if self.input_nodes[i]:
                inp = self.input_nodes[i].receive(frames)
                if self.input_muted[i]:
                    inp = np.zeros_like(inp)
                gain = db_to_linear(self.input_db[i])
                out += inp * gain

        # Apply master mute and gain
        if self.master_muted:
            return np.zeros_like(out)

        out *= db_to_linear(self.master_db)
        out = np.clip(out, -1.0, 1.0)
        return out

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("SUM MIXER (4 ➜ 1)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Add spacing above faders
        layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        sliders_layout = QHBoxLayout()
        self.sliders = []
        self.mute_buttons = []
        self.db_labels = []

        # Create 4 input strips + 1 master strip
        for i in range(5):
            strip = QVBoxLayout()
            strip.setSpacing(6)

            # Label
            label = QLabel(f"Input {i+1}" if i < 4 else "Master")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            strip.addWidget(label)

            # Volume slider
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setMinimum(0)
            slider.setMaximum(100)
            init_db = self.input_db[i] if i < 4 else self.master_db
            slider.setValue(int((init_db - DB_MIN) / (DB_MAX - DB_MIN) * 100))
            slider.setTickInterval(10)
            slider.setTickPosition(QSlider.TickPosition.TicksLeft)
            slider.setFixedHeight(220)
            strip.addWidget(slider, alignment=Qt.AlignmentFlag.AlignCenter)

            # dB label
            db_label = QLabel(f"{init_db:.1f} dB")
            db_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            strip.addWidget(db_label)

            # Mute button (copied from endpoint.py style)
            mute_button = QPushButton("Mute")
            mute_button.setCheckable(True)
            mute_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #95a5a6;
                }
            """)
            strip.addWidget(mute_button, alignment=Qt.AlignmentFlag.AlignCenter)

            # Connect signals
            def make_slider_cb(idx=i, lbl=db_label):
                def on_value_change(value: int):
                    db_val = DB_MIN + (value / 100) * (DB_MAX - DB_MIN)
                    lbl.setText(f"{db_val:.1f} dB")
                    if idx < 4:
                        self.input_db[idx] = db_val
                    else:
                        self.master_db = db_val
                return on_value_change

            slider.valueChanged.connect(make_slider_cb())

            def make_mute_cb(idx=i):
                def on_toggle(state: bool):
                    if idx < 4:
                        self.input_muted[idx] = state
                    else:
                        self.master_muted = state
                return on_toggle

            mute_button.toggled.connect(make_mute_cb())

            # Store references
            self.sliders.append(slider)
            self.db_labels.append(db_label)
            self.mute_buttons.append(mute_button)

            sliders_layout.addLayout(strip)

            # Add horizontal spacing between strips
            if i < 4:
                sliders_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))

        layout.addLayout(sliders_layout)
        layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "input_db": self.input_db,
            "master_db": self.master_db,
            "input_muted": self.input_muted,
            "master_muted": self.master_muted,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.input_db = state.get("input_db", [-6.0, -6.0, -6.0, -6.0])
        self.master_db = state.get("master_db", 0.0)
        self.input_muted = state.get("input_muted", [False, False, False, False])
        self.master_muted = state.get("master_muted", False)
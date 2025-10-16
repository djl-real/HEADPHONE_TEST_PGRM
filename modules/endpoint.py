# modules/endpoint.py
import numpy as np
import traceback
from PyQt6.QtWidgets import QWidget, QSlider, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt
from audio_module import AudioModule

DB_MIN = -80.0   # represent -inf dB
DB_MAX = 10.0

def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)


class Endpoint(AudioModule):
    """Final output module with vertical DJ-style volume fader and mute button"""
    def __init__(self, volume_db=-80.0):
        super().__init__(input_count=1, output_count=0)
        self.volume_db = volume_db
        self.muted = False

    def generate(self, frames: int) -> np.ndarray:
        # Always receive from input, even when muted
        try:
            if self.input_node is None:
                data = np.zeros((frames, 2), dtype=np.float32)
            else:
                data = self.input_node.receive(frames)
            
            if self.muted:
                return np.zeros_like(data, dtype=np.float32)

            gain = db_to_linear(self.volume_db)
            return data * gain
        except Exception:
            print("endpoint generate failed")
            traceback.print_exc()
            return np.zeros((frames, 2), dtype=np.float32)

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Volume label
        self.label = QLabel(f"Volume: {self.volume_db:.1f} dB")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        # Horizontal layout for slider and tick labels
        slider_layout = QHBoxLayout()

        # Slider
        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(int((self.volume_db - DB_MIN) / (DB_MAX - DB_MIN) * 100))
        self.slider.setTickInterval(10)
        self.slider.setTickPosition(QSlider.TickPosition.TicksLeft)
        self.slider.setFixedHeight(200)
        slider_layout.addWidget(self.slider)

        # Labels on the left
        label_layout = QVBoxLayout()
        for db in range(int(DB_MAX), int(DB_MIN)-1, -10):
            text = f"{db} dB" if db > DB_MIN else "-∞ dB"
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_layout.addWidget(lbl)
        slider_layout.addLayout(label_layout)

        layout.addLayout(slider_layout)

        # Mute button
        self.mute_button = QPushButton("Mute")
        self.mute_button.setCheckable(True)
        self.mute_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #95a5a6;
            }
        """)
        layout.addWidget(self.mute_button)
        self.mute_button.toggled.connect(lambda state: setattr(self, "muted", state))

        # Slider change updates volume_db
        def on_value_change(value: int):
            self.volume_db = DB_MIN + (value / 100) * (DB_MAX - DB_MIN)
            self.label.setText(f"Volume: {self.volume_db:.1f} dB")

        self.slider.valueChanged.connect(on_value_change)

        return widget

        # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "volume_db": self.volume_db,
            "muted": self.muted,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.volume_db = state.get("volume_db", DB_MIN)
        self.muted = state.get("muted", False)

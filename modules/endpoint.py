# modules/endpoint.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QSlider, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QSize
from audio_module import AudioModule

DB_MIN = -80.0   # represent -inf dB
DB_MAX = 10.0

def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)

class EndpointModule(AudioModule):
    """Final output module with vertical DJ-style volume fader"""
    def __init__(self, volume_db=-80.0):
        super().__init__(has_input=True, has_output=False)
        self.volume_db = volume_db  # default silent
        self.muted = False  # optional mute flag if needed

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None or self.muted:
            return np.zeros((frames, 2), dtype=np.float32)
        data = self.input_node.receive(frames)
        gain = db_to_linear(self.volume_db)
        return data * gain

    def get_ui(self) -> QWidget:
        """
        Returns a QWidget containing a vertical slider with labels every 10 dB,
        representing volume from -inf (~-80 dB) to +10 dB.
        """
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Volume label
        label = QLabel(f"Volume: {self.volume_db:.1f} dB")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        # Horizontal layout for slider and tick labels
        slider_layout = QHBoxLayout()

        # Slider
        slider = QSlider(Qt.Orientation.Vertical)
        slider.setMinimum(0)
        slider.setMaximum(100)
        # Initialize slider to match volume_db
        slider.setValue(int((self.volume_db - DB_MIN) / (DB_MAX - DB_MIN) * 100))
        slider.setTickInterval(10)
        slider.setTickPosition(QSlider.TickPosition.TicksLeft)
        slider.setFixedHeight(200)
        slider_layout.addWidget(slider)

        # Labels on the left
        label_layout = QVBoxLayout()
        for db in range(int(DB_MAX), int(DB_MIN)-1, -10):
            text = f"{db} dB" if db > DB_MIN else "-∞ dB"
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_layout.addWidget(lbl)
        slider_layout.addLayout(label_layout)

        layout.addLayout(slider_layout)

        # Slider change updates volume_db
        def on_value_change(value: int):
            self.volume_db = DB_MIN + (value / 100) * (DB_MAX - DB_MIN)
            label.setText(f"Volume: {self.volume_db:.1f} dB")

        slider.valueChanged.connect(on_value_change)

        return widget
    
    def sizeHint(self):
        """Return custom width/height for the fader."""
        return QSize(200, 250)  # width x height

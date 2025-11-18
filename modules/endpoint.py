# modules/endpoint.py
import numpy as np
import time
import traceback

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QWidget, QSlider, QVBoxLayout, QLabel,
    QHBoxLayout, QPushButton, QLineEdit
)

from audio_module import AudioModule

DB_MIN = -80.0
DB_MAX = 10.0

def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)

def linear_to_db(x):
    if x <= 1e-7:
        return DB_MIN
    return 20 * np.log10(x)


# =============================================================================
# VU METER WIDGET
# =============================================================================
class VUMeter(QWidget):
    """Vertical VU meter with peak-hold."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(5)
        self.setMaximumWidth(5)

        self.current_db = DB_MIN
        self.peak_db = DB_MIN
        self.peak_hold_time = 0.0    # timestamp when peak last updated

        # update timer (30 Hz)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    def update_level(self, db_value):
        # smooth ballistic
        ballistic = 0.2
        self.current_db = (1 - ballistic) * self.current_db + ballistic * db_value

        # peak hold logic
        if db_value > self.peak_db:
            self.peak_db = db_value
            self.peak_hold_time = time.time()
        else:
            # drop peak after 1 second
            if time.time() - self.peak_hold_time > 1.0:
                self.peak_db -= 1.5
                if self.peak_db < DB_MIN:
                    self.peak_db = DB_MIN

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        # background
        painter.fillRect(0, 0, w, h, QColor(30, 30, 30))

        # height scaling
        def db_to_y(db):
            norm = (db - DB_MIN) / (DB_MAX - DB_MIN)
            norm = max(0.0, min(1.0, norm))
            return int((1 - norm) * h)

        # meter body
        meter_y = db_to_y(self.current_db)
        painter.fillRect(0, meter_y, w, h - meter_y, self.level_color())

        # peak hold line
        peak_y = db_to_y(self.peak_db)
        painter.fillRect(0, peak_y - 2, w, 4, QColor(255, 50, 50))

    def level_color(self):
        """Green → Yellow → Red based on dB range."""
        if self.current_db > -3:
            return QColor(255, 30, 30)  # red
        elif self.current_db > -12:
            return QColor(255, 220, 0)  # yellow
        else:
            return QColor(0, 200, 0)    # green


# =============================================================================
# ENDPOINT
# =============================================================================
class Endpoint(AudioModule):
    def __init__(self, volume_db=-80.0):
        super().__init__(input_count=1, output_count=0)
        self.volume_db = volume_db
        self.muted = False
        self.nickname = ""

        self.last_peak_level = 0.0

        # NEW: hold all UI widgets associated with this module
        self.widgets = []

    # -------------------------------------------------------------------------
    # AUDIO
    # -------------------------------------------------------------------------
    def generate(self, frames: int) -> np.ndarray:
        try:
            if self.input_node is None:
                data = np.zeros((frames, 2), dtype=np.float32)
            else:
                data = self.input_node.receive(frames)

            gain = db_to_linear(self.volume_db)

            if self.muted:
                metersig = np.zeros_like(data)
                data_out = metersig
            else:
                data_out = data * gain
                metersig = data_out

            peak = float(np.max(np.abs(metersig)))
            peak_db = linear_to_db(peak)
            self.last_peak_level = peak_db

            # update meter on all widgets
            for ui in self.widgets:
                if hasattr(ui, "vu_meter"):
                    ui.vu_meter.update_level(peak_db)

            return data_out

        except Exception:
            print("endpoint generate failed")
            traceback.print_exc()
            return np.zeros((frames, 2), dtype=np.float32)

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ---- Nickname ----
        widget.nickname_box = QLineEdit()
        widget.nickname_box.setPlaceholderText("Enter nickname...")
        widget.nickname_box.setText(self.nickname)
        widget.nickname_box.setFixedWidth(100)
        widget.nickname_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nick_layout = QHBoxLayout()
        nick_layout.addStretch()
        nick_layout.addWidget(widget.nickname_box)
        nick_layout.addStretch()
        layout.addLayout(nick_layout)

        # ---- Volume label ----
        widget.label = QLabel(f"Volume: {self.volume_db:.1f} dB")
        widget.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(widget.label)

        # ---- Slider + VU ----
        fader_meter = QHBoxLayout()

        widget.slider = QSlider(Qt.Orientation.Vertical)
        widget.slider.setMinimum(0)
        widget.slider.setMaximum(100)
        widget.slider.setValue(int((self.volume_db - DB_MIN) / (DB_MAX - DB_MIN) * 100))
        widget.slider.setTickInterval(10)
        widget.slider.setTickPosition(QSlider.TickPosition.TicksLeft)
        widget.slider.setFixedHeight(200)

        # labels for dB ticks
        label_layout = QVBoxLayout()
        for db in range(int(DB_MAX), int(DB_MIN)-1, -10):
            text = f"{db} dB" if db > DB_MIN else "-∞ dB"
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_layout.addWidget(lbl)

        widget.vu_meter = VUMeter()

        fader_meter.addStretch()
        fader_meter.addWidget(widget.slider)
        fader_meter.addLayout(label_layout)
        fader_meter.addWidget(widget.vu_meter)
        fader_meter.addStretch()

        layout.addLayout(fader_meter)

        # ---- Mute button ----
        widget.mute_button = QPushButton("Mute")
        widget.mute_button.setCheckable(True)
        widget.mute_button.setChecked(self.muted)
        widget.mute_button.setFixedWidth(80)
        widget.mute_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #95a5a6;
            }
        """)
        layout.addWidget(widget.mute_button)

        # ---- Connections ----
        widget.mute_button.toggled.connect(lambda s: setattr(self, "muted", s))

        def on_value_change(value):
            self.volume_db = DB_MIN + (value / 100) * (DB_MAX - DB_MIN)
            widget.label.setText(f"Volume: {self.volume_db:.1f} dB")

        widget.slider.valueChanged.connect(on_value_change)
        widget.nickname_box.textChanged.connect(lambda t: setattr(self, "nickname", t))

        # final UI styling
        widget.setMaximumWidth(140)

        # STORE UI IN MODULE
        self.widgets.append(widget)

        return widget

    # -------------------------------------------------------------------------
    # SYNC ALL UIS
    # -------------------------------------------------------------------------
    def sync(self):
        """Force all UI widgets to match the module state."""
        for ui in self.widgets:

            # nickname
            if ui.nickname_box.text() != self.nickname:
                ui.nickname_box.blockSignals(True)
                ui.nickname_box.setText(self.nickname)
                ui.nickname_box.blockSignals(False)

            # volume label
            ui.label.setText(f"Volume: {self.volume_db:.1f} dB")

            # slider value
            expected = int((self.volume_db - DB_MIN) / (DB_MAX - DB_MIN) * 100)
            if ui.slider.value() != expected:
                ui.slider.blockSignals(True)
                ui.slider.setValue(expected)
                ui.slider.blockSignals(False)

            # mute toggle
            if ui.mute_button.isChecked() != self.muted:
                ui.mute_button.blockSignals(True)
                ui.mute_button.setChecked(self.muted)
                ui.mute_button.blockSignals(False)

            # VU meter
            if hasattr(ui, "vu_meter"):
                ui.vu_meter.current_db = self.last_peak_level

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------
    def serialize(self):
        data = super().serialize()
        data.update({
            "volume_db": self.volume_db,
            "muted": self.muted,
            "nickname": self.nickname,
        })
        return data

    def deserialize(self, state):
        super().deserialize(state)
        self.volume_db = state.get("volume_db", DB_MIN)
        self.muted = state.get("muted", False)
        self.nickname = state.get("nickname", "")
        self.sync()   # <-- ensure all UIs update

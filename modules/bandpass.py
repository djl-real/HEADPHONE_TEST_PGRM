# modules/bandpass.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal
from audio_module import AudioModule
from scipy.signal import butter, lfilter_zi, lfilter


class RangeSlider(QWidget):
    """A simple two-handle horizontal slider to select a range."""
    rangeChanged = pyqtSignal(int, int)  # low, high

    def __init__(self, minimum=1, maximum=20000, low=1, high=20000, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setMinimumWidth(400)
        self.minimum = minimum
        self.maximum = maximum
        self.low = low
        self.high = high
        self.dragging_low = False
        self.dragging_high = False

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor
        from PyQt6.QtCore import QRect
        painter = QPainter(self)
        rect = self.rect()
        half_height = rect.height() // 2
        top = (rect.height() - half_height) // 2

        # Draw background
        painter.setBrush(QColor(180, 180, 180))
        painter.drawRect(QRect(0, top, rect.width(), half_height))

        # Draw range selection
        low_pos = self.value_to_pos(self.low)
        high_pos = self.value_to_pos(self.high)
        painter.setBrush(QColor(220, 180, 30))
        painter.drawRect(QRect(low_pos, top, high_pos - low_pos, half_height))

        # Draw handles
        handle_width = 10
        painter.setBrush(QColor(80, 80, 80))
        painter.drawRect(QRect(low_pos - handle_width // 2, top, handle_width, half_height))
        painter.drawRect(QRect(high_pos - handle_width // 2, top, handle_width, half_height))

    def value_to_pos(self, val):
        return int((val - self.minimum) / (self.maximum - self.minimum) * self.width())

    def pos_to_value(self, x):
        return int(x / self.width() * (self.maximum - self.minimum) + self.minimum)

    def mousePressEvent(self, event):
        x = event.position().x()
        if abs(x - self.value_to_pos(self.low)) < 10:
            self.dragging_low = True
        elif abs(x - self.value_to_pos(self.high)) < 10:
            self.dragging_high = True

    def mouseMoveEvent(self, event):
        x = event.position().x()
        val = self.pos_to_value(x)
        if self.dragging_low:
            self.low = max(self.minimum, min(val, self.high - 1))
            self.rangeChanged.emit(self.low, self.high)
            self.update()
        elif self.dragging_high:
            self.high = min(self.maximum, max(val, self.low + 1))
            self.rangeChanged.emit(self.low, self.high)
            self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_low = False
        self.dragging_high = False


class Bandpass(AudioModule):
    """Real-time biquad bandpass filter with stateful filtering."""

    def __init__(self, sample_rate=44100, lp_freq=20000.0, hp_freq=1.0):
        super().__init__(input_count=1, output_count=1)
        self.sample_rate = sample_rate
        self.lp_freq = lp_freq
        self.hp_freq = hp_freq

        self.b, self.a = None, None
        self.zi = None  # per-channel state
        self._update_coeffs()

    def _update_coeffs(self, num_channels=2):
        nyq = 0.5 * self.sample_rate
        low = max(self.hp_freq / nyq, 1e-5)
        high = min(self.lp_freq / nyq, 0.99999)
        self.b, self.a = butter(N=2, Wn=[low, high], btype='band')

        # initialize per-channel filter state
        self.zi = [lfilter_zi(self.b, self.a) * 0.0 for _ in range(num_channels)]

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        if x is None or len(x) == 0:
            return np.zeros((frames, 2), dtype=np.float32)

        # Make sure zi has correct number of channels
        if self.zi is None or len(self.zi) != x.shape[1]:
            self._update_coeffs(num_channels=x.shape[1])

        y = np.zeros_like(x)
        for ch in range(x.shape[1]):
            y[:, ch], self.zi[ch] = lfilter(self.b, self.a, x[:, ch], zi=self.zi[ch])

        return y.astype(np.float32)

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel(f"Bandpass: {self.hp_freq:.0f} Hz – {self.lp_freq:.0f} Hz")
        layout.addWidget(label)

        slider = RangeSlider(low=int(self.hp_freq), high=int(self.lp_freq))
        layout.addWidget(slider)

        def on_range_change(low, high):
            self.hp_freq = low
            self.lp_freq = high
            label.setText(f"Bandpass: {self.hp_freq:.0f} Hz – {self.lp_freq:.0f} Hz")
            # Recompute filter with same number of channels
            num_channels = self.zi[0].shape[0] if self.zi else 2
            self._update_coeffs(num_channels=num_channels)

        slider.rangeChanged.connect(on_range_change)
        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "sample_rate": self.sample_rate,
            "lp_freq": self.lp_freq,
            "hp_freq": self.hp_freq,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.sample_rate = state.get("sample_rate", 44100)
        self.lp_freq = state.get("lp_freq", 20000.0)
        self.hp_freq = state.get("hp_freq", 1.0)
        self._update_coeffs()

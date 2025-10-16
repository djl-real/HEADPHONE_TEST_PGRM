# modules/bandpass.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor
from audio_module import AudioModule


class RangeSlider(QWidget):
    """A simple two-handle horizontal slider to select a range."""
    rangeChanged = pyqtSignal(int, int)  # low, high

    def __init__(self, minimum=1, maximum=20000, low=1, high=20000, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)  # half the previous height
        self.setMinimumWidth(400)  # make it longer
        self.minimum = minimum
        self.maximum = maximum
        self.low = low
        self.high = high
        self.dragging_low = False
        self.dragging_high = False

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()

        half_height = rect.height() // 2
        top = (rect.height() - half_height) // 2  # center vertically

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
        """Map value to widget X coordinate."""
        return int((val - self.minimum) / (self.maximum - self.minimum) * self.width())

    def pos_to_value(self, x):
        """Map widget X coordinate to value."""
        return int(x / self.width() * (self.maximum - self.minimum) + self.minimum)

    def mousePressEvent(self, event):
        low_pos = self.value_to_pos(self.low)
        high_pos = self.value_to_pos(self.high)
        x = event.position().x()

        if abs(x - low_pos) < 10:
            self.dragging_low = True
        elif abs(x - high_pos) < 10:
            self.dragging_high = True

    def mouseMoveEvent(self, event):
        x = event.position().x()
        val = self.pos_to_value(x)
        if self.dragging_low:
            self.low = max(self.minimum, min(val, self.high))
            self.rangeChanged.emit(self.low, self.high)
            self.update()
        elif self.dragging_high:
            self.high = min(self.maximum, max(val, self.low))
            self.rangeChanged.emit(self.low, self.high)
            self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_low = False
        self.dragging_high = False


class Bandpass(AudioModule):
    """One-pole bandpass filter with a range slider for low and high cutoff frequencies."""

    def __init__(self, sample_rate=44100, lp_freq=20000.0, hp_freq=1.0):
        super().__init__(input_count=1, output_count=1)
        self.sample_rate = sample_rate
        self.lp_freq = lp_freq
        self.hp_freq = hp_freq
        self.prev_x = np.zeros(2)
        self.prev_hp = np.zeros(2)
        self.prev_lp = np.zeros(2)

    def generate(self, frames: int) -> np.ndarray:
        """Generate bandpass-filtered audio using FFT for the given number of frames."""
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)  # shape: (frames, channels)
        y = np.zeros_like(x)

        # FFT parameters
        N = frames
        freqs = np.fft.rfftfreq(N, d=1.0 / self.sample_rate)  # frequencies for positive FFT bins

        # Create bandpass mask
        mask = (freqs >= self.hp_freq) & (freqs <= self.lp_freq)

        # Apply FFT per channel
        for ch in range(x.shape[1]):
            X = np.fft.rfft(x[:, ch])
            X_filtered = X * mask  # zero out frequencies outside band
            y[:, ch] = np.fft.irfft(X_filtered, n=N)

        return y.astype(np.float32)

    def get_ui(self) -> QWidget:
        """Return QWidget with single range slider for low/high cutoff."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel(f"Bandpass: {self.hp_freq:.0f} Hz – {self.lp_freq:.0f} Hz")
        layout.addWidget(label)

        slider = RangeSlider()
        layout.addWidget(slider)

        def on_range_change(low, high):
            self.hp_freq = low
            self.lp_freq = high
            label.setText(f"Bandpass: {self.hp_freq:.0f} Hz – {self.lp_freq:.0f} Hz")

        slider.rangeChanged.connect(on_range_change)

        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "sample_rate": self.sample_rate,
            "lp_freq": self.lp_freq,
            "hp_freq": self.hp_freq,
            "prev_x": self.prev_x.tolist(),
            "prev_hp": self.prev_hp.tolist(),
            "prev_lp": self.prev_lp.tolist(),
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.sample_rate = state.get("sample_rate", 44100)
        self.lp_freq = state.get("lp_freq", 20000.0)
        self.hp_freq = state.get("hp_freq", 1.0)
        self.prev_x = np.array(state.get("prev_x", [0.0, 0.0]), dtype=np.float32)
        self.prev_hp = np.array(state.get("prev_hp", [0.0, 0.0]), dtype=np.float32)
        self.prev_lp = np.array(state.get("prev_lp", [0.0, 0.0]), dtype=np.float32)

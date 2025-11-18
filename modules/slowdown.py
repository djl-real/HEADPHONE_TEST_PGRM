# modules/slowdown.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import InputNode, OutputNode


class Slowdown(AudioModule):
    """
    Positive interval (N > 0):
        Pull input once every N generates.
        Repeat last buffer otherwise.

    Zero (N == 0):
        Normal behavior: receive once per generate.

    Negative interval (N < 0):
        Call receive() abs(N) times per generate.
        Only the *last* received buffer is output.
    """

    def __init__(self, frame_interval=0):
        super().__init__(input_count=1, output_count=1)

        self.frame_interval = int(frame_interval)   # now allowed to be -5..5
        self._frame_counter = 0
        self._last_buffer = None

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        interval = self.frame_interval

        # -------------------------------------------------
        # Case: negative → speedup
        # -------------------------------------------------
        if interval < 0:
            n = abs(interval)
            buf = None
            for _ in range(n):
                buf = self.input_node.receive(frames)
            self._last_buffer = buf  # store the final one
            return buf.astype(np.float32)

        # -------------------------------------------------
        # Case: zero → normal passthrough
        # -------------------------------------------------
        if interval == 0:
            self._last_buffer = self.input_node.receive(frames)
            return self._last_buffer.astype(np.float32)

        # -------------------------------------------------
        # Case: positive → slowdown
        # -------------------------------------------------
        self._frame_counter += 1

        if self._last_buffer is None or self._frame_counter >= interval:
            self._frame_counter = 0
            self._last_buffer = self.input_node.receive(frames)

        return self._last_buffer.astype(np.float32)

    def get_ui(self) -> QWidget:
        """UI with a frame interval slider (-5 to 5)."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel(f"Frame Interval: {self.frame_interval}")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(-5)
        slider.setMaximum(5)
        slider.setValue(self.frame_interval)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(1)
        layout.addWidget(slider)

        def on_change(val):
            self.frame_interval = int(val)
            label.setText(f"Frame Interval: {self.frame_interval}")

        slider.valueChanged.connect(on_change)
        return widget

    # ---------------- Serialization ----------------

    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "frame_interval": self.frame_interval,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.frame_interval = int(state.get("frame_interval", 0))
        self._frame_counter = 0
        self._last_buffer = None

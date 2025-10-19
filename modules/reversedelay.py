import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import InputNode, OutputNode


class ReverseDelay(AudioModule):
    """Reverse delay: plays reversed echoes before the dry signal."""

    def __init__(self, delay_ms=500, mix=0.5):
        """
        Args:
            delay_ms (int): delay time in milliseconds before echo appears.
            mix (float): wet/dry balance (0.0–1.0)
        """
        super().__init__(input_count=1, output_count=1)
        self.delay_ms = delay_ms
        self.mix = mix

        # Audio buffer for reversing
        self.sample_rate = 48000  # Adjust if global rate differs
        self.buffer_size = int(self.sample_rate * (self.delay_ms / 1000.0))
        self.buffer = np.zeros((self.buffer_size, 2), dtype=np.float32)
        self.write_index = 0

    # --------------------------------------------------------
    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        if x is None:
            return np.zeros((frames, 2), dtype=np.float32)

        # Reverse buffer processing
        y = np.zeros_like(x)

        for i in range(frames):
            # Write incoming sample to buffer
            self.buffer[self.write_index] = x[i]

            # Compute reversed read index
            rev_index = (self.buffer_size - 1 - self.write_index) % self.buffer_size
            reversed_sample = self.buffer[rev_index]

            # Mix reversed echo with dry
            y[i] = (1.0 - self.mix) * x[i] + self.mix * reversed_sample

            # Increment circular buffer
            self.write_index = (self.write_index + 1) % self.buffer_size

        return y.astype(np.float32)

    # --------------------------------------------------------
    def get_ui(self) -> QWidget:
        """Return a QWidget with delay and mix sliders."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Delay label + slider
        delay_label = QLabel(f"Delay: {self.delay_ms} ms")
        layout.addWidget(delay_label)

        delay_slider = QSlider(Qt.Orientation.Horizontal)
        delay_slider.setMinimum(100)
        delay_slider.setMaximum(2000)
        delay_slider.setValue(self.delay_ms)
        layout.addWidget(delay_slider)

        def on_delay_change(val):
            self.delay_ms = val
            delay_label.setText(f"Delay: {val} ms")
            # Rebuild buffer
            self.buffer_size = int(self.sample_rate * (self.delay_ms / 1000.0))
            self.buffer = np.zeros((self.buffer_size, 2), dtype=np.float32)
            self.write_index = 0

        delay_slider.valueChanged.connect(on_delay_change)

        # Mix label + slider
        mix_label = QLabel(f"Mix: {self.mix:.2f}")
        layout.addWidget(mix_label)

        mix_slider = QSlider(Qt.Orientation.Horizontal)
        mix_slider.setMinimum(0)
        mix_slider.setMaximum(100)
        mix_slider.setValue(int(self.mix * 100))
        layout.addWidget(mix_slider)

        def on_mix_change(val):
            self.mix = val / 100.0
            mix_label.setText(f"Mix: {self.mix:.2f}")

        mix_slider.valueChanged.connect(on_mix_change)

        return widget

    # --------------------------------------------------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "delay_ms": self.delay_ms,
            "mix": self.mix,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.delay_ms = state.get("delay_ms", 500)
        self.mix = state.get("mix", 0.5)
        self.buffer_size = int(self.sample_rate * (self.delay_ms / 1000.0))
        self.buffer = np.zeros((self.buffer_size, 2), dtype=np.float32)
        self.write_index = 0

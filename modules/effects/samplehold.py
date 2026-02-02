import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule

class SampleHoldMod(AudioModule):
    """
    FFT-based Sample & Hold Pitch Modulation.
    Uses spectral resampling for faster, smoother pitch jumps.
    """

    def __init__(self, rate_hz=2.0, depth=12.0, sample_rate=48000):
        super().__init__(input_count=1, output_count=1)
        self.rate_hz = rate_hz
        self.depth = depth
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.current_pitch_shift = 1.0
        self.block_size = 512  # FFT window size
        self.buffer = np.zeros((0, 2), dtype=np.float32)

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        if x is None or len(x) == 0:
            return np.zeros((frames, 2), dtype=np.float32)

        self.buffer = np.concatenate((self.buffer, x), axis=0)
        out_blocks = []

        while len(self.buffer) >= self.block_size:
            block = self.buffer[:self.block_size]
            self.buffer = self.buffer[self.block_size:]

            # Update pitch every few blocks
            self.phase += self.rate_hz * self.block_size / self.sample_rate
            if self.phase >= 1.0:
                self.phase -= 1.0
                semitone_offset = (np.random.rand() - 0.5) * self.depth
                self.current_pitch_shift = 2 ** (semitone_offset / 12.0)

            # FFT-based pitch shift
            shifted = self.pitch_shift_fft(block, self.current_pitch_shift)
            out_blocks.append(shifted)

        if len(out_blocks) == 0:
            return np.zeros((frames, 2), dtype=np.float32)

        output = np.concatenate(out_blocks, axis=0)
        return output[:frames].astype(np.float32)

    def pitch_shift_fft(self, block: np.ndarray, shift: float) -> np.ndarray:
        """
        Simple spectral-domain pitch shift by rescaling FFT bins.
        """
        n = len(block)
        out = np.zeros_like(block)
        for ch in range(block.shape[1]):
            X = np.fft.rfft(block[:, ch])
            freqs = np.fft.rfftfreq(n)
            shifted_bins = np.interp(freqs, np.clip(freqs / shift, 0, 1), np.abs(X), left=0, right=0)
            phase = np.angle(X)
            Y = shifted_bins * np.exp(1j * phase)
            y = np.fft.irfft(Y)
            out[:, ch] = y.real
        return out

    # ---------------- UI ----------------
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label_rate = QLabel(f"Rate: {self.rate_hz:.2f} Hz")
        layout.addWidget(label_rate)
        slider_rate = QSlider(Qt.Orientation.Horizontal)
        slider_rate.setMinimum(1)
        slider_rate.setMaximum(200)
        slider_rate.setValue(int(self.rate_hz * 10))
        layout.addWidget(slider_rate)

        label_depth = QLabel(f"Depth: {self.depth:.1f} semitones")
        layout.addWidget(label_depth)
        slider_depth = QSlider(Qt.Orientation.Horizontal)
        slider_depth.setMinimum(0)
        slider_depth.setMaximum(240)
        slider_depth.setValue(int(self.depth * 10))
        layout.addWidget(slider_depth)

        def on_rate_change(val):
            self.rate_hz = val / 10.0
            label_rate.setText(f"Rate: {self.rate_hz:.2f} Hz")

        def on_depth_change(val):
            self.depth = val / 10.0
            label_depth.setText(f"Depth: {self.depth:.1f} semitones")

        slider_rate.valueChanged.connect(on_rate_change)
        slider_depth.valueChanged.connect(on_depth_change)

        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "rate_hz": self.rate_hz,
            "depth": self.depth,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.rate_hz = state.get("rate_hz", 2.0)
        self.depth = state.get("depth", 12.0)

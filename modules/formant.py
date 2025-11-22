import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import InputNode, OutputNode


class Formant(AudioModule):
    """
    Shift vocal formants without affecting pitch.
    Implemented by spectral envelope warping.

    Parameter:
        shift_ratio (0.5 = deeper/demonic, 2.0 = child-like)
    """

    def __init__(self, shift_ratio: float = 1.0):
        super().__init__(input_count=1, output_count=1)
        self.shift_ratio = shift_ratio

        # FFT parameters
        self.fft_size = 1024
        self.hop = self.fft_size // 2

        # STFT overlap buffer
        self.prev_input = np.zeros((self.fft_size,), dtype=np.float32)
        self.prev_output = np.zeros((self.fft_size,), dtype=np.float32)


    # ============================================================
    # AUDIO PROCESSING
    # ============================================================
    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 1), dtype=np.float32)

        # Mono source
        x = self.input_node.receive(frames)
        if x.ndim > 1:
            x = x[:, 0]  # collapse to mono

        # Append to buffer
        buf = np.concatenate([self.prev_input, x])
        out = np.zeros_like(buf)

        window = np.hanning(self.fft_size)

        # Process in hops
        pos = 0
        while pos + self.fft_size < len(buf):
            frame = buf[pos:pos + self.fft_size] * window
            spec = np.fft.rfft(frame)

            # magnitude + phase
            mag = np.abs(spec)
            phase = np.angle(spec)

            # -----------------------
            # FORMANT WARPING
            # -----------------------
            n_bins = len(mag)
            warped = np.zeros_like(mag)

            for i in range(n_bins):
                src_idx = int(i / self.shift_ratio)
                src_idx = np.clip(src_idx, 0, n_bins - 1)
                warped[i] = mag[src_idx]

            # Recombine
            new_spec = warped * np.exp(1j * phase)
            new_frame = np.fft.irfft(new_spec)

            # Overlap-add
            out[pos:pos + self.fft_size] += new_frame * window
            pos += self.hop

        # Save tail for next call
        self.prev_input = buf[-self.fft_size:]
        self.prev_output = out[-self.fft_size:]

        # Extract aligned block
        y = out[self.fft_size:self.fft_size + frames]

        # --------------------------------------------------------
        # 🔥 Apply amplitude compensation based on formant shift
        # --------------------------------------------------------
        if self.shift_ratio != 0:
            y = y / self.shift_ratio

        return y.reshape(-1, 1).astype(np.float32)


    # ============================================================
    # UI
    # ============================================================
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        label = QLabel(f"Formant Shift: {self.shift_ratio:.2f}x")
        layout.addWidget(label)

        # ---- 5-STATE DISCRETE SLIDER ----
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(8)
        slider.setSingleStep(1)
        slider.setTickInterval(1)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        # mapping index → shift ratio
        positions = [0.25, 0.33, 0.5, 0.66, 1.0, 1.5, 2.0, 3.0, 4.0]

        # find closest index to current shift_ratio
        def closest_index(val: float) -> int:
            return int(np.argmin([abs(val - p) for p in positions]))

        slider.setValue(closest_index(self.shift_ratio))
        layout.addWidget(slider)

        def on_change(index):
            self.shift_ratio = positions[index]
            label.setText(f"Formant Shift: {self.shift_ratio:.2f}x")

        slider.valueChanged.connect(on_change)

        return widget


    # ============================================================
    # SERIALIZATION
    # ============================================================
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "shift_ratio": self.shift_ratio,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.shift_ratio = state.get("shift_ratio", 1.0)

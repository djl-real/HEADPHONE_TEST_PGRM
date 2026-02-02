import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule
from nodes import InputNode, OutputNode


class Formant(AudioModule):
    """
    Shift vocal formants without affecting pitch.
    Streaming processing with sine/cosine crossfade between FFT blocks.
    """

    def __init__(self, shift_ratio: float = 1.0):
        super().__init__(input_count=1, output_count=1)
        self.shift_ratio = shift_ratio

        # FFT parameters
        self.fft_size = 1024
        self.hop = self.fft_size // 2

        # Overlap buffers
        self.prev_input = np.zeros(self.fft_size, dtype=np.float32)
        self.prev_output = np.zeros(self.fft_size, dtype=np.float32)

        # Output buffer for partial frames
        self.output_buffer = np.zeros(0, dtype=np.float32)

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 1), dtype=np.float32)

        # Mono input
        x = self.input_node.receive(frames)
        if x.ndim > 1:
            x = x[:, 0]

        # Append previous tail for overlap
        buf = np.concatenate([self.prev_input, x])
        out = np.zeros_like(buf)

        window = np.hanning(self.fft_size)
        pos = 0
        while pos + self.fft_size <= len(buf):
            frame = buf[pos:pos + self.fft_size] * window
            spec = np.fft.rfft(frame)

            mag = np.abs(spec)
            phase = np.angle(spec)

            # FORMANT WARPING
            n_bins = len(mag)
            warped = np.zeros_like(mag)
            for i in range(n_bins):
                src_idx = int(i / self.shift_ratio)
                src_idx = np.clip(src_idx, 0, n_bins - 1)
                warped[i] = mag[src_idx]

            new_spec = warped * np.exp(1j * phase)
            new_frame = np.fft.irfft(new_spec)

            # Overlap-add with sine/cosine crossfade
            if pos == 0:
                out[pos:pos + self.fft_size] = new_frame * window
            else:
                overlap = self.hop
                t = np.linspace(0, np.pi / 2, overlap)
                fade_in = np.sin(t)           # 0 -> 1
                fade_out = np.cos(t)          # 1 -> 0

                # Crossfade previous output with current frame
                out[pos:pos + overlap] = (
                    self.prev_output[-overlap:] * fade_out +
                    new_frame[:overlap] * fade_in
                )
                out[pos + overlap:pos + self.fft_size] += new_frame[overlap:] * window[overlap:]

            pos += self.hop

        # Save tail for next call
        self.prev_input = buf[-self.fft_size:]
        self.prev_output = out[-self.fft_size:]

        # Normalize by shift ratio
        if self.shift_ratio != 0:
            out = out / self.shift_ratio

        # Deliver requested frames
        self.output_buffer = np.concatenate([self.output_buffer, out[self.fft_size:]])
        y = self.output_buffer[:frames]
        self.output_buffer = self.output_buffer[frames:]

        return y.reshape(-1, 1).astype(np.float32)

    # ============================================================
    # UI
    # ============================================================
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        label = QLabel(f"Formant Shift: {self.shift_ratio:.2f}x")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(8)
        slider.setSingleStep(1)
        slider.setTickInterval(1)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        positions = [0.25, 0.33, 0.5, 0.66, 1.0, 1.5, 2.0, 3.0, 4.0]

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

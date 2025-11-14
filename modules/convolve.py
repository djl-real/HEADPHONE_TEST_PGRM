# modules/convolve.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule


class Convolve(AudioModule):
    """
    DSP convolution module.
    Input 0: audio signal
    Input 1: impulse response (IR)
    
    Performs FFT overlap-add convolution block-by-block.
    """

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=2, output_count=1)

        self.sample_rate = sample_rate

        # Wet/dry mix for UI usefulness
        self.mix = 1.0

        # FFT state
        self.fft_size = None
        self.ir_fft = None
        self.ir_len = 0
        self.overlap = None

    # ---------------- Internal Helpers ----------------

    def _prepare_ir(self, ir_block: np.ndarray):
        """
        Converts an incoming IR block into persistent FFT form.
        This is called automatically whenever input 1 gives new data.
        """

        if ir_block is None or ir_block.shape[0] == 0:
            return

        # Convert IR to mono (typical for convolution IRs)
        if ir_block.ndim == 2 and ir_block.shape[1] > 1:
            ir_block = ir_block.mean(axis=1)

        self.ir_len = len(ir_block)

        # Choose FFT size = next pow2 larger than block + IR
        fft_size = 1
        target = self.ir_len * 2
        while fft_size < target:
            fft_size *= 2

        self.fft_size = fft_size

        # Compute FFT of IR
        self.ir_fft = np.fft.rfft(ir_block, fft_size)

        # Overlap buffer for overlap-add
        self.overlap = np.zeros((fft_size,), dtype=np.float32)

    # ---------------- DSP Generate ----------------

    def generate(self, frames: int) -> np.ndarray:
        """
        Real-time convolution using overlap-add FFT convolution.
        """

        # Get audio input
        x = self.input_nodes[0].receive(frames) if self.input_nodes[0] else np.zeros((frames, 2))
        # Get IR (second input)
        ir = self.input_nodes[1].receive(frames) if self.input_nodes[1] else None

        # If new IR arrives, reinitialize FFT buffers
        if ir is not None and np.any(ir):
            self._prepare_ir(ir[:, 0] if ir.ndim == 2 else ir)

        # If no IR loaded yet → bypass
        if self.ir_fft is None:
            return x.astype(np.float32)

        # Stereo support: convolve left & right independently
        out = np.zeros_like(x, dtype=np.float32)

        # Process each channel
        for ch in range(x.shape[1]):
            out[:, ch] = self._process_channel(x[:, ch])

        # Wet/dry mix
        out = (out * self.mix) + (x * (1.0 - self.mix))

        return out.astype(np.float32)

    def _process_channel(self, x: np.ndarray) -> np.ndarray:
        """FFT block convolution for one channel."""

        fft_size = self.fft_size
        half = len(x)

        # FFT input block with zero padding
        X = np.fft.rfft(x, fft_size)

        # Multiply in frequency domain
        Y = X * self.ir_fft

        # IFFT back to time domain
        y = np.fft.irfft(Y, fft_size)

        # Overlap-add
        y[:len(self.overlap)] += self.overlap

        # Store new overlap
        self.overlap = y[half:].copy()

        # Output first half (the valid part)
        return y[:half]

    # ---------------- UI ----------------

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        label = QLabel(f"Mix: {self.mix:.2f}")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(1000)
        slider.setValue(int(self.mix * 1000))
        layout.addWidget(slider)

        def on_slider(val):
            self.mix = val / 1000.0
            label.setText(f"Mix: {self.mix:.2f}")

        slider.valueChanged.connect(on_slider)

        return widget

    # ---------------- Serialization ----------------

    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "sample_rate": self.sample_rate,
            "mix": self.mix,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.sample_rate = state.get("sample_rate", 44100)
        self.mix = state.get("mix", 1.0)

        # IR is NOT serialized because it may be large; user reloads IR

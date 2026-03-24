# modules/speed_warble.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QCheckBox
)
from PyQt6.QtCore import Qt
from source.audio_module import AudioModule


class SpeedWarble(AudioModule):
    """Smoothly and randomly varies playback speed, creating tape-warble or
    time-stretch effects.  Uses linear interpolation for resampling — no FFTs.

    Parameters
    ----------
    depth : float  0.0–1.0
        How far the speed can deviate from 1.0.
        At 0 the effect is bypassed; at 1.0 speed can swing between ~0.25× and ~4×.
    rate : float  0.01–10.0  (Hz)
        How quickly a new random speed target is chosen.
    smoothing : float  0.0–1.0
        One-pole smoothing on the speed envelope.  Higher = slower, smoother
        transitions.  Internally mapped to a coefficient.
    """

    # Maximum internal ring-buffer length in samples (stereo).
    # Must be large enough to cover the slowest playback speed across the
    # largest expected block size.  64 k samples ≈ 1.45 s @ 44.1 kHz.
    _RING_SIZE = 65536

    def __init__(self):
        super().__init__(input_count=1, output_count=1)

        # --- User-facing parameters ---
        self.depth = 0.5        # 0 – 1
        self.rate = 1.0         # Hz – how often a new target is picked
        self.smoothing = 0.7    # 0 – 1  (maps to pole coefficient)

        # --- Internal state ---
        self._ring = np.zeros((self._RING_SIZE, 2), dtype=np.float32)
        self._write_pos = 0          # integer write head into ring buffer
        self._read_pos = 0.0         # fractional read head
        self._current_speed = 1.0    # smoothed instantaneous speed
        self._target_speed = 1.0     # where we're heading
        self._phase = 0.0            # accumulator to decide when to pick a new target
        self._rng = np.random.default_rng()

    # ------------------------------------------------------------------ core
    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)

        # Write incoming audio into ring buffer
        self._write_ring(x)

        # Bypass when depth is essentially zero
        if self.depth < 1e-6:
            # Keep read head in sync with write head
            self._read_pos = float(self._write_pos)
            self._current_speed = 1.0
            self._target_speed = 1.0
            return x.astype(np.float32)

        # Smoothing coefficient (per-sample) derived from the 0–1 knob.
        # 0 → alpha=1 (instant), 1 → alpha≈0.0001 (very slow)
        alpha = 1.0 - self.smoothing * 0.9999

        # Speed deviation limits based on depth
        min_speed = max(1.0 - self.depth * 0.75, 0.25)
        max_speed = 1.0 + self.depth * 3.0  # up to 4× at full depth

        # How many seconds one block represents (assume 44100 if unknown)
        block_dur = frames / 44100.0

        out = np.empty((frames, 2), dtype=np.float32)
        ring = self._ring
        size = self._RING_SIZE

        rp = self._read_pos
        speed = self._current_speed
        target = self._target_speed
        phase = self._phase

        for i in range(frames):
            # --- Decide whether to pick a new random target ---
            phase += self.rate / 44100.0
            if phase >= 1.0:
                phase -= 1.0
                target = self._rng.uniform(min_speed, max_speed)

            # --- Smooth toward target ---
            speed += alpha * (target - speed)

            # --- Read with linear interpolation ---
            idx = int(rp) % size
            frac = rp - int(rp)
            idx_next = (idx + 1) % size
            sample = ring[idx] * (1.0 - frac) + ring[idx_next] * frac
            out[i] = sample

            rp += speed

        # Keep read_pos from drifting unboundedly
        rp = rp % size

        self._read_pos = rp
        self._current_speed = speed
        self._target_speed = target
        self._phase = phase

        return out

    # --------------------------------------------------------------- helpers
    def _write_ring(self, data: np.ndarray):
        n = len(data)
        size = self._RING_SIZE
        wp = self._write_pos
        end = wp + n
        if end <= size:
            self._ring[wp:end] = data
        else:
            first = size - wp
            self._ring[wp:] = data[:first]
            self._ring[:n - first] = data[first:]
        self._write_pos = end % size

    # ------------------------------------------------------------------- UI
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        title = QLabel("Speed Warble")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # --- Depth slider (0 – 100 → 0.0 – 1.0) ---
        depth_row = QHBoxLayout()
        depth_lbl = QLabel("Depth")
        self._depth_val = QLabel(f"{self.depth:.2f}")
        depth_slider = QSlider(Qt.Orientation.Horizontal)
        depth_slider.setMinimum(0)
        depth_slider.setMaximum(100)
        depth_slider.setValue(int(self.depth * 100))
        depth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        depth_slider.setTickInterval(25)
        depth_row.addWidget(depth_lbl)
        depth_row.addWidget(depth_slider)
        depth_row.addWidget(self._depth_val)
        layout.addLayout(depth_row)

        def on_depth(v):
            self.depth = v / 100.0
            self._depth_val.setText(f"{self.depth:.2f}")
        depth_slider.valueChanged.connect(on_depth)

        # --- Rate slider (1 – 1000 → 0.01 – 10.0 Hz, log-ish) ---
        rate_row = QHBoxLayout()
        rate_lbl = QLabel("Rate")
        self._rate_val = QLabel(f"{self.rate:.2f} Hz")
        rate_slider = QSlider(Qt.Orientation.Horizontal)
        rate_slider.setMinimum(1)
        rate_slider.setMaximum(1000)
        rate_slider.setValue(int(self.rate * 100))
        rate_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        rate_slider.setTickInterval(250)
        rate_row.addWidget(rate_lbl)
        rate_row.addWidget(rate_slider)
        rate_row.addWidget(self._rate_val)
        layout.addLayout(rate_row)

        def on_rate(v):
            self.rate = v / 100.0
            self._rate_val.setText(f"{self.rate:.2f} Hz")
        rate_slider.valueChanged.connect(on_rate)

        # --- Smoothing slider (0 – 100 → 0.0 – 1.0) ---
        smooth_row = QHBoxLayout()
        smooth_lbl = QLabel("Smooth")
        self._smooth_val = QLabel(f"{self.smoothing:.2f}")
        smooth_slider = QSlider(Qt.Orientation.Horizontal)
        smooth_slider.setMinimum(0)
        smooth_slider.setMaximum(100)
        smooth_slider.setValue(int(self.smoothing * 100))
        smooth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        smooth_slider.setTickInterval(25)
        smooth_row.addWidget(smooth_lbl)
        smooth_row.addWidget(smooth_slider)
        smooth_row.addWidget(self._smooth_val)
        layout.addLayout(smooth_row)

        def on_smooth(v):
            self.smoothing = v / 100.0
            self._smooth_val.setText(f"{self.smoothing:.2f}")
        smooth_slider.valueChanged.connect(on_smooth)

        return widget

    # --------------------------------------------------------- serialization
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "depth": self.depth,
            "rate": self.rate,
            "smoothing": self.smoothing,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.depth = state.get("depth", 0.5)
        self.rate = state.get("rate", 1.0)
        self.smoothing = state.get("smoothing", 0.7)
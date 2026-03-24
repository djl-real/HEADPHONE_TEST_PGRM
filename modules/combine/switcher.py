# modules/stochastic_switcher.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QCheckBox
)
from PyQt6.QtCore import Qt
from source.audio_module import AudioModule


class Switcher(AudioModule):
    """Randomly alternates between two audio inputs with smooth crossfading.

    A timer counts down samples until the next switch event.  When it fires,
    the active input flips and a new random interval is chosen.  A raised-
    cosine crossfade smooths each transition — short fades give glitchy hard
    cuts, long fades give dreamy morphing between the two signals.

    Parameters
    ----------
    rate : float  0.1 – 20.0 Hz
        Average switch rate.  The actual interval is randomised around this.
    randomness : float  0.0 – 1.0
        How much the interval varies.  0 = perfectly periodic, 1 = highly
        irregular (interval can be 0.1× to 3× the base period).
    fade_ms : float  1 – 500 ms
        Crossfade duration.  1 ms ≈ a hard glitch cut, 500 ms ≈ slow morph.
    bias : float  0.0 – 1.0
        Probability of choosing input B on each switch.  0.5 = equal chance,
        0.0 = always A, 1.0 = always B.
    """

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=2, output_count=1)
        self.sample_rate = sample_rate

        # User parameters
        self.rate = 3.0         # Hz
        self.randomness = 0.5   # 0–1
        self.fade_ms = 30.0     # milliseconds
        self.bias = 0.5         # probability of picking input B

        # Internal state
        self._init_runtime_state()

    def _init_runtime_state(self):
        """Initialise all non-serialised runtime state.
        Called from __init__ and deserialize so that every attribute
        generate() touches is guaranteed to exist."""
        self._active = 0            # 0 = input A, 1 = input B
        self._fade_pos = 0          # how many samples into current fade
        self._fading = False        # whether a crossfade is in progress
        self._fade_from = 0         # which input we're fading FROM
        self._rng = np.random.default_rng()
        self._samples_until_switch = self._pick_interval()

    # ------------------------------------------------------------ helpers
    def _pick_interval(self) -> int:
        """Choose how many samples until the next switch."""
        base = self.sample_rate / max(self.rate, 0.1)
        if self.randomness < 1e-6:
            return int(base)
        lo = base * (1.0 - self.randomness * 0.9)
        hi = base * (1.0 + self.randomness * 2.0)
        return max(1, int(self._rng.uniform(lo, hi)))

    @property
    def _fade_samples(self) -> int:
        return max(1, int(self.fade_ms * self.sample_rate / 1000.0))

    # --------------------------------------------------------------- core
    def generate(self, frames: int) -> np.ndarray:
        # Receive both inputs (silence if disconnected)
        a = (self.input_nodes[0].receive(frames)
             if self.input_nodes[0]
             else np.zeros((frames, 2), dtype=np.float32))
        b = (self.input_nodes[1].receive(frames)
             if self.input_nodes[1]
             else np.zeros((frames, 2), dtype=np.float32))

        inputs = [a.astype(np.float64), b.astype(np.float64)]
        out = np.empty((frames, 2), dtype=np.float64)
        fade_len = self._fade_samples

        i = 0
        while i < frames:
            if self._fading:
                # How many fade samples remain in this block
                fade_remaining = fade_len - self._fade_pos
                chunk = min(frames - i, fade_remaining)
                end = i + chunk

                # Raised cosine crossfade: 0 → 1 over fade_len samples
                t = np.arange(self._fade_pos, self._fade_pos + chunk, dtype=np.float64) / fade_len
                blend = 0.5 - 0.5 * np.cos(t * np.pi)  # 0 at start, 1 at end

                fade_to = 1 - self._fade_from
                # blend goes from 0 (old) to 1 (new)
                for ch in range(2):
                    out[i:end, ch] = (
                        inputs[self._fade_from][i:end, ch] * (1.0 - blend) +
                        inputs[fade_to][i:end, ch] * blend
                    )

                self._fade_pos += chunk
                i = end

                if self._fade_pos >= fade_len:
                    # Fade complete
                    self._fading = False
                    self._active = 1 - self._fade_from
                    self._fade_pos = 0
            else:
                # Steady state: output the active input
                chunk = min(frames - i, self._samples_until_switch)
                end = i + chunk
                out[i:end] = inputs[self._active][i:end]

                self._samples_until_switch -= chunk
                i = end

                if self._samples_until_switch <= 0:
                    # Trigger a switch
                    self._fade_from = self._active
                    # Decide which input to switch to
                    if self._rng.random() < self.bias:
                        new_target = 1
                    else:
                        new_target = 0
                    # If we'd switch to the same input, flip instead
                    if new_target == self._active:
                        new_target = 1 - new_target
                    self._active = new_target  # will be finalised after fade
                    self._fading = True
                    self._fade_pos = 0
                    self._samples_until_switch = self._pick_interval()

        return out.astype(np.float32)

    # ------------------------------------------------------------------ UI
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        title = QLabel("Switcher")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # --- Rate slider (1 – 200 → 0.1 – 20.0 Hz) ---
        rate_row = QHBoxLayout()
        rate_lbl = QLabel("Rate")
        self._rate_val = QLabel(f"{self.rate:.1f} Hz")
        rate_slider = QSlider(Qt.Orientation.Horizontal)
        rate_slider.setMinimum(1)
        rate_slider.setMaximum(200)
        rate_slider.setValue(int(self.rate * 10))
        rate_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        rate_slider.setTickInterval(50)
        rate_row.addWidget(rate_lbl)
        rate_row.addWidget(rate_slider)
        rate_row.addWidget(self._rate_val)
        layout.addLayout(rate_row)

        # --- Randomness slider (0 – 100 → 0.0 – 1.0) ---
        rand_row = QHBoxLayout()
        rand_lbl = QLabel("Random")
        self._rand_val = QLabel(f"{self.randomness:.2f}")
        rand_slider = QSlider(Qt.Orientation.Horizontal)
        rand_slider.setMinimum(0)
        rand_slider.setMaximum(100)
        rand_slider.setValue(int(self.randomness * 100))
        rand_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        rand_slider.setTickInterval(25)
        rand_row.addWidget(rand_lbl)
        rand_row.addWidget(rand_slider)
        rand_row.addWidget(self._rand_val)
        layout.addLayout(rand_row)

        # --- Fade slider (1 – 500 ms) ---
        fade_row = QHBoxLayout()
        fade_lbl = QLabel("Fade")
        self._fade_val = QLabel(f"{self.fade_ms:.0f} ms")
        fade_slider = QSlider(Qt.Orientation.Horizontal)
        fade_slider.setMinimum(1)
        fade_slider.setMaximum(500)
        fade_slider.setValue(int(self.fade_ms))
        fade_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        fade_slider.setTickInterval(100)
        fade_row.addWidget(fade_lbl)
        fade_row.addWidget(fade_slider)
        fade_row.addWidget(self._fade_val)
        layout.addLayout(fade_row)

        # --- Bias slider (0 – 100 → 0.0 – 1.0) ---
        bias_row = QHBoxLayout()
        bias_lbl = QLabel("Bias")
        self._bias_val = QLabel(f"{self.bias:.2f}")
        bias_slider = QSlider(Qt.Orientation.Horizontal)
        bias_slider.setMinimum(0)
        bias_slider.setMaximum(100)
        bias_slider.setValue(int(self.bias * 100))
        bias_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        bias_slider.setTickInterval(25)
        bias_row.addWidget(bias_lbl)
        bias_row.addWidget(bias_slider)
        bias_row.addWidget(self._bias_val)
        layout.addLayout(bias_row)

        # Connect signals
        rate_slider.valueChanged.connect(self._on_rate)
        rand_slider.valueChanged.connect(self._on_random)
        fade_slider.valueChanged.connect(self._on_fade)
        bias_slider.valueChanged.connect(self._on_bias)

        return widget

    def _on_rate(self, val):
        self.rate = val / 10.0
        self._rate_val.setText(f"{self.rate:.1f} Hz")

    def _on_random(self, val):
        self.randomness = val / 100.0
        self._rand_val.setText(f"{self.randomness:.2f}")

    def _on_fade(self, val):
        self.fade_ms = float(val)
        self._fade_val.setText(f"{val} ms")

    def _on_bias(self, val):
        self.bias = val / 100.0
        self._bias_val.setText(f"{self.bias:.2f}")

    # -------------------------------------------------------- serialization
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "sample_rate": self.sample_rate,
            "rate": self.rate,
            "randomness": self.randomness,
            "fade_ms": self.fade_ms,
            "bias": self.bias,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.sample_rate = state.get("sample_rate", 44100)
        self.rate = state.get("rate", 3.0)
        self.randomness = state.get("randomness", 0.5)
        self.fade_ms = state.get("fade_ms", 30.0)
        self.bias = state.get("bias", 0.5)

        # Re-init runtime state that isn't serialized
        self._init_runtime_state()
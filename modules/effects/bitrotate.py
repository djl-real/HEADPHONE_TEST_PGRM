# modules/bit_mangler.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QComboBox
)
from PyQt6.QtCore import Qt
from source.audio_module import AudioModule


class BitRotate(AudioModule):
    """Treats audio samples as raw integers and manipulates their bits.

    Modes
    -----
    Rotate Left   – circular bit rotation left by N positions
    Rotate Right  – circular bit rotation right by N positions
    Byte Swap     – swap high and low bytes of each 16-bit sample
    Bit Reverse   – reverse the order of all bits
    XOR Pattern   – XOR every sample with a repeating bit pattern
    Bit Shuffle   – permute bits using a fixed scramble table

    Parameters
    ----------
    mode : int      index into MODE_NAMES
    amount : int    0–15, meaning varies per mode (rotation count, pattern
                    index, shuffle seed, etc.)
    mix : float     0.0–1.0  dry/wet crossfade
    """

    MODE_NAMES = [
        "Rotate Left",
        "Rotate Right",
        "Byte Swap",
        "Bit Reverse",
        "XOR Pattern",
        "Bit Shuffle",
    ]

    # Pre-built XOR masks (16-bit) selected by amount knob
    _XOR_MASKS = np.array([
        0x0000, 0x00FF, 0xFF00, 0xFFFF,
        0x5555, 0xAAAA, 0x0F0F, 0xF0F0,
        0x3333, 0xCCCC, 0x1234, 0xABCD,
        0xDEAD, 0xBEEF, 0x8001, 0x7FFE,
    ], dtype=np.uint16)

    def __init__(self):
        super().__init__(input_count=1, output_count=1)
        self.mode = 0
        self.amount = 4
        self.mix = 1.0
        # Pre-compute lookup tables for modes that benefit from them
        self._build_bit_reverse_lut()
        self._build_shuffle_luts()

    # ------------------------------------------------------------ LUT setup
    def _build_bit_reverse_lut(self):
        """256-entry byte-reverse table."""
        self._byte_rev = np.zeros(256, dtype=np.uint8)
        for i in range(256):
            self._byte_rev[i] = int(f"{i:08b}"[::-1], 2)

    def _build_shuffle_luts(self):
        """16 deterministic bit-permutation tables (one per amount value).
        Each table is a length-16 permutation of bit positions."""
        rng = np.random.default_rng(seed=42)
        self._shuffle_perms = []
        for _ in range(16):
            perm = np.arange(16)
            rng.shuffle(perm)
            self._shuffle_perms.append(perm)

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _float_to_int16(x: np.ndarray) -> np.ndarray:
        """Convert float32 audio (-1..1) to int16, then view as uint16."""
        clamped = np.clip(x, -1.0, 1.0)
        return (clamped * 32767).astype(np.int16).view(np.uint16)

    @staticmethod
    def _uint16_to_float(u: np.ndarray) -> np.ndarray:
        """Convert uint16 back to float32 audio."""
        return u.view(np.int16).astype(np.float32) / 32767.0

    def _rotate_left(self, samples: np.ndarray, n: int) -> np.ndarray:
        n = n % 16
        if n == 0:
            return samples
        return ((samples << n) | (samples >> (16 - n))) & 0xFFFF

    def _rotate_right(self, samples: np.ndarray, n: int) -> np.ndarray:
        n = n % 16
        if n == 0:
            return samples
        return ((samples >> n) | (samples << (16 - n))) & 0xFFFF

    def _byte_swap(self, samples: np.ndarray) -> np.ndarray:
        return ((samples >> 8) | (samples << 8)) & 0xFFFF

    def _bit_reverse(self, samples: np.ndarray) -> np.ndarray:
        lo = samples & 0xFF
        hi = (samples >> 8) & 0xFF
        new_lo = self._byte_rev[hi.astype(np.intp)]
        new_hi = self._byte_rev[lo.astype(np.intp)]
        return (new_hi.astype(np.uint16) << 8) | new_lo.astype(np.uint16)

    def _xor_pattern(self, samples: np.ndarray, idx: int) -> np.ndarray:
        mask = self._XOR_MASKS[idx % len(self._XOR_MASKS)]
        return samples ^ mask

    def _bit_shuffle(self, samples: np.ndarray, idx: int) -> np.ndarray:
        perm = self._shuffle_perms[idx % len(self._shuffle_perms)]
        out = np.zeros_like(samples)
        for dst, src in enumerate(perm):
            bit = (samples >> src) & 1
            out |= (bit << dst).astype(np.uint16)
        return out

    # --------------------------------------------------------------- core
    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)

        if self.mix < 1e-6:
            return x.astype(np.float32)

        # Work on a flat view so both channels are mangled identically
        dry = x.astype(np.float32)
        flat = dry.ravel()
        samples = self._float_to_int16(flat)

        if self.mode == 0:
            mangled = self._rotate_left(samples, self.amount)
        elif self.mode == 1:
            mangled = self._rotate_right(samples, self.amount)
        elif self.mode == 2:
            mangled = self._byte_swap(samples)
        elif self.mode == 3:
            mangled = self._bit_reverse(samples)
        elif self.mode == 4:
            mangled = self._xor_pattern(samples, self.amount)
        elif self.mode == 5:
            mangled = self._bit_shuffle(samples, self.amount)
        else:
            mangled = samples

        wet = self._uint16_to_float(mangled).reshape(dry.shape)

        # Dry/wet crossfade
        out = dry * (1.0 - self.mix) + wet * self.mix
        return out.astype(np.float32)

    # ------------------------------------------------------------------ UI
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        title = QLabel("Bit Rotate")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # --- Mode selector ---
        mode_row = QHBoxLayout()
        mode_lbl = QLabel("Mode")
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(self.MODE_NAMES)
        self._mode_combo.setCurrentIndex(self.mode)
        mode_row.addWidget(mode_lbl)
        mode_row.addWidget(self._mode_combo)
        layout.addLayout(mode_row)

        # --- Amount slider (0 – 15) ---
        amt_row = QHBoxLayout()
        amt_lbl = QLabel("Amount")
        self._amt_val = QLabel(str(self.amount))
        self._amt_slider = QSlider(Qt.Orientation.Horizontal)
        self._amt_slider.setMinimum(0)
        self._amt_slider.setMaximum(15)
        self._amt_slider.setValue(self.amount)
        self._amt_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._amt_slider.setTickInterval(1)
        amt_row.addWidget(amt_lbl)
        amt_row.addWidget(self._amt_slider)
        amt_row.addWidget(self._amt_val)
        layout.addLayout(amt_row)

        # --- Mix slider (0 – 100 → 0.0 – 1.0) ---
        mix_row = QHBoxLayout()
        mix_lbl = QLabel("Mix")
        self._mix_val = QLabel(f"{self.mix:.2f}")
        self._mix_slider = QSlider(Qt.Orientation.Horizontal)
        self._mix_slider.setMinimum(0)
        self._mix_slider.setMaximum(100)
        self._mix_slider.setValue(int(self.mix * 100))
        self._mix_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._mix_slider.setTickInterval(25)
        mix_row.addWidget(mix_lbl)
        mix_row.addWidget(self._mix_slider)
        mix_row.addWidget(self._mix_val)
        layout.addLayout(mix_row)

        # Connect signals
        self._mode_combo.currentIndexChanged.connect(self._on_mode_change)
        self._amt_slider.valueChanged.connect(self._on_amount_change)
        self._mix_slider.valueChanged.connect(self._on_mix_change)

        return widget

    def _on_mode_change(self, idx):
        self.mode = idx

    def _on_amount_change(self, val):
        self.amount = val
        self._amt_val.setText(str(val))

    def _on_mix_change(self, val):
        self.mix = val / 100.0
        self._mix_val.setText(f"{self.mix:.2f}")

    # -------------------------------------------------------- serialization
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "mode": self.mode,
            "amount": self.amount,
            "mix": self.mix,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.mode = state.get("mode", 0)
        self.amount = state.get("amount", 4)
        self.mix = state.get("mix", 1.0)
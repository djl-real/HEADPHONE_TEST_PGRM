# modules/clip.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt

from audio_module import AudioModule


class Clip(AudioModule):
    """Audio clipping module with absolute and relative modes."""

    MODE_ABSOLUTE = "Absolute"
    MODE_RELATIVE = "Relative"

    def __init__(self):
        super().__init__(input_count=1, output_count=1)

        # --- Defaults ---
        self.mode = self.MODE_RELATIVE   # DEFAULT = RELATIVE
        self.abs_level = 1.0
        self.rel_percent = 100.0
        self.normalize_relative = False

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------
    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames).astype(np.float32)
        y = np.copy(x)

        if self.mode == self.MODE_ABSOLUTE:
            clip_val = max(1e-6, self.abs_level)
            np.clip(y, -clip_val, clip_val, out=y)

        elif self.mode == self.MODE_RELATIVE:
            peak = np.max(np.abs(x))
            if peak > 0:
                scale = self.rel_percent / 100.0
                clip_val = peak * scale
                clip_val = max(1e-6, clip_val)

                # 🔥 Normalize (amplify) before clipping
                if self.normalize_relative:
                    y /= scale

                np.clip(y, -clip_val, clip_val, out=y)

        return y

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ---------------- Mode Selector ----------------
        layout.addWidget(QLabel("Clip Mode"))
        mode_box = QComboBox()
        mode_box.addItems([self.MODE_RELATIVE, self.MODE_ABSOLUTE])
        mode_box.setCurrentText(self.mode)
        layout.addWidget(mode_box)

        # ---------------- Absolute Controls ----------------
        abs_label = QLabel(f"Absolute Level: {self.abs_level:.2f}")
        abs_slider = QSlider(Qt.Orientation.Horizontal)
        abs_slider.setRange(1, 200)      # 0.01 – 2.00
        abs_slider.setValue(int(self.abs_level * 100))

        layout.addWidget(abs_label)
        layout.addWidget(abs_slider)

        # ---------------- Relative Controls ----------------
        rel_label = QLabel(f"Relative Level: {self.rel_percent:.0f}%")
        rel_slider = QSlider(Qt.Orientation.Horizontal)
        rel_slider.setRange(1, 100)
        rel_slider.setValue(int(self.rel_percent))

        normalize_box = QCheckBox("Normalize before clip")
        normalize_box.setChecked(self.normalize_relative)

        layout.addWidget(rel_label)
        layout.addWidget(rel_slider)
        layout.addWidget(normalize_box)

        # ---------------- Logic ----------------
        def update_visibility():
            is_abs = self.mode == self.MODE_ABSOLUTE
            abs_label.setVisible(is_abs)
            abs_slider.setVisible(is_abs)

            is_rel = self.mode == self.MODE_RELATIVE
            rel_label.setVisible(is_rel)
            rel_slider.setVisible(is_rel)
            normalize_box.setVisible(is_rel)

        def on_mode_change(text):
            self.mode = text
            update_visibility()

        def on_abs_change(val):
            self.abs_level = val / 100.0
            abs_label.setText(f"Absolute Level: {self.abs_level:.2f}")

        def on_rel_change(val):
            self.rel_percent = float(val)
            rel_label.setText(f"Relative Level: {self.rel_percent:.0f}%")

        def on_normalize_toggle(state):
            self.normalize_relative = bool(state)

        mode_box.currentTextChanged.connect(on_mode_change)
        abs_slider.valueChanged.connect(on_abs_change)
        rel_slider.valueChanged.connect(on_rel_change)
        normalize_box.stateChanged.connect(on_normalize_toggle)

        update_visibility()
        return widget

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "mode": self.mode,
            "abs_level": self.abs_level,
            "rel_percent": self.rel_percent,
            "normalize_relative": self.normalize_relative,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.mode = state.get("mode", self.MODE_RELATIVE)
        self.abs_level = state.get("abs_level", 1.0)
        self.rel_percent = state.get("rel_percent", 100.0)
        self.normalize_relative = state.get("normalize_relative", False)

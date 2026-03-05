# modules/shuffle.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QCheckBox
from PyQt6.QtCore import Qt
from audio_module import AudioModule


class Shuffle(AudioModule):
    """Randomly shuffles chunks of samples within an audio block."""

    def __init__(self, chunk_size: int = 512, intensity: float = 1.0, enabled: bool = True):
        super().__init__(input_count=1, output_count=1)
        self.chunk_size = chunk_size    # size of each shuffled chunk in samples
        self.intensity = intensity      # 0.0 = no shuffle, 1.0 = full shuffle
        self.enabled = enabled

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)

        if not self.enabled or self.intensity == 0.0:
            return x.astype(np.float32)

        # Split the block into chunks and shuffle them
        chunk = max(1, self.chunk_size)
        n_chunks = frames // chunk
        remainder = frames % chunk

        if n_chunks < 2:
            # Nothing meaningful to shuffle
            return x.astype(np.float32)

        # Only shuffle a portion of chunks based on intensity
        indices = np.arange(n_chunks)
        n_to_shuffle = max(2, int(np.round(n_chunks * self.intensity)))
        shuffle_pool = np.random.choice(n_chunks, size=n_to_shuffle, replace=False)
        shuffled_pool = shuffle_pool.copy()
        np.random.shuffle(shuffled_pool)
        indices[shuffle_pool] = shuffled_pool

        # Reconstruct the output block from reordered chunks
        body = x[:n_chunks * chunk].reshape(n_chunks, chunk, x.shape[1])
        y_body = body[indices].reshape(n_chunks * chunk, x.shape[1])

        if remainder > 0:
            y = np.concatenate([y_body, x[n_chunks * chunk:]], axis=0)
        else:
            y = y_body

        return y.astype(np.float32)

    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Enabled toggle ---
        enabled_cb = QCheckBox("Enabled")
        enabled_cb.setChecked(self.enabled)
        layout.addWidget(enabled_cb)

        # --- Chunk size slider ---
        chunk_label = QLabel(f"Chunk Size: {self.chunk_size} samples")
        layout.addWidget(chunk_label)

        chunk_slider = QSlider(Qt.Orientation.Horizontal)
        chunk_slider.setMinimum(1)
        chunk_slider.setMaximum(200)   # mapped to 16..4096 samples
        chunk_slider.setValue(self._chunk_to_slider(self.chunk_size))
        chunk_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        chunk_slider.setTickInterval(20)
        layout.addWidget(chunk_slider)

        # --- Intensity slider ---
        intensity_label = QLabel(f"Intensity: {self.intensity:.2f}")
        layout.addWidget(intensity_label)

        intensity_slider = QSlider(Qt.Orientation.Horizontal)
        intensity_slider.setMinimum(0)
        intensity_slider.setMaximum(100)
        intensity_slider.setValue(int(self.intensity * 100))
        intensity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        intensity_slider.setTickInterval(25)
        layout.addWidget(intensity_slider)

        # --- Callbacks ---
        def on_enabled(state):
            self.enabled = bool(state)

        def on_chunk_change(val):
            self.chunk_size = self._slider_to_chunk(val)
            chunk_label.setText(f"Chunk Size: {self.chunk_size} samples")

        def on_intensity_change(val):
            self.intensity = val / 100.0
            intensity_label.setText(f"Intensity: {self.intensity:.2f}")

        enabled_cb.stateChanged.connect(on_enabled)
        chunk_slider.valueChanged.connect(on_chunk_change)
        intensity_slider.valueChanged.connect(on_intensity_change)

        return widget

    # --- Helpers for logarithmic chunk size mapping ---
    def _chunk_to_slider(self, chunk: int) -> int:
        """Map chunk size (16–4096) to slider value (1–200)."""
        log_min, log_max = np.log2(16), np.log2(4096)
        t = (np.log2(max(16, chunk)) - log_min) / (log_max - log_min)
        return int(round(t * 199 + 1))

    def _slider_to_chunk(self, val: int) -> int:
        """Map slider value (1–200) to chunk size (16–4096), snapped to power of 2."""
        log_min, log_max = np.log2(16), np.log2(4096)
        t = (val - 1) / 199.0
        raw = 2 ** (log_min + t * (log_max - log_min))
        # Snap to nearest power of 2
        power = round(np.log2(raw))
        return int(2 ** np.clip(power, 4, 12))

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "chunk_size": self.chunk_size,
            "intensity": self.intensity,
            "enabled": self.enabled,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.chunk_size = state.get("chunk_size", 512)
        self.intensity = state.get("intensity", 1.0)
        self.enabled = state.get("enabled", True)
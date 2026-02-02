# modules/reverb.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt
from audio_module import AudioModule


class Reverb(AudioModule):
    """
    Simple Schroeder-style reverb.
    Parameters:
        - mix: wet/dry balance (0.0–1.0)
        - decay: reverb tail decay amount
        - room_size: scales delay lengths (larger room = longer reflections)
    """

    def __init__(self, sample_rate=44100, mix=0.3, decay=0.5, room_size=0.5):
        super().__init__(input_count=1, output_count=1)
        self.sample_rate = sample_rate
        self.mix = mix
        self.decay = decay
        self.room_size = room_size

        # --- Comb filters (delay + feedback) ---
        base_delays = np.array([0.0297, 0.0371, 0.0411, 0.0437])  # seconds
        self.comb_delays = (base_delays * sample_rate).astype(int)
        self.comb_buffers = [np.zeros(d, dtype=np.float32) for d in self.comb_delays]
        self.comb_indices = [0 for _ in self.comb_delays]

        # --- All-pass filters for diffusion ---
        ap_delays = np.array([0.005, 0.0017])  # seconds
        self.ap_delays = (ap_delays * sample_rate).astype(int)
        self.ap_buffers = [np.zeros(d, dtype=np.float32) for d in self.ap_delays]
        self.ap_indices = [0 for _ in self.ap_delays]

    def _comb_filter(self, x, buf, idx, delay, feedback):
        # Ensure buffer is at least as long as 'delay'
        if len(buf) < delay:
            buf = np.concatenate([buf, np.zeros(delay - len(buf), dtype=np.float32)])
        
        out = np.zeros_like(x)
        for i in range(len(x)):
            y = buf[idx]
            out[i] = y
            buf[idx] = x[i] + feedback * y
            idx = (idx + 1) % delay
        return out, buf, idx

    def _allpass_filter(self, x, buf, idx, delay, feedback=0.5):
        out = np.zeros_like(x)
        for i in range(len(x)):
            buf_out = buf[idx]
            y = -feedback * x[i] + buf_out
            buf[idx] = x[i] + feedback * y
            out[i] = y
            idx = (idx + 1) % delay
        return out, buf, idx

    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        # Get input audio and convert to mono
        x = self.input_node.receive(frames)
        x_mono = x.mean(axis=1)

        # --- Comb filters (parallel) ---
        comb_sum = np.zeros_like(x_mono)
        for n in range(len(self.comb_delays)):
            # Compute effective delay for current room size
            effective_delay = int(self.comb_delays[n] * (0.7 + self.room_size * 0.6))
            effective_delay = max(1, effective_delay)

            # Ensure comb buffer is large enough
            if len(self.comb_buffers[n]) < effective_delay:
                extra = np.zeros(effective_delay - len(self.comb_buffers[n]), dtype=np.float32)
                self.comb_buffers[n] = np.concatenate([self.comb_buffers[n], extra])

            # Process comb filter
            out, self.comb_buffers[n], self.comb_indices[n] = self._comb_filter(
                x_mono,
                self.comb_buffers[n],
                self.comb_indices[n],
                effective_delay,
                self.decay * 0.8,
            )
            comb_sum += out

        comb_sum /= len(self.comb_delays)

        # --- All-pass filters (series) ---
        ap_out = comb_sum
        for n in range(len(self.ap_delays)):
            effective_delay = int(self.ap_delays[n] * (0.7 + self.room_size * 0.6))
            effective_delay = max(1, effective_delay)

            # Ensure all-pass buffer is large enough
            if len(self.ap_buffers[n]) < effective_delay:
                extra = np.zeros(effective_delay - len(self.ap_buffers[n]), dtype=np.float32)
                self.ap_buffers[n] = np.concatenate([self.ap_buffers[n], extra])

            # Process all-pass filter
            ap_out, self.ap_buffers[n], self.ap_indices[n] = self._allpass_filter(
                ap_out, self.ap_buffers[n], self.ap_indices[n], effective_delay, 0.5
            )

        # --- Mix wet/dry ---
        wet = np.repeat(ap_out[:, np.newaxis], 2, axis=1)
        y = (1 - self.mix) * x + self.mix * wet
        return y.astype(np.float32)


    def get_ui(self) -> QWidget:
        """Return QWidget with sliders for mix, decay, and room size."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # --- Mix slider ---
        mix_label = QLabel(f"Mix: {self.mix:.2f}")
        layout.addWidget(mix_label)
        mix_slider = QSlider(Qt.Orientation.Horizontal)
        mix_slider.setMinimum(0)
        mix_slider.setMaximum(100)
        mix_slider.setValue(int(self.mix * 100))
        mix_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        mix_slider.setTickInterval(25)
        layout.addWidget(mix_slider)

        def on_mix_change(val):
            self.mix = val / 100.0
            mix_label.setText(f"Mix: {self.mix:.2f}")

        mix_slider.valueChanged.connect(on_mix_change)

        # --- Decay slider ---
        decay_label = QLabel(f"Decay: {self.decay:.2f}")
        layout.addWidget(decay_label)
        decay_slider = QSlider(Qt.Orientation.Horizontal)
        decay_slider.setMinimum(0)
        decay_slider.setMaximum(100)
        decay_slider.setValue(int(self.decay * 100))
        decay_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        decay_slider.setTickInterval(25)
        layout.addWidget(decay_slider)

        def on_decay_change(val):
            self.decay = val / 100.0
            decay_label.setText(f"Decay: {self.decay:.2f}")

        decay_slider.valueChanged.connect(on_decay_change)

        # --- Room size slider ---
        room_label = QLabel(f"Room Size: {self.room_size:.2f}")
        layout.addWidget(room_label)
        room_slider = QSlider(Qt.Orientation.Horizontal)
        room_slider.setMinimum(0)
        room_slider.setMaximum(100)
        room_slider.setValue(int(self.room_size * 100))
        room_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        room_slider.setTickInterval(25)
        layout.addWidget(room_slider)

        def on_room_change(val):
            self.room_size = val / 100.0
            room_label.setText(f"Room Size: {self.room_size:.2f}")

        room_slider.valueChanged.connect(on_room_change)

        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()  # include input/output node info
        data.update({
            "mix": self.mix,
            "decay": self.decay,
            "room_size": self.room_size,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.mix = state.get("mix", 0.3)
        self.decay = state.get("decay", 0.5)
        self.room_size = state.get("room_size", 0.5)

        # Recompute buffer lengths based on room size
        base_comb_delays = np.array([0.0297, 0.0371, 0.0411, 0.0437])
        self.comb_delays = (base_comb_delays * self.sample_rate).astype(int)
        self.comb_buffers = [np.zeros(d, dtype=np.float32) for d in self.comb_delays]
        self.comb_indices = [0 for _ in self.comb_delays]

        base_ap_delays = np.array([0.005, 0.0017])
        self.ap_delays = (base_ap_delays * self.sample_rate).astype(int)
        self.ap_buffers = [np.zeros(d, dtype=np.float32) for d in self.ap_delays]
        self.ap_indices = [0 for _ in self.ap_delays]
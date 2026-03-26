# modules/speed_warble.py
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider
)
from PyQt6.QtCore import Qt
from source.audio_module import AudioModule


class SpeedWarble(AudioModule):
    """Smoothly varies playback speed using three layered modulation sources
    that share a single resampling read-head:

    1. **Wow** — slow, smooth sinusoidal pitch drift (0.3–4 Hz) emulating
       turntable or tape-deck speed irregularity.
    2. **Flutter** — faster, irregular pitch wobble (4–20 Hz) emulating
       capstan or motor vibration.  Uses two detuned sine oscillators
       summed together for a less predictable, more mechanical feel.
    3. **Random warble** — stochastic speed changes at a configurable rate,
       producing anything from subtle drift to extreme glitch.

    All three are mixed into a single instantaneous speed multiplier that
    drives the fractional read-head through a ring buffer with linear
    interpolation.  No FFTs.  The generate path is fully vectorised with
    NumPy — no per-sample Python loop.

    Parameters
    ----------
    wow_depth : float  0.0–1.0
        Wow pitch deviation.  At 1.0 the speed swings ±4 %.
    wow_rate : float  0.3–4.0 Hz
        Wow oscillation frequency.
    flutter_depth : float  0.0–1.0
        Flutter pitch deviation.  At 1.0 the speed swings ±1.5 %.
    flutter_rate : float  4.0–20.0 Hz
        Primary flutter oscillation frequency.  A second oscillator runs at
        an irrational multiple (~1.127×) for added irregularity.
    random_depth : float  0.0–1.0
        How far random warble can push the speed from 1.0.
    random_rate : float  0.01–10.0 Hz
        How often a new random speed target is chosen.
    smoothing : float  0.0–1.0
        One-pole smoothing on the random warble envelope only.
    """

    _RING_SIZE = 65536  # ~1.45 s @ 44 100 Hz

    def __init__(self):
        super().__init__(input_count=1, output_count=1)

        # --- Wow ---
        self.wow_depth = 0.0
        self.wow_rate = 1.2       # Hz

        # --- Flutter ---
        self.flutter_depth = 0.0
        self.flutter_rate = 6.0   # Hz

        # --- Random warble ---
        self.random_depth = 0.0
        self.random_rate = 1.0    # Hz
        self.smoothing = 0.7

        # --- Internal state ---
        self._init_runtime_state()

    def _init_runtime_state(self):
        """Create / reset all non-serialised runtime state."""
        self._ring = np.zeros((self._RING_SIZE, 2), dtype=np.float32)
        self._write_pos = 0
        self._read_pos = 0.0

        # Oscillator phases (kept as sample-accurate floats)
        self._wow_phase = 0.0
        self._flutter_phase_a = 0.0
        self._flutter_phase_b = 0.0

        # Random warble state
        self._current_speed = 1.0
        self._target_speed = 1.0
        self._rand_phase = 0.0
        self._rng = np.random.default_rng()

    # ------------------------------------------------------------------ core
    def generate(self, frames: int) -> np.ndarray:
        if self.input_node is None:
            return np.zeros((frames, 2), dtype=np.float32)

        x = self.input_node.receive(frames)
        self._write_ring(x)

        # Position read head should track if we're bypassed
        trailing_pos = float((self._write_pos - frames) % self._RING_SIZE)

        # Full bypass when all depths are zero
        if (self.wow_depth < 1e-6 and
                self.flutter_depth < 1e-6 and
                self.random_depth < 1e-6):
            self._read_pos = trailing_pos
            self._current_speed = 1.0
            self._target_speed = 1.0
            return x.astype(np.float32)

        sr = 44100.0
        inv_sr = 1.0 / sr
        size = self._RING_SIZE
        n = np.arange(frames, dtype=np.float64)

        # ---- Wow: vectorised sine ----
        if self.wow_depth > 1e-6:
            wow_dev = self.wow_depth * 0.04
            wow_phases = self._wow_phase + n * (self.wow_rate * inv_sr)
            self._wow_phase = (self._wow_phase + frames * self.wow_rate * inv_sr) % 1.0
            wow_mod = np.sin(2.0 * np.pi * wow_phases) * wow_dev
        else:
            wow_mod = 0.0

        # ---- Flutter: two vectorised sines ----
        if self.flutter_depth > 1e-6:
            flut_dev = self.flutter_depth * 0.015
            inc_a = self.flutter_rate * inv_sr
            inc_b = self.flutter_rate * 1.1267 * inv_sr

            phases_a = self._flutter_phase_a + n * inc_a
            phases_b = self._flutter_phase_b + n * inc_b
            self._flutter_phase_a = (self._flutter_phase_a + frames * inc_a) % 1.0
            self._flutter_phase_b = (self._flutter_phase_b + frames * inc_b) % 1.0

            flut_mod = (np.sin(2.0 * np.pi * phases_a) * 0.6 +
                        np.sin(2.0 * np.pi * phases_b) * 0.4) * flut_dev
        else:
            flut_mod = 0.0

        # ---- Random warble: segmented scalar + vectorised apply ----
        if self.random_depth > 1e-6:
            rand_mod = self._generate_random_warble(frames, inv_sr)
        else:
            rand_mod = 0.0
            self._current_speed = 1.0
            self._target_speed = 1.0

        # ---- Combined per-sample speed and cumulative read positions ----
        speed_array = 1.0 + wow_mod + flut_mod + rand_mod
        read_positions = self._read_pos + np.cumsum(speed_array)

        # ---- Vectorised linear interpolation from ring buffer ----
        rp = read_positions % size
        idx = rp.astype(np.intp)
        frac = (rp - idx).astype(np.float32)
        idx_next = (idx + 1) % size

        # Fancy-index both channels at once: (frames, 2)
        out = (self._ring[idx] * (1.0 - frac[:, np.newaxis]) +
               self._ring[idx_next] * frac[:, np.newaxis])

        self._read_pos = read_positions[-1] % size

        return out.astype(np.float32)

    def _generate_random_warble(self, frames: int, inv_sr: float) -> np.ndarray:
        """Build the random-warble deviation array using segmented processing.

        Instead of a per-sample Python loop, we:
        1. Figure out at which sample indices new targets are chosen.
        2. Build a piece-wise constant target array.
        3. Apply the one-pole smoother vectorised via an IIR scan.
        """
        alpha = 1.0 - self.smoothing * 0.9999
        rand_min = max(1.0 - self.random_depth * 0.75, 0.25)
        rand_max = 1.0 + self.random_depth * 3.0
        rand_inc = self.random_rate * inv_sr

        # Build per-sample target array by finding switch points
        targets = np.empty(frames, dtype=np.float64)
        phase = self._rand_phase
        target = self._target_speed
        pos = 0

        while pos < frames:
            # How many samples until phase rolls over?
            if rand_inc > 1e-12:
                samples_to_flip = int((1.0 - phase) / rand_inc) + 1
            else:
                samples_to_flip = frames  # never flips

            end = min(pos + samples_to_flip, frames)
            targets[pos:end] = target

            phase += (end - pos) * rand_inc
            if phase >= 1.0:
                phase -= 1.0
                target = self._rng.uniform(rand_min, rand_max)

            pos = end

        self._rand_phase = phase
        self._target_speed = target

        # Apply one-pole smoother: y[n] = y[n-1] + alpha * (target[n] - y[n-1])
        # This is a first-order IIR — we vectorise with a scan.
        smoothed = np.empty(frames, dtype=np.float64)
        speed = self._current_speed
        # Process in chunks to keep Python loop overhead minimal.
        # Each chunk applies the IIR formula vectorised.
        # For a one-pole filter y[n] = (1-alpha)*y[n-1] + alpha*x[n],
        # the exact solution across a constant-target segment is geometric.
        decay = 1.0 - alpha  # pole coefficient

        seg_start = 0
        # Find boundaries where target value changes
        change_mask = np.concatenate(([True], targets[1:] != targets[:-1]))
        change_indices = np.flatnonzero(change_mask)
        # Add end sentinel
        boundaries = np.concatenate((change_indices, [frames]))

        for i in range(len(boundaries) - 1):
            seg_s = boundaries[i]
            seg_e = boundaries[i + 1]
            seg_len = seg_e - seg_s
            tgt = targets[seg_s]

            # For a constant-target segment, the one-pole filter has a closed
            # form: y[n] = tgt + (y_start - tgt) * decay^n
            ns = np.arange(seg_len, dtype=np.float64)
            decay_curve = np.power(decay, ns + 1)
            smoothed[seg_s:seg_e] = tgt + (speed - tgt) * decay_curve
            # Update speed to the end-of-segment value
            speed = smoothed[seg_e - 1]

        self._current_speed = speed

        # Return deviation from unity
        return smoothed - 1.0

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

        # ============ Wow section ============
        wow_header = QLabel("— Wow —")
        wow_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(wow_header)

        wd_row = QHBoxLayout()
        wd_lbl = QLabel("Depth")
        self._wd_val = QLabel(f"{self.wow_depth:.2f}")
        wd_slider = QSlider(Qt.Orientation.Horizontal)
        wd_slider.setMinimum(0)
        wd_slider.setMaximum(100)
        wd_slider.setValue(int(self.wow_depth * 100))
        wd_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        wd_slider.setTickInterval(25)
        wd_row.addWidget(wd_lbl)
        wd_row.addWidget(wd_slider)
        wd_row.addWidget(self._wd_val)
        layout.addLayout(wd_row)

        def on_wd(v):
            self.wow_depth = v / 100.0
            self._wd_val.setText(f"{self.wow_depth:.2f}")
        wd_slider.valueChanged.connect(on_wd)

        wr_row = QHBoxLayout()
        wr_lbl = QLabel("Rate")
        self._wr_val = QLabel(f"{self.wow_rate:.1f} Hz")
        wr_slider = QSlider(Qt.Orientation.Horizontal)
        wr_slider.setMinimum(3)
        wr_slider.setMaximum(40)
        wr_slider.setValue(int(self.wow_rate * 10))
        wr_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        wr_slider.setTickInterval(10)
        wr_row.addWidget(wr_lbl)
        wr_row.addWidget(wr_slider)
        wr_row.addWidget(self._wr_val)
        layout.addLayout(wr_row)

        def on_wr(v):
            self.wow_rate = v / 10.0
            self._wr_val.setText(f"{self.wow_rate:.1f} Hz")
        wr_slider.valueChanged.connect(on_wr)

        # ============ Flutter section ============
        flut_header = QLabel("— Flutter —")
        flut_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(flut_header)

        fd_row = QHBoxLayout()
        fd_lbl = QLabel("Depth")
        self._fd_val = QLabel(f"{self.flutter_depth:.2f}")
        fd_slider = QSlider(Qt.Orientation.Horizontal)
        fd_slider.setMinimum(0)
        fd_slider.setMaximum(100)
        fd_slider.setValue(int(self.flutter_depth * 100))
        fd_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        fd_slider.setTickInterval(25)
        fd_row.addWidget(fd_lbl)
        fd_row.addWidget(fd_slider)
        fd_row.addWidget(self._fd_val)
        layout.addLayout(fd_row)

        def on_fd(v):
            self.flutter_depth = v / 100.0
            self._fd_val.setText(f"{self.flutter_depth:.2f}")
        fd_slider.valueChanged.connect(on_fd)

        fr_row = QHBoxLayout()
        fr_lbl = QLabel("Rate")
        self._fr_val = QLabel(f"{self.flutter_rate:.1f} Hz")
        fr_slider = QSlider(Qt.Orientation.Horizontal)
        fr_slider.setMinimum(40)
        fr_slider.setMaximum(200)
        fr_slider.setValue(int(self.flutter_rate * 10))
        fr_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        fr_slider.setTickInterval(40)
        fr_row.addWidget(fr_lbl)
        fr_row.addWidget(fr_slider)
        fr_row.addWidget(self._fr_val)
        layout.addLayout(fr_row)

        def on_fr(v):
            self.flutter_rate = v / 10.0
            self._fr_val.setText(f"{self.flutter_rate:.1f} Hz")
        fr_slider.valueChanged.connect(on_fr)

        # ============ Random Warble section ============
        rand_header = QLabel("— Random Warble —")
        rand_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(rand_header)

        rd_row = QHBoxLayout()
        rd_lbl = QLabel("Depth")
        self._rd_val = QLabel(f"{self.random_depth:.2f}")
        rd_slider = QSlider(Qt.Orientation.Horizontal)
        rd_slider.setMinimum(0)
        rd_slider.setMaximum(100)
        rd_slider.setValue(int(self.random_depth * 100))
        rd_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        rd_slider.setTickInterval(25)
        rd_row.addWidget(rd_lbl)
        rd_row.addWidget(rd_slider)
        rd_row.addWidget(self._rd_val)
        layout.addLayout(rd_row)

        def on_rd(v):
            self.random_depth = v / 100.0
            self._rd_val.setText(f"{self.random_depth:.2f}")
        rd_slider.valueChanged.connect(on_rd)

        rr_row = QHBoxLayout()
        rr_lbl = QLabel("Rate")
        self._rr_val = QLabel(f"{self.random_rate:.2f} Hz")
        rr_slider = QSlider(Qt.Orientation.Horizontal)
        rr_slider.setMinimum(1)
        rr_slider.setMaximum(1000)
        rr_slider.setValue(int(self.random_rate * 100))
        rr_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        rr_slider.setTickInterval(250)
        rr_row.addWidget(rr_lbl)
        rr_row.addWidget(rr_slider)
        rr_row.addWidget(self._rr_val)
        layout.addLayout(rr_row)

        def on_rr(v):
            self.random_rate = v / 100.0
            self._rr_val.setText(f"{self.random_rate:.2f} Hz")
        rr_slider.valueChanged.connect(on_rr)

        sm_row = QHBoxLayout()
        sm_lbl = QLabel("Smooth")
        self._sm_val = QLabel(f"{self.smoothing:.2f}")
        sm_slider = QSlider(Qt.Orientation.Horizontal)
        sm_slider.setMinimum(0)
        sm_slider.setMaximum(100)
        sm_slider.setValue(int(self.smoothing * 100))
        sm_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        sm_slider.setTickInterval(25)
        sm_row.addWidget(sm_lbl)
        sm_row.addWidget(sm_slider)
        sm_row.addWidget(self._sm_val)
        layout.addLayout(sm_row)

        def on_sm(v):
            self.smoothing = v / 100.0
            self._sm_val.setText(f"{self.smoothing:.2f}")
        sm_slider.valueChanged.connect(on_sm)

        return widget

    # --------------------------------------------------------- serialization
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "wow_depth": self.wow_depth,
            "wow_rate": self.wow_rate,
            "flutter_depth": self.flutter_depth,
            "flutter_rate": self.flutter_rate,
            "random_depth": self.random_depth,
            "random_rate": self.random_rate,
            "smoothing": self.smoothing,
        })
        return data

    def deserialize(self, state: dict):
        super().deserialize(state)
        self.wow_depth = state.get("wow_depth", 0.0)
        self.wow_rate = state.get("wow_rate", 1.2)
        self.flutter_depth = state.get("flutter_depth", 0.0)
        self.flutter_rate = state.get("flutter_rate", 6.0)
        self.random_depth = state.get("random_depth", 0.0)
        self.random_rate = state.get("random_rate", 1.0)
        self.smoothing = state.get("smoothing", 0.7)
        self._init_runtime_state()
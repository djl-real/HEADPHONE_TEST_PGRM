import numpy as np
from scipy.signal import butter, lfilter

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QComboBox, QHBoxLayout
)
from PyQt6.QtCore import Qt

from audio_module import AudioModule


def butter_bandpass(low, high, fs, order=4):
    nyq = 0.5 * fs
    low /= nyq
    high /= nyq
    return butter(order, [low, high], btype="band")


def make_band_filter(low, high, fs, order=4):
    b, a = butter_bandpass(low, high, fs, order)
    return (b, a)


def envelope_follower(x, prev_env, attack=0.005, release=0.05):
    """
    Smoothed envelope follower.
    attack/release in seconds.
    """
    alpha_a = np.exp(-1.0 / (44100 * attack))
    alpha_r = np.exp(-1.0 / (44100 * release))

    env = np.zeros_like(x)
    e = prev_env

    for i, s in enumerate(x):
        rect = abs(s)
        if rect > e:   # attack
            e = alpha_a * e + (1 - alpha_a) * rect
        else:          # release
            e = alpha_r * e + (1 - alpha_r) * rect
        env[i] = e

    return env, e


class Vocoder(AudioModule):
    """
    8-band real-time vocoder module.
    Input 0: modulator (speech)
    Output: vocoded signal
    """

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=1, output_count=1)
        self.sample_rate = sample_rate

        # ---------------------------------------------------
        # Vocoder configuration
        # ---------------------------------------------------
        self.band_count = 8
        self.bands = [
            (200, 300),
            (300, 450),
            (450, 700),
            (700, 1100),
            (1100, 1800),
            (1800, 2800),
            (2800, 4200),
            (4200, 6000),
        ]

        # Bandpass filters
        self.filters = [
            make_band_filter(lo, hi, sample_rate)
            for lo, hi in self.bands
        ]

        # Envelope memory
        self.prev_env = np.zeros(self.band_count, dtype=np.float32)

        # Carrier type
        self.carrier_type = "Saw"
        self.phase = 0.0
        self.carrier_freq = 110.0  # Base pitch

        # UI-controllable parameters
        self.formant_boost = 1.0
        self.noise_mix = 0.0

    # ----------------------------------------------------------------------
    # Carrier synthesis
    # ----------------------------------------------------------------------
    def _generate_carrier(self, frames):
        t = (self.phase + np.arange(frames)) / self.sample_rate
        freq = self.carrier_freq

        if self.carrier_type == "Saw":
            carrier = 2.0 * (t * freq % 1.0) - 1.0

        elif self.carrier_type == "Square":
            carrier = np.sign(np.sin(2 * np.pi * freq * t))

        elif self.carrier_type == "Sine":
            carrier = np.sin(2 * np.pi * freq * t)

        elif self.carrier_type == "Noise":
            carrier = np.random.randn(frames)

        else:
            carrier = np.zeros(frames)

        self.phase += frames
        return carrier.astype(np.float32)

    # ----------------------------------------------------------------------
    # Main audio processing
    # ----------------------------------------------------------------------
    def generate(self, frames: int):
        out = np.zeros((frames, 2), dtype=np.float32)
        in0 = self.input_node.receive(frames)

        if in0 is None:
            return out

        # Use mono modulator
        mod = in0[:, 0]

        # Carrier
        carrier = self._generate_carrier(frames)

        # Apply all bands
        final = np.zeros(frames, dtype=np.float32)

        for i, ((lo, hi), (b, a)) in enumerate(zip(self.bands, self.filters)):
            # Filter modulator → band signal
            band_mod = lfilter(b, a, mod)

            # Envelope follower
            env, self.prev_env[i] = envelope_follower(
                band_mod,
                self.prev_env[i],
                attack=0.005,
                release=0.05
            )

            env *= self.formant_boost

            # Filter carrier into same band
            band_car = lfilter(b, a, carrier)

            # Apply envelope
            final += band_car * env

        # Add optional noise (helps consonants)
        if self.noise_mix > 0:
            noise = np.random.randn(frames).astype(np.float32) * self.noise_mix
            final += noise * mod

        # Stereo
        out[:, 0] = final
        out[:, 1] = final
        return out

    # ----------------------------------------------------------------------
    # UI
    # ----------------------------------------------------------------------
    def get_ui(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ---------------- Carrier Type ----------------
        layout.addWidget(QLabel("Carrier Waveform:"))
        dropdown = QComboBox()
        dropdown.addItems(["Saw", "Square", "Sine", "Noise"])

        def change_carrier(i):
            self.carrier_type = dropdown.itemText(i)

        dropdown.currentIndexChanged.connect(change_carrier)
        layout.addWidget(dropdown)

        # ---------------- Carrier Pitch ----------------
        layout.addWidget(QLabel("Carrier Pitch"))
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setRange(20, 2000)
        pitch_slider.setValue(int(self.carrier_freq))

        pitch_slider.valueChanged.connect(
            lambda v: setattr(self, "carrier_freq", float(v))
        )
        layout.addWidget(pitch_slider)

        # ---------------- Formant Boost ----------------
        layout.addWidget(QLabel("Formant Boost"))
        boost_slider = QSlider(Qt.Orientation.Horizontal)
        boost_slider.setRange(0, 200)
        boost_slider.setValue(int(self.formant_boost * 100))

        boost_slider.valueChanged.connect(
            lambda v: setattr(self, "formant_boost", v / 100.0)
        )
        layout.addWidget(boost_slider)

        # ---------------- Noise Mix ----------------
        layout.addWidget(QLabel("Noise Mix"))
        noise_slider = QSlider(Qt.Orientation.Horizontal)
        noise_slider.setRange(0, 100)
        noise_slider.setValue(int(self.noise_mix * 100))

        noise_slider.valueChanged.connect(
            lambda v: setattr(self, "noise_mix", v / 100.0)
        )
        layout.addWidget(noise_slider)

        return widget

    # ----------------------------------------------------------------------
    # Serialization
    # ----------------------------------------------------------------------
    def serialize(self):
        data = super().serialize()
        data.update({
            "carrier_type": self.carrier_type,
            "carrier_freq": self.carrier_freq,
            "formant_boost": self.formant_boost,
            "noise_mix": self.noise_mix,
        })
        return data

    def deserialize(self, state):
        super().deserialize(state)
        self.carrier_type = state.get("carrier_type", "Saw")
        self.carrier_freq = state.get("carrier_freq", 110.0)
        self.formant_boost = state.get("formant_boost", 1.0)
        self.noise_mix = state.get("noise_mix", 0.0)

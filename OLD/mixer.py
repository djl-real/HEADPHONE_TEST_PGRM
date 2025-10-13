# mixer.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QDial
from PyQt6.QtCore import Qt
import numpy as np
import sounddevice as sd

DB_MIN = -60.0
DB_MAX = 10.0


def slider_to_db(slider_value: int) -> float:
    return DB_MIN + (slider_value / 100.0) * (DB_MAX - DB_MIN)


def db_to_slider(db_value: float) -> int:
    return int((db_value - DB_MIN) / (DB_MAX - DB_MIN) * 100)


def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)


class MixerFader(QWidget):
    """Fader that owns its module and applies volume/pan/mute."""

    def __init__(self, module):
        super().__init__()
        self.module = module  # <-- Each fader contains its module

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(QLabel(module.name, alignment=Qt.AlignmentFlag.AlignCenter))

        # Volume slider
        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)

        # Start muted at bottom of slider
        slider_value = 0
        self.slider.setValue(slider_value)
        db_val = slider_to_db(slider_value)
        self.module.volume = db_to_linear(db_val)

        self.slider.valueChanged.connect(self.update_volume)
        self.slider.setFixedHeight(200)
        self.slider.setTickPosition(QSlider.TickPosition.TicksLeft)
        self.slider.setTickInterval(10)

        # dB labels
        label_layout = QVBoxLayout()
        for db in range(10, -61, -10):
            text = f"{db} dB" if db > -60 else "-∞ dB"
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_layout.addWidget(lbl)

        slider_layout.addLayout(label_layout)
        slider_layout.addWidget(self.slider)
        layout.addLayout(slider_layout)

        # Mute button
        self.mute_button = QPushButton("MUTE")
        self.mute_button.setCheckable(True)
        self.mute_button.toggled.connect(self.update_mute)
        layout.addWidget(self.mute_button)

        # Pan dial
        layout.addWidget(QLabel("PAN", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pan_dial = QDial()
        self.pan_dial.setMinimum(-50)
        self.pan_dial.setMaximum(50)
        self.pan_dial.setValue(int(getattr(module, "pan", 0.0) * 50))
        self.pan_dial.valueChanged.connect(self.update_pan)
        layout.addWidget(self.pan_dial)

        self.setLayout(layout)

    def update_volume(self, slider_value: int):
        db_val = slider_to_db(slider_value)
        self.module.volume = db_to_linear(db_val)

    def update_mute(self, muted: bool):
        self.module.muted = muted

    def update_pan(self, value: int):
        self.module.pan = value / 50.0


class MixerPanel(QWidget):
    """Central mixer panel summing audio from faders."""

    def __init__(self):
        super().__init__()
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)

        self.faders: list[MixerFader] = []
        self.fs = 44100

        # OutputStream
        self.stream = sd.OutputStream(
            channels=2,
            samplerate=self.fs,
            callback=self.audio_callback,
            blocksize=1024
        )
        self.stream.start()

    def add_fader(self, module):
        fader = MixerFader(module)
        self.layout.addWidget(fader)
        self.faders.append(fader)

    def remove_fader(self, module):
        fader_to_remove = None
        for fader in self.faders:
            if fader.module == module:
                fader_to_remove = fader
                break
        if fader_to_remove:
            self.faders.remove(fader_to_remove)
            self.layout.removeWidget(fader_to_remove)
            fader_to_remove.deleteLater()

    def audio_callback(self, outdata, frames, time, status):
        buffer = np.zeros((frames, 2), dtype=np.float32)

        for fader in self.faders:
            if getattr(fader.module, "muted", False):
                continue

            try:
                samples = fader.module.get_samples(frames)

                # Apply fader volume and pan
                left_gain = np.sqrt(0.5 * (1 - fader.module.pan)) * fader.module.volume
                right_gain = np.sqrt(0.5 * (1 + fader.module.pan)) * fader.module.volume
                samples[:, 0] *= left_gain
                samples[:, 1] *= right_gain

                buffer += samples
            except Exception as e:
                print(f"[Mixer] Error in module {fader.module.name}: {e}")

        np.clip(buffer, -1.0, 1.0, out=buffer)
        outdata[:] = buffer

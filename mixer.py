# mixer.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QDial
from PyQt6.QtCore import Qt
import numpy as np
import sounddevice as sd

class MixerFader(QWidget):
    """Single fader controlling module volume, mute, and pan."""

    def __init__(self, module):
        super().__init__()
        self.module = module
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(QLabel(module.name))

        # Volume slider
        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(int(module.volume * 100))
        self.slider.valueChanged.connect(self.update_volume)
        layout.addWidget(self.slider)

        # Mute button
        self.mute_button = QPushButton("MUTE")
        self.mute_button.setCheckable(True)
        self.mute_button.toggled.connect(self.update_mute)
        layout.addWidget(self.mute_button)

        # Pan dial
        self.pan_dial = QDial()
        self.pan_dial.setMinimum(-50)
        self.pan_dial.setMaximum(50)
        self.pan_dial.setValue(int(module.pan * 50))
        self.pan_dial.valueChanged.connect(self.update_pan)
        layout.addWidget(QLabel("PAN"))
        layout.addWidget(self.pan_dial)

        self.setLayout(layout)

    def update_volume(self, value):
        self.module.volume = value / 100.0

    def update_mute(self, muted):
        self.module.muted = muted

    def update_pan(self, value):
        self.module.pan = value / 50.0  # -1 → 1

class MixerPanel(QWidget):
    """Central mixer panel with one OutputStream."""

    def __init__(self):
        super().__init__()
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)
        self.modules = []
        self.faders = {}
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
        self.faders[module] = fader
        self.modules.append(module)

    def remove_fader(self, module):
        if module in self.faders:
            widget = self.faders.pop(module)
            self.layout.removeWidget(widget)
            widget.deleteLater()
            self.modules.remove(module)

    def audio_callback(self, outdata, frames, time, status):
        buffer = np.zeros((frames, 2), dtype=np.float32)
        for mod in self.modules:
            buffer += mod.get_samples(frames)
        np.clip(buffer, -1.0, 1.0, out=buffer)
        outdata[:] = buffer

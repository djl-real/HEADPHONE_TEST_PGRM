from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt


class ModuleWindow(QWidget):
    def __init__(self, title, mixer_callback, close_callback):
        super().__init__()

        self.mixer_callback = mixer_callback
        self.close_callback = close_callback
        self.name = title

        # Every module should have volume/balance for mixer
        self.volume = -60.0   # dB
        self.pan = 0.0  # -1 left, +1 right

        # Main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Content area for child modules to populate
        self.content_layout = QVBoxLayout()
        main_layout.addLayout(self.content_layout)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close_module)
        main_layout.addWidget(close_btn)

        # Register with mixer (adds a fader)
        self.mixer_callback(self)

    def close_module(self):
        """Called when user closes a module window"""
        self.close_callback(self)
        self.close()

    def get_samples(self, frames: int):
        """Default implementation: silence (to be overridden by modules)"""
        import numpy as np
        return np.zeros((frames, 2), dtype=np.float32)

# module_base.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt
import numpy as np


class ModuleWindow(QWidget):
    """
    Base class for all audio modules.
    Automatically integrates with the central mixer.
    """

    def __init__(self, title: str, mixer_callback, close_callback):
        super().__init__()

        self.name = title
        self.mixer_callback = mixer_callback
        self.close_callback = close_callback

        # Default mixer parameters
        self.volume = -60.0  # dB
        self.pan = 0.0       # -1 left → +1 right
        self.muted = False

        # Main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Title label
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Content layout for child modules to populate
        self.content_layout = QVBoxLayout()
        main_layout.addLayout(self.content_layout)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close_module)
        main_layout.addWidget(close_btn)

        # Register with mixer (adds a fader)
        if self.mixer_callback:
            self.mixer_callback(self)

    def close_module(self):
        """Called when user clicks the Close button."""
        self._cleanup_and_close()

    def closeEvent(self, event):
        """
        Catch the window being closed via the title bar.
        Ensures mixer cleanup is called.
        """
        self._cleanup_and_close()
        super().closeEvent(event)

    def _cleanup_and_close(self):
        """Remove from mixer and close the window."""
        # Stop any audio by setting volume to minimum (optional safety)
        self.volume = -60.0
        self.muted = True

        # Remove fader from mixer
        if self.close_callback:
            self.close_callback(self)

        # Close the widget if not already closing
        if not self.isHidden():
            self.close()

    def get_samples(self, frames: int):
        """
        Default implementation: silence.
        Modules should override this to generate audio.
        """
        return np.zeros((frames, 2), dtype=np.float32)

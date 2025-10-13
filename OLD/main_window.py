# main_window.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QPushButton, QApplication, QLabel, QGroupBox
)
import inspect

from mixer import MixerPanel
from modules.static import StaticWindow
from modules.soundboard import SoundboardWindow
from modules.wave import WaveGenerator
from modules.music import Music
from modules.microphone import Microphone


class AudioGraph:
    """Tracks all active modules and their signal connections."""
    def __init__(self):
        self.modules = []

    def add_module(self, module):
        self.modules.append(module)

    def remove_module(self, module):
        if module in self.modules:
            self.modules.remove(module)

    def get_output_mix(self, frames: int):
        """Temporary: mix all generators for output."""
        import numpy as np
        mix = np.zeros((frames, 2), dtype=np.float32)
        for module in self.modules:
            if hasattr(module, "get_samples"):
                mix += module.get_samples(frames)
        return mix


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HEADPHONE_TEST_PGRM")

        self.graph = AudioGraph()

        # --- Layout ---
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- Generator Section ---
        gen_group = QGroupBox("Generators")
        gen_layout = QGridLayout()

        self.generators = [
            ("Static", StaticWindow),
            ("Soundboard", SoundboardWindow),
            ("Wave", WaveGenerator),
            ("Music", Music),
            ("Mic", Microphone),
        ]

        row, col = 0, 0
        for label, cls in self.generators:
            btn = QPushButton(label)
            btn.setFixedSize(120, 90)
            btn.clicked.connect(lambda _, c=cls: self.open_module(c))
            gen_layout.addWidget(btn, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1
        gen_group.setLayout(gen_layout)
        main_layout.addWidget(gen_group)

        # --- Filter Section (for future use) ---
        filter_group = QGroupBox("Filters (coming soon)")
        filter_layout = QGridLayout()
        filter_layout.addWidget(QLabel("No filters yet."), 0, 0)
        filter_group.setLayout(filter_layout)
        main_layout.addWidget(filter_group)

        # --- Output Section ---
        self.mixer = MixerPanel()
        main_layout.addWidget(self.mixer)

        # Track opened modules
        self.open_modules = []

    def open_module(self, module_cls):
        """Safely create a module, handling both old and new patch-compatible constructors."""
        try:
            sig = inspect.signature(module_cls)
            params = list(sig.parameters.keys())

            if len(params) >= 3:
                # New patch-compatible format
                module = module_cls(self.mixer.add_fader, self.mixer.remove_fader, self.graph.modules)
            elif len(params) == 2:
                # Older two-argument version
                module = module_cls(self.mixer.add_fader, self.mixer.remove_fader)
            else:
                # Legacy/no-arg fallback
                module = module_cls()
        except Exception as e:
            print(f"[MainWindow] Failed to instantiate {module_cls.__name__}: {e}")
            return

        module.show()
        self.open_modules.append(module)
        self.graph.add_module(module)

    def closeEvent(self, event):
        for module in self.open_modules:
            module.close()
        event.accept()


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

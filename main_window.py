from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QPushButton, QApplication
)

from mixer import MixerPanel
from modules.static import StaticGenerator
from modules.soundboard import Soundboard
from modules.wave import WaveGenerator


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HEADPHONE_TEST_PGRM")

        # Main vertical layout
        main_layout = QVBoxLayout()

        # --- Module buttons grid ---
        self.modules = [
            ("Static", StaticGenerator),
            ("Soundboard", Soundboard),
            ("Wave", WaveGenerator),
        ]

        grid = QGridLayout()
        row, col = 0, 0
        for label, module_cls in self.modules:
            btn = QPushButton(label)
            btn.setFixedSize(120, 90)  # 4:3 aspect
            btn.clicked.connect(lambda _, cls=module_cls: self.open_module(cls))
            grid.addWidget(btn, row, col)

            col += 1
            if col >= 4:
                col = 0
                row += 1

        main_layout.addLayout(grid)

        # --- Mixer ---
        self.mixer = MixerPanel()
        main_layout.addWidget(self.mixer)

        self.setLayout(main_layout)

        # Track opened modules
        self.open_modules = []

    def open_module(self, module_cls):
        module = module_cls(self.mixer.add_fader, self.mixer.remove_fader)
        module.show()
        self.open_modules.append(module)

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

# main_window.py
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QGridLayout, QPushButton
from mixer import MixerPanel
from modules.static import StaticGenerator

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HEADPHONE_TEST_PGRM")

        # Keep track of open modules
        self.open_modules = []

        # Central widget and layout
        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout()
        central.setLayout(self.main_layout)

        # --- Module buttons grid (4x3) ---
        self.module_grid = QGridLayout()
        self.main_layout.addLayout(self.module_grid)

        # List of module classes to add
        self.modules_list = [StaticGenerator]  # add more modules later

        # Populate buttons
        for i, module_cls in enumerate(self.modules_list):
            btn = QPushButton(module_cls.__name__)
            btn.setFixedSize(120, 90)  # 4:3 ratio
            btn.clicked.connect(lambda _, cls=module_cls: self.open_module(cls))
            self.module_grid.addWidget(btn, i // 4, i % 4)

        # --- Mixer panel ---
        self.mixer = MixerPanel()
        self.main_layout.addWidget(self.mixer)

    def open_module(self, module_cls):
        """Open a new instance of a module and register it with the mixer."""
        module = module_cls(self.mixer.add_fader, self.mixer.remove_fader)
        self.open_modules.append(module)
        module.show()
        # Remove from list when module closes
        module.destroyed.connect(lambda _, m=module: self.open_modules.remove(m))

    def closeEvent(self, event):
        """Close all module windows when main window closes."""
        for module in self.open_modules[:]:  # copy to avoid modification
            module.close()
        super().closeEvent(event)

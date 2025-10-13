# toolbar_manager.py
from PyQt6.QtWidgets import QToolBar, QMenu, QToolButton
from PyQt6.QtGui import QAction
from modules.bandpass import Bandpass
from modules.endpoint import EndpointModule
from modules.LFO import LFO
from modules.vco import VCO
from modules.static import Noise
from modules.pan import Pan
from modules.music import Music
from modules.soundboard import Soundboard
from audio_module import AudioModule
from ui_elements import ModuleItem


class ToolbarManager:
    """
    Handles the creation of the toolbar with folder grouping and module-spawning logic.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self.toolbar = QToolBar("Modules")
        self.main_window.addToolBar(self.toolbar)

        # Organize modules by folder
        self.module_folders = {
            "Source": [("Music", Music), ("VCO", VCO), ("Static", Noise), ("Soundboard", Soundboard), ("LFO", LFO)],
            "Effects": [("Bandpass", Bandpass), ("Pan", Pan)],
            "Master": [("Endpoint", EndpointModule)],
        }

        self.create_folder_buttons()

    def create_folder_buttons(self):
        """Creates a toolbar button for each folder with a dropdown menu of modules."""
        for folder_name, modules in self.module_folders.items():
            menu = QMenu()
            for name, cls in modules:
                action = QAction(name, self.main_window)
                action.triggered.connect(lambda checked, n=name: self.spawn_module(n))
                menu.addAction(action)

            # Create a toolbar button with the menu
            button = QToolButton()
            button.setText(folder_name)
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.toolbar.addWidget(button)

    def spawn_module(self, name: str):
        """Creates the backend module and adds its graphical ModuleItem to the scene."""
        # Find class by name
        cls = None
        for folder_modules in self.module_folders.values():
            for n, c in folder_modules:
                if n == name:
                    cls = c
                    break
            if cls:
                break

        if cls is None:
            print(f"Unknown module: {name}")
            return

        module = cls()

        # Register module
        if isinstance(module, EndpointModule):
            self.main_window.endpoints.append(module)
        else:
            self.main_window.modules.append(module)

        # Create visual representation
        item = ModuleItem(module)
        item.setPos(100, 100)
        self.main_window.scene.addItem(item)

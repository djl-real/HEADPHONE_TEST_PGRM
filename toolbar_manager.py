# toolbar_manager.py
from PyQt6.QtWidgets import QToolBar
from PyQt6.QtGui import QAction
from modules.bandpass import Bandpass
from modules.endpoint import EndpointModule
from modules.LFO import LFO
from audio_module import AudioModule
from ui_elements import ModuleItem


class ToolbarManager:
    """
    Handles the creation of the toolbar and management of available module types.
    MainWindow delegates all toolbar and module-spawning logic here.
    """

    def __init__(self, main_window):
        """
        :param main_window: Reference to the main window (for scene access, module tracking, etc.)
        """
        self.main_window = main_window
        self.toolbar = QToolBar("Modules")
        self.main_window.addToolBar(self.toolbar)

        # Map module names to constructors
        self.module_classes = {
            "LFO": LFO,
            "Bandpass": Bandpass,
            "Endpoint": EndpointModule,
        }

        # Register buttons for each available module
        for name in self.module_classes.keys():
            self.add_module_action(name)

    def add_module_action(self, name: str):
        """Adds a button to the toolbar that spawns the corresponding module."""
        action = QAction(name, self.main_window)
        self.toolbar.addAction(action)
        action.triggered.connect(lambda: self.spawn_module(name))

    def spawn_module(self, name: str):
        """Creates both the backend audio module and its visual representation."""
        if name not in self.module_classes:
            print(f"Unknown module: {name}")
            return

        module_class = self.module_classes[name]
        module = module_class()

        # Register the module with the main window
        if isinstance(module, EndpointModule):
            self.main_window.endpoints.append(module)
        else:
            self.main_window.modules.append(module)

        # Create the graphical representation
        item = ModuleItem(module)
        item.setPos(100, 100)
        self.main_window.scene.addItem(item)

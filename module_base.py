# module_base.py
from PyQt6.QtWidgets import QMainWindow

class ModuleWindow(QMainWindow):
    """
    Base class for all modules.

    name: Module display name
    mixer_callback: function to register module with mixer
    close_callback: function to deregister module from mixer
    """

    def __init__(self, name, mixer_callback, close_callback):
        super().__init__()
        self.name = name
        self.mixer_callback = mixer_callback
        self.close_callback = close_callback

        # Register with mixer
        if self.mixer_callback:
            self.mixer_callback(self)

    def closeEvent(self, event):
        """Remove module from mixer when window closes."""
        if self.close_callback:
            self.close_callback(self)
        super().closeEvent(event)

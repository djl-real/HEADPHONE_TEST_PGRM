# audio_module.py
import numpy as np
from nodes import InputNode, OutputNode
from PyQt6.QtWidgets import QWidget


class AudioModule:
    """Base class for all modules, including graphical node support."""
    def __init__(self, has_input=True, has_output=True):
        self.input_node = InputNode(self) if has_input else None
        self.output_node = OutputNode(self) if has_output else None

    def destroy(self):
        """Disconnect and clean up nodes."""
        if self.input_node:
            self.input_node.disconnect()
        if self.output_node:
            self.output_node.disconnect()

    def generate(self, frames: int) -> np.ndarray:
        """Override in child classes to produce audio."""
        return np.zeros((frames, 2), dtype=np.float32)
    
    def get_ui(self) -> QWidget | None:
        """
        Returns a QWidget representing the module's custom UI.
        By default, modules have no UI.
        Child classes (like EndpointModule) can override this.
        """
        return None

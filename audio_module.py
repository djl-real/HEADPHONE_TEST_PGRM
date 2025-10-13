import numpy as np
from nodes import InputNode, OutputNode
from PyQt6.QtWidgets import QWidget


class AudioModule:
    """Base class for all audio modules with support for multiple I/O nodes."""

    def __init__(self, input_count: int = 1, output_count: int = 1):
        self.input_count = max(0, input_count)
        self.output_count = max(0, output_count)

        # Create lists of input/output nodes
        self.input_nodes: list[InputNode] = [
            InputNode(self) for _ in range(self.input_count)
        ]
        self.output_nodes: list[OutputNode] = [
            OutputNode(self) for _ in range(self.output_count)
        ]

        # Backward compatibility for modules assuming single node
        self.input_node = self.input_nodes[0] if self.input_nodes else None
        self.output_node = self.output_nodes[0] if self.output_nodes else None

    def destroy(self):
        """Disconnect and clean up all nodes."""
        for node in getattr(self, "input_nodes", []):
            try:
                node.disconnect()
            except Exception:
                pass
        for node in getattr(self, "output_nodes", []):
            try:
                node.disconnect()
            except Exception:
                pass

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

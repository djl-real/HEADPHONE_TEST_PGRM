# nodes.py
import numpy as np
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from audio_module import AudioModule

class Node:
    """Base class for all nodes."""
    def __init__(self, module: 'AudioModule'):
        self.module = module
        self.connection: Optional['Node'] = None

    def disconnect(self):
        """Disconnect this node from its connected counterpart."""
        if self.connection:
            self.connection.connection = None
            self.connection = None

    def connect(self, other: 'Node'):
        """Connect this node to another node, disconnecting any previous connections."""
        if isinstance(self, InputNode) and not isinstance(other, OutputNode):
            raise TypeError("InputNode can only connect to an OutputNode")
        if isinstance(self, OutputNode) and not isinstance(other, InputNode):
            raise TypeError("OutputNode can only connect to an InputNode")

        # Disconnect previous connections
        if self.connection is not None:
            self.disconnect()
        self.connection = other
        other.connection = self


class InputNode(Node):
    """Receives audio from an OutputNode and passes it to the module."""
    def receive(self, frames: int) -> np.ndarray:
        """Called by connected OutputNode to propagate audio."""
        if self.connection is None:
            return np.zeros((frames, 2), dtype=np.float32)
        return self.connection.send(frames)


class OutputNode(Node):
    """Sends audio from a module to a connected InputNode."""
    def send(self, frames: int) -> np.ndarray:
        """Called by the module to propagate output to connected input."""
        if self.connection is None:
            return np.zeros((frames, 2), dtype=np.float32)
        return self.module.generate(frames)

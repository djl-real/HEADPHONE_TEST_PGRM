# nodes.py
import numpy as np

class InputNode:
    """Receives audio from an OutputNode and passes it to the module."""
    def __init__(self, module):
        self.module = module
        self.connection = None  # connected OutputNode

    def receive(self, frames: int) -> np.ndarray:
        """Called by connected OutputNode to propagate audio."""
        # If no connection, return silence
        if self.connection is None:
            return np.zeros((frames, 2), dtype=np.float32)
        # Otherwise, generate audio from parent module
        return self.connection.send(frames)

    def disconnect(self):
        """Disconnect from connected output."""
        if self.connection:
            self.connection.connection = None
            self.connection = None


class OutputNode:
    """Sends audio from a module to a connected InputNode."""
    def __init__(self, module):
        self.module = module
        self.connection = None  # connected InputNode

    def send(self, frames: int) -> np.ndarray:
        """Called by the module to propagate output to connected input."""
        if self.connection is None:
            return np.zeros((frames, 2), dtype=np.float32)
        return self.module.generate(frames)

    def connect(self, input_node: InputNode):
        """Connect this output to an input node, disconnecting previous connections."""
        # Disconnect previous
        if self.connection is not None:
            self.connection.connection = None
        self.connection = input_node
        input_node.connection = self

    def disconnect(self):
        """Disconnect this output from its input node."""
        if self.connection:
            self.connection.connection = None
            self.connection = None

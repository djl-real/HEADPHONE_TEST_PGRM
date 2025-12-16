# nodes.py
import numpy as np
from typing import Optional, TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from audio_module import AudioModule

class Node:
    """Unified node class that can send and receive data."""
    
    def __init__(self, module: 'AudioModule', is_input: bool = True, data_type: str = "audio",
                 color: str = None, position: str = None, label: str = "Audio"):
        """
        Initialize a node.
        
        Args:
            module: The audio module this node belongs to
            is_input: True if this is an input node, False if output
            data_type: Type of data this node handles ("audio", "control", "midi", etc.)
                      Defaults to "audio" for backward compatibility
            color: Hex color code for visual representation (e.g., "#FF5733")
            position: Position on module ("left", "right", "top", "bottom")
            label: Display label for the node (defaults to "Audio")
        """
        self.module = module
        self.is_input = is_input
        self.data_type = data_type
        self.color = color
        self.position = position
        self.label = label
        self.connection: Optional['Node'] = None
        self.block_touch = True

    def disconnect(self):
        """Disconnect this node from its connected counterpart."""
        if self.connection:
            self.connection.connection = None
            self.connection = None

    def connect(self, other: 'Node'):
        """Connect this node to another node, disconnecting any previous connections."""
        # Validate connection types
        if self.is_input == other.is_input:
            raise TypeError("Cannot connect two input nodes or two output nodes together")
        
        # Warn if data types don't match (but allow connection)
        if self.data_type != other.data_type:
            print(f"Warning: Connecting nodes with different data types: {self.data_type} -> {other.data_type}")
        
        # Disconnect previous connections
        if self.connection is not None:
            self.disconnect()
        if other.connection is not None:
            other.disconnect()
            
        # Establish bidirectional connection
        self.connection = other
        other.connection = self

    def receive(self, frames: int) -> Any:
        """
        Receive data from connected node.
        For input nodes, this pulls data from the connected output node.
        """
        if not self.is_input:
            raise RuntimeError("Cannot receive on an output node")
        
        if self.connection is None:
            # Return default data based on type
            return self._get_default_data(frames)
        
        return self.connection.send(frames)

    def send(self, frames: int) -> Any:
        """
        Send data to connected node.
        For output nodes, this generates data from the module.
        """
        if self.is_input:
            raise RuntimeError("Cannot send from an input node")
        
        if self.connection is None:
            return self._get_default_data(frames)
        
        # Call the module's generate method
        return self.module.generate(frames)

    def _get_default_data(self, frames: int) -> Any:
        """Return default data based on the node's data type."""
        if self.data_type == "audio":
            return np.zeros((frames, 2), dtype=np.float32)
        elif self.data_type == "control":
            return 0.0
        elif self.data_type == "midi":
            return []
        elif self.data_type == "cue":
            return None
        else:
            return None


# Backward compatibility aliases
class InputNode(Node):
    """Input node - receives data from output nodes."""
    def __init__(self, module: 'AudioModule', data_type: str = "audio", 
                 color: str = None, position: str = None):
        super().__init__(module, is_input=True, data_type=data_type, 
                        color=color, position=position)


class OutputNode(Node):
    """Output node - sends data to input nodes."""
    def __init__(self, module: 'AudioModule', data_type: str = "audio",
                 color: str = None, position: str = None):
        super().__init__(module, is_input=False, data_type=data_type,
                        color=color, position=position)
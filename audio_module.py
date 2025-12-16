# audio_module.py
import numpy as np
from nodes import Node, InputNode, OutputNode
from PyQt6.QtWidgets import QWidget

class AudioModule:
    """Base class for all audio modules with support for multiple I/O nodes."""

    def __init__(self, input_count: int = 1, output_count: int = 1, 
                 input_types: list[str] = None, output_types: list[str] = None,
                 input_colors: list[str] = None, output_colors: list[str] = None,
                 input_positions: list[str] = None, output_positions: list[str] = None,
                 input_labels: list[str] = None, output_labels: list[str] = None):
        """
        Initialize an audio module.
        
        Args:
            input_count: Number of input nodes
            output_count: Number of output nodes
            input_types: List of data types for each input (default: all "audio")
            output_types: List of data types for each output (default: all "audio")
            input_colors: List of hex color codes for each input (default: all None)
            output_colors: List of hex color codes for each output (default: all None)
            input_positions: List of positions for each input (default: all None)
            output_positions: List of positions for each output (default: all None)
            input_labels: List of labels for each input (default: all "Audio")
            output_labels: List of labels for each output (default: all "Audio")
        """
        self.input_count = max(0, input_count)
        self.output_count = max(0, output_count)

        # Default all nodes to "audio" type if not specified
        if input_types is None:
            input_types = ["audio"] * self.input_count
        if output_types is None:
            output_types = ["audio"] * self.output_count
        
        # Default colors and positions to None
        if input_colors is None:
            input_colors = [None] * self.input_count
        if output_colors is None:
            output_colors = [None] * self.output_count
        if input_positions is None:
            input_positions = [None] * self.input_count
        if output_positions is None:
            output_positions = [None] * self.output_count
        
        # Default labels to "Audio"
        if input_labels is None:
            input_labels = ["Audio"] * self.input_count
        if output_labels is None:
            output_labels = ["Audio"] * self.output_count

        # Validate list lengths
        if len(input_types) != self.input_count:
            raise ValueError(f"input_types length ({len(input_types)}) must match input_count ({self.input_count})")
        if len(output_types) != self.output_count:
            raise ValueError(f"output_types length ({len(output_types)}) must match output_count ({self.output_count})")
        if len(input_colors) != self.input_count:
            raise ValueError(f"input_colors length ({len(input_colors)}) must match input_count ({self.input_count})")
        if len(output_colors) != self.output_count:
            raise ValueError(f"output_colors length ({len(output_colors)}) must match output_count ({self.output_count})")
        if len(input_positions) != self.input_count:
            raise ValueError(f"input_positions length ({len(input_positions)}) must match input_count ({self.input_count})")
        if len(output_positions) != self.output_count:
            raise ValueError(f"output_positions length ({len(output_positions)}) must match output_count ({self.output_count})")
        if len(input_labels) != self.input_count:
            raise ValueError(f"input_labels length ({len(input_labels)}) must match input_count ({self.input_count})")
        if len(output_labels) != self.output_count:
            raise ValueError(f"output_labels length ({len(output_labels)}) must match output_count ({self.output_count})")

        # Create lists of input/output nodes with specified types, colors, positions, and labels
        self.input_nodes: list[Node] = [
            Node(self, is_input=True, data_type=input_types[i], 
                 color=input_colors[i], position=input_positions[i], label=input_labels[i]) 
            for i in range(self.input_count)
        ]
        self.output_nodes: list[Node] = [
            Node(self, is_input=False, data_type=output_types[i],
                 color=output_colors[i], position=output_positions[i], label=output_labels[i]) 
            for i in range(self.output_count)
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
        Child classes can override this.
        """
        return None

    # --- Insert module between nodes ---
    def insert(self, input_node: Node, output_node: Node):
        """Insert this module between two connected nodes."""
        # Enforce I/O requirements
        if self.input_count == 0 or self.output_count == 0:
            raise Exception("Module must have at least 1 input and 1 output to insert")

        # Validate node types
        if not output_node.is_input and input_node.is_input:
            # output_node is actually an output, input_node is actually an input
            self.input_node.connect(output_node)
            self.output_node.connect(input_node)
        else:
            raise TypeError("Invalid node types for insertion")

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """
        Return a dict representation of this module's state.
        Child modules should call super().serialize() and update the dict with their parameters.
        """
        return {
            "input_count": self.input_count,
            "output_count": self.output_count,
            "input_types": [node.data_type for node in self.input_nodes],
            "output_types": [node.data_type for node in self.output_nodes],
            "input_colors": [node.color for node in self.input_nodes],
            "output_colors": [node.color for node in self.output_nodes],
            "input_positions": [node.position for node in self.input_nodes],
            "output_positions": [node.position for node in self.output_nodes],
            "input_labels": [node.label for node in self.input_nodes],
            "output_labels": [node.label for node in self.output_nodes],
        }

    def deserialize(self, state: dict):
        """
        Restore this module's state from a dictionary.
        Child modules should call super().deserialize(state) first.
        """
        self.input_count = state.get("input_count", 1)
        self.output_count = state.get("output_count", 1)
        input_types = state.get("input_types", ["audio"] * self.input_count)
        output_types = state.get("output_types", ["audio"] * self.output_count)
        input_colors = state.get("input_colors", [None] * self.input_count)
        output_colors = state.get("output_colors", [None] * self.output_count)
        input_positions = state.get("input_positions", [None] * self.input_count)
        output_positions = state.get("output_positions", [None] * self.output_count)
        input_labels = state.get("input_labels", ["Audio"] * self.input_count)
        output_labels = state.get("output_labels", ["Audio"] * self.output_count)

        # Recreate nodes if counts changed
        current_inputs = len(self.input_nodes)
        current_outputs = len(self.output_nodes)

        # Add missing input nodes
        for i in range(self.input_count - current_inputs):
            idx = current_inputs + i
            data_type = input_types[idx] if idx < len(input_types) else "audio"
            color = input_colors[idx] if idx < len(input_colors) else None
            position = input_positions[idx] if idx < len(input_positions) else None
            label = input_labels[idx] if idx < len(input_labels) else "Audio"
            self.input_nodes.append(Node(self, is_input=True, data_type=data_type,
                                        color=color, position=position, label=label))

        # Add missing output nodes
        for i in range(self.output_count - current_outputs):
            idx = current_outputs + i
            data_type = output_types[idx] if idx < len(output_types) else "audio"
            color = output_colors[idx] if idx < len(output_colors) else None
            position = output_positions[idx] if idx < len(output_positions) else None
            label = output_labels[idx] if idx < len(output_labels) else "Audio"
            self.output_nodes.append(Node(self, is_input=False, data_type=data_type,
                                         color=color, position=position, label=label))

        # Remove extra nodes if count decreased
        self.input_nodes = self.input_nodes[:self.input_count]
        self.output_nodes = self.output_nodes[:self.output_count]

        # Update single-node references
        self.input_node = self.input_nodes[0] if self.input_nodes else None
        self.output_node = self.output_nodes[0] if self.output_nodes else None
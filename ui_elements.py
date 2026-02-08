# ui_elements.py
import traceback
from PyQt6.QtWidgets import (
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem,
    QGraphicsTextItem, QGraphicsProxyWidget, QGraphicsSimpleTextItem
)
from PyQt6.QtGui import QBrush, QPen, QColor, QPainterPath, QFont
from PyQt6.QtCore import QPointF, Qt, QRectF, QTimer

# from main_window import MainWindow
from audio_module import AudioModule


class ConnectionPath(QGraphicsPathItem):
    """Draws a curved line between two node circles and manages disconnection."""

    def __init__(self, start_node, end_node=None, scene=None, width: int = 3, color: QColor | None = None):
        super().__init__()
        self.start_node = start_node
        self.end_node = end_node

        # Visuals
        color = color or QColor(180, 180, 180)
        self.setZValue(-1)
        self.setPen(QPen(color, width))

        # Prevents repeated grab/ungrab warnings
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setAcceptTouchEvents(False)

        # Add to scene if provided
        if scene is not None:
            scene.addItem(self)

        # Register references on nodes
        try:
            self.start_node.connection = self
        except Exception:
            pass

        if self.end_node:
            try:
                self.end_node.connection = self
            except Exception:
                pass
            self.update_path()

    def update_path(self):
        """Recompute cubic bezier between start_node and end_node."""
        if not (self.start_node and self.end_node):
            return
        start = self.start_node.scenePos() + QPointF(self.start_node.RADIUS, 0)
        end = self.end_node.scenePos() - QPointF(self.end_node.RADIUS, 0)
        path = QPainterPath(start)
        dx = (end.x() - start.x()) * 0.5
        path.cubicTo(start + QPointF(dx, 0), end - QPointF(dx, 0), end)
        self.setPath(path)

    def update_path_from_pos(self, end_pos: QPointF):
        """Used during dragging: draw path from start node to arbitrary scene position."""
        if not self.start_node:
            return
        start = self.start_node.scenePos() + QPointF(self.start_node.RADIUS, 0)
        path = QPainterPath(start)
        dx = (end_pos.x() - start.x()) * 0.5
        path.cubicTo(start + QPointF(dx, 0), end_pos - QPointF(dx, 0), end_pos)
        self.setPath(path)

    def disconnect(self):
        """Sever the connection visually and in the audio backend."""
        start_node = getattr(self, "start_node", None)
        end_node = getattr(self, "end_node", None)

        # Backend disconnect via node_obj
        try:
            if start_node and getattr(start_node, "node_obj", None):
                start_node.node_obj.disconnect()
        except Exception:
            pass

        # Clear UI references
        for node in (start_node, end_node):
            try:
                if node:
                    node.connection = None
            except Exception:
                pass

        # Remove the path from its scene
        try:
            sc = self.scene()
            if sc is not None:
                sc.removeItem(self)
        except Exception:
            pass

        self.start_node = None
        self.end_node = None

    def is_audio_connection(self) -> bool:
        """Check if this connection is between audio-type nodes."""
        start_is_audio = (
            self.start_node and 
            self.start_node.node_obj and 
            hasattr(self.start_node.node_obj, 'data_type') and 
            self.start_node.node_obj.data_type == "audio"
        )
        end_is_audio = (
            self.end_node and 
            self.end_node.node_obj and 
            hasattr(self.end_node.node_obj, 'data_type') and 
            self.end_node.node_obj.data_type == "audio"
        )
        return start_is_audio and end_is_audio


class NodeCircle(QGraphicsEllipseItem):
    """Clickable circle representing an input or output node."""

    RADIUS = 10

    def __init__(self, parent_item, node_type="output", node_obj=None, index=0):
        """
        Parameters:
            parent_item: The parent QGraphicsItem (usually a ModuleItem)
            node_type: "input" or "output"
            node_obj: Backend node reference
            index: Position index within the module's I/O list
        """
        super().__init__(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS, parent_item)
        self.node_type = node_type
        self.node_obj = node_obj
        self.index = index
        self.connection: ConnectionPath | None = None

        # Unique ID for layout serialization
        self.node_id = f"{id(self)}"

        # UI parent and backend references
        self.module_item = parent_item
        self.audio_module = getattr(parent_item, "module", None)

        # Get color from node_obj if available, otherwise use default
        if node_obj and hasattr(node_obj, 'color') and node_obj.color:
            try:
                color = QColor(node_obj.color)
            except:
                color = QColor(150, 80, 200) if node_type == "output" else QColor(80, 150, 200)
        else:
            color = QColor(150, 80, 200) if node_type == "output" else QColor(80, 150, 200)
        
        self.default_color = color
        self.setBrush(QBrush(color))

        # Add label if available
        self.label = None
        if node_obj and hasattr(node_obj, 'label') and node_obj.label:
            self.label = QGraphicsSimpleTextItem(node_obj.label, parent_item)
            self.label.setBrush(QBrush(QColor(200, 200, 200)))
            self.label.setFont(QFont("Arial", 8))
            self.label.setZValue(3)

        # Enable mouse interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptTouchEvents(True)

        # Temporary connection during drag
        self.temp_connection: ConnectionPath | None = None

    def update_label_position(self):
        """Update the label position based on node type and custom position."""
        if not self.label:
            return
        
        label_width = self.label.boundingRect().width()
        label_height = self.label.boundingRect().height()
        
        # Get the node's position within the parent module
        node_x = self.pos().x()
        node_y = self.pos().y()
        
        # Get custom position from node_obj if available
        custom_position = None
        if self.node_obj and hasattr(self.node_obj, 'position'):
            custom_position = self.node_obj.position
        
        # Calculate label position based on custom position or defaults
        if custom_position == "top":
            label_x = node_x - label_width / 2
            label_y = node_y + self.RADIUS + 4
        elif custom_position == "bottom":
            label_x = node_x - label_width / 2
            label_y = node_y - self.RADIUS - label_height - 4
        elif custom_position == "left":
            label_x = node_x + self.RADIUS + 6
            label_y = node_y - label_height / 2
        elif custom_position == "right":
            label_x = node_x - label_width - self.RADIUS - 6
            label_y = node_y - label_height / 2
        else:
            # Default positioning based on node type
            if self.node_type == "input":
                # Input nodes are on the left, so label goes to the right of the node
                label_x = node_x + self.RADIUS + 6
                label_y = node_y - label_height / 2
            else:
                # Output nodes are on the right, so label goes to the left of the node
                label_x = node_x - label_width - self.RADIUS - 6
                label_y = node_y - label_height / 2
        
        self.label.setPos(label_x, label_y)

    def is_audio_node(self) -> bool:
        """Check if this node has data_type == 'audio'."""
        return (
            self.node_obj and 
            hasattr(self.node_obj, 'data_type') and 
            self.node_obj.data_type == "audio"
        )

    def get_data_type(self) -> str | None:
        """Get the data_type of this node, or None if not set."""
        if self.node_obj and hasattr(self.node_obj, 'data_type'):
            return self.node_obj.data_type
        return None

    def can_connect_to(self, other: "NodeCircle") -> bool:
        """Check if this node can connect to another node based on data types."""
        self_type = self.get_data_type()
        other_type = other.get_data_type()
        
        # If either node doesn't have a data_type, allow connection (backward compatibility)
        if self_type is None or other_type is None:
            return True
        
        return self_type == other_type

    def connect(self, dst: "NodeCircle"):
        """
        Connect this output NodeCircle to a destination input NodeCircle.
        Handles:
        - backend connect()
        - disconnecting any previous wires
        - creating new ConnectionPath
        - updating UI link
        """
        # Validate types
        if self.node_type != "output" or dst.node_type != "input":
            print("⚠️ NodeCircle.connect: invalid direction")
            return False

        # Validate data types match
        if not self.can_connect_to(dst):
            print(f"⚠️ NodeCircle.connect: data type mismatch ({self.get_data_type()} vs {dst.get_data_type()})")
            return False

        sc = self.scene()
        if sc is None:
            print("⚠️ NodeCircle.connect: no scene")
            return False

        # Disconnect old connections on both ends
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass
            self.connection = None

        if dst.connection:
            try:
                dst.connection.disconnect()
            except Exception:
                pass
            dst.connection = None

        # Backend connect
        if self.node_obj and dst.node_obj:
            try:
                self.node_obj.connect(dst.node_obj)
            except Exception:
                traceback.print_exc()
                return False

        # Create new UI path
        try:
            new_path = ConnectionPath(self, dst, scene=sc)
            self.connection = new_path
            dst.connection = new_path
            new_path.update_path()
        except Exception:
            traceback.print_exc()
            return False

        return True
    # ------------------- Interaction Events -------------------

    def mousePressEvent(self, event):
        # Disconnect any existing connection
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass
            self.connection = None

        # Begin dragging a new connection from an output node
        if self.node_type == "output":
            try:
                sc = self.scene()
                if sc:
                    self.temp_connection = ConnectionPath(self, scene=sc)
            except Exception:
                self.temp_connection = None

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.temp_connection:
            try:
                scene_pos = self.mapToScene(event.pos())
                self.temp_connection.update_path_from_pos(scene_pos)
            except Exception:
                pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # When releasing an output connection, finalize or discard
        if self.temp_connection:
            try:
                scene_pos = self.mapToScene(event.pos())
                items = self.scene().items(scene_pos) if self.scene() else []
                target_input = next(
                    (it for it in items 
                     if isinstance(it, NodeCircle) 
                     and it.node_type == "input"
                     and self.can_connect_to(it)),  # Check data type compatibility
                    None
                )

                if target_input:
                    # If target input already has a connection, remove it cleanly
                    if target_input.connection:
                        try:
                            old_conn = target_input.connection
                            # Backend disconnection
                            if getattr(target_input.node_obj, "disconnect", None):
                                target_input.node_obj.disconnect()
                            # Remove old connection visually
                            old_conn.disconnect()
                        except Exception:
                            pass
                        target_input.connection = None

                    # Backend connection (new)
                    if self.node_obj and target_input.node_obj:
                        try:
                            self.node_obj.connect(target_input.node_obj)
                        except Exception:
                            traceback.print_exc()

                    # Frontend path setup
                    self.temp_connection.end_node = target_input
                    self.connection = self.temp_connection
                    target_input.connection = self.temp_connection
                    self.temp_connection.update_path()

                else:
                    # Drop canceled — remove temp connection
                    try:
                        self.temp_connection.disconnect()
                    except Exception:
                        sc = self.scene()
                        if sc and self.temp_connection in sc.items():
                            sc.removeItem(self.temp_connection)

                self.temp_connection = None

            except Exception:
                self.temp_connection = None

        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        try:
            self.setBrush(QBrush(QColor(255, 180, 100)))
        except Exception:
            pass
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        try:
            self.setBrush(QBrush(self.default_color))
        except Exception:
            pass
        super().hoverLeaveEvent(event)

    # ------------------- Serialization -------------------

    def serialize(self) -> dict:
        """Return a dict representation for saving layout."""
        return {
            "type": self.node_type,
            "index": self.index,
            "module_id": getattr(self.module_item, "module_id", None),
        }

    @staticmethod
    def deserialize(data: dict, module_lookup: dict):
        """
        Static helper to rebuild NodeCircle connections when loading layout.
        module_lookup maps module_id -> ModuleItem.
        """
        mod = module_lookup.get(data.get("module_id"))
        if not mod:
            return None

        if data["type"] == "input" and data["index"] < len(mod.input_nodes):
            return mod.input_nodes[data["index"]]
        elif data["type"] == "output" and data["index"] < len(mod.output_nodes):
            return mod.output_nodes[data["index"]]
        return None


class CloseButton(QGraphicsSimpleTextItem):
    """Clickable 'X' to close and delete a module (visual only)."""

    def __init__(self, parent_module_item):
        super().__init__("✕", parent_module_item)
        self.setBrush(QBrush(QColor(200, 200, 200)))
        self.setFont(QFont("Arial", 12))
        self.setZValue(10)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.parent_module_item = parent_module_item
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event):
        try:
            if self.parent_module_item:
                self.parent_module_item.cleanup()
        except Exception:
            pass
        super().mousePressEvent(event)

class ModuleItem(QGraphicsRectItem):
    """Graphics item representing an audio module with multiple I/O nodes."""

    DEFAULT_WIDTH = 150
    DEFAULT_HEIGHT = 100
    NODE_SPACING = 20

    HIGHLIGHT_COLOR = QColor(220, 180, 30)
    DEFAULT_CONN_COLOR = QColor(180, 180, 180)

    def __init__(self, module: AudioModule, main_window):
        super().__init__(0, 0, self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.module = module
        self.module_id = f"{id(module)}"
        self.main_window = main_window

        self.setBrush(QBrush(QColor(40, 40, 40)))
        self.setPen(QPen(QColor(120, 120, 120)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self.label = QGraphicsTextItem(module.__class__.__name__, self)
        self.label.setDefaultTextColor(QColor(255, 255, 255))
        self.label.setPos(10, 5)

        self.close_button = CloseButton(self)

        # Node circles
        self.input_nodes: list[NodeCircle] = []
        for idx, node in enumerate(getattr(module, "input_nodes", [])):
            nc = NodeCircle(self, "input", node_obj=node, index=idx)
            nc.setZValue(2)
            self.input_nodes.append(nc)

        self.output_nodes: list[NodeCircle] = []
        for idx, node in enumerate(getattr(module, "output_nodes", [])):
            nc = NodeCircle(self, "output", node_obj=node, index=idx)
            nc.setZValue(2)
            self.output_nodes.append(nc)

        self.input_node = self.input_nodes[0] if self.input_nodes else None
        self.output_node = self.output_nodes[0] if self.output_nodes else None

        self._proxy_widget = None
        self.get_ui()

    def get_ui(self):
        """Embed the module's custom QWidget UI."""
        if self._proxy_widget:
            try:
                sc = self.scene()
                if sc:
                    sc.removeItem(self._proxy_widget)
            except Exception:
                pass
            self._proxy_widget = None

        ui_widget = None
        if hasattr(self.module, "get_ui"):
            try:
                ui_widget = self.module.get_ui()
            except Exception:
                pass

        width, height = self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT
        label_height = self.label.boundingRect().height()
        padding = 10

        if ui_widget:
            try:
                ui_widget.adjustSize()
            except Exception:
                pass
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(ui_widget)
            proxy.setZValue(2)
            proxy.setPos(10, label_height + padding)
            proxy_rect = proxy.boundingRect()
            width = max(width, proxy_rect.width() + 20)
            height = max(height, proxy_rect.height() + label_height + 20)
            self._proxy_widget = proxy

        self.setRect(0, 0, width, height)

        # Position nodes based on their custom position attribute or defaults
        self._position_nodes(width, height)

        self.close_button.setPos(width - 20, 2)

    def _position_nodes(self, width, height):
        """Position input and output nodes based on custom positions or defaults."""
        # Group nodes by position
        input_by_position = {"left": [], "right": [], "top": [], "bottom": [], None: []}
        output_by_position = {"left": [], "right": [], "top": [], "bottom": [], None: []}
        
        for node in self.input_nodes:
            pos = node.node_obj.position if node.node_obj and hasattr(node.node_obj, 'position') else None
            input_by_position[pos].append(node)
        
        for node in self.output_nodes:
            pos = node.node_obj.position if node.node_obj and hasattr(node.node_obj, 'position') else None
            output_by_position[pos].append(node)
        
        # Position left side (inputs default here if no position specified)
        left_nodes = input_by_position["left"] + input_by_position[None]
        if left_nodes:
            spacing = self.NODE_SPACING
            start_y = (height - spacing * (len(left_nodes) - 1)) / 2
            for idx, node in enumerate(left_nodes):
                node.setPos(0, start_y + idx * spacing)
                node.update_label_position()
        
        # Position right side (outputs default here if no position specified)
        right_nodes = output_by_position["right"] + output_by_position[None]
        if right_nodes:
            spacing = self.NODE_SPACING
            start_y = (height - spacing * (len(right_nodes) - 1)) / 2
            for idx, node in enumerate(right_nodes):
                node.setPos(width, start_y + idx * spacing)
                node.update_label_position()
        
        # Position top side
        top_nodes = input_by_position["top"] + output_by_position["top"]
        if top_nodes:
            spacing = self.NODE_SPACING
            start_x = (width - spacing * (len(top_nodes) - 1)) / 2
            for idx, node in enumerate(top_nodes):
                node.setPos(start_x + idx * spacing, 0)
                node.update_label_position()
        
        # Position bottom side
        bottom_nodes = input_by_position["bottom"] + output_by_position["bottom"]
        if bottom_nodes:
            spacing = self.NODE_SPACING
            start_x = (width - spacing * (len(bottom_nodes) - 1)) / 2
            for idx, node in enumerate(bottom_nodes):
                node.setPos(start_x + idx * spacing, height)
                node.update_label_position()
        
        # Position explicitly right-positioned inputs
        if input_by_position["right"]:
            spacing = self.NODE_SPACING
            start_y = (height - spacing * (len(input_by_position["right"]) - 1)) / 2
            for idx, node in enumerate(input_by_position["right"]):
                node.setPos(width, start_y + idx * spacing)
                node.update_label_position()
        
        # Position explicitly left-positioned outputs
        if output_by_position["left"]:
            spacing = self.NODE_SPACING
            start_y = (height - spacing * (len(output_by_position["left"]) - 1)) / 2
            for idx, node in enumerate(output_by_position["left"]):
                node.setPos(0, start_y + idx * spacing)
                node.update_label_position()

    def has_free_connections(self) -> bool:
        """Check if all input and output nodes are unconnected."""
        for node in self.input_nodes + self.output_nodes:
            if node.connection is not None:
                return False
        return True

    def get_audio_input_nodes(self) -> list[NodeCircle]:
        """Get all input nodes that have data_type == 'audio'."""
        return [n for n in self.input_nodes if n.is_audio_node()]

    def get_audio_output_nodes(self) -> list[NodeCircle]:
        """Get all output nodes that have data_type == 'audio'."""
        return [n for n in self.output_nodes if n.is_audio_node()]

    def can_insert(self) -> bool:
        """Check if this module can be inserted into a connection.
        
        Requirements:
        - Must have at least one audio input node
        - Must have at least one audio output node
        - All connections must be free (no existing connections)
        """
        has_audio_input = len(self.get_audio_input_nodes()) > 0
        has_audio_output = len(self.get_audio_output_nodes()) > 0
        return has_audio_input and has_audio_output and self.has_free_connections()

    def cleanup(self):
        """
        Safely clean up and remove module from scene.

        NEW FEATURE:
        If this module has at least one connected input and one connected output,
        auto-connect inbound node to outbound node before removing the module.
        """

        # --------------------------------------------------------------
        # 1. Detect upstream and downstream connections (ONLY if both exist)
        # --------------------------------------------------------------
        upstream_node = None
        downstream_node = None

        # Find first connected input (upstream)
        for n in self.input_nodes:
            if n.connection and n.connection.start_node:
                upstream_node = n.connection.start_node
                break

        # Find first connected output (downstream)
        for n in self.output_nodes:
            if n.connection and n.connection.end_node:
                downstream_node = n.connection.end_node
                break

        should_autobridge = upstream_node is not None and downstream_node is not None

        # --------------------------------------------------------------
        # 2. Disconnect this module's connections BEFORE removing UI nodes
        # --------------------------------------------------------------
        for node in self.input_nodes + self.output_nodes:
            if node.connection:
                try:
                    node.connection.disconnect()
                except Exception:
                    pass
                node.connection = None

            if getattr(node, "temp_connection", None):
                try:
                    node.temp_connection.disconnect()
                except Exception:
                    pass
                node.temp_connection = None

        # --------------------------------------------------------------
        # 3. Automatically reconnect upstream → downstream
        # --------------------------------------------------------------
        if should_autobridge:
            try:
                # The upstream is always an *output node*
                # The downstream is always an *input node*
                upstream_node.connect(downstream_node)
            except Exception:
                traceback.print_exc()

        # --------------------------------------------------------------
        # 4. Backend module destruction
        # --------------------------------------------------------------
        try:
            self.module.destroy()
        except Exception:
            pass

        # --------------------------------------------------------------
        # 5. Remove UI items
        # --------------------------------------------------------------
        sc = self.scene()
        if sc:
            if self._proxy_widget:
                try:
                    sc.removeItem(self._proxy_widget)
                except Exception:
                    pass

            QTimer.singleShot(1, lambda: sc.removeItem(self) if self.scene() else None)

        # --------------------------------------------------------------
        # 6. Final field cleanup
        # --------------------------------------------------------------
        self.main_window.destroy_module(self)
        self.module = None
        self.input_nodes = []
        self.output_nodes = []
        self.input_node = None
        self.output_node = None
        self._proxy_widget = None


    def itemChange(self, change, value):
        """Update connections and highlight overlapping paths while moving."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Update connected paths
            for node in self.input_nodes + self.output_nodes:
                if getattr(node, "connection", None):
                    try:
                        node.connection.update_path()
                    except Exception:
                        pass

            # Only highlight if module can be inserted (has free connections and audio nodes)
            if self.can_insert() and self.scene():
                module_rect = self.sceneBoundingRect()
                for item in self.scene().items():
                    if isinstance(item, ConnectionPath):
                        # Skip connections where this module is already the start or end
                        if (item.start_node and item.start_node.module_item == self) or \
                           (item.end_node and item.end_node.module_item == self):
                            continue

                        # Only highlight audio connections
                        if not item.is_audio_connection():
                            continue

                        path_rect = item.boundingRect().translated(item.scenePos())
                        pen = item.pen()
                        if module_rect.intersects(path_rect):
                            pen.setColor(self.HIGHLIGHT_COLOR)
                        else:
                            pen.setColor(self.DEFAULT_CONN_COLOR)
                        item.setPen(pen)

        return super().itemChange(change, value)

    def insert(self, output_node: NodeCircle, input_node: NodeCircle):
        """Insert this module between two existing NodeCircles.
        
        Parameters:
            output_node: The upstream output node (source of the connection)
            input_node: The downstream input node (destination of the connection)
        """
        # Check if this module can be inserted
        if not self.can_insert():
            print("Cannot insert: module has existing connections or no audio nodes")
            return

        # Get the first available audio input and output nodes for this module
        audio_inputs = self.get_audio_input_nodes()
        audio_outputs = self.get_audio_output_nodes()
        
        if not audio_inputs or not audio_outputs:
            print("Cannot insert: no audio input/output nodes available")
            return

        my_input = audio_inputs[0]
        my_output = audio_outputs[0]

        # Disconnect the existing connection (both backend and frontend)
        if output_node.connection:
            output_node.connection.disconnect()

        # Connect upstream output → our input (backend + frontend)
        try:
            if not output_node.connect(my_input):
                print("insert failed: could not connect upstream to module input")
                return
        except Exception:
            print("insert failed: upstream connection")
            traceback.print_exc()
            return

        # Connect our output → downstream input (backend + frontend)
        try:
            if not my_output.connect(input_node):
                print("insert failed: could not connect module output to downstream")
                return
        except Exception:
            print("insert failed: downstream connection")
            traceback.print_exc()

    def mouseReleaseEvent(self, event):
        """Finalize dragging and insert module if released over a highlighted connection."""
        super().mouseReleaseEvent(event)

        # Check if this module can be inserted
        if not self.can_insert() or not self.scene():
            return

        module_rect = self.sceneBoundingRect()
        highlighted_connections = [
            item for item in self.scene().items()
            if isinstance(item, ConnectionPath)
            and item.is_audio_connection()  # Only consider audio connections
            and item.pen().color() == self.HIGHLIGHT_COLOR
            and module_rect.intersects(item.boundingRect().translated(item.scenePos()))
        ]

        if highlighted_connections:
            conn = highlighted_connections[0]
            self.insert(conn.start_node, conn.end_node)
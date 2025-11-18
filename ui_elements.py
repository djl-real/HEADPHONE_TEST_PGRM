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
        self.index = index  # ✅ Unique index for saving/loading
        self.connection: ConnectionPath | None = None

        # Unique ID for layout serialization
        self.node_id = f"{id(self)}"  # ✅ transient unique identifier

        # UI parent and backend references
        self.module_item = parent_item
        self.audio_module = getattr(parent_item, "module", None)

        # Node color by type
        color = QColor(150, 80, 200) if node_type == "output" else QColor(80, 150, 200)
        self.setBrush(QBrush(color))

        # Enable mouse interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptTouchEvents(True)

        # Temporary connection during drag
        self.temp_connection: ConnectionPath | None = None

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
                    (it for it in items if isinstance(it, NodeCircle) and it.node_type == "input"),
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
            color = QColor(150, 80, 200) if self.node_type == "output" else QColor(80, 150, 200)
            self.setBrush(QBrush(color))
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
        self.module_id = f"{id(module)}"  # 🔧 unique ID for save/load mapping
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
            nc = NodeCircle(self, "input", node_obj=node, index=idx)  # 🔧 index passed in
            nc.setZValue(2)
            self.input_nodes.append(nc)

        self.output_nodes: list[NodeCircle] = []
        for idx, node in enumerate(getattr(module, "output_nodes", [])):
            nc = NodeCircle(self, "output", node_obj=node, index=idx)  # 🔧 index passed in
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

        # if self.width_override:
        #     width = max(width, self.width_override)
        # if self.height_override:
        #     height = max(height, self.height_override)

        self.setRect(0, 0, width, height)

        # Position input nodes
        if self.input_nodes:
            spacing = self.NODE_SPACING
            start_y = (height - spacing * (len(self.input_nodes) - 1)) / 2
            for idx, node in enumerate(self.input_nodes):
                node.setPos(0, start_y + idx * spacing)

        # Position output nodes
        if self.output_nodes:
            spacing = self.NODE_SPACING
            start_y = (height - spacing * (len(self.output_nodes) - 1)) / 2
            for idx, node in enumerate(self.output_nodes):
                node.setPos(width, start_y + idx * spacing)

        self.close_button.setPos(width - 20, 2)

    def cleanup(self):
        """Safely clean up and remove module from scene."""
        self.main_window.destroy_module(self)
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

        try:
            self.module.destroy()
        except Exception:
            pass

        sc = self.scene()
        if sc:
            if self._proxy_widget:
                try:
                    sc.removeItem(self._proxy_widget)
                except Exception:
                    pass
            QTimer.singleShot(1, lambda: sc.removeItem(self) if self.scene() else None)

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

            # Only highlight if module has at least 1 input and 1 output
            if len(self.input_nodes) > 0 and len(self.output_nodes) > 0 and self.scene():
                module_rect = self.sceneBoundingRect()
                for item in self.scene().items():
                    if isinstance(item, ConnectionPath):
                        # Skip connections where this module is already the start or end
                        if (item.start_node and item.start_node.module_item == self) or \
                           (item.end_node and item.end_node.module_item == self):
                            continue

                        path_rect = item.boundingRect().translated(item.scenePos())
                        pen = item.pen()
                        if module_rect.intersects(path_rect):
                            pen.setColor(self.HIGHLIGHT_COLOR)
                        else:
                            pen.setColor(self.DEFAULT_CONN_COLOR)
                        item.setPen(pen)

        return super().itemChange(change, value)

    def insert(self, input_node: NodeCircle, output_node: NodeCircle):
        """Insert this module between two existing NodeCircles (input and output)."""
        if not (self.input_nodes and self.output_nodes):
            print("not enough")
            return

        backend_input = input_node.node_obj
        backend_output = output_node.node_obj

        # Frontend: remove old connection
        if input_node.connection:
            input_node.connection.disconnect()

        if backend_input and backend_output:
            try:
                self.module.insert(backend_output, backend_input)
            except Exception:
                print("insert failed")
                traceback.print_exc()

        # Create new connections visually
        try:
            new_conn_start = ConnectionPath(input_node, self.input_nodes[0], scene=self.scene())
            input_node.connection = new_conn_start
            self.input_nodes[0].connection = new_conn_start

            new_conn_end = ConnectionPath(self.output_nodes[0], output_node, scene=self.scene())
            self.output_nodes[0].connection = new_conn_end
            output_node.connection = new_conn_end
        except Exception:
            print("ui failed")

    def mouseReleaseEvent(self, event):
        """Finalize dragging and insert module if released over a highlighted connection."""
        super().mouseReleaseEvent(event)

        if len(self.input_nodes) < 1 or len(self.output_nodes) < 1 or not self.scene():
            return

        module_rect = self.sceneBoundingRect()
        highlighted_connections = [
            item for item in self.scene().items()
            if isinstance(item, ConnectionPath)
            and item.pen().color() == self.HIGHLIGHT_COLOR
            and module_rect.intersects(item.boundingRect().translated(item.scenePos()))
        ]

        if highlighted_connections:
            conn = highlighted_connections[0]
            self.insert(conn.start_node, conn.end_node)
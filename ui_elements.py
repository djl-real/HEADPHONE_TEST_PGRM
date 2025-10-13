# ui_elements.py
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem, QGraphicsProxyWidget
from PyQt6.QtGui import QBrush, QPen, QColor, QPainterPath
from PyQt6.QtCore import QPointF, Qt

from audio_module import AudioModule


class ConnectionPath(QGraphicsPathItem):
    """Draws a curved line between two node circles."""
    def __init__(self, start_node, end_node=None, scene=None):
        super().__init__()
        self.start_node = start_node
        self.end_node = end_node

        self.setZValue(-1)
        self.setPen(QPen(QColor(180, 180, 180), 3))

        if scene is not None:
            scene.addItem(self)

        # Set node references
        self.start_node.connection = self
        if self.end_node:
            self.end_node.connection = self
            self.update_path()

    def update_path(self):
        if not self.end_node:
            return
        start = self.start_node.scenePos() + QPointF(self.start_node.RADIUS, 0)
        end = self.end_node.scenePos() - QPointF(self.end_node.RADIUS, 0)
        path = QPainterPath(start)
        dx = (end.x() - start.x()) * 0.5
        path.cubicTo(start + QPointF(dx, 0), end - QPointF(dx, 0), end)
        self.setPath(path)

    def update_path_from_pos(self, end_pos: QPointF):
        start = self.start_node.scenePos() + QPointF(self.start_node.RADIUS, 0)
        path = QPainterPath(start)
        dx = (end_pos.x() - start.x()) * 0.5
        path.cubicTo(start + QPointF(dx, 0), end_pos - QPointF(dx, 0), end_pos)
        self.setPath(path)


class NodeCircle(QGraphicsEllipseItem):
    RADIUS = 10

    def __init__(self, parent_item, node_type="output"):
        super().__init__(-self.RADIUS, -self.RADIUS, 2*self.RADIUS, 2*self.RADIUS, parent_item)
        self.node_type = node_type  # "input" or "output"
        self.connection: ConnectionPath | None = None

        self.module_item = parent_item
        self.audio_module = getattr(parent_item, "module", None)

        color = QColor(150, 80, 200) if node_type == "output" else QColor(80, 150, 200)
        self.setBrush(QBrush(color))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptTouchEvents(True)

        self.temp_connection: ConnectionPath | None = None

    def mousePressEvent(self, event):
        # Remove existing connection if present
        if self.connection:
            # Safely disconnect backend audio nodes
            if self.node_type == "output":
                if self.audio_module and self.connection.end_node and self.connection.end_node.audio_module:
                    try:
                        self.audio_module.output_node.disconnect(self.connection.end_node.audio_module.input_node)
                    except AttributeError:
                        pass  # ignore if disconnect is not implemented
            elif self.node_type == "input":
                if self.audio_module and self.connection.start_node and self.connection.start_node.audio_module:
                    try:
                        self.connection.start_node.audio_module.output_node.disconnect(self.audio_module.input_node)
                    except AttributeError:
                        pass

            # Remove visual connection
            if self.connection.start_node:
                self.connection.start_node.connection = None
            if self.connection.end_node:
                self.connection.end_node.connection = None
            self.scene().removeItem(self.connection)
            self.connection = None

        # Start a new connection if this is an output node
        if self.node_type == "output":
            self.temp_connection = ConnectionPath(self, scene=self.scene())

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.temp_connection:
            scene_pos = self.mapToScene(event.pos())
            self.temp_connection.update_path_from_pos(scene_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.temp_connection:
            scene_pos = self.mapToScene(event.pos())
            items = self.scene().items(scene_pos)
            target_input = next((i for i in items if isinstance(i, NodeCircle) and i.node_type == "input"), None)

            if target_input:
                # Connect backend nodes
                if self.audio_module and target_input.audio_module:
                    if getattr(self.audio_module, "output_node", None):
                        self.audio_module.output_node.connect(target_input.audio_module.input_node)

                # Finalize connection path
                self.temp_connection.end_node = target_input
                self.connection = self.temp_connection
                target_input.connection = self.temp_connection
                self.temp_connection.update_path()
            else:
                self.scene().removeItem(self.temp_connection)

            self.temp_connection = None

        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor(255, 180, 100)))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        color = QColor(150, 80, 200) if self.node_type == "output" else QColor(80, 150, 200)
        self.setBrush(QBrush(color))
        super().hoverLeaveEvent(event)

class ModuleItem(QGraphicsRectItem):
    """A graphics item representing an audio module with dynamic UI."""

    DEFAULT_WIDTH = 180
    DEFAULT_HEIGHT = 100

    def __init__(self, module: AudioModule, width_override: int = None, height_override: int = None):
        super().__init__(0, 0, self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.module = module
        self.width_override = width_override
        self.height_override = height_override

        # Background
        self.setBrush(QBrush(QColor(40, 40, 40)))
        self.setPen(QPen(QColor(120, 120, 120)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        # Module title
        self.label = QGraphicsTextItem(module.__class__.__name__, self)
        self.label.setDefaultTextColor(QColor(255, 255, 255))
        self.label.setPos(10, 5)

        # Input / output nodes
        self.input_node = NodeCircle(self, "input") if getattr(module, "input_node", None) else None
        self.output_node = NodeCircle(self, "output") if getattr(module, "output_node", None) else None

        # Embed UI and dynamically resize
        self.get_ui()

    def get_ui(self):
        """Embed the module's custom QWidget UI and dynamically resize ModuleItem."""
        if not hasattr(self.module, "get_ui"):
            return

        ui_widget = self.module.get_ui()
        if ui_widget is None:
            return

        # Ensure layout calculations are updated
        ui_widget.adjustSize()

        # Embed using QGraphicsProxyWidget
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(ui_widget)
        proxy.setZValue(2)

        # Position below the title
        label_height = self.label.boundingRect().height()
        padding = 10
        proxy.setPos(10, label_height + padding)

        # Use proxy.boundingRect for accurate size
        proxy_rect = proxy.boundingRect()
        new_width = max(self.DEFAULT_WIDTH, proxy_rect.width() + 20)
        new_height = max(self.DEFAULT_HEIGHT, proxy_rect.height() + label_height + 20)

        # Apply manual overrides
        if self.width_override:
            new_width = max(new_width, self.width_override)
        if self.height_override:
            new_height = max(new_height, self.height_override)

        # Set ModuleItem rect
        self.setRect(0, 0, new_width, new_height)

        # Reposition input/output nodes vertically centered
        if self.input_node:
            self.input_node.setPos(0, new_height / 2)
        if self.output_node:
            self.output_node.setPos(new_width, new_height / 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Update connection paths
            for node in [self.input_node, self.output_node]:
                if node and node.connection:
                    node.connection.update_path()
        return super().itemChange(change, value)

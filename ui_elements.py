# ui_elements.py
from PyQt6.QtWidgets import (
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem,
    QGraphicsTextItem, QGraphicsProxyWidget, QGraphicsSimpleTextItem
)
from PyQt6.QtGui import QBrush, QPen, QColor, QPainterPath, QFont
from PyQt6.QtCore import QPointF, Qt, QRectF, QTimer

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

        # Make sure this path never grabs the mouse or accepts hover events
        # — prevents repeated grab/ungrab warnings.
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setAcceptTouchEvents(False)

        # Add to scene if provided (the caller should supply scene once)
        if scene is not None and scene is not None:
            scene.addItem(self)

        # Register references on nodes (each node has at most one connection)
        try:
            # set start node reference
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
        # Control points keep the curve smooth
        path.cubicTo(start + QPointF(dx, 0), end_pos - QPointF(dx, 0), end_pos)
        self.setPath(path)

    def disconnect(self):
        """
        Sever the connection both visually and in the audio backend.
        This function is idempotent and safe to call multiple times.
        """
        start_node = getattr(self, "start_node", None)
        end_node = getattr(self, "end_node", None)

        # Backend disconnect: call output_node.disconnect() if available.
        # OutputNode.disconnect() should clear backend link to input node.
        try:
            if start_node and getattr(start_node, "audio_module", None):
                out = getattr(start_node.audio_module, "output_node", None)
                if out:
                    out.disconnect()
        except Exception:
            # be defensive: don't let audio exceptions break UI cleanup
            pass

        # Clear UI connection references on nodes
        try:
            if start_node:
                start_node.connection = None
        except Exception:
            pass

        try:
            if end_node:
                end_node.connection = None
        except Exception:
            pass

        # Remove the path from its scene (if it still belongs to one)
        try:
            sc = self.scene()
            if sc is not None:
                sc.removeItem(self)
        except Exception:
            pass

        # Clear internal refs
        self.start_node = None
        self.end_node = None


class NodeCircle(QGraphicsEllipseItem):
    RADIUS = 10

    def __init__(self, parent_item, node_type="output"):
        super().__init__(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS, parent_item)
        self.node_type = node_type  # "input" or "output"
        self.connection: ConnectionPath | None = None

        # UI parent and backend module references
        self.module_item = parent_item
        self.audio_module = getattr(parent_item, "module", None)

        color = QColor(150, 80, 200) if node_type == "output" else QColor(80, 150, 200)
        self.setBrush(QBrush(color))

        # Important flags for interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptTouchEvents(True)

        # Temporary connection (when dragging) is stored here
        self.temp_connection: ConnectionPath | None = None

    # Clicking a node severs an existing connection (if any) and starts a new drag for output nodes.
    def mousePressEvent(self, event):
        # If there is an existing connection, tear it down first (safe & idempotent)
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                # swallow errors; disconnect() is defensive already
                pass
            self.connection = None

        # If the user presses an output node, start a new temporary connection
        if self.node_type == "output":
            # Create temp connection and add it to scene — ConnectionPath adds itself to scene when scene passed
            try:
                # Some callers may not have a scene yet (defensive)
                sc = self.scene()
                self.temp_connection = ConnectionPath(self, scene=sc)
            except Exception:
                self.temp_connection = None

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.temp_connection:
            # Convert mouse position to scene coordinates, update temporary curve
            try:
                scene_pos = self.mapToScene(event.pos())
                self.temp_connection.update_path_from_pos(scene_pos)
            except Exception:
                pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # When releasing an output drag, finalize connection if over an input node
        if self.temp_connection:
            try:
                scene_pos = self.mapToScene(event.pos())
                items = self.scene().items(scene_pos) if self.scene() is not None else []
                # find an input NodeCircle under the mouse
                target_input = next((it for it in items if isinstance(it, NodeCircle) and it.node_type == "input"), None)

                if target_input:
                    # connect backend nodes if possible
                    if self.audio_module and target_input.audio_module:
                        out = getattr(self.audio_module, "output_node", None)
                        inp = getattr(target_input.audio_module, "input_node", None)
                        if out and inp:
                            try:
                                out.connect(inp)
                            except Exception:
                                # swallow backend connect exceptions; still attempt UI hookup
                                pass

                    # Finalize UI connection
                    self.temp_connection.end_node = target_input
                    # set both node references
                    self.connection = self.temp_connection
                    try:
                        target_input.connection = self.temp_connection
                    except Exception:
                        pass
                    # finalize path geometry
                    self.temp_connection.update_path()
                else:
                    # Not dropped on an input — remove the temporary path cleanly.
                    try:
                        # disconnect() will remove the path from the scene and clean internal refs
                        self.temp_connection.disconnect()
                    except Exception:
                        # as fallback try removing from scene
                        sc = self.scene()
                        if sc and self.temp_connection and sc.items and self.temp_connection in sc.items():
                            try:
                                sc.removeItem(self.temp_connection)
                            except Exception:
                                pass

                # clear the temporary handle
                self.temp_connection = None
            except Exception:
                # be defensive: ensure temp_connection cleared
                try:
                    self.temp_connection = None
                except Exception:
                    pass

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


class CloseButton(QGraphicsSimpleTextItem):
    """Clickable 'X' to close and delete a module (visual only here)."""

    def __init__(self, parent_module_item):
        super().__init__("✕", parent_module_item)
        self.setBrush(QBrush(QColor(200, 200, 200)))
        self.setFont(QFont("Arial", 12))
        self.setZValue(10)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.parent_module_item = parent_module_item

        # Prevent the close button from dragging or selecting the module item when clicked
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event):
        # Ask the parent to cleanup and remove itself. The parent does scene removal.
        try:
            if self.parent_module_item:
                self.parent_module_item.cleanup()
        except Exception:
            pass
        super().mousePressEvent(event)


class ModuleItem(QGraphicsRectItem):
    """A graphics item representing an audio module with dynamic UI and close button."""

    DEFAULT_WIDTH = 180
    DEFAULT_HEIGHT = 100

    def __init__(self, module: AudioModule, width_override: int = None, height_override: int = None):
        super().__init__(0, 0, self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.module = module
        self.width_override = width_override
        self.height_override = height_override

        # Visuals / interaction flags
        self.setBrush(QBrush(QColor(40, 40, 40)))
        self.setPen(QPen(QColor(120, 120, 120)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        # Title label
        self.label = QGraphicsTextItem(module.__class__.__name__, self)
        self.label.setDefaultTextColor(QColor(255, 255, 255))
        self.label.setPos(10, 5)

        # Close button
        self.close_button = CloseButton(self)
        # nodes will be created conditionally
        self.input_node = NodeCircle(self, "input") if getattr(module, "input_node", None) else None
        if self.input_node:
            self.input_node.setZValue(2)
        self.output_node = NodeCircle(self, "output") if getattr(module, "output_node", None) else None
        if self.output_node:
            self.output_node.setZValue(2)

        # Embed module UI (if provided) and compute sizing
        self._proxy_widget = None
        self.get_ui()

    def get_ui(self):
        """Embed the module's custom QWidget UI and dynamically resize ModuleItem."""
        # Remove existing proxy if any (rebuild)
        if self._proxy_widget:
            try:
                sc = self.scene()
                if sc:
                    sc.removeItem(self._proxy_widget)
            except Exception:
                pass
            self._proxy_widget = None

        if not hasattr(self.module, "get_ui"):
            # still set rect to defaults and pos nodes
            self.setRect(0, 0, self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            if self.input_node:
                self.input_node.setPos(0, self.DEFAULT_HEIGHT / 2)
            if self.output_node:
                self.output_node.setPos(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT / 2)
            self.close_button.setPos(self.DEFAULT_WIDTH - 20, 2)
            return

        try:
            ui_widget = self.module.get_ui()
        except Exception:
            ui_widget = None

        if ui_widget is None:
            # same as above: set defaults
            self.setRect(0, 0, self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            if self.input_node:
                self.input_node.setPos(0, self.DEFAULT_HEIGHT / 2)
            if self.output_node:
                self.output_node.setPos(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT / 2)
            self.close_button.setPos(self.DEFAULT_WIDTH - 20, 2)
            return

        # Ensure widget layout / sizeHint is computed
        try:
            ui_widget.adjustSize()
        except Exception:
            pass

        # Create proxy and embed
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(ui_widget)
        proxy.setZValue(2)
        # position below title
        label_height = self.label.boundingRect().height()
        padding = 10
        proxy.setPos(10, label_height + padding)

        # Use proxy bounding rect for actual size
        proxy_rect = proxy.boundingRect()
        new_width = max(self.DEFAULT_WIDTH, proxy_rect.width() + 20)
        new_height = max(self.DEFAULT_HEIGHT, proxy_rect.height() + label_height + 20)

        if self.width_override:
            new_width = max(new_width, self.width_override)
        if self.height_override:
            new_height = max(new_height, self.height_override)

        # Apply new rect and reposition nodes + close button
        self.setRect(0, 0, new_width, new_height)

        if self.input_node:
            self.input_node.setPos(0, new_height / 2)
        if self.output_node:
            self.output_node.setPos(new_width, new_height / 2)

        self.close_button.setPos(new_width - 20, 2)
        self._proxy_widget = proxy

    def cleanup(self):
        """
        Safe cleanup invoked by the close button or programmatic removal.
        Steps:
         - disconnect any UI connections
         - call backend destroy/close if present
         - remove this item from the scene (deferred briefly to allow Qt to finish mouse events)
        """
        # 1) disconnect UI connections
        for node in (self.input_node, self.output_node):
            if node and node.connection:
                try:
                    node.connection.disconnect()
                except Exception:
                    pass
                node.connection = None
            # also clear temp_connection if any
            if node and getattr(node, "temp_connection", None):
                try:
                    node.temp_connection.disconnect()
                except Exception:
                    pass
                node.temp_connection = None

        # 2) backend cleanup if module supports it
        try:
            if hasattr(self.module, "destroy"):
                self.module.destroy()
            elif hasattr(self.module, "close"):
                self.module.close()
        except Exception:
            pass

        # 3) remove from scene in a safe, deferred way to avoid mouse-grab race conditions
        sc = self.scene()
        if sc:
            # remove proxy widget first if present
            try:
                if self._proxy_widget and sc:
                    sc.removeItem(self._proxy_widget)
            except Exception:
                pass

            # schedule the rect item removal on the event loop after a short delay
            def _remove_item():
                try:
                    if self.scene():
                        self.scene().removeItem(self)
                except Exception:
                    pass

            QTimer.singleShot(1, _remove_item)

        # 4) break references to help GC
        self.module = None
        self.input_node = None
        self.output_node = None
        self._proxy_widget = None

    def itemChange(self, change, value):
        # Called when this item moves — update any connected paths
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for node in (self.input_node, self.output_node):
                if node and getattr(node, "connection", None):
                    try:
                        node.connection.update_path()
                    except Exception:
                        pass
        return super().itemChange(change, value)

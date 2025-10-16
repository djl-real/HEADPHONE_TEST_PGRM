# main_window.py
import sys
import time
import numpy as np
import sounddevice as sd
import json

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QPinchGesture, QFileDialog, QMessageBox
)
from PyQt6.QtGui import (
    QBrush, QColor, QWheelEvent, QPainter, QPen
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QEvent, QTimer
)

from audio_module import AudioModule
from toolbar_manager import ToolbarManager
from ui_elements import ModuleItem, NodeCircle, ConnectionPath


class WorkspaceScene(QGraphicsScene):
    """Custom scene with background grid only."""
    def __init__(self):
        super().__init__()
        # fallback background (drawBackground will paint over)
        self.setBackgroundBrush(QBrush(QColor(25, 25, 25)))

        # Grid settings (smaller spacing for more useful grid)
        self.grid_size = 25
        self.grid_color = QColor(50, 50, 50)
        self.grid_line_width = 1
        
        # Set an initial "infinite-ish" scene rect so scrolling works from the start
        self.setSceneRect(-100000, -100000, 200000, 200000)

    def drawBackground(self, painter, rect):
        # Fill background
        painter.fillRect(rect, QColor(25, 25, 25))

        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)

        pen = QPen(self.grid_color)
        pen.setWidth(self.grid_line_width)
        painter.setPen(pen)

        # Vertical lines
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += self.grid_size

        # Horizontal lines
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += self.grid_size


class WorkspaceView(QGraphicsView):
    """Custom QGraphicsView with zoom, pan, pinch gesture, inertia, and drag-box selection."""

    INERTIA_FPS = 60
    INERTIA_DECAY = 0.93
    INERTIA_MIN_VEL = 0.5

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.zoom_factor = 1.15

        # Mouse panning
        self.last_mouse_pos = None
        self.panning = False

        # Drag-selection
        self.drag_selecting = False
        self.drag_start_scene_pos = None
        self.selection_rect_item: QGraphicsRectItem | None = None

        # Touch support
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.setInteractive(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Touch scrolling state
        self.touch_last_pos: QPointF | None = None
        self._last_move_pos: QPointF | None = None
        self._last_move_time: float | None = None
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._inertia_timer: QTimer | None = None

    # ---------- Mouse ----------
    def wheelEvent(self, event: QWheelEvent):
        zoom = self.zoom_factor if event.angleDelta().y() > 0 else 1 / self.zoom_factor
        self.scale(zoom, zoom)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            clicked_items = self.scene().items(scene_pos)

            # If click is on empty space, start drag-selection
            if not any(it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable for it in clicked_items):
                self.drag_selecting = True
                self.drag_start_scene_pos = scene_pos

                # Create or reset rectangle
                if not self.selection_rect_item:
                    pen = QPen(QColor(100, 180, 255, 180))
                    pen.setWidth(1)
                    brush = QColor(100, 180, 255, 50)
                    self.selection_rect_item = QGraphicsRectItem()
                    self.selection_rect_item.setPen(pen)
                    self.selection_rect_item.setBrush(brush)
                    self.selection_rect_item.setZValue(10000)
                    self.scene().addItem(self.selection_rect_item)
                self.selection_rect_item.setRect(QRectF(scene_pos, scene_pos))
                self.selection_rect_item.show()
                event.accept()
                return
            else:
                # Clicked on a module: default behavior
                super().mousePressEvent(event)

        elif event.button() == Qt.MouseButton.MiddleButton or (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.panning = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_selecting and self.drag_start_scene_pos:
            scene_pos = self.mapToScene(event.pos())
            rect = self._make_rect(self.drag_start_scene_pos, scene_pos)
            self.selection_rect_item.setRect(rect)

            # Update which items are selected
            for item in self.scene().items():
                if isinstance(item, ModuleItem):
                    item_rect = item.sceneBoundingRect()
                    item.setSelected(rect.intersects(item_rect))
            event.accept()
            return

        elif self.panning and self.last_mouse_pos:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_selecting:
            self.drag_selecting = False
            if self.selection_rect_item:
                self.selection_rect_item.hide()
            self.drag_start_scene_pos = None
            event.accept()
            return

        elif self.panning:
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _make_rect(self, p1: QPointF, p2: QPointF) -> QRectF:
        return QRectF(
            min(p1.x(), p2.x()),
            min(p1.y(), p2.y()),
            abs(p2.x() - p1.x()),
            abs(p2.y() - p1.y()),
        )

    # ---------- Touch ----------
    def viewportEvent(self, event):
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            return self.handleTouchEvent(event)
        return super().viewportEvent(event)

    def handleTouchEvent(self, event):
        touch_points = event.points()
        if not touch_points:
            return super().event(event)

        tp = touch_points[0]
        pos = tp.position()
        scene_pos = self.mapToScene(pos.toPoint())

        items = self.scene().items(scene_pos) if self.scene() else []
        movable = any(
            isinstance(it, ModuleItem)
            or it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            for it in items
        )
        over_node = any(it.__class__.__name__ == "NodeCircle" for it in items)
        block_pan = movable or over_node

        if event.type() == QEvent.Type.TouchBegin:
            if not block_pan:
                self.touch_last_pos = pos
                self._last_move_pos = QPointF(pos)
                self._last_move_time = time.time()
                self._stop_inertia()
            event.accept()
            return True

        elif event.type() == QEvent.Type.TouchUpdate:
            if not block_pan and self.touch_last_pos is not None:
                delta = pos - self.touch_last_pos
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() - int(delta.x())
                )
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - int(delta.y())
                )

                now = time.time()
                dt = max(1e-6, now - (self._last_move_time or now))
                vx = (pos.x() - (self._last_move_pos.x() if self._last_move_pos else pos.x())) / dt
                vy = (pos.y() - (self._last_move_pos.y() if self._last_move_pos else pos.y())) / dt
                self._vel_x = (self._vel_x * 0.7) + (vx * 0.3)
                self._vel_y = (self._vel_y * 0.7) + (vy * 0.3)
                self._last_move_pos = QPointF(pos)
                self._last_move_time = now
                self.touch_last_pos = pos

                event.accept()
                return True

        elif event.type() == QEvent.Type.TouchEnd:
            if not block_pan:
                if abs(self._vel_x) > 50 or abs(self._vel_y) > 50:
                    self._start_inertia()
                self.touch_last_pos = None
                event.accept()
                return True

        return super().event(event)

    # ---------- Gesture ----------
    def event(self, event):
        if event.type() == QEvent.Type.Gesture:
            return self.gestureEvent(event)
        return super().event(event)

    def gestureEvent(self, event):
        pinch = event.gesture(Qt.GestureType.PinchGesture)
        if pinch and isinstance(pinch, QPinchGesture):
            center_pt = pinch.centerPoint()
            if center_pt is None:
                return False

            # Keep zoom centered on pinch midpoint
            scene_center_before = self.mapToScene(center_pt.toPoint())
            if pinch.changeFlags() & QPinchGesture.ChangeFlag.ScaleFactorChanged:
                scale_factor = pinch.scaleFactor()
                if scale_factor > 0:
                    self.scale(scale_factor, scale_factor)
            scene_center_after = self.mapToScene(center_pt.toPoint())
            delta_scene = scene_center_after - scene_center_before
            self.translate(delta_scene.x(), delta_scene.y())

            event.accept()
            return True

        return False

    # ---------- Inertia ----------
    def _start_inertia(self):
        self._stop_inertia()
        self._inertia_timer = QTimer(self)
        self._inertia_timer.setInterval(int(1000 / self.INERTIA_FPS))
        self._inertia_timer.timeout.connect(self._inertia_step)
        self._inertia_timer.start()

    def _stop_inertia(self):
        if self._inertia_timer:
            try:
                self._inertia_timer.stop()
                self._inertia_timer.deleteLater()
            except Exception:
                pass
            self._inertia_timer = None
        self._vel_x = 0.0
        self._vel_y = 0.0

    def _inertia_step(self):
        dt = 1.0 / max(1, self.INERTIA_FPS)
        dx = self._vel_x * dt
        dy = self._vel_y * dt
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(dx))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(dy))
        self._vel_x *= self.INERTIA_DECAY
        self._vel_y *= self.INERTIA_DECAY
        if abs(self._vel_x) < self.INERTIA_MIN_VEL and abs(self._vel_y) < self.INERTIA_MIN_VEL:
            self._stop_inertia()



class MainWindow(QMainWindow):
    """Main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HEADPHONE_TEST_PGRM")
        self.resize(1200, 800)

        # Workspace
        self.scene = WorkspaceScene()
        self.view = WorkspaceView(self.scene)
        self.setCentralWidget(self.view)

        # Audio backend
        self.sample_rate = 44100
        self.block_size = 512
        self.modules: list[AudioModule] = []
        self.endpoints: list[AudioModule] = []

        # Toolbar manager
        self.toolbar_manager = ToolbarManager(self)

        # Start audio output
        self.stream = sd.OutputStream(
            channels=2,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            callback=self.audio_callback,
            dtype="float32"
        )
        self.stream.start()

    def audio_callback(self, outdata, frames, time, status):
        if not self.endpoints:
            outdata.fill(0)
            return

        mix = np.zeros((frames, 2), dtype=np.float32)
        for endpoint in self.endpoints:
            audio = endpoint.generate(frames)
            if audio is not None:
                mix += audio
        outdata[:] = np.clip(mix, -1.0, 1.0)
    
    def save_layout(self, path: str):
        """Save all modules, nodes, and connections to a .layout JSON file."""
        if not path:
            return

        layout_data = {"version": 2, "modules": [], "connections": []}

        # Collect modules
        for item in self.scene.items():
            if isinstance(item, ModuleItem):
                module = item.module
                pos = item.pos()
                module_info = {
                    "id": item.module_id,  # 🔧 unique ID
                    "type": module.__class__.__name__,
                    "pos": [pos.x(), pos.y()],
                }
                if hasattr(module, "serialize"):
                    module_info["state"] = module.serialize()
                layout_data["modules"].append(module_info)

        # Collect connections
        for item in self.scene.items():
            if isinstance(item, ConnectionPath):
                src_node = getattr(item, "start_node", None)
                dst_node = getattr(item, "end_node", None)
                if src_node and dst_node:
                    src_item = src_node.module_item
                    dst_item = dst_node.module_item
                    if not src_item or not dst_item:
                        continue
                    layout_data["connections"].append({
                        "from": {
                            "module_id": src_item.module_id,
                            "node_index": getattr(src_node, "index", 0),
                            "type": "output"
                        },
                        "to": {
                            "module_id": dst_item.module_id,
                            "node_index": getattr(dst_node, "index", 0),
                            "type": "input"
                        },
                    })

        # Write to file
        try:
            with open(path, "w") as f:
                json.dump(layout_data, f, indent=4)
            QMessageBox.information(self, "Layout Saved", f"Layout saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Layout", str(e))

    def load_layout(self, path: str):
        """Load modules, positions, and connections from a .layout JSON file."""
        if not path:
            return

        try:
            with open(path, "r") as f:
                layout_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Layout", str(e))
            return

        # Clear scene
        self.scene.clear()
        self.modules.clear()
        self.endpoints.clear()

        module_map = {}  # 🔧 module_id → ModuleItem

        # Recreate modules
        for mod_info in layout_data.get("modules", []):
            mod_type = mod_info.get("type")
            module_id = mod_info.get("id")
            pos_x, pos_y = mod_info.get("pos", [0, 0])

            # Find matching class
            cls = None
            for folder_modules in self.toolbar_manager.module_folders.values():
                for name, c in folder_modules:
                    if name == mod_type:
                        cls = c
                        break
                if cls:
                    break

            if not cls:
                print(f"Skipping unknown module: {mod_type}")
                continue

            module = cls()
            if hasattr(module, "deserialize"):
                module.deserialize(mod_info.get("state", {}))

            if "Endpoint" in mod_type:
                self.endpoints.append(module)
            else:
                self.modules.append(module)

            item = ModuleItem(module)
            item.module_id = module_id  # 🔧 restore same ID
            item.setPos(QPointF(pos_x, pos_y))
            self.scene.addItem(item)
            module_map[module_id] = item

        # Recreate connections (UI + backend)
        for conn in layout_data.get("connections", []):
            src_id = conn["from"]["module_id"]
            dst_id = conn["to"]["module_id"]
            src_idx = conn["from"]["node_index"]
            dst_idx = conn["to"]["node_index"]

            src_item = module_map.get(src_id)
            dst_item = module_map.get(dst_id)
            if not src_item or not dst_item:
                continue

            src_node = src_item.output_nodes[src_idx] if src_idx < len(src_item.output_nodes) else None
            dst_node = dst_item.input_nodes[dst_idx] if dst_idx < len(dst_item.input_nodes) else None
            if not src_node or not dst_node:
                continue

            # Connect backend nodes first
            if src_node.node_obj and dst_node.node_obj:
                try:
                    src_node.node_obj.connect(dst_node.node_obj)
                except Exception:
                    pass

            # Create UI connection
            conn_path = ConnectionPath(src_node, dst_node, scene=self.scene)
            src_node.connection = conn_path
            dst_node.connection = conn_path
            self.scene.addItem(conn_path)

        QMessageBox.information(self, "Layout Loaded", f"Layout loaded from:\n{path}")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

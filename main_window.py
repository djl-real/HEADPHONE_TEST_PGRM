# main_window.py
import sys
import os, psutil
import time
import numpy as np
import sounddevice as sd
import json
import threading
import uuid

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QMenu,
    QGraphicsItem, QGraphicsRectItem, QPinchGesture, QFileDialog, QMessageBox, QWidget, QVBoxLayout
)
from PyQt6.QtGui import (
    QBrush, QColor, QWheelEvent, QPainter, QPen, QAction
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QEvent, QTimer
)

from audio_module import AudioModule
from toolbar_manager import ToolbarManager
from ui_elements import ModuleItem, NodeCircle, ConnectionPath
from modules.endpoint import Endpoint
from mixer import Mixer

def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)

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
        # Reduce painting overhead: disable antialiasing, draw only visible lines.
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(rect, QColor(25, 25, 25))

        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)

        pen = QPen(self.grid_color)
        pen.setWidth(self.grid_line_width)
        painter.setPen(pen)

        # Vertical lines (draw only across rect)
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += self.grid_size

        # Horizontal lines
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += self.grid_size
        painter.restore()

class WorkspaceView(QGraphicsView):
    """Custom QGraphicsView with zoom, pan, pinch gesture, inertia, and drag-box selection (touch + mouse)."""

    INERTIA_FPS = 60
    INERTIA_DECAY = 0.93
    INERTIA_MIN_VEL = 0.5

    def __init__(self, scene, main_window=None):
        super().__init__(scene)
        self.main_window = main_window
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
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
        self._last_touch_items_check_time = 0.0
        self._last_touch_items_result = []

        # --- Touch mode state machine ---
        self.touch_mode = "IDLE"  # IDLE, PANNING, DRAG_HOLD_PENDING, DRAG_SELECTING, MULTITOUCH
        self._touch_start_pos: QPointF | None = None
        self.long_press_timer = QTimer()
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._activate_drag_select)
        self._touch_move_threshold = 20

    # ---------- Mouse ----------
    def wheelEvent(self, event: QWheelEvent):
        zoom = self.zoom_factor if event.angleDelta().y() > 0 else 1 / self.zoom_factor
        self.scale(zoom, zoom)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            clicked_items = self.scene().items(scene_pos)

            # If click is on empty space (no module/node), start drag-selection
            if not any(isinstance(it, (ModuleItem, NodeCircle)) for it in clicked_items):
                self.drag_selecting = True
                self.drag_start_scene_pos = scene_pos
                self._create_selection_rect(scene_pos)
                event.accept()
                return
            else:
                # let the item (module/node) handle the event
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
            self._update_selection_rect(self.mapToScene(event.pos()))
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
            self._end_drag_select()
            event.accept()
            return
        elif self.panning:
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Right-click context menu for saving, copying, and pasting modules."""
        menu = QMenu(self)

        # Determine selected modules
        selected_items = [
            item for item in self.scene().selectedItems()
            if isinstance(item, ModuleItem)
        ]

        scene_pos = self.mapToScene(event.pos())

        if selected_items:
            # Selection-dependent options
            save_action = QAction("Save Selected as Layout…", self)
            copy_action = QAction("Copy Selected", self)
            menu.addAction(save_action)
            menu.addAction(copy_action)

            save_action.triggered.connect(
                lambda: self.main_window.save_selection_as_layout(selected_items)
            )
            copy_action.triggered.connect(
                lambda: self.main_window.copy_selection(selected_items)
            )

        else:
            # No selection → Paste available
            paste_action = QAction("Paste", self)
            menu.addAction(paste_action)

            paste_action.triggered.connect(
                lambda: self.main_window.paste_at(scene_pos)
            )

        menu.exec(event.globalPos())

    # ---------- Touch ----------
    def viewportEvent(self, event):
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            return self.handleTouchEvent(event)
        return super().viewportEvent(event)

    def handleTouchEvent(self, event):
        touch_points = event.points()
        if not touch_points:
            return super().event(event)

        # If multiple fingers, cancel long-press and let gesture handling / items manage it
        if len(touch_points) > 1:
            self.long_press_timer.stop()
            if self.drag_selecting:
                self._end_drag_select()
            self.touch_mode = "MULTITOUCH"
            return super().event(event)

        tp = touch_points[0]
        pos = tp.position()
        scene_pos = self.mapToScene(pos.toPoint())

        # --- IMPORTANT: do not steal touches that start on modules or nodes ---
        # This preserves module dragging and node connection behavior.
        # Throttle the expensive scene().items() checks to ~20Hz
        now = time.time()
        if now - self._last_touch_items_check_time > 0.05:
            try:
                self._last_touch_items_result = self.scene().items(scene_pos) if self.scene() else []
            except Exception:
                self._last_touch_items_result = []
            self._last_touch_items_check_time = now

        if any(isinstance(it, (ModuleItem, NodeCircle)) for it in self._last_touch_items_result):
            # Return to default handling so the QGraphicsItem receives events
            return super().event(event)

        # Single-finger behavior on empty workspace:
        if event.type() == QEvent.Type.TouchBegin:
            self._stop_inertia()
            self._touch_start_pos = pos
            self.touch_last_pos = pos
            self.touch_mode = "DRAG_HOLD_PENDING"
            self.long_press_timer.start(1000)  # 1s hold for drag-select
            event.accept()
            return True

        elif event.type() == QEvent.Type.TouchUpdate:
            if self.touch_mode == "DRAG_HOLD_PENDING":
                # If user moves too far, switch to panning and cancel long-press
                 if self._touch_start_pos is not None and (pos - self._touch_start_pos).manhattanLength() > self._touch_move_threshold:
                    self.long_press_timer.stop()
                    self.touch_mode = "PANNING"
                    event.accept()
                    return True

            elif self.touch_mode == "PANNING":
                delta = pos - self.touch_last_pos
                self._scroll_by_delta(delta)
                self._update_velocity(pos)
                self.touch_last_pos = pos
                event.accept()
                return True

            elif self.touch_mode == "DRAG_SELECTING" and self.drag_selecting:
                self._update_selection_rect(scene_pos)
                event.accept()
                return True

        elif event.type() == QEvent.Type.TouchEnd:
            self.long_press_timer.stop()
            if self.touch_mode == "DRAG_SELECTING":
                self._end_drag_select()
            elif self.touch_mode == "PANNING":
                if abs(self._vel_x) > 50 or abs(self._vel_y) > 50:
                    self._start_inertia()
            self.touch_mode = "IDLE"
            event.accept()
            return True

        return super().event(event)

    # ---------- Drag Selection Helpers ----------
    def _activate_drag_select(self):
        """Called after the long-press timer fires to begin drag selection."""
        if self.touch_mode != "DRAG_HOLD_PENDING":
            return
        if not self._touch_start_pos:
            return
        scene_pos = self.mapToScene(self._touch_start_pos.toPoint())
        self.drag_selecting = True
        self.drag_start_scene_pos = scene_pos
        self._create_selection_rect(scene_pos)
        self.touch_mode = "DRAG_SELECTING"

    def _create_selection_rect(self, scene_pos):
        # Defensive: ensure previous rect is still valid; if not, clear reference
        if self.selection_rect_item is not None:
            try:
                # calling scene() will raise if C++ object was deleted
                _ = self.selection_rect_item.scene()
            except Exception:
                self.selection_rect_item = None

        # Create a new rect if necessary
        if not self.selection_rect_item:
            pen = QPen(QColor(100, 180, 255, 180))
            pen.setWidth(1)
            brush = QColor(100, 180, 255, 50)
            rect = QGraphicsRectItem()
            rect.setPen(pen)
            rect.setBrush(brush)
            rect.setZValue(10000)
            self.selection_rect_item = rect
            try:
                if self.scene():
                    self.scene().addItem(self.selection_rect_item)
            except Exception:
                # If adding to the scene fails for any reason, clear reference
                self.selection_rect_item = None
                return

        # Now set rect safely
        try:
            self.selection_rect_item.setRect(QRectF(scene_pos, scene_pos))
            self.selection_rect_item.show()
        except Exception:
            # If the C++ object was destroyed between creation and setRect, clear it
            self.selection_rect_item = None

    def _update_selection_rect(self, scene_pos):
        if not self.selection_rect_item or not self.drag_start_scene_pos:
            return
        try:
            rect = self._make_rect(self.drag_start_scene_pos, scene_pos)
            self.selection_rect_item.setRect(rect)
            # Update module selection
            for item in self.scene().items():
                if isinstance(item, ModuleItem):
                    item_rect = item.sceneBoundingRect()
                    item.setSelected(rect.intersects(item_rect))
        except Exception:
            # If the rect was deleted unexpectedly, clear state
            self.selection_rect_item = None
            self.drag_selecting = False
            self.drag_start_scene_pos = None

    def _end_drag_select(self):
        self.drag_selecting = False
        if self.selection_rect_item:
            try:
                if self.scene():
                    self.scene().removeItem(self.selection_rect_item)
            except Exception:
                pass
            self.selection_rect_item = None
        self.drag_start_scene_pos = None

    def _make_rect(self, p1: QPointF, p2: QPointF) -> QRectF:
        return QRectF(
            min(p1.x(), p2.x()),
            min(p1.y(), p2.y()),
            abs(p2.x() - p1.x()),
            abs(p2.y() - p1.y()),
        )

    # If the view's scene is replaced, ensure selection rect is removed to avoid stale C++ pointers.
    def setScene(self, scene):
        if self.selection_rect_item:
            try:
                if self.scene():
                    self.scene().removeItem(self.selection_rect_item)
            except Exception:
                pass
            self.selection_rect_item = None
        super().setScene(scene)

    # ---------- Scroll / Inertia ----------
    def _scroll_by_delta(self, delta):
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(delta.x())
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(delta.y())
        )

    def _update_velocity(self, pos):
        now = time.time()
        dt = max(1e-6, now - (self._last_move_time or now))
        vx = (pos.x() - (self._last_move_pos.x() if self._last_move_pos else pos.x())) / dt
        vy = (pos.y() - (self._last_move_pos.y() if self._last_move_pos else pos.y())) / dt
        self._vel_x = (self._vel_x * 0.7) + (vx * 0.3)
        self._vel_y = (self._vel_y * 0.7) + (vy * 0.3)
        self._last_move_pos = QPointF(pos)
        self._last_move_time = now

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
        try:
            self._scroll_by_delta(QPointF(dx, dy))
        except Exception:
            pass
        self._vel_x *= self.INERTIA_DECAY
        self._vel_y *= self.INERTIA_DECAY
        if abs(self._vel_x) < self.INERTIA_MIN_VEL and abs(self._vel_y) < self.INERTIA_MIN_VEL:
            self._stop_inertia()

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


class MainWindow(QMainWindow):
    """Main application window with threaded real-time audio generation using a ring buffer."""
    def __init__(self):
        super().__init__()

        # --- Cross-platform process priority ---
        try:
            p = psutil.Process(os.getpid())

            if psutil.WIN32:
                # Windows: HIGH_PRIORITY_CLASS
                p.nice(psutil.HIGH_PRIORITY_CLASS)

            else:
                # Linux / macOS: negative nice value = higher priority
                # Requires root for values < -10, so we clamp safely.
                try:
                    os.nice(-10)   # attempt to raise priority
                except PermissionError:
                    # If running unprivileged, use the highest allowed
                    current_nice = os.nice(0)
                    if current_nice > 0:
                        os.nice(-current_nice)

        except Exception:
            # Priority tweaks are optional — never fail on this.
            pass


        self.setWindowTitle("HEADPHONE_TEST_PGRM")
        self.resize(1200, 800)
        self.copied_layout = None

        # Workspace
        self.scene = WorkspaceScene()
        self.view = WorkspaceView(self.scene, self)

        self.container = QWidget()
        self.setCentralWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(self.view)

        # Audio backend
        self.sample_rate = 44100
        self.block_size = 2048
        self.modules: list[AudioModule] = []
        self.endpoints: list[AudioModule] = []

        # Toolbar manager
        self.toolbar_manager = ToolbarManager(self)

        # Mixer (overlay)
        self.mixer = Mixer(self)
        self.mixer.setParent(self.container)
        self.mixer.raise_()

        # Whenever mixer collapses/expands, reposition it
        if hasattr(self.mixer, "toggled"):
            self.mixer.toggled.connect(self._reposition_mixer)


        # --- Ring buffer configuration ---
        self.ring_size = 4  # Number of blocks ahead to prefill
        self.ring_buffer = np.zeros((self.ring_size, self.block_size, 2), dtype=np.float32)
        self.write_index = 0  # Worker writes here
        self.read_index = 0   # Callback reads here
        self.available_blocks = 0
        self._buffer_lock = threading.Lock()

        # Stop signal for worker
        self._stop_event = threading.Event()

        # --- Background worker thread ---
        self._worker_thread = threading.Thread(target=self._audio_worker_loop, daemon=True)
        self._worker_thread.start()

        # --- Start audio output ---
        self.stream = sd.OutputStream(
            channels=2,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            callback=self.audio_callback,
            dtype="float32",
        )
        self.stream.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_mixer()

    def _reposition_mixer(self):
        """Keep mixer pinned to bottom as an overlay."""
        if not self.mixer:
            return

        cw = self.container.width()
        ch = self.container.height()
        mh = self.mixer.height()

        self.mixer.setGeometry(
            0,
            ch - mh,
            cw,
            mh
        )

    # ---------- Worker Thread ----------
    def _audio_worker_loop(self):
        """Continuously fill the ring buffer with precomputed audio blocks."""
        while not self._stop_event.is_set():
            # Only fill if there's space
            if self.available_blocks < self.ring_size:
                block = self._generate_mix_block(self.block_size)
                # Copy into ring buffer
                with self._buffer_lock:
                    np.copyto(self.ring_buffer[self.write_index], block)
                    self.write_index = (self.write_index + 1) % self.ring_size
                    self.available_blocks = min(self.available_blocks + 1, self.ring_size)
            else:
                # Ring buffer full, yield CPU
                threading.Event().wait(0.0005)

    # ---------- Mixing ----------
    def _generate_mix_block(self, frames: int) -> np.ndarray:
        """Generate a single block of mixed audio from endpoints."""
        if not self.endpoints:
            return np.zeros((frames, 2), dtype=np.float32)

        mix = np.zeros((frames, 2), dtype=np.float32)
        for endpoint in self.endpoints:
            try:
                audio = endpoint.generate(frames)
            except Exception:
                continue
            if audio is not None:
                n = min(audio.shape[0], frames)
                mix[:n] += audio[:n]

        np.clip(mix, -1.0, 1.0, out=mix)
        mix *= db_to_linear(self.mixer.master_volume_db)
        return mix

    # ---------- Audio Callback ----------
    def audio_callback(self, outdata, frames, time, status):
        """Real-time audio callback reads the next available block from the ring buffer."""
        try:
            with self._buffer_lock:
                if self.available_blocks > 0:
                    np.copyto(outdata, self.ring_buffer[self.read_index])
                    self.read_index = (self.read_index + 1) % self.ring_size
                    self.available_blocks -= 1
                else:
                    # Buffer underrun
                    outdata.fill(0)
        except Exception:
            outdata.fill(0)

    # ---------- Cleanup ----------
    def closeEvent(self, event):
        """Stop worker and audio stream."""
        self._stop_event.set()
        if hasattr(self, "stream") and self.stream:
            self.stream.stop()
            self.stream.close()
        super().closeEvent(event)

    def spawn_module(self, module: AudioModule):
        # Create visual representation
        item = ModuleItem(module, self)

        # Center spawn position based on current camera view
        view = self.view
        view_center = view.mapToScene(view.viewport().rect().center())

        item.setPos(QPointF(view_center.x() - 50, view_center.y() - 25))
        self.scene.addItem(item)

        # Register module
        if isinstance(module, Endpoint):
            self.endpoints.append(module)
            self.mixer.add_endpoint(module)
        else:
            self.modules.append(module)

    def destroy_module(self, module):
        if isinstance(module, Endpoint):
            self.mixer.remove_endpoint(module)
            if module in self.endpoints:
                self.endpoints.remove(module)
        else:
            if module in self.modules:
                self.modules.remove(module)
    
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
            # QMessageBox.information(self, "Layout Saved", f"Layout saved to:\n{path}")
        except Exception as e:
            # QMessageBox.critical(self, "Error Saving Layout", str(e))
            pass

    def load_layout(self, path: str):
        """Load modules, positions, and connections from a .layout JSON file."""
        if not path:
            return

        # --------------------------
        # Load JSON layout file
        # --------------------------
        try:
            with open(path, "r") as f:
                layout_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Layout", str(e))
            return

        # --------------------------
        # Clear existing scene
        # --------------------------
        
        self.scene.clear()
        self.modules.clear()
        self.endpoints.clear()
        self.mixer.scroll_layout.update()
        module_map = {}  # module_id → ModuleItem

        # --------------------------
        # Recreate modules
        # --------------------------
        for mod_info in layout_data.get("modules", []):
            mod_type = mod_info.get("type")
            module_id = mod_info.get("id")
            pos_x, pos_y = mod_info.get("pos", [0, 0])

            # Find class from toolbar registry
            cls = None
            for folder_modules in self.toolbar_manager.module_folders.values():
                for name, c in folder_modules:
                    if name == mod_type:
                        cls = c
                        break
                if cls:
                    break

            if not cls:
                print(f"Skipping unknown module type: {mod_type}")
                continue

            # Instantiate module backend
            module = cls()

            # Load module state
            if hasattr(module, "deserialize"):
                module.deserialize(mod_info.get("state", {}))

            # Use MainWindow's official spawner
            self.spawn_module(module)

            # Retrieve ModuleItem object from scene (it's the last added)
            item = None
            for it in self.scene.items():
                if isinstance(it, ModuleItem) and it.module is module:
                    item = it
                    break

            if not item:
                print("Error: ModuleItem was not created by spawn_module()!")
                continue

            # Set ID and position
            item.module_id = module_id
            item.setPos(QPointF(pos_x, pos_y))

            module_map[module_id] = item

        # --------------------------
        # Restore Connections
        # --------------------------
        for conn in layout_data.get("connections", []):
            src_id = conn["from"]["module_id"]
            dst_id = conn["to"]["module_id"]
            src_idx = conn["from"]["node_index"]
            dst_idx = conn["to"]["node_index"]

            src_item = module_map.get(src_id)
            dst_item = module_map.get(dst_id)
            if not src_item or not dst_item:
                continue

            # Get nodes
            try:
                src_node = src_item.output_nodes[src_idx]
                dst_node = dst_item.input_nodes[dst_idx]
            except Exception:
                continue

            if not src_node or not dst_node:
                continue

            # Backend connect
            if src_node.node_obj and dst_node.node_obj:
                try:
                    src_node.node_obj.connect(dst_node.node_obj)
                except Exception:
                    pass

            # UI connection
            conn_path = ConnectionPath(src_node, dst_node, scene=self.scene)
            src_node.connection = conn_path
            dst_node.connection = conn_path
            #self.scene.addItem(conn_path)

    def add_layout(self, path: str):
        """Add modules and connections from a .layout file WITHOUT clearing the existing scene."""

        view_center = self.view.mapToScene(self.view.viewport().rect().center())
        offset = QPointF(view_center.x() - 50, view_center.y() - 25)

        if not path:
            return

        # --------------------------
        # Load JSON
        # --------------------------
        try:
            with open(path, "r") as f:
                layout_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error Adding Layout", str(e))
            return

        module_map = {}       # new_id → ModuleItem
        id_remap = {}         # old_id → new_id   (important!)
        existing_ids = {item.module_id for item in self.scene.items()
                        if isinstance(item, ModuleItem)}

        # --------------------------
        # Create modules
        # --------------------------
        for mod_info in layout_data.get("modules", []):
            mod_type = mod_info.get("type")
            old_id = mod_info.get("id")
            pos_x, pos_y = mod_info.get("pos", [0, 0])

            # Find class
            cls = None
            for folder_modules in self.toolbar_manager.module_folders.values():
                for name, c in folder_modules:
                    if name == mod_type:
                        cls = c
                        break
                if cls:
                    break

            if not cls:
                print(f"Skipping unknown module type: {mod_type}")
                continue

            # Instantiate module backend
            module = cls()

            if hasattr(module, "deserialize"):
                module.deserialize(mod_info.get("state", {}))

            self.spawn_module(module)

            # Retrieve ModuleItem
            item = None
            for it in self.scene.items():
                if isinstance(it, ModuleItem) and it.module is module:
                    item = it
                    break

            if not item:
                print("Error: ModuleItem was not created by spawn_module()!")
                continue

            # Generate new ID if collision → REMEMBER THE MAPPING!
            new_id = old_id
            if new_id in existing_ids:
                new_id = str(uuid.uuid4())
            id_remap[old_id] = new_id

            item.module_id = new_id
            item.setPos(QPointF(pos_x, pos_y) + offset)

            module_map[new_id] = item

        # --------------------------
        # Create connections
        # --------------------------
        for conn in layout_data.get("connections", []):
            # remap IDs so repeated layouts still connect properly
            src_id = id_remap.get(conn["from"]["module_id"], conn["from"]["module_id"])
            dst_id = id_remap.get(conn["to"]["module_id"], conn["to"]["module_id"])
            src_idx = conn["from"]["node_index"]
            dst_idx = conn["to"]["node_index"]

            src_item = module_map.get(src_id)
            dst_item = module_map.get(dst_id)
            if not src_item or not dst_item:
                continue

            try:
                src_node = src_item.output_nodes[src_idx]
                dst_node = dst_item.input_nodes[dst_idx]
            except Exception:
                continue

            # Backend connection
            if src_node.node_obj and dst_node.node_obj:
                try:
                    src_node.node_obj.connect(dst_node.node_obj)
                except Exception:
                    pass

            # UI wire
            conn_path = ConnectionPath(src_node, dst_node, scene=self.scene)
            src_node.connection = conn_path
            dst_node.connection = conn_path



    def save_selection_as_layout(self, selected_items):
        """Save only the selected modules + internal connections to a layout file."""
        if not selected_items:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Selected Layout",
            "./layouts",
            "Layout Files (*.layout)"
        )
        if not path:
            return

        layout_data = {"version": 2, "modules": [], "connections": []}
        selected_ids = set(item.module_id for item in selected_items)

        # --------------------------
        # Collect module info
        # --------------------------
        for item in selected_items:
            module = item.module
            pos = item.pos()
            module_info = {
                "id": item.module_id,
                "type": module.__class__.__name__,
                "pos": [pos.x(), pos.y()],
            }
            if hasattr(module, "serialize"):
                module_info["state"] = module.serialize()
            layout_data["modules"].append(module_info)

        # --------------------------
        # Collect ONLY internal connections
        # --------------------------
        for obj in self.scene.items():
            if not isinstance(obj, ConnectionPath):
                continue

            src = getattr(obj, "start_node", None)
            dst = getattr(obj, "end_node", None)
            if not src or not dst:
                continue

            src_item = src.module_item
            dst_item = dst.module_item
            if not src_item or not dst_item:
                continue

            if src_item.module_id not in selected_ids:
                continue
            if dst_item.module_id not in selected_ids:
                continue

            layout_data["connections"].append({
                "from": {
                    "module_id": src_item.module_id,
                    "node_index": getattr(src, "index", 0),
                    "type": "output"
                },
                "to": {
                    "module_id": dst_item.module_id,
                    "node_index": getattr(dst, "index", 0),
                    "type": "input"
                },
            })

        # --------------------------
        # Write file
        # --------------------------
        try:
            with open(path, "w") as f:
                json.dump(layout_data, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Selection", str(e))

    def copy_selection(self, selected_items):
        """Copy selected modules + internal connections to an internal clipboard."""
        if not selected_items:
            return

        layout_data = {"version": 2, "modules": [], "connections": []}
        selected_ids = set(item.module_id for item in selected_items)

        # --------------------------
        # Module data
        # --------------------------
        for item in selected_items:
            module = item.module
            pos = item.pos()
            module_info = {
                "id": item.module_id,
                "type": module.__class__.__name__,
                "pos": [pos.x(), pos.y()],
            }
            if hasattr(module, "serialize"):
                module_info["state"] = module.serialize()
            layout_data["modules"].append(module_info)

        # --------------------------
        # Internal connections only
        # --------------------------
        for obj in self.scene.items():
            if not isinstance(obj, ConnectionPath):
                continue

            src = getattr(obj, "start_node", None)
            dst = getattr(obj, "end_node", None)
            if not src or not dst:
                continue

            src_item = src.module_item
            dst_item = dst.module_item
            if not src_item or not dst_item:
                continue

            if src_item.module_id not in selected_ids:
                continue
            if dst_item.module_id not in selected_ids:
                continue

            layout_data["connections"].append({
                "from": {
                    "module_id": src_item.module_id,
                    "node_index": getattr(src, "index", 0),
                    "type": "output"
                },
                "to": {
                    "module_id": dst_item.module_id,
                    "node_index": getattr(dst, "index", 0),
                    "type": "input"
                },
            })

        # --------------------------
        # Save internally
        # --------------------------
        self.copied_layout = layout_data

    def paste_at(self, scene_pos):
        """Paste copied modules at a given scene position."""
        if not self.copied_layout:
            return

        layout = self.copied_layout
        modules = layout["modules"]

        if not modules:
            return

        # --------------------------
        # Compute centroid of copied modules
        # --------------------------
        xs = [m["pos"][0] for m in modules]
        ys = [m["pos"][1] for m in modules]
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)

        paste_offset = scene_pos - QPointF(center_x, center_y)

        # Maps old module_id → new ModuleItem
        new_map = {}

        # --------------------------
        # Create modules
        # --------------------------
        for mod in modules:
            mod_type = mod["type"]
            old_id = mod["id"]

            # Find class in toolbar registry
            cls = None
            for folder_modules in self.toolbar_manager.module_folders.values():
                for name, c in folder_modules:
                    if name == mod_type:
                        cls = c
                        break
                if cls:
                    break
            if not cls:
                print(f"Skipping unknown module type: {mod_type}")
                continue

            module_backend = cls()

            if hasattr(module_backend, "deserialize"):
                module_backend.deserialize(mod.get("state", {}))

            # Spawn UI item with your standard method
            self.spawn_module(module_backend)

            # Retrieve ModuleItem created by spawn_module
            item = None
            for it in self.scene.items():
                if isinstance(it, ModuleItem) and it.module is module_backend:
                    item = it
                    break

            if not item:
                continue

            # Assign NEW unique ID
            item.module_id = str(uuid.uuid4())

            # Apply offset
            px, py = mod["pos"]
            item.setPos(QPointF(px, py) + paste_offset)

            new_map[old_id] = item

        # --------------------------
        # Connections
        # --------------------------
        for conn in layout.get("connections", []):
            src_old = conn["from"]["module_id"]
            dst_old = conn["to"]["module_id"]

            src_idx = conn["from"]["node_index"]
            dst_idx = conn["to"]["node_index"]

            src_item = new_map.get(src_old)
            dst_item = new_map.get(dst_old)
            if not src_item or not dst_item:
                continue

            try:
                src_node = src_item.output_nodes[src_idx]
                dst_node = dst_item.input_nodes[dst_idx]
            except Exception:
                continue

            # Backend connect() call
            try:
                if src_node.node_obj and dst_node.node_obj:
                    src_node.node_obj.connect(dst_node.node_obj)
            except Exception:
                pass

            # Create visual connection
            conn_path = ConnectionPath(src_node, dst_node, scene=self.scene)
            src_node.connection = conn_path
            dst_node.connection = conn_path





if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

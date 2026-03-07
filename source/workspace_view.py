import time

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsRectItem, QMenu, QPinchGesture
)
from PyQt6.QtGui import (
    QBrush, QColor, QPainter, QPen, QAction, QNativeGestureEvent, QCursor, QWheelEvent
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QEvent, QTimer
)

from source.ui_elements import ModuleItem, NodeCircle, ConnectionPath


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

        self._pan_accum_x = 0
        self._pan_accum_y = 0

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

        self._native_gesture_active = False

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
        # --- First try touchpad handling ---
        if self._handle_touchpad_wheel(event):
            return
        # --- Fallback: mouse wheel zoom ---
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
        # Throttle the expensive scene().items() checks to ~20Hz
        now = time.time()
        if now - self._last_touch_items_check_time > 0.05:
            try:
                self._last_touch_items_result = self.scene().items(scene_pos) if self.scene() else []
            except Exception:
                self._last_touch_items_result = []
            self._last_touch_items_check_time = now

        if any(isinstance(it, (ModuleItem, NodeCircle)) for it in self._last_touch_items_result):
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

    # ---------- Touchpad ----------

    def event(self, event):
        # --- Handle Native Gestures (Wayland/Linux + Windows Precision Touchpad + macOS) ---
        if isinstance(event, QNativeGestureEvent):
            g = event.gestureType()

            if g == Qt.NativeGestureType.Zoom:
                self._handle_native_pinch_zoom(event)
                return True

            elif g == Qt.NativeGestureType.Pan:
                self._handle_native_pinch_pan(event)
                return True

            elif g == Qt.NativeGestureType.BeginNativeGesture:
                self._native_gesture_active = True
                return True

            elif g == Qt.NativeGestureType.EndNativeGesture:
                self._native_gesture_active = False
                return True

        # --- Existing QPinchGesture path (fallback for macOS apps / X11) ---
        if event.type() == QEvent.Type.Gesture:
            return self.gestureEvent(event)

        return super().event(event)

    def _handle_native_pinch_zoom(self, e: QNativeGestureEvent):
        delta = e.value()
        zoom = 1.0 + delta

        if zoom <= 0:
            return

        global_pos = QCursor.pos()
        view_pos = self.mapFromGlobal(global_pos)
        old_scene_pos = self.mapToScene(view_pos)

        self.scale(zoom, zoom)

        new_scene_pos = self.mapToScene(view_pos)
        delta_scene = new_scene_pos - old_scene_pos
        self.translate(delta_scene.x(), delta_scene.y())

    def _handle_native_pinch_pan(self, e: QNativeGestureEvent):
        dx = e.delta().x()
        dy = e.delta().y()

        SCROLL = 1.0
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(dx * SCROLL)
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(dy * SCROLL)
        )

    def _handle_touchpad_wheel(self, event: QWheelEvent) -> bool:
        SCROLL_SCALE = 2

        pixel = event.pixelDelta()
        angle = event.angleDelta()

        # --- Reliable detection of real mouse wheel ---
        is_real_mouse_wheel = (
            abs(angle.y()) >= 120 and pixel.isNull()
        )
        if is_real_mouse_wheel:
            return False

        # --- Detect pinch zoom (libinput & macOS) ---
        is_pinch_zoom = (
            not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            and not pixel.isNull()
            and abs(pixel.y()) >= 1
            and abs(pixel.x()) >= 1
            and abs(angle.y()) < 40
        )

        if is_pinch_zoom:
            dy = pixel.y() / 60.0
            zoom = 1 + dy * 0.15

            if zoom > 0:
                old = self.mapToScene(event.position().toPoint())
                self.scale(zoom, zoom)
                new = self.mapToScene(event.position().toPoint())
                delta = new - old
                self.translate(delta.x(), delta.y())

            event.accept()
            return True

        # --- Ctrl+wheel zoom ---
        is_ctrl_zoom = (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            or abs(pixel.y()) > 40
        )

        if is_ctrl_zoom:
            dy = pixel.y() / 120.0
            zoom = 1 + dy * 0.1
            if zoom > 0:
                old = self.mapToScene(event.position().toPoint())
                self.scale(zoom, zoom)
                new = self.mapToScene(event.position().toPoint())
                delta = new - old
                self.translate(delta.x(), delta.y())
            event.accept()
            return True

        # --- Touchpad panning ---
        dx = pixel.x()
        dy = pixel.y()

        self._pan_accum_x += dx
        self._pan_accum_y += dy

        sx = int(self._pan_accum_x)
        sy = int(self._pan_accum_y)

        self._pan_accum_x -= sx
        self._pan_accum_y -= sy

        if sx != 0 or sy != 0:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - (sx * SCROLL_SCALE)
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - (sy * SCROLL_SCALE)
            )

        event.accept()
        return True

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
                self.selection_rect_item = None
                return

        # Now set rect safely
        try:
            self.selection_rect_item.setRect(QRectF(scene_pos, scene_pos))
            self.selection_rect_item.show()
        except Exception:
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
# main_window.py
import sys
import time
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QPinchGesture, QGraphicsItem
)
from PyQt6.QtGui import (
    QBrush, QColor, QWheelEvent, QPainter, QPen, QTouchEvent
)
from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer

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
    """Custom QGraphicsView with zoom, pan, pinch gesture, and touch scrolling with inertia."""

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
        if event.button() == Qt.MouseButton.MiddleButton or (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.panning = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.panning and self.last_mouse_pos:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.panning:
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)

    # ---------- Touch ----------
    def viewportEvent(self, event):
        """Intercept touch events at the viewport level."""
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

        # Check if the touch is over a movable item (module or widget)
        items = self.scene().items(scene_pos) if self.scene() else []
        movable = any(isinstance(it, ModuleItem) or it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable for it in items)

        if event.type() == QEvent.Type.TouchBegin:
            if not movable:
                self.touch_last_pos = pos
                self._last_move_pos = QPointF(pos)
                self._last_move_time = time.time()
                self._stop_inertia()
            event.accept()
            return True

        elif event.type() == QEvent.Type.TouchUpdate:
            if not movable and self.touch_last_pos is not None:
                delta = pos - self.touch_last_pos
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))

                # velocity update
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
            if not movable:
                if abs(self._vel_x) > 50 or abs(self._vel_y) > 50:
                    self._start_inertia()
                self.touch_last_pos = None
                event.accept()
                return True

        # If touch is over movable module, let the module handle it
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
            old_anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
            vp_center = QPointF(center_pt)
            scene_before = self.mapToScene(vp_center.toPoint())
            if pinch.changeFlags() & QPinchGesture.ChangeFlag.ScaleFactorChanged:
                scale = pinch.scaleFactor()
                if scale > 0:
                    self.scale(scale, scale)
            scene_after = self.mapToScene(vp_center.toPoint())
            shift = scene_after - scene_before
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + int(shift.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + int(shift.y()))
            self.setTransformationAnchor(old_anchor)
            event.accept()
            return True
        return False

    # ---------- Inertia ----------
    def _start_inertia(self):
        self._stop_inertia()
        self._inertia_timer = QTimer(self)
        interval_ms = int(1000 / self.INERTIA_FPS)
        self._inertia_timer.setInterval(interval_ms)
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

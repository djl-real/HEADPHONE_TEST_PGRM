# main_window.py
import sys
import time
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QPinchGesture
)
from PyQt6.QtGui import (
    QBrush, QColor, QWheelEvent, QPainter, QPen
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
    """Custom view with zoom/pan and touchscreen gesture support (pinch + momentum)."""

    # inertia parameters
    INERTIA_FPS = 60
    INERTIA_DECAY = 0.93  # multiply velocity by this each tick
    INERTIA_MIN_VEL = 0.5  # pixels per tick below which inertia stops

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

        # do not draw an additional background brush here; scene handles it
        self.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # mouse panning
        self.zoom_factor = 1.15
        self.last_mouse_pos = None
        self.panning = False

        # touch support & gestures
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        # request pinch gesture
        self.grabGesture(Qt.GestureType.PinchGesture)
        # make sure we get gesture events
        self.setInteractive(True)

        # transformation anchor default (we'll override when needed)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # touch panning state for 1-finger drag
        self.touch_last_pos: QPointF | None = None
        # velocity tracking for inertia (pixels per second)
        self._last_move_time = None
        self._last_move_pos = None
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._inertia_timer: QTimer | None = None

    # ---------- Mouse-based zoom ----------
    def wheelEvent(self, event: QWheelEvent):
        # zoom centered on mouse cursor (AnchorUnderMouse does that)
        zoom = self.zoom_factor if event.angleDelta().y() > 0 else 1 / self.zoom_factor
        self.scale(zoom, zoom)

    # ---------- Mouse-based panning ----------
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
            # integer scroll bar values required
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

    # ---------- Touch & Gesture Handling ----------
    def event(self, event):
        """Handle touch and gesture events (Gesture, TouchBegin/Update/End)."""
        et = event.type()
        if et == QEvent.Type.Gesture:
            # route to pinch handler
            return self.gestureEvent(event)
        elif et == QEvent.Type.TouchBegin:
            pts = event.touchPoints()
            if pts:
                self.touch_last_pos = pts[0].position()
                self._last_move_pos = QPointF(self.touch_last_pos)
                self._last_move_time = time.time()
                # stop any running inertia
                self._stop_inertia()
            event.accept()
            return True
        elif et == QEvent.Type.TouchUpdate:
            pts = event.touchPoints()
            if len(pts) == 1:
                # one-finger pan
                tp = pts[0]
                pos = tp.position()
                if self.touch_last_pos is not None:
                    delta = pos - self.touch_last_pos
                    # integer scroll update
                    self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
                    self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))

                    # update velocity estimate (pixels/sec)
                    now = time.time()
                    dt = max(1e-6, now - (self._last_move_time or now))
                    vx = (pos.x() - (self._last_move_pos.x() if self._last_move_pos is not None else pos.x())) / dt
                    vy = (pos.y() - (self._last_move_pos.y() if self._last_move_pos is not None else pos.y())) / dt
                    # low-pass blend velocities for stability
                    self._vel_x = (self._vel_x * 0.7) + (vx * 0.3)
                    self._vel_y = (self._vel_y * 0.7) + (vy * 0.3)
                    self._last_move_pos = QPointF(pos)
                    self._last_move_time = now

                self.touch_last_pos = pos
            event.accept()
            return True
        elif et == QEvent.Type.TouchEnd:
            # start inertia if velocity large enough
            if (abs(self._vel_x) > 50) or (abs(self._vel_y) > 50):
                self._start_inertia()
            self.touch_last_pos = None
            event.accept()
            return True

        return super().event(event)

    def gestureEvent(self, event):
        """Handle pinch gesture for zooming centered on the gesture focal point."""
        # note: event.gesture() returns a QGesture instance; we only asked for pinch
        pinch = event.gesture(Qt.GestureType.PinchGesture)
        if pinch and isinstance(pinch, QPinchGesture):
            change_flags = pinch.changeFlags()

            # Retrieve the center (in viewport coordinates). It may return a QPointF.
            center_pt = pinch.centerPoint()  # QPointF in viewport coordinates

            # Convert center to scene coordinates BEFORE scaling
            if center_pt is None:
                return False

            # Because we will manually keep the scene point under the same viewport coordinate,
            # set transformation anchor to NoAnchor temporarily to perform manual centering.
            old_anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

            # map viewport center to scene before scaling
            vp_center = QPointF(center_pt)
            scene_before = self.mapToScene(vp_center.toPoint())

            # If scale factor changed, apply scale around the viewport point
            if change_flags & QPinchGesture.ChangeFlag.ScaleFactorChanged:
                scale = pinch.scaleFactor()
                # prevent extremely large/small zooms
                if scale > 0:
                    self.scale(scale, scale)

            # After scaling, map the same viewport point to scene -> compute shift and pan to keep focal point stable
            scene_after = self.mapToScene(vp_center.toPoint())
            shift = scene_after - scene_before
            # Move view so that scene_after maps back to the same viewport position
            # convert scene shift to scrollbar adjustments (in pixels)
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + int(shift.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + int(shift.y()))

            # Restore transformation anchor
            self.setTransformationAnchor(old_anchor)

            event.accept()
            return True
        return False

    # ---------- Inertia / momentum ----------
    def _start_inertia(self):
        # stop any existing timer first
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
        # reset velocity
        self._vel_x = 0.0
        self._vel_y = 0.0

    def _inertia_step(self):
        # apply velocity (pixels/sec) scaled by frame dt to scrollbars
        dt = 1.0 / max(1, self.INERTIA_FPS)
        dx = self._vel_x * dt
        dy = self._vel_y * dt
        # apply integer scroll amounts
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(dx))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(dy))
        # decay velocities
        self._vel_x *= self.INERTIA_DECAY
        self._vel_y *= self.INERTIA_DECAY
        # stop condition when velocities are small
        if (abs(self._vel_x) < self.INERTIA_MIN_VEL and abs(self._vel_y) < self.INERTIA_MIN_VEL):
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

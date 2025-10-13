import sys
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QGestureEvent, QPinchGesture
from PyQt6.QtGui import QBrush, QColor, QWheelEvent, QPainter, QPen
from PyQt6.QtCore import Qt, QPointF, QEvent

from audio_module import AudioModule
from toolbar_manager import ToolbarManager
from ui_elements import ModuleItem, NodeCircle, ConnectionPath


class WorkspaceScene(QGraphicsScene):
    """Custom scene with background grid only."""
    def __init__(self):
        super().__init__()
        self.setBackgroundBrush(QColor(30, 30, 30))  # fallback background
        self.grid_size = 25
        self.grid_color = QColor(50, 50, 50)
        self.grid_line_width = 2

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(25, 25, 25))
        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)

        pen = QPen(self.grid_color)
        pen.setWidth(self.grid_line_width)
        painter.setPen(pen)

        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += self.grid_size

        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += self.grid_size


class WorkspaceView(QGraphicsView):
    """Custom view with zoom/pan and touchscreen gesture support."""
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self.zoom_factor = 1.15
        self.last_mouse_pos = None
        self.panning = False

        # Enable touch and gestures
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.setInteractive(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Track last touch position for panning
        self.touch_last_pos = None

    # ---------- Mouse-based zoom ----------
    def wheelEvent(self, event: QWheelEvent):
        zoom = self.zoom_factor if event.angleDelta().y() > 0 else 1 / self.zoom_factor
        self.scale(zoom, zoom)

    # ---------- Mouse-based panning ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.panning = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.panning and self.last_mouse_pos:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
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
        """Handle touch and gesture events."""
        if event.type() == QEvent.Type.Gesture:
            return self.gestureEvent(event)
        elif event.type() == QEvent.Type.TouchBegin:
            self.touch_last_pos = event.points()[0].position() if event.points() else None
            event.accept()
            return True
        elif event.type() == QEvent.Type.TouchUpdate:
            if len(event.points()) == 1:  # One-finger pan
                touch_point = event.points()[0]
                if self.touch_last_pos:
                    delta = touch_point.position() - self.touch_last_pos
                    self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                    self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
                self.touch_last_pos = touch_point.position()
            event.accept()
            return True
        elif event.type() == QEvent.Type.TouchEnd:
            self.touch_last_pos = None
            event.accept()
            return True
        return super().event(event)

    def gestureEvent(self, event: QGestureEvent):
        """Handle pinch gesture for zoom."""
        pinch = event.gesture(Qt.GestureType.PinchGesture)
        if pinch:
            change_flags = pinch.changeFlags()
            if change_flags & QPinchGesture.ChangeFlag.ScaleFactorChanged:
                self.scale(pinch.scaleFactor(), pinch.scaleFactor())
            event.accept()
            return True
        return False


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

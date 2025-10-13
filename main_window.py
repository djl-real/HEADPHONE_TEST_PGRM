# main_window.py
import sys
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt6.QtGui import QBrush, QColor, QWheelEvent, QPainter
from PyQt6.QtCore import Qt

from audio_module import AudioModule
from toolbar_manager import ToolbarManager
from ui_elements import ModuleItem, NodeCircle, ConnectionPath


class WorkspaceScene(QGraphicsScene):
    """Custom scene to handle temporary connection drag."""
    def __init__(self):
        super().__init__()
        self.temp_connection: ConnectionPath | None = None
        self.dragging_output: NodeCircle | None = None
        self.setBackgroundBrush(QColor(30, 30, 30))

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if isinstance(item, NodeCircle) and item.node_type == "output":
            self.dragging_output = item
            self.temp_connection = ConnectionPath(self.dragging_output, scene=self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.temp_connection and self.dragging_output:
            self.temp_connection.update_path_from_pos(event.scenePos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.temp_connection and self.dragging_output:
            items = self.items(event.scenePos())
            target_input = next(
                (i for i in items if isinstance(i, NodeCircle) and i.node_type == "input"), None
            )
            if target_input:
                # Connect backend nodes
                if self.dragging_output.audio_module and target_input.audio_module:
                    self.dragging_output.audio_module.output_node.connect(target_input.audio_module.input_node)

                # Finalize path references
                self.temp_connection.end_node = target_input
                self.dragging_output.connection = self.temp_connection
                target_input.connection = self.temp_connection
                self.temp_connection.update_path()
            else:
                self.removeItem(self.temp_connection)

            self.temp_connection = None
            self.dragging_output = None
        super().mouseReleaseEvent(event)


class WorkspaceView(QGraphicsView):
    """Custom view with zoom/pan support."""
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(25, 25, 25)))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.zoom_factor = 1.15
        self.last_mouse_pos = None
        self.panning = False

    def wheelEvent(self, event: QWheelEvent):
        zoom = self.zoom_factor if event.angleDelta().y() > 0 else 1 / self.zoom_factor
        self.scale(zoom, zoom)

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

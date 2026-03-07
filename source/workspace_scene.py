from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtCore import QPointF


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
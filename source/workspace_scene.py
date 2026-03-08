from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtCore import QPointF, QLineF


class WorkspaceScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.setBackgroundBrush(QBrush(QColor(25, 25, 25)))
        self.grid_size = 25
        self.grid_color = QColor(50, 50, 50)
        self.setSceneRect(-100000, -100000, 200000, 200000)

    def drawBackground(self, painter, rect):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(rect, QColor(25, 25, 25))

        # Determine screen-space pixel size of one scene unit.
        # If no view exists, assume 1:1.
        views = self.views()
        if views:
            tx = views[0].transform()
            scale = tx.m11()  # horizontal scale factor
        else:
            scale = 1.0

        # Step up through grid multiples until lines are >= 4px apart on screen.
        effective_grid = self.grid_size
        while effective_grid * scale < 4.0:
            effective_grid *= 5  # 25 -> 125 -> 625 ...

        # If even the coarsest level is still too dense, skip the grid entirely.
        if effective_grid * scale < 2.0:
            painter.restore()
            return

        # Snap to grid boundaries
        left = int(rect.left()) - (int(rect.left()) % effective_grid)
        top = int(rect.top()) - (int(rect.top()) % effective_grid)

        pen = QPen(self.grid_color)
        pen.setWidthF(1.0)
        pen.setCosmetic(True)  # width stays 1px regardless of zoom
        painter.setPen(pen)

        # Collect all lines into a list, then draw in one batch
        lines = []
        x = left
        while x <= rect.right():
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
            x += effective_grid

        y = top
        while y <= rect.bottom():
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            y += effective_grid

        if lines:
            painter.drawLines(lines)

        painter.restore()
import numpy as np
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, QRect
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton
)


# ----------------- PyQt6-safe deletion check -----------------
def is_dead(obj):
    """Return True if the Qt object has been deleted."""
    if obj is None:
        return True
    try:
        obj.objectName()  # calling ANY Qt method raises RuntimeError if deleted
        return False
    except RuntimeError:
        return True


class Mixer(QWidget):
    """Bottom-aligned mixer panel with channel strips and master fader."""
    COLLAPSED_HEIGHT = 100
    EXPANDED_HEIGHT = 350  # full fader height + margin

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.endpoints = []
        self.channel_strips = []
        self.master_volume_db = 0.0
        self.is_expanded = False
        self.anim = None

        # Base geometry (collapsed by default)
        self.setGeometry(0, main_window.height() - self.COLLAPSED_HEIGHT - 200,
                         main_window.width(), self.COLLAPSED_HEIGHT)
        self.setStyleSheet("background-color: rgba(50, 50, 50, 230);")

        self._build_ui()
        self._setup_timer()
        self.show()

        # Keep pinned to bottom on resize
        self.main_window.resizeEvent = self._on_main_window_resize

    def _on_main_window_resize(self, event):
        """Keep the mixer pinned to the bottom on resize."""
        height = self.EXPANDED_HEIGHT if self.is_expanded else self.COLLAPSED_HEIGHT
        self.setGeometry(0, self.main_window.height() - height,
                         self.main_window.width(), height)
        event.accept()

    # ---------------------------------------------------------
    # UI LAYOUT
    # ---------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable strip area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QHBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(10, 5, 10, 5)
        self.scroll_layout.setSpacing(15)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.scroll_content)

        # Mixer button
        self.toggle_button = QPushButton("Mixer ▲", self)
        self.toggle_button.setFixedHeight(30)
        self.toggle_button.clicked.connect(self.toggle_panel)

        layout.addWidget(self.toggle_button)
        layout.addWidget(self.scroll_area)

    def _setup_timer(self):
        """Syncs mixer UI with endpoints every 200ms."""
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_from_endpoints)
        self.sync_timer.start(200)

    # ---------------------------------------------------------
    # EXPAND / COLLAPSE
    # ---------------------------------------------------------
    def toggle_panel(self):
        self.is_expanded = not self.is_expanded
        self.toggle_button.setText("Mixer ▼" if self.is_expanded else "Mixer ▲")

        start_geom = self.geometry()
        end_height = self.EXPANDED_HEIGHT if self.is_expanded else self.COLLAPSED_HEIGHT
        end_geom = QRect(0, self.main_window.height() - end_height,
                         self.main_window.width(), end_height)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(300)
        self.anim.setStartValue(start_geom)
        self.anim.setEndValue(end_geom)
        self.anim.start()

    # ---------------------------------------------------------
    # CHANNEL MANAGEMENT
    # ---------------------------------------------------------
    def add_endpoint(self, endpoint):
        if endpoint in self.endpoints:
            return

        ui = endpoint.get_ui()
        ui.setParent(self.scroll_content)

        ui.setMaximumWidth(140)
        ui.setMaximumHeight(300)

        self.scroll_layout.addWidget(ui)

        self.endpoints.append(endpoint)
        self.channel_strips.append(ui)

    def remove_endpoint(self, endpoint):
        """Safely remove the endpoint's mixer UI without crashing."""

        if endpoint not in self.endpoints:
            return

        # Attempt to get endpoint's mixer UI (saved in endpoint.widgets)
        ui = None
        try:
            ui = endpoint.widgets[1]
        except Exception:
            ui = None

        # Remove mixer UI if it still exists
        if ui in self.channel_strips:
            self.scroll_layout.removeWidget(ui)

            if not is_dead(ui):
                ui.hide()
                ui.setParent(None)
                ui.deleteLater()

            self.channel_strips.remove(ui)

        # Remove from endpoint list
        if endpoint in self.endpoints:
            self.endpoints.remove(endpoint)

    # ---------------------------------------------------------
    # SYNC LOOP
    # ---------------------------------------------------------
    def sync_from_endpoints(self):
        """Safely sync all endpoints; remove any with dead UI."""
        dead_eps = []

        for ep in list(self.endpoints):
            # Endpoint must expose widgets list (you already do this)
            try:
                ui = ep.widgets[1]
            except Exception:
                ui = None

            # If UI is missing or deleted → schedule removal
            if ui is None or is_dead(ui):
                dead_eps.append(ep)
                continue

            # Try syncing
            try:
                ep.sync()
            except RuntimeError:
                # UI got deleted mid-operation
                dead_eps.append(ep)

        # Remove endpoints with dead UIs
        for ep in dead_eps:
            self.remove_endpoint(ep)

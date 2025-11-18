import numpy as np
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, QRect
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton,
    QSlider, QLabel, QLineEdit
)

# Shared constants from endpoint.py
DB_MIN = -80.0
DB_MAX = 10.0

def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)


class MixerChannel(QWidget):
    """UI representation of a single Endpoint channel strip (matches endpoint fader style)."""
    def __init__(self, endpoint):
        super().__init__()
        self.endpoint = endpoint
        self._build_ui()
        self._sync_from_endpoint()

        # Connect UI events
        self.slider.valueChanged.connect(self._update_endpoint)
        self.mute_button.toggled.connect(self._update_endpoint)
        self.nickname_box.textChanged.connect(self._update_endpoint)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Nickname box (same as endpoint.py)
        self.nickname_box = QLineEdit()
        self.nickname_box.setPlaceholderText("Enter nickname...")
        self.nickname_box.setText(getattr(self.endpoint, "nickname", ""))
        self.nickname_box.setFixedWidth(100)
        self.nickname_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.nickname_box, alignment=Qt.AlignmentFlag.AlignCenter)

        # Volume label
        self.label = QLabel(f"Volume: {self.endpoint.volume_db:.1f} dB")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        # Slider + dB labels layout
        slider_layout = QHBoxLayout()

        # Slider
        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(int((self.endpoint.volume_db - DB_MIN) / (DB_MAX - DB_MIN) * 100))
        self.slider.setTickInterval(10)
        self.slider.setTickPosition(QSlider.TickPosition.TicksLeft)
        self.slider.setFixedHeight(200)  # full fader height from endpoint.py
        slider_layout.addWidget(self.slider)

        # dB scale labels (on left)
        label_layout = QVBoxLayout()
        for db in range(int(DB_MAX), int(DB_MIN) - 1, -10):
            text = f"{db} dB" if db > DB_MIN else "-∞ dB"
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_layout.addWidget(lbl)
        slider_layout.addLayout(label_layout)
        layout.addLayout(slider_layout)

        # Mute button (same style as endpoint.py)
        self.mute_button = QPushButton("Mute")
        self.mute_button.setCheckable(True)
        self.mute_button.setChecked(self.endpoint.muted)
        self.mute_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #95a5a6;
            }
        """)
        layout.addWidget(self.mute_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setMaximumWidth(120)

    def _sync_from_endpoint(self):
        """Copy endpoint values into mixer UI."""
        val = int((self.endpoint.volume_db - DB_MIN) / (DB_MAX - DB_MIN) * 100)
        self.slider.setValue(val)
        self.mute_button.setChecked(self.endpoint.muted)
        self.nickname_box.setText(getattr(self.endpoint, "nickname", ""))
        self.label.setText(f"Volume: {self.endpoint.volume_db:.1f} dB")

    def _update_endpoint(self):
        """Sync UI → endpoint."""
        self.endpoint.muted = self.mute_button.isChecked()
        self.endpoint.nickname = self.nickname_box.text()
        self.endpoint.volume_db = DB_MIN + (self.slider.value() / 100) * (DB_MAX - DB_MIN)
        self.label.setText(f"Volume: {self.endpoint.volume_db:.1f} dB")

        # Reflect change in endpoint UI if applicable
        if hasattr(self.endpoint, "slider"):
            self.endpoint.slider.blockSignals(True)
            self.endpoint.slider.setValue(self.slider.value())
            self.endpoint.slider.blockSignals(False)
        if hasattr(self.endpoint, "label"):
            self.endpoint.label.setText(f"Volume: {self.endpoint.volume_db:.1f} dB")

    def sync_from_endpoint(self):
        """External call to refresh from endpoint."""
        self._sync_from_endpoint()


class MasterChannel(QWidget):
    """Master fader strip."""
    def __init__(self, mixer):
        super().__init__()
        self.mixer = mixer
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        label = QLabel("Master")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        self.slider.setFixedHeight(200)
        layout.addWidget(self.slider, alignment=Qt.AlignmentFlag.AlignCenter)

        self.db_label = QLabel("0.0 dB")
        self.db_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.db_label)

        self.slider.valueChanged.connect(self._on_change)

    def _on_change(self, val):
        db_val = DB_MIN + (val / 100) * (DB_MAX - DB_MIN)
        self.db_label.setText(f"{db_val:.1f} dB")
        self.mixer.master_volume_db = db_val


class Mixer(QWidget):
    """Bottom-aligned mixer panel with channel strips and master fader."""
    COLLAPSED_HEIGHT = 30
    EXPANDED_HEIGHT = 260  # full fader height + margin

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.endpoints = []
        self.channel_strips = []
        self.master_volume_db = 0.0
        self.is_expanded = False
        self.anim = None

        # Base geometry (collapsed by default)
        self.setGeometry(0, main_window.height() - self.COLLAPSED_HEIGHT,
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
        self.setGeometry(0, self.main_window.height() - height - 70,
                         self.main_window.width(), height)
        event.accept()

    def _build_ui(self):
        """Builds scroll area and toggle button inside the mixer."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable channel area (now parented to self)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QHBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(10, 5, 10, 5)
        self.scroll_layout.setSpacing(15)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.scroll_content)

        # Add master fader
        self.master_channel = MasterChannel(self)
        self.scroll_layout.addWidget(self.master_channel)
        self.scroll_area.hide()

        # Toggle button pinned at bottom
        self.toggle_button = QPushButton("Mixer ▲", self)
        self.toggle_button.setFixedHeight(30)
        self.toggle_button.clicked.connect(self.toggle_panel)

        # Stack them vertically: scroll area below, button above
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.scroll_area)

    def _setup_timer(self):
        """Syncs mixer UI with endpoints every 200ms."""
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_from_endpoints)
        self.sync_timer.start(200)

    def toggle_panel(self):
        """Expand/collapse mixer panel."""
        self.is_expanded = not self.is_expanded
        self.toggle_button.setText("Mixer ▼" if self.is_expanded else "Mixer ▲")

        start_geom = self.geometry()
        end_height = self.EXPANDED_HEIGHT if self.is_expanded else self.COLLAPSED_HEIGHT
        end_geom = QRect(0, self.main_window.height() - end_height - 70,
                         self.main_window.width(), end_height)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(300)
        self.anim.setStartValue(start_geom)
        self.anim.setEndValue(end_geom)
        self.anim.start()
        
        # Show/hide scroll area depending on expanded state
        if self.is_expanded:
            self.scroll_area.show()
        else:
            self.scroll_area.hide()

    # ---------- Channel Management ----------
    def add_endpoint(self, endpoint):
        if endpoint in self.endpoints:
            return
        channel = MixerChannel(endpoint)
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, channel)
        self.endpoints.append(endpoint)
        self.channel_strips.append(channel)

    def remove_endpoint(self, endpoint):
        for i, ch in enumerate(self.channel_strips):
            if ch.endpoint == endpoint:
                self.scroll_layout.removeWidget(ch)
                ch.deleteLater()
                del self.channel_strips[i]
                self.endpoints.remove(endpoint)
                break

    def sync_from_endpoints(self):
        for ch in self.channel_strips:
            ch.sync_from_endpoint()


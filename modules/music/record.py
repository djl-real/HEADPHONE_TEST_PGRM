from PyQt6.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QFont, QPainterPath, QRadialGradient


class Record(QWidget):
    """Circular vinyl record widget with album art, spinning animation, and drag-drop."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setAcceptDrops(True)
        
        # Display data
        self.album_art = None  # QPixmap
        self.song_name = "Drop a song here"
        self.artist_name = "Drag from playlist"
        self.rotation_angle = 0.0
        self.is_playing = False
        
        # Drop zone visual state
        self._drag_hover = False
        self._glow_intensity = 0.0
        self._drop_flash = 0.0
        
        # Animation
        self.spin_timer = QTimer(self)
        self.spin_timer.timeout.connect(self._update_rotation)
        self.spin_timer.setInterval(16)  # ~60 FPS
        
        # Glow animation for drag hover
        self.glow_timer = QTimer(self)
        self.glow_timer.timeout.connect(self._update_glow)
        self.glow_timer.setInterval(30)
        
        # Drop flash animation
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self._update_flash)
        self.flash_timer.setInterval(20)
        
        # Callbacks
        self.on_song_dropped = None  # Callback when song is dropped
        self.on_play_clicked = None  # Callback when play button clicked
    
    def set_album_art(self, pixmap: QPixmap):
        """Set the album art image."""
        self.album_art = pixmap
        self.update()
    
    def set_song_info(self, song_name: str, artist_name: str):
        """Set the song and artist text."""
        self.song_name = song_name
        self.artist_name = artist_name
        self.update()
    
    def set_playing(self, playing: bool):
        """Set playing state and control spinning animation."""
        self.is_playing = playing
        if playing:
            self.spin_timer.start()
        else:
            self.spin_timer.stop()
        self.update()
    
    def _update_rotation(self):
        """Update rotation angle for spinning animation."""
        # Rotate at ~33 RPM (vinyl speed)
        self.rotation_angle = (self.rotation_angle + 2.0) % 360
        self.update()
    
    def _update_glow(self):
        """Animate the glow effect during drag hover."""
        if self._drag_hover:
            self._glow_intensity = min(1.0, self._glow_intensity + 0.1)
        else:
            self._glow_intensity = max(0.0, self._glow_intensity - 0.15)
            if self._glow_intensity <= 0:
                self.glow_timer.stop()
        self.update()
    
    def _update_flash(self):
        """Animate the flash effect after drop."""
        self._drop_flash = max(0.0, self._drop_flash - 0.08)
        if self._drop_flash <= 0:
            self.flash_timer.stop()
        self.update()
    
    def _trigger_drop_flash(self):
        """Trigger the drop flash animation."""
        self._drop_flash = 1.0
        self.flash_timer.start()
    
    def paintEvent(self, event):
        """Draw the vinyl record with drop zone effects."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Calculate circle dimensions (70% of width)
        diameter = min(width, height) * 0.7
        radius = diameter / 2
        center_x = width / 2
        center_y = height / 2
        
        # Draw glow effect when dragging over
        if self._glow_intensity > 0:
            glow_radius = radius + 20 + (10 * self._glow_intensity)
            glow_gradient = QRadialGradient(center_x, center_y, glow_radius)
            glow_color = QColor(74, 144, 226, int(100 * self._glow_intensity))
            glow_gradient.setColorAt(0.7, glow_color)
            glow_gradient.setColorAt(1.0, QColor(74, 144, 226, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow_gradient))
            painter.drawEllipse(QPointF(center_x, center_y), glow_radius, glow_radius)
        
        # Draw drop flash effect
        if self._drop_flash > 0:
            flash_radius = radius + 30
            flash_gradient = QRadialGradient(center_x, center_y, flash_radius)
            flash_color = QColor(46, 204, 113, int(150 * self._drop_flash))
            flash_gradient.setColorAt(0.5, flash_color)
            flash_gradient.setColorAt(1.0, QColor(46, 204, 113, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(flash_gradient))
            painter.drawEllipse(QPointF(center_x, center_y), flash_radius, flash_radius)
        
        # Draw outer circle (vinyl edge) with highlight when hovering
        edge_color = QColor(100, 160, 230) if self._glow_intensity > 0.5 else QColor(40, 40, 40)
        edge_width = 4 if self._glow_intensity > 0.5 else 3
        painter.setPen(QPen(edge_color, edge_width))
        painter.setBrush(QBrush(QColor(60, 60, 60)))
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)
        
        # Draw vinyl grooves (decorative rings)
        painter.setPen(QPen(QColor(50, 50, 50), 1))
        for i in range(3, 8):
            groove_radius = radius * (i / 10)
            painter.drawEllipse(QPointF(center_x, center_y), groove_radius, groove_radius)
        
        # Draw album art or default background
        if self.album_art:
            # Save painter state
            painter.save()
            
            # Create circular clipping path
            path = QPainterPath()
            path.addEllipse(QPointF(center_x, center_y), radius - 5, radius - 5)
            painter.setClipPath(path)
            
            # Rotate around center if playing
            if self.is_playing:
                painter.translate(center_x, center_y)
                painter.rotate(self.rotation_angle)
                painter.translate(-center_x, -center_y)
            
            # Draw album art scaled to fit circle
            art_rect = QRectF(
                center_x - radius + 5,
                center_y - radius + 5,
                diameter - 10,
                diameter - 10
            )
            painter.drawPixmap(art_rect.toRect(), self.album_art)
            
            painter.restore()
        else:
            # Default gradient background
            bg_gradient = QRadialGradient(center_x, center_y, radius - 5)
            bg_gradient.setColorAt(0.0, QColor(70, 70, 70))
            bg_gradient.setColorAt(0.5, QColor(45, 45, 45))
            bg_gradient.setColorAt(1.0, QColor(35, 35, 35))
            painter.setBrush(QBrush(bg_gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(center_x, center_y), radius - 5, radius - 5)
            
            # Draw "drop here" visual hint when not hovering
            if self._glow_intensity < 0.3 and not self.is_playing:
                painter.setPen(QColor(100, 100, 100))
                font = QFont("Arial", 10)
                painter.setFont(font)
        
        # Draw center spindle hole
        spindle_radius = 10
        painter.setPen(QPen(QColor(30, 30, 30), 2))
        painter.setBrush(QBrush(QColor(20, 20, 20)))
        painter.drawEllipse(QPointF(center_x, center_y), spindle_radius, spindle_radius)
        
        # Draw play/pause button in center
        play_btn_radius = 40
        
        # Button background circle
        btn_bg_gradient = QRadialGradient(center_x, center_y, play_btn_radius)
        btn_bg_gradient.setColorAt(0.0, QColor(60, 60, 60, 200))
        btn_bg_gradient.setColorAt(1.0, QColor(40, 40, 40, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(btn_bg_gradient))
        painter.drawEllipse(QPointF(center_x, center_y), play_btn_radius, play_btn_radius)
        
        if self.is_playing:
            # Pause icon
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(46, 204, 113)))
            bar_width = 10
            bar_height = 26
            painter.drawRoundedRect(
                int(center_x - bar_width - 4),
                int(center_y - bar_height / 2),
                bar_width,
                bar_height,
                2, 2
            )
            painter.drawRoundedRect(
                int(center_x + 4),
                int(center_y - bar_height / 2),
                bar_width,
                bar_height,
                2, 2
            )
        else:
            # Play icon (triangle)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(46, 204, 113)))
            triangle = [
                QPointF(center_x - 10, center_y - 15),
                QPointF(center_x - 10, center_y + 15),
                QPointF(center_x + 15, center_y)
            ]
            painter.drawPolygon(triangle)
        
        # Draw song info text below the vinyl
        text_y_base = center_y + radius + 15
        
        # Song name
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        painter.setFont(font)
        song_rect = QRectF(0, text_y_base, width, 25)
        
        # Truncate long song names
        display_song = self.song_name
        if len(display_song) > 25:
            display_song = display_song[:24] + "…"
        painter.drawText(song_rect, Qt.AlignmentFlag.AlignCenter, display_song)
        
        # Artist name
        painter.setPen(QColor(180, 180, 180))
        font = QFont("Arial", 10)
        painter.setFont(font)
        artist_rect = QRectF(0, text_y_base + 22, width, 20)
        
        # Truncate long artist names
        display_artist = self.artist_name
        if len(display_artist) > 30:
            display_artist = display_artist[:29] + "…"
        painter.drawText(artist_rect, Qt.AlignmentFlag.AlignCenter, display_artist)
    
    def mousePressEvent(self, event):
        """Handle clicks on the play button."""
        width = self.width()
        height = self.height()
        center_x = width / 2
        center_y = height / 2
        
        # Check if click is within play button area
        dx = event.pos().x() - center_x
        dy = event.pos().y() - center_y
        distance = (dx * dx + dy * dy) ** 0.5
        
        if distance < 40:  # Play button radius
            if self.on_play_clicked:
                self.on_play_clicked()
    
    def dragEnterEvent(self, event):
        """Accept drag events from playlist with visual feedback."""
        mime = event.mimeData()
        if mime.hasText() or mime.hasFormat("application/x-song-index"):
            event.acceptProposedAction()
            self._drag_hover = True
            self.glow_timer.start()
    
    def dragMoveEvent(self, event):
        """Continue accepting drag while moving over widget."""
        mime = event.mimeData()
        if mime.hasText() or mime.hasFormat("application/x-song-index"):
            event.acceptProposedAction()
    
    def dragLeaveEvent(self, event):
        """Remove visual feedback when drag leaves."""
        self._drag_hover = False
        # Glow timer will fade out the effect
    
    def dropEvent(self, event):
        """Handle drop of song from playlist."""
        mime = event.mimeData()
        
        song_index = None
        if mime.hasFormat("application/x-song-index"):
            song_index = int(mime.data("application/x-song-index").data().decode())
        elif mime.hasText():
            try:
                song_index = int(mime.text())
            except ValueError:
                pass
        
        if song_index is not None:
            self._drag_hover = False
            self._trigger_drop_flash()
            
            if self.on_song_dropped:
                self.on_song_dropped(song_index)
            
            event.acceptProposedAction()
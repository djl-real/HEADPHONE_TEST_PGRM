from PyQt6.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QFont, QPainterPath, QRadialGradient


class Record(QWidget):
    """Circular vinyl record widget with album art, spinning animation, and drag-drop."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 320)
        self.setAcceptDrops(True)
        
        # Display data
        self.album_art = None  # QPixmap
        self.song_name = "Drop a song here"
        self.artist_name = "Drag from playlist"
        self.rotation_angle = 0.0
        self.is_playing = False
        self.pitch = 1.0  # Pitch multiplier for spin speed
        
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
    
    def set_pitch(self, pitch: float):
        """Set the pitch multiplier for spin speed."""
        self.pitch = pitch
    
    def _update_rotation(self):
        """Update rotation angle for spinning animation at 33 RPM adjusted by pitch."""
        # 33 RPM = 33 rotations per minute = 0.55 rotations per second
        # At 60 FPS (16ms interval), that's 0.55 * 360 / 60 = 3.3 degrees per frame
        # Base rotation adjusted by pitch
        base_rotation = 3.3 * self.pitch
        self.rotation_angle = (self.rotation_angle + base_rotation) % 360
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
        
        # Reserve space for text at bottom (reduced)
        text_area_height = 40
        vinyl_area_height = height - text_area_height
        
        # Calculate circle dimensions (85% of available area, moved up)
        diameter = min(width, vinyl_area_height) * 0.85
        radius = diameter / 2
        center_x = width / 2
        center_y = vinyl_area_height / 2  # Center in vinyl area only
        
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
        
        # Draw album art or default background
        if self.album_art:
            # Save painter state
            painter.save()
            
            # Create circular clipping path
            path = QPainterPath()
            path.addEllipse(QPointF(center_x, center_y), radius - 3, radius - 3)
            painter.setClipPath(path)
            
            # Rotate around center (always rotate when playing, pitch affects speed)
            if self.is_playing:
                painter.translate(center_x, center_y)
                painter.rotate(self.rotation_angle)
                painter.translate(-center_x, -center_y)
            
            # Draw album art scaled to fit circle
            art_rect = QRectF(
                center_x - radius + 3,
                center_y - radius + 3,
                diameter - 6,
                diameter - 6
            )
            painter.drawPixmap(art_rect.toRect(), self.album_art)
            
            painter.restore()
            
            # Draw vinyl grooves overlay (semi-transparent rings)
            painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
            for i in range(3, 9):
                groove_radius = radius * (i / 10)
                painter.drawEllipse(QPointF(center_x, center_y), groove_radius, groove_radius)
        else:
            # Default gradient background when no album art
            bg_gradient = QRadialGradient(center_x, center_y, radius - 3)
            bg_gradient.setColorAt(0.0, QColor(70, 70, 70))
            bg_gradient.setColorAt(0.5, QColor(45, 45, 45))
            bg_gradient.setColorAt(1.0, QColor(35, 35, 35))
            painter.setBrush(QBrush(bg_gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(center_x, center_y), radius - 3, radius - 3)
            
            # Draw vinyl grooves
            painter.setPen(QPen(QColor(50, 50, 50), 1))
            for i in range(3, 9):
                groove_radius = radius * (i / 10)
                painter.drawEllipse(QPointF(center_x, center_y), groove_radius, groove_radius)
        
        # Draw center spindle hole
        spindle_radius = 8
        painter.setPen(QPen(QColor(30, 30, 30), 2))
        painter.setBrush(QBrush(QColor(20, 20, 20)))
        painter.drawEllipse(QPointF(center_x, center_y), spindle_radius, spindle_radius)
        
        # Draw play/pause button in center
        play_btn_radius = 35
        
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
            bar_width = 8
            bar_height = 22
            painter.drawRoundedRect(
                int(center_x - bar_width - 3),
                int(center_y - bar_height / 2),
                bar_width,
                bar_height,
                2, 2
            )
            painter.drawRoundedRect(
                int(center_x + 3),
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
                QPointF(center_x - 8, center_y - 12),
                QPointF(center_x - 8, center_y + 12),
                QPointF(center_x + 12, center_y)
            ]
            painter.drawPolygon(triangle)
        
        # Draw song info text below the vinyl (compact spacing)
        text_y_base = vinyl_area_height + 2
        
        # Song name
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 11, QFont.Weight.Bold)
        painter.setFont(font)
        song_rect = QRectF(0, text_y_base, width, 18)
        
        # Truncate long song names
        display_song = self.song_name
        if len(display_song) > 30:
            display_song = display_song[:29] + "..."
        painter.drawText(song_rect, Qt.AlignmentFlag.AlignCenter, display_song)
        
        # Artist name (closer to song name)
        painter.setPen(QColor(160, 160, 160))
        font = QFont("Arial", 9)
        painter.setFont(font)
        artist_rect = QRectF(0, text_y_base + 16, width, 18)
        
        # Truncate long artist names
        display_artist = self.artist_name
        if len(display_artist) > 35:
            display_artist = display_artist[:34] + "..."
        painter.drawText(artist_rect, Qt.AlignmentFlag.AlignCenter, display_artist)
    
    def mousePressEvent(self, event):
        """Handle clicks on the play button."""
        width = self.width()
        height = self.height()
        text_area_height = 40
        vinyl_area_height = height - text_area_height
        center_x = width / 2
        center_y = vinyl_area_height / 2
        
        # Check if click is within play button area
        dx = event.pos().x() - center_x
        dy = event.pos().y() - center_y
        distance = (dx * dx + dy * dy) ** 0.5
        
        if distance < 35:  # Play button radius
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
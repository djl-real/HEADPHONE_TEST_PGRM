import os
import soundfile as sf
import mutagen
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QPushButton, QLabel, QApplication
from PyQt6.QtCore import Qt, QMimeData, QPoint, QSize
from PyQt6.QtGui import QDrag, QFontDatabase, QPixmap, QPainter, QColor, QFont, QBrush, QPen

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a")


class DraggableListWidget(QListWidget):
    """Custom QListWidget with styled drag support."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self.drag_enabled_mode = False
        self.playlist_ref = None  # Reference to parent Playlist for metadata access
    
    def set_drag_enabled_mode(self, enabled):
        """Enable or disable drag functionality."""
        self.drag_enabled_mode = enabled
    
    def set_playlist_ref(self, playlist):
        """Set reference to parent playlist for metadata access."""
        self.playlist_ref = playlist
    
    def startDrag(self, supportedActions):
        """Start drag operation with styled preview."""
        if not self.drag_enabled_mode:
            return
        
        item = self.currentItem()
        if not item:
            return
        
        index = self.currentRow()
        
        # Get song metadata for the drag preview
        song_title = "Song"
        song_artist = "Artist"
        if self.playlist_ref and index < len(self.playlist_ref.song_metadata):
            meta = self.playlist_ref.song_metadata[index]
            song_title = meta.get('title', 'Unknown')[:20]
            song_artist = meta.get('artist', 'Unknown')[:20]
        
        # Create styled drag pixmap
        drag_pixmap = self._create_drag_pixmap(song_title, song_artist)
        
        # Setup drag
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(str(index))
        mime_data.setData("application/x-song-index", str(index).encode())
        drag.setMimeData(mime_data)
        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(QPoint(drag_pixmap.width() // 2, drag_pixmap.height() // 2))
        
        # Execute drag
        drag.exec(Qt.DropAction.CopyAction)
    
    def _create_drag_pixmap(self, title, artist):
        """Create a styled pixmap for the drag preview."""
        # Dimensions
        width = 180
        height = 60
        
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw rounded rectangle background
        painter.setPen(QPen(QColor(74, 144, 226), 2))
        painter.setBrush(QBrush(QColor(40, 40, 40, 230)))
        painter.drawRoundedRect(2, 2, width - 4, height - 4, 10, 10)
        
        # Draw music note icon
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(74, 144, 226)))
        painter.drawEllipse(12, 35, 12, 12)
        painter.drawRect(22, 15, 3, 25)
        painter.drawRect(22, 12, 12, 6)
        
        # Draw title
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 11, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(40, 28, title)
        
        # Draw artist
        painter.setPen(QColor(180, 180, 180))
        font = QFont("Arial", 9)
        painter.setFont(font)
        painter.drawText(40, 45, artist)
        
        painter.end()
        return pixmap


class Playlist(QWidget):
    """Playlist widget with folder selection, drag-and-drop support, and navigation."""
    
    def __init__(self, playlists_base_dir, parent=None):
        super().__init__(parent)
        
        self.playlists_base_dir = playlists_base_dir
        os.makedirs(playlists_base_dir, exist_ok=True)
        
        # State
        self.current_mode = "folders"  # "folders" or "songs"
        self.current_playlist_path = None
        self.current_playlist_name = None
        
        # Data storage
        self.song_names = []
        self.song_metadata = []
        
        # Setup UI
        self.setup_ui()
        
        # Load folder list initially
        self.show_folder_list()
    
    def setup_ui(self):
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Header label
        self.header_label = QLabel("📁 Playlists")
        self.header_label.setStyleSheet("""
            QLabel {
                color: #4a90e2;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 8px;
                background-color: #1a1a1a;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.header_label)
        
        # List widget
        self.list_widget = DraggableListWidget()
        self.list_widget.set_playlist_ref(self)
        
        # Styling
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(11)
        self.list_widget.setFont(mono_font)
        self.list_widget.setMinimumWidth(350)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #2c2c2c;
                border: 1px solid #444;
                border-radius: 6px;
                color: white;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 4px;
                margin: 2px 4px;
            }
            QListWidget::item:hover {
                background-color: #3c3c3c;
            }
            QListWidget::item:selected {
                background-color: #4a90e2;
            }
        """)
        
        # Connect item click
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        layout.addWidget(self.list_widget)
        
        # Hint label for drag instruction
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 10px;
                font-style: italic;
                padding: 2px 8px;
            }
        """)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint_label)
        
        # Back button (hidden initially)
        self.back_button = QPushButton("← Back")
        self.back_button.setFixedHeight(32)
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 6px;
                border: 1px solid #555;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #4a90e2;
            }
        """)
        self.back_button.clicked.connect(self.go_back)
        self.back_button.hide()
        layout.addWidget(self.back_button)
    
    def show_folder_list(self):
        """Show list of playlist folders."""
        self.current_mode = "folders"
        self.list_widget.clear()
        self.folder_names = []  # Store actual folder names for lookup
        
        # Update header
        self.header_label.setText("Playlists")
        
        # Disable dragging in folder mode
        self.list_widget.set_drag_enabled_mode(False)
        
        # Hide back button and hint
        self.back_button.hide()
        self.hint_label.setText("")
        
        # Get all subdirectories
        try:
            folders = [f for f in sorted(os.listdir(self.playlists_base_dir)) 
                      if os.path.isdir(os.path.join(self.playlists_base_dir, f))]
            
            for folder in folders:
                # Count songs in folder
                folder_path = os.path.join(self.playlists_base_dir, folder)
                song_count = len([f for f in os.listdir(folder_path) 
                                 if f.lower().endswith(AUDIO_EXTENSIONS)])
                self.folder_names.append(folder)
                self.list_widget.addItem(f"{folder} ({song_count} songs)")
            
            if not folders:
                self.list_widget.addItem("No playlists found")
        except Exception as e:
            print(f"[Playlist] Error loading folders: {e}")
            self.list_widget.addItem("Error loading playlists")
    
    def show_song_list(self, playlist_name):
        """Show songs in a playlist folder."""
        self.current_mode = "songs"
        self.current_playlist_name = playlist_name
        self.current_playlist_path = os.path.join(self.playlists_base_dir, playlist_name)
        
        # Update header
        self.header_label.setText(playlist_name)
        
        # Enable dragging in songs mode
        self.list_widget.set_drag_enabled_mode(True)
        
        # Show back button and hint
        self.back_button.show()
        self.hint_label.setText("Drag songs to the vinyl record to load them")
        
        # Load songs
        self.load_songs()
    
    def load_songs(self):
        """Load and display songs from current playlist path."""
        self.list_widget.clear()
        self.song_names.clear()
        self.song_metadata.clear()
        
        if not os.path.exists(self.current_playlist_path):
            os.makedirs(self.current_playlist_path)
            self.list_widget.addItem("No songs in this playlist")
            return
        
        MAX_TITLE_LEN = 15
        MAX_ARTIST_LEN = 15
        
        for fname in sorted(os.listdir(self.current_playlist_path)):
            if fname.lower().endswith(AUDIO_EXTENSIONS):
                path = os.path.join(self.current_playlist_path, fname)
                try:
                    title = os.path.splitext(fname)[0]
                    artist = "Unknown Artist"
                    length_seconds = 0
                    
                    # Extract metadata
                    try:
                        meta = mutagen.File(path, easy=True)
                        if meta:
                            title = meta.get("title", [title])[0]
                            artist = meta.get("artist", [artist])[0]
                            if hasattr(meta, "info") and hasattr(meta.info, "length"):
                                length_seconds = int(meta.info.length)
                    except Exception:
                        pass
                    
                    # Fallback: compute duration from audio file
                    if length_seconds == 0:
                        try:
                            with sf.SoundFile(path) as f:
                                length_seconds = int(len(f) / f.samplerate)
                        except Exception:
                            length_seconds = 0
                    
                    # Store metadata
                    self.song_metadata.append({
                        'title': title,
                        'artist': artist,
                        'length': length_seconds,
                        'path': path,
                        'filename': fname
                    })
                    self.song_names.append(fname)
                    
                    # Create display text
                    display_title = (title.strip()[:MAX_TITLE_LEN-1] + "…") if len(title) > MAX_TITLE_LEN else title.ljust(MAX_TITLE_LEN)
                    display_artist = (artist.strip()[:MAX_ARTIST_LEN-1] + "…") if len(artist) > MAX_ARTIST_LEN else artist.ljust(MAX_ARTIST_LEN)
                    mins, secs = divmod(length_seconds, 60)
                    duration = f"{mins:02d}:{secs:02d}"
                    display_text = f"{display_title} {display_artist} {duration}"
                    
                    self.list_widget.addItem(display_text)
                    
                except Exception as e:
                    print(f"[Playlist] Failed to scan {fname}: {e}")
        
        if not self.song_names:
            self.list_widget.addItem("No songs found")
        else:
            print(f"[Playlist] Loaded {len(self.song_names)} songs")
    
    def on_item_clicked(self, item):
        """Handle single click - only navigates folders."""
        pass  # Single click just selects, doesn't navigate
    
    def on_item_double_clicked(self, item):
        """Handle double click - load playlist if in folder mode."""
        if self.current_mode == "folders":
            index = self.list_widget.currentRow()
            if hasattr(self, 'folder_names') and 0 <= index < len(self.folder_names):
                playlist_name = self.folder_names[index]
                self.show_song_list(playlist_name)
    
    def go_back(self):
        """Go back to folder list."""
        self.show_folder_list()
    
    def get_song_path(self, index):
        """Get the full path of a song by index."""
        if 0 <= index < len(self.song_metadata):
            return self.song_metadata[index]['path']
        return None
    
    def get_song_metadata(self, index):
        """Get metadata for a song by index."""
        if 0 <= index < len(self.song_metadata):
            return self.song_metadata[index]
        return None
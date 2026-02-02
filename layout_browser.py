# layout_browser.py
"""
Layout Browser - A popup panel for browsing, loading, and adding layouts.

Features:
- Favorites and recent history sections
- Real-time search filtering
- Collapsible folder-based categories
- Load or Add layout options
"""

import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame, QLabel, QGraphicsDropShadowEffect,
    QApplication, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QCursor, QAction

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class LayoutInfo:
    """Metadata about a discovered layout file."""
    name: str           # Display name (filename without extension)
    file_path: Path     # Full path to the .layout file
    category: str       # Category based on folder structure
    
    def get_display_name(self) -> str:
        """Get a formatted display name."""
        return self.name.replace('_', ' ').replace('-', ' ')


class LayoutScanner:
    """Scans a directory for .layout files and organizes by folder structure."""
    
    def __init__(self, layouts_dir: str = "layouts"):
        self.layouts_dir = Path(layouts_dir)
        self.layouts: Dict[str, LayoutInfo] = {}
        self._scanned = False
        
    def scan(self, force: bool = False) -> Dict[str, LayoutInfo]:
        """Scan the layouts directory for .layout files."""
        if self._scanned and not force:
            return self.layouts
            
        self.layouts.clear()
        
        if not self.layouts_dir.exists():
            return self.layouts
            
        self._scan_directory(self.layouts_dir, [])
        self._scanned = True
        
        return self.layouts
    
    def _scan_directory(self, directory: Path, category_parts: List[str]):
        """Recursively scan a directory for layout files."""
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return
            
        for entry in entries:
            # Skip hidden files and directories
            if entry.name.startswith('.'):
                continue
                
            if entry.is_dir():
                # Recurse into subdirectory
                new_category = category_parts + [self._format_category_name(entry.name)]
                self._scan_directory(entry, new_category)
                
            elif entry.suffix == '.layout':
                self._register_layout(entry, category_parts)
    
    def _format_category_name(self, folder_name: str) -> str:
        """Convert folder name to display category name."""
        name = folder_name.replace('_', ' ').replace('-', ' ')
        return name.title()
    
    def _register_layout(self, file_path: Path, category_parts: List[str]):
        """Register a discovered layout file."""
        name = file_path.stem  # Filename without extension
        category = "/".join(category_parts) if category_parts else "Uncategorized"
        
        info = LayoutInfo(
            name=name,
            file_path=file_path,
            category=category
        )
        
        self.layouts[name] = info
    
    def get_categories(self) -> List[str]:
        """Get list of all unique categories."""
        categories = set()
        for info in self.layouts.values():
            categories.add(info.category)
        return sorted(categories)
    
    def get_layouts_in_category(self, category: str) -> List[LayoutInfo]:
        """Get all layouts in a specific category."""
        return sorted(
            [info for info in self.layouts.values() if info.category == category],
            key=lambda x: x.name.lower()
        )
    
    def search(self, query: str) -> List[LayoutInfo]:
        """Search layouts by name."""
        query_lower = query.lower()
        return sorted(
            [info for info in self.layouts.values() if query_lower in info.name.lower()],
            key=lambda x: x.name.lower()
        )
    
    def get_layout(self, name: str) -> Optional[LayoutInfo]:
        """Get a specific layout by name."""
        return self.layouts.get(name)


class LayoutButton(QPushButton):
    """A styled button representing a layout in the browser."""
    
    favoriteToggled = pyqtSignal(str, bool)  # layout_name, is_favorite
    loadRequested = pyqtSignal(str)   # layout_name
    addRequested = pyqtSignal(str)    # layout_name
    
    def __init__(self, layout_info: LayoutInfo, is_favorite: bool = False,
                 compact: bool = False, parent=None):
        super().__init__(parent)
        self.layout_info = layout_info
        self._is_favorite = is_favorite
        self._compact = compact
        
        self.setText(layout_info.get_display_name())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        self._apply_style()
        
    def _apply_style(self):
        """Apply visual styling based on state."""
        if self._compact:
            padding = "5px 10px"
            font_size = "12px"
            min_height = "24px"
            border_radius = "6px"
        else:
            padding = "6px 12px"
            font_size = "12px"
            min_height = "26px"
            border_radius = "6px"
        
        favorite_indicator = "[*] " if self._is_favorite else ""
        if self._is_favorite and not self._compact:
            self.setText(f"{favorite_indicator}{self.layout_info.get_display_name()}")
        else:
            self.setText(self.layout_info.get_display_name())
        
        base_bg = "rgba(55, 65, 60, 0.9)" if not self._is_favorite else "rgba(70, 60, 45, 0.9)"
        hover_bg = "rgba(75, 85, 80, 0.95)" if not self._is_favorite else "rgba(90, 75, 50, 0.95)"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {base_bg};
                color: #e0e0e0;
                border: 1px solid rgba(100, 100, 105, 0.5);
                border-radius: {border_radius};
                padding: {padding};
                font-size: {font_size};
                font-weight: 500;
                text-align: left;
                min-height: {min_height};
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: rgba(140, 140, 145, 0.7);
            }}
            QPushButton:pressed {{
                background-color: rgba(50, 50, 55, 0.95);
            }}
        """)
        
    def set_favorite(self, is_favorite: bool):
        """Update favorite status and restyle."""
        self._is_favorite = is_favorite
        self._apply_style()
        
    def _on_context_menu(self, pos):
        """Handle right-click context menu."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 45, 0.98);
                border: 1px solid rgba(70, 70, 75, 0.8);
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
                color: #e0e0e0;
                border-radius: 4px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: rgba(80, 80, 85, 0.9);
            }
        """)
        
        # Add action (default)
        add_action = QAction("Add to Current", self)
        add_action.triggered.connect(lambda: self.addRequested.emit(self.layout_info.name))
        menu.addAction(add_action)
        
        # Load action
        load_action = QAction("Load (Replace)", self)
        load_action.triggered.connect(lambda: self.loadRequested.emit(self.layout_info.name))
        menu.addAction(load_action)
        
        menu.addSeparator()
        
        # Favorite toggle
        fav_text = "Remove from Favorites" if self._is_favorite else "Add to Favorites"
        fav_action = QAction(fav_text, self)
        fav_action.triggered.connect(self._toggle_favorite)
        menu.addAction(fav_action)
        
        menu.exec(self.mapToGlobal(pos))
        
    def _toggle_favorite(self):
        """Toggle favorite status."""
        self._is_favorite = not self._is_favorite
        self._apply_style()
        self.favoriteToggled.emit(self.layout_info.name, self._is_favorite)


class LayoutQuickAccessBar(QWidget):
    """Widget showing favorites and recent history as separate sections."""
    
    layoutClicked = pyqtSignal(str)  # layout_name
    favoriteToggled = pyqtSignal(str, bool)
    loadRequested = pyqtSignal(str)
    addRequested = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        
        self._buttons: Dict[str, LayoutButton] = {}
        self._layout_scanner = None
        
        # Favorites section
        self._favorites_label = QLabel("Favorites")
        self._favorites_label.setStyleSheet("""
            QLabel {
                color: rgba(180, 180, 185, 0.8);
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
        """)
        self._layout.addWidget(self._favorites_label)
        
        self._favorites_container = QWidget()
        self._favorites_layout = QHBoxLayout(self._favorites_container)
        self._favorites_layout.setContentsMargins(0, 0, 0, 0)
        self._favorites_layout.setSpacing(4)
        self._favorites_layout.addStretch()
        self._layout.addWidget(self._favorites_container)
        
        self._favorites_placeholder = QLabel("No favorites yet")
        self._favorites_placeholder.setStyleSheet("""
            QLabel {
                color: rgba(120, 120, 125, 0.6);
                font-size: 11px;
                font-style: italic;
                padding: 2px 0;
            }
        """)
        self._favorites_layout.insertWidget(0, self._favorites_placeholder)
        
        # History section
        self._history_label = QLabel("Recent")
        self._history_label.setStyleSheet("""
            QLabel {
                color: rgba(180, 180, 185, 0.8);
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
        """)
        self._layout.addWidget(self._history_label)
        
        self._history_container = QWidget()
        self._history_layout = QHBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(4)
        self._history_layout.addStretch()
        self._layout.addWidget(self._history_container)
        
        self._history_placeholder = QLabel("No recent layouts")
        self._history_placeholder.setStyleSheet("""
            QLabel {
                color: rgba(120, 120, 125, 0.6);
                font-size: 11px;
                font-style: italic;
                padding: 2px 0;
            }
        """)
        self._history_layout.insertWidget(0, self._history_placeholder)
        
    def set_scanner(self, scanner: LayoutScanner):
        """Set the layout scanner for lookups."""
        self._layout_scanner = scanner
        
    def update_layouts(self, favorites: List[str], history: List[str]):
        """Update the quick access sections."""
        # Clear existing buttons
        for btn in self._buttons.values():
            btn.deleteLater()
        self._buttons.clear()
        
        if not self._layout_scanner:
            return
        
        # Update favorites section
        valid_favorites = []
        for name in favorites:
            info = self._layout_scanner.get_layout(name)
            if info:
                valid_favorites.append(name)
                
        self._favorites_placeholder.setVisible(len(valid_favorites) == 0)
        for name in valid_favorites:
            info = self._layout_scanner.get_layout(name)
            if info:
                btn = LayoutButton(info, is_favorite=True, compact=True)
                btn.clicked.connect(lambda checked, n=name: self.layoutClicked.emit(n))
                btn.favoriteToggled.connect(self.favoriteToggled.emit)
                btn.loadRequested.connect(self.loadRequested.emit)
                btn.addRequested.connect(self.addRequested.emit)
                self._buttons[f"fav_{name}"] = btn
                self._favorites_layout.insertWidget(self._favorites_layout.count() - 1, btn)
        
        # Update history section (exclude favorites)
        history_filtered = [h for h in history if h not in favorites][:6]
        valid_history = []
        for name in history_filtered:
            info = self._layout_scanner.get_layout(name)
            if info:
                valid_history.append(name)
                
        self._history_placeholder.setVisible(len(valid_history) == 0)
        for name in valid_history:
            info = self._layout_scanner.get_layout(name)
            if info:
                btn = LayoutButton(info, is_favorite=False, compact=True)
                btn.clicked.connect(lambda checked, n=name: self.layoutClicked.emit(n))
                btn.favoriteToggled.connect(self.favoriteToggled.emit)
                btn.loadRequested.connect(self.loadRequested.emit)
                btn.addRequested.connect(self.addRequested.emit)
                self._buttons[f"hist_{name}"] = btn
                self._history_layout.insertWidget(self._history_layout.count() - 1, btn)


class LayoutCategorySection(QWidget):
    """A collapsible section showing layouts in a category."""
    
    layoutClicked = pyqtSignal(str)
    favoriteToggled = pyqtSignal(str, bool)
    loadRequested = pyqtSignal(str)
    addRequested = pyqtSignal(str)
    
    def __init__(self, category_name: str, layouts: List[LayoutInfo],
                 favorites: List[str], parent=None):
        super().__init__(parent)
        self._category_name = category_name
        self._layouts = layouts
        self._favorites = favorites
        self._expanded = False  # Start collapsed
        self._buttons: List[LayoutButton] = []
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)
        
        # Header button
        self._header = QPushButton(f">  {self._category_name}")
        self._header.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #b0b0b5;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
                text-align: left;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.05);
                color: #d0d0d5;
            }
        """)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle_expanded)
        layout.addWidget(self._header)
        
        # Content container - starts hidden
        self._content = QWidget()
        self._content.setVisible(False)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(6, 0, 0, 0)
        content_layout.setSpacing(2)
        
        # Sort layouts: favorites first, then alphabetical
        sorted_layouts = sorted(
            self._layouts,
            key=lambda l: (0 if l.name in self._favorites else 1, l.name.lower())
        )
        
        for layout_info in sorted_layouts:
            is_fav = layout_info.name in self._favorites
            btn = LayoutButton(layout_info, is_favorite=is_fav)
            btn.clicked.connect(lambda checked, n=layout_info.name: self.layoutClicked.emit(n))
            btn.favoriteToggled.connect(self._on_favorite_toggled)
            btn.loadRequested.connect(self.loadRequested.emit)
            btn.addRequested.connect(self.addRequested.emit)
            self._buttons.append(btn)
            content_layout.addWidget(btn)
            
        layout.addWidget(self._content)
        
    def _on_favorite_toggled(self, name: str, is_favorite: bool):
        """Handle favorite toggle from a button."""
        if is_favorite:
            self._favorites.append(name)
        elif name in self._favorites:
            self._favorites.remove(name)
        self.favoriteToggled.emit(name, is_favorite)
        
    def _toggle_expanded(self):
        """Toggle the expanded/collapsed state."""
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        arrow = "v" if self._expanded else ">"
        self._header.setText(f"{arrow}  {self._category_name}")
        
    def update_favorites(self, favorites: List[str]):
        """Update favorite status for all buttons."""
        self._favorites = favorites
        for btn in self._buttons:
            btn.set_favorite(btn.layout_info.name in favorites)
            
    def filter_layouts(self, query: str) -> int:
        """Filter layouts by search query."""
        query_lower = query.lower()
        visible_count = 0
        
        for btn in self._buttons:
            matches = query_lower in btn.layout_info.name.lower()
            btn.setVisible(matches)
            if matches:
                visible_count += 1
                
        self.setVisible(visible_count > 0 or query == "")
        
        if query and visible_count > 0 and not self._expanded:
            self._toggle_expanded()
            
        return visible_count


class LayoutUsageTracker:
    """Tracks layout usage statistics and favorites."""
    
    def __init__(self, config_path: Optional[str] = None):
        import json
        from pathlib import Path
        from datetime import datetime
        
        self._json = json
        self._datetime = datetime
        
        if config_path:
            self.config_path = Path(config_path)
        else:
            home = Path.home()
            self.config_path = home / ".config" / "audio_modules" / "layout_usage.json"
            
        self.usage_data: Dict[str, dict] = {}
        self._load()
    
    def _ensure_config_dir(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        if not self.config_path.exists():
            return
            
        try:
            with open(self.config_path, 'r') as f:
                data = self._json.load(f)
            self.usage_data = data.get('layouts', {})
        except Exception:
            pass
    
    def _save(self):
        try:
            self._ensure_config_dir()
            data = {'version': 1, 'layouts': self.usage_data}
            with open(self.config_path, 'w') as f:
                self._json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def record_use(self, layout_name: str):
        """Record that a layout was used."""
        if layout_name not in self.usage_data:
            self.usage_data[layout_name] = {'use_count': 0, 'is_favorite': False}
        self.usage_data[layout_name]['use_count'] = self.usage_data[layout_name].get('use_count', 0) + 1
        self.usage_data[layout_name]['last_used'] = self._datetime.now().isoformat()
        self._save()
    
    def set_favorite(self, layout_name: str, is_favorite: bool):
        """Set favorite status for a layout."""
        if layout_name not in self.usage_data:
            self.usage_data[layout_name] = {'use_count': 0, 'is_favorite': False}
        self.usage_data[layout_name]['is_favorite'] = is_favorite
        self._save()
    
    def get_favorites(self) -> List[str]:
        """Get list of favorited layout names."""
        return [name for name, data in self.usage_data.items() if data.get('is_favorite', False)]
    
    def get_recently_used(self, max_count: int = 10) -> List[str]:
        """Get list of recently used layouts."""
        with_timestamps = [
            (name, data.get('last_used', ''))
            for name, data in self.usage_data.items()
            if data.get('last_used')
        ]
        with_timestamps.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in with_timestamps[:max_count]]


class LayoutBrowser(QWidget):
    """Main layout browser popup panel."""
    
    layoutLoaded = pyqtSignal(str)   # layout_path
    layoutAdded = pyqtSignal(str)    # layout_path
    saveRequested = pyqtSignal()     # request to save current layout
    closed = pyqtSignal()
    
    PANEL_WIDTH = 400
    PANEL_MAX_HEIGHT = 650
    
    def __init__(self, layouts_dir: str = "layouts", parent=None):
        super().__init__(parent)
        self._layouts_dir = layouts_dir
        self._layout_scanner = LayoutScanner(layouts_dir)
        self._usage_tracker = LayoutUsageTracker()
        self._category_sections: List[LayoutCategorySection] = []
        
        self.setWindowFlags(
            Qt.WindowType.Popup |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._setup_ui()
        self._apply_shadow()
        
    def _setup_ui(self):
        # Main container
        self._container = QFrame(self)
        self._container.setObjectName("browserContainer")
        self._container.setStyleSheet("""
            #browserContainer {
                background-color: rgba(35, 35, 40, 0.98);
                border: 1px solid rgba(80, 80, 85, 0.8);
                border-radius: 12px;
            }
        """)
        
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(6)
        
        # Title row with save button
        title_row = QWidget()
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        
        title = QLabel("Layouts")
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 600;
            }
        """)
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        # Save button
        save_button = QPushButton("Save Current")
        save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        save_button.clicked.connect(self._on_save_clicked)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 75, 60, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(80, 100, 80, 0.6);
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(70, 90, 70, 0.95);
                border-color: rgba(100, 130, 100, 0.8);
            }
            QPushButton:pressed {
                background-color: rgba(50, 65, 50, 0.95);
            }
        """)
        title_layout.addWidget(save_button)
        
        container_layout.addWidget(title_row)
        
        # Quick access section
        self._quick_access = LayoutQuickAccessBar()
        self._quick_access.layoutClicked.connect(self._on_layout_clicked)
        self._quick_access.favoriteToggled.connect(self._on_favorite_toggled)
        self._quick_access.loadRequested.connect(self._on_load_requested)
        self._quick_access.addRequested.connect(self._on_add_requested)
        container_layout.addWidget(self._quick_access)
        
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: rgba(100, 100, 105, 0.3);")
        divider.setFixedHeight(1)
        container_layout.addWidget(divider)
        
        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search layouts...")
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(50, 50, 55, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(80, 80, 85, 0.6);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: rgba(120, 120, 130, 0.8);
                background-color: rgba(55, 55, 60, 0.95);
            }
            QLineEdit::placeholder {
                color: rgba(150, 150, 155, 0.6);
            }
        """)
        container_layout.addWidget(self._search_input)
        
        # Categories label
        categories_label = QLabel("Folders")
        categories_label.setStyleSheet("""
            QLabel {
                color: rgba(180, 180, 185, 0.8);
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
                padding-top: 2px;
            }
        """)
        container_layout.addWidget(categories_label)
        
        # Scrollable category area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: rgba(50, 50, 55, 0.5);
                width: 8px;
                border-radius: 4px;
                margin: 4px 2px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(100, 100, 105, 0.7);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(130, 130, 135, 0.8);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self._categories_widget = QWidget()
        self._categories_layout = QVBoxLayout(self._categories_widget)
        self._categories_layout.setContentsMargins(0, 0, 0, 0)
        self._categories_layout.setSpacing(2)
        self._categories_layout.addStretch()
        
        scroll.setWidget(self._categories_widget)
        container_layout.addWidget(scroll, 1)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(self._container)
        
        self.setFixedWidth(self.PANEL_WIDTH + 8)
        self.setFixedHeight(self.PANEL_MAX_HEIGHT + 8)
        
    def _apply_shadow(self):
        """Add drop shadow effect to the panel."""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self._container.setGraphicsEffect(shadow)
        
    def refresh(self):
        """Rescan layouts directory and rebuild UI."""
        self._layout_scanner.scan(force=True)
        self._quick_access.set_scanner(self._layout_scanner)
        self._rebuild_categories()
        self._update_quick_access()
        
    def _rebuild_categories(self):
        """Rebuild the category sections from the scanner."""
        for section in self._category_sections:
            section.deleteLater()
        self._category_sections.clear()
        
        favorites = self._usage_tracker.get_favorites()
        
        for category in self._layout_scanner.get_categories():
            layouts = self._layout_scanner.get_layouts_in_category(category)
            if layouts:
                section = LayoutCategorySection(category, layouts, favorites)
                section.layoutClicked.connect(self._on_layout_clicked)
                section.favoriteToggled.connect(self._on_favorite_toggled)
                section.loadRequested.connect(self._on_load_requested)
                section.addRequested.connect(self._on_add_requested)
                self._category_sections.append(section)
                self._categories_layout.insertWidget(
                    self._categories_layout.count() - 1, section
                )
                
    def _update_quick_access(self):
        """Update the quick access bar."""
        favorites = self._usage_tracker.get_favorites()
        history = self._usage_tracker.get_recently_used()
        self._quick_access.update_layouts(favorites, history)
        
    def _on_layout_clicked(self, layout_name: str):
        """Handle layout button click (default: add to current)."""
        self._on_add_requested(layout_name)
        
    def _on_load_requested(self, layout_name: str):
        """Handle load request."""
        info = self._layout_scanner.get_layout(layout_name)
        if info:
            self._usage_tracker.record_use(layout_name)
            self.layoutLoaded.emit(str(info.file_path))
            self.close()
            
    def _on_add_requested(self, layout_name: str):
        """Handle add request."""
        info = self._layout_scanner.get_layout(layout_name)
        if info:
            self._usage_tracker.record_use(layout_name)
            self.layoutAdded.emit(str(info.file_path))
            self.close()
    
    def _on_save_clicked(self):
        """Handle save button click."""
        self.saveRequested.emit()
        self.close()
            
    def _on_favorite_toggled(self, layout_name: str, is_favorite: bool):
        """Handle favorite toggle."""
        self._usage_tracker.set_favorite(layout_name, is_favorite)
        self._update_quick_access()
        
    def _on_search_changed(self, text: str):
        """Handle search input changes."""
        for section in self._category_sections:
            section.filter_layouts(text)
            
    def show_at(self, global_pos: QPoint):
        """Show the browser at a specific screen position."""
        # Refresh layouts before showing
        self.refresh()
        
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            
            panel_width = self.width()
            panel_height = self.height()
            
            x = global_pos.x()
            if x + panel_width > screen_rect.right():
                x = screen_rect.right() - panel_width - 10
            if x < screen_rect.left():
                x = screen_rect.left() + 10
                
            y = global_pos.y()
            if y + panel_height > screen_rect.bottom():
                y = global_pos.y() - panel_height - 10
            if y < screen_rect.top():
                y = screen_rect.top() + 10
                
            self.move(x, y)
            
        self.show()
        self._search_input.setFocus()
        self._search_input.clear()
        
        for section in self._category_sections:
            section.filter_layouts("")
            
    def show_below(self, widget: QWidget):
        """Show the browser below a widget."""
        global_pos = widget.mapToGlobal(QPoint(0, widget.height()))
        self.show_at(global_pos)
        
    def closeEvent(self, event):
        """Handle panel close."""
        self.closed.emit()
        super().closeEvent(event)
        
    def keyPressEvent(self, event):
        """Handle key presses."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
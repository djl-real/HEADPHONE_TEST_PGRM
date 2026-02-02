# module_browser.py
"""
Module Browser - A popup panel for browsing and spawning audio modules.

Features:
- Quick access bar for frequently used modules
- Real-time search filtering
- Collapsible category accordion
- Favorites/pinning support
- Smooth animations and polished aesthetics
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame, QLabel, QGraphicsDropShadowEffect,
    QSizePolicy, QApplication
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize,
    QTimer, QPoint, QEvent
)
from PyQt6.QtGui import QFont, QColor, QIcon, QPalette, QCursor

from typing import Dict, List, Callable, Optional
from module_scanner import ModuleInfo, ManualModuleRegistry


class ModuleButton(QPushButton):
    """
    A styled button representing a module in the browser.
    Supports right-click for favorites toggle.
    """
    
    favoriteToggled = pyqtSignal(str, bool)  # module_name, is_favorite
    
    def __init__(self, module_info: ModuleInfo, is_favorite: bool = False, 
                 compact: bool = False, parent=None):
        super().__init__(parent)
        self.module_info = module_info
        self._is_favorite = is_favorite
        self._compact = compact
        
        self.setText(module_info.name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        self._apply_style()
        
    def _apply_style(self):
        """Apply visual styling based on state."""
        if self._compact:
            # Compact style for quick access bar
            padding = "5px 10px"
            font_size = "12px"
            min_height = "24px"
            border_radius = "6px"
        else:
            # Compact style for category lists
            padding = "6px 12px"
            font_size = "12px"
            min_height = "26px"
            border_radius = "6px"
        
        favorite_indicator = "[*] " if self._is_favorite else ""
        if self._is_favorite and not self._compact:
            self.setText(f"{favorite_indicator}{self.module_info.name}")
        else:
            self.setText(self.module_info.name)
        
        base_bg = "rgba(60, 60, 65, 0.9)" if not self._is_favorite else "rgba(70, 60, 45, 0.9)"
        hover_bg = "rgba(80, 80, 85, 0.95)" if not self._is_favorite else "rgba(90, 75, 50, 0.95)"
        
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
        """Handle right-click to toggle favorite."""
        self._is_favorite = not self._is_favorite
        self._apply_style()
        self.favoriteToggled.emit(self.module_info.name, self._is_favorite)


class QuickAccessBar(QWidget):
    """
    Widget showing favorites and recent history as separate sections.
    """
    
    moduleClicked = pyqtSignal(str)  # module_name
    favoriteToggled = pyqtSignal(str, bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        
        self._buttons: Dict[str, ModuleButton] = {}
        self._module_registry = None
        
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
        
        self._history_placeholder = QLabel("No recent modules")
        self._history_placeholder.setStyleSheet("""
            QLabel {
                color: rgba(120, 120, 125, 0.6);
                font-size: 11px;
                font-style: italic;
                padding: 2px 0;
            }
        """)
        self._history_layout.insertWidget(0, self._history_placeholder)
        
    def set_registry(self, registry):
        """Set the module registry for lookups."""
        self._module_registry = registry
        
    def update_modules(self, favorites: List[str], history: List[str]):
        """
        Update the quick access sections.
        
        Args:
            favorites: List of favorited module names
            history: List of recently used module names (excluding favorites)
        """
        # Clear existing buttons
        for btn in self._buttons.values():
            btn.deleteLater()
        self._buttons.clear()
        
        if not self._module_registry:
            return
        
        # Update favorites section
        self._favorites_placeholder.setVisible(len(favorites) == 0)
        for name in favorites:
            info = self._module_registry.get_module(name)
            if info:
                btn = ModuleButton(info, is_favorite=True, compact=True)
                btn.clicked.connect(lambda checked, n=name: self.moduleClicked.emit(n))
                btn.favoriteToggled.connect(self.favoriteToggled.emit)
                self._buttons[f"fav_{name}"] = btn
                self._favorites_layout.insertWidget(self._favorites_layout.count() - 1, btn)
        
        # Update history section (exclude favorites)
        history_filtered = [h for h in history if h not in favorites][:6]
        self._history_placeholder.setVisible(len(history_filtered) == 0)
        for name in history_filtered:
            info = self._module_registry.get_module(name)
            if info:
                btn = ModuleButton(info, is_favorite=False, compact=True)
                btn.clicked.connect(lambda checked, n=name: self.moduleClicked.emit(n))
                btn.favoriteToggled.connect(self.favoriteToggled.emit)
                self._buttons[f"hist_{name}"] = btn
                self._history_layout.insertWidget(self._history_layout.count() - 1, btn)


class CategorySection(QWidget):
    """
    A collapsible section showing modules in a category.
    """
    
    moduleClicked = pyqtSignal(str)
    favoriteToggled = pyqtSignal(str, bool)
    
    def __init__(self, category_name: str, modules: List[ModuleInfo], 
                 favorites: List[str], parent=None):
        super().__init__(parent)
        self._category_name = category_name
        self._modules = modules
        self._favorites = favorites
        self._expanded = False  # Start collapsed
        self._buttons: List[ModuleButton] = []
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)
        
        # Header button (click to expand/collapse) - starts with collapsed arrow
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
        self._content.setVisible(False)  # Start collapsed
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(6, 0, 0, 0)
        content_layout.setSpacing(2)
        
        # Sort modules: favorites first, then alphabetical
        sorted_modules = sorted(
            self._modules,
            key=lambda m: (0 if m.name in self._favorites else 1, m.name.lower())
        )
        
        for module_info in sorted_modules:
            is_fav = module_info.name in self._favorites
            btn = ModuleButton(module_info, is_favorite=is_fav)
            btn.clicked.connect(lambda checked, n=module_info.name: self.moduleClicked.emit(n))
            btn.favoriteToggled.connect(self._on_favorite_toggled)
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
            btn.set_favorite(btn.module_info.name in favorites)
            
    def filter_modules(self, query: str) -> int:
        """
        Filter modules by search query.
        
        Returns:
            Number of visible modules
        """
        query_lower = query.lower()
        visible_count = 0
        
        for btn in self._buttons:
            matches = query_lower in btn.module_info.name.lower()
            btn.setVisible(matches)
            if matches:
                visible_count += 1
                
        # Hide entire section if no matches
        self.setVisible(visible_count > 0 or query == "")
        
        # Auto-expand if searching and has matches
        if query and visible_count > 0 and not self._expanded:
            self._toggle_expanded()
            
        return visible_count


class ModuleBrowser(QWidget):
    """
    Main module browser popup panel.
    
    Features:
    - Quick access bar at top
    - Search input
    - Scrollable category list
    - Click outside to dismiss
    """
    
    moduleSpawned = pyqtSignal(str)  # module_name
    closed = pyqtSignal()
    
    # Size constants
    PANEL_WIDTH = 400
    PANEL_MAX_HEIGHT = 650
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._module_registry = None
        self._usage_tracker = None
        self._category_sections: List[CategorySection] = []
        
        self.setWindowFlags(
            Qt.WindowType.Popup | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._setup_ui()
        self._apply_shadow()
        
    def _setup_ui(self):
        # Main container with background
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
        
        # Title
        title = QLabel("Modules")
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 600;
            }
        """)
        container_layout.addWidget(title)
        
        # Quick access section (favorites + history)
        self._quick_access = QuickAccessBar()
        self._quick_access.moduleClicked.connect(self._on_module_clicked)
        self._quick_access.favoriteToggled.connect(self._on_favorite_toggled)
        container_layout.addWidget(self._quick_access)
        
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: rgba(100, 100, 105, 0.3);")
        divider.setFixedHeight(1)
        container_layout.addWidget(divider)
        
        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search modules...")
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
        categories_label = QLabel("Categories")
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
        main_layout.setContentsMargins(4, 4, 4, 4)  # Shadow margin
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
        
    def set_registry(self, registry: ManualModuleRegistry):
        """Set the module registry."""
        self._module_registry = registry
        self._quick_access.set_registry(registry)
        self._rebuild_categories()
        
    def set_usage_tracker(self, tracker):
        """Set the usage tracker for quick access and favorites."""
        self._usage_tracker = tracker
        self._update_quick_access()
        self._update_favorites()
        
    def _rebuild_categories(self):
        """Rebuild the category sections from the registry."""
        # Clear existing sections
        for section in self._category_sections:
            section.deleteLater()
        self._category_sections.clear()
        
        if not self._module_registry:
            return
            
        favorites = self._get_favorites()
        
        # Create sections for each category
        for category in self._module_registry.get_categories():
            modules = self._module_registry.get_modules_in_category(category)
            if modules:
                section = CategorySection(category, modules, favorites)
                section.moduleClicked.connect(self._on_module_clicked)
                section.favoriteToggled.connect(self._on_favorite_toggled)
                self._category_sections.append(section)
                # Insert before stretch
                self._categories_layout.insertWidget(
                    self._categories_layout.count() - 1, section
                )
                
    def _get_favorites(self) -> List[str]:
        """Get list of favorite module names."""
        if self._usage_tracker:
            return self._usage_tracker.get_favorites()
        return []
    
    def _update_quick_access(self):
        """Update the quick access bar with favorites and history."""
        if not self._usage_tracker or not self._module_registry:
            return
            
        favorites = self._get_favorites()
        history = self._usage_tracker.get_recently_used(max_count=10)
        self._quick_access.update_modules(favorites, history)
        
    def _update_favorites(self):
        """Update favorite indicators in all sections."""
        favorites = self._get_favorites()
        for section in self._category_sections:
            section.update_favorites(favorites)
            
    def _on_module_clicked(self, module_name: str):
        """Handle module button click."""
        if self._usage_tracker:
            self._usage_tracker.record_spawn(module_name)
            
        self.moduleSpawned.emit(module_name)
        self.close()
        
    def _on_favorite_toggled(self, module_name: str, is_favorite: bool):
        """Handle favorite toggle."""
        if self._usage_tracker:
            self._usage_tracker.set_favorite(module_name, is_favorite)
            self._update_quick_access()
            
    def _on_search_changed(self, text: str):
        """Handle search input changes."""
        for section in self._category_sections:
            section.filter_modules(text)
            
    def show_at(self, global_pos: QPoint):
        """Show the browser at a specific screen position."""
        # Adjust position to stay on screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            
            panel_width = self.width()
            panel_height = self.height()
            
            # Adjust X position
            x = global_pos.x()
            if x + panel_width > screen_rect.right():
                x = screen_rect.right() - panel_width - 10
            if x < screen_rect.left():
                x = screen_rect.left() + 10
                
            # Adjust Y position
            y = global_pos.y()
            if y + panel_height > screen_rect.bottom():
                y = global_pos.y() - panel_height - 10
            if y < screen_rect.top():
                y = screen_rect.top() + 10
                
            self.move(x, y)
            
        self.show()
        self._search_input.setFocus()
        self._search_input.clear()
        
        # Reset search filter
        for section in self._category_sections:
            section.filter_modules("")
            
    def show_below(self, widget: QWidget):
        """Show the browser below a widget (e.g., toolbar button)."""
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
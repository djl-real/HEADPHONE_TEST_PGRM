# toolbar_manager_autodiscover.py
"""
Alternative Toolbar Manager with automatic module discovery.

This version scans the modules directory automatically instead of 
requiring manual imports. Use this when you want new modules to 
appear automatically just by adding .py files to the modules folder.

Usage:
    Replace 'from toolbar_manager import ToolbarManager' with
    'from toolbar_manager_autodiscover import ToolbarManager'
"""

from PyQt6.QtWidgets import (
    QToolBar, QMenu, QToolButton, QFileDialog
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QSize

from module_scanner import ModuleScanner, ManualModuleRegistry
from module_browser import ModuleBrowser
from usage_tracker import UsageTracker


class ToolbarManager:
    """
    Toolbar Manager with automatic module discovery.
    
    Scans the 'modules' directory recursively and automatically
    registers any AudioModule subclasses found. Hidden directories
    (starting with '.') are skipped.
    """

    def __init__(self, main_window, modules_dir: str = "modules"):
        self.main_window = main_window
        self.modules_dir = modules_dir
        self.toolbar = QToolBar("Modules")
        self.main_window.addToolBar(self.toolbar)

        # Touchscreen-friendly scaling
        self.toolbar.setIconSize(QSize(48, 48))
        self.toolbar.setStyleSheet("""
            QToolBar {
                spacing: 12px;
                padding: 8px;
                background-color: rgba(30, 30, 35, 0.95);
                border-bottom: 1px solid rgba(60, 60, 65, 0.8);
            }
            QToolButton {
                min-width: 60px;
                min-height: 30px;
                font-size: 16px;
                padding: 10px 16px;
                border-radius: 10px;
                background-color: rgba(50, 50, 55, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(70, 70, 75, 0.6);
            }
            QToolButton:hover {
                background-color: rgba(70, 70, 75, 0.95);
                border-color: rgba(100, 100, 105, 0.8);
            }
            QToolButton:pressed {
                background-color: rgba(40, 40, 45, 0.95);
            }
        """)

        # Initialize module registry via auto-discovery
        self._init_module_registry()
        
        # Initialize usage tracker
        self.usage_tracker = UsageTracker()
        
        # Create module browser
        self.module_browser = ModuleBrowser()
        self.module_browser.set_registry(self.module_registry)
        self.module_browser.set_usage_tracker(self.usage_tracker)
        self.module_browser.moduleSpawned.connect(self._on_module_spawned)

        # Create toolbar elements
        self._create_file_menu()
        self._create_modules_button()
        self._create_refresh_button()

    def _init_module_registry(self):
        """Initialize module registry by scanning the modules directory."""
        self.module_scanner = ModuleScanner(self.modules_dir)
        
        # Perform initial scan
        discovered = self.module_scanner.scan()
        
        # Convert to ManualModuleRegistry for browser compatibility
        self.module_registry = ManualModuleRegistry()
        
        for name, info in discovered.items():
            self.module_registry.register(
                name=info.name,
                cls=info.class_ref,
                category=info.category
            )
            
        print(f"Auto-discovered {len(discovered)} modules in {len(self.module_scanner.get_categories())} categories")

    def refresh_modules(self):
        """Rescan the modules directory for new modules."""
        self.module_scanner.scan(force=True)
        self._init_module_registry()
        
        # Update browser
        self.module_browser.set_registry(self.module_registry)
        self.module_browser.set_usage_tracker(self.usage_tracker)
        
        print("Module registry refreshed")

    def _create_file_menu(self):
        """Create the File dropdown menu."""
        file_menu = QMenu()
        file_menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 45, 0.98);
                border: 1px solid rgba(70, 70, 75, 0.8);
                border-radius: 10px;
                padding: 8px 4px;
            }
            QMenu::item {
                padding: 10px 20px;
                color: #e0e0e0;
                border-radius: 6px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: rgba(80, 80, 85, 0.9);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(80, 80, 85, 0.5);
                margin: 6px 12px;
            }
        """)

        save_action = QAction("💾  Save Layout", self.main_window)
        save_action.triggered.connect(self.save_layout)
        file_menu.addAction(save_action)

        load_action = QAction("📂  Load Layout", self.main_window)
        load_action.triggered.connect(self.load_layout)
        file_menu.addAction(load_action)

        file_menu.addSeparator()

        add_action = QAction("➕  Add Layout", self.main_window)
        add_action.triggered.connect(self.add_layout)
        file_menu.addAction(add_action)

        button = QToolButton()
        button.setText("File")
        button.setMenu(file_menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addWidget(button)

    def _create_modules_button(self):
        """Create the Modules button that opens the browser."""
        self.modules_button = QToolButton()
        self.modules_button.setText("➕ Modules")
        self.modules_button.setStyleSheet("""
            QToolButton {
                min-width: 100px;
                background-color: rgba(60, 90, 140, 0.9);
                border: 1px solid rgba(80, 110, 160, 0.8);
            }
            QToolButton:hover {
                background-color: rgba(70, 100, 150, 0.95);
                border-color: rgba(100, 130, 180, 0.9);
            }
            QToolButton:pressed {
                background-color: rgba(50, 80, 130, 0.95);
            }
        """)
        self.modules_button.clicked.connect(self._show_module_browser)
        self.toolbar.addWidget(self.modules_button)

    def _create_refresh_button(self):
        """Create a refresh button to rescan modules."""
        self.refresh_button = QToolButton()
        self.refresh_button.setText("🔄")
        self.refresh_button.setToolTip("Refresh module list")
        self.refresh_button.setStyleSheet("""
            QToolButton {
                min-width: 40px;
                background-color: rgba(50, 50, 55, 0.7);
            }
        """)
        self.refresh_button.clicked.connect(self.refresh_modules)
        self.toolbar.addWidget(self.refresh_button)

    def _show_module_browser(self):
        """Show the module browser popup below the modules button."""
        self.module_browser.show_below(self.modules_button)

    def _on_module_spawned(self, module_name: str):
        """Handle module spawn from the browser."""
        self.spawn_module(module_name)

    def spawn_module(self, name: str):
        """
        Creates the backend module and adds its graphical ModuleItem to the scene.
        
        Args:
            name: The display name of the module to spawn
        """
        module_info = self.module_registry.get_module(name)
        
        if module_info is None:
            print(f"Unknown module: {name}")
            return

        try:
            module = module_info.spawn()
            self.main_window.spawn_module(module)
        except Exception as e:
            print(f"Failed to spawn module '{name}': {e}")

    def save_layout(self):
        """Opens file dialog and delegates saving to the main window."""
        file_path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Save Layout",
            "./layouts",
            "Layout Files (*.layout)"
        )
        if file_path:
            if not file_path.endswith(".layout"):
                file_path += ".layout"
            self.main_window.save_layout(file_path)

    def load_layout(self):
        """Opens file dialog and delegates loading to the main window."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Load Layout",
            "./layouts",
            "Layout Files (*.layout)"
        )
        if file_path:
            self.main_window.load_layout(file_path)

    def add_layout(self):
        """Opens file dialog and adds layout to current scene."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Add Layout",
            "./layouts",
            "Layout Files (*.layout)"
        )
        if file_path:
            self.main_window.add_layout(file_path)
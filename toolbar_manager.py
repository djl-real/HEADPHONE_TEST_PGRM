# toolbar_manager.py

from PyQt6.QtWidgets import (
    QToolBar, QToolButton, QFileDialog
)
from PyQt6.QtCore import QSize

from module_scanner import ModuleScanner, ManualModuleRegistry
from module_browser import ModuleBrowser
from layout_browser import LayoutBrowser
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

        # Slim toolbar styling
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setStyleSheet("""
            QToolBar {
                spacing: 4px;
                padding: 2px 4px;
                background-color: rgba(35, 35, 40, 0.98);
                border-bottom: 1px solid rgba(60, 60, 65, 0.6);
            }
            QToolButton {
                min-width: 50px;
                min-height: 22px;
                font-size: 13px;
                padding: 4px 10px;
                border-radius: 4px;
                background-color: transparent;
                color: #d0d0d0;
                border: 1px solid transparent;
            }
            QToolButton:hover {
                background-color: rgba(70, 70, 75, 0.7);
                border-color: rgba(90, 90, 95, 0.5);
            }
            QToolButton:pressed {
                background-color: rgba(50, 50, 55, 0.9);
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
        
        # Create layout browser
        self.layout_browser = LayoutBrowser(layouts_dir="./layouts")
        self.layout_browser.layoutLoaded.connect(self._on_layout_loaded)
        self.layout_browser.layoutAdded.connect(self._on_layout_added)
        self.layout_browser.saveRequested.connect(self._on_save_requested)

        # Create toolbar elements
        self._create_layouts_button()
        self._create_modules_button()

    def _init_module_registry(self):
        """Initialize module registry by scanning the modules directory."""
        self.module_scanner = ModuleScanner(self.modules_dir)
        
        # Perform initial scan
        discovered = self.module_scanner.scan()
        
        # Convert to ManualModuleRegistry for browser compatibility
        self.module_registry = ManualModuleRegistry()
        
        # Also build module_folders dict for backward compatibility with main_window
        self.module_folders = {}
        
        for name, info in discovered.items():
            self.module_registry.register(
                name=info.name,
                cls=info.class_ref,
                category=info.category
            )
            
            # Add to module_folders for backward compatibility
            category = info.category
            if category not in self.module_folders:
                self.module_folders[category] = []
            self.module_folders[category].append((info.name, info.class_ref))
            
        print(f"Auto-discovered {len(discovered)} modules in {len(self.module_scanner.get_categories())} categories")

    def refresh_modules(self):
        """Rescan the modules directory for new modules."""
        self.module_scanner.scan(force=True)
        self._init_module_registry()
        
        # Update browser
        self.module_browser.set_registry(self.module_registry)
        self.module_browser.set_usage_tracker(self.usage_tracker)
        
        print("Module registry refreshed")

    def _create_layouts_button(self):
        """Create the Layouts button that opens the layout browser."""
        self.layouts_button = QToolButton()
        self.layouts_button.setText("Layouts")
        self.layouts_button.clicked.connect(self._show_layout_browser)
        self.toolbar.addWidget(self.layouts_button)

    def _create_modules_button(self):
        """Create the Modules button that opens the browser."""
        self.modules_button = QToolButton()
        self.modules_button.setText("Add Module")
        self.modules_button.clicked.connect(self._show_module_browser)
        self.toolbar.addWidget(self.modules_button)

    def _show_module_browser(self):
        """Show the module browser popup below the modules button."""
        self.module_browser.show_below(self.modules_button)

    def _show_layout_browser(self):
        """Show the layout browser popup below the layouts button."""
        self.layout_browser.show_below(self.layouts_button)

    def _on_module_spawned(self, module_name: str):
        """Handle module spawn from the browser."""
        self.spawn_module(module_name)

    def _on_layout_loaded(self, file_path: str):
        """Handle layout load from the browser."""
        self.main_window.load_layout(file_path)

    def _on_layout_added(self, file_path: str):
        """Handle layout add from the browser."""
        self.main_window.add_layout(file_path)

    def _on_save_requested(self):
        """Handle save request from the browser."""
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
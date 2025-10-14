# toolbar_manager.py
from PyQt6.QtWidgets import QToolBar, QMenu, QToolButton
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QPointF, QSize
from modules.bandpass import Bandpass
from modules.endpoint import EndpointModule
from modules.vco import VCO
from modules.static import Noise
from modules.pan import Pan
from modules.music import Music
from modules.soundboard import Soundboard
from modules.crossfade import Crossfade
from modules.hold import Hold
from modules.tts import TextToSpeech
from ui_elements import ModuleItem


class ToolbarManager:
    """
    Handles the creation of the toolbar with folder grouping and module-spawning logic.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self.toolbar = QToolBar("Modules")
        self.main_window.addToolBar(self.toolbar)

        # ✅ Touchscreen-friendly scaling
        self.toolbar.setIconSize(QSize(48, 48))  # larger icons
        self.toolbar.setStyleSheet("""
            QToolBar {
                spacing: 12px;
                padding: 8px;
            }
            QToolButton {
                min-width: 60px;
                min-height: 30px;
                font-size: 16px;
                padding: 10px 16px;
                border-radius: 10px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)

        # Organize modules by folder
        self.module_folders = {
            "Source": [
                ("Music", Music),
                ("VCO", VCO),
                ("Static", Noise),
                ("Soundboard", Soundboard),
                ("TTS", TextToSpeech)
            ],
            "Effects": [
                ("Bandpass", Bandpass),
                ("Pan", Pan),
                ("Crossfade", Crossfade),
                ("Hold", Hold)
            ],
            "Master": [
                ("Endpoint", EndpointModule)
            ],
        }

        self.create_folder_buttons()

    def create_folder_buttons(self):
        """Creates a toolbar button for each folder with a dropdown menu of modules."""
        for folder_name, modules in self.module_folders.items():
            menu = QMenu()
            for name, cls in modules:
                action = QAction(name, self.main_window)
                action.triggered.connect(lambda checked, n=name: self.spawn_module(n))
                menu.addAction(action)

            # Create a toolbar button with the menu
            button = QToolButton()
            button.setText(folder_name)
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

            # ✅ Make dropdown menus touch-friendly
            button.setStyleSheet("""
                QToolButton::menu-indicator {
                    width: 16px;
                    height: 16px;
                }
                QMenu {
                    font-size: 15px;
                    padding: 8px;
                }
                QMenu::item {
                    padding: 5px 10px;
                }
                QMenu::item:selected {
                    background-color: rgba(100, 100, 100, 0.3);
                }
            """)

            self.toolbar.addWidget(button)

    def spawn_module(self, name: str):
        """Creates the backend module and adds its graphical ModuleItem to the scene, centered in the current view."""
        # Find class by name
        cls = None
        for folder_modules in self.module_folders.values():
            for n, c in folder_modules:
                if n == name:
                    cls = c
                    break
            if cls:
                break

        if cls is None:
            print(f"Unknown module: {name}")
            return

        module = cls()

        # Register module
        if isinstance(module, EndpointModule):
            self.main_window.endpoints.append(module)
        else:
            self.main_window.modules.append(module)

        # Create visual representation
        item = ModuleItem(module)

        # Center spawn position based on current camera view
        view = self.main_window.view
        view_center = view.mapToScene(view.viewport().rect().center())

        # Optional offset so modules don’t overlap perfectly
        item.setPos(QPointF(view_center.x() - 50, view_center.y() - 25))

        self.main_window.scene.addItem(item)

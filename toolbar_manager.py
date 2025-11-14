# toolbar_manager.py
from PyQt6.QtWidgets import QToolBar, QMenu, QToolButton, QFileDialog
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QPointF, QSize
from modules.bandpass import Bandpass
from modules.endpoint import Endpoint
from modules.wave import Wave
from modules.static import Static
from modules.pan import Pan
from modules.music import Music
from modules.soundboard import Soundboard
from modules.crossfade import Crossfade
from modules.hold import Hold
from modules.tts import TTS
from modules.reverb import Reverb
from modules.bitcrusher import Bitcrusher
from modules.sum import Sum
from modules.split import Split
from modules.morse import Morse
from modules.reversedelay import ReverseDelay
from modules.samplehold import SampleHoldMod
from modules.multiply import Multiply
from modules.convolve import Convolve
from ui_elements import ModuleItem


class ToolbarManager:
    """
    Handles creation of toolbar with folder grouping, file actions, and module spawning logic.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self.toolbar = QToolBar("Modules")
        self.main_window.addToolBar(self.toolbar)

        # ✅ Touchscreen-friendly scaling
        self.toolbar.setIconSize(QSize(48, 48))
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

        # Create file menu first
        self.create_file_menu()

        # Organize modules by folder
        self.module_folders = {
            "Source": [
                ("Music", Music),
                ("Wave", Wave),
                ("Static", Static),
                ("Soundboard", Soundboard),
                ("TTS", TTS)
            ],
            "Effects": [
                ("Pan", Pan),
                ("Hold", Hold),
                ("Bitcrusher", Bitcrusher),
                ("Reverb", Reverb),
                ("Bandpass", Bandpass),
                ("Morse", Morse),
                ("ReverseDelay", ReverseDelay),
                ("SampleHoldMod", SampleHoldMod),
                ("Multiply", Multiply),
                ("Convolve", Convolve),
            ],
            "Routing": [
                ("Endpoint", Endpoint),
                ("Crossfade", Crossfade),
                ("Sum", Sum),
                ("Split", Split)
            ],
        }

        self.create_folder_buttons()

    def create_file_menu(self):
        """Adds the File dropdown with Save and Load layout options."""
        file_menu = QMenu()

        save_action = QAction("Save Layout", self.main_window)
        save_action.triggered.connect(self.save_layout)
        file_menu.addAction(save_action)

        load_action = QAction("Load Layout", self.main_window)
        load_action.triggered.connect(self.load_layout)
        file_menu.addAction(load_action)

        button = QToolButton()
        button.setText("File")
        button.setMenu(file_menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
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

    def create_folder_buttons(self):
        """Creates a toolbar button for each folder with a dropdown menu of modules."""
        for folder_name, modules in self.module_folders.items():
            menu = QMenu()
            for name, cls in modules:
                action = QAction(name, self.main_window)
                action.triggered.connect(lambda checked, n=name: self.spawn_module(n))
                menu.addAction(action)

            button = QToolButton()
            button.setText(folder_name)
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
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
        if isinstance(module, Endpoint):
            self.main_window.endpoints.append(module)
        else:
            self.main_window.modules.append(module)

        # Create visual representation
        item = ModuleItem(module)

        # Center spawn position based on current camera view
        view = self.main_window.view
        view_center = view.mapToScene(view.viewport().rect().center())

        item.setPos(QPointF(view_center.x() - 50, view_center.y() - 25))
        self.main_window.scene.addItem(item)

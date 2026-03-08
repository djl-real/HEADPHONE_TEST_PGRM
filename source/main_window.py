import sys
import os, psutil
import numpy as np
import sounddevice as sd
import json
import threading
import uuid

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QWidget, QVBoxLayout
)
from PyQt6.QtCore import QPointF

from source.audio_module import AudioModule
from source.toolbar_manager import ToolbarManager
from source.ui_elements import ModuleItem, ConnectionPath
from modules.endpoint import Endpoint
from source.mixer import Mixer
from source.workspace_scene import WorkspaceScene
from source.workspace_view import WorkspaceView


def db_to_linear(db_value: float) -> float:
    return 10.0 ** (db_value / 20.0)


class MainWindow(QMainWindow):
    """Main application window with threaded real-time audio generation using a ring buffer."""
    def __init__(self):
        super().__init__()

        # --- Cross-platform process priority ---
        try:
            p = psutil.Process(os.getpid())

            if psutil.WIN32:
                p.nice(psutil.HIGH_PRIORITY_CLASS)
            else:
                try:
                    os.nice(-10)
                except PermissionError:
                    current_nice = os.nice(0)
                    if current_nice > 0:
                        os.nice(-current_nice)
        except Exception:
            pass

        self.setWindowTitle("HEADPHONE_TEST_PGRM")
        self.resize(1200, 800)
        self.copied_layout = None

        # Workspace
        self.scene = WorkspaceScene()
        self.view = WorkspaceView(self.scene, self)

        self.container = QWidget()
        self.setCentralWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(self.view)

        # Audio backend
        self.sample_rate = 44100
        self.block_size = 2048
        self.modules: list[AudioModule] = []
        self.endpoints: list[AudioModule] = []

        # Toolbar manager
        self.toolbar_manager = ToolbarManager(self)

        # Mixer (overlay)
        self.mixer = Mixer(self)
        self.mixer.setParent(self.container)
        self.mixer.raise_()

        # Whenever mixer collapses/expands, reposition it
        if hasattr(self.mixer, "toggled"):
            self.mixer.toggled.connect(self._reposition_mixer)

        # --- Ring buffer configuration ---
        self.ring_size = 4  # Number of blocks ahead to prefill
        self.ring_buffer = np.zeros((self.ring_size, self.block_size, 2), dtype=np.float32)
        self.write_index = 0  # Worker writes here
        self.read_index = 0   # Callback reads here
        self.available_blocks = 0
        self._buffer_lock = threading.Lock()
        self._buffer_cond = threading.Condition(self._buffer_lock)

        # Stop signal for worker
        self._stop_event = threading.Event()

        # --- Background worker thread ---
        self._worker_thread = threading.Thread(target=self._audio_worker_loop, daemon=True)
        self._worker_thread.start()

        # --- Start audio output ---
        self.stream = sd.OutputStream(
            channels=2,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            callback=self.audio_callback,
            dtype="float32",
        )
        self.stream.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_mixer()

    def _reposition_mixer(self):
        """Keep mixer pinned to bottom as an overlay."""
        if not self.mixer:
            return

        cw = self.container.width()
        ch = self.container.height()
        mh = self.mixer.height()

        self.mixer.setGeometry(0, ch - mh, cw, mh)

    # ---------- Worker Thread ----------
    def _audio_worker_loop(self):
        """Continuously fill the ring buffer with precomputed audio blocks."""
        while not self._stop_event.is_set():
            with self._buffer_cond:
                # Wait until there is room in the ring buffer
                while self.available_blocks >= self.ring_size and not self._stop_event.is_set():
                    self._buffer_cond.wait(timeout=0.01)

                if self._stop_event.is_set():
                    break

            # Generate outside the lock so the callback isn't blocked
            block = self._generate_mix_block(self.block_size)

            with self._buffer_cond:
                np.copyto(self.ring_buffer[self.write_index], block)
                self.write_index = (self.write_index + 1) % self.ring_size
                self.available_blocks = min(self.available_blocks + 1, self.ring_size)

    # ---------- Mixing ----------
    def _generate_mix_block(self, frames: int) -> np.ndarray:
        """Generate a single block of mixed audio from endpoints."""
        if not self.endpoints:
            return np.zeros((frames, 2), dtype=np.float32)

        mix = np.zeros((frames, 2), dtype=np.float32)
        for endpoint in self.endpoints:
            try:
                audio = endpoint.generate(frames)
            except Exception:
                continue
            if audio is not None:
                n = min(audio.shape[0], frames)
                mix[:n] += audio[:n]

        np.clip(mix, -1.0, 1.0, out=mix)
        mix *= db_to_linear(self.mixer.master_volume_db)
        return mix

    # ---------- Audio Callback ----------
    def audio_callback(self, outdata, frames, time, status):
        """Real-time audio callback reads the next available block from the ring buffer."""
        try:
            with self._buffer_cond:
                if self.available_blocks > 0:
                    np.copyto(outdata, self.ring_buffer[self.read_index])
                    self.read_index = (self.read_index + 1) % self.ring_size
                    self.available_blocks -= 1
                    # Notify the worker that a slot is now free
                    self._buffer_cond.notify()
                else:
                    outdata.fill(0)
        except Exception:
            outdata.fill(0)

    # ---------- Cleanup ----------
    def closeEvent(self, event):
        """Stop worker and audio stream."""
        self._stop_event.set()
        # Wake the worker so it sees the stop event
        with self._buffer_cond:
            self._buffer_cond.notify()
        self._worker_thread.join(timeout=1.0)
        if hasattr(self, "stream") and self.stream:
            self.stream.stop()
            self.stream.close()
        super().closeEvent(event)

    def spawn_module(self, module: AudioModule):
        # Create visual representation
        item = ModuleItem(module, self)

        # Center spawn position based on current camera view
        view = self.view
        view_center = view.mapToScene(view.viewport().rect().center())

        item.setPos(QPointF(view_center.x() - 50, view_center.y() - 25))
        self.scene.addItem(item)

        # Register module
        if type(module).__name__ == "Endpoint":
            self.endpoints.append(module)
            self.mixer.add_endpoint(module)
        else:
            self.modules.append(module)

    def destroy_module(self, module):
        if isinstance(module, Endpoint):
            self.mixer.remove_endpoint(module)
            if module in self.endpoints:
                self.endpoints.remove(module)
        else:
            if module in self.modules:
                self.modules.remove(module)

    def save_layout(self, path: str):
        """Save all modules, nodes, and connections to a .layout JSON file."""
        if not path:
            return

        layout_data = {"version": 2, "modules": [], "connections": []}

        # Collect modules
        for item in self.scene.items():
            if isinstance(item, ModuleItem):
                module = item.module
                pos = item.pos()
                module_info = {
                    "id": item.module_id,
                    "type": module.__class__.__name__,
                    "pos": [pos.x(), pos.y()],
                }
                if hasattr(module, "serialize"):
                    module_info["state"] = module.serialize()
                layout_data["modules"].append(module_info)

        # Collect connections
        for item in self.scene.items():
            if isinstance(item, ConnectionPath):
                src_node = getattr(item, "start_node", None)
                dst_node = getattr(item, "end_node", None)
                if src_node and dst_node:
                    src_item = src_node.module_item
                    dst_item = dst_node.module_item
                    if not src_item or not dst_item:
                        continue
                    layout_data["connections"].append({
                        "from": {
                            "module_id": src_item.module_id,
                            "node_index": getattr(src_node, "index", 0),
                            "type": "output"
                        },
                        "to": {
                            "module_id": dst_item.module_id,
                            "node_index": getattr(dst_node, "index", 0),
                            "type": "input"
                        },
                    })

        try:
            with open(path, "w") as f:
                json.dump(layout_data, f, indent=4)
        except Exception:
            pass

    def load_layout(self, path: str):
        """Load modules, positions, and connections from a .layout JSON file."""
        if not path:
            return

        try:
            with open(path, "r") as f:
                layout_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Layout", str(e))
            return

        # Clear existing scene
        self.scene.clear()
        self.modules.clear()
        self.endpoints.clear()
        self.mixer.scroll_layout.update()
        module_map = {}  # module_id → ModuleItem

        # Recreate modules
        for mod_info in layout_data.get("modules", []):
            mod_type = mod_info.get("type")
            module_id = mod_info.get("id")
            pos_x, pos_y = mod_info.get("pos", [0, 0])

            cls = None
            for folder_modules in self.toolbar_manager.module_folders.values():
                for name, c in folder_modules:
                    if name == mod_type:
                        cls = c
                        break
                if cls:
                    break

            if not cls:
                print(f"Skipping unknown module type: {mod_type}")
                continue

            module = cls()

            if hasattr(module, "deserialize"):
                module.deserialize(mod_info.get("state", {}))

            self.spawn_module(module)

            item = None
            for it in self.scene.items():
                if isinstance(it, ModuleItem) and it.module is module:
                    item = it
                    break

            if not item:
                print("Error: ModuleItem was not created by spawn_module()!")
                continue

            item.module_id = module_id
            item.setPos(QPointF(pos_x, pos_y))

            module_map[module_id] = item

        # Restore Connections
        for conn in layout_data.get("connections", []):
            src_id = conn["from"]["module_id"]
            dst_id = conn["to"]["module_id"]
            src_idx = conn["from"]["node_index"]
            dst_idx = conn["to"]["node_index"]

            src_item = module_map.get(src_id)
            dst_item = module_map.get(dst_id)
            if not src_item or not dst_item:
                continue

            try:
                src_node = src_item.output_nodes[src_idx]
                dst_node = dst_item.input_nodes[dst_idx]
            except Exception:
                continue

            if not src_node or not dst_node:
                continue

            if src_node.node_obj and dst_node.node_obj:
                try:
                    src_node.node_obj.connect(dst_node.node_obj)
                except Exception:
                    pass

            conn_path = ConnectionPath(src_node, dst_node, scene=self.scene)
            src_node.connection = conn_path
            dst_node.connection = conn_path

    def add_layout(self, path: str):
        """Add modules and connections from a .layout file WITHOUT clearing the existing scene."""

        view_center = self.view.mapToScene(self.view.viewport().rect().center())
        offset = QPointF(view_center.x() - 50, view_center.y() - 25)

        if not path:
            return

        try:
            with open(path, "r") as f:
                layout_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error Adding Layout", str(e))
            return

        module_map = {}
        id_remap = {}
        existing_ids = {item.module_id for item in self.scene.items()
                        if isinstance(item, ModuleItem)}

        # Create modules
        for mod_info in layout_data.get("modules", []):
            mod_type = mod_info.get("type")
            old_id = mod_info.get("id")
            pos_x, pos_y = mod_info.get("pos", [0, 0])

            cls = None
            for folder_modules in self.toolbar_manager.module_folders.values():
                for name, c in folder_modules:
                    if name == mod_type:
                        cls = c
                        break
                if cls:
                    break

            if not cls:
                print(f"Skipping unknown module type: {mod_type}")
                continue

            module = cls()

            if hasattr(module, "deserialize"):
                module.deserialize(mod_info.get("state", {}))

            self.spawn_module(module)

            item = None
            for it in self.scene.items():
                if isinstance(it, ModuleItem) and it.module is module:
                    item = it
                    break

            if not item:
                print("Error: ModuleItem was not created by spawn_module()!")
                continue

            new_id = old_id
            if new_id in existing_ids:
                new_id = str(uuid.uuid4())
            id_remap[old_id] = new_id

            item.module_id = new_id
            item.setPos(QPointF(pos_x, pos_y) + offset)

            module_map[new_id] = item

        # Create connections
        for conn in layout_data.get("connections", []):
            src_id = id_remap.get(conn["from"]["module_id"], conn["from"]["module_id"])
            dst_id = id_remap.get(conn["to"]["module_id"], conn["to"]["module_id"])
            src_idx = conn["from"]["node_index"]
            dst_idx = conn["to"]["node_index"]

            src_item = module_map.get(src_id)
            dst_item = module_map.get(dst_id)
            if not src_item or not dst_item:
                continue

            try:
                src_node = src_item.output_nodes[src_idx]
                dst_node = dst_item.input_nodes[dst_idx]
            except Exception:
                continue

            if src_node.node_obj and dst_node.node_obj:
                try:
                    src_node.node_obj.connect(dst_node.node_obj)
                except Exception:
                    pass

            conn_path = ConnectionPath(src_node, dst_node, scene=self.scene)
            src_node.connection = conn_path
            dst_node.connection = conn_path

    def save_selection_as_layout(self, selected_items):
        """Save only the selected modules + internal connections to a layout file."""
        if not selected_items:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Selected Layout",
            "./layouts",
            "Layout Files (*.layout)"
        )
        if not path:
            return

        layout_data = {"version": 2, "modules": [], "connections": []}
        selected_ids = set(item.module_id for item in selected_items)

        for item in selected_items:
            module = item.module
            pos = item.pos()
            module_info = {
                "id": item.module_id,
                "type": module.__class__.__name__,
                "pos": [pos.x(), pos.y()],
            }
            if hasattr(module, "serialize"):
                module_info["state"] = module.serialize()
            layout_data["modules"].append(module_info)

        for obj in self.scene.items():
            if not isinstance(obj, ConnectionPath):
                continue

            src = getattr(obj, "start_node", None)
            dst = getattr(obj, "end_node", None)
            if not src or not dst:
                continue

            src_item = src.module_item
            dst_item = dst.module_item
            if not src_item or not dst_item:
                continue

            if src_item.module_id not in selected_ids:
                continue
            if dst_item.module_id not in selected_ids:
                continue

            layout_data["connections"].append({
                "from": {
                    "module_id": src_item.module_id,
                    "node_index": getattr(src, "index", 0),
                    "type": "output"
                },
                "to": {
                    "module_id": dst_item.module_id,
                    "node_index": getattr(dst, "index", 0),
                    "type": "input"
                },
            })

        try:
            with open(path, "w") as f:
                json.dump(layout_data, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Selection", str(e))

    def copy_selection(self, selected_items):
        """Copy selected modules + internal connections to an internal clipboard."""
        if not selected_items:
            return

        layout_data = {"version": 2, "modules": [], "connections": []}
        selected_ids = set(item.module_id for item in selected_items)

        for item in selected_items:
            module = item.module
            pos = item.pos()
            module_info = {
                "id": item.module_id,
                "type": module.__class__.__name__,
                "pos": [pos.x(), pos.y()],
            }
            if hasattr(module, "serialize"):
                module_info["state"] = module.serialize()
            layout_data["modules"].append(module_info)

        for obj in self.scene.items():
            if not isinstance(obj, ConnectionPath):
                continue

            src = getattr(obj, "start_node", None)
            dst = getattr(obj, "end_node", None)
            if not src or not dst:
                continue

            src_item = src.module_item
            dst_item = dst.module_item
            if not src_item or not dst_item:
                continue

            if src_item.module_id not in selected_ids:
                continue
            if dst_item.module_id not in selected_ids:
                continue

            layout_data["connections"].append({
                "from": {
                    "module_id": src_item.module_id,
                    "node_index": getattr(src, "index", 0),
                    "type": "output"
                },
                "to": {
                    "module_id": dst_item.module_id,
                    "node_index": getattr(dst, "index", 0),
                    "type": "input"
                },
            })

        self.copied_layout = layout_data

    def paste_at(self, scene_pos):
        """Paste copied modules at a given scene position."""
        if not self.copied_layout:
            return

        layout = self.copied_layout
        modules = layout["modules"]

        if not modules:
            return

        # Compute centroid of copied modules
        xs = [m["pos"][0] for m in modules]
        ys = [m["pos"][1] for m in modules]
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)

        paste_offset = scene_pos - QPointF(center_x, center_y)

        new_map = {}

        # Create modules
        for mod in modules:
            mod_type = mod["type"]
            old_id = mod["id"]

            cls = None
            for folder_modules in self.toolbar_manager.module_folders.values():
                for name, c in folder_modules:
                    if name == mod_type:
                        cls = c
                        break
                if cls:
                    break
            if not cls:
                print(f"Skipping unknown module type: {mod_type}")
                continue

            module_backend = cls()

            if hasattr(module_backend, "deserialize"):
                module_backend.deserialize(mod.get("state", {}))

            self.spawn_module(module_backend)

            item = None
            for it in self.scene.items():
                if isinstance(it, ModuleItem) and it.module is module_backend:
                    item = it
                    break

            if not item:
                continue

            item.module_id = str(uuid.uuid4())

            px, py = mod["pos"]
            item.setPos(QPointF(px, py) + paste_offset)

            new_map[old_id] = item

        # Connections
        for conn in layout.get("connections", []):
            src_old = conn["from"]["module_id"]
            dst_old = conn["to"]["module_id"]

            src_idx = conn["from"]["node_index"]
            dst_idx = conn["to"]["node_index"]

            src_item = new_map.get(src_old)
            dst_item = new_map.get(dst_old)
            if not src_item or not dst_item:
                continue

            try:
                src_node = src_item.output_nodes[src_idx]
                dst_node = dst_item.input_nodes[dst_idx]
            except Exception:
                continue

            try:
                if src_node.node_obj and dst_node.node_obj:
                    src_node.node_obj.connect(dst_node.node_obj)
            except Exception:
                pass

            conn_path = ConnectionPath(src_node, dst_node, scene=self.scene)
            src_node.connection = conn_path
            dst_node.connection = conn_path


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
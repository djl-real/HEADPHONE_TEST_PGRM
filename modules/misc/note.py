# modules/note.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QFont
from audio_module import AudioModule


class Note(AudioModule):
    """A simple note-taking module with markdown support."""

    def __init__(self, sample_rate=44100):
        super().__init__(input_count=0, output_count=0)
        self.sample_rate = sample_rate
        self.text = ""

    def generate(self, frames: int):
        # No audio processing
        return None

    def get_ui(self) -> QWidget:
        """Return a text editor with markdown rendering."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        widget.setLayout(layout)

        text_edit = QTextEdit()
        text_edit.setMarkdown(self.text)
        text_edit.setFont(QFont("Sans Serif", 10))
        text_edit.setMinimumSize(200, 150)
        layout.addWidget(text_edit)

        def on_text_changed():
            self.text = text_edit.toMarkdown()

        text_edit.textChanged.connect(on_text_changed)

        return widget

    # ---------------- Serialization ----------------
    def serialize(self) -> dict:
        """Return a dict representing this module's state."""
        data = super().serialize()
        data.update({
            "sample_rate": self.sample_rate,
            "text": self.text,
        })
        return data

    def deserialize(self, state: dict):
        """Restore module state from a dictionary."""
        super().deserialize(state)
        self.sample_rate = state.get("sample_rate", 44100)
        self.text = state.get("text", "")
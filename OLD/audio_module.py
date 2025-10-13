# audio_module.py
import numpy as np


class AudioModule:
    """
    Base class for all audio modules in the modular system.
    Supports input/output connections, recursive processing, and signal routing.
    """

    def __init__(self, name: str):
        self.name = name
        self.inputs = []       # upstream modules
        self.outputs = []      # downstream modules
        self.muted = False
        self.volume = -6.0     # default in dB
        self.pan = 0.0         # -1 (L) to +1 (R)
        self.fs = 44100        # default sample rate
        self._last_frame_id = None
        self._last_output = None

    # === Connection management ===
    def connect(self, other: "AudioModule"):
        """Connect this module’s output to another module’s input."""
        if other not in self.outputs:
            self.outputs.append(other)
        if self not in other.inputs:
            other.inputs.append(self)

    def disconnect(self, other: "AudioModule"):
        """Disconnect this module’s output from another module."""
        if other in self.outputs:
            self.outputs.remove(other)
        if self in other.inputs:
            other.inputs.remove(self)

    # === Audio processing ===
    def process(self, frames: int, frame_id=None) -> np.ndarray:
        """
        Process the module’s signal for a given number of frames.
        Handles recursive graph traversal and avoids redundant recomputation.
        """
        # Prevent re-processing within the same callback frame
        if frame_id is not None and self._last_frame_id == frame_id:
            return self._last_output

        # Default input mix
        if not self.inputs:
            input_signal = np.zeros((frames, 2), dtype=np.float32)
        else:
            input_signal = sum(inp.process(frames, frame_id) for inp in self.inputs)

        # Apply local processing
        output = self.apply_effect(input_signal, frames)

        # Cache the result
        self._last_output = output
        self._last_frame_id = frame_id

        return output

    def apply_effect(self, input_signal: np.ndarray, frames: int) -> np.ndarray:
        """
        Base audio processing. Generators override this to produce sound.
        Filters override it to process input.
        """
        return input_signal

    # === Utility ===
    def _apply_mixer_controls(self, signal: np.ndarray) -> np.ndarray:
        """Apply volume, pan, and mute controls."""
        if self.muted:
            return np.zeros_like(signal)

        # Convert dB to linear gain
        gain = 10 ** (self.volume / 20.0)
        signal *= gain

        # Apply pan
        left_gain = np.sqrt(0.5 * (1 - self.pan))
        right_gain = np.sqrt(0.5 * (1 + self.pan))
        signal[:, 0] *= left_gain
        signal[:, 1] *= right_gain
        return signal

    def __repr__(self):
        return f"<AudioModule {self.name} inputs={len(self.inputs)} outputs={len(self.outputs)}>"

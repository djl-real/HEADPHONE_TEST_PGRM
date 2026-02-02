# modules/microphone.py
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt
from audio_module import AudioModule


class Microphone(AudioModule):
    """Microphone input module with mute button and gain control."""

    def __init__(self, gain=1.0, sample_rate=44100, block_size=1024):
        super().__init__(input_count=0, output_count=1)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.gain = gain
        self.muted = False
        
        # Audio buffer
        self.buffer = np.zeros((block_size * 4, 2), dtype=np.float32)
        self.write_pos = 0
        self.read_pos = 0
        
        # Find default input device
        self.selected_device_index = None
        try:
            self.selected_device_index = sd.default.device[0]  # Default input device
        except:
            # If no default, find any input device
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    self.selected_device_index = i
                    break
        
        self.stream = None
        self.start_stream()

    def audio_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice stream."""
        if status:
            print(f"Sounddevice status: {status}")
        
        # Convert to stereo if needed
        if indata.shape[1] == 1:
            stereo_data = np.column_stack((indata[:, 0], indata[:, 0]))
        else:
            stereo_data = indata[:, :2]  # Take first 2 channels if more available
        
        # Write to circular buffer
        available = len(self.buffer) - self.write_pos
        if frames <= available:
            self.buffer[self.write_pos:self.write_pos + frames] = stereo_data
            self.write_pos = (self.write_pos + frames) % len(self.buffer)
        else:
            # Wrap around
            self.buffer[self.write_pos:] = stereo_data[:available]
            self.buffer[:frames - available] = stereo_data[available:]
            self.write_pos = frames - available

    def start_stream(self):
        """Start the audio input stream."""
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
        
        if self.selected_device_index is None:
            return
        
        try:
            # Get device info to determine channel count
            device_info = sd.query_devices(self.selected_device_index)
            channels = min(2, device_info['max_input_channels'])
            
            self.stream = sd.InputStream(
                device=self.selected_device_index,
                channels=channels,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=self.audio_callback,
                dtype=np.float32
            )
            self.stream.start()
        except Exception as e:
            print(f"Failed to open microphone stream: {e}")
            self.stream = None

    def generate(self, frames: int) -> np.ndarray:
        """Capture audio from microphone."""
        if self.muted or self.stream is None:
            return np.zeros((frames, 2), dtype=np.float32)
        
        # Read from circular buffer
        output = np.zeros((frames, 2), dtype=np.float32)
        available = (self.write_pos - self.read_pos) % len(self.buffer)
        
        if available >= frames:
            if self.read_pos + frames <= len(self.buffer):
                output[:] = self.buffer[self.read_pos:self.read_pos + frames]
                self.read_pos = (self.read_pos + frames) % len(self.buffer)
            else:
                # Wrap around
                first_part = len(self.buffer) - self.read_pos
                output[:first_part] = self.buffer[self.read_pos:]
                output[first_part:] = self.buffer[:frames - first_part]
                self.read_pos = frames - first_part
        else:
            # Not enough data, return silence
            pass
        
        # Apply gain
        return output * self.gain

    def get_input_devices(self):
        """Get list of available input devices."""
        devices = []
        all_devices = sd.query_devices()
        for i, dev in enumerate(all_devices):
            if dev['max_input_channels'] > 0:
                devices.append((i, dev['name']))
        return devices

    def get_ui(self) -> QWidget:
        """Return QWidget with mute button, gain slider, and device selector."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Device selector
        layout.addWidget(QLabel("Input Device:"))
        device_combo = QComboBox()
        devices = self.get_input_devices()
        
        for idx, name in devices:
            device_combo.addItem(name, idx)
            if idx == self.selected_device_index:
                device_combo.setCurrentIndex(device_combo.count() - 1)
        
        def on_device_change(index):
            self.selected_device_index = device_combo.itemData(index)
            self.start_stream()
        
        device_combo.currentIndexChanged.connect(on_device_change)
        layout.addWidget(device_combo)

        # Mute button
        mute_layout = QHBoxLayout()
        self.mute_btn = QPushButton("🔊 UNMUTED")
        self.mute_btn.setFixedHeight(50)
        self.update_mute_button_style()
        
        def toggle_mute():
            self.muted = not self.muted
            self.update_mute_button_style()
        
        self.mute_btn.clicked.connect(toggle_mute)
        mute_layout.addWidget(self.mute_btn)
        layout.addLayout(mute_layout)

        # Gain control
        gain_label = QLabel(f"Gain: {self.gain:.2f}x")
        layout.addWidget(gain_label)

        gain_slider = QSlider(Qt.Orientation.Horizontal)
        gain_slider.setMinimum(0)
        gain_slider.setMaximum(200)  # 0 to 2x gain
        gain_slider.setValue(int(self.gain * 100))
        gain_slider.setTickInterval(20)
        gain_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        layout.addWidget(gain_slider)

        def on_gain_change(val):
            self.gain = val / 100.0
            gain_label.setText(f"Gain: {self.gain:.2f}x")

        gain_slider.valueChanged.connect(on_gain_change)

        # Gain slider tick labels
        tick_layout = QHBoxLayout()
        for lbl in ["0.0", "0.5", "1.0", "1.5", "2.0"]:
            l = QLabel(lbl)
            l.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            tick_layout.addWidget(l)
        layout.addLayout(tick_layout)

        layout.addStretch()

        return widget

    def update_mute_button_style(self):
        """Update the mute button appearance based on mute state."""
        if self.muted:
            self.mute_btn.setText("🔇 MUTED")
            self.mute_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    font-size: 16px;
                    font-weight: bold;
                    border-radius: 8px;
                    border: 2px solid #c0392b;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
        else:
            self.mute_btn.setText("🔊 UNMUTED")
            self.mute_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2ecc71;
                    color: white;
                    font-size: 16px;
                    font-weight: bold;
                    border-radius: 8px;
                    border: 2px solid #27ae60;
                }
                QPushButton:hover {
                    background-color: #27ae60;
                }
            """)

    def cleanup(self):
        """Clean up audio resources."""
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
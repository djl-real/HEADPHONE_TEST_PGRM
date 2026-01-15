import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainter, QColor, QPen


class CueWaveformVisualizer(QWidget):
    """Widget to visualize full waveforms overlapping at a cue point."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setMaximumHeight(150)

        self.waveform_a = None
        self.waveform_b = None

        self.duration_a = 0.0
        self.duration_b = 0.0

        self.cue_offset = 0.0
        self.sample_rate = 44100

    def set_tracks(self, track_a_data, track_b_data, cue_seconds, sample_rate=44100):
        self.sample_rate = sample_rate
        self.cue_offset = cue_seconds

        if track_a_data is not None and len(track_a_data) > 0:
            self.duration_a = len(track_a_data) / sample_rate
            self.waveform_a = self._downsample_waveform(track_a_data, 800)
        else:
            self.waveform_a = None
            self.duration_a = 0.0

        if track_b_data is not None and len(track_b_data) > 0:
            self.duration_b = len(track_b_data) / sample_rate
            self.waveform_b = self._downsample_waveform(track_b_data, 800)
        else:
            self.waveform_b = None
            self.duration_b = 0.0

        self.update()

    def _downsample_waveform(self, data, target_points):
        if data.ndim == 2:
            data = np.mean(data, axis=1)

        chunk_size = max(1, len(data) // target_points)
        num_chunks = len(data) // chunk_size

        out = np.zeros(num_chunks * 2)
        for i in range(num_chunks):
            chunk = data[i * chunk_size:(i + 1) * chunk_size]
            out[i * 2] = np.max(chunk)
            out[i * 2 + 1] = np.min(chunk)

        return out

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center_y = height // 2
        amplitude = height * 0.4

        painter.fillRect(0, 0, width, height, QColor(30, 30, 30))
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(0, center_y, width, center_y)

        # --- OVERLAP TIME RANGE ---
        overlap_start = max(-self.duration_a, self.cue_offset)
        overlap_end = min(0.0, self.cue_offset + self.duration_b)
        overlap_duration = max(0.001, overlap_end - overlap_start)

        # --- DYNAMIC ZOOM ---
        overlap_pixels = width * 0.6
        seconds_per_pixel = overlap_duration / overlap_pixels
        visible_duration = width * seconds_per_pixel

        overlap_center = (overlap_start + overlap_end) / 2
        t_min = overlap_center - visible_duration / 2
        t_max = overlap_center + visible_duration / 2

        denom = t_max - t_min
        if denom <= 0:
            denom = 0.001

        def time_to_x(t):
            return (t - t_min) / denom * width

        # Cue marker
        cue_x = time_to_x(0.0)
        painter.setPen(QPen(QColor(255, 255, 0), 2))
        painter.drawLine(int(cue_x), 0, int(cue_x), height)

        # Track A
        if self.waveform_a is not None:
            self._draw_waveform_fade(
                painter,
                self.waveform_a,
                start_time=-self.duration_a,
                duration=self.duration_a,
                base_color=QColor(255, 120, 60),
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                time_to_x=time_to_x,
                center_y=center_y,
                amplitude=amplitude
            )

        # Track B
        if self.waveform_b is not None:
            self._draw_waveform_fade(
                painter,
                self.waveform_b,
                start_time=self.cue_offset,
                duration=self.duration_b,
                base_color=QColor(60, 150, 255),
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                time_to_x=time_to_x,
                center_y=center_y,
                amplitude=amplitude
            )

        painter.setPen(QColor(200, 200, 200))
        painter.drawText(10, 20, "Track A")
        painter.drawText(10, height - 10, f"Cue: {self.cue_offset:.2f}s")
        painter.drawText(width - 80, 20, "Track B")

    def _draw_waveform_fade(
        self,
        painter,
        waveform,
        start_time,
        duration,
        base_color,
        overlap_start,
        overlap_end,
        time_to_x,
        center_y,
        amplitude
    ):
        if waveform is None or duration <= 0 or len(waveform) == 0:
            return

        overlap_width = overlap_end - overlap_start
        if overlap_width <= 0:
            overlap_width = None  # disables fade logic safely

        n = len(waveform)

        for i in range(n - 1):
            t = start_time + (i / n) * duration
            v1 = waveform[i]
            v2 = waveform[i + 1]

            x1 = time_to_x(t)
            x2 = time_to_x(start_time + ((i + 1) / n) * duration)

            y1 = center_y + v1 * amplitude
            y2 = center_y + v2 * amplitude

            alpha = 255

            if overlap_width and overlap_start <= t <= overlap_end:
                center = (overlap_start + overlap_end) / 2
                fade = abs(t - center) / overlap_width
                fade = min(max(fade, 0.0), 1.0)
                alpha = int(255 * (0.3 + 0.7 * fade))

            color = QColor(base_color)
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

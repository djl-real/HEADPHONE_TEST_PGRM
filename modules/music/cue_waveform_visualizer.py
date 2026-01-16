import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush


class CueWaveformVisualizer(QWidget):
    """Widget to visualize full waveforms overlapping at a cue point.
    
    Timeline explanation:
    - t=0 is when Track A ends (the "cue point" marker)
    - Track A runs from t=-duration_a to t=0
    - Track B starts at t=cue_offset (negative value, e.g. -5 means 5 sec before A ends)
    - Track B runs from t=cue_offset to t=cue_offset+duration_b
    
    Durations are adjusted by pitch (higher pitch = shorter playback duration).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setMaximumHeight(100)

        self.waveform_a = None
        self.waveform_b = None

        # Raw durations (before pitch adjustment)
        self.raw_duration_a = 0.0
        self.raw_duration_b = 0.0
        
        # Playback durations (after pitch adjustment)
        self.duration_a = 0.0
        self.duration_b = 0.0

        self.cue_offset = 0.0  # When track B starts (in playback seconds relative to A's end)
        self.sample_rate = 44100
        self.pitch_a = 1.0
        self.pitch_b = 1.0

    def set_tracks(self, track_a_data, track_b_data, cue_seconds, sample_rate=44100, pitch_a=1.0, pitch_b=1.0):
        self.sample_rate = sample_rate
        self.cue_offset = cue_seconds  # This is in "real" seconds, not affected by pitch
        self.pitch_a = pitch_a if pitch_a > 0 else 1.0
        self.pitch_b = pitch_b if pitch_b > 0 else 1.0

        if track_a_data is not None and len(track_a_data) > 0:
            self.raw_duration_a = len(track_a_data) / sample_rate
            # Playback duration is shorter when pitch is higher
            self.duration_a = self.raw_duration_a / self.pitch_a
            self.waveform_a = self._downsample_waveform(track_a_data, 800)
        else:
            self.waveform_a = None
            self.raw_duration_a = 0.0
            self.duration_a = 0.0

        if track_b_data is not None and len(track_b_data) > 0:
            self.raw_duration_b = len(track_b_data) / sample_rate
            self.duration_b = self.raw_duration_b / self.pitch_b
            self.waveform_b = self._downsample_waveform(track_b_data, 800)
        else:
            self.waveform_b = None
            self.raw_duration_b = 0.0
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

        # Timeline:
        # - Track A ends at t=0
        # - Track A starts at t=-duration_a
        # - Track B starts at t=cue_offset (the cue trigger point)
        # - Track B ends at t=cue_offset + duration_b
        
        track_a_start = -self.duration_a
        track_a_end = 0.0
        track_b_start = self.cue_offset  # This is when the cue fires and B starts
        track_b_end = self.cue_offset + self.duration_b

        # Calculate visible time range to show the overlap nicely
        # We want to see where the tracks overlap
        overlap_start = max(track_a_start, track_b_start)
        overlap_end = min(track_a_end, track_b_end)
        
        if overlap_end <= overlap_start:
            # No overlap - just show both tracks
            t_min = min(track_a_start, track_b_start)
            t_max = max(track_a_end, track_b_end)
        else:
            # Center on the overlap region
            overlap_duration = overlap_end - overlap_start
            overlap_center = (overlap_start + overlap_end) / 2
            
            # Show enough context around the overlap
            visible_duration = max(overlap_duration * 2.5, 10.0)  # At least 10 seconds visible
            t_min = overlap_center - visible_duration / 2
            t_max = overlap_center + visible_duration / 2

        denom = t_max - t_min
        if denom <= 0:
            denom = 0.001

        def time_to_x(t):
            return (t - t_min) / denom * width

        # Draw Track A waveform (orange)
        if self.waveform_a is not None:
            self._draw_waveform(
                painter,
                self.waveform_a,
                start_time=track_a_start,
                end_time=track_a_end,
                base_color=QColor(255, 120, 60),
                time_to_x=time_to_x,
                center_y=center_y,
                amplitude=amplitude,
                fade_start=overlap_start,
                fade_end=overlap_end,
                is_track_b=False
            )

        # Draw Track B waveform (blue)
        if self.waveform_b is not None:
            self._draw_waveform(
                painter,
                self.waveform_b,
                start_time=track_b_start,
                end_time=track_b_end,
                base_color=QColor(60, 150, 255),
                time_to_x=time_to_x,
                center_y=center_y,
                amplitude=amplitude,
                fade_start=overlap_start,
                fade_end=overlap_end,
                is_track_b=True
            )

        # Draw cue trigger marker (where track B starts) - dashed yellow line
        cue_x = time_to_x(self.cue_offset)
        painter.setPen(QPen(QColor(255, 255, 0), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(cue_x), 0, int(cue_x), height)
        
        # Draw track A end marker (solid yellow line at t=0)
        end_x = time_to_x(0.0)
        painter.setPen(QPen(QColor(255, 255, 0), 2))
        painter.drawLine(int(end_x), 0, int(end_x), height)

        # Labels
        painter.setPen(QColor(200, 200, 200))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(6, 14, f"A: {self.pitch_a:.2f}x")
        painter.drawText(6, height - 6, f"Cue: {self.cue_offset:.1f}s")
        painter.drawText(width - 55, 14, f"B: {self.pitch_b:.2f}x")

    def _draw_waveform(
        self,
        painter,
        waveform,
        start_time,
        end_time,
        base_color,
        time_to_x,
        center_y,
        amplitude,
        fade_start,
        fade_end,
        is_track_b=False
    ):
        duration = end_time - start_time
        if waveform is None or duration <= 0 or len(waveform) == 0:
            return

        fade_width = fade_end - fade_start
        n = len(waveform)
        
        # Calculate how compressed this waveform is (for opacity adjustment)
        # More compressed waveforms (higher pitch) need lower opacity in overlap
        # so the other track remains visible
        compression_factor = 1.0
        if is_track_b and self.pitch_b > 1.0:
            compression_factor = self.pitch_b
        elif not is_track_b and self.pitch_a > 1.0:
            compression_factor = self.pitch_a

        for i in range(n - 1):
            # Map waveform index to time
            t1 = start_time + (i / n) * duration
            t2 = start_time + ((i + 1) / n) * duration
            
            v1 = waveform[i]
            v2 = waveform[i + 1]

            x1 = time_to_x(t1)
            x2 = time_to_x(t2)

            y1 = center_y + v1 * amplitude
            y2 = center_y + v2 * amplitude

            # Calculate alpha for crossfade effect in overlap region
            alpha = 255
            if fade_width > 0 and fade_start <= t1 <= fade_end:
                # Fade based on distance from center of overlap
                center = (fade_start + fade_end) / 2
                dist_from_center = abs(t1 - center) / (fade_width / 2)
                dist_from_center = min(dist_from_center, 1.0)
                
                # Base opacity calculation
                base_alpha = 0.3 + 0.7 * dist_from_center
                
                # Reduce opacity more for compressed (high pitch) waveforms
                # This makes the other track more visible
                if compression_factor > 1.0:
                    # Higher compression = lower opacity in overlap
                    opacity_reduction = min(compression_factor / 3.0, 0.5)  # Cap at 50% reduction
                    base_alpha = base_alpha * (1.0 - opacity_reduction)
                
                alpha = int(255 * base_alpha)

            color = QColor(base_color)
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
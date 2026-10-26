import os
import subprocess
import numpy as np
import imageio_ffmpeg

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QImage


def render_waveform(painter: QPainter, canvas_w: int, canvas_h: int,
                    top_bars: np.ndarray, bottom_bars: np.ndarray,
                    progress: float, params: dict):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)

    num_bars = len(top_bars)
    if num_bars == 0:
        return

    scale_x = canvas_w / 1920.0
    scale_y = canvas_h / 1080.0
    scale_min = min(scale_x, scale_y)
    scale_h = min(scale_y, scale_x * 1.35)

    wave_type = params.get("wave_type", "linear")
    roundness = params["roundness"] / 100.0
    sensitivity = params["sensitivity"] / 100.0
    color1 = QColor(params["color1"])
    color2 = QColor(params["color2"])
    mode = params["mode"]

    if wave_type == "circle":
        cx, cy = canvas_w / 2.0, canvas_h / 2.0
        bass_punch = float(params.get("_bass_punch", 0.0))

        base_radius = (params["wave_width"] * 0.27) * scale_min * (1.0 + 0.11 * bass_punch)
        max_bar_h = (params["max_height"] * 0.62) * scale_min
        thickness = max(2.0, params["bar_thickness"] * scale_min)
        corner_r = (thickness / 2.0) * roundness

        for i in range(num_bars):
            val = float(top_bars[i])
            h = max(thickness, val * max_bar_h * sensitivity)
            angle_deg = (360.0 * i) / num_bars

            bar_ratio = i / max(1, num_bars - 1)
            if mode == 1 and bar_ratio > progress:
                c = QColor(color2)
                c.setAlpha(110)
                painter.setBrush(c)
            else:
                grad = QLinearGradient(0, -base_radius - h * 0.72, 0, -base_radius + h * 0.28)
                grad.setColorAt(0.0, color1)
                grad.setColorAt(1.0, color2)
                painter.setBrush(grad)

            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle_deg)
            rect = QRectF(-thickness / 2.0, -base_radius - h * 0.72, thickness, h)
            if corner_r > 0.2:
                painter.drawRoundedRect(rect, corner_r, corner_r)
            else:
                painter.drawRect(rect)
            painter.restore()
        return

    wave_width = params["wave_width"] * scale_x
    max_height = params["max_height"] * scale_h
    bar_thickness = max(1.5, params["bar_thickness"] * scale_x)
    corner_r = (bar_thickness / 2.0) * roundness

    step = (wave_width - bar_thickness) / (num_bars - 1) if num_bars > 1 else 0
    start_x = (canvas_w - wave_width) / 2.0
    center_y = canvas_h / 2.0

    if wave_type == "split":
        gap = max(1.5, 3.0 * scale_h)
        half_max = max_height * 0.52

        for i in range(num_bars):
            x = start_x + i * step
            h_top = max(bar_thickness * 0.6, float(top_bars[i]) * half_max * sensitivity)
            h_bot = max(bar_thickness * 0.6, float(bottom_bars[i]) * half_max * sensitivity)

            bar_ratio = i / max(1, num_bars - 1)
            alpha = 100 if (mode == 1 and bar_ratio > progress) else 255

            c_top = QColor(color1)
            c_top.setAlpha(alpha)
            painter.setBrush(c_top)
            rect_top = QRectF(x, center_y - gap - h_top, bar_thickness, h_top)
            if corner_r > 0.2:
                painter.drawRoundedRect(rect_top, corner_r, corner_r)
            else:
                painter.drawRect(rect_top)

            c_bot = QColor(color2)
            c_bot.setAlpha(alpha)
            painter.setBrush(c_bot)
            rect_bot = QRectF(x, center_y + gap, bar_thickness, h_bot)
            if corner_r > 0.2:
                painter.drawRoundedRect(rect_bot, corner_r, corner_r)
            else:
                painter.drawRect(rect_bot)
        return

    for i, val in enumerate(top_bars):
        h = max(bar_thickness, float(val) * max_height * sensitivity)
        h = min(h, canvas_h * 0.95)
        x = start_x + i * step
        y = center_y - h / 2.0

        bar_ratio = i / max(1, num_bars - 1)
        if mode == 1:
            if bar_ratio <= progress:
                painter.setBrush(color1)
            else:
                c_unplayed = QColor(color2)
                c_unplayed.setAlpha(110)
                painter.setBrush(c_unplayed)
        else:
            grad = QLinearGradient(x, y, x, y + h)
            grad.setColorAt(0.0, color1)
            grad.setColorAt(0.5, color2)
            grad.setColorAt(1.0, color1)
            painter.setBrush(grad)

        rect = QRectF(x, y, bar_thickness, h)
        if corner_r > 0.2:
            painter.drawRoundedRect(rect, corner_r, corner_r)
        else:
            painter.drawRect(rect)


class ExportWorker(QThread):
    progress_changed = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, audio_path: str, output_path: str, analyzer,
                 params: dict, export_w: int, export_h: int, fps: int,
                 fmt_idx: int, include_audio: bool = True):
        super().__init__()
        self.audio_path = audio_path
        self.output_path = output_path
        self.analyzer = analyzer
        self.params = params.copy()
        self.export_w = export_w
        self.export_h = export_h
        self.fps = fps
        self.fmt_idx = fmt_idx
        self.include_audio = include_audio
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            total_frames = max(1, int(self.analyzer.duration * self.fps))

            if self.fmt_idx == 0:
                v_codec = ["-c:v", "png", "-pix_fmt", "rgba"]
                a_codec = ["-c:a", "aac", "-b:a", "192k"]
            elif self.fmt_idx == 1:
                v_codec = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
                a_codec = ["-c:a", "aac", "-b:a", "192k"]
            else:
                v_codec = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "4M"]
                a_codec = ["-c:a", "libopus", "-b:a", "192k"]

            audio_src = self.analyzer.extracted_wav_path or self.audio_path

            cmd = [
                ffmpeg_exe, "-y", "-loglevel", "error",
                "-f", "rawvideo", "-vcodec", "rawvideo",
                "-s", f"{self.export_w}x{self.export_h}",
                "-pix_fmt", "rgba", "-r", str(self.fps),
                "-i", "-"
            ]

            if self.include_audio and audio_src and os.path.exists(audio_src):
                cmd.extend([
                    "-i", audio_src,
                    "-map", "0:v:0", "-map", "1:a:0",
                    *v_codec, *a_codec, "-shortest", self.output_path
                ])
            else:
                cmd.extend([
                    "-an",
                    *v_codec, self.output_path
                ])

            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, creationflags=flags
            )

            image = QImage(self.export_w, self.export_h, QImage.Format.Format_RGBA8888)

            for frame_idx in range(total_frames):
                if self._is_cancelled:
                    proc.kill()
                    self.finished_signal.emit(False, "Экспорт отменён пользователем.")
                    return

                t_sec = frame_idx / self.fps
                progress = t_sec / max(0.01, self.analyzer.duration)
                top_b, bot_b = self.analyzer.get_frame_data(t_sec, self.params, reset_smoothing=(frame_idx == 0))

                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                render_waveform(painter, self.export_w, self.export_h, top_b, bot_b, progress, self.params)
                painter.end()

                ptr = image.constBits()
                ptr.setsize(image.sizeInBytes())
                proc.stdin.write(bytes(ptr))

                if frame_idx % 5 == 0 or frame_idx == total_frames - 1:
                    self.progress_changed.emit(int((frame_idx + 1) / total_frames * 100))

            proc.stdin.close()
            stderr_out = proc.stderr.read().decode("utf-8", errors="ignore")
            proc.wait()

            if proc.returncode != 0:
                self.finished_signal.emit(False, f"Ошибка FFmpeg:\n{stderr_out}")
            else:
                self.finished_signal.emit(True, self.output_path)

        except Exception as e:
            self.finished_signal.emit(False, str(e))
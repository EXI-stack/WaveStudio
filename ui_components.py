import os
import time
import json
import math
import numpy as np

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSlider, QFileDialog, QComboBox, QProgressBar,
    QFrame, QMessageBox, QGridLayout, QDialog, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, QRectF, QPoint, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPainterPath, QPen, QPolygonF, QLinearGradient
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from config import (
    DEFAULT_PARAMS, SUPPORTED_MEDIA_EXTENSIONS, MODE_DESCRIPTIONS,
    WAVE_PRESETS, DUAL_PALETTES, SINGLE_SWATCHES, APP_STYLESHEET
)
from audio_engine import AudioAnalyzer
from renderer import render_waveform, ExportWorker


class ScrubSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _value_from_mouse(self, pos_x: float) -> int:
        margin = 7.0
        usable_w = max(1.0, self.width() - margin * 2.0)
        ratio = float(np.clip((pos_x - margin) / usable_w, 0.0, 1.0))
        return int(round(self.minimum() + ratio * (self.maximum() - self.minimum())))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self.setValue(self._value_from_mouse(event.position().x()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self._value_from_mouse(event.position().x()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._value_from_mouse(event.position().x()))
            self.setSliderDown(False)
            self.sliderReleased.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class VectorTransportButton(QPushButton):
    def __init__(self, btn_type="play", parent=None):
        super().__init__(parent)
        self.btn_type = btn_type
        self.is_playing = False
        self.volume_level = 90
        self.hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if btn_type == "play":
            self.setFixedSize(48, 48)
        else:
            self.setFixedSize(42, 42)

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        enabled = self.isEnabled()

        painter.setPen(Qt.PenStyle.NoPen)
        if self.btn_type == "play":
            bg = QColor("#252532") if not enabled else (QColor("#8273F7") if self.hovered else QColor("#6C5CE7"))
        else:
            bg = QColor("#323244") if (self.hovered and enabled) else QColor("#252534")
        painter.setBrush(bg)
        painter.drawEllipse(QRectF(2, 2, w - 4, h - 4))

        fg = QColor("#FFFFFF") if enabled else QColor("#58586A")

        if self.btn_type == "play":
            painter.setBrush(fg)
            if self.is_playing:
                bar_w, bar_h = 4.5, 16.0
                painter.drawRoundedRect(QRectF(cx - 6.5, cy - bar_h / 2, bar_w, bar_h), 2, 2)
                painter.drawRoundedRect(QRectF(cx + 2.0, cy - bar_h / 2, bar_w, bar_h), 2, 2)
            else:
                path = QPainterPath()
                offset_x = 2.0
                path.moveTo(cx - 5.5 + offset_x, cy - 8.5)
                path.lineTo(cx + 8.5 + offset_x, cy)
                path.lineTo(cx - 5.5 + offset_x, cy + 8.5)
                path.closeSubpath()
                painter.drawPath(path)
            return

        if self.btn_type == "volume":
            painter.setBrush(fg)
            speaker = QPainterPath()
            speaker.moveTo(cx - 9, cy - 3.5)
            speaker.lineTo(cx - 5, cy - 3.5)
            speaker.lineTo(cx, cy - 8.0)
            speaker.lineTo(cx, cy + 8.0)
            speaker.lineTo(cx - 5, cy + 3.5)
            speaker.lineTo(cx - 9, cy + 3.5)
            speaker.closeSubpath()
            painter.drawPath(speaker)

            pen = QPen(fg, 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if self.volume_level == 0:
                painter.setPen(QPen(QColor("#FF4D6D"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(cx + 3, cy - 4), QPointF(cx + 9, cy + 4))
                painter.drawLine(QPointF(cx + 9, cy - 4), QPointF(cx + 3, cy + 4))
            else:
                if self.volume_level > 5:
                    painter.drawArc(QRectF(cx - 2, cy - 5, 8, 10), -45 * 16, 90 * 16)
                if self.volume_level >= 50:
                    painter.drawArc(QRectF(cx - 4, cy - 8.5, 14, 17), -45 * 16, 90 * 16)
            return

        arc_r = 13.5
        arc_rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
        pen = QPen(fg, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.btn_type == "rewind5":
            painter.drawArc(arc_rect, 130 * 16, -280 * 16)
            angle_rad = math.radians(130)
            tip_x = cx + arc_r * math.cos(angle_rad)
            tip_y = cy - arc_r * math.sin(angle_rad)
            arrow = QPolygonF([
                QPointF(tip_x - 1, tip_y + 4),
                QPointF(tip_x - 4.5, tip_y - 2.5),
                QPointF(tip_x + 3.5, tip_y - 3.0)
            ])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fg)
            painter.drawPolygon(arrow)
            text = "-5"
        else:
            painter.drawArc(arc_rect, 50 * 16, 280 * 16)
            angle_rad = math.radians(50)
            tip_x = cx + arc_r * math.cos(angle_rad)
            tip_y = cy - arc_r * math.sin(angle_rad)
            arrow = QPolygonF([
                QPointF(tip_x + 1, tip_y + 4),
                QPointF(tip_x + 4.5, tip_y - 2.5),
                QPointF(tip_x - 3.5, tip_y - 3.0)
            ])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fg)
            painter.drawPolygon(arrow)
            text = "+5"

        painter.setPen(fg)
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 12, cy - 8, 24, 17), Qt.AlignmentFlag.AlignCenter, text)


class VolumeControlWidget(QWidget):
    volume_changed = pyqtSignal(float)

    def __init__(self, initial_vol=90, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.btn_vol = VectorTransportButton("volume")
        self.btn_vol.volume_level = initial_vol
        self.btn_vol.setToolTip("Громкость воспроизведения")
        self.btn_vol.clicked.connect(self.toggle_popup)
        layout.addWidget(self.btn_vol)

        self.popup_frame = QFrame()
        self.popup_frame.setStyleSheet("""
            QFrame {
                background-color: #242432;
                border: 1px solid #36364A;
                border-radius: 12px;
            }
        """)
        pop_layout = QHBoxLayout(self.popup_frame)
        pop_layout.setContentsMargins(10, 4, 10, 4)
        pop_layout.setSpacing(8)

        self.slider = ScrubSlider(Qt.Orientation.Horizontal)
        self.slider.setFixedWidth(105)
        self.slider.setRange(0, 100)
        self.slider.setValue(initial_vol)
        self.slider.valueChanged.connect(self.on_slider_change)
        self.slider.sliderReleased.connect(self.on_slider_released)

        self.lbl_pct = QLabel(f"{initial_vol}%")
        self.lbl_pct.setFixedWidth(36)
        self.lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_pct.setStyleSheet("border: none; font-size: 12px; font-weight: bold; color: #E2E2EC;")

        pop_layout.addWidget(self.slider)
        pop_layout.addWidget(self.lbl_pct)
        self.popup_frame.setVisible(False)
        layout.addWidget(self.popup_frame)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(1000)
        self.hide_timer.timeout.connect(self.hide_popup_if_idle)

    def toggle_popup(self):
        if not self.popup_frame.isVisible():
            self.popup_frame.setVisible(True)
            self.hide_timer.stop()
        else:
            self.popup_frame.setVisible(False)

    def on_slider_change(self, val: int):
        self.lbl_pct.setText(f"{val}%")
        self.btn_vol.volume_level = val
        self.btn_vol.update()
        self.volume_changed.emit(val / 100.0)

    def on_slider_released(self):
        if not self.underMouse():
            self.hide_timer.start(1000)

    def enterEvent(self, event):
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.popup_frame.isVisible() and not self.slider.isSliderDown():
            self.hide_timer.start(1000)
        super().leaveEvent(event)

    def hide_popup_if_idle(self):
        if not self.underMouse() and not self.slider.isSliderDown():
            self.popup_frame.setVisible(False)


class DualPaletteCard(QPushButton):
    def __init__(self, title: str, c1: str, c2: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.c1 = c1
        self.c2 = c2
        self.hovered = False
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        bg = QColor("#282838") if self.hovered else QColor("#1E1E2A")
        border = QColor("#7C5CFF") if self.hovered else QColor("#323246")
        painter.setPen(QPen(border, 1.5))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 10, 10)

        grad_rect = QRectF(10, 9, 44, h - 18)
        grad = QLinearGradient(grad_rect.topLeft(), grad_rect.topRight())
        grad.setColorAt(0.0, QColor(self.c1))
        grad.setColorAt(1.0, QColor(self.c2))
        painter.setPen(QPen(QColor("#FFFFFF"), 1.0))
        painter.setBrush(grad)
        painter.drawRoundedRect(grad_rect, 7, 7)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(QRectF(64, 0, w - 72, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)


class TargetColorCard(QPushButton):
    def __init__(self, label_prefix: str, parent=None):
        super().__init__(parent)
        self.label_prefix = label_prefix
        self.hex_color = "#FFFFFF"
        self.is_active = False
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        bg = QColor("#262636") if self.is_active else QColor("#1B1B26")
        border = QColor("#8A75FF") if self.is_active else QColor("#2E2E40")
        pen_w = 2.0 if self.is_active else 1.0
        painter.setPen(QPen(border, pen_w))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(1.5, 1.5, w - 3, h - 3), 11, 11)

        painter.setPen(QPen(QColor("#FFFFFF"), 1.0))
        painter.setBrush(QColor(self.hex_color))
        painter.drawRoundedRect(QRectF(12, 9, 26, h - 18), 6, 6)

        painter.setPen(QColor("#FFFFFF") if self.is_active else QColor("#B0B0C0"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold if self.is_active else QFont.Weight.Normal))
        text = f"{self.label_prefix}:  {self.hex_color}"
        painter.drawText(QRectF(48, 0, w - 56, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


class ModernPaletteDialog(QDialog):
    def __init__(self, color1: str, color2: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(650, 560)
        self.setStyleSheet(APP_STYLESHEET)

        self.drag_pos = QPoint()
        self.color1 = color1.upper()
        self.color2 = color2.upper()
        self.active_target = 1

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame(self)
        container.setObjectName("PaletteContainer")
        outer_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(22, 16, 22, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("🎨  Палитра цветов и двойных градиентов")
        title.setObjectName("TitleLabel")
        btn_close = QPushButton("✕")
        btn_close.setObjectName("CloseBtn")
        btn_close.setFixedSize(32, 28)
        btn_close.clicked.connect(self.reject)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(btn_close)
        layout.addLayout(header)

        lbl_dual = QLabel("✨ Готовые двойные сочетания (в один клик):")
        lbl_dual.setStyleSheet("font-weight: bold; color: #CFCFE0;")
        layout.addWidget(lbl_dual)

        dual_grid = QGridLayout()
        dual_grid.setHorizontalSpacing(12)
        dual_grid.setVerticalSpacing(8)
        for idx, (name, c1, c2) in enumerate(DUAL_PALETTES):
            card = DualPaletteCard(name, c1, c2)
            card.clicked.connect(lambda checked, a=c1, b=c2: self.apply_dual(a, b))
            dual_grid.addWidget(card, idx // 2, idx % 2)
        layout.addLayout(dual_grid)

        lbl_edit = QLabel("Нажмите на слот ниже, чтобы изменить его цвет отдельно:")
        lbl_edit.setStyleSheet("color: #9A9AA8; font-size: 12px;")
        layout.addWidget(lbl_edit)

        target_layout = QHBoxLayout()
        target_layout.setSpacing(12)
        self.card_t1 = TargetColorCard("1. Основной / Верх")
        self.card_t2 = TargetColorCard("2. Второй / Бас")
        self.card_t1.clicked.connect(lambda: self.set_target(1))
        self.card_t2.clicked.connect(lambda: self.set_target(2))
        target_layout.addWidget(self.card_t1)
        target_layout.addWidget(self.card_t2)
        layout.addLayout(target_layout)

        swatch_grid = QGridLayout()
        swatch_grid.setSpacing(8)
        for idx, hex_col in enumerate(SINGLE_SWATCHES):
            sw_btn = QPushButton()
            sw_btn.setFixedSize(50, 32)
            sw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            sw_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_col};
                    border-radius: 8px;
                    border: 1px solid #3A3A4E;
                    padding: 0px;
                }}
                QPushButton:hover {{ border: 2px solid #FFFFFF; }}
            """)
            sw_btn.clicked.connect(lambda checked, c=hex_col: self.apply_single(c))
            swatch_grid.addWidget(sw_btn, idx // 10, idx % 10)
        layout.addLayout(swatch_grid)

        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("Плавный спектр оттенка:"))
        self.hue_slider = ScrubSlider(Qt.Orientation.Horizontal)
        self.hue_slider.setRange(0, 359)
        self.hue_slider.valueChanged.connect(self.on_hue_changed)
        custom_layout.addWidget(self.hue_slider, stretch=1)

        custom_layout.addSpacing(10)
        custom_layout.addWidget(QLabel("HEX-код:"))
        self.hex_input = QLineEdit(self.color1)
        self.hex_input.setFixedWidth(95)
        self.hex_input.setFixedHeight(34)
        self.hex_input.textChanged.connect(self.on_hex_typed)
        custom_layout.addWidget(self.hex_input)
        layout.addLayout(custom_layout)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setMinimumHeight(38)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("✔ Применить выбранные цвета")
        btn_ok.setObjectName("AccentBtn")
        btn_ok.setMinimumHeight(38)
        btn_ok.clicked.connect(self.accept)

        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_ok)
        layout.addLayout(bottom)

        self.update_target_cards()

    def set_target(self, idx: int):
        self.active_target = idx
        self.hex_input.blockSignals(True)
        self.hex_input.setText(self.color1 if idx == 1 else self.color2)
        self.hex_input.blockSignals(False)
        self.update_target_cards()

    def apply_dual(self, c1: str, c2: str):
        self.color1 = c1.upper()
        self.color2 = c2.upper()
        self.hex_input.blockSignals(True)
        self.hex_input.setText(self.color1 if self.active_target == 1 else self.color2)
        self.hex_input.blockSignals(False)
        self.update_target_cards()

    def apply_single(self, hex_col: str):
        hex_col = hex_col.upper()
        if self.active_target == 1:
            self.color1 = hex_col
        else:
            self.color2 = hex_col
        self.hex_input.blockSignals(True)
        self.hex_input.setText(hex_col)
        self.hex_input.blockSignals(False)
        self.update_target_cards()

    def on_hue_changed(self, hue: int):
        col = QColor.fromHsv(hue, 215, 255).name().upper()
        self.apply_single(col)

    def on_hex_typed(self, text: str):
        text = text.strip()
        if QColor.isValidColorName(text):
            if self.active_target == 1:
                self.color1 = text.upper()
            else:
                self.color2 = text.upper()
            self.update_target_cards()

    def update_target_cards(self):
        self.card_t1.hex_color = self.color1
        self.card_t1.is_active = (self.active_target == 1)
        self.card_t1.update()

        self.card_t2.hex_color = self.color2
        self.card_t2.is_active = (self.active_target == 2)
        self.card_t2.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 55:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = QPoint()


class WaveformPreviewWidget(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(265)
        self.setMouseTracking(True)
        self.top_bars = np.zeros(50)
        self.bottom_bars = np.zeros(50)
        self.progress = 0.0
        self.duration = 0.0
        self.params = {}

        self.is_scrubbing = False
        self.hover_bar = False
        self.is_drag_over = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_state(self, top_bars: np.ndarray, bottom_bars: np.ndarray,
                     progress: float, duration: float, params: dict):
        self.top_bars = top_bars
        self.bottom_bars = bottom_bars
        if not self.is_scrubbing:
            self.progress = progress
        self.duration = duration
        self.params = params
        self.update()

    def _ratio_from_x(self, x_pos: float) -> float:
        margin = 16.0
        usable_w = max(1.0, self.width() - margin * 2)
        return float(np.clip((x_pos - margin) / usable_w, 0.0, 1.0))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_scrubbing = True
            ratio = self._ratio_from_x(event.position().x())
            self.progress = ratio
            self.seek_requested.emit(ratio)
            self.update()

    def mouseMoveEvent(self, event):
        y = event.position().y()
        self.hover_bar = (y >= self.height() - 32)

        if self.is_scrubbing and (event.buttons() & Qt.MouseButton.LeftButton):
            ratio = self._ratio_from_x(event.position().x())
            self.progress = ratio
            self.seek_requested.emit(ratio)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_scrubbing:
            self.is_scrubbing = False
            ratio = self._ratio_from_x(event.position().x())
            self.progress = ratio
            self.seek_requested.emit(ratio)
            self.update()

    def leaveEvent(self, event):
        self.hover_bar = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 16, 16)
        painter.fillPath(path, QColor("#000000"))
        painter.setPen(QColor("#2A2A35"))
        painter.drawPath(path)

        if self.params:
            render_waveform(
                painter, w, h - 16,
                self.top_bars, self.bottom_bars, self.progress, self.params
            )

        margin = 16.0
        track_w = max(1.0, w - margin * 2)
        bar_h = 6.0 if (self.hover_bar or self.is_scrubbing) else 4.0
        bar_y = h - 13.0 - bar_h / 2.0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#262634"))
        painter.drawRoundedRect(QRectF(margin, bar_y, track_w, bar_h), bar_h / 2, bar_h / 2)

        accent = QColor(self.params.get("color1", "#7C5CFF"))
        fill_w = track_w * self.progress
        painter.setBrush(accent)
        painter.drawRoundedRect(QRectF(margin, bar_y, fill_w, bar_h), bar_h / 2, bar_h / 2)

        handle_x = margin + fill_w
        handle_r = 7.5 if (self.hover_bar or self.is_scrubbing) else 5.0
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#6C5CE7"), 2.0))
        painter.drawEllipse(QPointF(handle_x, bar_y + bar_h / 2.0), handle_r, handle_r)

        if self.is_scrubbing and self.duration > 0:
            sec = int(self.progress * self.duration)
            m, s = divmod(sec, 60)
            time_str = f"{m:02d}:{s:02d}"

            tip_w, tip_h = 54.0, 24.0
            tip_x = np.clip(handle_x - tip_w / 2.0, 10.0, w - tip_w - 10.0)
            tip_y = bar_y - tip_h - 10.0

            painter.setPen(QPen(QColor("#6C5CE7"), 1.2))
            painter.setBrush(QColor("#1A1A26"))
            painter.drawRoundedRect(QRectF(tip_x, tip_y, tip_w, tip_h), 7, 7)

            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(QRectF(tip_x, tip_y, tip_w, tip_h), Qt.AlignmentFlag.AlignCenter, time_str)

        if self.is_drag_over:
            overlay_rect = QRectF(3, 3, w - 6, h - 6)
            painter.setBrush(QColor(18, 18, 28, 215))
            pen = QPen(QColor("#8A75FF"), 2.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(overlay_rect, 14, 14)

            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            painter.drawText(
                overlay_rect,
                Qt.AlignmentFlag.AlignCenter,
                "📥 Отпустите файл для загрузки (Аудио / Видео / Проект .wproj)"
            )


class WaveStudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WaveStudio — Генератор звуковых волн")
        self.resize(1140, 815)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)

        self.drag_pos = QPoint()
        self.audio_path = None
        self.project_path = None
        self.is_modified = False

        self.analyzer = AudioAnalyzer()
        self.export_worker = None
        self.params = DEFAULT_PARAMS.copy()

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.9)

        self._smooth_time_sec = 0.0
        self._last_raw_pos_ms = -1
        self._last_perf_counter = time.perf_counter()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.on_timer_tick)
        self.timer.start()

        self.init_ui()
        self.setStyleSheet(APP_STYLESHEET)
        self.is_modified = False

    def init_ui(self):
        self.central_frame = QFrame(self)
        self.central_frame.setObjectName("MainContainer")
        self.setCentralWidget(self.central_frame)

        main_layout = QVBoxLayout(self.central_frame)
        main_layout.setContentsMargins(20, 14, 20, 18)
        main_layout.setSpacing(12)

        title_bar = QHBoxLayout()
        self.title_label = QLabel("〰️  WaveStudio  |  Генератор аудио-волн без фона")
        self.title_label.setObjectName("TitleLabel")

        btn_open_proj = QPushButton("📂 Открыть проект")
        btn_open_proj.clicked.connect(self.open_project_dialog)

        btn_save_proj = QPushButton("💾 Сохранить проект")
        btn_save_proj.clicked.connect(self.save_project_dialog)

        btn_min = QPushButton("—")
        btn_min.setObjectName("WinBtn")
        btn_min.setFixedSize(32, 28)
        btn_min.clicked.connect(self.showMinimized)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("CloseBtn")
        btn_close.setFixedSize(32, 28)
        btn_close.clicked.connect(self.close)

        title_bar.addWidget(self.title_label)
        title_bar.addStretch()
        title_bar.addWidget(btn_open_proj)
        title_bar.addWidget(btn_save_proj)
        title_bar.addSpacing(8)
        title_bar.addWidget(btn_min)
        title_bar.addWidget(btn_close)
        main_layout.addLayout(title_bar)

        self.preview_widget = WaveformPreviewWidget()
        self.preview_widget.seek_requested.connect(self.seek_audio)
        main_layout.addWidget(self.preview_widget, stretch=1)

        transport_frame = QFrame()
        transport_frame.setObjectName("CardFrame")
        transport_layout = QHBoxLayout(transport_frame)
        transport_layout.setContentsMargins(14, 8, 14, 8)
        transport_layout.setSpacing(10)

        self.btn_load = QPushButton("🎵 Выбрать аудио / видео")
        self.btn_load.setObjectName("AccentBtn")
        self.btn_load.setToolTip(
            "Поддерживаются аудио (.mp3, .wav, .flac, .m4a, .ogg) и видео (.mp4, .mov, .mkv, .avi, .webm).\n"
            "Также можно просто перетащить файл мышкой в окно программы."
        )
        self.btn_load.clicked.connect(self.load_audio_dialog)

        self.btn_rew5 = VectorTransportButton("rewind5")
        self.btn_rew5.setToolTip("Назад на 5 секунд")
        self.btn_rew5.setEnabled(False)
        self.btn_rew5.clicked.connect(lambda: self.skip_seconds(-5.0))

        self.btn_play = VectorTransportButton("play")
        self.btn_play.setToolTip("Воспроизвести / Пауза")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_fwd5 = VectorTransportButton("forward5")
        self.btn_fwd5.setToolTip("Вперёд на 5 секунд")
        self.btn_fwd5.setEnabled(False)
        self.btn_fwd5.clicked.connect(lambda: self.skip_seconds(5.0))

        self.vol_control = VolumeControlWidget(initial_vol=90)
        self.vol_control.volume_changed.connect(self.audio_output.setVolume)

        self.lbl_track = QLabel("Файл не выбран — выберите или перетащите аудио / видео сюда")
        self.lbl_track.setObjectName("MutedLabel")

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setObjectName("TimeLabel")

        transport_layout.addWidget(self.btn_load)
        transport_layout.addSpacing(6)
        transport_layout.addWidget(self.btn_rew5)
        transport_layout.addWidget(self.btn_play)
        transport_layout.addWidget(self.btn_fwd5)
        transport_layout.addWidget(self.vol_control)
        transport_layout.addSpacing(8)
        transport_layout.addWidget(self.lbl_track, stretch=1)
        transport_layout.addWidget(self.lbl_time)
        main_layout.addWidget(transport_frame)

        controls_frame = QFrame()
        controls_frame.setObjectName("CardFrame")
        grid = QGridLayout(controls_frame)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(9)

        grid.addWidget(QLabel("Готовый пресет:"), 0, 0)
        self.combo_preset = QComboBox()
        self.combo_preset.addItems([p["name"] for p in WAVE_PRESETS])
        self.combo_preset.setCurrentIndex(1)
        self.combo_preset.currentIndexChanged.connect(self.apply_preset)
        grid.addWidget(self.combo_preset, 0, 1)

        grid.addWidget(QLabel("Геометрия волны:"), 0, 2)
        self.combo_type = QComboBox()
        self.combo_type.addItems([
            "Обычная / Компактная (Симметричная)",
            "Двухсторонняя (Вокал сверху / Бас снизу)",
            "Круговая волна (Активное кольцо 360°)"
        ])
        self.combo_type.currentIndexChanged.connect(self.on_wave_type_changed)
        grid.addWidget(self.combo_type, 0, 3)

        self.sl_width = self.add_slider(grid, 1, 0, "Длина / Диаметр круга:", 180, 1850, self.params["wave_width"], "wave_width")
        self.sl_height = self.add_slider(grid, 1, 2, "Высота волны (размер):", 50, 950, self.params["max_height"], "max_height")

        self.sl_bars = self.add_slider(grid, 2, 0, "Количество полос:", 5, 160, self.params["num_bars"], "num_bars")
        self.sl_thick = self.add_slider(grid, 2, 2, "Толщина полос:", 2, 48, self.params["bar_thickness"], "bar_thickness")

        self.sl_round = self.add_slider(grid, 3, 0, "Скругление углов (%):", 0, 100, self.params["roundness"], "roundness")
        self.sl_smooth = self.add_slider(grid, 3, 2, "Плавность движения (%):", 10, 92, self.params["smoothing"], "smoothing")

        grid.addWidget(QLabel("Палитра волны:"), 4, 0)
        self.btn_palette = DualPaletteCard("Настроить цвета и градиент", self.params["color1"], self.params["color2"])
        self.btn_palette.clicked.connect(self.open_palette_dialog)
        grid.addWidget(self.btn_palette, 4, 1)

        grid.addWidget(QLabel("Режим анимации:"), 4, 2)
        mode_box = QVBoxLayout()
        mode_box.setContentsMargins(0, 0, 0, 0)
        mode_box.setSpacing(3)

        self.combo_mode = QComboBox()
        for idx, (m_title, m_desc) in enumerate(MODE_DESCRIPTIONS):
            self.combo_mode.addItem(m_title)
            self.combo_mode.setItemData(idx, m_desc, Qt.ItemDataRole.ToolTipRole)
        self.combo_mode.setToolTip(MODE_DESCRIPTIONS[0][1])
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)

        self.lbl_mode_hint = QLabel(f"💡 {MODE_DESCRIPTIONS[0][1]}")
        self.lbl_mode_hint.setObjectName("HintLabel")
        self.lbl_mode_hint.setWordWrap(True)

        mode_box.addWidget(self.combo_mode)
        mode_box.addWidget(self.lbl_mode_hint)
        grid.addLayout(mode_box, 4, 3)

        main_layout.addWidget(controls_frame)

        export_frame = QFrame()
        export_frame.setObjectName("CardFrame")
        export_layout = QHBoxLayout(export_frame)
        export_layout.setContentsMargins(14, 10, 14, 10)
        export_layout.setSpacing(8)

        export_layout.addWidget(QLabel("Формат:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems([
            "MOV (PNG Alpha — все редакторы)",
            "MOV (Apple ProRes 4444)",
            "WEBM (VP9 Alpha — лёгкий вес)"
        ])
        self.combo_format.setToolTip("Все форматы сохраняют прозрачный фон (альфа-канал)")
        export_layout.addWidget(self.combo_format, stretch=1)

        export_layout.addWidget(QLabel("Разрешение:"))
        self.combo_res = QComboBox()
        self.combo_res.addItems([
            "1920x1080 — Full HD (16:9)",
            "1280x720 — HD (16:9)",
            "1080x1080 — Квадрат (Обложки)",
            "1080x1920 — Reels / Shorts / TikTok"
        ])
        export_layout.addWidget(self.combo_res)

        export_layout.addWidget(QLabel("FPS:"))
        self.combo_fps = QComboBox()
        self.combo_fps.addItems(["60 FPS", "30 FPS"])
        self.combo_fps.setToolTip("Частота кадров экспортируемого видео")
        export_layout.addWidget(self.combo_fps)

        export_layout.addWidget(QLabel("Аудио:"))
        self.combo_audio = QComboBox()
        self.combo_audio.addItems([
            "🔊 Со звуком",
            "🔇 Без звука"
        ])
        self.combo_audio.setToolTip(
            "Со звуком: видео + аудиодорожка.\n"
            "Без звука: только прозрачное видео длительностью аудиофайла."
        )
        export_layout.addWidget(self.combo_audio)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(130)
        self.progress_bar.setVisible(False)
        export_layout.addWidget(self.progress_bar)

        self.btn_export = QPushButton("🎬 Рендер видео")
        self.btn_export.setObjectName("ExportBtn")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.start_export)
        export_layout.addWidget(self.btn_export)

        main_layout.addWidget(export_frame)

    def add_slider(self, grid: QGridLayout, row: int, col: int, title: str,
                   min_v: int, max_v: int, init_v: int, param_key: str) -> ScrubSlider:
        lbl = QLabel(f"{title} {init_v}")
        slider = ScrubSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_v, max_v)
        slider.setValue(init_v)

        def on_change(val):
            lbl.setText(f"{title} {val}")
            self.mark_modified(param_key, val)

        slider.valueChanged.connect(on_change)
        grid.addWidget(lbl, row, col)
        grid.addWidget(slider, row, col + 1)
        return slider

    def on_mode_changed(self, idx: int):
        if 0 <= idx < len(MODE_DESCRIPTIONS):
            desc = MODE_DESCRIPTIONS[idx][1]
            self.combo_mode.setToolTip(desc)
            self.lbl_mode_hint.setText(f"💡 {desc}")
        self.mark_modified("mode", idx)

    def mark_modified(self, key: str = None, val=None):
        if key is not None:
            self.params[key] = val
        self.is_modified = True
        if not self.title_label.text().endswith(" *"):
            self.title_label.setText("〰️  WaveStudio  |  Генератор аудио-волн без фона *")

    def on_wave_type_changed(self, idx: int):
        types = ["linear", "split", "circle"]
        self.mark_modified("wave_type", types[idx])

    def apply_preset(self, idx: int):
        p = WAVE_PRESETS[idx]
        self.params["preset_idx"] = idx

        type_map = {"linear": 0, "split": 1, "circle": 2}
        self.combo_type.setCurrentIndex(type_map.get(p["wave_type"], 0))

        self.sl_bars.setValue(p["num_bars"])
        self.sl_thick.setValue(p["bar_thickness"])
        self.sl_round.setValue(p["roundness"])
        self.sl_width.setValue(p["wave_width"])
        self.sl_height.setValue(p["max_height"])

        if "color1" in p and "color2" in p:
            self.params["color1"] = p["color1"]
            self.params["color2"] = p["color2"]
            self.update_palette_button()

        self.mark_modified()

    def open_palette_dialog(self):
        dlg = ModernPaletteDialog(self.params["color1"], self.params["color2"], self)
        if dlg.exec():
            if dlg.color1 != self.params["color1"] or dlg.color2 != self.params["color2"]:
                self.params["color1"] = dlg.color1
                self.params["color2"] = dlg.color2
                self.update_palette_button()
                self.mark_modified()

    def update_palette_button(self):
        self.btn_palette.c1 = self.params["color1"]
        self.btn_palette.c2 = self.params["color2"]
        self.btn_palette.title = f"{self.params['color1']}  •  {self.params['color2']}"
        self.btn_palette.update()

    def _extract_valid_dropped_file(self, mime_data) -> str:
        if not mime_data.hasUrls():
            return ""
        for url in mime_data.urls():
            local_path = url.toLocalFile()
            if local_path and os.path.isfile(local_path):
                ext = os.path.splitext(local_path)[1].lower()
                if ext in SUPPORTED_MEDIA_EXTENSIONS or ext == ".wproj":
                    return local_path
        return ""

    def dragEnterEvent(self, event):
        valid_path = self._extract_valid_dropped_file(event.mimeData())
        if valid_path:
            event.acceptProposedAction()
            self.preview_widget.is_drag_over = True
            self.preview_widget.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        valid_path = self._extract_valid_dropped_file(event.mimeData())
        if valid_path:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.preview_widget.is_drag_over = False
        self.preview_widget.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.preview_widget.is_drag_over = False
        self.preview_widget.update()

        file_path = self._extract_valid_dropped_file(event.mimeData())
        if not file_path:
            return

        event.acceptProposedAction()
        if file_path.lower().endswith(".wproj"):
            self.load_project_from_path(file_path)
        else:
            self.load_audio_file(file_path)

    def load_audio_dialog(self):
        ext_filter = " ".join(f"*{ext}" for ext in SUPPORTED_MEDIA_EXTENSIONS)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите аудио или видеофайл",
            "",
            f"Аудио и Видео ({ext_filter});;Все файлы (*.*)"
        )
        if file_path:
            self.load_audio_file(file_path)

    def load_audio_file(self, file_path: str):
        try:
            self.lbl_track.setText("Извлечение аудио и анализ частот (Бас / Вокал)...")
            self.player.stop()
            self.analyzer.load_audio(file_path)
            self.audio_path = file_path

            play_source = self.analyzer.extracted_wav_path or file_path
            self.player.setSource(QUrl.fromLocalFile(play_source))

            self.btn_play.setEnabled(True)
            self.btn_rew5.setEnabled(True)
            self.btn_fwd5.setEnabled(True)
            self.btn_export.setEnabled(True)
            self.lbl_track.setText(f"🎵 {os.path.basename(file_path)}")

            self._smooth_time_sec = 0.0
            self._last_raw_pos_ms = 0
            self._last_perf_counter = time.perf_counter()

            self.player.play()
            self.btn_play.is_playing = True
            self.btn_play.update()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки", f"Не удалось обработать медиафайл:\n{e}")
            self.lbl_track.setText("Ошибка чтения файла")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play.is_playing = False
        else:
            self._last_perf_counter = time.perf_counter()
            self.player.play()
            self.btn_play.is_playing = True
        self.btn_play.update()

    def skip_seconds(self, delta_sec: float):
        if self.analyzer.duration > 0:
            new_pos = int(np.clip(self.player.position() + delta_sec * 1000, 0, self.analyzer.duration * 1000))
            self.player.setPosition(new_pos)
            self._smooth_time_sec = new_pos / 1000.0
            self._last_raw_pos_ms = new_pos
            self._last_perf_counter = time.perf_counter()

    def seek_audio(self, ratio: float):
        if self.analyzer.duration > 0:
            new_pos = int(ratio * self.analyzer.duration * 1000)
            self.player.setPosition(new_pos)
            self._smooth_time_sec = new_pos / 1000.0
            self._last_raw_pos_ms = new_pos
            self._last_perf_counter = time.perf_counter()

    def on_timer_tick(self):
        now_perf = time.perf_counter()
        dt = min(0.1, max(0.0, now_perf - self._last_perf_counter))
        self._last_perf_counter = now_perf

        if self.audio_path and self.analyzer.duration > 0:
            raw_pos_ms = self.player.position()
            raw_sec = raw_pos_ms / 1000.0
            is_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

            if is_playing:
                if raw_pos_ms != self._last_raw_pos_ms:
                    self._last_raw_pos_ms = raw_pos_ms
                    if abs(raw_sec - self._smooth_time_sec) > 0.06:
                        self._smooth_time_sec = raw_sec
                    else:
                        self._smooth_time_sec = self._smooth_time_sec * 0.65 + raw_sec * 0.35
                else:
                    self._smooth_time_sec = min(self.analyzer.duration, self._smooth_time_sec + dt)
            else:
                self._smooth_time_sec = raw_sec
                self._last_raw_pos_ms = raw_pos_ms

            t_sec = float(np.clip(self._smooth_time_sec, 0.0, self.analyzer.duration))
            progress = np.clip(t_sec / self.analyzer.duration, 0.0, 1.0)

            cur_m, cur_s = divmod(int(t_sec), 60)
            tot_m, tot_s = divmod(int(self.analyzer.duration), 60)
            self.lbl_time.setText(f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}")

            if self.btn_play.is_playing != is_playing:
                self.btn_play.is_playing = is_playing
                self.btn_play.update()

            top_b, bot_b = self.analyzer.get_frame_data(t_sec, self.params)
            dur = self.analyzer.duration
        else:
            progress = 0.0
            dur = 0.0
            top_b, bot_b = self.analyzer.get_frame_data(0.0, self.params)

        self.preview_widget.update_state(top_b, bot_b, progress, dur, self.params)

    def save_project_dialog(self) -> bool:
        default_name = self.project_path or "my_waveform.wproj"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить проект WaveStudio", default_name, "Проект WaveStudio (*.wproj)")
        if not path:
            return False

        data = {"audio_path": self.audio_path, "params": self.params}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.project_path = path
            self.is_modified = False
            self.title_label.setText(f"〰️  WaveStudio  |  {os.path.basename(path)}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить проект:\n{e}")
            return False

    def open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть проект WaveStudio", "", "Проект WaveStudio (*.wproj)")
        if path:
            self.load_project_from_path(path)

    def load_project_from_path(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.params.update(data.get("params", {}))
            type_map = {"linear": 0, "split": 1, "circle": 2}
            self.combo_type.setCurrentIndex(type_map.get(self.params.get("wave_type", "linear"), 0))
            self.combo_mode.setCurrentIndex(self.params.get("mode", 0))
            self.sl_width.setValue(self.params["wave_width"])
            self.sl_height.setValue(self.params["max_height"])
            self.sl_bars.setValue(self.params["num_bars"])
            self.sl_thick.setValue(self.params["bar_thickness"])
            self.sl_round.setValue(self.params["roundness"])
            self.sl_smooth.setValue(self.params["smoothing"])
            self.update_palette_button()

            audio_p = data.get("audio_path")
            if audio_p and os.path.exists(audio_p):
                self.load_audio_file(audio_p)

            self.project_path = path
            self.is_modified = False
            self.title_label.setText(f"〰️  WaveStudio  |  {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть проект:\n{e}")

    def closeEvent(self, event):
        if self.is_modified:
            msg = QMessageBox(self)
            msg.setWindowTitle("Сохранение проекта")
            msg.setText("Вы изменили настройки звуковой волны.\nХотите сохранить проект перед выходом?")
            msg.setIcon(QMessageBox.Icon.Question)

            btn_save = msg.addButton("💾 Сохранить", QMessageBox.ButtonRole.AcceptRole)
            btn_discard = msg.addButton("Не сохранять", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
            msg.setStyleSheet(APP_STYLESHEET + "QMessageBox { background-color: #181822; }")

            msg.exec()
            clicked = msg.clickedButton()

            if clicked == btn_save:
                if not self.save_project_dialog():
                    event.ignore()
                    return
            elif clicked == btn_cancel:
                event.ignore()
                return

        self.player.stop()
        self.analyzer.cleanup_temp()
        event.accept()

    def start_export(self):
        if self.export_worker and self.export_worker.isRunning():
            self.export_worker.cancel()
            return
        if not self.audio_path:
            return

        self.player.pause()
        self.btn_play.is_playing = False
        self.btn_play.update()

        fmt_idx = self.combo_format.currentIndex()
        ext = ".mov" if fmt_idx in (0, 1) else ".webm"
        default_name = os.path.splitext(os.path.basename(self.audio_path))[0] + f"_wave{ext}"
        out_path, _ = QFileDialog.getSaveFileName(self, "Сохранить прозрачное видео", default_name, f"Видео (*{ext})")
        if not out_path:
            return

        res_map = {
            0: (1920, 1080),
            1: (1280, 720),
            2: (1080, 1080),
            3: (1080, 1920),
        }
        export_w, export_h = res_map.get(self.combo_res.currentIndex(), (1920, 1080))
        fps = 60 if self.combo_fps.currentIndex() == 0 else 30
        include_audio = (self.combo_audio.currentIndex() == 0)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_export.setText("✖ Отменить")
        self.btn_load.setEnabled(False)

        self.export_worker = ExportWorker(
            self.audio_path, out_path, self.analyzer,
            self.params, export_w, export_h, fps=fps,
            fmt_idx=fmt_idx, include_audio=include_audio
        )
        self.export_worker.progress_changed.connect(self.progress_bar.setValue)
        self.export_worker.finished_signal.connect(self.on_export_finished)
        self.export_worker.start()

    def on_export_finished(self, success: bool, msg: str):
        self.progress_bar.setVisible(False)
        self.btn_export.setText("🎬 Рендер видео")
        self.btn_load.setEnabled(True)
        if success:
            QMessageBox.information(self, "Готово!", f"Прозрачное видео сохранено:\n{msg}")
        else:
            QMessageBox.warning(self, "Экспорт", msg)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 55:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = QPoint()
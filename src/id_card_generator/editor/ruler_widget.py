"""Photoshop-inspired canvas rulers and container with cursor tracking and physical unit support."""

import math
from typing import Optional
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.editor.canvas_view import CanvasView


class RulerCorner(QWidget):
    """Top-left 22x22 corner box toggling ruler display units (px / mm)."""

    unit_toggled = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.unit = "px"
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to toggle ruler unit (pixels / millimeters)")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.unit = "mm" if self.unit == "px" else "px"
            self.unit_toggled.emit(self.unit)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#222224"))

        # Right and bottom border lines
        painter.setPen(QColor("#3A3A3D"))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height() - 1)
        painter.drawLine(0, self.height() - 1, self.width() - 1, self.height() - 1)

        # Label
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.setPen(QColor("#9CA3AF"))
        painter.drawText(self.rect(), Qt.AlignCenter, self.unit)


class HorizontalRuler(QWidget):
    """Horizontal ruler showing scale and tracking cursor X coordinate."""

    def __init__(self, view: CanvasView, parent=None):
        super().__init__(parent)
        self.view = view
        self.setFixedHeight(22)
        self.cursor_x: Optional[float] = None
        self.unit = "px"
        self.dpi = 300

    def set_unit(self, unit: str, dpi: int = 300) -> None:
        self.unit = unit
        self.dpi = dpi
        self.update()

    def set_cursor_pos(self, scene_x: Optional[float]) -> None:
        self.cursor_x = scene_x
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#222224"))

        # Bottom border
        painter.setPen(QColor("#3A3A3D"))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        if not self.view or not self.view.scene():
            return

        transform = self.view.transform()
        scale = transform.m11()
        if scale <= 0:
            return

        # Viewport visible scene range
        vp_rect = self.view.viewport().rect()
        scene_left = self.view.mapToScene(0, 0).x()
        scene_right = self.view.mapToScene(vp_rect.width(), 0).x()

        # Step calculation based on scale
        base_step = 100.0 if self.unit == "px" else (10.0 * self.dpi / 25.4)
        if scale > 2.5:
            step = base_step / 2
        elif scale < 0.6:
            step = base_step * 2
        else:
            step = base_step

        start_val = math.floor(scene_left / step) * step
        end_val = math.ceil(scene_right / step) * step

        painter.setFont(QFont("Segoe UI", 7))
        pen_tick = QPen(QColor("#6B7280"), 1)
        pen_sub = QPen(QColor("#4B5563"), 1)

        val = start_val
        while val <= end_val:
            pt_view = self.view.mapFromScene(val, 0)
            vx = pt_view.x()
            if 0 <= vx <= self.width():
                # Major tick
                painter.setPen(pen_tick)
                painter.drawLine(vx, self.height() - 8, vx, self.height() - 1)

                # Label
                label_num = int(val) if self.unit == "px" else int(val / self.dpi * 25.4)
                painter.setPen(QColor("#9CA3AF"))
                painter.drawText(vx + 3, 11, str(label_num))

                # Minor sub-ticks (4 intermediate ticks)
                painter.setPen(pen_sub)
                for i in range(1, 5):
                    sub_val = val + (step * i / 5.0)
                    svx = self.view.mapFromScene(sub_val, 0).x()
                    if 0 <= svx <= self.width():
                        h_tick = 5 if i == 2 or i == 3 else 3
                        painter.drawLine(svx, self.height() - h_tick, svx, self.height() - 1)

            val += step

        # Cursor position hairline indicator
        if self.cursor_x is not None:
            cx = self.view.mapFromScene(self.cursor_x, 0).x()
            if 0 <= cx <= self.width():
                painter.setPen(QPen(QColor("#EF4444"), 1))  # Red hairline
                painter.drawLine(cx, 0, cx, self.height())


class VerticalRuler(QWidget):
    """Vertical ruler showing scale and tracking cursor Y coordinate."""

    def __init__(self, view: CanvasView, parent=None):
        super().__init__(parent)
        self.view = view
        self.setFixedWidth(22)
        self.cursor_y: Optional[float] = None
        self.unit = "px"
        self.dpi = 300

    def set_unit(self, unit: str, dpi: int = 300) -> None:
        self.unit = unit
        self.dpi = dpi
        self.update()

    def set_cursor_pos(self, scene_y: Optional[float]) -> None:
        self.cursor_y = scene_y
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#222224"))

        # Right border
        painter.setPen(QColor("#3A3A3D"))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        if not self.view or not self.view.scene():
            return

        transform = self.view.transform()
        scale = transform.m22()
        if scale <= 0:
            return

        vp_rect = self.view.viewport().rect()
        scene_top = self.view.mapToScene(0, 0).y()
        scene_bottom = self.view.mapToScene(0, vp_rect.height()).y()

        base_step = 100.0 if self.unit == "px" else (10.0 * self.dpi / 25.4)
        if scale > 2.5:
            step = base_step / 2
        elif scale < 0.6:
            step = base_step * 2
        else:
            step = base_step

        start_val = math.floor(scene_top / step) * step
        end_val = math.ceil(scene_bottom / step) * step

        painter.setFont(QFont("Segoe UI", 7))
        pen_tick = QPen(QColor("#6B7280"), 1)
        pen_sub = QPen(QColor("#4B5563"), 1)

        val = start_val
        while val <= end_val:
            pt_view = self.view.mapFromScene(0, val)
            vy = pt_view.y()
            if 0 <= vy <= self.height():
                # Major tick
                painter.setPen(pen_tick)
                painter.drawLine(self.width() - 8, vy, self.width() - 1, vy)

                # Label (rotated or offset text)
                label_num = int(val) if self.unit == "px" else int(val / self.dpi * 25.4)
                painter.setPen(QColor("#9CA3AF"))
                painter.save()
                painter.translate(3, vy - 2)
                painter.drawText(0, 0, str(label_num))
                painter.restore()

                # Minor sub-ticks
                painter.setPen(pen_sub)
                for i in range(1, 5):
                    sub_val = val + (step * i / 5.0)
                    svy = self.view.mapFromScene(0, sub_val).y()
                    if 0 <= svy <= self.height():
                        w_tick = 5 if i == 2 or i == 3 else 3
                        painter.drawLine(self.width() - w_tick, svy, self.width() - 1, svy)

            val += step

        # Cursor position hairline indicator
        if self.cursor_y is not None:
            cy = self.view.mapFromScene(0, self.cursor_y).y()
            if 0 <= cy <= self.height():
                painter.setPen(QPen(QColor("#EF4444"), 1))
                painter.drawLine(0, cy, self.width(), cy)


class CanvasContainer(QWidget):
    """Photoshop-style canvas viewport container integrating rulers, canvas, and floating HUD."""

    def __init__(self, view: CanvasView, parent=None):
        super().__init__(parent)
        self.view = view

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Corner unit toggle widget
        self.corner = RulerCorner(self)
        self.corner.unit_toggled.connect(self._on_unit_toggled)
        layout.addWidget(self.corner, 0, 0)

        # 2. Horizontal ruler
        self.ruler_h = HorizontalRuler(self.view, self)
        layout.addWidget(self.ruler_h, 0, 1)

        # 3. Vertical ruler
        self.ruler_v = VerticalRuler(self.view, self)
        layout.addWidget(self.ruler_v, 1, 0)

        # 4. Central Canvas View with Overlay HUD
        self.center_frame = QFrame(self)
        self.center_frame.setFrameShape(QFrame.NoFrame)
        center_layout = QVBoxLayout(self.center_frame)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.view, stretch=1)

        # Floating HUD bar at bottom of canvas
        self.hud_bar = QFrame(self.center_frame)
        self.hud_bar.setObjectName("card_panel")
        self.hud_bar.setFixedHeight(34)
        self.hud_bar.setStyleSheet(
            "background: rgba(24, 24, 27, 0.90); border-top: 1px solid #3F3F46; padding: 2px 8px;"
        )
        hud_layout = QHBoxLayout(self.hud_bar)
        hud_layout.setContentsMargins(8, 2, 8, 2)
        hud_layout.setSpacing(8)

        # Zoom controls
        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setText("−")
        self.btn_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        self.btn_zoom_out.clicked.connect(self.view.zoom_out)
        hud_layout.addWidget(self.btn_zoom_out)

        self.slider_zoom = QSlider(Qt.Horizontal)
        self.slider_zoom.setRange(20, 500)
        self.slider_zoom.setValue(100)
        self.slider_zoom.setFixedWidth(100)
        self.slider_zoom.valueChanged.connect(lambda v: self.view.set_zoom(v / 100.0))
        hud_layout.addWidget(self.slider_zoom)

        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setText("+")
        self.btn_zoom_in.setToolTip("Zoom In (Ctrl++)")
        self.btn_zoom_in.clicked.connect(self.view.zoom_in)
        hud_layout.addWidget(self.btn_zoom_in)

        self.lbl_zoom_val = QLabel("100%")
        self.lbl_zoom_val.setStyleSheet("color: #E2E8F0; font-weight: bold; font-size: 11px;")
        hud_layout.addWidget(self.lbl_zoom_val)

        hud_layout.addSpacing(8)

        # View action buttons
        self.btn_fit = QPushButton("⊡ Fit Card")
        self.btn_fit.setToolTip("Fit card template inside screen (Ctrl+0)")
        self.btn_fit.clicked.connect(self.view.fit_to_view)
        hud_layout.addWidget(self.btn_fit)

        self.btn_100 = QPushButton("1:1 Actual")
        self.btn_100.setToolTip("Zoom to 100% actual print resolution (Ctrl+1)")
        self.btn_100.clicked.connect(self.view.reset_zoom)
        hud_layout.addWidget(self.btn_100)

        hud_layout.addStretch()

        # Canvas guide toggles
        self.btn_toggle_grid = QToolButton()
        self.btn_toggle_grid.setText("▦ Grid")
        self.btn_toggle_grid.setCheckable(True)
        self.btn_toggle_grid.setChecked(True)
        self.btn_toggle_grid.setToolTip("Toggle Grid Overlay (Ctrl+')")
        self.btn_toggle_grid.toggled.connect(self._toggle_grid)
        hud_layout.addWidget(self.btn_toggle_grid)

        self.btn_toggle_snap = QToolButton()
        self.btn_toggle_snap.setText("🧲 Snap")
        self.btn_toggle_snap.setCheckable(True)
        self.btn_toggle_snap.setChecked(True)
        self.btn_toggle_snap.setToolTip("Toggle Grid Snapping")
        self.btn_toggle_snap.toggled.connect(self._toggle_snap)
        hud_layout.addWidget(self.btn_toggle_snap)

        self.btn_toggle_safe = QToolButton()
        self.btn_toggle_safe.setText("⛶ Safe Margins")
        self.btn_toggle_safe.setCheckable(True)
        self.btn_toggle_safe.setChecked(True)
        self.btn_toggle_safe.setToolTip("Toggle Safe Area Guidelines")
        self.btn_toggle_safe.toggled.connect(self._toggle_safe_area)
        hud_layout.addWidget(self.btn_toggle_safe)

        center_layout.addWidget(self.hud_bar)
        layout.addWidget(self.center_frame, 1, 1)

        # Connect scrollbars & zoom to update rulers
        self.view.horizontalScrollBar().valueChanged.connect(lambda _: self.ruler_h.update())
        self.view.verticalScrollBar().valueChanged.connect(lambda _: self.ruler_v.update())
        self.view.zoom_changed.connect(self._on_zoom_changed)

    def _on_unit_toggled(self, unit: str) -> None:
        dpi = 300
        if self.view.scene() and hasattr(self.view.scene(), "template") and self.view.scene().template:
            dpi = self.view.scene().template.dpi
        self.ruler_h.set_unit(unit, dpi)
        self.ruler_v.set_unit(unit, dpi)

    def _on_zoom_changed(self, factor: float) -> None:
        pct = int(round(factor * 100))
        self.lbl_zoom_val.setText(f"{pct}%")
        self.slider_zoom.blockSignals(True)
        self.slider_zoom.setValue(pct)
        self.slider_zoom.blockSignals(False)
        self.ruler_h.update()
        self.ruler_v.update()

    def update_cursor_pos(self, scene_pos: QPointF) -> None:
        self.ruler_h.set_cursor_pos(scene_pos.x())
        self.ruler_v.set_cursor_pos(scene_pos.y())

    def _toggle_grid(self, checked: bool) -> None:
        if self.view.scene():
            self.view.scene().show_grid = checked
            self.view.scene().update()

    def _toggle_snap(self, checked: bool) -> None:
        if self.view.scene():
            self.view.scene().snap_to_grid = checked

    def _toggle_safe_area(self, checked: bool) -> None:
        if self.view.scene():
            self.view.scene().show_safe_area = checked
            self.view.scene().update()

    def toggle_rulers(self) -> bool:
        """Toggle ruler visibility."""
        vis = not self.ruler_h.isVisible()
        self.ruler_h.setVisible(vis)
        self.ruler_v.setVisible(vis)
        self.corner.setVisible(vis)
        return vis


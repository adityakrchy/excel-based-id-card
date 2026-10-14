"""Interactive canvas graphics item supporting selection, dragging, resizing, and live preview."""

from pathlib import Path
from typing import Dict, Optional
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneMouseEvent,
)

from id_card_generator.core.constants import ImageFitMode
from id_card_generator.core.models import CanvasElement, SourceRecord


class CanvasItem(QGraphicsObject):
    """QGraphicsItem representing an editable element on the ID card canvas."""

    # Signals
    geometry_changed = Signal(object)
    selected_changed = Signal(object)

    HANDLE_SIZE = 8.0
    # Handles: 0:TL, 1:T, 2:TR, 3:R, 4:BR, 5:B, 6:BL, 7:L
    HANDLE_NAMES = ["TL", "T", "TR", "R", "BR", "B", "BL", "L"]

    def __init__(self, element: CanvasElement, parent=None):
        super().__init__(parent)
        self.element = element
        self._rect = QRectF(0, 0, element.width, element.height)
        self.setPos(element.x, element.y)
        self.setZValue(element.z_index)

        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self._active_handle: Optional[int] = None
        self._drag_start_pos: Optional[QPointF] = None
        self._drag_start_rect: Optional[QRectF] = None

        # Sample record data for preview
        self._sample_record: Optional[SourceRecord] = None
        self._sample_photo_path: Optional[str] = None
        self._cached_pixmap: Optional[QPixmap] = None

    def boundingRect(self) -> QRectF:
        pad = self.HANDLE_SIZE + 2.0
        return self._rect.adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect)
        if self.isSelected():
            for handle_rect in self._get_handle_rects().values():
                path.addRect(handle_rect)
        return path

    def set_rect(self, rect: QRectF) -> None:
        """Update rectangle dimensions."""
        self.prepareGeometryChange()
        self._rect = rect
        self.element.width = max(10.0, rect.width())
        self.element.height = max(10.0, rect.height())
        self.update()
        self.geometry_changed.emit(self)

    def update_model_position(self) -> None:
        """Sync Qt item position to model coordinates."""
        self.element.x = self.pos().x()
        self.element.y = self.pos().y()
        self.geometry_changed.emit(self)

    def set_sample_data(self, record: Optional[SourceRecord], photo_path: Optional[str]) -> None:
        """Update sample record for live WYSIWYG rendering on the canvas."""
        self._sample_record = record
        self._sample_photo_path = photo_path
        self._cached_pixmap = None
        self.update()

    def _get_handle_rects(self) -> Dict[int, QRectF]:
        """Compute the 8 resize handle bounding rectangles in local coordinates."""
        r = self._rect
        s = self.HANDLE_SIZE
        hs = s / 2.0

        return {
            0: QRectF(r.left() - hs, r.top() - hs, s, s),
            1: QRectF(r.center().x() - hs, r.top() - hs, s, s),
            2: QRectF(r.right() - hs, r.top() - hs, s, s),
            3: QRectF(r.right() - hs, r.center().y() - hs, s, s),
            4: QRectF(r.right() - hs, r.bottom() - hs, s, s),
            5: QRectF(r.center().x() - hs, r.bottom() - hs, s, s),
            6: QRectF(r.left() - hs, r.bottom() - hs, s, s),
            7: QRectF(r.left() - hs, r.center().y() - hs, s, s),
        }

    def _get_handle_at(self, pos: QPointF) -> Optional[int]:
        if not self.isSelected() or self.element.locked:
            return None
        for handle_idx, handle_rect in self._get_handle_rects().items():
            if handle_rect.contains(pos):
                return handle_idx
        return None

    def hoverMoveEvent(self, event):
        if not self.element.locked:
            handle = self._get_handle_at(event.pos())
            if handle in (0, 4):
                self.setCursor(Qt.SizeFDiagCursor)
            elif handle in (2, 6):
                self.setCursor(Qt.SizeBDiagCursor)
            elif handle in (1, 5):
                self.setCursor(Qt.SizeVerCursor)
            elif handle in (3, 7):
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.SizeAllCursor if self.isSelected() else Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if self.element.locked:
            event.ignore()
            return

        handle = self._get_handle_at(event.pos())
        if handle is not None:
            self._active_handle = handle
            self._drag_start_pos = event.pos()
            self._drag_start_rect = QRectF(self._rect)
            event.accept()
            return

        self._active_handle = None
        super().mousePressEvent(event)
        self.selected_changed.emit(self)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._active_handle is not None and self._drag_start_rect is not None:
            delta = event.pos() - self._drag_start_pos
            new_rect = QRectF(self._drag_start_rect)
            handle = self._active_handle

            # Adjust new_rect based on handle
            if handle == 0:  # TL
                new_rect.setTopLeft(new_rect.topLeft() + delta)
            elif handle == 1:  # T
                new_rect.setTop(new_rect.top() + delta.y())
            elif handle == 2:  # TR
                new_rect.setTopRight(new_rect.topRight() + delta)
            elif handle == 3:  # R
                new_rect.setRight(new_rect.right() + delta.x())
            elif handle == 4:  # BR
                new_rect.setBottomRight(new_rect.bottomRight() + delta)
            elif handle == 5:  # B
                new_rect.setBottom(new_rect.bottom() + delta.y())
            elif handle == 6:  # BL
                new_rect.setBottomLeft(new_rect.bottomLeft() + delta)
            elif handle == 7:  # L
                new_rect.setLeft(new_rect.left() + delta.x())

            # Enforce minimum size
            if new_rect.width() >= 10.0 and new_rect.height() >= 10.0:
                self.set_rect(new_rect)
            event.accept()
            return

        super().mouseMoveEvent(event)
        self.update_model_position()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        self._active_handle = None
        self._drag_start_pos = None
        self._drag_start_rect = None
        super().mouseReleaseEvent(event)
        self.update_model_position()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        elem = self.element
        rect = self._rect

        # 1. Background fill & border
        bg_color = elem.style.background_color
        border_color = elem.style.border_color
        border_width = elem.style.border_width
        radius = elem.style.border_radius

        if border_color != "transparent" and border_width > 0:
            pen = QPen(QColor(border_color), border_width)
        else:
            pen = QPen(Qt.NoPen)
        brush = QBrush(QColor(bg_color)) if bg_color != "transparent" else QBrush(Qt.NoBrush)
        painter.setPen(pen)
        painter.setBrush(brush)

        if elem.type in ("rect", "round_rect"):
            if radius > 0 or elem.type == "round_rect":
                painter.drawRoundedRect(rect, radius, radius)
            else:
                painter.drawRect(rect)

        elif elem.type == "line":
            painter.drawLine(rect.topLeft(), rect.bottomRight())

        # 2. Photo element rendering
        elif elem.type == "photo":
            self._paint_photo(painter, rect, elem)

        # 3. Image element rendering
        elif elem.type == "image":
            self._paint_static_image(painter, rect, elem)

        # 4. Text elements rendering
        elif elem.type in ("static_text", "dynamic_text", "pin_field"):
            self._paint_text(painter, rect, elem)

        # 5. Selection overlay and handles
        if self.isSelected():
            self._paint_selection(painter)

    def _paint_photo(self, painter: QPainter, rect: QRectF, elem: CanvasElement):
        photo_path = self._sample_photo_path
        if photo_path and Path(photo_path).exists():
            if not self._cached_pixmap:
                self._cached_pixmap = QPixmap(photo_path)
            pix = self._cached_pixmap
        else:
            pix = None

        painter.save()
        clip_path = QPainterPath()
        if elem.style.mask_shape == "circle":
            clip_path.addEllipse(rect)
        elif elem.style.mask_shape == "rounded" or elem.style.border_radius > 0:
            r = elem.style.border_radius or 12
            clip_path.addRoundedRect(rect, r, r)
        else:
            clip_path.addRect(rect)
        painter.setClipPath(clip_path)

        if pix and not pix.isNull():
            # Scale pixmap according to fit mode
            scaled = pix.scaled(
                int(rect.width()),
                int(rect.height()),
                Qt.KeepAspectRatioByExpanding if elem.style.fit_mode == ImageFitMode.COVER else Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            # Center in rect
            x = rect.x() + (rect.width() - scaled.width()) / 2
            y = rect.y() + (rect.height() - scaled.height()) / 2
            painter.drawPixmap(int(x), int(y), scaled)
        else:
            # Placeholder
            painter.fillRect(rect, QColor("#E2E8F0"))
            painter.setPen(QColor("#64748B"))
            font = QFont("Arial", 14, QFont.Bold)
            painter.setFont(font)
            initials = "?"
            if self._sample_record:
                name = self._sample_record.get_value("Name", "")
                if not name:
                    for k, v in self._sample_record.data.items():
                        if "name" in k.lower() and v:
                            name = str(v).strip()
                            break
                if name:
                    initials = "".join(p[0] for p in name.split())[:2].upper()
            painter.drawText(rect, Qt.AlignCenter, initials)

        painter.restore()

        # Border around photo
        if elem.style.border_width > 0 and elem.style.border_color != "transparent":
            pen = QPen(QColor(elem.style.border_color), elem.style.border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            if elem.style.mask_shape == "circle":
                painter.drawEllipse(rect)
            elif elem.style.mask_shape == "rounded" or elem.style.border_radius > 0:
                r = elem.style.border_radius or 12
                painter.drawRoundedRect(rect, r, r)
            else:
                painter.drawRect(rect)

    def _paint_static_image(self, painter: QPainter, rect: QRectF, elem: CanvasElement):
        if elem.static_content and Path(elem.static_content).exists():
            pix = QPixmap(elem.static_content)
            if not pix.isNull():
                painter.drawPixmap(rect.toRect(), pix)
        else:
            painter.fillRect(rect, QColor("#F1F5F9"))
            painter.setPen(QColor("#94A3B8"))
            painter.drawText(rect, Qt.AlignCenter, "[Image]")

    def _paint_text(self, painter: QPainter, rect: QRectF, elem: CanvasElement):
        # Resolve text to display
        if elem.type == "static_text":
            text = elem.static_content or elem.name
        elif elem.type == "pin_field":
            text = self._sample_record.pin if self._sample_record else (elem.binding or "PIN-100001")
        else:
            # Dynamic text
            col = elem.binding or elem.name
            if self._sample_record:
                text = self._sample_record.get_value(col, f"[{col}]")
            else:
                text = f"[{col}]"

        font = QFont(elem.style.font_family, int(elem.style.font_size))
        font.setBold(elem.style.font_bold)
        font.setItalic(elem.style.font_italic)
        painter.setFont(font)

        painter.setPen(QColor(elem.style.font_color or "#000000"))

        flags = 0
        if elem.style.text_align == "center":
            flags |= Qt.AlignHCenter
        elif elem.style.text_align == "right":
            flags |= Qt.AlignRight
        else:
            flags |= Qt.AlignLeft

        if elem.style.vertical_align == "middle":
            flags |= Qt.AlignVCenter
        elif elem.style.vertical_align == "bottom":
            flags |= Qt.AlignBottom
        else:
            flags |= Qt.AlignTop

        if elem.style.wrap:
            flags |= Qt.TextWordWrap

        painter.drawText(rect, flags, text)

    def _paint_selection(self, painter: QPainter):
        """Draw outline and 8 resize handles."""
        # Selection outline
        pen = QPen(QColor("#3B82F6"), 1.5, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect)

        # Handles
        painter.setPen(QPen(QColor("#1D4ED8"), 1))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for handle_rect in self._get_handle_rects().values():
            painter.drawRect(handle_rect)

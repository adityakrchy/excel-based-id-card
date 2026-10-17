"""Interactive canvas graphics item supporting selection, dragging, resizing, and live preview."""

from pathlib import Path
from typing import Dict, Optional
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
)

from id_card_generator.core.constants import DEFAULT_DPI, ImageFitMode, TextOverflowPolicy
from id_card_generator.core.geometry import points_to_document_pixels
from id_card_generator.core.models import CanvasElement, SourceRecord


class CanvasItem(QGraphicsObject):
    """QGraphicsItem representing an editable element on the ID card canvas."""

    # Signals
    geometry_changed = Signal(object)
    selected_changed = Signal(object)

    HANDLE_SIZE = 8.0
    # Handles: 0:TL, 1:T, 2:TR, 3:R, 4:BR, 5:B, 6:BL, 7:L
    HANDLE_NAMES = ["TL", "T", "TR", "R", "BR", "B", "BL", "L"]

    _cached_avatar_pixmap: Optional[QPixmap] = None

    @classmethod
    def get_avatar_pixmap(cls) -> QPixmap:
        """Return cached avatar placeholder pixmap."""
        if cls._cached_avatar_pixmap is None or cls._cached_avatar_pixmap.isNull():
            try:
                from id_card_generator.resources.resource_loader import get_resource_path
                p = get_resource_path("assets", "avatar_placeholder.png")
                if p.exists():
                    cls._cached_avatar_pixmap = QPixmap(str(p))
                else:
                    cls._cached_avatar_pixmap = QPixmap()
            except Exception:
                cls._cached_avatar_pixmap = QPixmap()
        return cls._cached_avatar_pixmap

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
            | QGraphicsItem.ItemIsFocusable
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
        pad = self.HANDLE_SIZE + 4.0
        return self._rect.adjusted(-pad, -pad - 22.0, pad, pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect)
        if self.isSelected():
            for handle_rect in self._get_handle_rects().values():
                path.addRect(handle_rect)
        return path

    def scene_element_rect(self) -> QRectF:
        """Return the exact element bounding rectangle in scene coordinates."""
        return QRectF(
            self.pos().x() + self._rect.x(),
            self.pos().y() + self._rect.y(),
            self._rect.width(),
            self._rect.height(),
        )

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
        r = self.scene_element_rect()
        self.element.x = r.x()
        self.element.y = r.y()
        self.element.width = r.width()
        self.element.height = r.height()
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
        self.setFocus()
        self.selected_changed.emit(self)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        # 1. Handling Handle Resizing with Smart Edge Snapping
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

            scene = self.scene()
            if scene and hasattr(scene, "smart_alignment_engine"):
                pos_offset = self.pos()
                start_scene = QRectF(
                    pos_offset.x() + self._drag_start_rect.x(),
                    pos_offset.y() + self._drag_start_rect.y(),
                    self._drag_start_rect.width(),
                    self._drag_start_rect.height(),
                )
                prop_scene = QRectF(
                    pos_offset.x() + new_rect.x(),
                    pos_offset.y() + new_rect.y(),
                    new_rect.width(),
                    new_rect.height(),
                )
                targets = scene.get_reference_targets(exclude_items={self}) if hasattr(scene, "get_reference_targets") else []
                zoom = scene.get_zoom_factor() if hasattr(scene, "get_zoom_factor") else 1.0
                bypass = bool(event.modifiers() & Qt.AltModifier)
                keep_aspect = bool(event.modifiers() & Qt.ShiftModifier)

                snapped_scene, snap_res = scene.smart_alignment_engine.snap_resize(
                    handle=handle,
                    start_rect_scene=start_scene,
                    proposed_rect_scene=prop_scene,
                    targets=targets,
                    canvas_rect=scene.sceneRect(),
                    zoom_factor=zoom,
                    keep_aspect=keep_aspect,
                    bypass_snap=bypass,
                )
                new_rect = QRectF(
                    snapped_scene.x() - pos_offset.x(),
                    snapped_scene.y() - pos_offset.y(),
                    snapped_scene.width(),
                    snapped_scene.height(),
                )
                if hasattr(scene, "set_active_guides"):
                    scene.set_active_guides(snap_res.guides, snap_res.spacing_badges)
                scene.update()

            # Enforce minimum size
            if new_rect.width() >= 10.0 and new_rect.height() >= 10.0:
                self.set_rect(new_rect)
            event.accept()
            return

        # 2. Handling Dragging Movement with Magnetic Snapping
        scene = self.scene()
        if (
            scene
            and hasattr(scene, "smart_alignment_engine")
            and hasattr(scene, "_mouse_press_positions")
            and scene._mouse_press_positions
        ):
            scene._in_smart_drag = True
            selected_items = [it for it in scene.selectedItems() if isinstance(it, CanvasItem)]
            if self not in selected_items:
                selected_items.append(self)

            for it in selected_items:
                if it not in scene._mouse_press_positions:
                    scene._mouse_press_positions[it] = QPointF(it.pos())

            button_down_scene = event.buttonDownScenePos(Qt.LeftButton)
            mouse_disp = event.scenePos() - button_down_scene

            start_positions = scene._mouse_press_positions
            lefts = [start_positions[it].x() + it._rect.x() for it in selected_items]
            rights = [start_positions[it].x() + it._rect.x() + it._rect.width() for it in selected_items]
            tops = [start_positions[it].y() + it._rect.y() for it in selected_items]
            bottoms = [start_positions[it].y() + it._rect.y() + it._rect.height() for it in selected_items]

            group_start_rect = QRectF(
                min(lefts),
                min(tops),
                max(rights) - min(lefts),
                max(bottoms) - min(tops),
            )
            proposed_group_rect = group_start_rect.translated(mouse_disp.x(), mouse_disp.y())

            targets = scene.get_reference_targets(exclude_items=set(selected_items)) if hasattr(scene, "get_reference_targets") else []
            zoom = scene.get_zoom_factor() if hasattr(scene, "get_zoom_factor") else 1.0
            bypass = bool(event.modifiers() & Qt.AltModifier)

            snap_res = scene.smart_alignment_engine.snap_move(
                moving_rect=proposed_group_rect,
                targets=targets,
                canvas_rect=scene.sceneRect(),
                zoom_factor=zoom,
                bypass_snap=bypass,
            )

            final_disp_x = mouse_disp.x() + snap_res.delta_x
            final_disp_y = mouse_disp.y() + snap_res.delta_y

            for it in selected_items:
                it_start = start_positions[it]
                new_p = QPointF(it_start.x() + final_disp_x, it_start.y() + final_disp_y)
                it.setPos(new_p)
                it.update_model_position()

            if hasattr(scene, "set_active_guides"):
                scene.set_active_guides(snap_res.guides, snap_res.spacing_badges)
            scene.update()
            event.accept()
            return

        super().mouseMoveEvent(event)
        self.update_model_position()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        scene = self.scene()
        if scene and hasattr(scene, "clear_guides"):
            scene.clear_guides()
            scene._in_smart_drag = False
            scene.update()

        if self._drag_start_rect is not None and (
            self._rect.width() != self._drag_start_rect.width()
            or self._rect.height() != self._drag_start_rect.height()
            or self._rect.topLeft() != self._drag_start_rect.topLeft()
        ):
            if scene and hasattr(scene, "undo_stack"):
                from id_card_generator.editor.undo_manager import ResizeElementCommand
                scene.undo_stack.push(ResizeElementCommand(self, self._drag_start_rect, QRectF(self._rect)))

        self._active_handle = None
        self._drag_start_pos = None
        self._drag_start_rect = None
        super().mouseReleaseEvent(event)
        self.update_model_position()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

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
            # Placeholder: Render clean avatar image
            painter.fillRect(rect, QColor("#E2E8F0"))
            avatar_pix = self.get_avatar_pixmap()
            if avatar_pix and not avatar_pix.isNull():
                target_w = max(1, int(rect.width() * 0.75))
                target_h = max(1, int(rect.height() * 0.75))
                size = min(target_w, target_h)
                scaled_avatar = avatar_pix.scaled(
                    size,
                    size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                ax = rect.x() + (rect.width() - scaled_avatar.width()) / 2
                ay = rect.y() + (rect.height() - scaled_avatar.height()) / 2
                painter.drawPixmap(int(ax), int(ay), scaled_avatar)
            else:
                # Vector fallback if asset cannot be loaded
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#717A8A"))
                cx = rect.center().x()
                cy = rect.top() + rect.height() * 0.36
                r = min(rect.width(), rect.height()) * 0.18
                painter.drawEllipse(QPointF(cx, cy), r, r)

                torso_w = min(rect.width(), rect.height()) * 0.68
                torso_h = min(rect.width(), rect.height()) * 0.42
                tx = cx - torso_w / 2
                ty = rect.top() + rect.height() * 0.52
                torso_rect = QRectF(tx, ty, torso_w, torso_h * 2)
                painter.drawChord(torso_rect, 0 * 16, 180 * 16)

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

        # Determine document DPI from scene template
        scene = self.scene()
        dpi = DEFAULT_DPI
        if scene and hasattr(scene, "template") and scene.template and getattr(scene.template, "dpi", None):
            dpi = scene.template.dpi

        font_size_pt = float(elem.style.font_size)
        font = QFont(elem.style.font_family)
        font.setBold(elem.style.font_bold)
        font.setItalic(elem.style.font_italic)
        font.setStyleStrategy(QFont.PreferAntialias)

        flags = Qt.TextIncludeTrailingSpaces
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

        # Auto-shrink in point units to match TextLayout / Photoshop
        if elem.style.overflow_policy == TextOverflowPolicy.AUTO_SHRINK and text:
            cur_pt = font_size_pt
            min_pt = 4.0
            while cur_pt >= min_pt:
                doc_px = points_to_document_pixels(cur_pt, dpi)
                font.setPixelSize(max(1, int(round(doc_px))))
                fm = QFontMetrics(font)
                bounding = fm.boundingRect(rect.toRect(), flags, text)
                single_w = fm.horizontalAdvance(text)
                fits_single_line = (single_w <= rect.width()) and ("\n" not in text)
                if fits_single_line:
                    break
                if bounding.width() <= rect.width() and bounding.height() <= rect.height():
                    break
                cur_pt -= 0.5
        else:
            doc_px = points_to_document_pixels(font_size_pt, dpi)
            font.setPixelSize(max(1, int(round(doc_px))))

        draw_rect = QRectF(rect)
        fm = QFontMetrics(font)
        line_h = fm.height()
        if draw_rect.height() < line_h and ("\n" not in text):
            if elem.style.vertical_align == "middle":
                cy = rect.center().y()
                draw_rect.setTop(cy - line_h / 2.0)
                draw_rect.setHeight(line_h)
            elif elem.style.vertical_align == "bottom":
                draw_rect.setTop(rect.bottom() - line_h)
                draw_rect.setHeight(line_h)
            else:
                draw_rect.setHeight(line_h)

        painter.setFont(font)
        painter.setPen(QColor(elem.style.font_color or "#000000"))
        painter.drawText(draw_rect, flags, text)

    def _paint_selection(self, painter: QPainter):
        """Draw professional Transform Box (TBox) with outer contrast halo, crisp accent border, 8 resize handles, and element tag."""
        painter.save()
        rect = self._rect

        # 1. Outer dark halo for high contrast on light backgrounds
        outer_pen = QPen(QColor(0, 0, 0, 70), 2.5, Qt.SolidLine)
        painter.setPen(outer_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        # 2. Crisp bright primary selection border (Photoshop/Figma blue)
        inner_pen = QPen(QColor("#0078D4"), 1.8, Qt.SolidLine)
        painter.setPen(inner_pen)
        painter.drawRect(rect)

        # 3. 8 Transform Handles (pure white with blue border)
        handle_pen = QPen(QColor("#005A9E"), 1.5)
        handle_brush = QBrush(QColor("#FFFFFF"))
        painter.setPen(handle_pen)
        painter.setBrush(handle_brush)
        for handle_rect in self._get_handle_rects().values():
            painter.drawRoundedRect(handle_rect, 1.5, 1.5)

        # 4. Top-left Pill Badge (TBox element name & dimensions)
        badge_text = f"{self.element.name} ({int(self.element.width)}×{int(self.element.height)})"
        badge_font = QFont("Segoe UI", 8)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(badge_text) + 12
        th = fm.height() + 2
        badge_rect = QRectF(rect.left(), rect.top() - th - 3, tw, th)

        # Background pill
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#0078D4")))
        painter.drawRoundedRect(badge_rect, 3, 3)

        # Text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        painter.restore()

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent):
        """Right-click context menu for layer reordering and item actions."""
        scene = self.scene()
        if not scene:
            super().contextMenuEvent(event)
            return

        menu = QMenu()
        menu.setStyleSheet("font-size: 13px; padding: 4px;")

        act_top = menu.addAction("Bring to Front (To Top)")
        act_up = menu.addAction("Bring Forward (▲)")
        act_down = menu.addAction("Send Backward (▼)")
        act_bottom = menu.addAction("Send to Back (To Bottom)")
        menu.addSeparator()
        act_dup = menu.addAction("Duplicate")
        act_del = menu.addAction("Delete")

        chosen = menu.exec(event.screenPos())
        if chosen == act_top and hasattr(scene, "bring_to_front"):
            scene.bring_to_front(self)
        elif chosen == act_up and hasattr(scene, "bring_forward"):
            scene.bring_forward(self)
        elif chosen == act_down and hasattr(scene, "send_backward"):
            scene.send_backward(self)
        elif chosen == act_bottom and hasattr(scene, "send_to_back"):
            scene.send_to_back(self)
        elif chosen == act_dup and hasattr(scene, "duplicate_selected"):
            scene.duplicate_selected()
        elif chosen == act_del and hasattr(scene, "delete_selected"):
            scene.delete_selected()
        event.accept()

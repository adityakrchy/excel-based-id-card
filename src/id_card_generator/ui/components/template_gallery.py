"""Gallery rendering for the template browser.

The template list is shown as a grid of cards: every template gets a
thumbnail of the real card, its name and a small type tag.  Only the
templates that are actually visible are rendered, and the result is cached.
"""

from typing import Callable, Dict, Optional

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from id_card_generator.ui.studio_tokens import (
    BORDER_DEFAULT,
    PRIMARY,
    SURFACE_CONTAINER,
    SURFACE_HIGH,
    SURFACE_LOW,
    SURFACE_LOWEST,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

def pil_to_qimage(image) -> QImage:
    """Convert a Pillow image into a QImage.

    The copy detaches the QImage from the temporary byte buffer, otherwise the
    pixels would be freed while Qt still paints them.
    """
    if image.mode == "RGBA":
        fmt = QImage.Format_RGBA8888
        raw = image.tobytes("raw", "RGBA")
    else:
        fmt = QImage.Format_RGB888
        raw = image.tobytes("raw", "RGB")
    return QImage(raw, image.width, image.height, fmt).copy()


# Size of one gallery cell.
CARD_WIDTH = 164
CARD_HEIGHT = 168
THUMB_HEIGHT = 118


class TemplateGalleryDelegate(QStyledItemDelegate):
    """Paints a template as a thumbnail card with a name and a type tag."""

    def __init__(
        self,
        thumbnail_provider: Callable[[str], Optional[QPixmap]],
        is_builtin_provider: Callable[[str], bool],
        parent=None,
    ):
        super().__init__(parent)
        self._thumbnail_provider = thumbnail_provider
        self._is_builtin_provider = is_builtin_provider

    # -- metrics ----------------------------------------------------
    def sizeHint(self, option, index) -> QSize:
        return QSize(CARD_WIDTH, CARD_HEIGHT)

    # -- painting ----------------------------------------------------
    def paint(self, painter, option, index) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = option.rect.adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        template_id = index.data(Qt.UserRole) or ""
        name = index.data(Qt.DisplayRole) or ""
        builtin = self._is_builtin_provider(template_id) if template_id else False

        # Card surface
        surface = QRectF(rect)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(SURFACE_CONTAINER if selected else SURFACE_LOW))
        painter.drawRoundedRect(surface, 8, 8)

        border = QColor(PRIMARY if selected else BORDER_DEFAULT)
        if not selected and hovered:
            border = QColor(SURFACE_HIGH)
        painter.setPen(border)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(surface, 8, 8)

        # Thumbnail
        thumb_rect = QRectF(
            surface.left() + 10,
            surface.top() + 10,
            surface.width() - 20,
            THUMB_HEIGHT,
        )
        painter.setPen(QPen(QColor(SURFACE_HIGH), 1))
        painter.setBrush(QColor(SURFACE_LOWEST))
        painter.drawRoundedRect(thumb_rect, 5, 5)

        pixmap = self._thumbnail_provider(template_id) if template_id else None
        if pixmap is not None and not pixmap.isNull():
            inner = thumb_rect.adjusted(4, 4, -4, -4)
            scaled = pixmap.scaled(
                inner.size().toSize() if hasattr(inner.size(), "toSize") else QSize(1, 1),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            if scaled.isNull():
                scaled = pixmap.scaled(
                    int(inner.width()),
                    int(inner.height()),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            painter.drawPixmap(
                int(inner.center().x() - scaled.width() / 2),
                int(inner.center().y() - scaled.height() / 2),
                scaled,
            )

        # Type tag
        tag_text = "BUILT-IN" if builtin else "CUSTOM"
        tag_color = QColor(TEXT_MUTED) if builtin else QColor(PRIMARY)
        painter.setPen(tag_color)
        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2.0))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(
                surface.left() + 12,
                thumb_rect.bottom() + 6,
                surface.width() - 24,
                14,
            ),
            Qt.AlignLeft | Qt.AlignVCenter,
            tag_text,
        )

        # Name
        painter.setPen(QColor(TEXT_PRIMARY if selected else TEXT_MUTED))
        name_font = painter.font()
        name_font.setBold(True)
        name_font.setPointSizeF(max(8.0, name_font.pointSizeF()))
        painter.setFont(name_font)

        metrics = QFontMetrics(name_font)
        elided = metrics.elidedText(
            str(name), Qt.ElideRight, int(surface.width() - 24)
        )
        painter.drawText(
            QRectF(
                surface.left() + 12,
                thumb_rect.bottom() + 20,
                surface.width() - 24,
                18,
            ),
            Qt.AlignLeft | Qt.AlignVCenter,
            elided,
        )

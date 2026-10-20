"""Thumbnail loading for the photo library.

Loading a photograph with ``QPixmap(path)`` decodes the **full resolution**
image into memory - a 4000x3000 JPEG needs ~48 MB.  Doing that for a few
dozen rows is enough to exhaust the memory and crash the application.

This module therefore

* decodes straight into the target size with ``QImageReader.setScaledSize``
  (the image is never fully materialised),
* keeps the decoded thumbnails in a bounded LRU cache,
* generates them on a thread pool: Qt releases the GIL while decoding, so
  the work really runs in parallel.
"""

from collections import OrderedDict
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap

# Edge length of a generated thumbnail in pixels.
THUMBNAIL_SIZE = 48

# Upper bound of cached thumbnails (a thumbnail is ~10 kB, so this is tiny).
THUMBNAIL_CACHE_SIZE = 600


class ThumbnailCache:
    """A small, bounded LRU cache of decoded thumbnails."""

    def __init__(self, max_entries: int = THUMBNAIL_CACHE_SIZE) -> None:
        self._entries: "OrderedDict[str, QImage]" = OrderedDict()
        self._max_entries = max_entries

    def get(self, path: str) -> Optional[QImage]:
        """Return the cached image for a path, or None."""
        image = self._entries.get(path)
        if image is not None:
            self._entries.move_to_end(path)
        return image

    def put(self, path: str, image: QImage) -> None:
        """Store a thumbnail, evicting the oldest entry when full."""
        self._entries[path] = image
        self._entries.move_to_end(path)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


def load_thumbnail_image(
    path: str,
    size: int = THUMBNAIL_SIZE,
) -> Optional[QImage]:
    """Decode an image directly at thumbnail size.

    Returns None when the file cannot be decoded.  The full resolution image
    is never created, which keeps the memory usage flat regardless of the
    photo resolution.
    """
    reader = QImageReader(path)
    reader.setAutoTransform(True)

    original = reader.size()
    if original.isValid() and not original.isEmpty():
        target = original.scaled(
            QSize(size, size), Qt.KeepAspectRatio
        )
        reader.setScaledSize(target)

    image = reader.read()
    if image.isNull():
        return None
    return image


class ThumbnailSignals(QObject):
    """Signals emitted by the thumbnail runnables."""

    ready = Signal(int, str, object)  # row, path, QImage (or None)
    finished = Signal()


class ThumbnailTask(QRunnable):
    """Decodes one thumbnail on a worker thread."""

    def __init__(
        self,
        row: int,
        path: str,
        signals: ThumbnailSignals,
        size: int = THUMBNAIL_SIZE,
    ) -> None:
        super().__init__()
        self.row = row
        self.path = path
        self.signals = signals
        self.size = size
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            image = load_thumbnail_image(self.path, self.size)
        except Exception:
            image = None
        # QImage is safe to hand across threads; the QPixmap conversion
        # happens later in the GUI thread.
        self.signals.ready.emit(self.row, self.path, image)

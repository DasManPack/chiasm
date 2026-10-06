"""Small, bounded image decoding helpers for the Chiasm field."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader


MAX_FIELD_ARTWORK_EDGE = 320


def read_field_artwork(path: str, *, max_edge: int = MAX_FIELD_ARTWORK_EDGE) -> QImage:
    """Decode local album art to a centered square thumbnail, or return null."""
    image = QImage()
    if not str(path or "").strip():
        return image
    edge = max(32, min(MAX_FIELD_ARTWORK_EDGE, int(max_edge)))
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    source_size = reader.size()
    if not source_size.isValid() or source_size.width() <= 0 or source_size.height() <= 0:
        return image

    longest = max(source_size.width(), source_size.height())
    if longest > edge:
        scale = edge / longest
        reader.setScaledSize(
            QSize(
                max(1, round(source_size.width() * scale)),
                max(1, round(source_size.height() * scale)),
            )
        )
    image = reader.read()
    if image.isNull():
        return image
    if max(image.width(), image.height()) > edge:
        image = image.scaled(
            QSize(edge, edge),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
    side = min(image.width(), image.height())
    left = max(0, (image.width() - side) // 2)
    top = max(0, (image.height() - side) // 2)
    return image.copy(left, top, side, side)

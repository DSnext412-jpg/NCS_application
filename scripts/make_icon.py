"""Generate a multi-size Windows .ico from assets/icons/hotel.svg.

Renders the SVG with Qt's SVG renderer at several sizes, then packs the
PNGs into a single .ico using Pillow. Also produces a 256px PNG preview.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "assets" / "icons" / "hotel.svg"
ICO_PATH = ROOT / "assets" / "icons" / "hotel.ico"
PNG_PATH = ROOT / "assets" / "icons" / "hotel_256.png"

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _render_png(svg: QSvgRenderer, size: int) -> Image.Image:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(0)  # transparent
    painter = QPainter(image)
    svg.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QByteArray()
    from PySide6.QtCore import QBuffer

    out = QBuffer(buffer)
    out.open(QBuffer.ReadWrite)
    image.save(out, "PNG")
    out.close()
    return Image.open(BytesIO_from(buffer))


def BytesIO_from(buffer: QByteArray):  # noqa: N802
    import io

    return io.BytesIO(bytes(buffer))


def main() -> int:
    if not SVG_PATH.exists():
        print(f"Missing source SVG: {SVG_PATH}")
        return 1
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        print("SVG failed to load.")
        return 1

    pngs = [_render_png(renderer, size) for size in SIZES]

    pngs[-1].save(PNG_PATH, "PNG")
    print(f"Preview PNG: {PNG_PATH}")

    pngs[-1].save(ICO_PATH, "ICO", sizes=[(s, s) for s in SIZES])
    print(f"ICO written : {ICO_PATH} ({ICO_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
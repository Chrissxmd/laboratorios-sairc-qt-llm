"""Lectura binaria y renderizado de PDF con Qt; no realiza reconocimiento OCR."""

import base64
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtPdf import QPdfDocument

PDF_IMAGE_VERSION = "white_rgb_v1"


@contextmanager
def open_pdf(file_path: str):
    if QGuiApplication.instance() is None:
        raise RuntimeError("Inicializa Qt antes de procesar PDF (main_qt.py o cli.py).")
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    document = QPdfDocument()
    try:
        error = document.load(str(path.resolve()))
        if error != QPdfDocument.Error.None_ or document.pageCount() <= 0:
            raise ValueError(f"No se puede leer el PDF ({error.name}): {path.name}. Revisa si está protegido o dañado.")
        yield document
    finally:
        document.close()


def load_pdf_as_base64(file_path: str) -> str:
    return base64.standard_b64encode(Path(file_path).read_bytes()).decode("ascii")


def get_pdf_page_count(file_path: str) -> int:
    with open_pdf(file_path) as document:
        return document.pageCount()


def pdf_pages_to_base64_images(file_path: str, dpi: int = 144, max_pages: int | None = None) -> list[str]:
    """Prepara todas las páginas para Vision; nunca trunca un documento."""
    if not 72 <= dpi <= 300:
        raise ValueError("La resolución debe estar entre 72 y 300 DPI.")
    images = []
    with open_pdf(file_path) as document:
        if max_pages is not None and document.pageCount() > max_pages:
            raise ValueError("El PDF supera el límite de páginas de Vision; no se truncará.")
        for page in range(document.pageCount()):
            points = document.pagePointSize(page)
            scale = min(dpi / 72, 2000 / max(points.width(), points.height()))
            size = QSize(max(1, round(points.width() * scale)), max(1, round(points.height() * scale)))
            rendered = document.render(page, size)
            if rendered.isNull():
                raise ValueError(f"No se pudo renderizar la página {page + 1}.")
            opaque = QImage(rendered.size(), QImage.Format.Format_RGB32)
            opaque.fill("white")
            painter = QPainter(opaque)
            painter.drawImage(0, 0, rendered)
            painter.end()
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not opaque.save(buffer, "JPEG", 90):
                raise ValueError(f"No se pudo preparar la página {page + 1}.")
            images.append(base64.b64encode(bytes(data)).decode("ascii"))
            buffer.close()
    return images

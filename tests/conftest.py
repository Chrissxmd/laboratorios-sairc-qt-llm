import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    app = QApplication.instance() or QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Segoe UI", 10))
    yield app


@pytest.fixture
def make_pdf(tmp_path, qt_app):
    def create(name="synthetic.pdf", pages=1):
        path = tmp_path / name
        writer = QPdfWriter(str(path))
        painter = QPainter(writer)
        for page in range(pages):
            if page:
                writer.newPage()
            painter.drawText(400, 600, f"INFORME SINTETICO PAGINA {page + 1} HEMOGLOBINA 12.0")
        painter.end()
        del writer
        return path
    return create

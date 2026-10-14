from pathlib import Path

from PySide6.QtCore import QModelIndex, QPointF
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget


class PdfViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.search_model = QPdfSearchModel(self)
        self.search_model.setDocument(self.document)
        self.view.setSearchModel(self.search_model)
        self.path = None
        self.stamp = None
        self.positions = {}
        self.filename = QLabel("Selecciona un hallazgo para abrir su PDF")
        self.filename.setWordWrap(True)
        self.page = QSpinBox()
        self.page.setRange(1, 1)
        self.page.setPrefix("Página ")
        self.page.valueChanged.connect(self.jump)
        self.view.pageNavigator().currentPageChanged.connect(self.page_changed)
        self.zoom = QComboBox()
        self.zoom.addItems(["Ajustar ancho", "Página completa", "75%", "100%", "150%", "200%"])
        self.zoom.currentIndexChanged.connect(self.set_zoom)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar en el texto del PDF")
        self.search.textChanged.connect(self.search_model.setSearchString)
        self.search.returnPressed.connect(self.next_match)
        next_button = QPushButton("Siguiente coincidencia")
        next_button.clicked.connect(self.next_match)
        self.match_index = -1
        self.search.textChanged.connect(lambda: setattr(self, "match_index", -1))
        tools = QHBoxLayout()
        for widget in (self.page, self.zoom):
            tools.addWidget(widget)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filename)
        layout.addLayout(tools)
        search_tools = QHBoxLayout()
        search_tools.addWidget(self.search, 1)
        search_tools.addWidget(next_button)
        layout.addLayout(search_tools)
        layout.addWidget(self.view, 1)
        note = QLabel("Solo lectura · Los escaneos sin texto no permiten búsqueda · El PDF original permanece intacto")
        note.setWordWrap(True)
        layout.addWidget(note)

    def open_pdf(self, path):
        candidate = Path(path).resolve() if path else None
        stamp = (candidate.stat().st_size, candidate.stat().st_mtime_ns) if candidate and candidate.is_file() else None
        if candidate and candidate == self.path and stamp == self.stamp:
            return True
        if self.path:
            self.positions[str(self.path)] = (self.page.value(), self.zoom.currentIndex(), self.search.text())
        self.document.close()
        self.path = None
        self.stamp = None
        self.search.clear()
        candidate = Path(path) if path else None
        if candidate is None or not candidate.is_file():
            self.filename.setText("PDF no disponible. Selecciona la raíz de los PDF o revisa la ruta del informe.")
            return False
        error = self.document.load(str(candidate.resolve()))
        if error != QPdfDocument.Error.None_:
            self.filename.setText(f"No se puede abrir {candidate.name}: {error.name}")
            return False
        self.path = candidate.resolve()
        self.stamp = stamp
        self.filename.setText(candidate.name)
        self.filename.setToolTip(str(self.path))
        self.page.setRange(1, max(1, self.document.pageCount()))
        self.page.setValue(1)
        self.jump(1)
        if str(self.path) in self.positions:
            page, zoom, search = self.positions[str(self.path)]
            self.zoom.setCurrentIndex(zoom)
            self.page.setValue(page)
            self.search.setText(search)
        return True

    def jump(self, number):
        if self.document.pageCount():
            self.view.pageNavigator().jump(number - 1, QPointF(), self.view.zoomFactor())

    def page_changed(self, index):
        self.page.blockSignals(True)
        self.page.setValue(index + 1)
        self.page.blockSignals(False)

    def set_zoom(self, index):
        if index < 2:
            mode = QPdfView.ZoomMode.FitToWidth if index == 0 else QPdfView.ZoomMode.FitInView
            self.view.setZoomMode(mode)
        else:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor((0.75, 1.0, 1.5, 2.0)[index - 2])

    def next_match(self):
        count = self.search_model.rowCount(QModelIndex())
        if not count:
            return
        self.match_index = (self.match_index + 1) % count
        result = self.search_model.resultAtIndex(self.match_index)
        self.view.setCurrentSearchResultIndex(self.match_index)
        self.view.pageNavigator().jump(result.page(), result.location(), self.view.zoomFactor())

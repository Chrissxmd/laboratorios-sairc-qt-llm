import os
import threading
from datetime import date
from pathlib import Path

from PySide6.QtCore import QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget

from core.ai import AIConfig, DEFAULT_MODEL_BY_PROVIDER, MODELS, MISTRAL_VISION_MODELS, validate_reader_config
from core.comparador import compare_excels
from core.config import APP_VERSION, DEFAULT_OUTPUT_DIR
from core.db_extractor import generar_referencia_sairc_sql
from core.processor import process_folder, reprocess_ai_cache, reprocess_temporary_errors
from core.simulation import simulate_review
from core.workspace import find_hito2_excel, find_hito3_reference, get_hito_paths
from ui_qt.review import ReviewPane, read_discrepancies
from ui_qt.worker import TaskWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auditoría de Laboratorios SAIRC · Qt / IA remota")
        available = self.screen().availableGeometry()
        self.resize(min(1440, available.width() - 40), min(950, available.height() - 60))
        self.setMinimumSize(min(1050, available.width() - 40), min(600, available.height() - 60))
        self.thread = None
        self.worker = None
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.action_buttons = []
        self.operation = ""
        self.last_excel = ""
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Carpeta de informes PDF organizada por IPRESS")
        self.root_path = QLineEdit(str(DEFAULT_OUTPUT_DIR / "AUDITORIA_QT"))
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 18, 24, 18)
        title = QLabel("Auditoría de Laboratorios SAIRC")
        title.setObjectName("title")
        subtitle = QLabel(f"{APP_VERSION}  ·  Reconocimiento remoto  ·  Sin OCR local")
        self.title_label = title
        self.subtitle_label = subtitle
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        sources = QGroupBox("Proceso de trabajo")
        self.sources = sources
        form = QFormLayout(sources)
        form.addRow("Informes PDF", self.path_picker(self.input_path))
        form.addRow("Raíz de resultados", self.path_picker(self.root_path))
        layout.addWidget(sources)
        self.stage_status = QLabel()
        layout.addWidget(self.stage_status)
        self.error_banner = QLabel()
        self.error_banner.setWordWrap(True)
        self.error_banner.setStyleSheet("color: #ffb4b4; border: 1px solid #a34c4c; padding: 8px;")
        self.error_banner.hide()
        layout.addWidget(self.error_banner)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.scroll_tab(self.extraction_tab()), "1  Extracción")
        self.tabs.addTab(self.consolidation_tab(), "2  Consolidado")
        self.tabs.addTab(self.scroll_tab(self.reference_tab()), "3  Referencia")
        self.tabs.addTab(self.review_tab(), "4  Control y PDF")
        layout.addWidget(self.tabs, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status = QLabel("Listo. Selecciona la raíz del proceso o abre un reporte existente.")
        self.status.setWordWrap(True)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setMaximumHeight(80)
        self.log.setPlaceholderText("Aquí se mostrarán el progreso y los errores de cada etapa.")
        self.log.setVisible(False)
        self.log_toggle = QCheckBox("Mostrar registro de actividad")
        self.log_toggle.toggled.connect(self.log.setVisible)
        layout.addWidget(self.log_toggle)
        layout.addWidget(self.log)
        self.tabs.currentChanged.connect(self.review_mode_changed)
        self.setCentralWidget(central)
        self.root_path.editingFinished.connect(self.refresh_paths)
        self.input_path.editingFinished.connect(self.refresh_paths)
        self.refresh_paths()

    def review_mode_changed(self, index):
        for widget in (self.sources, self.title_label, self.subtitle_label):
            widget.setVisible(index != 3)

    def path_picker(self, field, files=None):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Seleccionar")
        def choose():
            if files:
                value, _filter = QFileDialog.getOpenFileName(self, "Seleccionar archivo", field.text(), files)
            else:
                value = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", field.text())
            if value:
                field.setText(value)
                if field in (self.root_path, self.input_path):
                    self.refresh_paths()
        button.clicked.connect(choose)
        self.action_buttons.append(button)
        row.addWidget(field, 1)
        row.addWidget(button)
        return container

    def action(self, label, callback, layout):
        button = QPushButton(label)
        button.clicked.connect(callback)
        self.action_buttons.append(button)
        layout.addWidget(button)
        return button

    def extraction_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        intro = QLabel("Lee los informes mediante un proveedor remoto. Esta etapa guarda respuestas JSON; el Excel se construye en el Hito 2.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        group = QGroupBox("Lector de documentos")
        form = QFormLayout(group)
        self.provider = QComboBox()
        self.provider.addItems(["gemini", "mistral"])
        self.mode = QComboBox()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("API key; también se admite la variable de entorno del proveedor")
        for label, widget in (("Proveedor", self.provider), ("Modalidad", self.mode), ("Modelo", self.model), ("API key", self.api_key)):
            form.addRow(label, widget)
        settings_layout.addWidget(group)
        self.consent = QCheckBox("Autorizo enviar los informes clínicos al proveedor seleccionado y asumir el costo.")
        self.consent.setToolTip("La autorización permite enviar informes clínicos al proveedor configurado y asumir las llamadas. El envío comienza solo al iniciar una extracción, reproceso o prueba.")
        layout.addWidget(self.consent)
        tuning = QGroupBox("Límites y rendimiento")
        limits = QGridLayout(tuning)
        limits.setHorizontalSpacing(20)
        limits.setColumnStretch(1, 1)
        limits.setColumnStretch(3, 1)
        self.threads = self.spin(1, 10, 4)
        self.rpm = self.spin(1, 1000, 60)
        self.timeout = self.spin(15, 900, 180)
        self.retries = self.spin(1, 5, 3)
        self.max_pages = self.spin(1, 1000, 100)
        self.vision_pages = self.spin(1, 100, 20)
        self.max_mb = self.spin(1, 100, 50)
        fields = (("Hilos (límite por proveedor)", self.threads), ("Solicitudes por minuto", self.rpm), ("Timeout en segundos", self.timeout), ("Intentos por solicitud", self.retries), ("Máximo de páginas por PDF", self.max_pages), ("Páginas Mistral Vision", self.vision_pages), ("Máximo de MB por PDF", self.max_mb))
        for index, (label, widget) in enumerate(fields):
            column = (index % 2) * 2
            limits.addWidget(QLabel(label), index // 2, column)
            limits.addWidget(widget, index // 2, column + 1)
        settings_layout.addWidget(tuning)
        note = QLabel("Los límites del proveedor pueden ser menores. No se truncan documentos. Las tarifas mostradas son estimaciones heredadas; verifica la facturación del proveedor.")
        note.setWordWrap(True)
        settings_layout.addWidget(note)
        self.reader_dialog = self.settings_dialog("Configuración del lector", settings)
        self.reader_summary = QLabel()
        self.reader_summary.setWordWrap(True)
        configuration = QHBoxLayout()
        configuration.addWidget(self.reader_summary, 1)
        self.action("Configurar lector…", self.reader_dialog.exec, configuration)
        layout.insertLayout(1, configuration)
        self.reader_dialog.finished.connect(self.update_config_summary)
        actions = QHBoxLayout()
        self.extract_button = self.action("Iniciar extracción", self.start_extraction, actions)
        self.extract_button.setToolTip("Procesa con el modelo seleccionado en Configurar lector.")
        self.action("Reprocesar errores", self.start_retry, actions)
        self.pause_button = QPushButton("Pausar")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("Detener")
        self.stop_button.clicked.connect(self.cancel_task)
        self.stop_button.setEnabled(False)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.stop_button)
        layout.addLayout(actions)
        layout.addStretch()
        self.provider.currentTextChanged.connect(self.provider_changed)
        self.mode.currentIndexChanged.connect(self.models_changed)
        self.provider_changed()
        self.update_config_summary()
        return tab

    def settings_dialog(self, title, content):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(820, 650)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self.scroll_tab(content), 1)
        note = QLabel("Los cambios quedan activos al cerrar este panel.")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        buttons.rejected.connect(dialog.accept)
        layout.addWidget(buttons)
        return dialog

    def update_config_summary(self, *_args):
        self.reader_summary.setText(f"{self.provider.currentText().capitalize()} · {self.mode.currentText()}\n{self.model.currentText()} · {self.threads.value()} hilos · {self.rpm.value()} solicitudes/min")
        if hasattr(self, "sql_summary"):
            server = self.sql_server.text().strip() or "Servidor sin configurar"
            self.sql_summary.setText(f"{server} · {self.sql_database.text()} · {self.month.value():02d}/{self.year.value()}")

    @staticmethod
    def scroll_tab(widget):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(widget)
        return area

    @staticmethod
    def spin(minimum, maximum, value):
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setMinimumHeight(34)
        return field

    def provider_changed(self):
        self.api_key.clear()
        self.consent.setChecked(False)
        self.mode.blockSignals(True)
        self.mode.clear()
        if self.provider.currentText() == "mistral":
            self.mode.addItem("OCR estructurado remoto", "ocr")
        self.mode.addItem("Visión multimodal", "vision")
        self.mode.setCurrentIndex(self.mode.findData("vision"))
        self.mode.blockSignals(False)
        self.models_changed()
        if hasattr(self, "reader_summary"):
            self.update_config_summary()

    def models_changed(self):
        self.consent.setChecked(False)
        self.model.clear()
        if self.provider.currentText() == "mistral":
            models = ["mistral-ocr-latest"] if self.mode.currentData() == "ocr" else MISTRAL_VISION_MODELS
        else:
            models = MODELS["gemini"]
        self.model.addItems(models)
        if hasattr(self, "reader_summary"):
            self.update_config_summary()

    def config(self):
        if not self.consent.isChecked():
            self.consent.setFocus()
            raise ValueError("Marca «Autorizo enviar los informes clínicos al proveedor seleccionado y asumir el costo».")
        provider = self.provider.currentText()
        key = self.api_key.text().strip() or os.environ.get(f"LAB_EXTRACTOR_{provider.upper()}_API_KEY", "").strip() or os.environ.get("LAB_EXTRACTOR_API_KEY", "").strip()
        config = AIConfig(provider=provider, model=self.model.currentText().strip() or DEFAULT_MODEL_BY_PROVIDER[provider], api_key=key, reader_mode=self.mode.currentData(), allow_external_processing=self.consent.isChecked(), timeout_seconds=self.timeout.value(), max_retries=self.retries.value(), requests_per_minute=self.rpm.value(), max_pdf_pages=self.max_pages.value(), max_vision_pages=self.vision_pages.value(), max_pdf_mb=self.max_mb.value())
        validate_reader_config(config)
        return config

    def consolidation_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        label = QLabel("Normaliza respuestas existentes y genera el universo SAIRC completo. No realiza nuevas llamadas al proveedor.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.cache_path = QLineEdit()
        form = QFormLayout()
        form.addRow("Origen de respuestas", self.path_picker(self.cache_path))
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.action("Construir Excel y CSV", self.start_consolidation, actions)
        self.action("Abrir Excel generado", self.open_excel, actions)
        layout.addLayout(actions)
        layout.addStretch()
        return tab

    def reference_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.reference_path = QLineEdit()
        form = QFormLayout()
        form.addRow("Referencia existente", self.path_picker(self.reference_path, "Referencias (*.csv *.xlsx)"))
        layout.addLayout(form)
        layout.addWidget(QLabel("Puedes usar un archivo autorizado existente o descargarlo desde SQL Server."))
        sql = QGroupBox("Conexión SQL (credenciales solo en esta sesión o variables de entorno)")
        fields = QFormLayout(sql)
        self.sql_driver = QLineEdit(os.environ.get("LAB_EXTRACTOR_SQL_DRIVER", "ODBC Driver 17 for SQL Server"))
        self.sql_server = QLineEdit(os.environ.get("LAB_EXTRACTOR_SQL_SERVER", ""))
        self.sql_database = QLineEdit(os.environ.get("LAB_EXTRACTOR_SQL_DATABASE", "BDSAIRC_PBI"))
        self.sql_user = QLineEdit(os.environ.get("LAB_EXTRACTOR_SQL_USERNAME", ""))
        self.sql_password = QLineEdit()
        self.sql_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.sql_trusted = QCheckBox("Usar autenticación de Windows")
        self.sql_trusted.setChecked(True)
        self.sql_certificate = QCheckBox("Confiar en el certificado del servidor (solo si está autorizado)")
        self.sql_certificate.setChecked(False)
        for name, widget in (("Driver ODBC", self.sql_driver), ("Servidor", self.sql_server), ("Base de datos", self.sql_database), ("Usuario SQL", self.sql_user), ("Contraseña", self.sql_password), ("Autenticación", self.sql_trusted), ("Certificado", self.sql_certificate)):
            fields.addRow(name, widget)
        self.year = self.spin(2000, 2100, date.today().year)
        self.month = self.spin(1, 12, date.today().month)
        self.establishment = QLineEdit()
        self.establishment.setPlaceholderText("Opcional: EstablecimientoId; vacío para todos")
        fields.addRow("Año", self.year)
        fields.addRow("Mes", self.month)
        fields.addRow("EstablecimientoId", self.establishment)
        self.sql_trusted.toggled.connect(lambda checked: (self.sql_user.setEnabled(not checked), self.sql_password.setEnabled(not checked)))
        self.sql_user.setEnabled(not self.sql_trusted.isChecked())
        self.sql_password.setEnabled(not self.sql_trusted.isChecked())
        self.sql_dialog = self.settings_dialog("Configuración de referencia SQL", sql)
        self.sql_summary = QLabel()
        self.sql_summary.setWordWrap(True)
        layout.addWidget(self.sql_summary)
        self.sql_dialog.finished.connect(self.update_config_summary)
        actions = QHBoxLayout()
        self.action("Configurar referencia…", self.sql_dialog.exec, actions)
        self.action("Descargar referencia SQL", self.start_reference, actions)
        layout.addLayout(actions)
        self.update_config_summary()
        note = QLabel("Requiere el controlador ODBC y acceso a la base. Confirma la correspondencia EstablecimientoId/CUI antes de validar un lote.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return tab

    def review_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.excel_path = QLineEdit()
        self.report_path = QLineEdit()
        files_panel = QWidget()
        form = QFormLayout(files_panel)
        form.addRow("Consolidado Hito 2", self.path_picker(self.excel_path, "Excel (*.xlsx)"))
        form.addRow("Reporte de discrepancias", self.path_picker(self.report_path, "Excel (*.xlsx)"))
        self.review_dialog = self.settings_dialog("Archivos para comparación y revisión", files_panel)
        actions = QHBoxLayout()
        self.action("Archivos de revisión…", self.review_dialog.exec, actions)
        self.action("Comparar Hito 2 / Hito 3", self.start_comparison, actions)
        self.action("Cargar reporte", self.load_report, actions)
        self.action("Resultados…", self.open_outputs, actions)
        layout.addLayout(actions)
        self.simulation_cache = QLineEdit()
        self.simulation_pdfs = QLineEdit()
        simulation_settings = QWidget()
        simulation_form = QFormLayout(simulation_settings)
        simulation_form.addRow("Lecturas del Hito 1", self.path_picker(self.simulation_cache))
        simulation_form.addRow("PDF originales", self.path_picker(self.simulation_pdfs))
        simulation_note = QLabel("Genera Hito 2 y una referencia ficticia del Hito 3. Incluye todos los PDF en el visor. Guarda en SIMULACION_VISOR dentro de la raíz de resultados; no necesita API ni SQL.")
        simulation_note.setWordWrap(True)
        simulation_form.addRow(simulation_note)
        self.simulation_dialog = self.settings_dialog("Simulación del visor PDF", simulation_settings)
        simulate_button = QPushButton("Generar simulación y abrir visor")
        simulate_button.clicked.connect(lambda: (self.simulation_dialog.accept(), self.start_simulation()))
        self.action_buttons.append(simulate_button)
        self.simulation_dialog.layout().insertWidget(1, simulate_button)
        simulation_actions = QHBoxLayout()
        layout.addLayout(simulation_actions)
        self.simulate_button = self.action("Simular desde Hito 1…", self.simulation_dialog.exec, simulation_actions)
        self.simulation_banner = QLabel("SIMULACIÓN · Referencia ficticia para probar el visor. No válida para auditoría ni carga SAIRC.")
        self.simulation_banner.setWordWrap(True)
        self.simulation_banner.setStyleSheet("color: #ffd38a;")
        self.simulation_banner.hide()
        simulation_actions.addWidget(self.simulation_banner, 1)
        simulation_actions.addStretch()
        self.review = ReviewPane()
        layout.addWidget(self.review, 1)
        return tab

    def paths(self):
        if not self.root_path.text().strip():
            raise ValueError("Selecciona una raíz de resultados.")
        return get_hito_paths(Path(self.root_path.text()).expanduser().resolve())

    def refresh_paths(self):
        if not self.root_path.text().strip():
            return
        paths = self.paths()
        self.cache_path.setText(str(paths.hito1))
        small = DEFAULT_MODEL_BY_PROVIDER["mistral"]
        candidates = (paths.hito1, paths.root / small / paths.hito1.name, paths.root / "PRUEBA_MISTRAL_3_MODELOS" / small / paths.hito1.name)
        simulation_source = next((path for path in candidates if path.is_dir()), paths.hito1)
        self.simulation_cache.setText(str(simulation_source))
        self.simulation_pdfs.setText(self.input_path.text().strip())
        excel = find_hito2_excel(paths.root)
        self.excel_path.setText(str(excel or paths.hito2 / "resultados_laboratorio_sairc.xlsx"))
        reference = find_hito3_reference(paths.root)
        self.reference_path.setText(str(reference or ""))
        self.report_path.setText(str(paths.hito4 / "reporte_priorizado_discrepancias_hito4.xlsx"))
        self.review.pdf_root = self.input_path.text().strip()
        self.stage_status.setText("   ·   ".join(("1 Respuestas disponibles" if paths.hito1.exists() else "1 Pendiente", "2 Consolidado disponible" if excel else "2 Pendiente", "3 Referencia disponible" if reference else "3 Seleccionar referencia", "4 Reporte disponible" if Path(self.report_path.text()).is_file() else "4 Pendiente")))

    def start_task(self, name, operation):
        if self.thread is not None:
            self.show_error("Ya hay una operación en curso.")
            return
        self.cancel_event.clear()
        self.pause_event.clear()
        self.operation = name
        self.thread = QThread(self)
        self.worker = TaskWorker(operation)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.on_result)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.task_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        for button in self.action_buttons:
            button.setEnabled(False)
        for widget in (self.input_path, self.root_path, self.provider, self.mode, self.model, self.api_key, self.consent):
            widget.setEnabled(False)
        cancellable = name in {"extract", "retry"}
        self.pause_button.setEnabled(cancellable)
        self.stop_button.setEnabled(cancellable)
        self.progress.setRange(0, 0)
        self.error_banner.hide()
        self.status.setStyleSheet("")
        self.status.setText("Operación en curso…")
        self.log.clear()
        self.thread.start()

    def show_error(self, message):
        message = str(message)
        secrets = [self.api_key.text(), self.sql_password.text()]
        secrets.extend(value for key, value in os.environ.items() if key.startswith("LAB_EXTRACTOR_") and (key.endswith("API_KEY") or key.endswith("PASSWORD")))
        for secret in secrets:
            if secret:
                message = message.replace(secret, "[oculto]")
        self.status.setText(f"Error: {message}")
        self.error_banner.setText(f"No se pudo completar la acción: {message}")
        self.error_banner.show()
        self.status.setStyleSheet("color: #ff9d9d")
        self.log.appendPlainText(f"ERROR: {message}")

    def on_progress(self, payload):
        if "percent" in payload:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, int(payload["percent"]))))
        if payload.get("message"):
            self.status.setText(str(payload["message"]))
            self.log.appendPlainText(str(payload["message"]))

    def on_result(self, result):
        if self.operation in {"extract", "retry", "consolidate"}:
            cancelled = self.cancel_event.is_set()
            message = f"{'Detenido' if cancelled else 'Terminado'}: {result.success}/{result.total} procesados · {result.errors} errores · {result.revisar} para revisión."
            if result.excel_path:
                self.last_excel = result.excel_path
                message += f" Excel: {result.excel_path}"
            message += f" Costo estimado acumulado: USD {result.total_cost_estimated_usd:.6f}."
            self.status.setText(message)
            self.refresh_paths()
        elif self.operation == "reference":
            self.refresh_paths()
            self.reference_path.setText(str(result))
            self.status.setText(f"Referencia guardada: {result}")
        elif self.operation == "compare":
            self.status.setText(f"{result['hallazgos_total']} hallazgos · {result['pdf_revision_copiados']} PDF copiados · {result['pdf_revision_no_encontrados']} PDF no encontrados.")
            self.refresh_paths()
            self.review.set_rows(result["_rows"])
            self.tabs.setCurrentIndex(3)
            self.simulation_banner.hide()
        elif self.operation == "load_report":
            self.review.set_rows(result, self.report_path.text().strip())
            self.simulation_banner.setVisible(any(row.get("_simulation", False) for row in result))
            label = "SIMULACIÓN" if not self.simulation_banner.isHidden() else "Reporte cargado"
            self.status.setText(f"{label}: {len(result)} hallazgos.")
            self.tabs.setCurrentIndex(3)
            self.stage_status.setText("2 Consolidado · 3 Referencia SIMULADA · 4 Revisión por PDF" if label == "SIMULACIÓN" else "4 Comparación Hito 2 ↔ Hito 3 · Revisión por PDF")
        elif self.operation == "simulate":
            self.report_path.setText(result["report"])
            self.excel_path.setText(result["excel"])
            self.last_excel = result["excel"]
            self.review.query.clear()
            self.review.priority.setCurrentIndex(0)
            self.review.set_rows(result["_rows"], result["report"])
            self.stage_status.setText(f"2 Consolidado generado · 3 Referencia SIMULADA · 4 {result['pdf_total']} PDF para revisión")
            self.simulation_banner.show()
            self.tabs.setCurrentIndex(3)
            self.status.setText(f"SIMULACIÓN: {result['pdf_total']} PDF disponibles · {result['pdf_without_reading']} sin lectura · sin llamadas IA ni SQL.")
        self.log.appendPlainText(self.status.text())

    def task_finished(self):
        self.thread = None
        self.worker = None
        for button in self.action_buttons:
            button.setEnabled(True)
        for widget in (self.input_path, self.root_path, self.provider, self.mode, self.model, self.api_key, self.consent):
            widget.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Pausar")
        self.stop_button.setEnabled(False)
        self.progress.setRange(0, 100)
        if not self.status.text().startswith("Error:") and not self.cancel_event.is_set():
            self.progress.setValue(100)

    def start_extraction(self):
        try:
            config = self.config()
            source, output = self.input_path.text().strip(), str(self.paths().hito1)
            if not source or not Path(source).is_dir():
                raise ValueError("Selecciona una carpeta existente de informes PDF.")
            threads = self.threads.value()
            self.start_task("extract", lambda progress: process_folder(source, config, progress_cb=progress, threads=threads, output_dir=output, pause_event=self.pause_event, cancel_event=self.cancel_event, build_exports=False))
        except Exception as exc:
            self.show_error(str(exc))

    def start_retry(self):
        try:
            config = self.config()
            source, output = self.input_path.text().strip(), str(self.paths().hito1)
            threads = min(2, self.threads.value())
            self.start_task("retry", lambda progress: reprocess_temporary_errors(output, source, config, progress_cb=progress, threads=threads, pause_event=self.pause_event, cancel_event=self.cancel_event))
        except Exception as exc:
            self.show_error(str(exc))

    def start_simulation(self):
        try:
            source = self.simulation_cache.text().strip()
            pdfs = self.simulation_pdfs.text().strip()
            output = str(self.paths().root)
            def operation(progress):
                result = simulate_review(source, pdfs, output, progress)
                result["_rows"] = read_discrepancies(result["report"], pdfs)
                return result
            self.start_task("simulate", operation)
        except Exception as exc:
            self.show_error(str(exc))

    def start_consolidation(self):
        try:
            source, output = self.cache_path.text().strip(), str(self.paths().hito2)
            self.start_task("consolidate", lambda _progress: reprocess_ai_cache(source, output))
        except Exception as exc:
            self.show_error(str(exc))

    def start_reference(self):
        try:
            if not self.sql_server.text().strip():
                raise ValueError("Indica el servidor SQL.")
            values = {"DRIVER": self.sql_driver.text(), "SERVER": self.sql_server.text(), "DATABASE": self.sql_database.text(), "USERNAME": self.sql_user.text(), "PASSWORD": self.sql_password.text() or os.environ.get("LAB_EXTRACTOR_SQL_PASSWORD", ""), "TRUSTED_CONNECTION": "1" if self.sql_trusted.isChecked() else "0", "TRUST_CERT": "yes" if self.sql_certificate.isChecked() else "no"}
            for key, value in values.items():
                os.environ[f"LAB_EXTRACTOR_SQL_{key}"] = value
            year, month, establishment, output = self.year.value(), self.month.value(), self.establishment.text().strip() or None, str(self.paths().hito3)
            self.start_task("reference", lambda _progress: generar_referencia_sairc_sql(year, month, establishment, output))
        except Exception as exc:
            self.show_error(str(exc))

    def start_comparison(self):
        try:
            excel, reference = self.excel_path.text().strip(), self.reference_path.text().strip()
            source = self.input_path.text().strip() or None
            output = str(self.paths().hito4 / "reporte_priorizado_discrepancias_hito4.xlsx")
            self.report_path.setText(output)
            def operation(progress):
                result = compare_excels(excel, reference, output, pdf_root=source, review_pdf_operation="copy")
                progress({"message": "Cargando la cola de revisión y comprobando fuentes…"})
                result["_rows"] = read_discrepancies(output, source or "")
                return result
            self.start_task("compare", operation)
        except Exception as exc:
            self.show_error(str(exc))

    def load_report(self):
        try:
            path = self.report_path.text().strip()
            source = self.input_path.text().strip()
            self.review.pdf_root = source
            if not Path(path).is_file():
                raise ValueError("Selecciona un reporte de discrepancias existente.")
            if self.thread is not None:
                rows = read_discrepancies(path, source)
                self.review.set_rows(rows, path)
                self.simulation_banner.setVisible(any(row.get("_simulation", False) for row in rows))
            else:
                self.start_task("load_report", lambda _progress: read_discrepancies(path, source))
        except Exception as exc:
            self.show_error(str(exc))

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.setText("Pausar")
        else:
            self.pause_event.set()
            self.pause_button.setText("Continuar")
            self.status.setText("Pausa solicitada; las solicitudes ya enviadas pueden terminar.")

    def cancel_task(self):
        self.cancel_event.set()
        self.pause_event.clear()
        self.stop_button.setEnabled(False)
        self.status.setText("Detención solicitada. Esperando que las tareas activas terminen o alcancen su timeout.")

    def open_excel(self):
        path = self.last_excel or str(find_hito2_excel(self.paths().root) or "")
        if path and Path(path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            self.show_error("No hay un Excel válido disponible.")

    def open_outputs(self):
        report = Path(self.report_path.text())
        folder = report.parent if self.tabs.currentIndex() == 3 and report.is_file() else self.paths().root
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, event):
        if self.thread is not None:
            self.cancel_task()
            self.status.setText("Se solicitó detener. Cierra nuevamente cuando termine la operación; se preservan las escrituras activas.")
            event.ignore()
        else:
            self.review.finish()
            event.accept()

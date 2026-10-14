"""Punto de entrada de la edición independiente Qt/IA remota."""
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Auditoría SAIRC Qt / IA remota")
    parser.add_argument("--smoke-test", action="store_true", help="Inicializa y cierra la interfaz sin llamadas externas.")
    parser.add_argument("--screenshot", help="Guarda una imagen de la ventana durante la prueba de arranque.")
    parser.add_argument("--smoke-report", help="Carga un reporte sintético en el visor durante --smoke-test.")
    parser.add_argument("--review-report", help="Abre directamente un reporte existente en el visor.")
    args = parser.parse_args()
    if args.smoke_report and not args.smoke_test:
        parser.error("Las opciones smoke requieren --smoke-test")
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from ui_qt.window import MainWindow

    app = QApplication(sys.argv[:1])
    if args.smoke_test and os.name == "nt":
        system_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if system_font.is_file():
            QFontDatabase.addApplicationFont(str(system_font))
    app.setApplicationName("AuditoriaLaboratoriosQt")
    app.setOrganizationName("AuditoriaSAIRC")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet("""
        QWidget { background: #101827; color: #e5edf9; }
        QMainWindow, QTabWidget::pane { background: #101827; }
        QLabel#title { font-size: 25px; font-weight: 700; }
        QLabel#muted { color: #a6bad1; }
        QGroupBox { border: 1px solid #33465e; border-radius: 8px; margin-top: 14px; padding: 13px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #a9c8fb; }
        QLineEdit, QComboBox, QSpinBox { background: #1c2b40; border: 1px solid #405772; border-radius: 5px; padding: 6px; }
        QPushButton { background: #2456a0; border: none; border-radius: 5px; padding: 8px 13px; font-weight: 600; }
        QPushButton:hover { background: #326ac0; }
        QPushButton:disabled { background: #26374d; color: #91a0b3; }
        QTabBar::tab { background: #1c2b40; padding: 10px 22px; margin-right: 4px; }
        QTabBar::tab:selected { background: #2456a0; }
        QProgressBar { border: 1px solid #33465e; border-radius: 4px; text-align: center; min-height: 19px; }
        QProgressBar::chunk { background: #168d79; }
        QTableView { background: #152136; alternate-background-color: #1d2c42; gridline-color: #33465e; selection-background-color: #2456a0; }
        QHeaderView::section { background: #263a56; padding: 7px; border: 1px solid #33465e; }
        QPlainTextEdit, QTextBrowser { background: #152136; border: 1px solid #33465e; border-radius: 5px; }
    """)
    window = MainWindow()
    if args.smoke_test:
        # El escritorio virtual offscreen mide 800x800 por defecto.
        window.resize(1440, 950)
    if args.smoke_report or args.review_report:
        from ui_qt.review import read_discrepancies
        from core.processor import _load_laboratory_mapping, _pipeline_signature
        from core.db_config import obtener_base_dir
        # También comprueba recursos empaquetados, sin conexiones externas.
        if not _load_laboratory_mapping() or not _pipeline_signature("llm") or not (obtener_base_dir() / "sql/consulta_sairc.sql").is_file():
            raise RuntimeError("Faltan recursos de la aplicación.")
        window.report_path.setText(args.smoke_report or args.review_report)
        if not args.smoke_test:
            QTimer.singleShot(0, window.load_report)
        else:
            rows = read_discrepancies(args.smoke_report or args.review_report)
            window.review.set_rows(rows, args.smoke_report or args.review_report)
            window.simulation_banner.setVisible(any(row.get("_simulation", False) for row in rows))
            window.tabs.setCurrentIndex(3)
            simulated = not window.simulation_banner.isHidden()
            window.stage_status.setText("2 Consolidado generado · 3 Referencia SIMULADA · 4 Revisión de PDF" if simulated else "4 Reporte de revisión cargado")
            window.status.setText(f"{'SIMULACIÓN' if simulated else 'Reporte cargado'}: {len(rows)} entradas. Selecciona una fila o utiliza Anterior/Siguiente.")
            if simulated:
                from core.workspace import find_hito2_excel
                excel = find_hito2_excel(Path(args.smoke_report or args.review_report).resolve().parent.parent)
                if excel:
                    window.excel_path.setText(str(excel))
                    window.last_excel = str(excel)
    window.show()
    if args.smoke_test:
        def finish():
            if args.screenshot:
                target = Path(args.screenshot)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(target)):
                    raise RuntimeError("No se pudo guardar la captura.")
            window.close()
            app.quit()
        QTimer.singleShot(350, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

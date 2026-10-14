import base64
import copy
import hashlib
import json
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtTest import QTest

from core import ai, processor
from core.ai import AIConfig, AIError, AIResponse, TokenUsage
from core.comparador import compare_excels, prepare_review_pdfs
from core.pdf_utils import get_pdf_page_count, pdf_pages_to_base64_images
from core.workspace import find_hito2_excel, get_hito_paths
from ui_qt.pdf_viewer import PdfViewer
from ui_qt.review import ReviewPane, read_discrepancies
from ui_qt.window import MainWindow


def config(**kwargs):
    return AIConfig(api_key="synthetic-key", allow_external_processing=True, **kwargs)


def wait_until(predicate, qt_app, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qt_app.processEvents()
        QTest.qWait(10)
    assert predicate()


@pytest.mark.parametrize("settings", [dict(allow_external_processing=False), dict(extraction_mode="python"), dict(extraction_mode="docling"), dict(provider="gemini", reader_mode="ocr"), dict(provider="mistral", reader_mode="vision", model="mistral-ocr-latest")])
def test_invalid_readers_never_send(settings, monkeypatch):
    monkeypatch.setattr(ai, "_post", lambda *a, **kw: pytest.fail("No debe enviar documentos"))
    values = dict(api_key="synthetic", allow_external_processing=True)
    values.update(settings)
    with pytest.raises(ValueError):
        ai.analyze_to_json(AIConfig(**values), pdf_path="nonexistent.pdf")


def test_pdf_all_pages_render_and_limit_prevents_send(make_pdf, monkeypatch):
    pdf = make_pdf(pages=3)
    assert get_pdf_page_count(str(pdf)) == 3
    images = pdf_pages_to_base64_images(str(pdf), dpi=72)
    assert len(images) == 3
    assert all(base64.b64decode(image).startswith(b"\xff\xd8") for image in images)
    with pytest.raises(ValueError, match="trunc"):
        pdf_pages_to_base64_images(str(pdf), max_pages=2)
    monkeypatch.setattr(ai, "_post", lambda *a, **kw: pytest.fail("No debe enviar PDF que exceden el límite"))
    with pytest.raises(AIError) as error:
        ai.analyze_vision(config(max_pdf_pages=2), str(pdf))
    assert error.value.category == "validation_error"


def test_damaged_pdf_does_not_silently_report_zero(tmp_path):
    path = tmp_path / "damaged.pdf"
    path.write_bytes(b"not a PDF")
    with pytest.raises(ValueError):
        get_pdf_page_count(str(path))


def test_mistral_modes_and_missing_annotation_cost(make_pdf, monkeypatch):
    pdf = make_pdf()
    calls = []
    response = AIResponse('{"v":2,"r":[]}')
    monkeypatch.setattr(ai, "call_mistral_ocr", lambda *a, **kw: calls.append("ocr") or response)
    monkeypatch.setattr(ai, "call_mistral_chat_vision", lambda *a, **kw: calls.append("vision") or response)
    ai.analyze_vision(config(provider="mistral", reader_mode="ocr", model="mistral-ocr-latest"), str(pdf))
    ai.analyze_vision(config(provider="mistral", reader_mode="vision", model="pixtral-large-latest"), str(pdf))
    assert calls == ["ocr", "vision"]


def test_mistral_missing_annotation_not_retried_and_usage_retained(make_pdf, monkeypatch):
    calls = []
    monkeypatch.setattr(ai, "_post", lambda *a, **kw: calls.append(1) or {"pages": [{"markdown": "synthetic"}], "usage_info": {"pages_processed": 1}})
    monkeypatch.setattr(ai.RATE_LIMITER, "wait_for_slot", lambda *a, **kw: None)
    with pytest.raises(AIError) as error:
        ai.analyze_to_json(config(provider="mistral", reader_mode="ocr", model="mistral-ocr-latest"), pdf_path=str(make_pdf()))
    assert len(calls) == 1
    assert error.value.category == "schema_required_field"
    assert error.value.token_usage.pages_processed == 1


def test_pipeline_four_hitos_cache_and_review(make_pdf, tmp_path, monkeypatch, qt_app):
    source = tmp_path / "originals"
    source.mkdir()
    pdf = source / "12345678.pdf"
    pdf.write_bytes(make_pdf().read_bytes())
    original_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    calls = []
    compact = {"v": 2, "p": "PACIENTE SINTETICO", "d": "12345678", "ft": "01/06/2026", "fx": "01/06/2026", "r": [{"a": "HEMOGLOBINA", "v": "12.0", "u": "g/dL"}]}
    monkeypatch.setattr(ai, "analyze_to_json", lambda *a, **kw: calls.append(1) or ai.validate_lab_json(copy.deepcopy(compact)))
    paths = get_hito_paths(tmp_path / "results")
    first = processor.process_folder(str(source), config(), output_dir=str(paths.hito1))
    assert first.success == 1 and first.errors == 0 and not first.excel_path
    assert not list(paths.hito1.rglob("*.xlsx"))
    resumed = processor.process_folder(str(source), config(), output_dir=str(paths.hito1))
    assert resumed.skipped_success == 1 and len(calls) == 1
    retry = processor.reprocess_temporary_errors(str(paths.hito1), str(source), config())
    assert retry.success == 1 and not retry.excel_path
    assert not list(paths.hito1.rglob("*.normalizado.json"))
    consolidated = processor.reprocess_ai_cache(str(paths.hito1), str(paths.hito2))
    assert consolidated.success == 1 and Path(consolidated.excel_path).is_file()
    assert find_hito2_excel(paths.root) == Path(consolidated.excel_path)
    assert len(calls) == 1
    paths.hito3.mkdir()
    reference = paths.hito3 / "Referencia_SAIRC_synthetic.csv"
    reference.write_text("Num Doc.,Fecha de Muestra,HB\n12345678,01/06/2026,9.0\n", encoding="utf-8")
    report = paths.hito4 / "reporte_priorizado_discrepancias_hito4.xlsx"
    stats = compare_excels(consolidated.excel_path, str(reference), str(report), pdf_root=str(source))
    rows = read_discrepancies(str(report))
    assert stats["hallazgos_total"] >= 1
    assert rows and Path(rows[0]["_pdf_path"]).is_file()
    pane = ReviewPane()
    pane.set_rows(rows)
    assert pane.viewer.path == Path(rows[0]["_pdf_path"]).resolve()
    pane.viewer.document.close()
    pane.close()
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == original_hash


def test_retry_recovers_invalid_json_without_exports(make_pdf, tmp_path, monkeypatch):
    pdf = make_pdf()
    source = tmp_path / "source"
    source.mkdir()
    (source / "12345678.pdf").write_bytes(pdf.read_bytes())
    output = tmp_path / "hito1"
    def fail(*a, **kw):
        raise AIError("Respuesta inválida sintética", category="invalid_json", token_usage=TokenUsage())
    monkeypatch.setattr(ai, "analyze_to_json", fail)
    first = processor.process_folder(str(source), config(), output_dir=str(output))
    assert first.errors == 1
    monkeypatch.setattr(ai, "analyze_to_json", lambda *a, **kw: ai.validate_lab_json({"v": 2, "r": [{"a": "Hemoglobina", "v": "12.0"}]}))
    recovered = processor.reprocess_temporary_errors(str(output), str(source), config())
    assert recovered.success == 1 and recovered.errors == 0 and not recovered.excel_path
    assert not list(output.rglob("*.xlsx"))
    assert not list(output.rglob("*.normalizado.json"))


def test_cache_does_not_confuse_reader_modes(make_pdf, tmp_path):
    pdf = make_pdf()
    raw = tmp_path / "raw.json"
    raw.write_text("{}")
    metadata = {**processor._quick_file_info(pdf, tmp_path), "status": "success", "provider": "mistral", "model": "mistral-ocr-latest", "extraction_mode": "llm", "pipeline_signature": processor.LEGACY_LLM_SIGNATURE}
    ocr = config(provider="mistral", model="mistral-ocr-latest", reader_mode="ocr")
    assert processor._cache_files_reusable(metadata, raw, tmp_path / "unused", pdf, tmp_path, ocr, require_normalized=False)
    metadata["reader_mode"] = "vision"
    assert not processor._cache_files_reusable(metadata, raw, tmp_path / "unused", pdf, tmp_path, ocr, require_normalized=False)


def test_viewer_navigation_zoom_search_and_missing(make_pdf, qt_app):
    viewer = PdfViewer()
    assert viewer.open_pdf(make_pdf(pages=2))
    viewer.page.setValue(2)
    assert viewer.view.pageNavigator().currentPage() == 1
    viewer.zoom.setCurrentIndex(4)
    assert viewer.view.zoomFactor() == 1.5
    viewer.search.setText("HEMOGLOBINA")
    wait_until(lambda: viewer.search_model.rowCount(QModelIndex()) >= 2, qt_app)
    viewer.next_match()
    assert viewer.match_index == 0
    assert not viewer.open_pdf("missing.pdf")
    assert viewer.path is None and viewer.document.pageCount() == 0
    viewer.close()


def test_review_proxy_selection_matches_visible_pdf_and_escape(make_pdf, qt_app):
    first = make_pdf("first.pdf")
    second = make_pdf("second.pdf")
    pane = ReviewPane()
    pane.set_rows([{"Documento": "BBBB", "Tipo_hallazgo": "DIFERENCIA", "Prioridad": "ALTA", "_pdf_path": str(first)}, {"Documento": "AAAA", "Tipo_hallazgo": "DIFERENCIA", "Prioridad": "BAJA", "Examen": "<script>texto</script>", "_pdf_path": str(second)}])
    pane.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
    pane.table.selectRow(0)
    assert pane.viewer.path == second.resolve()
    assert "&lt;script&gt;" in pane.details.toHtml()
    pane.query.setText("BBBB")
    pane.table.selectRow(0)
    assert pane.proxy.rowCount() == 1 and pane.viewer.path == first.resolve()
    pane.query.setText("no coincide")
    assert pane.proxy.rowCount() == 0
    pane.viewer.document.close()
    pane.close()


def test_worker_main_window_finish_error_and_safe_close(qt_app, monkeypatch):
    window = MainWindow()
    window.show()
    release = threading.Event()
    def operation(progress):
        progress({"percent": 30, "message": "Progreso sintético"})
        release.wait(3)
        return []
    window.start_task("load_report", operation)
    assert not window.action_buttons[0].isEnabled()
    window.close()
    assert window.isVisible() and window.cancel_event.is_set()
    release.set()
    wait_until(lambda: window.thread is None, qt_app)
    assert window.action_buttons[0].isEnabled()
    monkeypatch.setenv("LAB_EXTRACTOR_GEMINI_API_KEY", "synthetic-secret")
    def failed(_progress):
        raise RuntimeError("Fallo synthetic-secret")
    window.start_task("load_report", failed)
    wait_until(lambda: window.thread is None, qt_app)
    assert "synthetic-secret" not in window.log.toPlainText()
    assert "[oculto]" in window.status.text()
    window.close()


def test_review_copy_rejects_foreign_content_same_size(tmp_path):
    source, target = tmp_path / "source", tmp_path / "review"
    source.mkdir()
    target.mkdir()
    (source / "a.pdf").write_bytes(b"source")
    (target / "a.pdf").write_bytes(b"edited")
    findings = [{"Ruta_relativa": "a.pdf"}]
    with pytest.raises(FileExistsError):
        prepare_review_pdfs(findings, source, target)
    assert (target / "a.pdf").read_bytes() == b"edited"
    assert (source / "a.pdf").read_bytes() == b"source"


def test_original_application_preserved():
    root = Path(__file__).resolve().parents[1]
    origin = json.loads((root / "ORIGEN_CODIGO.json").read_text(encoding="utf-8"))
    if not (root.parent / "main.py").is_file():
        pytest.skip("La comprobación del original solo aplica en el checkout de migración")
    for relative, digest in origin["sha256"].items():
        assert hashlib.sha256((root.parent / relative).read_bytes()).hexdigest() == digest, relative


def test_settings_panels_and_pdf_workspace(qt_app):
    window = MainWindow()
    window.show()
    qt_app.processEvents()
    assert not window.provider.isVisible() and not window.log.isVisible()
    window.reader_dialog.show()
    qt_app.processEvents()
    assert window.provider.isVisible()
    window.threads.setValue(1)
    window.reader_dialog.accept()
    assert "1 hilos" in window.reader_summary.text()
    window.tabs.setCurrentIndex(2)
    assert not window.sql_server.isVisible()
    window.sql_dialog.show()
    qt_app.processEvents()
    assert window.sql_server.isVisible() and not window.sql_user.isEnabled()
    window.sql_trusted.setChecked(False)
    assert window.sql_user.isEnabled()
    window.sql_dialog.accept()
    window.tabs.setCurrentIndex(3)
    for width, height in ((1440, 950), (1050, 730)):
        window.resize(width, height)
        qt_app.processEvents()
        left, pdf = window.review.splitter.sizes()
        assert pdf > left and window.review.viewer.width() >= window.width() / 2
        assert not window.sources.isVisible()
    assert window.thread is None
    window.close()


def test_extraction_click_reports_missing_consent_and_starts_when_ready(qt_app, tmp_path, monkeypatch):
    window = MainWindow()
    window.show()
    window.input_path.setText(str(tmp_path))
    window.root_path.setText(str(tmp_path / "results"))
    window.provider.setCurrentText("mistral")
    window.mode.setCurrentIndex(window.mode.findData("vision"))
    window.api_key.setText("synthetic-secret")
    started = []
    monkeypatch.setattr(window, "start_task", lambda name, operation: started.append((name, operation)))
    window.extract_button.click()
    qt_app.processEvents()
    assert not started and window.error_banner.isVisible()
    assert "Autorizo enviar" in window.error_banner.text()
    assert not window.consent.isChecked()
    window.consent.setChecked(True)
    window.extract_button.click()
    assert len(started) == 1 and started[0][0] == "extract"
    window.show_error("Fallo synthetic-secret")
    assert "synthetic-secret" not in window.error_banner.text()
    window.close()


def test_cli_refuses_unapproved_external_processing(tmp_path, monkeypatch, capsys):
    from cli import main
    monkeypatch.setenv("LAB_EXTRACTOR_GEMINI_API_KEY", "synthetic-secret")
    monkeypatch.setattr(ai, "_post", lambda *a, **kw: pytest.fail("No debe enviar sin autorización"))
    code = main(["extract", str(tmp_path), str(tmp_path / "results"), "--model", "synthetic-model"])
    assert code == 1
    assert "synthetic-secret" not in capsys.readouterr().out
    assert not (tmp_path / "results").exists()


def test_mistral_defaults_small4_and_comparison_controls_removed(qt_app):
    window = MainWindow()
    window.provider.setCurrentText("mistral")
    assert window.mode.currentData() == "vision"
    assert window.model.currentText() == "mistral-small-2603"
    assert ai.DEFAULT_MODEL_BY_PROVIDER["mistral"] == "mistral-small-2603"
    assert not hasattr(window, "pilot_toggle")
    assert not any("3B" in button.text() for button in window.action_buttons)
    window.mode.setCurrentIndex(window.mode.findData("ocr"))
    assert window.model.currentText() == "mistral-ocr-latest"
    window.close()


def test_simulation_covers_each_pdf_without_sql_or_remote_calls(make_pdf, tmp_path, monkeypatch, qt_app):
    from core.simulation import simulate_review
    source = tmp_path / "originals"
    source.mkdir()
    pdf = source / "12345678.pdf"
    pdf.write_bytes(make_pdf().read_bytes())
    monkeypatch.setattr(ai, "analyze_to_json", lambda *a, **kw: ai.validate_lab_json({"v": 2, "d": "12345678", "ft": "01/06/2026", "r": [{"a": "HEMOGLOBINA", "v": "12.0"}]}))
    paths = get_hito_paths(tmp_path / "real")
    processor.process_folder(str(source), config(), output_dir=str(paths.hito1))
    (source / "without_reading.PDF").write_bytes(pdf.read_bytes())
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for base in (source, paths.hito1) for p in base.rglob("*") if p.is_file()}
    monkeypatch.setattr(ai, "_post", lambda *a, **kw: pytest.fail("La simulación no debe llamar a la IA"))
    monkeypatch.setattr(ai, "analyze_to_json", lambda *a, **kw: pytest.fail("La simulación no debe procesar PDF"))
    result = simulate_review(str(paths.hito1), str(source), str(paths.root))
    assert result["pdf_total"] == 2 and result["pdf_without_reading"] == 1
    assert result["external_calls"] == 0
    assert Path(result["root"]).is_relative_to(paths.root / "SIMULACION_VISOR")
    assert Path(result["excel"]).is_file() and Path(result["reference"]).is_file()
    assert not paths.hito3.exists() and not paths.hito4.exists()
    rows = read_discrepancies(result["report"])
    assert len(rows) == 2
    assert {row["Tipo_hallazgo"] for row in rows} == {"VALOR_DISCREPANTE", "SIMULACION_SIN_LECTURA"}
    assert all(row["_simulation"] for row in rows)
    pane = ReviewPane()
    pane.set_rows(rows)
    for index in range(2):
        pane.table.selectRow(index)
        qt_app.processEvents()
        assert pane.viewer.path == Path(rows[index]["_pdf_path"]).resolve()
        assert pane.viewer.document.pageCount() == 1
    pane.viewer.document.close()
    pane.close()
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    with pytest.raises(ValueError, match="fuera"):
        simulate_review(str(paths.hito1), str(source), str(source))


def test_simulation_button_works_without_reference_or_consent(qt_app, tmp_path, monkeypatch):
    window = MainWindow()
    window.root_path.setText(str(tmp_path))
    window.simulation_cache.setText(str(tmp_path / "hito1"))
    window.simulation_pdfs.setText(str(tmp_path / "pdfs"))
    assert not window.consent.isChecked() and not window.reference_path.text()
    started = []
    monkeypatch.setattr(window, "start_task", lambda name, op: started.append(name))
    window.start_simulation()
    assert started == ["simulate"]
    assert not window.error_banner.text()
    window.close()

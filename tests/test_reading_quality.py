import base64
import json
from contextlib import contextmanager

import pytest
from PySide6.QtCore import QSizeF
from PySide6.QtGui import QImage

from core import ai, pdf_utils, processor
from core.ai import AIConfig
from core.pilot import run_mistral_pilot
from core.sairc_normalizer import detect_field, normalize_result_value


def test_transparent_pdf_becomes_white_jpeg_without_losing_black_text(monkeypatch):
    image = QImage(72, 72, QImage.Format.Format_ARGB32)
    image.fill("transparent")
    for y in range(20, 40):
        for x in range(20, 40):
            image.setPixelColor(x, y, "black")

    class Document:
        def pageCount(self):
            return 1

        def pagePointSize(self, _page):
            return QSizeF(72, 72)

        def render(self, _page, size):
            return image.scaled(size)

    @contextmanager
    def opened(_path):
        yield Document()

    monkeypatch.setattr(pdf_utils, "open_pdf", opened)
    encoded = pdf_utils.pdf_pages_to_base64_images("synthetic.pdf", dpi=72)[0]
    decoded = QImage.fromData(base64.b64decode(encoded))
    assert decoded.pixelColor(5, 5).red() > 240
    assert decoded.pixelColor(30, 30).red() < 15


def test_serology_thresholds_and_quantitative_anti_hbs():
    assert normalize_result_value("ANTI_HBS", "3.86", "NO REACTIVO: < 10.0, REACTIVO: > 10.0") == ("3.86", 3.86, None)
    assert normalize_result_value("HIV", "3.86", "NO REACTIVO: < 10.0, REACTIVO: >= 10.0") == ("3.86", 3.86, None)
    assert normalize_result_value("HIV", "0.5", "NO REACTIVO: < 1.0, REACTIVO: ≥ 1.0")[0] == "NO REACTIVO"
    assert normalize_result_value("ANTI_HBC", "2.2", "REACTIVO: ≤ 1, NO REACTIVO: > 1")[0] == "NO REACTIVO"
    assert detect_field("FOSFATASA ALCANALINA") == "FOSFATASA_ALCALINA"


@pytest.mark.parametrize("value", ["sin_resultado", "Estado inmune >10.0", "UI/L"])
def test_placeholders_and_reference_text_are_not_results(value):
    assert normalize_result_value("ANTI_HBS", value) == (None, None, None)
    assert not ai.result_has_readable_value({"analisis": "Anti HBs", "resultado": value})
    assert normalize_result_value("HIV", "NEGATIVO")[0] == "NEGATIVO"


@pytest.mark.parametrize("results", [[], [{"a": "Hemoglobina", "v": "sin_resultado"}]])
def test_empty_reading_preserves_response_cost_and_manual_retry(make_pdf, tmp_path, monkeypatch, results):
    source = tmp_path / "pdfs"
    source.mkdir()
    (source / "synthetic.pdf").write_bytes(make_pdf().read_bytes())
    output = tmp_path / "results"
    data = ai.validate_lab_json({"v": 2, "r": results})
    assert not data["_meta"]["reading_valid"] and data["_meta"]["quality_level"] == "baja"
    data["_meta"]["token_usage"] = {"prompt_token_count": 100, "candidates_token_count": 10, "total_token_count": 110, "cost_estimated_usd": 0.04}
    monkeypatch.setattr(ai, "analyze_to_json", lambda *a, **kw: data)
    cfg = AIConfig(api_key="synthetic", allow_external_processing=True)
    summary = processor.process_folder(str(source), cfg, output_dir=str(output))
    assert summary.success == 0 and summary.errors == 1 and summary.revisar == 1
    assert summary.total_tokens == 110 and summary.total_cost_estimated_usd == 0.04
    assert list(output.rglob("respuestas_ia/*.json"))
    state = json.loads(next(output.rglob("*.meta.json")).read_text(encoding="utf-8"))
    assert state["error_type"] == "reading_empty" and state["reprocesable"]
    assert not state["temporary_error"]


def test_previous_mistral_images_and_pilot_are_not_reused(make_pdf, tmp_path, monkeypatch):
    pdf = make_pdf()
    raw = tmp_path / "raw.json"
    raw.write_text("{}")
    cfg = AIConfig(provider="mistral", reader_mode="vision", model="mistral-small-2603", api_key="synthetic", allow_external_processing=True)
    meta = {**processor._quick_file_info(pdf, tmp_path), "status": "success", "provider": cfg.provider, "model": cfg.model, "reader_mode": "vision", "extraction_mode": "llm", "pipeline_signature": processor.LEGACY_LLM_SIGNATURE}
    assert not processor._cache_files_reusable(meta, raw, tmp_path / "unused", pdf, tmp_path, cfg, require_normalized=False)
    meta["pdf_image_version"] = pdf_utils.PDF_IMAGE_VERSION
    assert processor._cache_files_reusable(meta, raw, tmp_path / "unused", pdf, tmp_path, cfg, require_normalized=False)
    pilot = tmp_path / "workspace/PRUEBA_MISTRAL_3_MODELOS"
    pilot.mkdir(parents=True)
    (pilot / "documentos_prueba.json").write_text(json.dumps({"sha256": {}}))
    source = tmp_path / "pdfs"
    source.mkdir()
    (source / "synthetic.pdf").write_bytes(pdf.read_bytes())
    monkeypatch.setattr(ai, "_get", lambda *a, **kw: pytest.fail("No debe consultar API para el piloto anterior"))
    with pytest.raises(ValueError, match="nueva raíz"):
        run_mistral_pilot(source, pilot.parent, cfg, authorize_three_models=True)

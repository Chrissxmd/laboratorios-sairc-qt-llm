import json
import pytest
from unittest.mock import patch

from core.ai import (
    AIConfig,
    AIError,
    validate_remote_model,
    call_mistral_chat_vision,
    call_mistral_ocr,
    call_mistral_text,
    estimate_cost_usd,
    test_connection as ai_test_connection,
)
from core.processor import safe_max_threads


def test_safe_max_threads_for_mistral():
    assert safe_max_threads("mistral") == 6


def test_estimate_cost_usd_mistral_models():
    # Ministral 3 14B: $0.20/M in, $0.20/M out
    cost_tokens = estimate_cost_usd("mistral", "ministral-3-14b", 1_000_000, 500_000)
    assert cost_tokens == 0.30

    # Pixtral 12B: $0.15/M in, $0.15/M out
    cost_pixtral = estimate_cost_usd("mistral", "pixtral-12b-2409", 1_000_000, 1_000_000)
    assert cost_pixtral == 0.30

    # Mistral OCR: $0.004 per page
    cost_ocr = estimate_cost_usd("mistral", "mistral-ocr-latest", None, None, pages_processed=5)
    assert cost_ocr == 0.02


def test_call_mistral_ocr_with_document_annotation():
    config = AIConfig(provider="mistral", model="mistral-ocr-latest", api_key="dummy_key")
    dummy_pdf_b64 = "JVBERi0xLjQKJcTl8uXr..."

    mock_resp = {
        "pages": [{"markdown": "# Lab Result", "page": 0}],
        "document_annotation": {
            "v": 2,
            "p": "JUAN PEREZ",
            "d": "12345678",
            "r": [
                {"a": "HEMOGLOBINA", "v": "11.5", "u": "g/dL"},
                {"a": "UREA PRE", "v": "140", "u": "mg/dL"},
            ],
        },
        "usage_info": {"pages_processed": 1, "document_size": 12345},
    }

    with patch("core.ai._post", return_value=mock_resp) as mock_post:
        ai_resp = call_mistral_ocr(config, dummy_pdf_b64)
        assert mock_post.called
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.mistral.ai/v1/ocr"
        assert kwargs["headers"]["Authorization"] == "Bearer dummy_key"

        # Debe contener el JSON de document_annotation
        parsed = json.loads(ai_resp.text)
        assert parsed["p"] == "JUAN PEREZ"
        assert parsed["v"] == 2
        assert len(parsed["r"]) == 2
        assert ai_resp.usage.pages_processed == 1
        assert ai_resp.usage.cost_estimated_usd == 0.004


def test_call_mistral_chat_vision_uses_images(make_pdf):
    pdf_path = str(make_pdf())

    config = AIConfig(provider="mistral", model="ministral-3-14b", api_key="dummy_key")

    mock_resp = {
        "choices": [
            {
                "message": {
                    "content": '{"v":2,"p":"MARIA LOPEZ","d":"87654321","r":[{"a":"HEMOGLOBINA","v":"12.0"}]}'
                }
            }
        ],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 200, "total_tokens": 1400},
    }

    with patch("core.ai._post", return_value=mock_resp) as mock_post:
        ai_resp = call_mistral_chat_vision(config, pdf_path)
        assert mock_post.called
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.mistral.ai/v1/chat/completions"
        assert kwargs["payload"]["model"] == "ministral-3-14b"
        assert kwargs["payload"]["response_format"] == {"type": "json_object"}

        # Verificar que el mensaje incluye image_url
        user_msg = kwargs["payload"]["messages"][1]
        assert any(part.get("type") == "image_url" for part in user_msg["content"])

        parsed = json.loads(ai_resp.text)
        assert parsed["p"] == "MARIA LOPEZ"
        assert ai_resp.usage.prompt_token_count == 1200
        assert ai_resp.usage.candidates_token_count == 200


def test_call_mistral_text():
    config = AIConfig(provider="mistral", model="ministral-3-14b", api_key="dummy_key")
    mock_resp = {
        "choices": [{"message": {"content": '{"v":2,"r":[]}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }

    with patch("core.ai._post", return_value=mock_resp) as mock_post:
        ai_resp = call_mistral_text(config, "# Markdown Text")
        assert mock_post.called
        assert ai_resp.text == '{"v":2,"r":[]}'
        assert ai_resp.usage.total_token_count == 120


def test_mistral_test_connection_successful():
    config = AIConfig(provider="mistral", model="mistral-ocr-latest", api_key="dummy_key")
    mock_resp = {"data": [{"id": "mistral-ocr-latest"}]}

    with patch("core.ai._get", return_value=mock_resp) as mock_get:
        ok, msg = ai_test_connection(config)
        assert ok is True
        assert "exitosa" in msg.lower()
        assert mock_get.called
        args, kwargs = mock_get.call_args
        assert args[0] == "https://api.mistral.ai/v1/models"
        assert kwargs["headers"]["Authorization"] == "Bearer dummy_key"


def test_catalog_accepts_alias_and_rejects_unavailable_or_text_only():
    cfg = AIConfig(provider="mistral", model="mistral-small-latest", api_key="synthetic", reader_mode="vision")
    with patch("core.ai._get", return_value={"data": [{"id": "mistral-small-current", "aliases": ["mistral-small-latest"], "capabilities": {"vision": True}}]}):
        validate_remote_model(cfg)
    with patch("core.ai._get", return_value={"data": []}):
        with pytest.raises(AIError) as error:
            validate_remote_model(cfg)
        assert error.value.category == "invalid_model"
    with patch("core.ai._get", return_value={"data": [{"id": cfg.model, "capabilities": {"vision": False}}]}):
        with pytest.raises(AIError) as error:
            validate_remote_model(cfg)
        assert error.value.category == "model_incompatible"


def test_missing_model_stops_entire_batch_without_pdf_upload(make_pdf, tmp_path, monkeypatch):
    from core import ai, processor
    source = tmp_path / "pdfs"
    source.mkdir()
    (source / "synthetic.pdf").write_bytes(make_pdf().read_bytes())
    calls = []
    monkeypatch.setattr(ai, "_get", lambda *a, **kw: calls.append(1) or {"data": []})
    monkeypatch.setattr(ai, "_post", lambda *a, **kw: pytest.fail("No debe enviar PDF con modelo inválido"))
    cfg = AIConfig(provider="mistral", model="pixtral-large-latest", api_key="synthetic", reader_mode="vision", allow_external_processing=True)
    output = tmp_path / "results"
    with pytest.raises(AIError, match="No se enviaron PDF"):
        processor.process_folder(str(source), cfg, output_dir=str(output))
    assert calls == [1]
    assert not list(output.rglob("*.meta.json"))


def test_legacy_invalid_model_errors_can_be_reprocessed(make_pdf, tmp_path, monkeypatch):
    from core import ai, processor
    source = tmp_path / "pdfs"
    source.mkdir()
    (source / "synthetic.pdf").write_bytes(make_pdf().read_bytes())
    output = tmp_path / "results"
    cfg = AIConfig(provider="mistral", model="mistral-small-latest", api_key="synthetic", reader_mode="vision", allow_external_processing=True)
    monkeypatch.setattr(ai, "_get", lambda *a, **kw: {"data": [{"id": cfg.model, "capabilities": {"vision": True}}]})
    def fail(*a, **kw):
        raise AIError('HTTP 400: {"message":"Invalid model: pixtral-large-latest","type":"invalid_model"}', category="http_400", status_code=400)
    monkeypatch.setattr(ai, "analyze_to_json", fail)
    assert processor.process_folder(str(source), cfg, output_dir=str(output)).errors == 1
    monkeypatch.setattr(ai, "analyze_to_json", lambda *a, **kw: ai.validate_lab_json({"v": 2, "r": [{"a": "Hemoglobina", "v": "12.0"}]}))
    summary = processor.reprocess_temporary_errors(str(output), str(source), cfg)
    assert summary.success == 1 and summary.errors == 0

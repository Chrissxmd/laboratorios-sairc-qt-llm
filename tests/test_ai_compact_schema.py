import json

import pytest

from core import ai
from core.ai import AIConfig, AIError, normalize_cached_lab_json, validate_lab_json


@pytest.fixture(autouse=True)
def clear_gemini_schema_capability_cache():
    ai._GEMINI_SCHEMA_SUPPORT.clear()
    yield
    ai._GEMINI_SCHEMA_SUPPORT.clear()


def test_compact_v2_expands_to_stable_internal_contract():
    compact = {
        "v": 2,
        "p": "PACIENTE PRUEBA",
        "d": "12345678",
        "ft": "10/07/2026",
        "r": [
            {"a": "HEMOGLOBINA", "v": "10.8", "u": "g/dL"},
            {"a": "UREA POST", "v": "46.3", "u": "mg/dL", "c": "baja", "el": "dudoso", "ol": "página 2"},
        ],
    }

    expanded = validate_lab_json(compact)

    assert expanded["paciente_nombre"] == "PACIENTE PRUEBA"
    assert expanded["documento_identidad"] == "12345678"
    assert expanded["fecha_toma_muestra"] == "10/07/2026"
    assert expanded["resultados"][0]["analisis"] == "HEMOGLOBINA"
    assert expanded["resultados"][0]["metodo"] is None
    assert expanded["resultados"][1]["confianza"] == "baja"
    assert expanded["_meta"]["schema_version"] == 2
    assert expanded["_meta"]["wire_format"] == "compact_objects_v2"


def test_compact_v2_corrects_unambiguous_value_unit_swap_and_audits_it():
    expanded = validate_lab_json({"v": 2, "r": [{"a": "UREA PRE", "v": "mg/dL", "u": "146.3"}]})

    row = expanded["resultados"][0]
    assert row["resultado"] == "146.3"
    assert row["unidades"] == "mg/dL"
    assert "resultado_1_valor_unidad_intercambiados; corregido" in expanded["_meta"]["schema_warnings"]


def test_compact_v2_rejects_unknown_keys_and_invalid_enums():
    with pytest.raises(AIError, match="claves no reconocidas"):
        validate_lab_json({"v": 2, "r": [{"a": "UREA PRE", "v": "146.3", "unidad": "mg/dL"}]})
    with pytest.raises(AIError, match="Confianza compacta inválida"):
        validate_lab_json({"v": 2, "r": [{"a": "UREA PRE", "v": "146.3", "c": "alta"}]})


def test_legacy_verbose_schema_remains_compatible():
    legacy = {
        "paciente_nombre": "PACIENTE HISTORICO",
        "documento_identidad": "87654321",
        "resultados": [{"analisis": "HEMOGLOBINA", "resultado": "11.2", "unidades": "g/dL"}],
    }

    expanded = validate_lab_json(legacy)

    assert expanded["paciente_nombre"] == "PACIENTE HISTORICO"
    assert expanded["resultados"][0]["resultado"] == "11.2"
    assert expanded["_meta"]["schema_version"] == 1
    assert expanded["_meta"]["wire_format"] == "legacy_verbose_v1"


def test_cached_compact_payload_keeps_source_and_usage_metadata():
    cached = {
        "v": 2,
        "r": [{"a": "UREA POST", "v": "40", "u": "mg/dL"}],
        "_source": {"ruta_relativa": "10806/a.pdf"},
        "_meta": {"token_usage": {"candidates_token_count": 100}},
    }

    expanded = normalize_cached_lab_json(cached)

    assert expanded["_source"]["ruta_relativa"] == "10806/a.pdf"
    assert expanded["_meta"]["token_usage"]["candidates_token_count"] == 100
    assert expanded["_meta"]["schema_version"] == 2


def test_gemini_request_uses_strict_compact_json_schema(monkeypatch):
    captured = {}

    def fake_post(url, headers, payload, timeout=120):
        captured.update(payload)
        return {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"v": 2, "r": []})}]}}],
            "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 8, "totalTokenCount": 28},
        }

    monkeypatch.setattr(ai, "_post", fake_post)
    response = ai.call_gemini(AIConfig(allow_external_processing=True, provider="gemini", model="gemini-test", api_key="x"), "informe")

    generation = captured["generationConfig"]
    assert generation["responseMimeType"] == "application/json"
    assert generation["responseJsonSchema"]["required"] == ["v", "r"]
    assert generation["responseJsonSchema"]["additionalProperties"] is False
    assert json.loads(response.text) == {"v": 2, "r": []}


def test_gemini_falls_back_once_when_endpoint_rejects_response_schema(monkeypatch):
    generation_configs = []

    def fake_post(url, headers, payload, timeout=120):
        generation_configs.append(payload["generationConfig"])
        if len(generation_configs) == 1:
            raise AIError("INVALID_ARGUMENT", category="http_400", status_code=400)
        return {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"v": 2, "r": []})}]}}],
            "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 8, "totalTokenCount": 28},
        }

    monkeypatch.setattr(ai, "_post", fake_post)
    config = AIConfig(allow_external_processing=True, provider="gemini", model="gemini-schema-rejected", api_key="x")

    first = ai.call_gemini(config, "informe")
    second = ai.call_gemini(config, "otro informe")

    assert "responseJsonSchema" in generation_configs[0]
    assert "responseJsonSchema" not in generation_configs[1]
    assert "responseJsonSchema" not in generation_configs[2]
    assert first.usage.structured_output_enforced is False
    assert first.usage.structured_output_fallback_reason == "http_400_invalid_argument_con_response_json_schema"
    assert second.usage.structured_output_enforced is False


def test_http_400_is_not_retried_by_outer_analysis_loop(monkeypatch):
    calls = []

    def fail_once(*args, **kwargs):
        calls.append(1)
        raise AIError("INVALID_ARGUMENT", category="http_400", status_code=400)

    monkeypatch.setattr(ai, "analyze_vision", fail_once)
    monkeypatch.setattr(ai.RATE_LIMITER, "wait_for_slot", lambda *args, **kwargs: None)

    with pytest.raises(AIError, match="INVALID_ARGUMENT"):
        ai.analyze_to_json(AIConfig(allow_external_processing=True, provider="gemini", api_key="x", max_retries=4), unused_path="synthetic.pdf")

    assert len(calls) == 1


def test_json_parser_uses_first_complete_object_and_audits_extra_content(monkeypatch):
    calls = []

    def response_with_extra(*args, **kwargs):
        calls.append(1)
        return ai.AIResponse(
            '{"v":2,"r":[{"a":"HEMOGLOBINA","v":"10.5","u":"g/dL"}]}\n{"nota":"extra"}',
            ai.TokenUsage(provider="gemini", model="gemini-test", prompt_token_count=30, candidates_token_count=20, total_token_count=50),
        )

    monkeypatch.setattr(ai, "analyze_vision", response_with_extra)
    monkeypatch.setattr(ai.RATE_LIMITER, "wait_for_slot", lambda *args, **kwargs: None)

    result = ai.analyze_to_json(AIConfig(allow_external_processing=True, provider="gemini", model="gemini-test", api_key="x"), unused_path="synthetic.pdf")

    assert len(calls) == 1
    assert result["resultados"][0]["analisis"] == "HEMOGLOBINA"
    assert "respuesta_con_contenido_adicional_ignorado; primer_json_utilizado" in result["_meta"]["schema_warnings"]
    assert result["_meta"]["token_usage"]["recovered_json_responses"] == 1


def test_token_usage_accumulates_across_invalid_json_retry(monkeypatch):
    responses = [
        ai.AIResponse("sin json", ai.TokenUsage(provider="gemini", model="gemini-test", prompt_token_count=20, candidates_token_count=8, total_token_count=28)),
        ai.AIResponse('{"v":2,"r":[]}', ai.TokenUsage(provider="gemini", model="gemini-test", prompt_token_count=30, candidates_token_count=10, total_token_count=40)),
    ]

    monkeypatch.setattr(ai, "analyze_vision", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(ai.RATE_LIMITER, "wait_for_slot", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai, "_sleep_cancelable", lambda *args, **kwargs: None)

    result = ai.analyze_to_json(AIConfig(allow_external_processing=True, provider="gemini", model="gemini-test", api_key="x", max_retries=2), unused_path="synthetic.pdf")
    usage = result["_meta"]["token_usage"]

    assert usage["prompt_token_count"] == 50
    assert usage["candidates_token_count"] == 18
    assert usage["total_token_count"] == 68
    assert usage["generation_attempts"] == 2
    assert usage["invalid_json_attempts"] == 1


def test_invalid_json_error_preserves_billable_usage(monkeypatch):
    monkeypatch.setattr(
        ai,
        "analyze_vision",
        lambda *args, **kwargs: ai.AIResponse(
            "sin json",
            ai.TokenUsage(provider="gemini", model="gemini-test", prompt_token_count=20, candidates_token_count=8, total_token_count=28),
        ),
    )
    monkeypatch.setattr(ai.RATE_LIMITER, "wait_for_slot", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai, "_sleep_cancelable", lambda *args, **kwargs: None)

    with pytest.raises(AIError) as exc_info:
        ai.analyze_to_json(AIConfig(allow_external_processing=True, provider="gemini", model="gemini-test", api_key="x", max_retries=2), unused_path="synthetic.pdf")

    assert exc_info.value.category == "invalid_json"
    assert exc_info.value.token_usage.prompt_token_count == 40
    assert exc_info.value.token_usage.candidates_token_count == 16
    assert exc_info.value.token_usage.generation_attempts == 2

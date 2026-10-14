import json

from core.retry import (
    is_reprocessable_error,
    is_temporary_error,
    reprocessable_errors_from_state,
    temporary_errors_from_state,
    write_retry_outputs,
)


def test_invalid_json_is_manual_reprocessable_but_not_automatic_temporary(tmp_path):
    state = tmp_path / "estado_documentos"
    state.mkdir()
    payload = {
        "filename": "documento.pdf",
        "ruta_relativa": "documento.pdf",
        "status": "error",
        "error_type": "invalid_json",
        "error": "Extra data",
    }
    (state / "documento.meta.json").write_text(json.dumps(payload), encoding="utf-8")

    assert is_temporary_error("invalid_json", "Extra data") is False
    assert is_reprocessable_error("invalid_json", "Extra data") is True
    assert temporary_errors_from_state(state) == []
    assert len(reprocessable_errors_from_state(state)) == 1

    queue = write_retry_outputs(tmp_path, state)
    assert len(queue) == 1
    assert queue[0]["error_type"] == "invalid_json"


def test_schema_unknown_keys_is_reprocessable(tmp_path):
    state = tmp_path / "estado_documentos"
    state.mkdir()
    payload = {
        "filename": "doc_schema.pdf",
        "ruta_relativa": "doc_schema.pdf",
        "status": "error",
        "error_type": "schema_unknown_keys",
        "error": "Resultado compacto 16 contiene claves no reconocidas: mg/dL.",
    }
    (state / "doc_schema.meta.json").write_text(json.dumps(payload), encoding="utf-8")

    assert is_reprocessable_error("schema_unknown_keys") is True
    assert len(reprocessable_errors_from_state(state)) == 1
    queue = write_retry_outputs(tmp_path, state)
    assert len(queue) == 1
    assert queue[0]["error_type"] == "schema_unknown_keys"


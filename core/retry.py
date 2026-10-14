from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.ai import AIError
from core.config import (
    LEGACY_RETRY_QUEUE_CSV_FILENAME,
    LEGACY_RETRY_QUEUE_FILENAME,
    RETRY_QUEUE_CSV_FILENAME,
    RETRY_QUEUE_FILENAME,
)
from core.exporters import write_csv_dicts
from core.persistence import write_json_atomic as _safe_write_json

TEMPORARY_ERROR_TYPES = {
    "http_500",
    "http_502",
    "http_503",
    "http_504",
    "timeout_408",
    "rate_limit_429",
    "network_error",
    "ai_failed",
}

REPROCESSABLE_ERROR_TYPES = TEMPORARY_ERROR_TYPES | {
    "invalid_json",
    "schema_unknown_keys",
    "schema_version_invalid",
    "schema_invalid",
    "schema_too_many_results",
    "schema_required_field",
    "schema_enum_invalid",
    "validation_error",
    "invalid_model",
    "model_incompatible",
    "reading_empty",
}


def normalize_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AIError):
        return exc.category, str(exc)
    if isinstance(exc, FileNotFoundError):
        return "file_not_found", str(exc)
    if isinstance(exc, PermissionError):
        return "permission_error", str(exc)
    if isinstance(exc, RuntimeError):
        return "runtime_error", str(exc)
    if isinstance(exc, ValueError):
        return "value_error", str(exc)
    return "unexpected_error", str(exc)


def is_temporary_error(error_type: str | None, error_msg: str | None = None) -> bool:
    et = (error_type or "").lower()
    msg = (error_msg or "").lower()
    if et in TEMPORARY_ERROR_TYPES:
        return True
    temporary_markers = [
        "tempor",
        "timeout",
        "timed out",
        "connection",
        "network",
        "unreachable",
        "high demand",
        "overloaded",
        "unavailable",
        "503",
        "502",
        "504",
        "429",
    ]
    return any(marker in et or marker in msg for marker in temporary_markers)


def is_reprocessable_error(error_type: str | None, error_msg: str | None = None) -> bool:
    et = (error_type or "").lower()
    return (
        et in REPROCESSABLE_ERROR_TYPES
        or (et in {"http_400", "http_404"} and ("invalid_model" in (error_msg or "").lower() or "invalid model" in (error_msg or "").lower()))
        or et.startswith("schema_")
        or is_temporary_error(error_type, error_msg)
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def temporary_errors_from_state(state_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for meta_path in sorted(state_dir.glob("*.meta.json")):
        try:
            meta = _read_json(meta_path)
            if meta.get("status") == "error" and is_temporary_error(meta.get("error_type"), meta.get("error")):
                rows.append({**meta, "_meta_path": str(meta_path)})
        except Exception:
            continue
    return rows


def reprocessable_errors_from_state(state_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for meta_path in sorted(state_dir.glob("*.meta.json")):
        try:
            meta = _read_json(meta_path)
            if meta.get("status") == "error" and is_reprocessable_error(meta.get("error_type"), meta.get("error")):
                rows.append({**meta, "_meta_path": str(meta_path)})
        except Exception:
            continue
    return rows


def write_retry_outputs(out_dir: Path, state_dir: Path) -> list[dict]:
    errors = reprocessable_errors_from_state(state_dir)
    queue = []
    for meta in errors:
        queue.append(
            {
                "archivo": meta.get("filename"),
                "ruta_relativa": meta.get("ruta_relativa"),
                "carpeta_origen": meta.get("carpeta_origen"),
                "error_type": meta.get("error_type"),
                "error": meta.get("error"),
                "updated_at": meta.get("updated_at"),
                "reprocesar_si_no": "SI",
                "recomendacion": "Ejecutar reproceso de errores recuperables; los temporales también pueden reintentarse automáticamente.",
            }
        )
    retry_queue_path = out_dir / RETRY_QUEUE_FILENAME
    if (out_dir / LEGACY_RETRY_QUEUE_FILENAME).exists() and not retry_queue_path.exists():
        retry_queue_path = out_dir / LEGACY_RETRY_QUEUE_FILENAME
    retry_csv_path = out_dir / RETRY_QUEUE_CSV_FILENAME
    if (out_dir / LEGACY_RETRY_QUEUE_CSV_FILENAME).exists() and not retry_csv_path.exists():
        retry_csv_path = out_dir / LEGACY_RETRY_QUEUE_CSV_FILENAME
    _safe_write_json(
        retry_queue_path,
        {"updated_at": datetime.now().isoformat(timespec="seconds"), "count": len(queue), "items": queue},
    )
    write_csv_dicts(retry_csv_path, queue)
    return queue

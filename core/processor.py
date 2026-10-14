from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from core.ai import AIError, AICancelled, AIConfig, TokenUsage, COMPACT_SCHEMA_VERSION, COMPACT_WIRE_FORMAT, normalize_cached_lab_json
from core.config import (
    ABSOLUTE_MAX_THREADS,
    APP_VERSION,
    AI_RESPONSE_DIRNAME,
    CACHE_DIRNAME,
    DEFAULT_OUTPUT_DIR,
    DOCUMENT_STATE_DIRNAME,
    INTERNAL_FILES_DIRNAME,
    LEGACY_AI_RESPONSE_DIRNAME,
    LEGACY_CACHE_DIRNAME,
    LEGACY_DOCUMENT_STATE_DIRNAME,
    LEGACY_NORMALIZED_DATA_DIRNAME,
    LEGACY_RETRY_QUEUE_CSV_FILENAME,
    LEGACY_RETRY_QUEUE_FILENAME,
    LEGACY_RUN_SUMMARY_FILENAME,
    MAX_THREADS_BY_PROVIDER,
    NORMALIZED_DATA_DIRNAME,
    PIPELINE_CACHE_VERSION,
    LEGACY_LLM_SIGNATURE,
    COMPATIBLE_LLM_SIGNATURES,
    RETRY_QUEUE_CSV_FILENAME,
    RETRY_QUEUE_FILENAME,
    RUN_SUMMARY_FILENAME,
)
from core.exporters import write_csv as _write_csv
from core.exporters import build_llm_vision_recommendations as _build_llm_vision_recommendations
from core.exporters import write_excel as _write_excel
from core.exporters import write_sairc_csvs as _write_sairc_csvs
from core.comparador import compare_and_update
from core.pdf_utils import get_pdf_page_count, PDF_IMAGE_VERSION
from core.persistence import write_json_atomic as _safe_write_json
from core.retry import (
    is_reprocessable_error as _is_reprocessable_error,
    is_temporary_error as _is_temporary_error,
    normalize_error as _normalize_error,
    reprocessable_errors_from_state as _reprocessable_errors_from_state,
    temporary_errors_from_state as _temporary_errors_from_state,
    write_retry_outputs as _write_retry_outputs,
)
from core.sairc_normalizer import normalize_ai_output, result_has_readable_value
from core.cache_index import init_index, upsert_entry, is_fast_reusable, get_entry

log = logging.getLogger("lab_extractor.processor")
ProgressCallback = Optional[Callable[[dict], None]]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_JSONL_LOCK = threading.Lock()


@dataclass
class ProcessingSummary:
    total: int = 0
    success: int = 0
    errors: int = 0
    digital: int = 0
    ocr: int = 0
    skipped_success: int = 0
    threads_used: int = 1
    output_dir: str = ""
    excel_path: str = ""
    total_prompt_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_estimated_usd: float = 0.0
    avg_seconds_per_pdf: float = 0.0
    revisar: int = 0
    ok: int = 0


def _emit(cb: ProgressCallback, **payload) -> None:
    if cb:
        cb(payload)


def _is_onedrive_path(path: Path) -> bool:
    return any(part.lower() == "onedrive" for part in path.resolve().parts)


def _close_log_handler(handler: logging.Handler | None) -> None:
    if handler is None:
        return
    try:
        log.removeHandler(handler)
    finally:
        handler.close()


def _close_log_handlers_for_path(log_path: Path) -> None:
    target = str(log_path.resolve()).lower()
    for handler in list(log.handlers):
        base_filename = getattr(handler, "baseFilename", None)
        if base_filename and str(Path(base_filename).resolve()).lower() == target:
            _close_log_handler(handler)


def _try_init_index(db_path: Path) -> bool:
    try:
        init_index(db_path)
        return True
    except Exception as exc:
        log.warning("No se pudo inicializar cache_index.sqlite. Se usará reanudación por archivos: %s", exc)
        return False


def _try_upsert_entry(db_path: Path, entry: dict) -> bool:
    try:
        upsert_entry(db_path, entry)
        return True
    except Exception as exc:
        log.debug("No se pudo actualizar cache_index.sqlite para %s: %s", entry.get("ruta_relativa"), exc)
        return False


def _try_get_entry(db_path: Path, ruta_relativa: str) -> dict | None:
    try:
        return get_entry(db_path, ruta_relativa)
    except Exception as exc:
        log.debug("No se pudo leer cache_index.sqlite para %s: %s", ruta_relativa, exc)
        return None


def _try_is_fast_reusable(
    db_path: Path,
    ruta_relativa: str,
    size_bytes: int,
    mtime_ns: int,
    provider: str,
    model: str,
    extraction_mode: str,
    pipeline_signature: str,
    validate_files: bool = True,
    require_normalized: bool = True,
) -> dict | None:
    try:
        return is_fast_reusable(
            db_path,
            ruta_relativa,
            size_bytes,
            mtime_ns,
            provider,
            model,
            extraction_mode,
            pipeline_signature,
            validate_files=validate_files,
            require_normalized=require_normalized,
        )
    except Exception as exc:
        log.debug("No se pudo validar cache rápido para %s: %s", ruta_relativa, exc)
        return None


def _wait_if_paused_or_cancelled(
    pause_event: threading.Event | None, cancel_event: threading.Event | None, cb: ProgressCallback, filename: str = "", rel: str = ""
) -> bool:
    """Devuelve False si el usuario solicitó detener. La pausa se aplica entre PDFs o antes de llamar a la API."""
    if cancel_event is not None and cancel_event.is_set():
        return False
    notified = False
    while pause_event is not None and pause_event.is_set():
        if cancel_event is not None and cancel_event.is_set():
            return False
        if not notified:
            _emit(
                cb,
                stage="paused",
                filename=filename,
                ruta_relativa=rel,
                message=f"Pausado. Se retomará desde cache al continuar: {rel or filename}",
            )
            notified = True
        time.sleep(0.25)
    if notified:
        _emit(cb, stage="resumed", filename=filename, ruta_relativa=rel, message="Proceso reanudado.")
    return True


def safe_max_threads(provider: str) -> int:
    return min(MAX_THREADS_BY_PROVIDER.get(provider.lower(), 2), ABSOLUTE_MAX_THREADS)




@lru_cache(maxsize=4)
def _pipeline_signature(extraction_mode: str) -> str:
    if extraction_mode != "llm":
        raise ValueError("Esta edición solo admite lectura remota LLM/OCR.")
    digest = hashlib.sha256(f"{PIPELINE_CACHE_VERSION}:llm".encode("utf-8"))
    digest.update(b"core/ai.py")
    digest.update((PROJECT_ROOT / "core" / "ai.py").read_bytes())
    return digest.hexdigest()[:20]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_cache_root(out_dir: Path) -> Path:
    legacy = out_dir / LEGACY_CACHE_DIRNAME
    current = out_dir / INTERNAL_FILES_DIRNAME / CACHE_DIRNAME
    if legacy.exists() and not current.exists():
        return legacy
    return current


def _resolve_state_dir(out_dir: Path) -> Path:
    legacy = out_dir / LEGACY_DOCUMENT_STATE_DIRNAME
    current = out_dir / INTERNAL_FILES_DIRNAME / DOCUMENT_STATE_DIRNAME
    if legacy.exists() and not current.exists():
        return legacy
    return current


def _resolve_ai_response_dir(cache_root: Path) -> Path:
    legacy = cache_root / LEGACY_AI_RESPONSE_DIRNAME
    current = cache_root / AI_RESPONSE_DIRNAME
    if legacy.exists() and not current.exists():
        return legacy
    return current


def _resolve_ai_reprocess_source(input_path: Path) -> tuple[Path, Path]:
    """Acepta raíz de resultados, ``_Archivos_Internos`` o una caché directa."""
    base = input_path.expanduser()
    name = base.name.lower()

    if name == AI_RESPONSE_DIRNAME.lower() and base.is_dir():
        return base.parent, base
    if name == CACHE_DIRNAME.lower() and base.is_dir():
        return base, _resolve_ai_response_dir(base)
    if name == INTERNAL_FILES_DIRNAME.lower() and (base / CACHE_DIRNAME).is_dir():
        cache_root = base / CACHE_DIRNAME
        return cache_root, _resolve_ai_response_dir(cache_root)

    cache_root = _resolve_cache_root(base)
    return cache_root, _resolve_ai_response_dir(cache_root)


def _resolve_normalized_dir(cache_root: Path) -> Path:
    legacy = cache_root / LEGACY_NORMALIZED_DATA_DIRNAME
    current = cache_root / NORMALIZED_DATA_DIRNAME
    if legacy.exists() and not current.exists():
        return legacy
    return current


def _resolve_run_summary_path(out_dir: Path) -> Path:
    legacy = out_dir / LEGACY_RUN_SUMMARY_FILENAME
    current = out_dir / INTERNAL_FILES_DIRNAME / RUN_SUMMARY_FILENAME
    if legacy.exists() and not current.exists():
        return legacy
    return current


def _resolve_retry_queue_path(out_dir: Path) -> Path:
    legacy = out_dir / LEGACY_RETRY_QUEUE_FILENAME
    current = out_dir / INTERNAL_FILES_DIRNAME / RETRY_QUEUE_FILENAME
    if legacy.exists() and not current.exists():
        return legacy
    return current


def _resolve_retry_queue_csv_path(out_dir: Path) -> Path:
    legacy = out_dir / LEGACY_RETRY_QUEUE_CSV_FILENAME
    current = out_dir / INTERNAL_FILES_DIRNAME / RETRY_QUEUE_CSV_FILENAME
    if legacy.exists() and not current.exists():
        return legacy
    return current


def _pdf_from_meta(meta: dict, input_dir: Path) -> Path | None:
    rel = meta.get("ruta_relativa") or meta.get("filename")
    if not rel:
        return None
    path = input_dir / rel
    return path if path.exists() else None


def _token_usage(data: dict) -> dict:
    meta = data.get("_meta") or {}
    usage = meta.get("token_usage") or {}

    if "model" in usage and "prompt_token_count" in usage and "candidates_token_count" in usage:
        from core.ai import estimate_cost_usd
        new_cost = estimate_cost_usd(
            provider=usage.get("provider", "gemini"),
            model=usage["model"],
            prompt_tokens=usage.get("prompt_token_count"),
            output_tokens=usage.get("candidates_token_count")
        )
        if new_cost is not None:
            usage["cost_estimated_usd"] = new_cost

    return usage


def _quality(data: dict) -> dict:
    meta = data.get("_meta") or {}
    return {
        "quality_score": meta.get("quality_score"),
        "quality_level": meta.get("quality_level"),
        "rows_detected": meta.get("rows_detected"),
        "rows_dropped": meta.get("rows_dropped"),
    }


def _sha12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _quick_file_info(pdf_path: Path, input_dir: Path) -> dict:
    st = pdf_path.stat()
    rel = pdf_path.relative_to(input_dir).as_posix()
    carpeta = str(Path(rel).parent).replace(".", "") or input_dir.name
    return {
        "ruta_relativa": rel,
        "filename": pdf_path.name,
        "carpeta_origen": carpeta,
        "size_bytes": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
    }


def _index_entry_from_meta(
    meta: dict, raw_path: Path | None, norm_path: Path | None, meta_path: Path, pdf_path: Path | None = None, input_dir: Path | None = None
) -> dict:
    entry = {
        "ruta_relativa": meta.get("ruta_relativa"),
        "filename": meta.get("filename"),
        "carpeta_origen": meta.get("carpeta_origen"),
        "cache_stem": meta.get("cache_stem"),
        "raw_json": str(raw_path) if raw_path else None,
        "norm_json": str(norm_path) if norm_path else None,
        "meta_json": str(meta_path),
        "status": meta.get("status"),
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "extraction_mode": meta.get("extraction_mode"),
        "pipeline_signature": meta.get("pipeline_signature"),
        "updated_at": meta.get("updated_at"),
        "error_type": meta.get("error_type"),
        "error": meta.get("error"),
    }
    if pdf_path is not None and input_dir is not None and pdf_path.exists():
        entry.update({k: v for k, v in _quick_file_info(pdf_path, input_dir).items() if k in {"size_bytes", "mtime_ns"}})
    else:
        entry["size_bytes"] = meta.get("size_bytes")
        entry["mtime_ns"] = meta.get("mtime_ns")
    return entry


def _cache_files_reusable(
    meta: dict,
    raw_path: Path,
    norm_path: Path,
    pdf_path: Path,
    input_dir: Path,
    ai_config: AIConfig,
    require_normalized: bool = True,
) -> bool:
    if meta.get("status") != "success":
        return False
    if not raw_path.exists() or (require_normalized and not norm_path.exists()):
        return False
    historical_mode = meta.get("reader_mode") or ("ocr" if meta.get("provider") == "mistral" and "ocr" in str(meta.get("model", "")).lower() else "vision")
    if historical_mode != ai_config.reader_mode:
        return False
    if ai_config.provider == "mistral" and ai_config.reader_mode == "vision" and meta.get("pdf_image_version") != PDF_IMAGE_VERSION:
        return False
    q = _quick_file_info(pdf_path, input_dir)
    if int(meta.get("size_bytes") or -1) != int(q["size_bytes"]):
        return False
    if int(meta.get("mtime_ns") or -1) != int(q["mtime_ns"]):
        return False
    extraction_mode = (getattr(ai_config, "extraction_mode", "") or "llm").lower()
    if (meta.get("extraction_mode") or "").lower() != extraction_mode:
        return False
    if meta.get("pipeline_signature") not in {_pipeline_signature(extraction_mode), LEGACY_LLM_SIGNATURE, *COMPATIBLE_LLM_SIGNATURES}:
        return False
    if extraction_mode == "llm":
        if (meta.get("provider") or "").lower() != (ai_config.provider or "").lower():
            return False
        if (meta.get("model") or "") != (ai_config.model or ""):
            return False
    return True


def _cached_paths_for_pdf(
    pdf_path: Path, input_dir: Path, raw_dir: Path, norm_dir: Path, state_dir: Path
) -> tuple[str, str, str, Path, Path, Path]:
    stem, rel, carpeta = _cache_stem(pdf_path, input_dir)
    return stem, rel, carpeta, state_dir / f"{stem}.meta.json", raw_dir / f"{stem}.json", norm_dir / f"{stem}.normalizado.json"


def _reuse_cached_pdf_if_valid(
    pdf_path: Path,
    input_dir: Path,
    raw_dir: Path,
    norm_dir: Path,
    state_dir: Path,
    cache_index_path: Path,
    ai_config: AIConfig,
    require_normalized: bool = True,
) -> dict | None:
    stem, rel, _carpeta, meta_path, raw_path, norm_path = _cached_paths_for_pdf(pdf_path, input_dir, raw_dir, norm_dir, state_dir)
    if not meta_path.exists():
        return None
    try:
        meta = _read_json(meta_path)
    except Exception:
        return None
    if not _cache_files_reusable(
        meta, raw_path, norm_path, pdf_path, input_dir, ai_config, require_normalized=require_normalized
    ):
        return None
    if meta.get("cache_stem") != stem:
        meta["cache_stem"] = stem
        _safe_write_json(meta_path, meta)
    _try_upsert_entry(cache_index_path, _index_entry_from_meta(meta, raw_path, norm_path, meta_path, pdf_path, input_dir))
    return {"meta": meta_path, "raw": raw_path, "norm": norm_path, "ruta_relativa": rel}


def _cache_stem(pdf_path: Path, input_dir: Path) -> tuple[str, str, str]:
    rel = pdf_path.relative_to(input_dir).as_posix()
    digest = _sha12(pdf_path)
    safe_rel = rel.replace("/", "__").replace("\\", "__")
    stem = f"{Path(safe_rel).stem}.{digest}"
    carpeta = str(Path(rel).parent).replace(".", "")
    if not carpeta:
        carpeta = input_dir.name
    return stem, rel, carpeta


def _row_archivo_from_meta(meta: dict, raw: dict | None, norm: dict | None) -> dict:
    usage = _token_usage(raw or {})
    q = _quality(raw or {})
    cab = (norm or {}).get("cabecera") or {}
    return {
        "ruta_relativa": meta.get("ruta_relativa"),
        "archivo": meta.get("filename"),
        "carpeta_origen": meta.get("carpeta_origen"),
        "status": meta.get("status"),
        "estado_archivo": cab.get("estado_archivo"),
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "pages": meta.get("pages"),
        "file_size_mb": meta.get("file_size_mb"),
        "seconds": meta.get("seconds"),
        "paciente": cab.get("paciente"),
        "documento_archivo_pdf": cab.get("documento_archivo_pdf"),
        "documento_identidad": cab.get("documento_identidad"),
        "coincidencia_documento": cab.get("coincidencia_documento"),
        "estado_identidad": cab.get("estado_identidad"),
        "requiere_verificacion_identidad": cab.get("requiere_verificacion_identidad"),
        "requiere_verificacion_resultados": cab.get("requiere_verificacion_resultados"),
        "requiere_verificacion_humana": cab.get("requiere_verificacion_humana"),
        "motivo_identidad": cab.get("motivo_identidad"),
        "laboratorio": cab.get("laboratorio"),
        "fecha_toma_muestra": cab.get("fecha_toma_muestra"),
        "fecha_emision": cab.get("fecha_emision"),
        "resultados_extraidos": cab.get("resultados_extraidos"),
        "resultados_normalizados": cab.get("resultados_normalizados"),
        "resultados_revisar": cab.get("resultados_revisar"),
        "faltantes_basicos": cab.get("faltantes_basicos"),
        **q,
        "tokens_estimados_entrada": usage.get("estimated_input_tokens"),
        "prompt_token_count": usage.get("prompt_token_count"),
        "candidates_token_count": usage.get("candidates_token_count"),
        "total_token_count": usage.get("total_token_count"),
        "costo_estimado_usd": usage.get("cost_estimated_usd"),
        "error_type": meta.get("error_type"),
        "error": meta.get("error"),
    }


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _JSONL_LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _process_single_pdf(
    pdf_path: Path,
    input_dir: Path,
    idx: int,
    total: int,
    ai_config: AIConfig,
    raw_dir: Path,
    norm_dir: Path,
    state_dir: Path,
    progress_cb: ProgressCallback,
    log_jsonl: Path,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    detected_lab: str = "GENERIC",
    normalize_output: bool = True,
) -> dict:
    stem, rel, carpeta, meta_path, raw_path, norm_path = _cached_paths_for_pdf(pdf_path, input_dir, raw_dir, norm_dir, state_dir)
    name = pdf_path.name
    extraction_mode = (getattr(ai_config, "extraction_mode", "") or "llm").lower()
    pipeline_signature = _pipeline_signature(extraction_mode)
    laboratory = detected_lab

    def emit(**kw):
        _emit(progress_cb, filename=name, ruta_relativa=rel, current=idx, total=total, **kw)

    started = time.perf_counter()
    try:
        if not _wait_if_paused_or_cancelled(pause_event, cancel_event, progress_cb, name, rel):
            emit(stage="cancelled_file", message=f"[{idx}/{total}] ⏹ Omitido por detención: {rel}")
            return {"ok": False, "cancelled": True, "skipped": False, "meta": None, "raw": None, "norm": None}
        if meta_path.exists() and raw_path.exists() and (norm_path.exists() or not normalize_output):
            meta = _read_json(meta_path)
            if _cache_files_reusable(
                meta, raw_path, norm_path, pdf_path, input_dir, ai_config, require_normalized=normalize_output
            ):
                emit(stage="skip_file", message=f"[{idx}/{total}] ↷ Reutilizando cache IA: {rel}")
                return {"ok": True, "skipped": True, "meta": meta_path, "raw": raw_path, "norm": norm_path}

        emit(stage="start_file", message=f"[{idx}/{total}] Iniciando {rel}")
        t_pdf = time.perf_counter()
        pages = get_pdf_page_count(str(pdf_path))
        size_mb = round(pdf_path.stat().st_size / (1024 * 1024), 3)

        pdf_load_seconds = round(time.perf_counter() - t_pdf, 2)
        if not _wait_if_paused_or_cancelled(pause_event, cancel_event, progress_cb, name, rel):
            emit(stage="cancelled_file", message=f"[{idx}/{total}] ⏹ Omitido por detención antes de extracción: {rel}")
            return {"ok": False, "cancelled": True, "skipped": False, "meta": None, "raw": None, "norm": None}
        mode = f"api_{ai_config.provider}_{ai_config.reader_mode}"

        def ai_progress(msg: str):
            emit(stage="ai_detail", message=f"{name}: {msg}")
            log.debug("%s: %s", name, msg)

        t_ai = time.perf_counter()

        from core.ai import analyze_to_json
        raw_data = analyze_to_json(ai_config, progress=ai_progress, unused_path=str(pdf_path), cancel_event=cancel_event)
        raw_data.setdefault("_meta", {})["reader_mode"] = ai_config.reader_mode
        raw_data["_meta"]["provider"] = ai_config.provider
        raw_data["_meta"]["model"] = ai_config.model

        ai_seconds = round(time.perf_counter() - t_ai, 2)
        raw_data.setdefault("_source", {})
        raw_data["_source"].update({"ruta_relativa": rel, "archivo": name, "carpeta_origen": carpeta, "cache_stem": stem})
        _safe_write_json(raw_path, raw_data)
        if not any(result_has_readable_value(item) for item in raw_data.get("resultados") or []):
            usage = _token_usage(raw_data)
            raise AIError("La respuesta no contiene resultados útiles. Se conservó el JSON para revisión y reproceso manual.", category="reading_empty", token_usage=TokenUsage(**{key: value for key, value in usage.items() if key in TokenUsage.__dataclass_fields__}))
        normalize_seconds = 0.0
        if normalize_output:
            t_norm = time.perf_counter()
            norm_data = normalize_ai_output(raw_data, ruta_relativa=rel, carpeta_origen=carpeta)
            normalize_seconds = round(time.perf_counter() - t_norm, 2)
            _safe_write_json(norm_path, norm_data)
        usage = _token_usage(raw_data)
        seconds = round(time.perf_counter() - started, 2)
        qinfo = _quick_file_info(pdf_path, input_dir)
        meta = {
            "filename": name,
            "ruta_relativa": rel,
            "carpeta_origen": carpeta,
            "cache_stem": stem,
            "size_bytes": qinfo.get("size_bytes"),
            "mtime_ns": qinfo.get("mtime_ns"),
            "status": "success",
            "mode": mode,
            "provider": ai_config.provider,
            "model": ai_config.model,
            "extraction_mode": extraction_mode,
            "reader_mode": ai_config.reader_mode,
            "pipeline_signature": pipeline_signature,
            "pdf_image_version": PDF_IMAGE_VERSION if ai_config.provider == "mistral" and ai_config.reader_mode == "vision" else None,
            "laboratory": laboratory,
            "pages": pages,
            "file_size_mb": size_mb,
            "pdf_load_seconds": pdf_load_seconds,
            "ai_seconds": ai_seconds,
            "normalize_seconds": normalize_seconds,
            "seconds": seconds,
            "rows": len(raw_data.get("resultados") or []),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error_type": None,
            "error": None,
        }
        _safe_write_json(meta_path, meta)
        _append_jsonl(log_jsonl, {"event": "success", **meta, "token_usage": usage})
        emit(
            stage="done_file",
            message=f"[{idx}/{total}] OK {rel} ({len(raw_data.get('resultados') or [])} filas IA, USD {usage.get('cost_estimated_usd') or 0})",
        )
        return {
            "ok": True,
            "skipped": False,
            "meta": meta_path,
            "raw": raw_path,
            "norm": norm_path if normalize_output else None,
        }
    except AICancelled:
        emit(stage="cancelled_file", message=f"[{idx}/{total}] ⏹ Cancelado por el usuario: {rel}")
        return {"ok": False, "cancelled": True, "skipped": False, "meta": None, "raw": None, "norm": None}
    except Exception as exc:
        error_type, error_msg = _normalize_error(exc)
        qinfo = _quick_file_info(pdf_path, input_dir) if pdf_path.exists() else {}
        temporary = _is_temporary_error(error_type, error_msg)
        reprocessable = _is_reprocessable_error(error_type, error_msg)
        error_usage = getattr(exc, "token_usage", None) if isinstance(exc, AIError) else None
        usage = error_usage.__dict__.copy() if error_usage is not None else {}
        meta = {
            "filename": name,
            "ruta_relativa": rel,
            "carpeta_origen": carpeta,
            "cache_stem": stem,
            "size_bytes": qinfo.get("size_bytes"),
            "mtime_ns": qinfo.get("mtime_ns"),
            "status": "error",
            "mode": None,
            "provider": ai_config.provider,
            "model": ai_config.model,
            "extraction_mode": extraction_mode,
            "reader_mode": ai_config.reader_mode,
            "pipeline_signature": pipeline_signature,
            "laboratory": laboratory,
            "pages": None,
            "file_size_mb": None,
            "seconds": round(time.perf_counter() - started, 2),
            "rows": 0,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error_type": error_type,
            "error": error_msg,
            "temporary_error": temporary,
            "reprocesable": reprocessable,
            "token_usage": usage,
        }
        _safe_write_json(meta_path, meta)
        _append_jsonl(log_jsonl, {"event": "error", **meta})
        log.error("ERROR %s [%s]: %s", rel, error_type, error_msg)
        emit(stage="error_file", message=f"[{idx}/{total}] [X] {rel}: {error_type} - {error_msg}")
        return {"ok": False, "skipped": False, "meta": meta_path, "raw": None, "norm": None}


def _avg_seconds(costos_rows: list[dict]) -> float:
    vals = []
    for r in costos_rows:
        try:
            v = float(r.get("seconds") or 0)
            if v > 0:
                vals.append(v)
        except Exception:
            pass
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def _collect_extraction_summary(
    pdf_files: list[Path], input_dir: Path, raw_dir: Path, state_dir: Path
) -> ProcessingSummary:
    """Resume el Hito 1 sin normalizar ni construir entregables del Hito 2."""
    summary = ProcessingSummary(total=len(pdf_files))
    seconds: list[float] = []
    for pdf_path in pdf_files:
        stem, _rel, _carpeta = _cache_stem(pdf_path, input_dir)
        meta_path = state_dir / f"{stem}.meta.json"
        raw_path = raw_dir / f"{stem}.json"
        if not meta_path.exists():
            continue
        meta = _read_json(meta_path)
        if meta.get("status") != "success" or not raw_path.exists():
            summary.errors += 1
            if meta.get("error_type") == "reading_empty":
                summary.revisar += 1
            usage = meta.get("token_usage") or {}
            summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
            summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
            summary.total_tokens += int(usage.get("total_token_count") or 0)
            summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
            continue
        summary.success += 1
        summary.digital += 1
        raw = _read_json(raw_path)
        usage = _token_usage(raw)
        summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
        summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
        summary.total_tokens += int(usage.get("total_token_count") or 0)
        summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
        try:
            if meta.get("seconds"):
                seconds.append(float(meta["seconds"]))
        except (TypeError, ValueError):
            pass
    summary.avg_seconds_per_pdf = round(sum(seconds) / len(seconds), 2) if seconds else 0.0
    summary.total_cost_estimated_usd = round(summary.total_cost_estimated_usd, 6)
    return summary


def _apply_llm_recommendations(archivo_rows: list[dict], control_rows: list[dict], pendientes: list[dict]) -> list[dict]:
    recommendations = _build_llm_vision_recommendations(archivo_rows, pendientes)
    recommended_labs = {r.get("carpeta_origen") for r in recommendations if r.get("recomendar_llm_vision") == "SI"}
    for row in archivo_rows + control_rows:
        lab = row.get("carpeta_origen") or "(raiz)"
        row["recomendacion_llm_vision"] = "SI" if lab in recommended_labs else "NO"
        row["motivo_recomendacion_llm_vision"] = (
            "inconsistencias_detectadas_en_laboratorio_reprocesar_grupo_completo_con_llm_vision" if lab in recommended_labs else None
        )
    for row in pendientes:
        lab = row.get("carpeta_origen") or "(raiz)"
        row["recomendacion_llm_vision"] = "SI" if lab in recommended_labs else "NO"
    return recommendations


def _collect_outputs(
    pdf_files: list[Path], input_dir: Path, raw_dir: Path, norm_dir: Path, state_dir: Path, output_dir: Path, ai_config: AIConfig, reference_csv: str = ""
) -> ProcessingSummary:
    summary = ProcessingSummary(total=len(pdf_files))
    archivo_rows: list[dict] = []
    control_rows: list[dict] = []
    normalizados: list[dict] = []
    sairc_rows: list[dict] = []
    pendientes: list[dict] = []
    raw_rows: list[dict] = []
    costos_rows: list[dict] = []
    error_rows: list[dict] = []

    for pdf_path in pdf_files:
        stem, rel, carpeta = _cache_stem(pdf_path, input_dir)
        meta_path = state_dir / f"{stem}.meta.json"
        raw_path = raw_dir / f"{stem}.json"
        norm_path = norm_dir / f"{stem}.normalizado.json"
        if not meta_path.exists():
            continue
        meta = _read_json(meta_path)
        raw = _read_json(raw_path) if raw_path.exists() and meta.get("status") == "success" else None
        norm = _read_json(norm_path) if norm_path.exists() and meta.get("status") == "success" else None
        archivo_rows.append(_row_archivo_from_meta(meta, raw, norm))
        if meta.get("status") != "success":
            summary.errors += 1
            summary.revisar += int(meta.get("error_type") == "reading_empty")
            usage = meta.get("token_usage") or {}
            summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
            summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
            summary.total_tokens += int(usage.get("total_token_count") or 0)
            summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
            error_rows.append(
                {"ruta_relativa": rel, "archivo": pdf_path.name, "error_tipo": meta.get("error_type"), "error": meta.get("error")}
            )
            continue
        summary.success += 1
        summary.digital += 1
        cab = (norm or {}).get("cabecera") or {}
        if str(cab.get("estado_archivo") or "").upper() in {"OK", "OK_CON_REGLA", "OK_CARGABLE", "OK_CON_ALERTA_CLINICA"}:
            summary.ok += 1
        else:
            summary.revisar += 1
        usage = _token_usage(raw or {})
        summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
        summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
        summary.total_tokens += int(usage.get("total_token_count") or 0)
        summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
        control_rows.append(cab)
        sairc_rows.append((norm or {}).get("sairc") or {})
        for r in (norm or {}).get("resultados_normalizados") or []:
            normalizados.append(
                {
                    **{
                        k: cab.get(k)
                        for k in [
                            "ruta_relativa",
                            "paciente",
                            "documento_archivo_pdf",
                            "documento_identidad",
                            "coincidencia_documento",
                            "estado_identidad",
                            "puede_cargarse_sairc",
                            "laboratorio",
                            "edad",
                            "sexo",
                            "fecha_examen",
                            "fecha_toma_muestra",
                            "fecha_emision",
                            "firma",
                        ]
                    },
                    **r,
                }
            )
        pendientes.extend((norm or {}).get("pendientes") or [])
        raw_rows.append(
            {
                "ruta_relativa": rel,
                "paciente": (raw or {}).get("paciente_nombre"),
                "documento_identidad": (raw or {}).get("documento_identidad"),
                "laboratorio": (raw or {}).get("laboratorio"),
                "resultados_extraidos_ia": len((raw or {}).get("resultados") or []),
                "respuesta_ia_json": raw_path.name,
                "datos_normalizados_json": norm_path.name,
            }
        )
        costos_rows.append(
            {
                "ruta_relativa": rel,
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "pages": meta.get("pages"),
                "file_size_mb": meta.get("file_size_mb"),
                "seconds": meta.get("seconds"),
                "pdf_load_seconds": meta.get("pdf_load_seconds"),
                "ai_seconds": meta.get("ai_seconds"),
                "normalize_seconds": meta.get("normalize_seconds"),
                "rpm_configurado": ai_config.requests_per_minute,
                "count_tokens_activo": ai_config.enable_token_count,
                "count_tokens_seconds": usage.get("count_tokens_seconds"),
                "tokens_estimados_entrada": usage.get("estimated_input_tokens"),
                "prompt_token_count": usage.get("prompt_token_count"),
                "candidates_token_count": usage.get("candidates_token_count"),
                "total_token_count": usage.get("total_token_count"),
                "costo_estimado_usd": usage.get("cost_estimated_usd"),
            }
        )

    summary.avg_seconds_per_pdf = _avg_seconds(costos_rows)

    resumen_rows = [
        {
            "version": APP_VERSION,
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
            "total_pdf": len(pdf_files),
            "procesados_ok": summary.success,
            "errores": summary.errors,
            "archivos_ok_o_alerta": summary.ok,
            "archivos_revisar": summary.revisar,
            "resultados_normalizados": len(normalizados),
            "pendientes_revision": len(pendientes),
            "provider": ai_config.provider,
            "model": ai_config.model,
            "input_tokens": summary.total_prompt_tokens,
            "output_tokens": summary.total_output_tokens,
            "total_tokens": summary.total_tokens,
            "costo_estimado_usd": round(summary.total_cost_estimated_usd, 6),
            "promedio_segundos_pdf": summary.avg_seconds_per_pdf,
        }
    ]

    llm_recommendations = _apply_llm_recommendations(archivo_rows, control_rows, pendientes)
    resumen_rows[0]["laboratorios_recomendados_llm_vision"] = len(
        [r for r in llm_recommendations if r.get("recomendar_llm_vision") == "SI"]
    )

    internal_dir = output_dir / INTERNAL_FILES_DIRNAME
    _write_csv(output_dir / "resultados_normalizados.csv", normalizados)
    if reference_csv:
        compare_and_update(reference_csv, archivo_rows, control_rows, sairc_rows)
    _write_sairc_csvs(internal_dir, sairc_rows)
    _write_csv(internal_dir / "pendientes_revision.csv", pendientes)
    _write_csv(internal_dir / "recomendaciones_llm_vision.csv", llm_recommendations)
    _write_csv(internal_dir / "archivos.csv", archivo_rows)
    _write_csv(internal_dir / "errores_laboratorio.csv", error_rows)
    summary.excel_path = str(_write_excel(
        output_dir, resumen_rows, control_rows, normalizados, sairc_rows, archivo_rows, pendientes, raw_rows, costos_rows, error_rows
    ))
    return summary


def _rebuild_index_from_state(cache_index_path: Path, input_dir: Path, raw_dir: Path, norm_dir: Path, state_dir: Path) -> int:
    """Reconstruye índice SQLite desde estado_documentos/*.meta.json sin llamar a IA."""
    if not _try_init_index(cache_index_path):
        return 0
    count = 0
    for meta_path in state_dir.glob("*.meta.json"):
        try:
            meta = _read_json(meta_path)
            rel = meta.get("ruta_relativa")
            if not rel:
                continue
            pdf_path = input_dir / rel
            raw_path = raw_dir / f"{meta.get('cache_stem')}.json" if meta.get("cache_stem") else None
            norm_path = norm_dir / f"{meta.get('cache_stem')}.normalizado.json" if meta.get("cache_stem") else None
            entry = _index_entry_from_meta(meta, raw_path, norm_path, meta_path, pdf_path if pdf_path.exists() else None, input_dir)
            if _try_upsert_entry(cache_index_path, entry):
                count += 1
        except Exception as exc:
            log.debug("No se pudo indexar %s: %s", meta_path, exc)
    return count


def _collect_outputs_fast(
    pdf_files: list[Path], input_dir: Path, cache_index_path: Path, output_dir: Path, ai_config: AIConfig, reference_csv: str = ""
) -> ProcessingSummary:
    """Colecta resultados usando SQLite, evitando calcular hash de todos los PDFs."""
    summary = ProcessingSummary(total=len(pdf_files))
    archivo_rows: list[dict] = []
    control_rows: list[dict] = []
    normalizados: list[dict] = []
    sairc_rows: list[dict] = []
    pendientes: list[dict] = []
    raw_rows: list[dict] = []
    costos_rows: list[dict] = []
    error_rows: list[dict] = []

    for pdf_path in pdf_files:
        qinfo = _quick_file_info(pdf_path, input_dir)
        rel = qinfo["ruta_relativa"]
        row = _try_get_entry(cache_index_path, rel)
        if not row:
            continue
        meta_path = Path(row.get("meta_json") or "")
        raw_path = Path(row.get("raw_json") or "") if row.get("raw_json") else None
        norm_path = Path(row.get("norm_json") or "") if row.get("norm_json") else None
        if not meta_path.exists():
            continue
        meta = _read_json(meta_path)
        raw = _read_json(raw_path) if raw_path and raw_path.exists() and meta.get("status") == "success" else None
        norm = _read_json(norm_path) if norm_path and norm_path.exists() and meta.get("status") == "success" else None
        archivo_rows.append(_row_archivo_from_meta(meta, raw, norm))
        if meta.get("status") != "success":
            summary.errors += 1
            error_rows.append(
                {"ruta_relativa": rel, "archivo": pdf_path.name, "error_tipo": meta.get("error_type"), "error": meta.get("error")}
            )
            continue
        summary.success += 1
        summary.digital += 1
        cab = (norm or {}).get("cabecera") or {}
        if str(cab.get("estado_archivo") or "").upper() in {"OK", "OK_CON_REGLA", "OK_CARGABLE", "OK_CON_ALERTA_CLINICA"}:
            summary.ok += 1
        else:
            summary.revisar += 1
        usage = _token_usage(raw or {})
        summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
        summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
        summary.total_tokens += int(usage.get("total_token_count") or 0)
        summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
        control_rows.append(cab)
        sairc_rows.append((norm or {}).get("sairc") or {})
        for r in (norm or {}).get("resultados_normalizados") or []:
            normalizados.append(
                {
                    **{
                        k: cab.get(k)
                        for k in [
                            "ruta_relativa",
                            "paciente",
                            "documento_archivo_pdf",
                            "documento_identidad",
                            "coincidencia_documento",
                            "estado_identidad",
                            "puede_cargarse_sairc",
                            "laboratorio",
                            "edad",
                            "sexo",
                            "fecha_examen",
                            "fecha_toma_muestra",
                            "fecha_emision",
                            "firma",
                        ]
                    },
                    **r,
                }
            )
        pendientes.extend((norm or {}).get("pendientes") or [])
        raw_rows.append(
            {
                "ruta_relativa": rel,
                "paciente": (raw or {}).get("paciente_nombre"),
                "documento_archivo_pdf": cab.get("documento_archivo_pdf"),
                "documento_identidad": (raw or {}).get("documento_identidad"),
                "coincidencia_documento": cab.get("coincidencia_documento"),
                "laboratorio": (raw or {}).get("laboratorio"),
                "resultados_extraidos_ia": len((raw or {}).get("resultados") or []),
                "respuesta_ia_json": raw_path.name if raw_path else None,
                "datos_normalizados_json": norm_path.name if norm_path else None,
            }
        )
        costos_rows.append(
            {
                "ruta_relativa": rel,
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "pages": meta.get("pages"),
                "file_size_mb": meta.get("file_size_mb"),
                "seconds": meta.get("seconds"),
                "pdf_load_seconds": meta.get("pdf_load_seconds"),
                "ai_seconds": meta.get("ai_seconds"),
                "normalize_seconds": meta.get("normalize_seconds"),
                "rpm_configurado": ai_config.requests_per_minute,
                "count_tokens_activo": ai_config.enable_token_count,
                "count_tokens_seconds": usage.get("count_tokens_seconds"),
                "tokens_estimados_entrada": usage.get("estimated_input_tokens"),
                "prompt_token_count": usage.get("prompt_token_count"),
                "candidates_token_count": usage.get("candidates_token_count"),
                "total_token_count": usage.get("total_token_count"),
                "costo_estimado_usd": usage.get("cost_estimated_usd"),
            }
        )

    summary.avg_seconds_per_pdf = _avg_seconds(costos_rows)

    resumen_rows = [
        {
            "version": APP_VERSION,
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
            "total_pdf": len(pdf_files),
            "procesados_ok": summary.success,
            "errores": summary.errors,
            "archivos_ok_o_alerta": summary.ok,
            "archivos_revisar": summary.revisar,
            "resultados_normalizados": len(normalizados),
            "pendientes_revision": len(pendientes),
            "provider": ai_config.provider,
            "model": ai_config.model,
            "input_tokens": summary.total_prompt_tokens,
            "output_tokens": summary.total_output_tokens,
            "total_tokens": summary.total_tokens,
            "costo_estimado_usd": round(summary.total_cost_estimated_usd, 6),
            "promedio_segundos_pdf": summary.avg_seconds_per_pdf,
            "cache_index": str(cache_index_path),
        }
    ]

    llm_recommendations = _apply_llm_recommendations(archivo_rows, control_rows, pendientes)
    resumen_rows[0]["laboratorios_recomendados_llm_vision"] = len(
        [r for r in llm_recommendations if r.get("recomendar_llm_vision") == "SI"]
    )

    internal_dir = output_dir / INTERNAL_FILES_DIRNAME
    _write_csv(output_dir / "resultados_normalizados.csv", normalizados)
    if reference_csv:
        compare_and_update(reference_csv, archivo_rows, control_rows, sairc_rows)
    _write_sairc_csvs(internal_dir, sairc_rows)
    _write_csv(internal_dir / "pendientes_revision.csv", pendientes)
    _write_csv(internal_dir / "recomendaciones_llm_vision.csv", llm_recommendations)
    _write_csv(internal_dir / "archivos.csv", archivo_rows)
    _write_csv(internal_dir / "errores_laboratorio.csv", error_rows)
    summary.excel_path = str(_write_excel(
        output_dir, resumen_rows, control_rows, normalizados, sairc_rows, archivo_rows, pendientes, raw_rows, costos_rows, error_rows
    ))
    return summary


def _load_laboratory_mapping() -> dict[str, str]:
    dict_path = PROJECT_ROOT / "diccionario_laboratorios.json"
    fallback = {"SANTA ENA": "CORLABS", "HEALT AND SAFETY": "HYS", "ROCHEM": "ROCHEM", "GRAU": "ROCHEM"}
    if not dict_path.exists():
        return fallback
    try:
        payload = json.loads(dict_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("No se pudo leer %s: %s", dict_path, exc)
        return fallback
    return {str(key).upper(): str(value).upper() for key, value in payload.items()}


def _laboratory_from_path(input_dir: Path, pdf_path: Path, mapping: dict[str, str]) -> str | None:
    """Resuelve el laboratorio con el CUI de la raíz o de cada subcarpeta."""
    try:
        relative_parts = pdf_path.relative_to(input_dir).parts[:-1]
    except ValueError:
        relative_parts = pdf_path.parts[:-1]
    for part in (input_dir.name, *relative_parts):
        upper = str(part).upper()
        cui_match = re.match(r"^(\d+)", upper)
        if cui_match and cui_match.group(1) in mapping:
            return mapping[cui_match.group(1)]
        for key, lab in mapping.items():
            if not key.isdigit() and key in upper:
                return lab
    return None






def _process_folder_impl(
    folder_path: str,
    ai_config: AIConfig,
    progress_cb: ProgressCallback = None,
    threads: int = 1,
    output_dir: str | None = None,
    resume_fast: bool = True,
    rebuild_index: bool = False,
    skip_cache_validation: bool = False,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    reference_csv: str = "",
    build_exports: bool = False,
) -> ProcessingSummary:
    from core.ai import validate_reader_config
    validate_reader_config(ai_config)
    provider_max = safe_max_threads(ai_config.provider)
    threads = max(1, min(int(threads), provider_max))
    input_dir = Path(folder_path)
    if not input_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta: {input_dir}")
    pdf_files = sorted(input_dir.rglob("*.pdf"))
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    cache_root = _resolve_cache_root(out_dir)
    raw_dir = _resolve_ai_response_dir(cache_root)
    norm_dir = _resolve_normalized_dir(cache_root)
    state_dir = _resolve_state_dir(out_dir)
    cache_index_path = cache_root / "cache_index.sqlite"
    cache_index_existed = cache_index_path.exists()
    required_dirs = [out_dir, raw_dir, state_dir, cache_index_path.parent]
    if build_exports:
        required_dirs.append(norm_dir)
    for d in required_dirs:
        d.mkdir(parents=True, exist_ok=True)
    index_available = _try_init_index(cache_index_path)
    internal_dir = out_dir / INTERNAL_FILES_DIRNAME
    run_log = internal_dir / "process.log"
    fh = logging.FileHandler(run_log, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(fh)
    log.setLevel(logging.DEBUG)
    log_jsonl = internal_dir / "process.jsonl"
    log.info("==== NUEVA EJECUCION v%s GEMINI/IA DIRECTA + SAIRC + CACHE RAPIDO ====", APP_VERSION)
    log.info("Inicio — %d PDFs, %d hilos, proveedor=%s, modelo=%s", len(pdf_files), threads, ai_config.provider, ai_config.model)

    if _is_onedrive_path(out_dir):
        warning_msg = f"Salida en carpeta OneDrive detectada. Para produccion se recomienda usar {DEFAULT_OUTPUT_DIR} u otra ruta local no sincronizada."
        log.warning(warning_msg)
        _emit(progress_cb, stage="output_warning", message=warning_msg, percent=0, total=len(pdf_files), current=0)

    if index_available and (rebuild_index or (resume_fast and not cache_index_existed)):
        rebuilt = _rebuild_index_from_state(cache_index_path, input_dir, raw_dir, norm_dir, state_dir)
        reason = "solicitado" if rebuild_index else "automático por índice faltante"
        _emit(
            progress_cb,
            stage="rebuild_index",
            message=f"Indice reconstruido desde {DOCUMENT_STATE_DIRNAME} ({reason}): {rebuilt} registros",
            percent=0,
            total=len(pdf_files),
            current=0,
        )

    _emit(
        progress_cb,
        stage="scan",
        message=f"Se encontraron {len(pdf_files)} PDFs incluyendo subcarpetas. Salida: {out_dir}",
        percent=0,
        total=len(pdf_files),
        current=0,
    )
    if not pdf_files:
        _close_log_handler(fh)
        return ProcessingSummary(total=0, threads_used=threads, output_dir=str(out_dir))

    laboratory_mapping = _load_laboratory_mapping()
    laboratory_by_pdf = {
        pdf_path: _laboratory_from_path(input_dir, pdf_path, laboratory_mapping) or "GENERIC" for pdf_path in pdf_files
    }
    laboratory_counts: dict[str, int] = {}
    for laboratory in laboratory_by_pdf.values():
        laboratory_counts[laboratory] = laboratory_counts.get(laboratory, 0) + 1
    laboratory_summary = ", ".join(f"{lab}={count}" for lab, count in sorted(laboratory_counts.items()))
    log.info("Laboratorios resueltos por PDF: %s", laboratory_summary)
    _emit(
        progress_cb,
        stage="scan",
        message=f"Laboratorios por PDF/IPRESS: {laboratory_summary}. El emisor se conserva desde la respuesta remota.",
        percent=0,
        total=len(pdf_files),
        current=0,
    )

    to_process: list[tuple[int, Path]] = []
    skipped_success = 0
    if resume_fast:
        for idx, pdf_path in enumerate(pdf_files, start=1):
            q = _quick_file_info(pdf_path, input_dir)
            reusable = (
                _try_is_fast_reusable(
                    cache_index_path,
                    q["ruta_relativa"],
                    q["size_bytes"],
                    q["mtime_ns"],
                    ai_config.provider,
                    ai_config.model,
                    (getattr(ai_config, "extraction_mode", "") or "llm").lower(),
                    _pipeline_signature((getattr(ai_config, "extraction_mode", "") or "llm").lower()),
                    validate_files=not skip_cache_validation,
                    require_normalized=build_exports,
                )
                if index_available
                else None
            )
            if reusable:
                try:
                    mode_meta = _read_json(Path(reusable["meta_json"]))
                    historical_mode = mode_meta.get("reader_mode") or ("ocr" if mode_meta.get("provider") == "mistral" and "ocr" in str(mode_meta.get("model", "")).lower() else "vision")
                    reusable = reusable if historical_mode == ai_config.reader_mode else None
                except (OSError, ValueError, KeyError):
                    reusable = None
            if reusable:
                skipped_success += 1
            elif _reuse_cached_pdf_if_valid(
                pdf_path,
                input_dir,
                raw_dir,
                norm_dir,
                state_dir,
                cache_index_path,
                ai_config,
                require_normalized=build_exports,
            ):
                skipped_success += 1
            else:
                to_process.append((idx, pdf_path))
        _emit(
            progress_cb,
            stage="resume_fast",
            message=f"Cache rápido reutilizado: {skipped_success}. Pendientes IA: {len(to_process)}",
            percent=0,
            total=len(pdf_files),
            current=0,
        )
    else:
        to_process = list(enumerate(pdf_files, start=1))

    if to_process and not (cancel_event and cancel_event.is_set()):
        from core.ai import validate_remote_model
        _emit(progress_cb, stage="preflight", message="Comprobando disponibilidad del modelo antes de enviar el lote…", percent=0)
        validate_remote_model(ai_config)

    completed = skipped_success
    completed_lock = threading.Lock()

    def wrap_progress(payload: dict) -> None:
        nonlocal completed
        if payload.get("stage") in {"done_file", "error_file", "skip_file", "cancelled_file"}:
            with completed_lock:
                completed += 1
                pct = int((completed / len(pdf_files)) * 100)
            payload = {**payload, "completed": completed, "percent": pct, "skipped": payload.get("stage") == "skip_file"}
        _emit(progress_cb, **payload)

    def _run_batch(batch_items: list[tuple[int, Path]], workers: int, progress_func: Callable[[dict], None]) -> None:
        nonlocal skipped_success
        if not batch_items:
            return
        if cancel_event is not None and cancel_event.is_set():
            return
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(
                    _process_single_pdf,
                    pdf_path,
                    input_dir,
                    idx,
                    len(pdf_files),
                    ai_config,
                    raw_dir,
                    norm_dir,
                    state_dir,
                    progress_func,
                    log_jsonl,
                    pause_event,
                    cancel_event,
                    laboratory_by_pdf.get(pdf_path)
                    or _laboratory_from_path(input_dir, pdf_path, laboratory_mapping)
                    or "AUTO",
                    build_exports,
                ): pdf_path
                for idx, pdf_path in batch_items
            }
            for future in as_completed(futures):
                if cancel_event is not None and cancel_event.is_set():
                    for f in futures:
                        f.cancel()
                    break
                try:
                    result = future.result()
                except Exception as exc:
                    log.error("Error no controlado en tarea de procesamiento: %s", exc)
                    if cancel_event is not None and cancel_event.is_set():
                        continue
                    continue
                if result.get("cancelled"):
                    continue
                meta_path = result.get("meta")
                try:
                    if meta_path:
                        meta = _read_json(Path(meta_path))
                        cache_stem = meta.get("cache_stem")
                        pdf_path = futures[future]
                        raw_path = raw_dir / f"{cache_stem}.json" if cache_stem else None
                        norm_candidate = norm_dir / f"{cache_stem}.normalizado.json" if cache_stem else None
                        norm_path = norm_candidate if norm_candidate and norm_candidate.exists() else None
                        _try_upsert_entry(
                            cache_index_path, _index_entry_from_meta(meta, raw_path, norm_path, Path(meta_path), pdf_path, input_dir)
                        )
                except Exception as exc:
                    log.debug("No se pudo actualizar índice para %s: %s", futures.get(future), exc)
                if result.get("skipped"):
                    skipped_success += 1

    _run_batch(to_process, threads, wrap_progress)
    cancelled = cancel_event is not None and cancel_event.is_set()

    # Reproceso automático de errores temporales: 503, 429, timeout y problemas de red.
    # No incrementa el contador global de progreso para no superar el 100%; solo actualiza log y estado.
    def retry_progress(payload: dict) -> None:
        stage = payload.get("stage")
        new_stage = {
            "done_file": "retry_done_file",
            "error_file": "retry_error_file",
            "start_file": "retry_start_file",
            "extract": "retry_extract",
            "ai_detail": "retry_ai_detail",
        }.get(stage, stage)
        payload = {**payload, "stage": new_stage, "percent": min(99, int((completed / len(pdf_files)) * 100) if pdf_files else 0)}
        _emit(progress_cb, **payload)

    retry_rounds_done = 0
    for retry_round, retry_workers, wait_seconds in [(1, min(2, threads), 45), (2, 1, 90)]:
        if cancel_event is not None and cancel_event.is_set():
            break
        temp_errors = _temporary_errors_from_state(state_dir)
        retry_items: list[tuple[int, Path]] = []
        for m in temp_errors:
            pdf = _pdf_from_meta(m, input_dir)
            if pdf:
                retry_items.append((int(m.get("retry_idx") or len(retry_items) + 1), pdf))
        if not retry_items:
            break
        retry_rounds_done += 1
        _emit(
            progress_cb,
            stage="retry_wait",
            message=f"Errores temporales detectados: {len(retry_items)}. Reintento automático {retry_round}/2 en {wait_seconds}s con {retry_workers} hilo(s).",
            percent=min(99, int((completed / len(pdf_files)) * 100) if pdf_files else 0),
            total=len(pdf_files),
            current=completed,
        )
        # Espera cancelable y pausible
        slept = 0
        while slept < wait_seconds:
            if cancel_event is not None and cancel_event.is_set():
                break
            if pause_event is not None and pause_event.is_set():
                _wait_if_paused_or_cancelled(pause_event, cancel_event, progress_cb, "", "")
            time.sleep(1)
            slept += 1
        if cancel_event is not None and cancel_event.is_set():
            break
        _emit(
            progress_cb,
            stage="retry_start",
            message=f"Reprocesando {len(retry_items)} errores temporales en modo seguro.",
            percent=min(99, int((completed / len(pdf_files)) * 100) if pdf_files else 0),
        )
        _run_batch(retry_items, retry_workers, retry_progress)

    retry_queue = _write_retry_outputs(_resolve_retry_queue_path(out_dir).parent, state_dir)

    if build_exports:
        summary = (
            _collect_outputs_fast(pdf_files, input_dir, cache_index_path, out_dir, ai_config, reference_csv=reference_csv)
            if (resume_fast and index_available)
            else _collect_outputs(pdf_files, input_dir, raw_dir, norm_dir, state_dir, out_dir, ai_config, reference_csv=reference_csv)
        )
    else:
        summary = _collect_extraction_summary(pdf_files, input_dir, raw_dir, state_dir)
    summary.threads_used = threads
    summary.output_dir = str(out_dir)
    summary.skipped_success = skipped_success
    summary.total_cost_estimated_usd = round(summary.total_cost_estimated_usd, 6)
    secs = []
    rows_for_avg = (
        [_try_get_entry(cache_index_path, _quick_file_info(p, input_dir)["ruta_relativa"]) for p in pdf_files] if index_available else []
    )
    for row in rows_for_avg:
        try:
            if row and row.get("meta_json") and Path(row["meta_json"]).exists():
                meta = _read_json(Path(row["meta_json"]))
                if meta.get("status") == "success" and meta.get("seconds"):
                    secs.append(float(meta["seconds"]))
        except Exception:
            pass
    summary.avg_seconds_per_pdf = round(sum(secs) / len(secs), 2) if secs else 0.0

    manifest = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "version": APP_VERSION,
        "total": summary.total,
        "success": summary.success,
        "errors": summary.errors,
        "hito": 1 if not build_exports else "1+2_compatibilidad",
        "resultado_funcional": str(raw_dir),
        "entregables_consolidados_generados": build_exports,
        "skipped_success": summary.skipped_success,
        "threads_used": summary.threads_used,
        "provider": ai_config.provider,
        "model": ai_config.model,
        "esquema_salida_ia": COMPACT_WIRE_FORMAT,
        "version_esquema_salida_ia": COMPACT_SCHEMA_VERSION,
        "mode": "pdf_directo_ia",
        "resume_fast": resume_fast,
        "cache_index": str(cache_index_path),
        "nota": f"{AI_RESPONSE_DIRNAME} guarda la respuesta estructurada de IA; no es JSON OCR tipo Azure.",
        "total_prompt_tokens": summary.total_prompt_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "total_tokens": summary.total_tokens,
        "total_cost_estimated_usd": summary.total_cost_estimated_usd,
        "avg_seconds_per_pdf": summary.avg_seconds_per_pdf,
        "retry_rounds_done": retry_rounds_done,
        "cancelled": cancelled,
        "estado_ejecucion": "DETENIDO_POR_USUARIO" if cancelled else "FINALIZADO",
        "errores_reprocesables": len(retry_queue),
        "cola_reproceso_json": str(_resolve_retry_queue_path(out_dir)),
        "cola_reproceso_csv": str(_resolve_retry_queue_csv_path(out_dir)),
    }
    _safe_write_json(_resolve_run_summary_path(out_dir), manifest)
    log.info(
        "Finalizado. Cancelled=%s Total=%d OK=%d Errores=%d Revisar=%d Tokens=%d CostoUSD=%s",
        cancelled,
        summary.total,
        summary.success,
        summary.errors,
        summary.revisar,
        summary.total_tokens,
        summary.total_cost_estimated_usd,
    )
    _close_log_handler(fh)
    final_label = "Proceso detenido y guardado para retomar" if cancelled else "Finalizado"
    _emit(
        progress_cb,
        stage="finished",
        message=f"{final_label}. OK={summary.success}, Errores={summary.errors}, Revisar={summary.revisar}, Costo USD={summary.total_cost_estimated_usd}. Salida: {summary.output_dir}",
        percent=100,
    )
    return summary


def process_folder(
    folder_path: str,
    ai_config: AIConfig,
    progress_cb: ProgressCallback = None,
    threads: int = 1,
    output_dir: str | None = None,
    resume_fast: bool = True,
    rebuild_index: bool = False,
    skip_cache_validation: bool = False,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    reference_csv: str = "",
    build_exports: bool = False,
) -> ProcessingSummary:
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    try:
        return _process_folder_impl(
            folder_path,
            ai_config,
            progress_cb=progress_cb,
            threads=threads,
            output_dir=output_dir,
            resume_fast=resume_fast,
            rebuild_index=rebuild_index,
            skip_cache_validation=skip_cache_validation,
            pause_event=pause_event,
            cancel_event=cancel_event,
            reference_csv=reference_csv,
            build_exports=build_exports,
        )
    finally:
        _close_log_handlers_for_path(out_dir / "process.log")
        _close_log_handlers_for_path(out_dir / INTERNAL_FILES_DIRNAME / "process.log")


def reprocess_temporary_errors(
    output_dir: str,
    folder_path: str,
    ai_config: AIConfig,
    progress_cb: ProgressCallback = None,
    threads: int = 1,
    reference_csv: str = "",
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
) -> ProcessingSummary:
    """Reprocesa errores recuperables registrados en cola_reproceso.json/estado_documentos.

    Incluye fallos temporales de red/API y respuestas JSON que requieren una nueva generación.
    No toca archivos ya exitosos.
    """
    from core.ai import validate_reader_config
    validate_reader_config(ai_config)
    out_dir = Path(output_dir)
    input_dir = Path(folder_path)
    if not out_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de resultados: {out_dir}")
    if not input_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de PDFs: {input_dir}")

    cache_root = _resolve_cache_root(out_dir)
    raw_dir = _resolve_ai_response_dir(cache_root)
    norm_dir = _resolve_normalized_dir(cache_root)
    state_dir = _resolve_state_dir(out_dir)
    cache_index_path = cache_root / "cache_index.sqlite"
    _try_init_index(cache_index_path)
    for d in [raw_dir, state_dir, cache_index_path.parent]:
        d.mkdir(parents=True, exist_ok=True)
    internal_dir = out_dir / INTERNAL_FILES_DIRNAME
    log_jsonl = internal_dir / "process.jsonl"
    provider_max = safe_max_threads(ai_config.provider)
    workers = max(1, min(int(threads), min(2, provider_max)))
    temp_errors = _reprocessable_errors_from_state(state_dir)
    items: list[tuple[int, Path]] = []
    for idx, meta in enumerate(temp_errors, start=1):
        pdf = _pdf_from_meta(meta, input_dir)
        if pdf:
            items.append((idx, pdf))

    _emit(
        progress_cb,
        stage="retry_manual_scan",
        message=f"Errores reprocesables encontrados: {len(items)}",
        percent=0,
        total=len(items),
        current=0,
    )

    if not items:
        _emit(
            progress_cb,
            stage="finished",
            message="No se encontraron errores reprocesables pendientes en este lote.",
            percent=100,
        )
        pdf_files = sorted(input_dir.rglob("*.pdf"))
        summary = _collect_extraction_summary(pdf_files, input_dir, raw_dir, state_dir)
        summary.threads_used = workers
        summary.output_dir = str(out_dir)
        return summary

    from core.ai import validate_remote_model
    if not (cancel_event and cancel_event.is_set()):
        _emit(progress_cb, stage="preflight", message="Comprobando modelo antes de reprocesar errores…", percent=0)
        validate_remote_model(ai_config)
    completed = 0
    lock = threading.Lock()

    def wrap(payload: dict) -> None:
        nonlocal completed
        if payload.get("stage") in {"done_file", "error_file", "cancelled_file"}:
            with lock:
                completed += 1
                pct = int((completed / len(items)) * 100) if items else 100
            payload = {**payload, "percent": pct, "completed": completed}
        _emit(progress_cb, **payload)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _process_single_pdf,
                pdf_path,
                input_dir,
                idx,
                len(items),
                ai_config,
                raw_dir,
                norm_dir,
                state_dir,
                wrap,
                log_jsonl,
                cancel_event=cancel_event,
                pause_event=pause_event,
                normalize_output=False,
            ): pdf_path
            for idx, pdf_path in items
        }
        for future in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                for f in futures:
                    if not f.done():
                        f.cancel()
                break
            result = future.result()
            meta_path = result.get("meta")
            if meta_path:
                try:
                    meta = _read_json(Path(meta_path))
                    cache_stem = meta.get("cache_stem")
                    pdf_path = futures[future]
                    raw_path = raw_dir / f"{cache_stem}.json" if cache_stem else None
                    norm_path = norm_dir / f"{cache_stem}.normalizado.json" if cache_stem else None
                    _try_upsert_entry(
                        cache_index_path, _index_entry_from_meta(meta, raw_path, norm_path, Path(meta_path), pdf_path, input_dir)
                    )
                except Exception as exc:
                    log.debug("No se pudo actualizar índice en reproceso para %s: %s", futures.get(future), exc)

    retry_queue = _write_retry_outputs(_resolve_retry_queue_path(out_dir).parent, state_dir)
    pdf_files = sorted(input_dir.rglob("*.pdf"))
    summary = _collect_extraction_summary(pdf_files, input_dir, raw_dir, state_dir)
    summary.threads_used = workers
    summary.output_dir = str(out_dir)
    manifest_path = internal_dir / "resumen_reproceso_errores.json"
    _safe_write_json(
        manifest_path,
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "version": APP_VERSION,
            "modo": "reprocess_temporary_errors",
            "input_dir": str(input_dir),
            "output_dir": str(out_dir),
            "errores_reprocesables_iniciales": len(items),
            "errores_reprocesables_restantes": len(retry_queue),
            "threads_used": workers,
            "provider": ai_config.provider,
            "model": ai_config.model,
        },
    )
    _emit(
        progress_cb,
        stage="finished",
        message=f"Reproceso de errores finalizado. Errores reprocesables restantes: {len(retry_queue)}",
        percent=100,
    )
    return summary










def reprocess_ai_cache(cache_or_output_dir: str, output_dir: str | None = None, reference_csv: str = "", *, state_dir: str | None = None) -> ProcessingSummary:
    """Hito 2: normaliza ``respuestas_ia`` y crea entregables sin llamar a la IA.

    Los normalizados se calculan en memoria porque son resultados derivados. No se
    crean miles de ``*.normalizado.json`` ni metadatos duplicados por documento.
    """
    base = Path(cache_or_output_dir)
    _source_cache_root, raw_dir = _resolve_ai_reprocess_source(base)
    out_dir = Path(output_dir) if output_dir else base
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(raw_dir.glob("*.json"))
    if state_dir is not None:
        states = Path(state_dir)
        raw_files = [path for path in raw_files if (states / f"{path.stem}.meta.json").is_file() and _read_json(states / f"{path.stem}.meta.json").get("status") == "success"]
    # Colector especifico para respuestas IA: no depende del hash ni del PDF original.
    summary = ProcessingSummary(total=len(raw_files))
    archivo_rows = []
    control_rows = []
    normalizados = []
    sairc_rows = []
    pendientes = []
    raw_rows = []
    costos_rows = []
    error_rows = []
    for raw_path in raw_files:
        raw = normalize_cached_lab_json(_read_json(raw_path))
        source = raw.get("_source") or {}
        rel = source.get("ruta_relativa") or raw_path.name.replace(".json", ".pdf")
        carpeta = source.get("carpeta_origen") or str(Path(rel).parent).replace(".", "") or base.name
        norm = normalize_ai_output(raw, ruta_relativa=rel, carpeta_origen=carpeta)
        meta = {
            "filename": Path(rel).name,
            "ruta_relativa": rel,
            "carpeta_origen": carpeta,
            "cache_stem": raw_path.stem,
            "status": "success",
            "mode": "hito_2_desde_respuestas_ia",
            "provider": (raw.get("_meta") or {}).get("provider"),
            "model": (raw.get("_meta") or {}).get("model"),
            "seconds": 0,
            "rows": len(raw.get("resultados") or []),
        }
        archivo_rows.append(_row_archivo_from_meta(meta, raw, norm))
        cab = norm.get("cabecera") or {}
        control_rows.append(cab)
        sairc_rows.append(norm.get("sairc") or {})
        if str(cab.get("estado_archivo") or "").upper() in {"OK", "OK_CON_REGLA", "OK_CARGABLE", "OK_CON_ALERTA_CLINICA"}:
            summary.ok += 1
        else:
            summary.revisar += 1
        summary.success += 1
        usage = _token_usage(raw or {})
        summary.total_cost_estimated_usd += float(usage.get("cost_estimated_usd") or 0.0)
        summary.total_prompt_tokens += int(usage.get("prompt_token_count") or usage.get("estimated_input_tokens") or 0)
        summary.total_output_tokens += int(usage.get("candidates_token_count") or 0)
        summary.total_tokens += int(usage.get("total_token_count") or 0)
        for r in norm.get("resultados_normalizados") or []:
            normalizados.append(
                {
                    **{
                        k: cab.get(k)
                        for k in [
                            "ruta_relativa",
                            "paciente",
                            "documento_archivo_pdf",
                            "documento_identidad",
                            "coincidencia_documento",
                            "estado_identidad",
                            "puede_cargarse_sairc",
                            "laboratorio",
                            "edad",
                            "sexo",
                            "fecha_examen",
                            "fecha_toma_muestra",
                            "fecha_emision",
                            "firma",
                        ]
                    },
                    **r,
                }
            )
        pendientes.extend(norm.get("pendientes") or [])
        raw_rows.append(
            {
                "ruta_relativa": cab.get("ruta_relativa"),
                "respuesta_ia_json": raw_path.name,
                "resultados_extraidos_ia": len(raw.get("resultados") or []),
            }
        )
        costos_rows.append(
            {
                "ruta_relativa": cab.get("ruta_relativa"),
                "total_token_count": usage.get("total_token_count"),
                "costo_estimado_usd": usage.get("cost_estimated_usd"),
            }
        )
    resumen_rows = [
        {
            "version": APP_VERSION,
            "modo": "hito_2_desde_respuestas_ia",
            "total_respuestas_ia": len(raw_files),
            "procesados_ok": summary.success,
            "archivos_revisar": summary.revisar,
            "pendientes_revision": len(pendientes),
            "input_tokens": summary.total_prompt_tokens,
            "output_tokens": summary.total_output_tokens,
            "total_tokens": summary.total_tokens,
            "costo_estimado_usd": round(summary.total_cost_estimated_usd, 6),
        }
    ]
    if reference_csv:
        compare_and_update(reference_csv, archivo_rows, control_rows, sairc_rows)
    summary_path = _resolve_run_summary_path(out_dir)
    export_state = {"hito": 2, "estado_ejecucion": "CONSTRUYENDO_ENTREGABLES", "output_dir": str(out_dir)}
    _safe_write_json(summary_path, export_state)
    try:
        summary.excel_path = str(_write_excel(
            out_dir, resumen_rows, control_rows, normalizados, sairc_rows, archivo_rows, pendientes, raw_rows, costos_rows, error_rows
        ))
        _write_csv(out_dir / "resultados_normalizados.csv", normalizados)
        _write_sairc_csvs(out_dir, sairc_rows)
        _write_csv(out_dir / "pendientes_revision.csv", pendientes)
    except Exception as exc:
        export_state.update(estado_ejecucion="EXPORTACION_INCOMPLETA", excel_path=summary.excel_path, error=str(exc))
        _safe_write_json(summary_path, export_state)
        raise RuntimeError(f"Exportación incompleta del Hito 2 en {out_dir}: {exc}") from exc
    summary.total_cost_estimated_usd = round(summary.total_cost_estimated_usd, 6)
    _safe_write_json(
        _resolve_run_summary_path(out_dir),
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "version": APP_VERSION,
            "hito": 2,
            "modo": "normalizacion_y_consolidacion_desde_respuestas_ia",
            "input_dir": str(raw_dir),
            "output_dir": str(out_dir),
            "respuestas_ia_origen": str(raw_dir),
            "normalizacion": "EN_MEMORIA_NO_PERSISTIDA_POR_PDF",
            "total_respuestas_ia": len(raw_files),
            "procesados_ok": summary.success,
            "archivos_revisar": summary.revisar,
            "pendientes_revision": len(pendientes),
            "total_tokens": summary.total_tokens,
            "total_cost_estimated_usd": summary.total_cost_estimated_usd,
            "estado_ejecucion": "REPROCESADO_DESDE_CACHE_IA",
            "excel_path": summary.excel_path,
        },
    )
    summary.output_dir = str(out_dir)
    return summary

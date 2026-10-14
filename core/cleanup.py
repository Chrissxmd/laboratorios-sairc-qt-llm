from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from core.config import (
    CACHE_DIRNAME,
    DOCUMENT_STATE_DIRNAME,
    INTERNAL_FILES_DIRNAME,
    LEGACY_CACHE_DIRNAME,
    LEGACY_DOCUMENT_STATE_DIRNAME,
    LEGACY_RETRY_QUEUE_CSV_FILENAME,
    LEGACY_RETRY_QUEUE_FILENAME,
    LEGACY_RUN_SUMMARY_FILENAME,
    RETRY_QUEUE_CSV_FILENAME,
    RETRY_QUEUE_FILENAME,
    RUN_SUMMARY_FILENAME,
)


@dataclass
class CleanupSummary:
    output_dir: str
    dry_run: bool = True
    deleted: int = 0
    candidates: int = 0
    errors: int = 0
    paths: list[str] | None = None
    error_messages: list[str] | None = None


def sensitive_output_candidates(output_dir: Path, include_exports: bool = False) -> list[Path]:
    candidates: list[Path] = []
    fixed_names = [
        CACHE_DIRNAME,
        LEGACY_CACHE_DIRNAME,
        DOCUMENT_STATE_DIRNAME,
        LEGACY_DOCUMENT_STATE_DIRNAME,
        INTERNAL_FILES_DIRNAME,
        "Textos_Markdown",
        "process.log",
        "process.jsonl",
        RETRY_QUEUE_FILENAME,
        LEGACY_RETRY_QUEUE_FILENAME,
        RETRY_QUEUE_CSV_FILENAME,
        LEGACY_RETRY_QUEUE_CSV_FILENAME,
    ]
    for name in fixed_names:
        p = output_dir / name
        if p.exists() and p not in candidates:
            candidates.append(p)
    for name in [RUN_SUMMARY_FILENAME, LEGACY_RUN_SUMMARY_FILENAME, "manifest_reproceso_errores.json", "resumen_reproceso_errores.json"]:
        p = output_dir / name
        if p.exists() and p not in candidates:
            candidates.append(p)
    if include_exports:
        for pattern in ["*.csv", "*.xlsx", "*.xlsm"]:
            for p in output_dir.rglob(pattern):
                covered_by_directory = any(candidate.is_dir() and candidate in p.parents for candidate in candidates)
                if p.exists() and p not in candidates and not covered_by_directory:
                    candidates.append(p)
    return sorted(candidates, key=lambda p: str(p).lower())


def cleanup_sensitive_outputs(output_dir: str, *, dry_run: bool = True, include_exports: bool = False) -> CleanupSummary:
    out_dir = Path(output_dir)
    if not out_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de resultados: {out_dir}")
    candidates = sensitive_output_candidates(out_dir, include_exports=include_exports)
    summary = CleanupSummary(
        output_dir=str(out_dir),
        dry_run=dry_run,
        candidates=len(candidates),
        paths=[str(p) for p in candidates],
        error_messages=[],
    )
    if dry_run:
        return summary
    for p in candidates:
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            summary.deleted += 1
        except Exception as exc:
            summary.errors += 1
            summary.error_messages = summary.error_messages or []
            summary.error_messages.append(f"{p}: {exc}")
    return summary

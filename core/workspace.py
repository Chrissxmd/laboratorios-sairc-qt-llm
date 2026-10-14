from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path

from core.config import HITO_1_DIRNAME, HITO_2_DIRNAME, HITO_3_DIRNAME, HITO_4_DIRNAME, INTERNAL_FILES_DIRNAME, RUN_SUMMARY_FILENAME


@dataclass(frozen=True)
class HitoPaths:
    root: Path
    hito1: Path
    hito2: Path
    hito3: Path
    hito4: Path


def result_workspace_for_input(results_parent: str | Path, input_dir: str | Path) -> Path:
    """Deriva ``NOMBRE_RESULTADOS`` sin duplicarlo si ya se eligió esa raíz."""
    parent = Path(results_parent).expanduser()
    input_name = Path(input_dir).expanduser().name.strip()
    if not input_name:
        return parent
    safe_name = re.sub(r'[<>:"/\\|?*]+', "_", input_name).strip(" ._") or "PROCESO"
    workspace_name = safe_name if safe_name.upper().endswith("_RESULTADOS") else f"{safe_name}_RESULTADOS"
    if parent.name.casefold() == workspace_name.casefold():
        return parent
    return parent / workspace_name


def get_hito_paths(workspace_root: str | Path) -> HitoPaths:
    root = Path(workspace_root).expanduser()
    return HitoPaths(
        root=root,
        hito1=root / HITO_1_DIRNAME,
        hito2=root / HITO_2_DIRNAME,
        hito3=root / HITO_3_DIRNAME,
        hito4=root / HITO_4_DIRNAME,
    )


def _latest_file(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def find_hito2_excel(workspace_root: str | Path) -> Path | None:
    """Localiza primero la salida estándar y después resultados históricos."""
    paths = get_hito_paths(workspace_root)
    summary_path = paths.hito2 / INTERNAL_FILES_DIRNAME / RUN_SUMMARY_FILENAME
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(summary, dict):
            return None
        if summary.get("estado_ejecucion") in {"CONSTRUYENDO_ENTREGABLES", "EXPORTACION_INCOMPLETA"}:
            return None
        if summary.get("excel_path"):
            if not isinstance(summary["excel_path"], str):
                return None
            candidate = Path(summary["excel_path"]).resolve()
            if candidate.parent == paths.hito2.resolve() and candidate.name.startswith("resultados_laboratorio_sairc") and candidate.suffix == ".xlsx":
                return candidate if candidate.is_file() else None
            return None
    standard = paths.hito2 / "resultados_laboratorio_sairc.xlsx"
    if standard.is_file():
        return standard
    legacy_direct = paths.root / "resultados_laboratorio_sairc.xlsx"
    if legacy_direct.is_file():
        return legacy_direct
    candidates = [
        candidate
        for candidate in paths.root.glob("HITO_2*/resultados_laboratorio_sairc*.xlsx")
        if candidate.is_file()
    ]
    return _latest_file(candidates)


def find_hito3_reference(workspace_root: str | Path) -> Path | None:
    """Localiza la referencia SAIRC estándar o la histórica más reciente."""
    paths = get_hito_paths(workspace_root)
    standard = sorted(paths.hito3.glob("Referencia_SAIRC_*.csv")) if paths.hito3.is_dir() else []
    latest = _latest_file(standard)
    if latest:
        return latest
    legacy_direct = list(paths.root.glob("Referencia_SAIRC_*.csv"))
    latest = _latest_file(legacy_direct)
    if latest:
        return latest
    historical = [
        candidate
        for candidate in paths.root.glob("HITO_2*/Referencia_SAIRC_*.csv")
        if candidate.is_file()
    ]
    return _latest_file(historical)

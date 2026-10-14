from pathlib import Path

from core.workspace import find_hito2_excel, find_hito3_reference, get_hito_paths, result_workspace_for_input


def test_result_workspace_uses_input_folder_name(tmp_path):
    assert result_workspace_for_input(tmp_path, "D:/Reportes/TEST") == tmp_path / "TEST_RESULTADOS"


def test_result_workspace_does_not_duplicate_existing_named_root(tmp_path):
    selected = tmp_path / "TEST_RESULTADOS"
    assert result_workspace_for_input(selected, "D:/Reportes/TEST") == selected


def test_result_workspace_sanitizes_windows_invalid_characters(tmp_path):
    assert result_workspace_for_input(tmp_path, "D:/Reportes/TEST:LOTE") == tmp_path / "TEST_LOTE_RESULTADOS"


def test_hito_paths_use_separate_standard_directories(tmp_path):
    paths = get_hito_paths(tmp_path)

    assert paths.root == tmp_path
    assert paths.hito1 == tmp_path / "HITO_1_EXTRACCION"
    assert paths.hito2 == tmp_path / "HITO_2_RESULTADOS_SAIRC"
    assert paths.hito3 == tmp_path / "HITO_3_REFERENCIA_SAIRC"
    assert paths.hito4 == tmp_path / "HITO_4_VALIDACION"


def test_standard_hito2_result_has_priority_over_legacy_result(tmp_path):
    standard = tmp_path / "HITO_2_RESULTADOS_SAIRC" / "resultados_laboratorio_sairc.xlsx"
    legacy = tmp_path / "resultados_laboratorio_sairc.xlsx"
    standard.parent.mkdir()
    standard.write_bytes(b"standard")
    legacy.write_bytes(b"legacy")

    assert find_hito2_excel(tmp_path) == standard


def test_hito2_historical_named_directory_is_detected(tmp_path):
    historical = tmp_path / "HITO_2_SAIRC_MEJORADO_2026_08_10" / "resultados_laboratorio_sairc.xlsx"
    historical.parent.mkdir()
    historical.write_bytes(b"historical")

    assert find_hito2_excel(tmp_path) == historical


def test_hito3_returns_latest_reference_in_standard_directory(tmp_path):
    hito3 = tmp_path / "HITO_3_REFERENCIA_SAIRC"
    hito3.mkdir()
    first = hito3 / "Referencia_SAIRC_2026_7_20260810_090000.csv"
    latest = hito3 / "Referencia_SAIRC_2026_7_20260810_100000.csv"
    first.write_text("first", encoding="utf-8")
    latest.write_text("latest", encoding="utf-8")
    first.touch()
    latest.touch()
    first_mtime = first.stat().st_mtime
    latest_mtime = first_mtime + 10
    Path(latest).touch()
    import os
    os.utime(latest, (latest_mtime, latest_mtime))

    assert find_hito3_reference(tmp_path) == latest


def test_hito3_historical_reference_in_hito2_is_detected(tmp_path):
    historical = tmp_path / "HITO_2_SAIRC_MEJORADO" / "Referencia_SAIRC_2026_7.csv"
    historical.parent.mkdir()
    historical.write_text("legacy", encoding="utf-8")

    assert find_hito3_reference(tmp_path) == historical

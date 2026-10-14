import pandas as pd
import pytest

from core.cleanup import cleanup_sensitive_outputs, sensitive_output_candidates
from core import db_extractor


def test_cleanup_removes_markdown_internal_data_and_exports(tmp_path):
    markdown = tmp_path / "Textos_Markdown"
    internal = tmp_path / "_Archivos_Internos"
    markdown.mkdir()
    internal.mkdir()
    (markdown / "patient.md").write_text("dato sintético", encoding="utf-8")
    (internal / "process.log").write_text("log", encoding="utf-8")
    export = tmp_path / "resultado.xlsx"
    export.write_bytes(b"synthetic")

    candidates = sensitive_output_candidates(tmp_path, include_exports=True)
    assert markdown in candidates
    assert internal in candidates
    assert export in candidates

    summary = cleanup_sensitive_outputs(str(tmp_path), dry_run=False, include_exports=True)
    assert summary.errors == 0
    assert not markdown.exists()
    assert not internal.exists()
    assert not export.exists()


def test_sql_inputs_are_validated_before_connecting(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="enteros válidos"):
        db_extractor.generar_referencia_sairc_sql(2026, 6, "1; SELECT 1", str(tmp_path))
    with pytest.raises(ValueError, match="mes"):
        db_extractor.generar_referencia_sairc_sql(2026, 13, None, str(tmp_path))


def test_sql_query_uses_bound_parameters(tmp_path, monkeypatch):
    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            captured["disposed"] = True

    def fake_read_sql(query, connection, params):
        captured["query"] = str(query)
        captured["params"] = params
        return pd.DataFrame([{"Num Doc.": "00000000"}])

    monkeypatch.setattr(db_extractor, "create_engine", lambda _url: FakeEngine())
    monkeypatch.setattr(db_extractor, "construir_sqlalchemy_url", lambda: "mssql+pyodbc://fake")
    monkeypatch.setattr(db_extractor.pd, "read_sql", fake_read_sql)

    output = db_extractor.generar_referencia_sairc_sql(2026, 6, "10806", str(tmp_path))
    assert captured["params"] == {"anio": 2026, "mes": 6, "establecimiento_id": 10806}
    assert ":establecimiento_id" in captured["query"]
    assert captured["disposed"] is True
    assert output.endswith(".csv")


def test_config_and_sample_are_gitignored():
    # La política se comprueba sin leer ni exponer el contenido real de sample.json.
    gitignore = (db_extractor.obtener_base_dir() / ".gitignore").read_text(encoding="utf-8")
    assert "config.yaml" in gitignore
    assert "sample.json" in gitignore

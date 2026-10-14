"""Audita entorno de ejecución y, si existe, manifiesto de empaquetado."""
import ast
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--executable", default="dist/10.0.7/AuditoriaSAIRC.exe")
args = parser.parse_args()
forbidden = ["docling", "flet", "fitz", "PIL", "torch", "transformers", "pytesseract", "easyocr", "paddleocr"]
installed = {name: importlib.util.find_spec(name) is not None for name in forbidden}
versions = {name: importlib.metadata.version(name) for name in ["PySide6", "openpyxl", "pandas", "SQLAlchemy", "pyodbc", "PyYAML"]}
toc = root / "build/AuditoriaSAIRC/Analysis-00.toc"
package_forbidden = []
external_binaries = []
if toc.is_file():
    entries = ast.literal_eval(toc.read_text(encoding="utf-8"))
    def audit(value):
        if isinstance(value, (tuple, list)):
            if len(value) == 3 and isinstance(value[0], str) and value[2] in {"PYMODULE", "PYSOURCE", "DATA", "BINARY", "EXTENSION"}:
                name = value[0].lower().replace("\\", "/")
                if any(name == item.lower() or name.startswith(item.lower() + ".") or name.startswith(item.lower() + "/") for item in forbidden + ["pytest", "_pytest", "PyInstaller"]):
                    package_forbidden.append(value[0])
            else:
                for item in value:
                    audit(item)
    audit(entries)
package_toc = root / "build/AuditoriaSAIRC/PKG-00.toc"
if package_toc.is_file():
    permitted = [root / ".venv", Path(sys.base_prefix), Path(os.environ.get("WINDIR", "C:/Windows"))]
    def audit_binaries(value):
        if isinstance(value, (tuple, list)):
            if len(value) == 3 and isinstance(value[0], str) and value[2] in {"BINARY", "EXTENSION"}:
                source = Path(value[1]).resolve()
                if not any(source.is_relative_to(base.resolve()) for base in permitted):
                    external_binaries.append(value[0])
            else:
                for item in value:
                    audit_binaries(item)
    audit_binaries(ast.literal_eval(package_toc.read_text(encoding="utf-8")))
origin = json.loads((root / "ORIGEN_CODIGO.json").read_text(encoding="utf-8"))
original_changed = []
if (root.parent / "main.py").is_file():
    original_changed = [relative for relative, digest in origin["sha256"].items() if hashlib.sha256((root.parent / relative).read_bytes()).hexdigest() != digest]
executable = root / args.executable
report = {"entorno": versions, "dependencias_excluidas_presentes": installed, "modulos_prohibidos_en_paquete": package_forbidden, "dll_externas_al_entorno": external_binaries, "originales_modificados": original_changed, "paquete_auditado": toc.is_file() and package_toc.is_file()}
if executable.is_file():
    report["ejecutable"] = {"archivo": executable.relative_to(root).as_posix(), "bytes": executable.stat().st_size, "sha256": hashlib.sha256(executable.read_bytes()).hexdigest()}
destination = root / "VERIFICACION.json"
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(1 if any(installed.values()) or package_forbidden or external_binaries or original_changed else 0)

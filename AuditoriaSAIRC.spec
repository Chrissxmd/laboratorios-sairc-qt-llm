# No se incluyen credenciales, PDF del usuario, resultados ni entornos virtuales.
from pathlib import Path
import os
import importlib.util
import sys

base = Path(SPECPATH)
# No recoger DLL de Poppler u otras aplicaciones añadidas al PATH del equipo.
# Qt usa ICU de Windows; una icuuc.dll externa puede tener símbolos incompatibles.
windows_directory = Path(os.environ.get("WINDIR", "C:/Windows"))
os.environ["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(Path(sys.base_prefix)), str(windows_directory / "System32"), str(windows_directory)])
analysis = Analysis(
    [str(base / "main_qt.py")],
    pathex=[str(base)],
    datas=[(str(base / "diccionario_laboratorios.json"), "."),
           (str(base / "config.example.yaml"), "."),
           (str(base / "sql/consulta_sairc.sql"), "sql"),
           (str(base / "core/ai.py"), "core")],
    hiddenimports=[],
    excludes=["flet", "docling", "torch", "transformers", "fitz", "PIL", "pytesseract",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "matplotlib", "scipy",
              "pytest", "_pytest", "py", "pygments", "ruff", "PyInstaller", "pandas.tests",
              "numpy.tests", "IPython", "notebook", "jupyter", "jinja2"],
    noarchive=False,
)
# Qt 6.11 incluye un runtime MSVC más reciente que Python 3.11. El cargador
# inicia Python antes de Qt; debe usar ese runtime también en la raíz del paquete.
qt_directory = Path(importlib.util.find_spec("PySide6").origin).parent
for runtime_name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_codecvt_ids.dll", "concrt140.dll"):
    runtime = qt_directory / runtime_name
    if runtime.is_file():
        analysis.binaries = [entry for entry in analysis.binaries if entry[0].casefold() != runtime_name]
        analysis.binaries.append((runtime_name, str(runtime), "BINARY"))
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, analysis.binaries, analysis.datas,
                 name="AuditoriaSAIRC_debug" if os.environ.get("SAIRC_BUILD_DEBUG") == "1" else "AuditoriaSAIRC",
                 console=os.environ.get("SAIRC_BUILD_DEBUG") == "1", upx=False)

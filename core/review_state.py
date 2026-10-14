"""Decisiones locales de revisión: fuentes inmutables e historial transaccional."""
import getpass
import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from core.persistence import write_json_atomic

CHOICES = ("Confirma Hito 2", "Confirma Hito 3", "Otro valor del PDF", "No concluyente")
RESOLVED = CHOICES[:3]
PRIORITIES = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3}
COMPARISON_RULES = "hito4_10_0_7"  # Incrementar al cambiar reglas de comparación.


def digest(path):
    path = Path(path)
    if not path.is_file():
        return "NO_DISPONIBLE"
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def file_stamp(path):
    path = Path(path)
    return (path.stat().st_size, path.stat().st_mtime_ns) if path.is_file() else None


def write_review_sources(report, excel, reference, fields, pdf_sources=None):
    sources = {str(Path(path).resolve()): digest(path) for path in (excel, reference)}
    write_json_atomic(Path(report).with_suffix(".fuentes.json"), {"schema": 1, "rules": COMPARISON_RULES, "report_sha256": digest(report), "sources": sources, "fields": fields, "pdf_sources": pdf_sources or {}})


def prepare_findings(rows, report=None):
    """Se ejecuta al cargar el reporte, fuera del hilo gráfico para archivos grandes."""
    sources, coverage, warnings, originals = {}, [], [], {}
    if report:
        report = Path(report).resolve()
        manifest = report.with_suffix(".fuentes.json")
        if manifest.is_file():
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            coverage = metadata.get("fields", [])
            originals = {os.path.normcase(str(Path(path))): value for path, value in metadata.get("pdf_sources", {}).items()}
            if metadata.get("rules") != COMPARISON_RULES:
                warnings.append("Las reglas cambiaron: vuelve a comparar.")
            if metadata.get("report_sha256") != digest(report):
                warnings.append("El reporte cambió desde su comparación.")
            for path, expected in metadata.get("sources", {}).items():
                actual = digest(path)
                sources[path] = actual
                if actual != expected:
                    warnings.append("Una fuente o las reglas cambiaron: vuelve a comparar antes de confirmar.")
        sources[str(report)] = digest(report)
    version = fingerprint([sources, COMPARISON_RULES]) if report else "TEMPORAL"
    watch = {path: file_stamp(path) for path in sources}
    pdf_digests, pdf_watch, source_digests, source_stamps = {}, {}, {}, {}
    for row in rows:
        path = str(row.get("_pdf_path") or "")
        if path and path not in pdf_digests:
            pdf_watch[path] = {**watch, path: file_stamp(path)}
            pdf_digests[path] = digest(path)
        original = originals.get(os.path.normcase(str(Path(path))), {})
        original_path = original.get("path")
        if original_path and original_path not in source_digests:
            source_stamps[original_path] = file_stamp(original_path)
            source_digests[original_path] = digest(original_path)
        if original_path:
            pdf_watch[path][original_path] = source_stamps[original_path]
        row["_version"] = version
        row["_watch"] = pdf_watch.get(path, watch)
        row["_coverage"] = coverage
        row["_warning"] = " ".join(dict.fromkeys(warnings))
        if original_path and (source_digests[original_path] != original.get("sha256") or pdf_digests.get(path) != original.get("sha256")):
            row["_warning"] += " El PDF original o su copia cambiaron: vuelve a comparar."
        row["_report"] = str(report or "")
        row["_id"] = fingerprint({"data": {k: v for k, v in row.items() if not k.startswith("_")}, "pdf": pdf_digests.get(path, "NO_DISPONIBLE"), "original": source_digests.get(original_path)})
    return rows


def case_key(row):
    relative = str(row.get("Ruta_relativa") or row.get("_pdf_path") or "").replace("\\", "/").casefold()
    return relative or fingerprint([row.get(k) for k in ("Documento", "Fecha_periodo", "CUI_IPRESS", "Tipo_hallazgo")])


class ReviewStore:
    def __init__(self, rows, report=None):
        self.version = rows[0].get("_version", "TEMPORAL") if rows else "VACIO"
        self.rows = {row["_id"]: row for row in rows}
        self.connection = sqlite3.connect(str(Path(report).with_name("revision_usuario.sqlite")) if report else ":memory:", timeout=3)
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS decisions(batch TEXT, finding TEXT, payload TEXT, PRIMARY KEY(batch,finding));
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, batch TEXT, finding TEXT, previous TEXT, current TEXT, undone INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS history_batch ON history(batch,id);
            CREATE TABLE IF NOT EXISTS session(batch TEXT PRIMARY KEY, payload TEXT);
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(history)")}
        for name in ("reviewer", "updated", "action"):
            if name not in columns:
                self.connection.execute(f"ALTER TABLE history ADD COLUMN {name} TEXT")
        self.connection.commit()
        self.decisions = {key: json.loads(payload) for key, payload in self.connection.execute("SELECT finding,payload FROM decisions WHERE batch=?", (self.version,)) if key in self.rows}

    def save(self, key, choice, value="", reason="", page=None):
        if choice not in (*CHOICES, "Reabrir"):
            raise ValueError("Selecciona una decisión.")
        row = self.rows[key]
        self.validate_sources([row])
        if choice in RESOLVED and (not row.get("_pdf_path") or not Path(row["_pdf_path"]).is_file()):
            raise ValueError("No puedes confirmar sin un PDF disponible; utiliza No concluyente.")
        if choice in RESOLVED and (not isinstance(page, int) or page < 1):
            raise ValueError("Abre el PDF y selecciona la página de evidencia antes de confirmar.")
        if choice in ("Otro valor del PDF", "No concluyente") and not reason.strip():
            raise ValueError("Indica el motivo de la corrección o derivación.")
        if choice == "Otro valor del PDF" and not value.strip():
            raise ValueError("Indica el valor confirmado en el PDF.")
        previous = self.decisions.get(key)
        target = "Hito 3 / SAIRC" if choice == "Confirma Hito 2" else "Hito 2 / lectura IA" if choice == "Confirma Hito 3" else "Sin resolver" if choice == "No concluyente" else "Ambos / verificar"
        confirmed = row.get("Valor_LLM_OCR") if choice == "Confirma Hito 2" else row.get("Valor_SAIRC") if choice == "Confirma Hito 3" else value.strip()
        payload = None if choice == "Reabrir" else {"choice": choice, "value": confirmed, "reason": reason.strip(), "target": target, "page": page, "reviewer": getpass.getuser(), "updated": datetime.now().astimezone().isoformat(timespec="seconds")}
        with self.connection:
            self.connection.execute("INSERT INTO history(batch,finding,previous,current,reviewer,updated,action) VALUES(?,?,?,?,?,?,?)", (self.version, key, json.dumps(previous, ensure_ascii=False), json.dumps(payload, ensure_ascii=False), getpass.getuser(), datetime.now().astimezone().isoformat(timespec="seconds"), choice))
            self._write(key, payload)
        self._remember(key, payload)

    def _write(self, key, payload):
        if payload is None:
            self.connection.execute("DELETE FROM decisions WHERE batch=? AND finding=?", (self.version, key))
        else:
            self.connection.execute("INSERT OR REPLACE INTO decisions VALUES(?,?,?)", (self.version, key, json.dumps(payload, ensure_ascii=False)))

    def _remember(self, key, payload):
        if payload is None:
            self.decisions.pop(key, None)
        else:
            self.decisions[key] = payload

    def undo(self):
        for identity, key, previous in self.connection.execute("SELECT id,finding,previous FROM history WHERE batch=? AND undone=0 ORDER BY id DESC", (self.version,)):
            if key not in self.rows:
                continue
            payload = json.loads(previous)
            self.validate_sources([self.rows[key]])
            with self.connection:
                self.connection.execute("INSERT INTO history(batch,finding,previous,current,undone,reviewer,updated,action) VALUES(?,?,?,?,1,?,?,?)", (self.version, key, json.dumps(self.decisions.get(key), ensure_ascii=False), json.dumps(payload, ensure_ascii=False), getpass.getuser(), datetime.now().astimezone().isoformat(timespec="seconds"), "DESHACER"))
                self._write(key, payload)
                self.connection.execute("UPDATE history SET undone=1 WHERE id=?", (identity,))
            self._remember(key, payload)
            return key
        return None

    def validate_sources(self, rows):
        checked = set()
        for row in rows:
            if row.get("_warning"):
                raise ValueError(row["_warning"])
            for path, stamp in row.get("_watch", {}).items():
                if path not in checked:
                    if file_stamp(path) != stamp:
                        raise ValueError("Una fuente cambió durante la revisión. Recarga y vuelve a comparar.")
                    checked.add(path)

    def save_session(self, payload):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO session VALUES(?,?)", (self.version, json.dumps(payload, ensure_ascii=False)))

    def load_session(self):
        row = self.connection.execute("SELECT payload FROM session WHERE batch=?", (self.version,)).fetchone()
        return json.loads(row[0]) if row else {}

    def export(self, destination):
        from openpyxl import Workbook
        from core.exporters import save_workbook_atomic
        self.validate_sources([self.rows[key] for key in self.decisions])
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Propuestas_NO_APLICADAS"
        sheet.append(["Documento", "IPRESS", "Fecha", "PDF", "Examen", "Hito_2_original", "Hito_3_original", "Decision", "Valor_confirmado", "Corregir_en", "Motivo", "Pagina_evidencia", "Revisor", "Fecha_revision", "Estado", "Version_fuentes"])
        for key, decision in self.decisions.items():
            row = self.rows[key]
            values = [row.get(k) for k in ("Documento", "CUI_IPRESS", "Fecha_periodo", "Ruta_relativa", "Examen", "Valor_LLM_OCR", "Valor_SAIRC")]
            values += [decision.get(k) for k in ("choice", "value", "target", "reason", "page", "reviewer", "updated")]
            values += ["DERIVADO" if decision["choice"] == "No concluyente" else "PROPUESTA_NO_APLICADA", self.version]
            sheet.append(values)
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"  # Nunca ejecutar texto importado como fórmula.
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        save_workbook_atomic(workbook, Path(destination))

    def close(self):
        self.connection.close()

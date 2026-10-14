from __future__ import annotations

import os
from pathlib import Path

APP_VERSION = "10.0.7-qt"
PIPELINE_CACHE_VERSION = "2"
DEFAULT_OUTPUT_FOLDER = "salida_laboratorio_gemini_sairc_v8_9"
_LEGACY_OUTPUT_DIR = Path(r"D:\Reportes\Resultados_laboratorio")
_PORTABLE_OUTPUT_DIR = Path.home() / "LabExtractor" / "Resultados"
DEFAULT_OUTPUT_DIR = Path(
    os.environ.get(
        "LAB_EXTRACTOR_OUTPUT_DIR",
        str(_LEGACY_OUTPUT_DIR if _LEGACY_OUTPUT_DIR.parent.exists() else _PORTABLE_OUTPUT_DIR),
    )
).expanduser()

CACHE_DIRNAME = "cache_ia"
AI_RESPONSE_DIRNAME = "respuestas_ia"
NORMALIZED_DATA_DIRNAME = "datos_normalizados"
DOCUMENT_STATE_DIRNAME = "estado_documentos"
INTERNAL_FILES_DIRNAME = "_Archivos_Internos"
HITO_1_DIRNAME = "HITO_1_EXTRACCION"
HITO_2_DIRNAME = "HITO_2_RESULTADOS_SAIRC"
HITO_3_DIRNAME = "HITO_3_REFERENCIA_SAIRC"
HITO_4_DIRNAME = "HITO_4_VALIDACION"
RUN_SUMMARY_FILENAME = "resumen_ejecucion.json"
RETRY_QUEUE_FILENAME = "cola_reproceso.json"
RETRY_QUEUE_CSV_FILENAME = "cola_reproceso.csv"

LEGACY_CACHE_DIRNAME = "cache_ai"
LEGACY_AI_RESPONSE_DIRNAME = "json_ai_raw"
LEGACY_NORMALIZED_DATA_DIRNAME = "json_ai_normalizado"
LEGACY_DOCUMENT_STATE_DIRNAME = "estado_pdf"
LEGACY_RUN_SUMMARY_FILENAME = "manifest.json"
LEGACY_RETRY_QUEUE_FILENAME = "retry_queue.json"
LEGACY_RETRY_QUEUE_CSV_FILENAME = "errores_reprocesables.csv"

MAX_THREADS_BY_PROVIDER: dict[str, int] = {
    "gemini": 8,
    "openai": 4,
    "claude": 4,
    "deepseek": 2,
    "mistral": 6,
}
ABSOLUTE_MAX_THREADS = 10


LEGACY_LLM_SIGNATURE = 'bcc2cb7410d868e5d104'
# La actualización del catálogo/preflight no cambia el contrato de resultados.
COMPATIBLE_LLM_SIGNATURES = {LEGACY_LLM_SIGNATURE, "df29251499d8627732c3", "f7a8310ec44241975f3e"}

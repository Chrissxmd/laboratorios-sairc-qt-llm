from __future__ import annotations

import json
import random
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Callable, Literal, Optional

from core.sairc_normalizer import result_has_readable_value

AIProvider = Literal["claude", "openai", "gemini", "deepseek", "mistral"]
MISTRAL_PILOT_MODELS = ("mistral-small-2603", "ministral-8b-2512", "ministral-3b-2512")
MISTRAL_VISION_MODELS = [*MISTRAL_PILOT_MODELS, "mistral-small-latest", "mistral-medium-latest", "mistral-large-latest", "ministral-14b-latest"]

MODELS = {
    "claude": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-5"],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    "gemini": ["gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.1-pro"],
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
    "mistral": [
        *MISTRAL_VISION_MODELS,
        "mistral-ocr-latest",
    ],
}
DEFAULT_MODEL_BY_PROVIDER = {provider: models[0] for provider, models in MODELS.items()}

ProgressCallback = Optional[Callable[[str], None]]

COMPACT_SCHEMA_VERSION = 2
COMPACT_WIRE_FORMAT = "compact_objects_v2"
MAX_COMPACT_RESULTS = 100

COMPACT_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["v", "r"],
    "properties": {
        "v": {"type": "integer", "enum": [COMPACT_SCHEMA_VERSION]},
        "p": {"type": "string", "description": "Nombre completo del paciente."},
        "d": {"type": "string", "description": "DNI, CE u otro documento del paciente."},
        "ds": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "e": {"type": "string", "description": "Edad del paciente tal como aparece."},
        "s": {"type": "string", "description": "Sexo del paciente."},
        "l": {"type": "string", "description": "Laboratorio emisor."},
        "fx": {"type": "string", "description": "Fecha general del examen."},
        "ft": {"type": "string", "description": "Fecha de toma de muestra."},
        "fm": {"type": "string", "description": "Fecha de emisión."},
        "r": {
            "type": "array",
            "maxItems": MAX_COMPACT_RESULTS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["a", "v"],
                "properties": {
                    "a": {"type": "string", "description": "Nombre del análisis."},
                    "v": {"type": "string", "description": "Resultado literal."},
                    "u": {"type": "string", "description": "Unidad, solo si aparece."},
                    "rr": {"type": "string", "description": "Rango solo si es necesario para interpretar una serología."},
                    "c": {"type": "string", "enum": ["baja"], "description": "Solo cuando la confianza sea baja."},
                    "el": {"type": "string", "enum": ["dudoso", "ilegible"], "description": "Solo si la lectura no es segura."},
                    "ol": {"type": "string", "description": "Evidencia breve de una lectura dudosa."},
                },
            },
        },
    },
}

SYSTEM_PROMPT = """Eres un experto en extracción de datos de laboratorios clínicos de hemodiálisis.
Analiza el PDF completo y devuelve exclusivamente JSON válido, sin markdown.

IMPORTANTE:
- Esta extracción alimentará un Excel SAIRC; no inventes ni completes datos por inferencia.
- Contexto clínico: son pacientes con enfermedad renal crónica en hemodiálisis; muchos valores serán patológicos. Extrae el valor real, no lo corrijas ni lo descartes por estar fuera del rango normal.
- Si un dato no aparece, omite su propiedad. No escribas propiedades con null ni cadenas vacías.
- No tomes rangos de referencia como resultados.
- Lee exclusivamente la columna RESULTADO. Una casilla vacía sigue vacía: omite esa fila aunque tenga unidad o rango impreso. No copies «Estado inmune >10», categorías de HTLV ni unidades como valores. No generes filas «sin_resultado».
- No interpretes el símbolo (-) de un encabezado como resultado de todos los análisis. Si el número no es legible, no lo inventes.
- Identidad: en "d" extrae SOLO el DNI/C.E./documento oficial asociado directamente al paciente. No confundas con CUI, código IPRESS, RUC, número de orden, teléfono, CMP, colegiatura, historia clínica o código de barra. Si en el documento no figura explícitamente el DNI/C.E. del paciente, OMITE la propiedad "d" (o déjala vacía). NUNCA escribas notas explicativas, aclaraciones entre paréntesis ni textos como "(No se identifica...)" o "CUI..." en el campo "d".
- Fechas: las propiedades "fx", "ft" y "fm" deben ser fechas de calendario válidas (DD/MM/AAAA o AAAA-MM-DD). NUNCA extraigas horas (HH:MM:SS) en los campos de fecha.
- Valores atómicos: devuelve valores puros y concisos; no incluyas justificaciones, comentarios entre paréntesis ni advertencias textuales dentro de los campos JSON.
- Usa "ds" únicamente cuando existan varios documentos candidatos; selecciona en "d" el asociado directamente al paciente.
- Conserva los resultados cualitativos como aparecen: NO REACTIVO, NEGATIVO, POSITIVO, REACTIVO, INDETERMINADO.
- En serologías con índice numérico, conserva la interpretación textual si existe. No reemplaces NO REACTIVO/REACTIVO por el índice cuando la interpretación esté disponible.
- Si una tabla trae columnas PRE DIÁLISIS y POS DIÁLISIS, distingue claramente urea pre y post. No asignes columna post a otros exámenes si no corresponde.
- Si hay valores con asteriscos o marcas de fuera de rango, conserva el resultado literal.
- Lee todas las páginas; un mismo PDF puede tener resultados mensuales, bimestrales o semestrales.

Devuelve el protocolo compacto versión 2. Las claves significan:
- v=versión fija 2; p=paciente; d=documento; ds=documentos candidatos; e=edad; s=sexo; l=laboratorio.
- fx=fecha del examen; ft=fecha de toma; fm=fecha de emisión; r=resultados.
- En cada resultado: a=análisis, v=valor, u=unidad, rr=rango de referencia, c=confianza baja, el=estado dudoso/ilegible y ol=evidencia breve.

Esquema:
{
  "v": 2,
  "p": string opcional,
  "d": string opcional,
  "ds": [string] opcional y solo si hay ambigüedad,
  "e": string opcional,
  "s": string opcional,
  "l": string opcional,
  "fx": string opcional,
  "ft": string opcional,
  "fm": string opcional,
  "r": [
    {
      "a": string requerido,
      "v": string requerido,
      "u": string opcional,
      "rr": string opcional solo para interpretar serologías,
      "c": "baja" opcional,
      "el": "dudoso"|"ilegible" opcional,
      "ol": string opcional solo cuando exista duda
    }
  ]
}

No devuelvas método, observaciones generales, confianza alta ni estado leído. No incluyas filas sin nombre o sin resultado legible. Si una fila parece rango de referencia, no la coloques como resultado.

Exámenes prioritarios a extraer cuando existan:
Hemoglobina, Hematocrito, Urea pre, Urea post, Sodio, Potasio, Cloro, Calcio, Fósforo, Albúmina,
TGO/AST, TGP/ALT, Fosfatasa alcalina, Hierro sérico, Ferritina, Transferrina, Saturación de transferrina,
Paratohormona/PTH, HIV, VDRL/RPR/Sífilis, HBsAg, Anti-HBs, Anti-HBc, HCV y HTLV.

Si el documento no tiene resultados confiables, devuelve {"v":2,"r":[]}.
"""

USER_PROMPT = "Analiza este informe de laboratorio y extrae los datos en el formato JSON indicado."
INVALID_ANALYSIS_NAMES = {"index", "índice", "indice", "item", "valor", "resultado", "result"}


@dataclass
class AIConfig:
    provider: AIProvider = "gemini"
    model: str = DEFAULT_MODEL_BY_PROVIDER["gemini"]
    api_key: str = ""
    timeout_seconds: int = 60
    max_retries: int = 4
    temperature: float = 0.0
    requests_per_minute: int = 10
    cooldown_on_429_seconds: int = 45
    enable_token_count: bool = False
    extraction_mode: str = "llm"
    reader_mode: str = "vision"
    allow_external_processing: bool = False
    max_pdf_pages: int = 100
    max_pdf_mb: int = 50
    max_vision_pages: int = 20


@dataclass
class TokenUsage:
    provider: str = ""
    model: str = ""
    estimated_input_tokens: int | None = None
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    total_token_count: int | None = None
    cached_content_token_count: int | None = None
    cost_estimated_usd: float | None = None
    count_tokens_error: str | None = None
    count_tokens_seconds: float | None = None
    structured_output_enforced: bool | None = None
    structured_output_fallback_reason: str | None = None
    generation_attempts: int = 0
    invalid_json_attempts: int = 0
    recovered_json_responses: int = 0
    pages_processed: int | None = None


@dataclass
class AIResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)


MODEL_PRICES_USD_PER_MTOK = {
    # Tarifas estándar verificadas: https://docs.mistral.ai/inference/pricing (2026-10-12).
    "mistral-small-2603": {"input": 0.15, "output": 0.60},
    "ministral-8b-2512": {"input": 0.15, "output": 0.15},
    "ministral-3b-2512": {"input": 0.10, "output": 0.10},
    "gemini-2.5-flash-lite": {"input": 0.05, "output": 0.15},
    "gemini-2.5-flash": {"input": 0.15, "output": 1.25},
    "gemini-3.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.1-flash": {"input": 0.25, "output": 1.50},
    "gemini-3.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-3.6-flash": {"input": 0.30, "output": 2.50},
    "gemini-3.1-pro": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5": {"input": 15.00, "output": 75.00},
    # Referenciales editables. Confirmar precios vigentes del proveedor antes de producción.
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"input": 0.435, "output": 0.87},
    "mistral-ocr-latest": {"input": 0.0, "output": 0.0, "per_page": 0.004},
    "pixtral-12b-2409": {"input": 0.15, "output": 0.15},
    "pixtral-12b": {"input": 0.15, "output": 0.15},
    "pixtral-large-latest": {"input": 0.50, "output": 1.50},
    "pixtral-large-2411": {"input": 0.50, "output": 1.50},
    "ministral-8b-latest": {"input": 0.15, "output": 0.15},
    "ministral-3b-latest": {"input": 0.10, "output": 0.10},
    "ministral-3-14b": {"input": 0.20, "output": 0.20},
    "mistral-small-latest": {"input": 0.15, "output": 0.60},
    "mistral-small-4": {"input": 0.15, "output": 0.60},
    "mistral-large-latest": {"input": 0.50, "output": 1.50},
    "mistral-large-2411": {"input": 0.50, "output": 1.50},
}


class AIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str = "ai_error",
        status_code: int | None = None,
        retry_after: int | None = None,
        token_usage: TokenUsage | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.retry_after = retry_after
        self.token_usage = token_usage


class AICancelled(RuntimeError):
    pass


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AICancelled("Operacion cancelada por el usuario.")


def _sleep_cancelable(seconds: float, cancel_event: threading.Event | None = None) -> None:
    deadline = time.time() + max(0.0, seconds)
    while True:
        _raise_if_cancelled(cancel_event)
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


class GlobalRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0
        self._last_call_at = 0.0
        self._consecutive_429 = 0

    def wait_for_slot(self, rpm: int, progress: ProgressCallback = None, cancel_event: threading.Event | None = None) -> None:
        rpm = max(1, int(rpm))
        min_interval = 60.0 / rpm
        while True:
            _raise_if_cancelled(cancel_event)
            with self._lock:
                now = time.time()
                target = max(self._next_allowed_at, self._last_call_at + min_interval)
                wait = target - now
                if wait <= 0:
                    self._last_call_at = now
                    return
            if progress and wait > 1:
                progress(f"Esperando cupo de API ({wait:.1f}s)...")
            _sleep_cancelable(min(wait, 1.0), cancel_event)

    def apply_cooldown(self, seconds: int, progress: ProgressCallback = None) -> None:
        seconds = max(1, int(seconds))
        with self._lock:
            self._consecutive_429 += 1
            now = time.time()
            self._next_allowed_at = max(self._next_allowed_at, now + seconds)
            current = self._consecutive_429
        if progress:
            progress(f"Rate limit detectado. Pausa global de {seconds}s (racha 429={current}).")

    def reset_error_streak(self) -> None:
        with self._lock:
            self._consecutive_429 = 0

    def current_streak(self) -> int:
        with self._lock:
            return self._consecutive_429


RATE_LIMITER = GlobalRateLimiter()
_GEMINI_SCHEMA_SUPPORT: dict[str, bool] = {}
_GEMINI_SCHEMA_PROBE_LOCK = threading.Lock()


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return max(1, int(value))
    try:
        dt = parsedate_to_datetime(value)
        return max(1, int(dt.timestamp() - time.time()))
    except Exception:
        return None

def _post(url: str, headers: dict, payload: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        retry_after = _parse_retry_after(e.headers.get("Retry-After"))
        category = {401: "auth_401", 403: "forbidden_403", 408: "timeout_408", 429: "rate_limit_429"}.get(e.code, f"http_{e.code}")
        if e.code in {400, 404} and ("invalid_model" in body.lower() or "invalid model" in body.lower()):
            category = "invalid_model"
        msg_suffix = " (Verifica que tu API key esté restringida a generativelanguage.googleapis.com)" if e.code == 403 else ""
        raise AIError(f"HTTP {e.code}: {body[:300]}{msg_suffix}", category=category, status_code=e.code, retry_after=retry_after) from e
    except urllib.error.URLError as e:
        raise AIError(str(e), category="network_error") from e
    except OSError as e:
        raise AIError(str(e), category="network_error") from e


def _get(url: str, headers: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        retry_after = _parse_retry_after(e.headers.get("Retry-After"))
        category = {401: "auth_401", 403: "forbidden_403", 408: "timeout_408", 429: "rate_limit_429"}.get(e.code, f"http_{e.code}")
        raise AIError(f"HTTP {e.code}: {body[:300]}", category=category, status_code=e.code, retry_after=retry_after) from e
    except urllib.error.URLError as e:
        raise AIError(str(e), category="network_error") from e
    except OSError as e:
        raise AIError(str(e), category="network_error") from e


def _extract_json_text(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_json_response(text: str) -> tuple[object, bool]:
    """Decodifica el primer valor JSON completo y detecta contenido sobrante.

    Algunos endpoints en modo JSON sin esquema estricto agregan una segunda
    respuesta o una nota después del objeto correcto. El decodificador incremental
    permite conservar el primer objeto sin ampliar de forma insegura el JSON.
    """
    cleaned = (text or "").strip().lstrip("\ufeff")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).lstrip()
    start = cleaned.find("{")
    if start < 0:
        start = cleaned.find("[")
    if start < 0:
        raise json.JSONDecodeError("No se encontro un objeto JSON", cleaned, 0)
    parsed, end = json.JSONDecoder().raw_decode(cleaned, idx=start)
    remainder = cleaned[end:].strip()
    if remainder.startswith("```"):
        remainder = remainder[3:].strip()
    return parsed, bool(remainder)


def _accumulate_usage(total: TokenUsage, current: TokenUsage) -> None:
    total.provider = current.provider or total.provider
    total.model = current.model or total.model
    for field_name in (
        "estimated_input_tokens",
        "prompt_token_count",
        "candidates_token_count",
        "total_token_count",
        "cached_content_token_count",
    ):
        value = getattr(current, field_name)
        if value is not None:
            setattr(total, field_name, int(getattr(total, field_name) or 0) + int(value))
    if current.cost_estimated_usd is not None:
        total.cost_estimated_usd = round(float(total.cost_estimated_usd or 0.0) + float(current.cost_estimated_usd), 8)
    if current.count_tokens_seconds is not None:
        total.count_tokens_seconds = round(float(total.count_tokens_seconds or 0.0) + float(current.count_tokens_seconds), 4)
    if current.count_tokens_error:
        total.count_tokens_error = current.count_tokens_error
    if current.pages_processed is not None:
        total.pages_processed = int(total.pages_processed or 0) + int(current.pages_processed)
    total.structured_output_enforced = current.structured_output_enforced
    total.structured_output_fallback_reason = current.structured_output_fallback_reason
    total.generation_attempts += 1


def _clean_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned or None
    return value


def _compact_schema_meta(source_format: str, warnings: list[str] | None = None) -> dict:
    return {
        "schema_version": COMPACT_SCHEMA_VERSION if source_format == COMPACT_WIRE_FORMAT else 1,
        "wire_format": source_format,
        "schema_warnings": warnings or [],
    }


def _looks_numeric_result(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"\s*[<>≤≥]?\s*[-+]?\d+(?:[.,]\d+)?(?:\s*[%*])?\s*", value))


def _looks_like_unit(value: object) -> bool:
    if not isinstance(value, str) or _looks_numeric_result(value):
        return False
    normalized = value.strip().lower().replace(" ", "")
    return bool(re.search(r"(?:mg|g|mmol|meq|mui|ui|u|pg|ng|µg|ug|fl|%)/(?:dl|l|ml)|g/dl|%", normalized))


def _expand_compact_lab_json(data: dict) -> tuple[dict, list[str]]:
    """Convierte el protocolo compacto de la API al contrato interno estable."""
    version = data.get("v")
    if version != COMPACT_SCHEMA_VERSION:
        raise AIError(f"Versión compacta no soportada: {version!r}.", category="schema_version_invalid")
    unknown_top = sorted(set(data) - set(COMPACT_RESPONSE_JSON_SCHEMA["properties"]))
    if unknown_top:
        raise AIError(f"Claves compactas no reconocidas: {', '.join(unknown_top)}.", category="schema_unknown_keys")
    compact_results = data.get("r")
    if not isinstance(compact_results, list):
        raise AIError("El campo compacto r no es una lista.", category="schema_invalid")
    if len(compact_results) > MAX_COMPACT_RESULTS:
        raise AIError(f"La respuesta contiene más de {MAX_COMPACT_RESULTS} resultados.", category="schema_too_many_results")

    warnings: list[str] = []
    expanded_results: list[dict] = []
    allowed_result_keys = set(COMPACT_RESPONSE_JSON_SCHEMA["properties"]["r"]["items"]["properties"])
    for index, item in enumerate(compact_results, start=1):
        if not isinstance(item, dict):
            raise AIError(f"Resultado compacto {index} no es un objeto.", category="schema_invalid")
        unknown = sorted(set(item) - allowed_result_keys)
        if unknown:
            raise AIError(
                f"Resultado compacto {index} contiene claves no reconocidas: {', '.join(unknown)}.",
                category="schema_unknown_keys",
            )
        analysis = _clean_value(item.get("a"))
        value = _clean_value(item.get("v"))
        confidence = _clean_value(item.get("c"))
        reading = _clean_value(item.get("el"))
        if not isinstance(analysis, str):
            raise AIError(f"Resultado compacto {index} requiere a como texto.", category="schema_required_field")
        if not isinstance(value, str):
            value = "sin_resultado"
            reading = reading or "dudoso"
            warnings.append(f"resultado_{index}_valor_vacio; asignado_sin_resultado")
        if confidence not in (None, "baja"):
            raise AIError(f"Confianza compacta inválida en resultado {index}.", category="schema_enum_invalid")
        if reading not in (None, "dudoso", "ilegible"):
            raise AIError(f"Estado de lectura compacto inválido en resultado {index}.", category="schema_enum_invalid")
        if item.get("ol") and reading is None:
            warnings.append(f"resultado_{index}_evidencia_sin_estado; marcado_dudoso")
            reading = "dudoso"
        unit = _clean_value(item.get("u"))
        if _looks_like_unit(value) and _looks_numeric_result(unit):
            warnings.append(f"resultado_{index}_valor_unidad_intercambiados; corregido")
            value, unit = unit, value
        expanded_results.append(
            {
                "analisis": analysis,
                "resultado": value,
                "unidades": unit,
                "rango_referencia": _clean_value(item.get("rr")),
                "metodo": None,
                "observacion": None,
                "confianza": confidence,
                "estado_lectura": reading,
                "observacion_lectura": _clean_value(item.get("ol")),
            }
        )

    detected_docs = data.get("ds") or []
    if not isinstance(detected_docs, list) or not all(isinstance(value, str) for value in detected_docs):
        raise AIError("El campo compacto ds debe ser una lista de textos.", category="schema_invalid")
    expanded = {
        "paciente_nombre": _clean_value(data.get("p")),
        "documento_identidad": _clean_value(data.get("d")),
        "documentos_detectados": detected_docs,
        "edad": _clean_value(data.get("e")),
        "sexo": _clean_value(data.get("s")),
        "laboratorio": _clean_value(data.get("l")),
        "fecha_examen": _clean_value(data.get("fx")),
        "fecha_toma_muestra": _clean_value(data.get("ft")),
        "fecha_emision": _clean_value(data.get("fm")),
        "resultados": expanded_results,
    }
    return expanded, warnings


def _normalize_result_item(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    analisis = _clean_value(item.get("analisis"))
    resultado = _clean_value(item.get("resultado"))
    unidades = _clean_value(item.get("unidades"))
    rango = _clean_value(item.get("rango_referencia"))
    if isinstance(analisis, str) and analisis.lower() in INVALID_ANALYSIS_NAMES:
        analisis = None
    if not any([analisis, resultado, unidades, rango]):
        return None
    return {
        "analisis": analisis,
        "resultado": resultado,
        "unidades": unidades,
        "rango_referencia": rango,
        "metodo": _clean_value(item.get("metodo")),
        "observacion": _clean_value(item.get("observacion")),
        "confianza": _clean_value(item.get("confianza")),
        "estado_lectura": _clean_value(item.get("estado_lectura")),
        "observacion_lectura": _clean_value(item.get("observacion_lectura")),
    }


def _quality_meta(data: dict) -> dict:
    resultados = data.get("resultados") or []
    total = len(resultados)
    with_value = sum(1 for r in resultados if result_has_readable_value(r))
    with_units = sum(1 for r in resultados if r.get("unidades"))
    has_patient = bool(data.get("paciente_nombre"))
    has_date = bool(data.get("fecha_examen") or data.get("fecha_toma_muestra") or data.get("fecha_emision"))
    score = 0
    score += 25 if has_patient else 0
    score += 20 if has_date else 0
    score += 25 if total >= 3 else (10 if total > 0 else 0)
    score += 20 if total and with_value / total >= 0.70 else (10 if with_value else 0)
    score += 10 if total and with_units / total >= 0.50 else 0
    if not with_value:
        score = min(score, 45)
    level = "alta" if score >= 75 else ("media" if score >= 50 else "baja")
    return {
        "quality_score": score,
        "quality_level": level,
        "has_patient": has_patient,
        "has_date": has_date,
        "results_with_value": with_value,
        "results_with_usable_value": with_value,
        "reading_valid": bool(with_value),
        "results_with_units": with_units,
    }


def validate_lab_json(data: object) -> dict:
    if not isinstance(data, dict):
        raise AIError("La IA no devolvio un objeto JSON.", category="schema_invalid")
    source_format = "legacy_verbose_v1"
    schema_warnings: list[str] = []
    if "v" in data or "r" in data:
        data, schema_warnings = _expand_compact_lab_json(data)
        source_format = COMPACT_WIRE_FORMAT
    resultados_raw = data.get("resultados") or []
    if not isinstance(resultados_raw, list):
        raise AIError("El campo resultados no es una lista.", category="schema_invalid")
    resultados = []
    dropped = 0
    for item in resultados_raw:
        normalized = _normalize_result_item(item)
        if normalized is None:
            dropped += 1
            continue
        resultados.append(normalized)
    detected_docs = data.get("documentos_detectados") or []
    if isinstance(detected_docs, str):
        detected_docs = [detected_docs]
    if not isinstance(detected_docs, list):
        detected_docs = []
    out = {
        "paciente_nombre": _clean_value(data.get("paciente_nombre")),
        "documento_identidad": _clean_value(data.get("documento_identidad")),
        "documentos_detectados": [_clean_value(x) for x in detected_docs if _clean_value(x)],
        "edad": _clean_value(data.get("edad")),
        "sexo": _clean_value(data.get("sexo")),
        "laboratorio": _clean_value(data.get("laboratorio")),
        "fecha_examen": _clean_value(data.get("fecha_examen")),
        "fecha_toma_muestra": _clean_value(data.get("fecha_toma_muestra")),
        "fecha_emision": _clean_value(data.get("fecha_emision")),
        "resultados": resultados,
    }
    meta = _quality_meta(out)
    meta.update({"rows_detected": len(resultados), "rows_dropped": dropped})
    meta.update(_compact_schema_meta(source_format, schema_warnings))
    out["_meta"] = meta
    return out


def normalize_cached_lab_json(data: dict) -> dict:
    """Acepta caché histórica, interna o compacta y devuelve el contrato interno."""
    if not isinstance(data, dict):
        raise AIError("La caché IA no contiene un objeto JSON.", category="schema_invalid")
    if "v" not in data and "r" not in data:
        return data
    source = data.get("_source")
    previous_meta = data.get("_meta") or {}
    compact_payload = {key: value for key, value in data.items() if not key.startswith("_")}
    normalized = validate_lab_json(compact_payload)
    normalized["_meta"] = {**previous_meta, **(normalized.get("_meta") or {})}
    if source:
        normalized["_source"] = source
    return normalized


def _get_price(model: str) -> dict:
    if model in MODEL_PRICES_USD_PER_MTOK:
        return MODEL_PRICES_USD_PER_MTOK[model]
    lower = model.lower()
    for key, value in MODEL_PRICES_USD_PER_MTOK.items():
        if key.lower() in lower or lower in key.lower():
            return value
    return {"input": 0.0, "output": 0.0}


def estimate_cost_usd(
    provider: str,
    model: str,
    prompt_tokens: int | None,
    output_tokens: int | None,
    pages_processed: int | None = None,
) -> float | None:
    price = _get_price(model)
    if "per_page" in price and pages_processed is not None:
        return round(float(pages_processed) * float(price["per_page"]), 6)
    if prompt_tokens is None and output_tokens is None:
        return None
    return round(
        ((prompt_tokens or 0) / 1_000_000) * price.get("input", 0.0) + ((output_tokens or 0) / 1_000_000) * price.get("output", 0.0), 8
    )


def _usage_to_dict(usage: TokenUsage) -> dict:
    return usage.__dict__.copy()


def _estimate_openai_input_tokens(md_text: str) -> int:
    return max(1, int((len(md_text or "") + len(SYSTEM_PROMPT) + len(USER_PROMPT)) / 4))


def _estimate_base64_image_tokens(images_b64: list[str]) -> int:
    total_chars = sum(len(x) for x in images_b64) + len(SYSTEM_PROMPT) + len(USER_PROMPT)
    return max(1, int(total_chars / 4))


def count_tokens_before_call(config: AIConfig, md_text: str = "", timeout: int | None = None, pdf_b64: str | None = None) -> TokenUsage:
    usage = TokenUsage(provider=config.provider, model=config.model)
    if not config.enable_token_count:
        return usage
    timeout = timeout or config.timeout_seconds
    started = time.perf_counter()
    is_vision = bool(pdf_b64)
    try:
        if config.provider == "gemini":
            parts = [{"text": md_text}, {"text": SYSTEM_PROMPT.strip() + "\n\n" + USER_PROMPT}]
            if is_vision:
                parts = [
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
                    {"text": SYSTEM_PROMPT.strip() + "\n\n" + USER_PROMPT},
                ]
            resp = _post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:countTokens?key={config.api_key}",
                headers={"Content-Type": "application/json"},
                payload={"contents": [{"parts": parts}]},
                timeout=timeout,
            )
            usage.estimated_input_tokens = resp.get("totalTokens")
        elif config.provider == "claude":
            content = [{"type": "text", "text": md_text}, {"type": "text", "text": USER_PROMPT}]
            if is_vision:
                content = [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                    {"type": "text", "text": USER_PROMPT},
                ]
            resp = _post(
                "https://api.anthropic.com/v1/messages/count_tokens",
                headers={"Content-Type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"},
                payload={"model": config.model, "system": SYSTEM_PROMPT.strip(), "messages": [{"role": "user", "content": content}]},
                timeout=timeout,
            )
            usage.estimated_input_tokens = resp.get("input_tokens")
        elif config.provider == "openai":
            usage.estimated_input_tokens = _estimate_openai_input_tokens(pdf_b64 or md_text)
        elif config.provider == "deepseek":
            usage.estimated_input_tokens = _estimate_openai_input_tokens(md_text)
        elif config.provider == "mistral":
            if "ocr" in config.model.lower():
                usage.estimated_input_tokens = None
            else:
                usage.estimated_input_tokens = _estimate_openai_input_tokens(pdf_b64 or md_text)
    except Exception as exc:
        usage.count_tokens_error = str(exc)[:300]
    finally:
        usage.count_tokens_seconds = round(time.perf_counter() - started, 2)
    return usage


def _apply_response_usage(usage: TokenUsage, resp: dict) -> TokenUsage:
    if usage.provider == "gemini":
        meta = resp.get("usageMetadata") or {}
        usage.prompt_token_count = meta.get("promptTokenCount")
        usage.candidates_token_count = meta.get("candidatesTokenCount")
        usage.total_token_count = meta.get("totalTokenCount")
        usage.cached_content_token_count = meta.get("cachedContentTokenCount")
    elif usage.provider in {"openai", "deepseek"}:
        meta = resp.get("usage") or {}
        usage.prompt_token_count = meta.get("prompt_tokens")
        usage.candidates_token_count = meta.get("completion_tokens")
        usage.total_token_count = meta.get("total_tokens")
    elif usage.provider == "mistral":
        if "usage_info" in resp:
            pages = int(resp["usage_info"].get("pages_processed", 1))
            usage.pages_processed = pages
            usage.cost_estimated_usd = estimate_cost_usd(usage.provider, usage.model, None, None, pages_processed=pages)
            return usage
        meta = resp.get("usage") or {}
        usage.prompt_token_count = meta.get("prompt_tokens")
        usage.candidates_token_count = meta.get("completion_tokens")
        usage.total_token_count = meta.get("total_tokens")
    elif usage.provider == "claude":
        meta = resp.get("usage") or {}
        usage.prompt_token_count = meta.get("input_tokens")
        usage.candidates_token_count = meta.get("output_tokens")
        if usage.prompt_token_count is not None or usage.candidates_token_count is not None:
            usage.total_token_count = (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)
    usage.cost_estimated_usd = estimate_cost_usd(
        usage.provider,
        usage.model,
        usage.prompt_token_count or usage.estimated_input_tokens,
        usage.candidates_token_count,
        pages_processed=usage.pages_processed,
    )
    return usage


def _gemini_generation_config(temperature: float, max_output_tokens: int | None = None) -> dict:
    config = {
        "temperature": temperature,
        "responseMimeType": "application/json",
        "responseJsonSchema": COMPACT_RESPONSE_JSON_SCHEMA,
    }
    if max_output_tokens is not None:
        config["maxOutputTokens"] = max_output_tokens
    return config


def _gemini_json_only_config(temperature: float, max_output_tokens: int | None = None) -> dict:
    config = {"temperature": temperature, "responseMimeType": "application/json"}
    if max_output_tokens is not None:
        config["maxOutputTokens"] = max_output_tokens
    return config


def _post_gemini_with_schema_fallback(
    config: AIConfig,
    payload: dict,
    usage: TokenUsage,
    *,
    timeout: int,
    temperature: float,
) -> dict:
    """Usa esquema estricto si el endpoint lo admite y degrada una sola vez ante HTTP 400.

    Algunas combinaciones de modelo/endpoint aceptan JSON pero rechazan
    ``responseJsonSchema`` con ``INVALID_ARGUMENT``. El prompt compacto y la
    validación local siguen siendo obligatorios en el modo de compatibilidad.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent?key={config.api_key}"
    headers = {"Content-Type": "application/json"}

    def post(strict: bool) -> dict:
        request_payload = dict(payload)
        request_payload["generationConfig"] = (
            _gemini_generation_config(temperature) if strict else _gemini_json_only_config(temperature)
        )
        return _post(url, headers=headers, payload=request_payload, timeout=timeout)

    known_support = _GEMINI_SCHEMA_SUPPORT.get(config.model)
    if known_support is False:
        usage.structured_output_enforced = False
        usage.structured_output_fallback_reason = "modelo_endpoint_sin_esquema_estricto"
        return post(False)
    if known_support is True:
        try:
            usage.structured_output_enforced = True
            return post(True)
        except AIError as exc:
            if exc.category != "http_400":
                raise
            response = post(False)
            with _GEMINI_SCHEMA_PROBE_LOCK:
                _GEMINI_SCHEMA_SUPPORT[config.model] = False
            usage.structured_output_enforced = False
            usage.structured_output_fallback_reason = "http_400_invalid_argument_con_response_json_schema"
            return response

    with _GEMINI_SCHEMA_PROBE_LOCK:
        known_support = _GEMINI_SCHEMA_SUPPORT.get(config.model)
        if known_support is False:
            usage.structured_output_enforced = False
            usage.structured_output_fallback_reason = "modelo_endpoint_sin_esquema_estricto"
            return post(False)
        try:
            response = post(True)
            _GEMINI_SCHEMA_SUPPORT[config.model] = True
            usage.structured_output_enforced = True
            return response
        except AIError as exc:
            if exc.category != "http_400":
                raise
            # Un único intento de compatibilidad permite distinguir esquema
            # rechazado de PDF/modelo inválido. Solo se memoriza si funciona.
            response = post(False)
            _GEMINI_SCHEMA_SUPPORT[config.model] = False
            usage.structured_output_enforced = False
            usage.structured_output_fallback_reason = "http_400_invalid_argument_con_response_json_schema"
            return response


def call_claude(config: AIConfig, md_text: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, md_text, timeout=timeout)
    resp = _post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"},
        payload={
            "model": config.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "system": SYSTEM_PROMPT.strip(),
            "messages": [{"role": "user", "content": [{"type": "text", "text": md_text}, {"type": "text", "text": USER_PROMPT}]}],
        },
        timeout=timeout,
    )
    return AIResponse(resp["content"][0]["text"], _apply_response_usage(usage, resp))


def call_openai(config: AIConfig, md_text: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, md_text, timeout=timeout)
    resp = _post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
        payload={
            "model": config.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": [{"type": "text", "text": md_text}, {"type": "text", "text": USER_PROMPT}]},
            ],
        },
        timeout=timeout,
    )
    return AIResponse(resp["choices"][0]["message"]["content"], _apply_response_usage(usage, resp))


def call_gemini(config: AIConfig, md_text: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, md_text, timeout=timeout)
    resp = _post_gemini_with_schema_fallback(
        config,
        {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT.strip()}]},
            "contents": [{"parts": [{"text": md_text}, {"text": USER_PROMPT}]}],
        },
        usage,
        timeout=timeout,
        temperature=temperature,
    )
    return AIResponse(resp["candidates"][0]["content"]["parts"][0]["text"], _apply_response_usage(usage, resp))


def call_claude_vision(config: AIConfig, pdf_b64: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, timeout=timeout, pdf_b64=pdf_b64)
    resp = _post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"},
        payload={
            "model": config.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "system": SYSTEM_PROMPT.strip(),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                }
            ],
        },
        timeout=timeout,
    )
    return AIResponse(resp["content"][0]["text"], _apply_response_usage(usage, resp))


def call_openai_vision(config: AIConfig, pdf_b64: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, timeout=timeout, pdf_b64=pdf_b64)
    resp = _post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
        payload={
            "model": config.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {
                    "role": "user",
                    "content": [
                        {"type": "file", "file": {"filename": "laboratorio.pdf", "file_data": f"data:application/pdf;base64,{pdf_b64}"}},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
        },
        timeout=timeout,
    )
    return AIResponse(resp["choices"][0]["message"]["content"], _apply_response_usage(usage, resp))


def call_gemini_vision(config: AIConfig, pdf_b64: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, timeout=timeout, pdf_b64=pdf_b64)
    resp = _post_gemini_with_schema_fallback(
        config,
        {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT.strip()}]},
            "contents": [{"parts": [{"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}}, {"text": USER_PROMPT}]}],
        },
        usage,
        timeout=timeout,
        temperature=temperature,
    )
    return AIResponse(resp["candidates"][0]["content"]["parts"][0]["text"], _apply_response_usage(usage, resp))


def call_deepseek(config: AIConfig, md_text: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, md_text, timeout=timeout)
    resp = _post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
        payload={
            "model": config.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": [{"type": "text", "text": md_text}, {"type": "text", "text": USER_PROMPT}]},
            ],
        },
        timeout=timeout,
    )
    return AIResponse(resp["choices"][0]["message"]["content"], _apply_response_usage(usage, resp))


def call_mistral_text(config: AIConfig, md_text: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    usage = count_tokens_before_call(config, md_text, timeout=timeout)
    resp = _post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
        payload={
            "model": config.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": [{"type": "text", "text": md_text}, {"type": "text", "text": USER_PROMPT}]},
            ],
        },
        timeout=timeout,
    )
    return AIResponse(resp["choices"][0]["message"]["content"], _apply_response_usage(usage, resp))


def call_mistral_chat_vision(config: AIConfig, pdf_path: str, timeout: int = 120, temperature: float = 0.0) -> AIResponse:
    from core.pdf_utils import pdf_pages_to_base64_images

    images_b64 = pdf_pages_to_base64_images(pdf_path, max_pages=config.max_vision_pages)
    usage = count_tokens_before_call(config, timeout=timeout, pdf_b64=images_b64[0] if images_b64 else "")
    image_contents: list[dict] = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}} for img in images_b64
    ]
    user_content: list[dict] = [{"type": "text", "text": USER_PROMPT}] + image_contents
    resp = _post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
        payload={
            "model": config.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": user_content},
            ],
        },
        timeout=timeout,
    )
    return AIResponse(resp["choices"][0]["message"]["content"], _apply_response_usage(usage, resp))


def call_mistral_ocr(config: AIConfig, pdf_b64: str, timeout: int = 120) -> AIResponse:
    usage = TokenUsage(provider=config.provider, model=config.model)
    payload = {
        "model": config.model,
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{pdf_b64}",
        },
        "document_annotation_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "lab_compact_schema",
                "strict": True,
                "schema": COMPACT_RESPONSE_JSON_SCHEMA,
            },
        },
        "document_annotation_prompt": SYSTEM_PROMPT.strip() + "\n\n" + USER_PROMPT,
    }
    resp = _post(
        "https://api.mistral.ai/v1/ocr",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
        payload=payload,
        timeout=timeout,
    )
    raw_annotation = resp.get("document_annotation")
    usage = _apply_response_usage(usage, resp)
    if raw_annotation is None or raw_annotation == "":
        raise AIError("Mistral OCR no devolvió document_annotation; no se interpretará Markdown localmente.", category="schema_required_field", token_usage=usage)
    text = raw_annotation if isinstance(raw_annotation, str) else json.dumps(raw_annotation, ensure_ascii=False)
    return AIResponse(text, _apply_response_usage(usage, resp))



def analyze_text(config: AIConfig, md_text: str, progress: ProgressCallback = None, pdf_path: str = "") -> AIResponse:
    if not config.api_key:
        raise ValueError("Configura tu API key antes de procesar.")
    if progress:
        progress(f"Enviando texto estructurado a {config.provider} / {config.model}...")
    if config.provider == "claude":
        return call_claude(config, md_text, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "openai":
        return call_openai(config, md_text, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "gemini":
        return call_gemini(config, md_text, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "deepseek":
        return call_deepseek(config, md_text, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "mistral":
        return call_mistral_text(config, md_text, timeout=config.timeout_seconds, temperature=config.temperature)
    raise ValueError(f"Proveedor no soportado: {config.provider}")


def analyze_vision(config: AIConfig, pdf_path: str, progress: ProgressCallback = None) -> AIResponse:
    validate_reader_config(config)
    if not pdf_path:
        raise ValueError("Se requiere la ruta del PDF para el modo LLM con vision.")
    if config.provider == "deepseek":
        raise ValueError("DeepSeek no esta configurado como lector vision de PDF en este flujo.")
    from core.pdf_utils import load_pdf_as_base64, get_pdf_page_count
    from pathlib import Path
    pages = get_pdf_page_count(pdf_path)
    page_limit = min(config.max_pdf_pages, config.max_vision_pages) if config.provider == "mistral" and config.reader_mode == "vision" else config.max_pdf_pages
    if pages > page_limit or Path(pdf_path).stat().st_size > config.max_pdf_mb * 1024 * 1024:
        raise AIError("El PDF excede los límites configurados; no se truncará ni enviará.", category="validation_error")

    if progress:
        progress(f"Lectura remota: {config.provider} / {config.model} · {config.reader_mode} · {pages} páginas...")
    if config.provider == "mistral" and config.reader_mode == "vision":
        return call_mistral_chat_vision(config, pdf_path, timeout=config.timeout_seconds, temperature=config.temperature)
    pdf_b64_value = load_pdf_as_base64(pdf_path)
    if config.provider == "claude":
        return call_claude_vision(config, pdf_b64_value, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "openai":
        return call_openai_vision(config, pdf_b64_value, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "gemini":
        return call_gemini_vision(config, pdf_b64_value, timeout=config.timeout_seconds, temperature=config.temperature)
    if config.provider == "mistral":
        return call_mistral_ocr(config, pdf_b64_value, timeout=config.timeout_seconds)
    raise ValueError(f"Proveedor no soportado para vision: {config.provider}")


def analyze(config: AIConfig, prompt: str, progress: ProgressCallback = None) -> str:
    if not config.api_key:
        raise ValueError("Configura tu API key antes de procesar.")
    if progress:
        progress(f"Conectando a {config.provider} con modelo {config.model}...")
    if config.provider == "claude":
        resp = _post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"},
            payload={
                "model": config.model,
                "max_tokens": 200,
                "temperature": config.temperature,
                "system": SYSTEM_PROMPT.strip(),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=config.timeout_seconds,
        )
        return resp["content"][0]["text"]
    if config.provider == "openai":
        resp = _post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
            payload={
                "model": config.model,
                "max_tokens": 200,
                "temperature": config.temperature,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": prompt}],
            },
            timeout=config.timeout_seconds,
        )
        return resp["choices"][0]["message"]["content"]
    if config.provider == "gemini":
        resp = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent?key={config.api_key}",
            headers={"Content-Type": "application/json"},
            payload={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT.strip()}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": config.temperature, "responseMimeType": "application/json"},
            },
            timeout=config.timeout_seconds,
        )
        return resp["candidates"][0]["content"]["parts"][0]["text"]
    if config.provider == "deepseek":
        resp = _post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
            payload={
                "model": config.model,
                "max_tokens": 200,
                "temperature": config.temperature,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": prompt}],
            },
            timeout=config.timeout_seconds,
        )
        return resp["choices"][0]["message"]["content"]
    if config.provider == "mistral":
        model_to_use = "pixtral-12b-2409" if "ocr" in config.model.lower() else config.model
        resp = _post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
            payload={
                "model": model_to_use,
                "max_tokens": 200,
                "temperature": config.temperature,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": prompt}],
            },
            timeout=config.timeout_seconds,
        )
        return resp["choices"][0]["message"]["content"]
    raise ValueError(f"Proveedor no soportado: {config.provider}")


def _compute_wait_seconds(config: AIConfig, error: AIError, attempt: int) -> int:
    if error.category == "rate_limit_429":
        if error.retry_after:
            return max(config.cooldown_on_429_seconds, int(error.retry_after))
        streak = max(1, RATE_LIMITER.current_streak())
        return max(config.cooldown_on_429_seconds, min(300, 30 * streak + 15 * attempt))
    if error.category in {"network_error", "timeout_408"}:
        # En producción conviene esperar más ante caída de internet o timeout.
        return min(90, 15 * attempt)
    if error.category in {"http_502", "http_503", "http_504"}:
        # Alta demanda/saturación temporal del modelo: backoff más conservador.
        return min(120, 30 * attempt)
    if error.category.startswith("http_"):
        return min(45, 5 * attempt)
    return min(30, 3 * attempt)


def _is_non_retryable_api_error(error: AIError) -> bool:
    return error.category in {"http_400", "auth_401", "forbidden_403", "http_404"}

def validate_reader_config(config: AIConfig) -> None:
    if config.extraction_mode != "llm":
        raise ValueError("Esta edición no admite OCR local.")
    if not config.allow_external_processing:
        raise ValueError("Confirma la autorización de procesamiento externo antes de enviar PDF.")
    if not config.api_key.strip():
        raise ValueError("Configura la API key del proveedor seleccionado.")
    if config.provider not in {"gemini", "mistral", "claude", "openai"}:
        raise ValueError("El proveedor no dispone de un lector PDF validado en esta edición.")
    if config.reader_mode not in {"ocr", "vision"} or (config.reader_mode == "ocr" and config.provider != "mistral"):
        raise ValueError("OCR remoto es una modalidad exclusiva de Mistral.")
    if config.provider == "mistral" and (("ocr" in config.model.lower()) != (config.reader_mode == "ocr")):
        raise ValueError("La modalidad Mistral y el modelo seleccionado son incompatibles.")
    if not config.model.strip() or min(config.max_retries, config.timeout_seconds, config.requests_per_minute, config.max_pdf_pages, config.max_pdf_mb, config.max_vision_pages) <= 0:
        raise ValueError("Modelo y límites deben ser válidos y positivos.")


def analyze_to_json(
    config: AIConfig,
    md_text: str = "",
    progress: ProgressCallback = None,
    pdf_path: str = "",
    cancel_event: threading.Event | None = None,
    *,
    pdf_b64: str | None = None,
    unused_path: str = "",
) -> dict:
    validate_reader_config(config)
    if not (pdf_path or unused_path):
        raise ValueError("La lectura remota requiere la ruta al PDF; no se procesa OCR local.")
    vision_path = pdf_path or unused_path
    last_error: Exception | None = None
    accumulated_usage = TokenUsage(provider=config.provider, model=config.model)
    for attempt in range(1, config.max_retries + 1):
        ai_response: AIResponse | None = None
        try:
            _raise_if_cancelled(cancel_event)
            RATE_LIMITER.wait_for_slot(config.requests_per_minute, progress=progress, cancel_event=cancel_event)
            if progress:
                progress(f"Consulta IA intento {attempt}/{config.max_retries}...")
            _raise_if_cancelled(cancel_event)
            ai_response = analyze_vision(config, vision_path, progress=progress)
            _accumulate_usage(accumulated_usage, ai_response.usage)
            _raise_if_cancelled(cancel_event)
            parsed, recovered_extra_content = _parse_json_response(ai_response.text)
            validated = validate_lab_json(parsed)
            if recovered_extra_content:
                accumulated_usage.recovered_json_responses += 1
                warnings = validated.setdefault("_meta", {}).setdefault("schema_warnings", [])
                warnings.append("respuesta_con_contenido_adicional_ignorado; primer_json_utilizado")
            validated.setdefault("_meta", {})["token_usage"] = _usage_to_dict(accumulated_usage)
            RATE_LIMITER.reset_error_streak()
            return validated
        except AICancelled:
            raise
        except AIError as e:
            last_error = e
            if accumulated_usage.generation_attempts:
                e.token_usage = accumulated_usage
            if _is_non_retryable_api_error(e) or e.category.startswith("schema_") or e.category == "validation_error":
                if progress:
                    progress(f"Error no reintentable de API ({e.category}): revisa modelo, solicitud o credenciales.")
                raise
            wait = _compute_wait_seconds(config, e, attempt)
            if e.category == "rate_limit_429":
                RATE_LIMITER.apply_cooldown(wait, progress=progress)
            if progress:
                progress(f"Intento {attempt} fallo ({e.category}). Esperando {wait}s...")
            if attempt < config.max_retries:
                _sleep_cancelable(wait + random.uniform(0.0, 0.8), cancel_event)
        except json.JSONDecodeError as e:
            accumulated_usage.invalid_json_attempts += 1
            last_error = AIError(f"JSON invalido: {e}", category="invalid_json", token_usage=accumulated_usage)
            wait = min(15, 2 * attempt)
            if progress:
                if attempt < config.max_retries:
                    progress(f"Intento {attempt}: la IA no devolvio JSON valido. Reintento en {wait}s...")
                else:
                    progress(f"Intento {attempt}: la IA no devolvio JSON valido. Se registra para reproceso manual.")
            if attempt < config.max_retries:
                _sleep_cancelable(wait + random.uniform(0.0, 0.8), cancel_event)
        except Exception as e:
            last_error = e
            wait = min(15, 2 * attempt)
            if progress:
                progress(f"Intento {attempt} fallo: {e}. Reintento en {wait}s...")
            if attempt < config.max_retries:
                _sleep_cancelable(wait + random.uniform(0.0, 0.8), cancel_event)
    if isinstance(last_error, AIError):
        raise last_error
    raise AIError(str(last_error) if last_error else "Error desconocido", category="ai_failed")


def validate_remote_model(config: AIConfig, catalog: dict | None = None) -> None:
    """Comprueba el catálogo Mistral una vez por lote, sin enviar PDF ni generar texto."""
    if config.provider != "mistral":
        return
    response = catalog if catalog is not None else _get("https://api.mistral.ai/v1/models", headers={"Authorization": f"Bearer {config.api_key}"}, timeout=min(config.timeout_seconds, 30))
    models = response.get("data")
    if not isinstance(models, list):
        raise AIError("Mistral devolvió un catálogo de modelos inválido.", category="validation_error")
    for model in models:
        if not isinstance(model, dict):
            continue
        aliases = model.get("aliases") or []
        if config.model not in [model.get("id"), *(aliases if isinstance(aliases, list) else [])]:
            continue
        capabilities = model.get("capabilities") or {}
        if config.reader_mode == "vision" and capabilities.get("vision") is False:
            raise AIError(f"El modelo {config.model} no admite visión. Selecciona un modelo multimodal disponible.", category="model_incompatible")
        return
    raise AIError(f"El modelo {config.model} no está disponible en el catálogo de Mistral para esta clave. Selecciona otro modelo y vuelve a iniciar o reprocesar errores. No se enviaron PDF.", category="invalid_model")


def test_connection(config: AIConfig) -> tuple[bool, str]:
    try:
        if config.provider == "mistral":
            validate_remote_model(config)
            return True, "Conexión exitosa; modelo disponible en Mistral."
        raw = analyze(config, '{"ping": "responde con JSON {\\"ok\\": true}"}')
        _extract_json_text(raw)
        return True, "Conexión correcta con la API."
    except Exception as e:
        return False, str(e)

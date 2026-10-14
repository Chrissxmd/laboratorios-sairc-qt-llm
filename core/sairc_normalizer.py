from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

SAIRC_FIELDS = [
    "HEMOGLOBINA",
    "HEMATOCRITO",
    "UREA_PRE",
    "UREA_POST",
    "PRU",
    "SODIO",
    "POTASIO",
    "CLORO",
    "CALCIO",
    "FOSFORO",
    "ALBUMINA",
    "TGO_AST",
    "TGP_ALT",
    "FOSFATASA_ALCALINA",
    "HIERRO_SERICO",
    "FERRITINA",
    "TRANSFERRINA",
    "SAT_TRANSFERRINA",
    "PTH",
    "HIV",
    "VDRL",
    "HBSAG",
    "ANTI_HBS",
    "ANTI_HBC",
    "HCV",
    "HTLV",
]

BASIC_FIELDS = ["HEMOGLOBINA", "HEMATOCRITO", "UREA_PRE", "UREA_POST", "SODIO", "POTASIO", "CLORO", "CALCIO", "FOSFORO"]
QUALITATIVE_FIELDS = {"HIV", "VDRL", "HBSAG", "ANTI_HBS", "ANTI_HBC", "HCV", "HTLV"}

# Rangos de plausibilidad para hemodiálisis: NO son rangos normales.
# Solo detectan valores imposibles, cruces de tabla o lecturas de unidad/campo incorrecto.
PLAUSIBLE_RANGES = {
    "HEMOGLOBINA": (4.0, 20.0),
    "HEMATOCRITO": (12.0, 65.0),
    "UREA_PRE": (1.0, 500.0),
    "UREA_POST": (1.0, 300.0),
    "PRU": (0.0, 100.0),
    "SODIO": (115.0, 170.0),
    "POTASIO": (2.0, 8.5),
    "CLORO": (70.0, 130.0),
    "CALCIO": (5.0, 15.0),
    "FOSFORO": (1.0, 15.0),
    "ALBUMINA": (1.0, 7.0),
    "TGO_AST": (0.0, 1000.0),
    "TGP_ALT": (0.0, 1000.0),
    "FOSFATASA_ALCALINA": (0.0, 3000.0),
    "HIERRO_SERICO": (0.0, 500.0),
    "FERRITINA": (0.0, 5000.0),
    "TRANSFERRINA": (50.0, 600.0),
    "SAT_TRANSFERRINA": (0.0, 100.0),
    "PTH": (0.0, 5000.0),
}

ALERT_RANGES_HD = {
    # Alertas clínicas o de control, no bloqueo automático.
    "POTASIO": (2.8, 6.8),
    "HEMOGLOBINA": (6.0, 18.0),
    "HEMATOCRITO": (18.0, 58.0),
    "SODIO": (125.0, 155.0),
    "CALCIO": (6.5, 13.0),
    "FOSFORO": (1.5, 10.0),
    "ALBUMINA": (2.0, 5.8),
    "TRANSFERRINA": (80.0, 500.0),
}

ALIASES: list[tuple[str, str]] = [
    (r"\bHEMOGLOBINA\b|^HB$|HEMOGLO[BΒ][IΙ]NA", "HEMOGLOBINA"),
    (r"\bHEMATOCRITO\b|\bHTO\b", "HEMATOCRITO"),
    (r"\bUREA\s*2\b|UREA.*(POST|DESPUES|POS|POST\s*HEMODIALISIS|POST\s*DIALISIS)|NITROGENO\s+UREICO.*POST|UREICO\s+EN\s+SANGRE\s+POST", "UREA_POST"),
    (r"\bUREA\s*1\b|UREA.*(PRE|ANTES|PRE\s*HEMODIALISIS|PRE\s*DIALISIS)|NITROGENO\s+UREICO.*PRE|UREICO.*CUANTITATIVO$|\bBUN\b", "UREA_PRE"),
    (r"\bUREA\b|UREA\s+SERICA|NITROGENO\s+UREICO", "UREA_PRE"),
    (r"^P\s*\.?\s*R\s*\.?\s*U\.?$|PORCENTAJE\s+DE\s+REDUCCION\s+DE\s+UREA", "PRU"),
    (r"\bSODIO\b|\bNA\b", "SODIO"),
    (r"\bPOTASIO\b|\bK\b", "POTASIO"),
    (r"\bCLORO\b|\bCL\b|CLORO\s+SERICO", "CLORO"),
    (r"CALCIO(?!\s+IONICO)|CALCIO\s+SERICO|DOSAJE\s+DE\s+CALCIO", "CALCIO"),
    (r"FOSFOR[OA]|FOSFATO", "FOSFORO"),
    (r"ALBUMINA", "ALBUMINA"),
    (r"\bTGO\b|\bAST\b|OXALACETICA|\bSGOT\b", "TGO_AST"),
    (r"\bTGP\b|\bALT\b|PIRUVICA|\bSGPT\b", "TGP_ALT"),
    (r"FOSFATAS?A?[\s,.;:-]+(?:ALCALINA|ALCANALINA)|\bALP\b", "FOSFATASA_ALCALINA"),
    (r"HIERRO", "HIERRO_SERICO"),
    (r"FERRITINA", "FERRITINA"),
    (r"SAT.*TRANSFERRINA|TRANSFERRINA.*(?:SAT|PORCENTAJE|%)|%\s*DE\s*TRANSFERRINA", "SAT_TRANSFERRINA"),
    (r"TRANSFERRINA", "TRANSFERRINA"),
    (r"PARATOHORMONA|PARATHORMONA|PARATIROIDEA|\bPTH\b", "PTH"),
    (r"\bH[\s.\-]*I[\s.\-]*V(?:\s*[12])?\b|\bVIH\b", "HIV"),
    (r"V\s*\.?\s*D\s*\.?\s*R\s*\.?\s*L\.?|SIFILIS|\bRPR\b", "VDRL"),
    (
        r"ANTI\s*-?\s*HBS(?:AG|AB)?|HBS\s*[-.]?\s*AB\b|ANTICUERPOS?.*SUPERFICIE"
        r"|HEPATITIS\s+B.*(?:HBS\s*[-.]?\s*AB|ANTIC(?:UERPOS?)?\.?\s*CUANT)",
        "ANTI_HBS",
    ),
    (
        r"ANTI\s*-?\s*(?:HBC|HCB)|HB\s*[-.]?\s*CORE|HBC\s*\.?\s*\(?ANTICORE\)?"
        r"|ANTI\s+CORE|CORE\s+TOTAL|NUCLEOCAPSIDE|HBC\s*AB|HBCA\s*B",
        "ANTI_HBC",
    ),
    (
        r"HBS\s*[-.]?\s*AG\b|\bHBSAG\b|ANTIGENOS?\s+DE\s+(?:VIRUS\s+DE\s+)?HEPATITIS\s+B"
        r"|ANTIGENO\s+DE\s+SUPERFICIE|HEPATITIS\s+B\s+AG\.?\s+SUPERFICIE|ANTIGENO\s+AUSTRALIANO",
        "HBSAG",
    ),
    (r"HCV|HEPATITIS\s+C|VHC", "HCV"),
    (r"HTLV", "HTLV"),
]

UNITS_DEFAULT = {
    "HEMOGLOBINA": "g/dL",
    "HEMATOCRITO": "%",
    "UREA_PRE": "mg/dL",
    "UREA_POST": "mg/dL",
    "PRU": "%",
    "SODIO": "mmol/L",
    "POTASIO": "mmol/L",
    "CLORO": "mmol/L",
    "CALCIO": "mg/dL",
    "FOSFORO": "mg/dL",
    "ALBUMINA": "g/dL",
    "TGO_AST": "U/L",
    "TGP_ALT": "U/L",
    "FOSFATASA_ALCALINA": "U/L",
    "HIERRO_SERICO": "ug/dL",
    "FERRITINA": "ng/mL",
    "TRANSFERRINA": "mg/dL",
    "SAT_TRANSFERRINA": "%",
    "PTH": "pg/mL",
}


@dataclass
class NormalizedResult:
    campo_sairc: str
    analisis_original: str | None
    resultado_original: str | None
    valor_normalizado: str | None
    valor_numerico: float | None
    unidad: str | None
    rango: str | None
    confianza: str | None
    estado_lectura: str | None
    estado_control: str
    usar_en_sairc: str
    severidad: str | None
    motivo_revision: str | None
    estado_produccion: str = "OK_CARGABLE"
    puede_cargarse_sairc: str = "SI"
    motivo_bloqueo: str | None = None
    interpretacion_textual: str | None = None
    indice_numerico: float | None = None


CONFUSABLES_TRANS = str.maketrans(
    {
        # Letras griegas/cirílicas que Gemini/OCR puede devolver en nombres de análisis.
        "Α": "A",
        "А": "A",
        "Β": "B",
        "В": "B",
        "Ε": "E",
        "Е": "E",
        "Ζ": "Z",
        "Η": "H",
        "Ι": "I",
        "І": "I",
        "Κ": "K",
        "К": "K",
        "Μ": "M",
        "М": "M",
        "Ν": "N",
        "О": "O",
        "Ο": "O",
        "Ρ": "P",
        "Р": "P",
        "Τ": "T",
        "Т": "T",
        "Υ": "Y",
        "Х": "X",
        "Χ": "X",
        "α": "a",
        "а": "a",
        "β": "b",
        "в": "b",
        "ε": "e",
        "е": "e",
        "ι": "i",
        "і": "i",
        "ν": "n",
        "ο": "o",
        "о": "o",
        "ρ": "p",
        "р": "p",
        "τ": "t",
        "х": "x",
        "χ": "x",
    }
)


def normalize_confusables(text: Any) -> str:
    return str(text).translate(CONFUSABLES_TRANS)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def norm_text(text: Any) -> str:
    if text is None:
        return ""
    text = strip_accents(normalize_confusables(text)).upper()
    text = re.sub(r"[^A-Z0-9%/().,<>:=+\-\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


SPANISH_MONTHS = {
    name: month for month, names in enumerate(
        ("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"), 1
    ) for name in names.split()
}


def standardize_date(d_str: Any) -> str | None:
    if not d_str:
        return None
    s = str(d_str).strip()
    # Si es solo una hora (HH:MM:SS o HH:MM), descartar
    if re.match(r"^\d{1,2}:\d{2}(?::\d{2})?$", s):
        return None
    iso = re.search(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", s)
    numeric = re.search(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?!\d)", s)
    natural = re.search(r"(?i)\b(\d{1,2})\s+(?:DE\s+)?([A-ZÁÉÍÓÚÑ]+)\s+(?:(?:DE|DEL)\s+)?(\d{4})\b", s)
    if iso:
        year, month, day = map(int, iso.groups())
    elif numeric:
        day, month, year = map(int, numeric.groups())
        if len(numeric.group(3)) == 2:
            year += 2000 if year <= 40 else 1900
    elif natural:
        day, year = int(natural.group(1)), int(natural.group(3))
        month = SPANISH_MONTHS.get(natural.group(2).upper(), 0)
    else:
        return None
    try:
        return date(year, month, day).strftime("%d/%m/%Y")
    except ValueError:
        return None


def standardize_laboratory(lab_str: Any) -> str | None:
    if not lab_str:
        return None
    s = str(lab_str).upper()
    aliases = (
        (("MULTISERVICIOS",), "MULTISERVICIOS"),
        (("SUIZA",), "SUIZA LAB"),
        (("ROE",), "LABORATORIOS ROE"),
        (("ANGAMOS",), "ANGAMOS"),
        (("CORLAB",), "CORLABS"),
        (("HYS",), "HYS"),
        (("ROCHEM",), "ROCHEM"),
        (("VIDALAB",), "VIDALAB"),
        (("SYNLAB",), "SYNLAB PERU S.A.C."),
        (("DEKALAB",), "DEKALAB"),
        (("SANDHOR",), "SANDHOR LABS"),
        (("PREVENIR",), "PREVENIR"),
        (("SKIN", "LAB"), "SKIN LAB"),
        (("METROLAB",), "METROLAB"),
        (("YJ", "MEDICAL"), "YJ MEDICAL"),
        (("LIMA", "LAB"), "LIMA LAB"),
        (("SEI", "SALUD"), "SEI SALUD"),
        (("SYRC",), "SYRC LAB"),
        (("CEDIALAB",), "CEDIALAB"),
        (("MELO",), "MELO"),
        (("LIGA", "LAB"), "LIGA LAB"),
        (("SAN FERNANDO",), "SAN FERNANDO"),
        (("CLASAM",), "CLASAM"),
        (("NORTH", "LAB"), "NORTH LAB"),
        (("SU SALUD",), "SU SALUD"),
        (("RENAIS",), "RENAIS"),
        (("SELVA AMAZONICA",), "SELVA AMAZONICA"),
        (("JUAN PABLO",), "JUAN PABLO II"),
        (("TACNA",), "TACNA"),
        (("RENAL CARE",), "RENAL CARE"),
        (("CABEMA",), "CABEMA"),
        (("CONSALUD",), "CONSALUD"),
        (("ESCALAB",), "ESCALABS"),
        (("UNILAB",), "UNILABS"),
    )
    for needles, canonical in aliases:
        if all(needle in s for needle in needles):
            return canonical
    return s.strip()


INVALID_DOC_KEYWORDS = (
    "CUI",
    "RENIPRESS",
    "RENAES",
    "RUC",
    "NO IDENTIFICADO",
    "NO DISPONIBLE",
    "NO ESPECIFICADO",
    "NO SE IDENTIFICA",
    "NO FIGURA",
    "NO VISIBLE",
    "EXPLICITO",
    "EXPLÍCITO",
    "LABORATORIO",
    "SEI SALUD",
    "CLINICA",
    "ORDEN",
    "HISTORIA",
    "TELEFONO",
    "COLEGIATURA",
    "CMP",
)


def normalize_doc(doc: Any) -> str | None:
    if doc is None:
        return None
    s = str(doc).strip()
    if not s:
        return None
    s_upper = s.upper()
    if any(kw in s_upper for kw in INVALID_DOC_KEYWORDS):
        return None
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    # Si contiene 11 dígitos y empieza con 10, 15, 17 o 20 es un RUC institucional
    if len(digits) == 11 and digits.startswith(("10", "15", "17", "20")):
        return None
    return digits


def document_from_pdf_name(ruta_relativa: str) -> str | None:
    if not ruta_relativa:
        return None
    name = str(ruta_relativa).replace("\\", "/").split("/")[-1]
    stem = name.rsplit(".", 1)[0]
    m = re.match(r"^([0-9]{6,12})(?=_REA_|[_-])", stem, flags=re.I)
    if m:
        return m.group(1)
    m = re.match(r"^([0-9]{6,12})", stem)
    return m.group(1) if m else None


def compare_documents(doc_file: str | None, doc_pdf: Any) -> str:
    state = identity_state(doc_file, doc_pdf)["coincidencia_documento"]
    return state


def identity_state(doc_file: str | None, doc_pdf: Any, detected_docs: list[Any] | None = None) -> dict:
    a = normalize_doc(doc_file)
    b = normalize_doc(doc_pdf)
    docs = []
    for x in detected_docs or []:
        nx = normalize_doc(x)
        if nx and nx not in docs:
            docs.append(nx)
    if not a and not b:
        return {
            "coincidencia_documento": "NO_DETECTADO",
            "estado_identidad": "REVISAR_SIN_DOCUMENTO",
            "requiere_verificacion_humana": "SI",
            "puede_cargarse_sairc": "NO",
            "motivo_identidad": "documento_archivo_y_pdf_no_detectados",
            "documentos_detectados": ", ".join(docs) or None,
        }
    if not a:
        return {
            "coincidencia_documento": "SIN_DOC_ARCHIVO",
            "estado_identidad": "REVISAR_SIN_DOCUMENTO_ARCHIVO",
            "requiere_verificacion_humana": "SI",
            "puede_cargarse_sairc": "NO",
            "motivo_identidad": "documento_archivo_no_detectado",
            "documentos_detectados": ", ".join(docs) or None,
        }
    if not b:
        return {
            "coincidencia_documento": "SIN_DOC_OCR",
            "estado_identidad": "REVISAR_SIN_DOCUMENTO_PDF",
            "requiere_verificacion_humana": "SI",
            "puede_cargarse_sairc": "NO",
            "motivo_identidad": "documento_pdf_no_detectado",
            "documentos_detectados": ", ".join(docs) or None,
        }
    if a == b:
        return {
            "coincidencia_documento": "SI",
            "estado_identidad": "OK_IDENTIDAD",
            "requiere_verificacion_humana": "NO",
            "puede_cargarse_sairc": "SI",
            "motivo_identidad": None,
            "documentos_detectados": ", ".join(docs) or None,
        }
    if a.lstrip("0") == b.lstrip("0") and a.lstrip("0"):
        return {
            "coincidencia_documento": "SI_NORMALIZADO",
            "estado_identidad": "OK_IDENTIDAD_NORMALIZADA",
            "requiere_verificacion_humana": "NO",
            "puede_cargarse_sairc": "SI",
            "motivo_identidad": "coincide_quitando_ceros_izquierda",
            "documentos_detectados": ", ".join(docs) or None,
        }
    # Coincidir solo por ultimos 8 digitos es una pista, no autorizacion de carga.
    if len(a) >= 8 and len(b) >= 8 and a[-8:] == b[-8:]:
        return {
            "coincidencia_documento": "SI_ULTIMOS_8",
            "estado_identidad": "REVISAR_IDENTIDAD_ULTIMOS_8",
            "requiere_verificacion_humana": "SI",
            "puede_cargarse_sairc": "NO",
            "motivo_identidad": "coincide_solo_por_ultimos_8_digitos",
            "documentos_detectados": ", ".join(docs) or None,
        }
    return {
        "coincidencia_documento": "NO",
        "estado_identidad": "NO_CARGABLE_IDENTIDAD",
        "requiere_verificacion_humana": "SI",
        "puede_cargarse_sairc": "NO",
        "motivo_identidad": "dni_pdf_no_coincide_con_nombre_archivo",
        "documentos_detectados": ", ".join(docs) or None,
    }


def _append_reason(original: str | None, extra: str) -> str:
    return f"{original}; {extra}" if original else extra


def _unit_warning(field: str | None, unit: Any) -> str | None:
    if not field or field in QUALITATIVE_FIELDS or not unit:
        return None
    u = norm_text(unit).replace(" ", "")
    expected = UNITS_DEFAULT.get(field)
    if not expected:
        return None
    e = norm_text(expected).replace(" ", "")
    equivalents = {
        "UG/DL": {"UG/DL", "MCG/DL", "ΜG/DL"},
        "MMOL/L": {"MMOL/L", "MEQ/L", "UMOL/L"},  # algunos laboratorios imprimen umol/L para electrolitos aunque el valor es mmol/L
        "U/L": {"U/L", "UI/L", "IU/L", "U/I"},
        "G/DL": {"G/DL", "GR/DL"},
        "MG/DL": {"MG/DL", "GR%"},
        "NG/ML": {"NG/ML"},
        "PG/ML": {"PG/ML"},
    }
    allowed = equivalents.get(e, {e})
    if any(a in u for a in allowed):
        return None
    if field == "HEMOGLOBINA" and "G/L" in u and "G/DL" not in u:
        return "unidad_hemoglobina_g_l_validar_conversion_a_g_dl"
    if field in {"CALCIO", "FOSFORO"} and "MMOL/L" in u:
        return f"unidad_{field.lower()}_mmol_l_validar_conversion"
    if field == "ALBUMINA" and "MG/DL" in u:
        return "unidad_albumina_mg_dl_sospechosa_validar_si_corresponde_g_dl"
    if field == "HIERRO_SERICO" and "UG/L" in u:
        return "unidad_hierro_ug_l_validar_si_laboratorio_quiso_ug_dl"
    return f"unidad_no_esperada_{unit}_esperada_{expected}"


def detect_fields(analysis: Any) -> list[str]:
    s = norm_text(analysis)
    if not s or "CALCIO IONICO" in s:
        return []
    fields: list[str] = []
    for pattern, field in ALIASES:
        if re.search(pattern, s) and field not in fields:
            fields.append(field)
    if "UREA_POST" in fields and "UREA_PRE" in fields and not re.search(r"\bPRE\b|ANTES", s) and s.count("UREA") == 1:
        fields.remove("UREA_PRE")
    return fields


def detect_field(analysis: Any) -> str | None:
    fields = detect_fields(analysis)
    return fields[0] if fields else None


NUMERIC_TOKEN_PATTERN = r"[-+]?(?:\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
NUMERIC_EXPRESSION_PATTERN = rf"{NUMERIC_TOKEN_PATTERN}(?:\s*(?:-|–|—|\bA\b)\s*{NUMERIC_TOKEN_PATTERN})?"


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).replace("\u00a0", " ").strip()
    if not s:
        return None
    m = re.search(NUMERIC_TOKEN_PATTERN, s.replace("*", ""))
    if not m:
        return None
    token = re.sub(r"\s+", "", m.group(0))
    if "," in token and "." in token:
        # El último separador es el decimal; el otro corresponde a millares.
        if token.rfind(".") > token.rfind(","):
            token = token.replace(",", "")
        else:
            token = token.replace(".", "").replace(",", ".")
    else:
        token = token.replace(",", ".")
    try:
        return float(token)
    except Exception:
        return None


def numeric_expression_kind(value: Any) -> str | None:
    """Detecta expresiones que no representan un valor cuantitativo exacto."""
    if value is None:
        return None
    text = str(value).strip().lstrip("* ")
    if re.match(r"^(?:<|>|<=|>=|≤|≥)", text):
        return "comparador"
    if re.match(rf"^{NUMERIC_TOKEN_PATTERN}\s*(?:-|–|—|\bA\b)\s*{NUMERIC_TOKEN_PATTERN}(?:\s+[A-Zµμ%/]+)?$", text, flags=re.I):
        return "intervalo"
    return None


def qualitative_interpretation(text: Any) -> str | None:
    s = norm_text(text)
    if not s:
        return None
    # Orden importante: NO REACTIVO antes de REACTIVO.
    patterns = [
        ("NO REACTIVO", "NO REACTIVO"),
        ("NOREACTIVO", "NO REACTIVO"),
        ("NEGATIVO", "NEGATIVO"),
        ("INDETERMINADO", "INDETERMINADO"),
        ("REACTIVO", "REACTIVO"),
        ("POSITIVO", "POSITIVO"),
        ("NO INMUNIZADO", "NO INMUNIZADO"),
        ("NOINMUNIZADO", "NO INMUNIZADO"),
        ("INMUNIZADO", "INMUNIZADO"),
    ]
    for needle, out in patterns:
        if needle in s:
            return out
    return None


def interpret_from_reference(field: str, result: Any, rango: Any) -> str | None:
    if field not in QUALITATIVE_FIELDS:
        return None
    text_interp = qualitative_interpretation(result)
    if text_interp:
        return text_interp
    n = parse_float(result)
    if field == "ANTI_HBS" and n is not None:
        return None  # Conservar el título cuantitativo, sin reemplazarlo por una interpretación.
    r = norm_text(str(rango or "").replace("≥", ">=").replace("≤", "<="))
    if n is None or not r:
        return None
    # Reglas frecuentes de serología. Conservadoras: si no se entiende, no interpreta.
    if any(x in r for x in ["NEGATIVO", "NO REACTIVO"]) and any(x in r for x in ["POSITIVO", "REACTIVO"]):
        # Caso: POSITIVO >= 1.0 / NEGATIVO < 1.0
        one = r"1(?:[.,]0+)?(?!\d|[.,]\d)"
        if re.search(rf"(?<!NO )\b(POSITIVO|REACTIVO)\b[^<>]*>=\s*{one}", r) and re.search(rf"\b(NEGATIVO|NO REACTIVO)\b[^<>]*<\s*{one}", r):
            return "REACTIVO" if n >= 1.0 else "NO REACTIVO"
        # Caso Anti-HBc: POSITIVO <= 1 / NEGATIVO > 1
        if re.search(rf"(?<!NO )\b(POSITIVO|REACTIVO)\b[^<>]*<=\s*{one}", r) and re.search(rf"\b(NEGATIVO|NO REACTIVO)\b[^<>]*>\s*{one}", r):
            return "REACTIVO" if n <= 1.0 else "NO REACTIVO"
    return None


def is_non_result(value: Any) -> bool:
    text = norm_text(value).replace("_", " ")
    return not text or text in {"SIN RESULTADO", "SIN DATO", "NO REALIZADO", "PENDIENTE", "ILEGIBLE", "NO DISPONIBLE", "N/A"} or bool(re.search(r"\b(?:ESTADO INMUNE|RANGO|REFERENCIA)\b", text)) or bool(re.fullmatch(r"(?:G|MG|UG|NG|PG|UI|U|IU|MMOL|NMOL|MUI)/(?:DL|L|ML)|%", text))


def result_has_readable_value(item: dict) -> bool:
    value = item.get("resultado")
    if is_non_result(value):
        return False
    return detect_field(item.get("analisis")) not in PLAUSIBLE_RANGES or parse_float(value) is not None


def normalize_result_value(field: str, result: Any, rango: Any = None) -> tuple[str | None, float | None, str | None]:
    if result is None:
        return None, None, None
    s = re.sub(r"\s+", " ", str(result)).strip()
    if not s:
        return None, None, None
    if is_non_result(s):
        return None, None, None
    if field in QUALITATIVE_FIELDS:
        interp = interpret_from_reference(field, s, rango)
        idx = parse_float(s)
        if interp:
            return interp, idx, interp
        # Si solo hay índice sin interpretación, mantener número pero marcará revisión.
    num = parse_float(s)
    if field in PLAUSIBLE_RANGES and numeric_expression_kind(s):
        preserved = re.sub(r"(?<=\d),(?=\d)", ".", s)
        return preserved, num, None
    if num is not None:
        return f"{num:.4f}".rstrip("0").rstrip("."), num, None
    return s, None, None


def classify(
    field: str | None, value_norm: str | None, num: float | None, item: dict
) -> tuple[str, str, str | None, str | None, str, str, str | None]:
    # estado_control, usar_en_sairc, severidad, motivo, estado_produccion, puede_cargarse, motivo_bloqueo
    if not field:
        return "REVISAR", "NO", "MEDIA", "analisis_no_mapeado_a_sairc", "SAIRC_REVISION", "NO", "analisis_no_mapeado"
    if value_norm in (None, ""):
        return "REVISAR", "NO", "MEDIA", "resultado_vacio", "SAIRC_REVISION", "NO", "resultado_vacio"
    expression_kind = numeric_expression_kind(item.get("resultado"))
    if field in PLAUSIBLE_RANGES and expression_kind:
        reason = f"resultado_cuantitativo_con_{expression_kind}"
        return "REVISAR", "REVISAR", "ALTA", reason, "SAIRC_REVISION", "NO", reason
    lectura = norm_text(item.get("estado_lectura"))
    confianza = norm_text(item.get("confianza"))
    warnings = []
    if lectura in {"DUDOSO", "ILEGIBLE"}:
        warnings.append("estado_lectura_dudoso")
    if confianza == "BAJA":
        warnings.append("confianza_baja")

    if field in PLAUSIBLE_RANGES and num is None:
        return "REVISAR", "REVISAR", "ALTA", "resultado_no_numerico_en_examen_cuantitativo", "SAIRC_REVISION", "NO", "resultado_no_numerico"
    if field in PLAUSIBLE_RANGES and num is not None:
        lo, hi = PLAUSIBLE_RANGES[field]
        if not (lo <= num <= hi):
            return (
                "REVISAR",
                "REVISAR",
                "ALTA",
                f"valor_improbable_hemodialisis_{lo}_{hi}",
                "SAIRC_REVISION",
                "NO",
                f"valor_improbable_{field.lower()}",
            )
        alo, ahi = ALERT_RANGES_HD.get(field, (None, None))
        if alo is not None and not (alo <= num <= ahi):
            warnings.append(f"alerta_clinica_hd_{field.lower()}_fuera_{alo}_{ahi}")

    if field in QUALITATIVE_FIELDS:
        s = norm_text(value_norm)
        # Anti-HBs puede informarse como interpretación o como título cuantitativo
        # (mUI/mL). Ambos formatos son clínicamente válidos y se cargan sin inventar
        # una interpretación cuando el laboratorio no aporta el punto de corte.
        anti_hbs_quantitative = field == "ANTI_HBS" and num is not None
        if not anti_hbs_quantitative and not any(
            x in s for x in ["NO REACTIVO", "NEGATIVO", "REACTIVO", "POSITIVO", "INDETERMINADO", "INMUNIZADO", "NO INMUNIZADO"]
        ):
            return (
                "REVISAR",
                "REVISAR",
                "MEDIA",
                "serologia_sin_interpretacion_textual",
                "SAIRC_REVISION",
                "NO",
                "serologia_requiere_interpretacion",
            )

    if warnings:
        return "OK_CON_REGLA", "SI_CON_ALERTA", "BAJA", "; ".join(warnings), "OK_CON_ALERTA_CLINICA", "SI", None
    return "OK", "SI", None, None, "OK_CARGABLE", "SI", None


def choose_best(existing: NormalizedResult | None, candidate: NormalizedResult) -> NormalizedResult:
    if existing is None:
        return candidate
    rank = {"OK": 4, "OK_CON_REGLA": 3, "REVISAR": 2, "ERROR": 0}
    if rank.get(candidate.estado_control, 0) > rank.get(existing.estado_control, 0):
        return candidate
    if candidate.valor_numerico is not None and existing.valor_numerico is None:
        return candidate
    return existing


def _mark_result_blocked(nr: NormalizedResult, reason: str, state: str = "SAIRC_REVISION", severity: str = "ALTA") -> None:
    nr.estado_control = "REVISAR"
    nr.usar_en_sairc = "REVISAR"
    nr.severidad = severity
    nr.motivo_revision = _append_reason(nr.motivo_revision, reason)
    nr.estado_produccion = state
    nr.puede_cargarse_sairc = "NO"
    nr.motivo_bloqueo = _append_reason(nr.motivo_bloqueo, reason)


def apply_cross_checks(by_field: dict[str, NormalizedResult]) -> list[str]:
    reasons: list[str] = []
    pre = by_field.get("UREA_PRE")
    post = by_field.get("UREA_POST")
    if pre and post and pre.valor_numerico is not None and post.valor_numerico is not None:
        if post.valor_numerico >= pre.valor_numerico:
            reason = "urea_post_mayor_o_igual_urea_pre"
            _mark_result_blocked(pre, reason)
            _mark_result_blocked(post, reason)
            reasons.append(reason)
    sodio = by_field.get("SODIO")
    if sodio and sodio.valor_numerico is not None and sodio.valor_numerico < 100:
        reason = "sodio_incompatible_con_hemodialisis_posible_cruce_tabla"
        _mark_result_blocked(sodio, reason)
        reasons.append(reason)
    transf = by_field.get("TRANSFERRINA")
    ferr = by_field.get("FERRITINA")
    if transf and ferr and transf.valor_numerico is not None and ferr.valor_numerico is not None:
        if abs(transf.valor_numerico - ferr.valor_numerico) < 0.01 and transf.valor_numerico > 600:
            reason = "transferrina_igual_a_ferritina_posible_arrastre_de_valor"
            _mark_result_blocked(transf, reason)
            reasons.append(reason)
    hb = by_field.get("HEMOGLOBINA")
    hto = by_field.get("HEMATOCRITO")
    if hb and hto and hb.valor_numerico is not None and hto.valor_numerico is not None and hb.valor_numerico > 0:
        ratio = hto.valor_numerico / hb.valor_numerico
        if ratio < 2.0 or ratio > 4.2:
            reason = "hemoglobina_hematocrito_relacion_inusual_validar"
            hb.estado_control = "OK_CON_REGLA" if hb.estado_control == "OK" else hb.estado_control
            hto.estado_control = "OK_CON_REGLA" if hto.estado_control == "OK" else hto.estado_control
            hb.usar_en_sairc = "SI_CON_ALERTA" if hb.usar_en_sairc == "SI" else hb.usar_en_sairc
            hto.usar_en_sairc = "SI_CON_ALERTA" if hto.usar_en_sairc == "SI" else hto.usar_en_sairc
            hb.motivo_revision = _append_reason(hb.motivo_revision, reason)
            hto.motivo_revision = _append_reason(hto.motivo_revision, reason)
            hb.estado_produccion = hto.estado_produccion = "OK_CON_ALERTA_CLINICA"
            reasons.append(reason)
    return reasons


_NUMERIC_CAPTURE = r"[-+]?\d+(?:[.,]\d+)?"
_UREA_COMBINED_PATTERNS = (
    re.compile(
        rf"(?P<pre>{_NUMERIC_CAPTURE})\s*\(?\s*PRE(?:\s*(?:DIALISIS|HEMODIALISIS))?\s*\)?"
        rf"\s*[/;|]\s*(?P<post>{_NUMERIC_CAPTURE})\s*\(?\s*POS(?:T)?(?:\s*(?:DIALISIS|HEMODIALISIS))?\s*\)?",
        re.IGNORECASE,
    ),
    re.compile(
        rf"PRE(?:\s*(?:DIALISIS|HEMODIALISIS))?\s*[:=]?\s*(?P<pre>{_NUMERIC_CAPTURE})"
        rf"\s*[/;|]\s*POS(?:T)?(?:\s*(?:DIALISIS|HEMODIALISIS))?\s*[:=]?\s*(?P<post>{_NUMERIC_CAPTURE})",
        re.IGNORECASE,
    ),
)


def expand_combined_results(results: Any) -> list[dict]:
    """Separa resultados inequívocos que contienen UREA pre y post en una sola celda."""
    expanded: list[dict] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        name = item.get("analisis")
        value = item.get("resultado")
        match = None
        if detect_field(name) in {"UREA_PRE", "UREA_POST"} and value is not None:
            text = strip_accents(str(value))
            for pattern in _UREA_COMBINED_PATTERNS:
                match = pattern.search(text)
                if match:
                    break
        if not match:
            expanded.append(item)
            continue
        for field, group in (("UREA_PRE", "pre"), ("UREA_POST", "post")):
            split_item = dict(item)
            split_item["resultado"] = match.group(group)
            split_item["_campo_sairc_forzado"] = field
            split_item["_resultado_original_combinado"] = value
            expanded.append(split_item)
    return expanded


def normalize_ai_output(data: dict, ruta_relativa: str = "", carpeta_origen: str = "") -> dict:
    results_raw = expand_combined_results(data.get("resultados") or [])
    normalized_rows: list[dict] = []
    by_field: dict[str, NormalizedResult] = {}
    urea_unlabeled: list[NormalizedResult] = []

    for item in results_raw:
        if not isinstance(item, dict):
            continue
        original_name = item.get("analisis")
        field = item.get("_campo_sairc_forzado") or detect_field(original_name)
        val_norm, num, interp = normalize_result_value(field or "", item.get("resultado"), item.get("rango_referencia"))
        unit = item.get("unidades") or (UNITS_DEFAULT.get(field or "") if field else None)
        estado, usar, sev, motivo, estado_prod, puede_cargar, motivo_bloqueo = classify(field, val_norm, num, item)
        nr = NormalizedResult(
            campo_sairc=field or "NO_MAPEADO",
            analisis_original=original_name,
            resultado_original=item.get("_resultado_original_combinado", item.get("resultado")),
            valor_normalizado=val_norm,
            valor_numerico=num,
            unidad=unit,
            rango=item.get("rango_referencia"),
            confianza=item.get("confianza"),
            estado_lectura=item.get("estado_lectura"),
            estado_control=estado,
            usar_en_sairc=usar,
            severidad=sev,
            motivo_revision=motivo,
            estado_produccion=estado_prod,
            puede_cargarse_sairc=puede_cargar,
            motivo_bloqueo=motivo_bloqueo,
            interpretacion_textual=interp,
            indice_numerico=num if field in QUALITATIVE_FIELDS else None,
        )
        unit_warn = _unit_warning(field, unit)
        if unit_warn:
            nr.estado_control = "OK_CON_REGLA" if nr.estado_control == "OK" else nr.estado_control
            nr.usar_en_sairc = "SI_CON_ALERTA" if nr.usar_en_sairc == "SI" else nr.usar_en_sairc
            nr.severidad = nr.severidad or "MEDIA"
            nr.motivo_revision = _append_reason(nr.motivo_revision, unit_warn)
            nr.estado_produccion = "OK_CON_ALERTA_CLINICA" if nr.estado_produccion == "OK_CARGABLE" else nr.estado_produccion
        if field == "UREA_PRE" and original_name and "POST" not in norm_text(original_name) and "PRE" not in norm_text(original_name):
            urea_unlabeled.append(nr)
        if field:
            by_field[field] = choose_best(by_field.get(field), nr)
        normalized_rows.append(nr.__dict__.copy())

    if len(urea_unlabeled) >= 2:
        vals = [u for u in urea_unlabeled if u.valor_numerico is not None]
        if len(vals) >= 2:
            vals = sorted(vals, key=lambda x: x.valor_numerico or 0, reverse=True)
            if "UREA_PRE" not in by_field:
                vals[0].campo_sairc = "UREA_PRE"
                vals[0].estado_control = "OK_CON_REGLA"
                vals[0].usar_en_sairc = "SI_CON_ALERTA"
                vals[0].severidad = vals[0].severidad or "MEDIA"
                vals[0].motivo_revision = _append_reason(vals[0].motivo_revision, "urea_pre_asignada_por_magnitud")
                vals[0].estado_produccion = "OK_CON_ALERTA_CLINICA"
                by_field["UREA_PRE"] = vals[0]
            if "UREA_POST" not in by_field:
                vals[-1].campo_sairc = "UREA_POST"
                vals[-1].estado_control = "OK_CON_REGLA"
                vals[-1].usar_en_sairc = "SI_CON_ALERTA"
                vals[-1].severidad = vals[-1].severidad or "MEDIA"
                vals[-1].motivo_revision = _append_reason(vals[-1].motivo_revision, "urea_post_asignada_por_magnitud")
                vals[-1].estado_produccion = "OK_CON_ALERTA_CLINICA"
                by_field["UREA_POST"] = vals[-1]

    cross_reasons = apply_cross_checks(by_field)

    # refresca normalized_rows con resultados finales por campo si fueron modificados por cross-checks
    normalized_rows = [r.__dict__.copy() for r in by_field.values()] + [r for r in normalized_rows if r.get("campo_sairc") == "NO_MAPEADO"]

    sairc = {field: None for field in SAIRC_FIELDS}
    sairc_estado = {f"{field}_estado": None for field in SAIRC_FIELDS}
    sairc_motivo = {f"{field}_motivo": None for field in SAIRC_FIELDS}
    for field, nr in by_field.items():
        if field in sairc and nr.usar_en_sairc in {"SI", "SI_CON_ALERTA", "REVISAR"}:
            sairc[field] = nr.valor_normalizado
            sairc_estado[f"{field}_estado"] = nr.estado_control
            sairc_motivo[f"{field}_motivo"] = nr.motivo_revision

    raw_pru = by_field.get("PRU")
    pru = sairc.get("PRU")
    pru_estado = sairc_estado.get("PRU_estado")
    pru_motivo = sairc_motivo.get("PRU_motivo")
    pru_estado_prod = raw_pru.estado_produccion if raw_pru else "OK_CARGABLE"
    pru_puede = raw_pru.puede_cargarse_sairc if raw_pru else "SI"
    pre = by_field.get("UREA_PRE")
    post = by_field.get("UREA_POST")
    if pre and post and pre.valor_numerico is not None and post.valor_numerico is not None and pre.valor_numerico > 0:
        pru_val = ((pre.valor_numerico - post.valor_numerico) / pre.valor_numerico) * 100
        pru = round(pru_val, 2)
        if post.valor_numerico >= pre.valor_numerico or pru_val < 20 or pru_val > 90:
            pru_estado = "REVISAR"
            pru_motivo = "pru_fuera_de_rango_hd_o_urea_inconsistente"
            pru_estado_prod = "SAIRC_REVISION"
            pru_puede = "NO"
        elif pru_val < 65:
            pru_estado = "OK_CON_REGLA"
            pru_motivo = "pru_bajo_alerta_clinica_hd"
            pru_estado_prod = "OK_CON_ALERTA_CLINICA"
        else:
            pru_estado = "OK"
        pru_estado_prod = "OK_CARGABLE" if pru_estado == "OK" else pru_estado_prod
        pru_puede = "SI" if pru_estado != "REVISAR" else "NO"
    sairc["PRU"] = pru
    sairc_estado["PRU_estado"] = pru_estado
    sairc_motivo["PRU_motivo"] = pru_motivo

    missing_basic = [f for f in BASIC_FIELDS if not sairc.get(f)]
    documento_archivo_pdf = document_from_pdf_name(ruta_relativa)
    raw_doc = data.get("documento_identidad")
    documento = normalize_doc(raw_doc) or documento_archivo_pdf
    detected_docs = data.get("documentos_detectados") or data.get("documentos_posibles") or []
    if isinstance(detected_docs, str):
        detected_docs = [detected_docs]
    ident = identity_state(documento_archivo_pdf, documento, detected_docs)

    review_rows = [r for r in normalized_rows if r.get("estado_control") == "REVISAR" or r.get("puede_cargarse_sairc") == "NO"]
    if ident["puede_cargarse_sairc"] == "NO":
        estado_archivo = "NO_CARGABLE_IDENTIDAD"
        puede_archivo = "NO"
        requiere_revision = "SI"
        motivo_bloqueo_archivo = ident["motivo_identidad"]
    elif review_rows:
        estado_archivo = "SAIRC_REVISION"
        puede_archivo = "NO"
        requiere_revision = "SI"
        motivo_bloqueo_archivo = "resultados_con_revision_critica"
    elif len(missing_basic) >= 3:
        estado_archivo = "SAIRC_REVISION"
        puede_archivo = "NO"
        requiere_revision = "SI"
        motivo_bloqueo_archivo = "faltan_examenes_basicos"
    elif missing_basic:
        estado_archivo = "OK_CON_ALERTA_CLINICA"
        puede_archivo = "SI"
        requiere_revision = "NO"
        motivo_bloqueo_archivo = None
    else:
        has_alert = any(r.get("estado_control") == "OK_CON_REGLA" for r in normalized_rows) or pru_estado == "OK_CON_REGLA"
        estado_archivo = "OK_CON_ALERTA_CLINICA" if has_alert else "OK_CARGABLE"
        puede_archivo = "SI"
        requiere_revision = "NO"
        motivo_bloqueo_archivo = None

    # Si la identidad falla, bloquea todos los registros SAIRC a nivel producción sin borrar valores.
    if ident["puede_cargarse_sairc"] == "NO":
        for r in normalized_rows:
            r["estado_produccion"] = "NO_CARGABLE_IDENTIDAD"
            r["puede_cargarse_sairc"] = "NO"
            r["motivo_bloqueo"] = _append_reason(r.get("motivo_bloqueo"), ident["motivo_identidad"] or "identidad_no_valida")

    header = {
        "ruta_relativa": ruta_relativa,
        "carpeta_origen": carpeta_origen,
        "archivo": ruta_relativa.split("/")[-1] if ruta_relativa else None,
        "documento_archivo_pdf": documento_archivo_pdf,
        "documento_archivo_normalizado": normalize_doc(documento_archivo_pdf),
        "paciente": data.get("paciente_nombre"),
        "documento_identidad": documento,
        "documento_pdf_normalizado": normalize_doc(documento),
        **ident,
        "edad": data.get("edad"),
        "sexo": data.get("sexo"),
        "laboratorio": standardize_laboratory(data.get("laboratorio")),
        "fecha_examen": standardize_date(data.get("fecha_examen")) or standardize_date(data.get("fecha_toma_muestra")) or standardize_date(data.get("fecha_emision")),
        "fecha_toma_muestra": standardize_date(data.get("fecha_toma_muestra")) or standardize_date(data.get("fecha_examen")) or standardize_date(data.get("fecha_emision")),
        "fecha_emision": standardize_date(data.get("fecha_emision")),
        "firma": data.get("firma"),
        "firma_ctmp": data.get("firma_ctmp"),
        "estado_archivo": estado_archivo,
        "puede_cargarse_sairc": puede_archivo,
        "requiere_verificacion_identidad": ident.get("requiere_verificacion_humana") or "NO",
        "requiere_verificacion_resultados": "SI" if requiere_revision == "SI" else "NO",
        "requiere_verificacion_humana": "SI" if requiere_revision == "SI" or ident.get("requiere_verificacion_humana") == "SI" else "NO",
        "motivo_bloqueo_archivo": motivo_bloqueo_archivo,
        "resultados_extraidos": len(results_raw),
        "resultados_normalizados": len([r for r in normalized_rows if r.get("campo_sairc") != "NO_MAPEADO"]),
        "resultados_revisar": len(review_rows),
        "sugerencia_llm": "SI"
        if len(normalized_rows) < 3
        or len(review_rows) >= 2
        or len([r for r in normalized_rows if r.get("campo_sairc") == "NO_MAPEADO"]) >= 2
        else "NO",
        "faltantes_basicos": ", ".join(missing_basic),
        "validaciones_cruzadas": "; ".join(cross_reasons) if cross_reasons else None,
    }
    sairc_row = {
        **header,
        **sairc,
        **sairc_estado,
        **sairc_motivo,
        "PRU_estado_produccion": pru_estado_prod,
        "PRU_puede_cargarse_sairc": pru_puede,
    }
    return {
        "cabecera": header,
        "resultados_normalizados": normalized_rows,
        "sairc": sairc_row,
        "pendientes": build_pending_rows(header, normalized_rows, missing_basic, pru_estado, pru_motivo),
    }


def build_pending_rows(
    header: dict, normalized_rows: list[dict], missing_basic: list[str], pru_estado: str | None, pru_motivo: str | None
) -> list[dict]:
    rows = []
    if header.get("estado_identidad") in {
        "NO_CARGABLE_IDENTIDAD",
        "REVISAR_SIN_DOCUMENTO_PDF",
        "REVISAR_DOCUMENTO_MULTIPLE",
        "REVISAR_SIN_DOCUMENTO",
        "REVISAR_IDENTIDAD_ULTIMOS_8",
    }:
        rows.append(
            {
                **{
                    k: header.get(k)
                    for k in [
                        "ruta_relativa",
                        "paciente",
                        "documento_archivo_pdf",
                        "documento_identidad",
                        "coincidencia_documento",
                        "laboratorio",
                        "estado_identidad",
                    ]
                },
                "examen": "IDENTIDAD",
                "analisis_original": None,
                "resultado_detectado": header.get("documento_identidad"),
                "valor_normalizado": None,
                "unidad": None,
                "motivo": header.get("motivo_identidad"),
                "severidad": "ALTA",
                "usar_en_sairc": "NO",
                "puede_cargarse_sairc": "NO",
                "estado_produccion": header.get("estado_archivo"),
            }
        )
    for r in normalized_rows:
        if r.get("estado_control") == "REVISAR" or r.get("puede_cargarse_sairc") == "NO":
            rows.append(
                {
                    **{
                        k: header.get(k)
                        for k in [
                            "ruta_relativa",
                            "paciente",
                            "documento_archivo_pdf",
                            "documento_identidad",
                            "coincidencia_documento",
                            "laboratorio",
                            "estado_identidad",
                        ]
                    },
                    "examen": r.get("campo_sairc"),
                    "analisis_original": r.get("analisis_original"),
                    "resultado_detectado": r.get("resultado_original"),
                    "valor_normalizado": r.get("valor_normalizado"),
                    "unidad": r.get("unidad"),
                    "motivo": r.get("motivo_revision") or r.get("motivo_bloqueo"),
                    "severidad": r.get("severidad") or "MEDIA",
                    "usar_en_sairc": r.get("usar_en_sairc"),
                    "puede_cargarse_sairc": r.get("puede_cargarse_sairc"),
                    "estado_produccion": r.get("estado_produccion"),
                }
            )
    for f in missing_basic:
        rows.append(
            {
                **{
                    k: header.get(k)
                    for k in [
                        "ruta_relativa",
                        "paciente",
                        "documento_archivo_pdf",
                        "documento_identidad",
                        "coincidencia_documento",
                        "laboratorio",
                        "estado_identidad",
                    ]
                },
                "examen": f,
                "analisis_original": None,
                "resultado_detectado": None,
                "valor_normalizado": None,
                "unidad": UNITS_DEFAULT.get(f),
                "motivo": "examen_basico_no_detectado",
                "severidad": "MEDIA",
                "usar_en_sairc": "NO",
                "puede_cargarse_sairc": "NO",
                "estado_produccion": "SAIRC_REVISION",
            }
        )
    if pru_estado == "REVISAR":
        rows.append(
            {
                **{
                    k: header.get(k)
                    for k in [
                        "ruta_relativa",
                        "paciente",
                        "documento_archivo_pdf",
                        "documento_identidad",
                        "coincidencia_documento",
                        "laboratorio",
                        "estado_identidad",
                    ]
                },
                "examen": "PRU",
                "analisis_original": "PRU calculado",
                "resultado_detectado": None,
                "valor_normalizado": None,
                "unidad": "%",
                "motivo": pru_motivo,
                "severidad": "ALTA",
                "usar_en_sairc": "REVISAR",
                "puede_cargarse_sairc": "NO",
                "estado_produccion": "SAIRC_REVISION",
            }
        )
    return rows

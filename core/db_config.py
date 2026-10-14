import os
import sys
import yaml
from pathlib import Path
from urllib.parse import quote_plus
from functools import lru_cache

def obtener_base_dir() -> Path:
    return Path(__file__).resolve().parents[1]

def obtener_ruta_config() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else obtener_base_dir()
    return Path(os.environ.get("LAB_EXTRACTOR_CONFIG", str(base / "config.yaml")))

@lru_cache(maxsize=1)
def cargar_config() -> dict:
    ruta = obtener_ruta_config()
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró archivo de configuración en {ruta}")
    with open(ruta, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def cfg(path: str, default=None):
    try:
        data = cargar_config()
    except (FileNotFoundError, ValueError):
        return default
        
    actual = data
    for parte in path.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return default
        actual = actual[parte]
    return actual

def construir_odbc_connection_string() -> str:
    sql = cfg("sql", {})
    driver = os.environ.get("LAB_EXTRACTOR_SQL_DRIVER", sql.get("driver", "ODBC Driver 17 for SQL Server"))
    server = os.environ.get("LAB_EXTRACTOR_SQL_SERVER", sql.get("server", ""))
    database = os.environ.get("LAB_EXTRACTOR_SQL_DATABASE", sql.get("database", ""))
    trust_cert = os.environ.get("LAB_EXTRACTOR_SQL_TRUST_CERT", "yes" if sql.get("trust_server_certificate", True) else "no")

    partes = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
        f"TrustServerCertificate={trust_cert}",
    ]

    trusted = os.environ.get("LAB_EXTRACTOR_SQL_TRUSTED_CONNECTION", "1" if sql.get("trusted_connection", True) else "0")
    if trusted.lower() in {"1", "true", "yes"}:
        partes.append("Trusted_Connection=yes")
    else:
        partes.append(f"UID={os.environ.get('LAB_EXTRACTOR_SQL_USERNAME', sql.get('username', ''))}")
        partes.append(f"PWD={os.environ.get('LAB_EXTRACTOR_SQL_PASSWORD', sql.get('password', ''))}")

    return ";".join(partes) + ";"

def construir_sqlalchemy_url() -> str:
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(construir_odbc_connection_string())}"

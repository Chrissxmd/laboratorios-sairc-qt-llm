import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from pathlib import Path
from core.db_config import construir_sqlalchemy_url, cfg, obtener_base_dir

def generar_referencia_sairc_sql(anio: int, mes: int, establecimiento_id: str = None, output_dir: str = None) -> str:
    """
    Se conecta a la BD, ejecuta la consulta de SAIRC y guarda el resultado en un CSV.
    Retorna la ruta del archivo generado.
    """
    # 1. Leer consulta
    sql_path = obtener_base_dir() / "sql" / "consulta_sairc.sql"
    if not sql_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo SQL en {sql_path}")
        
    with open(sql_path, "r", encoding="utf-8") as f:
        query_template = f.read()
        
    try:
        anio = int(anio)
        mes = int(mes)
        est_id = int(str(establecimiento_id).strip()) if establecimiento_id not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise ValueError("Año, mes y establecimiento deben ser valores enteros válidos.") from exc
    if not 2000 <= anio <= 2100:
        raise ValueError("El año debe estar entre 2000 y 2100.")
    if not 1 <= mes <= 12:
        raise ValueError("El mes debe estar entre 1 y 12.")
    if est_id is not None and est_id <= 0:
        raise ValueError("El establecimiento debe ser un entero positivo.")

    # 2. Conectar a BD
    engine = create_engine(construir_sqlalchemy_url())
    
    # 3. Ejecutar consulta parametrizada
    print(f"Ejecutando consulta para Año: {anio}, Mes: {mes}, Establecimiento: {est_id or 'TODOS'}...")
    try:
        with engine.connect() as connection:
            df = pd.read_sql(
                text(query_template),
                connection,
                params={"anio": anio, "mes": mes, "establecimiento_id": est_id},
            )
    finally:
        engine.dispose()
    
    # Limpiar saltos de línea y retornos de carro que rompen el CSV
    df = df.replace({r'\r': ' ', r'\n': ' '}, regex=True)
    
    # 4. Guardar resultado
    if output_dir:
        out_dir = Path(output_dir)
    else:
        carpeta_outputs = cfg("salidas.carpeta_outputs", "salidas")
        out_dir = obtener_base_dir() / carpeta_outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_filename = f"Referencia_SAIRC_{anio}_{mes}_{timestamp}.csv"
    out_path = out_dir / out_filename
    
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Archivo generado en: {out_path} con {len(df)} registros.")
    
    return str(out_path)

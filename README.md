# Auditoría SAIRC · Qt / lectura remota

Edición actual **10.0.7**: ejecutar/compartir `dist/10.0.7/AuditoriaSAIRC.exe`.

Mistral selecciona por defecto **Small 4 / Visión / mistral-small-2603**. Se retiraron los controles de comparación de tres modelos de la interfaz; los resultados históricos se conservan. La extracción remota sigue requiriendo autorización de envío.

## Revisión por PDF (10.0.7)

El Hito 4 compara el consolidado Hito 2 contra la referencia Hito 3. La cola reúne las diferencias de cada PDF, ordenadas por prioridad de revisión. Los registros sin PDF asociado permanecen como casos de excepción. El original ocupa inicialmente el 60 % de la zona de trabajo.

Selecciona un documento y un examen. Los valores originales del Hito 2 y del Hito 3 permanecen juntos en la tabla. Selecciona **Confirma Hito 2**, **Confirma Hito 3**, **Otro valor del PDF** o **No concluyente**; los dos últimos requieren motivo y el valor manual también requiere contenido. Se necesita PDF abierto y página de evidencia para confirmar. **Guardar y seguir** guarda inmediatamente, avanza al siguiente examen sin decisión y, al terminar el documento, al siguiente caso pendiente. Un caso con varias diferencias solo se completa al resolver todas; los derivados se cuentan aparte. **Reabrir** y **Deshacer** conservan el historial.

**Filtros…** permite escoger IPRESS/tipo; la vista inicial muestra pendientes. La prioridad ordena la revisión, no representa gravedad clínica confirmada. Cambiar de examen no recarga el mismo PDF; se conservan página, zoom y búsqueda. **Detalles…** muestra contexto, cobertura y coincidencias de los campos cuantitativos evaluados. El comparador tiene 13 campos mapeados; los demás, incluidas serologías, no están comparados por este motor. Las unidades no se infieren en la interfaz: verificarlas en las fuentes y el PDF.

Al pulsar Guardar, las decisiones, revisor, fecha, página e historial se guardan inmediatamente en `revision_usuario.sqlite`, junto al reporte. Al reabrirlo se recuperan filtros, caso, examen, página y zoom. Mantén ese archivo con el reporte para conservar el trabajo. Los cambios en las fuentes o reglas requieren otra comparación; los cambios en el original o copia PDF invalidan las decisiones de ese documento. Si no se puede escribir, el visor continúa como solo lectura y muestra el motivo. Primera versión para **un revisor por lote**, sin sincronización entre equipos.

**Propuestas…** exporta un Excel con ambos valores iniciales, decisión, valor confirmado, origen que corregir, motivo, evidencia y revisor. Son propuestas **no aplicadas**: no modifican el PDF, Hito 2, referencia, respuestas IA ni SQL. Atajos: Alt+G guarda; Alt+N busca siguiente pendiente; Alt+Izquierda/Derecha cambia de caso. Para mover o compartir resultados deben verificarse rutas y permisos; esta distribución no incorpora datos ni decisiones.

La carga de reportes y comparación se ejecuta en segundo plano. La medición sintética de 8.000 registros / 2.000 casos / 26.000 hallazgos está en `MEDICION_REVISION_10.0.7.md`; no equivale a una prueba de 8.000 PDF reales ni a validación clínica.

## Probar el visor sin acceso al Hito 3

En **4 Control y PDF**, pulsa **Simular desde Hito 1…**, selecciona la carpeta de lecturas y los PDF originales y pulsa **Generar simulación y abrir visor**. El programa reconstruye Hito 2, crea un Hito 3 compatible con cambios controlados y ejecuta el comparador real. Se introducen valores alterados, decimales desplazados, faltantes y duplicados; también se conservan coincidencias de control. Para recorrer todos los originales se añaden controles de visor a los PDF que no generaron discrepancia; esos controles se identifican como simulación y no son errores. Si un PDF no tiene lectura, también aparece indicado. No realiza llamadas IA ni conexiones SQL.

Los entregables quedan en `SIMULACION_VISOR/fecha_hora` dentro de la raíz de resultados, separados de la auditoría real. El reporte y la referencia llevan la marca **SIMULACIÓN**: las diferencias son creadas para probar el visor y no representan errores clínicos comprobados. La referencia sintética no puede usarse como referencia institucional ni cargarse en SAIRC. Los PDF originales y las respuestas del Hito 1 no se modifican.

Las simulaciones anteriores y su acceso directo local se retiraron durante la limpieza. Genera una nueva desde la interfaz con tus propias carpetas; estos datos no se incluyen en el repositorio.

Proyecto independiente de la edición Flet/Docling; no necesita su código ni su repositorio. Interfaz PySide6/Qt Widgets y visor Qt PDF. Esta edición no instala Docling, PyMuPDF, Pillow, Torch ni motores OCR locales. Qt renderiza páginas para Mistral Vision; el reconocimiento se realiza en el proveedor remoto.

## Correcciones de lectura heredadas de 10.0.5

Las páginas para Mistral Vision se componen sobre blanco antes de generar JPEG. Se conserva anti-HBs numérico, se evita confundir umbrales 1 y 10 y se reconoce la variante observada de fosfatasa alcalina. Se ignoran marcadores de no resultado, unidades solas y textos explícitos de referencia como valores normalizados. Las respuestas sin lectura útil se conservan con su costo y estado `reading_empty`, disponibles para revisión y reproceso manual; no se cuentan como éxito. El prompt reforzado no sustituye la revisión humana frente al PDF.

## Ejecutar

En Windows con Python 3.11, ejecuta `INSTALAR.bat` una vez y luego `INICIAR.bat`. En una copia nueva del repositorio, el instalador crea el entorno `.venv`. Para compartir el código, entrega la subcarpeta sin `.venv`, `tmp`, `build`, `dist` ni configuración con credenciales.

`requirements-lock.txt` fija también las dependencias transitivas del entorno verificado. El instalador lo usa como restricciones junto con `requirements.txt`.

El ejecutable único se genera con `powershell -ExecutionPolicy Bypass -File CONSTRUIR.ps1`. Se comparte `dist/10.0.7/AuditoriaSAIRC.exe`; no requiere Python en el equipo receptor. No lo ejecutes desde dentro del ZIP. El acceso SQL requiere además un controlador ODBC instalado y conectividad al servidor. La lectura remota requiere Internet y la API key de cada usuario. No lleva una clave compartida incorporada. El ejecutable se extrae temporalmente al iniciar, por lo que su primer arranque puede ser más lento. La distribución a otro equipo y la firma digital siguen pendientes hasta comprobarlas.

La edición 10.0.7 ya está generada y su arranque fue verificado en este equipo. Ocupa 73.1 MiB. Pasaron 124 pruebas; `VERIFICACION.json` registra dependencias y hash del ejecutable. Las capturas de pruebas se retiraron durante la limpieza. Se verificó además la apertura de los 70 PDF reales del lote (92 páginas), sin modificar originales. Los pendientes reales están en la memoria.

## Flujo

La configuración del lector y de SQL se abre en paneles separados; los cambios quedan activos al cerrar. En Control y PDF, **Seleccionar archivos** permite configurar consolidado/reporte. El visor empieza con 60 % del ancho de la zona de revisión, ajustable arrastrando el divisor. El registro se despliega con **Mostrar registro de actividad**. Consulta `UI_UX_10.0.3.md` para las decisiones de diseño y fuentes.

1. Selecciona la carpeta de PDF originales y una raíz independiente de resultados. En **Extracción**, elige Gemini Vision, Mistral OCR estructurado o Mistral Vision. Introduce tu clave y autoriza el envío para el lote. Se guardan respuestas y estados recuperables; esta etapa no construye el Excel.
2. **Consolidado** transforma las respuestas en Excel y CSV SAIRC, sin nuevas llamadas al proveedor. También acepta una carpeta de respuestas IA del programa anterior. El caché de OCR local no sustituye una lectura remota.
3. **Referencia** acepta CSV/Excel existente o descarga desde SQL Server. Las credenciales se mantienen en la sesión o variables de entorno. El archivo opcional `config.yaml` debe ubicarse junto al código o ejecutable, o indicarse mediante `LAB_EXTRACTOR_CONFIG`. No se incluye en la distribución.
4. **Control y PDF** compara contra la referencia, prepara copias de revisión y carga los hallazgos en tabla. Filtra, ordena y selecciona un PDF y revisa sus diferencias junto a los valores comparados. El visor ofrece páginas, zoom y búsqueda sobre texto existente; no realiza OCR ni modifica el PDF.

Pausar/detener se aplica a la extracción. Una petición remota ya enviada puede terminar y facturarse. Cerrar durante una operación solicita detención y espera a que las escrituras terminen; vuelve a cerrar después. Se rechazan documentos que superen los límites, sin truncar páginas. PDFs dañados o protegidos quedan como errores revisables. Las tarifas/modelos heredados son orientativos y editables; confirmar disponibilidad y facturación antes de la extracción.

## CLI

Desde esta carpeta, con la clave en `LAB_EXTRACTOR_GEMINI_API_KEY` o `LAB_EXTRACTOR_MISTRAL_API_KEY`:

```powershell
.\.venv\Scripts\python.exe cli.py extract C:\PDF C:\RESULTADOS --provider mistral --mode ocr --model mistral-ocr-latest --authorize-external-processing
.\.venv\Scripts\python.exe cli.py consolidate C:\RESULTADOS\HITO_1_EXTRACCION C:\RESULTADOS
.\.venv\Scripts\python.exe cli.py compare C:\consolidado.xlsx C:\referencia.csv C:\RESULTADOS --pdf-root C:\PDF
```

`retry` usa los mismos argumentos de `extract` y reprocesa errores recuperables. No imprime claves. La autorización no se guarda entre sesiones.

## Desarrollo y memoria

`MEMORIA_MIGRACION.md` registra mejoras, verificaciones y pendientes. `AGENTS.md` obliga a actualizarla en cada modificación futura; no es un servicio automático en segundo plano. La memoria no debe contener datos clínicos ni secretos.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pruebas
.\.venv\Scripts\python.exe -m ruff check . --no-cache
.\.venv\Scripts\python.exe main_qt.py --smoke-test
.\.venv\Scripts\python.exe tools/verificar_dependencias.py
```

Las pruebas utilizan documentos sintéticos y respuestas simuladas. No demuestran exactitud clínica ni conectividad con proveedores/SQL reales. La correspondencia EstablecimientoId/CUI debe validarse antes de usar el reporte para una auditoría institucional.

Para diagnosticar un fallo de arranque del paquete, define `SAIRC_BUILD_DEBUG=1` antes de construir: se genera `AuditoriaSAIRC_debug.exe` con consola. Retira esa variable para generar el ejecutable habitual. El spec utiliza los runtimes MSVC suministrados por Qt también en la raíz, evitando mezclar bibliotecas nativas de versiones distintas.

## Repositorio independiente

Nombre sugerido: **laboratorios-sairc-qt-llm**. En GitHub, los archivos de esta edición van directamente en la raíz del repositorio: `main_qt.py`, `core`, `ui_qt`, `tests`, SQL, recursos y dependencias. No incluir la edición Flet/Docling ni envolverlos en una subcarpeta `migracion_qt_llm`.

Cada usuario crea su propio entorno con `INSTALAR.bat`. El entorno local, ejecutable y datos del equipo de desarrollo no forman parte del código publicable. `ORIGEN_CODIGO.json` es un registro histórico de migración; el programa no necesita el proyecto original para ejecutarse. Define la licencia antes de publicar. Repositorio privado: https://github.com/Chrissxmd/laboratorios-sairc-qt-llm . La carga inicial del código se realiza por separado de Flet/Docling.

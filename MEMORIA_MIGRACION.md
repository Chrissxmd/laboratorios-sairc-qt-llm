# Memoria de la migración Qt / LLM

Fecha de inicio: 2026-10-12 (America/Lima).
Edición: `migracion_qt_llm`, independiente del programa Flet de la carpeta superior.
Estado actual: edición Qt 10.0.7 con revisión por PDF, decisiones persistentes y exportación de propuestas. 124 pruebas automatizadas aprobadas. Limpieza para GitHub completada; consultar el registro del 2026-10-14. Pendientes de validación clínica, SQL real y distribución en otro equipo.

## Objetivo acordado

PySide6/Qt Widgets con visor PDF integrado y cuatro hitos. Reconocimiento remoto mediante Gemini, Mistral OCR y Mistral Vision. Eliminar Docling y el OCR local de esta edición. Mantener reglas SAIRC, trazabilidad, cachés históricas, persistencia atómica y PDF fuente.

## Registro de mejoras

### 2026-10-12 — Preparación

- Se creó una copia selectiva de `core/`, SQL, diccionario y pruebas reutilizables. No se copiaron claves, configuración real, muestras clínicas ni resultados del usuario.
- `ORIGEN_CODIGO.json` registra hashes del código anterior para comprobar que la aplicación Flet permanece intacta.
- Se confirmó PySide6 6.11.1 con Qt PDF disponible. Aún falta verificar la versión nueva.

### 2026-10-12 — Núcleo exclusivo remoto

- `core/processor.py`, `core/ai.py` y `core/pdf_utils.py`: eliminación de rutas Docling/Python OCR. Gemini Vision y Mistral OCR/Visión tienen modalidad explícita, autorización por lote y límites de páginas/tamaño; nunca se truncan páginas.
- Mistral OCR exige `document_annotation` estructurado; no se interpreta Markdown mediante un OCR/extractor local. Se conserva uso facturable cuando falta el esquema.
- Hito 1 y reproceso manual guardan respuestas/estados sin crear Excel ni normalizados. Hito 2 conserva normalización SAIRC y formatos históricos, sin llamadas externas. Caché diferencia proveedor, modelo y modalidad; se admite la firma del flujo LLM original.
- Se conservaron escritura atómica, identidad/fechas, comparación por IPRESS y copias con hash/manifest que protegen PDF originales y archivos ajenos.
- `core/db_config.py`: configuración opcional fuera del ejecutable y variables de entorno de SQL. No se copiaron credenciales reales.

### 2026-10-12 — Interfaz y ejecución independiente

- `ui_qt/`: cuatro hitos, trabajador Qt separado, pausa/detención de lectura, cierre seguro durante operaciones, errores con secretos ocultos.
- Visor Qt PDF con páginas/zoom/búsqueda sobre texto existente, tabla ordenable/filtrable y detalle de discrepancias. No hay edición del PDF ni OCR local.
- Se corrigieron el argumento requerido de `QPdfSearchModel.rowCount`, la selección de PDF tras ordenar/filtrar y el tamaño de los controles mediante pestañas con desplazamiento.
- `main_qt.py`, `cli.py`, `INSTALAR.bat`, `INICIAR.bat`, `README.md` y dependencias separadas. `AuditoriaSAIRC.spec`/`CONSTRUIR.ps1` preparan ejecutable único Windows, incluyendo solo diccionario/SQL/configuración de ejemplo y fuente IA para firma del caché.
- Primera suite: **69 pruebas pasaron** en Python 3.11.9 aislado, PySide6 6.11.1 (4.34 s); Ruff crítico pasó. Se probó el flujo completo con PDF sintético, caché, consolidado, referencia sintética, comparación y visor; Mistral se simuló. Se verificó rechazo de envíos sin autorización también en CLI. Hashes originales coinciden. Una ejecución de pruebas quedó detenida y se interrumpió; las repeticiones completas con diagnóstico de bloqueo pasaron. La ampliación posterior llegó a 97 pruebas.
- Se revisaron visualmente las capturas de extracción y revisión: valores de límites legibles, tabla y PDF visibles, detalles con desplazamiento. Se retiró el camino de texto inalcanzable del analizador y el base64 innecesario para Mistral Vision.
- `pip check` confirmó consistencia de dependencias. El entorno aislado no contiene Docling/Flet/PyMuPDF/Pillow/Torch/Transformers ni motores OCR. `tools/verificar_dependencias.py` permite repetir la auditoría del entorno y paquete y guarda `VERIFICACION.json`.
- Estas comprobaciones iniciales se complementaron con el empaquetado descrito abajo; no equivalen a validación clínica para producción.

### 2026-10-12 — Integridad y distribución

- Se migraron las pruebas de negocio de `test_integrity.py` y `test_sairc_normalizer.py`, retirando únicamente casos del extractor local y CLI anterior. **97 pruebas pasaron** en 4.96 s: comparadores/intervalos, millares, aliases/serologías, urea/PRU, universo SAIRC, caché, copias ajenas/obsoletas, solapamientos, fallos atómicos y Excel alternativo/incompleto.
- El primer ejecutable falló al importar QtCore. Se diagnosticó una ICU de Poppler tomada del PATH global, incompatible con Qt. Se aisló el PATH de construcción y se unificaron runtimes MSVC con los distribuidos por Qt. Se confirmó la corrección: el ejecutable de diagnóstico arrancó, validó diccionario/SQL/firma de caché y abrió reporte/PDF sintéticos, con salida 0 y captura.
- `AuditoriaSAIRC.spec` excluye herramientas de prueba, OCR y Qt WebEngine. `tools/verificar_dependencias.py` comprueba además la procedencia de DLL para impedir incorporar bibliotecas de otras herramientas del equipo.
- La configuración de ejemplo utiliza un servidor marcador y no confía por defecto en certificados externos.
- `requirements-lock.txt` y `INSTALAR.bat` fijan las dependencias transitivas del entorno comprobado para repetir la instalación.
- Distribución final: `dist/AuditoriaSAIRC.exe`, **76,641,323 bytes (73.1 MiB)**. SHA-256 `b9ae4d5960a039f25a8b0fb4cda6c49b98b35af99c50ff1480d30923a254c95d`.
- El ejecutable final sin consola pasó la prueba de arranque, comprobación de recursos y apertura de reporte/PDF sintéticos con salida 0. Se revisó `capturas/visor_qt.png`. No se usaron API reales ni SQL institucional.
- Auditoría final guardada en `VERIFICACION.json`: sin módulos OCR/local/Flet/Docling, sin herramientas de prueba en el paquete, sin DLL de otros entornos y sin cambios en el código original. `pip check` y Ruff crítico pasaron.
- Se retiran el ejecutable de diagnóstico y temporales de pruebas/diagnóstico; se conservan fuente, entorno propio, ejecutable final y captura de verificación. El caché de construcción queda ignorado por Git y excluido al compartir el código.

### Mejora 10.0.1 — Diagnóstico Mistral y formulario compacto

- Se inspeccionaron los estados existentes sin copiar documentos ni datos clínicos: 40 errores idénticos `HTTP 400`, `invalid_model`, modelo `pixtral-large-latest` en Visión. La documentación oficial confirma que Pixtral Large está obsoleto. La lista predeterminada heredada era incorrecta.
- Se reemplazó la lista de Visión por aliases actuales: `mistral-small-latest`, `mistral-medium-latest`, `mistral-large-latest`, `ministral-14b-latest`; el primero es el predeterminado. OCR mantiene `mistral-ocr-latest`.
- `core/ai.py` y `core/processor.py`: consulta del catálogo por clave una vez antes de enviar un lote/reproceso; comprueba modelo/aliases y capacidad de visión. Si falla, detiene el lote sin envíos de PDF. Los resultados en caché conservan compatibilidad con 10.0.0.
- `core/retry.py`: los errores `invalid_model` nuevos y HTTP 400/404 históricos con ese motivo pueden reprocesarse manualmente después de cambiar modelo; no se reintentan automáticamente.
- `ui_qt/window.py`: siete controles de límites distribuidos en dos columnas y cuatro filas.
- Comprobación: 100 pruebas pasaron (5.06 s), Ruff crítico pasó y se revisó `capturas/limites_dos_columnas.png`. La recuperación de errores históricos se probó con respuestas simuladas. No se realizaron llamadas reales ni reproceso pagado.
- La edición actualizada se genera en `dist/10.0.1/AuditoriaSAIRC.exe`, separada del ejecutable histórico que puede estar abierto. `CONSTRUIR.ps1`, `README.md`, `pyproject.toml` y el verificador de dependencias apuntan a esta edición.
- Empaquetado terminado: `dist/10.0.1/AuditoriaSAIRC.exe`, 76,645,093 bytes, SHA-256 `2a7adbb7aec17262e7d267733ff45192dc7daaf6719e9a60d2e6a245ae6f8fdc`. Pasó arranque sin consola con salida 0; captura revisada `capturas/limites_dos_columnas_exe.png`.
- `VERIFICACION.json` actualizado: sin componentes OCR ni DLL externas, originales intactos. Lectura adicional de los estados reales confirmó que los 40 errores históricos ahora son elegibles para el reproceso manual, sin modificarlos.
- Fuentes de consulta: https://docs.mistral.ai/models/pixtral-large-24-11, https://docs.mistral.ai/studio/conversations/vision y https://docs.mistral.ai/api/endpoint/models.

### Consulta de costos e historial Mistral — 2026-10-12

- Fuentes oficiales consultadas: https://docs.mistral.ai/inference/pricing y https://mistral.ai/news/mistral-small-4/. `mistral-small-latest` corresponde a Small 4 en la documentación consultada: tarifa estándar USD 0.15/M tokens de entrada, USD 0.60/M de salida y USD 0.015/M de entrada en caché del proveedor. La tabla del programa ya contiene 0.15/0.60; no fue necesario modificar código ni reconstruir el ejecutable. La caché local de respuestas es distinta de la caché facturable del proveedor.
- Ejemplo hipotético: 10,000 tokens de entrada + 2,000 de salida cuestan USD 0.0027, sin entrada cacheada. No es una medición por PDF del lote real.
- Se revisó la carpeta del aplicativo anterior, incluida `salidas`, excluyendo entornos virtuales, pruebas sintéticas, paquete Qt y herramientas temporales: no se encontraron archivos de ejecución `.log`, `.jsonl`, estados o resúmenes históricos. `sample.json` tiene trazabilidad Gemini / `gemini-3.1-flash-lite`, no Mistral; no se copiaron ni registraron datos clínicos.
- La memoria original documenta la caché histórica en `D:\Reportes\RESULTADOS\resultados_2026_7_gpt\_Archivos_Internos` y el piloto en `D:\Reportes\RESULTADOS\TEST_RESULTADOS`. `D:\Reportes` no está accesible en este entorno. No se puede confirmar un modelo Mistral exitoso con los registros actualmente disponibles.
- La única raíz local disponible en `C:\Users\Chriss\LabExtractor\Resultados` es `AUDITORIA_QT`, cuyos 40 errores Mistral fueron diagnosticados en la mejora anterior. Las pruebas automatizadas Mistral del proyecto anterior utilizan respuestas simuladas y no acreditan ejecuciones reales exitosas.

### Comparación del catálogo Vision — 2026-10-12

- Se verificaron catálogo principal, fichas individuales y tarifas oficiales: siete modelos generalistas Vision actuales (Ministral 3B/8B/14B, Small 4, Large 3, Large 4 y Medium 3.5). Large 4 está en vista previa con promoción; no asumir tarifa permanente ni que el alias Large latest apunte a una versión determinada.
- Se guardaron precios, IDs, supuestos de costo, fuentes y recomendación de piloto en `COMPARATIVA_MISTRAL_VISION_2026-10-12.md`. El juicio de conveniencia no sustituye una prueba de exactitud clínica. No se modificó código, no se reconstruyó el ejecutable y no se hicieron llamadas pagadas.
- Se identificó que las opciones y tarifas de 10.0.1 todavía no abarcan el catálogo completo. Actualizarlas, registrar versiones resueltas de aliases y evitar mostrar costo cero para tarifas desconocidas queda pendiente.

### Mejora 10.0.2 — Prueba de Small 4, Ministral 8B y Ministral 3B

- Se añadieron al selector los IDs fijos `mistral-small-2603`, `ministral-8b-2512` y `ministral-3b-2512` y sus tarifas estándar verificadas de entrada/salida. Se conserva compatibilidad de caché con 10.0.1.
- `core/pilot.py`: prueba secuencial sobre la misma carpeta de PDF, manifiesto SHA-256 del conjunto, validación de los tres modelos antes de generar, raíces de cuatro hitos separadas por modelo y reanudación mediante caché. Un cambio del conjunto exige otra raíz de resultados.
- `ui_qt/window.py`: autorización específica de tres lecturas por PDF, botón de prueba y apertura de comparación; pausa/detención cooperativas. No inicia llamadas automáticamente al abrir la aplicación.
- El Excel `comparacion_modelos.xlsx` incluye resumen de éxitos/errores, tokens, tiempos/costo acumulado, valores SAIRC y lecturas originales (unidades/evidencia), más rutas a JSON para trazabilidad. Las coincidencias no acreditan exactitud clínica.
- Se conservan reporte y resultados parciales tras cancelar. El costo acumulado incluye la caché histórica de esa prueba; el tiempo corresponde a la ejecución actual.
- Hito 2 del piloto filtra por estados actualmente exitosos, evitando consolidar una respuesta anterior cuando su documento está en error. El consolidado histórico normal mantiene su comportamiento.
- 103 pruebas pasaron en la comprobación final (6.98 s), Ruff crítico pasó y se revisó visualmente `capturas/piloto_tres_modelos.png`. La prueba sintética verificó separación por modelo, precios, diferencias de hemoglobina, reanudación sin nuevas llamadas, bloqueo de PDF cambiados, rechazo sin autorización/modelo, descarte de respuestas antiguas en estado error y reporte parcial tras cancelación.
- Ejecutable final: `dist/10.0.2/AuditoriaSAIRC.exe`, 76,654,575 bytes, SHA-256 `cbea1fabbc5a9a8248b398bc2dd03a73bf40347241bbe71a0464485a98a2ed59`. Arranque sin consola aprobado (salida 0), captura `capturas/piloto_tres_modelos_exe.png` revisada, `VERIFICACION.json` actualizado: sin OCR local/DLL externas y originales intactos.
- No se enviaron PDF reales ni se ejecutó aún el piloto pagado. El usuario lo inicia con la misma carpeta de PDF, Mistral/Visión, clave y autorizaciones; el botón prueba los tres modelos elegidos, independiente del selector individual. Para 40 PDF sin caché serían 120 lecturas iniciales más reintentos.

### Revisión del piloto ejecutado por el usuario — 2026-10-12

- Se verificaron manifiesto, resumen de modelos, resumen del Hito 1, log y Excel en la raíz local de `PRUEBA_MISTRAL_3_MODELOS`, sin modificar resultados ni enviar PDF. Solo Small 4 tiene ejecución registrada: 40 PDF, 4 hilos, 0 éxitos, sin respuestas/estados persistidos, duración 262.83 s.
- El log registra cinco rechazos HTTP 429 (tres de primer intento y dos de segundo intento), enfriamiento global y final `Cancelled=True`. El estado es `DETENIDO_POR_USUARIO`. Ministral 8B y 3B no llegaron a iniciarse; no existe una comparación de calidad ni costos efectivos de los tres.
- Cero errores finales/costo registrado no significa éxito ni certifica la factura: el piloto fue cancelado durante reintentos y los 40 PDF permanecen pendientes. El Excel solo contiene marcadores de no procesado y columnas vacías para los otros modelos.
- Se archivó `REVISION_PILOTO_MISTRAL_2026-10-12.md` con evidencias agregadas y fuentes oficiales. El bloqueo actual es 429, diferente del antiguo modelo inválido. Sin el cuerpo de los rechazos, no se puede determinar si se alcanzó tasa, tokens o límite de gasto/uso.
- Pendiente: comprobar límites en la cuenta, repetir de forma controlada con un hilo/frecuencia acorde a la cuota y evaluar lecturas reales. No se cambiaron presupuestos ni se hicieron llamadas nuevas.
- La búsqueda ampliada encontró una ejecución individual posterior de Ministral 8B fuera del piloto, en `AUDITORIA_QT/HITO_1_EXTRACCION`: 13:22:17–13:23:27, 40 éxitos técnicos, 0 errores, 182,587 tokens y USD 0.027388 estimados. Las 40 respuestas corresponden al conjunto del manifiesto; se verificaron los SHA-256 actuales de sus PDF sin modificarlos.
- La extracción 8B contiene 446 resultados: 35 documentos con calidad interna alta y 5 baja/sin resultados. Tres carecen de identificación de paciente y tres de fecha; estos grupos pueden solaparse. Dos respuestas tienen advertencias de esquema. La etiqueta `success` acredita procesamiento técnico, no exactitud ni completitud clínica. Revisión manual pendiente de los cinco vacíos y demás alertas; no se generó Hito 2 en esta ejecución individual.
- No se encontró ejecución de Ministral 3B en los logs/resúmenes/cachés locales inspeccionados. La revisión no demuestra que los tres modelos se hayan completado. Se actualizó el informe para distinguir piloto e intento individual.

### Mejora 10.0.3 — Configuración en paneles y prioridad al PDF

- Investigación y decisiones documentadas en `UI_UX_10.0.3.md`, con fuentes NN/G y Qt. Se aplicó divulgación progresiva: mostrar acciones frecuentes y configurar bajo demanda, conservando resumen y estados visibles.
- `ui_qt/window.py`: Hito 1 abre proveedor/modalidad/modelo/API/límites en un panel; Hito 3 abre conexión/autenticación/filtros SQL en otro. Los cambios quedan activos al cerrar y no se guardan credenciales nuevas en disco. Autenticación Windows deshabilita usuario/contraseña SQL. La autorización de envío permanece en la pantalla principal y el piloto tiene sección desplegable con consentimiento independiente.
- Hito 4 mueve rutas a un panel y oculta la selección global de carpetas durante la revisión. `ui_qt/review.py` inicia el divisor en 40/60, sin colapsar los paneles; `pdf_viewer.py` agrupa página/zoom y búsqueda en filas distintas. Registro desplegable, progreso/errores siempre visibles.
- 104 pruebas aprobadas (7.33 s); Ruff crítico pasó. La prueba nueva verifica configuración sin operaciones externas y visor mayor que la mitad del ancho total a 1440 × 950 y 1050 × 730. Capturas sintéticas revisadas; no se enviaron PDF ni se repitió todavía el piloto pagado.
- Se actualizaron versión, README, construcción y auditoría a 10.0.3. La distribución se genera en `dist/10.0.3`, conservando las ediciones anteriores.
- Distribución terminada: `dist/10.0.3/AuditoriaSAIRC.exe`, 76,657,502 bytes, SHA-256 `b122672a641edf4877f8f71a75b9181e9a6940a66fe2e60017d25c6bec7dc304`. Arranque del ejecutable con reporte/PDF sintéticos aprobado (salida 0); captura revisada `capturas/ui_1003_hito4_exe.png`. `VERIFICACION.json` confirma sin OCR local, módulos prohibidos o DLL externas y código original intacto. No se ejecutó un nuevo lote remoto.

### Mejora 10.0.4 — Inicio y errores visibles

- La captura del usuario muestra consentimiento general desmarcado y consentimiento del piloto marcado. Se reprodujo con un clic real del botón en Qt usando datos sintéticos: `config()` rechaza el inicio antes de crear un trabajador o enviar documentos. El botón funciona; el aviso anterior quedaba en el pie de una ventana que podía exceder la pantalla.
- `ui_qt/window.py`: error persistente junto al estado de hitos, con secretos ocultos igual que en el registro; foco y mensaje específico para la casilla general faltante. No se marca automáticamente ni se omite la autorización. Tamaño inicial/mínimo ajustado al área de pantalla disponible, incluyendo margen para el marco/barra de tareas.
- Texto de ayuda diferencia extracción individual y piloto de tres modelos; el piloto sigue exigiendo ambas autorizaciones. La alerta desaparece al iniciar una operación válida. No se cambiaron proveedor, llamadas ni procesamiento.
- 105 pruebas aprobadas (7.03 s), Ruff crítico pasó. La prueba nueva comprueba clic sin autorización (alerta visible, sin tarea), clic con configuración y autorización válidas (entrada al inicio de tarea interceptada) y ocultación de clave en la alerta. No se usaron API reales ni PDF clínicos.
- Versión, construcción y auditoría actualizadas a 10.0.4; distribución en carpeta independiente para conservar el ejecutable anterior abierto.
- Distribución terminada: `dist/10.0.4/AuditoriaSAIRC.exe`, 76,657,428 bytes, SHA-256 `68c8c8081d8285df967880c5717e81613c1cde386134dfb93234ee0e513abfb9`. Arranque del ejecutable sin llamadas aprobado (salida 0). `VERIFICACION.json` confirma originales intactos, sin OCR local ni DLL externas. Se revisó visualmente `capturas/inicio_1004_autorizacion.png`, con bloqueo y mensaje visibles.

### Revisión del piloto completo de tres modelos — 2026-10-12

- Se encontró la nueva raíz `C:\PROYECTOS\RESULTADOS_LABORATORIO\PRUEBA_MISTRAL_3_MODELOS`, distinta de la prueba detenida anterior. 10.0.4 terminó los tres modelos a las 14:13:09: 40/40 éxitos cada uno, cero errores finales, sin caché reutilizada. Se verificaron resúmenes, logs, 120 respuestas y Excel, y SHA-256 actuales contra el manifiesto. No hubo nuevos envíos durante la revisión.
- Small 4: 94.67 s, USD 0.034323, 476 resultados y tres vacíos. 8B: 98.25 s, USD 0.027415, 446 resultados y cinco vacíos. 3B: 48.59 s, USD 0.018261, 453 resultados y cuatro vacíos. Cada modelo consumió 162,560 tokens de entrada; salida 16,565 / 20,204 / 20,045. Small superó un 429 por reintento.
- Concordancia de valores SAIRC: 447 de 512 pares documento/campo informativos coinciden en los tres; 65 difieren en 12 PDF. Solo cuatro desacuerdos tienen valor en los tres; los otros 61 contienen al menos una ausencia. No contabilizar metadatos, motivos ni vacíos totales como exactitud clínica.
- Los cinco PDF de la unión de vacíos, los 12 con discrepancias y las alertas de identidad/fecha requieren contraste humano. Small 4 mostró más cobertura; 3B menor tiempo/costo; 8B no mostró ventaja clara en este lote. No se valida un ganador clínico por cantidad o acuerdo entre modelos.
- Informe agregado guardado en `RESULTADOS_PILOTO_MISTRAL_2026-10-12.md`; no incluye identificadores de pacientes. Sin cambios de código, reconstrucción ni pruebas de software adicionales, ya que fue una revisión de registros.

### Revisión contra PDF originales — 2026-10-12

- Se revisaron 40 PDF/54 páginas, con texto incrustado donde existe y visualización de todas las páginas. Se construyó una referencia de 490 valores presentes de 25 campos directos SAIRC, excluyendo derivados, demografía y otros análisis; no equivale a certificación clínica ni revisión exhaustiva de unidades/fechas. Se verificó que los hashes originales no cambiaron.
- Reproducción local confirma que `QPdfDocument.render` conserva transparencia y el guardado JPEG directo oscurece el fondo/texto. Componer sobre blanco recupera legibilidad frente a Poppler. Cinco documentos con lecturas vacías o no útiles muestran el defecto extenso; hay transparencia parcial en otros 19. No se efectuaron llamadas pagadas.
- Coincidencia de respuesta original contra referencia: Small 4/8B/3B, 419/419/416 valores de 490. Valores diferentes 25/0/23, omitidos 46/71/51 y resultados sin respaldo en casillas vacías 16/5/5. La preparación defectuosa impide atribuir esto solo a calidad del modelo; más objetos de resultados no equivale a mejor lectura.
- Se confirmaron omisiones de transferrina en 3B y lecturas correctas de fosfatasa que se pierden por una variante de nombre no mapeada. Dos casos de serología correctamente transcrita por los tres cambian después en el normalizador: expresiones regulares de umbral 1 coinciden también con umbral 10. No se registran aquí datos clínicos de los pacientes.
- Informe `REVISION_CALIDAD_PDF_2026-10-12.md` y CSV anónimo `revision_pdf/hallazgos_por_documento.csv`. Índice local privado en `tmp/calidad_pdf/indice_privado.csv` para localizar originales. Se anotó el informe anterior para limitar su recomendación por cobertura. Sin cambios de código, reconstrucción ni reproceso de datos.

### Mejora 10.0.5 — Fondo blanco, serologías y lecturas útiles

- `core/pdf_utils.py`: composición sobre blanco en RGB antes de JPEG; no se pierde texto negro ni se cambian páginas/resolución. Marcador `white_rgb_v1` guardado en estados de Mistral Vision. El caché anterior de imágenes sin ese marcador no es reutilizable.
- `core/sairc_normalizer.py`: conservación del índice cuantitativo anti-HBs; límites numéricos completos y comparadores de referencia precisos, evitando confundir 1 con 10. Variante comprobada `ALCANALINA` reconocida como fosfatasa alcalina. Marcadores de no resultado, unidades aisladas y textos explícitos de referencia no se convierten a valores SAIRC; respuesta original conservada para revisión.
- `core/ai.py`: prompt reforzado para leer solo la columna de resultados, dejar vacíos sin inventar y no extender un símbolo de encabezado a todos los análisis. Las métricas cuentan valores útiles; una respuesta sin ninguno tiene calidad interna baja. Esto no garantiza eliminar toda alucinación ni permite verificar numéricos frente al original automáticamente.
- `core/processor.py` y `core/retry.py`: respuesta vacía/no útil conserva JSON y consumo, pero se registra `reading_empty`, sin éxito de lectura. Aparece como error para revisión y reproceso manual; no genera reintentos pagados automáticos por este motivo. Los resúmenes incluyen los tokens y costos de esos fallos.
- `core/pilot.py`: un piloto anterior sin marcador de imágenes se rechaza antes de consultar API y solicita nueva raíz. Se conservan resultados anteriores; no se sobrescribió ni reprocesó el lote del usuario. Se actualizaron versión/documentación/construcción a 10.0.5.
- 113 pruebas aprobadas (7.31 s), Ruff crítico pasó: imagen transparente conserva fondo blanco/texto negro, umbrales 1/10 y Unicode, alias, descarte de marcadores/unidades, respuesta vacía con costos/JSON/cola manual y rechazo de caché/piloto anterior. Dos pruebas históricas que usaban JSON vacío como éxito de recuperación ahora usan un resultado sintético válido.
- Renderizado local con la función corregida de 40 PDF/54 páginas sin llamadas externas. SHA-256 de todos los originales coinciden con el manifiesto. Se revisó visualmente el recorte sin identificación `capturas/correccion_fondo_blanco.png`, comparando JPEG anterior y corregido.
- Distribución final `dist/10.0.5/AuditoriaSAIRC.exe`: 76,659,756 bytes, SHA-256 `1b3000e1a40cc558fbc8c50967d63ff3e5f1bf089c74fe8d520e020c93efa199`. Arranque y visor con reporte/PDF sintéticos aprobados (salida 0). Auditoría `VERIFICACION.json`: originales intactos, sin OCR local, dependencias prohibidas ni DLL externas. No se ejecutó el piloto remoto corregido.

### Revisión real de 10.0.5 — Piloto V02 de 70 PDF

- Nueva raíz `PRUEBA_MISTRAL_V02/PRUEBA_MISTRAL_3_MODELOS`: 70/70 lecturas útiles en cada modelo, cero errores finales/vacíos/reutilizaciones, 92 páginas y marcador `white_rgb_v1` en todos los estados. Los 40 anteriores y los 30 nuevos coinciden en hash con sus manifiestos; sin alteraciones del usuario ni llamadas nuevas por esta revisión.
- Small/8B/3B: 187.28/280.56/82.01 segundos; USD 0.061989/0.049047/0.032545 estimados, total USD 0.143581. Tres incidencias 429 de Small resueltas; resto sin 429 en logs.
- Se amplió la referencia de PDF a 838 valores directos de 25 campos, con 762 valores de 18 campos cuantitativos para comparación separada de serologías/derivados. Small/8B: 761 coincidencias y una diferencia cada uno. 3B: 758 coincidencias y cuatro omisiones; una por nueva variante de nombre no mapeada y tres en la respuesta original.
- Los cinco documentos antes afectados por fondo ya recuperan sus valores cuantitativos revisados. Se confirmaron conservación de anti-HBs y descarte de marcadores de referencia conocidos. Persisten categorías cualitativas sin respaldo en casillas vacías; no considerar la calidad interna alta como validación del original.
- Informe `REVISION_PILOTO_V02_2026-10-12.md`, CSV anónimo `revision_pdf/hallazgos_piloto_v02.csv` e índice privado local para localizar originales. Se priorizaron 17 hallazgos de 11 documentos. Sin cambios de código, pruebas de software adicionales ni reconstrucción: se revisó una ejecución del usuario.

## Pendientes actuales

- Probar el ejecutable en otro equipo Windows sin Python; aún no realizado.
- Medir memoria y respuesta con lotes/reporte grandes y PDF complejos; la verificación inicial utilizó documentos sintéticos pequeños.
- Probar la nueva interfaz con el usuario, PDF reales y escalas de Windows distintas; ajustes visuales comprobados con datos sintéticos y dos tamaños de ventana.
- Corregir nueva variante exacta `FOSFATASE ALCANALINA`, tratar `[EN PROCESO]` como pendiente y reforzar evidencia de la columna de resultados para categorías cualitativas; el prompt solo no elimina referencias confundidas.
- Revisar hallazgos priorizados del piloto V02 antes de adoptar modelo para carga institucional. La corrección de imágenes quedó validada con lectura real, pero unidades, identidad, fechas y demás pruebas requieren validación exhaustiva independiente.
- Controlar tarifas desconocidas y resolver versiones de aliases para las opciones adicionales; los tres modelos del piloto y sus tarifas ya están incorporados.
- El lote histórico de 40 errores fue reprocesado con Ministral 8B por el usuario: técnicamente completo, con cinco respuestas vacías. Verificar estas respuestas frente al PDF y consolidar/validar el resto antes de considerar validada su extracción.
- Localizar/acceder a la carpeta histórica de resultados para verificar el modelo Mistral que funcionó anteriormente; la ubicación documentada en D: no está disponible.
- Validar SQL Server real y equivalencia EstablecimientoId/CUI; no realizado.
- Firma digital, instalador y publicación; fuera de la comprobación inicial.
- Observaciones persistentes y resaltado por coordenadas OCR; no incluidos en la primera versión.

## Mejora 10.0.6 — Small 4 y simulación local del visor (2026-10-12)

- Mistral selecciona Visión y Small 4 (`mistral-small-2603`) por defecto. OCR remoto sigue disponible como selección explícita. Se retiraron el despliegue, autorización, botones y ejecución del piloto de tres modelos de la interfaz; el módulo histórico y sus resultados no se borraron.
- Hito 4 incorpora «Simular desde Hito 1…» con panel de lecturas/PDF. Reconstruye Hito 2 sin IA, crea Hito 3 ficticio y una entrada de revisión por cada PDF. Diferencias creadas para probar el visor, sin validación clínica; no utiliza SQL ni constituye una referencia institucional.
- Entregables aislados en `SIMULACION_VISOR/fecha_hora`; rechazo de salida dentro de originales/lecturas. Excel/JSON con escrituras atómicas. PDF originales enlazados para lectura, sin copias ni modificaciones. Se incluyen archivos sin lectura asociada y se advierte su situación. Referencia marcada «NO CARGAR» y aviso permanente en el visor al cargar cualquier reporte de simulación.
- La interfaz reconoce la carpeta Small 4 del piloto cuando se selecciona su raíz. `--review-report` abre un reporte directamente; `ABRIR_SIMULACION_VISOR.cmd` abre la simulación real preparada en este equipo. Los entregables reales de `pruebas_visor/` se excluyen de Git y de la distribución.
- Comprobación local real: 70 lecturas de Small 4 → 70 entradas, ninguna sin lectura, 70 PDF / 92 páginas abiertos con Qt PDF. Se verificaron los hashes de 216 archivos de originales/lecturas, sin cambios. Cero nuevas llamadas IA/SQL. Esta prueba verifica generación, correspondencia por ruta y apertura; no confirma exactitud clínica de la lectura ni comparación SQL real.
- Verificación automatizada: 116 pruebas pasaron; Ruff crítico sin hallazgos. Incluye PDF sin lectura, extensión PDF mayúscula, protección de originales/caché, cambio de modalidad y selección predeterminada, apertura de cada PDF sintético y acción de simulación sin consentimiento remoto/referencia. Se comprobó también la operación completa por worker Qt, apertura automática del visor, aviso visible y PDF ocupando más de la mitad del ancho. Tras el ajuste final de estado/apertura de consolidado se repitieron las 23 pruebas de integración Qt, todas correctas.
- Archivos principales: `core/simulation.py`, `core/ai.py`, `ui_qt/window.py`, `main_qt.py`, pruebas, README, versiones, acceso directo y exclusión de entregables privados.
- Distribución 10.0.6 compilada y comprobada: `dist/10.0.6/AuditoriaSAIRC.exe`, 76,659,087 bytes; SHA256 `66e569f463e263422f471f38b7f8890176a7a67b535f86906e489cbfa44d1350`. Arranque/carga de reporte sintético y lote real terminaron con código 0. Captura del visor con datos sintéticos verificada. Auditoría de dependencias sin OCR local, módulos de desarrollo ni DLL externas; programa original sin modificaciones. Pendientes: comprobar manualmente navegación/zoom/búsqueda con el usuario y distribución en otro equipo. SQL real y demás pendientes anteriores continúan abiertos.

## Investigación — revisión de 8.000 PDF / cola de 2.000 (2026-10-12)

- Objetivo aclarado: comparar Hito 2 contra Hito 3, con PDF como evidencia para resolver discrepancias y posibles errores de digitación. Una discrepancia puede originarse también en lectura IA, correlación, fecha o unidades; no implica por sí sola error SAIRC.
- Documento `PROPUESTA_REVISION_8000_PDF.md` con inspección del comparador/visor, fuentes NN/G, GOV.UK, W3C y Qt, flujo por PDF, decisiones por campo, reanudación/historial, exportación de propuestas y criterios de aceptación. Investigación/diseño, sin modificación de aplicación ni nueva versión del ejecutable.
- Limitaciones identificadas: comparación actual de 13 campos cuantitativos; navegación por hallazgo que recarga el mismo PDF y reinicia página/búsqueda; sin decisiones persistentes. Serologías/campos no incluidos no deben figurar como comparados o validados. Prioridad de revisión no equivale a gravedad clínica confirmada.
- La simulación 10.0.6 crea hallazgos directamente y prueba el visor; no prueba el motor Hito 2–Hito 3. Pendiente sustituirla por referencia sintética compatible y comparación real con modificaciones controladas, coincidencias, faltantes y referencias ambiguas.
- Propuesta: un caso por PDF con todas sus diferencias, visor 60 %, cola pendiente estable, guardar/siguiente y deshacer. Registro SQLite local separado de las fuentes; revisar de nuevo decisiones cuando cambien fuentes/reglas. Conservar cola para registros sin PDF y casos sin correlación. No modificar SQL ni fuentes al registrar correcciones propuestas.
- Propuesta visual interactiva en la conversación, solo datos inventados. Comprobados decisiones por campo, avance por PDF, derivado sin cierre automático, deshacer y ausencia de desbordamiento a anchos 1024/736/320. No equivale a pruebas de la implementación Qt ni medición con 2.000 PDF reales.
- Pendientes: implementar en etapas simulación compatible, agrupación por PDF y comparación visible, persistencia/reanudación, luego medición con 8.000 registros y 10.000–30.000 hallazgos sintéticos; prueba de usabilidad con el usuario. Fuentes y límites detallados en la propuesta. No se añadieron dependencias a la aplicación ni se realizaron llamadas IA/SQL.

## Mejora 10.0.7 — revisión por PDF y decisiones persistentes (2026-10-14)

- Implementada cola por PDF con todas sus discrepancias, filtros de estado/prioridad/IPRESS/tipo y búsqueda por caso. Prioridades por rango explícito; guardar no reordena el caso activo. Los registros sin PDF siguen visibles como excepciones y los derivados se cuentan aparte.
- Tabla de valores Hito 2/Hito 3 junto al original, controles de decisión siempre visibles. Confirmar una diferencia no completa las demás; «Guardar y seguir» avanza a otro examen sin decisión y después al siguiente pendiente. «Anterior/Siguiente PDF», Alt+G, Alt+N y Alt+flechas. Campo manual y motivo, reapertura y deshacer. No se confirma sin documento abierto/página de evidencia.
- SQLite estándar junto al reporte: decisiones, valor confirmado, revisor, fecha, página e historial transaccional; recuperación de filtros/caso/examen/página/zoom. Propuestas Excel conservan ambos valores iniciales y se marcan no aplicadas. Texto importado no se ejecuta como fórmula. No modifica SQL, respuestas IA, referencia, consolidado ni PDF.
- Procedencia `.fuentes.json`: hashes de consolidado/referencia/reporte, versión de reglas y asociación entre copias y originales. Se invalida la decisión del PDF alterado, incluso cuando la copia de revisión no cambió. Cambiar fuentes/reglas requiere otra comparación. Guardado/exportación rechazan fuentes modificadas durante la sesión. Historial anterior conservado. La prueba descubrió y corrigió diferencias de separadores/capitalización de rutas Windows en la comprobación de procedencia.
- Se conserva el mismo PDF al cambiar de examen; página/zoom/búsqueda se mantienen. Detalles muestra cobertura, correlación y coincidencias de los campos cuantitativos comparados. No se infieren unidades ni posiciones del análisis; el resaltado de regiones OCR sigue pendiente.
- Simulación corregida: crea Hito 3 compatible y ejecuta `compare_excels`, en lugar de inventar directamente todas las discrepancias. Casos de valor alterado, decimal desplazado, faltante, duplicado y coincidencia; controles de visor explícitos permiten recorrer todos los originales sin declararlos errores ni clínicamente validados.
- Prueba local con datos existentes: 70 lecturas de Small 4, 59 hallazgos de comparación y 19 controles; 75 casos (incluye cinco excepciones duplicadas sin PDF propio). 70 PDF/92 páginas abiertos, 216 archivos originales/lecturas conservan hashes, cero avisos de integridad y cero llamadas IA/SQL. Actualizado `ABRIR_SIMULACION_VISOR.cmd` para la nueva edición y lote preparado. No constituye validación clínica.
- Carga sintética reproducible con 8.000 registros, 2.000 casos y 26.000 hallazgos. Medición final: comparación/exportación 76,305 s, carga de reporte 12,850 s, cola 0,937 s, filtro 30,60 ms, navegación media 8,30 ms, máximo del proceso 444,5 MiB. Primera medición: 164,250 s de comparación, 53,786 s de carga, 751,8 MiB. Lectura secuencial y reutilización de rutas evitan el coste repetido; se mantienen comprobaciones de carpetas. Corregido Excel sin dimensiones declaradas. No mide renderizado de 8.000 PDF; véase `MEDICION_REVISION_10.0.7.md`.
- Lectura de reportes/comparación fuera del hilo gráfico, incluido el inicio directo con `--review-report`; SQLite/UI en el hilo principal. Sin dependencias nuevas ni cambios al programa Flet. Documentación, exclusiones de datos/diarios SQLite y versión actualizadas.
- 124 pruebas aprobadas y Ruff crítico sin hallazgos. Tras ajustar el espacio del Hito 4 se repitieron las 23 pruebas Qt, todas aprobadas; capturas sintéticas verificadas a 1440×950 y 1050×730. Los controles de decisión quedan fuera del desplazamiento de la cola, y el título/subtítulo global se ocultan al revisar para dedicar más altura al documento. Distribución final `dist/10.0.7/AuditoriaSAIRC.exe` (76,692,022 bytes), SHA-256 `66643be3cee3f5396e092b9c190711fc9c293787ec112b45f7bfa9c07675678a`. Ejecutable con reporte sintético y simulación real del lote de 70 PDF: salida 0 en ambos casos. Captura del ejecutable verificada. Auditoría de dependencias aprobada: sin OCR local, herramientas de desarrollo ni DLL externas; hashes del programa Flet originales intactos. Archivos principales: `core/review_state.py`, comparador/simulación, visor/panel/ventana Qt, entrada principal, pruebas, herramienta de medición, README y documentación.
- Pendientes: usabilidad con el revisor a escala real, 8.000 PDF físicos y documentos extensos/escaneados, equipos/discos de red y distintas escalas de Windows; otro equipo sin Python y firma digital. Un revisor por lote, sin sincronización de decisiones. SQL real, ampliación validada de campos/serologías y pendientes anteriores de normalización continúan abiertos.

## Regla de actualización

Cada mejora debe actualizar esta memoria y sus pendientes. `AGENTS.md` establece esta obligación para el trabajo futuro; no es una automatización que se ejecute periódicamente. Los logs de uso del programa son independientes de esta memoria de desarrollo.

## 2026-10-14 — Limpieza y preparación para GitHub

- Retirados temporales raíz/Qt, cachés, herramientas temporales de desarrollo, archivos de construcción, ejecutables 10.0.0–10.0.6, simulaciones con copias de PDF/datos, capturas, CSV de hallazgos e informes específicos de pilotos. Retirados sample.json y el acceso directo local ABRIR_SIMULACION_VISOR.cmd. Las referencias a esos archivos en entradas antiguas son registro histórico, no entregables actuales.
- Conservados código de ambas ediciones, pruebas automatizadas sintéticas, documentación de diseño/medición, memoria, recursos SQL/diccionario y ejecutable 10.0.7. Se mantiene .venv para ejecutar localmente. config.yaml y salidas son datos/configuración del usuario: conservados localmente y excluidos de Git/ZIP. No se tocaron PDF ni resultados externos al proyecto.
- README raíz con instalación Qt, alcance y publicación; README Qt sin acceso directo ni capturas retiradas. .gitignore reforzado para PDF, logs, simulaciones, bases SQLite, configuración y ZIP; excepción necesaria para publicar AuditoriaSAIRC.spec y poder reconstruir. Plantilla raíz SQL sin dirección de red interna; .gitattributes define finales de línea.
- Antes de limpiar: 124 pruebas Qt aprobadas en 11.16 s, Ruff crítico sin hallazgos y auditoría del paquete sin dependencias prohibidas/DLL externas; código original intacto. Revisión de patrones habituales de claves en fuentes publicables e historial Git sin coincidencias; no constituye auditoría exhaustiva de secretos.
- Se prepara ZIP de fuentes usando archivos versionados/publicables según Git, sin .git, entornos, configuración, PDF, salidas ni ejecutables. Publicación remota, licencia y derechos de redistribución pendientes; no se creó repositorio ni se subió contenido.
- Cierre: más de 770 MiB retirados; ZIP de 142 archivos fuente verificado con CRC, sin datos/configuración privada ni binarios. Arranque Qt posterior a la limpieza terminado con código 0. Se conserva únicamente el ejecutable versionado 10.0.7. No se reconstruyó porque no hubo cambios de código de la aplicación.

## 2026-10-14 — Dos repositorios independientes

- Corregida la preparación: el ZIP conjunto se retira. Se generan dos raíces publicables y dos ZIP independientes: laboratorios-sairc-docling y laboratorios-sairc-qt-llm, dentro de dist/github y dist respectivamente. Cada ZIP contiene los archivos de su proyecto directamente en la raíz.
- Qt incluye sus propios recursos, SQL, diccionario, configuración de ejemplo, dependencias, README, .gitignore y .gitattributes. Su .gitignore se refuerza para funcionar sin reglas heredadas. El plan de migración pertenece a la documentación Qt. No depende de Flet/Docling ni de carpetas superiores para ejecutarse.
- README original ajustado a Flet/Docling. Se mantienen las carpetas de trabajo actuales para no romper lanzadores/entorno; las raíces preparadas para publicación están separadas. No se copian .git, credenciales, entornos, PDF, resultados ni ejecutables. No se crean repositorios remotos ni se publica contenido.
- Verificación de esta preparación: inventario separado, sintaxis Python, integridad de ambos ZIP y arranque Qt desde la raíz exportada con su propio código/recursos. No cambió código de aplicación; no se repitió la suite de 124 pruebas ya aprobada. Flet no se ejecutó en el entorno Qt.

## 2026-10-14 — Publicación inicial en GitHub

- Usuario autorizó dos repositorios privados en Chrissxmd: laboratorios-sairc-docling y laboratorios-sairc-qt-llm. Creados desde GitHub web con rama main; no se copió el historial mixto del proyecto.
- Carga por carpetas desde las raíces limpias dist/github. Sin credenciales, configuración local, PDF clínicos, salidas, entornos ni ejecutables. La conexión GitHub existente no tiene acceso a estos repositorios nuevos; la carga se realiza con la sesión web autorizada, sin ampliar permisos del conector.
- Documentación actualizada con el enlace del repositorio correspondiente. No hubo cambios funcionales ni llamadas a proveedores IA/SQL. Se conserva la validación anterior; esta operación publica fuentes, no acredita pruebas adicionales.
- El ejecutable Qt no se publica en esta carga de código; una Release, distribución en otro equipo y licencia siguen pendientes. El cierre de la carga se registra localmente en PREPARACION_GITHUB.md.

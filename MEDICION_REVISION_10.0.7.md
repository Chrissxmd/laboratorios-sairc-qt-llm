# Medición local de revisión — 14/10/2026

Escenario sintético: **8.000 registros del Hito 2 y 8.000 de referencia**, con 6.000 grupos coincidentes y 2.000 casos que generan **26.000 hallazgos** (13 campos por caso). Sin llamadas IA/SQL y sin rasterizar PDF reales. Los PDF de esta prueba de carga están ausentes deliberadamente; se miden comparación, reporte y cola, incluida gestión de rutas no disponibles.

Se ejecutó `tools/medir_revision.py` en el equipo de desarrollo. Lectura/comparación y exportación se miden juntas como «comparación»; las demás fases se separan. El máximo de memoria corresponde al proceso entero, incluidas generación/importación del reporte, pandas y Qt; no es el consumo incremental del visor.

| Operación | Primera medición | Después de los cambios |
|---|---:|---:|
| Comparación y generación del reporte | 164,250 s | 76,305 s |
| Carga del reporte y comprobación de fuentes | 53,786 s | 12,850 s |
| Preparación de la cola de 2.000 casos | 1,233 s | 0,937 s |
| Filtro por documento | 22,67 ms | 30,60 ms |
| Cambio de caso, media de 50 pasos | 8,95 ms | 8,30 ms |
| Memoria máxima del proceso | 751,8 MiB | 444,5 MiB |

Mediciones simples, no un ensayo estadístico ni una garantía para otros equipos. La diferencia pequeña en el filtro no indica una regresión comprobada; ambas observaciones son menores de 35 ms. La carga depende del número de campos, XML, almacenamiento, comprobaciones de integridad y tamaño de documentos. Los filtros no vuelven a abrir el Excel.

## Cambios que se midieron

- Lectura secuencial del Excel con hipervínculos obtenidos del XML, evitando materializar todas sus celdas y estilos.
- El contexto de coincidencias se conserva para PDF que requieren revisión; no se carga detalle de los otros 6.000 grupos sin hallazgos.
- Una URI y una comprobación de procedencia por PDF, reutilizadas por sus hallazgos. Se mantienen resoluciones y comprobaciones de límites de carpetas. Un perfil con 800 registros identificó resoluciones repetidas de rutas Windows como principal gasto, especialmente con archivos ausentes.
- Modelos Qt con datos agrupados e índice de búsqueda por caso; PDF abierto solo cuando se selecciona. Las decisiones se guardan en transacciones SQLite separadas de las fuentes.
- Corrección de lectura de Excel generados sin dimensiones declaradas: el recuento usa filas efectivas, no `max_row` inexistente.

## Prueba independiente con los originales disponibles

Se generó una referencia ficticia a partir de 70 lecturas previas de Small 4 y se ejecutó el comparador real. Produjo 59 hallazgos de comparación y 19 controles adicionales para recorrer todos los PDF; 75 casos en total incluyen cinco excepciones de referencia duplicada sin PDF propio. Se abrieron **70 PDF / 92 páginas** y se conservaron los hashes de **216 archivos** de origen/lecturas. Se verificó la procedencia de las copias frente a los originales. No se verificó exactitud clínica mediante esta simulación.

La referencia de prueba contiene cambios controlados y no puede utilizarse como referencia institucional ni cargarse a SAIRC. Los controles sin discrepancias se identifican explícitamente; no equivalen a validación humana ni clínica. No se enviaron documentos ni se efectuaron nuevas lecturas remotas.

## Límites y pendientes

- Falta probar 8.000 PDF reales, PDF escaneados extensos, discos de red y equipos con menos memoria. La prueba de carga no mide esas operaciones.
- Falta prueba de usabilidad con el revisor y distintas escalas de Windows. La navegación/guardado/reanudación se comprueban con casos sintéticos de resultado conocido.
- El comparador cubre 13 campos cuantitativos; serologías y campos no mapeados no cuentan como comparados.
- La primera versión admite un revisor por lote; no hay sincronización de decisiones entre equipos ni actualización automática de SQL.
- No se añadió OCR local ni resaltado por coordenadas inventadas. El salto/búsqueda de texto sigue dependiendo de que el PDF contenga texto.

Para repetir la prueba: `.venv/Scripts/python.exe tools/medir_revision.py`. Guarda los entregables sintéticos en `tmp/carga_revision_8000` y el resultado en `medicion.json`. Opciones `--records` y `--cases` para mediciones menores.

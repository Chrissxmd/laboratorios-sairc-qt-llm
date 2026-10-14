# Revisión de discrepancias Hito 2–Hito 3

Investigación y propuesta del 12/10/2026. No implementada en la aplicación Qt. El escenario indicado por el usuario es 8.000 PDF, de los cuales aproximadamente 2.000 requerirán revisión; no es una medición del lote disponible.

## Objetivo y alcance

Comparar el consolidado normalizado del Hito 2 con la referencia SAIRC del Hito 3. El PDF original es la evidencia para determinar cuál de los valores está mal, si falta un dato o si se correlacionaron registros distintos. Una diferencia no demuestra por sí sola un error de digitación: también puede deberse a extracción IA, fecha, identidad, unidades o referencia ambigua.

Los PDF sin discrepancias detectadas no deben figurar como «validados por el usuario». La cobertura de comparación y los fallos de lectura se informarán por separado. No se propone aprobar automáticamente resultados por confianza del LLM.

## Hallazgos en la edición 10.0.6

- `core/comparador.py` ya compara Hito 2 y Hito 3, correlaciona por documento/periodo y por IPRESS cuando la referencia incluye Renaes, intenta resolver fechas exactas, registra faltantes/duplicados y genera prioridades. La interfaz necesita mostrar cuándo la correlación es exacta, consolidada o ambigua.
- `FIELD_MAP` incluye 13 campos cuantitativos. Otros resultados y serologías no están cubiertos por esa comparación numérica. Se debe informar «no comparado»; ampliar el mapeo requerirá reglas y datos de referencia comprobados, no solo nuevas columnas.
- `ui_qt/review.py` navega por hallazgo. Un PDF con cinco diferencias puede aparecer cinco veces, intercalado con otros PDF por el orden de prioridad. El detalle se presenta como una lista de propiedades técnicas, con desplazamiento horizontal para ver ambos valores.
- `ui_qt/pdf_viewer.py` cierra y carga el documento, borra la búsqueda y vuelve a página 1 en cada selección, aunque corresponda al mismo PDF.
- No hay decisiones persistentes por campo, reanudación de revisión, deshacer ni exportación de correcciones confirmadas. Anterior/Siguiente recorre filas; no significa siguiente PDF pendiente.
- `core/simulation.py` crea directamente hallazgos ficticios y una referencia ilustrativa. Esa simulación comprueba navegación/apertura, pero no prueba el comparador real Hito 2–Hito 3. Debe reemplazarse por una referencia sintética compatible, con cambios controlados y comparación mediante `compare_excels`.

## Propuesta de interfaz

Dos zonas ajustables: revisión a la izquierda (40 %) y PDF a la derecha (60 %, nunca menos de la mitad en el diseño inicial). Esta proporción es una propuesta para esta tarea, no una obligación de las fuentes UX.

La izquierda contiene una cola compacta de **PDF**, el resumen del documento seleccionado y una tabla vertical de sus diferencias: examen/unidad, valor del Hito 2, valor del Hito 3 y decisión. Se muestran diferencias primero, con «Ver todos los campos» para consultar coincidencias y campos no comparados. Los nombres técnicos y rutas quedan en Detalles. Los valores y sus orígenes permanecen visibles juntos, sin desplazamiento horizontal en los tamaños de pantalla admitidos.

Al seleccionar una diferencia se conserva el PDF abierto, su página y zoom. Los PDF relacionados del mismo paciente/periodo/IPRESS se pueden consultar desde el caso, pero no se mezclan valores de informes de fechas distintas. Para un campo ausente en todos los PDF del grupo, se muestran los documentos utilizados para concluir esa ausencia.

### Cola y prioridades

- Vista inicial: «Pendientes», con filtros de IPRESS, tipo de hallazgo y prioridad. Estados separados: pendiente, en revisión, completado y derivado/no concluyente.
- Un PDF aparece una vez; muestra número de diferencias y máxima prioridad pendiente. Las prioridades se ordenan por rango explícito, no alfabéticamente.
- Orden estable mientras se revisa: guardar no hace saltar arbitrariamente la selección. «Guardar y siguiente pendiente» mantiene los filtros elegidos y avanza al siguiente PDF.
- Resumen: PDF del lote, PDF con discrepancias, PDF completados, pendientes y derivados. Mostrar también número de hallazgos, sin confundirlo con número de PDF.
- Una cola adicional conserva registros SAIRC sin PDF, referencias duplicadas y errores de correlación. Estos casos no desaparecen por no tener documento visualizable.
- Prioridad significa orden de revisión; no implica gravedad clínica ni confirma penalidad. Los umbrales requieren validación del responsable del proceso.

### Decisiones y correcciones

Acciones por campo, con etiquetas visibles:

1. «PDF confirma Hito 2»: proponer corrección del registro SAIRC.
2. «PDF confirma Hito 3»: marcar error de extracción y proponer corrección del consolidado.
3. «Registrar otro valor del PDF»: guardar valor confirmado y motivo, conservando los dos valores iniciales.
4. «No concluyente / derivar»: conservar pendiente la resolución; registrar motivo (ilegible, sin informe, fecha ambigua, etc.).

Una sospecha de decimal desplazado, dígitos invertidos o dato en columna equivocada puede ayudar al revisor, pero siempre debe etiquetarse como sugerencia. No decidir automáticamente cuál de las fuentes es correcta.

Una decisión por campo no cierra las demás diferencias del PDF. Un PDF queda completado solo cuando todas las diferencias aplicables estén resueltas. Los derivados no cuentan como resueltos. Guardado inmediato de decisiones, aviso visible, deshacer/reabrir y botón «Guardar y siguiente pendiente»; botones y atajos no actúan sobre otro registro cuando el foco está en un campo de edición. No confirmar 2.000 PDF con una aprobación masiva.

La corrección se registra aparte: no reemplazar respuestas IA, PDF ni referencia importada. Exportar una propuesta de correcciones por origen/IPRESS con valor anterior, propuesto, motivo, evidencia y estado. Registrar una propuesta no significa que SQL haya sido corregido; una actualización institucional queda fuera de esta propuesta.

### Persistencia

Usar SQLite de la biblioteca estándar como registro local de decisiones. Guardar lote, documento fuente, campo, valores iniciales, decisión, valor confirmado, motivo, revisor, fecha e historial de cambios; recuperar posición, filtros y caso al reiniciar.

Vincular decisiones a versiones/hashes del PDF, consolidado, referencia y reglas de comparación. Si cambia una fuente o regla, conservar el historial y marcar decisiones afectadas para nueva revisión; nunca aplicarlas silenciosamente a valores diferentes. Para la primera versión, un revisor por lote: trabajo simultáneo entre equipos necesitará diseño específico de asignación y conflictos.

## Evidencia dentro del PDF

Primera mejora: conservar página/zoom al cambiar de examen del mismo PDF, navegación de pendientes y salto/búsqueda cuando exista texto. Qt PDF dispone de resultados de búsqueda con ubicación. Un PDF escaneado sin texto no permite esa búsqueda local.

Resaltar una región exacta requiere página y coordenadas verificables. La salida actual del LLM no conserva esa evidencia geométrica. No dibujar recuadros estimados ni anunciar navegación precisa cuando no se dispone de posiciones. Se puede guardar manualmente una página como evidencia sin añadir OCR local. Incorporar coordenadas de un servicio remoto sería una etapa posterior con comprobación de exactitud/costo.

## Rendimiento y medición

La aplicación ya utiliza QTableView/QAbstractTableModel: mantenerlo y evitar crear un widget por hallazgo. Abrir únicamente el PDF seleccionado. No rasterizar ni precargar los 8.000 PDF para mostrar la cola. Agrupar e indexar casos una vez; filtrar sin recargar Excel ni PDF y realizar lectura/comparación fuera del hilo de interfaz. Aplicar carga incremental si las mediciones la justifican; 2.000 casos no obligan por sí solos a cambiar todo el modelo.

Pruebas previstas: lote de 8.000 registros, cola de 2.000 PDF y 10.000–30.000 hallazgos sintéticos; PDF digitales, escaneados, varias páginas, dañados y no disponibles. Medir arranque/carga, respuesta de filtros, selección, apertura de PDF, memoria máxima, guardado y recuperación tras interrupción. Los objetivos de respuesta se fijarán tras una medición en el equipo del usuario; actualmente no existe prueba de rendimiento a esta escala.

Como ilustración aritmética, ahorrar 10 segundos por cada uno de 2.000 PDF reduce 5 horas y 33 minutos de trabajo. No es un ahorro medido ni una estimación de precisión. El criterio de éxito debe incluir tiempo por documento, errores de decisión y capacidad de retomar sin perder trabajo, no solo apariencia.

## Implementación por etapas

1. Corregir la simulación: referencia Hito 3 compatible con el comparador y alteraciones controladas (decimales, faltantes, duplicados, fechas ambiguas, extracción equivocada). Conservar coincidencias para probar exclusión de la cola. Controles sintéticos sin IA/SQL.
2. Revisión por PDF: agrupación estable, tabla Hito 2/Hito 3, preservación del visor, filtros y siguiente pendiente. Mantener todos los campos originales del reporte para consulta.
3. Decisiones persistentes: guardado/reanudación, evidencia, revisión no concluyente, deshacer e historial; exportar propuestas sin modificar fuentes.
4. Medir carga/fluidez a escala y hacer prueba con usuarios: primero casos sintéticos de resultado conocido; luego casos reales autorizados. Ajustar atajos, proporciones y vocabulario. Coordinar exactitud de correlación, unidades y cobertura de campos antes de evaluar falsos positivos.

## Criterios de aceptación

- Un PDF con varias diferencias se abre una vez y permite resolverlas sin perder la página.
- Hito 2, Hito 3 y evidencia original se distinguen claramente; el valor LLM no se presenta como lectura humana confirmada.
- Cerrar/reabrir conserva decisiones y último caso. Cambiar fuentes invalida decisiones afectadas de forma visible.
- Los documentos sin PDF y errores de correlación se mantienen en cola; no se etiquetan como errores de digitación confirmados.
- Contadores de documentos/hallazgos/derivados son distintos y consistentes. No se confunde ausencia de discrepancia con revisión humana completa.
- Operación con teclado y mouse; las etiquetas y símbolos comunican estado además del color. Acciones peligrosas no se activan al escribir.
- Ningún PDF, respuesta IA ni referencia inicial se altera por revisar. No se realizan nuevas llamadas IA/SQL para navegar o decidir.
- Prueba de carga y prueba de usabilidad documentadas antes de declarar que soporta cómodamente 2.000 PDF.

## Fuentes consultadas y adaptación

- [NN/G — Recognition and recall](https://www.nngroup.com/articles/recognition-and-recall/): presentar información necesaria junta reduce la dependencia de la memoria. Adaptación: valores de ambas fuentes y PDF visibles en el mismo caso.
- [NN/G — Progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/): reservar funciones secundarias para acceso bajo demanda. Adaptación: diferencias primero; coincidencias, rutas y datos técnicos en detalles.
- [GOV.UK — Check answers](https://design-system.service.gov.uk/patterns/check-answers/): revisión agrupada, posibilidad de corregir y conservación de contexto. Es un patrón de formularios, no una validación de este flujo clínico; se adapta y debe probarse con usuarios.
- [W3C — Use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) y [Keyboard](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html): estados legibles sin depender solo del color y funcionamiento por teclado. Son criterios web utilizados como principios de diseño de escritorio, no una declaración de conformidad de la aplicación Qt.
- [Qt — Model/View Programming](https://doc.qt.io/qt-6/model-view-programming.html): vistas/modelos y opciones de carga incremental para datos grandes. Se recomienda conservar la arquitectura existente y medir antes de añadir complejidad.
- [Qt 6.11 — QPdfSearchModel](https://doc.qt.io/qt-6.11/qpdfsearchmodel.html): búsqueda y ubicaciones en texto del documento; no equivale a OCR ni proporciona coordenadas de resultados LLM en escaneos.

Las proporciones, acciones, SQLite, agrupación por PDF y etapas son decisiones propuestas para este proyecto a partir del código y del volumen indicado; no mandatos de las fuentes ni cambios implementados.

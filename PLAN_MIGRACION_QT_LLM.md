# Plan de migración a PySide6/Qt con lectura LLM y OCR remoto

Fecha: 12 de octubre de 2026, America/Lima.

Estado: propuesta para revisión y ajustes. Este documento no inicia la migración ni cambia el programa actual.

## 1. Objetivo y alcance

Crear una aplicación de escritorio para Windows con PySide6/Qt Widgets, conservando los cuatro hitos y el núcleo de procesamiento Python. Toda lectura/reconocimiento de resultados desde PDF se realizará mediante IA remota: LLM por visión o Mistral OCR con anotaciones estructuradas. Se eliminarán Docling, los extractores OCR locales y los controles del modo local de la edición final.

El visor PDF funcionará localmente. Mostrar, contar páginas o convertirlas en imágenes para enviarlas a un LLM no constituye OCR local: el reconocimiento de texto y resultados seguirá realizándose en el proveedor.

La primera versión cubrirá extracción, consolidación, referencia SQL/archivo y comparación, con visor integrado para revisar discrepancias. El despliegue web, colaboración entre usuarios, edición del contenido PDF y resaltado automático por coordenadas quedan fuera de esta migración inicial.

## 2. Decisiones propuestas

| Tema | Propuesta |
|---|---|
| Plataforma inicial | Windows de 64 bits; validar las versiones de Windows utilizadas antes de fijar soporte. |
| Interfaz | PySide6 + Qt Widgets; evitar QML y Qt WebEngine en la primera versión. |
| Visor | `QPdfDocument` + `QPdfView`, con controles de zoom, página y búsqueda construidos para el flujo de revisión. |
| Reconocimiento | Exclusivamente remoto: LLM Vision y Mistral OCR; sin Docling, Tesseract ni fallback local. |
| Proveedores incluidos | Gemini y Mistral desde la primera versión; Mistral incluye modalidades OCR estructurado y Vision. No fijar todavía modelos definitivos. |
| Otros proveedores | Conservar los adaptadores existentes compatibles con visión, sujetos a pruebas de contrato y piloto. Ocultar combinaciones incompatibles. |
| Procesamiento | Reutilizar `core/`; adaptar progreso, finalización y errores a señales Qt. |
| Caché | Preservar respuestas LLM históricas, metadatos, costos, reanudación y separación por hitos. |
| Configuración | Claves y credenciales fuera del ejecutable; variables de entorno y configuración local excluida de Git. |
| Distribución | Validar primero una carpeta/ZIP portable; evaluar un ejecutable único o instalador después. |

El código actual rechaza DeepSeek como lector de PDF por visión: no se ofrecerá para Hito 1 mientras no exista un adaptador validado. Por ajuste explícito del usuario, Mistral OCR y Mistral Vision forman parte del alcance inicial. Son modalidades diferentes: OCR es el servicio remoto de Document AI con extracción estructurada; Vision es lectura mediante un modelo multimodal. Ambas evitan reconocimiento local.

### 2.1. Integración Mistral incluida

| Modalidad visible | Flujo | Salida requerida |
|---|---|---|
| Mistral OCR | PDF completo → API OCR con `document_annotation_format` y prompt de extracción. | `document_annotation` compatible con el esquema JSON de laboratorio. |
| Mistral Vision | Páginas del PDF → imágenes preparadas localmente → modelo con capacidad de visión mediante Chat Completions. | JSON validado y expandido al mismo contrato interno. |

- Reutilizar `call_mistral_ocr()` y `call_mistral_chat_vision()` de `core/ai.py`; comprobar sus solicitudes y respuestas contra las versiones seleccionadas antes del piloto.
- Mostrar proveedor, modalidad y modelo por separado; no decidir la modalidad únicamente porque el nombre del modelo contenga `ocr`. Validar compatibilidad antes de procesar.
- Proponer OCR para lectura estructurada de documentos y Vision como alternativa de interpretación visual. La elección final por laboratorio se basará en el piloto, no en una superioridad supuesta.
- Solicitar identidad, fechas y resultados con el esquema compacto existente. Si OCR devuelve solo Markdown o una anotación ausente/inválida, registrar el error de contrato: no usar regex local ni asumir que Markdown es JSON válido.
- No enviar el mismo PDF a ambas modalidades automáticamente. Una segunda lectura por Vision requerirá selección explícita o una política acordada posteriormente, con costo adicional visible.
- Configurar `LAB_EXTRACTOR_MISTRAL_API_KEY`, consentimiento externo, límites, timeouts y reintentos. Conservar uso reportado, páginas procesadas cuando estén disponibles, modalidad, modelo y versión en metadatos. Validar la estimación de costos de OCR y Vision por separado.
- Mantener separadas las entradas reutilizables por proveedor, modalidad, modelo y firma de extracción; cambiar entre OCR y Vision no debe recuperar una respuesta de la otra modalidad por coincidencia de ruta.
- Preparar imágenes para Vision sin OCR local. Intentar sustituir PyMuPDF por renderizado Qt PDF; conservar temporalmente PyMuPDF si esa sustitución no mantiene legibilidad, integridad de páginas y uso de memoria aceptables.
- Verificar límites de páginas/tamaño del modelo elegido. No truncar silenciosamente documentos largos: informar el límite y validar cualquier división del documento con trazabilidad por página y conservación de resultados.

La autorización para incluir estas modalidades en el plan no inicia llamadas reales ni envío de documentos. Se mantienen los controles de privacidad y autorización institucional ya existentes.

## 3. Qué se reutiliza y qué se reemplaza

**Se conserva:** normalización SAIRC y alias clínicos, esquema compacto versionado, validación de identidad y fechas, comparación por paciente/periodo/IPRESS, consolidación de paneles, exportación, SQL parametrizado, reintentos, caché SQLite, persistencia atómica y registro de copias de revisión.

**Se reemplaza:** controles Flet de `main.py`, callbacks que actualizan `page`, selectores de archivos, navegación, presentación de resultados y gestión del ciclo de vida de la ventana.

**Se simplifica:** ramas `python`/`llm` de `core/processor.py`, valores predeterminados de `AIConfig` y CLI, `OCRConfig`, smart fallback local y reproceso recomendado desde un primer pase local. El reproceso de errores de API/JSON se conserva. Los antiguos argumentos que soliciten OCR local producirán un mensaje claro; nunca se transformarán silenciosamente en llamadas pagadas al LLM.

**Se retira al terminar la transición:** `core/doc_parser.py`, `core/python_extractor.py`, `core/extractors/` y los auxiliares exclusivamente locales, una vez comprobadas todas sus referencias. El retiro se hará en el código de la edición nueva y en su paquete; se conservará un punto de recuperación de la versión anterior.

El diccionario de laboratorios se conserva mientras participe en identificación por CUI y metadatos. `core/sairc_normalizer.py` permanece: aplicar reglas y validar JSON localmente no es OCR.

## 4. Dependencias de la edición final

| Dependencia | Acción prevista | Comprobación necesaria |
|---|---|---|
| Flet | Retirar del paquete Qt al finalizar. | Nueva interfaz con equivalencia funcional. |
| Docling | Retirar. | Ninguna importación ni descarga de modelos en instalación limpia. |
| Dependencias/modelos de Docling | Excluir del entorno y paquete nuevos. | Revisar dependencias transitivas; no desinstalar paquetes globales indiscriminadamente. |
| PySide6 | Añadir con versión fijada y módulos necesarios. | Qt Widgets y Qt PDF disponibles en el paquete distribuido. |
| PyMuPDF | Evaluar retiro. | Hoy cuenta páginas y rasteriza PDF para Mistral Vision; sustituir con Qt PDF si las pruebas de calidad y memoria pasan. |
| Pillow | Evaluar retiro como dependencia directa. | Verificar importaciones y requerimientos transitivos de las dependencias conservadas. |
| openpyxl | Conservar. | Exportaciones y lectura de reportes. |
| pandas | Conservar inicialmente. | Lo usan SQL y el comparador; su eliminación sería otra tarea. |
| SQLAlchemy, pyodbc | Conservar para Hito 3 SQL. | El controlador ODBC del sistema requiere instalación/configuración independiente. |
| PyYAML | Conservar mientras se use configuración YAML. | Configuración local compatible. |
| pytest, Ruff y empaquetador | Solo desarrollo/construcción. | No incluirlos como recursos del usuario final. |

Se generarán dependencias fijadas desde un entorno limpio. No se construirá el paquete a partir del entorno actual con Docling instalado. El tamaño final se medirá: retirar Docling no garantiza por sí solo un ejecutable pequeño, porque Qt y las dependencias de datos también ocupan espacio.

## 5. Diseño de la experiencia de uso

La ventana tendrá una carpeta maestra de trabajo y navegación por los cuatro hitos. El proveedor/modelo, los límites y la configuración SQL quedarán agrupados en configuración; el estado y las acciones de cada etapa serán visibles.

| Pantalla | Función inicial |
|---|---|
| Extracción | Selección de carpeta PDF, autorización de envío, proveedor/modelo, iniciar, detener, progreso y errores. |
| Consolidado | Construir desde caché, mostrar procesados/revisión y abrir el Excel realmente generado. |
| Referencia | Consultar SQL o seleccionar una referencia existente; validar columnas y periodo. |
| Revisión | Filtrar discrepancias, mostrar valores PDF/SAIRC y abrir el PDF correspondiente dentro de la ventana. |

La revisión utilizará una tabla a la izquierda y el visor a la derecha, con un panel de detalle del hallazgo. Tendrá filtros por IPRESS, tipo, examen y prioridad, navegación anterior/siguiente, zoom, ajuste al ancho y selector de página.

En la primera entrega, el visor será de lectura: no modificará PDF, resultados normalizados ni registros SQL. Observaciones persistentes y estados de revisión pueden añadirse como una etapa separada si se acuerda su contrato de auditoría.

La búsqueda operará sobre el texto disponible en el PDF. Para un escaneo sin texto, el visor mostrará las imágenes; no se incorporará OCR local. Localizar automáticamente una celda requeriría coordenadas de extracción y queda aplazado.

## 6. Fases, entregables y criterios de salida

Estimaciones de esfuerzo para una persona, no compromisos de calendario. Se revisarán tras el prototipo técnico y la prueba de empaquetado.

| Fase | Trabajo y entregable | Criterio de salida | Jornadas |
|---|---|---|---:|
| 0. Base y viabilidad | Registrar el estado vigente sin perder cambios previos, validar pruebas y preparar un entorno limpio. Probar una ventana Qt con PDF y un paquete mínimo. | Visor y paquete abren en un segundo equipo; se conoce qué dependencias requiere la variante de visión. | 1–2 |
| 1. Núcleo remoto exclusivo | Eliminar ramas OCR local de la edición nueva, ajustar CLI/configuración y validar Gemini, Mistral OCR y Mistral Vision. Mantener salida JSON y controles de integridad. | Las tres modalidades funcionan con respuestas simuladas sin importar Docling; modo local se rechaza explícitamente; Hito 2 no llama a IA. | 2–3 |
| 2. Ventana y trabajadores | Crear navegación Qt, configuración y adaptador de tareas mediante señales. Usar cancelación cooperativa y los callbacks existentes. | La ventana responde durante una tarea, informa errores y termina sin abandonar escrituras activas. | 2–3 |
| 3. Cuatro hitos | Conectar extracción, consolidado, referencia y comparación con el núcleo. Preservar carpetas y selección de resultados. | Un proceso sintético completa los cuatro hitos; entradas inválidas y exportaciones incompletas se muestran correctamente. | 4–6 |
| 4. Revisión integrada | Tabla de discrepancias, filtros y visor Qt PDF; navegación y apertura segura de rutas. | Seleccionar un hallazgo abre su PDF; archivos ausentes/protegidos se informan; no se modifican originales. | 3–5 |
| 5. Validación y piloto | Adaptar pruebas, revisar privacidad, compatibilidad de caché, cancelación y funcionamiento sin internet. Ejecutar piloto real solo cuando se autorice proveedor/lote/costo. | No hay regresiones de integridad; el piloto conserva identidad, fechas y resultados prioritarios y registra costos reales. | 2–3 |
| 6. Distribución y retiro | Construir paquete limpio, probar en equipos sin Python ni Docling, documentar uso y retirar Flet/local OCR de la edición final. | Inicio y flujo verificados en otro equipo; paquete sin componentes OCR locales ni secretos; recuperación documentada. | 2–4 |

**Total estimado: 16–26 jornadas de trabajo.** El piloto puede agregar espera externa y no se incluye el tiempo de aprobación institucional. No se fijan fechas de entrega hasta cerrar alcance y completar la fase 0.

## 7. Arquitectura mínima prevista

```text
Interfaz Qt Widgets
  ├── tabla de discrepancias y visor Qt PDF
  └── trabajador Qt: progreso, resultado y error
         └── núcleo Python existente
              ├── Hito 1: PDF → Gemini / Mistral OCR / Mistral Vision → JSON validado/caché
              ├── Hito 2: caché → normalización → Excel/CSV
              ├── Hito 3: SQL o referencia suministrada
              └── Hito 4: comparación → reporte + copias para revisión
```

Se conservará la concurrencia interna existente; Qt envolverá la operación y transmitirá eventos a la pantalla. Los controles gráficos se actualizarán en el hilo principal. Detener impedirá nuevas tareas y solicitará cancelación; una llamada HTTP ya activa puede tardar hasta retornar o alcanzar su timeout. No se prometerá cancelación instantánea.

Se usará un nuevo punto de entrada, propuesto como `main_qt.py`, y un paquete `ui_qt/` pequeño. Se añadirán archivos por responsabilidad real, sin introducir un framework propio de servicios. `core/` seguirá sin depender de controles visuales; cualquier preparación de imágenes con Qt deberá quedar en un adaptador acotado.

## 8. Datos históricos y transición

1. Preservar carpetas, cachés, exportaciones y PDF existentes; no ejecutar limpieza masiva.
2. Abrir respuestas LLM detalladas y compactas históricas en Hito 2 sin nuevas llamadas.
3. Permitir consolidar respuestas locales históricas como datos existentes, sin conservar el motor OCR local ni reutilizarlas como prueba de que un PDF ya fue procesado por LLM.
4. Mantener separadas firmas y metadatos del procesamiento anterior y del nuevo; cambios de interfaz no deben invalidar una respuesta LLM válida.
5. No reenviar automáticamente documentos ya procesados ni corregir resultados históricos sin un reproceso solicitado.
6. Mantener la aplicación anterior disponible durante el piloto. Tras validar la edición Qt, retirarla de la distribución nueva y conservar su versión recuperable.

## 9. Verificaciones obligatorias

- Suite actual como referencia: 163 pruebas aprobadas el 11 de octubre. No se promete conservar ese número exacto: las pruebas específicas del OCR retirado se reemplazarán o quedarán en la versión histórica; las garantías de negocio seguirán cubiertas.
- Nuevas regresiones: lector remoto exclusivo, consentimiento externo, selección proveedor/modalidad/modelo, progreso, cancelación, salida parcial, cierre de ventana y apertura del PDF correcto.
- Conservar y ampliar `dev/tests/test_mistral_integration.py`: OCR con anotación compacta, Vision multipágina, respuesta OCR sin anotación, modelos incompatibles, páginas/tamaño excesivos, contabilización por modalidad, errores temporales y separación de caché OCR/Vision. Añadir pruebas del adaptador de renderizado Qt si sustituye PyMuPDF.
- El piloto comparará Gemini, Mistral OCR y Mistral Vision sobre una misma muestra autorizada y diversa: identidad, fechas, hemoglobina, urea pre/post, serologías, omisiones, tiempo y costo. Su tamaño y presupuesto se acordarán antes de ejecutarlo.
- Mantener pruebas de universo SAIRC completo, identidad, fechas, comparadores/intervalos/millares, correlación por IPRESS, paneles, caché, JSON inválido y contabilización de intentos.
- Mantener pruebas de PDF originales, copias ajenas/modificadas, solapamientos de carpetas, escrituras atómicas y ruta del Excel alternativo.
- Validar que el paquete no contiene Docling, motores OCR locales, sus modelos ni claves/configuración clínica reales. Medir tamaño, arranque, memoria y cambio de documento.
- En ausencia de internet, permitir visor, Hito 2 y Hito 4 desde archivos. Hito 1 requiere acceso al proveedor; Hito 3 SQL requiere conexión a la base institucional.
- Confirmar la consulta SQL contra la base real y la equivalencia `EstablecimientoId`/CUI antes de dar por validada una referencia institucional. La migración no resuelve esa correspondencia por suposición.

## 10. Puntos que se ajustarán antes de implementar

- Modelos y modalidad predeterminada del piloto; Mistral OCR y Mistral Vision ya están incluidos en el alcance.
- Si añadir desde el inicio los lectores Claude/OpenAI existentes, además de Gemini y Mistral.
- Versiones de Windows y requisitos de los equipos destinatarios.
- Distribución como ZIP portable, instalador o archivo único, según el resultado del empaquetado.
- Si las observaciones y estados de revisión forman parte de la primera versión.
- Si Hito 3 SQL irá en el mismo paquete o habrá posteriormente una edición que use únicamente referencias CSV/Excel.

Los valores de la sección 2 son propuestas operativas para avanzar en el diseño; no autorizan envíos de documentos, gastos de API ni publicación. La implementación quedará sujeta a los ajustes que indique el usuario después de revisar este plan.

## 11. Referencias técnicas

- [Qt para Python](https://doc.qt.io/qtforpython-6/).
- [Ejemplo de visor PDF](https://doc.qt.io/qtforpython-6/examples/example_pdfwidgets_pdfviewer.html).
- [Hilos y objetos](https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-qobject.html).
- [Distribución](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html).
- [Mistral: OCR de documentos](https://docs.mistral.ai/studio/document-processing/basic_ocr).
- [Mistral: anotaciones estructuradas](https://docs.mistral.ai/studio/document-processing/annotations).
- [Mistral: modelos de visión](https://docs.mistral.ai/studio/conversations/vision).

Estas referencias orientan la implementación. La versión de PySide6 y las condiciones de los módulos distribuidos se verificarán al fijar dependencias; no se asume que todas las versiones publicadas tengan idéntico empaquetado o comportamiento.

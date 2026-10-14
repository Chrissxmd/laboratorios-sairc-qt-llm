# Interfaz 10.0.3: configuración y revisión documental

Se conservan los cuatro hitos. La prioridad es facilitar la siguiente acción y dedicar el espacio de revisión al informe original.

## Criterios investigados y aplicación

- Mostrar ajustes secundarios bajo demanda, con un botón explícito. [Nielsen Norman Group: progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) recomienda separar las funciones frecuentes de las especializadas y hacer visible su acceso. Hito 1 muestra un resumen del lector y abre proveedor, modalidad, modelo, clave y rendimiento en un panel. Hito 3 permite seleccionar una referencia existente y reserva conexión, autenticación y filtros SQL para otro panel.
- Conservar el contexto del trabajo. Las [guías para aplicaciones complejas de NN/G](https://www.nngroup.com/articles/complex-application-design/) recomiendan gestionar la abundancia de opciones sin reducir capacidades. Se mantienen estado de los hitos, resumen de configuración, progreso y errores. La autorización de envío sigue visible en la pantalla principal; la comparación de tres modelos se despliega a petición y conserva su autorización independiente.
- Ajustar el espacio a la tarea. El hito 4 oculta las rutas globales mientras se revisa y mueve los archivos de comparación a un panel. La zona de trabajo empieza con 40 % para hallazgos y 60 % para el visor; el divisor se puede arrastrar. [QSplitter de Qt](https://doc.qt.io/qt-6/qsplitter.html) proporciona este comportamiento sin dependencias nuevas. Es una proporción de diseño para este programa, no un porcentaje obligatorio en las fuentes UX.
- Agrupar controles relacionados y conservar acceso al detalle. Los filtros quedan sobre los hallazgos; página/zoom y búsqueda están en dos filas dentro del visor. El registro de actividad se despliega mediante una casilla, mientras el estado y los errores permanecen visibles. Los paneles admiten desplazamiento y muestran que sus cambios quedan activos al cerrar; no hay un botón Cancelar que sugiera descartar cambios.
- No confundir limpieza visual con validación clínica. El visor mantiene selección vinculada al hallazgo, búsqueda sobre texto existente y PDF de solo lectura. No se incorporó OCR local ni resaltado de coordenadas. La revisión humana del informe sigue siendo necesaria.

## Comprobaciones

- 104 pruebas aprobadas, incluidos controles en paneles, autenticación SQL, ausencia de llamadas al configurar y anchura del visor mayor que la mitad de la ventana a 1440 × 950 y 1050 × 730. Ruff crítico aprobado.
 - Las capturas sintéticas de esta revisión histórica se retiraron durante la limpieza para GitHub.
- La usabilidad con usuarios, distintas escalas de Windows y PDF reales permanece pendiente. Esta mejora no resuelve ni oculta los rechazos 429 de Mistral; antes de repetir el piloto deben ajustarse las solicitudes a la cuota disponible.

## Cómo repetir el piloto

Abrir Hito 1 → Configurar lector → Mistral / Visión → introducir clave y ajustar límites según la cuenta → Cerrar. Seleccionar la misma carpeta de informes y raíz de resultados, autorizar el envío, desplegar «Comparar Small 4, Ministral 8B y Ministral 3B», marcar su autorización e iniciar la prueba. El piloto utiliza sus tres modelos fijos y raíces separadas, independientemente del modelo seleccionado para extracciones individuales.

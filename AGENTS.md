# Reglas de mantenimiento de esta edición

- Leer `MEMORIA_MIGRACION.md` antes de modificar esta subcarpeta.
- Actualizar `MEMORIA_MIGRACION.md` en cada mejora: comportamiento cambiado, archivos, comprobaciones reales, limitaciones y pendientes. No registrar claves, DNI ni datos clínicos.
- Esta edición es independiente. No modificar el programa Flet situado en la carpeta superior para completar una tarea Qt.
- No añadir OCR local, Docling, Flet ni modelos OCR al paquete. Qt PDF puede visualizar y rasterizar páginas, sin reconocer resultados localmente.
- Mantener las validaciones de identidad/fechas, universo SAIRC completo, separación por IPRESS, caché histórica y protección de PDF originales.
- No realizar llamadas pagadas ni enviar PDF reales durante pruebas sin autorización explícita del usuario.
- Verificar con `python -m pytest -q` desde esta subcarpeta y Ruff crítico. Las pruebas de Qt se ejecutan con `QT_QPA_PLATFORM=offscreen` y datos sintéticos.
- No marcar pendientes como completados por tener código: registrar si hubo pruebas simuladas, pruebas reales y distribución verificada en otro equipo.

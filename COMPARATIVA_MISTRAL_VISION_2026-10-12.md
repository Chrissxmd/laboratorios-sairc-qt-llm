# Modelos Mistral Vision y costos

Consulta: 2026-10-12. Catálogo público oficial; no se consultó una API key ni se enviaron documentos. Tarifas estándar USD por millón de tokens, sin Batch/Priority/región especial. La disponibilidad final debe comprobarse con el catálogo de la cuenta.

| Modelo | Identificador documentado | Entrada | Entrada cacheada | Salida | Estado |
|---|---|---:|---:|---:|---|
| Ministral 3 3B | `ministral-3b-2512` | 0.10 | 0.01 | 0.10 | GA |
| Ministral 3 8B | `ministral-8b-2512` | 0.15 | 0.015 | 0.15 | GA |
| Ministral 3 14B | `ministral-14b-2512` | 0.20 | 0.02 | 0.20 | GA |
| Mistral Small 4 | `mistral-small-2603` | 0.15 | 0.015 | 0.60 | GA |
| Mistral Large 3 | `mistral-large-2512` | 0.50 | 0.05 | 1.50 | GA |
| Mistral Large 4 | `mistral-large-4` | 0.68 | 0.07 | 2.09 | Vista previa, promoción |
| Mistral Medium 3.5 | `mistral-medium-3-5` | 1.50 | 0.15 | 7.50 | GA |

Large 4 fue publicado el 6 de octubre de 2026. Sus tarifas sin promoción mostradas por Mistral son 1.36 entrada, 0.14 entrada cacheada y 4.18 salida. No se da por permanente el precio rebajado. Los aliases `latest` pueden cambiar de versión y tarifa; se muestran identificadores documentados para distinguir las versiones. El catálogo de Vision de una guía general aún enumera Medium 3.1/Small 3.2, pero el catálogo principal y sus fichas los sitúan entre los obsoletos: no deben usarse como opciones actuales para nuevas integraciones.

## Ejemplo uniforme de costos

Supuesto hipotético: 1,000 documentos, cada uno con 10,000 tokens de entrada y 2,000 de salida, sin caché ni reintentos. Las imágenes/páginas pueden consumir diferentes tokens según modelo/preparación; no es una medición del lote real.

| Modelo | USD para el supuesto de 1,000 documentos |
|---|---:|
| Ministral 3 3B | 1.20 |
| Ministral 3 8B | 1.80 |
| Ministral 3 14B | 2.40 |
| Mistral Small 4 | 2.70 |
| Mistral Large 3 | 8.00 |
| Mistral Large 4 | 10.98 (21.96 sin promoción) |
| Mistral Medium 3.5 | 30.00 |

Fórmula: `(tokens_entrada * tarifa_entrada + tokens_salida * tarifa_salida) / 1_000_000`. La caché de respuestas de la aplicación evita otra llamada; es distinta de los tokens de entrada cacheados que cobra el proveedor.

## Recomendación para laboratorios

Juicio de implementación, no un benchmark clínico: comparar Small 4, Ministral 8B y Ministral 14B sobre los mismos PDF autorizados. Small 4 es la referencia inicial propuesta; 8B es un candidato económico y 14B permite comparar una alternativa con salida más barata. Seleccionar por errores/omisiones de identidad, fechas, decimales, unidades y resultados prioritarios, tiempo, tokens y costo por documento correctamente extraído.

14B no es siempre más barato que Small 4: con los mismos tokens y sin caché, Small 4 resulta más barato cuando la entrada supera ocho veces la salida. El tamaño nominal del modelo no demuestra exactitud sobre estos laboratorios. Evaluar 3B si el ahorro sigue siendo relevante después de medir omisiones. Probar Large 3 o Large 4 únicamente como candidatos para casos que fallen en la comparación inicial, sin reenviar automáticamente informes. Medium 3.5 tiene la tarifa más alta de este grupo; su conveniencia exige evidencia de mejor extracción.

OCR 4.1 y OCR 3 pertenecen al servicio Document AI, con otro endpoint/esquema y cobro por páginas; no se mezclan con la tabla de Vision Chat. La tarifa publicada de OCR 4.1 básico es USD 4/1,000 páginas; anotaciones estructuradas y su facturación deben verificarse aparte. Shieldstral 1.0 acepta imágenes para moderación y clasificación, no para extraer informes; su ficha no publica una tarifa de Vision Chat. Pixtral y los Magistral/Devstral antiguos aparecen entre los obsoletos del catálogo y no se recomiendan para una nueva integración.

## Fuentes oficiales

- [Catálogo y modelos obsoletos](https://docs.mistral.ai/models)
- [Tarifas estándar y caché](https://docs.mistral.ai/inference/pricing)
- [Small 4](https://docs.mistral.ai/models/mistral-small-4-0-26-03)
- [Medium 3.5](https://docs.mistral.ai/models/mistral-medium-3-5-26-04)
- [Large 3](https://docs.mistral.ai/models/mistral-large-3-25-12)
- [Large 4: vista previa y promoción](https://docs.mistral.ai/models/mistral-large-4-0)
- [Ministral 14B](https://docs.mistral.ai/models/ministral-3-14b-25-12)
- [Ministral 8B](https://docs.mistral.ai/models/ministral-3-8b-25-12)
- [Ministral 3B](https://docs.mistral.ai/models/ministral-3-3b-25-12)
- [Shieldstral](https://docs.mistral.ai/models/shieldstral-1-0)

## Pendientes de aplicación

- En 10.0.2 ya se incorporaron Small 4, Ministral 8B y Ministral 3B con IDs fijos/tarifas y prueba conjunta. Las restantes opciones de esta tabla son candidatas opcionales, todavía sin actualización completa del selector/cálculo.
- Resolver y registrar la versión real de aliases, y distinguir tarifa desconocida de costo cero, para no interpretar como gratuito un modelo manual no configurado.
- Piloto real de exactitud/costo; ninguna llamada pagada se realizó para esta comparación.

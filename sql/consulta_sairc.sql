DECLARE @Anio INT = :anio;
DECLARE @Mes  INT = :mes;

-- Opcional: colocar un EstablecimientoId específico, o dejar NULL para todos
DECLARE @EstablecimientoId INT = :establecimiento_id;

SELECT  
      e.Descripcion AS Establecimiento

      -- En el Excel figura como Renaes, pero la consulta original usa EstablecimientoId.
      -- Si deseas el RENAES real, cambiar esta línea por: e.SisId AS Renaes
    , e.EstablecimientoId AS Renaes

    , pe.NumeroDocumento AS [Num Doc.]

    , LTRIM(RTRIM(
        ISNULL(pe.ApellidoPaterno, '') + ' ' +
        ISNULL(pe.ApellidoMaterno, '') + ' ' +
        ISNULL(pe.NombrePersona, '')
      )) AS [Nombres y apellidos]

    , ISNULL(CONVERT(VARCHAR(10), ce.FechaMuesta, 103), '') AS [Fecha de Muestra]

    , ISNULL(CONVERT(VARCHAR(10), ce.UPOST), '') AS UPOST
    , ISNULL(CONVERT(VARCHAR(10), ce.UPRE), '') AS UPRE
    , ISNULL(CONVERT(VARCHAR(10), ce.TIEMPOHD), '') AS TIEMPOHD
    , ISNULL(CONVERT(VARCHAR(10), ce.PESOINICIAL), '') AS PESOINICIAL
    , ISNULL(CONVERT(VARCHAR(10), ce.PESOFINAL), '') AS PESOFINAL
    , ISNULL(CONVERT(VARCHAR(10), ce.ULTRAFILTRACION), '') AS ULTRAFILTRACION
    , ISNULL(CONVERT(VARCHAR(10), ce.PESOSECO), '') AS PESOSECO

    , ISNULL(CONVERT(VARCHAR(10), ce.HB), '') AS HB
    , ISNULL(CONVERT(VARCHAR(10), ce.HTO), '') AS HTO
    , ISNULL(CONVERT(VARCHAR(10), ce.CalcioSerico), '') AS CalcioSerico
    , ISNULL(CONVERT(VARCHAR(10), ce.FosforoSerico), '') AS FosforoSerico
    , ISNULL(CONVERT(VARCHAR(10), ce.PTH), '') AS PTH
    , ISNULL(CONVERT(VARCHAR(10), ce.AlbuminaSerica), '') AS AlbuminaSerica
    , ISNULL(CONVERT(VARCHAR(10), ce.FOSFATASA), '') AS FOSFATASA
    , ISNULL(CONVERT(VARCHAR(10), ce.TGO), '') AS TGO
    , ISNULL(CONVERT(VARCHAR(10), ce.TGP), '') AS TGP
    , ISNULL(CONVERT(VARCHAR(10), ce.HIERROSERICO), '') AS HIERROSERICO
    , ISNULL(CONVERT(VARCHAR(10), ce.FERRITINA), '') AS FERRITINA

      -- Esta columna en el Excel sale truncada a varchar(10)
    , ISNULL(CONVERT(VARCHAR(10), ce.Observaciones), '') AS Observaciones

    , ISNULL(CONVERT(VARCHAR(10), ce.CalculoKTV), '') AS CalculoKTV
    , ISNULL(CONVERT(VARCHAR(10), ce.CalculoPRU), '') AS CalculoPRU

      -- Esta columna contiene la observación completa
    , ISNULL(ce.Observaciones, '') AS Observacion

    , ISNULL(CONVERT(VARCHAR(10), ce.FechaPrimeraHemodialisis_OTI, 103), '') AS FechaPrimeraHemodialisis_OTI
    , ISNULL(CONVERT(VARCHAR(10), ce.FechaPrimeraHemodialisis_DICOE, 103), '') AS FechaPrimeraHemodialisis_DICOE
    , ISNULL(ce.DiasAntiguedad, 0) AS DiasAntiguedad
    , ISNULL(CONVERT(VARCHAR(1), ce.SeleccionFechaPrimeraHemodialisis), '') AS SeleccionFechaPrimeraHemodialisis
    , ISNULL(ce.Observaciones_DICOE, '') AS Observaciones_DICOE

FROM [BDSAIRC_PBI].[dbo].[SAIRT_FormularioEstado] fe

INNER JOIN [BDSAIRC_PBI].[dbo].[SAIRT_PARAMETRO] p
    ON p.CodigoParametro = fe.ParametroFormularioId

INNER JOIN [BDSAIRC_PBI].[dbo].[SAIRT_DatoKTVHD] ce
    ON ce.FormularioEstadoId = fe.FormularioEstadoId

INNER JOIN [BDSAIRC_PBI].[dbo].[Paciente] pa
    ON pa.PacienteId = ce.PacienteId

INNER JOIN [BDSAIRC_PBI].[dbo].[Persona] pe
    ON pe.PersonaId = pa.PersonaId

INNER JOIN [BDSAIRC_PBI].[dbo].[Establecimiento] e
    ON e.EstablecimientoId = fe.EstablecimientoId

WHERE fe.Anio = @Anio
  AND fe.Mes = @Mes
  -- Preserva el requisito de autorización sin multiplicar resultados por cada autorización.
  AND EXISTS (
        SELECT 1
        FROM [BDSAIRC_PBI].[dbo].[AutorizacionTratamientoEstablecimiento] ate
        WHERE ate.PacienteId = ce.PacienteId
      )
  AND (
        @EstablecimientoId IS NULL
        OR fe.EstablecimientoId = @EstablecimientoId
      )

ORDER BY 
      e.Descripcion
    , pe.ApellidoPaterno
    , pe.ApellidoMaterno
    , pe.NombrePersona;

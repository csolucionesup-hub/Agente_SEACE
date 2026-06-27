# Seguimiento de obras y adjudicación — experiencia de usuario Agente SEACE

## Conclusión de producto

Sí: la app no debe quedarse solo en “encontrar oportunidades”. El valor mayor está en hacer **seguimiento del ciclo de vida del procedimiento** hasta saber si:

- Se acerca la fecha de otorgamiento de la buena pro.
- Ya se otorgó la buena pro.
- La buena pro fue consentida.
- Se suscribió contrato.
- La obra/proceso fue declarado desierto.
- Fue cancelado.
- Fue declarado nulo.
- Hubo pérdida de buena pro.
- Hubo no suscripción del contrato por decisión de la entidad.
- Se creó una nueva versión/reinicio del procedimiento.

Esto convierte la app en un **monitor comercial de seguimiento**, no solo en un buscador.

## Fuentes oficiales revisadas

### Portal de Contrataciones Abiertas OCDS — OECE

Fuente oficial: https://www.gob.pe/52005-acceder-al-portal-de-contrataciones-abiertas-de-la-compra-publica-ocds

Puntos relevantes:

- El portal contiene información y documentos de **todas las etapas** de los procesos de contratación.
- La información sigue el estándar OCDS.
- El portal incluye búsqueda por palabras clave, entidades, periodos, etapas o procedimientos.
- La API oficial expone endpoints de releases, records y archivos masivos.

### Manual de usuario del Módulo de Selección v1.6 — OECE

Fuente oficial: https://www.gob.pe/institucion/oece/informes-publicaciones/7534203-manual-de-usuario-del-modulo-de-seleccion-vigente

Puntos relevantes del manual:

- La fase de selección registra información desde la **convocatoria** hasta el **consentimiento de la buena pro**.
- Etapas/actividades relevantes:
  - Publicación de convocatoria.
  - Registro de participantes.
  - Formulación de consultas y observaciones.
  - Absolución de consultas/observaciones.
  - Integración de bases.
  - Presentación de ofertas.
  - Evaluación/calificación.
  - Otorgamiento de buena pro.
  - Consentimiento de buena pro.
- El sistema permite registrar acciones posteriores o incidentes:
  - Desierto.
  - Nulidad.
  - Cancelación.
  - Pérdida de buena pro.
  - No suscripción del contrato por decisión de la entidad.
  - Nueva versión del procedimiento.

### Manual del Buscador Público de Ejecución Contractual — OECE

Fuente oficial: https://www.gob.pe/institucion/oece/informes-publicaciones/7480824-manual-de-usuario-del-buscador-publico-de-ejecucion-contractual

Puntos relevantes:

- Permite consultar contratos publicados por departamento.
- Cada contrato puede vincularse con su procedimiento de selección.
- Permite ver detalle del contrato, contratista y documentos asociados.
- Útil para confirmar quién ganó y si se llegó a contrato.

## Modelo de ciclo de vida propuesto

La app debe modelar cada oportunidad como un expediente vivo:

```text
Detectado
  ↓
Convocado
  ↓
Registro de participantes / consultas
  ↓
Integración de bases
  ↓
Presentación de ofertas
  ↓
Evaluación y calificación
  ↓
Buena pro programada
  ↓
Buena pro otorgada
  ↓
Buena pro consentida
  ↓
Contrato suscrito
  ↓
Ejecución contractual
```

Y debe detectar salidas alternativas:

```text
Desierto
Cancelado
Nulo
Pérdida de buena pro
No suscripción de contrato
Nueva versión / reinicio
```

## Estados internos recomendados para la app

Estos estados son los que debería ver el cliente, no necesariamente los nombres técnicos del SEACE:

1. **Nueva oportunidad**
   - Recién detectada por keyword, entidad o rubro.

2. **En evaluación comercial**
   - El cliente aún decide si le interesa.

3. **En proceso activo**
   - Convocatoria vigente; hay fechas próximas.

4. **Próxima a buena pro**
   - La fecha de otorgamiento de buena pro está cerca.
   - Este es el momento más valioso para alertar.

5. **Buena pro otorgada**
   - Ya hay ganador/adjudicatario o resultado publicado.

6. **Buena pro consentida**
   - El resultado quedó firme según registro publicado.

7. **Contrato suscrito**
   - Ya existe contrato y se puede identificar contratista/proveedor.

8. **Caída / desierta / cancelada / nula**
   - El proceso no siguió el camino normal.

9. **Reiniciada / nueva versión**
   - Se debe volver a monitorear porque puede aparecer una nueva oportunidad.

## Alertas que sí generan valor

### Alerta 1 — Nueva oportunidad detectada

“Se detectó una oportunidad relacionada con PUENTE en la Municipalidad X.”

### Alerta 2 — Fecha crítica próxima

“Esta oportunidad se acerca a presentación de ofertas / buena pro. Revisar hoy.”

### Alerta 3 — Buena pro otorgada

“Ya se otorgó la buena pro. Ganador: proveedor X. Monto: S/ Y.”

### Alerta 4 — Buena pro consentida

“El resultado fue consentido. Alta probabilidad de pasar a contrato.”

### Alerta 5 — Contrato suscrito

“Contrato publicado. Contratista: proveedor X. Fecha de firma: DD/MM/AAAA.”

### Alerta 6 — Proceso caído o reiniciado

“El proceso fue declarado desierto/cancelado/nulo. Puede reaparecer como nueva versión.”

## Por qué el cliente pagaría por seguimiento

El cliente no paga solo por “buscar SEACE”. Paga porque la app le responde preguntas comerciales:

- ¿Qué oportunidades nuevas aparecieron?
- ¿Cuáles están cerca de una fecha crítica?
- ¿Cuáles debo revisar hoy?
- ¿Se otorgó la buena pro?
- ¿Quién ganó?
- ¿Por cuánto ganó?
- ¿El proceso quedó firme o se cayó?
- ¿Se firmó contrato?
- ¿El proceso se reinició y puedo volver a intentarlo?

Esto permite:

- No enterarse tarde.
- Preparar documentación con anticipación.
- Coordinar proveedores/socios antes de la buena pro.
- Saber contra quién compite.
- Analizar entidades y ganadores recurrentes.
- Detectar procesos desiertos que podrían volver a convocarse.

## Experiencia UX recomendada para Lovable

### 1. Dashboard “Hoy debo mirar”

Tarjetas:

- Nuevas oportunidades.
- Vencen pronto.
- Próximas a buena pro.
- Buena pro otorgada.
- Contratos firmados.
- Procesos caídos/reiniciados.

### 2. Línea de tiempo por oportunidad

Cada expediente debe tener una línea de tiempo:

```text
Convocatoria → Consultas → Bases integradas → Ofertas → Buena pro → Consentimiento → Contrato
```

Con colores:

- Gris: pendiente.
- Azul: en curso.
- Amarillo: atención próxima.
- Verde: completado favorablemente.
- Rojo: caído/observado.

### 3. Bandeja de seguimiento

Columnas recomendadas:

- Prioridad.
- Estado comercial.
- Entidad.
- Código de proceso.
- Objeto.
- Monto.
- Fecha próxima crítica.
- Días restantes.
- Último cambio detectado.
- Ganador, si existe.
- Contrato, si existe.
- Acción recomendada.

### 4. Vista detalle del expediente

Debe responder:

- Qué es.
- Quién compra.
- Cuánto vale.
- En qué etapa está.
- Qué fecha crítica viene.
- Qué documentos existen.
- Qué proveedor ganó, si ya se adjudicó.
- Qué pasó si cayó.
- Evidencia oficial/API/SEACE.

## Datos técnicos a extraer de la API OCDS

Campos principales:

- `ocid`: identificador único del proceso.
- `tender`: convocatoria/procedimiento.
- `tender.status` y `tender.items[].statusDetails`: estado del procedimiento/ítems cuando esté disponible.
- `tender.tenderPeriod`: fechas del procedimiento.
- `tender.documents`: bases, documentos y publicaciones.
- `awards`: buena pro/adjudicación.
- `awards[].suppliers`: proveedor ganador.
- `awards[].value`: monto adjudicado.
- `awards[].date`: fecha de adjudicación.
- `contracts`: contrato suscrito.
- `contracts[].dateSigned`: fecha de firma.
- `contracts[].period`: plazo contractual.
- `contracts[].documents`: documentos de contrato.

Validación real realizada:

- Un registro reciente en etapa convocada no trae `awards` ni `contracts`.
- Un registro histórico adjudicado/contratado sí trae `awards` y `contracts`, incluyendo proveedor, monto, fecha de adjudicación y fecha de firma del contrato.

## Recomendación de implementación

1. Guardar cada oportunidad por `ocid` en una base local.
2. Reconsultar diariamente los `record/{ocid}` activos.
3. Comparar estado anterior vs estado nuevo.
4. Crear eventos cuando cambie algo importante:
   - Nuevo documento.
   - Nueva fecha.
   - Buena pro publicada.
   - Consentimiento publicado.
   - Contrato firmado.
   - Desierto/cancelado/nulo.
5. Mostrar esos eventos en timeline.
6. Enviar alerta solo cuando el cambio sea comercialmente relevante.

## Mensaje comercial corregido

“Agente SEACE no solo encuentra oportunidades: las sigue hasta saber si se acercan a buena pro, quién ganó, por cuánto ganó, si se firmó contrato o si el proceso se cayó/reinició.”

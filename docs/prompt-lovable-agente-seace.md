# Prompt para pegar en Lovable — Agente SEACE

Crea una aplicación web SaaS en español llamada **Agente SEACE**.

## Objetivo del producto

Agente SEACE es un radar comercial para empresas que venden al Estado peruano. La app monitorea oportunidades públicas desde su convocatoria hasta buena pro, contrato, cancelación, nulidad, desierto o reinicio.

No es solo un buscador. Debe sentirse como un **CRM de oportunidades públicas**: el usuario entra y entiende qué procesos debe revisar hoy, cuáles se acercan a buena pro, quién ganó, por cuánto, y qué procesos se cayeron o deben seguirse.

## Estilo visual recomendado

Diseña una interfaz profesional, moderna, tipo dashboard B2B/SaaS.

Inspiración visual:
- Linear: limpio, ordenado, productivo.
- Vercel: profesional, sobrio, mucho espacio en blanco.
- Stripe: tarjetas claras, jerarquía visual y métricas.

Debe verse confiable para empresas constructoras, consultoras y proveedores del Estado.

Usar:
- Fondo claro.
- Sidebar lateral.
- Cards de métricas.
- Tablas limpias.
- Badges de estado.
- Timeline visual.
- Semáforo de prioridad.
- Acciones recomendadas.

## Pantallas requeridas

### 1. Dashboard principal

Debe mostrar cards superiores:

- Nuevas oportunidades
- En seguimiento
- Próximas a buena pro
- Buena pro otorgada
- Contratos suscritos
- Procesos caídos/reiniciados

Debajo mostrar:

- Lista de alertas recientes.
- Tabla resumida de oportunidades prioritarias.
- Gráfico simple por etapa del proceso.
- Gráfico simple por resultado: activo, adjudicado, contratado, desierto, cancelado, nulo.

### 2. Bandeja de oportunidades

Crear una vista tipo CRM/lista con filtros.

Columnas:

- Prioridad
- Estado
- Código de proceso
- Entidad
- Descripción corta
- Monto referencial
- Próxima fecha crítica
- Ganador, si existe
- Monto adjudicado, si existe
- Acción recomendada

Filtros:

- Keyword
- Entidad
- Región
- Monto mínimo
- Estado
- Etapa
- Resultado
- Fecha crítica

### 3. Detalle de oportunidad

Al abrir una oportunidad, mostrar:

- Código del proceso
- OCID
- Entidad convocante
- Descripción completa
- Monto referencial
- Estado actual
- Resultado actual
- Próxima fecha crítica
- Ganador / proveedor adjudicado
- RUC del ganador
- Monto adjudicado
- Fecha de buena pro
- Contrato
- Fecha de firma de contrato
- Inicio y fin contractual
- Fuente oficial SEACE/OECE

También incluir una sección “Acción recomendada”.

Ejemplos:

- Revisar hoy
- Preparar documentación
- Monitorear buena pro
- Revisar ganador
- Contactar proveedor/entidad
- Esperar reinicio
- Descartar por baja relevancia

### 4. Timeline del proceso

Crear una línea de tiempo visual por oportunidad:

1. Convocatoria
2. Consultas / observaciones
3. Integración de bases
4. Presentación de ofertas
5. Evaluación
6. Buena pro
7. Buena pro consentida
8. Contrato firmado
9. Ejecución contractual

Debe soportar eventos negativos:

- Desierto
- Cancelado
- Nulo
- Pérdida de buena pro
- Reiniciado

### 5. Alertas

Vista con eventos comerciales importantes:

- Nueva oportunidad detectada
- Fecha crítica actualizada
- Próxima a buena pro
- Buena pro otorgada
- Contrato suscrito
- Proceso caído
- Proceso reiniciado

Cada alerta debe mostrar:

- Severidad: alta, media, baja
- Fecha
- Oportunidad relacionada
- Mensaje claro
- Botón “Ver expediente”

### 6. Configuración del cliente

Crear pantalla para configurar monitoreo:

- Nombre del cliente
- Rubro
- Keywords a monitorear
- Entidades prioritarias
- Regiones prioritarias
- Monto mínimo
- Frecuencia de seguimiento
- Canales de alerta

## Estados y colores

Usa badges:

- `convocado`: azul
- `en_seguimiento`: celeste
- `proximo_buena_pro`: amarillo
- `buena_pro_otorgada`: verde
- `contrato_suscrito`: verde oscuro
- `desierto`: rojo
- `cancelado`: rojo
- `nulo`: rojo
- `reiniciado`: morado o naranja

Resultados:

- `activo`: azul
- `adjudicado`: verde
- `contratado`: verde oscuro
- `desierto`: rojo
- `cancelado`: rojo
- `nulo`: rojo

Severidad de alertas:

- `high`: rojo/naranja intenso
- `medium`: amarillo/azul
- `low`: gris

## Datos que recibirá el frontend

La app recibirá un JSON con esta estructura:

```json
{
  "counts_by_stage": {
    "convocado": 1,
    "contrato_suscrito": 1
  },
  "counts_by_outcome": {
    "activo": 1,
    "contratado": 1
  },
  "opportunities": [
    {
      "ocid": "ocds-dgv273-seacev3-1221249",
      "process_code": "SIE-SIE-4-2026-MML-OGA-OL-1",
      "entity_name": "MUNICIPALIDAD METROPOLITANA DE LIMA",
      "description": "Suministro de materiales de construcción...",
      "amount": 0,
      "currency": "PEN",
      "tender_status": "",
      "stage": "convocado",
      "next_critical_date": "2026-06-01T00:00:00-05:00",
      "winner_name": "",
      "winner_ruc": "",
      "awarded_amount": null,
      "award_date": "",
      "contract_id": "",
      "contract_date_signed": "",
      "contract_start_date": "",
      "contract_end_date": "",
      "outcome": "activo"
    }
  ],
  "recent_events": [
    {
      "ocid": "ocds-dgv273-seacev3-999999",
      "event_type": "nueva_oportunidad",
      "title": "Nueva oportunidad detectada",
      "message": "Nueva oportunidad DIRECTA-PROC-4-2024-FAP/DIGED-1 de FUERZA AEREA DEL PERU.",
      "severity": "medium",
      "occurred_at": "2024-04-14T08:29:51.507819-05:00",
      "payload": {}
    }
  ]
}
```

## Reglas UX importantes

- El usuario no debe sentirse en un portal técnico del Estado.
- Debe sentir que está usando una bandeja comercial de oportunidades.
- Prioriza claridad sobre exceso de información.
- Cada proceso debe tener una acción recomendada.
- La buena pro, contrato y procesos caídos deben ser muy visibles.
- El dashboard debe responder: “¿Qué debo mirar hoy?”

## Datos de ejemplo para poblar el mockup

Usa estos ejemplos:

### Ejemplo 1

- Código: SIE-SIE-4-2026-MML-OGA-OL-1
- Entidad: MUNICIPALIDAD METROPOLITANA DE LIMA
- Descripción: Suministro de materiales de construcción para trabajos operativos
- Estado: convocado
- Resultado: activo
- Próxima fecha crítica: 2026-06-01
- Acción recomendada: Revisar si aplica al rubro del cliente

### Ejemplo 2

- Código: DIRECTA-PROC-4-2024-FAP/DIGED-1
- Entidad: FUERZA AEREA DEL PERU
- Descripción: Programa de especialización en administración
- Estado: contrato_suscrito
- Resultado: contratado
- Ganador: UNIVERSIDAD SAN IGNACIO DE LOYOLA S.R.L.
- RUC ganador: 20297868790
- Monto adjudicado: S/ 89,950
- Fecha contrato: 2024-04-05
- Acción recomendada: Registrar ganador y alimentar inteligencia competitiva

## Entregable esperado

Crear una app navegable con:

- Layout completo.
- Sidebar.
- Dashboard.
- Bandeja de oportunidades.
- Detalle de oportunidad.
- Timeline.
- Alertas.
- Configuración.
- Datos mock basados en el JSON anterior.

No necesito backend real todavía. Primero crear el frontend y experiencia de usuario. Luego conectaremos el JSON real generado por el Agente SEACE.

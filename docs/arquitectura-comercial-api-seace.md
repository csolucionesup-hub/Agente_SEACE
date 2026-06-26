# Arquitectura comercial — Agente SEACE API + Evidencia

## Decisión principal

Agente SEACE debe usar como fuente primaria la API oficial de **Contrataciones Abiertas OECE** y usar Playwright solo para evidencia visual o validación de fichas públicas.

Esto cambia el producto de “bot que navega SEACE” a “sistema de inteligencia comercial para compras públicas”.

## Fuentes oficiales

### 1. API OCDS — principal

Base URL:

```text
https://contratacionesabiertas.oece.gob.pe
```

Endpoints confirmados:

```text
/api/v1/search?q=puente&page=1&paginateBy=5&format=json
/api/v1/files?format=json
/api/v1/releases?page=1&paginateBy=1&format=json
/api/v1/records?page=1&paginateBy=1&format=json
/api/v1/release/{id}?format=json
/api/v1/record/{ocid}?format=json
```

Uso del producto:

- Búsqueda por palabras clave.
- Datos estructurados por proceso.
- Identificador OCID para trazabilidad.
- Exportación CSV/JSON para dashboard.
- Consulta de records/releases cuando se necesite detalle.

### 2. CONOSCE datos abiertos — histórico/BI

Portal:

```text
https://bi.seace.gob.pe/pentaho/api/repos/%3Apublic%3Aportal%3Adatosabiertos.html/content?userid=public&password=key
```

Descargas directas confirmadas:

```text
https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes/convocatorias/2026/CONOSCE_CONVOCATORIAS2026_0.xlsx
```

Uso del producto:

- Inteligencia histórica.
- Entidades que más compran.
- Montos por rubro/keyword.
- Análisis de proveedores adjudicados.
- Estudios de mercado para vender consultoría.

Limitación: actualización mensual y no necesariamente ideal para oportunidades en marcha.

### 3. Playwright — evidencia

Uso recomendado:

- Captura de ficha pública.
- Validación visual.
- Descarga manual/visual de documentos cuando la API no alcance.
- Demo comercial con evidencia en PNG/PDF.

No debe ser la fuente primaria de datos.

## Contrato de datos para Lovable

Lovable puede diseñar la interfaz sobre este modelo mínimo:

```json
{
  "keyword": "PUENTE",
  "ocid": "ocds-dgv273-seacev3-1221249",
  "tender_id": "1221249",
  "process_code": "SIE-SIE-4-2026-MML-OGA-OL-1",
  "entity_name": "MUNICIPALIDAD METROPOLITANA DE LIMA",
  "entity_id": "PE-CONSUCODE-1307",
  "description": "Descripción del objeto de contratación",
  "category": "works|goods|services",
  "procurement_method": "Licitación Pública / Subasta Inversa / etc.",
  "amount": 12345.67,
  "currency": "PEN",
  "date": "2026-06-02T10:23:17-05:00",
  "tender_start_date": "2026-06-01T00:00:00-05:00",
  "tender_end_date": "2026-06-10T00:00:00-05:00",
  "source": "Sistema Electrónico de Contrataciones del Estado - Versión 3",
  "api_url": "https://contratacionesabiertas.oece.gob.pe/api/v1/record/{ocid}?format=json",
  "record_url": "https://contratacionesabiertas.oece.gob.pe/api/v1/record/{ocid}?format=json"
}
```

## Pantallas recomendadas para Lovable

### Dashboard ejecutivo

Indicadores:

- Oportunidades nuevas.
- Monto total estimado.
- Oportunidades por keyword.
- Oportunidades por entidad.
- Oportunidades por categoría: obra, bienes, servicios.
- Próximos cierres.

### Bandeja de oportunidades

Columnas:

- Semáforo de urgencia.
- Keyword.
- Entidad.
- Código de proceso.
- Objeto resumido.
- Monto.
- Fecha de publicación.
- Fecha fin/presentación.
- Estado de revisión interna.
- Link API / evidencia.

### Vista detalle

Secciones:

- Datos generales del proceso.
- Cronograma.
- Entidad contratante.
- Valor referencial.
- Documentos/enlaces.
- Evidencias capturadas por Playwright.
- Notas comerciales.

### Inteligencia de mercado

Filtros:

- Keyword.
- Departamento/provincia/distrito cuando esté disponible.
- Entidad.
- Tipo de procedimiento.
- Categoría.
- Rango de monto.
- Año/mes.

## Comandos implementados

Buscar oportunidades reales vía API oficial y exportar CSV/JSON:

```bash
python seace_oportunidades.py --keywords PUENTE,CARRETERA,PILOTE --pages 1 --paginate-by 25 --output-dir reportes
```

Ejemplo de salida:

```text
Oportunidades encontradas: N
CSV: reportes/oportunidades-seace-YYYYMMDD-HHMMSS.csv
JSON: reportes/oportunidades-seace-YYYYMMDD-HHMMSS.json
```

## Roadmap recomendado

1. API OCDS + CSV/JSON normalizado. Hecho.
2. Ranking/scoring comercial de oportunidades.
3. Dedupe por OCID para detectar solo novedades.
4. Capturas Playwright bajo demanda para oportunidades seleccionadas.
5. Dashboard Lovable consumiendo JSON/CSV o backend simple.
6. Histórico CONOSCE para inteligencia comercial y benchmarking.
7. Seguimiento por OCID hasta buena pro, consentimiento, contrato o caída/reinicio del procedimiento. Ver `docs/seguimiento-adjudicacion-ux.md`.

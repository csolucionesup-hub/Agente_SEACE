# 🌉 Agente SEACE — Monitor de Proyectos de Obras

Bot automatizado en Python para monitorear y documentar proyectos de construcción de puentes en el portal público del **SEACE** (Sistema Electrónico de Contrataciones del Estado - Perú).

## 🎯 ¿Qué hace?

El agente tiene dos modos complementarios:

1. **Modo API oficial OCDS/OECE**: consulta la API pública de Contrataciones Abiertas, encuentra oportunidades por palabra clave y exporta datos precisos en CSV/JSON para dashboards, reportes o Lovable.
2. **Modo evidencia Playwright**: navega el buscador público del SEACE, entra a la ficha visible del procedimiento y toma capturas cuando se necesita respaldo visual para cliente.

La fuente primaria recomendada es la API oficial; Playwright queda como verificador/evidencia.

## 🗂️ Estructura del Proyecto

```
DCC_SEACE/
├── agente_seace.py         # Agente Playwright para evidencia visual/fichas
├── seace_api.py            # Cliente de API oficial OCDS/OECE
├── seace_oportunidades.py  # CLI: búsqueda API + exportación CSV/JSON
├── seace_config.py         # Configuración por variables de entorno
├── google_drive_handler.py # Módulo de integración con Google Drive API
├── tests/                  # Pruebas automáticas
├── docs/                   # Arquitectura comercial y contrato para Lovable
├── requirements.txt        # Dependencias del proyecto
├── .gitignore              # Archivos excluidos del repositorio
│
# --- Archivos locales (NO subir al repo) ---
├── credentials.json        # 🔒 Credenciales OAuth de Google (ignorado)
└── token.json              # 🔒 Token de sesión de Google Drive (ignorado)
```

## ⚙️ Instalación

### 1. Clonar el repositorio
```bash
git clone https://github.com/TU_USUARIO/DCC_SEACE.git
cd DCC_SEACE
```

### 2. Crear y activar entorno virtual
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
playwright install chromium
```

## 🔑 Configuración de Google Drive (Opcional)

Para que el agente suba las capturas automáticamente a Google Drive:

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto y habilita la **Google Drive API**
3. Crea credenciales de tipo **OAuth 2.0 (Desktop App)**
4. Descarga el archivo JSON y renómbralo a `credentials.json`
5. Colócalo en la raíz del proyecto

> ⚠️ **NUNCA subas `credentials.json` ni `token.json` a GitHub.** Están incluidos en `.gitignore`.

Si no configuras Google Drive, las capturas se guardarán localmente en la carpeta del proyecto.

## 🚀 Uso

### Modo recomendado: API oficial + exportación CSV/JSON

```bash
python seace_oportunidades.py --keywords PUENTE,CARRETERA,PILOTE --pages 1 --paginate-by 25 --output-dir reportes
```

El comando genera:

```text
reportes/oportunidades-seace-YYYYMMDD-HHMMSS.csv
reportes/oportunidades-seace-YYYYMMDD-HHMMSS.json
```

Estos archivos son el insumo recomendado para Lovable o para un dashboard comercial.

### Modo seguimiento: OCID activos hasta buena pro/contrato/caída

```bash
python seace_seguimiento.py \
  --db data/seace_tracking.sqlite3 \
  --dashboard reportes/dashboard-seguimiento.json \
  --ocids ocds-dgv273-seacev3-1221249,ocds-dgv273-seacev3-999999
```

Actualizar diariamente los procesos activos ya guardados:

```bash
python seace_seguimiento.py --active
```

El seguimiento guarda cada expediente por `ocid`, genera eventos comerciales y produce un JSON limpio para dashboard/Lovable:

- Nueva oportunidad.
- Buena pro otorgada.
- Contrato suscrito.
- Proceso caído/interrumpido.
- Fecha crítica actualizada.

### Dashboard web local: FastAPI + frontend propio

Primero genera o actualiza el JSON del seguimiento:

```bash
python seace_seguimiento.py \
  --db data/seace_tracking.sqlite3 \
  --dashboard reportes/dashboard-seguimiento.json \
  --active
```

Luego levanta el dashboard local:

```bash
python -m uvicorn web_app:app --host 127.0.0.1 --port 8765
```

Abre:

```text
http://127.0.0.1:8765/
```

Endpoints disponibles:

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/opportunities/{ocid}`

La capa web sirve JSON sanitizado: no expone blobs `raw_json` al frontend y agrega cabeceras básicas de seguridad.

### Modo evidencia visual: Playwright

```bash
python agente_seace.py
```

El agente:
1. Abre Chromium con Playwright
2. Navega al SEACE y aplica filtros de búsqueda
3. Entra a fichas de proyectos encontrados
4. Toma capturas de pantalla completas
5. Las sube a Google Drive si `credentials.json` existe; si no, las guarda localmente

### Variables de entorno útiles para demo

```bash
SEACE_HEADLESS=true
SEACE_KEYWORDS=PUENTE,CARRETERA,PILOTE
SEACE_YEAR_START=2025
SEACE_YEAR_END=2026
SEACE_MAX_PAGES=1
SEACE_MAX_CAPTURES=2
SEACE_OUTPUT_DIR=screenshots/demo
```

## 🛠️ Stack Tecnológico

| Herramienta | Uso |
|---|---|
| API OCDS/OECE | Fuente primaria de datos estructurados de contrataciones abiertas |
| Python stdlib `urllib` | Consultas HTTP sin dependencia adicional |
| CSV/JSON | Entregables para dashboard, Lovable y análisis comercial |
| [Playwright](https://playwright.dev/python/) | Automatización del navegador para evidencia visual |
| [Google Drive API](https://developers.google.com/drive) | Almacenamiento opcional en la nube |
| Python `asyncio` | Ejecución asíncrona para Playwright |
| `logging` | Registro detallado de cada acción del agente |

## 📋 Requisitos del Sistema

- Python 3.9+
- Conexión a internet
- Google Chrome / Chromium (Playwright lo instala automáticamente)

## 📄 Licencia

Proyecto interno — DCC (Dirección de Concesiones y Construcción). Uso reservado.

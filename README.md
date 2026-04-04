# 🌉 Agente SEACE — Monitor de Proyectos de Obras

Bot automatizado en Python para monitorear y documentar proyectos de construcción de puentes en el portal público del **SEACE** (Sistema Electrónico de Contrataciones del Estado - Perú).

## 🎯 ¿Qué hace?

El agente navega automáticamente el portal del SEACE, búsca procedimientos de selección de **Obras** (con filtro "puente") desde el año 2025 hasta el año actual, entra a la **Ficha de Selección** de cada proyecto encontrado, toma una captura de pantalla completa y la sube automáticamente a una carpeta de **Google Drive**.

## 🗂️ Estructura del Proyecto

```
DCC_SEACE/
├── agente_seace.py         # Agente principal (Playwright + lógica de navegación)
├── google_drive_handler.py # Módulo de integración con Google Drive API
├── test_ficha.py           # Tests aislados de componentes
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

```bash
python agente_seace.py
```

El agente:
1. Abre una ventana de Chromium visible
2. Navega al SEACE y aplica los filtros de búsqueda
3. Entra a cada ficha de proyecto de puente encontrada
4. Toma capturas de pantalla completas de cada ficha
5. Las sube a Google Drive en una carpeta `SEACE_Proyectos_YYYY-MM-DD`

## 🛠️ Stack Tecnológico

| Herramienta | Uso |
|---|---|
| [Playwright](https://playwright.dev/python/) | Automatización del navegador (RPA) |
| [Google Drive API](https://developers.google.com/drive) | Almacenamiento en la nube |
| Python `asyncio` | Ejecución asíncrona para performance |
| `logging` | Registro detallado de cada acción del agente |

## 📋 Requisitos del Sistema

- Python 3.9+
- Conexión a internet
- Google Chrome / Chromium (Playwright lo instala automáticamente)

## 📄 Licencia

Proyecto interno — DCC (Dirección de Concesiones y Construcción). Uso reservado.

# LicitaScan — Diseño del Sistema
**Fecha:** 2026-06-05
**Dominio:** licitascan.com
**Estado:** Aprobado

## Resumen

LicitaScan es una plataforma SaaS web que automatiza el monitoreo de licitaciones públicas peruanas del SEACE/OSCE. El usuario configura sus palabras clave y año de búsqueda; LicitaScan consulta la API OCDS oficial, muestra resultados estructurados, notifica por Telegram o email cuando aparece una licitación relevante o se adjudica la Buena Pro, y entrega los datos del ganador (empresa, RUC, monto) sin que el empresario navegue manualmente el portal del Estado.

**Propuesta de valor:** Recuperar las 2-3 horas semanales que un ingeniero pierde buscando manualmente en el SEACE.

**Diferenciador:** Especialización en obras de infraestructura y cimentaciones. Ningún competidor es nicho-específico.

---

## Planes y precios

| Plan | Precio | Búsquedas | Alertas | Datos Buena Pro | Usuarios |
|---|---|---|---|---|---|
| Gratis | S/. 0 | 10/mes | No | No (delay 48h) | 1 |
| Pro | S/. 149/mes | Ilimitadas | Sí | Sí (tiempo real) | 1 |
| Empresa | S/. 349/mes | Ilimitadas | Sí | Sí (tiempo real) | 5 + Excel |

**Cobros:** MercadoPago (suscripción recurrente). Acepta Yape, Plin, tarjeta, transferencia.

---

## Arquitectura

```
Cliente (Navegador)
        │ HTTPS
        ▼
FastAPI (Backend Python)
  ├── /auth        → Registro, login, sesiones JWT
  ├── /busquedas   → Ejecutar búsqueda OCDS
  ├── /alertas     → Configurar Telegram / email
  ├── /suscripcion → Planes, pagos MercadoPago
  └── /documentos  → Rutas de descarga (Playwright)
        │
        ├── ocds_client.py     → API OSCE pública
        ├── db.py              → SQLite vía SQLAlchemy
        ├── notificador.py     → Telegram Bot + SMTP
        ├── pagos.py           → MercadoPago webhooks
        ├── agente_seace.py    → Solo descarga de docs (Playwright)
        └── ia_helper.py       → Gemini fallback (solo si necesario)
```

**Stack:** Python 3.12 · FastAPI · SQLite · Jinja2 · MercadoPago · Telegram Bot API

---

## Base de datos (SQLite)

### Tabla: `usuarios`
| Campo | Tipo | Notas |
|---|---|---|
| id | INTEGER PK | |
| email | TEXT UNIQUE | |
| password_hash | TEXT | bcrypt |
| nombre | TEXT | |
| telegram_chat_id | TEXT NULL | se llena al conectar Telegram |
| creado_en | DATETIME | |

### Tabla: `suscripciones`
| Campo | Tipo | Notas |
|---|---|---|
| id | INTEGER PK | |
| usuario_id | FK → usuarios | |
| plan | TEXT | gratis / pro / empresa |
| estado | TEXT | activa / vencida / cancelada |
| vence_en | DATETIME | |
| mp_subscription_id | TEXT NULL | ID de MercadoPago |

### Tabla: `busquedas`
| Campo | Tipo | Notas |
|---|---|---|
| id | INTEGER PK | |
| usuario_id | FK → usuarios | |
| keywords | TEXT | separadas por coma |
| anio | INTEGER | |
| ejecutada_en | DATETIME | |
| total_hallazgos | INTEGER | |

### Tabla: `licitaciones`
| Campo | Tipo | Notas |
|---|---|---|
| id | INTEGER PK | |
| busqueda_id | FK → busquedas | |
| ocds_id | TEXT UNIQUE | ID oficial OCDS — índice único |
| titulo | TEXT | |
| entidad | TEXT | |
| monto_referencial | REAL NULL | |
| estado | TEXT | convocado / buena_pro / desierto |
| fecha_convocatoria | DATE | |
| ganador_nombre | TEXT NULL | se llena al detectar Buena Pro |
| ganador_ruc | TEXT NULL | |
| monto_adjudicado | REAL NULL | |
| url_expediente | TEXT | |
| notificado | BOOLEAN | cola de alertas pendientes |

### Tabla: `alertas_config`
| Campo | Tipo | Notas |
|---|---|---|
| id | INTEGER PK | |
| usuario_id | FK → usuarios | |
| keywords | TEXT | separadas por coma |
| anio_desde | INTEGER | |
| canal | TEXT | telegram / email / ambos |
| activa | BOOLEAN | |

---

## Flujos principales

### Flujo 1 — Registro
1. Email + contraseña → hash bcrypt → guardar en DB
2. Plan Gratis activo automáticamente
3. Redirect al dashboard

### Flujo 2 — Búsqueda manual
1. Usuario ingresa keywords + año → [Buscar]
2. Backend verifica cuota del plan (Gratis: 10/mes)
3. `ocds_client.py` consulta API OSCE con filtros
4. Resultados se guardan en `licitaciones` con `ocds_id` único
5. Se muestra tabla: título, entidad, monto, estado, fecha, link
6. Si estado = buena_pro → columnas extra: ganador, RUC, monto adjudicado
7. Se descuenta 1 búsqueda del plan

### Flujo 3 — Alertas automáticas
1. Usuario configura keywords + canal en `/alertas`
2. Job en background corre cada hora
3. Consulta API OCDS con las keywords de cada alerta activa
4. Por cada licitación nueva (no existe `ocds_id` en DB) → insertar + `notificado = false`
5. `notificador.py` procesa cola → envía mensaje Telegram o email
6. Marca `notificado = true`

**Formato mensaje Telegram:**
```
📡 LicitaScan — Nueva licitación detectada
─────────────────────────────────
📋 [título del proyecto]
🏛️ [entidad convocante]
💰 S/. [monto referencial]
📅 Convocado: [fecha]
🔗 Ver expediente → [url]
```

### Flujo 4 — Conexión Telegram
1. Usuario va a Configuración → Alertas → [Conectar Telegram]
2. Se muestra botón que abre t.me/LicitaScanBot con parámetro start=TOKEN_UNICO
3. Usuario presiona Start en Telegram
4. Bot recibe el token → busca usuario en DB → guarda `telegram_chat_id`
5. Confirmación en web: "Telegram conectado ✓"

### Flujo 5 — Upgrade de plan
1. Usuario alcanza límite gratuito → modal de upgrade
2. Selecciona plan Pro o Empresa
3. Redirect a MercadoPago Checkout
4. Pago exitoso → MercadoPago llama webhook `/pagos/webhook`
5. Backend actualiza `suscripciones` → plan activo
6. Si pago falla 3 días consecutivos → email al usuario + plan vuelve a Gratis

---

## Manejo de errores

| Situación | Comportamiento |
|---|---|
| API OCDS no responde | Reintento x3 con espera de 30s. Si persiste, encola para próxima hora. Usuario no ve error. |
| Licitación con datos incompletos | Muestra campos disponibles, marca faltantes como "No disponible" |
| Pago rechazado | MercadoPago reintenta. Tras 3 días fallidos → email al usuario |
| Usuario sin cuota intenta buscar | Bloqueo en servidor (no frontend). Muestra modal de upgrade. |
| SEACE cambia estructura web | Solo afecta descarga de docs (Playwright). Core OCDS no se rompe. |
| Token Telegram inválido o expirado | Token tiene TTL de 10 minutos. Si expira, usuario genera uno nuevo. |

---

## Estructura de archivos

```
licitascan/
├── main.py                     ← FastAPI app, rutas, startup
├── db.py                       ← Modelos SQLAlchemy + init DB
├── ocds_client.py              ← Cliente API OSCE (nuevo)
├── notificador.py              ← Telegram Bot + SMTP email
├── pagos.py                    ← MercadoPago webhooks + lógica de planes
├── agente_seace.py             ← Reducido: solo descarga de documentos
├── google_drive_handler.py     ← Se mantiene igual
├── ia_helper.py                ← Se mantiene igual
├── templates/
│   ├── base.html               ← Layout común, navbar, footer
│   ├── index.html              ← Landing page
│   ├── dashboard.html          ← Home post-login
│   ├── busqueda.html           ← Formulario + tabla de resultados
│   ├── alertas.html            ← Config alertas + conexión Telegram
│   └── cuenta.html             ← Plan actual, pagos, perfil
├── static/
│   ├── css/style.css
│   ├── js/app.js
│   └── img/logo.svg
├── .env                        ← Claves API (nunca en git)
└── requirements.txt
```

---

## Variables de entorno requeridas (.env)

```
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=LicitaScanBot
MP_ACCESS_TOKEN=                    ← MercadoPago producción
MP_WEBHOOK_SECRET=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SECRET_KEY=                         ← JWT signing key
DATABASE_URL=sqlite:///licitascan.db
```

---

## API OCDS — Endpoint principal

```
GET https://contratacionesabiertas.osce.gob.pe/api/search
Params:
  q          = keyword (ej: "pilotes")
  year       = año convocatoria
  ocid_prefix= PE (Perú)
  status     = active / complete / cancelled
```

La respuesta OCDS estándar incluye:
- `tender.title` → título
- `buyer.name` → entidad
- `tender.value.amount` → monto referencial
- `tender.status` → estado
- `awards[].suppliers[].name` → ganador (si hay Buena Pro)
- `awards[].suppliers[].identifier.id` → RUC del ganador
- `awards[].value.amount` → monto adjudicado

---

## Decisiones de diseño

- **SQLite sobre PostgreSQL:** El producto lanza como MVP. SQLite es suficiente para cientos de usuarios. Migración a PostgreSQL es una tarea de 2 horas cuando sea necesario.
- **Jinja2 sobre React:** Reduce complejidad. El producto no requiere interactividad compleja en el cliente. Bootstrap + htmx para actualizaciones parciales si se necesitan.
- **MercadoPago sobre Stripe:** Stripe no está disponible nativamente en Perú. MercadoPago acepta Yape, Plin y medios locales.
- **OCDS API sobre scraping:** La API pública es más estable, rápida y estructurada que el scraping del portal web. El scraper Playwright se conserva solo para descarga de documentos.
- **Un bot Telegram propio:** El usuario no crea nada. Solo presiona Start en el bot de LicitaScan.

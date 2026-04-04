import asyncio
import logging
import os
import datetime
from playwright.async_api import async_playwright, Page
from google_drive_handler import GDriveHandler
from ia_helper import cerebro_ia

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Palabras clave a buscar en el portal SEACE
KEYWORDS_INGENIERIA = ["PUENTE", "PILOTES", "CIMENTACION", "MURO PANTALLA", "VIADUCTO"]

async def esperar_procesamiento(page: Page):
    """Espera a que los indicadores de carga de PrimeFaces desaparezcan."""
    try:
        await page.wait_for_selector(".ui-blockui", state="hidden", timeout=10000)
        await page.wait_for_selector(".status-dialog", state="hidden", timeout=10000)
    except:
        pass  # Si no aparecen, continuamos

async def clic_con_vision_ia(page: Page, tarea_objetivo: str) -> bool:
    """
    Fallback inteligente: si un selector fijo falla, la IA analiza el DOM
    y propone el selector correcto para completar la tarea.
    """
    if cerebro_ia is None:
        logger.warning("🤖 Fallback de IA no disponible (sin API Key).")
        return False
    try:
        logger.info(f"🧠 Consultando a Gemini para: {tarea_objetivo}...")
        html_contexto = await page.locator("form").inner_html()
        nuevo_selector = await cerebro_ia.razonar_selector(html_contexto, tarea_objetivo)

        if nuevo_selector:
            logger.info(f"👁️ IA encontró el elemento: '{nuevo_selector}'")
            await page.locator(nuevo_selector).scroll_into_view_if_needed()
            await page.click(nuevo_selector, force=True)
            return True

        return False
    except Exception as e:
        logger.error(f"❌ La visión de IA falló: {e}")
        return False

async def seleccionar_opcion_primefaces(page: Page, label_text: str, option_text: str):
    """Selección semántica label → tr → dropdown, con fallback de IA."""
    try:
        # Paso 1: Localizar la fila (<tr>) que contiene el label buscado
        # Luego escoger el div.ui-selectonemenu dentro de esa fila — semántico y único
        fila_label = page.locator(
            f"xpath=//label[contains(text(), '{label_text}')]/ancestor::tr[1]"
        )
        container = fila_label.locator("div.ui-selectonemenu").first

        # Paso 2: Asegurarnos que es visible y hacer scroll antes de cualquier clic
        await container.wait_for(state="visible", timeout=10000)
        await container.scroll_into_view_if_needed()

        # Paso 3: Abrir el panel con force=True para ignorar overlays de PrimeFaces
        await container.locator(".ui-selectonemenu-trigger").click(force=True)

        # Paso 4: Esperar el panel flotante y seleccionar la opción
        panel_selector = "div.ui-selectonemenu-panel:visible"
        await page.wait_for_selector(panel_selector, state="visible", timeout=5000)
        await page.locator(f"{panel_selector} li.ui-selectonemenu-item").filter(
            has_text=option_text
        ).first.click()

        await esperar_procesamiento(page)
        logger.info(f"✅ Seleccionado '{option_text}' en '{label_text}'")
        return True

    except Exception as e:
        logger.warning(f"⚠️ Error al seleccionar '{label_text}': {e}. Activando visión IA...")
        # Delegar completamente a la IA para que encuentre y accione el dropdown
        return await clic_con_vision_ia(
            page,
            f"seleccionar la opción '{option_text}' en el menú desplegable cuyo label dice '{label_text}'"
        )

async def capturar_y_subir(page: Page, texto_proyecto: str, year: int, drive_handler: GDriveHandler, folder_id: str):
    """Genera una captura completa de la Ficha de Selección y la sube."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_text = "".join([c if c.isalnum() else "_" for c in texto_proyecto[:20]])
        filename = f"Ficha_{year}_{safe_text}_{timestamp}.png"
        filepath = os.path.join(os.getcwd(), filename)
        
        # Realizar captura de toda la página de manera limpia (full page)
        await page.screenshot(path=filepath, full_page=True)
        logger.info(f"📸 Captura de Ficha guardada localmente: {filename}")

        # Subir a Drive si el handler está listo
        if drive_handler and folder_id:
            drive_handler.upload_file(filepath, folder_id)
            # Opcional: borrar local después de subir
            # os.remove(filepath)
        
        return True
    except Exception as e:
        logger.error(f"Error en capturar_y_subir: {e}")
        return False

async def scanear_resultados(page: Page, year: int, drive_handler: GDriveHandler, folder_id: str):
    """Escanea la tabla y gestiona hallazgos."""
    try:
        table_selector = 'tbody[id$="dtProcesos_data"]'
        row_selector = f'{table_selector} tr.ui-widget-content'

        # TIP SENIOR: Verificación temprana de tabla vacía antes de iterar
        empty_msg = page.locator('td.ui-datatable-empty-message')
        if await empty_msg.is_visible():
            logger.info("ℹ️ No se encontraron resultados en esta página.")
            return False

        await page.wait_for_selector(row_selector, state="visible", timeout=30000)
        count = await page.locator(row_selector).count()

        encontrado_en_esta_pagina = False
        for i in range(count):
            # Recargar el locator base de la fila CADA iteración
            await page.wait_for_selector(row_selector, state="visible", timeout=30000)
            fila = page.locator(row_selector).nth(i)

            texto_fila = await fila.inner_text()
            texto_proyecto = texto_fila.upper()
            
            if any(key in texto_proyecto for key in KEYWORDS_INGENIERIA) and len(texto_fila.strip()) > 10:
                logger.info(f"🎯 Hallazgo relevante: {texto_proyecto[:50]}...")

                # Clic en el botón "Ver Ficha de Selección" (2do icono en 'Acciones')
                btn_ficha = fila.locator('td').last.locator('a, button').nth(1)
                await btn_ficha.click(force=True)

                # Esperamos que aparezca la ficha
                await page.wait_for_selector('text="Regresar"', state="visible", timeout=30000)
                await page.wait_for_timeout(1000)

                await capturar_y_subir(page, texto_fila, year, drive_handler, folder_id)

                # Volver a resultados
                await page.locator('text="Regresar"').first.click(force=True)
                await esperar_procesamiento(page)
                await page.wait_for_selector(row_selector, state="visible", timeout=30000)
                await page.wait_for_timeout(2000)

                encontrado_en_esta_pagina = True

        return encontrado_en_esta_pagina
    except Exception as e:
        logger.error(f"Error en escaneo: {e}")
        return False

async def ejecutar_agente():
    # Inicializar Drive si existen credenciales
    logger.info("Verificando integración con Google Drive...")
    drive_handler = None
    folder_id = None
    if os.path.exists('credentials.json'):
        try:
            drive_handler = GDriveHandler()
            folder_id = drive_handler.get_or_create_folder(f"SEACE_Proyectos_{datetime.datetime.now().strftime('%Y-%m-%d')}")
        except Exception as e:
            logger.error(f"No se pudo iniciar DriveHandler: {e}")
    else:
        logger.warning("FALTA 'credentials.json'. Las capturas solo se guardarán localmente.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--ssl-version-min=tls1', '--ignore-certificate-errors', '--window-size=1280,720']
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            TIMEOUT_PORTAL = 45000 
            logger.info("🤖 Iniciando navegación al SEACE...")
            # Cambiado a domcontentloaded y pausa manual para PrimeFaces
            await page.goto("https://prod2.seace.gob.pe/seacebus-uiwd-pub/publico/buscadorPublico.xhtml", 
                          wait_until="domcontentloaded", timeout=TIMEOUT_PORTAL)
            await page.wait_for_timeout(3000)
            
            try:
                await page.click('a:has-text("Buscador de Procedimientos de Selección")', force=True)
                await page.wait_for_selector('div[id$="tab1"][aria-hidden="false"]', timeout=15000)
                # Esperar al panel principal del buscador y a que PrimeFaces termine de renderizar
                await page.wait_for_selector('form[id$="frmBuscar"], div[id$="idPanelBusquedaProceso"]', state="visible", timeout=TIMEOUT_PORTAL)
                await page.wait_for_timeout(1500)
                logger.info("✅ Panel de búsqueda detectado.")
            except Exception as nav_e:
                logger.error(f"❌ No se pudo cargar el buscador por vía normal: {nav_e}")
                # Entramos a la capa de visión IA de ser necesario
                await clic_con_vision_ia(page, "el botón o pestaña para abrir el buscador de procedimientos de selección")
                await page.wait_for_selector('form[id$="frmBuscar"], div[id$="idPanelBusquedaProceso"]', state="visible", timeout=TIMEOUT_PORTAL)
                await page.wait_for_timeout(1500)
                logger.info("✅ Panel de búsqueda detectado vía IA.")

            anyo_inicial = 2025
            anyo_actual = datetime.datetime.now().year

            for anyo in range(anyo_inicial, anyo_actual + 1):
                for keyword in KEYWORDS_INGENIERIA:
                    logger.info(f"🚀 Iniciando búsqueda: año={anyo}, keyword='{keyword}'...")

                    # Seleccionar parámetros de búsqueda
                    await seleccionar_opcion_primefaces(page, "Objeto de Contratación", "Obra")
                    await seleccionar_opcion_primefaces(page, "Año de la Convocatoria", str(anyo))

                    # Rellenar el filtro de descripción — :visible evita escribir en el campo oculto de PrimeFaces
                    input_desc = page.locator('input[id$="descripcionObjeto"]:visible').first
                    await input_desc.wait_for(state="visible")
                    await input_desc.fill(keyword)

                    # Buscar — usa JS click como fallback si el botón aparece deshabilitado
                    btn_buscar = page.locator('button[id$="btnBuscarSelToken"]')
                    try:
                        await btn_buscar.click(force=True)
                    except Exception:
                        logger.warning("⚠️ Clic normal falló, usando JavaScript click en botón buscar...")
                        await page.evaluate('document.querySelector("[id$=\'btnBuscarSelToken\']").click()')
                    await esperar_procesamiento(page)
                    await page.wait_for_load_state("networkidle")

                    pagina = 1
                    while True:
                        logger.info(f"📄 [{keyword}] Año {anyo} - Revisando página {pagina}...")
                        await scanear_resultados(page, anyo, drive_handler, folder_id)

                        next_btn = page.locator('.ui-paginator-next').first
                        is_disabled = "ui-state-disabled" in (await next_btn.get_attribute("class") or "")

                        if is_disabled:
                            break

                        await next_btn.click()
                        await esperar_procesamiento(page)
                        await page.wait_for_load_state("networkidle")
                        pagina += 1

                    logger.info(f"✅ Búsqueda terminada: año={anyo}, keyword='{keyword}'.")

        except Exception as e:
            logger.error(f"Error crítico: {e}")
        finally:
            await browser.close()
            logger.info("🔒 Auditoría completada.")

if __name__ == "__main__":
    asyncio.run(ejecutar_agente())
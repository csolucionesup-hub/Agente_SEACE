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
KEYWORDS = ["puente", "pilotes", "cimentación profunda", "muro pantalla"]

async def esperar_procesamiento(page: Page):
    """Espera a que el indicador de carga de PrimeFaces desaparezca."""
    try:
        await page.wait_for_selector(".ui-blockui", state="hidden", timeout=10000)
    except:
        pass  # Si no aparece el overlay, no hay problema

async def seleccionar_opcion_primefaces(page: Page, label_text: str, option_text: str):
    """Selección ultra-robusta para componentes PrimeFaces con fallback de IA."""
    try:
        # Estrategia principal: localizar el contenedor del dropdown por label cercano
        container = page.locator("div.ui-selectonemenu").filter(
            has=page.locator(f"xpath=ancestor::tr//label[contains(text(), '{label_text}')]")
        ).first

        trigger = container.locator(".ui-selectonemenu-trigger")
        await trigger.click()

        panel_selector = "div.ui-selectonemenu-panel[style*='display: block']"
        await page.wait_for_selector(panel_selector, state="visible")

        await page.locator(f"{panel_selector} li.ui-selectonemenu-item").filter(
            has_text=option_text
        ).first.click()

        await esperar_procesamiento(page)
        logger.info(f"✅ Seleccionado '{option_text}' en '{label_text}'")
        return True

    except Exception as e:
        logger.warning(f"⚠️ Selector principal falló para '{label_text}': {e}")

        if cerebro_ia is None:
            logger.warning("🤖 Fallback de IA no disponible (sin API Key).")
            return False

        logger.info("🤖 Activando fallback de IA (Gemini)...")
        try:
            html_form = await page.locator("form").first.inner_html()
            objetivo = f"Hacer clic en el trigger del dropdown cuyo label dice '{label_text}'"
            selector_ia = await cerebro_ia.razonar_selector(html_form, objetivo)

            if selector_ia:
                await page.click(selector_ia, force=True)
                panel_selector = "div.ui-selectonemenu-panel[style*='display: block']"
                await page.wait_for_selector(panel_selector, state="visible")
                await page.locator(f"{panel_selector} li.ui-selectonemenu-item").filter(
                    has_text=option_text
                ).first.click()
                await esperar_procesamiento(page)
                logger.info(f"✅ [IA] Seleccionado '{option_text}' en '{label_text}'")
                return True
        except Exception as e_ia:
            logger.error(f"❌ Fallback de IA también falló ({label_text}): {e_ia}")

        return False

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
            if len(texto_fila.strip()) > 10:
                logger.info(f"🌉 ENTRANDO A FICHA: {texto_fila.strip()[:60]}...")

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
            logger.info("🤖 Iniciando navegación al SEACE...")
            await page.goto("https://prod2.seace.gob.pe/seacebus-uiwd-pub/publico/buscadorPublico.xhtml", 
                          wait_until="networkidle", timeout=60000)
            await page.click('a:has-text("Buscador de Procedimientos de Selección")')
            await page.wait_for_selector('div[id$="tab1"][aria-hidden="false"]', timeout=15000)

            anyo_inicial = 2025
            anyo_actual = datetime.datetime.now().year

            for anyo in range(anyo_inicial, anyo_actual + 1):
                for keyword in KEYWORDS:
                    logger.info(f"🚀 Iniciando búsqueda: año={anyo}, keyword='{keyword}'...")

                    # Seleccionar parámetros de búsqueda
                    await seleccionar_opcion_primefaces(page, "Objeto de Contratación", "Obra")
                    await seleccionar_opcion_primefaces(page, "Año de la Convocatoria", str(anyo))

                    # Rellenar el filtro de descripción con la keyword actual
                    input_desc_selector = 'input[id$="descripcionObjeto"]'
                    await page.wait_for_selector(input_desc_selector, state="visible")
                    await page.fill(input_desc_selector, keyword, force=True)

                    # Buscar y esperar respuesta AJAX de PrimeFaces
                    await page.click('button[id$="btnBuscarSelToken"]', force=True)
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
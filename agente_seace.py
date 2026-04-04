import asyncio
import logging
import os
import datetime
from playwright.async_api import async_playwright, Page
from google_drive_handler import GDriveHandler

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def seleccionar_opcion_primefaces(page: Page, label_text: str, option_text: str, timeout: int = 15000):
    """Selecciona una opción en un componente SelectOneMenu de PrimeFaces."""
    try:
        label_locator = page.get_by_text(label_text).first
        label_for = await label_locator.get_attribute('for')
        base_id = label_for if label_for else None
        
        if not base_id:
            label_id = await label_locator.get_attribute('id')
            if label_id and '_label' in label_id:
                base_id = label_id.replace('_label', '')
        
        if base_id:
            trigger_selector = f'div[id$="{base_id}"] .ui-selectonemenu-trigger'
        else:
            trigger_selector = f'xpath=//td[contains(., "{label_text}")]/following-sibling::td//div[contains(@class, "ui-selectonemenu-trigger")]'

        await page.wait_for_selector(trigger_selector, state="visible", timeout=timeout)
        await page.click(trigger_selector, force=True)

        await page.wait_for_selector('div.ui-selectonemenu-panel:visible', state="visible", timeout=timeout)
        option_locator = page.locator('div.ui-selectonemenu-panel:visible li.ui-selectonemenu-item').filter(has_text=option_text).first
        await option_locator.click(force=True)
        # Primefaces carga un overlay transparente después de seleccionar, hay que esperar un poco
        await page.wait_for_timeout(1500)
        
        logger.info(f"✅ Seleccionado '{option_text}' en '{label_text}'")
        return True
    except Exception as e:
        logger.warning(f"⚠️ No se pudo seleccionar '{option_text}' en '{label_text}': {str(e)}")
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
        # Esperar específicamente a las filas de datos con contenido real, no a la tabla vacía
        table_selector = 'tbody[id$="dtProcesos_data"]'
        
        # Esperar hasta que aparezca la clase ui-widget-content que indica filas reales
        row_selector = f'{table_selector} tr.ui-widget-content'
        await page.wait_for_selector(row_selector, state="visible", timeout=30000)
        
        # Extraemos count primero. Si la tabla cambia, count en teoría es idéntico por página
        count = await page.locator(row_selector).count()
        
        encontrado_en_esta_pagina = False
        for i in range(count):
            # Recargar el locator base de la fila CADA iteración
            await page.wait_for_selector(row_selector, state="visible", timeout=30000)
            fila = page.locator(row_selector).nth(i)
            
            # Validar que no sea la fila de "No se encontraron registros"
            clases = await fila.get_attribute("class")
            if clases and "ui-datatable-empty-message" in clases:
                break
                
            texto_fila = await fila.inner_text()
            if len(texto_fila.strip()) > 10:
                logger.info(f"🌉 ENTRANDO A FICHA: {texto_fila.strip()[:60]}...")
                
                # Clic en el botón "Ver Ficha de Selección" (es el 2do icono en 'Acciones')
                btn_ficha = fila.locator('td').last.locator('a, button').nth(1)
                await btn_ficha.click(force=True)
                
                # Esperamos que aparezca la ficha (buscando el texto Regresar)
                await page.wait_for_selector('text="Regresar"', state="visible", timeout=30000)
                await page.wait_for_timeout(1000) # Dejar que termine de pintar la UI
                
                # Toma foto a toda la ficha y la sube
                await capturar_y_subir(page, texto_fila, year, drive_handler, folder_id)
                
                # Volver a resultados
                await page.locator('text="Regresar"').first.click(force=True)
                
                # Esperar a que la tabla vuelva a aparecer para seguir la iteración asincronamente
                await page.wait_for_selector(row_selector, state="visible", timeout=30000)
                await page.wait_for_timeout(2000) # Espera a estabilizar PrimeFaces
                
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
            folder_id = drive_handler.create_folder(f"SEACE_Proyectos_{datetime.datetime.now().strftime('%Y-%m-%d')}")
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
                logger.info(f"🚀 Iniciando búsqueda para el año {anyo}...")
                
                # Seleccionar parámetros comunes
                await seleccionar_opcion_primefaces(page, "Objeto de Contratación", "Obra")
                await seleccionar_opcion_primefaces(page, "Año de la Convocatoria", str(anyo))
                
                # Audit Fix: Usar el filtro de descripción para buscar 'puente' directamente
                # Esto es MUCHO más eficiente que escanear páginas manualmente
                input_desc_selector = 'input[id$="descripcionObjeto"]'
                await page.wait_for_selector(input_desc_selector, state="visible")
                await page.fill(input_desc_selector, "puente", force=True)

                # Buscar
                await page.click('button[id$="btnBuscarSelToken"]', force=True)
                # Esperar a que pase el AJAX de PrimeFaces
                await page.wait_for_timeout(3000)
                await page.wait_for_load_state("networkidle")

                pagina = 1
                while True:
                    logger.info(f"📄 Año {anyo} - Revisando página {pagina}...")
                    await scanear_resultados(page, anyo, drive_handler, folder_id)
                    
                    next_btn = page.locator('.ui-paginator-next').first
                    is_disabled = "ui-state-disabled" in (await next_btn.get_attribute("class") or "")
                    
                    if is_disabled:
                        break
                    
                    await next_btn.click()
                    await page.wait_for_load_state("networkidle")
                    pagina += 1
                
                logger.info(f"✅ Búsqueda terminada para el año {anyo}.")

        except Exception as e:
            logger.error(f"Error crítico: {e}")
        finally:
            await browser.close()
            logger.info("🔒 Auditoría completada.")

if __name__ == "__main__":
    asyncio.run(ejecutar_agente())
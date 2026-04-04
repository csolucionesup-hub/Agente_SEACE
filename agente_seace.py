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
        html_contexto = await page.locator("body").inner_html()
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
        # Paso 1: Localizar la fila (<tr>) que contiene el texto de la etiqueta
        # Cambiado a //*[contains(text()...)] porque PrimeFaces a menudo usa <td> en lugar de <label>
        fila_label = page.locator(
            f"xpath=//*[contains(text(), '{label_text}')]/ancestor::tr[1]"
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

async def capturar_ficha_seace(page: Page, texto_proyecto: str, year: int, drive_handler: GDriveHandler, folder_id: str):
    """Espera el renderizado completo de la ficha y toma la captura."""
    try:
        # 1. Espera de Seguridad: Verificamos que el cronograma cargó
        await page.wait_for_selector('text="Cronograma"', state="visible", timeout=30000)
        
        # 2. Pequeña pausa para que PrimeFaces termine las animaciones de tablas
        await page.wait_for_timeout(2000)
        
        # 3. Generar nombre de archivo único
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join([c if c.isalnum() else "_" for c in texto_proyecto[:30]])
        filename = f"FICHA_{year}_{safe_name}_{timestamp}.png"
        filepath = os.path.join(os.getcwd(), filename)
        
        # 4. CAPTURA FULL PAGE: Esto asegura que se vea toda la ficha
        await page.screenshot(path=filepath, full_page=True)
        logger.info(f"📸 Captura de ficha realizada localmente: {filename}")

        # 5. Subida inmediata a Google Drive
        if drive_handler and folder_id:
            file_id = drive_handler.upload_file(filepath, folder_id)
            if file_id:
                logger.info(f"🚀 Respaldado en Drive con ID: {file_id}")
                os.remove(filepath)  # Limpieza local automática
        
        # 6. Regresar a la lista de resultados usando el botón marcado en rojo
        btn_regresar = page.locator('button:has-text("Regresar"), a:has-text("Regresar"), span:has-text("Regresar")').first
        await btn_regresar.click(force=True)
        await esperar_procesamiento(page)
        
        # Esperar a que la tabla principal (resultados) vuelva a ser visible
        await page.wait_for_selector('tbody[id$="dtProcesos_data"]', state="visible", timeout=30000)
        await page.wait_for_timeout(1000)
        
        return True
    except Exception as e:
        logger.error(f"❌ Error al capturar la ficha: {e}")
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

                # 🎯 LOCALIZADOR DE PRECISIÓN para el icono de la Ficha (evita Lupas o Historial)
                btn_ficha = fila.locator('td').last.locator('a, button').filter(
                    has=page.locator('img[src*="ficha"], img[src*="cronograma"], .ui-icon-calendar, [title*="Ficha"], [title*="Cronograma"]')
                ).first

                if await btn_ficha.is_visible():
                    logger.info(f"📅 Clic en Icono de Calendario (Ficha) para: {texto_fila[:40]}...")
                    await btn_ficha.click(force=True)

                    # La validación 'Regresar' se mantiene como señal de que llegamos a la Ficha
                    await page.wait_for_selector('text="Regresar"', state="visible", timeout=30000)

                    # La función capturar_ficha_seace se encarga de esperar el cronograma, capturar y regresar
                    await capturar_ficha_seace(page, texto_fila, year, drive_handler, folder_id)
                else:
                    logger.warning(f"⚠️ No se encontró el icono de Ficha en la fila: {texto_fila[:40]}...")
                    continue

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
                # Filtrar el clic para tomar el tab explícito usando la clase CSS de PrimeFaces o nth(0)
                btn_tab = page.locator('a:has-text("Buscador de Procedimientos de Selección")').first
                await btn_tab.click(force=True)
                
                # Esperar al panel principal observando de forma estructural que carguen los campos clave
                # Usamos locator().first.wait_for para evitar errores de Strict Mode ("resolved to 2 elements")
                await page.locator("input[id$='idFormBuscarProceso:descripcionObjeto']").first.wait_for(state="visible", timeout=TIMEOUT_PORTAL)
                await page.wait_for_timeout(1500)
                logger.info("✅ Panel de búsqueda detectado.")
            except Exception as nav_e:
                logger.error(f"❌ No se pudo cargar el buscador por vía normal: {nav_e}")
                # Entramos a la capa de visión IA de ser necesario
                await clic_con_vision_ia(page, "el botón o pestaña para abrir el buscador de procedimientos de selección")
                await page.locator("input[id$='idFormBuscarProceso:descripcionObjeto']").first.wait_for(state="visible", timeout=TIMEOUT_PORTAL)
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
                    
                    # PASO 3: Ver que la versión del SEACE sea la versión 3
                    await seleccionar_opcion_primefaces(page, "Version SEACE", "Seace 3")

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
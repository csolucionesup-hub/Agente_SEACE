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
        # Paso 1: Restringimos la búsqueda EXCLUSIVAMENTE al panel de pestaña visible 
        # Extraemos la celda contigua exacta (following-sibling::td) para evitar colisiones en filas con múltiples campos
        panel_activo = page.locator('.ui-tabs-panel:visible').first
        trigger_locator = panel_activo.locator(
            f"xpath=descendant::td[contains(., '{label_text}')]/following-sibling::td[1]//div[contains(@class, 'ui-selectonemenu')]"
        ).first.locator(".ui-selectonemenu-trigger")

        await trigger_locator.scroll_into_view_if_needed()

        # Paso 3: Abrir el panel con force=True para ignorar overlays de PrimeFaces
        await trigger_locator.click(force=True, timeout=10000)

        # Paso 4: Esperar el panel flotante y seleccionar la opción con coincidencia EXACTA
        panel_selector = "div.ui-selectonemenu-panel:visible"
        await page.wait_for_selector(panel_selector, state="visible", timeout=5000)
        # Usamos :text-is para asegurar coincidencia exacta ('Obra' vs 'Consultoría de Obra')
        await page.locator(f"{panel_selector} li.ui-selectonemenu-item:text-is('{option_text}')").first.click()

        await esperar_procesamiento(page)
        # TRUCO SENIOR: PrimeFaces tarda un milisegundo en despachar el Ajax que borra el DOM. 
        # Si no esperamos fijamente aquí, Playwright intentará ubicar el siguiente cuadro de texto y...
        # ...luego PrimeFaces lo borrará por debajo, dejando a Playwright en un timeout eterno.
        await page.wait_for_timeout(2000)
        
        logger.info(f"✅ Seleccionado '{option_text}' en '{label_text}'")
        return True

    except Exception as e:
        logger.warning(f"⚠️ Error al seleccionar '{label_text}': {e}. Activando visión IA...")
        # Delegar completamente a la IA para que encuentre y accione el dropdown
        return await clic_con_vision_ia(
            page,
            f"seleccionar la opción '{option_text}' en el menú desplegable cuyo label dice '{label_text}'"
        )

async def capturar_ficha_seace(page: Page, keyword: str, institucion: str, year: int, drive_handler: GDriveHandler, folder_id: str):
    """Espera el renderizado completo de la ficha y toma la captura."""
    try:
        # 1. Espera de Seguridad: Verificamos que el cronograma cargó
        await page.wait_for_selector('text="Cronograma"', state="visible", timeout=30000)
        
        # 2. Pequeña pausa para que PrimeFaces termine las animaciones de tablas
        await page.wait_for_timeout(2000)
        
        # 3. Generar nombre de archivo con orden exacto: PALABRA_CLAVE + FECHA + ENTIDAD
        fecha_captura = datetime.datetime.now().strftime("%Y%m%d")
        safe_keyword = keyword.replace(" ", "_").upper()
        safe_institucion = "".join([c if c.isalnum() else "_" for c in institucion.strip()[:60]])
        # Estructura final: PUENTE_20260404_MUNICIPALIDAD.png
        filename = f"{safe_keyword}_{fecha_captura}_{safe_institucion}.png"
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

async def scanear_resultados(page: Page, keyword: str, year: int, drive_handler: GDriveHandler, folder_id: str):
    """Escanea la tabla y gestiona hallazgos."""
    try:
        table_selector = 'tbody[id$="dtProcesos_data"]'
        row_selector = f'{table_selector} tr.ui-widget-content'

        # TIP SENIOR: Esperar un momento a que el AJAX dibuje los resultados o el mensaje de vacío
        await page.wait_for_timeout(1500)
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

                    # Obtener la Institución (usualmente en la segunda columna)
                    institucion_texto = await fila.locator('td').nth(1).inner_text()

                    # La validación 'Regresar' se mantiene como señal de que llegamos a la Ficha
                    await page.wait_for_selector('text="Regresar"', state="visible", timeout=30000)

                    # La función capturar_ficha_seace se encarga de esperar el cronograma, capturar y regresar
                    await capturar_ficha_seace(page, keyword, institucion_texto, year, drive_handler, folder_id)
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
                # Filtrar el clic para tomar el tab explícito usando el rol seguro de PrimeFaces
                btn_tab = page.locator("li[role='tab']:has-text('Buscador de Procedimientos de Selección')").first
                await btn_tab.click(force=True)
                
                # Esperamos a que el panel estructural cambie a visible mediante su etiqueta
                panel_activo = page.locator('.ui-tabs-panel:visible').first
                await panel_activo.locator('xpath=descendant::*[contains(text(), "Objeto de Contratación")]').first.wait_for(state="visible", timeout=TIMEOUT_PORTAL)
                await page.wait_for_timeout(1500)
                logger.info("✅ Panel de búsqueda detectado.")
            except Exception as nav_e:
                logger.error(f"❌ No se pudo cargar el buscador por vía normal: {nav_e}")
                # Entramos a la capa de visión IA de ser necesario
                await clic_con_vision_ia(page, "el botón o pestaña para abrir el buscador de procedimientos de selección")
                panel_activo = page.locator('.ui-tabs-panel:visible').first
                await panel_activo.locator('xpath=descendant::*[contains(text(), "Objeto de Contratación")]').first.wait_for(state="visible", timeout=TIMEOUT_PORTAL)
                await page.wait_for_timeout(1500)
                logger.info("✅ Panel de búsqueda detectado vía IA.")

            anyo_inicial = 2025
            anyo_actual = datetime.datetime.now().year

            for anyo in range(anyo_inicial, anyo_actual + 1):
                logger.info(f"📅 Configurando parámetros fijos para el año {anyo}...")
                # Seleccionar parámetros fijos por año
                await seleccionar_opcion_primefaces(page, "Objeto de Contratación", "Obra")
                await seleccionar_opcion_primefaces(page, "Año de la Convocatoria", str(anyo))
                await seleccionar_opcion_primefaces(page, "Version SEACE", "Seace 3")
                
                for keyword in KEYWORDS_INGENIERIA:
                    logger.info(f"🚀 Iniciando búsqueda: año={anyo}, keyword='{keyword}'...")

                    # Rellenar el filtro de descripción — Búsqueda dentro del panel usando su sufijo estático (inmune a j_idt)
                    panel_activo = page.locator('.ui-tabs-panel:visible').first
                    input_desc = panel_activo.locator('input[id$=":descripcionObjeto"]').first
                    
                    # Playwright maneja internamente la espera con fill
                    await input_desc.fill(keyword, timeout=15000)

                    # Buscar — Localiza el botón 'Buscar' explícitamente en el panel visible
                    btn_buscar = panel_activo.locator('button:has-text("Buscar"), button[id$="btnBuscarSelToken"]').first
                    try:
                        await btn_buscar.click(force=True)
                    except Exception:
                        logger.warning("⚠️ Clic normal falló, usando JavaScript click en botón buscar...")
                        await btn_buscar.evaluate('node => node.click()')
                    await esperar_procesamiento(page)
                    await page.wait_for_load_state("networkidle")

                    pagina = 1
                    while True:
                        logger.info(f"📄 [{keyword}] Año {anyo} - Revisando página {pagina}...")
                        await scanear_resultados(page, keyword, anyo, drive_handler, folder_id)

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
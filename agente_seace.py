import asyncio
import logging
import os
import re
import datetime
from playwright.async_api import async_playwright, Page
from google_drive_handler import GDriveHandler
from ia_helper import cerebro_ia
from seace_config import RuntimeConfig, get_runtime_config, DEFAULT_SEACE_URL

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Palabras clave a buscar en el portal SEACE
KEYWORDS_INGENIERIA = [
    "PUENTE", "CARRETERA", "PILOTE", "MICROPILOTE",
    "CFA", "MUELLE", "PILOTE HINCADO"
]

_YEAR_RE = re.compile(r"20\d{2}")


def _derive_year_from_nomenclatura(nomenclatura: str, fallback: int | None = None) -> int:
    """Extrae el año (20xx) de la nomenclatura, p.ej. 'LP-ABR-2-2025-CS-MDPP-1' -> 2025.

    Si el parseo falla (formato raro, sin año), cae al `fallback` dado y, en última
    instancia, al año actual. Así la captura dirigida nunca se queda sin filtro de año.
    """
    match = _YEAR_RE.search(nomenclatura or "")
    if match:
        year = int(match.group(0))
        if 2000 <= year <= 2100:
            return year
    if fallback:
        return int(fallback)
    return datetime.datetime.now().year


# Comillas (rectas y tipográficas) y sus versiones corruptas por mojibake (¿ ¡). La
# descripción OCDS suele venir como: EJECUCION DE OBRA "NOMBRE DEL PROYECTO ..." y a veces
# la comilla llega como ¿/¡, lo que rompe el match en SEACE.
_SEPARADORES_TERMINO = re.compile("[¿¡\"“”'‘’`]+")


def _termino_busqueda_obra(descripcion: str, nomenclatura: str) -> str:
    """Término distintivo para el campo 'Descripción del Objeto'.

    El buscador SEACE NO matchea la nomenclatura en ese campo (verificado en vivo: pegar
    la nomenclatura devuelve 0 resultados), pero sí matchea la descripción real. Usamos el
    tramo más distintivo: el NOMBRE DEL PROYECTO que va entre comillas (SEACE lo guarda tal
    cual). Partimos por las comillas —incluida la corrupta ``¿``— y tomamos el segmento más
    largo; así evitamos que un mojibake al inicio rompa la búsqueda. La fila exacta se
    confirma luego con el guard por nomenclatura. Si no hay descripción, cae a la nomenclatura.
    """
    desc = (descripcion or "").strip()
    if len(desc) >= 12:
        segmentos = [segmento.strip() for segmento in _SEPARADORES_TERMINO.split(desc) if segmento.strip()]
        mejor = max(segmentos, key=len) if segmentos else desc
        if len(mejor) < 12:  # ningún segmento distintivo → usa la descripción completa
            mejor = desc
        return mejor[:90]
    return (nomenclatura or "").strip()


def _base_nomenclatura(nomen: str) -> str:
    """Nomenclatura sin el número de convocatoria final (1-2 dígitos).

    SEACE a veces lista la obra con otra convocatoria (p. ej. la data trae ...-MPC-2 pero
    SEACE muestra ...-MPC-1). Se quita el sufijo solo si el año (20XX) sigue presente, para
    no comerse el año en nomenclaturas cortas. Si no aplica, devuelve la nomenclatura igual.
    """
    nomen = (nomen or "").strip()
    m = re.search(r"-\d{1,2}$", nomen)
    if m and re.search(r"20\d{2}", nomen[: m.start()]):
        return nomen[: m.start()]
    return nomen

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
        # Extraemos el contenedor principal de la celda contigua (following-sibling::td)
        panel_activo = page.locator('.ui-tabs-panel:visible').first
        dropdown_container = panel_activo.locator(
            f"xpath=descendant::td[contains(., '{label_text}')]/following-sibling::td[1]//div[contains(@class, 'ui-selectonemenu')]"
        ).first

        # TIP SENIOR: Evitar re-ejecutar AJAX si la opción ya está seleccionada visualmente
        current_label = await dropdown_container.locator('label').first.inner_text()
        if option_text.lower() in current_label.lower():
            logger.info(f"✅ '{label_text}' ya está en '{option_text}', no se requiere AJAX.")
            return

        trigger_locator = dropdown_container.locator(".ui-selectonemenu-trigger")
        await trigger_locator.scroll_into_view_if_needed()

        # Paso 3: Abrir el panel con force=True para ignorar overlays de PrimeFaces
        await trigger_locator.click(force=True, timeout=10000)
        await page.wait_for_timeout(1000) # Respirar antes de que cargue la lista flotante

        # Paso 4: Esperar el panel flotante y seleccionar la opción con coincidencia EXACTA
        panel_selector = "div.ui-selectonemenu-panel:visible"
        await page.wait_for_selector(panel_selector, state="visible", timeout=5000)
        # Usamos :text-is para asegurar coincidencia exacta ('Obra' vs 'Consultoría de Obra')
        await page.locator(f"{panel_selector} li.ui-selectonemenu-item:text-is('{option_text}')").first.click()

        await esperar_procesamiento(page)
        # ACUERDO DE RELAJACIÓN: Darle a PrimeFaces 4 segundos fijos para asentar la red y los callbacks
        # de Javascript internos tras haber tocado cualquier selector crítico.
        await page.wait_for_timeout(4000)
        
        logger.info(f"✅ Seleccionado '{option_text}' en '{label_text}'")
        return True

    except Exception as e:
        logger.warning(f"⚠️ Error al seleccionar '{label_text}': {e}. Activando visión IA...")
        # Delegar completamente a la IA para que encuentre y accione el dropdown
        return await clic_con_vision_ia(
            page,
            f"seleccionar la opción '{option_text}' en el menú desplegable cuyo label dice '{label_text}'"
        )

async def capturar_ficha_seace(page: Page, keyword: str, institucion: str, year: int, drive_handler: GDriveHandler | None, folder_id: str | None, output_dir: os.PathLike | str = "."):
    """Espera el renderizado completo de la ficha y toma la captura."""
    profundidad = 0
    try:
        # 1. Navegación Profunda: Entrar a la Ficha desde el Historial Intermedio
        # SEACE usa una estructura anidada: Buscador -> Historial -> Ficha
        # (Ocultando validación textual por recomendación heurística externa)
        await page.wait_for_timeout(8000)
        profundidad = 1
        
        # Buscar el enlace que contiene el icono CORRECTO de "Ver Ficha de Selección" (Checklist verde)
        btn_ver_ficha = page.locator('tbody.ui-datatable-data').first.locator('tr').first.locator('a:has(img[title="Ver Ficha de Selección"])').first
        
        # Si la tabla intermedia existe, taladramos a la capa final
        if await btn_ver_ficha.is_visible():
            await btn_ver_ficha.click(timeout=10000)
            
        # 2. Espera de Seguridad: Verificamos que el cronograma cargó finalmente (Ancla Estructural Nivel 1)
        await page.locator(':has-text("Cronograma")').first.wait_for(state="visible", timeout=30000)
        profundidad = 2 # Declaramos nivel 2 únicamente si el DOM del Cronograma existe
        
        # 3. Pausa grande requerida para que PrimeFaces termine de dibujar el Cronograma
        await page.wait_for_timeout(5000)
        
        # 3. Generar nombre de archivo con orden exacto: PALABRA_CLAVE + FECHA + ENTIDAD
        fecha_captura = datetime.datetime.now().strftime("%Y%m%d")
        safe_keyword = keyword.replace(" ", "_").upper()
        safe_institucion = "".join([c if c.isalnum() else "_" for c in institucion.strip()[:60]])
        # Estructura final: PUENTE_20260404_MUNICIPALIDAD.png
        filename = f"{safe_keyword}_{fecha_captura}_{safe_institucion}.png"
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, filename)
        
        # 4. CAPTURA RECORTADA: solo la parte superior de la ficha (Convocatoria +
        # Cronograma + Entidad Contratante + Información general del procedimiento),
        # sin la "Lista de Documentos" ni la "Vista de Items" de abajo. Se agranda el
        # viewport para que toda la zona superior entre y se corta a la altura del
        # primer bloque de documentos/items; si no se ubica, se cae a full_page.
        await page.set_viewport_size({"width": 1920, "height": 2600})
        await page.wait_for_timeout(800)
        cut_y = await page.evaluate(
            """() => {
                const labels = ['Lista de Documentos', 'Vista de Items', 'Vista de Ítems'];
                let best = null;
                for (const el of document.querySelectorAll('td, th, span, div, legend, label, h1, h2, h3')) {
                    const txt = (el.textContent || '').trim();
                    if (!txt) continue;
                    if (labels.some(l => txt === l || txt.startsWith(l + ' '))) {
                        const top = el.getBoundingClientRect().top + window.scrollY;
                        if (top > 200 && (best === null || top < best)) best = top;
                    }
                }
                return best;
            }"""
        )
        full_width = await page.evaluate(
            "() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)"
        )
        if cut_y and cut_y > 200:
            await page.screenshot(path=filepath, clip={"x": 0, "y": 0, "width": full_width, "height": cut_y})
            logger.info(f"📸 Captura recortada (alto={int(cut_y)}px) realizada localmente: {filename}")
        else:
            await page.screenshot(path=filepath, full_page=True)
            logger.info(f"📸 Captura full-page (no se ubicó corte) realizada localmente: {filename}")

        # 5. Subida inmediata a Google Drive
        if drive_handler and folder_id:
            file_id = drive_handler.upload_file(filepath, folder_id)
            if file_id:
                logger.info(f"🚀 Respaldado en Drive con ID: {file_id}")
                os.remove(filepath)  # Limpieza local automática
                return file_id  # truthy; el archivo local ya no existe

        # Devolvemos la RUTA (truthy) para que el flujo de alerta pueda adjuntarla a Telegram.
        return filepath
    except Exception as e:
        logger.error(f"❌ Error al capturar la ficha: {e}")
        return None
    finally:
        try:
            if profundidad >= 2:
                # 6. Primer Regreso (Ficha -> Historial)
                btn_regresar = page.locator('button:has-text("Regresar"), a:has-text("Regresar"), span:has-text("Regresar")').first
                if await btn_regresar.is_visible():
                    await btn_regresar.click(force=True)
                    await page.wait_for_timeout(3000)
            
            if profundidad >= 1:
                # 7. Segundo Regreso (Historial -> Buscador Principal)
                btn_regresar_dos = page.locator('button:has-text("Regresar"), a:has-text("Regresar"), span:has-text("Regresar")').first
                if await btn_regresar_dos.is_visible():
                    await btn_regresar_dos.click(force=True)
                    await esperar_procesamiento(page)
                
                # Esperar a que la tabla principal (resultados) vuelva a ser visible
                await page.wait_for_selector('tbody[id$="dtProcesos_data"]', state="visible", timeout=30000)
                await page.wait_for_timeout(4000)
        except Exception as pop_err:
            logger.error(f"⚠️ Fallo crítico al intentar retroceder capas: {pop_err}")

async def buscar_y_capturar_obra(
    page: Page,
    nomenclatura: str,
    descripcion: str,
    entity_name: str = "",
    year: int | None = None,
    drive_handler: GDriveHandler | None = None,
    folder_id: str | None = None,
    output_dir: os.PathLike | str = ".",
    seace_url: str = DEFAULT_SEACE_URL,
    max_pages: int = 3,
) -> bool:
    """Captura la ficha de UNA obra específica, identificada por su nomenclatura.

    A diferencia del barrido por keywords (que toma 'la primera que matchee'), esta función
    apunta a la obra exacta: busca por su descripción en el campo 'Descripción del Objeto'
    (el buscador SEACE no tiene campo de nomenclatura) y luego selecciona la fila cuya
    nomenclatura coincide EXACTAMENTE con `nomenclatura`. Pensada para la alerta de buena pro.

    Devuelve True si capturó la ficha de la obra correcta.
    """
    nomen = (nomenclatura or "").strip()
    if not nomen:
        logger.error("buscar_y_capturar_obra: nomenclatura vacía; no se puede apuntar a la obra.")
        return False

    anio = _derive_year_from_nomenclatura(nomen, fallback=year)
    termino = _termino_busqueda_obra(descripcion, nomen)
    # Base sin el número de convocatoria final (ver _base_nomenclatura).
    nomen_base = _base_nomenclatura(nomen)
    logger.info("🎯 Captura dirigida: nomenclatura=%s (base=%s) año=%s término=%r", nomen, nomen_base, anio, termino[:40])

    # 1. Navegar al buscador y abrir su pestaña
    await page.goto(seace_url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)
    tab_activo = False
    for _ in range(5):
        try:
            btn_tab = page.locator("li[role='tab']:has-text('Buscador de Procedimientos de Selección')").first
            await btn_tab.scroll_into_view_if_needed()
            await btn_tab.click(force=True)
            await page.locator("li[role='tab'].ui-state-active:has-text('Buscador de Procedimientos de Selección')").wait_for(state="visible", timeout=4000)
            tab_activo = True
            break
        except Exception:
            await page.wait_for_timeout(1000)
    if not tab_activo:
        logger.error("❌ No se pudo abrir el buscador SEACE para la captura dirigida.")
        return False
    await page.wait_for_timeout(4000)

    # 2. Filtros fijos (Obra + año + Seace 3)
    await seleccionar_opcion_primefaces(page, "Objeto de Contratación", "Obra")
    await seleccionar_opcion_primefaces(page, "Año de la Convocatoria", str(anio))
    await seleccionar_opcion_primefaces(page, "Version SEACE", "Seace 3")

    # 3. Buscar por la descripción de la obra
    panel = page.locator('.ui-tabs-panel:visible').first
    input_desc = panel.locator('input[id$=":descripcionObjeto"]').first
    await input_desc.click()
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Backspace")
    await page.wait_for_timeout(400)
    await input_desc.fill(termino, timeout=15000)
    await page.wait_for_timeout(1500)

    btn_buscar = panel.locator('button:has-text("Buscar"), button[id$="btnBuscarSelToken"]').first
    try:
        await btn_buscar.click(force=True)
    except Exception:
        await btn_buscar.evaluate('node => node.click()')
    await esperar_procesamiento(page)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await page.wait_for_timeout(3000)

    # 4. Guard: localizar la fila con la nomenclatura EXACTA (recorre páginas si hace falta)
    row_selector = 'tbody[id$="dtProcesos_data"] tr.ui-widget-content'
    pagina = 1
    while pagina <= max_pages:
        empty_msg = page.locator('td.ui-datatable-empty-message')
        try:
            if await empty_msg.is_visible():
                logger.info("ℹ️ Sin resultados para la obra %s (página %s).", nomen, pagina)
                break
        except Exception:
            pass
        try:
            await page.wait_for_selector(row_selector, state="visible", timeout=20000)
        except Exception:
            break

        count = await page.locator(row_selector).count()
        # Primero la nomenclatura EXACTA; si no está, la base (misma obra, otra convocatoria).
        objetivos = [nomen] if nomen_base == nomen else [nomen, nomen_base]
        fila_idx = None
        for objetivo in objetivos:
            for i in range(count):
                try:
                    texto_fila = await page.locator(row_selector).nth(i).inner_text()
                except Exception:
                    continue
                if objetivo in texto_fila:
                    fila_idx = i
                    logger.info("✅ Fila encontrada (pág %s, fila %s) por '%s' para %s", pagina, i, objetivo, nomen)
                    break
            if fila_idx is not None:
                break

        if fila_idx is not None:
            fila = page.locator(row_selector).nth(fila_idx)
            btn_ficha = fila.locator('td').last.locator('a, button').filter(
                has=page.locator('img[src*="ficha"], img[src*="cronograma"], .ui-icon-calendar, [title*="Ficha"], [title*="Cronograma"]')
            ).first
            if not await btn_ficha.is_visible():
                logger.warning("⚠️ Fila de %s encontrada pero sin icono de ficha visible.", nomen)
                return False

            institucion = (entity_name or "").strip() or await fila.locator('td').nth(1).inner_text()
            await page.wait_for_timeout(3000)  # PrimeFaces event hydration
            await btn_ficha.scroll_into_view_if_needed()
            await btn_ficha.click(timeout=10000)
            await page.wait_for_selector('text="Regresar"', state="visible", timeout=30000)
            # Reutiliza el core probado (espera cronograma, screenshot recortado, doble-regreso).
            # Sanea '/' de la nomenclatura para el nombre de archivo.
            return await capturar_ficha_seace(
                page, nomen.replace("/", "-"), institucion, anio, drive_handler, folder_id, output_dir
            )

        # Siguiente página
        next_btn = page.locator('.ui-paginator-next').first
        try:
            is_disabled = "ui-state-disabled" in (await next_btn.get_attribute("class") or "")
        except Exception:
            is_disabled = True
        if is_disabled:
            break
        await next_btn.click()
        await esperar_procesamiento(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        pagina += 1

    logger.warning("❌ No se encontró la fila con nomenclatura %s tras %s página(s).", nomen, pagina)
    return False


async def capturar_obra_standalone(
    nomenclatura: str,
    descripcion: str,
    entity_name: str = "",
    year: int | None = None,
    output_dir: os.PathLike | str = ".",
    seace_url: str = DEFAULT_SEACE_URL,
    headless: bool = True,
) -> str | None:
    """Lanza un navegador propio, captura la ficha de la obra exacta y devuelve la ruta del PNG.

    Pensada para el flujo de alerta (worker): gestiona el ciclo de vida del browser y NO usa
    Drive, para que el PNG persista en disco y se pueda adjuntar a Telegram. Devuelve la ruta
    del archivo o None si no se pudo capturar.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--ssl-version-min=tls1', '--ignore-certificate-errors', '--window-size=1280,720', '--no-sandbox'],
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        try:
            result = await buscar_y_capturar_obra(
                page,
                nomenclatura=nomenclatura,
                descripcion=descripcion,
                entity_name=entity_name,
                year=year,
                drive_handler=None,
                folder_id=None,
                output_dir=output_dir,
                seace_url=seace_url,
            )
            return result if isinstance(result, str) and os.path.exists(result) else None
        finally:
            await browser.close()


async def scanear_resultados(page: Page, keyword: str, year: int, drive_handler: GDriveHandler | None, folder_id: str | None, config: RuntimeConfig, captures_taken: int = 0):
    """Escanea la tabla y gestiona hallazgos. Retorna cantidad de capturas nuevas."""
    captured_count = 0
    try:
        table_selector = 'tbody[id$="dtProcesos_data"]'
        row_selector = f'{table_selector} tr.ui-widget-content'

        # TIP SENIOR: Esperar pacientemente (4 segundos) a que el AJAX dibuje los resultados o el mensaje de vacío
        await page.wait_for_timeout(4000)
        empty_msg = page.locator('td.ui-datatable-empty-message')
        if await empty_msg.is_visible():
            logger.info("ℹ️ No se encontraron resultados en esta página.")
            return 0

        await page.wait_for_selector(row_selector, state="visible", timeout=30000)
        count = await page.locator(row_selector).count()

        for i in range(count):
            if config.max_captures and captures_taken + captured_count >= config.max_captures:
                logger.info("Límite SEACE_MAX_CAPTURES=%s alcanzado.", config.max_captures)
                return captured_count

            # Recargar el locator base de la fila CADA iteración
            await page.wait_for_selector(row_selector, state="visible", timeout=30000)
            fila = page.locator(row_selector).nth(i)

            texto_fila = await fila.inner_text()
            texto_proyecto = texto_fila.upper()
            
            if any(key in texto_proyecto for key in config.keywords) and len(texto_fila.strip()) > 10:
                logger.info(f"🎯 Hallazgo relevante: {texto_proyecto[:50]}...")

                # 🎯 LOCALIZADOR DE PRECISIÓN para el icono de la Ficha (evita Lupas o Historial)
                btn_ficha = fila.locator('td').last.locator('a, button').filter(
                    has=page.locator('img[src*="ficha"], img[src*="cronograma"], .ui-icon-calendar, [title*="Ficha"], [title*="Cronograma"]')
                ).first

                if await btn_ficha.is_visible():
                    logger.info(f"📅 Extrayendo entidad y abriendo Historial Interno para: {texto_proyecto[:40]}...")
                    
                    # OBLIGATORIO: Obtener el texto ANTES de hacer clic, para no enfrentarse a un DOM muerto
                    institucion_texto = await fila.locator('td').nth(1).inner_text()
                    
                    # PrimeFaces Event Hydration
                    await page.wait_for_timeout(4000)
                    
                    # Playwright nativo es preferido sobre JS para emular el rastro humano si el nodo es visible
                    await btn_ficha.scroll_into_view_if_needed()
                    await btn_ficha.click(timeout=10000)

                    # La validación 'Regresar' se mantiene como señal de que llegamos a la siguiente capa
                    await page.wait_for_selector('text="Regresar"', state="visible", timeout=30000)

                    # La función capturar_ficha_seace se encarga de esperar el cronograma, capturar y doble-regresar

                    if await capturar_ficha_seace(page, keyword, institucion_texto, year, drive_handler, folder_id, config.output_dir):
                        captured_count += 1
                else:
                    logger.warning(f"⚠️ No se encontró el icono de Ficha en la fila: {texto_fila[:40]}...")
                    continue

        return captured_count
    except Exception as e:
        logger.error(f"Error en escaneo: {e}")
        return captured_count

async def ejecutar_agente():
    config = get_runtime_config()
    logger.info(
        "Configuración: headless=%s, años=%s-%s, keywords=%s, max_pages=%s, output_dir=%s",
        config.headless,
        config.year_start,
        config.year_end,
        ", ".join(config.keywords),
        config.max_pages or "sin límite",
        config.output_dir,
    )

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
            headless=config.headless,
            args=['--ssl-version-min=tls1', '--ignore-certificate-errors', '--window-size=1280,720', '--no-sandbox']
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            TIMEOUT_PORTAL = 45000 
            logger.info("🤖 Iniciando navegación al SEACE...")
            # Cambiado a domcontentloaded y pausa manual para PrimeFaces
            await page.goto(config.seace_url, 
                          wait_until="domcontentloaded", timeout=TIMEOUT_PORTAL)
            await page.wait_for_timeout(3000)
            
            try:
                # Filtrar el clic para tomar el tab explícito usando el rol seguro de PrimeFaces
                btn_tab = page.locator("li[role='tab']:has-text('Buscador de Procedimientos de Selección')").first
                await btn_tab.scroll_into_view_if_needed()
                
                # Bucle de validación estricta para garantizar que cambiamos de pestaña
                tab_activo = False
                for _ in range(5):
                    await btn_tab.click(force=True)
                    try:
                        # PrimeFaces añade la clase 'ui-state-active' al li cuando está seleccionado
                        await page.locator("li[role='tab'].ui-state-active:has-text('Buscador de Procedimientos de Selección')").wait_for(state="visible", timeout=3000)
                        tab_activo = True
                        break
                    except Exception:
                        await page.wait_for_timeout(1000)
                        
                if not tab_activo:
                    raise Exception("El portal no respondió al clic de la pestaña; falló la validación 'ui-state-active'")
                
                # Esperar generosamente la estabilización tras la animación de PrimeFaces para el cambio de tab
                await page.wait_for_timeout(5000)
                logger.info("✅ Panel de búsqueda detectado genuinamente.")
            except Exception as nav_e:
                logger.error(f"❌ No se pudo cargar el buscador por vía normal: {nav_e}")
                # Entramos a la capa de visión IA de ser necesario
                await clic_con_vision_ia(page, "el botón o pestaña para abrir el buscador de procedimientos de selección")
                panel_activo = page.locator('.ui-tabs-panel:visible').first
                await panel_activo.locator('xpath=descendant::*[contains(text(), "Objeto de Contratación")]').first.wait_for(state="visible", timeout=TIMEOUT_PORTAL)
                await page.wait_for_timeout(1500)
                logger.info("✅ Panel de búsqueda detectado vía IA.")

            anyo_inicial = config.year_start
            anyo_actual = config.year_end

            capturas_totales = 0
            for anyo in range(anyo_inicial, anyo_actual + 1):
                logger.info(f"📅 Configurando parámetros fijos para el año {anyo}...")
                # Seleccionar parámetros fijos por año
                await seleccionar_opcion_primefaces(page, "Objeto de Contratación", "Obra")
                await seleccionar_opcion_primefaces(page, "Año de la Convocatoria", str(anyo))
                await seleccionar_opcion_primefaces(page, "Version SEACE", "Seace 3")
                
                for keyword in config.keywords:
                    try:
                        logger.info(f"🚀 Iniciando búsqueda: año={anyo}, keyword='{keyword}'...")

                        # Idempotencia: Asegurarse de que el bot esté en el buscador nativo antes de iniciar
                        if "buscadorPublico.xhtml" not in page.url:
                            logger.warning(f"🔄 URL corrupta detectada para {keyword}. Forzando restablecimiento de la Pila de Navegación...")
                            await page.goto(config.seace_url, wait_until="domcontentloaded")
                            await page.wait_for_timeout(3000)
                            
                            # 1. Recuperar el Tab
                            btn_tab = page.locator("li[role='tab']:has-text('Buscador de Procedimientos de Selección')").first
                            await btn_tab.click()
                            await page.locator("li[role='tab'].ui-state-active:has-text('Buscador de Procedimientos de Selección')").wait_for(state="visible", timeout=5000)
                            await page.wait_for_timeout(3000)
                            
                            # 2. Restaurar los filtros perdidos del año actual
                            await seleccionar_opcion_primefaces(page, "Objeto de Contratación", "Obra")
                            await seleccionar_opcion_primefaces(page, "Año de la Convocatoria", str(anyo))
                            await seleccionar_opcion_primefaces(page, "Version SEACE", "Seace 3")

                        # Rellenar el filtro de descripción — Búsqueda dentro del panel usando su sufijo estático (inmune a j_idt)
                        panel_activo = page.locator('.ui-tabs-panel:visible').first
                        input_desc = panel_activo.locator('input[id$=":descripcionObjeto"]').first
                        
                        # Defensivo extremo: Forzar limpieza nativa para despejar la memoria RAM de PrimeFaces
                        await input_desc.click()
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        await page.wait_for_timeout(500)
                        # Playwright maneja internamente la espera con fill
                        await input_desc.fill(keyword, timeout=15000)
                        await page.wait_for_timeout(2000) # Dejar que el cajón registre el texto visualmente

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
                            nuevas_capturas = await scanear_resultados(page, keyword, anyo, drive_handler, folder_id, config, capturas_totales)
                            capturas_totales += nuevas_capturas

                            if config.max_captures and capturas_totales >= config.max_captures:
                                logger.info("Límite total SEACE_MAX_CAPTURES=%s alcanzado; finalizando demo.", config.max_captures)
                                return

                            if config.max_pages and pagina >= config.max_pages:
                                logger.info("Límite SEACE_MAX_PAGES=%s alcanzado para demo/control de ejecución.", config.max_pages)
                                break

                            next_btn = page.locator('.ui-paginator-next').first
                            is_disabled = "ui-state-disabled" in (await next_btn.get_attribute("class") or "")

                            if is_disabled:
                                break

                            await next_btn.click()
                            await esperar_procesamiento(page)
                            await page.wait_for_load_state("networkidle")
                            pagina += 1

                    except Exception as loop_e:
                        logger.error(f"⚠️ Fallo general procesando la keyword '{keyword}': {loop_e}")
                        # El script simplemente continuará con la próxima keyword, y el chequeo
                        # de "buscadorPublico" forzará a SEACE a reconstruirse de ser necesario.
                        continue

        except Exception as global_e:
            logger.error(f"Error crítico en el esqueleto principal: {global_e}")
        finally:
            await browser.close()
            logger.info("🔒 Auditoría completada.")

if __name__ == "__main__":
    asyncio.run(ejecutar_agente())
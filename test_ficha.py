import asyncio
from playwright.async_api import async_playwright
import sys

async def run():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--ssl-version-min=tls1', '--ignore-certificate-errors'])
            page = await browser.new_page(ignore_https_errors=True)
            await page.goto('https://prod2.seace.gob.pe/seacebus-uiwd-pub/publico/buscadorPublico.xhtml', wait_until='networkidle')
            await page.click('a:has-text("Buscador de Procedimientos de Selección")')
            await page.wait_for_selector('div[id$="tab1"][aria-hidden="false"]')
            
            await page.click('div[id$="j_idt188"] .ui-selectonemenu-trigger')
            await page.click('div.ui-selectonemenu-panel:visible li.ui-selectonemenu-item:has-text("Obra")')
            
            await page.click('div[id$="anioConvocatoria"] .ui-selectonemenu-trigger')
            await page.click('div.ui-selectonemenu-panel:visible li.ui-selectonemenu-item:has-text("2025")')
            
            await page.fill('input[id$="descripcionObjeto"]', 'puente')
            await page.click('button[id$="btnBuscarSelToken"]')
            
            row_selector = 'tbody[id$="dtProcesos_data"] tr.ui-widget-content'
            await page.wait_for_selector(row_selector, state='visible', timeout=15000)
            
            count = await page.locator(row_selector).count()
            print(f'Rows found: {count}')
            
            for i in range(count):
                await page.wait_for_selector(row_selector, state='visible', timeout=15000)
                fila = page.locator(row_selector).nth(i)
                text = await fila.inner_text()
                print(f'Row {i} length: {len(text)}')
                if len(text.strip()) > 10:
                    btn_ficha = fila.locator('td').last.locator('a, button').nth(1)
                    await btn_ficha.click(force=True)
                    print('Clicked ficha')
                    await page.wait_for_selector('text="Regresar"', state='visible', timeout=15000)
                    print('Loaded ficha')
                    await page.wait_for_timeout(1000)
                    await page.locator('text="Regresar"').first.click(force=True)
                    print('Clicked Regresar')
                    await page.wait_for_selector(row_selector, state='visible', timeout=15000)
                    print('Back to table')
    except Exception as e:
        print(f'ERROR CRITICO: {e}')

asyncio.run(run())

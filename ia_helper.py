import os
import logging
import google.generativeai as genai
from dotenv import load_dotenv

# Carga la llave desde el .env que ya tienes listo
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

logger = logging.getLogger(__name__)


class IA_Helper:
    def __init__(self):
        if not api_key:
            raise ValueError("❌ No se encontró GEMINI_API_KEY en el archivo .env")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        logger.info("🤖 IA_Helper (Gemini) inicializado correctamente.")

    async def razonar_selector(self, html_snippet: str, objetivo: str) -> str | None:
        """
        Analiza el HTML y decide qué selector CSS usar basado en el objetivo.
        Retorna el selector como string, o None si no puede determinarlo.
        Ejemplo: objetivo='botón para buscar licitaciones de puentes'
        """
        prompt = f"""
Eres un experto en automatización de portales gubernamentales PrimeFaces.
Analiza este fragmento HTML del SEACE:
{html_snippet}

Necesito el selector CSS exacto para: {objetivo}.
Responde exclusivamente con el selector CSS (ej. button[id$='btnBuscar']), sin texto adicional.
Si no es claro, responde 'NOT_FOUND'.
"""
        try:
            response = await self.model.generate_content_async(prompt)
            result = response.text.strip()
            if result == "NOT_FOUND":
                logger.warning(f"🤖 IA: No encontró selector para '{objetivo}'")
                return None
            logger.info(f"🤖 IA sugiere selector: '{result}' para '{objetivo}'")
            return result
        except Exception as e:
            logger.error(f"❌ Error consultando Gemini: {e}")
            return None


# Instancia global — se pone en None si no hay API Key configurada
# para que el agente pueda importar este módulo sin crashear
try:
    cerebro_ia = IA_Helper()
except ValueError as e:
    logger.warning(f"⚠️ {e}. El fallback de IA estará deshabilitado.")
    cerebro_ia = None

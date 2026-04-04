import os
import logging
from google import genai
from dotenv import load_dotenv

# Carga la llave desde el .env
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

logger = logging.getLogger(__name__)


class IA_Helper:
    def __init__(self):
        if not api_key:
            raise ValueError("No se encontró GEMINI_API_KEY en el archivo .env")
        self.client = genai.Client(api_key=api_key)
        logger.info("🤖 IA_Helper (Gemini) inicializado correctamente.")

    async def razonar_selector(self, html_snippet: str, objetivo: str) -> str | None:
        """
        Analiza el HTML y decide qué selector CSS usar basado en el objetivo.
        Retorna el selector como string, o None si no puede determinarlo.
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
            response = await self.client.aio.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            result = response.text.strip()
            if result == "NOT_FOUND":
                logger.warning(f"🤖 IA: No encontró selector para '{objetivo}'")
                return None
            logger.info(f"🤖 IA sugiere selector: '{result}' para '{objetivo}'")
            return result
        except Exception as e:
            logger.error(f"❌ Error consultando Gemini: {e}")
            return None


# Instancia global segura — None si no hay API Key
try:
    cerebro_ia = IA_Helper()
except ValueError as e:
    logger.warning(f"⚠️ {e}. El fallback de IA estará deshabilitado.")
    cerebro_ia = None

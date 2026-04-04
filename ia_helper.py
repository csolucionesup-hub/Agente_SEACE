import os
import logging
import google.generativeai as genai
from dotenv import load_dotenv

# Carga automática del archivo .env local
load_dotenv()

logger = logging.getLogger(__name__)

# Inicializar con la API Key desde variable de entorno
_API_KEY = os.environ.get("GEMINI_API_KEY")
if _API_KEY:
    genai.configure(api_key=_API_KEY)
else:
    logger.warning("⚠️ GEMINI_API_KEY no configurada. El fallback de IA estará deshabilitado.")


async def consultar_ia_sobre_dom(html_snippet: str, tarea: str) -> str | None:
    """
    Usa Gemini para analizar un fragmento de HTML y devolver un selector CSS.
    Retorna el selector como string, o None si la IA no puede ayudar o no está disponible.
    """
    if not _API_KEY:
        return None

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
Eres un experto en el portal SEACE, que usa componentes PrimeFaces (JSF).
Analiza este fragmento de HTML y dime el selector CSS exacto para realizar la siguiente tarea: {tarea}.

HTML:
{html_snippet}

Reglas:
- Responde SOLO con el selector CSS. Sin explicaciones, sin markdown.
- Si no puedes determinarlo con certeza, responde exactamente: NOT_FOUND
"""
        response = await model.generate_content_async(prompt)
        result = response.text.strip()

        if result == "NOT_FOUND":
            logger.warning(f"🤖 IA: No encontró selector para '{tarea}'")
            return None

        logger.info(f"🤖 IA sugiere selector: '{result}' para '{tarea}'")
        return result

    except Exception as e:
        logger.error(f"❌ Error consultando Gemini: {e}")
        return None

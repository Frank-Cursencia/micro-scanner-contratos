import asyncio
import logging
from functools import lru_cache

from google import genai
from google.genai import types
from google.genai.errors import ServerError
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

# Gemini devuelve 503 "high demand" de forma transitoria — confirmado en
# staging incluso después de los reintentos internos del SDK (visible en el
# stack trace: tenacity ya reintentó y aun así llegó ServerError). Un
# reintento propio, espaciado, evita que el usuario tenga que volver a subir
# el PDF a mano cada vez que el modelo está saturado.
MAX_INTENTOS_503 = 3
ESPERA_ENTRE_INTENTOS_S = 5

PROMPT_BASE = """Sos un extractor de datos de contratos peruanos. Se te adjunta un PDF.

Reglas estrictas:
- Si un dato no aparece en el documento, devolvé null. Nunca inventes valores.
- RUC: exactamente 11 dígitos. Si no cumple, null.
- DNI: exactamente 8 dígitos. Si no cumple, null.
- Montos en soles: la coma en el documento es separador de miles, no decimal (ej. "1,500.00" es mil quinientos). Al devolver el valor, usá SIEMPRE notación decimal simple sin separador de miles (ej. devolvé "4500.00", nunca "4,500.00").
- Fechas: devolvé en formato dd/mm/yyyy, incluso si en el documento están escritas en letras.

Campos a buscar (clave -> qué significa):
{campos}
"""


def _client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


@lru_cache
def _semaphore() -> asyncio.Semaphore:
    # Tope de llamadas simultáneas a Gemini File API — evitar 429/503 propios
    # al paralelizar extracciones (contrato + carta fianza + SCTR + EPP).
    return asyncio.Semaphore(get_settings().gemini_max_concurrency)


async def extract_fields(pdf_bytes: bytes, response_model: type[BaseModel], field_descriptions: dict[str, str]) -> BaseModel:
    settings = get_settings()
    campos_txt = "\n".join(f"- {key}: {label}" for key, label in field_descriptions.items())
    prompt = PROMPT_BASE.format(campos=campos_txt)

    client = _client()
    # PDF va inline (bytes) en vez de por Files API — nos ahorramos el
    # round-trip de upload + espera a que el archivo quede ACTIVE. Files API
    # se justifica para reusar el mismo archivo en llamadas repetidas; acá
    # cada PDF se usa una sola vez, así que inline es directamente más rápido.
    # Límite de Gemini para contenido inline es ~20MB de request (el PDF en
    # base64 pesa ~4/3 su tamaño real) — MAX_FILE_SIZE_MB ya deja margen.
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    async with _semaphore():
        for intento in range(1, MAX_INTENTOS_503 + 1):
            try:
                response = await client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=[pdf_part, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_model,
                        temperature=0.1,
                    ),
                )
                break
            except ServerError as exc:
                if exc.code != 503 or intento == MAX_INTENTOS_503:
                    raise
                logger.warning(
                    "Gemini 503 (alta demanda), reintento %d/%d en %ds",
                    intento, MAX_INTENTOS_503 - 1, ESPERA_ENTRE_INTENTOS_S,
                )
                await asyncio.sleep(ESPERA_ENTRE_INTENTOS_S)
    return response.parsed

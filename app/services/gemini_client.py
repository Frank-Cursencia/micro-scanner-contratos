import asyncio
import logging
from functools import lru_cache

from google import genai
from google.genai import types
from google.genai.errors import ServerError
from pydantic import BaseModel

from app.config import get_settings
from app.models.gastos_tupa import PROMPT_TUPA

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
- Revisá el documento completo, incluidas todas sus páginas, anexos, cuadros,
  encabezados y cláusulas. No te detengas en la primera página.
- Si un dato no aparece en el documento, devolvé null. Nunca inventes valores.
- Para ubicación del proyecto, distinguí cuidadosamente entre: (1) lugar donde
  se ejecuta el servicio o está el predio/proyecto, (2) domicilio legal del
  cliente, (3) domicilio del proveedor, (4) ciudad de firma y (5) lugares de
  notificación. Solo (1) sirve como ubicación/ciudad del proyecto.
- Buscá el lugar de ejecución también en antecedentes, objeto, alcance,
  descripción del predio, coordenadas, tablas y anexos. Si aparece distrito,
  provincia o departamento explícitamente vinculado al proyecto, podés usar
  esa jerarquía para completar el campo ciudad. No deduzcas una ciudad desde
  el nombre de una empresa ni desde su domicilio fiscal.
- RUC: exactamente 11 dígitos. Si no cumple, null.
- DNI: exactamente 8 dígitos. Si no cumple, null.
- Si se solicita numeroDocumentoOriginal, leé el encabezado completo del
  contrato: no omitas CONTRATO ni el servicio que precede al correlativo.
  Conservá ceros iniciales y año. Si también se pide tipoServicio, obtenelo
  del objeto y alcance del mismo contrato, no de una cuota o anexo. Para
  varios servicios diferentes devolvé null, no elijas el primero. Nunca
  inventes correlativo, año ni servicio para completar el identificador.
- Montos: conservá la moneda original del documento; no asumas soles ni
  conviertas dólares a soles. La coma de miles (ej. "1,500.00") no es decimal.
  Devolvé SIEMPRE notación decimal simple sin separador de miles (ej. "4500.00",
  nunca "4,500.00"). Si se pide moneda y no está expresada, devolvé null.
- Si se solicita precio/monto total, tomá únicamente el TOTAL FINAL del
  contrato. Nunca uses como precio un RUC, año, subtotal, IGV, porcentaje,
  carta fianza o penalidad. Verificá que sea coherente con la suma del
  cronograma de pagos cuando el documento contiene ambos datos.
- En cronograma_pagos.monto devolvé el IMPORTE MONETARIO de cada cuota, no el
  porcentaje. Si el documento solo da porcentajes, calculá cada importe usando
  el total final del contrato.
- Fechas: devolvé en formato dd/mm/yyyy, incluso si en el documento están escritas en letras.

Campos a buscar (clave -> qué significa):
{campos}
"""


def _client(*, single_attempt: bool = False) -> genai.Client:
    settings = get_settings()
    if single_attempt:
        return genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(
            timeout=35000, retry_options=types.HttpRetryOptions(attempts=1),
        ))
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
    tupa = "gastos_tupa" in response_model.model_fields
    if tupa:
        prompt += PROMPT_TUPA
    client = _client(single_attempt=True) if tupa else _client()
    # PDF va inline (bytes) en vez de por Files API — nos ahorramos el
    # round-trip de upload + espera a que el archivo quede ACTIVE. Files API
    # se justifica para reusar el mismo archivo en llamadas repetidas; acá
    # cada PDF se usa una sola vez, así que inline es directamente más rápido.
    # Límite de Gemini para contenido inline es ~20MB de request (el PDF en
    # base64 pesa ~4/3 su tamaño real) — MAX_FILE_SIZE_MB ya deja margen.
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    async with _semaphore():
        max_intentos = 1 if tupa else MAX_INTENTOS_503
        for intento in range(1, max_intentos + 1):
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
                if exc.code != 503 or intento == max_intentos:
                    raise
                logger.warning(
                    "Gemini 503 (alta demanda), reintento %d/%d en %ds",
                    intento, MAX_INTENTOS_503 - 1, ESPERA_ENTRE_INTENTOS_S,
                )
                await asyncio.sleep(ESPERA_ENTRE_INTENTOS_S)
    return response.parsed

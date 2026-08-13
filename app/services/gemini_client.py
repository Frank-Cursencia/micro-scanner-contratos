import io

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import get_settings

PROMPT_BASE = """Sos un extractor de datos de contratos peruanos. Se te adjunta un PDF.

Reglas estrictas:
- Si un dato no aparece en el documento, devolvé null. Nunca inventes valores.
- RUC: exactamente 11 dígitos. Si no cumple, null.
- DNI: exactamente 8 dígitos. Si no cumple, null.
- Montos en soles: la coma es separador de miles, no decimal (ej. "1,500.00" es mil quinientos).
- Fechas: devolvé en formato dd/mm/yyyy, incluso si en el documento están escritas en letras.

Campos a buscar (clave -> qué significa):
{campos}
"""


def _client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


def extract_fields(pdf_bytes: bytes, response_model: type[BaseModel], field_descriptions: dict[str, str]) -> BaseModel:
    settings = get_settings()
    campos_txt = "\n".join(f"- {key}: {label}" for key, label in field_descriptions.items())
    prompt = PROMPT_BASE.format(campos=campos_txt)

    client = _client()
    uploaded = client.files.upload(
        file=io.BytesIO(pdf_bytes),
        config=types.UploadFileConfig(mime_type="application/pdf"),
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[uploaded, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_model,
            temperature=0.1,
        ),
    )
    return response.parsed

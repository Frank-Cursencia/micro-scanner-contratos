import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from google.genai.errors import ClientError

from app.api.dependencies import require_service_token
from app.config import get_settings
from app.models.schemas import FieldSpec
from app.services.dynamic_schema import build_dynamic_model
from app.services.gemini_client import extract_fields
from app.services.pdf_text_values import extract_textual_total

router = APIRouter(tags=["extract"])
logger = logging.getLogger(__name__)

LOCATION_KEYS = frozenset({"locacionProyecto", "ciudad"})
LOCATION_RETRY_PREFIX = (
    "SEGUNDA REVISIÓN EXCLUSIVA DE UBICACIÓN. Revisá nuevamente todo el PDF, "
    "especialmente antecedentes, objeto, alcance, descripción del predio, "
    "coordenadas, tablas y anexos. "
)
TOTAL_KEYS = frozenset({"precioTotal"})
TOTAL_RETRY_PREFIX = (
    "SEGUNDA REVISIÓN EXCLUSIVA DEL PRECIO TOTAL. Leé el valor textual junto "
    "a la etiqueta TOTAL, PRECIO TOTAL, CONTRAPRESTACIÓN o VALOR DEL CONTRATO. "
    "No lo calcules desde las cuotas y no uses RUC, año, subtotal, IGV, "
    "porcentaje, garantía ni penalidad. Devolvé solo el número decimal. "
)


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower().replace("s/", "").replace("%", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _total_is_suspicious(data: dict, key: str) -> bool:
    cuotas = data.get("cronograma_pagos")
    if not isinstance(cuotas, list) or len(cuotas) < 2:
        return _is_blank(data.get(key))
    montos = [_number(cuota.get("monto")) for cuota in cuotas if isinstance(cuota, dict)]
    if len(montos) != len(cuotas) or any(monto is None or monto <= 0 for monto in montos):
        return _is_blank(data.get(key))
    suma = sum(montos)  # type: ignore[arg-type]
    # Una suma cercana a 100 probablemente todavía son porcentajes, no montos
    # monetarios; en ese caso no se usa para juzgar el total textual.
    if suma <= 100.1:
        return _is_blank(data.get(key))
    total = _number(data.get(key))
    return total is None or abs(total - suma) > max(0.01, suma * 0.01)


def _schedule_monetary_total(data: dict) -> float | None:
    cuotas = data.get("cronograma_pagos")
    if not isinstance(cuotas, list) or not cuotas:
        return None
    montos = [_number(cuota.get("monto")) for cuota in cuotas if isinstance(cuota, dict)]
    if len(montos) != len(cuotas) or any(monto is None or monto <= 0 for monto in montos):
        return None
    total = sum(montos)  # type: ignore[arg-type]
    return total if total > 100.1 else None


async def enrich_missing_location(
    pdf_bytes: bytes,
    parsed_fields: list[FieldSpec],
    result: object,
) -> dict:
    """Segundo pase focalizado cuando el modelo general omite ubicación.

    El primer pase resuelve muchos campos y cronograma a la vez; en contratos
    extensos Gemini puede priorizar los datos comerciales y devolver null para
    una ubicación débilmente expresada. El segundo pase solo contiene las
    claves faltantes, conserva intacto el resultado original y es best-effort.
    """
    data = result.model_dump()
    retry_fields = [
        field for field in parsed_fields
        if field.key in LOCATION_KEYS and _is_blank(data.get(field.key))
    ]
    retry_fields.extend(
        field for field in parsed_fields
        if field.key in TOTAL_KEYS and _total_is_suspicious(data, field.key)
    )
    if not retry_fields:
        return data

    focused_fields = [
        FieldSpec(
            key=field.key,
            label=f"{TOTAL_RETRY_PREFIX if field.key in TOTAL_KEYS else LOCATION_RETRY_PREFIX}{field.label}",
        )
        for field in retry_fields
    ]
    retry_model = build_dynamic_model(focused_fields, False, False)
    retry_descriptions = {field.key: field.label for field in focused_fields}
    try:
        retry_result = await extract_fields(pdf_bytes, retry_model, retry_descriptions)
    except Exception:
        logger.warning("Falló el segundo pase focalizado del contrato", exc_info=True)
        return data

    if retry_result is None:
        return data
    retry_data = retry_result.model_dump()
    for field in retry_fields:
        value = retry_data.get(field.key)
        if not _is_blank(value):
            data[field.key] = value
    return data


@router.post("/api/extract-contrato", dependencies=[Depends(require_service_token)])
async def extract_contrato(
    file: UploadFile = File(...),
    fields: str = Form(..., description='JSON: [{"key": "...", "label": "..."}]'),
    include_cronograma: bool = Form(False),
    include_items: bool = Form(False),
) -> dict:
    settings = get_settings()

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser un PDF.")

    pdf_bytes = await file.read()
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El PDF supera los {settings.max_file_size_mb}MB.",
        )

    try:
        raw_fields = json.loads(fields)
        parsed_fields = [FieldSpec(**f) for f in raw_fields]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='"fields" debe ser JSON: [{"key": "...", "label": "..."}]',
        ) from exc

    if not parsed_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='"fields" no puede estar vacío.')

    if settings.gemini_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GEMINI_API_KEY_NOT_CONFIGURED", "message": "GEMINI_API_KEY no está configurado."},
        )

    response_model = build_dynamic_model(parsed_fields, include_cronograma, include_items)
    field_descriptions = {f.key: f.label for f in parsed_fields}

    try:
        result = await extract_fields(pdf_bytes, response_model, field_descriptions)
    except ClientError as exc:
        logger.exception("Fallo llamando a Gemini en /api/extract-contrato")
        if exc.code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "GEMINI_QUOTA_EXCEEDED", "message": "Se agotó la cuota diaria de Gemini. Probá de nuevo más tarde."},
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GEMINI_EXTRACTION_FAILED", "message": "No se pudo analizar el PDF con IA. Intentá de nuevo."},
        )
    except Exception:
        logger.exception("Fallo llamando a Gemini en /api/extract-contrato")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GEMINI_EXTRACTION_FAILED", "message": "No se pudo analizar el PDF con IA. Intentá de nuevo."},
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GEMINI_EMPTY_RESPONSE", "message": "Gemini no devolvió datos para este PDF."},
        )

    data = await enrich_missing_location(pdf_bytes, parsed_fields, result)
    if any(field.key == "precioTotal" for field in parsed_fields):
        textual_total = extract_textual_total(pdf_bytes, _schedule_monetary_total(data))
        if textual_total is not None:
            data["precioTotal"] = textual_total
    return data

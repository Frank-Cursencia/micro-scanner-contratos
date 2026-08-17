import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from google.genai.errors import ClientError

from app.api.dependencies import require_service_token
from app.config import get_settings
from app.models.schemas import FieldSpec
from app.services.dynamic_schema import build_dynamic_model
from app.services.gemini_client import extract_fields

router = APIRouter(tags=["extract"])
logger = logging.getLogger(__name__)


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

    return result.model_dump()

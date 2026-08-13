import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import require_service_token
from app.config import get_settings
from app.models.schemas import FieldSpec
from app.services.dynamic_schema import build_dynamic_model
from app.services.gemini_client import extract_fields

router = APIRouter(tags=["extract"])


@router.post("/api/extract-contrato", dependencies=[Depends(require_service_token)])
async def extract_contrato(
    file: UploadFile = File(...),
    fields: str = Form(..., description='JSON: [{"key": "...", "label": "..."}]'),
    include_cronograma: bool = Form(False),
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

    response_model = build_dynamic_model(parsed_fields, include_cronograma)
    field_descriptions = {f.key: f.label for f in parsed_fields}

    result = extract_fields(pdf_bytes, response_model, field_descriptions)
    return result.model_dump()

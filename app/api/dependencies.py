import hmac

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
    """Protege /api/extract-contrato, que debe venir desde el Gateway."""
    settings = get_settings()
    expected = settings.microservice_token
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_TOKEN_NOT_CONFIGURED", "message": "MICROSERVICE_TOKEN no está configurado."},
        )
    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "INVALID_SERVICE_TOKEN", "message": "Token de servicio inválido."},
        )

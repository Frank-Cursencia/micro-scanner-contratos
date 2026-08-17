import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai.errors import ServerError
from pydantic import BaseModel

from app.config import get_settings
from app.services import gemini_client
from app.services.gemini_client import _semaphore, extract_fields


def test_semaphore_caps_concurrency_at_configured_limit():
    get_settings.cache_clear()
    _semaphore.cache_clear()
    limit = get_settings().gemini_max_concurrency

    async def scenario():
        sem = _semaphore()

        async def hold():
            async with sem:
                await asyncio.sleep(0.05)

        tasks = [asyncio.create_task(hold()) for _ in range(limit + 1)]
        await asyncio.sleep(0.01)
        assert sem._value == 0  # todos los slots ocupados, el (limit+1)-ésimo espera
        await asyncio.gather(*tasks)
        assert sem._value == limit  # se liberaron todos al terminar

    asyncio.run(scenario())


class _CamposDummy(BaseModel):
    nombre: str | None = None


def _server_error_503() -> ServerError:
    return ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})


def test_extract_fields_reintenta_en_503_y_termina_devolviendo_el_resultado(monkeypatch):
    _semaphore.cache_clear()
    monkeypatch.setattr(gemini_client.asyncio, "sleep", AsyncMock())  # no esperar los 5s reales en el test

    parsed = _CamposDummy(nombre="Juan")
    respuesta_ok = MagicMock(parsed=parsed)
    generate_content = AsyncMock(side_effect=[_server_error_503(), _server_error_503(), respuesta_ok])

    fake_client = MagicMock()
    fake_client.aio.models.generate_content = generate_content
    monkeypatch.setattr(gemini_client, "_client", lambda: fake_client)

    result = asyncio.run(extract_fields(b"%PDF-1.4", _CamposDummy, {"nombre": "Nombre"}))

    assert result is parsed
    assert generate_content.await_count == 3  # 2 fallos por 503 + 1 éxito
    assert gemini_client.asyncio.sleep.await_count == 2  # una espera entre cada reintento


def test_extract_fields_agota_reintentos_y_propaga_el_503(monkeypatch):
    _semaphore.cache_clear()
    monkeypatch.setattr(gemini_client.asyncio, "sleep", AsyncMock())

    generate_content = AsyncMock(side_effect=[_server_error_503() for _ in range(gemini_client.MAX_INTENTOS_503)])
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = generate_content
    monkeypatch.setattr(gemini_client, "_client", lambda: fake_client)

    with pytest.raises(ServerError):
        asyncio.run(extract_fields(b"%PDF-1.4", _CamposDummy, {"nombre": "Nombre"}))

    assert generate_content.await_count == gemini_client.MAX_INTENTOS_503


def test_extract_fields_no_reintenta_errores_distintos_de_503(monkeypatch):
    _semaphore.cache_clear()
    monkeypatch.setattr(gemini_client.asyncio, "sleep", AsyncMock())

    error_429 = ServerError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    generate_content = AsyncMock(side_effect=[error_429])
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = generate_content
    monkeypatch.setattr(gemini_client, "_client", lambda: fake_client)

    with pytest.raises(ServerError):
        asyncio.run(extract_fields(b"%PDF-1.4", _CamposDummy, {"nombre": "Nombre"}))

    assert generate_content.await_count == 1  # no reintenta un código que no sea 503
    gemini_client.asyncio.sleep.assert_not_awaited()

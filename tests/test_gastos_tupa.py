import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile
from google.genai.errors import ServerError
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.api import routes_extract
from app.models.schemas import FieldSpec
from app.services import gemini_client
from app.services.dynamic_schema import build_dynamic_model


def test_collection_is_opt_in_and_preserves_other_fields():
    fields = [FieldSpec(key="cliente", label="Cliente")]
    assert "gastos_tupa" not in build_dynamic_model(fields, True, True).model_fields
    model = build_dynamic_model(fields, True, True, True)
    r = model(cliente="Cliente", cronograma_pagos=[{"monto": "100"}], items=[{"descripcion": "Plano"}],
              gastos_tupa=[{"concepto": "Tasa CIRAS", "naturaleza": "presupuesto", "importe": "90.00"},
                           {"concepto": "PMAR", "pagina": 4, "pagador_literal": "Cliente"}])
    assert r.cliente == "Cliente"
    assert len(r.gastos_tupa) == 2
    assert r.gastos_tupa[1].moneda is None
    assert model().gastos_tupa == []


def test_collection_rejects_approval_ids_invalid_currency_and_overflow():
    model = build_dynamic_model([], False, False, True)
    for candidate in [{"gastoId": "inventado"}, {"pagador": "empresa"}, {"revisionHumana": True},
                      {"moneda": "EUR"}, {"pagina": 0}, {"naturaleza": "confirmado"}]:
        with pytest.raises(ValidationError):
            model(gastos_tupa=[candidate])
    with pytest.raises(ValidationError):
        model(gastos_tupa=[{}] * 51)


def test_tupa_does_not_retry_provider_and_sets_single_attempt(monkeypatch):
    gemini_client._semaphore.cache_clear()
    error = ServerError(503, {"error": {"code": 503, "message": "busy"}})
    generate = AsyncMock(side_effect=error)
    client = MagicMock()
    client.aio.models.generate_content = generate
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(gemini_client, "_client", factory)
    model = build_dynamic_model([], False, False, True)
    with pytest.raises(ServerError):
        asyncio.run(gemini_client.extract_fields(b"%PDF-1.4", model, {}))
    factory.assert_called_once_with(single_attempt=True)
    assert generate.await_count == 1
    prompt = generate.await_args.kwargs["contents"][1]
    assert "No calcular importes" in prompt and "yyyy-mm-dd" in prompt


def test_single_attempt_disables_sdk_retries(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(gemini_client.genai, "Client", factory)
    monkeypatch.setattr(gemini_client, "get_settings", lambda: SimpleNamespace(gemini_api_key="fake"))
    gemini_client._client(single_attempt=True)
    opts = factory.call_args.kwargs["http_options"]
    assert opts.retry_options.attempts == 1
    assert opts.timeout == 35000


def call_route(monkeypatch, *, enabled=True, fields="[]", extractor=None):
    monkeypatch.setattr(routes_extract, "get_settings", lambda: SimpleNamespace(max_file_size_mb=10, gemini_api_key="fake"))
    if extractor is None:
        async def extractor(pdf, model, descriptions):
            return model(gastos_tupa=[{"concepto": "Tasa", "naturaleza": "mencion", "pagina": 2}])
    fake = AsyncMock(side_effect=extractor)
    monkeypatch.setattr(routes_extract, "extract_fields", fake)
    file = UploadFile(file=io.BytesIO(b"%PDF-1.4\n%%EOF"), filename="f.pdf", headers=Headers({"content-type": "application/pdf"}))
    return asyncio.run(routes_extract.extract_contrato(file=file, fields=fields, include_cronograma=False,
                       include_items=False, include_gastos_tupa=enabled)), fake


def test_endpoint_allows_collection_only_without_second_pass(monkeypatch):
    enrich = AsyncMock()
    monkeypatch.setattr(routes_extract, "enrich_missing_location", enrich)
    result, extract = call_route(monkeypatch)
    assert result["gastos_tupa"][0]["naturaleza"] == "mencion"
    assert extract.await_count == 1
    enrich.assert_not_awaited()


def test_endpoint_old_empty_fields_and_reserved_scalar_fail(monkeypatch):
    for opts in [{"enabled": False}, {"fields": '[{"key":"gastos_tupa","label":"monto"}]'}]:
        with pytest.raises(HTTPException) as e:
            call_route(monkeypatch, **opts)
        assert e.value.status_code == 400


def test_endpoint_timeout_is_safe_and_does_not_retry(monkeypatch):
    async def timeout(*args):
        raise TimeoutError("provider secret")
    with pytest.raises(HTTPException) as e:
        call_route(monkeypatch, extractor=timeout)
    assert e.value.status_code == 504
    assert "secret" not in str(e.value.detail)

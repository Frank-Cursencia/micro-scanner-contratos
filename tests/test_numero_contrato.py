import asyncio
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.api import routes_extract
from app.services.numero_contrato import normalizar_numero_contrato


@pytest.mark.parametrize("numero,servicio,expected", [
    ("074-2026-DPAH-RUWARK S.A.C.", "pea", "CONTRATO-PEA-074-2026"),
    ("074- 2026-DPAH-RUWARK S.A.C.", "PEA", "CONTRATO-PEA-074-2026"),
    ("CONTRATO PEA-074-2026-DPAH-RUWARK S.A.C.", "pea", "CONTRATO-PEA-074-2026"),
    ("CONTRATO-PEA-074-2026", "pea", "CONTRATO-PEA-074-2026"),
    ("0008–2020", "pmar", "CONTRATO-PMAR-0008-2020"),
    ("CONTRATO 4 CIRAS Y 1 OPINIÓN FAVORABLE-475-2026-DPAH-RUWARK S.A.C.", None, "CONTRATO 4 CIRAS Y 1 OPINIÓN FAVORABLE-475-2026"),
    ("CONTRATO-CIRAS-074-2026-DPAH-RUWARK S.A.C.", "pea", "CONTRATO-CIRAS-074-2026"),
])
def test_internal_detected_service_keeps_correlative_year_and_titles(numero, servicio, expected):
    data = {"numeroDocumentoOriginal": numero, "tipoServicio": servicio, "tipoDocumentoRegularizado": "contrato_interno", "cliente": "No cambiar"}
    result = normalizar_numero_contrato(data)
    assert result["numeroDocumentoOriginal"] == expected
    assert result["cliente"] == data["cliente"]
    assert data["numeroDocumentoOriginal"] == numero
    assert normalizar_numero_contrato(result) == result


def test_no_invention_reclassification_or_new_response_fields():
    raw = "074-2026-DPAH-RUWARK S.A.C."
    for modalidad in (None, "", "contrato_externo", "orden_servicio"):
        data = {"numeroDocumentoOriginal": raw, "tipoServicio": "pea", "tipoDocumentoRegularizado": modalidad}
        assert normalizar_numero_contrato(data) == data
    for servicio in (None, "", "otro", "pea, pmar", "peritaje"):
        data = {"numeroDocumentoOriginal": raw, "tipoServicio": servicio, "tipoDocumentoRegularizado": "contrato_interno"}
        assert normalizar_numero_contrato(data) == data
    for numero in (None, "", "074", "074-20261", "074-2026-CLIENTE", "ANEXO-074-2026", "DOC-0007-2020"):
        data = {"numeroDocumentoOriginal": numero, "tipoServicio": "pea", "tipoDocumentoRegularizado": "contrato_interno"}
        assert normalizar_numero_contrato(data) == data
    assert normalizar_numero_contrato({"cliente": "Texto"}) == {"cliente": "Texto"}


def test_endpoint_returns_internal_identifier_without_extra_model_calls(monkeypatch):
    monkeypatch.setattr(routes_extract, "get_settings", lambda: SimpleNamespace(max_file_size_mb=10, gemini_api_key="fake"))
    async def extract(pdf, model, descriptions):
        return model(numeroDocumentoOriginal="074-2026-DPAH-RUWARK S.A.C.", tipoServicio="pea", tipoDocumentoRegularizado="contrato_interno")
    extractor = AsyncMock(side_effect=extract)
    monkeypatch.setattr(routes_extract, "extract_fields", extractor)
    fields = [{"key": key, "label": key} for key in ("numeroDocumentoOriginal", "tipoServicio", "tipoDocumentoRegularizado")]
    file = UploadFile(file=io.BytesIO(b"%PDF-1.4\n%%EOF"), filename="f.pdf", headers=Headers({"content-type": "application/pdf"}))
    result = asyncio.run(routes_extract.extract_contrato(file=file, fields=json.dumps(fields), include_cronograma=False, include_items=False, include_gastos_tupa=False))
    assert result["numeroDocumentoOriginal"] == "CONTRATO-PEA-074-2026"
    assert result["tipoServicio"] == "pea"
    assert extractor.await_count == 1

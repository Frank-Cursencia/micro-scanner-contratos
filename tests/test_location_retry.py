import asyncio
from unittest.mock import AsyncMock

from pydantic import BaseModel

from app.api import routes_extract
from app.models.schemas import FieldSpec


class _FirstResult(BaseModel):
    nombreProyecto: str | None = None
    locacionProyecto: str | None = None
    ciudad: str | None = None
    precioTotal: str | None = None
    cronograma_pagos: list[dict] | None = None


def test_second_pass_merges_missing_location_without_losing_other_fields(monkeypatch):
    first = _FirstResult(
        nombreProyecto="Parque Industrial",
        locacionProyecto=None,
        ciudad="",
        cronograma_pagos=[{"nombre": "Primer pago"}],
    )
    retry_model = type("RetryResult", (BaseModel,), {
        "__annotations__": {
            "locacionProyecto": str | None,
            "ciudad": str | None,
        },
        "locacionProyecto": None,
        "ciudad": None,
    })
    retry = retry_model(
        locacionProyecto="Parque Industrial de Lurín",
        ciudad="Lurín, Lima",
    )
    extract = AsyncMock(return_value=retry)
    monkeypatch.setattr(routes_extract, "extract_fields", extract)

    fields = [
        FieldSpec(key="nombreProyecto", label="Nombre"),
        FieldSpec(key="locacionProyecto", label="Ubicación"),
        FieldSpec(key="ciudad", label="Ciudad"),
    ]
    result = asyncio.run(routes_extract.enrich_missing_location(b"%PDF", fields, first))

    assert result["nombreProyecto"] == "Parque Industrial"
    assert result["cronograma_pagos"] == [{"nombre": "Primer pago"}]
    assert result["locacionProyecto"] == "Parque Industrial de Lurín"
    assert result["ciudad"] == "Lurín, Lima"
    assert extract.await_count == 1
    descriptions = extract.await_args.args[2]
    assert "SEGUNDA REVISIÓN EXCLUSIVA DE UBICACIÓN" in descriptions["locacionProyecto"]


def test_second_pass_is_skipped_when_location_is_complete(monkeypatch):
    first = _FirstResult(
        nombreProyecto="Parque Industrial",
        locacionProyecto="Lurín",
        ciudad="Lima",
    )
    extract = AsyncMock()
    monkeypatch.setattr(routes_extract, "extract_fields", extract)

    fields = [
        FieldSpec(key="locacionProyecto", label="Ubicación"),
        FieldSpec(key="ciudad", label="Ciudad"),
    ]
    result = asyncio.run(routes_extract.enrich_missing_location(b"%PDF", fields, first))

    assert result["locacionProyecto"] == "Lurín"
    assert result["ciudad"] == "Lima"
    extract.assert_not_awaited()


def test_second_pass_rereads_suspicious_total_from_document(monkeypatch):
    first = _FirstResult(
        nombreProyecto="Parque Industrial",
        locacionProyecto="Lurín",
        ciudad="Lima",
        precioTotal="2006.00",
        cronograma_pagos=[
            {"monto": "14280.00"},
            {"monto": "19040.00"},
            {"monto": "14280.00"},
        ],
    )
    retry_model = type("RetryTotal", (BaseModel,), {
        "__annotations__": {"precioTotal": str | None},
        "precioTotal": None,
    })
    extract = AsyncMock(return_value=retry_model(precioTotal="47600.00"))
    monkeypatch.setattr(routes_extract, "extract_fields", extract)

    fields = [
        FieldSpec(key="locacionProyecto", label="Ubicación"),
        FieldSpec(key="ciudad", label="Ciudad"),
        FieldSpec(key="precioTotal", label="Precio total"),
    ]
    result = asyncio.run(routes_extract.enrich_missing_location(b"%PDF", fields, first))

    assert result["precioTotal"] == "47600.00"
    descriptions = extract.await_args.args[2]
    assert "SEGUNDA REVISIÓN EXCLUSIVA DEL PRECIO TOTAL" in descriptions["precioTotal"]

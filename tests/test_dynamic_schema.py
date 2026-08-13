from app.models.schemas import FieldSpec
from app.services.dynamic_schema import build_dynamic_model


def test_build_dynamic_model_matches_requested_fields():
    fields = [FieldSpec(key="ruc", label="RUC de la empresa"), FieldSpec(key="monto", label="Monto total")]
    model = build_dynamic_model(fields, include_cronograma=False)

    assert set(model.model_fields) == {"ruc", "monto"}

    instance = model(ruc="20613452436")
    assert instance.ruc == "20613452436"
    assert instance.monto is None


def test_build_dynamic_model_adds_cronograma_when_requested():
    fields = [FieldSpec(key="ruc", label="RUC de la empresa")]
    model = build_dynamic_model(fields, include_cronograma=True)

    assert "cronograma_pagos" in model.model_fields

    instance = model(ruc="1", cronograma_pagos=[{"nombre": "Primer pago", "monto": "S/. 500", "condicion": "a la firma"}])
    assert instance.cronograma_pagos[0].nombre == "Primer pago"


def test_build_dynamic_model_without_cronograma_omits_field():
    model = build_dynamic_model([FieldSpec(key="dni", label="DNI")], include_cronograma=False)
    assert "cronograma_pagos" not in model.model_fields

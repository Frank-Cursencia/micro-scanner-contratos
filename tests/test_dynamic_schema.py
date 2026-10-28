from app.models.schemas import FieldSpec, PagoExtraido
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
    assert "nunca el porcentaje" in PagoExtraido.model_fields["monto"].description
    assert "tal como aparece" in PagoExtraido.model_fields["nombre"].description
    assert "conservando la redaccion" in PagoExtraido.model_fields["condicion"].description


def test_build_dynamic_model_without_cronograma_omits_field():
    model = build_dynamic_model([FieldSpec(key="dni", label="DNI")], include_cronograma=False)
    assert "cronograma_pagos" not in model.model_fields


def test_payment_details_are_optional_and_preserve_the_previous_contract():
    old = PagoExtraido(nombre="30%", monto="1500", condicion="A la firma")
    assert old.fecha is None
    assert old.hitoActivador is None
    assert old.porcentaje is None
    full = PagoExtraido(nombre="30%", monto="1500", condicion="A la firma",
                        fecha="15/01/2020", hitoActivador="Informe final", porcentaje="30")
    assert full.fecha == "15/01/2020"
    assert full.hitoActivador == "Informe final"
    assert full.porcentaje == "30"


def test_internal_external_and_service_order_keep_their_own_requested_fields():
    profiles = [
        (["cliente", "representanteDomicilio", "proyectoDistrito", "moneda"], False),
        (["nombreEmpresa", "precioTotal", "locacionProyecto", "ciudad"], False),
        (["nrOrdenCliente", "clienteNombre", "montoTotal", "lugarPrestacion"], True),
    ]
    for keys, include_items in profiles:
        model = build_dynamic_model([FieldSpec(key=key, label=key) for key in keys], True, include_items)
        expected = set(keys) | {"cronograma_pagos"} | ({"items"} if include_items else set())
        assert set(model.model_fields) == expected
        instance = model(**{key: f"valor-{key}" for key in keys},
                         cronograma_pagos=[{"nombre": "Saldo", "monto": "100"}])
        assert all(getattr(instance, key) == f"valor-{key}" for key in keys)
        assert instance.cronograma_pagos[0].monto == "100"

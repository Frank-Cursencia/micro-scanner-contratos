from pydantic import BaseModel, Field, create_model

from app.models.schemas import FieldSpec, ItemExtraido, PagoExtraido


def build_dynamic_model(
    fields: list[FieldSpec], include_cronograma: bool, include_items: bool = False
) -> type[BaseModel]:
    """Arma el modelo de respuesta de Gemini en runtime, a partir de los
    campos que pide el frontend. El backend no conoce de antemano qué
    campos existen — eso vive en FormData (GestionContratos.tsx /
    GestionOrdenServicio.tsx), no acá."""
    attrs: dict[str, tuple[type, Field]] = {
        field.key: (str | None, Field(default=None, description=field.label)) for field in fields
    }
    if include_cronograma:
        attrs["cronograma_pagos"] = (
            list[PagoExtraido] | None,
            Field(default=None, description="Cronograma de pagos: cuotas con nombre, monto y condición"),
        )
    if include_items:
        attrs["items"] = (
            list[ItemExtraido] | None,
            Field(default=None, description="Servicios/ítems pedidos en el documento, con su descripción y cantidad"),
        )
    return create_model("CamposExtraidos", **attrs)

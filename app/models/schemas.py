from pydantic import BaseModel, Field


class FieldSpec(BaseModel):
    """Un campo del formulario que el frontend pide buscar en el PDF."""

    key: str
    label: str


class PagoExtraido(BaseModel):
    """Una cuota del cronograma de pagos. Shape fija: espeja CronogramaPago
    en GestionContratos.tsx, es igual para los 5 tipos de servicio."""

    nombre: str | None = Field(
        default=None,
        description=(
            "Nombre o porcentaje de la cuota tal como aparece en el documento. "
            "No inventar etiquetas como Primer pago si el contrato dice Treinta "
            "por ciento (30%)."
        ),
    )
    monto: str | None = Field(
        default=None,
        description=(
            "Importe monetario de la cuota, nunca el porcentaje. Si el documento "
            "solo indica un porcentaje y contiene el monto total del contrato, "
            "calcular el importe correspondiente. Devolver solo el numero decimal "
            "sin S/, comas ni signo %."
        ),
    )
    condicion: str | None = Field(
        default=None,
        description=(
            "Condicion que activa el pago, conservando la redaccion del documento "
            "sin resumir ni agregar requisitos inexistentes."
        ),
    )


class ItemExtraido(BaseModel):
    """Un servicio/ítem pedido en el documento (ej. tabla "Descripción del
    servicio a contratar" de un TDR). Espeja Item en
    GestionOrdenServicio.tsx — sin tipoServicio: mapear ese campo al
    catálogo interno queda a criterio de quien revisa, la IA no lo intenta."""

    descripcion: str | None = None
    cantidad: str | None = None

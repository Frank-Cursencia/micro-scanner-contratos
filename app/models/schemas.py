from pydantic import BaseModel


class FieldSpec(BaseModel):
    """Un campo del formulario que el frontend pide buscar en el PDF."""

    key: str
    label: str


class PagoExtraido(BaseModel):
    """Una cuota del cronograma de pagos. Shape fija: espeja CronogramaPago
    en GestionContratos.tsx, es igual para los 5 tipos de servicio."""

    nombre: str | None = None
    monto: str | None = None
    condicion: str | None = None


class ItemExtraido(BaseModel):
    """Un servicio/ítem pedido en el documento (ej. tabla "Descripción del
    servicio a contratar" de un TDR). Espeja Item en
    GestionOrdenServicio.tsx — sin tipoServicio: mapear ese campo al
    catálogo interno queda a criterio de quien revisa, la IA no lo intenta."""

    descripcion: str | None = None
    cantidad: str | None = None

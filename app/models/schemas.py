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

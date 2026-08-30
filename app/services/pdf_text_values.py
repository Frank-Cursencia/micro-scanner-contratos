import io
import re
from decimal import Decimal, InvalidOperation

from pypdf import PdfReader


# Exige una etiqueta TOTAL propia al inicio de línea. Así no confunde
# SUBTOTAL, IGV, RUC, años ni porcentajes con el precio contractual final.
_TOTAL_LINE = re.compile(
    r"(?im)^\s*(?:precio\s+total|total(?:\s+general|\s+del\s+contrato)?)"
    r"\s*[:\-]?\s*(?:s\s*/\s*\.?\s*)?([0-9][0-9.,]*)\s*$"
)


def _decimal_amount(raw: str) -> str | None:
    cleaned = raw.strip().replace(" ", "")
    if not cleaned:
        return None
    # Formato contractual peruano usual: 47,600.00. Si solo hay coma y los
    # últimos dos dígitos parecen decimales, también acepta 47600,00.
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1 and len(cleaned.rsplit(",", 1)[1]) == 2:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return f"{Decimal(cleaned):.2f}"
    except InvalidOperation:
        return None


def extract_textual_total(pdf_bytes: bytes, expected_total: float | None = None) -> str | None:
    """Lee el TOTAL etiquetado del texto nativo del PDF, sin usar IA.

    En PDFs escaneados sin capa de texto devuelve None y el flujo conserva el
    resultado de Gemini. No realiza OCR ni calcula el total desde las cuotas.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return None

    values = [
        value
        for match in _TOTAL_LINE.finditer(text)
        if (value := _decimal_amount(match.group(1))) is not None
    ]
    if not values:
        return None
    if expected_total is not None and expected_total > 0:
        closest = min(values, key=lambda value: abs(float(value) - expected_total))
        return closest if abs(float(closest) - expected_total) <= max(0.01, expected_total * 0.01) else None
    # Sin una referencia cruzada solo es seguro usar el valor cuando el PDF
    # contiene una única línea TOTAL; con varias no se adivina cuál corresponde.
    return values[0] if len(values) == 1 else None

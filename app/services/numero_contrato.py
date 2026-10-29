"""Identificación de contratos internos; no genera números ni consulta servicios."""
import re


def normalizar_numero_contrato(data: dict) -> dict:
    original = data.get("numeroDocumentoOriginal")
    if data.get("tipoDocumentoRegularizado") != "contrato_interno" or not isinstance(original, str):
        return data
    numero = original.strip()
    if not numero or len(numero) > 255:
        return data
    servicio = data.get("tipoServicio")
    servicio = servicio.strip().lower() if isinstance(servicio, str) else ""
    # PERITAJE no lleva prefijo de servicio en su título histórico.
    prefijo = servicio.upper() if servicio in {"ciras", "pea", "das", "pmar", "optecnica", "pra"} else ""
    limpio = re.sub(r"\s*[-–—]\s*DPAH\s*[-–—]\s*RUWARK\s+S\.?\s*A\.?\s*C\.?\s*$", "", numero, flags=re.I).strip()
    corto = re.fullmatch(r"(?:CONTRATO[\s–—-]+)?([0-9]+)\s*[-–—]\s*((?:19|20)[0-9]{2})", limpio)
    completo = re.fullmatch(r"CONTRATO[\s–—-]+(CIRAS|PEA|DAS|PMAR|OPTECNICA|PRA)[\s–—-]+([0-9]+)\s*[-–—]\s*((?:19|20)[0-9]{2})", limpio, flags=re.I)
    if corto and prefijo:
        numero = f"CONTRATO-{prefijo}-{corto[1]}-{corto[2]}"
    elif completo and completo[1].upper() == prefijo:
        numero = f"CONTRATO-{prefijo}-{completo[2]}-{completo[3]}"
    elif re.fullmatch(r"CONTRATO\b.+[-–—]\s*[0-9]+\s*[-–—]\s*(?:19|20)[0-9]{2}", limpio, flags=re.I):
        numero = limpio
    return {**data, "numeroDocumentoOriginal": numero}

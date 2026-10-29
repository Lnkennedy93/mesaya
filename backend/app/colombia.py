"""Reglas y catálogos específicos de Colombia."""

# Tipos de impuesto aplicables a restaurantes. `pct` es el valor por defecto.
# - INC 8 %: Impuesto Nacional al Consumo (régimen habitual de restaurantes, bares y cafeterías).
# - IVA: para quienes son responsables de IVA y no de INC.
# Confirma con tu contador cuál aplica a tu negocio: aquí solo se configura.
TAX_TYPES = {
    "INC": {"label": "INC (Impoconsumo)", "pct": 8.0, "dian_code": "04"},
    "IVA": {"label": "IVA", "pct": 19.0, "dian_code": "01"},
    "IVA5": {"label": "IVA 5 %", "pct": 5.0, "dian_code": "01"},
    "NONE": {"label": "No responsable / excluido", "pct": 0.0, "dian_code": "ZZ"},
}

# Tipos de documento del cliente. `factus` = id interno de Factus (verifícalo en tu sandbox),
# `dian` = código DIAN estándar.
ID_TYPES = {
    "CC": {"label": "Cédula de ciudadanía", "factus": 3, "dian": "13"},
    "NIT": {"label": "NIT", "factus": 6, "dian": "31"},
    "CE": {"label": "Cédula de extranjería", "factus": 5, "dian": "22"},
    "PP": {"label": "Pasaporte", "factus": 7, "dian": "41"},
}

CONSUMIDOR_FINAL = {"doc_type": "CC", "doc_number": "222222222222", "name": "Consumidor Final", "email": ""}

_WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def nit_dv(nit: str) -> str:
    """Dígito de verificación de un NIT (algoritmo oficial DIAN, módulo 11)."""
    digits = "".join(c for c in str(nit) if c.isdigit())
    if not digits or len(digits) > 15:
        return ""
    total = sum(int(d) * w for d, w in zip(reversed(digits), _WEIGHTS))
    r = total % 11
    return str(r if r < 2 else 11 - r)


def clean_customer(raw: dict | None) -> dict:
    """Normaliza los datos de factura que escribe el cliente. Sin datos → Consumidor Final."""
    raw = raw or {}
    num = "".join(c for c in str(raw.get("doc_number", "")) if c.isdigit())
    name = str(raw.get("name", "")).strip()[:100]
    if not num or not name:
        return dict(CONSUMIDOR_FINAL)
    dt = raw.get("doc_type") if raw.get("doc_type") in ID_TYPES else "CC"
    out = {"doc_type": dt, "doc_number": num[:15], "name": name, "email": str(raw.get("email", "")).strip()[:120],
           "phone": "".join(c for c in str(raw.get("phone", "")) if c.isdigit())[:10],
           "address": str(raw.get("address", "")).strip()[:120]}
    if dt == "NIT":
        out["dv"] = nit_dv(num)
    return out

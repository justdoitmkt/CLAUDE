"""Normalización de teléfonos a E.164 para usarlos como clave única en HubSpot y WhatsApp.

Reglas, en orden de confianza:
  * Con "+" (código de país explícito)  -> se respeta tal cual.
  * 12 dígitos que empiezan con 52      -> México con código de país.
  * 13 dígitos que empiezan con 521     -> México con el "1" histórico de móvil; se elimina el "1".
  * 11 dígitos que empiezan con 1       -> EE. UU./Canadá.
  * 044/045 + 10 dígitos, o 01 + 10     -> prefijos de marcación históricos de México; se eliminan.
  * 10 dígitos sin código               -> México asumido (el negocio es mexicano).
  * Cualquier otra cosa                 -> "revisar".

El resultado siempre se valida con libphonenumber; lo que no valida nunca llega
como "Válido" a HubSpot, así el bot no intenta escribirle a números imposibles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import phonenumbers

# Calidad del teléfono (valores = etiquetas de la propiedad `calidad_telefono` en HubSpot).
VALIDO = "Válido"
ASUMIDO_MX = "Asumido MX"
REVISAR = "Revisar"
SIN_TELEFONO = "Sin teléfono"

_VACIOS = re.compile(r"^\s*(no\s+disponible|n/?a|s/?n|sin\s+tel[eé]fono|-+|\.+)?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class PhoneResult:
    e164: str | None  # "+525512345678" o None
    calidad: str  # VALIDO | ASUMIDO_MX | REVISAR | SIN_TELEFONO
    nota: str = ""  # explicación humana cuando calidad != VALIDO


def normalize_phone(raw: object, default_region: str = "MX") -> PhoneResult:
    """Convierte cualquier formato capturado a mano a E.164 y clasifica su calidad."""
    s = "" if raw is None else str(raw)
    # El PDF trae guion no separable (U+2011) y saltos de línea dentro de la celda.
    s = s.replace("‑", "-").replace(" ", " ").replace("\n", " ").strip()
    if _VACIOS.match(s):
        return PhoneResult(None, SIN_TELEFONO, "sin teléfono en el origen")

    digits = re.sub(r"\D", "", s)
    explicit_cc = "+" in s
    asumido = False

    if explicit_cc:
        candidate = "+" + digits
    elif len(digits) == 12 and digits.startswith("52"):
        candidate = "+" + digits
    elif len(digits) == 13 and digits.startswith("521"):
        candidate = "+52" + digits[3:]
    elif len(digits) == 11 and digits.startswith("1"):
        candidate = "+" + digits
    elif len(digits) == 13 and digits[:3] in ("044", "045"):  # prefijo móvil anterior a 2019
        candidate, asumido = "+52" + digits[3:], True
    elif len(digits) == 12 and digits.startswith("01"):  # prefijo de larga distancia nacional
        candidate, asumido = "+52" + digits[2:], True
    elif len(digits) == 10:
        candidate = "+52" + digits
        asumido = True
    else:
        return PhoneResult(None, REVISAR, f"longitud inesperada ({len(digits)} dígitos): {s!r}")

    try:
        num = phonenumbers.parse(candidate, None)
    except phonenumbers.NumberParseException as exc:
        return PhoneResult(None, REVISAR, f"no se pudo interpretar {s!r}: {exc}")

    # México: libphonenumber acepta "+52 1 ..." (formato viejo). WhatsApp trabaja con +52 + 10 dígitos.
    if num.country_code == 52:
        national = str(num.national_number)
        if len(national) == 11 and national.startswith("1"):
            num = phonenumbers.parse("+52" + national[1:], None)

    if not phonenumbers.is_valid_number(num):
        return PhoneResult(None, REVISAR, f"número inválido para libphonenumber: {s!r}")

    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    if asumido:
        return PhoneResult(e164, ASUMIDO_MX, "sin código de país en el origen; se asumió México (+52)")
    return PhoneResult(e164, VALIDO)


def normalize_wa_id(wa_id: object) -> str | None:
    """Normaliza el `wa_id` que WhatsApp entrega en los webhooks para buscarlo en HubSpot.

    WhatsApp puede devolver móviles mexicanos como "521XXXXXXXXXX" (con el 1 histórico)
    y HubSpot guarda "+52XXXXXXXXXX". Devuelve E.164 o None si no es interpretable.
    """
    digits = re.sub(r"\D", "", "" if wa_id is None else str(wa_id))
    if not digits:
        return None
    res = normalize_phone("+" + digits)
    return res.e164

"""Limpieza y separación de nombres de huéspedes.

El origen mezcla "Nombre Apellido", "APELLIDO APELLIDO NOMBRE", "Apellidos, Nombre",
MAYÚSCULAS, minúsculas y anotaciones ("(Segunda reserva)", "- Boda Sol").
Para el bot lo crítico es NO saludar con un apellido, así que `saludo` solo se llena
cuando hay evidencia de cuál token es el nombre de pila; si no, queda vacío y el bot
usa un saludo genérico.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .given_names import NOMBRES_DE_PILA

ALTA, MEDIA, BAJA, INVALIDA = "alta", "media", "baja", "invalida"

_PARTICULAS = {"de", "del", "la", "las", "los", "y", "e", "da", "di", "van", "von"}
_MESES = {
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
}
_ABREVIATURAS = {"fco": "Francisco", "ma": "María", "jose": "José"}
_SEPARADOR_EXTRA = re.compile(r"\s+(?:-{1,2}|–|—|/)\s+")
_PREFIJO_FAMILIA = re.compile(r"^(?:familia|fam\.?)\s+", re.IGNORECASE)
_TITULOS = re.compile(r"^(?:dr|dra|lic|licda|ing|arq|mtro|mtra|prof|profe|sr|sra|srita|don|doña|dona)\.?\s+",
                      re.IGNORECASE)
# Compuestos que son parte del nombre de pila ("María del Carmen", "Miguel de Jesús"). Los primeros
# son casi siempre nombre; "de Jesús"/"de Padua" también son apellido, así que exigen nombre de pila previo.
_COMPUESTO_SEGURO = r"del carmen|de la luz|de los angeles|del rosario|de guadalupe|del socorro|de la paz|del pilar|de lourdes|del refugio"
_COMPUESTO_CONDICIONAL = r"de jesus|de padua"
_RE_COMPUESTO = re.compile(
    rf"^(?P<pre>\S+(?:\s\S+)?)\s+(?P<comp>{_COMPUESTO_SEGURO}|{_COMPUESTO_CONDICIONAL})(?:\s+(?P<resto>.+))?$",
    re.IGNORECASE,
)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _clave(token: str) -> str:
    return _sin_acentos(token).lower().strip(".")


def _es_nombre_de_pila(token: str) -> bool:
    return _clave(token) in NOMBRES_DE_PILA


@dataclass(frozen=True)
class NombreLimpio:
    completo: str  # "Nombre Apellidos" ya capitalizado ("" si es inválido)
    nombre: str  # -> firstname en HubSpot
    apellidos: str  # -> lastname en HubSpot
    saludo: str  # para el bot; "" si no hay certeza
    confianza: str  # alta | media | baja | invalida
    extras: str  # anotaciones recortadas ("Segunda reserva", "Boda Sol"...)
    es_grupo: bool  # familia / varios nombres


def _capitalizar_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for i, tok in enumerate(tokens):
        if i > 0 and tok.lower() in _PARTICULAS:
            out.append(tok.lower())
            continue
        if tok.islower() or tok.isupper():
            # "ramón" / "JUAREZ" -> "Ramón" / "Juarez"; respeta compuestos con guion.
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in tok.split("-")))
        else:
            out.append(tok)  # ya viene con mayúsculas mixtas ("McGregor", "De Lira")
    return out


def _saludo(nombre: str) -> str:
    primero = nombre.split()[0] if nombre.split() else ""
    return _ABREVIATURAS.get(_clave(primero), primero)


def limpiar_nombre(raw: object) -> NombreLimpio:
    s = "" if raw is None else re.sub(r"\s+", " ", str(raw)).strip()
    extras: list[str] = []

    for m in re.findall(r"\(([^)]*)\)", s):
        if m.strip():
            extras.append(m.strip())
    s = re.sub(r"\([^)]*\)", " ", s)

    partes = _SEPARADOR_EXTRA.split(s)
    s = partes[0].strip()
    extras += [p.strip() for p in partes[1:] if p.strip()]
    extras_txt = " | ".join(extras)

    m_tit = _TITULOS.match(s)
    if m_tit:
        extras.append(m_tit.group(0).strip().rstrip("."))
        s = s[m_tit.end():]
        extras_txt = " | ".join(extras)

    if not s or _clave(s) in _MESES or len(_sin_acentos(s)) < 2:
        return NombreLimpio("", "", "", "", INVALIDA, extras_txt, False)

    # --- Familias ("Familia Roble", "Fam. Duarte Nieto") -------------------------------
    m_fam = _PREFIJO_FAMILIA.match(s)
    if m_fam:
        apellidos = " ".join(_capitalizar_tokens(s[m_fam.end():].split()))
        if not apellidos:
            return NombreLimpio("", "", "", "", INVALIDA, extras_txt, True)
        primero = apellidos.split()[0]
        return NombreLimpio(f"Familia {apellidos}", "Familia", apellidos,
                            f"familia {primero}", ALTA, extras_txt, True)

    # --- "Apellidos, Nombre(s)" -----------------------------------------------------------
    if "," in s:
        trozos = [t.strip() for t in s.split(",") if t.strip()]
        if len(trozos) >= 2:
            nombre = " ".join(_capitalizar_tokens(trozos[-1].split()))
            apellidos = " ".join(_capitalizar_tokens(" ".join(trozos[:-1]).split()))
            return NombreLimpio(f"{nombre} {apellidos}".strip(), nombre, apellidos,
                                _saludo(nombre), ALTA, extras_txt, False)
        s = trozos[0] if trozos else s

    toks = _capitalizar_tokens(s.split())

    # --- "Nombre del Carmen Apellido", "Miguel de Jesús Apellido" --------------------------
    m_comp = _RE_COMPUESTO.match(_sin_acentos(" ".join(toks)))
    if m_comp:
        comp_es_seguro = re.fullmatch(_COMPUESTO_SEGURO, m_comp.group("comp").lower()) is not None
        pre_toks = toks[: len(m_comp.group("pre").split())]
        if comp_es_seguro or _es_nombre_de_pila(pre_toks[0]):
            n_comp = len(m_comp.group("comp").split())
            nombre = " ".join(pre_toks + [t.lower() if t.lower() in _PARTICULAS else t
                                          for t in toks[len(pre_toks): len(pre_toks) + n_comp]])
            apellidos = " ".join(toks[len(pre_toks) + n_comp:])
            return NombreLimpio(f"{nombre} {apellidos}".strip(), nombre, apellidos,
                                _saludo(nombre), ALTA, extras_txt, False)

    nucleo = toks[:]
    iniciales: list[str] = []  # "Norma A" -> la "A" final no cuenta para clasificar
    while len(nucleo) > 1 and len(nucleo[-1].strip(".")) == 1:
        iniciales.insert(0, nucleo.pop())
    n = len(nucleo)

    def armar(nombre_toks: list[str], apellido_toks: list[str], conf: str, apellido_primero: bool = False) -> NombreLimpio:
        # La inicial suelta es del apellido materno en "Nombre Apellido X", pero del nombre en "Apellido Nombre X".
        a_nombre = apellido_primero or not apellido_toks
        nombre = " ".join(nombre_toks + (iniciales if a_nombre else []))
        apellidos = " ".join(apellido_toks + ([] if a_nombre else iniciales))
        completo = f"{nombre} {apellidos}".strip()
        saludo = _saludo(nombre) if conf in (ALTA, MEDIA) else ""
        return NombreLimpio(completo, nombre, apellidos, saludo, conf, extras_txt, False)

    if n == 1:
        if _es_nombre_de_pila(nucleo[0]):
            return armar(nucleo, [], ALTA)
        return NombreLimpio(" ".join(toks), " ".join(toks), "", "", BAJA, extras_txt, False)

    if _es_nombre_de_pila(nucleo[0]):  # "Nombre [Nombre] Apellido(s)"
        k = 1
        while k < min(n, 3) and _es_nombre_de_pila(nucleo[k]) and k < n - 1:
            k += 1
        if k == n - 1 and n == 2 and _es_nombre_de_pila(nucleo[1]):
            return armar(nucleo, [], MEDIA)  # "Iker Mateo": sin apellido
        return armar(nucleo[:k], nucleo[k:], ALTA)

    if _es_nombre_de_pila(nucleo[-1]):  # "Apellido(s) Nombre [Nombre]"
        j = n - 1
        while j - 1 >= 1 and _es_nombre_de_pila(nucleo[j - 1]) and (n - j) < 2:
            j -= 1
        return armar(nucleo[j:], nucleo[:j], MEDIA, apellido_primero=True)

    return NombreLimpio(" ".join(toks), " ".join(toks), "", "", BAJA, extras_txt, False)


def clave_comparacion(nombre: str) -> str:
    """Clave insensible a acentos, mayúsculas y orden de tokens (para detectar nombres repetidos)."""
    toks = [t for t in re.split(r"\W+", _sin_acentos(nombre).lower()) if t and t not in _PARTICULAS]
    return " ".join(sorted(toks))

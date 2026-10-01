"""Cliente mínimo de la API de HubSpot (CRM v3) para el bot de WhatsApp.

Contrato entre el bot y HubSpot (HubSpot es la fuente de verdad de los huéspedes):
  * Clave de búsqueda: propiedad única `telefono_e164` (E.164, p. ej. +525512345678).
  * Solo se envían mensajes de iniciativa propia a quien tenga `whatsapp_opt_in = "Sí"`.
  * Dentro de las 24 h posteriores a un mensaje entrante se puede responder libremente;
    fuera de esa ventana, solo con plantillas aprobadas por Meta.

No necesita librerías de HubSpot; usa `requests`. El token es el de una Private App y se
lee de la variable de entorno HUBSPOT_TOKEN (nunca va en el código ni en el repositorio).
Alcances (scopes) mínimos para el bot: crm.objects.contacts.read y crm.objects.contacts.write.
"""
from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator
from urllib.parse import quote

import requests

from . import hubspot_schema as H
from .phones import normalize_wa_id

log = logging.getLogger(__name__)

BASE_URL = "https://api.hubapi.com"
CLAVE = "telefono_e164"
LOTE = 100  # máximo de registros por llamada batch
VENTANA_SERVICIO = timedelta(hours=24)

PROPIEDADES_BOT = [
    CLAVE, "firstname", "lastname", "phone", "nombre_saludo", "nombre_confianza", "calidad_telefono",
    "whatsapp_opt_in", "whatsapp_opt_in_fecha", "wa_ultimo_mensaje_cliente", "wa_ultimo_envio",
    "wa_estado_envio", "ultima_reserva", "total_reservas", "anios_visita", "lastmodifieddate",
]


class HubSpotError(RuntimeError):
    def __init__(self, status: int, mensaje: str):
        super().__init__(f"HubSpot respondió {status}: {mensaje}")
        self.status = status


def _iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _a_datetime(valor: Any) -> datetime | None:
    """HubSpot devuelve fechas-hora como ISO 8601 o como milisegundos desde 1970 (en texto)."""
    if valor in (None, ""):
        return None
    s = str(valor).strip()
    try:
        if re.fullmatch(r"\d{10,}", s):
            return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class HubSpotClient:
    def __init__(self, token: str | None = None, *, base_url: str = BASE_URL,
                 session: requests.Session | None = None, max_reintentos: int = 5,
                 timeout: float = 30.0, dormir: Callable[[float], None] = time.sleep) -> None:
        token = token or os.environ.get("HUBSPOT_TOKEN")
        if not token:
            raise ValueError("Falta el token de HubSpot: define la variable de entorno HUBSPOT_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.max_reintentos = max_reintentos
        self.timeout = timeout
        self._dormir = dormir
        self._s = session or requests.Session()
        self._s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    # --------------------------------------------------------------------------------------------
    def _request(self, metodo: str, ruta: str, *, params: dict | None = None, cuerpo: dict | None = None,
                 aceptar: Iterable[int] = (200, 201, 204, 207)) -> dict:
        """Una llamada con reintentos ante 429 (límite de tasa) y 5xx. Nunca registra el token."""
        aceptar = set(aceptar)
        for intento in range(self.max_reintentos + 1):
            resp = self._s.request(metodo, self.base_url + ruta, params=params, json=cuerpo, timeout=self.timeout)
            if resp.status_code in aceptar:
                return resp.json() if resp.content else {}
            reintentable = resp.status_code == 429 or resp.status_code >= 500
            if reintentable and intento < self.max_reintentos:
                espera = self._espera(resp, intento)
                log.warning("HubSpot %s en %s %s; reintento %d/%d en %.1fs", resp.status_code, metodo, ruta,
                            intento + 1, self.max_reintentos, espera)
                self._dormir(espera)
                continue
            try:
                detalle = resp.json().get("message", resp.text)
            except ValueError:
                detalle = resp.text
            raise HubSpotError(resp.status_code, str(detalle)[:500])
        raise AssertionError("inalcanzable")  # pragma: no cover

    @staticmethod
    def _espera(resp: requests.Response, intento: int) -> float:
        try:
            return min(float(resp.headers["Retry-After"]), 60.0)
        except (KeyError, ValueError):
            return float(min(2 ** intento, 30))

    # --------------------------------------------------------------------------------------------
    # Contactos
    # --------------------------------------------------------------------------------------------
    def obtener_por_telefono(self, e164: str, propiedades: list[str] | None = None) -> dict | None:
        try:
            return self._request(
                "GET", f"/crm/v3/objects/contacts/{quote(e164, safe='')}",
                params={"idProperty": CLAVE, "properties": ",".join(propiedades or PROPIEDADES_BOT)})
        except HubSpotError as exc:
            if exc.status == 404:
                return None
            raise

    def buscar(self, filtros: list[dict], propiedades: list[str] | None = None, *, por_pagina: int = 100,
               orden: list[dict] | None = None) -> Iterator[dict]:
        """Recorre todas las páginas de una búsqueda (los filtros de un grupo se combinan con AND)."""
        cuerpo: dict[str, Any] = {"filterGroups": [{"filters": filtros}], "limit": por_pagina,
                                  "properties": propiedades or PROPIEDADES_BOT}
        if orden:
            cuerpo["sorts"] = orden
        despues: str | None = None
        while True:
            pagina = {**cuerpo, "after": despues} if despues else dict(cuerpo)  # un cuerpo nuevo por petición
            data = self._request("POST", "/crm/v3/objects/contacts/search", cuerpo=pagina)
            yield from data.get("results", [])
            despues = data.get("paging", {}).get("next", {}).get("after")
            if not despues:
                return
            self._dormir(0.25)  # la búsqueda tiene un límite de tasa más estricto (~5 llamadas/s)

    def modificados_desde(self, desde: datetime | None = None) -> Iterator[dict]:
        """Sincronización: contactos creados o modificados desde `desde` (sin fecha = todos los que tienen teléfono).

        Salen del más antiguo al más reciente: guarda la `lastmodifieddate` del último como marca de agua y
        en la siguiente vuelta pide desde esa fecha (se usa >= para no perder registros del mismo instante;
        reprocesar uno repetido es inocuo porque la caché se actualiza por teléfono).
        En contactos la propiedad es `lastmodifieddate` (en negocios y empresas es `hs_lastmodifieddate`).
        """
        if desde is None:
            filtros = [{"propertyName": CLAVE, "operator": "HAS_PROPERTY"}]
        else:
            filtros = [{"propertyName": "lastmodifieddate", "operator": "GTE",
                        "value": str(int(desde.timestamp() * 1000))}]
        yield from self.buscar(filtros, orden=[{"propertyName": "lastmodifieddate", "direction": "ASCENDING"}])

    def elegibles_para_envio(self, filtros_extra: list[dict] | None = None) -> Iterator[dict]:
        """Contactos a los que SÍ se puede escribir por iniciativa propia (con plantilla aprobada)."""
        filtros = [
            {"propertyName": "whatsapp_opt_in", "operator": "EQ", "value": H.OPT_IN_SI},
            {"propertyName": "calidad_telefono", "operator": "IN", "values": ["Válido", "Asumido MX"]},
            *(filtros_extra or []),
        ]
        for c in self.buscar(filtros):
            # Se filtra aquí y no en la consulta: los operadores negativos de HubSpot no siempre
            # incluyen registros sin valor, y un "vacío" aquí significa "nunca se ha enviado".
            if c.get("properties", {}).get("wa_estado_envio") not in H.ESTADOS_NO_ENVIAR:
                yield c

    def upsert(self, items: list[dict]) -> list[dict]:
        """Crea o actualiza por teléfono. items = [{"id": "+52...", "properties": {...}}]."""
        resultados: list[dict] = []
        for i in range(0, len(items), LOTE):
            lote = items[i:i + LOTE]
            data = self._request("POST", "/crm/v3/objects/contacts/batch/upsert", cuerpo={
                "inputs": [{"idProperty": CLAVE, "id": it["id"], "properties": it["properties"]} for it in lote]})
            if data.get("errors"):
                raise HubSpotError(207, f"{len(data['errors'])} registros con error: {str(data['errors'][0])[:300]}")
            resultados += data.get("results", [])
        return resultados

    def actualizar(self, e164: str, propiedades: dict[str, Any]) -> dict:
        return self._request("PATCH", f"/crm/v3/objects/contacts/{quote(e164, safe='')}",
                             params={"idProperty": CLAVE}, cuerpo={"properties": propiedades})

    def crear(self, propiedades: dict[str, Any]) -> dict:
        return self._request("POST", "/crm/v3/objects/contacts", cuerpo={"properties": propiedades})

    # --------------------------------------------------------------------------------------------
    # Operaciones del bot
    # --------------------------------------------------------------------------------------------
    def registrar_mensaje_entrante(self, wa_id: str, nombre_perfil: str | None = None,
                                   ahora: datetime | None = None) -> tuple[dict, bool]:
        """Llamar en cada mensaje entrante. Devuelve (contacto, fue_creado).

        Actualiza la marca de la ventana de 24 h; si el número no existe en HubSpot lo crea con
        consentimiento "Pendiente" (que alguien escriba primero no equivale a aceptar promociones).
        """
        e164 = normalize_wa_id(wa_id)
        if not e164:
            raise ValueError("wa_id no interpretable como teléfono")
        marca = _iso(ahora)
        contacto = self.obtener_por_telefono(e164)
        if contacto:
            self.actualizar(e164, {"wa_ultimo_mensaje_cliente": marca})
            return contacto, False
        try:
            nuevo = self.crear({
                CLAVE: e164, "phone": e164, "firstname": (nombre_perfil or "").strip(),
                "lifecyclestage": "lead", "whatsapp_opt_in": H.OPT_IN_PENDIENTE, "calidad_telefono": "Válido",
                "fuentes_datos": "Bot WhatsApp", "wa_ultimo_mensaje_cliente": marca})
            return nuevo, True
        except HubSpotError as exc:
            if exc.status != 409:  # 409 = otro proceso lo creó justo ahora (clave única)
                raise
            self.actualizar(e164, {"wa_ultimo_mensaje_cliente": marca})
            return self.obtener_por_telefono(e164) or {}, False

    def registrar_envio(self, e164: str, estado: str, plantilla: str | None = None,
                        ahora: datetime | None = None) -> None:
        if estado not in H.ESTADOS_ENVIO:
            raise ValueError(f"estado de envío desconocido: {estado!r}")
        props: dict[str, Any] = {"wa_ultimo_envio": _iso(ahora), "wa_estado_envio": estado}
        if plantilla:
            props["wa_plantilla_ultima"] = plantilla
        self.actualizar(e164, props)

    def registrar_baja(self, e164: str, hoy: date | None = None) -> None:
        self.actualizar(e164, {"whatsapp_opt_in": H.OPT_IN_NO,
                               "whatsapp_opt_in_fecha": (hoy or date.today()).isoformat()})

    def registrar_opt_in(self, e164: str, fuente: str, hoy: date | None = None) -> None:
        self.actualizar(e164, {"whatsapp_opt_in": H.OPT_IN_SI, "whatsapp_opt_in_fuente": fuente,
                               "whatsapp_opt_in_fecha": (hoy or date.today()).isoformat()})


# ------------------------------------------------------------------------------------------------
# Reglas de decisión (funciones puras: no tocan la red)
# ------------------------------------------------------------------------------------------------
def ventana_24h_abierta(contacto: dict, ahora: datetime | None = None) -> bool:
    """¿Se puede responder con texto libre? (último mensaje del cliente hace menos de 24 h)."""
    ultimo = _a_datetime(contacto.get("properties", {}).get("wa_ultimo_mensaje_cliente"))
    return bool(ultimo) and (ahora or datetime.now(timezone.utc)) - ultimo < VENTANA_SERVICIO


def puede_enviar_plantilla(contacto: dict) -> bool:
    """¿Se le puede escribir por iniciativa propia? Exige consentimiento y un teléfono usable."""
    p = contacto.get("properties", {})
    return (p.get("whatsapp_opt_in") == H.OPT_IN_SI
            and p.get("calidad_telefono") in ("Válido", "Asumido MX")
            and p.get("wa_estado_envio") not in H.ESTADOS_NO_ENVIAR)


def saludo(contacto: dict, generico: str = "Hola") -> str:
    """'Hola Marina' si hay nombre confiable; si no, el saludo genérico (nunca saluda por apellido)."""
    p = contacto.get("properties", {})
    nombre = (p.get("nombre_saludo") or "").strip()
    return f"{generico} {nombre}" if nombre and p.get("nombre_confianza") in ("Alta", "Media") else generico


_BAJAS = {"baja", "stop", "alto", "cancelar", "salir", "unsubscribe", "no mas", "ya no", "cancelar suscripcion"}
_FRASES_BAJA = ("dejar de recibir", "no quiero recibir", "no me escriban", "no me escribas", "ya no me escriban")


def texto_es_baja(texto: str) -> bool:
    """Detecta una solicitud de baja. Ante la duda se asume baja: respetar la baja es obligatorio."""
    t = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    t = " ".join(t.split())
    return t in _BAJAS or any(f in t for f in _FRASES_BAJA)

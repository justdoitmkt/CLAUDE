"""Pruebas del cliente de HubSpot con una sesión simulada (sin red y sin credenciales reales)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from guest_crm import hubspot_schema as H, hubspot_setup
from guest_crm.hubspot_api import (HubSpotClient, HubSpotError, puede_enviar_plantilla, saludo, texto_es_baja,
                                   ventana_24h_abierta)

AHORA = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)


class Resp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code, self._data, self.headers = status, data if data is not None else {}, headers or {}
        self.content = b"x" if data is not None else b""
        self.text = str(self._data)

    def json(self):
        return self._data


class FakeSession:
    """Responde en orden con lo que se le programe y guarda cada petición para inspeccionarla."""

    def __init__(self, *respuestas):
        self.headers, self.cola, self.llamadas = {}, list(respuestas), []

    def request(self, metodo, url, params=None, json=None, timeout=None):
        self.llamadas.append({"metodo": metodo, "url": url, "params": params, "json": json})
        return self.cola.pop(0) if self.cola else Resp(200, {})


def cliente(*respuestas):
    s = FakeSession(*respuestas)
    esperas: list[float] = []
    return HubSpotClient("token-de-prueba", session=s, dormir=esperas.append), s, esperas


def test_sin_token_falla_claro(monkeypatch):
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="HUBSPOT_TOKEN"):
        HubSpotClient()


def test_el_token_va_en_el_encabezado_y_nunca_en_los_errores():
    c, s, _ = cliente(Resp(401, {"message": "invalid credentials"}))
    assert s.headers["Authorization"] == "Bearer token-de-prueba"
    with pytest.raises(HubSpotError) as exc:
        c.obtener_por_telefono("+525512345678")
    assert "token-de-prueba" not in str(exc.value) and exc.value.status == 401


def test_busqueda_por_telefono_codifica_el_mas_y_usa_la_clave_unica():
    c, s, _ = cliente(Resp(200, {"id": "7", "properties": {"telefono_e164": "+525512345678"}}))
    assert c.obtener_por_telefono("+525512345678")["id"] == "7"
    llamada = s.llamadas[0]
    assert llamada["url"].endswith("/crm/v3/objects/contacts/%2B525512345678")
    assert llamada["params"]["idProperty"] == "telefono_e164"


def test_telefono_inexistente_devuelve_none():
    c, _, _ = cliente(Resp(404, {"message": "not found"}))
    assert c.obtener_por_telefono("+525512345678") is None


def test_reintenta_ante_429_respetando_retry_after_y_ante_5xx_con_espera_exponencial():
    c, s, esperas = cliente(Resp(429, {}, {"Retry-After": "3"}), Resp(502, {}), Resp(200, {"id": "1"}))
    assert c.obtener_por_telefono("+525512345678")["id"] == "1"
    assert esperas == [3.0, 2.0] and len(s.llamadas) == 3


def test_se_rinde_tras_los_reintentos_y_no_reintenta_errores_del_cliente():
    c, s, _ = cliente(*[Resp(429, {})] * 10)
    with pytest.raises(HubSpotError) as exc:
        c.obtener_por_telefono("+525512345678")
    assert exc.value.status == 429 and len(s.llamadas) == 6
    c, s, _ = cliente(Resp(400, {"message": "bad"}), Resp(200, {}))
    with pytest.raises(HubSpotError):
        c.actualizar("+525512345678", {"x": "y"})
    assert len(s.llamadas) == 1


def test_upsert_manda_lotes_de_100_con_la_clave_unica():
    c, s, _ = cliente(*[Resp(200, {"results": [{"id": str(i)} for i in range(100)]})] * 3)
    items = [{"id": f"+52551234{i:04d}", "properties": {"firstname": "A"}} for i in range(250)]
    assert len(c.upsert(items)) == 300  # el simulado devuelve 100 por llamada
    assert [len(l["json"]["inputs"]) for l in s.llamadas] == [100, 100, 50]
    assert s.llamadas[0]["json"]["inputs"][0] == {"idProperty": "telefono_e164", "id": "+525512340000",
                                                  "properties": {"firstname": "A"}}
    assert s.llamadas[0]["url"].endswith("/crm/v3/objects/contacts/batch/upsert")


def test_upsert_con_errores_parciales_no_pasa_en_silencio():
    c, _, _ = cliente(Resp(207, {"results": [], "errors": [{"message": "boom"}]}))
    with pytest.raises(HubSpotError, match="1 registros con error"):
        c.upsert([{"id": "+525512345678", "properties": {}}])


def test_la_busqueda_recorre_todas_las_paginas():
    p1 = Resp(200, {"results": [{"id": "1"}, {"id": "2"}], "paging": {"next": {"after": "2"}}})
    p2 = Resp(200, {"results": [{"id": "3"}]})
    c, s, esperas = cliente(p1, p2)
    assert [r["id"] for r in c.buscar([{"propertyName": "a", "operator": "EQ", "value": "b"}])] == ["1", "2", "3"]
    assert "after" not in s.llamadas[0]["json"] and s.llamadas[1]["json"]["after"] == "2"
    assert esperas == [0.25]  # pausa entre páginas por el límite de tasa de la búsqueda


def test_sincronizacion_incremental_pide_desde_la_marca_de_agua_en_orden_ascendente():
    c, s, _ = cliente(Resp(200, {"results": [{"id": "1"}]}), Resp(200, {"results": [{"id": "2"}]}))
    assert [r["id"] for r in c.modificados_desde(AHORA)] == ["1"]
    cuerpo = s.llamadas[0]["json"]
    assert cuerpo["filterGroups"][0]["filters"] == [
        {"propertyName": "lastmodifieddate", "operator": "GTE", "value": str(int(AHORA.timestamp() * 1000))}]
    assert cuerpo["sorts"] == [{"propertyName": "lastmodifieddate", "direction": "ASCENDING"}]
    assert "lastmodifieddate" in cuerpo["properties"]
    list(c.modificados_desde())                                   # carga completa inicial
    assert s.llamadas[1]["json"]["filterGroups"][0]["filters"] == [
        {"propertyName": "telefono_e164", "operator": "HAS_PROPERTY"}]


def test_elegibles_exige_consentimiento_y_excluye_sin_whatsapp_y_bloqueados():
    resultados = [
        {"id": "1", "properties": {"wa_estado_envio": None}},               # nunca se le ha escrito: elegible
        {"id": "2", "properties": {"wa_estado_envio": "Entregado"}},        # elegible
        {"id": "3", "properties": {"wa_estado_envio": "Sin WhatsApp"}},     # excluido
        {"id": "4", "properties": {"wa_estado_envio": "Bloqueado"}},        # excluido
    ]
    c, s, _ = cliente(Resp(200, {"results": resultados}))
    assert [r["id"] for r in c.elegibles_para_envio()] == ["1", "2"]
    filtros = s.llamadas[0]["json"]["filterGroups"][0]["filters"]
    assert {"propertyName": "whatsapp_opt_in", "operator": "EQ", "value": "Sí"} in filtros


def test_mensaje_entrante_de_contacto_existente_solo_actualiza_la_ventana():
    c, s, _ = cliente(Resp(200, {"id": "7", "properties": {}}), Resp(200, {}))
    contacto, creado = c.registrar_mensaje_entrante("5215512345678", ahora=AHORA)   # wa_id con el "1" histórico
    assert not creado and contacto["id"] == "7"
    assert s.llamadas[0]["url"].endswith("%2B525512345678")                          # normalizado a +52...
    assert s.llamadas[1]["metodo"] == "PATCH"
    assert s.llamadas[1]["json"] == {"properties": {"wa_ultimo_mensaje_cliente": "2026-10-01T18:00:00Z"}}


def test_mensaje_entrante_de_numero_nuevo_crea_el_contacto_sin_consentimiento():
    c, s, _ = cliente(Resp(404, {}), Resp(201, {"id": "9", "properties": {}}))
    _, creado = c.registrar_mensaje_entrante("525512345678", nombre_perfil=" Marina ", ahora=AHORA)
    props = s.llamadas[1]["json"]["properties"]
    assert creado and props["telefono_e164"] == "+525512345678" and props["firstname"] == "Marina"
    assert props["whatsapp_opt_in"] == "Pendiente" and props["fuentes_datos"] == "Bot WhatsApp"


def test_condicion_de_carrera_al_crear_se_resuelve_con_actualizacion():
    c, s, _ = cliente(Resp(404, {}), Resp(409, {"message": "exists"}), Resp(200, {}), Resp(200, {"id": "5"}))
    contacto, creado = c.registrar_mensaje_entrante("525512345678", ahora=AHORA)
    assert not creado and contacto["id"] == "5"
    assert [l["metodo"] for l in s.llamadas] == ["GET", "POST", "PATCH", "GET"]


def test_baja_y_opt_in_registran_estado_fecha_y_origen():
    c, s, _ = cliente(Resp(200, {}), Resp(200, {}))
    c.registrar_baja("+525512345678", hoy=date(2026, 10, 1))
    c.registrar_opt_in("+525512345678", "Formulario web", hoy=date(2026, 10, 2))
    assert s.llamadas[0]["json"]["properties"] == {"whatsapp_opt_in": "No", "whatsapp_opt_in_fecha": "2026-10-01"}
    assert s.llamadas[1]["json"]["properties"] == {"whatsapp_opt_in": "Sí", "whatsapp_opt_in_fuente": "Formulario web",
                                                  "whatsapp_opt_in_fecha": "2026-10-02"}


def test_registrar_envio_valida_el_estado():
    c, s, _ = cliente(Resp(200, {}))
    c.registrar_envio("+525512345678", "Entregado", plantilla="recordatorio_v1", ahora=AHORA)
    assert s.llamadas[0]["json"]["properties"] == {"wa_ultimo_envio": "2026-10-01T18:00:00Z",
                                                  "wa_estado_envio": "Entregado", "wa_plantilla_ultima": "recordatorio_v1"}
    with pytest.raises(ValueError):
        c.registrar_envio("+525512345678", "inventado")


# --- reglas puras ----------------------------------------------------------------------------
def _contacto(**props):
    return {"properties": props}


def test_ventana_de_24_horas():
    hace = lambda h: (AHORA - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
    assert ventana_24h_abierta(_contacto(wa_ultimo_mensaje_cliente=hace(23)), AHORA)
    assert not ventana_24h_abierta(_contacto(wa_ultimo_mensaje_cliente=hace(25)), AHORA)
    assert not ventana_24h_abierta(_contacto(), AHORA)
    epoch_ms = str(int((AHORA - timedelta(hours=1)).timestamp() * 1000))             # HubSpot también devuelve ms
    assert ventana_24h_abierta(_contacto(wa_ultimo_mensaje_cliente=epoch_ms), AHORA)


@pytest.mark.parametrize("props, esperado", [
    ({"whatsapp_opt_in": "Sí", "calidad_telefono": "Válido"}, True),
    ({"whatsapp_opt_in": "Sí", "calidad_telefono": "Asumido MX"}, True),
    ({"whatsapp_opt_in": "Pendiente", "calidad_telefono": "Válido"}, False),     # sin consentimiento
    ({"whatsapp_opt_in": "No", "calidad_telefono": "Válido"}, False),
    ({"whatsapp_opt_in": "Sí", "calidad_telefono": "Revisar"}, False),
    ({"whatsapp_opt_in": "Sí", "calidad_telefono": "Válido", "wa_estado_envio": "Sin WhatsApp"}, False),
    ({}, False),
])
def test_solo_se_escribe_por_iniciativa_propia_con_consentimiento(props, esperado):
    assert puede_enviar_plantilla(_contacto(**props)) is esperado


def test_saludo_usa_nombre_solo_si_es_confiable():
    assert saludo(_contacto(nombre_saludo="Marina", nombre_confianza="Alta")) == "Hola Marina"
    assert saludo(_contacto(nombre_saludo="Marina", nombre_confianza="Media")) == "Hola Marina"
    assert saludo(_contacto(nombre_saludo="Torres", nombre_confianza="Baja")) == "Hola"
    assert saludo(_contacto(nombre_confianza="Alta"), generico="Buenas tardes") == "Buenas tardes"


@pytest.mark.parametrize("texto, esperado", [
    ("BAJA", True), ("Stop", True), ("  alto!! ", True), ("Cancelar", True), ("no más", True),
    ("Ya no quiero recibir mensajes", True), ("ya no me escriban por favor", True),   # frases libres
    ("quiero dejar de recibir mensajes", True),
    ("hola, quiero reservar", False), ("¿cuánto cuesta la baja temporada?", False),
])
def test_deteccion_de_baja(texto, esperado):
    assert texto_es_baja(texto) is esperado


# --- script de configuración -----------------------------------------------------------------
def test_setup_en_simulacro_no_toca_la_red(capsys, monkeypatch):
    monkeypatch.setattr(hubspot_setup, "HubSpotClient", lambda *a, **k: pytest.fail("no debe crear cliente"))
    assert hubspot_setup.main([]) == 0
    salida = capsys.readouterr().out
    assert "SIMULACRO" in salida and "telefono_e164" in salida and "[valor único]" in salida


def test_setup_es_idempotente_ante_409(capsys, monkeypatch):
    n = 1 + len(H.PROPIEDADES_CONTACTO)
    s = FakeSession(Resp(201, {}), *([Resp(409, {"message": "exists"})] * (n - 1)))
    monkeypatch.setattr(hubspot_setup, "HubSpotClient", lambda: HubSpotClient("t", session=s, dormir=lambda _: None))
    assert hubspot_setup.main(["--apply"]) == 0
    salida = capsys.readouterr().out
    assert "creada" in salida and salida.count("ya existía") == n - 1
    assert s.llamadas[0]["url"].endswith("/crm/v3/properties/contacts/groups")
    assert s.llamadas[1]["json"]["hasUniqueValue"] is True        # telefono_e164 va primero

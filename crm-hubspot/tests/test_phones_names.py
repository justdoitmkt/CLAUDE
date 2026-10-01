"""Pruebas de normalización de teléfonos y nombres. Todos los datos son sintéticos."""
import pytest

from guest_crm.names import ALTA, BAJA, INVALIDA, MEDIA, clave_comparacion, limpiar_nombre
from guest_crm.phones import ASUMIDO_MX, REVISAR, SIN_TELEFONO, VALIDO, normalize_phone, normalize_wa_id


@pytest.mark.parametrize("crudo, e164, calidad", [
    ("+52 55 1234 5678", "+525512345678", VALIDO),
    ("52 33 1234 5678", "+523312345678", VALIDO),            # código de país sin "+"
    ("521 33 1234 5678", "+523312345678", VALIDO),           # "1" histórico de móvil mexicano
    ("+52 1 55 1234 5678", "+525512345678", VALIDO),
    ("55 1234 5678", "+525512345678", ASUMIDO_MX),           # sin código: se asume México
    ("3345 12:28 42", "+523345122842", ASUMIDO_MX),          # Excel convirtió espacios en horas
    ("33: 1234 5678", "+523312345678", ASUMIDO_MX),
    ("722.123 4567", "+527221234567", ASUMIDO_MX),
    ("3345-122842", "+523345122842", ASUMIDO_MX),
    ("+1 (212) 555 0123", "+12125550123", VALIDO),
    ("1 (212) 555 0123", "+12125550123", VALIDO),
    ("(+)51 987 654 321", "+51987654321", VALIDO),
    ("‑\n+1 (212) 555 0123", "+12125550123", VALIDO),         # guion no separable + salto de línea del PDF
])
def test_normaliza_formatos_reales(crudo, e164, calidad):
    r = normalize_phone(crudo)
    assert (r.e164, r.calidad) == (e164, calidad)


@pytest.mark.parametrize("crudo", ["No disponible", "no disponible ", "", None, "N/A", "-"])
def test_sin_telefono(crudo):
    r = normalize_phone(crudo)
    assert r.e164 is None and r.calidad == SIN_TELEFONO


@pytest.mark.parametrize("crudo", ["12345", "55 1234", "+52 12", "0000000000"])
def test_invalidos_no_llegan_como_validos(crudo):
    r = normalize_phone(crudo)
    assert r.e164 is None and r.calidad == REVISAR and r.nota


def test_wa_id_con_521_se_normaliza_para_buscar_en_hubspot():
    assert normalize_wa_id("5215512345678") == "+525512345678"
    assert normalize_wa_id("525512345678") == "+525512345678"
    assert normalize_wa_id("") is None and normalize_wa_id("abc") is None


# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("crudo, nombre, apellidos, saludo, confianza", [
    ("Marina Quintero Lagos", "Marina", "Quintero Lagos", "Marina", ALTA),
    ("ramón peña", "Ramón", "Peña", "Ramón", ALTA),                      # minúsculas
    ("MARCO ANTONIO VALDEZ", "Marco Antonio", "Valdez", "Marco", ALTA),      # nombre compuesto
    ("Buenavista Lagos Alejandra", "Alejandra", "Buenavista Lagos", "Alejandra", MEDIA),  # Apellidos Nombre
    ("Quiroz Mena Juan Carlos", "Juan Carlos", "Quiroz Mena", "Juan", MEDIA),
    ("Ochoa Lagos, Rosa Elena", "Rosa Elena", "Ochoa Lagos", "Rosa", ALTA),
    ("Xiomara del Carmen Aranda", "Xiomara del Carmen", "Aranda", "Xiomara", ALTA),  # compuesto con "del Carmen"
    ("Mateo Andrés Cortez de Jesús", "Mateo Andrés", "Cortez de Jesús", "Mateo", ALTA),
    ("Dra Paola Medina", "Paola", "Medina", "Paola", ALTA),                    # título fuera
    ("Fco Salgado", "Fco", "Salgado", "Francisco", ALTA),                    # abreviatura expandida en el saludo
    ("Ibarra Soto", "Ibarra Soto", "", "", BAJA),                        # sin nombre de pila: no se saluda
    ("Lucas", "Lucas", "", "Lucas", ALTA),
])
def test_nombres(crudo, nombre, apellidos, saludo, confianza):
    n = limpiar_nombre(crudo)
    assert (n.nombre, n.apellidos, n.saludo, n.confianza) == (nombre, apellidos, saludo, confianza)


def test_nunca_saluda_por_apellido_en_orden_apellido_nombre():
    n = limpiar_nombre("Barrera Ponce Marina")
    assert n.saludo == "Marina" and n.saludo not in ("Castillo", "Torres")


@pytest.mark.parametrize("crudo", ["Marzo", "enero", "", None, "x"])
def test_nombre_invalido(crudo):
    assert limpiar_nombre(crudo).confianza == INVALIDA


def test_anotaciones_se_separan_del_nombre():
    n = limpiar_nombre("Mauricio Salgado Pérez (Segunda reserva)")
    assert n.completo == "Mauricio Salgado Pérez" and n.extras == "Segunda reserva"
    n = limpiar_nombre("familia lagos - boda sol")
    assert (n.nombre, n.apellidos, n.saludo, n.es_grupo, n.extras) == ("Familia", "Lagos", "familia Lagos", True, "boda sol")


def test_inicial_suelta_va_al_apellido_en_nombre_apellido_y_al_nombre_en_apellido_nombre():
    assert limpiar_nombre("Anselmo Duarte R").apellidos == "Duarte R"
    assert limpiar_nombre("Orozco Vidal Norma A").nombre == "Norma A"


def test_clave_de_comparacion_ignora_acentos_mayusculas_y_orden():
    assert clave_comparacion("JOSÉ de la Cruz") == clave_comparacion("cruz jose")


@pytest.mark.parametrize("crudo, e164", [
    ("045 33 1234 5678", "+523312345678"),        # prefijo móvil histórico
    ("044 55 1234 5678", "+525512345678"),
    ("01 55 1234 5678", "+525512345678"),         # prefijo de larga distancia nacional
])
def test_prefijos_historicos_de_marcacion_en_mexico(crudo, e164):
    r = normalize_phone(crudo)
    assert (r.e164, r.calidad) == (e164, ASUMIDO_MX)

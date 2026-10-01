"""La guía de HubSpot no puede decir una cosa y el código otra."""
import re
from pathlib import Path

from guest_crm import hubspot_schema as H

GUIA = (Path(__file__).resolve().parent.parent / "docs" / "02-configuracion-hubspot.md").read_text(encoding="utf-8")


def test_la_guia_documenta_todas_las_propiedades_del_esquema():
    faltan = [p["name"] for p in H.PROPIEDADES_CONTACTO if f"`{p['name']}`" not in GUIA]
    assert not faltan, f"propiedades sin documentar en docs/02: {faltan}"


def test_la_guia_anuncia_el_numero_correcto_de_propiedades():
    assert f"Crear las {len(H.PROPIEDADES_CONTACTO)} propiedades" in GUIA
    assert f"{len(H.PROPIEDADES_CONTACTO)} propiedades dentro del grupo" in GUIA


def test_cada_columna_del_csv_esta_en_la_tabla_de_mapeo():
    bloque = GUIA.split("**Mapeo de columnas.**", 1)[1].split("5. **Fechas:**", 1)[0]
    faltan = [c for c in H.COLUMNAS_CSV_CONTACTOS if f"`{c}`" not in bloque]
    assert not faltan, f"columnas del CSV ausentes de la tabla de mapeo: {faltan}"


def test_las_opciones_de_las_listas_estan_en_la_guia():
    for p in H.PROPIEDADES_CONTACTO:
        if p["type"] == "enumeration" and p["name"] not in ("anios_visita",):
            for o in p["options"]:
                assert o["label"] in GUIA, f"opción {o['label']!r} de {p['name']} no aparece en la guía"

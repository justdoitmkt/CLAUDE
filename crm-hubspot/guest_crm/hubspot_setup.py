"""Crea en HubSpot el grupo y las propiedades de contacto del CRM de huéspedes.

Uso:
    export HUBSPOT_TOKEN=...                       # Private App con el alcance crm.schemas.contacts.write
    python -m guest_crm.hubspot_setup              # simulacro: muestra qué haría, no llama a HubSpot
    python -m guest_crm.hubspot_setup --apply      # crea lo que falte (es seguro repetirlo)

Es idempotente: lo que ya existe se deja intacto (HubSpot responde 409). No modifica ni borra
propiedades existentes. Recomendación: usa para esto un token temporal y bórralo al terminar.
"""
from __future__ import annotations

import argparse
import sys

from . import hubspot_schema as H
from .hubspot_api import HubSpotClient, HubSpotError


def asegurar(cliente: HubSpotClient, ruta: str, cuerpo: dict) -> str:
    """Crea el recurso; si ya existe (409) lo deja como está. Devuelve 'creada' o 'ya existía'."""
    try:
        cliente._request("POST", ruta, cuerpo=cuerpo)  # noqa: SLF001 (mismo paquete)
        return "creada"
    except HubSpotError as exc:
        if exc.status == 409:
            return "ya existía"
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="crear de verdad (sin esto solo se muestra el plan)")
    args = ap.parse_args(argv)

    if not args.apply:
        print(f"SIMULACRO. Se crearía el grupo '{H.GRUPO_CONTACTOS['label']}' y {len(H.PROPIEDADES_CONTACTO)} propiedades:")
        for p in H.PROPIEDADES_CONTACTO:
            extra = " [valor único]" if p.get("hasUniqueValue") else ""
            print(f"  - {p['name']:<28} {p['type']}/{p['fieldType']:<9} {p['label']}{extra}")
        print("\nPara crearlas: python -m guest_crm.hubspot_setup --apply")
        return 0

    cliente = HubSpotClient()
    errores = 0
    print(f"grupo {H.GRUPO_CONTACTOS['name']:<28} {asegurar(cliente, '/crm/v3/properties/contacts/groups', H.GRUPO_CONTACTOS)}")
    for p in H.PROPIEDADES_CONTACTO:
        try:
            print(f"propiedad {p['name']:<24} {asegurar(cliente, '/crm/v3/properties/contacts', p)}")
        except HubSpotError as exc:
            errores += 1
            print(f"propiedad {p['name']:<24} ERROR: {exc}")
    print("\nListo." if not errores else f"\nTerminó con {errores} error(es): revisa los alcances del token.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())

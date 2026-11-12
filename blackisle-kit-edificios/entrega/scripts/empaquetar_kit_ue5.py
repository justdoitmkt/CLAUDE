"""empaquetar_kit_ue5.py — ZIPs de descarga del kit UE5 (GitHub limita a 100 MB por archivo: uno común + uno por modelo).

Uso: python3 scripts/empaquetar_kit_ue5.py
Escribe blackisle-kit-edificios/kit_ue5_descargas/BLACKISLE_UE5_comun.zip y BLACKISLE_UE5_<ID>.zip. Todos llevan rutas que
empiezan por kit_ue5/: al descomprimirlos en la misma carpeta queda el kit completo tal como lo espera LEEME_UE5.md.
"""
import json
import os
import zipfile

ENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KIT = os.path.abspath(os.path.join(ENT, "..", "kit_ue5"))
OUT = os.path.abspath(os.path.join(ENT, "..", "kit_ue5_descargas"))
LIMIT = 95 * 2**20


def add_tree(z, root, rel):
    for dp, _, fs in os.walk(os.path.join(root, rel)):
        for f in sorted(fs):
            p = os.path.join(dp, f)
            z.write(p, os.path.join("kit_ue5", os.path.relpath(p, root)))


def main():
    os.makedirs(OUT, exist_ok=True)
    man = json.load(open(os.path.join(KIT, "manifiesto.json")))
    sizes = {}
    f = os.path.join(OUT, "BLACKISLE_UE5_comun.zip")
    with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in ("LEEME_UE5.md", "manifiesto.json", "importar_blackisle.py"):
            z.write(os.path.join(KIT, name), os.path.join("kit_ue5", name))
        add_tree(z, KIT, "comun")
    sizes["comun"] = os.path.getsize(f)
    for bid in man["modelos"]:
        f = os.path.join(OUT, f"BLACKISLE_UE5_{bid}.zip")
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            add_tree(z, KIT, os.path.join("modelos", bid))
        sizes[bid] = os.path.getsize(f)
    for k, v in sizes.items():
        print(f"{k:16s} {v / 2**20:6.1f} MiB", "DEMASIADO GRANDE para GitHub" if v > LIMIT else "")


if __name__ == "__main__":
    main()

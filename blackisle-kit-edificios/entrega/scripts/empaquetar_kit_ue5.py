"""empaquetar_kit_ue5.py — ZIPs de descarga del kit UE5 (GitHub limita a 100 MB por archivo: uno común + uno por modelo).

Uso: python3 scripts/empaquetar_kit_ue5.py
Escribe blackisle-kit-edificios/kit_ue5_descargas/BLACKISLE_UE5_comun.zip y BLACKISLE_UE5_<ID>.zip. Todos llevan rutas que
empiezan por kit_ue5/: al descomprimirlos en la misma carpeta queda el kit completo tal como lo espera LEEME_UE5.md.
Un modelo cuyo ZIP no cabe en 95 MB se reparte por archivos en BLACKISLE_UE5_<ID>.zip, BLACKISLE_UE5_<ID>_parte2.zip, ...
(por tamaño en disco); todas las partes van a la misma carpeta al descomprimir.
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
        for old in os.listdir(OUT):                       # partes viejas de este modelo
            if old.startswith(f"BLACKISLE_UE5_{bid}_parte"):
                os.remove(os.path.join(OUT, old))
        files = []
        for dp, _, fs in os.walk(os.path.join(KIT, "modelos", bid)):
            files += [os.path.join(dp, f) for f in sorted(fs)]
        bins = [files]
        f = os.path.join(OUT, f"BLACKISLE_UE5_{bid}.zip")
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(files):
                z.write(p, os.path.join("kit_ue5", os.path.relpath(p, KIT)))
        if os.path.getsize(f) > LIMIT:                   # no cabe comprimido: reparto voraz por tamaño en disco
            bins, cur, acc = [], [], 0
            for p in sorted(files, key=os.path.getsize, reverse=True):
                n = os.path.getsize(p)
                if cur and acc + n > LIMIT - 2**20:
                    bins.append(cur)
                    cur, acc = [], 0
                cur.append(p)
                acc += n
            bins.append(cur)
        else:
            sizes[bid] = os.path.getsize(f)
            continue
        for k, group in enumerate(bins):
            tag = bid if k == 0 else f"{bid}_parte{k + 1}"
            f = os.path.join(OUT, f"BLACKISLE_UE5_{tag}.zip")
            with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                for p in sorted(group):
                    z.write(p, os.path.join("kit_ue5", os.path.relpath(p, KIT)))
            sizes[tag] = os.path.getsize(f)
    for k, v in sizes.items():
        print(f"{k:16s} {v / 2**20:6.1f} MiB", "DEMASIADO GRANDE para GitHub" if v > LIMIT else "")


if __name__ == "__main__":
    main()

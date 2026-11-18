"""empaquetar_kit_ue5.py — ZIPs de descarga del kit UE5 (GitHub limita a 100 MB por archivo: uno común + uno por modelo).

Uso: python3 scripts/empaquetar_kit_ue5.py [--solo ID1,ID2]
  --solo: rehace solo el común y los modelos indicados (los ZIP de los demás no cambian: no se reescriben en el historial).
Escribe blackisle-kit-edificios/kit_ue5_descargas/BLACKISLE_UE5_comun.zip y BLACKISLE_UE5_<ID>.zip. Todos llevan rutas que
empiezan por kit_ue5/: al descomprimirlos en la misma carpeta queda el kit completo tal como lo espera LEEME_UE5.md.
Un ZIP (común o de modelo) que no cabe en 95 MB se reparte por archivos en BLACKISLE_UE5_<X>.zip, BLACKISLE_UE5_<X>_parte2.zip,
... (por tamaño en disco); todas las partes van a la misma carpeta al descomprimir.
"""
import json
import os
import sys
import zipfile

ENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KIT = os.path.abspath(os.path.join(ENT, "..", "kit_ue5"))
OUT = os.path.abspath(os.path.join(ENT, "..", "kit_ue5_descargas"))
LIMIT = 95 * 2**20


def _files(root, rel):
    out = []
    for dp, _, fs in os.walk(os.path.join(root, rel)):
        out += [os.path.join(dp, f) for f in sorted(fs)]
    return out


def _write(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, os.path.join("kit_ue5", os.path.relpath(p, KIT)))
    return os.path.getsize(path)


def pack(tag, files, head=()):
    """Escribe BLACKISLE_UE5_<tag>.zip; si comprimido no cabe en LIMIT, reparte por tamaño en disco en
    <tag>.zip, <tag>_parte2.zip, ... (los archivos de `head` van siempre en la primera parte). Devuelve {tag: bytes}."""
    for old in os.listdir(OUT):                           # partes viejas de este paquete
        if old.startswith(f"BLACKISLE_UE5_{tag}_parte"):
            os.remove(os.path.join(OUT, old))
    first = os.path.join(OUT, f"BLACKISLE_UE5_{tag}.zip")
    n = _write(first, list(head) + sorted(files))
    if n <= LIMIT:
        return {tag: n}
    bins, cur, acc = [], list(head), sum(os.path.getsize(p) for p in head)
    for p in sorted(files, key=os.path.getsize, reverse=True):   # reparto voraz
        k = os.path.getsize(p)
        if cur and acc + k > LIMIT - 2**20:
            bins.append(cur)
            cur, acc = [], 0
        cur.append(p)
        acc += k
    bins.append(cur)
    sizes = {}
    for i, group in enumerate(bins):
        t = tag if i == 0 else f"{tag}_parte{i + 1}"
        sizes[t] = _write(os.path.join(OUT, f"BLACKISLE_UE5_{t}.zip"), sorted(group))
    return sizes


def main():
    os.makedirs(OUT, exist_ok=True)
    man = json.load(open(os.path.join(KIT, "manifiesto.json")))
    head = [os.path.join(KIT, n) for n in ("LEEME_UE5.md", "manifiesto.json", "importar_blackisle.py")]
    sizes = pack("comun", _files(KIT, "comun"), head)
    solo = sys.argv[sys.argv.index("--solo") + 1].split(",") if "--solo" in sys.argv else None
    for bid in man["modelos"]:
        if solo is not None and bid not in solo:
            continue
        sizes.update(pack(bid, _files(KIT, os.path.join("modelos", bid))))
    for k, v in sizes.items():
        print(f"{k:24s} {v / 2**20:6.1f} MiB", "DEMASIADO GRANDE para GitHub" if v > LIMIT else "")


if __name__ == "__main__":
    main()

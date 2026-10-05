"""Write MODELOS.md: every GLB with size (m), triangles, materials and file weight, from the GLBs themselves."""
import glob, json, os, struct
import numpy as np
WORK = os.environ.get("KIT_WORK", "/home/user/work2")
CAT = [("Modular", "Piezas modulares de la cabaña"), ("Props", "Props"), ("Foliage", "Vegetación"),
       ("Unique", "Piezas únicas del diorama"), ("Utility", "Utilidad"),
       ("Assemblies", "Ensamblajes de Blueprint (pieza + puertas/marcos/contraventanas/tapas como nodos hijos)"),
       ("Cabins", "Cabañas completas (de los niveles del autor)")]


def load(path):
    d = open(path, "rb").read()
    jl = struct.unpack_from("<I", d, 12)[0]
    return json.loads(d[20:20 + jl])


def node_mats(j):
    """world matrices of nodes (glTF column-major)"""
    out = {}
    def mat(n):
        if "matrix" in n: return np.array(n["matrix"]).reshape(4, 4).T
        M = np.eye(4)
        t = n.get("translation", [0, 0, 0]); r = n.get("rotation", [0, 0, 0, 1]); s = n.get("scale", [1, 1, 1])
        x, y, z, w = r
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M[:3, :3] = R @ np.diag(s); M[:3, 3] = t
        return M
    def walk(i, parent):
        W = parent @ mat(j["nodes"][i]); out[i] = W
        for c in j["nodes"][i].get("children", []): walk(c, W)
    for root in j["scenes"][0]["nodes"]: walk(root, np.eye(4))
    return out


def stats(path):
    j = load(path)
    W = node_mats(j)
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf); tris = 0
    for i, n in enumerate(j["nodes"]):
        if "mesh" not in n: continue
        for p in j["meshes"][n["mesh"]]["primitives"]:
            a = j["accessors"][p["attributes"]["POSITION"]]
            corners = np.array([[x, y, z] for x in (a["min"][0], a["max"][0]) for y in (a["min"][1], a["max"][1]) for z in (a["min"][2], a["max"][2])])
            w = corners @ W[i][:3, :3].T + W[i][:3, 3]
            lo = np.minimum(lo, w.min(0)); hi = np.maximum(hi, w.max(0))
            tris += j["accessors"][p["indices"]]["count"] // 3
    mats = sorted({m.get("name", "").split("@")[0] for m in j.get("materials", [])})
    res = sorted({j["images"][t["source"]].get("name", "") for t in j.get("textures", [])})
    return dict(size=hi - lo, tris=tris, mats=mats, nodes=sum(1 for n in j["nodes"] if "mesh" in n),
                mb=os.path.getsize(path) / 1e6)


def main():
    rep = json.load(open(f"{WORK}/build_report.json"))
    lines = ["# Catálogo de modelos", "", "Medidas en metros: ancho (X) × alto (Y) × fondo (Z) en coordenadas glTF. Triángulos y peso, leídos del propio GLB.", ""]
    total = 0; count = 0
    for folder, title in CAT:
        files = sorted(glob.glob(f"{WORK}/glb/{folder}/*.glb"))
        if not files: continue
        lines += [f"## {title} — `glb/{folder}/` ({len(files)})", ""]
        if folder in ("Assemblies", "Cabins"):
            lines += ["| Archivo | Medidas (m) | Piezas | Triángulos | Materiales | Peso | Origen |", "|---|---|---|---|---|---|---|"]
        else:
            lines += ["| Archivo | Medidas (m) | Triángulos | Materiales | Peso |", "|---|---|---|---|---|"]
        for f in files:
            s = stats(f); name = os.path.basename(f); key = f"{folder}/{name[:-4]}"
            dims = " × ".join(f"{v:.2f}" for v in s["size"])
            if folder in ("Assemblies", "Cabins"):
                src = rep.get(key, {}).get("source", "Blueprint `" + name[:-4] + "`")
                lines.append(f"| `{name}` | {dims} | {s['nodes']} | {s['tris']:,} | {len(s['mats'])} | {s['mb']:.1f} MB | {src} |")
            else:
                lines.append(f"| `{name}` | {dims} | {s['tris']:,} | {', '.join(s['mats'])} | {s['mb']:.1f} MB |")
            total += s["mb"]; count += 1
        lines.append("")
    lines.insert(3, f"**{count} archivos, {total / 1000:.2f} GB en total.**\n")
    open(f"{WORK}/MODELOS.md", "w").write("\n".join(lines))
    print(count, round(total / 1000, 2), "GB")


if __name__ == "__main__":
    main()

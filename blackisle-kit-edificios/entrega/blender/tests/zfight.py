"""Detector de z-fighting VISIBLE: caras coplanares superpuestas (mismo sentido, a menos de `tol`) dentro de un objeto o entre
objetos, que en un rasterizador (Three.js) se pelean y dan mosaicos. Para cada cara (área > 1 cm²):
  1) rayo desde 0,5 mm delante de su centro hacia atrás (-normal), en todos los objetos: si golpea OTRA cara casi paralela
     (mismo sentido) a menos de `tol`, hay superposición;
  2) solo cuenta si la cara se ve: desde 3 mm delante, el primer impacto hacia adelante no puede ser la cara trasera de un
     sólido (normal en el mismo sentido que el rayo = el punto está dentro de un volumen: tapa pegada al techo, canto metido
     en otro muro).
Uso: python tests/zfight.py --blend APT_A_5p.blend [--tol 0.0012] [--out informe.json]   |   --id CAB_1_tablones (construye)"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

argv = sys.argv
tol = float(argv[argv.index("--tol") + 1]) if "--tol" in argv else 0.0012
min_area = 1e-4
if "--blend" in argv:
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(argv[argv.index("--blend") + 1]))
    objs = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("_")]
else:
    import builders
    from kit.common import reset_scene
    reset_scene()
    res = builders.build(argv[argv.index("--id") + 1])
    objs = [o for k in builders.KEYS for o in res.get(k, [])]

bms, trees = [], []
for o in objs:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    bm.faces.ensure_lookup_table()
    bms.append(bm)
    trees.append(BVHTree.FromBMesh(bm))


def first_hit(origin, d, dist):
    best = None
    for k, t in enumerate(trees):
        loc, nrm, idx, dd = t.ray_cast(origin, d, dist)
        if idx is not None and (best is None or dd < best[3]):
            best = (k, idx, nrm, dd)
    return best


report = {}
for k, (o, bm) in enumerate(zip(objs, bms)):
    hits, area, other = [], 0.0, {}
    for f in bm.faces:
        a = f.calc_area()
        if a < min_area:
            continue
        n = f.normal
        c = f.calc_center_median()
        twin = None
        for j, t in enumerate(trees):
            for start, dist in ((c + n * 0.0005, tol + 0.0005), (c - n * 0.00002, tol)):
                loc, nrm, idx, dd = t.ray_cast(start, -n, dist)
                if idx is None or (j == k and idx == f.index):
                    continue
                if bms[j].faces[idx].normal.dot(n) > 0.995:
                    twin = j
                    break
            if twin is not None:
                break
        if twin is None:
            continue
        h = first_hit(c + n * 0.003, n, 1.0)
        if h is not None and h[2].dot(n) > 0.0:          # dentro de un sólido: no se ve
            continue
        hits.append((round(c.x, 2), round(c.y, 2), round(c.z, 2)))
        area += a
        other[objs[twin].name] = other.get(objs[twin].name, 0) + 1
    report[o.name] = dict(faces=len(bm.faces), zfight_faces=len(hits), zfight_area_m2=round(area, 3), with_objects=other,
                          sample=hits[:60])
    print(o.name, len(bm.faces), "caras;", len(hits), "visibles en z-fighting;", round(area, 3), "m2;", other, flush=True)
if "--out" in argv:
    json.dump(report, open(argv[argv.index("--out") + 1], "w"), indent=1)

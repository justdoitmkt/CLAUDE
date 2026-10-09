"""test_G1_vanos.py — vitrina y QA del grupo G1 · VANOS (kit/openings.py).

Arma una fachada-vitrina de 2 niveles (muro de 0,20 con `wall_with_openings`): en PB puertas, cortinas enrollables y
celosías; en el nivel 1 ventanas de los 4 tipos y rejas. Imprime por asset triángulos y salud de malla (separando las
láminas intencionales de tela), verifica el contrato (devuelve MB, determinismo por semilla, presupuesto 800–5000 de las
ventanas, door(..., parts=True) reproduce exactamente la puerta combinada) y renderiza las vistas de QA en
entrega/render_qa/kit/G1_*.png. Sale con código 1 si algo falla.

Uso:  cd entrega/blender && /root/blk-venv/bin/python tests/test_G1_vanos.py [--norender] [--only general,ventanas,...]
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402,F401
import bmesh  # noqa: E402
from mathutils import Matrix, Vector, kdtree  # noqa: E402

from kit.common import MB, clay_render, mesh_health, reset_scene, tri_count, wall_with_openings  # noqa: E402
from kit import openings as O  # noqa: E402

OUT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "render_qa", "kit"))
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[1:]
RENDER = "--norender" not in ARGS
ONLY = None
if "--only" in ARGS:
    ONLY = set(ARGS[ARGS.index("--only") + 1].split(","))

PB_H, SLAB, DEPTH = 3.2, 0.2, 0.2
Z1 = PB_H + SLAB          # piso terminado del nivel 1
SILL_H = 0.9              # antepecho
PIER = 0.7                # machón entre vanos


def lamina_split(ob):
    """(aristas no-manifold en sólidos, aristas abiertas de láminas intencionales)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    mats = [m.name for m in ob.data.materials]
    solid = lam = 0
    for e in bm.edges:
        if e.is_manifold:
            continue
        if e.link_faces and all(mats[f.material_index] in O.LAMINA_MATS for f in e.link_faces):
            lam += 1
        else:
            solid += 1
    bm.free()
    return solid, lam


# ---------------------------------------------------------------------------------------------------------------------
# catálogo de la vitrina: (nombre, constructor, w, h)
# ---------------------------------------------------------------------------------------------------------------------
PB = [
    ("door_flush_s0", lambda: O.door("flush", 0.9, 2.05, seed=0, open_angle=32), 0.9, 2.05),
    ("door_flush_s1", lambda: O.door("flush", 0.9, 2.05, seed=1, open_angle=0), 0.9, 2.05),
    ("door_double_glazed_s0", lambda: O.door("double_glazed", 1.6, 2.45, seed=0, open_angle=38), 1.6, 2.45),
    ("door_double_glazed_s1", lambda: O.door("double_glazed", 1.8, 2.3, seed=1, open_angle=12), 1.8, 2.3),
    ("rolling_shutter_s0", lambda: O.rolling_shutter(2.6, 2.6, seed=0, dent=0.7, open_frac=0.0), 2.6, 2.6),
    ("rolling_shutter_s1", lambda: O.rolling_shutter(2.4, 2.6, seed=1, dent=0.4, open_frac=0.45), 2.4, 2.6),
    ("rolling_shutter_s2", lambda: O.rolling_shutter(2.6, 2.6, seed=2, dent=1.0, open_frac=0.0), 2.6, 2.6),
    ("door_plank_s0", lambda: O.door("plank", 0.9, 2.0, seed=0, open_angle=48), 0.9, 2.0),
    ("door_plank_s1", lambda: O.door("plank", 0.85, 1.95, seed=1, open_angle=0), 0.85, 1.95),
    ("door_metal_s0", lambda: O.door("metal", 0.95, 2.1, seed=0, open_angle=22), 0.95, 2.1),
    ("door_metal_s1", lambda: O.door("metal", 0.9, 2.05, seed=1, open_angle=65), 0.9, 2.05),
    ("breeze_block_4sq_s0", lambda: O.breeze_block_screen(1.9, 2.6, seed=0, missing=0.05), 1.9, 2.6),
    ("breeze_block_cross_s1", lambda: O.breeze_block_screen(1.9, 2.6, seed=1, missing=0.08, pattern="cross"), 1.9, 2.6),
    ("breeze_block_nine_s2", lambda: O.breeze_block_screen(1.48, 2.6, seed=2, missing=0.04, pattern="nine"), 1.48, 2.6),
]
L1 = [
    ("window_sliding_s0", lambda: O.window("sliding", 1.5, 1.2, seed=0, broken=0.6), 1.5, 1.2),
    ("window_sliding_s1", lambda: O.window("sliding", 1.8, 1.5, seed=1, broken=0.85), 1.8, 1.5),
    ("window_casement_s2", lambda: O.window("casement", 1.4, 1.5, seed=2, broken=0.5), 1.4, 1.5),
    ("window_casement_s3", lambda: O.window("casement", 1.2, 1.2, seed=3, broken=0.8, curtain=False), 1.2, 1.2),
    ("window_shutter_s0", lambda: O.window("shutter", 1.2, 1.3, seed=0, broken=0.6), 1.2, 1.3),
    ("window_shutter_s5", lambda: O.window("shutter", 1.0, 1.2, seed=5, broken=0.4), 1.0, 1.2),
    ("window_boarded_s3", lambda: O.window("boarded", 1.5, 1.2, seed=3, broken=0.8), 1.5, 1.2),
    ("window_boarded_s4", lambda: O.window("boarded", 1.2, 1.4, seed=4, broken=0.9, curtain=False), 1.2, 1.4),
    ("grille_s0+window_sliding_s7", lambda: _combo(1.4, 1.2, 0, 7), 1.4, 1.2),
    ("security_grille_s1", lambda: O.security_grille(1.2, 1.2, seed=1), 1.2, 1.2),
]


def _combo(w, h, sg, sw):
    mb = O.window("sliding", w, h, seed=sw, broken=0.7)
    mb.join(O.security_grille(w, h, seed=sg))
    return mb


def layout(items, x0=PIER):
    xs, x = [], x0
    for it in items:
        xs.append(x)
        x += it[2] + PIER
    return xs, x


# ---------------------------------------------------------------------------------------------------------------------
reset_scene()
xs_pb, Lpb = layout(PB)
xs_l1, Ll1 = layout(L1)
L = max(Lpb, Ll1)
openings = [(x, x + w, 0.0, h) for x, (_, _, w, h) in zip(xs_pb, PB)]
openings += [(x, x + w, Z1 + SILL_H, Z1 + SILL_H + h) for x, (_, _, w, h) in zip(xs_l1, L1)]
props = MB()
wall_with_openings(props, L, Z1 + 2.9, DEPTH, openings, mat_out="concrete", mat_in="plaster")
props.box((-2.0, -4.0, -0.3), (L + 2.0, 4.0, 0.0), "concrete")                       # suelo
props.box((0.0, DEPTH + 0.001, PB_H), (L, DEPTH + 2.2, Z1), "concrete")               # losa del nivel 1 (interior)
wall = props.finish("_vitrina_muros")
pm = MB()
pm.box((-0.225, -0.125, 0.0), (0.225, 0.125, 1.8), "plastic")
person = pm.finish("_persona_1.80")
person.location = (xs_pb[4] - 0.35, -0.9, 0.0)   # en el machón junto a la cortina metálica s0: escala humana en la vista general

assets = {}
report = []
t_all = time.time()
for (items, xs, z) in ((PB, xs_pb, 0.0), (L1, xs_l1, Z1 + SILL_H)):
    for (name, fn, w, h), x in zip(items, xs):
        t = time.time()
        mb = fn()
        ob = mb.finish("G1_" + name)
        ob.location = (x, 0.0, z)
        assets[name] = ob
        s, lam = lamina_split(ob)
        tc = tri_count([ob])
        hl = mesh_health(ob)
        report.append((name, tc, hl, s, lam, time.time() - t))
bpy.context.view_layer.update()

print("\n=== G1 · VANOS — triángulos y salud de malla ===")
print(f"{'asset':34s} {'tris':>7s}  nm_sólidos  bordes_lámina(tela)  área0  sueltos   t")
fails = 0
for name, tc, hl, s, lam, dt in report:
    flag = "" if (s == 0 and hl["zero_area_faces"] == 0 and hl["loose_verts"] == 0) else "  <-- REVISAR"
    fails += bool(flag)
    print(f"{name:34s} {tc:7d}  {s:10d}  {lam:19d}  {hl['zero_area_faces']:5d}  {hl['loose_verts']:7d}  {dt:5.2f}s{flag}")
    print(f"    mesh_health={hl}")
print(f"total vitrina: {sum(r[1] for r in report)} tris · {len(report)} assets · {time.time() - t_all:.1f}s · fallas={fails}")


# ---------------------------------------------------------------------------------------------------------------------
# verificaciones de contrato: tipo MB, determinismo, presupuesto de ventanas, hojas de puerta separables
# ---------------------------------------------------------------------------------------------------------------------
def _tris(mb):
    return sum(len(f.verts) - 2 for f in mb.bm.faces)


print("\n=== verificaciones de contrato ===")
cfail = 0
for (name, fn, w, h) in PB + L1:
    a, b = fn(), fn()
    ok = isinstance(a, MB) and _tris(a) == _tris(b) and len(a.bm.verts) == len(b.bm.verts)
    if not ok:
        cfail += 1
        print(f"  DETERMINISMO/TIPO FALLA: {name}")
    a.bm.free()
    b.bm.free()
for name, tc, *_ in report:
    if name.startswith("window_") and not (800 <= tc <= 5000):
        cfail += 1
        print(f"  PRESUPUESTO FALLA: {name} = {tc} tris (800–5000)")
for kind, w, h, ang in (("flush", 0.9, 2.05, 32), ("double_glazed", 1.6, 2.45, 38), ("plank", 0.9, 2.0, 48), ("metal", 0.9, 2.05, 65)):
    P = O.door(kind, w, h, seed=0, open_angle=ang, parts=True)
    comb = O.door(kind, w, h, seed=0, open_angle=ang)
    re_ = MB()
    re_.join(P["frame"])
    for lf_ in P["leaves"]:
        piv = Vector(lf_["pivot"])
        re_.join(lf_["mb"], Matrix.Translation(piv) @ Matrix.Rotation(math.radians(lf_["angle"]), 4, Vector(lf_["axis"]))
                 @ Matrix.Translation(-piv))
    kd = kdtree.KDTree(len(re_.bm.verts))
    for i, v in enumerate(re_.bm.verts):
        kd.insert(v.co, i)
    kd.balance()
    ok = len(comb.bm.verts) == len(re_.bm.verts) and all(kd.find(v.co)[2] < 2e-5 for v in comb.bm.verts)
    cfail += not ok
    print(f"  door('{kind}', parts=True): {len(P['leaves'])} hoja(s), ángulos aplicados "
          f"{[round(q['angle'], 1) for q in P['leaves']]} -> reproduce el MB combinado: {'OK' if ok else 'FALLA'}")
print(f"verificaciones: {'OK' if cfail == 0 else f'{cfail} FALLAS'}")
EXIT = 1 if (fails or cfail) else 0


# ---------------------------------------------------------------------------------------------------------------------
def shot(tag, objs, **kw):
    if not RENDER or (ONLY and tag not in ONLY):
        return
    out = os.path.join(OUT, f"G1_{tag}.png")
    t = time.time()
    clay_render(objs, out, res=(1280, 720), samples=kw.pop("samples", 28), **kw)
    print(f"render {out}  ({time.time() - t:.0f}s)")


def center(names, dz=0.0):
    obs = [assets[n] for n in names]
    pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
    return Vector(((min(p.x for p in pts) + max(p.x for p in pts)) / 2, 0.0, (min(p.z for p in pts) + max(p.z for p in pts)) / 2 + dz))


allobs = list(assets.values()) + [wall, person]
# 1) general con persona
shot("general", allobs, azim=-18, elev=9, fov=40, margin=0.86, sun_azim=-62, sun_elev=26)
# 2) primer plano a ~2 m: ventanas (nivel 1)
shot("ventanas_cerca", [assets["window_sliding_s0"]], target=center(["window_sliding_s0", "window_casement_s2"]) + Vector((0.2, 0, 0.1)),
     dist=3.4, azim=8, elev=4, fov=55, sun_azim=-80, sun_elev=18)
shot("ventanas_cerca2", [assets["window_shutter_s0"]], target=center(["window_shutter_s0", "window_boarded_s3"]) + Vector((0, 0, 0.0)),
     dist=3.6, azim=-10, elev=3, fov=55, sun_azim=78, sun_elev=18)
shot("ventana_corrediza_2m", [assets["window_sliding_s1"]], target=center(["window_sliding_s1"]), dist=2.0, azim=24, elev=6, fov=60,
     sun_azim=-78, sun_elev=20)
# 3) puertas
shot("puertas_cerca", [assets["door_flush_s0"]], target=center(["door_flush_s0", "door_double_glazed_s0"]) + Vector((0.3, 0, 0)),
     dist=4.2, azim=22, elev=6, fov=50, sun_azim=-78, sun_elev=20)
shot("puertas_cerca2", [assets["door_plank_s0"]], target=center(["door_plank_s0", "door_metal_s0"]) + Vector((0.6, 0, 0)),
     dist=4.6, azim=-25, elev=6, fov=50, sun_azim=78, sun_elev=20)
# 4) cortinas enrollables y celosías
shot("cortinas_metalicas", [assets["rolling_shutter_s0"]], target=center(["rolling_shutter_s0", "rolling_shutter_s1"]) + Vector((0, 0, 0)),
     dist=6.0, azim=-22, elev=8, fov=50, sun_azim=-82, sun_elev=16)
shot("celosia_cerca", [assets["breeze_block_4sq_s0"]], target=center(["breeze_block_4sq_s0"]) + Vector((0.4, 0, -0.2)),
     dist=2.2, azim=-28, elev=6, fov=55, sun_azim=-75, sun_elev=28)
shot("celosias", [assets["breeze_block_cross_s1"]], target=center(["breeze_block_4sq_s0", "breeze_block_nine_s2"]),
     dist=6.0, azim=18, elev=5, fov=50, sun_azim=72, sun_elev=24)
# 5) oblicua a lo largo de la fachada y vista interior (cortinas, hojas abiertas hacia adentro)
shot("oblicua", allobs, target=Vector((L * 0.35, 0, 2.6)), dist=13.0, azim=-58, elev=12, fov=50, sun_azim=-70, sun_elev=24)
shot("interior", [assets["window_sliding_s0"]], target=center(["window_sliding_s0", "window_casement_s3"]) + Vector((0, DEPTH, 0)),
     dist=4.5, azim=196, elev=6, fov=55, sun_azim=160, sun_elev=25)
shot("rejas", [assets["security_grille_s1"]], target=center(["grille_s0+window_sliding_s7", "security_grille_s1"]),
     dist=3.8, azim=-14, elev=4, fov=55, sun_azim=-78, sun_elev=20)
sys.exit(EXIT)

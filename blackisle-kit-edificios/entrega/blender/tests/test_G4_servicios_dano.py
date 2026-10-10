"""test_G4_servicios_dano.py — vitrina y QA del grupo G4 · SERVICIOS, PROPS Y DAÑO (kit/services.py, kit/damage.py).

Arma un muro-vitrina de 19,6 m × 5,5 m (con `wall_with_openings`: huecos para los A/C de ventana y ventanas con
cortinas) con todos los props de muro, a la derecha una "azotea" con tinacos y antenas, tendederos entre columnas y,
al frente, la zona de daño (varillas, escombro, trozos, mordidas de arista en losa y columna). 2–3 variantes por semilla.
Imprime por asset triángulos y salud de malla (separando las láminas intencionales de tela) y renderiza las vistas de
QA en entrega/render_qa/kit/G4_*.png (1280 × 720, 28 muestras).
NIVELES DE DETALLE: cada asset se construye además con detail='mid' y 'low' (tabla de triángulos y salud por nivel, con
los presupuestos del A/C: mid <= 9 k, low <= 4 k) y hay una vitrina LOD (muro con los 3 A/C × 3 niveles y la zona de daño
× 3 niveles) con sus renders G4_lod_*.png.

Uso:  cd entrega/blender && /root/blk-venv/bin/python tests/test_G4_servicios_dano.py [--norender] [--only general,ac,...]
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402,F401
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from kit.common import MB, clay_render, mesh_health, reset_scene, tri_count, wall_with_openings  # noqa: E402
from kit import services as S  # noqa: E402
from kit import damage as D  # noqa: E402

OUT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "render_qa", "kit"))
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[1:]
RENDER = "--norender" not in ARGS
ONLY = None
if "--only" in ARGS:
    ONLY = set(ARGS[ARGS.index("--only") + 1].split(","))


def T(x, y, z):
    return Matrix.Translation((x, y, z))


def lamina_split(ob):
    """(aristas no-manifold en sólidos, aristas abiertas de láminas intencionales 'fabric')."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    mats = [m.name for m in ob.data.materials]
    solid = lam = 0
    for e in bm.edges:
        if e.is_manifold:
            continue
        if e.link_faces and all(mats[f.material_index] in S.LAMINA_MATS for f in e.link_faces):
            lam += 1
        else:
            solid += 1
    bm.free()
    return solid, lam


def spalled(mn, mx, spalls, **kw):
    mb = MB()
    D.spalled_box(mb, mn, mx, spalls, **kw)
    return mb


# ---------------------------------------------------------------------------------------------------------------------
# catálogo: (nombre, constructor, (x, y, z) de colocación, grupo)
# ---------------------------------------------------------------------------------------------------------------------
WIN_AC = [(1.0, 2.3), (2.2, 2.3)]
OLD_AC = [(6.2, 2.15), (7.4, 2.15)]
CURT = [(14.6, 1.0, 1.4, 1.5), (16.6, 0.9, 1.8, 2.0)]
CATALOG = [
    ("ac_window_s0", lambda d="high": S.ac_unit("window", 0, detail=d), (WIN_AC[0][0], 0, WIN_AC[0][1]), "ac"),
    ("ac_window_s1", lambda d="high": S.ac_unit("window", 1, detail=d), (WIN_AC[1][0], 0, WIN_AC[1][1]), "ac"),
    ("ac_split_s0", lambda d="high": S.ac_unit("split_outdoor", 0, detail=d), (3.6, 0, 2.5), "ac"),
    ("ac_split_s1", lambda d="high": S.ac_unit("split_outdoor", 1, detail=d), (4.9, 0, 2.5), "ac"),
    ("ac_box_old_s0", lambda d="high": S.ac_unit("box_old", 0, detail=d), (OLD_AC[0][0], 0, OLD_AC[0][1]), "ac"),
    ("ac_box_old_s1", lambda d="high": S.ac_unit("box_old", 1, detail=d), (OLD_AC[1][0], 0, OLD_AC[1][1]), "ac"),
    ("meter_box_s0_open", lambda d="high": S.meter_box(0, open_door=True, detail=d), (8.7, 0, 1.2), "serv"),
    ("meter_box_s1_closed", lambda d="high": S.meter_box(1, open_door=False, detail=d), (9.7, 0, 1.2), "serv"),
    ("light_wall_s0", lambda d="high": S.light_fixture("wall", 0, detail=d), (8.7, 0, 2.6), "serv"),
    ("light_wall_s1", lambda d="high": S.light_fixture("wall", 1, detail=d), (9.7, 0, 2.6), "serv"),
    ("light_bracket_s0", lambda d="high": S.light_fixture("bracket", 0, detail=d), (11.0, 0, 2.75), "serv"),
    ("light_bracket_s1", lambda d="high": S.light_fixture("bracket", 1, detail=d), (12.0, 0, 2.75), "serv"),
    ("mailboxes_n8_s0", lambda d="high": S.mailboxes(8, 0, detail=d), (11.0, 0, 0.9), "serv"),
    ("mailboxes_n6_s1", lambda d="high": S.mailboxes(6, 1, detail=d), (11.9, 0, 0.9), "serv"),
    ("extinguisher_s0", lambda d="high": S.extinguisher_cabinet(0, detail=d), (13.0, 0, 1.0), "serv"),
    ("extinguisher_s1", lambda d="high": S.extinguisher_cabinet(1, detail=d), (13.6, 0, 1.0), "serv"),
    ("sign_torn_2.4x0.6_s0", lambda d="high": S.sign_torn(2.4, 0.6, 0, detail=d), (11.4, 0, 3.2), "cab"),
    ("sign_torn_1.8x0.5_s1", lambda d="high": S.sign_torn(1.8, 0.5, 1, detail=d), (9.0, 0, 3.3), "cab"),
    ("satellite_dish_s0", lambda d="high": S.satellite_dish(0, detail=d), (15.3, 0, 3.55), "cab"),
    ("satellite_dish_s1", lambda d="high": S.satellite_dish(1, detail=d), (17.5, 0, 3.65), "cab"),
    ("conduit_s0", lambda d="high": S.conduit([(13.95, 0.35), (13.95, 2.2), (12.55, 2.2), (12.55, 2.6)], 0, detail=d), (0, 0, 0), "serv"),
    ("conduit_s1", lambda d="high": S.conduit([(19.0, 0.3), (19.0, 3.15), (14.3, 3.15), (14.3, 2.7)], 1, detail=d), (0, 0, 0), "cab"),
    ("cable_bundle_n4_s0", lambda d="high": S.cable_bundle([(0.6, 0, 4.7), (5.5, 0, 4.95), (10.4, 0, 4.65)], n=4, sag=0.35, seed=0, detail=d), (0, 0, 0), "cab"),
    ("cable_bundle_n3_s1", lambda d="high": S.cable_bundle([(11.6, 0, 4.85), (15.2, 0, 4.55), (19.1, 0, 4.85)], n=3, sag=0.25, seed=1, detail=d), (0, 0, 0), "cab"),
    ("curtain_torn_1.4x1.5_s0", lambda d="high": S.curtain_torn(1.4, 1.5, 0, detail=d), (CURT[0][0], 0.13, CURT[0][1]), "cab"),
    ("curtain_torn_1.8x2.0_s1", lambda d="high": S.curtain_torn(1.8, 2.0, 1, detail=d), (CURT[1][0], 0.13, CURT[1][1]), "cab"),
    ("water_tank_s0", lambda d="high": S.water_tank(0, detail=d), (21.8, -1.4, 0), "roof"),
    ("water_tank_s1", lambda d="high": S.water_tank(1, detail=d), (24.0, -1.4, 0), "roof"),
    ("tv_antenna_s0", lambda d="high": S.tv_antenna(0, detail=d), (27.0, -1.4, 0), "roof"),
    ("tv_antenna_s1", lambda d="high": S.tv_antenna(1, detail=d), (30.0, -1.6, 0), "roof"),
    ("laundry_line_2.9_s0", lambda d="high": S.laundry_line(2.9, 0, detail=d), (21.15, -3.6, 1.95), "roof"),
    ("laundry_line_2.4_s1", lambda d="high": S.laundry_line(2.4, 1, detail=d), (24.35, -3.6, 1.95), "roof"),
    ("rebar_nest_s0", lambda d="high": D.rebar_nest(0, n=8, length=0.6, detail=d), (21.4, -6.4, 0), "dmg"),
    ("rebar_nest_s1", lambda d="high": D.rebar_nest(1, n=8, length=0.8, detail=d), (22.5, -6.6, 0), "dmg"),
    ("rebar_nest_s2_n4", lambda d="high": D.rebar_nest(2, n=4, length=0.5, stump=(0.25, 0.25, 0.3), detail=d), (23.4, -6.3, 0), "dmg"),
    ("rubble_pile_r1.0_s0", lambda d="high": D.rubble_pile(1.0, 0, 60, detail=d), (25.3, -7.0, 0), "dmg"),
    ("rubble_pile_r1.6_s1", lambda d="high": D.rubble_pile(1.6, 1, 90, detail=d), (28.6, -7.4, 0), "dmg"),
    ("chunk_0.45_s0", lambda d="high": D.chunk(0.45, 0, detail=d), (21.2, -8.0, 0), "dmg"),
    ("chunk_slab_0.6_s1", lambda d="high": D.chunk(0.6, 1, "slab", detail=d), (22.0, -8.1, 0), "dmg"),
    ("chunk_0.25_s2", lambda d="high": D.chunk(0.25, 2, detail=d), (22.8, -7.9, 0), "dmg"),
    ("chunk_0.15_s3", lambda d="high": D.chunk(0.15, 3, detail=d), (23.2, -8.1, 0), "dmg"),
    ("spall_edge_1.2x0.12_s0", lambda d="high": D.spall_edge(1.2, 0.12, 0, detail=d), (23.8, -8.2, 0.12), "dmg"),
    ("spalled_slab_s3", lambda d="high": spalled((21.0, -10.6, 1.0), (24.6, -9.4, 1.2),
                                          [dict(axis="x", sides=(-1, -1), start=0.5, length=1.4, depth=0.12, seed=3),
                                           dict(axis="x", sides=(-1, 1), start=2.2, length=0.9, depth=0.09, seed=4)], detail=d),
     (0, 0, 0), "dmg"),
    ("spalled_column_s5", lambda d="high": spalled((25.6, -10.2, 0.0), (25.95, -9.85, 2.6),
                                            [dict(axis="z", sides=(-1, -1), start=0.4, length=1.1, depth=0.1, seed=5),
                                             dict(axis="z", sides=(1, -1), start=1.3, length=0.8, depth=0.08, seed=6)], bevel=0.02, detail=d),
     (0, 0, 0), "dmg"),
]


# ---------------------------------------------------------------------------------------------------------------------
reset_scene()
t_all = time.time()
assets, report = {}, []
for name, fn, (x, y, z), grp in CATALOG:
    t = time.time()
    mb = fn()
    ob = mb.finish("G4_" + name)
    ob.location = (x, y, z)
    assets[name] = (ob, grp)
    s_nm, lam = lamina_split(ob)
    report.append((name, tri_count([ob]), mesh_health(ob), s_nm, lam, time.time() - t))


def measure(mb, name):
    """Triángulos y salud de un MB (objeto temporal que se borra)."""
    ob = mb.finish(name)
    bpy.context.view_layer.update()
    r = (tri_count([ob]), mesh_health(ob), lamina_split(ob))
    me = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return r


# niveles de detalle: cada asset del catálogo en 'mid' y 'low'
lod_report = {}
for name, fn, _, _ in CATALOG:
    lod_report[name] = {lv: measure(fn(lv), f"_lod_{lv}_{name}") for lv in ("mid", "low")}

# vitrina LOD (x >= 33): muro con los 3 tipos de A/C × (high, mid, low) y zona de daño × 3 niveles
LOD_X0 = 33.0
LOD_AC = [("window", 0.606, 0.406), ("split_outdoor", None, None), ("box_old", 0.666, 0.446)]
LEVELS = ("high", "mid", "low")
lod_objs, lod_open = [], []
for ki, (kind, ow, oh) in enumerate(LOD_AC):
    for li, lv in enumerate(LEVELS):
        x, z = LOD_X0 + 1.0 + li * 1.3, 1.2 + (2 - ki) * 1.1
        ob = S.ac_unit(kind, 0, detail=lv).finish(f"G4_lod_ac_{kind}_{lv}")
        ob.location = (x, 0, z)
        lod_objs.append(ob)
        if ow:
            lod_open.append((x - LOD_X0 - ow / 2, x - LOD_X0 + ow / 2, z - 0.003, z + oh - 0.003))
lod_dmg = []
for li, lv in enumerate(LEVELS):
    x0 = LOD_X0 + 0.6 + li * 2.0
    for (nm_, mb_, (dx, dy)) in (("rebar", D.rebar_nest(0, n=8, length=0.6, detail=lv), (0.0, 0.0)),
                                 ("rubble", D.rubble_pile(0.7, 0, 40, detail=lv), (0.9, -0.6)),
                                 ("chunk", D.chunk(0.45, 0, detail=lv), (-0.1, -1.0)),
                                 ("spall", D.spall_edge(1.2, 0.12, 0, detail=lv), (-0.4, -1.6))):
        ob = mb_.finish(f"G4_lod_{nm_}_{lv}")
        ob.location = (x0 + dx, -3.0 + dy, 0.12 if nm_ == "spall" else 0.0)
        lod_dmg.append(ob)

# contexto (no se cuenta): muro con vanos, piso, columnas del tendedero, apoyos de la losa, personas de 1,80 m
openings = [(x - 0.303, x + 0.303, z - 0.003, z + 0.403) for (x, z) in WIN_AC]
openings += [(x - 0.333, x + 0.333, z - 0.003, z + 0.443) for (x, z) in OLD_AC]
openings += [(u, u + w, v, v + h) for (u, v, w, h) in CURT]
ctx = MB()
wall_with_openings(ctx, 19.6, 5.5, 0.2, openings, mat_out="concrete", mat_in="plaster")
ctx.box((-60.0, -70.0, -0.2), (90.0, 40.0, 0.0), "concrete")
for cx in (21.0, 24.2, 26.9):
    ctx.box((cx - 0.15, -3.75, 0.0005), (cx + 0.15, -3.45, 2.4), "concrete", bevel=0.01)
for cx in (21.4, 24.2):
    ctx.box((cx - 0.15, -10.3, 0.0005), (cx + 0.15, -9.9, 0.999), "concrete", bevel=0.01)
wall_with_openings(ctx, 4.6, 4.3, 0.2, lod_open, mat_out="concrete", mat_in="plaster", m=T(LOD_X0, 0, 0))
for li in range(3):  # apoyo de las mordidas sueltas (spall_edge) de la vitrina LOD
    xs = LOD_X0 + 0.2 + li * 2.0
    ctx.box((xs, -4.6 + 0.001, 0.0005), (xs + 1.2, -4.6 + 0.4, 0.119), "concrete")
ctx_ob = ctx.finish("_vitrina_contexto")
people = []
for (px, py) in ((2.9, -1.3), (23.9, -5.2), (14.0, -1.5)):
    pm = MB()
    pm.box((-0.225, -0.125, 0.0005), (0.225, 0.125, 1.8), "plastic")
    p = pm.finish("_persona_1.80")
    p.location = (px, py, 0.0)
    people.append(p)
bpy.context.view_layer.update()

print("\n=== G4 · SERVICIOS, PROPS Y DAÑO — triángulos y salud de malla ===")
print(f"{'asset':30s} {'tris':>7s}  nm_sólidos  bordes_lámina(tela)  área0  sueltos     t")
fails = 0
for name, tc, hl, s_nm, lam, dt in report:
    flag = "" if (s_nm == 0 and hl["zero_area_faces"] == 0 and hl["loose_verts"] == 0) else "  <-- REVISAR"
    fails += bool(flag)
    print(f"{name:30s} {tc:7d}  {s_nm:10d}  {lam:19d}  {hl['zero_area_faces']:5d}  {hl['loose_verts']:7d}  {dt:5.2f}s{flag}")
    print(f"    mesh_health={hl}")
print(f"total vitrina G4: {sum(r[1] for r in report)} tris · {len(report)} assets · {time.time() - t_all:.1f}s · fallas={fails}")

print("\n=== NIVELES DE DETALLE (detail='high' | 'mid' | 'low') — triángulos y salud por nivel ===")
print(f"{'asset':30s} {'high':>7s} {'mid':>7s} {'low':>7s}   mid/high  low/high   salud mid / low (nm_sólidos, área0, sueltos)")
lod_fails = 0
for name, tc, hl, s_nm, lam, dt in report:
    m, lo = lod_report[name]["mid"], lod_report[name]["low"]
    bad = [lv for lv, (t_, h_, (snm_, _)) in (("mid", m), ("low", lo)) if snm_ or h_["zero_area_faces"] or h_["loose_verts"]]
    budget = ""
    if name.startswith("ac_"):
        if m[0] > 9000 or lo[0] > 4000:
            bad.append("presupuesto A/C")
        budget = "  (A/C: mid <= 9 k, low <= 4 k)"
    lod_fails += bool(bad)
    hs = " / ".join(f"({r_[2][0]}, {r_[1]['zero_area_faces']}, {r_[1]['loose_verts']})" for r_ in (m, lo))
    print(f"{name:30s} {tc:7d} {m[0]:7d} {lo[0]:7d}   {m[0] / tc:7.0%}  {lo[0] / tc:7.0%}   {hs}{budget}"
          + (f"  <-- REVISAR {bad}" if bad else ""))
print(f"total por nivel: high {sum(r[1] for r in report)} · mid {sum(v['mid'][0] for v in lod_report.values())} · "
      f"low {sum(v['low'][0] for v in lod_report.values())} · fallas LOD={lod_fails}")


# ---------------------------------------------------------------------------------------------------------------------
def shot(tag, objs, **kw):
    if not RENDER or (ONLY and tag not in ONLY):
        return
    out = os.path.join(OUT, f"G4_{tag}.png")
    t = time.time()
    clay_render(objs, out, res=(1280, 720), samples=kw.pop("samples", 28), **kw)
    print(f"render {out}  {time.time() - t:.1f}s")


def grp(*gs):
    return [ob for (ob, g) in assets.values() if g in gs]


ALL = [ob for (ob, _) in assets.values()]
LOD_ALL = lod_objs + lod_dmg
shot("general", ALL + people, azim=22, elev=20, margin=0.92)
shot("oblicua", ALL + people, azim=58, elev=28, margin=1.02)
shot("ac_cerca", grp("ac"), target=Vector((3.0, -0.35, 2.45)), dist=2.3, azim=24, elev=6, fov=50)
shot("ac_bajo", grp("ac"), target=Vector((6.6, -0.3, 2.2)), dist=2.4, azim=-28, elev=-14, fov=50)
shot("servicios_cerca", grp("serv"), target=Vector((10.4, -0.35, 1.85)), dist=2.9, azim=18, elev=8, fov=55)
shot("cables_letrero", grp("cab"), target=Vector((8.2, -0.3, 4.1)), dist=3.6, azim=-15, elev=-6, fov=55)
shot("ventanas_parabolicas", grp("cab"), target=Vector((16.5, -0.3, 2.6)), dist=4.4, azim=20, elev=4, fov=55)
shot("azotea", grp("roof"), target=Vector((25.8, -1.5, 1.1)), dist=6.0, azim=24, elev=30, fov=50)
shot("tendedero", grp("roof"), target=Vector((22.7, -3.6, 1.5)), dist=2.9, azim=-6, elev=3, fov=60)
shot("dano_cerca", grp("dmg"), target=Vector((22.4, -6.9, 0.45)), dist=2.1, azim=18, elev=22, fov=55)
shot("escombro", grp("dmg"), target=Vector((26.6, -7.4, 0.35)), dist=4.6, azim=30, elev=26, fov=50)
shot("mordida_losa", grp("dmg"), target=Vector((21.9, -10.6, 1.02)), dist=1.7, azim=28, elev=-9, fov=55)
shot("mordida_columna", grp("dmg"), target=Vector((25.93, -10.18, 1.7)), dist=1.3, azim=38, elev=6, fov=55)
# primeros planos a 1,6 m de cada A/C en 'high' y vitrina LOD (columnas: high, mid, low)
for kind, ki in (("window", 0), ("split_outdoor", 1), ("box_old", 2)):
    zc = 1.2 + (2 - ki) * 1.1
    shot(f"ac_{kind}_1m6", lod_objs, target=Vector((LOD_X0 + 1.0, -0.2, zc + 0.15)), dist=1.6, azim=28, elev=-18, fov=50, ground=False)
shot("lod_ac", lod_objs, target=Vector((LOD_X0 + 2.3, -0.25, 2.45)), dist=5.6, azim=10, elev=-4, fov=50, ground=False)
shot("lod_ac_bajo", lod_objs, target=Vector((LOD_X0 + 2.3, -0.25, 1.4)), dist=3.4, azim=-14, elev=-16, fov=55, ground=False)
shot("lod_dano", lod_dmg, target=Vector((LOD_X0 + 2.6, -3.7, 0.3)), dist=4.4, azim=8, elev=24, fov=55)
print(f"listo en {time.time() - t_all:.1f}s")

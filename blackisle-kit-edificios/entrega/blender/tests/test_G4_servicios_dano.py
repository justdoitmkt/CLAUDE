"""test_G4_servicios_dano.py — vitrina y QA del grupo G4 · SERVICIOS, PROPS Y DAÑO (kit/services.py, kit/damage.py).

Arma un muro-vitrina de 19,6 m × 5,5 m (con `wall_with_openings`: huecos para los A/C de ventana y ventanas con
cortinas) con todos los props de muro, a la derecha una "azotea" con tinacos y antenas, tendederos entre columnas y,
al frente, la zona de daño (varillas, escombro, trozos, mordidas de arista en losa y columna). 2–3 variantes por semilla.
Imprime por asset triángulos y salud de malla (separando las láminas intencionales de tela) y renderiza las vistas de
QA en entrega/render_qa/kit/G4_*.png (1280 × 720, 28 muestras).

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
    ("ac_window_s0", lambda: S.ac_unit("window", 0), (WIN_AC[0][0], 0, WIN_AC[0][1]), "ac"),
    ("ac_window_s1", lambda: S.ac_unit("window", 1), (WIN_AC[1][0], 0, WIN_AC[1][1]), "ac"),
    ("ac_split_s0", lambda: S.ac_unit("split_outdoor", 0), (3.6, 0, 2.5), "ac"),
    ("ac_split_s1", lambda: S.ac_unit("split_outdoor", 1), (4.9, 0, 2.5), "ac"),
    ("ac_box_old_s0", lambda: S.ac_unit("box_old", 0), (OLD_AC[0][0], 0, OLD_AC[0][1]), "ac"),
    ("ac_box_old_s1", lambda: S.ac_unit("box_old", 1), (OLD_AC[1][0], 0, OLD_AC[1][1]), "ac"),
    ("meter_box_s0_open", lambda: S.meter_box(0, open_door=True), (8.7, 0, 1.2), "serv"),
    ("meter_box_s1_closed", lambda: S.meter_box(1, open_door=False), (9.7, 0, 1.2), "serv"),
    ("light_wall_s0", lambda: S.light_fixture("wall", 0), (8.7, 0, 2.6), "serv"),
    ("light_wall_s1", lambda: S.light_fixture("wall", 1), (9.7, 0, 2.6), "serv"),
    ("light_bracket_s0", lambda: S.light_fixture("bracket", 0), (11.0, 0, 2.75), "serv"),
    ("light_bracket_s1", lambda: S.light_fixture("bracket", 1), (12.0, 0, 2.75), "serv"),
    ("mailboxes_n8_s0", lambda: S.mailboxes(8, 0), (11.0, 0, 0.9), "serv"),
    ("mailboxes_n6_s1", lambda: S.mailboxes(6, 1), (11.9, 0, 0.9), "serv"),
    ("extinguisher_s0", lambda: S.extinguisher_cabinet(0), (13.0, 0, 1.0), "serv"),
    ("extinguisher_s1", lambda: S.extinguisher_cabinet(1), (13.6, 0, 1.0), "serv"),
    ("sign_torn_2.4x0.6_s0", lambda: S.sign_torn(2.4, 0.6, 0), (11.4, 0, 3.2), "cab"),
    ("sign_torn_1.8x0.5_s1", lambda: S.sign_torn(1.8, 0.5, 1), (9.0, 0, 3.3), "cab"),
    ("satellite_dish_s0", lambda: S.satellite_dish(0), (15.3, 0, 3.55), "cab"),
    ("satellite_dish_s1", lambda: S.satellite_dish(1), (17.5, 0, 3.65), "cab"),
    ("conduit_s0", lambda: S.conduit([(13.95, 0.35), (13.95, 2.2), (12.55, 2.2), (12.55, 2.6)], 0), (0, 0, 0), "serv"),
    ("conduit_s1", lambda: S.conduit([(19.0, 0.3), (19.0, 3.15), (14.3, 3.15), (14.3, 2.7)], 1), (0, 0, 0), "cab"),
    ("cable_bundle_n4_s0", lambda: S.cable_bundle([(0.6, 0, 4.7), (5.5, 0, 4.95), (10.4, 0, 4.65)], n=4, sag=0.35, seed=0), (0, 0, 0), "cab"),
    ("cable_bundle_n3_s1", lambda: S.cable_bundle([(11.6, 0, 4.85), (15.2, 0, 4.55), (19.1, 0, 4.85)], n=3, sag=0.25, seed=1), (0, 0, 0), "cab"),
    ("curtain_torn_1.4x1.5_s0", lambda: S.curtain_torn(1.4, 1.5, 0), (CURT[0][0], 0.13, CURT[0][1]), "cab"),
    ("curtain_torn_1.8x2.0_s1", lambda: S.curtain_torn(1.8, 2.0, 1), (CURT[1][0], 0.13, CURT[1][1]), "cab"),
    ("water_tank_s0", lambda: S.water_tank(0), (21.8, -1.4, 0), "roof"),
    ("water_tank_s1", lambda: S.water_tank(1), (24.0, -1.4, 0), "roof"),
    ("tv_antenna_s0", lambda: S.tv_antenna(0), (27.0, -1.4, 0), "roof"),
    ("tv_antenna_s1", lambda: S.tv_antenna(1), (30.0, -1.6, 0), "roof"),
    ("laundry_line_2.9_s0", lambda: S.laundry_line(2.9, 0), (21.15, -3.6, 1.95), "roof"),
    ("laundry_line_2.4_s1", lambda: S.laundry_line(2.4, 1), (24.35, -3.6, 1.95), "roof"),
    ("rebar_nest_s0", lambda: D.rebar_nest(0, n=8, length=0.6), (21.4, -6.4, 0), "dmg"),
    ("rebar_nest_s1", lambda: D.rebar_nest(1, n=8, length=0.8), (22.5, -6.6, 0), "dmg"),
    ("rebar_nest_s2_n4", lambda: D.rebar_nest(2, n=4, length=0.5, stump=(0.25, 0.25, 0.3)), (23.4, -6.3, 0), "dmg"),
    ("rubble_pile_r1.0_s0", lambda: D.rubble_pile(1.0, 0, 60), (25.3, -7.0, 0), "dmg"),
    ("rubble_pile_r1.6_s1", lambda: D.rubble_pile(1.6, 1, 90), (28.6, -7.4, 0), "dmg"),
    ("chunk_0.45_s0", lambda: D.chunk(0.45, 0), (21.2, -8.0, 0), "dmg"),
    ("chunk_slab_0.6_s1", lambda: D.chunk(0.6, 1, "slab"), (22.0, -8.1, 0), "dmg"),
    ("chunk_0.25_s2", lambda: D.chunk(0.25, 2), (22.8, -7.9, 0), "dmg"),
    ("chunk_0.15_s3", lambda: D.chunk(0.15, 3), (23.2, -8.1, 0), "dmg"),
    ("spall_edge_1.2x0.12_s0", lambda: D.spall_edge(1.2, 0.12, 0), (23.8, -8.2, 0.12), "dmg"),
    ("spalled_slab_s3", lambda: spalled((21.0, -10.6, 1.0), (24.6, -9.4, 1.2),
                                          [dict(axis="x", sides=(-1, -1), start=0.5, length=1.4, depth=0.12, seed=3),
                                           dict(axis="x", sides=(-1, 1), start=2.2, length=0.9, depth=0.09, seed=4)]),
     (0, 0, 0), "dmg"),
    ("spalled_column_s5", lambda: spalled((25.6, -10.2, 0.0), (25.95, -9.85, 2.6),
                                            [dict(axis="z", sides=(-1, -1), start=0.4, length=1.1, depth=0.1, seed=5),
                                             dict(axis="z", sides=(1, -1), start=1.3, length=0.8, depth=0.08, seed=6)], bevel=0.02),
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
shot("general", ALL + people, azim=22, elev=20, margin=0.92)
shot("oblicua", ALL + people, azim=58, elev=28, margin=0.85)
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
print(f"listo en {time.time() - t_all:.1f}s")

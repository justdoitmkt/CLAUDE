"""test_G3_cubiertas_revestimientos.py — vitrina y QA del grupo G3 · CUBIERTAS Y REVESTIMIENTOS (kit/roofing.py, kit/cladding.py).

Fila de cubiertas (cada una sobre su estructura roof_frame y un bloque de muros de 3 m como soporte de vitrina) y fila de
revestimientos (muros de 6,5 x 2,8 con una ventana, una puerta y otra ventana). Imprime por asset triángulos y salud de malla
separando las láminas intencionales (roof_metal / roof_metal_light) y renderiza las vistas de QA en entrega/render_qa/kit/G3_*.png.

Uso:  cd entrega/blender && /root/blk-venv/bin/python tests/test_G3_cubiertas_revestimientos.py [--norender] [--only a,b] [--sweep]
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402,F401
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

from kit.common import MB, clay_render, mesh_health, reset_scene, tri_count  # noqa: E402
from kit import roofing as RF  # noqa: E402
from kit import cladding as CL  # noqa: E402

OUT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "render_qa", "kit"))
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[1:]
RENDER = "--norender" not in ARGS
ONLY = set(ARGS[ARGS.index("--only") + 1].split(",")) if "--only" in ARGS else None
WALL_H = 3.0


def lamina_split(ob):
    """(aristas no-manifold en sólidos, aristas abiertas de láminas intencionales)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    mats = [m.name for m in ob.data.materials]
    solid = lam = 0
    for e in bm.edges:
        if e.is_manifold:
            continue
        if e.link_faces and all(mats[f.material_index] in RF.LAMINA_MATS for f in e.link_faces):
            lam += 1
        else:
            solid += 1
    bm.free()
    return solid, lam


# ---------------------------------------------------------------------------------------------------------------------
# barrido de robustez (sin render): muchas semillas y medidas
# ---------------------------------------------------------------------------------------------------------------------
if "--sweep" in ARGS:
    reset_scene()
    bad, n = 0, 0
    t0 = time.time()

    def chk(name, mb):
        global bad, n
        ob = mb.finish(name)
        s, lam = lamina_split(ob)
        h = mesh_health(ob)
        n += 1
        if s or h["zero_area_faces"] or h["loose_verts"]:
            bad += 1
            print("FALLA", name, s, h)
        bpy.data.objects.remove(ob)

    for sd in range(4):
        for (k, w, d, p) in (("hip", 12, 9, 26), ("hip", 8, 11, 30), ("gable", 9, 6, 35), ("gable", 7, 6, 28), ("hip", 10.8, 7.2, 22)):
            for cov in ("tile", "sheet", "boards"):
                chk(f"frame_{k}_{cov}_{sd}", RF.roof_frame(k, w, d, p, 0.6, seed=sd, damage=0.3 * sd, tails=bool(sd % 2), cover=cov))
            chk(f"tiles_{k}_{sd}", RF.barrel_tiles(w, d, k, p, 0.6, seed=sd, hole=RF.damage_spot(k, w, d, p, 0.6, sd, 0.5) if sd else None))
        for (w, d, p) in ((9, 6, 35), (7, 6, 28), (5.5, 4.2, 18)):
            chk(f"corr_{sd}", RF.corrugated_roof(w, d, p, 0.5, seed=sd, light=bool(sd % 2), torn=True if sd % 2 else None))
            chk(f"boards_{sd}", RF.board_roof_stepped(w, d, p, 0.5, seed=sd))
        for (L, H, ops) in ((6.5, 2.8, [(0.8, 1.9, 0.9, 2.1), (2.8, 3.7, 0.0, 2.05)]), (3.1, 2.6, [(0.0, 0.9, 0.0, 2.0)]),
                            (8.0, 3.0, [(1.0, 2.2, 1.0, 2.2), (3.0, 4.6, 0.8, 2.25), (6.6, 7.6, 0.0, 2.1)]), (2.2, 2.9, [])):
            chk(f"brick_{sd}", CL.brick_wall(L, H, seed=sd, openings=ops, missing=0.02 + 0.03 * sd))
            chk(f"bb_{sd}", CL.board_and_batten(L, H, seed=sd, openings=ops, rot=0.1 * sd))
            chk(f"clap_{sd}", CL.clapboard(L, H, seed=sd, openings=ops))
    print(f"barrido: {n} mallas, {bad} con fallas, {time.time() - t0:.1f}s")
    sys.exit(1 if bad else 0)


# ---------------------------------------------------------------------------------------------------------------------
# vitrina
# ---------------------------------------------------------------------------------------------------------------------
reset_scene()
assets, report, support = {}, [], []


def add(name, fn, loc, frame=None):
    t = time.time()
    mb = fn()
    ob = mb.finish("G3_" + name)
    ob.location = loc
    assets[name] = ob
    s, lam = lamina_split(ob)
    report.append((name, tri_count([ob]), mesh_health(ob), s, lam, time.time() - t))
    return ob


def base_block(x, y, w, d, h=WALL_H, mat="concrete"):
    m = MB()
    m.box((x - w / 2, y - d / 2, 0.0), (x + w / 2, y + d / 2, h - 0.002), mat, bevel=0.02, seg=1)
    o = m.finish(f"_soporte_{len(support)}")
    support.append(o)
    return o


Z = WALL_H
ROOFS = {}
# 1) APT: hip 12 x 9 a 26°, teja curva sobre estructura con hueco
sp1 = RF.damage_spot("hip", 12, 9, 26, 0.6, seed=3, damage=0.7)
base_block(0, 0, 12, 9)
add("roof_frame_hip_tile_dmg_s3", lambda: RF.roof_frame("hip", 12, 9, 26, 0.6, seed=3, damage=0.7, tails=True), (0, 0, Z))
add("barrel_tiles_hip_hole_s3", lambda: RF.barrel_tiles(12, 9, "hip", 26, 0.6, seed=3, hole=sp1), (0, 0, Z))
# 2) gable 8 x 6 a 30° con teja (sin daño) — fascia en lugar de colas
base_block(16, 0, 8, 6)
add("roof_frame_gable_tile_s2", lambda: RF.roof_frame("gable", 8, 6, 30, 0.5, seed=2, tails=False), (16, 0, Z))
add("barrel_tiles_gable_s2", lambda: RF.barrel_tiles(8, 6, "gable", 30, 0.5, seed=2, missing=0.06), (16, 0, Z))
# 3) hip con w < d (cumbrera en Y), teja sola
base_block(29, 0, 7.2, 10.8)
add("roof_frame_hip_swap_s7", lambda: RF.roof_frame("hip", 7.2, 10.8, 24, 0.6, seed=7, tails=True), (29, 0, Z))
add("barrel_tiles_hip_swap_s7", lambda: RF.barrel_tiles(7.2, 10.8, "hip", 24, 0.6, seed=7, missing=0.03), (29, 0, Z))
# 4) CAB_1: gable 9 x 6 a 35°, lámina oxidada con sección arrancada
tr = RF.damage_spot("gable", 9, 6, 35, 0.6, seed=5, damage=0.6)
base_block(42, 0, 9, 6, mat="wood_dark")
add("roof_frame_gable_sheet_dmg_s5", lambda: RF.roof_frame("gable", 9, 6, 35, 0.6, seed=5, damage=0.6, cover="sheet", spot=tr),
    (42, 0, Z))
add("corrugated_rust_torn_s5", lambda: RF.corrugated_roof(9, 6, 35, 0.6, seed=5, torn=tr), (42, 0, Z))
# 5) CAB_2: gable 7 x 6 a 28°, lámina clara con sección arrancada
tr2 = RF.damage_spot("gable", 7, 6, 28, 0.5, seed=9, damage=0.5)
base_block(54, 0, 7, 6, mat="wood_grey")
add("roof_frame_gable_sheet_s9", lambda: RF.roof_frame("gable", 7, 6, 28, 0.5, seed=9, damage=0.5, cover="sheet", spot=tr2),
    (54, 0, Z))
add("corrugated_light_torn_s9", lambda: RF.corrugated_roof(7, 6, 28, 0.5, seed=9, light=True, torn=tr2), (54, 0, Z))
# 6) CAB_3: gable 8 x 6,5 a 30°, tablones escalonados
base_block(66, 0, 8, 6.5, mat="brick")
add("roof_frame_gable_boards_s14", lambda: RF.roof_frame("gable", 8, 6.5, 30, 0.5, seed=14, cover="boards", tails=False),
    (66, 0, Z))
add("board_roof_stepped_s14", lambda: RF.board_roof_stepped(8, 6.5, 30, 0.5, seed=14), (66, 0, Z))
# variantes por semilla (solo cubierta)
add("corrugated_rust_s1", lambda: RF.corrugated_roof(6, 4.5, 22, 0.45, seed=1), (42, -12, 0.0))
add("board_roof_stepped_s3", lambda: RF.board_roof_stepped(6, 4.5, 34, 0.4, seed=3), (54, -12, 0.0))

# fila de revestimientos (y = -12)
OPS = [(0.7, 1.9, 0.95, 2.15), (2.7, 3.6, 0.0, 2.05), (4.5, 5.8, 0.95, 2.15)]
add("brick_wall_s1", lambda: CL.brick_wall(6.5, 2.8, seed=1, openings=OPS, missing=0.03), (-3.25, -12, 0))
add("brick_wall_s2", lambda: CL.brick_wall(4.0, 2.8, seed=2, openings=[(1.2, 2.4, 0.9, 2.1)], missing=0.06, plaster=0.25), (4.2, -12, 0))
add("board_and_batten_s1", lambda: CL.board_and_batten(6.5, 2.8, seed=1, openings=OPS, rot=0.15), (9.5, -12, 0))
add("board_and_batten_s2", lambda: CL.board_and_batten(4.0, 2.8, seed=2, openings=[(1.2, 2.4, 0.9, 2.1)], rot=0.4), (17, -12, 0))
add("clapboard_s1", lambda: CL.clapboard(6.5, 2.8, seed=1, openings=OPS), (22, -12, 0))
add("clapboard_s2", lambda: CL.clapboard(4.0, 2.8, seed=2, openings=[(1.2, 2.4, 0.9, 2.1)], loose=0.15), (29.5, -12, 0))

pm = MB()
pm.box((-0.225, -0.125, 0.0), (0.225, 0.125, 1.8), "plastic")
person = pm.finish("_persona_1.80")
person.location = (-4.5, -12.8, 0.0)
p2 = person.copy()
p2.location = (-7.2, -5.2, 0.0)
bpy.context.scene.collection.objects.link(p2)
bpy.context.view_layer.update()

print("\n=== G3 · CUBIERTAS Y REVESTIMIENTOS — triángulos y salud de malla ===")
print(f"{'asset':34s} {'tris':>8s}  nm_sólidos  bordes_lámina  área0  sueltos   t")
fails = 0
for name, tc, hl, s, lam, dt in report:
    flag = "" if (s == 0 and hl["zero_area_faces"] == 0 and hl["loose_verts"] == 0) else "  <-- REVISAR"
    fails += bool(flag)
    print(f"{name:34s} {tc:8d}  {s:10d}  {lam:13d}  {hl['zero_area_faces']:5d}  {hl['loose_verts']:7d}  {dt:5.2f}s{flag}")
print(f"total vitrina: {sum(r[1] for r in report)} tris · {len(report)} assets · fallas={fails}")


# ---------------------------------------------------------------------------------------------------------------------
def shot(tag, objs, hide=(), **kw):
    if not RENDER or (ONLY and tag not in ONLY):
        return
    out = os.path.join(OUT, f"G3_{tag}.png")
    t = time.time()
    for o in hide:
        o.hide_render = True
    clay_render(objs, out, res=(1280, 720), samples=kw.pop("samples", 28), **kw)
    for o in hide:
        o.hide_render = False
    print(f"render {out} ({time.time() - t:.0f}s)")


A = assets
ALL = list(A.values()) + support + [person, p2]
shot("general", ALL, target=Vector((31.0, -6.0, 1.5)), dist=112.0, azim=-14, elev=30, samples=24)
# primer plano ~2 m: alero de teja visto desde abajo (punto de vista del jugador) y cumbrera
shot("teja_alero_2m", [A["barrel_tiles_hip_hole_s3"], A["roof_frame_hip_tile_dmg_s3"], support[0]],
     target=Vector((3.6, -5.05, Z - 0.12)), dist=2.0, azim=-20, elev=-14, ground=False)
shot("teja_cumbrera_2m", [A["barrel_tiles_hip_hole_s3"]], target=Vector((0.9, 0.1, Z + 2.5)), dist=2.1, azim=165, elev=24,
     ground=False)
shot("teja_hueco_oblicua", [A["barrel_tiles_hip_hole_s3"], A["roof_frame_hip_tile_dmg_s3"]],
     target=Vector((sp1[0], sp1[1], Z + 1.2)), dist=6.5, azim=-35, elev=38)
shot("teja_limatesa", [A["barrel_tiles_hip_hole_s3"], A["roof_frame_hip_tile_dmg_s3"]], target=Vector((5.4, -4.0, Z + 0.3)),
     dist=3.2, azim=-60, elev=16)
shot("teja_gable_oblicua", [A["barrel_tiles_gable_s2"], A["roof_frame_gable_tile_s2"]] + support[1:2], azim=35, elev=22,
     margin=0.9)
shot("teja_remate_2m", [A["barrel_tiles_gable_s2"], A["roof_frame_gable_tile_s2"], support[1]],
     target=Vector((16 + 4.3, -2.2, Z + 0.9)), dist=2.2, azim=55, elev=18, ground=False)
shot("estructura_hueco", [A["roof_frame_hip_tile_dmg_s3"], support[0]], hide=[A["barrel_tiles_hip_hole_s3"]],
     target=Vector((0.0, -1.2, Z + 1.0)), dist=9.0, azim=-30, elev=42)
shot("lamina_oblicua", [A["corrugated_rust_torn_s5"], A["roof_frame_gable_sheet_dmg_s5"]] + support[3:4], azim=-35, elev=30,
     margin=0.85)
shot("lamina_desgarro_2m", [A["corrugated_rust_torn_s5"], A["roof_frame_gable_sheet_dmg_s5"]],
     target=Vector((42 + tr[0], tr[1] - 0.6, Z + 1.0)), dist=2.6, azim=-25, elev=30)
shot("lamina_alero_2m", [A["corrugated_rust_torn_s5"], A["roof_frame_gable_sheet_dmg_s5"]],
     target=Vector((42 + 4.2, -3.4, Z - 0.1)), dist=2.0, azim=-40, elev=-5)
shot("lamina_clara_oblicua", [A["corrugated_light_torn_s9"], A["roof_frame_gable_sheet_s9"]] + support[4:5], azim=40, elev=28,
     margin=0.85)
shot("tablones_oblicua", [A["board_roof_stepped_s14"], A["roof_frame_gable_boards_s14"]] + support[5:6], azim=-50, elev=18,
     margin=0.85)
shot("tablones_alero_2m", [A["board_roof_stepped_s14"], A["roof_frame_gable_boards_s14"]], target=Vector((66 + 4.3, -3.2, Z + 0.15)),
     dist=2.0, azim=-62, elev=8)
shot("tablones_remate_2m", [A["board_roof_stepped_s14"], A["roof_frame_gable_boards_s14"], support[5]],
     target=Vector((66 - 4.5, -1.4, Z + 0.75)), dist=2.4, azim=-110, elev=6, ground=False)
shot("ladrillo_2m", [A["brick_wall_s1"], person], target=Vector((-3.25 + 2.0, -12, 1.2)), dist=2.0, azim=22, elev=5)
WALLS = [A[k] for k in ("brick_wall_s1", "brick_wall_s2", "board_and_batten_s1", "board_and_batten_s2", "clapboard_s1",
                         "clapboard_s2")]
ROOFS_HIDE = [o for k, o in A.items() if o not in WALLS] + support
shot("revestimientos", WALLS + [person], hide=ROOFS_HIDE, target=Vector((15.0, -12.0, 1.3)), dist=44.0, azim=-6, elev=7)
shot("revestimientos_oblicua", WALLS, hide=ROOFS_HIDE, target=Vector((12.0, -12.0, 1.3)), dist=7.5, azim=-38, elev=9)
shot("tablon_junquillo_2m", [A["board_and_batten_s2"]], target=Vector((17 + 1.0, -12, 0.9)), dist=2.0, azim=25, elev=6)
shot("tabla_traslapada_2m", [A["clapboard_s2"]], target=Vector((29.5 + 0.9, -12, 1.0)), dist=2.0, azim=-28, elev=6)
print("listo")

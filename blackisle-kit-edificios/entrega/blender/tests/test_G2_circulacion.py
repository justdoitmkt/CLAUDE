"""Prueba y vitrina del GRUPO G2 · CIRCULACIÓN Y BORDES (kit/circulation.py).

Construye TODOS los assets con 2–3 variantes por semilla, imprime triángulos y salud de malla por asset y renderiza en
entrega/render_qa/kit/G2_*.png (Cycles CPU 1280x720, 28 muestras):
  G2_general.png            vitrina completa con persona de 1,80 m
  G2_primer_plano.png       primer plano a ~2 m (narices despostilladas, pasamanos soldado)
  G2_oblicua.png            vista oblicua de barandales y losas de balcón
  G2_escalera_apilada.png   dos módulos stair_u apilados en un núcleo recortado (contexto, no cuenta triángulos)
  G2_escalera_inferior.png  cara inferior de los tramos: encofrado, desconchado y varillas
  G2_barandales.png         primer plano de balaustradas de concreto y barandales de tubo
  G2_barandal_madera.png    barandales de madera (sano y con vano roto)
  G2_madera.png             escaleras de madera de zanca cerrada y recortada (cabañas)
  G2_balcon_inferior.png    gotero y cantos desconchados de la losa de balcón
  G2_canalon_bajante.png    bajante con tramo faltante junto a un balcón
  G2_canalon_alero.png      canalón de alero con cuello de cisne y tramo de bajante roto colgando
  G2_canalon_detalle.png    ganchos de fleje, flecha entre ganchos, boquilla y casquillo
  G2_canalon_esquina.png    canalón que dobla la esquina del alero (inglete + pieza de esquina con dos bocas)
  G2_balaustrada_giro.png   pilar de arranque con remate en el ojo de la U (PB 3,4 m con balaustrada de concreto)
  G2_escalera_paso.png      tramo visto a la altura de los ojos (1,6 m) al subir: narices, grietas, gravilla
  G2_balcon_superior.png    cara superior del balcón: grieta de flexión junto al muro, arena en la junta, escombro
Además verifica: salud de malla, autointersecciones dentro de cada pieza (BVH) y determinismo (misma semilla ->
mismos triángulos y vértices). Termina en OK o en FALLO (código de salida 1).
La fachada, el alero, la fascia, el núcleo recortado y la persona son CONTEXTO (no se cuentan).
Uso: cd entrega/blender && /root/blk-venv/bin/python tests/test_G2_circulacion.py [--only plano1,plano2]
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402,F401
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from kit.common import MB, clay_render, mesh_health, reset_scene, tri_count  # noqa: E402
from kit import circulation as C  # noqa: E402

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "render_qa", "kit"))
os.makedirs(OUT, exist_ok=True)
RES, SAMPLES = (1280, 720), 28
# --only a,b: renderiza solo esos planos (la medición y las comprobaciones se hacen siempre)
ONLY = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else set()

reset_scene()
assets, ctx = [], []
recipes = {}  # nombre -> (función, args, kwargs) para la prueba de determinismo


def sig(mb):
    """Firma de una malla: (vértices, caras, suma ponderada de coordenadas)."""
    return len(mb.bm.verts), len(mb.bm.faces), round(sum(v.co.x * 1.3 + v.co.y * 2.1 + v.co.z * 0.7 for v in mb.bm.verts), 5)


def put(mb, name, loc=(0, 0, 0), rot_z=0.0, recipe=None):
    if recipe is not None:
        recipes[name] = (recipe, sig(mb))
    ob = mb.finish(name)
    ob.location = loc
    ob.rotation_euler = (0.0, 0.0, rot_z)
    assets.append(ob)
    return ob


def mk(fn, *a, **kw):
    """Construye y recuerda la receta (para reconstruir con la misma semilla)."""
    mb = fn(*a, **kw)
    mb._recipe = (fn, a, kw)
    return mb


def putr(mb, name, loc=(0, 0, 0), rot_z=0.0):
    return put(mb, name, loc, rot_z, recipe=mb._recipe)


def context_box(name, mn, mx):
    m = MB()
    m.box(mn, mx, "plaster", bevel=0.01, seg=1)
    ob = m.finish(name)
    ctx.append(ob)
    return ob


# ------------------------------------------------------------------ fila 1: escaleras
su0 = putr(mk(C.stair_u, seed=0, broken=0.15), "G2_stair_u_s0")
su1 = putr(mk(C.stair_u, seed=3, broken=0.4, rail="tube_metal"), "G2_stair_u_s3_rail", (4.6, 0.0, 0.0))
su2_mb = mk(C.stair_u, floor_h=3.4, seed=7, broken=0.25, rail="baluster_concrete", core_length=3.9)
su2_meta = dict(su2_mb.meta)
su2 = putr(su2_mb, "G2_stair_u_PB34_s7", (9.2, 0.0, 0.0))
ss0 = putr(mk(C.stair_straight, 1.4, 0.9, seed=1, broken=0.3), "G2_stair_straight_conc_s1", (14.0, 0.0, 0.0))
ss1 = putr(mk(C.stair_straight, 1.2, 3.0, seed=2, stringers=True, rail="tube_metal", broken=0.2),
          "G2_stair_straight_zancas_s2", (14.0, 1.9, 0.0))
sw0 = putr(mk(C.stair_straight, 1.0, 1.4, seed=3, kind="wood", broken=0.35, rail="wood", rail_side="right"),
          "G2_stair_straight_wood_s3", (14.0, 3.9, 0.0))
sw1 = putr(mk(C.stair_straight, 1.0, 2.6, seed=4, kind="wood", stringers=False, broken=0.2), "G2_stair_straight_wood_recortada_s4",
          (14.0, 5.3, 0.0))
# acceso de PB de concreto con balaustrada: pilar de arranque con remate donde el pasamanos pasa a horizontal
ss2 = putr(mk(C.stair_straight, 1.2, 1.7, seed=6, broken=0.15, rail="baluster_concrete", rail_side="right"),
           "G2_stair_straight_balaustrada_s6", (14.0, 6.7, 0.0))

# ------------------------------------------------------------------ fila 2: barandales
rails = []
for i, (kind, bend, miss) in enumerate([("baluster_concrete", 0.0, 0.08), ("tube_metal", 0.0, 0.08), ("wood", 0.0, 0.1)]):
    rails.append(putr(mk(C.railing, kind, 3.2, seed=10 + i, bend=bend, missing=miss), f"G2_railing_{kind}_s{10 + i}",
                     (i * 3.8, -2.6, 0.0)))
for i, (kind, bend, miss) in enumerate([("baluster_concrete", 0.14, 0.2), ("tube_metal", 0.25, 0.15), ("wood", 0.16, 0.2)]):
    rails.append(putr(mk(C.railing, kind, 3.2, seed=20 + i, bend=bend, missing=miss), f"G2_railing_{kind}_s{20 + i}_roto",
                     (i * 3.8, -4.0, 0.0)))
sr0 = putr(mk(C.stair_railing, [(0, 0, 0), (2.24, 0, 1.28), (2.8, 0, 1.28)], h=0.9, kind="baluster_concrete", seed=31),
          "G2_stair_railing_conc_s31", (11.6, -2.6, 0.0))
sr1 = putr(mk(C.stair_railing, [(0, 0, 0), (2.24, 0, 1.28)], h=0.9, kind="wood", seed=32), "G2_stair_railing_wood_s32",
          (11.6, -4.0, 0.0))

# ------------------------------------------------------------------ fachada de contexto: balcones, canalones y bajantes
WY = 9.5  # cara del muro (la fachada mira a -Y), detrás de la fila de escaleras
X0 = 0.0
context_box("ctx_fachada", (X0, WY, 0.0), (X0 + 12.7, WY + 0.25, 3.1))
ZB = 1.2
bal0 = putr(mk(C.balcony_slab, 1.8, 1.2, seed=0, spalled=0.35), "G2_balcony_slab_s0", (X0 + 1.0, WY, ZB))
bal1 = putr(mk(C.balcony_slab, 2.4, 1.0, seed=5, spalled=0.8), "G2_balcony_slab_s5", (X0 + 3.4, WY, ZB))
bal2 = putr(mk(C.balcony_slab, 1.5, 1.2, t=0.12, seed=9, spalled=0.15), "G2_balcony_slab_s9", (X0 + 6.6, WY, ZB))
br0 = putr(mk(C.railing, "tube_metal", 1.7, seed=41, missing=0.1), "G2_bal_railing_tube_s41", (X0 + 1.05, WY - 1.08, ZB + 0.13))
br1 = putr(mk(C.railing, "baluster_concrete", 2.3, seed=42, missing=0.15), "G2_bal_railing_conc_s42",
          (X0 + 3.45, WY - 0.88, ZB + 0.12))
FASCIA = 0.06 + 0.0265  # = gutter(...).meta["fascia_offset"]: cara de la fascia respecto al eje del canalón
gy0 = WY - FASCIA  # canalón colgado del zuncho: la pestaña del gancho atornilla en la cara del muro
gut0_mb = mk(C.gutter, [(X0 + 0.1, gy0, 3.0), (X0 + 6.8, gy0, 3.0)], seed=0, outlets=(0.7,), fault="fallen")
assert abs(gut0_mb.meta["fascia_offset"] - FASCIA) < 1e-9
top0 = Vector(gut0_mb.meta["outlets"][0])
gut0 = putr(gut0_mb, "G2_gutter_s0_caido")
dp0 = putr(mk(C.downpipe, top0, (top0.x, WY - 0.06, 0.0), wall_offset=0.06, seed=2, fault="missing"), "G2_downpipe_s2_falta")
gy1 = WY - 0.40  # canalón en el borde de un alero que vuela 0,40: la bajante hace cuello de cisne hasta el muro
gut1_mb = mk(C.gutter, [(X0 + 7.3, gy1, 3.0), (X0 + 12.6, gy1, 3.0)], seed=5, fault="bent", outlets=(4.3, 1.7))
top1 = Vector(gut1_mb.meta["outlets"][0])
top2 = Vector(gut1_mb.meta["outlets"][1])
fz = gy1 + gut1_mb.meta["fascia_offset"]
gut1 = putr(gut1_mb, "G2_gutter_s5_doblado")
dp1 = putr(mk(C.downpipe, top1, (top1.x, WY - 0.06, 0.0), seed=6, fault="broken"), "G2_downpipe_s6_roto")
dp2 = putr(mk(C.downpipe, top2, (top2.x, WY - 0.06, 0.0), seed=8, fault="none", mat="metal_rust"), "G2_downpipe_s8_hierro")
context_box("ctx_fascia_alero", (X0 + 7.1, fz, 2.93), (X0 + 12.7, fz + 0.025, 3.16))
context_box("ctx_alero", (X0 + 7.1, fz + 0.02, 3.1), (X0 + 12.7, WY + 0.02, 3.18))
# canalón que dobla la esquina de un bloque (alero de 4 aguas): inglete + pieza de esquina, bajante en el frente
XC0, XC1 = 13.4, 16.4
context_box("ctx_bloque_esquina", (XC0, WY, 0.0), (XC1, WY + 2.6, 3.1))
gut2_mb = mk(C.gutter, [(XC0 + 0.1, WY - FASCIA, 3.0), (XC1 + FASCIA, WY - FASCIA, 3.0), (XC1 + FASCIA, WY + 2.5, 3.0)],
             seed=12, fault="bent", outlets=(1.0,))
top3 = Vector(gut2_mb.meta["outlets"][0])
gut2 = putr(gut2_mb, "G2_gutter_s12_esquina")
dp3 = putr(mk(C.downpipe, top3, (top3.x, WY - 0.06, 0.0), seed=13, fault="missing"), "G2_downpipe_s13_esquina")

# ------------------------------------------------------------------ persona de escala
pm = MB()
pm.box((-0.225, -0.125, 0.0), (0.225, 0.125, 1.80), "fabric", bevel=0.02, seg=1)
person = pm.finish("persona_1_80")
person.location = (-0.9, 0.6, 0.0)
ctx.append(person)

# ------------------------------------------------------------------ medición
print("\n=== G2 · CIRCULACIÓN Y BORDES ===")
tot, bad = 0, []
for ob in assets:
    t = tri_count([ob])
    h = mesh_health(ob)
    tot += t
    if h["non_manifold_edges"] or h["zero_area_faces"] or h["loose_verts"]:
        bad.append(ob.name)
    print(f"{ob.name:38s} tris {t:7d}   {h}")
print(f"TOTAL tris {tot}   assets {len(assets)}   con problemas de salud: {bad or 'ninguno'}")
print("stair_u footprint (2,9 m):", C.stair_u_footprint())
print("stair_u footprint (3,4 m, core 3,9):", {k: su2_meta[k] for k in ("N", "riser", "L", "W", "landing_z")})


def self_x(ob):
    """Pares de caras que se cruzan DENTRO de una misma pieza (sin vértices comunes). Las piezas distintas pueden
    interpenetrarse a propósito; una pieza que se cruza a sí misma da normales invertidas y sombreado sucio."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    isl, seen = {}, set()
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, k = [f], len(set(isl.values()))
        seen.add(f.index)
        while stack:
            g = stack.pop()
            isl[g.index] = k
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
    tree = BVHTree.FromBMesh(bm)
    n = sum(1 for a, b in tree.overlap(tree) if a < b and isl[a] == isl[b]
            and not (set(bm.faces[a].verts) & set(bm.faces[b].verts)))
    bm.free()
    return n


print("\n--- autointersección por pieza (pares) y determinismo (misma semilla -> misma malla)")
selfx_bad, det_bad = [], []
for ob in assets:
    n = self_x(ob)
    if n > 6:  # quedan 1-2 pares submilimétricos ocultos (extremo de tramo dentro del descanso, borde dentro de la zanca)
        selfx_bad.append(ob.name)
    msg = ""
    if ob.name in recipes:
        (fn, a, kw), sg = recipes[ob.name]
        sg2 = sig(fn(*a, **kw))
        msg = "determinista" if sg2 == sg else f"NO DETERMINISTA {sg} != {sg2}"
        if sg2 != sg:
            det_bad.append(ob.name)
    print(f"{ob.name:38s} autointersección {n:3d}   {msg}")
print(f"autointersección: {selfx_bad or 'ninguna'}   determinismo: {det_bad or 'todo determinista'}")

# ------------------------------------------------------------------ escena de contexto: dos módulos apilados en un núcleo
STK = Vector((-14.0, 0.0, 0.0))
fp = C.stair_u_footprint()
stack = []
for lvl in range(2):
    ob = C.stair_u(seed=50 + lvl, broken=0.2, rail="tube_metal").finish(f"ctx_stack_{lvl}")
    ob.location = STK + Vector((0.0, 0.0, lvl * 2.9))
    stack.append(ob)
L_, W_ = fp["L"], fp["W"]
for lvl in range(3):  # losas de piso con el hueco (solo la franja de llegada x<0 y los bordes)
    z = lvl * 2.9
    stack.append(context_box(f"stk_losa_{lvl}", STK + Vector((-1.55, -0.2, z - 0.2)), STK + Vector((0.0, W_ + 0.1, z))))
stack.append(context_box("stk_muro_fondo", STK + Vector((L_, -0.2, -0.2)), STK + Vector((L_ + 0.2, W_ + 0.2, 6.0))))
stack.append(context_box("stk_muro_lado", STK + Vector((-1.6, W_, -0.2)), STK + Vector((L_ + 0.2, W_ + 0.2, 6.0))))
pc = MB()
pc.box((-0.225, -0.125, 0.0), (0.225, 0.125, 1.80), "fabric", bevel=0.02, seg=1)
p2 = pc.finish("stk_persona")
p2.location = STK + Vector((-0.6, W_ - 0.35, 2.9))
stack.append(p2)
bpy.context.view_layer.update()

SPECIAL = {"_ground", "_cam", "_sun"}


def shot(objs, name, ground_z=0.0, **kw):
    """Renderiza solo `objs` (oculta el resto). El encuadre y el piso salen de una caja proxy (2 vértices, sin caras)
    con el mismo XY que `objs` pero con el fondo en ground_z: así el piso del render queda en z=0 y los pies de los
    tramos que bajan bajo el nivel de piso (se empotran en la losa) quedan enterrados, como en el edificio."""
    if ONLY and name not in ONLY:
        return None
    keep = {o.name for o in objs}
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name not in SPECIAL:
            o.hide_render = o.name not in keep
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), ground_z))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    me = bpy.data.meshes.new("_frame")
    me.from_pydata([tuple(mn), tuple(mx)], [], [])
    fr = bpy.data.objects.new("_frame", me)
    bpy.context.scene.collection.objects.link(fr)
    bpy.context.view_layer.update()
    path = os.path.join(OUT, f"G2_{name}.png")
    clay_render([fr], path, res=RES, samples=SAMPLES, **kw)
    bpy.data.objects.remove(fr)
    bpy.data.meshes.remove(me)
    print("render", path)
    return path


main = assets + [o for o in ctx if o.name.startswith("ctx_")] + [person]
fac = [bal0, bal1, bal2, br0, br1, gut0, gut1, dp0, dp1, dp2] + [o for o in ctx if o.name.startswith("ctx_") and
                                                                    o.name != "ctx_bloque_esquina"]
shot(main, "general", azim=-30, elev=38, margin=0.95)
shot(main, "primer_plano", azim=-20, elev=45, target=Vector((4.6 + 1.3, 1.0, 0.7)), dist=2.0, fov=50)
shot(fac, "oblicua", azim=-42, elev=14, target=Vector((X0 + 6.2, WY - 0.8, 1.6)), dist=9.5, fov=45)
shot(stack, "escalera_apilada", azim=-58, elev=20, target=STK + Vector((1.5, 1.2, 2.9)), dist=10.5, fov=45)
shot([su1], "escalera_inferior", azim=-100, elev=-40, target=Vector((4.6 + 1.7, 1.6, 2.0)), dist=2.7, fov=65,
     ground=False, sun_elev=-40, sun_azim=160)
shot(main, "barandales", azim=-28, elev=14, target=Vector((3.0, -3.4, 0.6)), dist=3.4, fov=50)
shot(main, "barandal_madera", azim=-25, elev=16, target=Vector((9.2, -3.3, 0.6)), dist=3.4, fov=50)
shot([ss0, ss1, sw0, sw1, ss2], "madera", azim=-58, elev=20, target=Vector((15.2, 4.6, 0.9)), dist=4.2, fov=45)
shot([bal0, bal1, bal2, br0, br1], "balcon_inferior", azim=-25, elev=-16, target=Vector((X0 + 4.1, WY - 0.6, ZB)),
     dist=2.6, fov=55, ground=False, sun_elev=-30)
shot(fac, "canalon_bajante", azim=-22, elev=6, target=Vector((X0 + 1.4, WY - 0.3, 1.6)), dist=4.6, fov=50)
shot(fac, "canalon_alero", azim=-38, elev=8, target=Vector((X0 + 11.4, WY - 0.3, 1.9)), dist=3.8, fov=50)
shot(fac, "canalon_detalle", azim=-40, elev=-5, target=Vector((X0 + 0.8, WY - 0.12, 2.9)), dist=1.1, fov=50)
esq = [gut2, dp3, bpy.data.objects["ctx_bloque_esquina"]]
shot(esq, "canalon_esquina", azim=48, elev=-12, target=Vector((XC1 - 0.1, WY - 0.05, 2.9)), dist=1.6, fov=50,
     ground=False)
shot([su2], "balaustrada_giro", azim=60, elev=35, target=Vector((9.2 + 2.4, 1.2, 2.0)), dist=2.4, fov=55)
shot([su0], "escalera_paso", azim=-90, elev=18, target=Vector((1.4, 0.55, 0.9)), dist=2.1, fov=60)
shot([bal0, bpy.data.objects["ctx_fachada"]], "balcon_superior", azim=-72, elev=20,
     target=Vector((X0 + 1.0 + 1.0, WY - 0.35, ZB + 0.15)), dist=1.9, fov=55, sun_azim=105, sun_elev=28)
if bad or selfx_bad or det_bad:
    print("FALLO", bad, selfx_bad, det_bad)
    sys.exit(1)
print("OK")

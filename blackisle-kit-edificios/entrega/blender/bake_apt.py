"""bake_apt.py — horneado final de un edificio de departamentos (fase F) y materiales glTF.

Uso: /root/blk-venv/bin/python bake_apt.py --id APT_A_5p [--quick] [--reuse] [--ue]
  --quick : tamaños 1/4 y pocas muestras (prueba del flujo completo).
  --ue    : variante del kit para Unreal Engine 5: sin arena ni hierba alrededor (el escombro exterior queda como pieza suelta),
            atlas de muros horneados sin la arena (texturas_ue/<ID>), materiales separados por tipo (vidrio, aluminio, tela...)
            en vez del 'liso' combinado, y <ID>_ue.blend para blender/export_ue5.py.
Atlas (brief §4.7 con el recorte de memoria aplicado): walls_main (cara principal + banda de grafiti de las 4 caras),
walls_rest (resto del exterior de la carcasa), details (vanos, servicios, daño), roof (estructura + teja + canalón),
skirt (arena + hierba). Interior: materiales repetibles a escala real (UV de caja) + AO horneada en el canal 'lightmap'.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

import apt_builder as ab  # noqa: E402
import builders  # noqa: E402
import lookdev as ld  # noqa: E402
from kit.common import box_uv_bm, reset_scene, tri_count  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))

SIZES = {   # atlas: (albedo, normal, orm)
    # walls_main: normal a 2048 (a 1024 eran ~35 px/m; revisión de aceptación de A: muro blando a 2 m)
    "walls_main": (4096, 2048, 1024), "walls_rest": (3072, 1024, 1024), "details": (2048, 2048, 1024),
    "roof": (2048, 1024, 1024), "skirt": (2048, 512, 512),
}
SIZES_CAB = {   # cabañas: superficie ~1/4 de un edificio -> mitad de resolución en el atlas principal
    "walls_main": (2048, 1024, 1024), "walls_rest": (2048, 1024, 1024), "details": (2048, 1024, 1024),
    "roof": (2048, 1024, 1024), "skirt": (2048, 512, 512),
}
SIZES_MUE = {   # muelle: ~2x la superficie exterior de un edificio -> atlas principal de 8K para conservar la densidad
    "walls_main": (8192, 2048, 1024), "walls_rest": (4096, 1024, 1024), "details": (2048, 2048, 1024),
    "roof": (2048, 1024, 1024), "skirt": (2048, 512, 512),
}
INTERIOR_AO = 1024
BAND_SCALE = 2.0   # islas de la banda de PB (grafiti, lo que el jugador ve de cerca) ampliadas dentro de walls_main; antes 1,4


def log(*a):
    print("[bake]", *a, flush=True)


def join(objs, name):
    objs = [o for o in objs if o is not None and len(o.data.polygons)]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    return ob


def split_by(obj, pred, name_true, name_false):
    """Separa caras de obj según pred(face_center_world, normal_world)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    mw = obj.matrix_world
    mask = [pred(mw @ f.calc_center_median(), (mw.to_3x3() @ f.normal).normalized()) for f in bm.faces]
    me_t, me_f = ld._split_mesh(bm, mask)
    bm.free()
    res = []
    for me, nm in ((me_t, name_true), (me_f, name_false)):
        for m in obj.data.materials:
            me.materials.append(m)
        o = bpy.data.objects.new(nm, me)
        o.matrix_world = obj.matrix_world
        for c in obj.users_collection:
            c.objects.link(o)
        res.append(o)
    bpy.data.objects.remove(obj)
    return res


def uv_islands(bm, uv):
    """Islas UV (union-find por vértice + coordenada UV compartida)."""
    parent = {}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in bm.faces:
        parent[f.index] = f.index
    key = {}
    for f in bm.faces:
        for lp in f.loops:
            k = (lp.vert.index, round(lp[uv].uv.x, 5), round(lp[uv].uv.y, 5))
            if k in key:
                ra, rb = find(key[k]), find(f.index)
                if ra != rb:
                    parent[ra] = rb
            else:
                key[k] = f.index
    isl = {}
    for f in bm.faces:
        isl.setdefault(find(f.index), []).append(f)
    return list(isl.values())


def scale_band_islands(obj, band_top, factor):
    """Agranda (factor) las islas UV que contienen caras de la banda de grafiti (z < band_top) y re-empaqueta."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv["atlas"]
    bm.faces.ensure_lookup_table()
    mw = obj.matrix_world
    n = 0
    for faces in uv_islands(bm, uv):
        if not any((mw @ f.calc_center_median()).z < band_top for f in faces):
            continue
        pts = [lp[uv].uv.copy() for f in faces for lp in f.loops]
        c = sum(pts, Vector((0, 0))) / len(pts)
        for f in faces:
            for lp in f.loops:
                lp[uv].uv = c + (lp[uv].uv - c) * factor
        n += 1
    bm.to_mesh(obj.data)
    bm.free()
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    return n


def mem_mb(w, h):
    return w * h * 4 * 1.33 / 2**20


def _load_or_bake(obj, name, kind, size, out_dir, reuse, **kw):
    path = os.path.join(out_dir, name + ".png")
    if reuse and os.path.exists(path):
        img = bpy.data.images.load(path)
        img.name = name
        if kw.get("colorspace") == "Non-Color":
            img.colorspace_settings.name = "Non-Color"
        return img, True
    return ld.bake(obj, name, kind, size, out_dir, **kw), False


def bake_atlas(obj, aid, prefix, out_dir, sizes, quick, metal=0.0, reuse=False):
    a_size, n_size, o_size = sizes
    if quick:
        a_size, n_size, o_size = max(a_size // 4, 256), max(n_size // 4, 256), max(o_size // 4, 256)
    t = time.time()
    alb, r1 = _load_or_bake(obj, f"{prefix}_{aid}_albedo", "DIFFUSE", a_size, out_dir, reuse, samples=4 if quick else 8, pass_filter={"COLOR"})
    rough, _ = _load_or_bake(obj, f"{prefix}_{aid}_rough", "ROUGHNESS", o_size, out_dir, reuse, samples=1 if quick else 4, colorspace="Non-Color")
    nrm, _ = _load_or_bake(obj, f"{prefix}_{aid}_normal", "NORMAL", n_size, out_dir, reuse, samples=4 if quick else 8, colorspace="Non-Color")
    ao, r_ao = _load_or_bake(obj, f"{prefix}_{aid}_ao", "AO", o_size, out_dir, reuse, samples=8 if quick else 32, colorspace="Non-Color")
    if not r_ao:
        _ao_floor(ao, AO_FLOOR)
    orm = ld.pack_orm(ao, rough, metal, os.path.join(out_dir, f"{prefix}_{aid}_orm.png"))
    if not r1:                                  # el AO al 35 % multiplicado en el albedo (brief F-3), solo al hornear de nuevo
        _mix_ao_into_albedo(alb, ao, 0.35)
    fm = ld.final_material(f"{prefix}_{aid}", alb, nrm, orm)
    for lay in [l.name for l in obj.data.uv_layers if l.name != "atlas"]:     # la caja de modelado no se exporta
        obj.data.uv_layers.remove(obj.data.uv_layers[lay])
    obj.data.materials.clear()
    obj.data.materials.append(fm)
    for p in obj.data.polygons:
        p.material_index = 0
    mem = mem_mb(a_size, a_size) + mem_mb(n_size, n_size) + mem_mb(o_size, o_size)
    log(f"{aid}: {round(time.time() - t)} s, {a_size}/{n_size}/{o_size}, {mem:.1f} MB{' (reutilizado)' if r1 else ''}")
    return mem


AO_FLOOR = 0.35   # mínimo de la AO de los atlas: Three.js multiplica la luz ambiente por ella; con 0 una cara en sombra sale negra


def _ao_floor(ao, lo):
    import numpy as np
    px = np.array(ao.pixels[:], dtype=np.float32).reshape(-1, 4)
    px[:, :3] = lo + (1.0 - lo) * px[:, :3]
    ao.pixels[:] = px.ravel()
    ao.save()


def _mix_ao_into_albedo(alb, ao, k):
    import numpy as np
    aw, ah = alb.size
    a = np.array(alb.pixels[:], dtype=np.float32).reshape(ah, aw, 4)
    ow, oh = ao.size
    o = np.array(ao.pixels[:], dtype=np.float32).reshape(oh, ow, 4)[..., 0]
    if (ow, oh) != (aw, ah):
        yi = (np.arange(ah) * oh // ah).clip(0, oh - 1)
        xi = (np.arange(aw) * ow // aw).clip(0, ow - 1)
        o = o[yi][:, xi]
    a[..., :3] *= (1 - k) + k * o[..., None]
    alb.pixels[:] = a.ravel()
    alb.save()


# ----------------------------------------------------------------------------------------------
# detalles, techo, interior, hierba y escombro: materiales repetibles + oclusión en colores de vértice (glTF COLOR_0)
# ----------------------------------------------------------------------------------------------
TILE_TEX = {   # material -> (textura repetible, tamaño m, rugosidad, metal, tinte)
    "concrete": ("T1_concrete.png", 3.0, 0.9, 0.0, (0.92, 0.92, 0.9)), "plaster": ("T2_plaster_int_2k.png", 2.4, 0.88, 0.0, (0.97, 0.96, 0.93)),
    "wood": ("T4_wood_weathered.png", 1.6, 0.8, 0.0, (1, 1, 1)), "wood_dark": ("W1_wood_dark_planks.png", 1.8, 0.8, 0.0, (1, 1, 1)),
    "wood_grey": ("W2_wood_grey_clapboard.png", 1.8, 0.82, 0.0, (1, 1, 1)), "brick": ("S1_brick_red_worn.png", 2.0, 0.85, 0.0, (1, 1, 1)),
    "tile": ("T3_roof_tile.png", 2.0, 0.75, 0.0, (1, 1, 1)), "metal_rust": ("M1_rust_metal.png", 1.2, 0.7, 0.3, (1, 1, 1)),
    "metal_paint": ("M1_rust_metal.png", 1.2, 0.6, 0.3, (0.62, 0.66, 0.62)), "roof_metal": ("R1_roof_corrugated_rust.png", 2.0, 0.65, 0.35, (1, 1, 1)),
    "roof_metal_light": ("R2_roof_corrugated_light.png", 2.0, 0.55, 0.4, (1, 1, 1)),
    # hospital (HOS_1): terrazo, azulejo, plafón y muros pintados (la pintura es el aplanado interior teñido)
    "terrazzo": ("T5_terrazo.png", 1.5, 0.32, 0.0, (1, 1, 1)), "tile_white": ("T6_azulejo_blanco.png", 0.6, 0.22, 0.0, (1, 1, 1)),
    "ceiling_tile": ("T7_plafon.png", 1.22, 0.92, 0.0, (1, 1, 1)),
    "paint_mint": ("T8_pintura_lisa.png", 2.0, 0.6, 0.0, (0.70, 0.88, 0.74)),
    "paint_green": ("T8_pintura_lisa.png", 2.0, 0.5, 0.0, (0.10, 0.34, 0.20)),
    "paint_white": ("T8_pintura_lisa.png", 2.0, 0.7, 0.0, (1.0, 1.0, 0.98)),
    "wood_varnish": ("T9_madera_barniz.png", 0.8, 0.35, 0.0, (1, 1, 1)),
    # granero con tienda (GRA_1): tabla roja, block, piso de barro y la pintura interior de la tienda (amarillo y zoclo azul)
    "wood_red": ("T10_tabla_roja.png", 2.4, 0.82, 0.0, (1, 1, 1)), "block": ("T11_block.png", 2.4, 0.9, 0.0, (1, 1, 1)),
    "tile_clay": ("T12_barro.png", 1.2, 0.55, 0.0, (1, 1, 1)),
    "paint_cream": ("T8_pintura_lisa.png", 2.0, 0.7, 0.0, (0.98, 0.88, 0.58)),
    "paint_navy": ("T8_pintura_lisa.png", 2.0, 0.6, 0.0, (0.10, 0.15, 0.34)),
    # sitio de telecom (COM_1): acero galvanizado (torre, malla, postes, charolas) y grava triturada de la plataforma
    "galvanized": ("T13_galvanizado.png", 1.0, 0.45, 1.0, (1, 1, 1)), "gravel": ("T14_grava.png", 1.2, 0.95, 0.0, (1, 1, 1)),
    # base militar (MIL_1 / MIL_2)
    "canvas": ("T15_lona.png", 1.0, 0.92, 0.0, (1, 1, 1)), "sandbag": ("T16_costal_pp.png", 0.6, 0.88, 0.0, (1, 1, 1)),
    "geotextile": ("T17_geotextil.png", 1.0, 0.95, 0.0, (1, 1, 1)), "wood_od": ("T18_madera_od.png", 1.2, 0.72, 0.0, (1, 1, 1)),
    "net": ("T19_camuflaje.png", 2.0, 0.9, 0.0, (1, 1, 1)), "plywood": ("T20_triplay.png", 1.22, 0.8, 0.0, (1, 1, 1)),
    "paint_od": ("T8_pintura_lisa.png", 2.0, 0.55, 0.1, (0.20, 0.22, 0.13)),
    "paint_tan": ("T8_pintura_lisa.png", 2.0, 0.55, 0.1, (0.56, 0.46, 0.30)),
    "rack_orange": ("T8_pintura_lisa.png", 2.0, 0.45, 0.1, (0.70, 0.19, 0.03)),
    "rack_blue": ("T8_pintura_lisa.png", 2.0, 0.45, 0.1, (0.03, 0.10, 0.38)),
}
# materiales del kit que se pintan con un repetible ajeno: el escombro (montones, trozos) con concreto; antes iba como color liso
# y en Three.js se leía como montones blancos de plástico (revisión de aceptación de B, verificada)
TILE_ALIAS = {"rubble": "concrete", "cladding": "metal_paint", "container": "metal_paint", "cladding_tan": "paint_tan"}   # lámina: cara interior repetible
# doble cara: láminas (lámina ondulada, tela, hierba) y la teja (piezas sueltas sin cara inferior: desde el ático se veía el cielo
# y el sol pasaba, porque Three.js no dibuja la cara trasera ni la usa para la sombra)
DOUBLE_SIDED = ("vegetation", "fabric", "roof_metal", "roof_metal_light", "tile", "linen", "wool_blue", "hay", "canvas", "net")


def vertex_ao(obj, samples, dist=0.5, inset=0.03, lift=0.001):
    """Hornea la oclusión ambiental a un atributo de color por esquina 'AO' (todos los objetos visibles ocluyen).
    - Distancia de AO corta (`dist`, en un world propio): la AO mide rincones y juntas. Sin world, dentro de un edificio cerrado
      todos los rayos chocaban con algún muro y el 95 % de las esquinas salía negro (el arreglo posterior las volvía cuadros).
    - Se hornea sobre una copia con las caras separadas, cada esquina movida `inset` m hacia el centro de su cara (máx. 25 %)
      y levantada `lift`: la esquina real suele caer en una unión (pie del muro contra la losa) y nacía tapada. Los valores se
      copian esquina por esquina a la malla original (mismo orden de esquinas)."""
    me = obj.data
    if "AO" not in me.color_attributes:
        me.color_attributes.new("AO", "BYTE_COLOR", "CORNER")
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new("_ao")
    sc.world.light_settings.distance = dist
    tmp_me = me.copy()
    bm = bmesh.new()
    bm.from_mesh(tmp_me)
    bmesh.ops.split_edges(bm, edges=bm.edges[:])
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal.copy()
        for v in f.verts:
            d = c - v.co
            ln = d.length
            if ln > 1e-6:
                v.co += d * (min(inset, 0.25 * ln) / ln)
            v.co += n * lift
    bm.to_mesh(tmp_me)
    bm.free()
    tmp = bpy.data.objects.new(obj.name + "_aotmp", tmp_me)
    tmp.matrix_world = obj.matrix_world
    for c in obj.users_collection:
        c.objects.link(tmp)
    hid = obj.hide_render
    obj.hide_render = True
    tmp_me.color_attributes.active_color = tmp_me.color_attributes["AO"]
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    bpy.ops.object.select_all(action="DESELECT")
    tmp.select_set(True)
    bpy.context.view_layer.objects.active = tmp
    bpy.ops.object.bake(type="AO", target="VERTEX_COLORS")
    import numpy as np
    src = tmp_me.color_attributes["AO"]
    col = np.zeros(len(src.data) * 4, dtype=np.float32)
    src.data.foreach_get("color", col)
    me.color_attributes["AO"].data.foreach_set("color", col)
    me.color_attributes.active_color = me.color_attributes["AO"]
    obj.hide_render = hid
    bpy.data.objects.remove(tmp)
    bpy.data.meshes.remove(tmp_me)


def fix_vertex_ao(obj, floor=0.25, neutral=0.85, dead=0.04):
    """AO por esquina -> por posición. Las esquinas que comparten posición (±1 mm) y orientación de cara (6 sentidos) toman el
    promedio de las válidas del grupo: sin bordes duros entre caras coplanares ni entre piezas que se tocan (antes cada cara
    reemplazaba sus esquinas incrustadas con su propio promedio y un mismo vértice quedaba con valores distintos: cuadros).
    Las esquinas incrustadas en otra pieza (AO <= dead) se descartan; un grupo sin esquinas válidas toma el promedio de su cara
    o un neutro; al final, un piso para que nada quede negro puro."""
    import numpy as np
    me = obj.data
    ca = me.color_attributes["AO"]
    col = np.zeros(len(ca.data) * 4, dtype=np.float32)
    ca.data.foreach_get("color", col)
    col = col.reshape(-1, 4)
    ao = col[:, 0].astype(np.float64)
    n = len(me.polygons)
    lt = np.zeros(n, dtype=np.int32)
    me.polygons.foreach_get("loop_total", lt)
    face = np.repeat(np.arange(n), lt)
    vi = np.zeros(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", vi)
    co = np.zeros(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    fn = np.zeros(n * 3, dtype=np.float64)
    me.polygons.foreach_get("normal", fn)
    fn = fn.reshape(-1, 3)
    ax = np.abs(fn).argmax(axis=1)
    obin = (ax * 2 + (fn[np.arange(n), ax] > 0))[face].astype(np.int64)
    q = np.round(co[vi] / 0.002).astype(np.int64)
    _, gid = np.unique(np.column_stack([q, obin]), axis=0, return_inverse=True)
    gid = gid.ravel()
    valid = ao > dead
    ng = int(gid.max()) + 1
    s = np.bincount(gid, weights=np.where(valid, ao, 0.0), minlength=ng)
    c = np.bincount(gid, weights=valid.astype(np.float64), minlength=ng)
    out = np.where(c > 0, s / np.maximum(c, 1), np.nan)[gid]
    bad = np.isnan(out)
    if bad.any():
        fs = np.bincount(face, weights=np.where(bad, 0.0, out), minlength=n)
        fc = np.bincount(face, weights=(~bad).astype(np.float64), minlength=n)
        out[bad] = np.where(fc > 0, fs / np.maximum(fc, 1), neutral)[face[bad]]
    out = floor + (1.0 - floor) * out
    col[:, 0] = col[:, 1] = col[:, 2] = out
    col[:, 3] = 1.0
    ca.data.foreach_set("color", col.ravel())
    return int((~valid).sum())


FABRIC_PALETTE = ((0.62, 0.60, 0.55), (0.36, 0.42, 0.52), (0.55, 0.31, 0.27), (0.46, 0.48, 0.36), (0.58, 0.52, 0.40),
                  (0.32, 0.32, 0.34), (0.60, 0.50, 0.30), (0.50, 0.44, 0.48))


def _fabric_tints(me, mat_idx, ls, lt):
    """Color por esquina para las caras de tela: cada pieza conexa (sábana, cortina, camisa) toma un color de FABRIC_PALETTE
    según su posición (determinista). Antes toda la tela era del mismo canela liso."""
    import numpy as np
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    out = np.ones((sum(lt), 3), dtype=np.float32)
    seen = set()
    for f in bm.faces:
        if f.material_index != mat_idx or f.index in seen:
            continue
        comp, stack = [], [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.material_index == mat_idx and h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        c = sum((g.calc_center_median() for g in comp), Vector()) / len(comp)
        tint = FABRIC_PALETTE[int(abs(c.x * 7.31 + c.y * 3.17 + c.z * 5.53) * 10) % len(FABRIC_PALETTE)]
        for g in comp:
            out[ls[g.index]:ls[g.index] + lt[g.index]] = tint
    bm.free()
    return out


def ue_materials(objs):
    """Kit UE5: un material por tipo con nombre común a los 7 modelos (BLK_<tipo>; el escombro usa BLK_concrete), sin fundir
    los colores lisos. COLOR_0 = AO por esquina (x color desteñido por pieza en la tela); el color, la rugosidad, el metal, la
    escala de los repetibles y el vidrio translúcido los pone el material de Unreal (kit_ue5/manifiesto.json). El material de
    Blender es solo un marcador con un color aproximado para la vista previa."""
    import numpy as np
    cache = {}

    def mat_for(name):
        key = TILE_ALIAS.get(name, name)
        if key not in cache:
            mat = bpy.data.materials.new(f"BLK_{key}")
            c = ld.BASE_COLORS.get(key, ((0.6, 0.6, 0.6), 0.8, 0.0))[0] if key not in TILE_TEX else TILE_TEX[key][4]
            mat.diffuse_color = (*c, 1.0)
            mat.use_backface_culling = key not in DOUBLE_SIDED and key not in ("glass",)
            cache[key] = mat
        return cache[key]
    for obj in objs:
        me = obj.data
        if "Float2" in me.uv_layers and "UVMap" not in me.uv_layers:
            me.uv_layers["Float2"].name = "UVMap"
        old = [m.name.split(".")[0] for m in me.materials]
        mi = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("material_index", mi)
        if "fabric" in old:
            ls = np.zeros(len(me.polygons), dtype=np.int32)
            me.polygons.foreach_get("loop_start", ls)
            lt = np.zeros(len(me.polygons), dtype=np.int32)
            me.polygons.foreach_get("loop_total", lt)
            ca = me.color_attributes["AO"]
            cols = np.zeros(len(ca.data) * 4, dtype=np.float32)
            ca.data.foreach_get("color", cols)
            cols = cols.reshape(-1, 4)
            k = old.index("fabric")
            sel = np.repeat(mi, lt) == k
            cols[sel, :3] *= _fabric_tints(me, k, ls, lt)[sel]
            ca.data.foreach_set("color", cols.ravel())
        new = [mat_for(nm) for nm in old]
        uniq = []
        for m in new:
            if m not in uniq:
                uniq.append(m)
        remap = np.array([uniq.index(m) for m in new], dtype=np.int32)
        me.materials.clear()
        for m in uniq:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", remap[mi])
        me.update()
    return sorted(m.name for m in cache.values())


def tileable_materials(objs, prefix, uv_unit):
    """Sustituye los materiales de `objs` por repetibles a escala real (canal 'UVMap' de caja a `uv_unit` m por unidad) y funde
    los de color liso en un solo material 'liso' cuyo color va en COLOR_0 (color x AO). COLOR_0 multiplica el color base en glTF."""
    import numpy as np
    cache = {}

    def mat_for(name):
        # colores lisos: 'glass' aparte (oscuro, rugosidad 0,1: con la del liso las esquirlas parecían cartulina blanca); el resto en
        # un solo 'liso' de doble cara (tela, ropa tendida y hierba lo necesitan; en piezas cerradas la cara trasera no se ve)
        name = TILE_ALIAS.get(name, name)
        key = name if name in TILE_TEX else ("glass" if name == "glass" else "liso")
        if key in cache:
            return cache[key]
        mat = bpy.data.materials.new(f"{prefix}_t_{key}")
        nb = ld.NB(mat)
        out = nb.n("ShaderNodeOutputMaterial")
        bsdf = nb.n("ShaderNodeBsdfPrincipled")
        nb.link(bsdf.outputs[0], out.inputs[0])
        vc = nb.n("ShaderNodeVertexColor", layer_name="AO")
        if key in TILE_TEX:
            fn, size, rough, metal, tint = TILE_TEX[key]
            uv0 = nb.n("ShaderNodeUVMap", uv_map="UVMap")
            t = nb.n("ShaderNodeTexImage")
            t.image = ld._img(os.path.join(ld.TEX, fn))
            sc = nb.n("ShaderNodeMapping")
            sc.inputs["Scale"].default_value = (uv_unit / size, uv_unit / size, 1)
            nb.link(uv0.outputs[0], sc.inputs[0])
            nb.link(sc.outputs[0], t.inputs[0])
            col = nb.mix(1.0, t.outputs[0], vc.outputs[0], "MULTIPLY")
            col = nb.mix(1.0, col, (*[min(c, 1.0) for c in tint], 1.0), "MULTIPLY")
            nb.link(col, bsdf.inputs["Base Color"])
        else:
            rough, metal = (0.1, 0.0) if key == "glass" else (0.8, 0.0)
            nb.link(vc.outputs[0], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        mat.use_backface_culling = key in TILE_TEX and key not in DOUBLE_SIDED
        cache[key] = mat
        return mat
    for obj in objs:
        me = obj.data
        if "Float2" in me.uv_layers and "UVMap" not in me.uv_layers:
            me.uv_layers["Float2"].name = "UVMap"
        old = [m.name.split(".")[0] for m in me.materials]
        # colores lisos -> COLOR_0 = color x AO (por esquina)
        ca = me.color_attributes["AO"]
        cols = np.zeros(len(ca.data) * 4, dtype=np.float32)
        ca.data.foreach_get("color", cols)
        cols = cols.reshape(-1, 4)
        mi = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("material_index", mi)
        ls = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("loop_start", ls)
        lt = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("loop_total", lt)
        loop_mat = np.repeat(mi, lt)
        for k, nm in enumerate(old):
            if TILE_ALIAS.get(nm, nm) in TILE_TEX:
                continue
            c, _, _ = ld.BASE_COLORS.get(nm, ((0.5, 0.5, 0.5), 0.8, 0.0))
            sel = loop_mat == k
            if nm == "fabric":                         # ropa tendida, cortinas, colchones: un color desteñido por pieza
                cols[sel, :3] *= _fabric_tints(me, k, ls, lt)[sel]
                continue
            cols[sel, :3] *= np.array(c, dtype=np.float32)
        ca.data.foreach_set("color", cols.ravel())
        new = [mat_for(nm) for nm in old]
        uniq = []
        for m in new:
            if m not in uniq:
                uniq.append(m)
        remap = np.array([uniq.index(m) for m in new], dtype=np.int32)
        me.materials.clear()
        for m in uniq:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", remap[mi])
        me.update()
    return sorted(m.name for m in cache.values())


def main():
    argv = sys.argv
    bid = argv[argv.index("--id") + 1] if "--id" in argv else "APT_A_5p"
    quick = "--quick" in argv
    reuse = "--reuse" in argv
    ue = "--ue" in argv
    out_tex = os.path.join(ENT, "texturas_ue" if ue else "texturas", bid if not quick else bid + "_quick")
    os.makedirs(out_tex, exist_ok=True)
    reset_scene()
    t0 = time.time()
    if ue:
        ab.SKIRT_TERRAIN = False
    res = builders.build(bid)
    cfg = res["cfg"]
    prefix = bid
    g = lambda k: res.get(k, [])  # noqa: E731
    shell = g("Shell")[0]
    dmg = {o.name.split("_Damage_")[-1]: o for o in g("Damage")}
    roof = g("Roof")[0]
    det = join(g("Details") + [dmg.get("Details"), dmg.get("Shell")], f"{prefix}_Details")
    inter = join(g("Interior") + [dmg.get("Interior")], f"{prefix}_Interior")
    furn = join(g("Furniture"), f"{prefix}_Furniture") if g("Furniture") else None   # mobiliario en malla propia (hospital)
    skirt = g("Skirt")[0] if g("Skirt") else None        # sin terreno (--ue) las cabañas no tienen nada en la base
    log("construido", round(time.time() - t0), "s; tris", tri_count([o for o in (shell, det, inter, roof, skirt, furn) if o]))
    # caras apoyadas en el terreno (cara inferior de la losa de desplante, pies de columna): nunca se ven y ocupaban medio atlas
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    kill = [f for f in bm.faces if f.normal.z < -0.9 and f.calc_center_median().z < 0.02]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(shell.data)
    bm.free()
    log("caras de apoyo retiradas:", len(kill))
    import coplanar                                   # z-fighting: borra caras cubiertas por otra coplanar, hunde 3 mm las parciales
    log("coplanares (borradas, m2, hundidas):", coplanar.dedupe([o for o in (shell, det, inter, roof, furn) if o is not None], log=log))
    # oclusores: techo e interior (tabiques, puertas, escaleras). Sin el interior, la cara interior de un muro exterior veía el cielo
    # cruzando el cuarto y las ventanas de enfrente, iba al atlas exterior y salía con AO ~0 (cuartos negros en Three.js) o con la
    # textura de fachada. Los detalles no tapan: barandales, letreros y cables delante de un canto de losa no lo vuelven "interior"
    ext, intr = ld.split_exterior(shell, others=[roof, inter], footprint=cfg.get("exterior_footprint"))
    bpy.data.objects.remove(shell)
    short = "_".join(bid.split("_")[:2])
    gfile = os.path.join(ld.TEX, "graffiti", f"G_{short}_mapa.json")
    has_g = os.path.exists(gfile)                         # las cabañas no llevan panel de grafiti
    band_top = cfg.get("band_top", cfg["h"][0] + ab.GROUND + 0.7) if has_g else -1.0
    main_o, rest_o = split_by(ext, lambda c, n: n.y < -0.5 or c.z < band_top, f"{prefix}_WallsMain", f"{prefix}_WallsRest")
    inter = join([inter, intr], f"{prefix}_Interior")
    if ue:                                               # sin terreno: lo que queda en la base es escombro exterior suelto
        sand_o, loose_o = None, skirt
        if skirt is not None:
            skirt.name = f"{prefix}_SkirtLoose"
    else:
        # la base: el terreno de arena va a su propio atlas; hierba, escombro y varillas pasan al grupo de detalles
        sand_idx = [i for i, m in enumerate(skirt.data.materials) if m and m.name.split(".")[0] == "sand"]
        sand_o, loose_o = _split_by_material(skirt, sand_idx, f"{prefix}_Sand", f"{prefix}_SkirtLoose")
        # el terreno es un campo de alturas: el recálculo de normales de una malla abierta deja islas boca abajo, que en glTF
        # (una sola cara) se verían como agujeros desde arriba
        bm = bmesh.new()
        bm.from_mesh(sand_o.data)
        down = [f for f in bm.faces if f.normal.z < -0.05]
        bmesh.ops.reverse_faces(bm, faces=down)
        bm.to_mesh(sand_o.data)
        bm.free()
        log("arena: caras volteadas hacia arriba", len(down))
    atlas_objs = [(main_o, "walls_main"), (rest_o, "walls_rest")] + ([] if ue else [(sand_o, "skirt")])
    log("split ok", round(time.time() - t0), "s")
    gb = cfg.get("graffiti_bounds") or (cfg["xs"][0] - ab.COL_CORNER / 2, cfg["xs"][-1] + ab.COL_CORNER / 2,
                                        cfg["ys"][0] - ab.COL_CORNER / 2, cfg["ys"][-1] + ab.COL_CORNER / 2)
    gmap = ld.graffiti_map(f"G_{short}", json.load(open(gfile)), *gb) if has_g else None
    for nm in sorted({m.name for o, _ in atlas_objs for m in o.data.materials}):
        ld.lookdev_material(nm, seed=cfg["seed"], gmap=gmap, band_top=band_top, dust_h=0.12 if ue else 0.35, **cfg.get("lookdev", {}))
    for o, _ in atlas_objs:
        t = time.time()
        ld.unwrap(o)
        log("unwrap", o.name, round(time.time() - t), "s", len(o.data.polygons), "caras")
    nb = scale_band_islands(main_o, band_top, BAND_SCALE) if has_g else 0
    log("islas de banda ampliadas:", nb)
    mem = 0.0
    sizes = SIZES_CAB if bid.startswith("CAB") else (SIZES_MUE if bid.startswith("MUE") else SIZES)   # GRA: 4K (con 8K y 1,1 M de tris se quedaba sin memoria)
    for o, aid in atlas_objs:
        mem += bake_atlas(o, aid, prefix, out_tex, sizes[aid], quick, reuse=reuse)
    # oclusión por vértice + materiales repetibles
    loose = [o for o in (det, roof, inter, loose_o, furn) if o is not None and len(o.data.polygons)]
    for o in loose:
        t = time.time()
        vertex_ao(o, 8 if quick else 64)
        nfix = fix_vertex_ao(o)
        log("AO por vértice", o.name, round(time.time() - t), "s; esquinas incrustadas corregidas:", nfix)
    # el interior se reproyecta a 2 m por unidad para compartir materiales con los detalles (techo de 14 materiales)
    bm = bmesh.new()
    bm.from_mesh(inter.data)
    box_uv_bm(bm, 2.0)
    bm.to_mesh(inter.data)
    bm.free()
    mats = ue_materials(loose) if ue else tileable_materials(loose, prefix, 2.0)
    mats_i = []
    tex_used = {TILE_TEX[k][0] for k in TILE_TEX}
    for fn in tex_used:                               # tamaño real de cada repetible (el aplanado interior es de 2048²)
        w, h = ld._img(os.path.join(ld.TEX, fn)).size
        mem += mem_mb(w, h)
    log("materiales repetibles:", mats, mats_i)
    log(f"memoria de texturas decodificada ≈ {mem:.0f} MB")
    blend = os.path.join(ENT, "blender", f"{bid}{'_ue' if ue else ''}{'_quick' if quick else ''}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("guardado", blend, "total", round(time.time() - t0), "s")
    if ue:                                               # focos colgando del vestido interior: posiciones para luces del motor
        bulbs = res.get("stats", {}).get("interior_dress", {}).get("bulb_pos", [])
        json.dump(dict(unidades="m, ejes de Blender (z arriba)", focos=bulbs), open(os.path.join(out_tex, "focos.json"), "w"))
        prox = res.get("stats", {}).get("proxies")
        if prox:                                         # cajas de colisión del mobiliario (lo usa export_ue5)
            json.dump(dict(unidades="m, ejes de Blender", cajas=prox), open(os.path.join(out_tex, "proxies.json"), "w"))
    json.dump(dict(tris=tri_count([o for o, _ in atlas_objs] + loose), mem_mb=round(mem, 1), materials=mats + mats_i),
              open(os.path.join(out_tex, "bake_info.json"), "w"), indent=1)


def _split_by_material(obj, idx, name_true, name_false):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    mask = [f.material_index in idx for f in bm.faces]
    me_t, me_f = ld._split_mesh(bm, mask)
    bm.free()
    res = []
    for me, nm in ((me_t, name_true), (me_f, name_false)):
        for m in obj.data.materials:
            me.materials.append(m)
        o = bpy.data.objects.new(nm, me)
        o.matrix_world = obj.matrix_world
        for c in obj.users_collection:
            c.objects.link(o)
        res.append(o)
    bpy.data.objects.remove(obj)
    return res


if __name__ == "__main__":
    main()

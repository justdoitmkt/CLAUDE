"""bake_apt.py — horneado final de un edificio de departamentos (fase F) y materiales glTF.

Uso: /root/blk-venv/bin/python bake_apt.py --id APT_A_5p [--quick] [--blend]
  --quick : tamaños 1/4 y pocas muestras (prueba del flujo completo).
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
    "walls_main": (4096, 1024, 1024), "walls_rest": (3072, 1024, 1024), "details": (2048, 2048, 1024),
    "roof": (2048, 1024, 1024), "skirt": (2048, 512, 512),
}
SIZES_CAB = {   # cabañas: superficie ~1/4 de un edificio -> mitad de resolución en el atlas principal
    "walls_main": (2048, 1024, 1024), "walls_rest": (2048, 1024, 1024), "details": (2048, 1024, 1024),
    "roof": (2048, 1024, 1024), "skirt": (2048, 512, 512),
}
INTERIOR_AO = 1024
BAND_SCALE = 1.4


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
    alb, r1 = _load_or_bake(obj, f"{prefix}_{aid}_albedo", "DIFFUSE", a_size, out_dir, reuse, samples=4 if quick else 16, pass_filter={"COLOR"})
    rough, _ = _load_or_bake(obj, f"{prefix}_{aid}_rough", "ROUGHNESS", o_size, out_dir, reuse, samples=1 if quick else 4, colorspace="Non-Color")
    nrm, _ = _load_or_bake(obj, f"{prefix}_{aid}_normal", "NORMAL", n_size, out_dir, reuse, samples=4 if quick else 16, colorspace="Non-Color")
    ao, _ = _load_or_bake(obj, f"{prefix}_{aid}_ao", "AO", o_size, out_dir, reuse, samples=8 if quick else 48, colorspace="Non-Color")
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
    "concrete": ("T1_concrete.png", 3.0, 0.9, 0.0, (0.92, 0.92, 0.9)), "plaster": ("T2_old_plaster_paint.png", 2.4, 0.88, 0.0, (1.0, 0.97, 0.92)),
    "wood": ("T4_wood_weathered.png", 1.6, 0.8, 0.0, (1, 1, 1)), "wood_dark": ("W1_wood_dark_planks.png", 1.8, 0.8, 0.0, (1, 1, 1)),
    "wood_grey": ("W2_wood_grey_clapboard.png", 1.8, 0.82, 0.0, (1, 1, 1)), "brick": ("S1_brick_red_worn.png", 2.0, 0.85, 0.0, (1, 1, 1)),
    "tile": ("T3_roof_tile.png", 2.0, 0.75, 0.0, (1, 1, 1)), "metal_rust": ("M1_rust_metal.png", 1.2, 0.7, 0.3, (1, 1, 1)),
    "metal_paint": ("M1_rust_metal.png", 1.2, 0.6, 0.3, (0.62, 0.66, 0.62)), "roof_metal": ("R1_roof_corrugated_rust.png", 2.0, 0.65, 0.35, (1, 1, 1)),
    "roof_metal_light": ("R2_roof_corrugated_light.png", 2.0, 0.55, 0.4, (1, 1, 1)),
}
DOUBLE_SIDED = ("vegetation", "fabric", "roof_metal", "roof_metal_light")


def vertex_ao(obj, samples):
    """Hornea la oclusión ambiental a un atributo de color por esquina 'AO' (todos los objetos de la escena ocluyen)."""
    me = obj.data
    if "AO" not in me.color_attributes:
        me.color_attributes.new("AO", "BYTE_COLOR", "CORNER")
    me.color_attributes.active_color = me.color_attributes["AO"]
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type="AO", target="VERTEX_COLORS")


def fix_vertex_ao(obj, floor=0.25, neutral=0.85, dead=0.04):
    """Los vértices incrustados en otra pieza (muro que entra en la losa, marco dentro del vano) hornean AO = 0 (negro) y esa
    oscuridad se interpola por toda la cara. Se descartan esas esquinas: toman el promedio de las esquinas válidas de su cara o
    un valor neutro si no hay ninguna; después se aplica un piso para que nada quede negro puro."""
    import numpy as np
    me = obj.data
    ca = me.color_attributes["AO"]
    col = np.zeros(len(ca.data) * 4, dtype=np.float32)
    ca.data.foreach_get("color", col)
    col = col.reshape(-1, 4)
    ao = col[:, 0].copy()
    n = len(me.polygons)
    ls = np.zeros(n, dtype=np.int32)
    lt = np.zeros(n, dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    face = np.repeat(np.arange(n), lt)
    valid = ao > dead
    s = np.bincount(face, weights=np.where(valid, ao, 0.0), minlength=n)
    c = np.bincount(face, weights=valid.astype(np.float64), minlength=n)
    mean = np.where(c > 0, s / np.maximum(c, 1), neutral)
    bad = ~valid
    ao[bad] = mean[face[bad]]
    ao = floor + (1.0 - floor) * ao
    col[:, 0] = col[:, 1] = col[:, 2] = ao
    col[:, 3] = 1.0
    ca.data.foreach_set("color", col.ravel())
    return int(bad.sum())


def tileable_materials(objs, prefix, uv_unit):
    """Sustituye los materiales de `objs` por repetibles a escala real (canal 'UVMap' de caja a `uv_unit` m por unidad) y funde
    los de color liso en un solo material 'liso' cuyo color va en COLOR_0 (color x AO). COLOR_0 multiplica el color base en glTF."""
    import numpy as np
    cache = {}

    def mat_for(name):
        key = name if name in TILE_TEX else ("liso_2c" if name in DOUBLE_SIDED else "liso")
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
            rough, metal = 0.8, 0.0
            nb.link(vc.outputs[0], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        mat.use_backface_culling = key != "liso_2c" and key not in DOUBLE_SIDED     # láminas (lámina ondulada, tela, hierba)
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
            if nm in TILE_TEX:
                continue
            c, _, _ = ld.BASE_COLORS.get(nm, ((0.5, 0.5, 0.5), 0.8, 0.0))
            sel = loop_mat == k
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
    out_tex = os.path.join(ENT, "texturas", bid if not quick else bid + "_quick")
    os.makedirs(out_tex, exist_ok=True)
    reset_scene()
    t0 = time.time()
    res = builders.build(bid)
    cfg = res["cfg"]
    prefix = bid
    g = lambda k: res.get(k, [])  # noqa: E731
    shell = g("Shell")[0]
    dmg = {o.name.split("_Damage_")[-1]: o for o in g("Damage")}
    roof = g("Roof")[0]
    det = join(g("Details") + [dmg.get("Details"), dmg.get("Shell")], f"{prefix}_Details")
    inter = join(g("Interior") + [dmg.get("Interior")], f"{prefix}_Interior")
    skirt = g("Skirt")[0]
    log("construido", round(time.time() - t0), "s; tris", tri_count([shell, det, inter, roof, skirt]))
    # caras apoyadas en el terreno (cara inferior de la losa de desplante, pies de columna): nunca se ven y ocupaban medio atlas
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    kill = [f for f in bm.faces if f.normal.z < -0.9 and f.calc_center_median().z < 0.02]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(shell.data)
    bm.free()
    log("caras de apoyo retiradas:", len(kill))
    # solo el techo cuenta como oclusor: barandales, letreros y cables delante de un canto de losa no lo vuelven "interior"
    ext, intr = ld.split_exterior(shell, others=[roof])
    bpy.data.objects.remove(shell)
    short = "_".join(bid.split("_")[:2])
    gfile = os.path.join(ld.TEX, "graffiti", f"G_{short}_mapa.json")
    has_g = os.path.exists(gfile)                         # las cabañas no llevan panel de grafiti
    band_top = (cfg["h"][0] + ab.GROUND + 0.7) if has_g else -1.0
    main_o, rest_o = split_by(ext, lambda c, n: n.y < -0.5 or c.z < band_top, f"{prefix}_WallsMain", f"{prefix}_WallsRest")
    inter = join([inter, intr], f"{prefix}_Interior")
    # la base: el terreno de arena va a su propio atlas; hierba, escombro y varillas pasan al grupo de detalles
    sand_idx = [i for i, m in enumerate(skirt.data.materials) if m and m.name.split(".")[0] == "sand"]
    sand_o, loose_o = _split_by_material(skirt, sand_idx, f"{prefix}_Sand", f"{prefix}_SkirtLoose")
    log("split ok", round(time.time() - t0), "s")
    gmap = ld.graffiti_map(f"G_{short}", json.load(open(gfile)),
                           cfg["xs"][0] - ab.COL_CORNER / 2, cfg["xs"][-1] + ab.COL_CORNER / 2,
                           cfg["ys"][0] - ab.COL_CORNER / 2, cfg["ys"][-1] + ab.COL_CORNER / 2) if has_g else None
    for nm in sorted({m.name for o in (main_o, rest_o, sand_o) for m in o.data.materials}):
        ld.lookdev_material(nm, seed=cfg["seed"], gmap=gmap, band_top=band_top, **cfg.get("lookdev", {}))
    for o in (main_o, rest_o, sand_o):
        t = time.time()
        ld.unwrap(o)
        log("unwrap", o.name, round(time.time() - t), "s", len(o.data.polygons), "caras")
    nb = scale_band_islands(main_o, band_top, BAND_SCALE) if has_g else 0
    log("islas de banda ampliadas:", nb)
    mem = 0.0
    sizes = SIZES if bid.startswith("APT") else SIZES_CAB
    for o, aid in ((main_o, "walls_main"), (rest_o, "walls_rest"), (sand_o, "skirt")):
        mem += bake_atlas(o, aid, prefix, out_tex, sizes[aid], quick, reuse=reuse)
    # oclusión por vértice + materiales repetibles
    loose = [o for o in (det, roof, inter, loose_o) if o is not None and len(o.data.polygons)]
    for o in loose:
        t = time.time()
        vertex_ao(o, 8 if quick else 32)
        nfix = fix_vertex_ao(o)
        log("AO por vértice", o.name, round(time.time() - t), "s; esquinas incrustadas corregidas:", nfix)
    # el interior se reproyecta a 2 m por unidad para compartir materiales con los detalles (techo de 14 materiales)
    bm = bmesh.new()
    bm.from_mesh(inter.data)
    box_uv_bm(bm, 2.0)
    bm.to_mesh(inter.data)
    bm.free()
    mats = tileable_materials(loose, prefix, 2.0)
    mats_i = []
    tex_used = {TILE_TEX[k][0] for k in TILE_TEX}
    mem += len(tex_used) * mem_mb(1024, 1024)
    log("materiales repetibles:", mats, mats_i)
    log(f"memoria de texturas decodificada ≈ {mem:.0f} MB")
    blend = os.path.join(ENT, "blender", f"{bid}{'_quick' if quick else ''}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("guardado", blend, "total", round(time.time() - t0), "s")
    json.dump(dict(tris=tri_count([main_o, rest_o, sand_o] + loose), mem_mb=round(mem, 1), materials=mats + mats_i),
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

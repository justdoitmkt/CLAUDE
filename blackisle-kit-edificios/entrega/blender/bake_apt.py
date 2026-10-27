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
import lookdev as ld  # noqa: E402
from kit.common import reset_scene, tri_count  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))

SIZES = {   # atlas: (albedo, normal, orm)
    "walls_main": (4096, 1024, 1024), "walls_rest": (3072, 1024, 1024), "details": (2048, 2048, 1024),
    "roof": (2048, 1024, 1024), "skirt": (1024, 512, 512),
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


def bake_atlas(obj, aid, prefix, out_dir, sizes, quick, metal=0.0):
    a_size, n_size, o_size = sizes
    if quick:
        a_size, n_size, o_size = max(a_size // 4, 256), max(n_size // 4, 256), max(o_size // 4, 256)
    t = time.time()
    alb = ld.bake(obj, f"{prefix}_{aid}_albedo", "DIFFUSE", a_size, out_dir, samples=4 if quick else 16, pass_filter={"COLOR"})
    rough = ld.bake(obj, f"{prefix}_{aid}_rough", "ROUGHNESS", o_size, out_dir, samples=1 if quick else 4, colorspace="Non-Color")
    nrm = ld.bake(obj, f"{prefix}_{aid}_normal", "NORMAL", n_size, out_dir, samples=4 if quick else 16, colorspace="Non-Color")
    ao = ld.bake(obj, f"{prefix}_{aid}_ao", "AO", o_size, out_dir, samples=8 if quick else 48, colorspace="Non-Color")
    orm = ld.pack_orm(ao, rough, metal, os.path.join(out_dir, f"{prefix}_{aid}_orm.png"))
    # el AO al 35 % multiplicado en el albedo (brief F-3)
    _mix_ao_into_albedo(alb, ao, 0.35)
    fm = ld.final_material(f"{prefix}_{aid}", alb, nrm, orm)
    obj.data.materials.clear()
    obj.data.materials.append(fm)
    for p in obj.data.polygons:
        p.material_index = 0
    mem = mem_mb(a_size, a_size) + mem_mb(n_size, n_size) + mem_mb(o_size, o_size)
    log(f"{aid}: {round(time.time() - t)} s, {a_size}/{n_size}/{o_size}, {mem:.1f} MB")
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


INTERIOR_TEX = {   # material -> (textura repetible, tamaño m, rugosidad, metal, tinte)
    "concrete": ("T1_concrete.png", 3.0, 0.9, 0.0, (0.92, 0.92, 0.9)), "plaster": ("T2_old_plaster_paint.png", 2.4, 0.88, 0.0, (1.0, 0.97, 0.92)),
    "wood": ("T4_wood_weathered.png", 1.6, 0.8, 0.0, (1, 1, 1)), "wood_dark": ("W1_wood_dark_planks.png", 1.8, 0.8, 0.0, (1, 1, 1)),
    "metal_rust": ("M1_rust_metal.png", 1.2, 0.7, 0.3, (1, 1, 1)), "metal_paint": ("M1_rust_metal.png", 1.2, 0.6, 0.3, (0.6, 0.65, 0.6)),
}


def interior_materials(obj, prefix, ao_img):
    """Sustituye los materiales del interior por repetibles (canal 'UVMap' de caja) + AO del canal 'lightmap'."""
    new = []
    for m in obj.data.materials:
        name = m.name.split(".")[0]
        tex = INTERIOR_TEX.get(name)
        mat = bpy.data.materials.new(f"{prefix}_int_{name}")
        nb = ld.NB(mat)
        out = nb.n("ShaderNodeOutputMaterial")
        bsdf = nb.n("ShaderNodeBsdfPrincipled")
        nb.link(bsdf.outputs[0], out.inputs[0])
        uv0 = nb.n("ShaderNodeUVMap", uv_map="UVMap")
        uv1 = nb.n("ShaderNodeUVMap", uv_map="lightmap")
        if tex:
            fn, size, rough, metal, tint = tex
            t = nb.n("ShaderNodeTexImage")
            t.image = ld._img(os.path.join(ld.TEX, fn))
            sc = nb.n("ShaderNodeMapping")
            sc.inputs["Scale"].default_value = (3.0 / size, 3.0 / size, 1)     # UVMap de caja hecho a 3 m por unidad
            nb.link(uv0.outputs[0], sc.inputs[0])
            nb.link(sc.outputs[0], t.inputs[0])
            col = nb.mix(1.0, t.outputs[0], (*tint, 1.0), "MULTIPLY")
            nb.link(col, bsdf.inputs["Base Color"])
        else:
            c, rough, metal = ld.BASE_COLORS.get(name, ((0.5, 0.5, 0.5), 0.8, 0.0))
            bsdf.inputs["Base Color"].default_value = (*c, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        ta = nb.n("ShaderNodeTexImage")
        ta.image = ao_img
        ta.image.colorspace_settings.name = "Non-Color"
        nb.link(uv1.outputs[0], ta.inputs[0])
        sp = nb.n("ShaderNodeSeparateColor")
        nb.link(ta.outputs[0], sp.inputs[0])
        grp = bpy.data.node_groups.get("glTF Material Output")
        if grp is None:
            grp = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
            grp.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        gn = nb.n("ShaderNodeGroup")
        gn.node_tree = grp
        nb.link(sp.outputs[0], gn.inputs["Occlusion"])
        new.append(mat)
    obj.data.materials.clear()
    for m in new:
        obj.data.materials.append(m)


def main():
    argv = sys.argv
    bid = argv[argv.index("--id") + 1] if "--id" in argv else "APT_A_5p"
    quick = "--quick" in argv
    out_tex = os.path.join(ENT, "texturas", bid if not quick else bid + "_quick")
    os.makedirs(out_tex, exist_ok=True)
    reset_scene()
    t0 = time.time()
    res = ab.build_apt_a()
    cfg = res["cfg"]
    prefix = bid
    g = lambda k: res.get(k, [])
    shell = g("Shell")[0]
    dmg = {o.name.split("_Damage_")[-1]: o for o in g("Damage")}
    roof = g("Roof")[0]
    det = join(g("Details") + [dmg.get("Details"), dmg.get("Shell")], f"{prefix}_Details")
    inter = join(g("Interior") + [dmg.get("Interior")], f"{prefix}_Interior")
    skirt = g("Skirt")[0]
    log("construido", round(time.time() - t0), "s; tris", tri_count([shell, det, inter, roof, skirt]))
    # exterior / interior de la carcasa (el techo y los detalles tapan)
    ext, intr = ld.split_exterior(shell, others=[det, inter, roof])
    bpy.data.objects.remove(shell)
    band_top = cfg["h"][0] + ab.GROUND + 0.7
    main_o, rest_o = split_by(ext, lambda c, n: n.y < -0.5 or c.z < band_top, f"{prefix}_WallsMain", f"{prefix}_WallsRest")
    inter = join([inter, intr], f"{prefix}_Interior")
    log("split ok", round(time.time() - t0), "s")
    # materiales de look-dev
    gmap = ld.graffiti_map(f"G_{bid.split('_')[0]}_{bid.split('_')[1]}",
                           json.load(open(os.path.join(ld.TEX, "graffiti", f"G_{bid.split('_')[0]}_{bid.split('_')[1]}_mapa.json"))),
                           cfg["xs"][0] - ab.COL_CORNER / 2, cfg["xs"][-1] + ab.COL_CORNER / 2,
                           cfg["ys"][0] - ab.COL_CORNER / 2, cfg["ys"][-1] + ab.COL_CORNER / 2)
    for nm in sorted({m.name for o in (main_o, rest_o, det, roof, skirt, inter) for m in o.data.materials}):
        ld.lookdev_material(nm, seed=cfg["seed"], gmap=gmap, band_top=band_top)
    # UV únicas
    for o in (main_o, rest_o, det, roof, skirt):
        t = time.time()
        ld.unwrap(o)
        log("unwrap", o.name, round(time.time() - t), "s")
    nb = scale_band_islands(main_o, band_top, BAND_SCALE)
    log("islas de banda ampliadas:", nb)
    mem = 0.0
    for o, aid in ((main_o, "walls_main"), (rest_o, "walls_rest"), (det, "details"), (roof, "roof"), (skirt, "skirt")):
        mem += bake_atlas(o, aid, prefix, out_tex, SIZES[aid], quick)
    # interior: AO en canal 'lightmap' + materiales repetibles
    ld.unwrap(inter, uv_name="lightmap", make_active=False)
    inter.data.uv_layers["UVMap"].active_render = True
    aos = INTERIOR_AO if not quick else 256
    ao = ld.bake(inter, f"{prefix}_interior_ao", "AO", aos, out_tex, samples=8 if quick else 48, colorspace="Non-Color", uv_name="lightmap")
    interior_materials(inter, prefix, ao)
    mem += mem_mb(aos, aos) + 4 * mem_mb(1024, 1024)
    log(f"memoria de texturas decodificada ≈ {mem:.0f} MB")
    blend = os.path.join(ENT, "blender", f"{bid}{'_quick' if quick else ''}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("guardado", blend, "total", round(time.time() - t0), "s")
    json.dump(dict(tris=tri_count([main_o, rest_o, det, inter, roof, skirt]), mem_mb=round(mem, 1)),
              open(os.path.join(out_tex, "bake_info.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

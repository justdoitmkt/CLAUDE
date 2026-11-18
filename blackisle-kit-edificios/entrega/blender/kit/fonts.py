"""kit/fonts.py — texto 3D con tipografías reales (todas SIL Open Font License, en blender/fonts/):
  stencil  → Saira Stencil One (estarcido militar moderno: cajas de munición, LOT, avisos pintados en muros, capacidades)
  stencil2 → Allerta Stencil (estarcido sans más angosto, para marcas chicas de lote)
  sign     → Overpass (derivada de Highway Gothic: letreros y placas de señalización)
Uso:
    from kit.fonts import text_font
    text_font(mb, "AMMO", 0.034, 0.0006, "paint_yellow", M, font="stencil", align="CENTER", res=3)
M = plano de la superficie (XY local, +Z hacia afuera); el texto sobresale `depth` desde z = 0 (se hunde 0,3 mm para no
quedar flotando). Devuelve el ancho del texto en metros.
"""
import os

import bmesh
import bpy
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.abspath(os.path.join(HERE, "..", "fonts"))
FONTS = {"stencil": "SairaStencilOne-Regular.ttf", "stencil2": "AllertaStencil-Regular.ttf",
         "stencil_serif": "StardosStencil-Bold.ttf", "sign": "Overpass-VF.ttf"}


def get_font(name):
    path = os.path.join(FONT_DIR, FONTS[name])
    return bpy.data.fonts.load(path, check_existing=True)


def text_font(mb, s, size, depth, mat, M=None, font="stencil", align="CENTER", res=3, bold=False, spacing=1.0, sink=0.0003):
    cu = bpy.data.curves.new("_txt", "FONT")
    cu.body = s
    cu.font = get_font(font)
    cu.size = size
    cu.extrude = (depth + sink) / 2
    cu.align_x = align
    cu.space_character = spacing
    cu.resolution_u = res
    if bold:
        cu.offset = size * 0.018
    ob = bpy.data.objects.new("_txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    M2 = (M if M is not None else Matrix()) @ Matrix.Translation((0, 0, (depth + sink) / 2 - sink))
    vs = [mb.bm.verts.new(M2 @ v.co) for v in me.vertices]
    xs = [v.co.x for v in me.vertices] or [0.0]
    mi = mb.mi(mat)
    for p in me.polygons:
        try:
            f = mb.bm.faces.new([vs[i] for i in p.vertices])
            f.material_index = mi
        except ValueError:
            pass
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bmesh.ops.remove_doubles(mb.bm, verts=vs, dist=size * 1e-4)
    vs = [v for v in vs if v.is_valid]
    edges = list({e for v in vs for e in v.link_edges})
    bmesh.ops.dissolve_degenerate(mb.bm, dist=size * 1e-4, edges=edges)
    return max(xs) - min(xs)

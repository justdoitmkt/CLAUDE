"""Genera texturas/T2_plaster_int_2k.png: aplanado interior (pintura gris sucia descascarada sobre concreto), 2048² para 2,4 m.

Sustituye a T2_old_plaster_paint_int.png (1024² a 1,2 m), que tiene una estructura casi periódica dentro de la propia losa y en
muros de 4 m se leía como papel tapiz (revisión de aceptación de APT_B, verificada). Se hornea un sombreador periódico por
construcción, así que no hace falta el cross-fade de make_seamless (que deja fantasmas):
  - texturas de imagen a 1 y 3 repeticiones por losa (T1 concreto, K1 descascarado, K2 manchas de agua): repetibles exactas;
  - ruido de Blender en 4D sobre un toro (u, v) -> (cos 2πu, sin 2πu, cos 2πv, sin 2πv): periódico en u y v.
Uso: /root/blk-venv/bin/python tools/make_plaster_int.py [--size 2048]
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import lookdev as ld  # noqa: E402
from kit.common import reset_scene  # noqa: E402

SIZE = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 2048
OUT = os.path.join(ld.TEX, "T2_plaster_int_2k.png")

reset_scene()
me = bpy.data.meshes.new("tile")
bm = bmesh.new()
vs = [bm.verts.new(v) for v in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
f = bm.faces.new(vs)
uv = bm.loops.layers.uv.new("atlas")
for lp, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
    lp[uv].uv = (u, v)
bm.to_mesh(me)
obj = bpy.data.objects.new("tile", me)
bpy.context.scene.collection.objects.link(obj)

mat = bpy.data.materials.new("plaster_int")
nb = ld.NB(mat)
out = nb.n("ShaderNodeOutputMaterial")
bsdf = nb.n("ShaderNodeBsdfPrincipled")
nb.link(bsdf.outputs[0], out.inputs[0])
uvn = nb.n("ShaderNodeUVMap", uv_map="atlas")
sep = nb.n("ShaderNodeSeparateXYZ")
nb.link(uvn.outputs[0], sep.inputs[0])


def img(fn, reps, colorspace="sRGB", rot90=False, off=(0.0, 0.0)):
    """Textura repetible con `reps` repeticiones enteras por losa (y giro de 90°, que conserva la periodicidad)."""
    mp = nb.n("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (reps, reps, 1)
    mp.inputs["Rotation"].default_value = (0, 0, math.pi / 2 if rot90 else 0.0)
    mp.inputs["Location"].default_value = (off[0], off[1], 0)
    nb.link(uvn.outputs[0], mp.inputs["Vector"])
    t = nb.n("ShaderNodeTexImage", extension="REPEAT", interpolation="Cubic")
    t.image = ld._img(os.path.join(ld.TEX, fn), colorspace)
    nb.link(mp.outputs[0], t.inputs[0])
    return t.outputs[0]


def torus_noise(radius, detail, rough=0.55, seed=0.0):
    """Ruido periódico: (u, v) en un toro 4D. `radius` grande = manchas pequeñas."""
    two_pi = 2 * math.pi
    cu = nb.math("COSINE", nb.math("MULTIPLY", sep.outputs[0], two_pi))
    su = nb.math("SINE", nb.math("MULTIPLY", sep.outputs[0], two_pi))
    cv = nb.math("COSINE", nb.math("MULTIPLY", sep.outputs[1], two_pi))
    sv = nb.math("SINE", nb.math("MULTIPLY", sep.outputs[1], two_pi))
    cmb = nb.n("ShaderNodeCombineXYZ")
    nb.link(nb.math("ADD", nb.math("MULTIPLY", cu, radius), seed), cmb.inputs[0])
    nb.link(nb.math("MULTIPLY", su, radius), cmb.inputs[1])
    nb.link(nb.math("MULTIPLY", cv, radius), cmb.inputs[2])
    nz = nb.n("ShaderNodeTexNoise", noise_dimensions="4D", in_Scale=1.0, in_Detail=detail, in_Roughness=rough)
    nb.link(cmb.outputs[0], nz.inputs["Vector"])
    nb.link(nb.math("MULTIPLY", sv, radius), nz.inputs["W"])
    return nz.outputs["Fac"]


conc = img("T1_concrete.png", 1)
# pintura: gris crema sucio con variación grande y fina
n_big = torus_noise(0.9, 3.0, seed=3.1)
n_fine = torus_noise(6.0, 8.0, seed=7.7)
paint = nb.mix(nb.math("MULTIPLY", n_big, 1.0), (0.70, 0.69, 0.65, 1.0), (0.84, 0.83, 0.79, 1.0))
paint = nb.mix(nb.math("MULTIPLY", n_fine, 0.35), paint, (0.62, 0.61, 0.58, 1.0), "MULTIPLY")
# descascarado: K1 a 1 y 3 repeticiones + ruido; borde oscuro donde la pintura se levanta
k1a = img("K1_peel.png", 1, "Non-Color", off=(0.37, 0.11))
k1b = img("K1_peel.png", 3, "Non-Color", rot90=True, off=(0.21, 0.64))
pv = nb.math("ADD", nb.math("MULTIPLY", k1a, 0.6), nb.math("MULTIPLY", k1b, 0.4))
pv = nb.math("ADD", pv, nb.math("MULTIPLY", nb.math("SUBTRACT", torus_noise(1.6, 2.0, seed=11.3), 0.5), 0.55))
peel = nb.n("ShaderNodeMapRange", in_From_Min=0.50, in_From_Max=0.515, interpolation_type="SMOOTHSTEP")
nb.link(pv, peel.inputs[0])
rim = nb.n("ShaderNodeMapRange", in_From_Min=0.47, in_From_Max=0.50, interpolation_type="SMOOTHSTEP")
nb.link(pv, rim.inputs[0])
rim_only = nb.math("MULTIPLY", rim.outputs[0], nb.math("SUBTRACT", 1.0, peel.outputs[0]))
paint = nb.mix(nb.math("MULTIPLY", rim_only, 0.55), paint, (0.55, 0.54, 0.51, 1.0), "MULTIPLY")
color = nb.mix(peel.outputs[0], paint, nb.mix(0.15, conc, (0.55, 0.55, 0.53, 1.0), "MULTIPLY"))
# manchas de agua (goteras) y mugre fina
k2 = img("K2_rain_streaks.png", 1, "Non-Color", off=(0.5, 0.0))
color = nb.mix(nb.math("MULTIPLY", k2, 0.35), color, (0.62, 0.60, 0.56, 1.0), "MULTIPLY")
grime = torus_noise(3.0, 6.0, seed=19.9)
color = nb.mix(nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, grime), 0.25), color, (0.70, 0.69, 0.66, 1.0), "MULTIPLY")
hsv = nb.n("ShaderNodeHueSaturation", in_Saturation=0.35, in_Value=1.0)
nb.link(color, hsv.inputs["Color"])
nb.link(hsv.outputs[0], bsdf.inputs["Base Color"])
me.materials.append(mat)

tmp = os.path.dirname(OUT)
im = ld.bake(obj, "T2_plaster_int_2k", "DIFFUSE", SIZE, tmp, samples=4, margin=0, pass_filter={"COLOR"})
print("OK", OUT, im.size[:])

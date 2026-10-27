"""Plantas seccionadas en arcilla (revisión del interior): cámara ortográfica cenital cuyo plano de recorte corta el edificio a
`--cut` m sobre la losa de cada nivel. Uso: python tests/render_plan.py --id APT_A_5p [--samples 32] [--levels 0,1]"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import apt_builder as ab  # noqa: E402
import builders  # noqa: E402
from kit.common import reset_scene  # noqa: E402

argv = sys.argv
bid = argv[argv.index("--id") + 1]
S = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
cut = float(argv[argv.index("--cut") + 1]) if "--cut" in argv else 1.4
reset_scene()
res = builders.build(bid)
cfg = res["cfg"]
objs = [o for k in builders.KEYS for o in res.get(k, [])]
zl = ab.level_z(cfg)
levels = [int(v) for v in argv[argv.index("--levels") + 1].split(",")] if "--levels" in argv else list(range(len(cfg["h"])))
out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "render_qa"))
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = S
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1600, 1400
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
clay = bpy.data.materials.new("_clay")
sc.view_layers[0].material_override = clay
sc.world = bpy.data.worlds.new("W")
sc.world.use_nodes = True
bg = sc.world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.8, 0.82, 0.85, 1)
bg.inputs[1].default_value = 0.6
sun = bpy.data.objects.new("_sun", bpy.data.lights.new("_sun", "SUN"))
sc.collection.objects.link(sun)
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(18), 0, math.radians(35))
xs, ys = cfg["xs"], cfg["ys"]
cx, cy = (xs[0] + xs[-1]) / 2, (ys[0] + ys[-1]) / 2
span = max(xs[-1] - xs[0], ys[-1] - ys[0]) + 3.0
cam = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
sc.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = span * 1.6 / 1.4
sc.camera = cam
H = 80.0
# el plano de recorte solo afecta a la cámara: los pisos de arriba siguen tapando el sol, así que se ilumina el interior con un
# área cenital justo bajo el corte (invisible a la cámara)
lamp = bpy.data.objects.new("_area", bpy.data.lights.new("_area", "AREA"))
sc.collection.objects.link(lamp)
lamp.data.shape = "RECTANGLE"
lamp.data.size = xs[-1] - xs[0] + 2.0
lamp.data.size_y = ys[-1] - ys[0] + 2.0
lamp.data.energy = 7.0 * lamp.data.size * lamp.data.size_y
lamp.visible_camera = False
for lv in levels:
    zc = zl[lv] + cut
    lamp.location = Vector((cx, cy, zc - 0.03))
    cam.location = Vector((cx, cy, H))
    cam.rotation_euler = (0, 0, 0)
    cam.data.clip_start = H - zc
    cam.data.clip_end = H - zl[lv] + 4.0
    sc.render.filepath = f"{out}/{bid}_planta_N{lv}.png"
    bpy.ops.render.render(write_still=True)
    print("PLANTA", lv, flush=True)

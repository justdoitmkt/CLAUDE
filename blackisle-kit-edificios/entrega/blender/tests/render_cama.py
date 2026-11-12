"""Primer plano de la cama hospitalaria (regla R-AAA: revisión a < 2 m). python tests/render_cama.py [--samples 64]"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402,F401
from mathutils import Matrix, Vector  # noqa: E402

from kit import clinic as cl  # noqa: E402
from kit.common import MB, clay_render, reset_scene, tri_count  # noqa: E402

S = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 48
out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "render_qa", "piezas"))
reset_scene()
t0 = time.time()
a = cl.hospital_bed(1, rails_up=True, fowler=0.0)
b = cl.hospital_bed(2, rails_up=False, fowler=32.0, rails=(True, False))
print("cama", round(time.time() - t0, 1), "s", flush=True)
mb = MB()
mb.join(a, Matrix.Translation((-0.75, 0, 0)))
mb.join(b, Matrix.Translation((0.75, 0, 0)))
o = mb.finish("camas", None, merge=0)
print("tris", tri_count([o]) // 2, "por cama", flush=True)
for nm, kw in {"cama_34": dict(azim=-35, elev=22, dist=4.2, target=Vector((0, 0.1, 0.55)), fov=50),
               "cama_almohada": dict(azim=-150, elev=28, dist=1.6, target=Vector((-0.75, 0.75, 0.68)), fov=50),
               "cama_pie": dict(azim=-15, elev=8, dist=1.9, target=Vector((-0.75, -0.9, 0.45)), fov=55),
               "cama_rodaja": dict(azim=-40, elev=10, dist=0.7, target=Vector((-1.15, -0.97, 0.12)), fov=45)}.items():
    clay_render([o], f"{out}/{nm}.png", res=(1600, 900), samples=S, **kw)
    print("CLAY", nm, flush=True)

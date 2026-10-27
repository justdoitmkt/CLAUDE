"""QA con materiales horneados (fase G): abre blender/<ID>.blend y renderiza a 50 m, 15 m y 2 m con sol a 45° y con cielo
cubierto. Uso: python tests/render_final.py --id APT_A_5p [--samples 64]
Salida: render_qa/<ID>_final_<toma>.png"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from kit.common import clay_render  # noqa: E402

argv = sys.argv
bid = argv[argv.index("--id") + 1]
S = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
HERE = os.path.dirname(os.path.abspath(__file__))
blend = os.path.join(HERE, "..", argv[argv.index("--blend") + 1] if "--blend" in argv else f"{bid}.blend")
bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
objs = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name.startswith(bid)]
out = os.path.abspath(os.path.join(HERE, "..", "..", "render_qa"))
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ctr = (mn + mx) / 2
front_y = mn.y + 3.0                       # la base (arena) sobresale 3 m: la fachada está ~3 m dentro de la caja
shots = {
    "50m_sol45": dict(azim=-32, elev=14, dist=50.0, target=Vector((ctr.x, ctr.y, ctr.z * 0.8)), fov=40, sun_elev=45, sun_azim=40),
    "15m_sol45": dict(azim=-25, elev=4, dist=15.0, target=Vector((ctr.x - 1.0, front_y, 4.0)), fov=70, sun_elev=45, sun_azim=40),
    "2m_pb": dict(azim=-10, elev=2, dist=2.2, target=Vector((ctr.x - 3.0, front_y, 1.5)), fov=70, sun_elev=45, sun_azim=40),
    "50m_nublado": dict(azim=145, elev=14, dist=50.0, target=Vector((ctr.x, ctr.y, ctr.z * 0.8)), fov=40, sun_elev=80, sun_azim=0,
                        sun_energy=0.4, sky=1.1),
}
only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else list(shots)
for name in only:
    v = dict(shots[name])
    clay_render(objs, f"{out}/{bid}_final_{name}.png", res=(1600, 900), samples=S, clay=False, **v)
    print("FINAL", name, flush=True)

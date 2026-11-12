"""Revisión en arcilla de cualquier modelo: python tests/render_clay.py --id APT_B_4p [--only a,b] [--samples 64] [--tag PC3]
Tomas: 4 esquinas exteriores, techo y las tomas extra que defina SHOTS_EXTRA[id] (altura de ojos, detalle de PB, interior)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402,F401
from mathutils import Vector  # noqa: E402

import builders  # noqa: E402
from kit.common import clay_render, reset_scene, tri_count  # noqa: E402

argv = sys.argv
bid = argv[argv.index("--id") + 1]
S = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "clay"
R = (1920, 1080) if S >= 128 else (1600, 900)
reset_scene()
res = builders.build(bid)
objs = [o for k in builders.KEYS for o in res.get(k, [])]
out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "render_qa"))
shots = {
    "ext_fo": dict(azim=-35, elev=12), "ext_fe": dict(azim=35, elev=12),
    "ext_te": dict(azim=145, elev=14), "ext_to": dict(azim=-145, elev=14), "techo": dict(azim=-30, elev=52),
}
SHOTS_EXTRA = {
    "APT_B_4p": {
        "ojo_galeria": dict(azim=-10, elev=-12, dist=17.0, target=Vector((0.0, -5.9, 5.0)), fov=60),
        "detalle_colapso": dict(azim=-40, elev=18, dist=9.0, target=Vector((-5.0, -5.0, 10.0)), fov=55),
        "interior_galeria": dict(azim=-90, elev=1.0, dist=6.2, target=Vector((3.0, -4.95, 6.25 + 1.4)), fov=75, ground=False),
    },
    "APT_C_3p": {
        "esquina": dict(azim=-45, elev=8, dist=22.0, target=Vector((-1.0, -1.0, 4.5)), fov=55),
        "ojo_acceso": dict(azim=-60, elev=-6, dist=10.0, target=Vector((-3.2, -1.8, 2.2)), fov=60),
    },
    "MUE_1_carga": {
        "playa": dict(azim=-22, elev=3, dist=52.0, target=Vector((2.0, 10.0, 4.0)), fov=60),
        "mar": dict(azim=160, elev=1, dist=44.0, target=Vector((18.0, 48.0, 3.5)), fov=60),
        "nave_interior": dict(azim=10, elev=2, dist=10.0, target=Vector((1.0, 23.0, 4.2)), fov=78, ground=False),
        "rampa": dict(azim=-18, elev=7, dist=24.0, target=Vector((2.0, -8.0, 1.6)), fov=62),
        "rampa_pie": dict(azim=-40, elev=4, dist=9.0, target=Vector((-21.0, -24.0, 0.8)), fov=60),
        "atraque": dict(azim=165, elev=6, dist=13.0, target=Vector((22.0, 52.0, 2.0)), fov=58),
        "grua": dict(azim=135, elev=8, dist=24.0, target=Vector((43.0, 49.0, 7.5)), fov=55),
        "esquina": dict(azim=-30, elev=6, dist=5.0, target=Vector((-10.6, 10.0, 3.3)), fov=55),
        "esquina_e": dict(azim=30, elev=6, dist=5.0, target=Vector((10.6, 10.0, 3.3)), fov=55),
    },
    "HOS_1_pueblo": {
        "calle": dict(azim=-25, elev=4, dist=34.0, target=Vector((3.0, -6.0, 2.4)), fov=55),
        "urgencias": dict(azim=35, elev=6, dist=13.0, target=Vector((15.2, -9.0, 2.0)), fov=60),
        "trasera": dict(azim=160, elev=10, dist=30.0, target=Vector((4.0, 8.0, 2.0)), fov=55),
        "espera": dict(azim=108, elev=3, dist=9.8, target=Vector((-11.8, -8.0, 1.0)), fov=75, ground=False),
        "pasillo": dict(azim=90, elev=0, dist=9.0, target=Vector((-4.0, -2.9, 1.5)), fov=70, ground=False),
        "encamados": dict(azim=52, elev=8, dist=5.8, target=Vector((-10.0, 8.6, 0.8)), fov=75, ground=False),
        "urgencias_int": dict(azim=125, elev=6, dist=7.0, target=Vector((7.0, -8.6, 0.9)), fov=75, ground=False),
        "patio": dict(azim=-30, elev=35, dist=10.0, target=Vector((0.5, 1.1, 1.0)), fov=60),
    },
    "APT_D_4p": {
        "ojo_frente": dict(azim=-15, elev=-12, dist=20.0, target=Vector((0.0, -4.2, 5.4)), fov=60),
        "testero_oeste": dict(azim=-80, elev=10, dist=16.0, target=Vector((-8.2, 0.0, 6.0)), fov=55),
    },
}
shots.update(SHOTS_EXTRA.get(bid, {}))
for p in (res.get("stats", {}).get("interior_dress", {}).get("bulb_pos", []) if bid.startswith("HOS_") else []):
    L = bpy.data.lights.new("_foco", "AREA")          # luminarias del hospital encendidas (interiores legibles en arcilla)
    L.energy = 22.0
    L.size = 1.1
    lo = bpy.data.objects.new("_foco", L)
    lo.location = (p[0], p[1], p[2] - 0.01)
    bpy.context.scene.collection.objects.link(lo)
if bid.startswith("MUE_"):
    # muelle: playa a z 0 que baja bajo la cubierta y mar a -0,5 (el piso automático quedaría en el fondo de los pilotes)
    me = bpy.data.meshes.new("_playa")
    me.from_pydata([(-200, -150, 0.0), (200, -150, 0.0), (200, -1.0, 0.0), (-200, -1.0, 0.0), (200, 30, -4.0), (-200, 30, -4.0)],
                   [], [(0, 1, 2, 3), (3, 2, 4, 5)])
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("_playa", me))
    me = bpy.data.meshes.new("_mar")
    me.from_pydata([(-200, -4.0, -0.5), (200, -4.0, -0.5), (200, 250, -0.5), (-200, 250, -0.5)], [], [(0, 1, 2, 3)])
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("_mar", me))
    for v in shots.values():
        v["ground"] = False
only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else list(shots)
for name in only:
    clay_render(objs, f"{out}/{bid}_{tag}_{name}.png", res=R, samples=S, **dict(shots[name]))
    print("CLAY", name, flush=True)
json.dump(dict(tris=tri_count(objs), stats=res.get("stats")), open(f"{out}/{bid}_{tag}_info.json", "w"), indent=1, default=str)

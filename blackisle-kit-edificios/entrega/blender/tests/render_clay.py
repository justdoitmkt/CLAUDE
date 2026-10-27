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
    "APT_D_4p": {
        "ojo_frente": dict(azim=-15, elev=-12, dist=20.0, target=Vector((0.0, -4.2, 5.4)), fov=60),
        "testero_oeste": dict(azim=-80, elev=10, dist=16.0, target=Vector((-8.2, 0.0, 6.0)), fov=55),
    },
}
shots.update(SHOTS_EXTRA.get(bid, {}))
only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else list(shots)
for name in only:
    clay_render(objs, f"{out}/{bid}_{tag}_{name}.png", res=R, samples=S, **dict(shots[name]))
    print("CLAY", name, flush=True)
json.dump(dict(tris=tri_count(objs), stats=res.get("stats")), open(f"{out}/{bid}_{tag}_info.json", "w"), indent=1, default=str)

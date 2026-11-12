"""Primeros planos en arcilla de las piezas de kit/port.py: python tests/render_piezas.py [--only grua,poste,...]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402,F401
from mathutils import Matrix, Vector  # noqa: E402

from kit import port  # noqa: E402
from kit.common import MB, clay_render, reset_scene, tri_count  # noqa: E402

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "render_qa", "piezas"))
os.makedirs(OUT, exist_ok=True)


def pieces():
    yield "bita", lambda: port.bollard(1), dict(azim=-35, elev=20, dist=1.9, target=Vector((0, 0, 0.3)), fov=45)

    def llanta():
        mb = MB()
        mb.join(port.fender_tyre(2), Matrix.Translation((0, 0, 0.8)))
        port.chain(mb, [(0, 0.05, 1.9), (0, 0.05, 1.27)], r=None)
        return mb
    yield "llanta", llanta, dict(azim=-25, elev=10, dist=2.8, target=Vector((0, 0, 1.0)), fov=45)
    yield "defensa", lambda: port.timber_fender(3.0, 3), dict(azim=-30, elev=10, dist=3.2, target=Vector((0, 0.15, 1.5)), fov=50)
    yield "escalera", lambda: port.marine_ladder(-1.0, 2.5, 4), dict(azim=160, elev=8, dist=4.5, target=Vector((0, 0, 1.6)), fov=50)
    yield "poste", lambda: port.light_pole(9.0, 5), dict(azim=-60, elev=8, dist=7.5, target=Vector((0, -0.6, 4.8)), fov=70)
    yield "poste_cabeza", lambda: port.light_pole(9.0, 5), dict(azim=-70, elev=-5, dist=2.0, target=Vector((0, -1.3, 8.8)), fov=50)
    yield "poste_base", lambda: port.light_pole(9.0, 5), dict(azim=-30, elev=25, dist=1.6, target=Vector((0, 0, 0.3)), fov=50)
    yield "tambo", lambda: port.drum(6), dict(azim=-30, elev=20, dist=2.0, target=Vector((0, 0, 0.45)), fov=45)
    yield "grua", lambda: port.pedestal_crane(7, yaw=0.0), dict(azim=-55, elev=12, dist=24.0, target=Vector((0, -5, 7.5)), fov=55)
    yield "grua_cabina", lambda: port.pedestal_crane(7, yaw=0.0), dict(azim=-40, elev=8, dist=7.5, target=Vector((0.5, -0.8, 5.8)), fov=55)
    yield "grua_cabeza", lambda: port.pedestal_crane(7, yaw=0.0), dict(azim=-70, elev=-10, dist=4.0, target=Vector((0, -13.0, 13.6)), fov=55)
    yield "contenedor", lambda: port.container(8), dict(azim=-35, elev=12, dist=9.5, target=Vector((3.0, 1.2, 1.3)), fov=50)
    yield "contenedor_puertas", lambda: port.container(8, open_doors=True), dict(azim=60, elev=8, dist=4.8, target=Vector((6.0, 1.2, 1.3)), fov=55)


only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
for name, fn, cam in pieces():
    if only and name not in only:
        continue
    reset_scene()
    mb = fn()
    o = mb.finish(name, None, uv_size=2.0, merge=0)
    clay_render([o], f"{OUT}/{name}.png", res=(1200, 800), samples=24, **cam)
    print("PIEZA", name, tri_count([o]), flush=True)

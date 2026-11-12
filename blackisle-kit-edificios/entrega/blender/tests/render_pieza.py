"""Revisión de primer plano (regla R-AAA, < 2 m) de UNA pieza, comparada con la versión anterior de kit/clinic.py.

Uso: /root/blk-venv/bin/python tests/render_pieza.py <modulo> <funcion> <carpeta_salida> [kwargs_json] [--samples N]
  p. ej.  tests/render_pieza.py kit.clinic_aaa_a washer /tmp/out '{"seed": 3}'
Escribe <carpeta>/<funcion>_34.png (3/4 frontal), _det.png (detalle cercano), _lado.png (perfil) y, si existe la función homónima
en kit.clinic, <funcion>_antes.png. Imprime triángulos, caja envolvente (mín/máx) de la nueva y de la anterior y su diferencia.
"""
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402,F401
from mathutils import Vector  # noqa: E402

from kit.common import clay_render, reset_scene, tri_count  # noqa: E402

args = [a for a in sys.argv[1:]]
S = 16
if "--samples" in args:
    i = args.index("--samples")
    S = int(args[i + 1])
    del args[i:i + 2]
mod, fn, out = args[0], args[1], args[2]
kw = json.loads(args[3]) if len(args) > 3 else {}
os.makedirs(out, exist_ok=True)


def build(module, name):
    reset_scene()
    m = importlib.import_module(module)
    mb = getattr(m, name)(**kw)
    o = mb.finish(name, None, merge=0)
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    return o, mn, mx


def views(o, mn, mx, tag):
    ctr = (mn + mx) / 2
    size = max((mx - mn).length, 0.2)
    clay_render([o], f"{out}/{fn}_{tag}34.png", res=(1000, 750), samples=S, azim=-35, elev=18, fov=40, target=ctr, dist=size * 1.6)
    if tag:
        return
    clay_render([o], f"{out}/{fn}_det.png", res=(1000, 750), samples=S, azim=-20, elev=28, fov=35,
                target=Vector((ctr.x, mn.y, ctr.z + (mx.z - mn.z) * 0.15)), dist=size * 0.75)
    clay_render([o], f"{out}/{fn}_lado.png", res=(1000, 750), samples=S, azim=-90, elev=8, fov=40, target=ctr, dist=size * 1.5)


o, mn, mx = build(mod, fn)
print(f"NUEVA {fn}: tris {tri_count([o])}  caja {tuple(round(v, 3) for v in mn)} -> {tuple(round(v, 3) for v in mx)}", flush=True)
views(o, mn, mx, "")
old = importlib.import_module("kit.clinic")
if mod != "kit.clinic" and hasattr(old, fn):
    o2, mn2, mx2 = build("kit.clinic", fn)
    print(f"ANTES {fn}: tris {tri_count([o2])}  caja {tuple(round(v, 3) for v in mn2)} -> {tuple(round(v, 3) for v in mx2)}", flush=True)
    d = max(max(abs(a - b) for a, b in zip(mn, mn2)), max(abs(a - b) for a, b in zip(mx, mx2)))
    print(f"DIF_CAJA {fn}: {d:.3f} m", flush=True)
    views(o2, mn2, mx2, "antes_")
print("LISTO", out, flush=True)

import sys, os, math, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import bpy  # noqa
from kit.common import reset_scene, tri_count, mesh_health, clay_render
import apt_builder as ab
reset_scene()
t = time.time()
cfg = ab.cfg_apt_a()
objs, placed = ab.build_structure(cfg)
print('construido en', round(time.time() - t, 2), 's')
for o in objs:
    print(f'{o.name:26s} tris {tri_count([o]):7d}  {mesh_health(o)}  dims {tuple(round(d,2) for d in o.dimensions)}')
print('TOTAL', tri_count(objs))
out = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'render_qa'))
clay_render(objs, f'{out}/APT_A_5p_struct_front.png', res=(1280, 720), samples=24, azim=-30, elev=12)
#clay_render(objs, f'{out}/APT_A_5p_struct_back.png', res=(1280, 720), samples=24, azim=150, elev=20)
# corte: ocultar la mitad superior para ver la planta del piso 2

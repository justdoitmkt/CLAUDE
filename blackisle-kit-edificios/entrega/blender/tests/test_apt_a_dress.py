import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import bpy  # noqa
from kit.common import reset_scene, tri_count, mesh_health, clay_render
import apt_builder as ab
reset_scene()
t = time.time()
res = ab.build_apt_a()
print('construido en', round(time.time() - t, 1), 's', res.get('stats'))
objs = []
for k in ('Shell', 'Details', 'Interior', 'Skirt', 'Roof', 'Damage'):
    for o in res.get(k, []):
        objs.append(o)
        print(f'{o.name:22s} tris {tri_count([o]):8d}  {mesh_health(o)}')
print('TOTAL', tri_count(objs))
out = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'render_qa'))
if '--render' in sys.argv:
    clay_render(objs, f'{out}/APT_A_5p_dress_front.png', res=(1600, 900), samples=32, azim=-28, elev=10)
    clay_render(objs, f'{out}/APT_A_5p_dress_east.png', res=(1600, 900), samples=32, azim=62, elev=12)

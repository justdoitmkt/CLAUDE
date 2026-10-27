"""PC3 · revisión en arcilla de APT_A (brief: Cycles >= 128 muestras, 1920x1080)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import bpy  # noqa
from mathutils import Vector
from kit.common import reset_scene, tri_count, clay_render
import apt_builder as ab
reset_scene()
res = ab.build_apt_a()
objs = [o for k in ('Shell', 'Details', 'Interior', 'Skirt', 'Roof', 'Damage') for o in res.get(k, [])]
out = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'render_qa'))
S = int(os.environ.get('PC3_SAMPLES', 128))
R = (1920, 1080)
shots = {
    'ext_fo': dict(azim=-35, elev=12),
    'ext_fe': dict(azim=35, elev=12),
    'ext_te': dict(azim=145, elev=14),
    'ext_to': dict(azim=-145, elev=14),
    'ojo_1p7': dict(azim=-12, elev=-13.5, dist=19.0, target=Vector((0.8, -5.6, 6.2)), fov=58),
    'techo': dict(azim=-30, elev=52),
    'detalle_pb': dict(azim=-22, elev=4, dist=6.5, target=Vector((2.2, -5.6, 1.8)), fov=55),
    'interior_corredor': dict(azim=-90, elev=1.0, dist=9.0, target=Vector((3.2, 0.0, 6.45 + 1.45)), fov=75, ground=False),
}
only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else list(shots)
for name in only:
    v = dict(shots[name])
    clay_render(objs, f'{out}/APT_A_5p_PC3_clay_{name}.png', res=R, samples=S, **v)
    print('PC3', name, flush=True)
json.dump(dict(tris=tri_count(objs)), open(f'{out}/APT_A_5p_PC3_info.json', 'w'))

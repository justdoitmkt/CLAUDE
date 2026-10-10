import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import bpy  # noqa
from kit.common import reset_scene, tri_count, clay_render
import apt_builder as ab
reset_scene()
res = ab.build_apt_a()
objs = [o for k in ('Shell', 'Details', 'Interior', 'Skirt', 'Roof', 'Damage') for o in res.get(k, [])]
print('TOTAL', tri_count(objs))
out = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'render_qa'))
tag = sys.argv[sys.argv.index('--tag') + 1] if '--tag' in sys.argv else 'clay'
views = {'front': dict(azim=-32, elev=14), 'back': dict(azim=148, elev=16), 'east': dict(azim=70, elev=22), 'west': dict(azim=-110, elev=12)}
for name, v in views.items():
    if '--only' in sys.argv and name not in sys.argv[sys.argv.index('--only') + 1].split(','):
        continue
    clay_render(objs, f'{out}/APT_A_5p_{tag}_{name}.png', res=(1600, 900), samples=32, **v)

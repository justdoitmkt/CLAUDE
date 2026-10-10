import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import bpy  # noqa
from kit.common import reset_scene, tri_count, clay_render
import apt_builder as ab
import lookdev as ld
reset_scene()
t = time.time()
res = ab.build_apt_a()
shell, det, inter = res['Shell'][0], res['Details'][0], res['Interior'][0]
ext, intr = ld.split_exterior(shell, others=[det, inter])
print('split', round(time.time() - t, 1), 's  ext tris', tri_count([ext]), 'int tris', tri_count([intr]))
bpy.data.objects.remove(shell)
cfg = res['cfg']
gm = ld.graffiti_map('G_APT_A', json.load(open(os.path.join(ld.TEX, 'graffiti', 'G_APT_A_mapa.json'))),
                     cfg['xs'][0] - ab.COL_CORNER / 2, cfg['xs'][-1] + ab.COL_CORNER / 2, cfg['ys'][0] - ab.COL_CORNER / 2, cfg['ys'][-1] + ab.COL_CORNER / 2)
names = sorted({m.name for o in (ext, intr, det, inter) for m in o.data.materials})
for n in names:
    ld.lookdev_material(n, seed=cfg['seed'], gmap=gm)
print('materiales', names)
out = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'render_qa'))
objs = [ext, intr, det, inter]
clay_render(objs, f'{out}/APT_A_5p_lookdev_front.png', res=(1600, 900), samples=48, azim=-30, elev=9, clay=False, dist=42)
print('render', round(time.time() - t, 1), 's')

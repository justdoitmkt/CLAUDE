import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import bpy  # noqa
from kit.common import reset_scene, tri_count, clay_render
import apt_builder as ab
import lookdev as ld
OUT = sys.argv[sys.argv.index('--out') + 1]
SIZE = int(sys.argv[sys.argv.index('--size') + 1])
reset_scene()
res = ab.build_apt_a()
shell, det, inter = res['Shell'][0], res['Details'][0], res['Interior'][0]
ext, intr = ld.split_exterior(shell, others=[det, inter])
bpy.data.objects.remove(shell)
cfg = res['cfg']
gm = ld.graffiti_map('G_APT_A', json.load(open(os.path.join(ld.TEX, 'graffiti', 'G_APT_A_mapa.json'))),
                     cfg['xs'][0] - ab.COL_CORNER / 2, cfg['xs'][-1] + ab.COL_CORNER / 2, cfg['ys'][0] - ab.COL_CORNER / 2, cfg['ys'][-1] + ab.COL_CORNER / 2)
for n in sorted({m.name for o in (ext, intr, det, inter) for m in o.data.materials}):
    ld.lookdev_material(n, seed=cfg['seed'], gmap=gm)
t = time.time(); ld.unwrap(ext); print('unwrap', round(time.time() - t, 1), 's')
t = time.time(); alb = ld.bake(ext, 'APT_A_walls_albedo', 'DIFFUSE', SIZE, OUT, samples=16, pass_filter={'COLOR'}); print('bake color', round(time.time() - t, 1), 's')
t = time.time(); rough = ld.bake(ext, 'APT_A_walls_rough', 'ROUGHNESS', SIZE, OUT, samples=4, colorspace='Non-Color'); print('bake rough', round(time.time() - t, 1), 's')
t = time.time(); nrm = ld.bake(ext, 'APT_A_walls_normal', 'NORMAL', SIZE, OUT, samples=16, colorspace='Non-Color'); print('bake normal', round(time.time() - t, 1), 's')
t = time.time(); ao = ld.bake(ext, 'APT_A_walls_ao', 'AO', SIZE, OUT, samples=64, colorspace='Non-Color'); print('bake ao', round(time.time() - t, 1), 's')
orm = ld.pack_orm(ao, rough, 0.0, os.path.join(OUT, 'APT_A_walls_orm.png'))
fm = ld.final_material('APT_A_walls_final', alb, nrm, orm)
ext.data.materials.clear(); ext.data.materials.append(fm)
for p in ext.data.polygons: p.material_index = 0
clay_render([ext, intr, det, inter], os.path.join(OUT, 'baked_front.png'), res=(1600, 900), samples=48, azim=-30, elev=9, clay=False, dist=42)
print('ok')

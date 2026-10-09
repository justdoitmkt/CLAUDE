import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import bpy  # noqa: F401
from mathutils import Matrix, Vector
from kit.common import MB, wall_with_openings, tri_count, mesh_health, clay_render, reset_scene

reset_scene()
objs = []
mb = MB(); mb.box((0, 0, 0), (1, 0.5, 0.3), bevel=0.02); objs.append(mb.finish('caja_bisel'))
mb = MB(); mb.cyl((2, 0, 0), (2, 0, 1), 0.1, seg=10); objs.append(mb.finish('cilindro'))
mb = MB(); mb.tube([(3, 0, 1), (3.5, 0, 0.6), (4.2, 0, 0.55), (5, 0, 0.9)], 0.02, seg=6); objs.append(mb.finish('cable'))
mb = MB(); mb.sweep([(-0.03, 0), (0.03, 0), (0.03, 0.06), (-0.03, 0.06)], [(6, 0, 0), (6, 0, 1.3), (7.6, 0, 1.3), (7.6, 0, 0)], mat='aluminium', normal=(0, 1, 0)); objs.append(mb.finish('marco'))
mb = MB(); mb.plate([(0, 0), (1, 0), (1, 0.6), (0, 0.6)], 0.2, m=Matrix.Translation((8, 0, 0))); objs.append(mb.finish('placa'))
mb = MB(); wall_with_openings(mb, 3.6, 2.9, 0.2, [(0.6, 2.2, 0.9, 2.1), (2.5, 3.3, 0.0, 2.05)], m=Matrix.Translation((0, -3, 0))); w = mb.finish('muro')
objs.append(w)
for o in objs:
    print(f'{o.name:12s} tris {tri_count([o]):5d}  {mesh_health(o)}')
out = os.path.join(os.path.dirname(__file__), '..', '..', 'render_qa', 'kit', 'test_common.png')
clay_render(objs, os.path.abspath(out), res=(960, 540), samples=16, azim=20, elev=22)
print('render', os.path.abspath(out))

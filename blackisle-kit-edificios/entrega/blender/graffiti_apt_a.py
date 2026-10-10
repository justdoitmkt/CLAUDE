"""Paneles de grafiti de PB de APT_A_5p (capa RGBA por cara + versión JPG sobre T1 para revisión).
Coordenadas de cara: metros desde la esquina inferior izquierda MIRANDO LA FACHADA DESDE FUERA."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import bpy  # noqa
from mathutils import Vector
import apt_builder as ab
import texture_tools as tt

ENT = os.path.abspath(os.path.join(HERE, '..'))
CUT = os.path.join(ENT, 'lettering', 'cutouts')
OUT = os.path.join(ENT, 'texturas', 'graffiti')
cfg = ab.cfg_apt_a()
xs, ys = cfg['xs'], cfg['ys']
X0, X1 = xs[0] - ab.COL_CORNER / 2, xs[-1] + ab.COL_CORNER / 2
Y0, Y1 = ys[0] - ab.COL_CORNER / 2, ys[-1] + ab.COL_CORNER / 2
BAND_H = cfg['h'][0] + ab.GROUND + 0.7          # PB + 0,7 m de desvanecimiento
FACES = {   # ancho de cara y función mundo->u
    'front': (X1 - X0, lambda p: p.x - X0),
    'back': (X1 - X0, lambda p: X1 - p.x),
    'west': (Y1 - Y0, lambda p: Y1 - p.y),
    'east': (Y1 - Y0, lambda p: p.y - Y0),
}
bpy.ops.wm.read_factory_settings(use_empty=True)
res = ab.build_apt_a(dress=False)
keep = {k: [] for k in FACES}
for side, panels in res['placed'].items():
    W, fu = FACES[side]
    for p in panels:
        if p['level'] != 0:
            continue
        if p['kind'] == 'lobby':                         # el vestíbulo rehundido es un hueco en la cara
            a = Vector((p['a0'], 0, 0)); b = Vector((p['a1'], 0, 0))
            u0, u1 = sorted((fu(a), fu(b)))
            keep[side].append((u0, 0.0, u1, p['z0'] + p['H'])); continue
        o = p.get('opening')
        if not o:
            continue
        c0 = p['m'] @ Vector((o[0], 0, o[2])); c1 = p['m'] @ Vector((o[1], 0, o[3]))
        u0, u1 = sorted((fu(c0), fu(c1)))
        keep[side].append((round(u0 - 0.02, 3), round(c0.z - 0.02, 3), round(u1 + 0.02, 3), round(c1.z + 0.02, 3)))
c = lambda n: os.path.join(CUT, n)
# composición densa por capas (R10: semilla y subconjunto propios de APT_A; "Mi Vida Loca" protagonista aquí)
TAGS = [c(f'S05_hoja_tags_0{i}.png') for i in range(1, 7)] + [c('S04_rexo.png')]
ICONS = [c(f'S06_hoja_iconos_0{i}.png') for i in (1, 2, 3, 5, 6)]
DRIPS = [c(f'S07_hoja_goteos_0{i}.png') for i in range(1, 7)]
HERO = {
 'front': [dict(png=c('C01_mi_vida_loca.png'), w=2.9, rot=-4), dict(png=c('S01_kaos.png'), w=1.6)],
 'back': [dict(png=c('C02_isla_negra.png'), w=2.5, rot=3), dict(png=c('S02_zoro.png'), w=2.4), dict(png=c('C04_por_vida.png'), w=1.5),
          dict(png=c('S01_kaos.png'), w=2.0)],
 'west': [dict(png=c('S03_nova.png'), w=3.2), dict(png=c('C07_sin_miedo.png'), w=2.6), dict(png=c('C03_con_safos.png'), w=2.3),
          dict(png=c('C05_familia.png'), w=1.8)],
 'east': [dict(png=c('C08_puro_corazon.png'), w=2.1), dict(png=c('C06_respeto.png'), w=2.2), dict(png=c('S02_zoro.png'), w=1.6)],
}
PXM = 276.0
info = {}
for i, (side, (W, _)) in enumerate(FACES.items()):
    ov = os.path.join(OUT, f'G_APT_A_{side}.png')
    tt.compose_graffiti_dense(W, BAND_H, PXM, keep[side], ov, seed=cfg['seed'] * 100 + i, hero=HERO[side], tags=TAGS, icons=ICONS,
                              drips=DRIPS, pb_top_m=cfg['h'][0] + ab.GROUND, n_tags=int(W * 9), n_buffs=3 + (i % 2),
                              peel_mask=os.path.join(ENT, 'texturas', 'K1_peel.png'),
                              jpg_base=os.path.join(ENT, 'texturas', 'T1_concrete.png'), jpg_out=os.path.join(OUT, f'G_APT_A_{side}.jpg'))
    info[side] = dict(width_m=round(W, 3), height_m=round(BAND_H, 3), px=[int(W * PXM), int(BAND_H * PXM)], px_per_m=PXM, keepout=keep[side])
    print(side, info[side]['px'], 'keepouts', len(keep[side]))
json.dump(info, open(os.path.join(OUT, 'G_APT_A_mapa.json'), 'w'), indent=1)

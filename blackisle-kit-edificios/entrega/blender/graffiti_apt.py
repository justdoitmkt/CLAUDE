"""Paneles de grafiti de PB por cara (capa RGBA + JPG sobre T1 para revisión) para APT_B / APT_C / APT_D.
(APT_A conserva su script aprobado graffiti_apt_a.py.)  Uso: python graffiti_apt.py --id APT_B_4p
Coordenadas de cara: metros desde la esquina inferior izquierda MIRANDO LA FACHADA DESDE FUERA.
R10: cada edificio usa su propia semilla y su propio subconjunto de piezas; "Mi Vida Loca" solo en 2 de los 4 (A y C)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import apt_builder as ab  # noqa: E402
import builders  # noqa: E402
import texture_tools as tt  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))
CUT = os.path.join(ENT, "lettering", "cutouts")
OUT = os.path.join(ENT, "texturas", "graffiti")
c = lambda n: os.path.join(CUT, n)  # noqa: E731

HEROES = {
    "APT_B_4p": {
        "front": [dict(png=c("S03_nova.png"), w=2.6, rot=-3), dict(png=c("C05_familia.png"), w=1.6), dict(png=c("S04_rexo.png"), w=1.1)],
        "back": [dict(png=c("C07_sin_miedo.png"), w=2.4, rot=2), dict(png=c("S02_zoro.png"), w=1.9)],
        "west": [dict(png=c("C03_con_safos.png"), w=2.2), dict(png=c("S01_kaos.png"), w=1.8, rot=-5)],
        "east": [dict(png=c("C06_respeto.png"), w=2.0), dict(png=c("C08_puro_corazon.png"), w=1.7)],
    },
}
ICON_SETS = {"APT_B_4p": (2, 3, 4, 6)}
PXM = 276.0


def keepouts(res, fu_by_side):
    """Vanos de PB (y pórtico) en coordenadas de cara: (u0, z0, u1, z1)."""
    keep = {k: [] for k in fu_by_side}
    for p in res["placed"]:
        if p["level"] != 0 or p["side"] not in keep:
            continue
        fu = fu_by_side[p["side"]][1]
        for kind, (u0, u1, v0, v1) in p["ops"]:
            c0 = p["m"] @ Vector((u0, 0, v0))
            c1 = p["m"] @ Vector((u1, 0, v1))
            a, b = sorted((fu(c0), fu(c1)))
            pad = 0.02                                          # los postes del pórtico van 1 m adelante: no tapan el muro
            top = c1.z + (0.42 if kind == "portico" else 0.02)  # la marquesina se empotra sobre el vano
            keep[p["side"]].append((round(a - pad, 3), round(c0.z - 0.02, 3), round(b + pad, 3), round(top, 3)))
    return keep


def main():
    bid = sys.argv[sys.argv.index("--id") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    res = builders.build(bid, dress_all=False)
    cfg = res["cfg"]
    xs, ys = cfg["xs"], cfg["ys"]
    X0, X1 = xs[0] - ab.COL_CORNER / 2, xs[-1] + ab.COL_CORNER / 2
    Y0, Y1 = ys[0] - ab.COL_CORNER / 2, ys[-1] + ab.COL_CORNER / 2
    faces = {"front": (X1 - X0, lambda p: p.x - X0), "back": (X1 - X0, lambda p: X1 - p.x),
             "west": (Y1 - Y0, lambda p: Y1 - p.y), "east": (Y1 - Y0, lambda p: p.y - Y0)}
    band_h = cfg["h"][0] + ab.GROUND + 0.7
    keep = keepouts(res, faces)
    tags = [c(f"S05_hoja_tags_0{i}.png") for i in range(1, 7)]
    icons = [c(f"S06_hoja_iconos_0{i}.png") for i in ICON_SETS[bid]]
    drips = [c(f"S07_hoja_goteos_0{i}.png") for i in range(1, 7)]
    short = "_".join(bid.split("_")[:2])
    info = {}
    for i, (side, (W, _)) in enumerate(faces.items()):
        ov = os.path.join(OUT, f"G_{short}_{side}.png")
        tt.compose_graffiti_dense(W, band_h, PXM, keep[side], ov, seed=cfg["seed"] * 100 + i, hero=HEROES[bid][side], tags=tags,
                                  icons=icons, drips=drips, pb_top_m=cfg["h"][0] + ab.GROUND, n_tags=int(W * 8), n_buffs=2 + (i % 3),
                                  peel_mask=os.path.join(ENT, "texturas", "K1_peel.png"),
                                  jpg_base=os.path.join(ENT, "texturas", "T1_concrete.png"), jpg_out=os.path.join(OUT, f"G_{short}_{side}.jpg"))
        info[side] = dict(width_m=round(W, 3), height_m=round(band_h, 3), px=[int(W * PXM), int(band_h * PXM)], px_per_m=PXM,
                          keepout=keep[side])
        print(side, info[side]["px"], "keepouts", len(keep[side]), flush=True)
    json.dump(info, open(os.path.join(OUT, f"G_{short}_mapa.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

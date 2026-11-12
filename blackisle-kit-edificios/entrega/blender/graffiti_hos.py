"""Grafiti del hospital HOS_1_pueblo con su biblioteca EXCLUSIVA (lettering/hos/cutouts: crews KITE y LUMA, firmas BEAM, WAVE,
FIZZ, HUSH, throw-ups, esténciles y el mural comunitario). Ninguna pieza de los otros edificios.
El hospital está en uso: fachadas casi limpias (parches de pintura que tapan firmas, un sticker, el mural); el grafiti se carga
en la barda perimetral y en los costados y el fondo de la cochera.
Cada capa se limita a una franja de profundidad (lookdev.graffiti_map 'depth'): muros que miran al mismo lado no comparten piezas.
Uso: /root/blk-venv/bin/python graffiti_hos.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import bpy  # noqa: E402,F401
from PIL import Image  # noqa: E402

import hos_builder as hb  # noqa: E402
import texture_tools as tt  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))
CUT = os.path.join(ENT, "lettering", "hos", "cutouts")
OUT = os.path.join(ENT, "texturas", "graffiti")
c = lambda n: os.path.join(CUT, n)  # noqa: E731
TAGS = [c(f"H02_{w}.png") for w in ("KITE", "LUMA", "BEAM", "WAVE", "FIZZ", "HUSH")]
STENCILS = [c("H04_gull.png"), c("H04_palm.png")]


def main():
    cfg = hb.cfg_hos()
    gx0, gx1, gy0, gy1 = cfg["graffiti_bounds"]
    PXM = cfg["graffiti_px_per_m"]
    H = 4.6
    U = dict(front=lambda x: x - gx0, back=lambda x: gx1 - x, west=lambda y: gy1 - y, east=lambda y: y - gy0)
    W = dict(front=gx1 - gx0, back=gx1 - gx0, west=gy1 - gy0, east=gy1 - gy0)

    def span(side, a, b):
        u0, u1 = sorted((U[side](a), U[side](b)))
        return u0, u1

    def zone(side, a, b, z0, z1):                  # zona del compositor: (u0, z0, u1, z1)
        u0, u1 = span(side, a, b)
        return (u0, z0, u1, z1)
    L = {}
    mu = span("west", -9.4, -4.4)                   # mural: muro poniente de la sala de espera, entre la banqueta y el pretil
    # fachada principal y frente de la cochera: casi limpias
    L["front"] = dict(side="front", depth=[1, -10.15, -8.85], zones=[zone("front", 16.42, 16.78, 0.15, 2.9), zone("front", 20.22, 20.58, 0.15, 2.9),
                                                                     zone("front", 24.02, 24.38, 0.15, 2.9), zone("front", 13.0, 13.95, 0.2, 1.25)],
                      hero=[dict(png=c("H04_sun_poster.png"), w=0.34)], tags=[c("H02_HUSH.png")], tpm=0.6, buffs=2)
    L["east_garage"] = dict(side="east", depth=[0, 24.3, 24.5], zones=[zone("east", -8.95, 1.95, 0.15, 2.2)],
                            hero=[dict(png=c("H03_KITE_throw.png"), w=2.3, rot=-2), dict(png=c("H04_be_kind.png"), w=0.6)],
                            tags=TAGS, tpm=0.9, buffs=4)
    L["east_wall"] = dict(side="east", depth=[0, 26.95, 27.2], zones=[zone("east", -9.0, 13.5, 0.1, 1.75)],
                          hero=[dict(png=c("H03_LUMA_throw.png"), w=1.9, rot=2), dict(png=c("H04_gull.png"), w=0.7)],
                          tags=TAGS, icons=STENCILS, tpm=1.3, buffs=3)
    L["back_wall"] = dict(side="back", depth=[1, 13.45, 13.7],
                          zones=[zone("back", -17.0, 2.85, 0.1, 1.75), zone("back", 7.15, 27.0, 0.1, 1.75)],
                          hero=[dict(png=c("H03_KITE_throw.png"), w=2.0, rot=3), dict(png=c("H03_LUMA_throw.png"), w=1.7, rot=-3),
                                dict(png=c("H04_be_kind.png"), w=0.8), dict(png=c("H04_sun_poster.png"), w=0.45)],
                          tags=TAGS, icons=STENCILS, tpm=1.4, buffs=5)
    L["west_wall"] = dict(side="west", depth=[0, -17.2, -16.95], zones=[zone("west", -10.0, 13.5, 0.1, 1.75)],
                          hero=[dict(png=c("H03_LUMA_throw.png"), w=1.6), dict(png=c("H04_palm.png"), w=0.6)],
                          tags=TAGS, icons=STENCILS, tpm=1.1, buffs=3)
    L["back"] = dict(side="back", depth=[1, 9.95, 10.15], zones=[zone("back", -13.9, 11.4, 0.15, 1.2), zone("back", 12.8, 13.9, 0.15, 1.2)],
                     hero=[], tags=TAGS[2:], tpm=0.25, buffs=4)
    L["west"] = dict(side="west", depth=[0, -14.15, -13.95], zones=[zone("west", -2.2, -1.2, 0.25, 1.3)], hero=[],
                     tags=[c("H02_WAVE.png")], tpm=0.6, buffs=1,
                     fixed=[(c("H01_mural_get_well.png"), mu[0], mu[1] - mu[0], 1.35), (c("H04_sticker_luma.png"), U["west"](-2.2) - 0.25, 0.25, 1.4)])
    L["passage"] = dict(side="west", depth=[0, 16.3, 16.5], zones=[zone("west", -2.0, 1.9, 0.15, 1.2)], hero=[], tags=[c("H02_BEAM.png")],
                        tpm=0.5, buffs=1,
                        fixed=[(c("H04_heart_nurses.png"), U["west"](-6.3), 0.62, 1.5), (c("H04_sticker_luma.png"), U["west"](-8.4), 0.2, 1.35)])
    L["back_garage"] = dict(side="back", depth=[1, 1.95, 2.15], zones=[zone("back", 16.45, 24.35, 0.15, 2.2)],
                            hero=[dict(png=c("H02_KITE.png"), w=1.2)], tags=TAGS, tpm=1.0, buffs=2)
    info = {}
    for i, (key, spec) in enumerate(L.items()):
        side = spec["side"]
        out = os.path.join(OUT, f"G_HOS_1_{key}.png")
        tt.compose_graffiti_zones(W[side], H, PXM, spec["zones"], [], out, seed=cfg["seed"] * 100 + i, hero=spec["hero"],
                                  tags=spec["tags"], icons=spec.get("icons", ()), drips=(), tags_per_m2=spec["tpm"],
                                  n_buffs=spec["buffs"], peel_mask=os.path.join(ENT, "texturas", "K1_peel.png"))
        if spec.get("fixed"):                        # piezas en sitio fijo: el mural junto a la entrada, el corazón en urgencias
            cv = Image.open(out).convert("RGBA")
            for (png, u0, w_m, z0) in spec["fixed"]:     # (imagen, u inicial, ancho en m, z del pie)
                pc = Image.open(png).convert("RGBA")
                wpx = int(w_m * PXM)
                hpx = int(pc.size[1] * wpx / pc.size[0])
                pc = pc.resize((wpx, hpx), Image.LANCZOS)
                cv.alpha_composite(pc, (int(u0 * PXM), int(H * PXM - z0 * PXM - hpx)))
            cv.save(out)
        info[key] = dict(side=side, depth=spec["depth"], width_m=round(W[side], 3), height_m=H, px=[int(W[side] * PXM), int(H * PXM)],
                         px_per_m=PXM, zonas=len(spec["zones"]))
        print(key, info[key]["px"], flush=True)
    json.dump(info, open(os.path.join(OUT, "G_HOS_1_mapa.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

"""Paneles de grafiti del muelle MUE_1_carga (capa RGBA por cara + JPG de revisión): solo sobre paredes reales (zonas de
mue_builder.graffiti_zones) y fuera de los vanos. Uso: /root/blk-venv/bin/python graffiti_mue.py [--id MUE_1_carga]
Palabras y crews del kit (R4): KAOS, ZORO, NOVA, REXO (ficticios), Puro Corazón, Sin Miedo, Respeto, Con Safos, Isla Negra."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import bpy  # noqa: E402,F401  (mathutils viene con bpy)
import mue_builder as mb  # noqa: E402
import texture_tools as tt  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))
CUT = os.path.join(ENT, "lettering", "cutouts")
OUT = os.path.join(ENT, "texturas", "graffiti")
c = lambda n: os.path.join(CUT, n)  # noqa: E731
HEROES = {
    "front": [dict(png=c("C08_puro_corazon.png"), w=2.2), dict(png=c("S01_kaos.png"), w=2.0, rot=-3), dict(png=c("C07_sin_miedo.png"), w=1.8),
              dict(png=c("S03_nova.png"), w=1.6)],
    "back": [dict(png=c("S03_nova.png"), w=2.2, rot=2), dict(png=c("C06_respeto.png"), w=1.8), dict(png=c("S04_rexo.png"), w=1.6)],
    "west": [dict(png=c("S02_zoro.png"), w=2.0, rot=3), dict(png=c("C03_con_safos.png"), w=1.6), dict(png=c("C02_isla_negra.png"), w=1.4),
             dict(png=c("S01_kaos.png"), w=1.3)],
    "east": [dict(png=c("S04_rexo.png"), w=1.8), dict(png=c("C07_sin_miedo.png"), w=1.6), dict(png=c("S02_zoro.png"), w=1.4),
             dict(png=c("C08_puro_corazon.png"), w=1.4)],
}


def main():
    bid = sys.argv[sys.argv.index("--id") + 1] if "--id" in sys.argv else "MUE_1_carga"
    cfg = mb.cfg_mue(bid)
    gx0, gx1, gy0, gy1 = cfg["graffiti_bounds"]
    H = cfg["band_top"]
    PXM = cfg["graffiti_px_per_m"]
    zones, keep = mb.graffiti_zones()
    widths = {"front": gx1 - gx0, "back": gx1 - gx0, "west": gy1 - gy0, "east": gy1 - gy0}
    tags = [c(f"S05_hoja_tags_0{i}.png") for i in range(1, 7)]
    icons = [c(f"S06_hoja_iconos_0{i}.png") for i in (3, 5, 6)]    # sin 02 ni 04 (R4)
    drips = [c(f"S07_hoja_goteos_0{i}.png") for i in range(1, 7)]
    short = "_".join(bid.split("_")[:2])
    info = {}
    for i, side in enumerate(("front", "back", "west", "east")):
        W = widths[side]
        tt.compose_graffiti_zones(W, H, PXM, zones[side], keep[side], os.path.join(OUT, f"G_{short}_{side}.png"),
                                  seed=cfg["seed"] * 100 + i, hero=HEROES[side], tags=tags, icons=icons, drips=drips,
                                  peel_mask=os.path.join(ENT, "texturas", "K1_peel.png"),
                                  jpg_base=os.path.join(ENT, "texturas", "T1_concrete.png"),
                                  jpg_out=os.path.join(OUT, f"G_{short}_{side}.jpg"))
        info[side] = dict(width_m=round(W, 3), height_m=round(H, 3), px=[int(W * PXM), int(H * PXM)], px_per_m=PXM,
                          zonas=len(zones[side]), keepout=keep[side])
        print(side, info[side]["px"], "zonas", len(zones[side]), flush=True)
    json.dump(info, open(os.path.join(OUT, f"G_{short}_mapa.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

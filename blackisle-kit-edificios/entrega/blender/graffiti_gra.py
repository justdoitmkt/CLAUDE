"""Grafiti del granero con tienda GRA_1_tienda con su biblioteca EXCLUSIVA (lettering/gra/cutouts).

Regla R-GRAF (CLAUDE.md): solo grafiti callejero cholo/chicano y, aquí, por pedido del usuario, SOLO UN PAR de piezas en un
costado del granero: la placa gótica DRY CREEK con su roll call sobre la base de block y la firma "Sparky" en script sobre la
tabla roja, en el costado oriente (el que da a la tienda). Nada más: sin tags de relleno, sin murales, sin ilustraciones.
La capa se limita a la franja de profundidad del muro oriente del granero (lookdev.graffiti_map 'depth').
Uso: /root/blk-venv/bin/python graffiti_gra.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402,F401
from PIL import Image  # noqa: E402

import gra_builder as gb  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))
CUT = os.path.join(ENT, "lettering", "gra", "cutouts")
OUT = os.path.join(ENT, "texturas", "graffiti")


def main():
    cfg = gb.cfg_gra()
    gx0, gx1, gy0, gy1 = cfg["graffiti_bounds"]
    PXM = cfg["graffiti_px_per_m"]
    H = 4.6
    W = gy1 - gy0                                          # costado oriente: u = y - gy0
    cv = Image.new("RGBA", (int(W * PXM), int(H * PXM)), (0, 0, 0, 0))
    pieces = [  # (archivo, y inicial, ancho m, z del pie, opacidad)
        ("G01_DRYCREEK_placa.png", -6.75, 1.05, 0.22, 0.93),   # placa con roll call sobre el block
        ("G02_Sparky_firma.png", -3.85, 0.92, 1.58, 0.90),     # firma sobre la tabla, antes de la ventana
    ]
    for (fn, y0, w_m, z0, op) in pieces:
        pc = Image.open(os.path.join(CUT, fn)).convert("RGBA")
        wpx = int(w_m * PXM)
        hpx = int(pc.size[1] * wpx / pc.size[0])
        pc = pc.resize((wpx, hpx), Image.LANCZOS)
        a = pc.getchannel("A").point(lambda v: int(v * op))
        pc.putalpha(a)
        cv.alpha_composite(pc, (int((y0 - gy0) * PXM), int(H * PXM - z0 * PXM - hpx)))
    os.makedirs(OUT, exist_ok=True)
    cv.save(os.path.join(OUT, "G_GRA_1_east.png"))
    info = {"east": dict(side="east", depth=[0, gb.BX1 - 0.05, gb.BX1 + 0.10], width_m=round(W, 3), height_m=H,
                         px=[int(W * PXM), int(H * PXM)], px_per_m=PXM, zonas=0)}
    json.dump(info, open(os.path.join(OUT, "G_GRA_1_mapa.json"), "w"), indent=1)
    print("east", info["east"]["px"], flush=True)


if __name__ == "__main__":
    main()

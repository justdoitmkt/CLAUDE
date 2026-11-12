"""Grafiti del sitio de telecom COM_1_antena con su biblioteca EXCLUSIVA (lettering/com/cutouts).

Regla R-GRAF (CLAUDE.md): solo grafiti callejero cholo/chicano. El usuario no fijó cantidad; un sitio de telecom vigilado lleva
poco: unas cuantas piezas SOLO en la trasera de la caseta (la cara que da a la malla del fondo y al baldío): la placa gótica
STATIK, su roll call CHISPA / NENE / GUERO y las firmas en script "Chispa" y "Nene". Sin tags de relleno, sin murales, sin
ilustraciones propias. R4: nombres ficticios, sin números, coronas, estrellas ni puntos.
La capa se limita a la franja de profundidad del muro trasero de la caseta (lookdev.graffiti_map 'depth').
Uso: /root/blk-venv/bin/python graffiti_com.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402,F401
from PIL import Image  # noqa: E402

import com_builder as cb  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))
CUT = os.path.join(ENT, "lettering", "com", "cutouts")
OUT = os.path.join(ENT, "texturas", "graffiti")


def main():
    cfg = cb.cfg_com()
    gx0, gx1, gy0, gy1 = cfg["graffiti_bounds"]
    PXM = cfg["graffiti_px_per_m"]
    H = 3.3
    W = gx1 - gx0                                          # trasera: u = x1 - x (de oriente a poniente, como la ve quien está atrás)
    cv = Image.new("RGBA", (int(W * PXM), int(H * PXM)), (0, 0, 0, 0))
    pieces = [  # (archivo, u inicial, ancho m, z del pie, opacidad)
        ("G04_Nene_firma.png", 0.75, 0.62, 1.10, 0.88),        # firma chica junto a la esquina del puerto de cables
        ("G01_STATIK_placa.png", 1.70, 1.75, 0.62, 0.94),      # placa a media altura
        ("G02_STATIK_rollcall.png", 3.62, 0.60, 0.70, 0.92),   # roll call al lado de la placa
        ("G03_Chispa_firma.png", 4.45, 1.05, 1.62, 0.90),      # firma alta hacia el poniente
    ]
    for (fn, u0, w_m, z0, op) in pieces:
        pc = Image.open(os.path.join(CUT, fn)).convert("RGBA")
        wpx = int(w_m * PXM)
        hpx = int(pc.size[1] * wpx / pc.size[0])
        pc = pc.resize((wpx, hpx), Image.LANCZOS)
        a = pc.getchannel("A").point(lambda v: int(v * op))
        pc.putalpha(a)
        cv.alpha_composite(pc, (int((u0 + (cb.SH_X1 + 0.2 - gx1)) * PXM), int(H * PXM - z0 * PXM - hpx)))
    os.makedirs(OUT, exist_ok=True)
    cv.save(os.path.join(OUT, "G_COM_1_back.png"))
    info = {"back": dict(side="back", depth=[1, cb.SH_Y1 - 0.05, cb.SH_Y1 + 0.10], width_m=round(W, 3), height_m=H,
                         px=[int(W * PXM), int(H * PXM)], px_per_m=PXM, zonas=0)}
    json.dump(info, open(os.path.join(OUT, "G_COM_1_mapa.json"), "w"), indent=1)
    print("back", info["back"]["px"], flush=True)


if __name__ == "__main__":
    main()

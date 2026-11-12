"""texturas_granja.py — repetibles procedurales del granero con tienda (GRA_1_tienda), sin costura por construcción (toro).

Uso: /root/blk-venv/bin/python tools/texturas_granja.py
Escribe en entrega/texturas/:
  T10_tabla_roja.png  tablas verticales de 30 cm pintadas de rojo granero (2,4 m por repetición): veta vertical, nudos, pintura
                      deslavada por el sol con desprendimientos que dejan ver la madera gris, clavos en hileras y escurrimientos.
  T11_block.png       muro de block de concreto 40 x 20 cm aparejo cuatrapeado (2,4 m por repetición): poro, aristas
                      despostilladas, variación por pieza y junta de mortero de 1 cm rehundida.
  T12_barro.png       piso de barro rojo de 30 x 30 cm (1,2 m por repetición): variación de cocción por pieza, desgaste al
                      centro de cada loseta, cantos gastados, boquilla de cemento gris.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from texturas_hospital import _aniso_noise, _wrap_noise  # noqa: E402

TEX = os.path.abspath(os.path.join(HERE, "..", "..", "texturas"))


def _save(img, name, blur=0.0):
    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    out.save(os.path.join(TEX, name), optimize=True)


def tabla_roja(n=2048, seed=21, boards=8):
    r = np.random.default_rng(seed)
    bw = n // boards
    xx = np.arange(n)[None, :] * np.ones((n, 1))
    yy = np.arange(n)[:, None] * np.ones((1, n))
    # madera gris intemperizada (veta vertical: celdas largas en Y)
    grain = _aniso_noise(n, 48, 3, r, 3)
    fine = _aniso_noise(n, 160, 6, r, 2)
    wood = 0.42 + 0.20 * (grain - 0.5) + 0.10 * (fine - 0.5)
    wood_rgb = np.dstack([wood * 0.95, wood * 0.92, wood * 0.86])
    # pintura roja: tono por tabla, deslave por el sol (más claro y rosado arriba), ruido de brochazo vertical
    red = np.array([0.44, 0.115, 0.085])
    paint = np.ones((n, n, 3)) * red
    tone = np.zeros((n, n))
    for b in range(boards):
        tone[:, b * bw:(b + 1) * bw] = r.uniform(-0.06, 0.06)
    brush = _aniso_noise(n, 30, 2, r, 3)
    fade = _wrap_noise(n, 3, r, 3)
    paint *= (0.90 + tone + 0.12 * (brush - 0.5) + 0.16 * (grain - 0.5))[..., None]     # la veta asoma bajo la pintura
    paint = paint + (fade - 0.45).clip(0, 1)[..., None] * np.array([0.16, 0.09, 0.08])       # deslave rosado por zonas
    # desprendimientos: manchas alargadas en vertical, más en los bordes de cada tabla
    peel_n = _aniso_noise(n, 24, 5, r, 4)
    edge = np.abs(((xx % bw) / bw) - 0.5) * 2              # 0 al centro de la tabla, 1 en la junta
    peel = (peel_n + 0.16 * edge ** 4) > 0.735             # granero en uso: desprendimientos sueltos, no medio muro
    img = np.where(peel[..., None], wood_rgb, paint)
    # borde del desprendimiento: pintura levantada un poco más oscura
    pe = Image.fromarray((peel * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))
    ring = (np.asarray(pe) > 0) & ~peel
    img[ring] *= 0.82
    # junta entre tablas (quedará bajo el tapajuntas, pero da sombra en los cantos)
    for b in range(boards):
        x0 = b * bw
        for d in range(-3, 4):
            img[:, (x0 + d) % n] *= 0.55 + 0.12 * abs(d)
    # nudos
    for _ in range(18):
        cx, cy = r.integers(0, n), r.integers(0, n)
        rx, ry = r.uniform(6, 14), r.uniform(12, 26)
        d = ((((xx - cx + n / 2) % n - n / 2) / rx) ** 2 + (((yy - cy + n / 2) % n - n / 2) / ry) ** 2)
        img *= np.where(d < 1, 0.75 + 0.2 * d, 1.0)[..., None]
    # clavos en hileras (a la altura de los largueros: cada 0,6 m), con escurrimiento de óxido corto
    for row in range(4):
        y0 = int((row + 0.5) * n / 4)
        for b in range(boards):
            for side in (0.25, 0.75):
                cx = int(b * bw + side * bw)
                img[(y0 - 3) % n:(y0 + 3) % n or n, cx - 3:cx + 3] *= 0.35
                L = int(r.uniform(8, 40))
                for k in range(L):
                    img[(y0 + 3 + k) % n, cx - 1:cx + 2] *= 0.88 + 0.12 * k / L
    _save(img, "T10_tabla_roja.png", 0.5)


def block(n=2048, seed=22, cols=6, rows=12):
    r = np.random.default_rng(seed)
    bw, bh = n // cols, n // rows
    base = np.ones((n, n, 3)) * np.array([0.56, 0.56, 0.54])
    pores = _wrap_noise(n, 90, r, 2)
    big = _wrap_noise(n, 5, r, 3)
    img = base * (0.86 + 0.18 * (pores - 0.5) + 0.10 * (big - 0.5))[..., None]
    for _ in range(60000):                                  # poro grueso del block de jalcreto
        x, y = r.integers(0, n), r.integers(0, n)
        img[y, x] *= r.uniform(0.55, 0.85)
    g = max(4, int(0.010 / (2.4 / n)))
    for j in range(rows):
        off = (bw // 2) if j % 2 else 0
        for i in range(cols):
            tone = r.uniform(-0.05, 0.05)
            y0, x0 = j * bh, (i * bw + off) % n
            ys = np.arange(y0, y0 + bh) % n
            xs = np.arange(x0, x0 + bw) % n
            img[np.ix_(ys, xs)] *= 1 + tone
            # despostilladuras en las aristas
            for _ in range(int(r.integers(0, 4))):
                cx, cy = x0 + r.integers(0, bw), y0 + (0 if r.random() < 0.5 else bh)
                rad = int(r.integers(4, 12))
                yy, xx = np.ogrid[-rad:rad, -rad:rad]
                m = (xx * xx + yy * yy) < rad * rad
                img[np.ix_((cy + np.arange(-rad, rad)) % n, (cx + np.arange(-rad, rad)) % n)][m] *= 0.8
    mortar = np.array([0.66, 0.65, 0.62])
    for j in range(rows):
        y0 = j * bh
        img[np.arange(y0 - g // 2, y0 + g - g // 2) % n, :] = mortar * 0.86
        img[np.arange(y0 - g // 2, y0 - g // 2 + 3) % n, :] *= 0.62     # sombra bajo el canto del block de arriba (junta rehundida)
        off = (bw // 2) if j % 2 else 0
        for i in range(cols):
            x0 = (i * bw + off) % n
            img[np.ix_(np.arange(y0, y0 + bh) % n, np.arange(x0 - g // 2, x0 + g - g // 2) % n)] = mortar * 0.86
    _save(img, "T11_block.png", 0.6)


def barro(n=1024, seed=23, tiles=4):
    r = np.random.default_rng(seed)
    s = n // tiles
    img = np.zeros((n, n, 3))
    nz = _wrap_noise(n, 12, r, 4)
    yy, xx = np.mgrid[0:s, 0:s] / s
    wear = 1 - ((xx - 0.5) ** 2 + (yy - 0.5) ** 2) * 2.2       # gastado al centro (paso)
    for j in range(tiles):
        for i in range(tiles):
            c = np.array([0.55, 0.24, 0.13]) * r.uniform(0.82, 1.12) + r.normal(0, 0.015, 3)
            tile = np.ones((s, s, 3)) * c
            tile *= (0.94 + 0.10 * wear.clip(0, 1))[..., None]
            img[j * s:(j + 1) * s, i * s:(i + 1) * s] = tile
    img *= (0.90 + 0.18 * (nz - 0.5))[..., None]
    for _ in range(9000):                                   # picaduras de la cocción
        x, y = r.integers(0, n), r.integers(0, n)
        img[y, x] *= r.uniform(0.6, 0.85)
    g = max(3, int(0.008 / (1.2 / n)))
    grout = np.array([0.50, 0.48, 0.45])
    for k in range(tiles):
        a = k * s
        idx = np.arange(a - g // 2, a + g - g // 2) % n
        img[:, idx] = grout
        img[idx, :] = grout
        for d in range(1, 5):                                # canto gastado (más oscuro) junto a la boquilla
            for j in ((a + g - g // 2 + d - 1) % n, (a - g // 2 - d) % n):
                img[:, j] *= 0.80 + 0.045 * d
                img[j, :] *= 0.80 + 0.045 * d
    _save(img, "T12_barro.png", 0.5)


if __name__ == "__main__":
    tabla_roja()
    block()
    barro()
    print("ok", TEX)

"""texturas_militar.py — repetibles procedurales de la base militar (MIL_1_almacen / MIL_2_avanzada), sin costura (toro).

Uso: /root/blk-venv/bin/python tools/texturas_militar.py
Escribe en entrega/texturas/:
  T15_lona.png        lona de algodón/poliéster verde olivo de tienda (1,0 m): tejido de tafetán fino, moteado de teñido,
                      polvo en zonas y alguna mancha de agua seca.
  T16_costal_pp.png   costal de polipropileno tejido (0,6 m): cintas planas de ~3 mm en tafetán, color arena con brillo de
                      cinta y polvo.
  T17_geotextil.png   geotextil no tejido de los HESCO (1,0 m): fieltro de fibras cortas color arena con motas.
  T18_madera_od.png   tabla pintada verde olivo de las cajas de munición (1,2 m): veta que se nota bajo la pintura, cantos
                      gastados y raspones a madera clara.
  T19_camuflaje.png   tela de red de camuflaje desértico (2,0 m): manchas arena, café y verde seco de bordes recortados.
  T20_triplay.png     triplay de pino (1,22 m): chapa con vetas anchas, nudos parchados y polvo de pisadas.
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


def _weave(n, threads, r, contrast=0.12):
    """Tafetán: hilos de urdimbre y trama alternando arriba/abajo (periódico)."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    p = n / threads
    u, v = xx / p, yy / p
    iu, iv = np.floor(u), np.floor(v)
    fu, fv = u - iu, v - iv
    over = ((iu + iv) % 2) == 0
    warp = np.sin(np.pi * fu) ** 0.6           # perfil redondeado del hilo vertical
    weft = np.sin(np.pi * fv) ** 0.6
    h = np.where(over, warp * (0.6 + 0.4 * np.sin(np.pi * fv)), weft * (0.6 + 0.4 * np.sin(np.pi * fu)))
    jit = _wrap_noise(n, threads // 4, r, 2)
    return 1.0 + contrast * (h - 0.5) + 0.04 * (jit - 0.5)


def lona(n=1024, seed=41):
    r = np.random.default_rng(seed)
    base = np.array([0.255, 0.275, 0.165])
    w = _weave(n, 340, r, 0.10)
    mott = _wrap_noise(n, 6, r, 4)
    img = base[None, None] * (w * (0.92 + 0.16 * (mott - 0.5)))[..., None]
    dust = np.clip((_wrap_noise(n, 4, r, 4) - 0.55) * 2.5, 0, 1) * 0.35
    img = img * (1 - dust[..., None]) + np.array([0.48, 0.44, 0.34]) * dust[..., None]
    stain = np.clip((_wrap_noise(n, 3, r, 3) - 0.68) * 6, 0, 1)
    ring = np.clip(stain * (1 - stain) * 4, 0, 1) * 0.12
    img *= (1 - ring)[..., None]
    _save(img, "T15_lona.png", 0.3)


def costal_pp(n=1024, seed=42):
    r = np.random.default_rng(seed)
    base = np.array([0.56, 0.49, 0.34])
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    tapes = 200                                  # 0,6 m / 200 = 3 mm por cinta
    p = n / tapes
    u, v = xx / p, yy / p
    over = ((np.floor(u) + np.floor(v)) % 2) == 0
    fu, fv = u % 1, v % 1
    gap = np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv))
    sheen = np.where(over, 0.08 * np.cos(np.pi * (fv - 0.5)), 0.08 * np.cos(np.pi * (fu - 0.5)))
    img = base[None, None] * (1.0 + sheen - 0.07 * (gap < 0.05) - 0.05 * np.clip(0.12 - gap, 0, 0.12) / 0.12)[..., None]
    tone = _wrap_noise(n, 8, r, 3)
    img *= (0.93 + 0.12 * (tone - 0.5))[..., None]
    dust = np.clip((_wrap_noise(n, 5, r, 4) - 0.5) * 2.0, 0, 1) * 0.25
    img = img * (1 - dust[..., None]) + np.array([0.62, 0.55, 0.42]) * dust[..., None]
    _save(img, "T16_costal_pp.png", 0.35)


def geotextil(n=1024, seed=43):
    r = np.random.default_rng(seed)
    base = np.array([0.53, 0.45, 0.32])
    f1 = _wrap_noise(n, 220, r, 2)
    f2 = _aniso_noise(n, 300, 40, r, 2)
    f3 = _aniso_noise(n, 40, 300, r, 2)
    fib = 0.5 * f1 + 0.25 * f2 + 0.25 * f3
    img = base[None, None] * (0.84 + 0.32 * (fib - 0.5))[..., None]
    specks = r.random((n, n)) < 0.01
    img[specks] *= 0.6
    tone = _wrap_noise(n, 5, r, 3)
    img *= (0.92 + 0.14 * (tone - 0.5))[..., None]
    _save(img, "T17_geotextil.png", 0.4)


def madera_od(n=1024, seed=44, boards=6):
    r = np.random.default_rng(seed)
    bw = n // boards
    grain = _aniso_noise(n, 3, 90, r, 3)       # veta a lo largo de X (la caja se mapea con la tabla horizontal)
    fine = _aniso_noise(n, 8, 260, r, 2)
    wood = 0.47 + 0.22 * (grain - 0.5) + 0.10 * (fine - 0.5)
    wood_rgb = np.dstack([wood * 1.0, wood * 0.82, wood * 0.58])
    od = np.array([0.205, 0.225, 0.13])
    paint = np.ones((n, n, 3)) * od
    tone = np.zeros((n, n))
    for b in range(boards):
        tone[b * bw:(b + 1) * bw, :] = r.uniform(-0.05, 0.05)
    paint *= (0.95 + tone + 0.10 * (grain - 0.5) + 0.05 * (fine - 0.5))[..., None]
    yy = np.arange(n)[:, None] * np.ones((1, n))
    edge = np.abs(((yy % bw) / bw) - 0.5) * 2
    wearn = _aniso_noise(n, 12, 50, r, 3)
    worn = (wearn + 0.20 * edge ** 6) > 0.86
    img = np.where(worn[..., None], wood_rgb, paint)
    for b in range(boards):
        y0 = b * bw
        for d in range(-2, 3):
            img[(y0 + d) % n, :] *= 0.5 + 0.12 * abs(d)
    _save(img, "T18_madera_od.png", 0.4)


def camuflaje(n=1024, seed=45):
    r = np.random.default_rng(seed)
    cols = [np.array([0.50, 0.43, 0.30]), np.array([0.34, 0.27, 0.17]), np.array([0.30, 0.31, 0.19]), np.array([0.62, 0.55, 0.40])]
    a = _wrap_noise(n, 5, r, 4)
    b = _wrap_noise(n, 7, r, 4)
    img = np.ones((n, n, 3)) * cols[0]
    img = np.where((a > 0.56)[..., None], cols[1], img)
    img = np.where((b > 0.60)[..., None], cols[2], img)
    img = np.where(((a < 0.38) & (b < 0.45))[..., None], cols[3], img)
    img *= (0.94 + 0.12 * (_wrap_noise(n, 60, r, 2) - 0.5))[..., None]
    _save(img, "T19_camuflaje.png", 0.6)


def triplay(n=1024, seed=46):
    r = np.random.default_rng(seed)
    grain = _aniso_noise(n, 2, 30, r, 4)
    rings = np.sin((grain * 18.0) * np.pi) * 0.5 + 0.5
    base = 0.62 + 0.10 * (rings - 0.5) + 0.06 * (_aniso_noise(n, 6, 200, r, 2) - 0.5)
    img = np.dstack([base * 0.96, base * 0.80, base * 0.56])
    yy, xx = np.mgrid[0:n, 0:n]
    for _ in range(5):                                   # parches de nudo (elipses de chapa sustituida)
        cx, cy = r.integers(0, n), r.integers(0, n)
        rx, ry = r.uniform(18, 30), r.uniform(8, 14)
        d = (((xx - cx + n / 2) % n - n / 2) / rx) ** 2 + (((yy - cy + n / 2) % n - n / 2) / ry) ** 2
        img = np.where((d < 1)[..., None], img * 1.04, img)
        img = np.where(((d > 0.92) & (d < 1.06))[..., None], img * 0.95, img)
    foot = np.clip((_wrap_noise(n, 4, r, 4) - 0.5) * 2.0, 0, 1) * 0.3
    img = img * (1 - foot[..., None]) + np.array([0.45, 0.40, 0.32]) * foot[..., None]
    _save(img, "T20_triplay.png", 0.4)


if __name__ == "__main__":
    lona()
    costal_pp()
    geotextil()
    madera_od()
    camuflaje()
    triplay()
    print("ok", TEX)

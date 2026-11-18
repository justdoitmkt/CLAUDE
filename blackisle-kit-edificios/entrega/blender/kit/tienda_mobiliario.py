"""kit/tienda_mobiliario.py — mobiliario AAA de la tienda de campaña MIL_2_avanzada (expendio de munición y armas del puesto
avanzado). Segunda pasada R-AAA de las piezas que antes vivían en kit/campaign.py, con las MISMAS firmas, orígenes, orientación
y huellas (± 2 cm), para que mil_builder.py las coloque igual:

    plywood_floor(L=9.5, W=5.8, seed=0, ramp=True)       crate_counter(L=2.4, seed=0)
    shelving(w=1.2, seed=0, stock="mixed")               weapon_rack_slots(n=8)      weapon_rack(n=8, seed=0)
    pegboard_hooks(w=1.2, h=1.0)                         pegboard(w=1.2, h=1.0, seed=0, posts=None)
    folding_table(L=1.83, seed=0)                        folding_chair(seed=0)
    string_lights(points=(...), n=6, seed=0)             hanging_sign(text="SUPPLY", w=0.9, seed=0)

Todo se ve a < 1,5 m: construcción real (tablas con holgura y cantos redondeados, triplay con chapas en el canto, tornillos
avellanados con cruz, lámina doblada con radio, perforaciones pasantes reales, soldaduras, remaches, bisagras con nudillos y
perno, cuerdas y cables con catenaria). Nada redondo facetado: cilindros visibles >= 24 lados, tubos y cuerdas >= 14, alambres
y cables <= 6 mm con 12 lados dentro de mb.soft(). Estado: limpio, mantenido, poco desgaste (rozones de pisadas, cantos un poco
despostillados, polvo); nada roto. Sin grafiti ni placas. Textos en inglés e inocuos (R4); esténciles con kit.fonts.

CONVENCIONES (como kit/campaign.py): MB de kit.clinic; metros, Z arriba; piezas de piso con origen en el piso al centro de la
huella y frente (cliente) hacia -Y; piezas de muro (shelving, pegboard) con la espalda en y = 0 y crecen hacia -Y;
string_lights en coordenadas absolutas; hanging_sign con origen en el punto de cuelgue.

MEDIDAS VERIFICADAS (web, 2026-11-18):
- Triplay 4 × 8 ft de 23/32" (18,3 mm) y 2×4 real de 1-1/2 × 3-1/2" (38 × 89 mm): inchcalculator.com/actual-plywood-thickness-size/,
  inchcalculator.com/actual-size-of-dimensional-lumber/. Holgura de 1/8" entre hojas y tornillos a 6" en extremos de hoja y 12"
  en apoyos intermedios, 3/8" del canto (APA): apawood.org/Data/Sites/1/documents/handouts/quality-floors-from-start-to-finish.pdf
- Caja de dinero de lámina 11,8 × 9,4 × 3,5" (30 × 24 × 9 cm), lámina de 0,79 mm: bhphotovideo.com/c/product/937610-REG/
- Tabla con clip 9 × 12-1/2" de hardboard de 1/8" con clip de perfil bajo: officechase.com/products/universal-hardboard-clipboard-unv40304
- Anaquel 48 × 18 × 72" de 5 entrepaños, postes de cal. 14 y entrepaños de cal. 22 con contravientos en espalda y costados:
  globalindustrial.com/p/shelving-48x18x72-with-5-shelves-no-deck ; zoro.com/hallowell-metal-shelving-18d-x-48w-x-87h-6-shelves-steel-a4711-18hg/i/G8245377
- Caja RSC de cartón corrugado de una pared, flauta C (~4 mm) con unión de fabricante pegada:
  en.wikipedia.org/wiki/Corrugated_box_design
- Candado laminado de 40 mm: arco de 7 mm, claro interior 19 × 16 mm, cuerpo 40 × 33 × 21 mm:
  masterlock.com/products/product/3 ; screwfix.ie/p/master-lock-3eurd-laminated-steel-water-resistant-padlock-40mm/48804
- Tablero perforado de hardboard de 1/4" con agujeros de 1/4" a 1" entre centros; gancho de un brazo de 4" de alambre de
  0,149-0,186": doitbest.com/product/100061/ ; products.kinter.com/compare/metal-display-hooks/single-prong-all-wire-pegboard-hook
- Mesa plegable de 6 ft 72 × 30 × 29" de polietileno de alta densidad sobre bastidor de acero, tubo de pata de 0,9" (25 mm),
  2" de espesor: lifetime.com/lifetime-2924g-6-foot-folding-table ; homehardware.ca/en/p/4468538
- Silla plegable de acero: tubo de 7/8" cal. 18, asiento a 17-1/2", alto total 29-1/2": todaysclassroom.com/national-public-seating-300-steel-folding-chair-17-5-seat-height-set-of-4 ;
  schooloutlet.com/167_Premium_Folding_Chair_p/167.htm
- Serie comercial: cable SJTW 14 AWG de 2 hilos, socket E26 colgante a 24": partylights.com/48-Medium-Base-String-Light-Suspended-Socket/ ;
  socket de hule Ø 1,7 × 2,1": 1000bulbs.com/product/229424/PLT-11947.html ; foco A19 Ø 60 × 99-109 mm (ANSI C79.1):
  attainablehome.com/?p=22740
"""
import math

import bmesh  # noqa: F401
import bpy  # noqa: F401  (bpy antes que mathutils)
import numpy as np
from mathutils import Matrix, Vector, noise

from kit import port
from kit.campaign import _catenary, _cyl, _f, _frame_z, _jit, _lathe, _ring, _slab_grid, _tube  # noqa: F401
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rr_profile, rtube  # noqa: F401
from kit.clinic_equipo import loft_rings, loop_tube, revolve, sweep_frame  # noqa: F401
from kit.clinic_servicios import rr_pts, skin, slab  # noqa: F401
from kit.common import rng
from kit.fonts import text_font

IN = 0.0254
SEG = 24          # lados de todo cilindro visible
SEG_T = 14        # tubos, cuerdas y cables > 6 mm


# ======================================================================================================== utilidades
def _soft(mb):
    return mb.soft()


def _axis_samples(a, b, r, m=2, step=0.1, forced=(), r1=None):
    """Coordenadas de muestreo de a a b para _dbox: zonas redondeadas [a, a + r] y [b - r1, b] con m segmentos por 45° (ángulo
    uniforme), interior a paso <= step y valores forzados (líneas de tornillos, despostilladuras, bordes de chapas)."""
    r1 = r if r1 is None else r1
    out = []
    if r > 0:
        out += [a + r * (1 - math.tan(PI / 4 * k / m)) for k in range(m, -1, -1)]
    else:
        out.append(a)
    ia, ib = a + r, b - r1
    n = max(1, int(math.ceil((ib - ia) / step))) if ib > ia else 0
    out += [ia + (ib - ia) * k / n for k in range(1, n)] if n else []
    if r1 > 0:
        out += [b - r1 * (1 - math.tan(PI / 4 * k / m)) for k in range(0, m + 1)]
    else:
        out.append(b)
    out += [f for f in forced if ia + 1e-4 < f < ib - 1e-4]
    out = sorted(out)
    res = [out[0]]
    for v in out[1:]:
        if v - res[-1] > 2e-5:
            res.append(v)
    return np.array(res)


def _dbox(mb, M, xs, ys, zs, r, mat, disp=None, skip=(), ngon=(), matfn=None):
    """Caja de cantos redondeados (radio r, escalar o (rx, ry, rz)) generada desde un cubo subdividido por las muestras xs, ys,
    zs (ver _axis_samples): cada punto del cubo se proyecta al sólido redondeado; disp(Q, N, P) -> desplazamientos (n, 3)
    (alabeo, abombado, desgaste, despostilladuras). Caras: 0 x-, 1 x+, 2 y-, 3 y+, 4 z-, 5 z+. skip: caras omitidas (caja
    abierta); ngon: caras cerradas con un solo polígono (cara oculta plana: fondo de una hoja apoyada). matfn(fid, P) -> material
    por celda. Devuelve (verts dict, función de posición)."""
    S = [np.asarray(xs, float), np.asarray(ys, float), np.asarray(zs, float)]
    n = [len(s) for s in S]
    rr = np.array(r if isinstance(r, (tuple, list)) else (r, r, r), float)
    rr = np.maximum(rr, 1e-6)
    lo = np.array([S[0][0], S[1][0], S[2][0]]) + rr
    hi = np.array([S[0][-1], S[1][-1], S[2][-1]]) - rr
    keys = {}
    order = []

    def K(idx):
        if idx not in keys:
            keys[idx] = len(order)
            order.append(idx)
        return keys[idx]
    quads = []
    for fid in range(6):
        a, side = fid // 2, fid % 2
        b, c = (a + 1) % 3, (a + 2) % 3
        ia = 0 if side == 0 else n[a] - 1
        if fid in skip:
            continue
        if fid in ngon:
            loop = []
            for u in range(n[b] - 1):
                loop.append((u, 0))
            for v in range(n[c] - 1):
                loop.append((n[b] - 1, v))
            for u in range(n[b] - 1, 0, -1):
                loop.append((u, n[c] - 1))
            for v in range(n[c] - 1, 0, -1):
                loop.append((0, v))
            ids = []
            for (u, v) in loop:
                idx = [0, 0, 0]
                idx[a], idx[b], idx[c] = ia, u, v
                ids.append(K(tuple(idx)))
            quads.append((fid, ids[::-1] if side == 0 else ids, None))
            continue
        for u in range(n[b] - 1):
            for v in range(n[c] - 1):
                q = []
                for (du, dv) in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    idx = [0, 0, 0]
                    idx[a], idx[b], idx[c] = ia, u + du, v + dv
                    q.append(K(tuple(idx)))
                quads.append((fid, q[::-1] if side == 0 else q, (u, v)))
    I = np.array(order)
    P = np.stack([S[0][I[:, 0]], S[1][I[:, 1]], S[2][I[:, 2]]], -1)
    C = np.clip(P, lo, hi)
    D = (P - C) / rr
    L = np.linalg.norm(D, axis=1, keepdims=True)
    Nn = D / np.maximum(L, 1e-12)
    Q = C + Nn * rr
    N = Nn / rr
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    if disp is not None:
        Q = Q + disp(Q, N, P)
    Mx = np.array(M) if M is not None else np.eye(4)
    Qw = Q @ Mx[:3, :3].T + Mx[:3, 3]
    V = [mb.bm.verts.new(tuple(p)) for p in Qw]
    mi_def = mb.mi(mat)
    for (fid, q, uv) in quads:
        f = mb.bm.faces.new([V[i] for i in q])
        if matfn is not None and uv is not None:
            pc = P[q].mean(0)
            f.material_index = mb.mi(matfn(fid, pc))
        else:
            f.material_index = mi_def
        f.smooth = True
    return V, Q


def _board(mb, x0, x1, y0, y1, z0, z1, mat, r=0.003, M=None, step=0.25, disp=None, m=2, skip=(), ngon=()):
    """Tabla / lámina de cantos redondeados reales (radio r, 4 segmentos por cuarto de vuelta) dada por su caja."""
    r = min(r, 0.45 * min(x1 - x0, y1 - y0, z1 - z0))
    xs = _axis_samples(x0, x1, r, m, step)
    ys = _axis_samples(y0, y1, r, m, step)
    zs = _axis_samples(z0, z1, r, m, step)
    return _dbox(mb, M, xs, ys, zs, r, mat, disp=disp, skip=skip, ngon=ngon)


def _screw_cs(mb, M, d=0.0082, seed=0, proud=0.0004, mat="steel"):
    """Tornillo avellanado de cabeza plana con cruz (Phillips): cabeza a ras (proud sobre la cara, sin z-fighting), bisel que se
    hunde en la madera y cruz de 4 brazos hundida 1,3 mm. M: z local = normal de la cara, origen en la cara."""
    rot = ((abs(int(seed)) * 0.618034) % 1.0) * PI / 2
    seg = 12
    R = d / 2

    def ring(rad_fn, z):
        out = []
        for k in range(seg):
            a = rot + 2 * PI * k / seg
            rr_ = rad_fn(a)
            out.append(mb.bm.verts.new(M @ Vector((rr_ * math.cos(a), rr_ * math.sin(a), z))))
        return out
    A = ring(lambda a: R * 1.04, -0.0005)
    B = ring(lambda a: R * 0.9, proud)
    Cx = ring(lambda a: R * (0.17 + 0.42 * max(0.0, math.cos(2 * (a - rot))) ** 4), proud)
    pole = mb.bm.verts.new(M @ Vector((0, 0, proud - 0.0013)))
    mi = mb.mi(mat)
    for k in range(seg):
        kk = (k + 1) % seg
        for q in ((A[k], A[kk], B[kk], B[k]), (B[k], B[kk], Cx[kk], Cx[k]), (Cx[k], Cx[kk], pole)):
            f = mb.bm.faces.new(q)
            f.material_index = mi
            f.smooth = True


def _nail(mb, M, r=0.0035, mat="steel", seg=12):
    """Cabeza de clavo común (abombada 0,9 mm, hundida 0,4 mm), sombreado suave."""
    with mb.soft():
        revolve(mb, [(r * 1.02, -0.0004), (r, 0.0003), (r * 0.75, 0.0008), (r * 0.35, 0.0011), (0.0, 0.0012)], mat, seg=seg, M=M,
                caps=False)


def _hexbolt(mb, M, d=0.008, h=None, washer=True, mat="steel", stub=0.0):
    """Perno hexagonal con chaflán, rondana y punta de rosca opcional (stub) del otro lado; apoyado en z = 0 local, eje +Z."""
    h = h if h is not None else d * 0.65
    s = d * 0.78          # entre caras / 2
    z = 0.0
    if washer:
        _lathe(mb, [(d * 0.55, -0.0003), (d * 1.05, -0.0003), (d * 1.05, d * 0.12), (d * 0.98, d * 0.16), (d * 0.55, d * 0.16)],
               M, mat, seg=SEG, closed=True)
        z = d * 0.16
    rc = s / math.cos(PI / 6)
    prof = [(rc * 0.94, z), (rc, z + h * 0.12), (rc, z + h * 0.8), (s * 0.98, z + h), (0.0, z + h)]
    loops = []
    for (rad, zz) in prof:
        if rad < 1e-6:
            loops.append([(0.0, 0.0, zz)])
            continue
        L = []
        for k in range(6):
            for j in range(4):                       # esquinas del hexágono con chaflán (4 puntos por arista)
                a0, a1 = PI / 3 * k + PI / 6, PI / 3 * (k + 1) + PI / 6
                t = j / 4
                p0 = Vector((math.cos(a0), math.sin(a0), 0)) * rad
                p1 = Vector((math.cos(a1), math.sin(a1), 0)) * rad
                p = p0.lerp(p1, t)
                lim = min(rad, s / math.cos(PI / 6) * (0.93 if zz > z + h * 0.85 or zz < z + h * 0.05 else 1.0))
                if p.length > lim:
                    p = p.normalized() * lim
                L.append((p.x, p.y, zz))
        loops.append(L)
    skin(mb, loops, mat, M, cap0=True, cap1=False)
    if stub > 0:
        _lathe(mb, [(d / 2 * 0.95, -stub), (d / 2, -stub + 0.0008), (d / 2, 0.0)], M, mat, seg=16)


def _rivet(mb, M, r=0.0035, mat="steel"):
    """Remache de cabeza redonda (domo), hundido 0,3 mm."""
    with mb.soft():
        revolve(mb, [(r * 1.02, -0.0003), (r, 0.0004), (r * 0.82, 0.0013), (r * 0.45, 0.0019), (0.0, 0.0021)], mat, seg=12, M=M,
                caps=False)


def _noise2(x, y, f, seed):
    return np.array([noise.noise(Vector((a * f + seed * 3.17, b * f - seed * 1.93, seed * 0.71))) for a, b in
                     zip(np.ravel(x), np.ravel(y))]).reshape(np.shape(x))


def _seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / max(L2, 1e-12), 0.0, 1.0)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ======================================================================================================== piso de triplay
PLY_T = 0.0183                 # triplay de 23/32"
JOIST_H = 0.0895               # 2×4 de canto (3-1/2" + tolerancia de aserradero)
FLOOR_TOP = JOIST_H + 0.0002 + PLY_T   # = 0,108 (cara superior del piso; mil_builder usa 0,108)


def _ply_zs(z0, t, r, n_ply=7):
    """Muestras de z de una hoja de triplay: redondeos del canto y, en el canto, las chapas cruzadas (2ª, 4ª, 6ª) hundidas."""
    pz = [z0 + t * k / n_ply for k in range(1, n_ply)]
    cz = [z0 + t * (k + 0.5) / n_ply for k in (1, 3, 5)]
    return _axis_samples(z0, z0 + t, r, 2, 1.0, forced=pz + cz)


def _ply_sheet(mb, x0, x1, y0, y1, z0, t, seed, topfn=None, chips=(), M=None, step=0.15, r=0.0016, extra_x=(), extra_y=()):
    """Hoja de triplay como sólido: cara superior en rejilla (alabeo, desgaste y desniveles vía topfn(x, y) -> dz), canto con
    las chapas a la vista (las chapas cruzadas 0,3 mm hundidas), cantos matados r y despostilladuras chips = [(lado, s, largo,
    profundidad)] con lado 0 x-, 1 x+, 2 y-, 3 y+ y s la coordenada a lo largo del canto: la chapa de cara se desprende en un
    escalón de borde vivo (meseta con flancos cortos), no una abolladura. Fondo plano de un polígono (cara apoyada)."""
    fx = list(extra_x) + [x0 + 0.004, x0 + 0.009, x1 - 0.004, x1 - 0.009]
    fy = list(extra_y) + [y0 + 0.004, y0 + 0.009, y1 - 0.004, y1 - 0.009]
    for (side, s, ln, dep) in chips:
        tgt = fy if side < 2 else fx
        tgt += [s - ln / 2 - 0.002, s - ln / 2 + 0.0015, s - ln * 0.15, s + ln * 0.2, s + ln / 2 - 0.0015, s + ln / 2 + 0.002]
    xs = _axis_samples(x0, x1, r, 2, step, forced=fx)
    ys = _axis_samples(y0, y1, r, 2, step, forced=fy)
    zs = _ply_zs(z0, t, r)
    ply = t / 7
    cross = [(z0 + ply * k, z0 + ply * (k + 1)) for k in (1, 3, 5)]

    def disp(Q, N, P):
        D = np.zeros_like(Q)
        w = np.clip((Q[:, 2] - z0) / t, 0.0, 1.0) ** 2
        if topfn is not None:
            D[:, 2] += topfn(Q[:, 0], Q[:, 1]) * w
        # chapas cruzadas hundidas en el canto (solo en las caras laterales, fuera de los redondeos)
        side = (np.abs(N[:, 2]) < 0.2)
        rec = np.zeros(len(Q))
        for (za, zb) in cross:
            zc, hw = (za + zb) / 2, (zb - za) / 2
            rec += np.clip(1.6 * (1 - np.abs(Q[:, 2] - zc) / hw), 0, 1)
        rec *= side * 0.0003
        D[:, 0] -= N[:, 0] * rec
        D[:, 1] -= N[:, 1] * rec
        for (sd, s, ln, dep) in chips:
            if sd < 2:
                along, edge = Q[:, 1], (x0 if sd == 0 else x1)
                dist = np.abs(Q[:, 0] - edge)
                nx_, ny_ = (1.0 if sd == 0 else -1.0), 0.0
            else:
                along, edge = Q[:, 0], (y0 if sd == 2 else y1)
                dist = np.abs(Q[:, 1] - edge)
                nx_, ny_ = 0.0, (1.0 if sd == 2 else -1.0)
            g = np.clip((ln / 2 - np.abs(along - s)) / 0.003, 0, 1)            # meseta con flancos de 3 mm
            reach = 0.0065 * (0.8 + 0.4 * np.sin(along * 900.0 + s * 37.0))   # orilla del desprendimiento irregular
            h = np.clip((reach - dist) / 0.0025, 0, 1) * np.clip((Q[:, 2] - (z0 + t - dep * 2.5)) / (dep * 1.5), 0, 1)
            a = dep * g * h
            D[:, 0] += nx_ * a * 0.35
            D[:, 1] += ny_ * a * 0.35
            D[:, 2] -= a
        return D
    _dbox(mb, M, xs, ys, zs, r, "plywood", disp=disp, ngon=(4,))


def _floor_wear(L, W):
    """Desgaste por pisadas (m, positivo = hundido) en las zonas de paso de la tienda: de la rampa (-X) al centro, detrás del
    mostrador, el pasillo frente a anaqueles y armeros (+Y), detrás de la mesa y el paso entre mostrador y mesa."""
    sx, sy = L / 9.5, W / 5.8
    segs = [((-4.75, 0.0), (-2.0, -0.3), 0.45, 1.0), ((-2.0, -0.3), (0.8, -1.65), 0.4, 0.8), ((-1.8, -1.75), (0.6, -1.75), 0.3, 1.0),
            ((-2.0, -0.3), (-1.0, 1.85), 0.35, 0.7), ((-4.4, 1.9), (3.4, 1.9), 0.35, 0.9), ((0.9, -1.45), (2.6, -1.6), 0.3, 0.6),
            ((0.82, -2.9), (0.82, -1.6), 0.3, 0.9)]
    segs = [((a[0] * sx, a[1] * sy), (b[0] * sx, b[1] * sy), w, k) for (a, b, w, k) in segs]

    def f(x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        acc = np.zeros_like(x)
        for (a, b, w, k) in segs:
            d = _seg_dist(x, y, a, b)
            acc = np.maximum(acc, k * np.exp(-(d / w) ** 2))
        return 0.00045 * acc
    return f


def plywood_floor(L=9.5, W=5.8, seed=0, ramp=True):
    """Tarima de la tienda: durmientes de 2×4" de canto (38 × 89 mm) a 16" (406 mm) entre centros a lo largo de X, en sentido
    Y, cerrados por cabezales de 2×4 en los cantos largos (clavados de punta, dos clavos 16d por durmiente); hojas de triplay de
    4 × 8 ft × 23/32" con la veta larga atravesada a los durmientes, hiladas trabadas (juntas a 4 ft) y holgura de 1/8" en todas
    las juntas; juntas de extremo sobre el eje de un durmiente. Cada hoja: canto con sus 7 chapas a la vista (las cruzadas un
    poco hundidas), cantos matados con algunas despostilladuras, alabeo leve, desniveles de medio milímetro entre hojas y
    desgaste por pisadas en las zonas de paso. Tornillos avellanados con cruz a 6" en los extremos de hoja y 12" en los
    durmientes intermedios, a 3/8" del canto. ramp=True: rampa de entrada en el testero -X (frente a la puerta de la tienda),
    1,10 × 0,60 m, de triplay sobre tres largueros cónicos, con listones antiderrapantes y escuadras atornilladas al durmiente
    de remate (la huella crece 0,60 m hacia -X en |y| <= 0,55).
    Origen: centro, al piso; L en X, W en Y. Cara superior a z = 0,108 m."""
    r = rng(seed)
    mb = MB()
    t, jh = PLY_T, JOIST_H
    zb = jh + 0.0002
    zt = zb + t
    g = 0.0032                                      # holgura de 1/8"
    tw = 0.038                                      # canto de un 2×4
    x0, x1 = -L / 2, L / 2
    y0, y1 = -W / 2, W / 2
    # ---- durmientes (2×4 de canto en Y, a 16" desde el canto -X) y cabezales en X
    jx = [x0 + tw / 2] + [x0 + k * 0.4064 for k in range(1, 40) if x0 + k * 0.4064 < x1 - tw / 2 - 0.06] + [x1 - tw / 2]
    for x in jx:
        _board(mb, x - tw / 2, x + tw / 2, y0 + tw + 0.0005, y1 - tw - 0.0005, 0.0, jh, "wood", r=0.003, step=1.0, ngon=(4,))
    for (ya, yb_) in ((y0, y0 + tw), (y1 - tw, y1)):
        _board(mb, x0, x1, ya, yb_, 0.0, jh, "wood", r=0.003, step=1.0, ngon=(4,))
    for x in jx:                                    # clavos de punta por el cabezal (dos por durmiente)
        for (yf, sy) in ((y0, -1), (y1, 1)):
            for z in (0.026, 0.063):
                _nail(mb, _T(x + _jit(r, 0.004), yf, z + _jit(r, 0.003)) @ _Rx(-90 * sy), r=0.0036)
    # ---- hojas de triplay en hiladas trabadas
    wear = _floor_wear(L, W)
    pw, pl = 1.2192, 2.4384
    yb = [y0]
    while yb[-1] + pw < y1 - 0.05:
        yb.append(yb[-1] + pw)
    yb.append(y1)
    n_scr = 0
    for j in range(len(yb) - 1):
        off = 6 if j % 2 == 0 else 3                # junta de extremo sobre el durmiente k (k = 6 o 3, luego cada 6)
        xb = [x0]
        k = off
        while x0 + k * 0.4064 < x1 - 0.3:
            xb.append(x0 + k * 0.4064)
            k += 6
        xb.append(x1)
        for i in range(len(xb) - 1):
            sa = xb[i] + (g / 2 if i > 0 else 0.0)
            sb = xb[i + 1] - (g / 2 if i < len(xb) - 2 else 0.0)
            ta = yb[j] + (g / 2 if j > 0 else 0.0)
            tb = yb[j + 1] - (g / 2 if j < len(yb) - 2 else 0.0)
            sd = int(r.integers(0, 1 << 30))
            rs = rng(sd)
            dz = -_f(rs.uniform(0.0, 0.0005))
            crown = _f(rs.uniform(-0.0004, 0.0008))
            ns = _f(rs.uniform(0, 100))

            def topfn(X, Y, sa=sa, sb=sb, ta=ta, tb=tb, dz=dz, crown=crown, ns=ns):
                u = np.clip((X - sa) / (sb - sa), 0, 1)
                v = np.clip((Y - ta) / (tb - ta), 0, 1)
                return (dz + crown * np.sin(PI * u) * np.sin(PI * v) + 0.00022 * _noise2(X, Y, 1.3, ns)
                        - wear(X, Y) * (0.75 + 0.25 * _noise2(X, Y, 4.0, ns + 7)))
            chips = []
            for _ in range(int(rs.integers(1, 4))):
                sd_ = int(rs.integers(0, 4))
                if sd_ < 2:
                    s = _f(rs.uniform(ta + 0.08, tb - 0.08))
                else:
                    s = _f(rs.uniform(sa + 0.08, sb - 0.08))
                chips.append((sd_, s, _f(rs.uniform(0.012, 0.035)), _f(rs.uniform(0.0007, 0.0013))))
            _ply_sheet(mb, sa, sb, ta, tb, zb, t, sd, topfn=topfn, chips=chips)
            # tornillos sobre los durmientes que caen en esta hoja
            for x in jx:
                if not (xb[i] - 0.03 < x < xb[i + 1] + 0.03):
                    continue
                at_end = abs(x - xb[i]) < 0.03 or abs(x - xb[i + 1]) < 0.03
                if at_end:
                    xx = x + (0.0095 if abs(x - xb[i]) < 0.03 else -0.0095)
                    if x in (jx[0], jx[-1]):
                        xx = x
                    pitch = 0.1524
                else:
                    xx = x
                    pitch = 0.3048
                yy = ta + 0.04
                while yy < tb - 0.0095:
                    px, py = xx + _jit(rs, 0.002), yy + _jit(rs, 0.004)
                    pz = zt + _f(topfn(np.array([px]), np.array([py]))[0])
                    _screw_cs(mb, _T(px, py, pz), seed=sd + n_scr)
                    n_scr += 1
                    yy += pitch
    if ramp:
        _floor_ramp(mb, x0, zt, r)
    return mb


def _floor_ramp(mb, xe, zt, r, wr=1.10, lr=0.60):
    """Rampa de entrada pegada al canto -X del piso (xe): cubierta de triplay de 23/32" inclinada de z = zt (a ras del piso,
    3 mm de holgura) a 18 mm del suelo, punta biselada, tres largueros cónicos de 2×4, listones antiderrapantes de 1×2" con
    tornillos, y dos escuadras de lámina atornilladas al durmiente de remate."""
    t = PLY_T
    xa = xe - 0.003                                 # canto alto de la rampa (holgura con el piso)
    xt = xa - lr                                    # punta
    z_hi, z_lo = zt, 0.0195
    ang = math.atan2(z_hi - z_lo, lr)
    Ld = lr / math.cos(ang)
    # cubierta: hoja en su marco inclinado (origen en la arista superior alta, X local hacia la punta)
    Md = _T(xa, 0.0, z_hi) @ _Ry(-math.degrees(ang)) @ _Rz(180)
    _ply_sheet(mb, 0.0, Ld, -wr / 2, wr / 2, -t, t, 7, M=Md,
               chips=[(2, Ld * 0.6, 0.02, 0.001)], step=0.1, extra_x=(Ld - 0.03, Ld - 0.018, Ld - 0.008),
               topfn=lambda X, Y: (-0.0004 * np.exp(-((Y) / 0.3) ** 2) * np.clip(X / Ld, 0, 1)
                                   - 0.009 * np.clip((X - (Ld - 0.03)) / 0.03, 0, 1) ** 1.3))
    # largueros cónicos (2×4 cortados en cuña) bajo la cubierta: caja de cantos matados aplastada hacia la punta
    xs_lo, xs_hi = xt + 0.035, xa - 0.002
    def under(x):
        return z_hi - t / math.cos(ang) - (xa - x) * math.tan(ang) - 0.0002
    h_hi = under(xs_hi)
    for yy in (-wr / 2 + 0.03, 0.0, wr / 2 - 0.03):
        def dsq(Q, N, P):
            D = np.zeros_like(Q)
            fac = np.array([under(x) for x in Q[:, 0]]) / h_hi
            D[:, 2] = Q[:, 2] * (fac - 1.0)
            return D
        _board(mb, xs_lo, xs_hi, yy - 0.019, yy + 0.019, 0.0, h_hi, "wood", r=0.003, step=0.2, disp=dsq, ngon=(4,))
    # listones antiderrapantes atornillados
    nl = 3
    for k in range(nl):
        s = Ld * (0.2 + 0.6 * k / (nl - 1))
        Ml = Md @ _T(s, 0.0, 0.0)
        _board(mb, -0.0125, 0.0125, -wr / 2 + 0.05, wr / 2 - 0.05, -0.0003, 0.0095, "wood", r=0.0025, M=Ml, step=0.3, ngon=(4,))
        for yy in (-wr / 2 + 0.12, 0.0, wr / 2 - 0.12):
            _screw_cs(mb, Ml @ _T(0.0, yy, 0.0095), d=0.007, seed=k * 7 + int(yy * 100))
    # escuadras de lámina (largueros extremos -> cara del durmiente de remate)
    for yy in (-wr / 2 + 0.03, wr / 2 - 0.03):
        sy = 1 if yy > 0 else -1
        yo = yy + sy * 0.0191
        ya_, yb_ = sorted((yo, yo + sy * 0.045))
        _board(mb, xe - 0.0016, xe, ya_, yb_, 0.014, 0.064, "galvanized", r=0.0006, step=1.0)
        ya_, yb_ = sorted((yo, yo + sy * 0.0016))
        _board(mb, xe - 0.055, xe, ya_, yb_, 0.014, 0.064, "galvanized", r=0.0006, step=1.0)
        for dz in (0.026, 0.052):
            _screw_cs(mb, _T(xe - 0.0016, yo + sy * 0.03, dz) @ _Ry(-90), d=0.006, seed=int(dz * 1000) + sy)
            _screw_cs(mb, _T(xe - 0.032, yo + sy * 0.0016, dz) @ _Rx(-90 * sy), d=0.006, seed=int(dz * 1000) + 3 * sy)

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
    mb._last_dbox = (keys, V, Q, N)
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
    fc = mb.bm.faces.new(list(reversed(A)))
    fc.material_index = mi
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
                caps=True)


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
                caps=True)


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


def _ply_zs(z0, t, r, n_ply=5):
    """Muestras de z de una hoja de triplay de 5 chapas: redondeos del canto y, en el canto, las chapas cruzadas (2ª y 4ª)
    hundidas."""
    pz = [z0 + t * k / n_ply for k in range(1, n_ply)]
    cz = [z0 + t * (k + 0.5) / n_ply for k in (1, 3)]
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
    ply = t / 5
    cross = [(z0 + ply * k, z0 + ply * (k + 1)) for k in (1, 3)]

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
    pw = 1.2192                                     # hoja de 4 ft (las juntas de extremo caen cada 8 ft sobre un durmiente)
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
        _board(mb, xe - 0.055, xe - 0.0004, ya_, yb_, 0.014, 0.064, "galvanized", r=0.0006, step=1.0)
        for dz in (0.026, 0.052):
            _screw_cs(mb, _T(xe - 0.0016, yo + sy * 0.03, dz) @ _Ry(-90), d=0.006, seed=int(dz * 1000) + sy)
            _screw_cs(mb, _T(xe - 0.032, yo + sy * 0.0016, dz) @ _Rx(-90 * sy), d=0.006, seed=int(dz * 1000) + 3 * sy)


# ======================================================================================================== mostrador de cajas
CR_H = 0.4255                  # alto de cada caja (2 hiladas + listones de 2×2 + triplay = cubierta a 0,909)
CR_BAT = 0.038                 # listones de tapa de 2×2" (38 mm) de las cajas de arriba
CR_LIFT = 0.0018               # las cajas de arriba descansan sobre las hojas de las bisagras de las de abajo
COUNTER_TOP = 2 * CR_H + CR_LIFT + CR_BAT + PLY_T      # 0,909


def _plank(mb, x0, x1, y0, y1, z0, z1, mat, rs, r=0.0028, M=None, bow=0.0004, step=0.15, ngon=(), flat=False):
    """Tabla de madera aserrada: cantos redondeados reales, combeo leve a lo largo (bow), alabeo en el ancho y espesor que
    varía medio milímetro (tablas distintas entre sí)."""
    dims = (x1 - x0, y1 - y0, z1 - z0)
    th = int(np.argmin(dims))
    lg = int(np.argmax(dims))
    wd = 3 - th - lg
    lo = (x0, y0, z0)
    b = bow * _f(rs.uniform(-1, 1))
    cup = 0.00025 * _f(rs.uniform(-1, 1))
    tw = 0.0003 * _f(rs.uniform(-1, 1))
    if flat:                                                             # tabla con esténcil: solo cantos, sin combeo
        b = cup = tw = 0.0

    def disp(Q, N, P):
        D = np.zeros_like(Q)
        u = np.clip((Q[:, lg] - lo[lg]) / dims[lg], 0, 1)
        v = np.clip((Q[:, wd] - lo[wd]) / dims[wd], 0, 1)
        D[:, th] = b * np.sin(PI * u) + cup * (2 * v - 1) ** 2 + tw * (2 * u - 1) * (2 * v - 1)
        return D
    return _board(mb, x0, x1, y0, y1, z0, z1, mat, r=r, M=M, step=step, disp=disp, ngon=ngon)


def _rope(mb, path, r=0.006, mat="fabric", lay=None, n_prof=18, step=0.004):
    """Cuerda de 3 torones: sección trilobulada cuyo patrón gira a lo largo (paso de cableado ~6 radios), marco por transporte
    paralelo (sin giros bruscos), remuestreada a `step`."""
    P = [Vector(p) for p in path]
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    tot = acc[-1]
    n = max(4, int(tot / step))
    pts, ss = [], []
    for k in range(n + 1):
        sv = tot * k / n
        i = next((j for j in range(1, len(acc)) if acc[j] >= sv - 1e-12), len(acc) - 1)
        t = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-12)
        pts.append(P[i - 1].lerp(P[i], t))
        ss.append(sv)
    lay = lay or 6 * r
    m = len(pts)
    T = [(pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(m)]
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    rings = []
    for i in range(m):
        if i:
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        ph = 2 * PI * ss[i] / lay
        ring = []
        for k in range(n_prof):
            a_ = 2 * PI * k / n_prof
            rad = r * (1 + 0.12 * math.cos(3 * (a_ - ph)))
            ring.append(pts[i] + (N * math.cos(a_) + B * math.sin(a_)) * rad)
        rings.append(ring)
    loft_rings(mb, rings, mat)


def _strap_hinge(mb, M, L=0.064, leaf_top=0.07, leaf_back=0.075, rk=0.0042, mat="steel"):
    """Bisagra de libro reforzada en la arista superior trasera de una tapa: M con origen en la arista (eje X a lo largo, -Y hacia
    el frente, +Z arriba). Hoja superior sobre la tapa, hoja trasera sobre el costado, 3 nudillos con perno de cabeza
    redonda y 3 tornillos por hoja."""
    t = 0.0016
    yk, zk = rk * 0.55, -rk * 0.25
    slab(mb, M @ _T(0, -leaf_top / 2 + 0.002, -0.0003), L, leaf_top, t, rc=0.008, re=0.0006, mat=mat, nc=4, ne=1)
    slab(mb, M @ _T(0, 0.0, -leaf_back / 2 + 0.001) @ _Rx(-90) @ _T(0, 0, -0.0002), L, leaf_back, t, rc=0.008, re=0.0006, mat=mat,
         nc=4, ne=1)
    gap = 0.0008
    for k in range(3):
        xa = -L / 2 + L * k / 3 + (gap if k else 0.0)
        xb = -L / 2 + L * (k + 1) / 3 - (gap if k < 2 else 0.0)
        _lathe(mb, [(rk * 0.45, 0.0), (rk * 0.96, 0.0), (rk, 0.0006), (rk, xb - xa - 0.0006), (rk * 0.96, xb - xa), (rk * 0.45, xb - xa)],
               M @ _T(xa, yk, zk) @ _Ry(90), mat, seg=SEG, closed=True)
    for sx in (-1, 1):                                                   # cabezas del perno
        _lathe(mb, [(rk * 0.5, 0.0), (rk * 0.62, 0.0003), (rk * 0.55, 0.0012), (0.0, 0.0018)],
               M @ _T(sx * L / 2, yk, zk) @ _Ry(90 * sx), mat, seg=16)
    for k, x in enumerate((-L * 0.32, 0.0, L * 0.32)):
        _screw_cs(mb, M @ _T(x, -leaf_top * (0.45 if k == 1 else 0.7), t), d=0.0065, seed=k + 11)
        _screw_cs(mb, M @ _T(x, 0.0, -leaf_back * (0.45 if k == 1 else 0.7)) @ _T(0, t, 0) @ _Rx(-90), d=0.0065, seed=k + 17)


def _draw_latch(mb, M, z_keep, mat="steel"):
    """Cierre de palanca (draw latch) cerrado sobre la cara frontal: M en la cara (z local = normal hacia afuera, y local arriba),
    origen en el eje del pivote de la palanca; cuerpo con orejas enrolladas, palanca de lámina embutida con canal, arco de
    alambre de 3 mm enganchado en la uña del contraplaco a z_keep (sobre la tapa)."""
    t = 0.0014
    slab(mb, M @ _T(0, -0.018, 0.0), 0.036, 0.05, t, rc=0.005, re=0.0005, mat=mat, nc=4, ne=1)            # base
    for sx in (-1, 1):                                                                                     # orejas
        x = sx * 0.0135
        _lathe(mb, [(0.0018, 0.0), (0.0038, 0.0), (0.0038, 0.006), (0.0018, 0.006)], M @ _T(x - 0.003, 0.0, 0.0055) @ _Ry(90),
               mat, seg=SEG, closed=True)
        _board(mb, x - 0.0026, x + 0.0026, -0.006, -0.0006, t - 0.0002, 0.0052, mat, r=0.0006, M=M, step=1.0)
    _cyl(mb, tuple(M @ Vector((-0.0185, 0.0, 0.0055))), tuple(M @ Vector((0.0185, 0.0, 0.0055))), 0.0016, mat, seg=16)
    for sx in (-1, 1):                                                                                     # remaches
        for y in (-0.034, -0.006):
            _rivet(mb, M @ _T(sx * 0.0148, y - 0.006, t), r=0.0021)
    # palanca: canal de lámina (alas dobladas hacia la cara) de 22 mm, del pivote hacia abajo, punta redondeada
    pts = [(0.0, 0.002, 0.0062), (0.0, -0.02, 0.0072), (0.0, -0.05, 0.0068), (0.0, -0.066, 0.006)]
    prof = [(-0.011, -0.003), (-0.0108, -0.0012), (-0.0098, 0.0), (0.0098, 0.0), (0.0108, -0.0012), (0.011, -0.003),
            (0.0095, -0.003), (0.0093, -0.0014), (-0.0093, -0.0014), (-0.0095, -0.003)]
    sweep_frame(mb, prof, [tuple(M @ Vector(p)) for p in fillet(pts, 0.02, 4)], mat, up=tuple(M.to_3x3() @ Vector((0, 0, 1))))
    _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0062, 0.0012), (0.0054, 0.0019), (0.0, 0.0019)],
           M @ _T(0, -0.063, 0.0071), mat, seg=SEG)
    # arco de alambre: colas metidas en las alas de la palanca, dos piernas y travesaño asentado en la cuna de la uña
    zk = z_keep + 0.0012
    bail = [(-0.0101, -0.008, 0.0066), (-0.0122, -0.008, 0.0066), (-0.0122, zk - 0.007, 0.0042), (-0.0122, zk, 0.0033),
            (0.0122, zk, 0.0033), (0.0122, zk - 0.007, 0.0042), (0.0122, -0.008, 0.0066), (0.0101, -0.008, 0.0066)]
    with mb.soft():
        _tube(mb, [tuple(M @ Vector(p)) for p in fillet(bail, 0.0026, 4)], 0.0015, seg=12, mat=mat)
    # contraplaco con uña en la tapa
    slab(mb, M @ _T(0, z_keep + 0.0075, 0.0), 0.03, 0.014, t, rc=0.004, re=0.0005, mat=mat, nc=4, ne=1)
    sweep_frame(mb, rr_profile(0.0014, 0.022, 0.0006, n=1),
                [tuple(M @ Vector(p)) for p in fillet([(0, z_keep + 0.004, t), (0, z_keep - 0.0008, 0.0026), (0, z_keep + 0.0022, 0.0056)],
                                                      0.0015, 2)],
                mat, up=tuple(M.to_3x3() @ Vector((1, 0, 0))))
    for sx in (-1, 1):
        _rivet(mb, M @ _T(sx * 0.0095, z_keep + 0.0095, t), r=0.0019)


def _od_crate(mb, M, w=0.8, d=0.55, h=CR_H, seed=0, ends=(True, True), lid_battens=False, stencil=None, bands=True,
              handles=(True, True), lot=None):
    """Caja de madera de munición pintada OD (origen: centro de la base, frente -Y): dos patines de 2×2 a lo largo, fondo de dos
    tablas, costados y testeros de dos tablas de 18 mm con holgura de 3 mm entre ellas y cantos redondeados, marco de
    travesaños de 19 × 70 mm en los testeros expuestos con asa de cuerda de 3 torones de 1/2" que sale por dos barrenos,
    tapa de dos tablas con bisagras reforzadas atrás y dos cierres de palanca al frente, listones de 2×2 sobre la tapa
    (lid_battens), flejes de acero de 5/8" con sello engargolado, clavos a la vista y esténcil (kit.fonts, stencil)."""
    r = rng(seed)
    hs = 0.025
    tb = 0.018
    tc = 0.019
    wb = w - 2 * tc
    xb = wb / 2
    g = 0.003
    T = lambda x0, x1, y0, y1, z0, z1, mat="wood_od", rr=0.0028, ngon=(), flat=False: _plank(  # noqa
        mb, x0, x1, y0, y1, z0, z1, mat, r, r=rr, M=M, ngon=ngon, flat=flat)
    for sy in (-1, 1):                                                   # patines
        yc = sy * (d / 2 - 0.065)
        T(-xb + 0.012, xb - 0.012, yc - 0.019, yc + 0.019, 0.0, hs, ngon=(4,))
    for k in range(2):                                                   # fondo
        ya = -d / 2 + tb + (d - 2 * tb) * k / 2 + (g / 2 if k else 0.0)
        yb_ = -d / 2 + tb + (d - 2 * tb) * (k + 1) / 2 - (0.0 if k else g / 2)
        T(-xb + tb, xb - tb, ya, yb_, hs, hs + tb)
    hb = (h - tb - hs - g) / 2
    zs_b = [(hs, hs + hb), (hs + hb + g, h - tb)]
    for sy in (-1, 1):                                                   # costados (los del frente llevan esténcil: planos)
        ya, yb_ = sorted((sy * d / 2, sy * (d / 2 - tb)))
        for (za, zb) in zs_b:
            T(-xb + 0.0002, xb - 0.0002, ya, yb_, za, zb, flat=(sy < 0 and stencil is not None))
    for sx in (-1, 1):                                                   # testeros (entre los costados)
        xa, xb_ = sorted((sx * xb, sx * (xb - tb)))
        for (za, zb) in zs_b:
            T(xa, xb_, -d / 2 + tb + 0.0004, d / 2 - tb - 0.0004, za, zb)
    for k in range(2):                                                   # tapa
        ya = -d / 2 + d * k / 2 + (g / 2 if k else 0.0)
        yb_ = -d / 2 + d * (k + 1) / 2 - (0.0 if k else g / 2)
        T(-xb, xb, ya, yb_, h - tb + 0.0002, h - 0.0003 * k)
    nails = []
    for sy in (-1, 1):                                                   # clavos de costados y tapa a los testeros
        for sx in (-1, 1):
            x = sx * (xb - tb / 2)
            for (za, zb) in zs_b:
                for zz in (za + 0.03, zb - 0.03):
                    nails.append((M @ _T(x + _jit(r, 0.002), sy * d / 2, zz + _jit(r, 0.004)) @ _Rx(-90 * sy)))
            for yy in (sy * 0.07, sy * 0.2):
                nails.append(M @ _T(x + _jit(r, 0.002), yy + _jit(r, 0.006), h))
    for sx in (-1, 1):
        i = 0 if sx < 0 else 1
        if not ends[i]:
            continue
        xa, xb_ = sorted((sx * xb, sx * (xb + tc)))
        T(xa, xb_, -d / 2, d / 2, 0.004, 0.074)
        T(xa, xb_, -d / 2, d / 2, h - 0.07, h)
        for sy in (-1, 1):
            ya, yb_ = sorted((sy * d / 2, sy * (d / 2 - 0.07)))
            T(xa, xb_, ya, yb_, 0.0745, h - 0.0705)
            for zz in (0.039, h - 0.035):
                for yy in (sy * (d / 2 - 0.035), sy * 0.12):
                    nails.append(M @ _T(sx * (xb + tc), yy + _jit(r, 0.004), zz + _jit(r, 0.004)) @ _Ry(90 * sx))
            for zz in (0.15, h - 0.15):
                nails.append(M @ _T(sx * (xb + tc), sy * (d / 2 - 0.035) + _jit(r, 0.004), zz) @ _Ry(90 * sx))
        if handles[i]:                                                   # asa de cuerda por dos barrenos del testero
            zc = h * 0.6
            pth = [(sx * (xb - 0.004), -0.07, zc), (sx * (xb + 0.0135), -0.07, zc), (sx * (xb + 0.0095), -0.074, zc - 0.035),
                   (sx * (xb + 0.0078), -0.045, zc - 0.076), (sx * (xb + 0.0078), 0.045, zc - 0.076), (sx * (xb + 0.0095), 0.074, zc - 0.035),
                   (sx * (xb + 0.0135), 0.07, zc), (sx * (xb - 0.004), 0.07, zc)]
            pth = fillet(pth, 0.03, 8)
            _rope(mb, [tuple(M @ Vector(p)) for p in pth], r=0.0063)
            for yy in (-0.07, 0.07):                                     # boca del barreno (sombra del hueco alrededor de la cuerda)
                with mb.soft():
                    _ring(mb, M @ _T(sx * (xb + 0.0001), yy, zc) @ _Ry(90), 0.0083, 0.001, seg=SEG, sseg=10, mat="cable")
    if lid_battens:
        for sx in (-1, 1):
            xc = sx * (xb - 0.085)
            T(xc - 0.019, xc + 0.019, -d / 2 + 0.006, d / 2 - 0.006, h - 0.0003, h + CR_BAT)
            for yy in (-0.2, 0.0, 0.2):
                nails.append(M @ _T(xc + _jit(r, 0.004), yy + _jit(r, 0.01), h + CR_BAT))
    for Mn in nails:
        _nail(mb, Mn, r=0.0032, seg=10)
    # bisagras atrás y cierres al frente
    xh = xb - 0.2
    for sx in (-1, 1):
        _strap_hinge(mb, M @ _T(sx * xh, d / 2, h), mat="steel")
        _draw_latch(mb, M @ _T(sx * xh, -d / 2, h - tb - 0.048) @ _Rx(90), 0.048 + 0.003)
    if bands:                                                            # flejes: suben por el frente, pasan sobre la tapa, bajan atrás
        for xbd in (-w * 0.31, w * 0.31):
            e = 0.0007
            zt = h + (CR_BAT if lid_battens and abs(abs(xbd) - (xb - 0.085)) < 0.04 else 0.0)
            pth = [(xbd, -d / 2 + 0.006, hs - 0.0005), (xbd, -d / 2 - e, hs + 0.004), (xbd, -d / 2 - e, zt - 0.004), (xbd, -d / 2 + 0.004, zt + e),
                   (xbd, d / 2 - 0.004, zt + e), (xbd, d / 2 + e, zt - 0.004), (xbd, d / 2 + e, hs + 0.004), (xbd, d / 2 - 0.006, hs - 0.0005)]
            sweep_frame(mb, rr_profile(0.0006, 0.0159, 0.00025, n=1), [tuple(M @ Vector(p)) for p in fillet(pth, 0.003, 3)], "steel",
                        up=tuple(M.to_3x3() @ Vector((1, 0, 0))))
            zs_ = hs + hb + g + 0.06
            Ms = M @ _T(xbd, -d / 2 - e - 0.0003, zs_) @ _Rx(90)
            slab(mb, Ms, 0.0205, 0.032, 0.0018, rc=0.0012, re=0.0006, mat="steel", nc=2, ne=1)
            for zz in (-0.008, 0.008):
                _board(mb, -0.0105, 0.0105, zz - 0.0012, zz + 0.0012, 0.0016, 0.0022, "steel", r=0.0005, M=Ms, step=1.0)
    if stencil:
        Ms = M @ _T(0.0, -d / 2, zs_b[1][0] + (zs_b[1][1] - zs_b[1][0]) * 0.32) @ _Rx(90)
        text_font(mb, stencil, 0.072, 0.0005, "paint_yellow" if stencil == "AMMO" else "sign_white", Ms, font="stencil", res=3)
        lot = lot or "LOT 7-%02d" % (seed % 90 + 10)
        Ml = M @ _T(-0.22, -d / 2, zs_b[0][0] + hb * 0.62) @ _Rx(90)
        text_font(mb, lot, 0.024, 0.0004, "sign_white", Ml, font="stencil2", res=2, align="LEFT")
        Ml = M @ _T(-0.22, -d / 2, zs_b[0][0] + hb * 0.3) @ _Rx(90)
        text_font(mb, "NET WT %d LB" % (40 + seed % 30), 0.02, 0.0004, "sign_white", Ml, font="stencil2", res=2, align="LEFT")


def _cash_box(mb, M, seed=0):
    """Caja de dinero de lámina de 0,8 mm (30 × 24 × 9 cm) cerrada: cuerpo embutido de esquinas redondeadas sobre 4 topes de
    hule, tapa con faldón que abraza el cuerpo (1,2 mm de holgura) y panel estampado en relieve, bisagra de piano atrás con
    nudillos alternados y perno, asa de alambre de 6 mm abatida sobre la tapa en dos orejas remachadas y chapa de llave al
    frente del faldón. Origen: centro de la base, frente -Y."""
    W, D, H = 0.300, 0.240, 0.090
    Hb = 0.066
    for sx in (-1, 1):                                                   # topes de hule
        for sy in (-1, 1):
            _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.007, 0.0012), (0.007, 0.0035), (0.0055, 0.0045), (0.0, 0.0045)],
                   M @ _T(sx * (W / 2 - 0.025), sy * (D / 2 - 0.025), 0.0), "rubber", seg=SEG)
    slab(mb, M @ _T(0, 0, 0.0042), W - 0.004, D - 0.004, Hb - 0.0042, rc=0.012, re=0.002, re0=0.003, mat="steel", nc=6, ne=2)
    # tapa: faldón exterior, canto superior de r 4 mm, panel estampado, faldón interior (lámina de 0,8 mm)
    t = 0.0008
    zs = Hb - 0.012
    rc = 0.0135

    def L(inset, z, rc_=rc):
        return [(x, y, z) for (x, y) in rr_pts(W - 2 * inset, D - 2 * inset, max(rc_ - inset, 0.002), 6)]
    loops = [L(t, H - 0.0045 - t), L(t, zs), L(0.0, zs), L(0.0, zs + 0.0006)]
    for j in range(5):
        a = PI / 2 * j / 4
        loops.append(L(0.004 * (1 - math.cos(a)), H - 0.004 * 1.0 - 0.0006 + 0.004 * math.sin(a) + 0.0006))
    for (ins, dz) in ((0.026, 0.0), (0.0275, 0.0009), (0.029, 0.0013), (0.031, 0.0014)):
        loops.append(L(ins, H + dz, rc_=0.03))
    skin(mb, loops, "steel", M)
    # bisagra de piano
    yk, zk, rk = D / 2 + 0.0016, zs + 0.0018, 0.0026
    slab(mb, M @ _T(0, D / 2 + 0.0004, zs + 0.004) @ _Rx(-90), W - 0.03, 0.008, 0.0008, rc=0.002, re=0.0003, mat="steel", nc=2, ne=1)
    slab(mb, M @ _T(0, D / 2 - 0.0016, zs - 0.009) @ _Rx(-90), W - 0.03, 0.016, 0.0008, rc=0.002, re=0.0003, mat="steel", nc=2, ne=1)
    nk = 9
    Lk = W - 0.03
    for k in range(nk):
        xa = -Lk / 2 + Lk * k / nk + 0.0003
        xb = -Lk / 2 + Lk * (k + 1) / nk - 0.0003
        _lathe(mb, [(0.0011, 0.0), (rk * 0.95, 0.0), (rk, 0.0004), (rk, xb - xa - 0.0004), (rk * 0.95, xb - xa), (0.0011, xb - xa)],
               M @ _T(xa, yk, zk) @ _Ry(90), "steel", seg=SEG, closed=True)
    _cyl(mb, tuple(M @ Vector((-Lk / 2 - 0.0015, yk, zk))), tuple(M @ Vector((Lk / 2 + 0.0015, yk, zk))), 0.0012, "steel", seg=12)
    # asa de alambre abatida hacia el frente, en dos orejas
    zt = H + 0.0014
    for sx in (-1, 1):
        x = sx * 0.058
        slab(mb, M @ _T(x, 0.0, zt - 0.0004), 0.012, 0.016, 0.0065, rc=0.004, re=0.0025, mat="steel", nc=4, ne=2)
        _rivet(mb, M @ _T(x, -0.0062, zt + 0.0002), r=0.0016)
    hp = [(-0.0645, 0.0, zt + 0.0042), (-0.05, 0.0, zt + 0.0042), (-0.05, -0.05, zt + 0.0037), (0.05, -0.05, zt + 0.0037),
          (0.05, 0.0, zt + 0.0042), (0.0645, 0.0, zt + 0.0042)]
    with mb.soft():
        _tube(mb, [tuple(M @ Vector(p)) for p in fillet(hp, 0.012, 6)], 0.003, seg=12, mat="steel")
    # chapa de llave en el faldón
    Mk = M @ _T(0, -D / 2, zs + 0.0068) @ _Rx(90)
    _lathe(mb, [(0.0, 0.0006), (0.0088, 0.0006), (0.0088, -0.0004), (0.0092, -0.0004), (0.0092, 0.0018), (0.0084, 0.0026),
                (0.0066, 0.0026), (0.0062, 0.0018), (0.0, 0.0018)], Mk, "aluminium", seg=SEG)
    _board(mb, -0.0007, 0.0007, -0.0035, 0.0035, 0.0015, 0.0023, "cable", r=0.0003, M=Mk, step=1.0)


def _clipboard(mb, M, seed=0):
    """Tabla con clip de 9 × 12-1/2" de hardboard de 1/8" con cantos redondeados, clip de perfil bajo (base remachada, palanca
    con orilla enrollada, resorte de torsión de alambre enrollado), tres hojas carta con la esquina levantada y pluma. Origen:
    centro de la base sobre la mesa; el clip hacia +Y."""
    r = rng(seed)
    Wb, Db = 0.2286, 0.3175
    slab(mb, M, Wb, Db, 0.0032, rc=0.009, re=0.0012, mat="wood_dark", nc=6, ne=2)
    z0 = 0.0032
    for k in range(3):                                                   # hojas carta (8,5 × 11")
        ang = _jit(r, 1.2)
        nu, nv = 12, 16
        Ws, Ds = 0.2159, 0.2794
        P = np.zeros((nu, nv, 3))
        for i in range(nu):
            for j in range(nv):
                u, v = i / (nu - 1), j / (nv - 1)
                x = -Ws / 2 + Ws * u
                y = Db / 2 - 0.026 - Ds * (1 - v)
                lift = 0.0
                if k == 2:
                    cu = max(0.0, (0.35 - math.hypot(1 - u, v * 0.8)) / 0.35)
                    lift = 0.011 * cu ** 2 + 0.0008 * math.sin(u * 5.0 + v * 3.0) * (1 - v)
                P[i, j] = (x, y, z0 + 0.00045 * k + 0.0002 + lift + 0.0004 * (1 - v) ** 2 * (k == 2))
        Mr = M @ _T(0, Db / 2 - 0.03, 0) @ _Rz(ang) @ _T(0, -(Db / 2 - 0.03), 0)
        PP = np.array([[tuple(Mr @ Vector(P[i, j])) for j in range(nv)] for i in range(nu)])
        N = np.zeros_like(PP)
        N[..., :] = tuple(M.to_3x3() @ Vector((0, 0, 1)))
        _slab_grid(mb, PP, N, 0.0, 0.00012, "paper")
    zc = z0 + 0.0012
    # clip: base remachada
    slab(mb, M @ _T(0, Db / 2 - 0.022, zc - 0.0004), 0.1, 0.03, 0.0009, rc=0.006, re=0.0004, mat="steel", nc=4, ne=1)
    for sx in (-1, 1):
        _rivet(mb, M @ _T(sx * 0.038, Db / 2 - 0.012, zc + 0.0005), r=0.0028)
        _board(mb, sx * 0.03 - 0.0045, sx * 0.03 + 0.0045, Db / 2 - 0.03, Db / 2 - 0.022, zc, zc + 0.0075, "steel", r=0.0004, M=M,
               step=1.0)
    # palanca: lámina curva con la orilla de mordida enrollada
    prof = [(0.0, Db / 2 - 0.008, zc + 0.012), (0.0, Db / 2 - 0.022, zc + 0.0095), (0.0, Db / 2 - 0.042, zc + 0.0035),
            (0.0, Db / 2 - 0.05, zc + 0.0012)]
    sweep_frame(mb, rr_profile(0.0009, 0.082, 0.0004, n=1), [tuple(M @ Vector(p)) for p in fillet(prof, 0.02, 6)], "steel",
                up=tuple(M.to_3x3() @ Vector((1, 0, 0))))
    _cyl(mb, tuple(M @ Vector((-0.041, Db / 2 - 0.0505, zc + 0.0021))), tuple(M @ Vector((0.041, Db / 2 - 0.0505, zc + 0.0021))),
         0.0016, "steel", seg=16)
    # resorte de torsión entre las orejas
    with mb.soft():
        hel = []
        for k in range(8 * 14 + 1):
            a = 2 * PI * k / 14
            x = -0.024 + 0.048 * k / (8 * 14)
            hel.append((x, Db / 2 - 0.026 + 0.0034 * math.cos(a), zc + 0.0042 + 0.0034 * math.sin(a)))
        _tube(mb, [tuple(M @ Vector(p)) for p in hel], 0.0006, seg=8, mat="steel")
        _cyl(mb, tuple(M @ Vector((-0.0345, Db / 2 - 0.026, zc + 0.0042))), tuple(M @ Vector((0.0345, Db / 2 - 0.026, zc + 0.0042))),
             0.0011, "steel", seg=12)
    # pluma
    pm = M @ _T(0.075, -0.03, z0 + 0.0013 + 0.0045) @ _Rz(66) @ _Ry(90)
    _lathe(mb, [(0.0, -0.072), (0.0004, -0.0718), (0.0012, -0.069), (0.0026, -0.064), (0.0042, -0.054), (0.0045, -0.05),
                (0.0045, 0.052), (0.0047, 0.053), (0.0047, 0.068), (0.0035, 0.071), (0.0, 0.072)], pm, "plastic", seg=SEG)
    _board(mb, -0.0012, 0.0012, 0.0045, 0.0062, 0.02, 0.066, "steel", r=0.0004, M=pm, step=1.0)


def _tape_roll(mb, M, seed=0):
    """Rollo de cinta de tela (48 mm) acostado: núcleo de cartón de 3" con su espesor, capas visibles en los costados (escalones
    de 0,15 mm), canto suave y la punta despegada levantándose del rollo. Origen: centro de la base."""
    R0, Rc, R1, Wt = 0.0381, 0.0420, 0.0565, 0.048
    prof = [(Rc + 0.0003, 0.0004)]
    nr = 10
    for k in range(nr + 1):
        rr_ = Rc + 0.0003 + (R1 - 0.0012 - Rc - 0.0003) * k / nr
        prof.append((rr_, 0.0004 + 0.00025 * (k % 2)))
    prof += [(R1 - 0.0004, 0.0008), (R1, 0.0016), (R1, Wt - 0.0016), (R1 - 0.0004, Wt - 0.0008)]
    for k in range(nr, -1, -1):
        rr_ = Rc + 0.0003 + (R1 - 0.0012 - Rc - 0.0003) * k / nr
        prof.append((rr_, Wt - 0.0004 - 0.00025 * (k % 2)))
    prof.append((Rc + 0.0003, Wt - 0.0004))
    _lathe(mb, prof, M, "plastic", seg=48, closed=True)
    _lathe(mb, [(R0, 0.0), (Rc + 0.0006, 0.0), (Rc + 0.0006, Wt), (R0, Wt)], M, "cardboard", seg=48, closed=True)
    a0 = 0.5
    pts = []
    for k in range(9):
        a = a0 + 0.07 * k
        rr_ = R1 + 0.00025 + 0.0045 * (k / 8) ** 2.2
        pts.append((rr_ * math.cos(a), rr_ * math.sin(a)))
    P = np.array([[(x, y, z) for z in np.linspace(0.0012, Wt - 0.0012, 5)] for (x, y) in pts])
    PP = np.array([[tuple(M @ Vector(p)) for p in row] for row in P])
    Nn = np.zeros_like(PP)
    for i in range(len(pts)):
        n = Vector((pts[i][0], pts[i][1], 0)).normalized()
        Nn[i, :] = tuple(M.to_3x3() @ n)
    _slab_grid(mb, PP, Nn, -0.00015, 0.00015, "plastic")


def crate_counter(L=2.4, seed=0):
    """Mostrador de venta armado con cajas de madera de munición pintadas OD (2 hiladas de 3 cajas de 0,79 × 0,55 × 0,43 m;
    ver _od_crate) con cubierta de una hoja de triplay de 8 ft × 23/32" (canto de chapas, despostilladuras, desgaste de manos
    al frente) que vuela 10 cm hacia el cliente, atornillada a los listones de 2×2 de las tapas de arriba. Encima: caja de
    dinero de lámina, tabla con clip con hojas y pluma, y rollo de cinta (a la derecha queda libre el lugar donde mil_builder
    pone la lata de munición abierta, x ≈ +0,8).
    Origen: piso al centro; L en X, cliente en -Y. Cubierta a z = 0,909 m (COUNTER_TOP)."""
    r = rng(seed)
    mb = MB()
    n = max(1, int(round(L / 0.8)))
    w = L / n
    d, h = 0.55, CR_H
    for lay in range(2):
        for i in range(n):
            x = -L / 2 + w * (i + 0.5) + _jit(r, 0.001)
            M = _T(x, _jit(r, 0.004), lay * (h + CR_LIFT)) @ _Rz(_jit(r, 0.25))
            ends = (i == 0, i == n - 1)
            _od_crate(mb, M, w - 0.006, d, h, seed=seed + 7 * lay + i, ends=ends, lid_battens=(lay == 1),
                      stencil=("AMMO" if (i + lay) % 2 == 0 else "SUPPLY"), handles=ends)
    zt = COUNTER_TOP
    zb = zt - PLY_T
    Lt = min(2.4384, L + 0.04)
    wear = lambda X, Y: -0.0004 * np.exp(-((Y + d / 2 + 0.1) / 0.06) ** 2) - 0.00025 * np.exp(-((X - 0.1) / 0.5) ** 2 - ((Y + 0.15) / 0.2) ** 2)  # noqa
    _ply_sheet(mb, -Lt / 2, Lt / 2, -d / 2 - 0.1, d / 2 + 0.03, zb, PLY_T, seed, topfn=wear, step=0.12,
               chips=[(2, -0.6, 0.025, 0.0011), (2, 0.9, 0.016, 0.0009), (0, 0.1, 0.02, 0.001)])
    for i in range(n):                                                   # tornillos a los listones de las cajas de arriba
        xc = -L / 2 + w * (i + 0.5)
        for sx in (-1, 1):
            xs_ = xc + sx * ((w - 0.006) / 2 - 0.019 - 0.085)
            for yy in (-0.2, 0.2):
                px, py = xs_ + _jit(r, 0.002), yy + _jit(r, 0.004)
                _screw_cs(mb, _T(px, py, zt + _f(wear(np.array([px]), np.array([py]))[0])), seed=i * 10 + int(yy * 10) + sx)
    _cash_box(mb, _T(0.3, 0.05, zt - 0.0002) @ _Rz(7 + _jit(r, 4)), seed=seed)
    _clipboard(mb, _T(-0.32, -0.13, zt - 0.0002) @ _Rz(186 + _jit(r, 4)), seed=seed)
    _tape_roll(mb, _T(-L / 2 + 0.27, 0.08, zt - 0.0002) @ _Rz(-140), seed=seed)
    return mb


# ======================================================================================================== anaquel
SH_D = 0.4572                  # 18"
SH_POST_A, SH_POST_T = 0.0381, 0.0019     # ángulo de 1-1/2" cal. 14
SH_PITCH = 0.0381              # perforaciones a cada 1-1/2"
SH_BACK = -0.007               # cara trasera de los postes (deja lugar a los contravientos y tuercas contra el muro)
SH_LEV = 0.016                 # alto del nivelador bajo la placa de pie
SH_HOLE0 = 0.045               # primera perforación sobre la base del poste


def _keyhole_sdf(u, z, uc, zc):
    """Perforación de gota (keyhole): cabeza redonda de Ø 9 mm arriba y ranura de 5 mm con fondo redondo abajo."""
    dh = math.hypot(u - uc, z - (zc + 0.0045)) - 0.0045
    qz = min(max(z, zc - 0.003), zc + 0.0045)
    ds = math.hypot(u - uc, z - qz) - 0.0025
    return min(dh, ds)


def _hole_pts(bpts, uc, zc):
    """Contorno de la perforación: un punto por punto del borde de la celda, por rayo desde el centro de la cabeza."""
    ox, oz = uc, zc + 0.0045
    out = []
    for (u, z) in bpts:
        dx, dz = u - ox, z - oz
        L = math.hypot(dx, dz)
        dx, dz = dx / L, dz / L
        lo, hi = 0.0, L
        for _ in range(30):
            mid = (lo + hi) / 2
            if _keyhole_sdf(ox + dx * mid, oz + dz * mid, uc, zc) < 0:
                lo = mid
            else:
                hi = mid
        out.append((ox + dx * lo, oz + dz * lo))
    return out


def _slotted_angle(mb, M, H, a=SH_POST_A, t=SH_POST_T, ri=0.0016, p=SH_PITCH, z0=0.0, holes=True, mat="steel", m=4, q=4):
    """Poste de ángulo ranurado de lámina rolada: talón con radio exterior (ri + t) y filete interior ri, puntas de ala
    redondas, y perforaciones de gota REALES (pasantes, con su pared) a paso p en el centro de ambas alas. M: talón en el
    origen, ala A a lo largo de +X local (espesor en +Y), ala B a lo largo de +Y (espesor en +X); de z0 a H.
    Devuelve las alturas de los centros de las cabezas de perforación (para pernos y niveles)."""
    Ro = ri + t
    uc = (a + t) / 2
    hw = 0.0078
    ua, ub = uc - hw, uc + hw
    zone = [ua + (ub - ua) * k / m for k in range(m + 1)]
    # perfil (u, v) cerrado y marcas de zona: (flange, face) -> índices consecutivos en el lazo
    loop, tags = [], []

    def add(pt, tag=None):
        loop.append(pt)
        tags.append(tag)
    # 1 cara exterior del ala A (v = 0) de la punta al talón
    add((a - t / 2, 0.0))
    for u in reversed(zone):
        add((u, 0.0), ("A", 0))
    for k in range(5):                                                   # talón exterior
        th = 1.5 * PI - (PI / 2) * k / 4
        add((Ro + Ro * math.cos(th), Ro + Ro * math.sin(th)))
    for v in zone:                                                       # 2 cara exterior del ala B (u = 0)
        add((0.0, v), ("B", 0))
    add((0.0, a - t / 2))
    for k in range(1, 4):                                                # punta del ala B
        th = PI - PI * k / 4
        add((t / 2 + t / 2 * math.cos(th), a - t / 2 + t / 2 * math.sin(th)))
    add((t, a - t / 2))
    for v in reversed(zone):                                             # 4 cara interior del ala B (u = t)
        add((t, v), ("B", 1))
    for k in range(4):                                                   # filete interior
        th = PI + (PI / 2) * k / 3
        add((t + ri + ri * math.cos(th), t + ri + ri * math.sin(th)))
    for u in zone:                                                       # 6 cara interior del ala A (v = t)
        add((u, t), ("A", 1))
    add((a - t / 2, t))
    for k in range(1, 4):                                                # punta del ala A
        th = PI / 2 - PI * k / 4
        add((a - t / 2 + t / 2 * math.cos(th), t / 2 + t / 2 * math.sin(th)))
    nL = len(loop)
    # filas de z: tramos lisos en los extremos, celdas de perforación con q filas internas
    cells = []
    if holes:
        zc = z0 + SH_HOLE0
        while zc + p / 2 < H - 0.02:
            cells.append(zc)
            zc += p
    rows = [z0]
    rowcell = []                                                         # índice de celda para el tramo entre fila i e i+1
    for ci, zc in enumerate(cells):
        zlo = zc - p / 2 + 0.0045
        if ci == 0:
            rows.append(zlo)
            rowcell.append(None)
        for k in range(1, q + 1):
            rows.append(zlo + p * k / q)
            rowcell.append(ci)
    rows.append(H)
    rowcell.append(None)
    Mx = M
    R = [[mb.bm.verts.new(Mx @ Vector((u_, v_, z))) for (u_, v_) in loop] for z in rows]
    mi = mb.mi(mat)

    def F(vs):
        f = mb.bm.faces.new(vs)
        f.material_index = mi
        f.smooth = True
    for i in range(len(rows) - 1):
        inc = rowcell[i] is not None
        for k in range(nL):
            kk = (k + 1) % nL
            if inc and tags[k] is not None and tags[kk] is not None and tags[k] == tags[kk]:
                continue
            F([R[i][k], R[i][kk], R[i + 1][kk], R[i + 1][k]])
    F(list(reversed(R[0])))
    F(R[-1])
    # paneles perforados de cada celda (exterior e interior) y pared del barreno
    idx = {}
    for k, tg in enumerate(tags):
        if tg is not None:
            idx.setdefault(tg, []).append(k)
    out_z = []
    for ci, zc in enumerate(cells):
        i0 = rows.index(next(r_ for r_ in rows if abs(r_ - (zc - p / 2 + 0.0045)) < 1e-9))
        rws = list(range(i0, i0 + q + 1))
        out_z.append(zc + 0.0045)
        for fl in ("A", "B"):
            hole_rings = []
            for face in (0, 1):
                ks = idx[(fl, face)]
                kk = sorted(ks, key=lambda k_: loop[k_][0] if fl == "A" else loop[k_][1])
                bnd = []                                                 # (vertex, (s, z))
                for k_ in kk:
                    bnd.append((R[rws[0]][k_], ((loop[k_][0] if fl == "A" else loop[k_][1]), rows[rws[0]])))
                for r_ in rws[1:]:
                    bnd.append((R[r_][kk[-1]], ((loop[kk[-1]][0] if fl == "A" else loop[kk[-1]][1]), rows[r_])))
                for k_ in reversed(kk[:-1]):
                    bnd.append((R[rws[-1]][k_], ((loop[k_][0] if fl == "A" else loop[k_][1]), rows[rws[-1]])))
                for r_ in reversed(rws[1:-1]):
                    bnd.append((R[r_][kk[0]], ((loop[kk[0]][0] if fl == "A" else loop[kk[0]][1]), rows[r_])))
                hp = _hole_pts([b[1] for b in bnd], uc, zc)
                vv = face * t
                HV = [mb.bm.verts.new(Mx @ (Vector((s_, vv, z_)) if fl == "A" else Vector((vv, s_, z_)))) for (s_, z_) in hp]
                nb = len(bnd)
                for j in range(nb):
                    jj = (j + 1) % nb
                    F([bnd[j][0], bnd[jj][0], HV[jj], HV[j]])
                hole_rings.append(HV)
            nb = len(hole_rings[0])
            for j in range(nb):
                jj = (j + 1) % nb
                F([hole_rings[0][j], hole_rings[0][jj], hole_rings[1][jj], hole_rings[1][j]])
    return out_z


def _shelf_pan(mb, M, w, d, t=0.00076, fl=0.038, hem=0.007, mat="steel"):
    """Entrepaño de lámina cal. 22 formado: cubierta w × d (cara superior en z = 0 local), cuatro pestañas de 1-1/2" dobladas
    hacia abajo con radio interior de 1,6 mm y dobladillo de 7 mm hacia adentro en la orilla (sin filo), esquinas con radio
    de 2 mm en planta; refuerzo de canal sombrero soldado por debajo a lo largo. Origen: centro de la cara superior."""
    rb = 0.0016 + t

    def L(inset, z):
        return [(x, y, z) for (x, y) in rr_pts(w - 2 * inset, d - 2 * inset, max(0.002 - inset, 0.0004), 2)]
    prof = [(rb, 0.0)]
    for k in range(1, 4):                                                # doblez exterior
        a = PI / 2 * k / 3
        prof.append((rb - rb * math.sin(a), -rb + rb * math.cos(a)))
    prof.append((0.0, -fl + 0.0012))
    for k in range(1, 5):                                                # dobladillo (180°)
        a = PI * k / 4
        prof.append((t - t * math.cos(a), -fl + t - t * math.sin(a)))
    prof += [(2 * t, -fl + hem), (t, -fl + hem), (t, -rb), (t + 0.0016 * (1 - math.cos(PI / 4)), -t - 0.0016 * (1 - math.sin(PI / 4)) - 0.0003),
             (rb, -t)]
    loops = [L(i, z) for (i, z) in prof]
    skin(mb, loops, mat, M)
    hat = [(-0.024, 0.0), (-0.013, 0.0), (-0.0105, -0.016), (0.0105, -0.016), (0.013, 0.0), (0.024, 0.0), (0.024, -0.0012),
           (0.0141, -0.0012), (0.0115, -0.0172), (-0.0115, -0.0172), (-0.0141, -0.0012), (-0.024, -0.0012)]
    sweep_frame(mb, [(x, z) for (x, z) in hat], [tuple(M @ Vector((-w / 2 + 0.012, 0.0, -t))), tuple(M @ Vector((w / 2 - 0.012, 0.0, -t)))],
                mat, up=tuple(M.to_3x3() @ Vector((0, 0, 1))))


def _brace(mb, p0, p1, nrm, w=0.019, t=0.0015, mat="steel"):
    """Contraviento de solera de 3/4" × cal. 16 entre dos pernos (extremos redondeados), plano sobre la cara de normal nrm."""
    p0, p1 = Vector(p0), Vector(p1)
    X = (p1 - p0).normalized()
    Z = Vector(nrm).normalized()
    Y = Z.cross(X)
    L = (p1 - p0).length
    Mb = Matrix(((X.x, Y.x, Z.x, p0.x), (X.y, Y.y, Z.y, p0.y), (X.z, Y.z, Z.z, p0.z), (0, 0, 0, 1)))
    slab(mb, Mb @ _T(L / 2, 0, 0), L + w, w, t, rc=w / 2 - 0.0005, re=0.0005, mat=mat, nc=6, ne=1)
    return Mb


def _leveler(mb, M, mat="steel"):
    """Nivelador: tuerca hexagonal soldada bajo la placa de pie, espárrago roscado de 3/8" con sus hilos y base de acero con
    pata de hule. M: origen en el piso, la placa de pie arriba en z = SH_LEV."""
    _lathe(mb, [(0.0, 0.0), (0.0158, 0.0), (0.0162, 0.0008), (0.0162, 0.0035), (0.0145, 0.004), (0.0, 0.004)], M, "rubber", seg=SEG)
    _lathe(mb, [(0.0, 0.0038), (0.0148, 0.0038), (0.0152, 0.0048), (0.013, 0.0062), (0.006, 0.0068), (0.0, 0.0068)], M, mat, seg=SEG)
    prof = [(0.0043, 0.0066)]
    z = 0.0068
    while z < SH_LEV - 0.0085:
        prof += [(0.0048, z + 0.0004), (0.0043, z + 0.0008)]
        z += 0.0008
    prof += [(0.0043, SH_LEV - 0.007)]
    _lathe(mb, prof, M, mat, seg=16)
    _hexbolt(mb, M @ _T(0, 0, SH_LEV - 0.0075), d=0.0095, h=0.0075, washer=False, mat=mat)


def _ammo_can(mb, M, seed=0):
    """Compatibilidad con kit.campaign._ammo_can: une la lata M2A1 en M (origen: centro de la base, largo en X)."""
    mb.join(_ammo_can_mb(seed=seed), M)


def _ammo_can_mb(seed=0, stencil=True):
    """Lata de munición de acero tipo M2A1 (11-3/4 × 6 × 7-1/2"; 298 × 152 × 191 mm) cerrada: cuerpo de lámina de esquinas
    redondeadas con costura rolada abajo, tapa con faldón, panel estampado y canto redondeado, bisagra de nudillos con perno
    en el extremo -X, palanca de cierre con su gancho en +X, asa de solera abatible remachada y esténcil. Origen: centro de
    la base; largo en X."""
    mb = MB()
    L, W, H = 0.298, 0.152, 0.191
    lid_h = 0.042
    zl = H - lid_h
    Lb, Wb = L - 0.008, W - 0.006
    slab(mb, _T(0, 0, 0.0055), Lb, Wb, zl + 0.022 - 0.0055, rc=0.009, re=0.002, re0=0.0, mat="paint_od", nc=4, ne=1)
    slab(mb, Matrix(), Lb + 0.0035, Wb + 0.0035, 0.0062, rc=0.0105, re=0.0022, re0=0.0016, mat="paint_od", nc=4, ne=2)
    # tapa: faldón y panel estampado
    rc = 0.011

    def Lp(ins, z, r_=rc):
        return [(x, y, z) for (x, y) in rr_pts(L - 2 * ins, W - 2 * ins, max(r_ - ins, 0.002), 4)]
    loops = [Lp(0.0012, H - 0.006), Lp(0.0012, zl), Lp(0.0, zl), Lp(0.0, zl + 0.0008)]
    for j in range(4):
        a = PI / 2 * (j + 1) / 4
        loops.append(Lp(0.006 * (1 - math.cos(a)), H - 0.006 + 0.006 * math.sin(a)))
    for (ins, dz) in ((0.016, 0.0), (0.018, 0.0012), (0.0205, 0.0017), (0.023, 0.0018)):
        loops.append(Lp(ins, H + dz, r_=0.02))
    skin(mb, loops, "paint_od")
    # bisagra en -X: nudillos (lámina enrollada) alternados tapa / cuerpo y perno
    hx, hz, rk = -L / 2 - 0.0035, zl + 0.004, 0.0042
    for k in range(5):
        ya = -0.05 + 0.1 * k / 5 + 0.0004
        yb_ = -0.05 + 0.1 * (k + 1) / 5 - 0.0004
        _lathe(mb, [(0.0018, 0.0), (rk * 0.95, 0.0), (rk, 0.0004), (rk, yb_ - ya - 0.0004), (rk * 0.95, yb_ - ya), (0.0018, yb_ - ya)],
               _T(hx, ya, hz) @ _Rx(-90), "paint_od", seg=SEG, closed=True)
        if k % 2 == 0:
            _board(mb, hx - 0.0008, -Lb / 2 + 0.0005, ya + 0.001, yb_ - 0.001, hz - 0.016, hz - 0.002, "paint_od", r=0.0006, step=1.0)
    _cyl(mb, (hx, -0.0515, hz), (hx, 0.0515, hz), 0.0018, "steel", seg=16)
    # palanca de cierre en +X: palanca de lámina con canal sobre el extremo, gancho al cuerpo
    xe = L / 2 + 0.0008
    lev = [(xe + 0.003, 0.0, H - 0.008), (xe + 0.0055, 0.0, H - 0.04), (xe + 0.0052, 0.0, zl - 0.055), (xe + 0.0085, 0.0, zl - 0.07)]
    prof = [(-0.0016, -0.013), (0.0, -0.0135), (0.0016, -0.013), (0.0016, 0.013), (0.0, 0.0135), (-0.0016, 0.013)]
    sweep_frame(mb, prof, fillet(lev, 0.012, 4), "paint_od", up=(0, 1, 0))
    _lathe(mb, [(0.0028, 0.0), (0.0042, 0.0), (0.0042, 0.03), (0.0028, 0.03)], _T(xe + 0.002, -0.015, H - 0.007) @ _Rx(-90),
           "paint_od", seg=SEG, closed=True)
    _board(mb, Lb / 2 - 0.0005, xe + 0.0015, -0.02, 0.02, zl - 0.085, zl - 0.06, "paint_od", r=0.0007, step=1.0)
    with mb.soft():
        _tube(mb, fillet([(xe + 0.0015, -0.011, zl - 0.07), (xe + 0.009, -0.011, zl - 0.07), (xe + 0.009, 0.011, zl - 0.07),
                          (xe + 0.0015, 0.011, zl - 0.07)], 0.003, 3), 0.0016, seg=12, mat="steel")
    # asa abatible acostada sobre la tapa: solera de 18 × 3 con dobleces y orejas remachadas
    zt = H + 0.0018
    hp = [(-0.062, 0.022, zt + 0.0035), (-0.062, -0.034, zt + 0.004), (0.062, -0.034, zt + 0.004), (0.062, 0.022, zt + 0.0035)]
    sweep_frame(mb, rr_profile(0.018, 0.003, 0.0012, n=2), fillet(hp, 0.014, 5), "paint_od", up=(0, 0, 1))
    for sx in (-1, 1):
        slab(mb, _T(sx * 0.062, 0.03, zt - 0.0005), 0.024, 0.02, 0.0075, rc=0.005, re=0.002, mat="paint_od", nc=3, ne=1)
        _rivet(mb, _T(sx * 0.0745, 0.03, zt + 0.0045) @ _Ry(90 * sx), r=0.003)
    if stencil:
        Ms = _T(0.0, -Wb / 2 - 0.0002, zl * 0.52) @ _Rx(90)
        text_font(mb, "AMMO", 0.032, 0.0004, "paint_yellow", Ms, font="stencil", res=2)
        Ms = _T(0.0, -Wb / 2 - 0.0002, zl * 0.3) @ _Rx(90)
        text_font(mb, "LOT 4-%02d" % (10 + seed % 80), 0.014, 0.0004, "paint_yellow", Ms, font="stencil2", res=2)
    return mb


def _carton_map(xs, ys, zs, rr):
    lo = np.array([xs[0], ys[0], zs[0]]) + rr
    hi = np.array([xs[-1], ys[-1], zs[-1]]) - rr

    def f(P):
        C = np.clip(P, lo, hi)
        D = (P - C) / rr
        Nn = D / np.maximum(np.linalg.norm(D, axis=1, keepdims=True), 1e-12)
        Q = C + Nn * rr
        N = Nn / rr
        return Q, N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return f


def _carton(mb, M, w, d, h, seed=0, opened=False, stamp=None, tape=True, contents=True, tilts=None):
    """Caja RSC de cartón corrugado de una pared (4 mm): costados abombados unos milímetros, dobleces redondeados (r 3 mm) en
    aristas y esquinas, ranuras de las solapas en las esquinas de arriba, solapas mayores que cierran al centro con su junta
    y cinta canela de 48 mm con espesor que baja 6 cm por los testeros. opened=True: abierta, con el espesor del cartón a la
    vista en la orilla, cuatro solapas abiertas (tilts = inclinación hacia afuera desde la vertical, grados, para frente,
    fondo, -X y +X) y cajitas de cartuchos adentro. stamp=(texto,
    tamaño) impreso en el frente. Origen: centro de la base; w en X, frente -Y."""
    r = rng(seed)
    rc = 0.003
    tw = 0.004
    xs = _axis_samples(-w / 2, w / 2, rc, 2, 0.05)
    ys = _axis_samples(-d / 2, d / 2, rc, 2, 0.05, forced=[-0.0018, 0.0, 0.0018])
    zs = _axis_samples(0.0, h, rc, 2, 0.05, forced=[h - 0.008, h - 0.004])
    bul = min(0.0035, 0.012 * min(w, d, h)) * _f(r.uniform(0.6, 1.0))
    sag = _f(r.uniform(-0.0012, 0.0006))

    def disp_fn(seam=True):
        def disp(Q, N, P):
            u = np.clip((Q[:, 0] + w / 2) / w, 0, 1)
            v = np.clip((Q[:, 1] + d / 2) / d, 0, 1)
            z = np.clip(Q[:, 2] / h, 0, 1)
            side_x = np.abs(N[:, 0]) > 0.7
            side_y = np.abs(N[:, 1]) > 0.7
            top = N[:, 2] > 0.7
            D = np.zeros_like(Q)
            b_y = bul * np.sin(PI * u) * np.sin(PI * z) ** 0.8
            b_x = bul * 0.8 * np.sin(PI * v) * np.sin(PI * z) ** 0.8
            D += N * (np.where(side_y, b_y, 0.0) + np.where(side_x, b_x, 0.0))[:, None]
            D[:, 2] += np.where(top, sag * np.sin(PI * u) * np.sin(PI * v), 0.0)
            if seam:
                D[:, 2] -= np.where(top, 0.0014 * np.exp(-(Q[:, 1] / 0.0016) ** 2), 0.0)
            # ranuras de las solapas en las 4 esquinas de arriba (la solapa menor queda 2 mm adentro de la mayor)
            for (sx, sy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                dc = np.hypot(Q[:, 0] - sx * w / 2, Q[:, 1] - sy * d / 2)
                k = np.exp(-(dc / 0.004) ** 2) * np.clip((Q[:, 2] - (h - 0.009)) / 0.004, 0, 1)
                D[:, 0] -= sx * 0.0014 * k
                D[:, 1] -= sy * 0.0014 * k
            return D
        return disp
    if not opened:
        _dbox(mb, M, xs, ys, zs, rc, "cardboard", disp=disp_fn(True), ngon=(4,))
        if tape:
            fmap = _carton_map(xs, ys, zs, np.array([rc, rc, rc]))
            a_ = w / 2
            path = [(-a_, z) for z in np.linspace(h - 0.06, h - rc, 5)] + \
                   [(-a_ + rc * (1 - math.cos(PI / 4 * k / 3)), h - rc + rc * math.sin(PI / 4 * k / 3)) for k in range(1, 4)]
            path += [(x, h) for x in np.linspace(-a_ + rc, a_ - rc, 16)]
            path += [(a_ - rc * (1 - math.cos(PI / 4 * k / 3)), h - rc + rc * math.sin(PI / 4 * k / 3)) for k in range(3, 0, -1)]
            path += [(a_, z) for z in np.linspace(h - rc, h - 0.06, 5)]
            yv = np.linspace(-0.024, 0.024, 5)
            P = np.array([[(x, y, z) for y in yv] for (x, z) in path])
            sh = P.shape
            Qs, Ns = fmap(P.reshape(-1, 3))
            Qs = Qs + disp_fn(False)(Qs, Ns, P.reshape(-1, 3))
            Mx = np.array(M)
            Qw = (Qs @ Mx[:3, :3].T + Mx[:3, 3]).reshape(sh)
            Nw = (Ns @ Mx[:3, :3].T).reshape(sh)
            _slab_grid(mb, Qw, Nw, 0.0003, 0.00045, "paper")
        if stamp:
            txt, size = stamp
            zc = h * 0.55
            off = bul * math.sin(PI * 0.5) * math.sin(PI * 0.55) ** 0.8
            text_font(mb, txt, size, 0.0004, "cable", M @ _T(0.0, -d / 2 - off - 0.0001, zc) @ _Rx(90), font="stencil2", res=2)
        return
    # ---- abierta: cáscara exterior sin tapa + interior (4 mm adentro) + orilla con el espesor del corrugado
    zs_o = _axis_samples(0.0, h, rc, 2, 0.05)
    _dbox(mb, M, xs, ys, zs_o, rc, "cardboard", disp=disp_fn(False), skip=(5,), ngon=(4,))
    ko, Vo = mb._last_dbox[0], mb._last_dbox[1]
    xi = xs * (w / 2 - tw) / (w / 2)
    yi = ys * (d / 2 - tw) / (d / 2)
    zi = tw + zs_o * (h - tw) / h
    _dbox(mb, M, xi, yi, zi, rc, "cardboard", disp=disp_fn(False), skip=(5,), ngon=(4,))
    ki, Vi = mb._last_dbox[0], mb._last_dbox[1]
    nx, ny, nz = len(xs), len(ys), len(zs_o)
    rim = [(i, 0) for i in range(nx - 1)] + [(nx - 1, j) for j in range(ny - 1)] + [(i, ny - 1) for i in range(nx - 1, 0, -1)] + \
          [(0, j) for j in range(ny - 1, 0, -1)]
    mi = mb.mi("cardboard")
    for a in range(len(rim)):
        b = (a + 1) % len(rim)
        ia, ib = rim[a] + (nz - 1,), rim[b] + (nz - 1,)
        f = mb.bm.faces.new([Vo[ko[ia]], Vo[ko[ib]], Vi[ki[ib]], Vi[ki[ia]]])
        f.material_index = mi
        f.smooth = True
    # solapas abatidas hacia afuera (mayores en ±Y, menores en ±X), con caída por su peso
    tl = tilts or [_f(r.uniform(35, 75)) for _ in range(4)]
    for fi, (ax, sgn, span, ln) in enumerate((("y", -1, w, d / 2), ("y", 1, w, d / 2), ("x", -1, d, d / 2 - 0.004),
                                              ("x", 1, d, d / 2 - 0.004))):
        tilt = tl[fi]
        cu = _f(r.uniform(0.004, 0.012))
        if ax == "y":
            Mf = M @ _T(0, sgn * (d / 2 - tw / 2), h - 0.0005) @ _Rx(-sgn * tilt)
            _board(mb, -span / 2 + 0.003, span / 2 - 0.003, -tw / 2, tw / 2, 0.0, ln, "cardboard", r=0.0016, M=Mf, step=0.06,
                   disp=lambda Q, N, P, sgn=sgn, cu=cu, ln=ln: np.stack([np.zeros(len(Q)), sgn * cu * (Q[:, 2] / ln) ** 2,
                                                                        np.zeros(len(Q))], -1))
        else:
            Mf = M @ _T(sgn * (w / 2 - tw / 2), 0, h - 0.0005) @ _Ry(sgn * tilt)
            _board(mb, -tw / 2, tw / 2, -span / 2 + 0.006, span / 2 - 0.006, 0.0, ln, "cardboard", r=0.0016, M=Mf, step=0.06,
                   disp=lambda Q, N, P, sgn=sgn, cu=cu, ln=ln: np.stack([sgn * cu * (Q[:, 2] / ln) ** 2, np.zeros(len(Q)),
                                                                        np.zeros(len(Q))], -1))
    if contents:                                                         # cajitas de cartuchos (cartón impreso) adentro
        cw, cd_, ch = 0.105, 0.065, 0.04
        nxc = max(1, int((w - 2 * tw - 0.01) / (cw + 0.004)))
        nyc = max(1, int((d - 2 * tw - 0.01) / (cd_ + 0.004)))
        nzc = max(1, int((h - tw - 0.03) / (ch + 0.001)))
        for kz in range(nzc):
            for ix in range(nxc):
                for iy in range(nyc):
                    if kz == nzc - 1 and r.uniform() < 0.35:
                        continue
                    x = (ix - (nxc - 1) / 2) * (cw + 0.004) + _jit(r, 0.002)
                    y = (iy - (nyc - 1) / 2) * (cd_ + 0.004) + _jit(r, 0.002)
                    slab(mb, M @ _T(x, y, tw + kz * (ch + 0.0008)) @ _Rz(_jit(r, 2)), cw, cd_, ch, rc=0.0015, re=0.0012, mat="cardboard",
                         nc=2, ne=1)


def _post_bolt(mb, Mh, Mn):
    """Perno de cabeza de gota de 5/16" por una perforación del poste (Mh: cara exterior del poste, z hacia afuera) con tuerca
    hexagonal y rondana del lado del entrepaño (Mn: cara interior de la pestaña, z hacia adentro)."""
    _lathe(mb, [(0.0, -0.0002), (0.0068, -0.0002), (0.0068, 0.0006), (0.0058, 0.0024), (0.0035, 0.0035), (0.0, 0.0038)], Mh, "steel",
           seg=SEG)
    _hexbolt(mb, Mn, d=0.0079, h=0.0068, washer=True, mat="steel", stub=0.0)
    _lathe(mb, [(0.0034, 0.0), (0.0036, 0.009), (0.0028, 0.0105), (0.0, 0.0108)], Mn, "steel", seg=16)


def shelving(w=1.2, seed=0, stock="mixed"):
    """Anaquel de acero de 48 × 18 × 72" de 5 entrepaños (1,22 × 0,46 × 1,83 m) cargado. Postes de ángulo ranurado de 1-1/2"
    cal. 14 con perforaciones de gota pasantes a cada 1-1/2" en ambas alas, sobre placa de pie y nivelador roscado con pata
    de hule; entrepaños de lámina cal. 22 con pestañas dobladas, dobladillo y canal de refuerzo, sujetos con pernos de 5/16"
    y tuerca en las perforaciones; contravientos en X de solera (atrás y a los costados). stock = "cans" (latas M2A1), "boxes"
    (cajas RSC cerradas con cinta, alguna abierta con cajitas adentro) o "mixed". Uso ligero: huecos donde ya se vendió.
    Origen: piso, centrado en X; espalda contra el muro (cara trasera de los postes a y = -0,007, frente a y = -0,464)."""
    r = rng(seed)
    mb = MB()
    t = SH_POST_T
    a = SH_POST_A
    uc = (a + t) / 2
    H = 1.83
    zf = SH_LEV + 0.003
    yF, yB = SH_BACK - SH_D, SH_BACK
    posts = ((-w / 2, yF, 1, 1), (w / 2, yF, -1, 1), (-w / 2, yB, 1, -1), (w / 2, yB, -1, -1))
    hz = None
    for (x, y, sx, sy) in posts:
        Mp = _T(x, y, zf) @ Matrix.Diagonal((sx, sy, 1.0, 1.0))
        hz = _slotted_angle(mb, Mp, H - zf)
        slab(mb, _T(x + sx * 0.024, y + sy * 0.024, SH_LEV), 0.05, 0.05, 0.003, rc=0.004, re=0.0008, mat="steel", nc=3, ne=1)
        _leveler(mb, _T(x + sx * 0.022, y + sy * 0.022, 0.0))
    holes = [zf + z for z in hz]
    targets = [0.15 + (H - 0.035 - 0.15) * i / 4 for i in range(5)]
    lvi = []
    for tz in targets:
        lvi.append(min(range(len(holes)), key=lambda i: abs(holes[i] + 0.019 - tz)))
    lv = [holes[k] + 0.019 for k in lvi]
    lv[-1] = min(lv[-1], H - 0.001)
    ws, ds = w - 2 * t - 0.0006, SH_D - 2 * t - 0.0006
    yc = (yF + yB) / 2
    for z in lv:
        _shelf_pan(mb, _T(0, yc, z), ws, ds)
        zb = z - 0.019
        for (x, y, sx, sy) in posts:
            yy = y + sy * uc
            xo = x
            xi_ = x + sx * (t + 0.0003 + 0.00076)
            _post_bolt(mb, _T(xo, yy, zb) @ _Ry(-90 * sx), _T(xi_, yy, zb) @ _Ry(90 * sx))
    # contravientos en X (atrás y costados), pernos en las perforaciones
    tb_ = 0.0015
    for (ka, kb) in ((lvi[0] + 2, lvi[2] - 2), (lvi[2] + 2, lvi[4] - 2)):   # perforaciones libres (no las de los entrepaños)
        za, zb_ = holes[ka], holes[kb]
        # atrás: por fuera de las alas traseras (entre el anaquel y el muro)
        pA, pB = Vector((-w / 2 + uc, yB, za)), Vector((w / 2 - uc, yB, zb_))
        pC, pD = Vector((w / 2 - uc, yB + tb_, za)), Vector((-w / 2 + uc, yB + tb_, zb_))
        _brace(mb, pA, pB, (0, 1, 0))
        _brace(mb, pC, pD, (0, 1, 0))
        for pp in (pA, pB):
            _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0055, 0.0018), (0.003, 0.0028), (0.0, 0.003)], _T(pp.x, yB + 2 * tb_, pp.z) @ _Rx(-90),
                   "steel", seg=SEG)
        for sx in (-1, 1):                                               # costados
            xs_ = sx * w / 2
            p0, p1 = Vector((xs_, yF + uc, za)), Vector((xs_, yB - uc, zb_))
            p2, p3 = Vector((xs_ + sx * tb_, yB - uc, za)), Vector((xs_ + sx * tb_, yF + uc, zb_))
            _brace(mb, p0, p1, (sx, 0, 0))
            _brace(mb, p2, p3, (sx, 0, 0))
            for pp in (p0, p1, p2, p3):
                if abs(pp.z - (za + zb_) / 2) < 0.01:
                    continue
                _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0055, 0.0018), (0.003, 0.0028), (0.0, 0.003)],
                       _T(xs_ + sx * 2 * tb_, pp.y, pp.z) @ _Ry(90 * sx), "steel", seg=SEG)
            cm = (p0 + p1) / 2
            _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0055, 0.0018), (0.003, 0.0028), (0.0, 0.003)],
                   _T(xs_ + sx * 2 * tb_, cm.y, cm.z) @ _Ry(90 * sx), "steel", seg=SEG)
    # mercancía
    kinds = {"cans": ["cans"] * 5, "boxes": ["boxes"] * 5, "mixed": ["boxes", "cans", "cans", "boxes", "boxes"]}[stock]
    words = ("KEEP DRY", "THIS SIDE UP", "FRAGILE", "HANDLE WITH CARE")
    can = None
    yfront = yF + t + 0.004
    for li, z in enumerate(lv):
        gapz = (lv[li + 1] - z - 0.045) if li + 1 < len(lv) else 0.3
        kind = kinds[li]
        xl, xr = -w / 2 + t + 0.012, w / 2 - t - 0.012
        if kind == "cans":
            if can is None:
                can = _ammo_can_mb(seed=seed)
            x = xl + 0.003
            while x + 0.152 <= xr:
                if r.uniform() < 0.86:
                    Mc = _T(x + 0.076 + _jit(r, 0.0015), yfront + 0.03 + 0.149 + _jit(r, 0.01), z) @ _Rz(90 + _jit(r, 0.8))
                    mb.join(can, Mc)
                x += 0.152 + 0.006
        else:
            x = xl + 0.004
            opened_done = False
            while x < xr - 0.15:
                bw = min(_f(r.uniform(0.22, 0.4)), xr - x)
                if bw < 0.15:
                    break
                bd = _f(r.uniform(0.28, 0.38))
                bh = min(_f(r.uniform(0.18, 0.3)), gapz)
                if r.uniform() < 0.88:
                    opn = (not opened_done) and r.uniform() < 0.4 and bh > 0.14 and x > -w / 2 + 0.045 and x + bw < w / 2 - 0.045
                    tl = None
                    if opn:                                              # solapas abiertas que no topen arriba ni atrás
                        ln = bd / 2
                        up_room = gapz - bh - 0.015
                        back_room = (yB - t - 0.004) - (yfront + bd)
                        tb_min = math.degrees(math.acos(max(-1.0, min(1.0, up_room / ln))))
                        if back_room < ln * math.sin(math.radians(max(tb_min, 3.0))):
                            opn = False
                        else:
                            tback = max(tb_min, 4.0) + 2.0
                            ts = math.degrees(math.acos(max(-1.0, min(1.0, up_room / (bd / 2 - 0.004)))))
                            room = min(x - (xl - 0.008), (xr + 0.008) - (x + bw))
                            ts_max = math.degrees(math.asin(max(0.0, min(1.0, room / (bd / 2 - 0.004)))))
                            if ts > ts_max:
                                opn = False
                            else:
                                dmax = bh - 0.006                        # solapa del frente colgando sobre la cara de la caja
                                tf = 180.0 - (math.degrees(math.acos(min(1.0, dmax / ln))) if ln > dmax else _f(r.uniform(6, 12)))
                                tl = [tf, tback, min(max(ts, 12.0) + 3.0, ts_max), min(max(ts, 12.0) + 3.0, ts_max)]
                    opened_done = opened_done or opn
                    st = (words[int(r.integers(0, 4))], 0.02) if r.uniform() < 0.6 else None
                    _carton(mb, _T(x + bw / 2, yfront + bd / 2 + abs(_jit(r, 0.008)), z) @ _Rz(_jit(r, 1.0)), bw - 0.008, bd, bh,
                            seed=int(r.integers(0, 999)), opened=opn, stamp=st, tilts=tl)
                    if not opn and bh < gapz * 0.5 and r.uniform() < 0.5:   # una caja chica encima
                        bh2 = min(_f(r.uniform(0.12, 0.2)), gapz - bh - 0.01)
                        if bh2 > 0.08:
                            _carton(mb, _T(x + bw / 2 + _jit(r, 0.02), yfront + bd * 0.45, z + bh + 0.0004) @ _Rz(_jit(r, 5)),
                                    bw * 0.7, bd * 0.8, bh2, seed=int(r.integers(0, 999)))
                x += bw + _f(r.uniform(0.006, 0.02))
    return mb


# ======================================================================================================== armero vertical
RACK_PITCH = 0.115           # paso entre ranuras del armero
RACK_TILT = 6.0              # inclinación hacia atrás de los cañones (grados)
RACK_ZC = 0.80               # altura del peine de cañones
RACK_BORE = 0.07             # eje del cañón a ~70 mm sobre la línea inferior de la culata (supuesto para el peine)


def weapon_rack_slots(n=8):
    """Matrices de colocación de las armas largas del armero (espacio local de weapon_rack(n)). Convención del arma: origen en
    la parte trasera inferior de la culata (talón inferior de la cantonera), cañón a lo largo de +X, lomo (+Z) arriba.
    En el armero el arma queda de pie sobre la cantonera en el tapete de hule de la charola (z = 0,072): cañón hacia arriba
    inclinado RACK_TILT° hacia atrás (+Y), lomo hacia +Y (el muro) y cargador/empuñadura hacia el frente (-Y); la culata
    ocupa ~16 cm hacia atrás desde el origen y el cañón descansa en la muesca forrada del peine (z = 0,80). Sin cambios
    respecto de kit.campaign.weapon_rack_slots (la geometría nueva respeta estas posiciones)."""
    th = math.radians(RACK_TILT)
    c, s = math.cos(th), math.sin(th)
    R = Matrix(((0, 1, 0, 0), (s, 0, c, 0), (c, 0, -s, 0), (0, 0, 0, 1)))
    out = []
    for i in range(n):
        x = (i - (n - 1) / 2) * RACK_PITCH
        out.append(Matrix.Translation((x, -0.085, 0.072)) @ R)
    return out


def _bead(mb, pts, r=0.0024, closed=False, ripple=0.14, pitch=0.0032, seg=10, mat="paint_od"):
    """Cordón de soldadura: tubo de sección redonda con las ondas del avance (radio modulado a paso `pitch`), sombreado suave.
    pts: polilínea (o lazo plano si closed)."""
    P = [Vector(p) for p in pts]
    if closed:
        P = P + [P[0]]
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    tot = acc[-1]
    n = max(4, int(tot / (pitch / 3)))
    Q = []
    for k in range(n + (0 if closed else 1)):
        sv = tot * k / n
        i = next((j for j in range(1, len(acc)) if acc[j] >= sv - 1e-12), len(acc) - 1)
        t = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-12)
        Q.append((P[i - 1].lerp(P[i], t), sv))
    m = len(Q)
    T = []
    for i in range(m):
        a = Q[(i + 1) % m][0] if closed else Q[min(i + 1, m - 1)][0]
        b = Q[i - 1][0] if closed else Q[max(i - 1, 0)][0]
        T.append((a - b).normalized())
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    rings = []
    for i in range(m):
        if i:
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        rr_ = r * (1 + ripple * math.sin(2 * PI * Q[i][1] / pitch))
        if not closed:
            e = min(Q[i][1], tot - Q[i][1])
            rr_ *= min(1.0, 0.35 + e / (2.5 * r))
        rings.append([Q[i][0] + (N * math.cos(2 * PI * k / seg) + B * math.sin(2 * PI * k / seg)) * rr_ for k in range(seg)])
    with mb.soft():
        if closed:
            R = [[mb.bm.verts.new(p) for p in ring] for ring in rings]
            mi = mb.mi(mat)
            for i in range(m):
                A, B_ = R[i], R[(i + 1) % m]
                for k in range(seg):
                    kk = (k + 1) % seg
                    f = mb.bm.faces.new([A[k], A[kk], B_[kk], B_[k]])
                    f.material_index = mi
                    f.smooth = True
        else:
            loft_rings(mb, rings, mat)


def _weld_around(mb, M, w, h, rc=0.004, rb=0.0024, mat="paint_od"):
    """Cordón perimetral alrededor de un tubo rectangular w × h (esquinas de radio rc) que llega a una cara: M con origen en el
    centro de la sección sobre la cara y z local a lo largo del tubo (alejándose de la cara)."""
    o = rb * 0.45
    pts = [M @ Vector((x, y, o)) for (x, y) in rr_pts(w + 2 * o, h + 2 * o, rc + o, 4)]
    _bead(mb, pts, rb, closed=True, mat=mat)


def _padlock(mb, M, seed=0, scratched=False):
    """Candado laminado de 40 mm: cuerpo de 10 láminas de acero con juntas visibles y cantos matados, 4 remaches arriba y abajo,
    cilindro de latón con bocallave abajo y defensa, arco de acero de Ø 7 mm (16 lados) con claro interior de 19 × 16 mm,
    pata larga y pata corta. M: origen en el punto interior más alto del arco (donde apoya en la grapa), cuelga hacia -Z,
    cara ancha hacia -Y."""
    W, Dd, Hh = 0.040, 0.024, 0.033
    ztop = -0.016                               # tapa del cuerpo: claro interior de 16 mm bajo el arco
    zb = ztop - Hh
    nl = 10
    zs = _axis_samples(zb, ztop, 0.0012, 2, 1.0, forced=[zb + Hh * k / nl + d_ for k in range(1, nl) for d_ in (-0.00025, 0.0, 0.00025)])
    xs = _axis_samples(-W / 2, W / 2, 0.003, 2, 0.01)
    ys = _axis_samples(-Dd / 2, Dd / 2, 0.003, 2, 0.01)
    joints = [zb + Hh * k / nl for k in range(1, nl)]

    def disp(Q, N, P):
        D = np.zeros_like(Q)
        g = np.zeros(len(Q))
        for zj in joints:
            g = np.maximum(g, np.clip(1 - np.abs(Q[:, 2] - zj) / 0.00025, 0, 1))
        side = np.abs(N[:, 2]) < 0.5
        D[:, 0] -= N[:, 0] * 0.0004 * g * side
        D[:, 1] -= N[:, 1] * 0.0004 * g * side
        return D
    _dbox(mb, M, xs, ys, zs, (0.003, 0.003, 0.0012), "steel", disp=disp)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for (z, s_) in ((ztop, 1), (zb, -1)):
                _rivet(mb, M @ _T(sx * 0.0145, sy * 0.0065, z) @ (Matrix() if s_ > 0 else _Rx(180)), r=0.0022)
    Mk = M @ _T(0.006, 0.0, zb) @ _Rx(180)
    _lathe(mb, [(0.0, 0.0002), (0.0064, 0.0002), (0.0064, -0.0003), (0.0068, -0.0003), (0.0068, 0.0006), (0.006, 0.0012),
                (0.0, 0.0012)], Mk, "brass", seg=SEG)
    _board(mb, -0.0008, 0.0008, -0.0032, 0.0032, 0.001, 0.0016, "cable", r=0.0003, M=Mk, step=1.0)
    rs = 0.0035
    Ra = 0.0095 + rs
    sh = [(-Ra, 0.0, ztop - 0.004)] + [(-Ra * math.cos(PI * k / 16), 0.0, -0.0095 + Ra * math.sin(PI * k / 16)) for k in range(17)] + \
         [(Ra, 0.0, ztop + 0.0015)]
    _tube(mb, [tuple(M @ Vector(p)) for p in sh], rs, seg=16, mat="steel")


def weapon_rack(n=8, seed=0):
    """Armero vertical de acero soldado para n armas largas (VACÍO; ver weapon_rack_slots), pintado verde olivo:
    patines de PTR 40 × 40 × 2 con tapas soldadas y orejas de anclaje con pija hexagonal de 3/8" y rondana al piso; postes de
    PTR 40 × 40 soldados con cordón perimetral; charola de culatas de lámina doblada (cal. 14) sobre dos travesaños, con
    divisiones soldadas y tapete de hule estriado en cada casilla; peine de cañones de placa de 1/4" con muescas forradas de
    perfil U de hule y ménsulas soldadas a los postes; travesaño superior y riel trasero soldados; barra de seguridad de
    solera abisagrada (3 nudillos y perno) que cierra frente a las bocas de las muescas, con oreja ranurada en la punta que
    pasa por la grapa soldada al poste derecho y candado laminado colgado de la grapa. Origen: piso al centro; frente -Y."""
    r = rng(seed)
    mb = MB()
    P = "paint_od"
    Wr = n * RACK_PITCH + 0.09
    x0, x1 = -Wr / 2, Wr / 2
    xu = Wr / 2 - 0.02                           # eje de los postes
    yf, yb = -0.12, 0.09
    zt = 0.06
    # ---- patines con tapas y orejas de anclaje
    for sx in (-1, 1):
        x = sx * xu
        rtube(mb, (x, -0.26 + 0.003, 0.022), (x, 0.22 - 0.003, 0.022), 0.04, 0.04, P, r=0.004, caps=True)
        for (ye, s_) in ((-0.26, -1), (0.22, 1)):                       # tapas soldadas en las puntas del patín
            _board(mb, x - 0.02, x + 0.02, min(ye, ye - s_ * 0.003), max(ye, ye - s_ * 0.003), 0.002, 0.042, P, r=0.0012, step=1.0)
            _bead(mb, [(x - 0.02, ye - s_ * 0.003, 0.0425), (x + 0.02, ye - s_ * 0.003, 0.0425)], 0.0018, mat=P)
            # oreja de anclaje del lado de adentro
            yc_ = ye - s_ * 0.035
            xt = x - sx * 0.02
            _board(mb, min(xt, xt - sx * 0.045), max(xt, xt - sx * 0.045), yc_ - 0.022, yc_ + 0.022, 0.0, 0.005, P, r=0.0015, step=1.0)
            _bead(mb, [(xt - sx * 0.002, yc_ - 0.02, 0.0065), (xt - sx * 0.002, yc_ + 0.02, 0.0065)], 0.0022, mat=P)
            _hexbolt(mb, _T(xt - sx * 0.024, yc_, 0.005), d=0.0095, h=0.0064, washer=True, mat="galvanized")
        # poste soldado al patín
        rtube(mb, (x, 0.0, 0.042), (x, 0.0, 1.0), 0.04, 0.04, P, r=0.004, up=(0, 1, 0))
        _weld_around(mb, _T(x, 0.0, 0.042), 0.04, 0.04)
        slab(mb, _T(x, 0.0, 1.0), 0.0405, 0.0405, 0.003, rc=0.004, re=0.001, mat=P, nc=3, ne=1)
    # ---- travesaños bajo la charola y charola de lámina doblada
    for yy in (-0.085, 0.06):
        rtube(mb, (-xu + 0.02, yy, 0.048), (xu - 0.02, yy, 0.048), 0.02, 0.02, P, r=0.002)
        for sx in (-1, 1):
            _weld_around(mb, _T(sx * (xu - 0.02), yy, 0.048) @ _Ry(-90 * sx), 0.02, 0.02, rc=0.002, rb=0.002)
    t = 0.0019
    xa, xb = -xu + 0.02, xu - 0.02

    # charola: canal barrido a lo largo de X (sección en U con dobleces de radio real)
    Lp = [(y, z) for (y, z) in fillet([(yf + t / 2, zt + 0.045), (yf + t / 2, zt - t / 2), (yb - t / 2, zt - t / 2),
                                         (yb - t / 2, zt + 0.06)], 0.006, 4)]
    outer, inner = [], []
    for i, (y, z) in enumerate(Lp):
        a = Vector((0, Lp[min(i + 1, len(Lp) - 1)][0] - Lp[max(i - 1, 0)][0], Lp[min(i + 1, len(Lp) - 1)][1] - Lp[max(i - 1, 0)][1])).normalized()
        nrm = Vector((0, -a.z, a.y))
        outer.append((y + nrm.y * t / 2, z + nrm.z * t / 2))
        inner.append((y - nrm.y * t / 2, z - nrm.z * t / 2))
    sec = outer + inner[::-1]
    loops = [[(x, y, z) for (y, z) in sec] for x in (xa, xb)]
    skin(mb, loops, P)
    for x in (xa, xb):                                                   # charola soldada a los postes por sus extremos
        sx = 1 if x > 0 else -1
        _bead(mb, [(x - sx * 0.0035, yf + 0.004, zt + 0.0025), (x - sx * 0.0035, yb - 0.004, zt + 0.0025)], 0.0016, mat=P)
    zr = zt + 0.0015
    for i in range(n + 1):                                               # divisiones y tapetes estriados
        xd = (i - n / 2) * RACK_PITCH
        if 0 < i < n:
            _board(mb, xd - 0.0015, xd + 0.0015, yf + t + 0.0003, yb - t - 0.0003, zt - 0.0002, zt + 0.048, P, r=0.0007, step=1.0)
            for yy in (yf + 0.004, yb - 0.004):
                _bead(mb, [(xd - 0.0032, yy, zt + 0.002), (xd - 0.0032, yy, zt + 0.04)], 0.0013, mat=P)
        if i < n:
            xm0 = xd + (0.0018 if i > 0 else 0.0)
            xm1 = xd + RACK_PITCH - (0.0018 if i < n - 1 else 0.0)
            if i == 0:
                xm0 = max(xm0, xa + 0.0005)
            if i == n - 1:
                xm1 = min(xm1, xb - 0.0005)
            ys_r = [yf + t + 0.002 + k * 0.012 for k in range(int((yb - yf - 2 * t - 0.004) / 0.012) + 1)]

            def rib(Q, N, P_, ys_r=ys_r):
                D = np.zeros_like(Q)
                top = N[:, 2] > 0.7
                ph = np.cos((Q[:, 1] - ys_r[0]) / 0.012 * 2 * PI)
                D[:, 2] = np.where(top, -0.0012 * (0.5 - 0.5 * ph), 0.0)
                return D
            _dbox(mb, None, _axis_samples(xm0, xm1, 0.002, 2, 0.2),
                  _axis_samples(yf + t + 0.0006, yb - t - 0.0006, 0.002, 2, 0.003), _axis_samples(zr - 0.0003, zr + 0.0105, 0.002, 2, 1.0),
                  0.002, "rubber", disp=rib, ngon=(4,))
    # ---- postes: travesaño superior y riel trasero soldados
    rtube(mb, (x0 + 0.04, 0.0, 0.985), (x1 - 0.04, 0.0, 0.985), 0.03, 0.03, P, r=0.003)
    rtube(mb, (x0 + 0.04, 0.012, 0.42), (x1 - 0.04, 0.012, 0.42), 0.016, 0.03, P, r=0.002)
    for sx in (-1, 1):
        _weld_around(mb, _T(sx * (xu - 0.02), 0.0, 0.985) @ _Ry(-90 * sx), 0.03, 0.03, rc=0.003)
        _weld_around(mb, _T(sx * (xu - 0.02), 0.012, 0.42) @ _Ry(-90 * sx), 0.016, 0.03, rc=0.002, rb=0.002)
    # ---- peine de cañones: placa de 1/4" con muescas y forro U de hule
    th = math.radians(RACK_TILT)
    tt = (RACK_ZC - 0.072 + RACK_BORE * math.sin(th)) / math.cos(th)
    yc = -0.085 + RACK_BORE * math.cos(th) + tt * math.sin(th)        # eje del cañón a la altura del peine
    rn, yfr = 0.026, yc - 0.075
    pts = []
    for i in range(n):
        xc = (i - (n - 1) / 2) * RACK_PITCH
        mouth = fillet([(xc - 0.042, yfr), (xc - 0.031, yfr), (xc - rn, yc)], 0.006, 3)[:-1]
        pts += mouth
        for k in range(17):
            a = PI - PI * k / 16
            pts.append((xc + rn * math.cos(a), yc + rn * math.sin(a)))
        pts += [(2 * xc - p_[0], p_[1]) for p_ in reversed(mouth)]
    outline = [(x0 + 0.04, yfr)] + [p_[:2] for p_ in pts] + [(x1 - 0.04, yfr), (x1 - 0.04, yc + 0.07), (x0 + 0.04, yc + 0.07)]
    clean = [outline[0]]
    for p_ in outline[1:]:
        if math.hypot(p_[0] - clean[-1][0], p_[1] - clean[-1][1]) > 2e-4:
            clean.append(p_)
    mb.plate(clean, 0.0064, P, m=_T(0, 0, RACK_ZC - 0.0032))
    U = [(0.0021, -0.0052), (0.0021, 0.0052), (0.0009, 0.0062), (-0.006, 0.0062), (-0.0068, 0.0055), (-0.0068, 0.0043), (-0.006, 0.0036),
         (-0.0002, 0.0036), (-0.0002, -0.0036), (-0.006, -0.0036), (-0.0068, -0.0043), (-0.0068, -0.0055), (-0.006, -0.0062), (0.0009, -0.0062)]
    for i in range(n):
        xc = (i - (n - 1) / 2) * RACK_PITCH
        e = [(xc - 0.031, yfr + 0.0005, RACK_ZC), (xc - rn, yc, RACK_ZC)] + \
            [(xc + rn * math.cos(PI - PI * k / 16), yc + rn * math.sin(PI - PI * k / 16), RACK_ZC) for k in range(1, 16)] + \
            [(xc + rn, yc, RACK_ZC), (xc + 0.031, yfr + 0.0005, RACK_ZC)]
        sweep_frame(mb, U, fillet(e, 0.01, 4), "rubber", up=(0, 0, 1))
    for sx in (-1, 1):                                                   # ménsulas del peine a los postes
        x = sx * (xu - 0.02)
        xa_, xb_ = sorted((x, x - sx * 0.035))
        _board(mb, xa_, xb_, -0.018, yc + 0.065, RACK_ZC - 0.0092, RACK_ZC - 0.0032, P, r=0.0012, step=1.0)
        _bead(mb, [(x - sx * 0.0025, -0.016, RACK_ZC - 0.0035), (x - sx * 0.0025, 0.016, RACK_ZC - 0.0035)], 0.0022, mat=P)
        _bead(mb, [(x - sx * 0.0025, -0.016, RACK_ZC - 0.0115), (x - sx * 0.0025, 0.016, RACK_ZC - 0.0115)], 0.0022, mat=P)
    # ---- barra de seguridad abisagrada (cerrada) frente a las bocas de las muescas
    yl = min(yfr - 0.008, -0.031)
    zl = RACK_ZC + 0.019
    xh = -xu
    for k in range(3):                                                   # bisagra de 3 nudillos al frente del poste izquierdo
        zk = zl - 0.03 + k * 0.02
        _lathe(mb, [(0.0045, 0.0), (0.0083, 0.0), (0.0085, 0.0005), (0.0085, 0.0185), (0.0083, 0.019), (0.0045, 0.019)],
               _T(xh, yl, zk + 0.0005), P, seg=SEG, closed=True)
    _cyl(mb, (xh, yl, zl - 0.0335), (xh, yl, zl + 0.0335), 0.0045, "steel", seg=SEG)
    for s_ in (-1, 1):
        _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0058, 0.0016), (0.0038, 0.0028), (0.0, 0.003)], _T(xh, yl, zl + s_ * 0.0335) @
               (Matrix() if s_ > 0 else _Rx(180)), "steel", seg=SEG)
    for k in (0, 2):                                                     # hojas fijas soldadas al poste
        zk = zl - 0.03 + k * 0.02
        _board(mb, xh - 0.007, xh + 0.007, yl + 0.004, -0.0198, zk + 0.001, zk + 0.0185, P, r=0.0012, step=1.0)
        _bead(mb, [(xh - 0.008, -0.0215, zk + 0.002), (xh - 0.008, -0.0215, zk + 0.0175)], 0.0015, mat=P)
        _bead(mb, [(xh + 0.008, -0.0215, zk + 0.002), (xh + 0.008, -0.0215, zk + 0.0175)], 0.0015, mat=P)
    rtube(mb, (xh + 0.0085, yl, zl), (xu - 0.012, yl, zl), 0.008, 0.025, P, r=0.0025, up=(0, 0, 1))
    _weld_around(mb, _T(xh + 0.0085, yl, zl) @ _Ry(90), 0.008, 0.025, rc=0.002, rb=0.0016)
    # oreja ranurada en la punta de la barra, grapa soldada al poste derecho y candado
    xs_ = xu
    xt0, xt1 = xu - 0.03, xu + 0.016
    zt0, zt1 = zl - 0.022, zl + 0.022
    holed_outer = (0.0, 0.0, (xt1 - xt0) / 2, (zt1 - zt0) / 2, 0.006)
    from kit.clinic_servicios import holed
    holed(mb, _T((xt0 + xt1) / 2, yl + 0.0025, zl) @ _Rx(90), holed_outer, (xs_ - (xt0 + xt1) / 2, 0.0, 0.004, 0.017, 0.0039), 0.005,
          re_o=0.0012, re_i=0.0008, n=48, mat=P, ne=2, ctr=(xs_ - (xt0 + xt1) / 2, 0.0))
    _bead(mb, [(xt0 + 0.002, yl - 0.0035, zl - 0.012), (xt0 + 0.002, yl - 0.0035, zl + 0.012)], 0.0018, mat=P)
    ys0, ys1 = -0.0198, yl - 0.022
    st = [(xs_, ys0, zl - 0.012), (xs_, ys1, zl - 0.012), (xs_, ys1, zl + 0.012), (xs_, ys0, zl + 0.012)]
    _tube(mb, fillet(st, 0.007, 6), 0.0032, seg=16, mat="steel")
    for zz in (zl - 0.012, zl + 0.012):
        _weld_around(mb, _T(xs_, -0.02, zz) @ _Rx(90), 0.0064, 0.0064, rc=0.0031, rb=0.0016)
    _padlock(mb, _T(xs_ + 0.0003, yl - 0.0125, zl - 0.012 + 0.0032 + 0.0001), seed=seed)
    del r
    return mb


# ======================================================================================================== tablero perforado
PEG = 0.0254
PEG_T = 0.00635                # hardboard de 1/4"
PEG_HR = 0.003175              # perforación de 1/4"
PEG_YB = -0.019                # espalda del tablero (sobre listones de 3/4")
PEG_YF = PEG_YB - PEG_T        # cara frontal
HOOK_RW = 0.0024               # alambre de 0,186" (4,7 mm)
HOOK_L = 0.1016                # brazo de 4"
HOOK_RISE = 10.0               # el brazo sube 10° hacia la punta


def _peg_grid(w, h):
    nx = int(w / PEG) - 1
    nz = int(h / PEG) - 1
    xs = [(i - (nx - 1) / 2) * PEG for i in range(nx)]
    zs = [(j + 1) * PEG + (h - (nz + 1) * PEG) / 2 for j in range(nz)]
    hooks = []
    for fz in (0.74, 0.36):
        for fx in (0.27, 0.73):
            hooks.append((int(round(fx * (nx - 1))), int(round(fz * (nz - 1)))))
    return xs, zs, hooks


def pegboard_hooks(w=1.2, h=1.0):
    """Puntos de cuelgue de los ganchos del tablero (espacio local de pegboard(w, h)): Matrix con la traslación sobre el lomo
    del alambre del brazo, a 2 cm de la punta, donde descansa la gaza / el gancho del objeto (ejes del mundo: el objeto
    cuelga hacia -Z con su frente a -Y). 4 ganchos de 4" en 2 filas × 2 columnas. Coincide con la geometría de pegboard():
    el brazo sale de la perforación inferior del gancho (alambre apoyado en el fondo del barreno) y sube HOOK_RISE°."""
    xs, zs, hooks = _peg_grid(w, h)
    a = math.radians(HOOK_RISE)
    s = HOOK_L - 0.02
    out = []
    for (i, j) in hooks:
        z0 = zs[j] - (PEG_HR - HOOK_RW) * 0.9
        out.append(Matrix.Translation((xs[i], PEG_YF - s * math.cos(a), z0 + s * math.sin(a) + HOOK_RW / math.cos(a))))
    return out


def _peg_board(mb, w, h, xs, zs, r=0.0012, mat="wood_dark"):
    """Hardboard de 1/4" con perforaciones pasantes reales de 1/4" a 1" entre centros (12 lados, pared con sombreado suave):
    celdas de 1" con 12 nodos en el borde unidos a cada barreno, franja perimetral y canto matado."""
    yf, yb = PEG_YF, PEG_YB
    nx, nz = len(xs), len(zs)
    LX = [xs[0] - PEG / 2 + PEG * k / 3 for k in range(3 * nx + 1)]
    LZ = [zs[0] - PEG / 2 + PEG * k / 3 for k in range(3 * nz + 1)]
    mi = mb.mi(mat)
    VF, VB = {}, {}

    def vf(ix, iz, store, y):
        k = (ix, iz)
        if k not in store:
            store[k] = mb.bm.verts.new((LX[ix], y, LZ[iz]))
        return store[k]

    def F(vs, soft=False):
        f = mb.bm.faces.new(vs)
        f.material_index = mi
        f.smooth = True
        return f
    sl = mb._soft_layer()
    angs = [math.radians(-15 + 30 * k) for k in range(12)]
    for ci in range(nx):
        for cj in range(nz):
            a, b = 3 * ci, 3 * cj
            ring = [(a + 3, b + 1), (a + 3, b + 2), (a + 3, b + 3), (a + 2, b + 3), (a + 1, b + 3), (a, b + 3), (a, b + 2), (a, b + 1),
                    (a, b), (a + 1, b), (a + 2, b), (a + 3, b)]
            cx, cz = xs[ci], zs[cj]
            HF = [mb.bm.verts.new((cx + PEG_HR * math.cos(t_), yf, cz + PEG_HR * math.sin(t_))) for t_ in angs]
            HB = [mb.bm.verts.new((cx + PEG_HR * math.cos(t_), yb, cz + PEG_HR * math.sin(t_))) for t_ in angs]
            for k in range(12):
                kk = (k + 1) % 12
                F([vf(*ring[k], VF, yf), vf(*ring[kk], VF, yf), HF[kk], HF[k]])
                F([vf(*ring[kk], VB, yb), vf(*ring[k], VB, yb), HB[k], HB[kk]])
                fw = F([HF[k], HF[kk], HB[kk], HB[k]])
                fw[sl] = 1
    # franja perimetral y canto matado
    per = [(ix, 0) for ix in range(3 * nx)] + [(3 * nx, iz) for iz in range(3 * nz)] + [(ix, 3 * nz) for ix in range(3 * nx, 0, -1)] + \
          [(0, iz) for iz in range(3 * nz, 0, -1)]

    def outer(ix, iz, ins):
        x, z = LX[ix], LZ[iz]
        xo = -w / 2 + ins if ix == 0 else (w / 2 - ins if ix == 3 * nx else x)
        zo = ins if iz == 0 else (h - ins if iz == 3 * nz else z)
        return xo, zo
    c = 1 - math.sqrt(0.5)
    prof = [(r, yf), (r * c, yf + r * c), (0.0, yf + r), (0.0, yb - r), (r * c, yb - r * c), (r, yb)]
    rings = [[mb.bm.verts.new((*outer(ix, iz, ins)[:1], y, outer(ix, iz, ins)[1])) for (ix, iz) in per] for (ins, y) in prof]
    n = len(per)
    for k in range(n):
        kk = (k + 1) % n
        F([vf(*per[k], VF, yf), vf(*per[kk], VF, yf), rings[0][kk], rings[0][k]])
        F([vf(*per[kk], VB, yb), vf(*per[k], VB, yb), rings[-1][k], rings[-1][kk]])
        for q in range(len(prof) - 1):
            F([rings[q][k], rings[q][kk], rings[q + 1][kk], rings[q + 1][k]])


def _j_trim(mb, w, h, mat="aluminium"):
    """Moldura J de aluminio que abraza el canto del tablero: ceja frontal de 8 mm con orilla redondeada, pared exterior y ceja
    trasera de 4 mm, esquinas a inglete (0,2 mm de holgura con el tablero)."""
    yf, yb = PEG_YF, PEG_YB
    g = 0.0002
    sec = [(0.0081, yf - g - 0.0004), (0.0078, yf - g - 0.0011), (0.0072, yf - g - 0.0012), (-0.0004, yf - g - 0.0012),
           (-0.0010, yf - g - 0.0009), (-0.0012 - g, yf - g - 0.0003), (-0.0012 - g, yb + g + 0.0003), (-0.0010, yb + g + 0.0009),
           (-0.0004, yb + g + 0.0011), (0.0038, yb + g + 0.0011), (0.0042, yb + g + 0.0006), (0.0040, yb + g), (-g, yb + g),
           (-g, yf - g), (0.0076, yf - g)]
    loops = []
    for (ins, y) in sec:
        L = [(-w / 2 + ins, y, ins), (w / 2 - ins, y, ins), (w / 2 - ins, y, h - ins), (-w / 2 + ins, y, h - ins)]
        loops.append(L)
    skin(mb, loops, mat, closed=True)


def _peg_hook(mb, x, zl, zu, mat="galvanized"):
    """Gancho de alambre de un brazo de 4": brazo de la perforación inferior con subida de 10° y punta redonda; doblez de radio
    real hacia el lomo pegado a la cara, que entra por la perforación superior y se dobla hacia abajo detrás del tablero;
    patita corta que entra por la perforación inferior."""
    yf, yb = PEG_YF, PEG_YB
    rw = HOOK_RW
    a = math.radians(HOOK_RISE)
    z0 = zl - (PEG_HR - rw) * 0.9
    zt = zu - (PEG_HR - rw) * 0.9
    tip = (x, yf - HOOK_L * math.cos(a), z0 + HOOK_L * math.sin(a))
    path = [tip, (x, yf - 0.006, z0 + 0.006 * math.sin(a)), (x, yf - rw - 0.0002, z0), (x, yf - rw - 0.0002, zt), (x, yb + 0.004, zt),
            (x, yb + 0.004, zt - 0.014)]
    with mb.soft():
        _tube(mb, fillet(path, 0.0042, 6), rw, seg=12, mat=mat, caps=True)
        _tube(mb, fillet([(x, yf - rw - 0.0002, z0 + 0.0047), (x, yf - rw - 0.0002, z0 + 0.0004), (x, yb - 0.001, z0 + 0.0004)], 0.003,
                         4), rw * 0.96, seg=12, mat=mat)
        _lathe(mb, [(0.0, -rw * 1.1), (rw * 0.8, -rw * 0.8), (rw * 1.15, 0.0), (rw * 0.8, rw * 0.8), (0.0, rw * 1.1)],
               _frame_z(Vector(tip), Vector((0, -math.cos(a), math.sin(a)))), mat, seg=12)


def pegboard(w=1.2, h=1.0, seed=0, posts=None):
    """Tablero perforado de hardboard de 1/4" (6,35 mm) con perforaciones REALES de 1/4" a 1" entre centros (pasantes, con
    pared), canto matado y moldura J de aluminio en todo el perímetro; bastidor de listones de 1×2" (19 × 38 mm) detrás que
    lo separa 19 mm del muro (el hueco para los ganchos), atornillado con pijas de cabeza de gota y rondana de copa; 4 ganchos
    de alambre de 4" en 2 filas × 2 columnas (ver pegboard_hooks). posts=x (opcional): los largueros de arriba y abajo se
    alargan hasta postes de 2×4 con eje en x = ±posts y se atornillan a su cara (mil_builder: posts=0.62).
    Origen: plano del muro / cara de los postes (y = 0), centro del canto inferior del tablero; crece hacia -Y y +Z."""
    r = rng(seed)
    mb = MB()
    xs, zs, hooks = _peg_grid(w, h)
    _peg_board(mb, w, h, xs, zs)
    _j_trim(mb, w, h)
    # bastidor de listones
    tb = 0.038
    xe = (posts + 0.019) if posts else w / 2
    for (za, zb) in ((0.0, tb), (h - tb, h)):
        _board(mb, -xe, xe, PEG_YB + 0.0001, -0.0003, za, zb, "wood", r=0.0025, step=0.4)
    for x in (-w / 2 + tb / 2, 0.0, w / 2 - tb / 2):
        _board(mb, x - tb / 2, x + tb / 2, PEG_YB + 0.0001, -0.0003, tb + 0.0004, h - tb - 0.0004, "wood", r=0.0025, step=0.4)
    if posts:
        for sx in (-1, 1):                                               # pijas de los largueros a los postes
            for z in (tb / 2, h - tb / 2):
                _screw_cs(mb, _T(sx * posts, PEG_YB, z) @ _Rx(90), d=0.008, seed=int(z * 100) + sx)
    # pijas con rondana de copa en celdas (esquinas de 4 perforaciones) sobre los listones
    nx, nz = len(xs), len(zs)
    pts = []
    for ci in (0, nx // 2, nx):
        for cj in (0, nz // 2, nz):
            x = xs[0] - PEG / 2 + ci * PEG
            z = zs[0] - PEG / 2 + cj * PEG
            if ci == nx // 2:
                x = xs[nx // 2] - PEG / 2
            pts.append((x, z))
    for (x, z) in pts:
        x = min(max(x, -w / 2 + 0.019), w / 2 - 0.019)
        if not (abs(x) < 0.02 or abs(abs(x) - (w / 2 - tb / 2)) < 0.03):
            continue
        if not (z < tb + 0.005 or z > h - tb - 0.005 or abs(abs(x) - (w / 2 - tb / 2)) < 0.03 or abs(x) < 0.02):
            continue
        M = _T(x, PEG_YF, z) @ _Rx(90)
        _lathe(mb, [(0.0048, -0.0002), (0.0052, 0.0002), (0.0047, 0.0012), (0.0032, 0.0014), (0.0032, 0.0006), (0.0, 0.0006)], M, "steel",
               seg=SEG)
        _lathe(mb, [(0.0, 0.0005), (0.0031, 0.0005), (0.003, 0.0015), (0.002, 0.0024), (0.0, 0.0026)], M, "steel", seg=16)
    for (i, j) in hooks:
        _peg_hook(mb, xs[i], zs[j], zs[j + 1])
    del r
    return mb


# ======================================================================================================== mesa y silla plegables
TABLE_TOP = 0.737              # 29"


def _channel(mb, p0, p1, w=0.02, hgt=0.025, t=0.0014, up=(0, 0, 1), mat="steel", open_down=True):
    """Canal C de lámina rolada (alma arriba, alas hacia abajo) con dobleces de radio real, de p0 a p1."""
    r = 0.0025
    s = -1 if open_down else 1
    o = [(-w / 2, s * hgt), (-w / 2, 0.0), (w / 2, 0.0), (w / 2, s * hgt)]
    path = fillet([(x, z) + (0,) for (x, z) in o], r, 3)
    out, inn = [], []
    P = [Vector(p) for p in path]
    for i, p in enumerate(P):
        a = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        n = Vector((-a.y, a.x, 0)) * (-s)
        out.append((p.x + n.x * t / 2, p.y + n.y * t / 2))
        inn.append((p.x - n.x * t / 2, p.y - n.y * t / 2))
    prof = out + inn[::-1]
    sweep_frame(mb, prof, [p0, p1], mat, up=up)


def folding_table(L=1.83, seed=0):
    """Mesa plegable de 6 ft (72 × 30 × 29"; 1,83 × 0,76 × 0,737 m): cubierta de polietileno de alta densidad soplada de 2" con
    canto de media caña, línea de partición del molde, faldón inferior y bajo cara con nervaduras moldeadas; bastidor de
    canal C de acero rolado atornillado al bajo cara (largueros, cabezales y travesaños de los tirantes); dos juegos de patas
    en U de tubo de 1" (25 mm) con eje en abrazaderas de lámina, travesaño inferior soldado, tirante plegable de dos
    eslabones con remaches y anillo de seguro en la rodilla, y regatones de hule con domo. Origen: piso al centro; L en X.
    Cara superior a TABLE_TOP = 0,737 m."""
    r = rng(seed)
    mb = MB()
    D, H = 0.762, TABLE_TOP
    tt = 0.05
    rcp = 0.045
    zu = H - 0.034                                                       # bajo cara (dentro del faldón)

    def LL(ins, z):
        return [(x, y, z) for (x, y) in rr_pts(L - 2 * ins, D - 2 * ins, max(rcp - ins, 0.004), 6)]
    rt, rb = 0.017, 0.006
    loops = []
    for k in range(7):                                                   # media caña superior
        a = PI / 2 * k / 6
        loops.append(LL(rt - rt * math.sin(a), H - rt + rt * math.cos(a)))
    zm = H - tt / 2 - 0.004                                              # línea de partición del molde
    loops += [LL(0.0, zm + 0.002), LL(-0.0006, zm + 0.0007), LL(-0.0006, zm - 0.0007), LL(0.0, zm - 0.002), LL(0.0, H - tt + rb)]
    for k in range(1, 4):
        a = PI / 2 * k / 3
        loops.append(LL(rb - rb * math.cos(a), H - tt + rb - rb * math.sin(a)))
    loops += [LL(0.03, H - tt), LL(0.033, H - tt + 0.0015), LL(0.034, zu - 0.002), LL(0.036, zu)]
    skin(mb, loops, "plastic")
    # nervaduras moldeadas en el bajo cara (evitan el bastidor y las abrazaderas)
    xr_ = L / 2 - 0.06
    for y in (-0.24, -0.12, 0.0, 0.12, 0.24):
        for (xa, xb) in ((-xr_ + 0.07, -L / 2 + 0.45), (-L / 2 + 0.47, L / 2 - 0.47), (L / 2 - 0.45, xr_ - 0.07)):
            _board(mb, xa, xb, y - 0.004, y + 0.004, zu - 0.011, zu + 0.001, "plastic", r=0.003, step=0.3, ngon=(5,))
    for x in np.linspace(-L / 2 + 0.6, L / 2 - 0.6, 4):
        _board(mb, x - 0.004, x + 0.004, -0.3, 0.3, zu - 0.0125, zu + 0.001, "plastic", r=0.003, step=0.2, ngon=(5,))
    # bastidor de canal C atornillado
    yr = D / 2 - 0.05
    for sy in (-1, 1):
        _channel(mb, (-L / 2 + 0.055, sy * yr, zu), (L / 2 - 0.055, sy * yr, zu), w=0.022, hgt=0.024, up=(0, 0, 1))
        for x in np.linspace(-L / 2 + 0.15, L / 2 - 0.15, 6):
            _hexbolt(mb, _T(x, sy * yr, zu - 0.0014) @ _Rx(180), d=0.006, h=0.0035, washer=False, mat="steel")
    for sx in (-1, 1):
        for xx in (sx * (L / 2 - 0.055), sx * (L / 2 - 0.42)):
            _channel(mb, (xx, -yr + 0.012, zu), (xx, yr - 0.012, zu), w=0.022, hgt=0.024 if abs(xx) > 0.5 else 0.02, up=(0, 0, 1))
    # patas
    R = 0.0127
    yl = D / 2 - 0.085
    zp = zu - 0.024 - R - 0.002
    for sx in (-1, 1):
        xl = sx * (L / 2 - 0.11)
        zb = 0.028
        leg = [(xl, -yl, zb), (xl, -yl, zp), (xl, yl, zp), (xl, yl, zb)]
        _tube(mb, fillet(leg, 0.05, 10), R, seg=SEG, mat="steel")
        for sy in (-1, 1):                                               # regatones de hule
            _lathe(mb, [(0.0, 0.0), (0.0128, 0.0), (0.0148, 0.0015), (0.0152, 0.006), (0.0146, 0.009), (0.0146, 0.029), (0.0136, 0.031),
                        (R - 0.0004, 0.031), (R - 0.0004, 0.026)], _T(xl, sy * yl, 0.0), "rubber", seg=SEG)
            _lathe(mb, [(0.0152, 0.0062), (0.0158, 0.007), (0.0152, 0.0078)], _T(xl, sy * yl, 0.0), "rubber", seg=SEG, closed=True)
        zc = 0.13
        _cyl(mb, (xl, -yl + R * 0.6, zc), (xl, yl - R * 0.6, zc), 0.0095, "steel", seg=SEG, caps=True)
        for sy in (-1, 1):
            _weld_around(mb, _T(xl, sy * (yl - R * 0.9), zc) @ _Rx(90 * sy), 0.019, 0.019, rc=0.0094, rb=0.0016, mat="steel")
        # abrazaderas del eje (lámina en U atornillada al bajo cara)
        for yb_ in (-0.2, 0.2):
            path = [(xl - 0.04, yb_, zu - 0.0005), (xl - R - 0.0012, yb_, zu - 0.0005), (xl - R - 0.0012, yb_, zp)] + \
                   [(xl - (R + 0.0012) * math.cos(PI * k / 8), yb_, zp - (R + 0.0012) * math.sin(PI * k / 8)) for k in range(1, 8)] + \
                   [(xl + R + 0.0012, yb_, zp), (xl + R + 0.0012, yb_, zu - 0.0005), (xl + 0.04, yb_, zu - 0.0005)]
            sweep_frame(mb, rr_profile(0.0022, 0.02, 0.0008, n=1), fillet(path, 0.003, 3), "steel", up=(0, 1, 0))
            for dx in (-0.029, 0.029):
                _hexbolt(mb, _T(xl + dx, yb_, zu - 0.0016) @ _Rx(180), d=0.006, h=0.0035, washer=False, mat="steel")
        # tirante plegable: del travesaño inferior al travesaño de la cubierta, rodilla con remache y anillo de seguro
        p0 = Vector((xl, 0.0, zc))
        p2 = Vector((sx * (L / 2 - 0.42), 0.0, zu - 0.012))
        pm = p0.lerp(p2, 0.5)
        u = (p2 - p0).normalized()
        for (a_, b_) in ((p0 + u * 0.012, pm - u * 0.003), (pm + u * 0.003, p2 - u * 0.012)):
            for sy in (-1, 1):
                Mb_, Lb_ = port.frame_on(tuple(a_ + Vector((0, sy * 0.0105, 0))), tuple(b_ + Vector((0, sy * 0.0105, 0))), (0, 1, 0))
                sweep_frame(mb, [(x, y) for (x, y) in rr_profile(0.016, 0.0035, 0.0012, n=2)],
                            [tuple(a_ + Vector((0, sy * 0.0105, 0))), tuple(b_ + Vector((0, sy * 0.0105, 0)))], "steel", up=(0, 1, 0))
        for (pp, rr_) in ((p0, 0.0045), (pm, 0.004), (p2, 0.004)):
            _cyl(mb, tuple(pp + Vector((0, -0.0145, 0))), tuple(pp + Vector((0, 0.0145, 0))), rr_ * 0.6, "steel", seg=16)
            for sy in (-1, 1):
                _lathe(mb, [(0.0, 0.0), (rr_ * 1.25, 0.0), (rr_ * 1.1, 0.0012), (rr_ * 0.6, 0.0019), (0.0, 0.002)],
                       _T(pp.x, sy * 0.0128, pp.z) @ _Rx(-90 * sy), "steel", seg=16)
        _lathe(mb, [(0.0152, -0.02), (0.0168, -0.0195), (0.017, -0.017), (0.017, 0.017), (0.0168, 0.0195), (0.0152, 0.02),
                    (0.0145, 0.016), (0.0145, -0.016)], _frame_z(pm + u * 0.03, u), "steel", seg=SEG, closed=True)
        # abrazadera del tirante en el travesaño inferior
        _lathe(mb, [(0.0095, -0.02), (0.0118, -0.02), (0.0118, 0.02), (0.0095, 0.02)], _T(xl, 0.0, zc) @ _Rx(90), "steel", seg=SEG,
               closed=True)
    del r
    return mb


def folding_chair(seed=0):
    """Silla plegable de acero de doble bisagra: marco delantero / respaldo de tubo de 7/8" (22 mm) cal. 18 doblado con radio
    real, patas traseras en U con dos travesaños, travesaño delantero; asiento de lámina embutida con faldón y dobladillo,
    montado en ménsulas de canal con remaches de pivote (rondanas) al marco y a las patas traseras; respaldo curvo de lámina
    con orillas enrolladas remachado a los postes; regatones de plástico con domo en las cuatro patas. Asiento a 17-1/2"
    (0,445 m), alto total 29-1/2" (0,75 m). Pintura OD. Origen: piso al centro; frente -Y."""
    mb = MB()
    P = "paint_od"
    R = 0.0111
    hs = 0.445
    wf = 0.41                                                            # ancho entre ejes del marco delantero
    yfa, ytop, ztop = -0.22, 0.165, 0.75 - R
    for sx in (-1, 1):                                                   # marco delantero / respaldo (cada lado)
        x = sx * wf / 2
        pth = [(x, yfa, 0.028), (x, 0.075, hs + 0.03), (x, 0.13, 0.62), (x, ytop, ztop - 0.03)]
        _tube(mb, fillet(pth, 0.12, 12), R, seg=SEG, mat=P)
    top = [(-wf / 2, ytop - 0.0006, ztop - 0.034), (-wf / 2, ytop + 0.004, ztop), (wf / 2, ytop + 0.004, ztop),
           (wf / 2, ytop - 0.0006, ztop - 0.034)]
    _tube(mb, fillet(top, 0.035, 10), R, seg=SEG, mat=P)
    wr = 0.37
    # pivote de las patas traseras SOBRE el marco delantero (cruce de la X)
    zpv = 0.40
    ypv = yfa + (zpv - 0.028) / (hs + 0.03 - 0.028) * (0.075 - yfa)
    ybot = 0.215
    dvec = Vector((0.0, ypv - ybot, zpv - 0.028)).normalized()
    ytp, ztp = ypv + dvec.y * 0.042, zpv + dvec.z * 0.042                 # punta superior de la pata trasera (bajo el asiento)

    def rear_y(z):
        return ybot + (z - 0.028) / (zpv - 0.028) * (ypv - ybot)
    for sx in (-1, 1):                                                   # patas traseras
        x = sx * wr / 2
        _tube(mb, [(x, ybot, 0.028), (x, ytp, ztp)], R * 0.95, seg=SEG, mat=P)
        _lathe(mb, [(R * 0.93, -0.0006), (R * 0.97, 0.0004), (R * 0.6, 0.0016), (0.0, 0.002)], _frame_z(Vector((x, ytp, ztp)), dvec), P,
               seg=SEG)
    for (zz, xw, rr_, yy) in ((0.1, wr, R * 0.82, None), (0.25, wr, R * 0.7, None), (0.065, wf, R * 0.82, -0.195)):
        y_ = rear_y(zz) if yy is None else yy
        _tube(mb, [(-xw / 2, y_, zz), (xw / 2, y_, zz)], rr_, seg=SEG, mat=P)
    for sx in (-1, 1):                                                   # regatones
        for (xx, yy) in ((sx * wf / 2, yfa), (sx * wr / 2, ybot)):
            _lathe(mb, [(0.0, 0.0), (0.0118, 0.0), (0.0132, 0.0018), (0.0136, 0.006), (0.0128, 0.022), (0.0118, 0.024), (R - 0.0003, 0.024),
                        (R - 0.0003, 0.02)], _T(xx, yy, 0.0), "plastic", seg=SEG)
    # remache de pivote con rondanas (pata trasera adentro, marco afuera)
    for sx in (-1, 1):
        _cyl(mb, (sx * (wr / 2 - R * 0.9), ypv, zpv), (sx * (wf / 2 + R * 1.05), ypv, zpv), 0.0032, "steel", seg=16)
        for (xx, s2) in ((sx * (wf / 2 + R * 1.02), 1), (sx * (wr / 2 - R * 0.92), -1)):
            _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.006, 0.0008), (0.0045, 0.0018), (0.0, 0.0022)],
                   _T(xx, ypv, zpv) @ _Ry(90 * sx * s2), "steel", seg=16)
    # asiento: lámina embutida con faldón y dobladillo
    ws, ds = 0.39, 0.365
    zs_ = hs - 0.003
    Ms = _T(0, -0.035, zs_)

    def LS(ins, z, rcc=0.05):
        return [(x, y, z) for (x, y) in rr_pts(ws - 2 * ins, ds - 2 * ins, max(rcc - ins, 0.004), 6)]
    sl = []
    for k in range(5):                                                   # domo leve del asiento y canto redondeado
        sl.append(LS(0.04 - 0.04 * k / 4 if k < 4 else 0.004, 0.003 + 0.0035 * (1 - (k / 4) ** 2) if k < 4 else 0.0005))
    sl = [LS(0.12, 0.0068), LS(0.06, 0.0055), LS(0.02, 0.0035), LS(0.006, 0.0025)]
    for k in range(1, 5):
        a = PI / 2 * k / 4
        sl.append(LS(0.006 - 0.006 * math.sin(a), 0.0025 - 0.006 + 0.006 * math.cos(a)))
    sl += [LS(0.0, -0.018), LS(0.0003, -0.0195), LS(0.0012, -0.0201), LS(0.0022, -0.0195), LS(0.0026, -0.018), LS(0.0026, -0.012),
           LS(0.0016, -0.0115), LS(0.0016, -0.003), LS(0.004, -0.0006)]
    skin(mb, sl, P, Ms)
    for sx in (-1, 1):                                                   # ménsulas del asiento con remaches a marco y patas
        xm = sx * (ws / 2 - 0.004)
        _channel(mb, (xm, -0.035 - ds / 2 + 0.03, zs_ - 0.0006), (xm, -0.035 + ds / 2 - 0.02, zs_ - 0.0006), w=0.016, hgt=0.02,
                 up=(0, 0, 1))
        yfr_ = yfa + (zs_ - 0.012 - 0.028) / (hs + 0.03 - 0.028) * (0.075 - yfa)
        for (yy, zz, xx) in ((yfr_, zs_ - 0.012, wf / 2 + R * 0.95), (ytp, ztp, ws / 2 + 0.0005)):
            _rivet(mb, _T(sx * xx, yy, zz) @ _Ry(90 * sx), r=0.0045)
    # respaldo: lámina curva con orillas enrolladas, remachada a los postes
    zb0, zb1 = 0.585, 0.715
    prof = []
    for k in range(9):
        z = zb0 + (zb1 - zb0) * k / 8
        f = (z - 0.62) / (ztop - 0.03 - 0.62)
        y = 0.13 + (ytop - 0.13) * min(max(f, 0.0), 1.0) + 0.012 + 0.01 * math.sin(PI * k / 8)
        prof.append((y, z))
    from kit.clinic import shell_strip
    shell_strip(mb, prof, wf - 2 * R - 0.004, 0.0012, P, smooth_n=3, edge_seg=4)
    for (y, z) in (prof[0], prof[-1]):                                   # orillas enrolladas arriba y abajo
        _cyl(mb, (-(wf / 2 - R - 0.0055), y + 0.001, z), ((wf / 2 - R - 0.0055), y + 0.001, z), 0.0032, P, seg=SEG)
    for sx in (-1, 1):
        for k in (1, 7):
            y, z = prof[k]
            _rivet(mb, _T(sx * (wf / 2 - R * 0.2), y - 0.004, z) @ _Ry(90 * sx), r=0.004)
            _board(mb, sx * (wf / 2 - R - 0.004) - 0.006, sx * (wf / 2 - R - 0.004) + 0.006, y - 0.004, y + 0.0035, z - 0.012, z + 0.012, P,
                   r=0.0012, step=1.0)
    return mb


# ======================================================================================================== serie de focos
def _catenary_pts(p0, p1, sag, n=24):
    """Catenaria real (cosh) entre p0 y p1 con flecha `sag` a media luz (se resuelve el parámetro a)."""
    p0, p1 = Vector(p0), Vector(p1)
    S = (p1 - p0).length
    lo, hi = 1e-3, 1e4
    for _ in range(80):
        a = math.sqrt(lo * hi)
        if a * (math.cosh(S / (2 * a)) - 1) > sag:
            lo = a
        else:
            hi = a
    out = []
    for k in range(n + 1):
        t = k / n
        u = (t - 0.5) * S
        drop = sag - a * (math.cosh(u / a) - 1)
        out.append(p0.lerp(p1, t) - Vector((0, 0, drop)))
    return out


def _s_hook(mb, M, rw=0.0018, r_up=0.011, r_lo=0.008, span=0.05, mat="galvanized"):
    """Gancho S de alambre en el plano XZ local: gancho superior abierto hacia abajo-izquierda (su punto interior más alto en el
    origen de M), vástago recto y gancho inferior abierto hacia arriba-derecha cuyo punto interior más bajo queda a -span."""
    Ru, Rl = r_up + rw, r_lo + rw
    cu = Vector((0, 0, rw - Ru))
    cl = Vector((0, 0, -span - rw + Rl))
    pts = [cu + Vector((math.cos(math.radians(a_)), 0, math.sin(math.radians(a_)))) * Ru for a_ in np.linspace(215, -90, 22)]
    pts += [cl + Vector((math.cos(math.radians(a_)), 0, math.sin(math.radians(a_)))) * Rl for a_ in np.linspace(90, 395, 22)]
    with mb.soft():
        _tube(mb, [tuple(M @ p) for p in pts], rw, seg=12, mat=mat)
        for (p, q) in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            d = (p - q).normalized()
            _lathe(mb, [(rw * 0.97, -0.0004), (rw * 0.85, rw * 0.5), (rw * 0.5, rw * 0.85), (0.0, rw)], _frame_z(M @ p, M.to_3x3() @ d),
                   mat, seg=12)


def _bulb(mb, M, seed=0):
    """Portalámparas E26 de hule moldeado (Ø 43 × 53 mm) con anillos de sello, rosca de latón a la vista y foco A19 (Ø 60 ×
    108 mm) de vidrio con vástago y cuatro filamentos LED. M: origen en la boca superior del portalámparas, cuelga a -Z."""
    sp = [(0.0, 0.0), (0.0058, 0.0)]
    for k in range(1, 11):                                               # hombro abombado del portalámparas
        a = PI / 2 * k / 10
        sp.append((0.0058 + 0.015 * math.sin(a), -0.0205 * (1 - math.cos(a)) * 1.0))
    for z in (-0.024, -0.029, -0.034):                                   # anillos de agarre moldeados
        sp += [(0.0211, z + 0.0016), (0.0217, z + 0.0009), (0.022, z + 0.0003), (0.022, z - 0.0003), (0.0217, z - 0.0009),
               (0.0211, z - 0.0016)]
    sp += [(0.0212, -0.046), (0.0222, -0.047), (0.0222, -0.050), (0.0212, -0.051), (0.0208, -0.053), (0.0168, -0.0535), (0.0168, -0.05)]
    _lathe(mb, sp, M, "rubber", seg=32)
    prof = [(0.0128, -0.05)]
    z = -0.0505
    for k in range(5):                                                   # rosca E26 de latón
        prof += [(0.0131, z - 0.0009), (0.0124, z - 0.0018)]
        z -= 0.0018
    prof += [(0.0124, z - 0.001), (0.0135, z - 0.0016)]
    _lathe(mb, prof, M, "brass", seg=32)
    zg = z - 0.0016
    zc = zg - 0.054                                                      # centro del domo (A19: Ø 60 mm, 108 mm de largo)
    g = [(0.0128, zg + 0.0012)]
    for k in range(13):                                                  # cuello en S del casquillo al ecuador
        t = k / 12
        sm = t * t * (3 - 2 * t)
        g.append((0.0135 + 0.0165 * sm ** 0.75, zg - 0.054 * t))
    for k in range(1, 17):                                               # domo
        a = -PI / 2 * k / 16
        g.append((max(0.030 * math.cos(a), 0.0), zc + 0.030 * math.sin(a)))
    g[-1] = (0.0, g[-1][1])
    _lathe(mb, g, M, "glass", seg=48)
    _lathe(mb, [(0.0, zg - 0.0012), (0.0035, zg - 0.0012), (0.0026, zg - 0.02), (0.0018, zg - 0.028), (0.0, zg - 0.029)], M, "glass",
           seg=16)
    with mb.soft():
        for k in range(4):
            a = PI / 2 * k + PI / 4
            p0 = M @ Vector((0.0016 * math.cos(a), 0.0016 * math.sin(a), zg - 0.027))
            p1 = M @ Vector((0.0085 * math.cos(a), 0.0085 * math.sin(a), zg - 0.06))
            _tube(mb, [tuple(p0), tuple(p1)], 0.0007, seg=8, mat="paint_yellow")


def string_lights(points=((-3.0, 0.0, 2.6), (0.0, 0.0, 2.75), (3.0, 0.0, 2.6)), n=6, seed=0, hook_z=None):
    """Serie comercial de intemperie: cable SJTW 14 AWG de dos hilos (Ø 8 mm, 14 lados) en catenaria real entre los puntos
    dados (coordenadas absolutas), n portalámparas colgantes de hule E26 con su sobremoldeado en el cable y bajada de 9 cm,
    foco A19 de vidrio con filamentos LED; en cada punto de amarre un gancho S galvanizado que abraza el cable por abajo y un
    cincho; clavija macho colgando del primer amarre y tapa en el remate. hook_z (opcional): altura del larguero / alambre
    guía del que cuelgan los ganchos (el gancho se alarga hasta ahí); si no, ganchos S de 5 cm."""
    r = rng(seed)
    mb = MB()
    P = [Vector(p) for p in points]
    path = []
    for k in range(len(P) - 1):
        a, b = P[k], P[k + 1]
        Ls = (b - a).length
        seg = _catenary_pts(a, b, 0.03 + 0.012 * Ls, n=max(12, int(Ls / 0.06)))
        path += seg if k == 0 else seg[1:]
    rc = 0.004
    # cola con clavija antes del primer amarre y remate con tapa al final: un solo cable continuo
    p0, pl = P[0], P[-1]
    d0 = (path[1] - path[0]).normalized()
    tail = fillet([tuple(p0 - d0 * 0.05 + Vector((0, 0.006, -0.17))), tuple(p0 - d0 * 0.06 + Vector((0, 0.004, -0.07))),
                   tuple(p0 - d0 * 0.03 + Vector((0, 0, -0.008))), tuple(p0)], 0.03, 6)
    d1 = (path[-1] - path[-2]).normalized()
    full = [Vector(q) for q in tail[:-1]] + path + [pl + d1 * 0.03 + Vector((0, 0, -0.004))]
    _tube(mb, [tuple(p) for p in full], rc, seg=SEG_T, mat="cable")
    _lathe(mb, [(rc * 0.9, -0.004), (0.0062, 0.0), (0.0068, 0.012), (0.0062, 0.02), (0.0, 0.022)],
           _frame_z(full[-1] - d1 * 0.004, d1), "rubber", seg=SEG)
    pe = Vector(tail[0])
    Mp = _frame_z(pe, Vector((0, 0, 1)))
    _lathe(mb, [(rc, -0.002), (0.0065, -0.006), (0.0105, -0.02), (0.012, -0.03), (0.0125, -0.045), (0.0118, -0.047), (0.0, -0.047)], Mp,
           "rubber", seg=SEG)
    for sx in (-1, 1):
        _board(mb, sx * 0.0063 - 0.0008, sx * 0.0063 + 0.0008, -0.0032, 0.0032, -0.064, -0.0465, "brass", r=0.0003, M=Mp, step=1.0)
    # amarres: gancho S y cincho
    for p in P:
        span = max(0.05, (hook_z - p.z)) if hook_z is not None else 0.05
        _s_hook(mb, _T(p.x, p.y, p.z - rc - 0.0018 + span) @ _Rz(90 + _jit(r, 10)), span=span)
        _lathe(mb, [(rc + 0.0001, -0.0024), (rc + 0.0013, -0.0024), (rc + 0.0013, 0.0024), (rc + 0.0001, 0.0024)],
               _frame_z(p + Vector((0.025, 0, -0.0005)), Vector((1, 0, 0))), "plastic", seg=SEG, closed=True)
    # portalámparas
    Q = [Vector(p) for p in path]
    acc = [0.0]
    for i in range(1, len(Q)):
        acc.append(acc[-1] + (Q[i] - Q[i - 1]).length)
    for k in range(n):
        sv = acc[-1] * (k + 0.5) / n
        i = next(j for j in range(1, len(acc)) if acc[j] >= sv)
        t = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-9)
        c = Q[i - 1].lerp(Q[i], t)
        tng = (Q[i] - Q[i - 1]).normalized()
        _lathe(mb, [(rc * 0.98, -0.022), (0.0058, -0.017), (0.0068, -0.006), (0.0068, 0.006), (0.0058, 0.017), (rc * 0.98, 0.022)],
               _frame_z(c, tng), "rubber", seg=SEG)
        drop = 0.09 + _jit(r, 0.008)
        top = c - Vector((0, 0, 0.005))
        _lathe(mb, [(0.0, -0.001), (0.0052, -0.001), (0.0042, -0.012), (0.0032, -0.016)], Matrix.Translation(top), "rubber", seg=16)
        sw = Vector((_jit(r, 0.006), _jit(r, 0.006), 0))
        bend = [top - Vector((0, 0, 0.014)), top - Vector((0, 0, drop * 0.5)) + sw * 0.4, top - Vector((0, 0, drop)) + sw]
        _tube(mb, [tuple(q) for q in bend], 0.0032, seg=SEG_T, mat="cable", caps=True)
        Ms = Matrix.Translation(bend[-1]) @ _Rx(_jit(r, 3)) @ _Ry(_jit(r, 3))
        _bulb(mb, Ms, seed=k)
    return mb


# ======================================================================================================== letrero colgante
def _chain(mb, pts, link=0.022, wire=0.0024, width=0.011, mat="galvanized", seed=0):
    """Cadena de eslabones ovalados alternados a 90° repartidos por longitud de arco a lo largo de la polilínea (alambre de
    sección redonda de 12 lados con sombreado suave)."""
    P = [Vector(p) for p in pts]
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    pitch = link - 2 * wire * 1.05
    nlk = max(int(round(acc[-1] / pitch)), 1)
    step = acc[-1] / nlk

    def at(sv):
        i = next((k for k in range(1, len(acc)) if acc[k] >= sv - 1e-12), len(acc) - 1)
        t = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-9)
        return P[i - 1].lerp(P[i], t)
    r = rng(seed)
    with mb.soft():
        for k in range(nlk):
            a_, b_ = at(k * step), at((k + 1) * step)
            c = (a_ + b_) / 2
            d = (b_ - a_).normalized()
            M, _ = port.frame_on(c - d * link / 2, c + d * link / 2, up=(0, 1, 0) if abs(d.y) < 0.9 else (1, 0, 0))
            M = M @ _T(link / 2, 0, 0) @ _Rx(90 * (k % 2) + _f(r.uniform(-8, 8)))
            hw = width / 2 - wire
            hl = link / 2 - wire
            loop = []
            for q in range(18):
                ang = 2 * PI * q / 18
                cx = math.cos(ang)
                sx_ = math.sin(ang)
                x = (hl - hw) * (1 if cx >= 0 else -1) + hw * cx if abs(cx) > 1e-9 else 0.0
                loop.append(M @ Vector((x, hw * sx_, 0)))
            loop_tube(mb, loop, wire, seg=12, mat=mat, normal=M.to_3x3() @ Vector((0, 0, 1)))


def _screw_eye(mb, M, r_eye=0.009, rw=0.0022, shank=0.03, mat="galvanized"):
    """Armella cerrada: ojo de alambre (plano XZ local) con cuello y vástago roscado que entra en la madera (-Z local)."""
    with mb.soft():
        ring = [M @ Vector((r_eye * math.cos(a), 0, r_eye + rw + r_eye * math.sin(a))) for a in np.linspace(-PI / 2, 1.5 * PI, 25)[:-1]]
        loop_tube(mb, ring, rw, seg=12, mat=mat, normal=M.to_3x3() @ Vector((0, 1, 0)))
    prof = [(0.0, -shank), (rw * 0.6, -shank + 0.002)]
    z = -shank + 0.003
    while z < -0.003:
        prof += [(rw * 1.25, z + 0.0006), (rw * 0.75, z + 0.0016)]
        z += 0.0018
    prof += [(rw, 0.0), (rw * 1.6, 0.0012), (rw * 1.1, 0.003), (rw * 0.9, rw + 0.0005)]
    _lathe(mb, prof, M, mat, seg=12)


def hanging_sign(text="SUPPLY", w=0.9, seed=0):
    """Letrero de tabla pintado a mano: tabla de pino de 1×10" (19 × 220 mm) con veta en relieve (vetas tardías levantadas por
    la intemperie, dos nudos), cantos redondeados y gastados con mellas; letras de esténcil (Saira Stencil) aplicadas a mano
    (cada una con su giro, altura y tamaño un poco distintos), filete pintado alrededor y leyenda chica; dos armellas en el
    canto superior, cadena galvanizada de eslabón ovalado que sube a un gancho S común. Origen: punto de cuelgue (z = 0, la
    cara interior del gancho S, p. ej. sobre el larguero del alero); la tabla cuelga 0,30 m abajo, cara a -Y."""
    r = rng(seed)
    mb = MB()
    hgt, th = 0.22, 0.019
    zb = -0.30 - hgt
    xs = _axis_samples(-w / 2, w / 2, 0.004, 2, 0.02)
    ys = _axis_samples(-th / 2, th / 2, 0.004, 2, 1.0)
    zs = _axis_samples(zb, zb + hgt, 0.004, 2, 0.0035)
    knots = [(_f(r.uniform(-w * 0.35, w * 0.35)), zb + _f(r.uniform(0.04, hgt - 0.04))) for _ in range(2)]
    fr = [(_f(r.uniform(90, 160)), _f(r.uniform(0, 6.28)), _f(r.uniform(0.3, 1.0))) for _ in range(5)]
    nseed = _f(r.uniform(0, 50))

    def disp(Q, N, P):
        D = np.zeros_like(Q)
        face = np.abs(N[:, 1]) > 0.6
        z = Q[:, 2] - zb
        x = Q[:, 0]
        # vetas: frecuencia que varía, ondulando con el largo
        g = np.zeros(len(Q))
        for (f, ph, a) in fr:
            g += a * np.sin(f * (z + 0.004 * np.sin(x * 9.0 + ph)) + ph)
        g = np.clip(g / 2.5, -1, 1)
        g = np.maximum(g, 0.0) ** 2
        for (kx, kz) in knots:
            dk = np.hypot((x - kx) / 0.022, (Q[:, 2] - kz) / 0.014)
            g += 0.8 * np.exp(-dk ** 2) + 0.5 * np.cos(dk * 5.0) * np.exp(-dk ** 2 / 4)
        amp = 0.0005 * g * face
        D[:, 1] += N[:, 1] * amp
        # cantos gastados con mellas
        edge = ~face
        m = 0.0008 * np.clip(_noise2(x * 3.0, Q[:, 2] * 3.0, 6.0, nseed), 0, 1) * edge
        D -= N * m[:, None]
        return D
    _dbox(mb, None, xs, ys, zs, 0.004, "wood", disp=disp)
    # letras a mano: posiciones por el avance real de la fuente, cada letra con su giro, altura y tamaño
    size = hgt * 0.52
    tmp = MB()
    wid = [text_font(tmp, text[:i + 1], size, 0.0005, "paint_od", font="stencil", align="LEFT", res=1) for i in range(len(text))]
    del tmp
    tot = wid[-1] * 1.08
    yfc = -th / 2 - 0.0001
    prev = 0.0
    for i, ch in enumerate(text):
        cw = wid[i] - prev
        cx = prev * 1.08 + cw / 2 - tot / 2
        prev = wid[i]
        if ch == " ":
            continue
        x = cx + _jit(r, 0.003)
        Ml = _T(x, yfc, zb + hgt * 0.36 + _jit(r, 0.004)) @ _Rx(90) @ _Rz(_jit(r, 2.5))
        text_font(mb, ch, size * (1 + _jit(r, 0.035)), 0.0009, "paint_od", Ml, font="stencil", res=3)
    text_font(mb, "AMMO  -  GEAR  -  PARTS", 0.022, 0.0009, "paint_od", _T(_jit(r, 0.004), yfc, zb + hgt * 0.13) @ _Rx(90) @ _Rz(_jit(r, 1.0)),
              font="stencil2", res=2)
    # filete pintado a 14 mm del canto (marco de una pieza)
    from kit.clinic_servicios import rrframe
    m_ = 0.014
    rrframe(mb, _T(0, yfc + 0.0003, zb + hgt / 2) @ _Rx(90), (0.0, 0.0, w - 2 * m_ + 0.005, hgt - 2 * m_ + 0.005, 0.003),
            (0.0, 0.0, w - 2 * m_ - 0.005, hgt - 2 * m_ - 0.005, 0.001), 0.0012, re_o=0.0003, re_i=0.0003, n=2, ne=1, mat="paint_od")
    # armellas, cadena y gancho S
    ze = zb + hgt
    for sx in (-1, 1):
        x = sx * (w / 2 - 0.08)
        _screw_eye(mb, _T(x, 0.0, ze) @ _Rz(90))
        eye_top = Vector((x, 0.0, ze + 2 * 0.009 + 2 * 0.0022))
        top = Vector((sx * 0.0035, 0.0, -0.05 - 0.0028 + 0.0028 + 0.0024 + 0.0005))
        _chain(mb, [eye_top - Vector((0, 0, 0.0035)), top], seed=seed + sx)
    _s_hook(mb, Matrix(), r_up=0.022, r_lo=0.009, span=0.05, rw=0.0028)
    return mb

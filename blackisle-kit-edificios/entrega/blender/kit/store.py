"""kit/store.py — GRA_1_tienda: tienda comunitaria de una granja en la llanura costera seca (6 × 8 m, aplanado amarillo pálido,
guardapolvo azul, piso de barro rojo). Vende medicinas, abarrotes, munición y cerveza; en uso diario, modesta, polvosa.

Mobiliario y mercancía a calidad AAA (regla R-AAA): cada pieza con su construcción real (bastidor y tableros, lámina doblada con
cantos redondeados, malla soldada, bisagras, tornillos, holguras), lo blando subdividido y deformado (bolsas, costales, gasas,
paquetes de papel), y desgaste geométrico (cantos gastados, hundidos de uso, golpes).

Convenciones (las del kit): metros, Z arriba, cada función devuelve un MB.
- Piezas de piso: origen en el piso al centro de la pieza, frente hacia -Y (el lado del cliente en el mostrador).
- Piezas de muro de piso (gabinete, anaqueles, refrigerador): espalda contra el plano del muro y = 0, crecen hacia -Y; origen
  en el piso, centrado en X.
- Piezas colgadas del muro (pizarrón: origen en la cara del muro al centro del canto inferior; letrero OPEN y calendario:
  origen en el clavo / gancho, cuelgan hacia -Z).
- Mercancía de anaquel: unas cuantas mallas héroe (lata, botella, bolsa, rollo...) instanciadas con posición, giro y escala
  con jitter por semilla (mismo seed, mismo resultado).
Textos solo en inglés, genéricos, sin marcas ni logotipos; primeros auxilios con cruz VERDE.
Materiales: wood, wood_dark, wood_grey, wood_varnish, steel, aluminium, metal_rust, rubber, cable, plastic, plastic_blue, enamel,
glass, paper, paint_green, paint_yellow, sign_red, sign_white, sign_blue, sign_green, linen, hay, burlap, cardboard, amber.
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
from mathutils import Matrix, Vector

from kit import port
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rbox, rng, rr_profile, rtube, zloft  # noqa: F401
from kit.clinic_equipo import angle_l, loft_rings, sweep_frame, weld  # noqa: F401
from kit.clinic_equipo import chain as echain
from kit.clinic_equipo import rtube_lo as _rtube_lo0
from kit.clinic_equipo import screw_lo as _screw_lo0
from kit.clinic_equipo import text as etext
from kit.clinic_servicios import foot_leveler, hexnut, holed, louver_grille, skin  # noqa: F401
from kit.clinic_servicios import hose as _hose0
# redondos sin facetas (segunda pasada R-AAA): los envoltorios de kit.farm dan a cada redondo los lados que pide su radio y a
# cada canto redondeado pasos de <= 22,5° (ver kit.farm.nsides / qsegs)
from kit.farm import cyl, nsides, qsegs, revolve, rr_pts, rrframe, slab, tube  # noqa: F401
from kit.farm import lathe as slathe
from kit.farm import rope_tube
from kit.clinic_equipo import revolve as _revolve_raw


def rtube_lo(mb, p0, p1, w, h, mat, up=(0, 0, 1), r=0.004, n=2, caps=True):
    """PTR de esquinas redondeadas con pasos de <= 22,5° (suave a cualquier distancia)."""
    return _rtube_lo0(mb, p0, p1, w, h, mat, up=up, r=r, n=max(n, qsegs(r)), caps=caps)


def screw_lo(mb, M, d=0.007, mat="steel", seg=6):
    """Cabeza de tornillo redonda (14+ lados)."""
    return _screw_lo0(mb, M, d=d, mat=mat, seg=max(seg, 14))


def hose(mb, pts, r, bend=0.03, mat="rubber", seg=10, pitch=None, depth=0.12, nseg=8):
    """Manguera / cable / varilla doblada con los lados que pide su radio (Ø <= 6 mm: 12 lados, sombreado continuo)."""
    if r <= 0.003:
        with mb.soft():
            return _hose0(mb, pts, r, bend=bend, mat=mat, seg=max(seg, 12), pitch=pitch, depth=depth, nseg=max(nseg, 6))
    return _hose0(mb, pts, r, bend=bend, mat=mat, seg=max(seg, nsides(r)), pitch=pitch, depth=depth, nseg=max(nseg, 6))


# ======================================================================================================== utilidades
def _f(x):
    return float(x)


def board(mb, x0, x1, y0, y1, z0, z1, mat, rc=0.002, re=0.002, nc=1, ne=1, re0=None, M=None):
    """Tabla / lámina de cantos redondeados (slab) dada por su caja; M opcional la coloca."""
    Mb = _T((x0 + x1) / 2, (y0 + y1) / 2, z0)
    slab(mb, (M @ Mb) if M is not None else Mb, x1 - x0, y1 - y0, z1 - z0, rc=rc, re=re, mat=mat, nc=nc, ne=ne, re0=re0)


def nail(mb, M, r=0.0032, mat="metal_rust", seg=6):
    """Cabeza de clavo (abombada, 0,8 mm sobre la madera; hundida 0,3 mm)."""
    revolve(mb, [(r, -0.0003), (r * 0.9, 0.0004), (r * 0.5, 0.0008), (0.0, 0.0009)], mat, seg=seg, M=M, caps=False)


def lofts(mb, stations, mat, M=None, cap0=True, cap1=True):
    """Sólido por estaciones a lo largo de X: [(x, [(y, z), ...])] con igual número de puntos por perfil."""
    loops = [[(x, y, z) for (y, z) in prof] for (x, prof) in stations]
    return skin(mb, loops, mat, M, cap0=cap0, cap1=cap1)


def _inset(prof, d):
    """Contrae un perfil cerrado (y, z) hacia su centro `d` en cada eje (chaflán de extremos de tabla)."""
    cy = sum(p[0] for p in prof) / len(prof)
    cz = sum(p[1] for p in prof) / len(prof)
    return [(y - math.copysign(min(d, abs(y - cy) * 0.5), y - cy), z - math.copysign(min(d, abs(z - cz) * 0.5), z - cz))
            for (y, z) in prof]


def _plank_prof(y0, y1, z0, z1, rf, rb, rbot=0.0015, n=3, k=3, top=None, nb=1):
    """Perfil (y, z) de tabla acostada: cantos superiores de radio rf (frente, y0) y rb (atrás, y1), inferiores rbot (nb
    segmentos: abajo casi no se ve); k puntos intermedios en la cara superior (hundidos de uso). top(y) -> desplazamiento z."""
    top = top or (lambda y: 0.0)
    pts = []
    for j in range(nb + 1):                                       # canto inferior frontal
        a = PI + PI / 2 * j / nb
        pts.append((y0 + rbot + rbot * math.cos(a), z0 + rbot + rbot * math.sin(a)))
    for j in range(nb + 1):                                       # canto inferior trasero
        a = 1.5 * PI + PI / 2 * j / nb
        pts.append((y1 - rbot + rbot * math.cos(a), z0 + rbot + rbot * math.sin(a)))
    for j in range(n + 1):                                        # canto superior trasero
        a = PI / 2 * j / n
        yy = y1 - rb + rb * math.cos(a)
        pts.append((yy, z1 - rb + rb * math.sin(a) + top(yy) * (j / n)))
    for i in range(1, k + 1):                                     # cara superior
        yy = y1 - rb - (y1 - y0 - rf - rb) * i / (k + 1)
        pts.append((yy, z1 + top(yy)))
    for j in range(n + 1):                                        # canto superior frontal
        a = PI / 2 + PI / 2 * j / n
        yy = y0 + rf + rf * math.cos(a)
        pts.append((yy, z1 - rf + rf * math.sin(a) + top(yy) * (1 - j / n)))
    return pts


def plank_x(mb, x0, x1, y0, y1, z0, z1, mat, rf=0.003, rb=0.003, nst=12, wear=None, end=0.0025, n=3, k=3, M=None, rfx=None,
            extra=()):
    """Tabla a lo largo de X con extremos achaflanados; wear(x, y) -> hundido (m, positivo hacia abajo) de la cara superior;
    rfx(x) -> radio del canto frontal a lo largo de la tabla (canto gastado irregular); extra: estaciones adicionales
    (alrededor de golpes)."""
    xs = [x0 + end + (x1 - x0 - 2 * end) * i / (nst - 1) for i in range(nst)]
    xs = sorted(set([round(x, 5) for x in xs] + [round(x, 5) for x in extra if x0 + end + 0.004 < x < x1 - end - 0.004]))
    xs = [x0] + xs + [x1]
    st = []
    for i, x in enumerate(xs):
        r_f = rfx(x) if rfx else rf
        prof = _plank_prof(y0, y1, z0, z1, r_f, rb, n=n, k=k, top=(lambda y, x=x: -wear(x, y)) if wear else None)
        if i in (0, len(xs) - 1):
            prof = _inset(prof, end)
        st.append((x, prof))
    return lofts(mb, st, mat, M)


def wire(mb, p0, p1, r, mat="steel", seg=6):
    cyl(mb, p0, p1, r, seg=seg, mat=mat)


def _jit(r, a):
    return _f(r.uniform(-a, a))


# ======================================================================================================== mostrador
def shop_counter(L=3.0, d=0.6, h=0.95, seed=0, mesh=True):
    """Mostrador de madera gastado de tienda de pueblo. Frente del cliente (-Y) de bastidor (postes de esquina, largueros y
    montantes) con tableros de duela vertical rehundidos y zoclo remetido; cubierta gruesa de 4 tablones con canto frontal
    boleado y gastado (radio irregular), hundidos de uso frente al cliente, juntas entre tablones y clavos; costados de bastidor
    y duela; lado del dependiente (+Y) abierto: postes traseros, faldón, divisiones, piso y entrepaño sobre listones.
    mesh=True: mampara de seguridad de PTR 25 × 25 con malla electrosoldada sobre la mitad izquierda, con ventanilla de paso
    al ras de la cubierta y escuadras atornilladas."""
    r = rng(seed)
    mb = MB()
    tt = 0.045                                                   # espesor de cubierta
    zt0 = h - tt
    yF = -d / 2 + 0.035                                          # cara del bastidor frontal
    yB = d / 2 - 0.025                                           # cara trasera de los postes traseros
    x0, x1 = -L / 2 + 0.012, L / 2 - 0.012
    # ---------------- cubierta: 4 tablones con hundido de uso al frente y canto frontal gastado
    xc_use = [_f(r.uniform(-0.1, 0.5) * L / 3), _f(r.uniform(0.15, 0.45) * L)]
    dents = [(_f(r.uniform(-L / 2 + 0.1, L / 2 - 0.1)), _f(r.uniform(0.012, 0.03)), _f(r.uniform(0.003, 0.006))) for _ in range(7)]

    def wear(x, y):
        fy = max(0.0, 1.0 - (y + d / 2) / 0.32)                  # más gastado hacia el cliente
        w = 0.0
        for xc in xc_use:
            w += 0.0032 * math.exp(-((x - xc) / 0.35) ** 2) * fy
        w += 0.0004 * math.sin(7.3 * x + 1.7) * math.sin(11.0 * y + 0.4)
        return w

    def rfx(x):
        rr = 0.012 + 0.005 * math.sin(2.1 * x + 0.6) + 0.003 * math.sin(5.7 * x + 2.0)
        for (xd, wd, dd) in dents:
            rr += dd * math.exp(-((x - xd) / wd) ** 2)
        for xc in xc_use:
            rr += 0.004 * math.exp(-((x - xc) / 0.3) ** 2)
        return rr

    ys = [-d / 2, -d / 2 + 0.152, -d / 2 + 0.302, -d / 2 + 0.451, d / 2]
    for i in range(4):
        ya, yb = ys[i] + (0.0006 if i else 0.0), ys[i + 1] - (0.0006 if i < 3 else 0.0)
        dz = _jit(r, 0.0008)                                      # tablones desparejos: la junta se lee
        if i == 0:
            dz0 = dz
        ex = [xd + o * wd for (xd, wd, _) in dents for o in (-1.2, -0.5, 0.0, 0.5, 1.2)] if i == 0 else ()
        plank_x(mb, -L / 2, L / 2, ya, yb, zt0, h + dz, "wood", rf=0.0025, rb=0.0025 if i < 3 else 0.006,
                nst=int(L / 0.12) if i == 0 else int(L / 0.2), wear=wear, k=2 if i else 3, rfx=rfx if i == 0 else None, extra=ex)
    xp = _f(r.uniform(0.25, 0.4)) * L                            # parche de lámina clavado sobre el canto astillado
    _tin_patch(mb, xp, -d / 2, lambda x, y: h + dz0 - wear(x, y), rfx, 0.14, r)
    for i in range(int(L / 0.42)):                              # clavos de la cubierta sobre largueros
        x = -L / 2 + 0.2 + i * (L - 0.4) / max(int(L / 0.42) - 1, 1)
        for yy in (yF + 0.03, yB - 0.03):
            nail(mb, _T(x + _jit(r, 0.01), yy + _jit(r, 0.004), h - wear(x, yy) + 0.0) @ _Rz(_f(r.uniform(0, 60))), r=0.0035)
    # ---------------- bastidor frontal
    npan = max(2, int(round(L / 0.75)))
    sw = 0.075
    xs_st = [x0 + sw / 2 + i * (x1 - x0 - sw) / npan for i in range(npan + 1)]
    zr0, zr1 = 0.095, 0.17                                       # larguero inferior
    zq0, zq1 = zt0 - 0.085, zt0                                  # larguero superior
    kick = [(_f(r.uniform(-L / 2 + 0.2, L / 2 - 0.2)), _f(r.uniform(0.02, 0.06)), _f(r.uniform(0.003, 0.007))) for _ in range(5)]

    def rkick(x):                                                # canto del larguero inferior pateado
        rr = 0.004 + 0.0025 * math.sin(3.3 * x + 0.2)
        for (xd, wd, dd) in kick:
            rr += dd * math.exp(-((x - xd) / wd) ** 2)
        return max(rr, 0.002)

    for i, x in enumerate(xs_st):
        if i in (0, npan):                                       # postes de esquina hasta el piso, cantos gastados
            sx = x0 if i == 0 else x1 - sw
            board(mb, sx, sx + sw, yF, yF + sw, 0.0, zt0 - 0.0015, "wood_dark", rc=0.008, re=0.003, nc=2)
        else:                                                    # montantes: del larguero inferior a la cubierta
            board(mb, x - sw / 2 + _jit(r, 0.002), x + sw / 2 + _jit(r, 0.002), yF + _jit(r, 0.001) + 0.001, yF + 0.026, zr0,
                  zt0 - 0.0015, "wood_dark", rc=0.004, re=0.002)
    for i in range(npan):
        xa, xb = xs_st[i] + sw / 2 + 0.0008, xs_st[i + 1] - sw / 2 - 0.0008
        ex = [xd + o * wd for (xd, wd, _) in kick for o in (-1.0, 0.0, 1.0)]
        plank_x(mb, xa, xb, yF + 0.002, yF + 0.025, zr0, zr1, "wood_dark", rf=0.004, rb=0.002, nst=8, n=3, k=0, rfx=rkick,
                extra=ex, end=0.0015)                            # larguero inferior
        board(mb, xa, xb, yF + 0.002, yF + 0.025, zq0, zq1 - 0.002, "wood_dark", rc=0.003, re=0.003, nc=2)  # larguero superior
        # duela vertical rehundida 12 mm (entra 8 mm en el bastidor), anchos y holguras desparejos, una tabla rajada
        xa2, xb2 = xa - 0.008, xb + 0.008
        nb = max(3, int(round((xb2 - xa2) / 0.09)))
        cuts = [xa2] + sorted(xa2 + (xb2 - xa2) * (k + _f(r.uniform(-0.12, 0.12))) / nb for k in range(1, nb)) + [xb2]
        crack = int(r.integers(0, nb)) if r.random() < 0.6 else -1
        for k in range(nb):
            g = _f(r.uniform(0.0003, 0.0012))
            bx0, bx1 = cuts[k] + g, cuts[k + 1] - g
            yo = _jit(r, 0.0012)
            Mt = _T((bx0 + bx1) / 2, 0, 0) @ _Rz(_jit(r, 0.35)) @ _T(-(bx0 + bx1) / 2, 0, 0)
            if k == crack:                                       # raja a lo largo de la tabla
                xm = bx0 + (bx1 - bx0) * _f(r.uniform(0.35, 0.65))
                board(mb, bx0, xm - 0.0012, yF + 0.012 + yo, yF + 0.028 + yo, zr1 - 0.008, zq0 + 0.008, "wood_dark", rc=0.0025,
                      re=0.001, M=Mt)
                board(mb, xm + 0.0012, bx1, yF + 0.0125 + yo, yF + 0.028 + yo, zr1 - 0.008, zq0 + 0.008, "wood_dark",
                      rc=0.0025, re=0.001, M=Mt)
            else:
                board(mb, bx0, bx1, yF + 0.012 + yo, yF + 0.028 + yo, zr1 - 0.008, zq0 + 0.008, "wood_dark", rc=0.0035, re=0.001,
                      M=Mt)
    # zoclo remetido entre postes
    board(mb, x0 + sw, x1 - sw, yF + 0.03, yF + 0.05, 0.0, zr0 + 0.01, "wood_dark", rc=0.002, re=0.004, nc=2)
    for x in xs_st[1:-1]:
        nail(mb, _T(x, yF + 0.03, 0.05) @ _Rx(90), r=0.003)
    # ---------------- costados (bastidor + duela) y postes traseros
    for sgn in (-1, 1):
        xo = sgn * (L / 2 - 0.012)                               # cara exterior del costado
        xi = xo - sgn * 0.026
        # poste trasero de esquina
        bx = (x0, x0 + 0.06) if sgn < 0 else (x1 - 0.06, x1)
        board(mb, bx[0], bx[1], yB - 0.06, yB, 0.0, zt0, "wood_dark", rc=0.005, re=0.003, nc=2)
        ya, yb = yF + sw - 0.004, yB - 0.06 + 0.004
        lo, hi = min(xo, xi), max(xo, xi)
        board(mb, lo + 0.0005, hi, ya, yb, zr0, zr1, "wood_dark", rc=0.003, re=0.004, nc=2)
        board(mb, lo + 0.0005, hi, ya, yb, zq0, zq1 - 0.002, "wood_dark", rc=0.003, re=0.003, nc=2)
        nb = max(3, int(round((yb - ya) / 0.09)))
        bw = (yb - ya + 0.016) / nb
        for k in range(nb):
            b0 = ya - 0.008 + k * bw + 0.0004
            b1 = ya - 0.008 + (k + 1) * bw - 0.0004
            xo2 = xo - sgn * 0.012 + _jit(r, 0.0008)
            board(mb, min(xo2, xo2 - sgn * 0.016), max(xo2, xo2 - sgn * 0.016), b0, b1, zr1 - 0.008, zq0 + 0.008, "wood_dark",
                  rc=0.0035, re=0.001)
        board(mb, min(xo - sgn * 0.03, xo - sgn * 0.05), max(xo - sgn * 0.03, xo - sgn * 0.05), yF + sw, yB - 0.06, 0.0, zr0 + 0.01,
              "wood_dark", rc=0.002, re=0.004, nc=2)
    # ---------------- lado del dependiente: postes, faldón, piso, divisiones y entrepaño
    for x in xs_st[1:-1]:
        board(mb, x - 0.03, x + 0.03, yB - 0.06, yB, 0.0, zt0, "wood_dark", rc=0.005, re=0.003, nc=2)
    board(mb, x0 + 0.06, x1 - 0.06, yB - 0.024, yB - 0.002, zt0 - 0.09, zt0, "wood_dark", rc=0.003, re=0.003, nc=2)     # faldón
    yi0 = yF + 0.028                                             # cara interior de la duela frontal
    zb0 = zr0 + 0.012                                            # piso interior
    board(mb, x0 + 0.06, x1 - 0.06, yB - 0.024, yB - 0.002, 0.03, zb0 + 0.019, "wood_dark", rc=0.003, re=0.003, nc=2)   # zoclo trasero
    board(mb, x0 + sw, x1 - sw, yF + 0.051, yF + 0.073, zb0 - 0.045, zb0, "wood_grey", rc=0.002, re=0.002)             # durmiente
    for k, (xa, xb) in enumerate(zip(xs_st[:-1], xs_st[1:])):
        xa_ = xa + (sw / 2 if k == 0 else 0.03) + 0.003
        xb_ = xb - (sw / 2 if k == npan - 1 else 0.03) - 0.003
        nbd = 3
        for j in range(nbd):                                     # piso interior: tablas a lo largo de Y
            ya = yi0 + 0.002 + j * (yB - 0.025 - yi0) / nbd
            yb = yi0 + (j + 1) * (yB - 0.025 - yi0) / nbd
            board(mb, xa_, xb_, ya, yb - 0.0008, zb0, zb0 + 0.019, "wood_grey", rc=0.002, re=0.0015)
        zs_ = 0.47 + _jit(r, 0.01)
        for (cx0, cx1) in ((xa_, xa_ + 0.022), (xb_ - 0.022, xb_)):          # listones del entrepaño
            board(mb, cx0, cx1, yi0 + 0.01, yB - 0.07, zs_ - 0.03, zs_, "wood_grey", rc=0.002, re=0.002)
        for j in range(3):                                       # entrepaño de 3 tablas, sueltas sobre los listones
            ya = yi0 + 0.004 + j * (yB - 0.066 - yi0) / 3
            yb = yi0 + (j + 1) * (yB - 0.066 - yi0) / 3 - 0.002
            board(mb, xa_ + 0.0005, xb_ - 0.0005, ya, yb, zs_, zs_ + 0.019 + _jit(r, 0.0006), "wood_grey", rc=0.002, re=0.0015)
            for xn in (xa_ + 0.011, xb_ - 0.011):
                nail(mb, _T(xn, (ya + yb) / 2, zs_ + 0.019), r=0.0028)
    for x in xs_st[1:-1]:
        board(mb, x - 0.011, x + 0.011, yi0 + 0.001, yB - 0.061, zb0 + 0.019, zt0 - 0.001, "wood_grey", rc=0.002, re=0.002)
    # travesaños bajo la cubierta (de frente a fondo, sobre postes)
    for x in xs_st:
        xx = min(max(x, x0 + 0.04), x1 - 0.04)
        board(mb, xx - 0.02, xx + 0.02, yF + 0.026, yB - 0.06, zt0 - 0.06, zt0 - 0.0005, "wood_dark", rc=0.002, re=0.002)
    # ---------------- mampara de malla electrosoldada con ventanilla
    if mesh:
        _mesh_partition(mb, -L / 2 + 0.09, -0.03, -0.17, h, r)
    return mb


def _tin_patch(mb, x, y0, ztop, rfx, w, r):
    """Lámina de bote (1,2 mm) doblada sobre el canto frontal gastado de la cubierta (remiendo), clavada arriba y al frente;
    sigue el radio real del canto (rfx) y la cara superior gastada (ztop(x, y))."""
    t = 0.0012
    st = []
    for k in range(7):
        xx = x - w / 2 + w * k / 6
        rf = rfx(xx)
        z1 = ztop(xx, y0 + rf)
        dz = 0.0008 * math.sin(k * 1.7) + 0.0008                 # lámina abollada (siempre por fuera)
        po = [(y0 - t - dz, z1 - 0.05), (y0 - t - dz, z1 - rf)]
        po += [(y0 + rf - (rf + t + dz) * math.cos(a), z1 - rf + (rf + t + dz) * math.sin(a)) for a in (0.4, 0.8, 1.2)]
        po += [(y0 + rf, z1 + t + dz), (y0 + 0.06, ztop(xx, y0 + 0.06) + t + 0.0004)]
        pi = [(y0 + 0.06, ztop(xx, y0 + 0.06) - 0.0003), (y0 + rf, z1 - 0.0003)]
        pi += [(y0 + rf - (rf - 0.0003) * math.cos(a), z1 - rf + (rf - 0.0003) * math.sin(a)) for a in (1.2, 0.8, 0.4)]
        pi += [(y0 + 0.0003, z1 - rf), (y0 + 0.0003, z1 - 0.05)]
        st.append((xx, po + pi))
    lofts(mb, st, "metal_rust")
    for k in range(4):
        xx = x - w / 2 + 0.015 + (w - 0.03) * k / 3
        nail(mb, _T(xx, y0 + 0.042, ztop(xx, y0 + 0.042) + t + 0.0004), r=0.003)
        nail(mb, _T(xx + 0.01, y0 - t - 0.0008, ztop(xx, y0 + 0.02) - 0.034) @ _Rx(90), r=0.003)


def _mesh_partition(mb, xa, xb, y, z0, r, H=0.78, t=0.025, pitch=0.05, slot=(0.34, 0.13)):
    """Mampara sobre la cubierta (z0): marco de PTR t × t, malla de alambre Ø 3 mm (verticales al frente, horizontales atrás,
    soldadas en cada cruce por contacto), ventanilla de paso al ras de la cubierta con dintel y postes, escuadras con pijas."""
    ht = t / 2
    zc0, zc1 = z0 + ht, z0 + H - ht
    xm = xa + (xb - xa) * 0.62                                   # centro de la ventanilla
    sw, sh = slot
    xs0, xs1 = xm - sw / 2 - ht, xm + sw / 2 + ht
    rr = 0.0025
    # marco: postes y travesaños (PTR de esquinas redondeadas, soldados a tope)
    rtube_lo(mb, (xa, y, z0), (xa, y, z0 + H), t, t, "steel", up=(1, 0, 0), r=rr, n=2)
    rtube_lo(mb, (xb, y, z0), (xb, y, z0 + H), t, t, "steel", up=(1, 0, 0), r=rr, n=2)
    rtube_lo(mb, (xa + ht, y, zc1), (xb - ht, y, zc1), t, t, "steel", up=(0, 0, 1), r=rr, n=2)
    rtube_lo(mb, (xa + ht, y, zc0), (xs0 - ht, y, zc0), t, t, "steel", up=(0, 0, 1), r=rr, n=2)
    rtube_lo(mb, (xs1 + ht, y, zc0), (xb - ht, y, zc0), t, t, "steel", up=(0, 0, 1), r=rr, n=2)
    zh = z0 + sh + ht                                            # dintel de la ventanilla
    for xx in (xs0, xs1):
        rtube_lo(mb, (xx, y, z0), (xx, y, zh + ht), t, t, "steel", up=(1, 0, 0), r=rr, n=2)
    rtube_lo(mb, (xs0 + ht, y, zh), (xs1 - ht, y, zh), t, t, "steel", up=(0, 0, 1), r=rr, n=2)
    zm = z0 + H * 0.55                                           # travesaño intermedio
    rtube_lo(mb, (xa + ht, y, zm), (xb - ht, y, zm), t, t * 0.6, "steel", up=(0, 0, 1), r=rr * 0.8, n=2)
    # escuadras de piso (ángulo 40 × 50 × 3, una pieza) a los dos lados de cada poste, con pija a la cubierta
    for xx in (xa, xb, xs0, xs1):
        for s in (-1, 1):
            yw = y + s * ht                                      # cara del poste
            angle_l(mb, (xx - 0.02, yw, z0), (xx + 0.02, yw, z0), 0.045, 0.003, up=(0, 0, 1), s=-s, mat="steel", rf=0.002)
            screw_lo(mb, _T(xx, yw + s * 0.027, z0 + 0.003), d=0.008, seg=6)
    # malla: verticales al frente (y - ht + r_w) y horizontales detrás, de cara interior a cara interior del marco (+1 mm)
    rw = 0.0015
    yv, yh = y - rw, y + rw
    nx = int((xb - xa - t) / pitch)
    for i in range(1, nx + 1):
        x = xa + ht + (xb - xa - t) * i / (nx + 1)
        if abs(x - xs0) < ht + rw or abs(x - xs1) < ht + rw:
            continue
        lo = (zh + ht - 0.001) if xs0 < x < xs1 else (zc0 + ht - 0.001)
        if abs(x - xa) < 0.01 or abs(x - xb) < 0.01:
            continue
        for (za, zb_) in ((lo, zm - t * 0.3 + 0.001), (zm + t * 0.3 - 0.001, zc1 - ht + 0.001)):
            if zb_ - za > 0.01:
                wire(mb, (x, yv, za), (x, yv, zb_), rw, seg=4)
    for (za, zb_) in ((zc0 + ht, zm - t * 0.3), (zm + t * 0.3, zc1 - ht)):
        nz = max(1, int((zb_ - za) / pitch))
        for j in range(1, nz + 1):
            z = za + (zb_ - za) * j / (nz + 1)
            if z < zh + ht + 0.004:                              # junto a la ventanilla: dos tramos
                for (p, q) in ((xa + ht - 0.001, xs0 - ht + 0.001), (xs1 + ht - 0.001, xb - ht + 0.001)):
                    wire(mb, (p, yh, z), (q, yh, z), rw, seg=4)
            else:
                wire(mb, (xa + ht - 0.001, yh, z), (xb - ht + 0.001, yh, z), rw, seg=4)


# ======================================================================================================== anaquel sin tornillos
def slotted_flange(mb, M, leg, t, z0, z1, slots=True, pitch=0.0508, sl=0.026, sw=0.006, off=0.04):
    """Ala de ángulo ranurado en el plano XZ local: x de 0 a leg, espesor y de 0 a t, de z0 a z1, con ranuras pasantes
    (sw × sl, a paso `pitch`) centradas en el ala. Malla sin juntas en T (columnas subdivididas en cada borde de ranura)."""
    xa, xb = leg / 2 - sw / 2, leg / 2 + sw / 2
    xs = [0.0, xa, xb, leg]
    zs = [z0]
    holes = []
    if slots:
        z = z0 + off
        while z + sl < z1 - off:
            zs += [z, z + sl]
            holes.append((z, z + sl))
            z += pitch
    zs.append(z1)
    V = {}

    def v(i, j, s):
        k = (i, j, s)
        if k not in V:
            V[k] = mb.bm.verts.new(M @ Vector((xs[i], s * t, zs[j])))
        return V[k]

    def hole(j):
        a = (zs[j] + zs[j + 1]) / 2
        return any(h0 < a < h1 for (h0, h1) in holes)
    for j in range(len(zs) - 1):
        for i in range(3):
            if i == 1 and hole(j):
                continue
            mb.face([v(i, j, 0), v(i + 1, j, 0), v(i + 1, j + 1, 0), v(i, j + 1, 0)], "steel")
            mb.face([v(i, j, 1), v(i, j + 1, 1), v(i + 1, j + 1, 1), v(i + 1, j, 1)], "steel")
        mb.face([v(0, j, 0), v(0, j + 1, 0), v(0, j + 1, 1), v(0, j, 1)], "steel")          # cantos largos
        mb.face([v(3, j, 0), v(3, j, 1), v(3, j + 1, 1), v(3, j + 1, 0)], "steel")
        if hole(j):                                                                           # paredes laterales de la ranura
            mb.face([v(1, j, 0), v(1, j, 1), v(1, j + 1, 1), v(1, j + 1, 0)], "steel")
            mb.face([v(2, j, 0), v(2, j + 1, 0), v(2, j + 1, 1), v(2, j, 1)], "steel")
    for (h0, h1) in holes:                                                                    # extremos de la ranura
        j0, j1 = zs.index(h0), zs.index(h1)
        mb.face([v(1, j0, 0), v(2, j0, 0), v(2, j0, 1), v(1, j0, 1)], "steel")
        mb.face([v(1, j1, 0), v(1, j1, 1), v(2, j1, 1), v(2, j1, 0)], "steel")
    n = len(zs) - 1
    for (j, rev) in ((0, False), (n, True)):                                                  # tapas
        q = [v(i, j, 0) for i in range(4)] + [v(i, j, 1) for i in (3, 2, 1, 0)]
        mb.face(list(reversed(q)) if not rev else q, "steel")
    return [z for (z, _) in holes]


def boltless_post(mb, x, y, h, sx, sy, leg=0.038, t=0.0018, slots_front=True, slots_side=False, wall=False):
    """Poste de ángulo 38 × 38 × 1,8 con talón en (x, y); alas hacia sx·X (ala frontal, plano XZ) y sy·Y (ala lateral).
    Devuelve las alturas de las ranuras del ala frontal. Regatón de plástico en L abajo."""
    Mf = _T(x, y, 0) @ Matrix.Diagonal((sx, sy, 1.0, 1.0))
    zs = slotted_flange(mb, Mf, leg, t, 0.012, h, slots=slots_front)
    Ms = _T(x, y, 0) @ Matrix(((0, sx, 0, 0), (sy, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))  # ala lateral: x local -> ±Y
    slotted_flange(mb, Ms @ _T(t, 0, 0), leg - t, t, 0.012, h, slots=slots_side)
    # regatón de plástico en L: funda que abraza el pie del ángulo + base (del lado del muro, al ras)
    Mr = _T(x, y, 0) @ Matrix.Diagonal((sx, sy, 1.0, 1.0))
    m = 0.003
    mw = 0.0015 if wall else m
    for (e, z0_, z1_) in ((0.0025, 0.0, 0.006), (0.0, 0.006, 0.034)):
        out = [(-m - e, -mw), (leg + m + e, -mw), (leg + m + e, t + m + e), (t + m + e, t + m + e), (t + m + e, leg + m + e),
               (-m - e, leg + m + e)]
        if sx * sy < 0:
            out = out[::-1]
        mb.plate(out, z1_ - z0_, "plastic", m=Mr @ _T(0, 0, z0_))
    return zs


def _beam(mb, p0, p1, inward, t=0.0016, hgt=0.038, ledge=0.02):
    """Larguero de remache: alma vertical de `hgt` + ceja horizontal de `ledge` hacia el vector `inward`, 20 mm bajo el borde
    superior (ahí apoya el entrepaño). p0, p1 = borde superior de la cara exterior del alma."""
    T = (Vector(p1) - Vector(p0)).normalized()
    B = T.cross(Vector((0, 0, 1)))
    s = 1.0 if B.dot(Vector(inward)) > 0 else -1.0
    prof = [(0.0, 0.0), (0.0, -hgt), (t, -hgt), (t, -0.02 - t), (ledge, -0.02 - t), (ledge + 0.0012, -0.02 - t / 2), (ledge, -0.02),
            (t, -0.02), (t, -0.0015), (t * 0.4, 0.0)]
    sweep_frame(mb, [(s * a, b) for (a, b) in prof], [p0, p1], "steel", up=(0, 0, 1))


def _rivet(mb, M, r=0.0045):
    revolve(mb, [(r, -0.0003), (r * 0.85, 0.0012), (r * 0.45, 0.0021), (0.0, 0.0023)], "steel", seg=8, M=M, caps=False)


def shelving_frame(mb, w, d, h, levels, slots_front=True):
    """Anaquel de remache: 4 postes de ángulo ranurado (ranuras en el ala frontal de los postes delanteros), largueros
    perimetrales en cada nivel (remaches vistos en las ranuras), entrepaños de lámina con canal rigidizador, regatones y
    escuadra antivuelco al muro. Espalda en y = 0, frente en y = -d. levels: alturas del borde superior de los largueros."""
    t = 0.0018
    tb = 0.0016
    yw = -0.0015                                                # holgura al muro de los postes traseros
    for (x, y, sx, sy) in ((-w / 2, -d, 1, 1), (w / 2, -d, -1, 1), (-w / 2, yw, 1, -1), (w / 2, yw, -1, -1)):
        boltless_post(mb, x, y, h, sx, sy, t=t, slots_front=(slots_front and y < -0.01), wall=(y > -0.01))
    for z in levels:
        yf, yb = -d + t, yw - t
        xl, xr = -w / 2 + t + 0.0005, w / 2 - t - 0.0005
        _beam(mb, (xl, yf, z), (xr, yf, z), (0, 1, 0), t=tb)
        _beam(mb, (xl, yb, z), (xr, yb, z), (0, -1, 0), t=tb)
        for xs in (-1, 1):
            xw = xs * (w / 2 - t)
            _beam(mb, (xw, yf + 0.021, z - 0.0003), (xw, yb - 0.021, z - 0.0003), (-xs, 0, 0), t=tb)
        # entrepaño de lámina (pestañas de 20 mm ocultas tras los largueros) y canal rigidizador
        board(mb, xl + tb + 0.0008, xr - tb - 0.0008, yf + tb + 0.0008, yb - tb - 0.0008, z - 0.02, z - 0.0006, "steel",
              rc=0.002, re=0.0012, ne=1)
        hat = [(-0.02, 0.0), (-0.012, 0.0), (-0.009, -0.014), (0.009, -0.014), (0.012, 0.0), (0.02, 0.0), (0.02, -0.0012),
               (0.0128, -0.0012), (0.0098, -0.0152), (-0.0098, -0.0152), (-0.0128, -0.0012), (-0.02, -0.0012)]
        sweep_frame(mb, hat, [(xl + 0.025, -d / 2, z - 0.02), (xr - 0.025, -d / 2, z - 0.02)], "steel", up=(0, 0, 1))
        for xs in (-1, 1):                                      # remaches en las ranuras de los postes delanteros
            _rivet(mb, _T(xs * (w / 2 - 0.019), -d, z - 0.019) @ _Rx(90))


def snap_levels(h, n, z_first=0.1, z_top=None, z0=0.012, off=0.04, pitch=0.0508, sl=0.026):
    """Alturas de nivel acomodadas a la ranura (el alma del larguero centrada en una ranura del poste)."""
    z_top = z_top if z_top is not None else h - 0.06
    out = []
    for i in range(n):
        zt = z_first + (z_top - z_first) * i / (n - 1)
        k = max(0, round((zt - 0.019 - sl / 2 - z0 - off) / pitch))
        out.append(z0 + off + k * pitch + sl / 2 + 0.019)
    return out


# ======================================================================================================== mercancía (mallas héroe)
def grid_solid(mb, top, bot, mats, M=None, edge_mat=None):
    """Sólido delgado cerrado por dos rejillas (nu × nv) superior e inferior + cantos; mats[i][j] = material de la celda
    superior (i, j) (la inferior usa el mismo): zonas impresas sin calcomanías coplanares."""
    T = [[mb.bm.verts.new((M @ Vector(p)) if M is not None else Vector(p)) for p in row] for row in top]
    B = [[mb.bm.verts.new((M @ Vector(p)) if M is not None else Vector(p)) for p in row] for row in bot]
    nu, nv = len(T), len(T[0])
    em = edge_mat or mats[0][0]
    for i in range(nu - 1):
        for j in range(nv - 1):
            mb.face([T[i][j], T[i + 1][j], T[i + 1][j + 1], T[i][j + 1]], mats[i][j])
            mb.face([B[i][j], B[i][j + 1], B[i + 1][j + 1], B[i + 1][j]], mats[i][j])
    for i in range(nu - 1):
        mb.face([B[i][0], B[i + 1][0], T[i + 1][0], T[i][0]], em)
        mb.face([T[i][-1], T[i + 1][-1], B[i + 1][-1], B[i][-1]], em)
    for j in range(nv - 1):
        mb.face([T[0][j], T[0][j + 1], B[0][j + 1], B[0][j]], em)
        mb.face([B[-1][j], B[-1][j + 1], T[-1][j + 1], T[-1][j]], em)


def pillow_bag(L, W, T, mat="plastic", band=None, seed=0, nu=12, nv=7, seal=0.022, zr=0.38, wr=0.0025, crimp=True, band_u=0.38):
    """Bolsa de almohada llena (arroz, frijol, costal), acostada sobre z = 0, largo L en X: cuerpo abombado con fondo aplanado
    por el peso, costuras laterales a media altura, sellos de engargolado en los extremos, arrugas y pellizcos en las esquinas.
    band: material de la franja impresa central (celdas de la malla, no calcomanía)."""
    r = rng(seed)
    ph = [_f(v) for v in r.uniform(0, 2 * PI, 6)]
    Lb = L / 2 - seal
    xs = [-L / 2, -Lb] + [-Lb * math.cos(PI * i / (nu - 3)) for i in range(1, nu - 3)] + [Lb, L / 2]
    ys = [-W / 2 * math.cos(PI * j / (nv - 1)) for j in range(nv)]
    zm = zr * T
    top, bot, mats = [], [], []
    for x in xs:
        u = max(-1.0, min(1.0, x / Lb))
        rt, rb = [], []
        for y in ys:
            v = y / (W / 2)
            if abs(x) > Lb + 1e-6:
                cz = (0.0006 * math.sin(y * 520.0) if crimp else 0.0) + 0.002 * math.sin(ph[4] + 3 * y / W) * (abs(x) - Lb) / seal
                rt.append((x, y, zm + 0.0007 + cz))
                rb.append((x, y, zm - 0.0007 + cz))
                continue
            S = max(0.0, 1 - abs(u) ** 3) ** 0.5 * max(0.0, 1 - abs(v) ** 2.2) ** 0.55
            wz = wr * (math.sin(8.3 * u + ph[0]) * math.sin(6.1 * v + ph[1]) + 0.6 * math.sin(15.0 * u + 7.0 * v + ph[2]))
            pinch = 0.06 * W * max(0.0, abs(u) - 0.55) / 0.45 * (1 - abs(v)) ** 2 * math.copysign(1, v)
            yy = y * (1 - 0.07 * max(0.0, abs(u) - 0.5) / 0.5) - pinch * 0.2
            zt = zm + (T - zm) * S + wz * S ** 0.5 * (1 - S * 0.6)
            zb = zm * (1 - min(1.0, 2.6 * S)) ** 1.6 + 0.0004
            rt.append((x, yy, zt))
            rb.append((x, yy, min(zb, zt - 0.0012)))
        top.append(rt)
        bot.append(rb)
    for i in range(len(xs) - 1):
        xc = (xs[i] + xs[i + 1]) / 2
        mats.append([band if (band and abs(xc) < band_u * L / 2) else mat for _ in range(nv - 1)])
    mb = MB()
    grid_solid(mb, top, bot, mats, edge_mat=mat)
    return mb


def paper_bag(w, d, h, mat="paper", band=None, seed=0, lv=6):
    """Bolsa de papel de fondo cuadrado (harina, azúcar) parada: frentes abombados, fuelles laterales con pliegue hacia adentro
    que se cierra arriba, fondo plano, arrugas; la boca se cierra en una aleta doble que se dobla hacia el frente."""
    r = rng(seed)
    ph = [_f(v) for v in r.uniform(0, 2 * PI, 4)]
    c = 0.005
    zt = h - 0.045

    def ring(z, inset=0.0, crease=0.004, bulge=0.0, sq=1.0):
        hw, hd = w / 2 - inset, d / 2 - inset
        P = [(hw - crease, 0.0), (hw, hd - c), (hw - c, hd), (0.0, hd + bulge), (-hw + c, hd), (-hw, hd - c), (-hw + crease, 0.0),
             (-hw, -hd + c), (-hw + c, -hd), (0.0, -hd - bulge), (hw - c, -hd), (hw, -hd + c)]
        out = []
        for (x, y) in P:
            wz = 0.0012 * math.sin(31 * x + 13 * z + ph[0]) * math.sin(21 * z + ph[1]) if 0.01 < z < zt - 0.005 else 0.0
            out.append((x + wz, y * sq + wz * 0.6, z))
        return out
    loops = [ring(0.0, inset=0.003), ring(0.006)]
    mats = [mat, mat]
    for k in range(1, lv):
        z = 0.006 + (zt - 0.006) * k / (lv - 1)
        f = z / zt
        loops.append(ring(z, crease=0.004 + 0.016 * f ** 3, bulge=0.0045 * math.sin(PI * min(f, 1.0) ** 0.8)))
        mats.append(band if (band and 0.3 * h < z - (zt - 0.006) / (lv - 1) * 0.5 < 0.62 * h) else mat)
    loops.append(ring(zt + 0.016, crease=w * 0.3, sq=0.3))
    mats.append(mat)
    base = ring(zt + 0.016, crease=w * 0.33)
    path = [(0.0, zt + 0.03), (-0.004, zt + 0.037), (-0.012, zt + 0.0405), (-0.024, zt + 0.0385)]
    for i, (py, pz) in enumerate(path):
        a_, b_ = path[max(i - 1, 0)], path[min(i + 1, len(path) - 1)]
        ty, tz = b_[0] - a_[0], b_[1] - a_[1]
        ln = math.hypot(ty, tz)
        ny, nz = tz / ln, -ty / ln
        loops.append([(x * 0.97, py + (y / (d / 2)) * 0.002 * ny, pz + (y / (d / 2)) * 0.002 * nz) for (x, y, _) in base])
        mats.append(mat)
    mb = MB()
    skin(mb, loops, mat, mats=mats[:len(loops) - 1])
    return mb


def can(R=0.037, H=0.11, label="sign_red", seg=14, lod=0, band=None, style="paper", pull=False):
    """Lata de conserva de hojalata: fondo con doble engargolado y ceja de estiba, cuerpo, doble engargolado arriba y tapa
    rehundida con anillos de expansión (o abre-fácil con argolla si pull). style="paper": etiqueta de papel que envuelve el cuerpo
    (0,3 mm sobre la lámina, con franja `band` de otro color: el producto se reconoce por su combinación de colores);
    style="litho": lata litografiada con 3 cordones de refuerzo en el cuerpo. Todo de un perfil torneado (materiales por tramo,
    sin calcomanías). lod=1: fila trasera (perfil reducido)."""
    mb = MB()
    if lod == 0:
        zb0, zb1 = 0.0095, H - 0.0095
        if style == "litho":
            body = [(R * 0.97, zb0)]
            for k in range(3):                                    # cordones de refuerzo
                zc = zb0 + (zb1 - zb0) * (k + 1) / 4
                body += [(R * 0.97, zc - 0.003), (R * 0.955, zc - 0.0012), (R * 0.955, zc + 0.0012), (R * 0.97, zc + 0.003)]
            body += [(R * 0.97, zb1)]
            bm = [label] * (len(body) - 1)
            if band:
                mid = len(bm) // 2
                bm[mid - 1:mid + 2] = [band] * 3
        else:
            Rl = R * 0.97 + 0.0003
            zm = zb0 + (zb1 - zb0) * 0.62
            body = [(R * 0.97, zb0), (Rl, zb0 + 0.0008), (Rl, zm), (Rl, zm + 0.012), (Rl, zb1 - 0.0008), (R * 0.97, zb1)]
            bm = ["steel", label, band or label, label, "steel"]
        prof = [(0.0, 0.0012), (R * 0.82, 0.0005), (R * 0.95, 0.0), (R * 0.985, 0.003), (R * 0.985, 0.006), (R * 0.97, zb0)] + body[1:] + \
               [(R, H - 0.0058), (R, H - 0.0012), (R * 0.97, H - 0.0006), (R * 0.9, H - 0.0045), (R * 0.75, H - 0.0045),
                (R * 0.72, H - 0.0035), (R * 0.69, H - 0.0045), (R * 0.45, H - 0.0045), (R * 0.42, H - 0.0036), (R * 0.39, H - 0.0045),
                (0.0, H - 0.0045)]
        mats = ["steel"] * 5 + bm + ["steel"] * 11
        _revolve_raw(mb, prof, mats, seg=max(seg, 24))     # 24 lados: flecha 0,3 mm en Ø 75 (se repite cientos de veces)
        if pull:                                                  # remache, lengüeta y argolla del abre-fácil
            zt = H - 0.0045
            revolve(mb, [(0.0035, zt), (0.0035, zt + 0.0008), (0.0, zt + 0.0012)], "aluminium", seg=16, M=_T(0, 0, 0), caps=False)
            Mr = _T(R * 0.42, 0.0, zt + 0.0006) @ _Rz(180)
            ring = [(0.009 * math.cos(2 * PI * k / 16) + 0.0, 0.0072 * math.sin(2 * PI * k / 16), 0.0) for k in range(16)]
            tube(mb, [tuple(Mr @ Vector(p)) for p in ring + [ring[0]]], 0.0009, mat="aluminium", caps=False)
            slab(mb, _T(R * 0.18, 0, zt + 0.0003), 0.016, 0.009, 0.0006, rc=0.003, re=0.0002, mat="aluminium")
    else:
        prof = [(R * 0.985, 0.0), (R * 0.985, H - 0.0095), (R, H - 0.0058), (R, H - 0.0025), (R * 0.88, H - 0.0045), (0.0, H - 0.0045)]
        mats = [label, "steel", "steel", "steel", "steel"]
        _revolve_raw(mb, prof, mats, seg=max(seg, 24))     # 24 lados: flecha 0,3 mm en Ø 75 (se repite cientos de veces)
    return mb


def oval_can(L=0.105, W=0.065, H=0.03, label="sign_red", band="paint_yellow"):
    """Lata oval de sardinas (125 g): cuerpo de estadio litografiado con franja, doble engargolado arriba y abajo, tapa
    rehundida con la llave abre-fácil (argolla y lengüeta) en un extremo."""
    mb = MB()
    n = 48

    def oval(off, z):
        return [(x + nx * off, y + ny * off, z) for (x, y, nx, ny) in _oval_pts(L, W, n)]
    loops = [oval(-0.002, 0.0), oval(-0.0005, 0.0012), oval(0.0, 0.003), oval(-0.0012, 0.0045), oval(-0.0012, H * 0.4),
             oval(-0.0012, H * 0.62), oval(-0.0012, H - 0.0045), oval(0.0, H - 0.003), oval(0.0, H - 0.0008), oval(-0.0015, H - 0.0002),
             oval(-0.004, H - 0.0025), oval(-0.0055, H - 0.0025)]
    mats = ["steel", "steel", "steel", label, band, label, "steel", "steel", "steel", "steel", "steel"]
    skin(mb, loops, "steel", mats=mats)
    zt = H - 0.0025
    Mr = _T(-L / 2 + 0.016, 0.0, zt + 0.0006)
    ring = [(0.0085 * math.cos(2 * PI * k / 16), 0.0068 * math.sin(2 * PI * k / 16), 0.0) for k in range(16)]
    tube(mb, [tuple(Mr @ Vector(p)) for p in ring + [ring[0]]], 0.0009, mat="aluminium", caps=False)
    slab(mb, _T(-L / 2 + 0.028, 0, zt), 0.014, 0.008, 0.0006, rc=0.003, re=0.0002, mat="aluminium")
    return mb


def _oval_pts(L, W, n):
    """Estadio (largo L en X, ancho W en Y) a paso constante: (x, y, nx, ny)."""
    R = W / 2
    a = L / 2 - R
    per = 4 * a + 2 * PI * R
    out = []
    for k in range(n):
        s_ = per * k / n
        if s_ < 2 * a:
            x, y, nx, ny = -a + s_, -R, 0.0, -1.0
        elif s_ < 2 * a + PI * R:
            th = -PI / 2 + (s_ - 2 * a) / R
            x, y, nx, ny = a + R * math.cos(th), R * math.sin(th), math.cos(th), math.sin(th)
        elif s_ < 4 * a + PI * R:
            x, y, nx, ny = a - (s_ - 2 * a - PI * R), R, 0.0, 1.0
        else:
            th = PI / 2 + (s_ - 4 * a - PI * R) / R
            x, y, nx, ny = -a + R * math.cos(th), R * math.sin(th), math.cos(th), math.sin(th)
        out.append((x + nx * 0.0, y + ny * 0.0, nx, ny))
    return out


def glass_jar(R=0.04, H=0.13, fill="cardboard", label="paper", lid="sign_red", band=None):
    """Frasco de vidrio (café soluble, chiles, mermelada): fondo grueso, hombro, cuello con rosca, tapa metálica con estrías y
    ceja; contenido visible (sólido interior de su color) y etiqueta de papel como tramo del perfil (0,3 mm sobre el vidrio)."""
    mb = MB()
    Rn = R * 0.78
    prof = [(0.0, 0.004), (R * 0.85, 0.0), (R * 0.97, 0.003), (R, 0.012), (R, 0.02), (R + 0.0003, 0.021), (R + 0.0003, H * 0.45),
            (R + 0.0003, H * 0.55), (R + 0.0003, H * 0.7), (R, H * 0.71), (R, H * 0.8), (R * 0.93, H * 0.87), (Rn, H * 0.9),
            (Rn, H - 0.012)]
    mats = ["glass", "glass", "glass", "glass", label, band or label, label, "glass", "glass", "glass", "glass", "glass", "glass"]
    revolve(mb, prof, mats, seg=48, caps=False)
    revolve(mb, [(0.0, 0.0045), (R * 0.95, 0.0045), (R * 0.95, H * 0.72), (R * 0.75, H * 0.86), (0.0, H * 0.86)], fill, seg=32)
    lp = [(Rn + 0.0035, H - 0.016), (Rn + 0.0045, H - 0.0145)]
    for k in range(5):
        zz = H - 0.014 + k * 0.0028
        lp += [(Rn + 0.0045, zz), (Rn + 0.0037, zz + 0.0014)]
    lp += [(Rn + 0.0045, H + 0.0012), (Rn + 0.003, H + 0.0022), (Rn * 0.7, H + 0.0024), (0.0, H + 0.0022)]
    revolve(mb, lp, lid, seg=56)
    return mb


def box_pack(w, d, h, mat="sign_white", band="sign_red", top_mat=None):
    """Caja de cartoncillo impresa (avena, galletas, jabón en polvo, focos): cuerpo de cantos un poco vencidos, franja de color
    a media altura (tramo de material), solapas superior e inferior con su ceja de pegado (0,6 mm)."""
    mb = MB()
    pts = rr_pts(w, d, 0.0018, 4)
    lv = [(0.0, 0.0012), (0.0012, 0.0), (h * 0.35, 0.0), (h * 0.62, 0.0), (h - 0.0012, 0.0), (h, 0.0012)]
    loops = [[(x - math.copysign(i_, x), y - math.copysign(i_, y), z) for (x, y) in pts] for (z, i_) in lv]
    skin(mb, loops, mat, mats=[mat, mat, band, mat, top_mat or mat])
    for z in (h - 0.0004, 0.0):                                  # ceja de la solapa de pegado
        mb.box((-w / 2 + 0.003, -d / 2 - 0.0006, z - 0.0006 if z else 0.0), (w / 2 - 0.003, -d / 2 + 0.0004, z + 0.0006 if z else 0.0012),
               mat, bevel=0.0002)
    return mb


def stand_pouch(w=0.16, d=0.07, h=0.24, mat="sign_blue", band="sign_white", seed=0):
    """Bolsa de pie de plástico (detergente, azúcar): fondo de fuelle ovalado, cuerpo abombado que se angosta arriba hasta el
    sello plano termosoldado con muesca de rasgado y estrías del sello; arrugas suaves del plástico."""
    r = rng(seed)
    mb = MB()
    n = 32
    ph = [_f(v) for v in r.uniform(0, 2 * PI, 3)]
    loops = []
    zs = [0.0, 0.004, 0.015, 0.04, h * 0.3, h * 0.5, h * 0.7, h * 0.82, h * 0.9, h - 0.025, h - 0.024, h - 0.001]
    mats = []
    for i, z in enumerate(zs):
        f = z / h
        dd = d / 2 * (0.82 if i == 0 else 1.0) * (1.0 - 0.95 * _sstep(0.6, 0.96, f)) + (0.0012 if f > 0.9 else 0.0)
        ww = w / 2 * (0.92 if i == 0 else 1.0) * (1.0 + 0.03 * math.sin(PI * f))
        ring = []
        for k in range(n):
            a = 2 * PI * k / n
            ca, sa = math.cos(a), math.sin(a)
            x = ww * math.copysign(abs(ca) ** 0.6, ca)
            y = dd * math.copysign(abs(sa) ** 0.85, sa)
            wr = 0.0012 * math.sin(9 * a + ph[0] + 13 * f) * math.sin(7 * f + ph[1]) if 0.05 < f < 0.88 else 0.0
            ring.append((x + wr * ca, y + wr * sa, z))
        loops.append(ring)
        if i < len(zs) - 1:
            mats.append(band if 0.35 < (f + zs[i + 1] / h) / 2 < 0.62 else mat)
    skin(mb, loops, mat, mats=mats)
    for k in range(6):                                           # estrías del sello
        zz = h - 0.022 + k * 0.0035
        mb.box((-w / 2 + 0.004, -0.0016, zz), (w / 2 - 0.004, 0.0016, zz + 0.0012), mat, bevel=0.0004)
    return mb


def _sstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def salt_canister(R=0.045, H=0.135, mat="sign_blue", band="sign_white"):
    """Bote de sal de cartón: tubo con tapas de lámina engargoladas y pico vertedor de lámina abatible en la tapa."""
    mb = MB()
    prof = [(0.0, 0.001), (R * 0.95, 0.001), (R + 0.0006, 0.0), (R + 0.0008, 0.005), (R, 0.006), (R, H * 0.4), (R, H * 0.62),
            (R, H - 0.006), (R + 0.0008, H - 0.005), (R + 0.0006, H), (R * 0.95, H - 0.001), (0.0, H - 0.001)]
    revolve(mb, prof, ["steel", "steel", "steel", "steel", mat, band, mat, "steel", "steel", "steel", "steel"], seg=48)
    mb.box((R * 0.35, -0.012, H - 0.001), (R * 0.85, 0.012, H + 0.0012), "steel", bevel=0.0004)
    return mb


def soda_bottle(mat="glass", label="sign_red", cap="sign_red", fill="amber"):
    """Botella PET de refresco de 2 L (Ø 110 × 310 mm): base de 5 pétalos, cuerpo con anillos, etiqueta de banda, hombro,
    cuello con anillo de seguridad y tapa estriada; el líquido se ve por dentro (sólido interior)."""
    mb = MB()
    R = 0.055

    def petal(a):
        return 1.0 - 0.18 * (0.5 + 0.5 * math.cos(5 * a)) ** 2
    revolve(mb, [(0.0, 0.006), (R * 0.6, 0.0), (R * 0.95, 0.012), (R, 0.03)], mat, seg=60, rmod=lambda a: petal(a), caps=False)
    prof = [(R, 0.03), (R, 0.08), (R * 0.97, 0.088), (R, 0.096), (R + 0.0003, 0.1), (R + 0.0003, 0.2), (R, 0.205), (R * 0.97, 0.212),
            (R, 0.22), (R * 0.9, 0.245), (R * 0.55, 0.275), (0.0135, 0.29), (0.0135, 0.292), (0.016, 0.293), (0.016, 0.295), (0.0135, 0.296)]
    mats = [mat, mat, mat, mat, label, mat, mat, mat, mat, mat, mat, mat, mat, mat, mat]
    revolve(mb, prof, mats, seg=56, caps=False)
    revolve(mb, [(0.0, 0.007), (R * 0.95, 0.012), (R * 0.97, 0.06), (R * 0.97, 0.2), (R * 0.85, 0.24), (0.0, 0.24)], fill, seg=40)
    revolve(mb, [(0.0145, 0.2955), (0.0155, 0.297), (0.0155, 0.318), (0.0145, 0.3195), (0.0, 0.3198)], cap, seg=40,
            rmod=lambda a: 1.0 - 0.04 * (0.5 + 0.5 * math.cos(24 * a)) ** 4, caps=False)
    return mb


def oil_bottle(mat="amber", label="paper", cap="plastic_blue"):
    """Botella PET de aceite de 1 L: base de pétalos (insinuada), cintura, hombro, cuello con anillo, tapa estriada; etiqueta
    como tramo del perfil."""
    mb = MB()
    R = 0.04
    prof = [(0.0, 0.004), (R * 0.97, 0.0), (R, 0.03), (R * 0.93, 0.085), (R * 0.93, 0.15), (R, 0.162), (R, 0.2), (R * 0.72, 0.236),
            (0.0135, 0.262), (0.0135, 0.266)]
    mats = [mat, mat, mat, label, mat, mat, mat, mat, mat]
    revolve(mb, prof, mats, seg=14)
    revolve(mb, [(0.0165, 0.2655), (0.0165, 0.2685), (0.0142, 0.27)], "plastic", seg=13, caps=False)   # anillo
    revolve(mb, [(0.0152, 0.2695), (0.0158, 0.2715), (0.0158, 0.287), (0.0146, 0.289), (0.0, 0.2895)], cap, seg=13, caps=False)
    return mb


def jug(mat="plastic", cap="plastic_blue", label="sign_blue"):
    """Garrafa de cloro de 1 gal: cuerpo de sección cuadrada redondeada, asa hueca integrada, cuello y tapa; etiqueta como
    banda de material del cuerpo."""
    mb = MB()
    lv = [(0.0, 0.135, 0.135), (0.004, 0.142, 0.142), (0.02, 0.145, 0.145), (0.11, 0.145, 0.145), (0.2, 0.145, 0.145),
          (0.235, 0.13, 0.13), (0.26, 0.08, 0.08), (0.27, 0.05, 0.05)]
    loops = [[(x, y, z) for (x, y) in rr_pts(a, b, min(a, b) * 0.3, 3)] for (z, a, b) in lv]
    skin(mb, loops, mat, mats=[mat, mat, label, mat, mat, mat, mat])
    revolve(mb, [(0.019, 0.268), (0.019, 0.285), (0.0205, 0.287), (0.0205, 0.305), (0.018, 0.307), (0.0, 0.307)], cap, seg=8,
            caps=False)
    tube(mb, [(0.03, 0.03, 0.25), (0.066, 0.066, 0.262), (0.08, 0.08, 0.24), (0.079, 0.079, 0.21), (0.052, 0.052, 0.19)], 0.011,
            seg=6, mat=mat)
    return mb


def carton(w, d, h, seed=0, tape=True, mat="cardboard", tape_mat="paper", open_flaps=None, crush=0.0, stamp=None):
    """Caja de cartón corrugado cerrada: cuerpo con cantos un poco aplastados y costados abombados, tapas superiores (dos
    solapas largas con junta de 3 mm al centro), cinta canela sobre la junta que baja por los costados, ceja de la solapa
    de unión en una esquina. open_flaps=(a1, a2): solapas abiertas (grados) y caja hueca con fondo."""
    r = rng(seed)
    mb = MB()
    hb = h - 0.004
    if open_flaps is None:
        bul = [_f(r.uniform(0.002, 0.006)) for _ in range(4)]        # costados abombados por el contenido / la estiba
        dent = (int(r.integers(0, 4)), _f(r.uniform(0.0, 0.007)))   # una esquina golpeada

        def ring(z, inset, fz):
            c_ = 0.005
            P = [(w / 2, 0.0, 0), (w / 2, d / 2 - c_, -1), (w / 2 - c_, d / 2, -1), (0.0, d / 2, 1), (-w / 2 + c_, d / 2, -1),
                 (-w / 2, d / 2 - c_, -1), (-w / 2, 0.0, 2), (-w / 2, -d / 2 + c_, -1), (-w / 2 + c_, -d / 2, -1), (0.0, -d / 2, 3),
                 (w / 2 - c_, -d / 2, -1), (w / 2, -d / 2 + c_, -1)]
            out = []
            for k, (x, y, side) in enumerate(P):
                sx_, sy_ = (1 if x > 0 else -1 if x < 0 else 0), (1 if y > 0 else -1 if y < 0 else 0)
                b = bul[side] * fz if side >= 0 else 0.0
                if side in (0, 2):
                    x += sx_ * b
                elif side in (1, 3):
                    y += sy_ * b
                if side < 0 and k // 3 == dent[0] and fz > 0.6:
                    x -= sx_ * dent[1] * 0.7
                    y -= sy_ * dent[1] * 0.7
                out.append((x - sx_ * inset, y - sy_ * inset, z))
            return out
        loops = [ring(0.0, 0.003 + crush, 0.0), ring(0.004 + crush, 0.0, 0.2), ring(hb * 0.5, 0.0, 1.0), ring(hb - 0.004, 0.0, 0.7),
                 ring(hb, 0.002, 0.6)]
        skin(mb, loops, mat)
        if stamp:                                                # leyenda impresa (relieve 1,2 mm) que sigue el abombado del frente
            word, size = stamp
            tmp = MB()
            etext(tmp, word, size, 0.0015, "cable", _T(0, -size * 0.36, -0.0003), res=1, back=False, bold=True)
            z0_ = hb * 0.5

            def fzz(z):
                if z <= hb * 0.5:
                    return 0.2 + 0.8 * (z - 0.004) / (hb * 0.5 - 0.004)
                return 1.0 - 0.3 * (z - hb * 0.5) / (hb * 0.5 - 0.004)
            for v in tmp.bm.verts:
                tx, ty, tz = v.co
                zz = z0_ + ty
                yy = -(d / 2 + bul[3] * fzz(zz) * max(0.0, 1 - abs(tx) / (w / 2 - 0.005))) - tz
                v.co = Vector((tx, yy, zz))
            mb.join(tmp)
        rise = 0.0
        for s in (-1, 1):                                       # solapas con bisagra en el canto y junta al centro, levantadas
            th = math.degrees(math.atan(0.0015 / (w / 2))) * _f(r.uniform(0.3, 1.0))
            rise = max(rise, (w / 2) * math.sin(math.radians(th)))
            Mf = _T(s * (w / 2 - 0.001), 0, hb - 0.0005) @ _Ry(s * th)
            x0, x1 = sorted((0.0, -s * (w / 2 - 0.0025)))
            board(mb, x0, x1, -d / 2 + 0.001, d / 2 - 0.001, 0.0, 0.004, mat, rc=0.002, re=0.0012, M=Mf)
        if tape:
            tw = 0.048
            zt = hb - 0.0005 + 0.004 + rise - 0.0003
            mb.box((-tw / 2, -d / 2 - 0.0012, zt), (tw / 2, d / 2 + 0.0012, zt + 0.0011), tape_mat, bevel=0.0)
            for s in (-1, 1):                                   # cinta que baja por el frente y la espalda (sigue el abombado)
                side = 1 if s > 0 else 3

                def fz(z):
                    return 0.7 + 0.3 * max(0.0, (hb - 0.004 - z) / (hb * 0.5 - 0.004)) if z < hb - 0.004 else 0.7 - 0.1 * (z - hb + 0.004) / 0.004
                tl = []
                for z in (hb - 0.06, hb - 0.03, hb - 0.004, zt + 0.0004):
                    y0_ = s * (d / 2 + bul[side] * min(fz(z), 0.7 if z > hb - 0.004 else 1.0) + 0.0001)
                    y1_ = y0_ + s * 0.0011
                    tl.append([(-tw / 2, y0_, z), (tw / 2, y0_, z), (tw / 2, y1_, z), (-tw / 2, y1_, z)])
                skin(mb, tl, tape_mat)
    else:
        t = 0.004
        cupw = [(x, y) for (x, y) in rr_pts(w, d, 0.004, 1)]
        cupi = [(x, y) for (x, y) in rr_pts(w - 2 * t, d - 2 * t, 0.002, 1)]
        loops = [[(x, y, 0.0) for (x, y) in cupw], [(x, y, hb) for (x, y) in cupw], [(x, y, hb) for (x, y) in cupi],
                 [(x, y, t) for (x, y) in cupi]]
        skin(mb, loops, mat)
        for (s, ax, L_, ang) in ((-1, "y", d, open_flaps[0]), (1, "y", d, open_flaps[1])):
            Mf = _T(s * (w / 2 - t / 2), 0, hb) @ _Ry(s * (90 - ang))
            board(mb, -t / 2, t / 2, -d / 2 + t + 0.0015, d / 2 - t - 0.0015, 0.0, w / 2 - 0.004, mat, rc=0.002, re=0.0015, M=Mf)
        for (s, ang) in ((-1, open_flaps[0] * 0.8), (1, open_flaps[1] * 1.1)):
            Mf = _T(0, s * (d / 2 - t / 2), hb) @ _Rx(-s * (90 - ang))
            board(mb, -w / 2 + t + 0.0015, w / 2 - t - 0.0015, -t / 2, t / 2, 0.0, d / 2 - 0.004, mat, rc=0.002, re=0.0015, M=Mf)
    return mb


def tp_pack(mat="plastic", band="sign_blue", n=16):
    """Paquete de 4 rollos de papel higiénico (2 × 2, de pie) envuelto en plástico: contorno de rectángulo con esquinas del
    radio del rollo, envoltura doblada abajo y arriba; arriba la película se hunde en cruz entre rollos y en los canutos."""
    mb = MB()
    Rr = 0.054
    Hh = 0.102
    hw = 2 * Rr

    def outline(a):
        c, s_ = math.cos(a), math.sin(a)
        ex = 3.4
        return (hw * math.copysign(abs(c) ** (2 / ex), c), hw * math.copysign(abs(s_) ** (2 / ex), s_))

    def ring(frac, z, dz=None):
        out = []
        for k in range(n):
            a = 2 * PI * k / n
            x, y = outline(a)
            zz = z + (dz(a) if dz else 0.0)
            out.append((x * frac, y * frac, zz))
        return out
    cross = lambda a: -0.006 * math.cos(2 * a) ** 8                      # noqa: E731  valle entre rollos (0°, 90°...)
    cores = lambda a: -0.005 * max(0.0, math.cos(2 * (a - PI / 4))) ** 4 - 0.004 * math.cos(2 * a) ** 8  # noqa: E731
    loops = [[(0.0, 0.0, 0.003)], ring(0.88, 0.0), ring(1.0, 0.012), ring(1.0, 0.035), ring(1.0, 0.07), ring(1.0, Hh - 0.011),
             ring(0.93, Hh - 0.002, cross), ring(0.78, Hh, cross), ring(0.61, Hh, cores), ring(0.44, Hh, cross),
             ring(0.2, Hh - 0.002), [(0.0, 0.0, Hh - 0.003)]]
    mats = [mat, mat, mat, band, mat, mat, mat, mat, mat, mat, mat]
    skin(mb, loops, mat, mats=mats)
    return mb


def jar_candle(print_mat="sign_white", R=0.029, H=0.2, seg=14):
    """Veladora: vaso de vidrio con fondo grueso, manga impresa (material del tramo), labio, cera rehundida y pabilo."""
    mb = MB()
    prof = [(0.0, 0.003), (R * 0.93, 0.0), (R, 0.02), (R, H - 0.016), (R, H), (R - 0.0022, H), (R - 0.0022, H - 0.013),
            (0.0, H - 0.013)]
    revolve(mb, prof, ["glass", "glass", print_mat, "glass", "glass", "glass", "plastic"], seg=seg)
    cyl(mb, (0, 0, H - 0.0135), (0.0008, 0, H - 0.003), 0.0009, seg=4, mat="cable")
    return mb


def battery_box(seed=0):
    """Exhibidor de cartón con pilas AA de pie (frente bajo, respaldo alto) y una tarjeta con 4 pilas."""
    r = rng(seed)
    mb = MB()
    w, d, t = 0.15, 0.1, 0.0025
    board(mb, -w / 2, w / 2, -d / 2, d / 2, 0.0, t, "cardboard", rc=0.002, re=0.001)
    board(mb, -w / 2, w / 2, -d / 2, -d / 2 + t, t, 0.035, "cardboard", rc=0.001, re=0.001)
    board(mb, -w / 2, w / 2, d / 2 - t, d / 2, t, 0.12, "sign_red", rc=0.001, re=0.001)
    for s in (-1, 1):
        x0, x1 = sorted((s * w / 2, s * (w / 2 - t)))
        Mside = [(-d / 2 + t, 0.035), (d / 2 - t, 0.12), (d / 2 - t, t), (-d / 2 + t, t)]
        mb.plate([(y, z) for (y, z) in Mside], x1 - x0, "cardboard", m=_T(x0, 0, 0) @ Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))))
    etext(mb, "AA", 0.03, 0.0012, "sign_white", _T(0, d / 2 - t, 0.075) @ _Rx(90), res=1, back=False)
    bat = MB()
    revolve(bat, [(0.0071, 0.0), (0.0071, 0.044), (0.0066, 0.047), (0.0028, 0.0475), (0.0028, 0.0495), (0.0, 0.0495)],
            ["cable", "steel", "steel", "steel", "steel"], seg=6, caps=False)
    for i in range(6):
        for j in range(4):
            if r.random() < 0.15:
                continue
            x = -w / 2 + 0.016 + i * 0.0235 + _jit(r, 0.001)
            y = -d / 2 + 0.017 + j * 0.022 + _jit(r, 0.001)
            mb.join(bat, _T(x, y, t) @ _Rz(_f(r.uniform(0, 360))))
    return mb


def rope_coil(seed=0, R=0.12, rr=0.0105, turns=4.5, mat="burlap"):
    """Rollo de soga de yute acostado: espiras apiladas con holgura irregular, dos amarres y la punta suelta."""
    r = rng(seed)
    mb = MB()
    pts = []
    n = int(turns * 12)
    for k in range(n + 1):
        a = 2 * PI * k / 12
        lay = k / 12
        rad = R + 0.006 * math.sin(3 * a + 0.5) + _jit(r, 0.002)
        z = rr + 0.6 * rr * lay + 0.003 * math.sin(2 * a)
        pts.append((rad * math.cos(a), rad * math.sin(a), z))
    a_end = 2 * PI * n / 12
    pts += [((R + 0.02) * math.cos(a_end + 0.3), (R + 0.02) * math.sin(a_end + 0.3), rr),
            ((R + 0.045) * math.cos(a_end + 0.5), (R + 0.045) * math.sin(a_end + 0.55), rr)]
    rope_tube(mb, pts, rr, mat=mat, lay=rr * 14)                # yute de 3 cabos torcidos
    zt = rr * (1 + 0.6 * turns) + rr
    for a in (0.7, 3.9):                                        # amarres
        c, s_ = math.cos(a), math.sin(a)
        loop = []
        for k in range(9):
            b = 2 * PI * k / 8
            loop.append(((R + (rr + 0.006) * math.cos(b)) * c, (R + (rr + 0.006) * math.cos(b)) * s_,
                         zt / 2 + (zt / 2 + 0.004) * math.sin(b)))
        rope_tube(mb, loop, 0.004, mat=mat, lay=0.03)
    return mb


def hammer(seed=0):
    """Martillo de uña acostado (mango en X, cabeza en Y; z = 0 en el eje): mango de madera ovalado con cuello, cabeza forjada
    con cara de golpe redonda, ojo, y uña partida y curva."""
    mb = MB()
    st = []
    for (x, a, b) in ((0.0, 0.0125, 0.017), (0.012, 0.0135, 0.019), (0.12, 0.012, 0.016), (0.22, 0.0092, 0.0132), (0.285, 0.0105,
                                                                                                                    0.0155), (0.312, 0.0105, 0.0155)):
        st.append((x, [(b * math.cos(2 * PI * k / 10), a * math.sin(2 * PI * k / 10)) for k in range(10)]))
    lofts(mb, st, "wood")
    Mh = _T(0.30, 0, 0)
    slathe(mb, [(0.0, -0.072), (0.0125, -0.072), (0.0142, -0.068), (0.0142, -0.05), (0.0105, -0.034), (0.0105, -0.02)], seg=10,
           mat="steel", M=Mh @ _Rx(-90))
    board(mb, -0.016, 0.016, -0.031, 0.022, -0.0118, 0.0118, "steel", rc=0.006, re=0.003, M=Mh)
    for s in (-1, 1):                                           # uña partida y curva hacia el mango
        path = [(0.30, 0.02, s * 0.0052), (0.298, 0.05, s * 0.0062), (0.287, 0.078, s * 0.0072), (0.272, 0.092, s * 0.0078)]
        sweep_frame(mb, [(-0.0042, -0.010), (0.0042, -0.010), (0.0032, 0.010), (-0.0032, 0.010)], path, "steel", up=(1, 0, 0),
                    scale=lambda t_: (1.0 - 0.45 * t_, 1.0 - 0.65 * t_))
    return mb


def machete(seed=0):
    """Machete de campo acostado (z = 0 en el plano de la hoja): hoja de 2,2 mm con lomo recto, panza, punta curva y filo
    biselado (arista viva a media hoja); espiga cubierta por cachas de madera con 3 remaches."""
    mb = MB()
    edge = [(0.0, -0.013), (0.06, -0.017), (0.14, -0.02), (0.22, -0.022), (0.3, -0.023), (0.37, -0.022), (0.43, -0.017),
            (0.47, -0.008), (0.495, 0.004)]
    spine = [(0.5, 0.013), (0.47, 0.02), (0.3, 0.019), (0.0, 0.016), (-0.135, 0.013), (-0.142, 0.002), (-0.135, -0.011)]
    out = edge + spine
    t = 0.0022
    ne = len(edge)
    bot = [(x, y, -t / 2) for (x, y) in out]
    top = [(x, y, t / 2) for (x, y) in out]
    mid = [(x, y - (0.0035 if i < ne and x > 0.02 else 0.0), 0.0) for i, (x, y) in enumerate(out)]
    mid = [(x, y + (0.0015 if i < ne and x > 0.02 else 0.0), z) for i, (x, y, z) in enumerate(mid)]
    bot = [(x, y + (0.0035 if i < ne and x > 0.02 else 0.0), z) for i, (x, y, z) in enumerate(bot)]
    top = [(x, y + (0.0035 if i < ne and x > 0.02 else 0.0), z) for i, (x, y, z) in enumerate(top)]
    skin(mb, [bot, mid, top], "steel")
    for s in (-1, 1):                                          # cachas
        prof = [(-0.138, -0.012), (-0.004, -0.0145), (-0.004, 0.0175), (-0.138, 0.0145), (-0.148, 0.002)]
        mb.plate(prof, 0.008, "wood_dark", m=_T(0, 0, s * t / 2) @ (Matrix() if s > 0 else Matrix.Diagonal((1, 1, -1, 1))))
        for x in (-0.115, -0.07, -0.025):
            revolve(mb, [(0.0034, -0.0003), (0.0028, 0.0011), (0.0, 0.0015)], "steel", seg=6,
                    M=_T(x, 0.0015, s * (t / 2 + 0.008)) @ (Matrix() if s > 0 else _Rx(180)), caps=False)
    return mb


# ======================================================================================================== anaquel de abarrotes
LABELS = ("sign_red", "paint_yellow", "sign_green", "sign_blue", "paper", "sign_white", "paint_green")


class _Heroes:
    """Caché de mallas héroe por clave (cada variante se construye una vez y se instancia con join)."""

    def __init__(self):
        self.d = {}

    def get(self, key, fn):
        if key not in self.d:
            self.d[key] = fn()
        return self.d[key]


def _tris(mb):
    return sum(len(f.verts) - 2 for f in mb.bm.faces)


class Placer:
    """Junta las colocaciones de mallas héroe con su prioridad (0 = frente visible, 1 = estiba / pila, 2 = fila trasera) y
    las vacía en el MB respetando un presupuesto de triángulos: si sobra mercancía, quita primero filas traseras y estibas
    (al azar, por semilla) — un anaquel de tienda a medio surtir, nunca uno que rebase el límite."""

    def __init__(self, mb):
        self.mb = mb
        self.items = []
        self.deps = []

    def join(self, hero, M, prio=0, on=None):
        """on: índice de la pieza sobre la que descansa (si esa se quita, ésta también: nada queda flotando)."""
        self.items.append((hero, M, prio))
        self.deps.append(on)
        return len(self.items) - 1

    def flush(self, r, budget):
        tot = _tris(self.mb) + sum(_tris(h) for (h, _, _) in self.items)
        keep = [True] * len(self.items)
        kids = {}
        for i, on in enumerate(self.deps):
            if on is not None:
                kids.setdefault(on, []).append(i)

        def drop(i):
            nonlocal tot
            if not keep[i]:
                return
            keep[i] = False
            tot -= _tris(self.items[i][0])
            for k in kids.get(i, ()):
                drop(k)
        for prio in (2, 1, 0):
            idx = [i for i, it in enumerate(self.items) if it[2] == prio]
            r.shuffle(idx)
            for i in idx:
                if tot <= budget:
                    break
                drop(i)
        for k, (h, M, _) in zip(keep, self.items):
            if k:
                self.mb.join(h, M)
        return tot


def _put(mb, hero, x, y, z, rz=0.0, s=1.0, extra=None, prio=0, on=None):
    M = _T(x, y, z) @ _Rz(rz)
    if s != 1.0:
        M = M @ Matrix.Diagonal((s, s, s, 1.0))
    if extra is not None:
        M = M @ extra
    if isinstance(mb, Placer):
        return mb.join(hero, M, prio, on)
    mb.join(hero, M)
    return None


class SKU:
    """Producto de anaquel: malla héroe (fn), huella w (frente) × d (fondo), alto h, frentes min-max, filas de fondo, estiba
    máxima, giro libre (round) o acostado a lo largo (rz). Las combinaciones de colores lo hacen reconocible sin marcas."""

    def __init__(self, key, fn, w, d, h, f=(2, 5), rows=3, stack=1, round_=False, rz=0.0, back=None):
        self.key, self.fn, self.w, self.d, self.h = key, fn, w, d, h
        self.f, self.rows, self.stack, self.round, self.rz, self.back = f, rows, stack, round_, rz, back


def _cat_canned():
    return [
        SKU("beans", lambda: can(0.0375, 0.112, "sign_red", seg=24, band="paint_yellow"), 0.0775, 0.0775, 0.112, (3, 5), 3, 2, True,
            back=lambda: can(0.0375, 0.112, "sign_red", seg=24, lod=1)),
        SKU("chiles", lambda: can(0.0375, 0.112, "paint_yellow", seg=24, band="sign_red", style="litho"), 0.0775, 0.0775, 0.112, (2, 4), 3, 2,
            True, back=lambda: can(0.0375, 0.112, "paint_yellow", seg=24, lod=1)),
        SKU("corn", lambda: can(0.0375, 0.112, "sign_green", seg=24, band="paint_yellow"), 0.0775, 0.0775, 0.112, (2, 4), 3, 2, True,
            back=lambda: can(0.0375, 0.112, "sign_green", seg=24, lod=1)),
        SKU("paste", lambda: can(0.033, 0.074, "sign_red", seg=24, band="sign_green", style="litho", pull=True), 0.068, 0.068, 0.074, (3, 6),
            3, 3, True, back=lambda: can(0.033, 0.074, "sign_red", seg=24, lod=1)),
        SKU("evap", lambda: can(0.037, 0.1, "sign_blue", seg=24, band="sign_white"), 0.0765, 0.0765, 0.1, (3, 5), 3, 2, True,
            back=lambda: can(0.037, 0.1, "sign_blue", seg=24, lod=1)),
        SKU("cmilk", lambda: can(0.038, 0.083, "sign_white", seg=24, band="sign_blue", pull=True), 0.078, 0.078, 0.083, (2, 4), 2, 3, True),
        SKU("tuna", lambda: can(0.043, 0.039, "sign_blue", seg=24, band="paint_yellow", style="litho", pull=True), 0.088, 0.088, 0.039,
            (2, 4), 2, 4, True),
        SKU("sardine", lambda: oval_can(), 0.068, 0.108, 0.03, (2, 3), 2, 5, False, rz=90.0),
        SKU("juice", lambda: can(0.042, 0.122, "paint_green", seg=24, band="paint_yellow", style="litho"), 0.086, 0.086, 0.122, (2, 4), 2, 1,
            True),
        SKU("coffee", lambda: glass_jar(0.04, 0.13, fill="cardboard", label="sign_red", lid="sign_red", band="paint_yellow"), 0.083, 0.083,
            0.133, (2, 3), 2, 1, True),
        SKU("salsa", lambda: glass_jar(0.032, 0.11, fill="sign_red", label="paper", lid="paint_yellow", band="sign_green"), 0.067, 0.067,
            0.113, (3, 5), 2, 1, True),
    ]


def _cat_dry():
    return [
        SKU("rice", lambda: pillow_bag(0.2, 0.13, 0.05, mat="plastic", band="sign_red", seed=21, nu=16, nv=9, seal=0.018), 0.135, 0.205,
            0.05, (2, 4), 2, 3, False, rz=90.0),
        SKU("beansbag", lambda: pillow_bag(0.2, 0.13, 0.05, mat="plastic", band="paint_yellow", seed=22, nu=16, nv=9, seal=0.018), 0.135,
            0.205, 0.05, (2, 3), 2, 3, False, rz=90.0),
        SKU("lentil", lambda: pillow_bag(0.17, 0.11, 0.045, mat="plastic", band="sign_green", seed=23, nu=16, nv=9, seal=0.016), 0.115,
            0.175, 0.045, (2, 3), 2, 3, False, rz=90.0),
        SKU("flour", lambda: paper_bag(0.115, 0.07, 0.23, band="sign_blue", seed=31), 0.12, 0.075, 0.23, (2, 4), 2, 1, False),
        SKU("masa", lambda: paper_bag(0.12, 0.075, 0.25, band="sign_red", seed=32), 0.125, 0.08, 0.25, (2, 3), 2, 1, False),
        SKU("sugar", lambda: stand_pouch(0.14, 0.065, 0.22, mat="sign_white", band="sign_blue", seed=3), 0.15, 0.07, 0.22, (2, 3), 2, 1,
            False),
        SKU("oil", lambda: oil_bottle(), 0.084, 0.084, 0.29, (2, 4), 2, 1, True),
        SKU("salt", lambda: salt_canister(), 0.093, 0.093, 0.137, (2, 4), 2, 1, True),
        SKU("pasta", lambda: pillow_bag(0.17, 0.09, 0.028, mat="plastic", band="paint_yellow", seed=41, nu=14, nv=8, seal=0.014, zr=0.45),
            0.095, 0.175, 0.028, (3, 5), 2, 4, False, rz=90.0),
        SKU("cookies", lambda: pillow_bag(0.21, 0.065, 0.048, mat="sign_red", band="sign_white", seed=42, nu=16, nv=8, seal=0.016, zr=0.5),
            0.215, 0.07, 0.048, (1, 2), 2, 3, False),
        SKU("oats", lambda: box_pack(0.13, 0.06, 0.2, mat="sign_white", band="paint_yellow", top_mat="sign_blue"), 0.133, 0.063, 0.2,
            (2, 3), 2, 1, False),
        SKU("cereal", lambda: box_pack(0.19, 0.07, 0.27, mat="paint_yellow", band="sign_red"), 0.193, 0.073, 0.27, (1, 2), 2, 1, False),
    ]


def _cat_household():
    return [
        SKU("soap", lambda: pillow_bag(0.09, 0.06, 0.03, mat="paper", band="sign_green", seed=51, nu=10, nv=7, seal=0.008, zr=0.5,
                                       crimp=False), 0.065, 0.095, 0.03, (3, 6), 2, 4, False, rz=90.0),
        SKU("detergent", lambda: stand_pouch(0.17, 0.08, 0.26, mat="sign_blue", band="sign_white", seed=5), 0.18, 0.085, 0.26, (2, 3), 2, 1,
            False),
        SKU("bulbs", lambda: box_pack(0.065, 0.065, 0.12, mat="sign_white", band="sign_blue"), 0.068, 0.068, 0.12, (3, 6), 2, 2, False),
        SKU("coils", lambda: box_pack(0.14, 0.14, 0.035, mat="sign_green", band="sign_red", top_mat="sign_green"), 0.143, 0.143, 0.035,
            (1, 2), 2, 5, False),
        SKU("matches", lambda: box_pack(0.055, 0.035, 0.016, mat="paint_yellow", band="sign_red"), 0.058, 0.04, 0.016, (4, 8), 2, 6, False),
        SKU("candle", lambda: jar_candle("sign_white"), 0.06, 0.062, 0.2, (3, 5), 2, 1, True),
        SKU("candle_r", lambda: jar_candle("sign_red"), 0.06, 0.062, 0.2, (2, 4), 2, 1, True),
        SKU("tp", lambda: tp_pack(), 0.218, 0.218, 0.102, (1, 3), 2, 2, False),
    ]


def _fill_level(P, r, H, cat, x0, x1, y0, y1, z, zmax, gap=0.12):
    """Llena un entrepaño con bloques de producto (frentes de 1-8, varias filas de fondo, estibas) y huecos de lo vendido; la
    fila de enfrente es prioridad 0, las estibas 1 y las filas traseras 2 (el presupuesto quita primero lo de atrás)."""
    x = x0 + _f(r.uniform(0.0, 0.012))
    last = None
    while x < x1 - 0.05:
        if last is not None and r.random() < gap:
            x += _f(r.uniform(0.05, 0.13))
            last = None
            continue
        opts = [k for k in cat if k.h < zmax - z - 0.01 and k.w < x1 - x and k is not last]
        if not opts:
            break
        sku = opts[int(r.integers(0, len(opts)))]
        last = sku
        nf = int(r.integers(sku.f[0], sku.f[1] + 1))
        nf = max(1, min(nf, int((x1 - x) / (sku.w + 0.002))))
        rows = max(1, min(sku.rows, int((y1 - y0 - 0.006) / (sku.d + 0.004))))
        nst = max(1, min(sku.stack, int((zmax - z) / (sku.h + 0.0006))))
        hero = H.get(("sku", sku.key), sku.fn)
        back = H.get(("skub", sku.key), sku.back) if sku.back else hero
        for fi in range(nf):
            cx = x + sku.w / 2 + fi * (sku.w + 0.002) + _jit(r, 0.0015)
            for row in range(rows):
                cy = y0 + 0.004 + sku.d / 2 + row * (sku.d + 0.004) + _jit(r, 0.002)
                ns = nst if row == 0 else int(r.integers(1, nst + 1))
                below = None
                for st in range(ns):
                    rz = _f(r.uniform(0, 360)) if sku.round else sku.rz + _jit(r, 4)
                    h_ = hero if (row == 0 or not sku.back) else back
                    below = _put(P, h_, cx + _jit(r, 0.002 * st), cy + _jit(r, 0.002 * st), z + st * (sku.h + 0.0004), rz=rz,
                                 prio=(0 if st == 0 else 1) if row == 0 else 2, on=below)
        x += nf * (sku.w + 0.002) + _f(r.uniform(0.008, 0.03))


def _stock_canned(mb, r, H, x0, x1, y0, y1, z, zmax, kind):
    """Abarrotes enlatados: latas de frijol, chiles, elote, puré, leche evaporada y condensada, atún, sardina oval y jugo;
    frascos de café y salsa; huecos de lo vendido; abajo latas grandes y refresco de 2 L; arriba cajas cerradas."""
    if kind == "top":
        x = x0 + _f(r.uniform(0.0, 0.03))
        while x < x1 - 0.2:
            cw, cd, ch = _f(r.uniform(0.24, 0.34)), _f(r.uniform(0.26, 0.33)), _f(r.uniform(0.14, 0.24))
            if x + cw > x1:
                break
            hero = H.get(("carton", round(cw, 2), round(cd, 2), round(ch, 2)), lambda: carton(cw, cd, ch, seed=int(r.integers(0, 99))))
            _put(mb, hero, x + cw / 2, (y0 + y1) / 2 + _jit(r, 0.02), z, rz=_jit(r, 3))
            x += cw + _f(r.uniform(0.01, 0.06))
        return
    if kind == "bottom":
        cat = [SKU("lard", lambda: can(0.05, 0.142, "paint_yellow", seg=28, band="sign_red", style="litho"), 0.102, 0.102, 0.142, (2, 3), 3,
                   2, True),
               SKU("soda", lambda: soda_bottle(label="sign_red", cap="sign_red", fill="amber"), 0.112, 0.112, 0.32, (2, 4), 3, 1, True),
               SKU("soda2", lambda: soda_bottle(label="sign_green", cap="sign_green", fill="glass"), 0.112, 0.112, 0.32, (2, 3), 3, 1, True)]
        _fill_level(mb, r, H, cat, x0, x1, y0, y1, z, zmax, gap=0.05)
        return
    _fill_level(mb, r, H, _cat_canned(), x0, x1, y0, y1, z, zmax)


def _stock_dry(mb, r, H, x0, x1, y0, y1, z, zmax, kind, lvl):
    """Abarrotes secos: costales abajo; bolsas de arroz, frijol y lenteja acostadas en pilas, harina y masa en bolsa de papel,
    azúcar en bolsa de pie, aceite, sal, sopa de pasta, galletas, avena y cereal en caja; arriba cajas y un costal."""
    if kind == "bottom":
        x = x0 + 0.005
        for k in range(2):
            L, W, T = 0.56, 0.34, 0.13
            if x + L > x1 + 0.02:
                break
            hero = H.get(("sack", k), lambda: pillow_bag(L, W, T, mat="burlap", band=None, seed=7 + k, nu=22, nv=12, seal=0.035,
                                                          zr=0.42, wr=0.006, crimp=False))
            _put(mb, hero, x + L / 2, (y0 + y1) / 2 + _jit(r, 0.01), z, rz=_jit(r, 4))
            x += L + 0.015
        return
    if kind == "top":
        x = x0 + 0.01
        hero = H.get(("sack_top",), lambda: pillow_bag(0.5, 0.32, 0.12, mat="burlap", seed=11, nu=22, nv=12, seal=0.035, zr=0.42,
                                                       wr=0.006, crimp=False))
        _put(mb, hero, x + 0.25, (y0 + y1) / 2, z, rz=_jit(r, 8))
        x += 0.53
        cw, cd, ch = 0.3, 0.3, 0.2
        hero = H.get(("carton_dry",), lambda: carton(cw, cd, ch, seed=3))
        if x + cw < x1:
            _put(mb, hero, x + cw / 2, (y0 + y1) / 2, z, rz=_jit(r, 4))
        return
    _fill_level(mb, r, H, _cat_dry(), x0, x1, y0, y1, z, zmax)


def _stock_household(mb, r, H, x0, x1, y0, y1, z, zmax, kind, lvl):
    """Mercería y ferretería: garrafas de cloro y soga abajo; jabón en barra, detergente, focos, espirales contra mosquito,
    cerillos, veladoras, papel higiénico y pilas; un entrepaño de herramienta (machetes, martillos, clavos, soga); arriba cajas."""
    if kind == "bottom":
        x = x0 + 0.005
        for k in range(4):
            hero = H.get(("jug",), lambda: jug())
            _put(mb, hero, x + 0.074, y0 + 0.08 + (0.0 if k % 2 == 0 else 0.15), z, rz=_jit(r, 12) + (0 if k % 2 else 90))
            x += 0.15 if k % 2 else 0.0
        x += 0.02
        hero = H.get(("rope",), lambda: rope_coil(seed=5))
        _put(mb, hero, x + 0.14, (y0 + y1) / 2, z, rz=_f(r.uniform(0, 360)))
        x += 0.31
        if x + 0.25 < x1:
            hero = H.get(("cart_h",), lambda: carton(0.25, 0.25, 0.2, seed=9, open_flaps=(78, 98)))
            _put(mb, hero, x + 0.125, (y0 + y1) / 2, z, rz=_jit(r, 4))
        return
    if kind == "top":
        x = x0 + 0.01
        for k in range(3):
            cw = _f(r.uniform(0.25, 0.32))
            if x + cw > x1:
                break
            hero = H.get(("carton_hh", k), lambda: carton(cw, 0.3, _f(r.uniform(0.15, 0.25)), seed=40 + k))
            _put(mb, hero, x + cw / 2, (y0 + y1) / 2, z, rz=_jit(r, 4))
            x += cw + 0.03
        return
    if lvl % 3 == 0:                                            # herramienta: machetes al frente, martillos detrás, clavos, soga
        x = x0 + 0.16
        for k in range(2):
            _put(mb, H.get(("mach",), lambda: machete()), x + k * 0.03, y0 + 0.03 + k * 0.022, z + 0.0011 + k * 0.0102,
                 rz=_jit(r, 2) + k * 3)
        for k in range(2):
            _put(mb, H.get(("ham",), lambda: hammer()), x0 + 0.1 + k * 0.17, y0 + 0.062, z + 0.0118, rz=90 + _jit(r, 5))
        x = x0 + 0.68
        for k in range(2):
            _put(mb, H.get(("nails",), lambda: carton(0.12, 0.08, 0.07, seed=60, tape=False)), x + 0.06, y0 + 0.05 + k * 0.1, z,
                 rz=_jit(r, 8))
        x += 0.15
        if x + 0.24 < x1:
            _put(mb, H.get(("rope2",), lambda: rope_coil(seed=6, R=0.1, rr=0.007, turns=5.5, mat="burlap")), x + 0.12,
                 (y0 + y1) / 2, z, rz=_f(r.uniform(0, 360)))
        return
    cat = _cat_household()
    if lvl % 3 == 2:                                            # pilas en su exhibidor al principio del entrepaño
        _put(mb, H.get(("batt",), lambda: battery_box(seed=2)), x0 + 0.08, y0 + 0.06, z, rz=_jit(r, 5))
        x0 += 0.17
    _fill_level(mb, r, H, cat, x0, x1, y0, y1, z, zmax)


def grocery_shelving(w=1.2, d=0.40, h=2.0, seed=0, stock="canned"):
    """Anaquel de remache de lámina gris (sin tornillos) contra el muro: postes de ángulo ranurado, largueros con remaches,
    entrepaños de lámina con canal, regatones y escuadra antivuelco; surtido según `stock`:
    "canned" latas (grupos con frentes, fondo, estibas y huecos; cajas arriba), "dry" costales, bolsas de arroz/frijol, bolsas de
    papel de harina, aceite; "household" garrafas de cloro, soga, papel higiénico, veladoras, pilas, herramienta.
    La mercancía son unas cuantas mallas héroe instanciadas con jitter por semilla."""
    r = rng(seed)
    base = MB()
    levels = snap_levels(h, 5, z_first=0.10, z_top=h - 0.08)
    shelving_frame(base, w, d, h, levels)
    mb = Placer(base)
    H = _Heroes()
    x0, x1 = -w / 2 + 0.008, w / 2 - 0.008
    y0, y1 = -d + 0.008, -0.008
    for i, z in enumerate(levels):
        kind = "bottom" if i == 0 else ("top" if i == len(levels) - 1 else "mid")
        zmax = levels[i + 1] - 0.045 if i + 1 < len(levels) else z + 0.32
        zs = z - 0.0006
        if stock == "canned":
            _stock_canned(mb, r, H, x0, x1, y0, y1, zs, zmax, kind)
        elif stock == "dry":
            _stock_dry(mb, r, H, x0, x1, y0, y1, zs, zmax, kind, i)
        else:
            _stock_household(mb, r, H, x0, x1, y0, y1, zs, zmax, kind, i)
    mb.flush(r, 48000)
    return base


# ======================================================================================================== refrigerador de cerveza
def beer_bottle(lod=0, cap=True, empty=False, seg=14):
    """Botella ámbar de cuello largo de 355 ml (Ø 62 × 230 mm): fondo con picón, talón, cuerpo, hombro, cuello largo, corona con
    corcholata de acero (o boca abierta con hueco si empty). lod=1: perfil reducido para filas traseras / dentro de jaba."""
    mb = MB()
    if empty:
        prof = [(0.031, 0.0), (0.031, 0.118), (0.0215, 0.152), (0.0135, 0.172), (0.0122, 0.216), (0.0145, 0.2185), (0.0145, 0.2245),
                (0.0092, 0.2255), (0.0088, 0.214), (0.0, 0.207)]
        if lod == 0:
            prof = [(0.0, 0.004), (0.027, 0.0), (0.031, 0.006)] + prof[1:]
        else:
            prof = prof[:5] + [(0.0145, 0.2215), (0.0092, 0.2255), (0.0, 0.21)]
        revolve(mb, prof, "amber", seg=seg)
        return mb
    if lod == 0:
        prof = [(0.0, 0.004), (0.027, 0.0), (0.031, 0.006), (0.031, 0.118), (0.026, 0.142), (0.0145, 0.168), (0.0122, 0.214),
                (0.0146, 0.2175), (0.0152, 0.22), (0.0152, 0.2265), (0.012, 0.2285), (0.0, 0.2285)]
        mats = ["amber"] * 7 + ["steel"] * 4
    else:
        prof = [(0.031, 0.0), (0.031, 0.118), (0.0145, 0.168), (0.0122, 0.214), (0.0152, 0.22), (0.0152, 0.2265), (0.0, 0.2285)]
        mats = ["amber"] * 3 + ["steel"] * 3
    revolve(mb, prof, mats, seg=seg)
    return mb


def beer_can(lod=0, seg=14):
    """Lata de aluminio de 355 ml sin etiqueta (Ø 66 × 122 mm): fondo de domo, hombro cónico, cuello y ceja; tapa rehundida
    con anillo abre-fácil."""
    mb = MB()
    if lod == 0:
        prof = [(0.0, 0.009), (0.025, 0.0), (0.033, 0.011), (0.033, 0.108), (0.0295, 0.1185), (0.0285, 0.1222), (0.0262, 0.1198),
                (0.0, 0.1198)]
    else:
        prof = [(0.033, 0.0), (0.033, 0.108), (0.0295, 0.1185), (0.0285, 0.1222), (0.0262, 0.1198), (0.0, 0.1198)]
    revolve(mb, prof, "aluminium", seg=seg)
    if lod == 0:
        board(mb, -0.006, 0.012, -0.0045, 0.0045, 0.1196, 0.1208, "aluminium", rc=0.004, re=0.0004, M=_Rz(25))   # anillo
    return mb


def wire_shelf(mb, x0, x1, y0, y1, z, pitch=0.032, rw=0.0022, lip=0.03):
    """Parrilla de alambre: marco perimetral Ø 5 con ceja frontal levantada (tope de botellas), alambres longitudinales Ø 4,4
    sobre 2 travesaños, soldados por contacto."""
    R = 0.0025
    rim = rr_pts(x1 - x0, y1 - y0, 0.012, 2)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tube(mb, [(cx + x, cy + y, z) for (x, y) in rim] + [(cx + rim[0][0], cy + rim[0][1], z)], R, seg=5, mat="steel")
    tube(mb, [(x0 + 0.004, y0, z + lip), (x1 - 0.004, y0, z + lip)], R, seg=5, mat="steel")                 # tope frontal
    for x in (x0 + 0.004, x1 - 0.004):
        tube(mb, [(x, y0, z), (x, y0, z + lip)], R * 0.8, seg=4, mat="steel")
    for yy in (y0 + 0.12, y1 - 0.12):
        cyl(mb, (x0 + 0.002, yy, z - R - 0.0018), (x1 - 0.002, yy, z - R - 0.0018), 0.002, seg=4, mat="steel")
    n = int((x1 - x0 - 0.02) / pitch)
    for i in range(1, n + 1):
        x = x0 + (x1 - x0) * i / (n + 1)
        cyl(mb, (x, y0 + 0.002, z), (x, y1 - 0.002, z), rw, seg=4, mat="steel")


def _condensing_unit(mb, W, yf, D, z0, z1, r):
    """Unidad condensadora inferior de refrigerador comercial (montaje inferior, aire por el frente), dentro del cuarto de
    máquina de z0 a z1: charola base de lámina con ceja, compresor hermético (domo de dos cascos con cordón de soldadura, patas
    con ojillos de hule y tornillos, caja de terminales con tapa y cable), serpentín condensador de tubo de cobre Ø 3/8" con
    curvas en U y aletas de aluminio cada 3 mm entre dos placas porta-tubos, ventilador axial de 5 aspas con anillo-tobera,
    motor y soporte, filtro deshidratador, tubo capilar enrollado, líneas de succión y descarga que suben al evaporador, charola
    de deshielo con su lazo de gas caliente y cordón con prensacable atrás."""
    xa, xb = -W / 2 + 0.05, W / 2 - 0.05
    # charola base
    board(mb, xa, xb, yf + 0.06, D / 2 - 0.06, z0, z0 + 0.0015, "steel", rc=0.004, re=0.0007)
    for x in (xa, xb - 0.0015):
        board(mb, x, x + 0.0015, yf + 0.06, D / 2 - 0.06, z0, z0 + 0.025, "steel", rc=0.001, re=0.0007)
    # serpentín condensador detrás de la rejilla (cara a 5 cm del frente)
    yc0, yc1 = yf + 0.075, yf + 0.115
    cx0, cx1 = xa + 0.035, xb - 0.035
    cz0, cz1 = z0 + 0.03, z1 - 0.02
    for x in (cx0, cx1):                                         # placas porta-tubos
        board(mb, x - 0.0008, x + 0.0008, yc0 - 0.004, yc1 + 0.004, cz0 - 0.006, cz1 + 0.006, "steel", rc=0.001, re=0.0006)
        for (y, z) in ((yc0 + 0.01, cz0 + 0.004), (yc1 - 0.01, cz1 - 0.004)):
            screw_lo(mb, _T(x - 0.001, y, z) @ _Ry(-90), d=0.006)
    x = cx0 + 0.003
    while x < cx1 - 0.002:                                       # aletas de aluminio de 0,15 mm a cada 3 mm
        mb.box((x - 0.0001, yc0, cz0), (x + 0.0001, yc1, cz1), "aluminium", bevel=0.0)
        x += 0.003
    rows = [(yc0 + 0.01, 0.0), (yc1 - 0.01, 0.5)]
    npass = 6
    for (y, off) in rows:                                        # dos filas de tubo con curvas en U alternadas a cada lado
        zs = [cz0 + 0.012 + (cz1 - cz0 - 0.024) * (k + off * 0.5) / (npass - 0.5) for k in range(npass)]
        for k in range(npass):
            tube(mb, [(cx0 - 0.004, y, zs[k]), (cx1 + 0.004, y, zs[k])], 0.0048, mat="copper", caps=False)
        for k in range(npass - 1):
            xe = cx1 + 0.004 if k % 2 == 0 else cx0 - 0.004
            sg = 1 if k % 2 == 0 else -1
            zc_, rr_ = (zs[k] + zs[k + 1]) / 2, (zs[k + 1] - zs[k]) / 2
            arc = [(xe + sg * rr_ * math.sin(PI * j / 10), y, zc_ - rr_ * math.cos(PI * j / 10)) for j in range(11)]
            tube(mb, arc, 0.0048, mat="copper", caps=False)
    # ventilador axial con anillo-tobera, detrás del serpentín
    fy = yc1 + 0.05
    fx, fz = 0.0, (z0 + z1) / 2 + 0.005
    Rf = min(0.085, (z1 - z0) / 2 - 0.012)
    Mfan = _T(fx, fy, fz) @ _Rx(90)
    revolve(mb, [(Rf + 0.004, -0.018), (Rf + 0.004, 0.012), (Rf + 0.012, 0.02), (Rf + 0.03, 0.022), (Rf + 0.03, 0.024),
                 (Rf + 0.0105, 0.0225), (Rf + 0.0025, 0.0135), (Rf + 0.0025, -0.018)], "plastic", seg=64, M=Mfan, closed=True)
    board(mb, fx - Rf - 0.03, fx + Rf + 0.03, fy + 0.0215, fy + 0.0235, fz - Rf - 0.03, fz + Rf + 0.03, "plastic", rc=0.01,
          re=0.0008, M=None)
    for k in range(5):                                           # aspas de lámina estampada (torcidas)
        a = 2 * PI * k / 5 + 0.3
        blade = [(0.018, -0.012), (Rf - 0.004, -0.03), (Rf - 0.002, 0.018), (0.02, 0.012)]
        Mb_ = Mfan @ _Rz(math.degrees(a)) @ _T(0, 0, 0.0) @ _Rx(18)
        mb.plate(blade, 0.0012, "aluminium", m=Mb_)
    revolve(mb, [(0.0, -0.004), (0.02, -0.004), (0.022, 0.002), (0.02, 0.008), (0.0, 0.009)], "aluminium", seg=24, M=Mfan)
    revolve(mb, [(0.0, 0.009), (0.034, 0.012), (0.036, 0.02), (0.036, 0.06), (0.032, 0.068), (0.0, 0.07)], "gunmetal", seg=32, M=Mfan)
    for k in range(3):                                           # soporte del motor (tres brazos de solera)
        a = 2 * PI * k / 3 + 0.5
        p0 = Mfan @ Vector((0.03 * math.cos(a), 0.03 * math.sin(a), 0.05))
        p1 = Mfan @ Vector(((Rf + 0.02) * math.cos(a), (Rf + 0.02) * math.sin(a), 0.022))
        rtube_lo(mb, tuple(p0), tuple(p1), 0.012, 0.0025, "steel", up=(0, 1, 0), r=0.0008)
    # compresor hermético
    cxp, cyp = -0.13, D / 2 - 0.17
    revolve(mb, [(0.0, 0.0), (0.09, 0.0), (0.092, 0.003), (0.092, 0.006), (0.0, 0.006)], "gunmetal", seg=48,
            M=_T(cxp, cyp, z0 + 0.0015) @ Matrix.Diagonal((1.0, 0.75, 1.0, 1.0)))            # base del compresor
    for (dx, dy) in ((-0.07, -0.05), (0.07, -0.05), (-0.07, 0.05), (0.07, 0.05)):
        Mg = _T(cxp + dx, cyp + dy, z0 + 0.0015)
        revolve(mb, [(0.0, 0.0), (0.012, 0.0), (0.013, 0.004), (0.009, 0.007), (0.012, 0.01), (0.013, 0.016), (0.0, 0.016)], "rubber",
                seg=20, M=Mg)
        hexnut(mb, Mg @ _T(0, 0, 0.016), s=0.011, h=0.006, mat="steel")
    zc0 = z0 + 0.018
    Rc, Hc_ = 0.072, min(0.19, z1 - z0 - 0.03)
    prof = [(0.0, zc0), (0.045, zc0), (Rc * 0.92, zc0 + 0.006), (Rc, zc0 + 0.025), (Rc, zc0 + Hc_ * 0.48), (Rc + 0.003, zc0 + Hc_ * 0.5),
            (Rc, zc0 + Hc_ * 0.52), (Rc, zc0 + Hc_ * 0.8), (Rc * 0.9, zc0 + Hc_ * 0.94), (Rc * 0.6, zc0 + Hc_), (0.0, zc0 + Hc_ + 0.004)]
    revolve(mb, prof, "gunmetal", seg=64, M=_T(cxp, cyp, 0.0))
    Mt = _T(cxp + Rc - 0.004, cyp, zc0 + Hc_ * 0.55) @ _Ry(90)          # caja de terminales
    slab(mb, Mt @ _T(0, 0, 0.0), 0.06, 0.07, 0.03, rc=0.008, re=0.004, mat="plastic")
    hose(mb, [(cxp + Rc + 0.026, cyp + 0.01, zc0 + Hc_ * 0.55), (cxp + Rc + 0.05, cyp + 0.04, zc0 + Hc_ * 0.55),
              (cxp + Rc + 0.05, D / 2 - 0.07, z0 + 0.03), (0.2, D / 2 - 0.07, z0 + 0.03)], 0.0045, bend=0.03, mat="cable")
    # líneas de refrigerante: descarga al condensador, succión que sube al evaporador, filtro y capilar
    tube_d = [(cxp + 0.03, cyp - 0.02, zc0 + Hc_ * 0.86), (cxp + 0.03, cyp - 0.09, zc0 + Hc_ * 0.86 + 0.01), (cx0 - 0.004, cyp - 0.09, cz1 - 0.012),
              (cx0 - 0.004, yc0 + 0.01, cz1 - 0.012)]
    hose(mb, tube_d, 0.0032, bend=0.025, mat="copper")
    tube_s = [(cxp - 0.03, cyp + 0.02, zc0 + Hc_ * 0.9), (cxp - 0.03, cyp + 0.05, zc0 + Hc_ + 0.02), (cxp - 0.03, D / 2 - 0.09, z1 - 0.005),
              (cxp - 0.03, D / 2 - 0.09, z1 + 0.02)]
    hose(mb, tube_s, 0.0048, bend=0.03, mat="copper")
    fx0 = cx1 - 0.05                                             # filtro deshidratador vertical junto al serpentín
    revolve(mb, [(0.0, -0.055), (0.003, -0.055), (0.009, -0.045), (0.0095, -0.042), (0.0095, 0.042), (0.009, 0.045), (0.003, 0.055),
                 (0.0, 0.055)], "copper", seg=24, M=_T(fx0, yc1 + 0.02, (z0 + z1) / 2))
    hose(mb, [(fx0, yc1 + 0.02, (z0 + z1) / 2 + 0.055), (fx0, yc1 + 0.02, z1 - 0.004), (fx0 - 0.02, D / 2 - 0.09, z1 - 0.004),
              (fx0 - 0.02, D / 2 - 0.09, z1 + 0.02)], 0.0012, bend=0.02, mat="copper")
    cap = [(fx0 - 0.02 + 0.022 * math.cos(2 * PI * k / 14), D / 2 - 0.12 + 0.022 * math.sin(2 * PI * k / 14), z1 - 0.03 + 0.0015 * k / 14 * 4)
           for k in range(14 * 3)]
    tube(mb, cap, 0.0012, mat="copper")
    # charola de deshielo con lazo de gas caliente
    tx0, tx1, ty0, ty1 = 0.05, xb - 0.02, D / 2 - 0.2, D / 2 - 0.08
    board(mb, tx0, tx1, ty0, ty1, z1 - 0.06, z1 - 0.058, "steel", rc=0.006, re=0.0006)
    for (a_, b_) in (((tx0, ty0), (tx1, ty0 + 0.0012)), ((tx0, ty1 - 0.0012), (tx1, ty1)), ((tx0, ty0), (tx0 + 0.0012, ty1)),
                     ((tx1 - 0.0012, ty0), (tx1, ty1))):
        board(mb, a_[0], b_[0], a_[1], b_[1], z1 - 0.06, z1 - 0.025, "steel", rc=0.0005, re=0.0005)
    loop = [(tx0 + 0.02, ty0 + 0.02, z1 - 0.052), (tx1 - 0.02, ty0 + 0.02, z1 - 0.052), (tx1 - 0.02, ty1 - 0.02, z1 - 0.052),
            (tx0 + 0.02, ty1 - 0.02, z1 - 0.052), (tx0 + 0.02, ty0 + 0.05, z1 - 0.052)]
    hose(mb, loop, 0.0032, bend=0.02, mat="copper")
    hose(mb, [(0.10, D / 2 - 0.075, z1 + 0.01), (0.10, D / 2 - 0.075, z1 - 0.03)], 0.007, bend=0.01, mat="plastic")      # desagüe


def _louvered_panel(mb, M, w, h, n, t=0.0012, mat="enamel", frame=0.014):
    """Tapa de rejilla del cuarto de máquina: lámina doblada (marco perimetral) con n persianas estampadas abiertas hacia abajo
    (aire por el frente) y ranuras pasantes: a través de ellas se ve el serpentín. Plano XY local, cara vista +Z."""
    holed(mb, M, (0, 0, w / 2, h / 2, 0.006), (0, 0, w / 2 - frame, h / 2 - frame, 0.002), t * 4, re_o=0.002, re_i=0.0012, n=40,
          mat=mat, ne=2, ctr=(0, 0))
    ih = h - 2 * frame
    pitch = ih / n
    for k in range(n):
        y = -ih / 2 + pitch * (k + 0.5)
        Ms = M @ _T(0, y, t * 2) @ _Rx(-38)
        slab(mb, Ms @ _T(0, 0, -t / 2), w - 2 * frame + 0.002, pitch * 0.62, t, rc=0.001, re=0.0005, mat=mat)
    for x in (-w / 2 + frame * 0.5, w / 2 - frame * 0.5):        # tornillos de la tapa
        screw_lo(mb, M @ _T(x, 0, t * 4), d=0.0065)


def beer_cooler(seed=0):
    """Refrigerador vertical de puerta de vidrio para bebidas (enfriador comercial de una puerta, montaje inferior: 0,65 × 0,65 ×
    2,0; cf. MainStreet GMC-12 0,60 × 0,60 × 1,90 y Hoshizaki RM-26 0,76 × 0,76 × 2,03), origen al centro de la huella, frente -Y:
    gabinete de lámina con cantos redondeados, marco frontal, puerta de perfil de aluminio con doble vidrio, empaque magnético,
    jaladera de barra con bases, bisagras de pivote y chapa; interior con forro, cremalleras y 4 parrillas de alambre llenas de
    botellas ámbar y latas (frentes completos, fondo a medias); copete superior iluminado con la palabra COLD en relieve;
    cuarto de máquina abajo (23 cm) con tapa de rejilla de persianas por la que respira y deja ver la UNIDAD CONDENSADORA
    (serpentín de cobre con aletas, ventilador, compresor, líneas, charola de deshielo), rejilla de ventilación atrás, patas
    niveladoras y cordón."""
    r = rng(seed)
    base = MB()
    mb = base
    W, D, Hc = 0.65, 0.65, 2.0
    zb, zc = 0.26, 1.79                                          # piso del gabinete (sobre el cuarto de máquina) y copete
    yf = -D / 2
    zf0 = 0.03
    # gabinete: costados, espalda, techo y piso de lámina (forro interior blanco = mismas piezas, cara interior)
    for s in (-1, 1):
        board(mb, min(s * W / 2, s * (W / 2 - 0.045)), max(s * W / 2, s * (W / 2 - 0.045)), yf + 0.035, D / 2, 0.0, zc, "enamel",
              rc=(0.0, 0.0, 0.0, 0.0), re=0.004)
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, D / 2 - 0.05, D / 2, zb, zc, "enamel", rc=0.002, re=0.003)          # espalda
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, yf + 0.035, D / 2 - 0.05, zc - 0.05, zc, "enamel", rc=0.002, re=0.002)
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, yf + 0.035, D / 2 - 0.05, zb, zb + 0.05, "enamel", rc=0.002, re=0.002)
    # cuarto de máquina: unidad condensadora, tapa de rejilla al frente y rejilla de ventilación atrás
    _condensing_unit(mb, W, yf, D, zf0, zb, r)
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, D / 2 - 0.0015, D / 2, zf0, zb, "enamel", rc=0.002, re=0.0008)       # tapa trasera
    louver_grille(mb, _T(0.12, D / 2 + 0.0, (zf0 + zb) / 2) @ _Rx(-90), 0.26, zb - zf0 - 0.07, 8, mat="enamel", back_mat="cable",
                  t=0.004, frame=0.012, slat_ang=40, depth=0.04, nr=24)
    # marco frontal (perímetro del vano de la puerta) y marco de la rejilla
    Mf = _T(0, yf + 0.035, 0) @ _Rx(90)
    rrframe(mb, Mf, (0, (zb + zc) / 2, W, zc - zb, 0.012), (0, (zb + 0.06 + zc - 0.05) / 2, W - 0.09, zc - 0.05 - zb - 0.06, 0.008),
            0.035, re_o=0.006, re_i=0.003, n=3, ne=2, mat="enamel")
    rrframe(mb, Mf, (0, (zf0 + zb) / 2, W, zb - zf0, 0.012), (0, (zf0 + zb) / 2 + 0.004, W - 0.1, zb - zf0 - 0.05, 0.006),
            0.035, re_o=0.006, re_i=0.002, n=3, ne=2, mat="enamel")
    _louvered_panel(mb, _T(0, yf, (zf0 + zb) / 2 + 0.004) @ _Rx(90), W - 0.085, zb - zf0 - 0.035, 9)
    slab(mb, _T(0, 0.0, zc), W + 0.01, D, Hc - zc, rc=(0.014, 0.014, 0.02, 0.02), re=0.008, re0=0.003, mat="enamel", nc=3, ne=2)
    # caja de luz del copete: marco + acrílico + letras COLD en relieve
    yl = -D / 2
    rrframe(mb, _T(0, yl, 0) @ _Rx(90), (0, zc + (Hc - zc) / 2, W - 0.03, Hc - zc - 0.04, 0.008),
            (0, zc + (Hc - zc) / 2, W - 0.09, Hc - zc - 0.08, 0.004), 0.012, re_o=0.004, re_i=0.002, n=2, ne=2, mat="aluminium")
    board(mb, -W / 2 + 0.05, W / 2 - 0.05, yl - 0.006, yl + 0.002, zc + 0.045, Hc - 0.045, "sign_white", rc=0.002, re=0.001)
    etext(mb, "COLD", 0.085, 0.0035, "sign_blue", _T(0, yl - 0.006, zc + (Hc - zc) / 2 - 0.03) @ _Rx(90), res=2, back=False,
          bold=True)
    for x in (-W / 2 + 0.06, W / 2 - 0.06):
        for y in (yf + 0.07, D / 2 - 0.07):
            foot_leveler(mb, _T(x, y, 0.0), r=0.02, h=0.035)
    # puerta: perfil de aluminio con doble vidrio, empaque, jaladera, bisagras y chapa
    yd = yf - 0.008                                              # cara trasera de la puerta (el empaque llena la holgura)
    dz0, dz1 = zb + 0.012, zc - 0.012
    Md = _T(0, yd, 0) @ _Rx(90)
    zcd = (dz0 + dz1) / 2
    rrframe(mb, Md, (0, zcd, W - 0.012, dz1 - dz0, 0.01), (0, zcd + 0.01, W - 0.012 - 0.11, dz1 - dz0 - 0.15, 0.006), 0.042,
            re_o=0.006, re_i=0.004, n=3, ne=2, mat="aluminium")
    for gy in (yd - 0.012, yd - 0.030):
        board(mb, -W / 2 + 0.06, W / 2 - 0.06, gy - 0.004, gy, dz0 + 0.06, dz1 - 0.04, "glass", rc=0.004, re=0.0015)
    path = [(x, yf - 0.004, zcd + z) for (x, z) in rr_pts(W - 0.04, dz1 - dz0 - 0.03, 0.014, 4)]
    mb.sweep([(u, v) for (u, v) in rr_pts(0.016, 0.009, 0.0035, 4)], path, mat="rubber", closed_path=True, normal=(0, 1, 0))
    xh = W / 2 - 0.035
    yh = yd - 0.042
    hose(mb, [(xh, yh + 0.002, 0.82), (xh, yh - 0.045, 0.82), (xh, yh - 0.045, 1.42), (xh, yh + 0.002, 1.42)], 0.011, bend=0.03,
         mat="aluminium", seg=12, nseg=5)
    for z in (0.82, 1.42):
        slab(mb, _T(xh, yh + 0.0005, z) @ _Rx(90), 0.032, 0.045, 0.012, rc=0.012, re=0.004, re0=0.0, mat="plastic", nc=2, ne=2)
    for (za, zb_) in ((dz0 - 0.011, dz0 - 0.002), (dz1 + 0.002, dz1 + 0.0105)):   # bisagras de pivote (izquierda)
        board(mb, -W / 2 + 0.004, -W / 2 + 0.06, yd - 0.04, yf + 0.03, za, zb_, "steel", rc=0.003, re=0.0015)
        for x in (-W / 2 + 0.04, -W / 2 + 0.052):
            screw_lo(mb, _T(x, yf + 0.012, zb_ if za < dz0 else za) @ (Matrix() if za < dz0 else _Rx(180)), d=0.006)
    revolve(mb, [(0.0095, -0.0003), (0.0095, 0.004), (0.0078, 0.0055), (0.006, 0.0055), (0.0058, 0.0042), (0.0, 0.0042)], "steel",
            seg=12, M=_T(xh, yd - 0.042, dz0 + 0.12) @ _Rx(90))      # chapa con cilindro rehundido
    # interior: forro, cremalleras, luz y parrillas
    xi0, xi1 = -W / 2 + 0.05, W / 2 - 0.05
    yi0, yi1 = yf + 0.075, D / 2 - 0.06
    for x in (xi0 - 0.005, xi1 + 0.005):                         # cremalleras de las parrillas
        for y in (yi0 + 0.03, yi1 - 0.03):
            board(mb, x - 0.0075, x + 0.0075, y - 0.012, y + 0.012, zb + 0.05, zc - 0.05, "aluminium", rc=0.002, re=0.001)
            z_ = zb + 0.08
            while z_ < zc - 0.07:                                # ranuras de la cremallera (ceja de lámina)
                mb.box((x - 0.0085, y - 0.006, z_), (x + 0.0085, y + 0.006, z_ + 0.0035), "aluminium", bevel=0.0006)
                z_ += 0.0254
    board(mb, xi0 + 0.04, xi1 - 0.04, yi0 + 0.01, yi0 + 0.04, zc - 0.075, zc - 0.05, "plastic", rc=0.01, re=0.006)   # luz
    levels = [zb + 0.05, 0.62, 0.94, 1.26, 1.56]
    for z in levels[1:]:
        wire_shelf(mb, xi0 + 0.004, xi1 - 0.004, yi0 + 0.005, yi1 - 0.005, z)
    # bebidas (presupuesto)
    P = Placer(base)
    H = _Heroes()
    for i, z in enumerate(levels):
        zs = z + (0.0025 if i else 0.0)
        cans = i in (1, 3)
        pitch = 0.067 if cans else 0.0635
        nx = int((xi1 - xi0 - 0.01) / pitch)
        x_start = (xi0 + xi1) / 2 - (nx - 1) * pitch / 2
        for row in range(int((yi1 - yi0 - 0.02) / pitch)):
            fill = 1.0 if row == 0 else (0.85 if row < 3 else 0.55)
            for k in range(nx):
                if r.random() > fill:
                    continue
                x = x_start + k * pitch + _jit(r, 0.002)
                y = yi0 + 0.04 + row * pitch + _jit(r, 0.002)
                lod = 0 if row == 0 else 1
                fn = beer_can if cans else beer_bottle
                hm = H.get(("c" if cans else "b", lod), lambda: fn(lod=lod))
                _put(P, hm, x, y, zs, rz=_f(r.uniform(0, 360)), prio=0 if row == 0 else (1 if row < 3 else 2))
                if cans and r.random() < 0.6 and i == 1:                     # latas estibadas
                    _put(P, hm, x, y, zs + 0.1222 - 0.004, rz=_f(r.uniform(0, 360)), prio=2)
    # cordón de corriente por detrás (sale del prensacable de la tapa trasera)
    hose(mb, [(0.2, D / 2 - 0.02, 0.09), (0.2, D / 2 + 0.03, 0.09), (0.22, D / 2 + 0.035, 0.0045), (0.3, D / 2 + 0.03, 0.0045),
              (0.31, D / 2 - 0.04, 0.0045)], 0.0045, bend=0.03, mat="cable", seg=6, nseg=4)
    revolve(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.006), (0.006, 0.012), (0.0, 0.012)], "plastic", seg=24, M=_T(0.2, D / 2, 0.09) @ _Rx(-90))
    P.flush(r, 60000)
    return base


# ======================================================================================================== congelador horizontal
def chest_freezer(seed=0):
    """Congelador horizontal blanco 1,2 × 0,65 × 0,85 (origen al centro de la huella, frente -Y): gabinete de lámina con esquinas
    redondeadas sobre zoclo remetido gris, tapa abombada con ceja y junta (empaque visible en la holgura), jaladera moldeada al
    frente con chapa de llave, dos bisagras de contrapeso atrás, rejilla del compresor en la espalda, perilla del termostato y
    piloto en el costado, tapón de desagüe, patas, cordón; golpes leves del uso."""
    r = rng(seed)
    mb = MB()
    W, D, H = 1.2, 0.65, 0.85
    zk, zt = 0.085, 0.775                                        # zoclo, borde superior del gabinete
    slab(mb, _T(0, 0, zk), W, D, zt - zk, rc=0.035, re=0.012, re0=0.006, mat="enamel", nc=4, ne=2)
    slab(mb, _T(0, 0.004, 0.022), W - 0.03, D - 0.03, zk - 0.022 + 0.004, rc=0.025, re=0.004, mat="plastic", nc=3, ne=1)
    for (x, y) in ((-W / 2 + 0.06, -D / 2 + 0.06), (W / 2 - 0.06, -D / 2 + 0.06), (-W / 2 + 0.06, D / 2 - 0.06), (W / 2 - 0.06, D / 2 - 0.06)):
        revolve(mb, [(0.0, 0.0), (0.024, 0.0), (0.026, 0.004), (0.022, 0.022), (0.0, 0.0225)], "rubber", seg=14, M=_T(x, y, 0.0))
    # empaque en la holgura y tapa
    path = [(x, y, zt + 0.004) for (x, y) in rr_pts(W - 0.03, D - 0.03, 0.028, 3)]
    mb.sweep([(u, v) for (u, v) in rr_pts(0.018, 0.008, 0.0035, 1)], path, mat="rubber", closed_path=True, normal=(0, 0, 1))
    zl = zt + 0.0075
    slab(mb, _T(0, 0, zl), W + 0.008, D + 0.008, H - zl - 0.002, rc=0.038, re=0.018, re0=0.004, mat="enamel", nc=4, ne=3)
    slab(mb, _T(0, 0.01, H - 0.0035), W - 0.16, D - 0.17, 0.0035, rc=0.03, re=0.003, re0=0.0, mat="enamel", nc=3, ne=2)  # panel
    slab(mb, _T(W / 2 - 0.16, -D / 2 - 0.0005, zt - 0.075) @ _Rx(90), 0.09, 0.022, 0.0015, rc=0.003, re=0.0006, re0=0.0,
         mat="aluminium", nc=2, ne=1)                            # placa de datos (en blanco)
    for x in (W / 2 - 0.2, W / 2 - 0.12):
        revolve(mb, [(0.0016, -0.0003), (0.0016, 0.0019), (0.0, 0.0024)], "steel", seg=6, M=_T(x, -D / 2 - 0.002, zt - 0.075) @ _Rx(90))
    # jaladera moldeada (bajo la ceja frontal de la tapa) y chapa
    Mh = _T(0, -D / 2 - 0.004, zl + 0.004)
    slab(mb, Mh @ _T(0, -0.012, -0.012), 0.26, 0.03, 0.03, rc=(0.006, 0.006, 0.014, 0.014), re=0.006, re0=0.004, mat="plastic",
         nc=3, ne=2)
    board(mb, -0.11, 0.11, -0.032, -0.02, -0.0125, -0.006, "cable", rc=0.004, re=0.002, M=Mh)       # hueco de los dedos
    revolve(mb, [(0.008, -0.0003), (0.008, 0.004), (0.0065, 0.0052), (0.005, 0.0052), (0.0048, 0.0042), (0.0, 0.0042)], "aluminium",
            seg=12, M=_T(0.2, -D / 2, zt - 0.03) @ _Rx(90))
    # bisagras de contrapeso (carcasa plástica atornillada al gabinete y a la tapa)
    for x in (-W / 2 + 0.2, W / 2 - 0.2):
        slab(mb, _T(x, D / 2 + 0.012, zt - 0.11), 0.07, 0.03, 0.17, rc=0.008, re=0.006, mat="plastic", nc=2, ne=2)
        for z in (zt - 0.09, zt - 0.03):
            screw_lo(mb, _T(x, D / 2 + 0.027, z) @ _Rx(-90), d=0.007)
        board(mb, x - 0.03, x + 0.03, D / 2 - 0.02, D / 2 + 0.027, H - 0.002, H + 0.004, "plastic", rc=0.006, re=0.002)
    # rejilla del compresor en la espalda (lado derecho, abajo)
    louver_grille(mb, _T(W / 2 - 0.2, D / 2, zk + 0.1) @ _Rx(-90), 0.28, 0.14, 8, mat="plastic", back_mat="cable", t=0.008,
                  frame=0.012, slat_ang=40, depth=-0.0006, nr=24)
    # termostato y piloto en el costado derecho
    Ms = _T(W / 2, -0.1, zk + 0.09) @ _Rz(90) @ _Rx(90)
    board(mb, -0.05, 0.05, -0.03, 0.03, -0.0003, 0.004, "plastic", rc=0.008, re=0.002, M=Ms)
    revolve(mb, [(0.017, 0.0035), (0.017, 0.016), (0.015, 0.02), (0.0, 0.021)], "plastic", seg=16, M=Ms @ _T(-0.015, 0, 0))
    board(mb, -0.022, -0.008, -0.004, 0.004, 0.019, 0.0275, "plastic", rc=0.003, re=0.002, M=Ms)
    revolve(mb, [(0.0045, 0.0035), (0.0045, 0.0065), (0.0, 0.008)], "sign_green", seg=10, M=Ms @ _T(0.03, 0, 0))
    # tapón de desagüe (frente izquierdo, abajo)
    revolve(mb, [(0.013, -0.0003), (0.013, 0.006), (0.011, 0.009), (0.0, 0.0095)], "plastic", seg=12,
            M=_T(-W / 2 + 0.12, -D / 2, zk + 0.035) @ _Rx(90))
    # cordón
    hose(mb, [(-W / 2 + 0.15, D / 2, zk + 0.06), (-W / 2 + 0.15, D / 2 + 0.03, zk + 0.06), (-W / 2 + 0.13, D / 2 + 0.04, 0.0045),
              (-W / 2 + 0.03, D / 2 + 0.03, 0.0045)], 0.0045, bend=0.03, mat="cable", seg=6, nseg=4)
    return mb


# ======================================================================================================== báscula de reloj
def hand_scale(seed=0):
    """Báscula de mostrador de reloj (10 kg): base de fundición con patas de hule, cuerpo que sube al reloj, carátula blanca con
    rayas y números, aguja roja, bisel cromado y mica; plato de acero inoxidable con ceja enrollada sobre su soporte."""
    mb = MB()
    # base y cuerpo (fundición pintada)
    slab(mb, _T(0, 0, 0.008), 0.24, 0.2, 0.035, rc=0.03, re=0.012, re0=0.004, mat="enamel", nc=3, ne=2)
    for (x, y) in ((-0.1, -0.08), (0.1, -0.08), (-0.1, 0.08), (0.1, 0.08)):
        revolve(mb, [(0.0, 0.0), (0.011, 0.0), (0.012, 0.004), (0.01, 0.0085), (0.0, 0.0085)], "rubber", seg=8, M=_T(x, y, 0))
    st = [(0.04, 0.2, 0.17, 0.0), (0.06, 0.16, 0.13, 0.0), (0.12, 0.12, 0.085, 0.005), (0.16, 0.14, 0.06, 0.012),
          (0.205, 0.16, 0.05, 0.014)]
    zloft(mb, st, seg=20, mat="enamel", ex=3.0, caps=False)
    # caja del reloj (cilindro de eje Y) y carátula
    zc, Rd = 0.255, 0.105
    Mr = _T(0, 0.0, zc) @ _Rx(90)                                 # z local -> -Y (cara del reloj)
    revolve(mb, [(0.0, -0.06), (Rd * 0.92, -0.06), (Rd, -0.05), (Rd, 0.035), (Rd - 0.004, 0.04)], "enamel", seg=28, M=Mr, caps=False)
    revolve(mb, [(Rd - 0.004, 0.04), (Rd + 0.002, 0.043), (Rd + 0.002, 0.05), (Rd - 0.006, 0.053), (Rd - 0.012, 0.05),
                 (Rd - 0.012, 0.044)], "aluminium", seg=28, M=Mr, caps=False)                     # bisel cromado
    revolve(mb, [(Rd - 0.004, 0.04), (Rd - 0.012, 0.044), (Rd - 0.012, 0.03), (0.0, 0.03)], "sign_white", seg=28, M=Mr, caps=False)
    revolve(mb, [(Rd - 0.0121, 0.047), (0.06, 0.05), (0.0, 0.0515)], "glass", seg=28, M=Mr, caps=False)   # mica abombada
    for k in range(40):                                          # rayas cada 250 g (largas cada kg)
        a = math.radians(225 - 270 * k / 40)
        L = 0.012 if k % 4 == 0 else 0.006
        rr = Rd - 0.016
        c, s_ = math.cos(a), math.sin(a)
        Mt = Mr @ _T(rr * c - L / 2 * c, rr * s_ - L / 2 * s_, 0.0302) @ _Rz(math.degrees(a))
        mb.box((-L / 2, -0.0007 if k % 4 else -0.0011, -0.0005), (L / 2, 0.0007 if k % 4 else 0.0011, 0.0011), "cable", bevel=0.0, m=Mt)
    for k in range(11):
        a = math.radians(225 - 270 * k / 10)
        rr = Rd - 0.036
        etext(mb, str(k), 0.011, 0.0011, "cable", Mr @ _T(rr * math.cos(a), rr * math.sin(a) - 0.004, 0.0298), res=1, back=False)
    etext(mb, "KG", 0.012, 0.0011, "sign_red", Mr @ _T(0, -0.042, 0.0298), res=1, back=False)
    revolve(mb, [(0.0, 0.0302), (0.008, 0.0302), (0.008, 0.034), (0.005, 0.037), (0.0, 0.0375)], "cable", seg=12, M=Mr)
    a = math.radians(225 - 270 * 0.008)                          # aguja en cero (plato vacío)
    Mn = Mr @ _T(0, 0, 0.0345) @ _Rz(math.degrees(a))
    slab(mb, Mn @ _T(0.035, 0, 0), 0.088, 0.003, 0.001, rc=0.0012, re=0.0003, re0=0.0, mat="sign_red", nc=1, ne=1)
    # soporte y plato
    revolve(mb, [(0.0, 0.31), (0.012, 0.31), (0.012, 0.36), (0.0, 0.36)], "steel", seg=10, M=_T(0, 0.02, 0))
    revolve(mb, [(0.0, 0.358), (0.06, 0.358), (0.06, 0.362), (0.0, 0.364)], "steel", seg=16, M=_T(0, 0.02, 0))
    prof = [(0.0, 0.362), (0.1, 0.362), (0.135, 0.37), (0.16, 0.392), (0.166, 0.398), (0.168, 0.402), (0.163, 0.4035), (0.1585, 0.3965),
            (0.133, 0.3745), (0.1, 0.3655), (0.0, 0.3655)]
    revolve(mb, prof, "steel", seg=32, M=_T(0, 0.02, 0) @ Matrix.Diagonal((1.0, 0.82, 1.0, 1.0)))
    return mb


# ======================================================================================================== caja de dinero
def cash_box(seed=0):
    """Caja de dinero de lámina (0,30 × 0,24 × 0,09) con la tapa entreabierta 14°: cuerpo de lámina con ceja enrollada, tapa
    con faldón, bisagra de piano atrás, asa abatible sobre la tapa, chapa al frente y charola de monedas con divisiones."""
    mb = MB()
    W, D, Hb = 0.30, 0.24, 0.065
    t = 0.0012
    outer = [(x, y) for (x, y) in rr_pts(W, D, 0.012, 2)]
    inner = [(x, y) for (x, y) in rr_pts(W - 2 * t, D - 2 * t, 0.011, 2)]
    loops = [[(x, y, 0.0) for (x, y) in outer], [(x, y, Hb - 0.002) for (x, y) in outer],
             [(x * 1.004, y * 1.005, Hb) for (x, y) in outer], [(x, y, Hb) for (x, y) in inner], [(x, y, t) for (x, y) in inner]]
    skin(mb, loops, "steel")
    # charola de monedas (5 divisiones) apoyada en ménsulas
    zt = Hb - 0.03
    board(mb, -W / 2 + 0.006, W / 2 - 0.006, -D / 2 + 0.006, -D / 2 + 0.11, zt, zt + 0.0015, "plastic", rc=0.004, re=0.0006)
    for k in range(6):
        x = -W / 2 + 0.0072 + (W - 0.0144) * k / 5
        mb.box((x - 0.0012, -D / 2 + 0.0086, zt + 0.0015), (x + 0.0012, -D / 2 + 0.1074, zt + 0.025), "plastic", bevel=0.0004, seg=1)
    for y in (-D / 2 + 0.0072, -D / 2 + 0.1088):
        mb.box((-W / 2 + 0.006, y - 0.0012, zt + 0.0015), (W / 2 - 0.006, y + 0.0012, zt + 0.0245), "plastic", bevel=0.0004, seg=1)
    # bisagra de piano: hoja del cuerpo (con calza), nudillos alternados y perno; la tapa gira sobre el perno
    lo_w, lo_d = W + 0.006, D + 0.006
    yh, zh = lo_d / 2 + 0.0012 + 0.0034, Hb - 0.004
    board(mb, -W / 2 + 0.02, W / 2 - 0.02, D / 2 - 0.0003, yh - 0.0034 + 0.0002, Hb - 0.02, zh, "steel", rc=0.002, re=0.0004)
    cyl(mb, (-W / 2 + 0.018, yh, zh), (W / 2 - 0.018, yh, zh), 0.0018, seg=8, mat="steel")
    Ml = _T(0, yh, zh) @ _Rx(-14) @ _T(0, -yh, -zh)
    nk = 5
    for k in range(nk):
        x0_ = -W / 2 + 0.02 + (W - 0.04) * k / nk
        x1_ = -W / 2 + 0.02 + (W - 0.04) * (k + 1) / nk - 0.0008
        Mk_ = (Ml if k % 2 else Matrix()) @ _T(x0_, yh, zh) @ _Ry(90)
        revolve(mb, [(0.0019, 0.0), (0.0034, 0.0), (0.0034, x1_ - x0_), (0.0019, x1_ - x0_)], "steel", seg=7, M=Mk_, closed=True)
    # tapa (cáscara con faldón, 1,5 mm de holgura sobre el cuerpo) girada 14° sobre la bisagra
    Hl = 0.026
    lo = [(x, y) for (x, y) in rr_pts(lo_w, lo_d, 0.013, 2)]
    li = [(x, y) for (x, y) in rr_pts(lo_w - 2 * t, lo_d - 2 * t, 0.012, 2)]
    loops = [[(x * 0.985, y * 0.98, Hb + Hl) for (x, y) in lo], [(x, y, Hb + Hl - 0.006) for (x, y) in lo],
             [(x, y, Hb - 0.008) for (x, y) in lo], [(x, y, Hb - 0.008) for (x, y) in li], [(x, y, Hb + Hl - 0.006 - t) for (x, y) in li],
             [(x * 0.985, y * 0.98, Hb + Hl - t) for (x, y) in li]]
    skin(mb, loops, "steel", M=Ml)
    board(mb, -W / 2 + 0.02, W / 2 - 0.02, lo_d / 2 - 0.0003, lo_d / 2 + 0.0012, zh, Hb + 0.012, "steel", rc=0.002, re=0.0004, M=Ml)
    # asa abatible acostada sobre la tapa, con orejas
    zt2 = Hb + Hl
    for s in (-1, 1):
        board(mb, s * 0.06 - 0.008, s * 0.06 + 0.008, -0.012, 0.012, zt2 - 0.0005, zt2 + 0.009, "steel", rc=0.004, re=0.002, M=Ml)
    tmp = MB()
    hose(tmp, [(-0.06, 0.004, zt2 + 0.006), (-0.06, -0.035, zt2 + 0.006), (0.06, -0.035, zt2 + 0.006), (0.06, 0.004, zt2 + 0.006)],
         0.0035, bend=0.012, mat="steel", seg=7, nseg=4)
    mb.join(tmp, Ml)
    # chapa al frente del faldón
    Mk = Ml @ _T(0, -lo_d / 2, Hb + Hl * 0.45) @ _Rx(90)
    revolve(mb, [(0.0075, -0.0003), (0.0075, 0.003), (0.006, 0.004), (0.0045, 0.004), (0.0043, 0.0032), (0.0, 0.0032)], "aluminium",
            seg=12, M=Mk)
    return mb


# ======================================================================================================== pizarrón de precios
PRICES = (("RICE", "3.00"), ("BEANS", "3.50"), ("OIL", "6.10"), ("FLOUR", "3.00"), ("SALT", "2.50"), ("BATTERIES", "4.00"),
          ("ALCOHOL", "1.10"), ("BANDAGES", "2.00"), ("COLD BEER", "1.50"), ("AMMO", "12.00"))


def _arc(cx, cy, rx, ry, a0, a1, n=None):
    """Arco de elipse de a0 a a1 (grados, con signo: a1 < a0 = sentido horario) como polilínea."""
    n = n or max(4, int(abs(a1 - a0) / 15))
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * k / n)), cy + ry * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


# Letra de gis a mano (trazos de una sola línea, mayúscula de imprenta): por carácter, (ancho, [trazos]) en unidades de la
# altura de mayúscula. Los arcos se dan con _arc. Se escriben con el trazo del gis (ver chalk_text), no con una tipografía.
CHALK = {
    "A": (0.62, [[(0, 0), (0.31, 1), (0.62, 0)], [(0.13, 0.38), (0.49, 0.38)]]),
    "B": (0.58, [[(0, 0), (0, 1)], [(0, 1), (0.3, 1)] + _arc(0.3, 0.755, 0.245, 0.245, 90, -90) + [(0, 0.51)],
                 [(0, 0.51), (0.31, 0.51)] + _arc(0.31, 0.255, 0.255, 0.255, 90, -90) + [(0, 0)]]),
    "C": (0.6, [_arc(0.33, 0.5, 0.33, 0.5, 48, 312)]),
    "D": (0.62, [[(0, 0), (0, 1)], [(0, 1), (0.22, 1)] + _arc(0.22, 0.5, 0.38, 0.5, 90, -90) + [(0, 0)]]),
    "E": (0.52, [[(0.5, 1), (0, 1), (0, 0), (0.52, 0)], [(0, 0.52), (0.4, 0.52)]]),
    "F": (0.5, [[(0.5, 1), (0, 1), (0, 0)], [(0, 0.52), (0.4, 0.52)]]),
    "G": (0.64, [_arc(0.33, 0.5, 0.33, 0.5, 50, 345) + [(0.64, 0.42)], [(0.64, 0.42), (0.38, 0.42)]]),
    "H": (0.56, [[(0, 0), (0, 1)], [(0.56, 0), (0.56, 1)], [(0, 0.52), (0.56, 0.52)]]),
    "I": (0.04, [[(0.02, 0), (0.02, 1)]]),
    "J": (0.46, [[(0.46, 1), (0.46, 0.26)] + _arc(0.24, 0.26, 0.22, 0.26, 0, -170)]),
    "K": (0.54, [[(0, 0), (0, 1)], [(0.52, 1), (0, 0.4)], [(0.17, 0.6), (0.56, 0)]]),
    "L": (0.48, [[(0, 1), (0, 0), (0.48, 0)]]),
    "M": (0.74, [[(0, 0), (0, 1), (0.37, 0.32), (0.74, 1), (0.74, 0)]]),
    "N": (0.58, [[(0, 0), (0, 1), (0.58, 0), (0.58, 1)]]),
    "O": (0.68, [_arc(0.34, 0.5, 0.34, 0.5, 100, 465)]),
    "P": (0.54, [[(0, 0), (0, 1), (0.28, 1)] + _arc(0.28, 0.75, 0.25, 0.25, 90, -90) + [(0, 0.5)]]),
    "Q": (0.68, [_arc(0.34, 0.5, 0.34, 0.5, 100, 465), [(0.42, 0.24), (0.72, -0.06)]]),
    "R": (0.56, [[(0, 0), (0, 1), (0.28, 1)] + _arc(0.28, 0.75, 0.25, 0.25, 90, -90) + [(0, 0.5)], [(0.22, 0.5), (0.56, 0)]]),
    "S": (0.54, [_arc(0.27, 0.75, 0.25, 0.25, 25, 270) + _arc(0.27, 0.25, 0.27, 0.25, 90, -155)[1:]]),
    "T": (0.58, [[(0, 1), (0.58, 1)], [(0.29, 1), (0.29, 0)]]),
    "U": (0.56, [[(0, 1), (0, 0.3)] + _arc(0.28, 0.3, 0.28, 0.3, 180, 360) + [(0.56, 1)]]),
    "V": (0.6, [[(0, 1), (0.3, 0), (0.6, 1)]]),
    "W": (0.8, [[(0, 1), (0.19, 0), (0.4, 0.72), (0.61, 0), (0.8, 1)]]),
    "X": (0.56, [[(0, 1), (0.56, 0)], [(0.56, 1), (0, 0)]]),
    "Y": (0.58, [[(0, 1), (0.29, 0.5), (0.58, 1)], [(0.29, 0.5), (0.29, 0)]]),
    "Z": (0.56, [[(0, 1), (0.56, 1), (0, 0), (0.58, 0)]]),
    "0": (0.5, [_arc(0.25, 0.5, 0.25, 0.5, 100, 465)]),
    "1": (0.3, [[(0.02, 0.78), (0.24, 1), (0.24, 0)]]),
    "2": (0.5, [_arc(0.25, 0.74, 0.24, 0.26, 160, -25) + [(0, 0), (0.52, 0)]]),
    "3": (0.48, [_arc(0.23, 0.76, 0.23, 0.24, 150, -90) + _arc(0.23, 0.26, 0.26, 0.26, 90, -150)[1:]]),
    "4": (0.52, [[(0.38, 0), (0.38, 1), (0, 0.3), (0.54, 0.3)]]),
    "5": (0.5, [[(0.46, 1), (0.07, 1), (0.03, 0.55)] + _arc(0.24, 0.3, 0.26, 0.3, 125, -150)]),
    "6": (0.52, [_arc(0.28, 0.5, 0.28, 0.5, 70, 190) + _arc(0.26, 0.28, 0.26, 0.28, 190, 540)[1:]]),
    "7": (0.5, [[(0, 1), (0.5, 1), (0.16, 0)]]),
    "8": (0.5, [_arc(0.25, 0.76, 0.22, 0.24, 270, 630), _arc(0.25, 0.26, 0.26, 0.26, 90, 450)]),
    "9": (0.5, [_arc(0.24, 0.72, 0.24, 0.28, 0, 365), [(0.48, 0.72), (0.45, 0.3), (0.32, 0)]]),
    ".": (0.08, [[(0.02, 0.0), (0.06, 0.03)]]),
    "$": (0.54, [_arc(0.27, 0.75, 0.25, 0.25, 25, 270) + _arc(0.27, 0.25, 0.27, 0.25, 90, -155)[1:], [(0.28, -0.12), (0.26, 1.12)]]),
    "-": (0.36, [[(0, 0.46), (0.36, 0.47)]]),
    ":": (0.08, [[(0.02, 0.0), (0.06, 0.03)], [(0.02, 0.6), (0.06, 0.63)]]),
    "/": (0.42, [[(0, -0.05), (0.42, 1.05)]]),
}


def _catmull(pts, step):
    """Polilínea suavizada (Catmull-Rom) muestreada a ~`step` (el trazo de la mano, sin quiebres de polígono)."""
    P = [Vector((p[0], p[1], 0.0)) for p in pts]
    if len(P) < 2:
        return P
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        n = max(1, int((p2 - p1).length / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return out


def chalk_stroke(mb, pts, wd, M, rr, h=0.0007, mat="sign_white"):
    """Trazo de gis sobre el plano local XZ (cara del pizarrón en y = 0, relieve hacia -Y): cinta de ancho `wd` con lomo de
    `h` (>= 0,5 mm), presión que varía a lo largo (más ancho al arrancar, se adelgaza al soltar), cantos desmoronados (borde
    irregular) y puntas redondeadas; los cantos entran 0,2 mm en el tablero (sin coplanares ni rendijas). pts: [(x, z)]."""
    P = _catmull(pts, max(wd * 0.8, 0.0025))
    if len(P) < 2:
        P = [Vector((pts[0][0], pts[0][1], 0.0)), Vector((pts[0][0] + wd * 0.3, pts[0][1] + wd * 0.2, 0.0))]
    n = len(P)
    ph = float(rr.uniform(0, 10))
    acc = [0.0]
    for i in range(1, n):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    tot = max(acc[-1], 1e-6)
    rings = []
    for i in range(n):
        t = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)])
        t = t.normalized() if t.length > 1e-9 else Vector((1, 0, 0))
        nrm = Vector((-t.y, t.x, 0.0))
        u = acc[i] / tot
        press = (1.06 - 0.22 * u) * (1.0 + 0.08 * math.sin(acc[i] * 260 + ph))
        w_ = wd * press * (0.55 + 0.45 * min(1.0, acc[i] / (wd * 0.9), (tot - acc[i]) / (wd * 0.9)))
        e0 = 1.0 + float(rr.uniform(-0.12, 0.12))
        e1 = 1.0 + float(rr.uniform(-0.12, 0.12))
        hh = h * (0.8 + 0.2 * press) * (0.7 + 0.3 * min(1.0, acc[i] / wd, (tot - acc[i]) / wd))
        prof = [(-w_ / 2 * e0, -0.0002), (-w_ * 0.3, hh * 0.75), (0.0, hh), (w_ * 0.3, hh * 0.75), (w_ / 2 * e1, -0.0002), (0.0, -0.0004)]
        rings.append([(P[i].x + nrm.x * o, -hz, P[i].y + nrm.y * o) for (o, hz) in prof])
    t0 = (P[1] - P[0]).normalized()
    t1 = (P[-1] - P[-2]).normalized()
    c0 = P[0] - t0 * wd * 0.35
    c1 = P[-1] + t1 * wd * 0.3
    loops = [[(c0.x, -h * 0.25, c0.y)]] + rings + [[(c1.x, -h * 0.2, c1.y)]]
    with mb.soft():
        skin(mb, loops, mat, M)


def chalk_text(mb, txt, size, M, rr, align="LEFT", slant=0.1, wd=None, mat="sign_white"):
    """Texto escrito a mano con gis en el plano local XZ (renglón sobre z = 0, cara del tablero en y = 0): cada letra con su
    giro, tamaño, inclinación y desplazamiento de la línea base; temblor suave del pulso a lo largo de cada trazo."""
    wd = wd or max(0.0032, size * 0.1)
    sp = size * 0.2
    widths = [(CHALK[c][0] if c in CHALK else 0.35) * size for c in txt]
    total = sum(widths) + sp * (len(txt) - 1)
    x = {"LEFT": 0.0, "RIGHT": -total, "CENTER": -total / 2}[align]
    drift = float(rr.uniform(-0.02, 0.02)) * size
    for ci, c in enumerate(txt):
        gw = widths[ci]
        if c in CHALK:
            sc = size * float(rr.uniform(0.94, 1.06))
            rot = math.radians(float(rr.uniform(-3.0, 3.0)))
            dz = float(rr.uniform(-0.025, 0.025)) * size + drift * (ci / max(len(txt) - 1, 1))
            cr, sr = math.cos(rot), math.sin(rot)
            ph = float(rr.uniform(0, 50))
            for stroke in CHALK[c][1]:
                pts = []
                for (gx, gy) in stroke:
                    lx, lz = gx * sc + gy * sc * slant, gy * sc
                    lx, lz = lx * cr - lz * sr, lx * sr + lz * cr
                    pts.append((x + lx, lz + dz))
                dense = _catmull(pts, size * 0.08)
                wob = [(p.x + 0.012 * size * math.sin(ph + p.y * 60 / max(size, 0.01)), p.y + 0.01 * size * math.sin(ph * 1.3 + p.x * 55 / max(size, 0.01)))
                       for p in dense]
                chalk_stroke(mb, wob, wd, M, rr, mat=mat)
        x += gw + sp
    return total


def chalkboard(w=0.9, h=1.2, seed=0):
    """Pizarrón de muro (origen: cara del muro, centro del canto inferior; sale hacia -Y): tablero verde de 12 mm dentro de un
    marco de moldura con ingletes y galce, pijas en las esquinas, repisa para gises con ceja y dos ménsulas; lista de precios
    escrita A MANO con gis (trazos de gis de 4-6 mm con lomo de 0,7 mm, presión variable y cantos desmoronados; letra de
    imprenta con su temblor, giro e inclinación por letra y renglones un poco chuecos), raya bajo el título de dos pasadas,
    gises de punta gastada (uno roto) y borrador de fieltro."""
    r = rng(seed)
    mb = MB()
    zt0 = 0.03                                                   # la repisa ocupa los primeros 3 cm
    fw = 0.045                                                   # ancho de la moldura
    x0, x1, z0, z1 = -w / 2, w / 2, zt0, h
    # tablero (entra 14 mm bajo el galce del marco)
    board(mb, x0 + 0.025 + 0.0055, x1 - 0.025 - 0.0055, -0.012, -0.0002, z0 + 0.025 + 0.0055, z1 - 0.025 - 0.0055,
          "paint_green", rc=0.002, re=0.001)
    # marco de moldura (barrido con ingletes): perfil x hacia adentro, y hacia el muro (+Y) / cuarto (-Y)
    prof = [(-0.025, 0.0), (-0.025, -0.017), (-0.0245, -0.0195), (-0.0235, -0.0215), (-0.0215, -0.023), (-0.019, -0.024),
            (-0.004, -0.024), (0.006, -0.0205), (0.016, -0.0178), (0.02, -0.0158), (0.02, -0.0125), (0.004, -0.0125), (0.004, 0.0)]
    cx0, cx1, cz0, cz1 = x0 + 0.025, x1 - 0.025, z0 + 0.025, z1 - 0.025
    mb.sweep(prof, [(cx0, 0.0, cz0), (cx1, 0.0, cz0), (cx1, 0.0, cz1), (cx0, 0.0, cz1)], mat="wood_dark", closed_path=True,
             normal=(0, 1, 0))
    for (x, z) in ((cx0, cz0), (cx1, cz0), (cx0, cz1), (cx1, cz1)):
        revolve(mb, [(0.0042, -0.0003), (0.0042, 0.0006), (0.0, 0.0012)], "steel", seg=8,
                M=_T(x - math.copysign(0.004, x), -0.024 + 0.0003 * 0, z - math.copysign(0.004, z - (z0 + z1) / 2)) @ _Rx(90))
    # repisa del gis con ceja + ménsulas
    tp = [(0.0, 0.0), (-0.075, 0.0), (-0.0772, 0.0009), (-0.0785, 0.0035), (-0.0785, 0.018), (-0.0777, 0.0197), (-0.0755, 0.0205),
          (-0.0733, 0.0197), (-0.072, 0.018), (-0.0715, 0.009), (-0.012, 0.009), (-0.012, 0.03), (0.0, 0.03)]
    lofts(mb, [(x, [(y, z) for (y, z) in tp]) for x in (x0 - 0.01, x1 + 0.01)], "wood_dark")
    for x in (x0 + 0.08, x1 - 0.08):
        Mb_ = _T(x - 0.009, 0.0, 0.0) @ Matrix(((0, 0, 1, 0), (-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        mb.plate([(0.0, -0.0003), (0.05, -0.0003), (0.0, -0.075)], 0.018, "wood_dark", m=Mb_)
    # gises y borrador en la repisa (piso de la repisa en z = 0,009); gis = cilindro de punta gastada (redonda)
    for (xc, L, a) in ((-0.2, 0.08, 4.0), (-0.05, 0.034, -11.0), (0.05, 0.062, 2.0)):
        Mg = _T(xc, -0.045, 0.009 + 0.0048) @ _Rz(a) @ _Ry(90)
        revolve(mb, [(0.0, -L / 2), (0.0035, -L / 2 + 0.0003), (0.0048, -L / 2 + 0.003), (0.0048, L / 2 - 0.004), (0.004, L / 2 - 0.0012),
                     (0.0, L / 2)], "sign_white", seg=16, M=Mg)
    Me = _T(0.25, -0.042, 0.009) @ _Rz(-6)
    board(mb, -0.065, 0.065, -0.024, 0.024, 0.0, 0.006, "linen", rc=0.006, re=0.0025, M=Me)
    board(mb, -0.064, 0.064, -0.023, 0.023, 0.006, 0.024, "wood", rc=0.008, re=0.006, nc=2, ne=2, M=Me)
    # lista de precios escrita con gis sobre la cara del tablero (y = -0,012)
    yb = -0.012
    Mb = _T(0, yb, 0)
    xl, xr = x0 + fw + 0.04, x1 - fw - 0.04
    top = z1 - fw - 0.03
    tsz = min(0.07, (z1 - z0) * 0.058)
    zz = top - tsz
    chalk_text(mb, "PRICE LIST", tsz, Mb @ _T(_jit(r, 0.01), 0, zz) @ _Ry(_jit(r, 0.8)), r, align="CENTER", slant=0.08,
               wd=max(0.0045, tsz * 0.11))
    wt = 0.5 * w                                                 # raya bajo el título (dos pasadas del gis)
    for k in range(2):
        zl_ = zz - 0.018 - k * 0.006
        chalk_stroke(mb, [(-wt / 2 + _jit(r, 0.01), zl_ + _jit(r, 0.002)), (_jit(r, 0.02), zl_ - 0.002 + _jit(r, 0.002)),
                          (wt / 2 + _jit(r, 0.01), zl_ + 0.003 + _jit(r, 0.003))], 0.0042, Mb, r)
    n = len(PRICES)
    lh = (zz - 0.04 - (z0 + fw + 0.04)) / n
    sz = min(lh * 0.58, 0.055)
    for i, (item, price) in enumerate(PRICES):
        zl = zz - 0.045 - (i + 1) * lh + lh * 0.25
        rot = _jit(r, 0.9)
        s_ = sz * _f(r.uniform(0.93, 1.05))
        Mi = Mb @ _T(xl + _jit(r, 0.006), 0, zl + _jit(r, 0.003)) @ _Ry(rot)
        chalk_text(mb, item, s_, Mi, r, align="LEFT")
        Mp = Mb @ _T(xr + _jit(r, 0.004), 0, zl + _jit(r, 0.003)) @ _Ry(rot * 0.5)
        chalk_text(mb, "$" + price, s_, Mp, r, align="RIGHT")
    return mb


# ======================================================================================================== banca
def bench(L=1.6, seed=0):
    """Banca rústica de madera: asiento de dos tablones gruesos con cantos gastados y desparejos, dos caballetes de patas
    abiertas con travesaño alto y bajo, larguero bajo de punta a punta y dos tornapuntas diagonales al asiento; clavos."""
    r = rng(seed)
    mb = MB()
    hs, ts = 0.45, 0.05
    zs0 = hs - ts

    def wear(x, y):
        return 0.0015 * math.exp(-((x - 0.25 * L * math.sin(seed + 1.0)) / (0.3 * L)) ** 2) + 0.0006 * math.sin(9 * x + 2 * y)
    for i, (ya, yb) in enumerate(((-0.155, -0.0015), (0.0015, 0.155))):
        dz = _jit(r, 0.002)
        plank_x(mb, -L / 2 + _jit(r, 0.01), L / 2 + _jit(r, 0.01), ya, yb, zs0 + dz, hs + dz, "wood_grey", rf=0.009 if i == 0 else 0.004,
                rb=0.004 if i == 0 else 0.008, nst=int(L / 0.12), wear=wear, k=2, end=0.004,
                rfx=(lambda x: 0.009 + 0.004 * math.sin(4.1 * x + seed)) if i == 0 else None)
    xl = L / 2 - 0.2
    for s in (-1, 1):
        x = s * xl
        # caballete: travesaño alto bajo el asiento, dos patas abiertas, travesaño bajo
        board(mb, x - 0.025, x + 0.025, -0.16, 0.16, zs0 - 0.07, zs0 - 0.0005, "wood_grey", rc=0.004, re=0.004)
        for sy in (-1, 1):
            ztp = zs0 - 0.035
            lb = [(x + a, sy * 0.175 + b, 0.0) for (a, b) in rr_pts(0.044, 0.092, 0.005, 2)]
            lt = [(x + a, sy * 0.1 + b, ztp) for (a, b) in rr_pts(0.044, 0.092, 0.005, 2)]
            lm = [(x + a * 0.995, sy * 0.1375 + b, ztp / 2) for (a, b) in rr_pts(0.044, 0.092, 0.005, 2)]
            skin(mb, [lb, lm, lt], "wood_grey")
            for k in range(2):
                nail(mb, _T(x + s * 0.0255, sy * 0.1 + _jit(r, 0.01), zs0 - 0.05 + k * 0.025) @ _Ry(s * 90), r=0.0035)
        board(mb, x - 0.027, x + 0.027, -0.17, 0.17, 0.12, 0.19, "wood_grey", rc=0.004, re=0.004)
        for yy in (-0.06, 0.06):                                 # clavos del asiento al travesaño
            for xx in (x - 0.012, x + 0.012):
                nail(mb, _T(xx, yy + _jit(r, 0.01), hs + _f(r.uniform(-0.001, 0.0)) - wear(xx, yy)) @ _Rz(_f(r.uniform(0, 60))), r=0.004)
    # larguero bajo y tornapuntas
    board(mb, -xl - 0.022, xl + 0.022, -0.02, 0.02, 0.19, 0.26, "wood_grey", rc=0.004, re=0.004)
    for s in (-1, 1):
        p0 = Vector((s * 0.08, 0.0, 0.26))
        p1 = Vector((s * (xl - 0.06), 0.0, zs0 - 0.0005))
        M, Ln = port.frame_on(p0, p1, up=(0, 1, 0))
        board(mb, 0.0, Ln, -0.03, 0.03, -0.0195, 0.0195, "wood_grey", rc=0.003, re=0.003, M=M)
        nail(mb, _T(s * 0.1, -0.0205, 0.24) @ _Rx(90), r=0.0035)
    return mb


# ======================================================================================================== letrero OPEN
def open_sign():
    """Letrero colgante OPEN / CLOSED (origen: el clavo en el muro, cuelga hacia -Z, frente -Y): tabla de 8 mm con filete
    negro en relieve, letras en relieve en las dos caras, armellas y alambre torcido al clavo."""
    mb = MB()
    w, hh, t = 0.30, 0.11, 0.008
    zc = -0.2
    yc = -0.012
    Mp = _T(0, yc, zc) @ _Rx(90)
    slab(mb, Mp @ _T(0, 0, -t / 2), w, hh, t, rc=0.008, re=0.002, mat="sign_white", nc=1, ne=1)
    for sgn in (-1, 1):                                          # cara frontal (-Y) OPEN, trasera CLOSED
        Mf = _T(0, yc - sgn * t / 2, zc) @ (_Rx(90) if sgn > 0 else _Rz(180) @ _Rx(90))
        outer, inner = rr_pts(w - 0.016, hh - 0.016, 0.006, 1), rr_pts(w - 0.026, hh - 0.026, 0.002, 1)
        loops = [[(x, y, -0.0003) for (x, y) in outer], [(x, y, 0.0012) for (x, y) in outer], [(x, y, 0.0012) for (x, y) in inner],
                 [(x, y, -0.0003) for (x, y) in inner]]
        skin(mb, loops, "cable", M=Mf, closed=True)
        etext(mb, "OPEN" if sgn > 0 else "CLOSED", 0.058 if sgn > 0 else 0.042, 0.0015, "cable",
              Mf @ _T(0, -0.021 if sgn > 0 else -0.015, -0.0003), res=3 if sgn > 0 else 1, back=False, bold=True)
    for x in (-0.1, 0.1):                                        # armellas
        tmp = MB()
        tube(tmp, [(0.006 * math.cos(2 * PI * k / 8), 0.0, 0.007 + 0.006 * math.sin(2 * PI * k / 8)) for k in range(9)], 0.0012, seg=4,
                 mat="steel")
        cyl(tmp, (0, 0, -0.006), (0, 0, 0.0015), 0.0012, seg=4, mat="steel")
        mb.join(tmp, _T(x, yc, zc + hh / 2))
    pts = [(-0.1, yc, zc + hh / 2 + 0.013), (-0.05, yc + 0.003, -0.06), (0.0, -0.006, -0.004), (0.05, yc + 0.003, -0.06),
           (0.1, yc, zc + hh / 2 + 0.013)]
    tube(mb, pts, 0.0011, seg=4, mat="steel")
    revolve(mb, [(0.0028, 0.0), (0.0028, 0.0015), (0.0018, 0.002), (0.0018, 0.028), (0.0, 0.03)], "steel", seg=6,
            M=_T(0, 0.0, 0.0) @ _Rx(90))                         # clavo
    return mb


# ======================================================================================================== calendario
def wall_calendar(seed=0):
    """Calendario de pared de papel (origen: el clavo, cuelga hacia -Z): cartón de respaldo colgado por su perforación,
    hoja del mes con ilustración (zonas de cielo / campo / sol como materiales de celda) y cuadrícula de días con domingos en
    rojo, hojas pasadas dobladas hacia arriba y esquinas inferiores enroscadas."""
    r = rng(seed)
    mb = MB()
    w, H = 0.30, 0.46
    yb = -0.004
    # cartón de respaldo con perforación (colgado del clavo)
    board(mb, -w / 2, w / 2, yb - 0.0015, yb, -H, -0.012, "cardboard", rc=0.003, re=0.0005)

    def sheet(z_top, hgt, nu, nv, mats_fn, curl, lift, t=0.0006, y0=yb - 0.0017):
        top, bot, mats = [], [], []
        for i in range(nu):
            u = i / (nu - 1)
            x = -w / 2 + 0.004 + (w - 0.008) * u
            rt, rb = [], []
            for j in range(nv):
                v = j / (nv - 1)
                z = z_top - hgt * v
                e = max(abs(u - 0.5) * 2, 0.0)
                dy = -(curl * max(0.0, (v - 0.82) / 0.18) ** 2 * (0.4 + 0.6 * e ** 2)) - lift * v
                rt.append((x, y0 + dy - t, z))
                rb.append((x, y0 + dy, z))
            top.append(rt)
            bot.append(rb)
        for i in range(nu - 1):
            mats.append([mats_fn(i, j) for j in range(nv - 1)])
        grid_solid(mb, top, bot, mats, edge_mat="paper")
    # hoja del mes: ilustración arriba (cielo, sol, campo) y cuadrícula de días abajo
    nu, nv = 7, 12

    def mfn(i, j):
        if j < 2:
            return "sign_blue"
        if j < 3:
            return "paint_yellow" if i == 4 else "sign_blue"
        if j < 5:
            return "paint_green"
        if j < 6:
            return "paper"
        return "sign_red" if i == 0 else "paper"
    sheet(-0.03, H - 0.04, nu, nv, mfn, curl=0.022 + _f(r.uniform(0, 0.01)), lift=0.0)
    # renglones de la cuadrícula de días (relieve de tinta de 1 mm)
    yg = yb - 0.0017 - 0.0006
    zg0, zg1 = -0.03 - (H - 0.04) * 6.2 / 11, -0.03 - (H - 0.04) * 8.9 / 11
    for k in range(6):                                           # renglones de semana (la curva de la esquina queda libre)
        z = zg0 + (zg1 - zg0) * k / 5
        mb.box((-w / 2 + 0.012, yg - 0.001, z - 0.0006), (w / 2 - 0.012, yg + 0.0002, z + 0.0006), "cable", bevel=0.0)
    etext(mb, "MAY", 0.022, 0.0014, "sign_red", _T(0, yg + 0.0002, zg0 + 0.008) @ _Rx(90), res=1, back=False)
    # engargolado de lámina doblado sobre el canto superior (sujeta hojas y respaldo) con ojillo para el clavo
    tp = [(yb + 0.0016, -0.034), (yb + 0.0016, -0.0115), (yb + 0.0002, -0.0098), (yb - 0.0024, -0.0098), (yb - 0.0038, -0.0115),
          (yb - 0.0038, -0.034), (yb - 0.0026, -0.034), (yb - 0.0026, -0.0122), (yb - 0.0018, -0.0112), (yb - 0.0002, -0.0112),
          (yb + 0.0004, -0.0122), (yb + 0.0004, -0.034)]
    lofts(mb, [(x, tp) for x in (-w / 2 - 0.002, w / 2 + 0.002)], "steel")
    revolve(mb, [(0.0045, -0.0003), (0.0045, 0.0008), (0.0032, 0.0012), (0.0032, -0.0003)], "steel", seg=10, closed=True,
            M=_T(0, yb - 0.0038, -0.022) @ _Rx(90), caps=False)
    # todo cuelga del clavo por el ojillo: el clavo (origen) toca el borde superior del ojillo
    mb.transform(_T(0, 0, 0.022 - 0.0014))
    revolve(mb, [(0.0026, 0.0), (0.0026, 0.0012), (0.0016, 0.0018), (0.0016, 0.014), (0.0, 0.016)], "steel", seg=6, M=_Rx(90))
    return mb


# ======================================================================================================== jaba de refrescos / cerveza
def bottle_crate(seed=0, empty=True):
    """Jaba de plástico para 24 botellas (6 × 4): paredes con costillas verticales y borde superior reforzado, asas caladas en
    las cabeceras (marco con travesaño redondo), esquineros, rejilla de divisiones; con botellas ámbar (vacías, sin corcholata,
    o llenas si empty=False), algunas celdas vacías."""
    r = rng(seed)
    base = MB()
    mb = base
    mat = "sign_red" if seed % 2 == 0 else "plastic_blue"
    c = 0.068
    nx, ny = 6, 4
    W, D, Hh = nx * c + 0.016, ny * c + 0.016, 0.19
    t = 0.006
    # piso con perforaciones de escurrimiento insinuadas (ranuras) y costados largos con costillas
    board(mb, -W / 2 + 0.002, W / 2 - 0.002, -D / 2 + 0.002, D / 2 - 0.002, 0.0, 0.008, mat, rc=0.012, re=0.002)
    for sy in (-1, 1):
        y0_, y1_ = sorted((sy * D / 2, sy * (D / 2 - t)))
        board(mb, -W / 2 + 0.012, W / 2 - 0.012, y0_, y1_, 0.004, Hh - 0.012, mat, rc=0.002, re=0.002)
        for k in range(5):                                       # costillas verticales
            x = -W / 2 + 0.05 + (W - 0.1) * k / 4
            yr = sy * (D / 2 + 0.0035)
            mb.box((x - 0.004, min(yr, sy * D / 2 - sy * 0.0005), 0.006), (x + 0.004, max(yr, sy * D / 2 - sy * 0.0005), Hh - 0.014), mat,
                   bevel=0.0012, seg=1)
        yr0 = sy * (D / 2 + 0.006)                               # borde superior reforzado
        board(mb, -W / 2 + 0.008, W / 2 - 0.008, min(yr0, sy * (D / 2 - t - 0.002)), max(yr0, sy * (D / 2 - t - 0.002)), Hh - 0.014,
              Hh, mat, rc=0.004, re=0.003, nc=2)
    for sx in (-1, 1):                                           # cabeceras con asa calada
        x0_, x1_ = sorted((sx * W / 2, sx * (W / 2 - t)))
        board(mb, x0_, x1_, -D / 2 + 0.012, D / 2 - 0.012, 0.004, Hh - 0.07, mat, rc=0.002, re=0.002)
        for sy in (-1, 1):
            board(mb, x0_, x1_, min(sy * 0.055, sy * (D / 2 - 0.012)), max(sy * 0.055, sy * (D / 2 - 0.012)), Hh - 0.072, Hh - 0.012,
                  mat, rc=0.003, re=0.002)
        xh = sx * (W / 2 - t / 2)
        tube(mb, [(xh, -0.06, Hh - 0.02), (xh, 0.06, Hh - 0.02)], 0.011, seg=8, mat=mat)                 # travesaño del asa
        board(mb, min(sx * (W / 2 + 0.002), sx * (W / 2 - t - 0.002)), max(sx * (W / 2 + 0.002), sx * (W / 2 - t - 0.002)),
              -D / 2 + 0.008, D / 2 - 0.008, Hh - 0.0095, Hh, mat, rc=0.004, re=0.003, nc=2)
    for (sx, sy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):     # esquineros
        board(mb, sx * W / 2 - 0.013, sx * W / 2 + 0.013, sy * D / 2 - 0.013, sy * D / 2 + 0.013, 0.0, Hh + 0.003, mat, rc=0.008,
              re=0.003, nc=2)
    # rejilla de divisiones
    for i in range(1, nx):
        x = -W / 2 + 0.008 + i * c
        mb.box((x - 0.0012, -D / 2 + t, 0.008), (x + 0.0012, D / 2 - t, Hh - 0.045), mat, bevel=0.0)
    for j in range(1, ny):
        y = -D / 2 + 0.008 + j * c
        for i in range(nx):
            xa = -W / 2 + 0.008 + i * c + 0.0012
            mb.box((xa, y - 0.0012, 0.008), (xa + c - 0.0024, y + 0.0012, Hh - 0.046), mat, bevel=0.0)
    # botellas
    P = Placer(base)
    hero = beer_bottle(lod=1, empty=empty, seg=13)
    for i in range(nx):
        for j in range(ny):
            if r.random() < 0.15:
                continue
            x = -W / 2 + 0.008 + (i + 0.5) * c + _jit(r, 0.0015)
            y = -D / 2 + 0.008 + (j + 0.5) * c + _jit(r, 0.0015)
            _put(P, hero, x, y, 0.008, rz=_f(r.uniform(0, 360)), prio=0 if (j == 0 or i in (0, nx - 1)) else 1)
    P.flush(r, 4950)
    return base


# ======================================================================================================== estiba de cajas
def wood_crate(w=0.5, d=0.33, h=0.3, seed=0):
    """Huacal de madera: cabeceras de tabla con agarradera calada (dos tablas con hueco), esquineros, 3 tablillas por costado
    con holgura, fondo de tablillas y clavos."""
    r = rng(seed)
    mb = MB()
    te, ts = 0.018, 0.008
    for sx in (-1, 1):                                           # cabeceras: dos tablas con hueco de agarradera
        x0_, x1_ = sorted((sx * w / 2, sx * (w / 2 - te)))
        board(mb, x0_, x1_, -d / 2 + ts, d / 2 - ts, 0.0, h * 0.62, "wood", rc=0.002, re=0.002)
        board(mb, x0_, x1_, -d / 2 + ts, d / 2 - ts, h * 0.78, h, "wood", rc=0.002, re=0.003)
        for sy in (-1, 1):
            board(mb, x0_, x1_, min(sy * 0.06, sy * (d / 2 - ts)), max(sy * 0.06, sy * (d / 2 - ts)), h * 0.62, h * 0.78, "wood",
                  rc=0.002, re=0.002)
        for sy in (-1, 1):                                       # esquineros interiores
            xa, xb = sorted((sx * (w / 2 - te), sx * (w / 2 - te - 0.02)))
            ya, yb = sorted((sy * (d / 2 - ts), sy * (d / 2 - ts - 0.02)))
            board(mb, xa, xb, ya, yb, 0.0085, h - 0.004, "wood", rc=0.002, re=0.002)
    for sy in (-1, 1):                                           # tablillas de costado
        y0_, y1_ = sorted((sy * d / 2, sy * (d / 2 - ts)))
        for k in range(3):
            z0 = 0.01 + k * (h - 0.02) / 3
            z1 = z0 + (h - 0.02) / 3 - 0.025
            dz = _jit(r, 0.003)
            board(mb, -w / 2, w / 2, y0_, y1_, z0 + dz, z1 + dz, "wood", rc=0.002, re=0.002)
            for sx in (-1, 1):
                for zz in ((z0 + z1) / 2 + dz,):
                    nail(mb, _T(sx * (w / 2 - te / 2), sy * d / 2, zz) @ _Rx(-sy * 90), r=0.0028)
    for k in range(3):                                           # fondo
        y = -d / 2 + ts + 0.036 + k * (d - 2 * ts - 0.072) / 2
        board(mb, -w / 2 + te + 0.0005, w / 2 - te - 0.0005, y - 0.035, y + 0.035, 0.0, 0.008, "wood", rc=0.002, re=0.0015)
    return mb


def crate_stack(seed=0):
    """Estiba de bodega: huacal de madera en el piso con dos cajas de cartón encima, y al lado dos cajas más (una abierta con
    las solapas levantadas); cajas con solapas, junta y cinta, cantos aplastados; ligeros giros y desplomes."""
    r = rng(seed)
    mb = MB()
    mb.join(wood_crate(seed=seed), _T(-0.27, 0.0, 0.0) @ _Rz(_jit(r, 3)))
    c1 = carton(0.46, 0.32, 0.26, seed=seed + 1, crush=0.002, stamp=("THIS SIDE UP", 0.024))
    mb.join(c1, _T(-0.27 + _jit(r, 0.01), _jit(r, 0.01), 0.3) @ _Rz(_jit(r, 4)))
    c2 = carton(0.36, 0.28, 0.22, seed=seed + 2)
    mb.join(c2, _T(-0.25 + _jit(r, 0.015), _jit(r, 0.01), 0.3 + 0.26 + 0.0028) @ _Rz(_f(r.uniform(-12, 12))))
    c3 = carton(0.4, 0.34, 0.3, seed=seed + 3, crush=0.003, stamp=("KEEP DRY", 0.03))
    mb.join(c3, _T(0.25, -0.02, 0.0) @ _Rz(_jit(r, 5)))
    c4 = carton(0.3, 0.26, 0.24, seed=seed + 4, open_flaps=(_f(r.uniform(60, 100)), _f(r.uniform(70, 110))))
    mb.join(c4, _T(0.27 + _jit(r, 0.01), 0.0, 0.3 + 0.0028) @ _Rz(_f(r.uniform(-15, 15))))
    return mb


# ======================================================================================================== gabinetes de lámina (muro)
def _carcass(mb, W, D, H, zp, mat="steel", t=0.018, yf=0.0):
    """Cuerpo de gabinete de lámina contra el muro (espalda en y = 0, frente en y = -D): costados de doble lámina con canto
    redondeado, techo con ceja, piso, espalda y zoclo remetido sobre niveladores. yf: profundidad que ocupa el marco frontal
    (los costados y el techo empiezan detrás de él)."""
    for s in (-1, 1):
        x0_, x1_ = sorted((s * W / 2, s * (W / 2 - t)))
        board(mb, x0_, x1_, -D + yf, 0.0, 0.0, H, mat, rc=0.004, re=0.003, nc=2)
    board(mb, -W / 2 + t, W / 2 - t, -D + max(yf, 0.0005), 0.0, H - t, H - 0.0005, mat, rc=0.003, re=0.003)
    board(mb, -W / 2 + t, W / 2 - t, -D + 0.02, 0.0, zp, zp + t, mat, rc=0.002, re=0.002)
    board(mb, -W / 2 + t, W / 2 - t, -0.012, -0.0005, zp + t, H - t, mat, rc=0.002, re=0.001)
    board(mb, -W / 2 + t, W / 2 - t, -D + 0.035, -D + 0.05, 0.012, zp, mat, rc=0.002, re=0.002)                  # zoclo
    for x in (-W / 2 + 0.06, W / 2 - 0.06):
        for y in (-D + 0.07, -0.07):
            foot_leveler(mb, _T(x, y, 0.0), r=0.018, h=zp - 0.005, lite=True)


def _shelf_sheet(mb, x0, x1, y0, y1, z, mat="steel", lip=0.025, t=0.0012):
    """Entrepaño de lámina: placa con ceja frontal y trasera dobladas hacia abajo (un solo perfil barrido) y canto redondeado."""
    prof = [(y0, z - lip), (y0, z - 0.002), (y0 + 0.002, z), (y1 - 0.002, z), (y1, z - 0.002), (y1, z - lip * 0.6), (y1 - t, z - lip * 0.6),
            (y1 - t, z - t), (y0 + t, z - t), (y0 + t, z - lip)]
    lofts(mb, [(x, prof) for x in (x0, x1)], mat)


def ammo_box(w=0.065, d=0.10, h=0.038, mat="cardboard", band="sign_red", word=None, seed=0):
    """Cajita de cartuchos de cartón (de pie sobre su cara ancha, la cabecera de w × h mira a -Y): cuerpo con cantos un poco
    vencidos, franja impresa que le da la vuelta (tramo de material, sin calcomanía), ceja de la tapa de lengüeta en la cabecera
    y, si word, la palabra genérica en relieve de 1,1 mm sobre la franja."""
    mb = MB()
    pts = rr_pts(w, d, 0.0025, 1)
    zs = [(0.0, 0.0), (h * 0.3, 0.0), (h * 0.7, 0.0), (h - 0.0012, 0.0), (h, 0.0012)]
    loops = [[(x - math.copysign(i_, x), y - math.copysign(i_, y), z) for (x, y) in pts] for (z, i_) in zs]
    skin(mb, loops, mat, mats=[mat, band, mat, mat])
    # lengüeta de la tapa (ceja en la cabecera frontal, 1,2 mm)
    mb.box((-w / 2 + 0.004, -d / 2 - 0.0012, h - 0.009), (w / 2 - 0.004, -d / 2 + 0.0003, h - 0.0015), mat, bevel=0.0)
    if word:
        etext(mb, word, min(h * 0.26, w * 0.18), 0.0015, "sign_white", _T(0, -d / 2 - 0.0, h * 0.5 - h * 0.1) @ _Rx(90) @
              _T(0, 0, -0.0003), res=1, back=False, bold=True)
    return mb


def ammo_cabinet(seed=0):
    """Gabinete de lámina de muro para munición, 1,0 × 0,40 × 1,9 (espalda en y = 0): cuerpo de doble lámina, marco frontal,
    dos puertas de perfil con vidrio, junquillo de hule, 3 bisagras de barril por puerta, jaladeras, porta-candado con
    candado; 4 entrepaños de lámina con cajitas de cartuchos genéricas en pilas (franja impresa; algunas con AMMO / RIFLE /
    SHOTGUN), dos sueltas y caídas; cajas de cartón arriba. Sin armas."""
    r = rng(seed)
    base = MB()
    mb = base
    W, D, H, zp = 1.0, 0.40, 1.9, 0.07
    t = 0.018
    _carcass(mb, W, D, H, zp, yf=0.02)
    # marco frontal (cara en y = -D) y puertas inset con vidrio
    zo0, zo1 = zp + t, H - t
    Mf = _T(0, -D + 0.02, 0) @ _Rx(90)
    rrframe(mb, Mf, (0, (zp + H) / 2, W, H - zp, 0.004), (0, (zo0 + zo1) / 2, W - 2 * t, zo1 - zo0, 0.003), 0.02,
            re_o=0.003, re_i=0.002, n=2, ne=1, mat="steel")
    g = 0.003
    dw = (W - 2 * t - 3 * g) / 2
    dh = zo1 - zo0 - 2 * g
    zc = (zo0 + zo1) / 2
    for s in (-1, 1):
        xc = s * (g / 2 + dw / 2)
        yd = -D + 0.0025                                         # cara frontal de la puerta 2,5 mm adentro
        Md = _T(xc, yd + 0.022, 0) @ _Rx(90)
        rrframe(mb, Md, (0, zc, dw, dh, 0.004), (0, zc + 0.01, dw - 0.11, dh - 0.17, 0.004), 0.022, re_o=0.003, re_i=0.002, n=2,
                ne=1, mat="steel")
        board(mb, xc - dw / 2 + 0.05, xc + dw / 2 - 0.05, yd + 0.011, yd + 0.015, zc + 0.01 - (dh - 0.17) / 2 - 0.005,
              zc + 0.01 + (dh - 0.17) / 2 + 0.005, "glass", rc=0.003, re=0.001)
        path = [(xc + x, yd + 0.0095, zc + 0.01 + z) for (x, z) in rr_pts(dw - 0.11 + 0.003, dh - 0.17 + 0.003, 0.004, 1)]
        mb.sweep([(u, v) for (u, v) in rr_pts(0.006, 0.004, 0.0015, 1)], path, mat="rubber", closed_path=True, normal=(0, 1, 0))
        xh = s * (W / 2 - t - g)                                 # bisagras de barril en el canto exterior
        for zz in (zo0 + 0.15, zc, zo1 - 0.15):
            revolve(mb, [(0.0, -0.035), (0.005, -0.035), (0.0055, -0.033), (0.0055, 0.033), (0.005, 0.035), (0.0, 0.035)], "steel",
                    seg=10, M=_T(xh, -D - 0.002, zz))
            board(mb, min(xh, xh - s * 0.02), max(xh, xh - s * 0.02), -D - 0.0015, -D + 0.0025, zz - 0.03, zz + 0.03, "steel",
                  rc=0.002, re=0.0006)
        xg = s * 0.06                                            # jaladera
        hose(mb, [(xg, yd + 0.0005, zc + 0.05), (xg, yd - 0.03, zc + 0.05), (xg, yd - 0.03, zc - 0.07), (xg, yd + 0.0005, zc - 0.07)],
             0.0055, bend=0.012, mat="steel", seg=8, nseg=3)
    # porta-candado: escuadra con argolla en la puerta derecha, aldaba en la izquierda, candado colgando
    zh = zc + 0.18
    board(mb, 0.008, 0.05, -D - 0.0025, -D + 0.0025, zh - 0.022, zh + 0.022, "steel", rc=0.003, re=0.001)
    board(mb, -0.07, -0.004, -D - 0.006, -D + 0.0005, zh - 0.017, zh + 0.017, "steel", rc=0.004, re=0.001)
    revolve(mb, [(0.0, -0.016), (0.004, -0.016), (0.004, 0.016), (0.0, 0.016)], "steel", seg=8, M=_T(-0.07, -D - 0.003, zh))
    for x in (0.02, 0.04, -0.05, -0.03):
        revolve(mb, [(0.0035, -0.0003), (0.003, 0.0012), (0.0, 0.0018)], "steel", seg=6,
                M=_T(x, -D - (0.0025 if x > 0 else 0.006), zh + (0.012 if x in (0.02, -0.05) else -0.012)) @ _Rx(90), caps=False)
    sp = [(0.0, -D - 0.0025, zh - 0.006), (0.0, -D - 0.022, zh - 0.006), (0.0, -D - 0.022, zh + 0.006), (0.0, -D - 0.0025, zh + 0.006)]
    hose(mb, sp, 0.0028, bend=0.005, mat="steel", seg=6, nseg=3)                               # argolla
    Mp = _T(0.0, -D - 0.022, zh - 0.006) @ _Rx(8)
    pts = [(-0.012, 0.0, -0.012), (-0.012, 0.0, 0.006), (0.012, 0.0, 0.006), (0.012, 0.0, -0.012)]
    tmp = MB()
    hose(tmp, pts, 0.0035, bend=0.011, mat="steel", seg=8, nseg=5)
    slab(tmp, _T(0, 0, -0.05), 0.04, 0.016, 0.04, rc=0.004, re=0.003, mat="aluminium", nc=2, ne=2)
    revolve(tmp, [(0.0035, -0.0003), (0.0035, 0.001), (0.0, 0.0013)], "steel", seg=8, M=_T(0, -0.008, -0.04) @ _Rx(90), caps=False)
    mb.join(tmp, Mp @ _Rx(-90) @ _Rx(90))
    # entrepaños
    xi0, xi1 = -W / 2 + t + 0.002, W / 2 - t - 0.002
    yi0, yi1 = -D + 0.03, -0.014
    levels = [zp + t, 0.48, 0.84, 1.2, 1.56]
    for z in levels[1:]:
        _shelf_sheet(mb, xi0, xi1, yi0, yi1, z)
    # cajitas de cartuchos (presupuesto)
    P = Placer(base)
    H_ = _Heroes()
    kinds = [((0.065, 0.10, 0.036), None), ((0.06, 0.105, 0.045), "RIFLE"), ((0.065, 0.11, 0.066), "SHOTGUN"), ((0.065, 0.10, 0.036), "AMMO")]
    bands = ("sign_red", "sign_green", "paint_yellow", "sign_blue")
    for i, z in enumerate(levels):
        zs = z + (0.0 if i else 0.0)
        top = (levels[i + 1] - 0.03) if i + 1 < len(levels) else H - t - 0.02
        x = xi0 + 0.012
        gap_p = (0.45, 0.25, 0.3, 0.35, 0.5)[i]
        while x < xi1 - 0.08:
            if r.random() < gap_p:
                x += _f(r.uniform(0.05, 0.14))
                continue
            k = int(r.integers(0, len(kinds)))
            (bw, bd, bh), word = kinds[k]
            if word and r.random() < 0.5:
                word = None
            band = bands[(k + i) % len(bands)]
            nh = max(1, min(int(r.integers(1, 4)) + (1 if bh < 0.04 else 0), int((top - zs) / (bh + 0.001))))
            rows = 2 if r.random() < 0.3 else 1
            for row in range(rows):
                y = yi0 + 0.004 + bd / 2 + row * (bd + 0.006)
                if y + bd / 2 > yi1:
                    break
                below = None
                for j in range(nh if row == 0 else max(1, nh - int(r.integers(0, 3)))):
                    wd = word if (row == 0 and j == 0 and word) else None
                    hero = H_.get(("ab", k, band, wd), lambda: ammo_box(bw, bd, bh, band=band, word=wd))
                    below = _put(P, hero, x + bw / 2 + _jit(r, 0.002), y + _jit(r, 0.003), zs + j * (bh + 0.0004), rz=_jit(r, 2.5),
                                 prio=(0 if j < 2 else 1) if row == 0 else 2, on=below)
            x += bw + _f(r.uniform(0.004, 0.02))
    # dos cajitas sueltas caídas en el piso del gabinete
    for (x, rz) in ((xi1 - 0.12, 35.0), (xi1 - 0.2, -70.0)):
        hero = H_.get(("ab", 0, "sign_red", None), lambda: ammo_box(0.065, 0.10, 0.036, band="sign_red"))
        _put(P, hero, x, yi0 + 0.12, levels[0] + 0.0325, rz=rz, extra=_Ry(90) @ _T(-0.0325, 0, 0) @ _T(0.0, 0, -0.0325 + 0.0325), prio=0)
    # cajas de cartón sobre el gabinete
    c1 = carton(0.42, 0.34, 0.2, seed=seed + 5)
    _put(P, c1, -0.22, -D / 2, H, rz=_jit(r, 4), prio=1)
    c2 = carton(0.36, 0.3, 0.16, seed=seed + 6)
    _put(P, c2, 0.24, -D / 2 + 0.01, H, rz=_jit(r, 6), prio=1)
    P.flush(r, 11900)
    return base


# ======================================================================================================== anaquel de curación
def first_aid_kit(w=0.26, d=0.1, h=0.17, words=False):
    """Botiquín de plástico blanco (de pie, frente -Y): casco y tapa con junta de 2 mm, asa abatible arriba con orejas, dos
    broches al frente y cruz VERDE en relieve de 1,5 mm (y FIRST AID si words)."""
    mb = MB()
    hl = h * 0.42
    slab(mb, _T(0, 0, 0), w, d, h - hl - 0.001, rc=0.012, re=0.004, re0=0.006, mat="sign_white", nc=2, ne=1)
    slab(mb, _T(0, 0, h - hl + 0.001), w, d, hl - 0.001, rc=0.012, re=0.008, re0=0.003, mat="sign_white", nc=2, ne=2)
    cw, ct = 0.05 if not words else 0.04, 0.016 if not words else 0.013
    cz = h * 0.58 if not words else h * 0.66
    cross = [(ct / 2, cw / 2), (-ct / 2, cw / 2), (-ct / 2, ct / 2), (-cw / 2, ct / 2), (-cw / 2, -ct / 2), (-ct / 2, -ct / 2),
             (-ct / 2, -cw / 2), (ct / 2, -cw / 2), (ct / 2, -ct / 2), (cw / 2, -ct / 2), (cw / 2, ct / 2), (ct / 2, ct / 2)]
    mb.plate(cross, 0.0018, "sign_green", m=_T(0, -d / 2 + 0.0003, cz) @ _Rx(90))
    if words:
        etext(mb, "FIRST AID", 0.018, 0.0015, "sign_green", _T(0, -d / 2 + 0.0003, h * 0.27) @ _Rx(90), res=1, back=False, bold=True)
    for x in (-w / 2 + 0.035, w / 2 - 0.035):                    # broches
        board(mb, x - 0.012, x + 0.012, -d / 2 - 0.006, -d / 2 + 0.002, h - hl - 0.018, h - hl + 0.012, "plastic", rc=0.004, re=0.002)
    for x in (-0.055, 0.055):                                    # orejas del asa
        board(mb, x - 0.008, x + 0.008, -0.008, 0.008, h - 0.0005, h + 0.012, "plastic", rc=0.004, re=0.002)
    hose(mb, [(-0.055, 0.0, h + 0.006), (-0.05, -0.03, h + 0.0065), (0.05, -0.03, h + 0.0065), (0.055, 0.0, h + 0.006)], 0.0045,
         bend=0.01, mat="plastic", seg=6, nseg=3)
    return mb


def bandage_roll(R=0.024, L=0.075, mat="linen", core=0.008):
    """Venda elástica enrollada (de pie): rollo con canto boleado, capas insinuadas en la cara superior y hueco del centro."""
    mb = MB()
    prof = [(core, L - 0.0015), (R * 0.6, L - 0.0007), (R - 0.0025, L), (R, L - 0.0025), (R, 0.0025), (R - 0.0025, 0.0), (core, 0.0015)]
    revolve(mb, prof, mat, seg=14, closed=True)
    return mb


def med_bottle(kind="iodine"):
    """Frasco ámbar (yodo 60 ml / alcohol 250 ml) con hombro, cuello, tapa de rosca estriada y etiqueta como tramo del perfil."""
    mb = MB()
    if kind == "iodine":
        R, Hb, cap = 0.019, 0.075, "cable"
    else:
        R, Hb, cap = 0.028, 0.15, "sign_red"
    prof = [(0.0, 0.002), (R * 0.93, 0.0), (R, 0.006), (R, 0.2 * Hb), (R, 0.8 * Hb), (R * 0.95, 0.88 * Hb), (R * 0.55, 0.96 * Hb),
            (R * 0.45, Hb), (R * 0.45, Hb + 0.006)]
    revolve(mb, prof, ["amber", "amber", "amber", "paper", "amber", "amber", "amber", "amber"], seg=14)
    revolve(mb, [(R * 0.52, Hb + 0.002), (R * 0.55, Hb + 0.003), (R * 0.55, Hb + 0.018), (R * 0.5, Hb + 0.0195), (0.0, Hb + 0.0195)],
            cap, seg=14, caps=False)
    return mb


def syringe_pack():
    """Jeringa desechable en su sobre: papel grado médico con la jeringa (cilindro, émbolo y capuchón azul) bajo película
    termoformada que sigue su silueta, sello perimetral. Acostada sobre z = 0, larga en X."""
    mb = MB()
    board(mb, -0.085, 0.085, -0.019, 0.019, 0.0, 0.0012, "paper", rc=0.004, re=0.0004)
    Ms = _T(0, 0, 0.0012 + 0.0052) @ _Ry(90)
    revolve(mb, [(0.0, -0.065), (0.0045, -0.065), (0.0045, -0.062), (0.0048, -0.06), (0.0048, 0.02), (0.002, 0.024), (0.0015, 0.03),
                 (0.0, 0.03)], ["plastic", "plastic", "plastic", "plastic", "plastic", "plastic", "plastic"], seg=10, M=Ms)
    revolve(mb, [(0.0, 0.03), (0.0032, 0.03), (0.0028, 0.072), (0.0, 0.073)], "plastic_blue", seg=8, M=Ms)     # capuchón
    board(mb, -0.076, -0.072, -0.009, 0.009, 0.0012, 0.0045, "plastic", rc=0.002, re=0.0006)              # aletas
    return mb


def gauze_pack(seed=0):
    """Sobre de gasa estéril: almohadilla de papel con el contenido abombado y sellos dentados en los cuatro cantos."""
    return pillow_bag(0.1, 0.085, 0.014, mat="paper", band="sign_blue", seed=seed, nu=8, nv=6, seal=0.009, zr=0.5, wr=0.0008,
                      band_u=0.25)


def medical_shelf(seed=0):
    """Anaquel de lámina de muro para curación, 0,9 × 0,32 × 1,8 (espalda en y = 0): costados, techo, espalda y zoclo de lámina,
    4 entrepaños con cejas; botiquines blancos con cruz verde (uno con FIRST AID), vendas elásticas, sobres de gasa, cajas
    blancas de medicamento con franja, frascos ámbar de yodo y alcohol, jeringas en sobre y una caja abierta con más."""
    r = rng(seed)
    base = MB()
    mb = base
    W, D, H, zp = 0.9, 0.32, 1.8, 0.07
    t = 0.016
    _carcass(mb, W, D, H, zp, t=t)
    xi0, xi1 = -W / 2 + t + 0.002, W / 2 - t - 0.002
    yi0, yi1 = -D + 0.004, -0.014
    levels = [zp + t, 0.46, 0.83, 1.2, 1.55]
    for z in levels[1:]:
        _shelf_sheet(mb, xi0, xi1, yi0, yi1, z)
    P = Placer(base)
    H_ = _Heroes()
    yf = yi0 + 0.006

    def kits(z, x):
        for k in range(2):
            hero = H_.get(("fak", k == 0), lambda: first_aid_kit(words=(k == 0)))
            _put(P, hero, x + 0.13, yf + 0.05 + 0.006, z, rz=_jit(r, 3))
            x += 0.275
        return x

    def rolls(z, x, n):
        for k in range(n):
            hero = H_.get(("roll", k % 2), lambda: bandage_roll(mat="linen" if k % 2 == 0 else "paper"))
            _put(P, hero, x + 0.025, yf + 0.025 + (k % 2) * 0.05 + _jit(r, 0.003), z, rz=_f(r.uniform(0, 360)), prio=0 if k % 2 == 0 else 2)
            if k % 2:
                x += 0.052
        return x + 0.052

    def gauze(z, x):
        below = None
        for k in range(int(r.integers(3, 7))):
            hero = H_.get(("gz", k % 2), lambda: gauze_pack(seed=k % 2))
            below = _put(P, hero, x + 0.055 + _jit(r, 0.004), yf + 0.05 + _jit(r, 0.004), z + k * 0.0125, rz=_jit(r, 8), prio=0 if k < 2 else 1,
                         on=below)
        return x + 0.12

    def medboxes(z, x, n, band):
        for k in range(n):
            below = None
            for j in range(int(r.integers(1, 3))):
                hero = H_.get(("mbx", band), lambda: ammo_box(0.045, 0.095, 0.06, mat="sign_white", band=band))
                below = _put(P, hero, x + 0.023, yf + 0.048 + _jit(r, 0.004), z + j * 0.0605, rz=_jit(r, 4), prio=0 if j == 0 else 1,
                             on=below)
            x += 0.049
        return x + 0.01

    def bottles(z, x, n, kind):
        for k in range(n):
            hero = H_.get(("mb", kind), lambda: med_bottle(kind))
            R = 0.019 if kind == "iodine" else 0.028
            for j in range(2 if r.random() < 0.5 else 1):
                _put(P, hero, x + R + 0.002, yf + R + 0.004 + j * (2 * R + 0.006), z, rz=_f(r.uniform(0, 360)), prio=0 if j == 0 else 2)
            x += 2 * R + 0.006
        return x + 0.01

    def syringes(z, x):
        bx = carton(0.18, 0.1, 0.07, seed=seed + 8, open_flaps=(95, 85), mat="sign_white")
        i0 = _put(P, bx, x + 0.09, yf + 0.055, z, rz=_jit(r, 3))
        sp = H_.get(("syr",), lambda: syringe_pack())
        for k in range(4):                                       # sobres parados de canto dentro de la caja, recargados
            _put(P, sp, x + 0.09, yf + 0.055 + (k - 1.5) * 0.02, z + 0.0045 + 0.0195, rz=0.0, extra=_Rx(78), prio=1, on=i0)
        for k in range(3):                                       # sueltos al lado
            _put(P, sp, x + 0.28 + _jit(r, 0.01), yf + 0.03 + k * 0.045, z + k * 0.0, rz=_jit(r, 10), prio=0)
        return x + 0.38

    # nivel 4 (arriba): botiquines + vendas; 3: gasas, cajas, frascos de yodo; 2: alcohol, cajas; 1: jeringas, vendas; piso: botiquín
    x = kits(levels[4], xi0 + 0.01)
    rolls(levels[4], x + 0.02, 6)
    x = gauze(levels[3], xi0 + 0.01)
    x = gauze(levels[3], x)
    x = medboxes(levels[3], x + 0.01, 4, "sign_blue")
    bottles(levels[3], x, 4, "iodine")
    x = bottles(levels[2], xi0 + 0.01, 5, "alcohol")
    medboxes(levels[2], x + 0.02, 6, "sign_green")
    x = syringes(levels[1], xi0 + 0.01)
    rolls(levels[1], x + 0.02, 4)
    hero = H_.get(("fak", False), lambda: first_aid_kit(words=False))
    _put(P, hero, xi0 + 0.2, yf + 0.06, levels[0], rz=_jit(r, 4))
    _put(P, H_.get(("mbx", "sign_red"), lambda: ammo_box(0.045, 0.095, 0.06, mat="sign_white", band="sign_red")), xi0 + 0.45,
         yf + 0.07, levels[0], rz=25)
    _put(P, carton(0.34, 0.26, 0.22, seed=seed + 12, crush=0.002), xi1 - 0.19, yf + 0.14, levels[0], rz=_jit(r, 5), prio=1)
    P.flush(r, 11900)
    return base

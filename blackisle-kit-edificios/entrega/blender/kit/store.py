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
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rbox, rng, rr_profile, rtube  # noqa: F401
from kit.clinic_equipo import angle_l, loft_rings, revolve, sweep_frame, weld  # noqa: F401
from kit.clinic_equipo import chain as echain
from kit.clinic_equipo import rtube_lo, screw_lo
from kit.clinic_equipo import text as etext
from kit.clinic_servicios import foot_leveler, holed, hose, louver_grille, rr_pts, skin, slab  # noqa: F401
from kit.clinic_servicios import lathe as slathe


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
    mb.cyl(p0, p1, r, seg=seg, mat=mat)


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
        if 0 < k:                                                # división entre compartimentos (bajo el montante)
            pass
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
    xs = [-L / 2, -Lb] + [-Lb + 2 * Lb * i / (nu - 3) for i in range(1, nu - 3)] + [Lb, L / 2]
    ys = [-W / 2 + W * j / (nv - 1) for j in range(nv)]
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
            S = max(0.0, 1 - abs(u) ** 4) ** 0.55 * max(0.0, 1 - abs(v) ** 3) ** 0.5
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


def paper_bag(w, d, h, mat="paper", band=None, seed=0, n=1, lv=5):
    """Bolsa de papel de fondo cuadrado (harina, azúcar) parada: cuerpo con costados abombados y arrugas, fondo plano, boca
    doblada dos veces hacia el frente."""
    r = rng(seed)
    ph = [_f(v) for v in r.uniform(0, 2 * PI, 4)]
    loops = []
    zs = [0.0, 0.006] + [0.006 + (h - 0.05) * k / (lv - 1) for k in range(1, lv)]
    mats = []
    for k, z in enumerate(zs):
        bul = 0.004 * math.sin(PI * min(1.0, z / (h - 0.05)))
        pts = rr_pts(w - (0.006 if k == 0 else 0.0), d - (0.006 if k == 0 else 0.0), 0.006, n)
        L = []
        for (x, y) in pts:
            nx_, ny_ = (x / (w / 2)), (y / (d / 2))
            g = 1.0 + bul / max(w, d) * 2 * (1 - abs(nx_) ** 4 if abs(ny_) > 0.9 else 1 - abs(ny_) ** 4)
            wz = 0.0015 * math.sin(23 * x + 17 * z + ph[0]) * math.sin(19 * y + ph[1])
            L.append((x * g + wz, y * g + wz, z))
        loops.append(L)
        mats.append(band if (band and 0.35 * h < z < 0.65 * h) else mat)
    # boca: se aplana en un fuelle y se dobla hacia el frente (-Y)
    zt = zs[-1]
    base = loops[-1]
    for (dz, sq, fy) in ((0.02, 0.3, 0.0), (0.034, 0.07, -0.002), (0.041, 0.05, -0.014), (0.036, 0.045, -0.03)):
        loops.append([(x * 0.98, y * sq + fy, zt + dz) for (x, y, _) in base])
        mats.append(mat)
    mb = MB()
    skin(mb, loops, mat, mats=mats[:len(loops) - 1])
    return mb


def can(R=0.037, H=0.11, label="sign_red", seg=10, lod=0):
    """Lata de conserva: fondo con cejas, doble engargolado arriba y abajo, tapa rehundida; la etiqueta es un tramo del perfil
    (material propio, sin calcomanía). lod=1: versión de fila trasera (sin fondo visto)."""
    mb = MB()
    if lod == 0:
        prof = [(0.0, 0.002), (R * 0.92, 0.0), (R, 0.004), (R * 0.985, 0.0095), (R * 0.985, H - 0.0095), (R, H - 0.004),
                (R * 0.97, H), (R * 0.88, H - 0.0045), (0.0, H - 0.0045)]
        mats = ["steel", "steel", "steel", label, "steel", "steel", "steel", "steel"]
    else:
        prof = [(R * 0.985, 0.0), (R * 0.985, H - 0.0095), (R, H - 0.004), (R * 0.97, H), (R * 0.88, H - 0.0045), (0.0, H - 0.0045)]
        mats = [label, "steel", "steel", "steel", "steel"]
    revolve(mb, prof, mats, seg=seg)
    return mb


def oil_bottle(mat="amber", label="paper", cap="plastic_blue"):
    """Botella PET de aceite de 1 L: base de pétalos (insinuada), cintura, hombro, cuello con anillo, tapa estriada; etiqueta
    como tramo del perfil."""
    mb = MB()
    R = 0.04
    prof = [(0.0, 0.004), (R * 0.97, 0.0), (R, 0.03), (R * 0.93, 0.085), (R * 0.93, 0.15), (R, 0.162), (R, 0.2), (R * 0.72, 0.236),
            (0.0135, 0.262), (0.0135, 0.266)]
    mats = [mat, mat, mat, label, mat, mat, mat, mat, mat]
    revolve(mb, prof, mats, seg=10)
    revolve(mb, [(0.0165, 0.2655), (0.0165, 0.2685), (0.0142, 0.27)], "plastic", seg=10, caps=False)   # anillo
    revolve(mb, [(0.0152, 0.2695), (0.0158, 0.2715), (0.0158, 0.287), (0.0146, 0.289), (0.0, 0.2895)], cap, seg=10, caps=False)
    return mb


def jug(mat="plastic", cap="plastic_blue", label="sign_blue"):
    """Garrafa de cloro de 1 gal: cuerpo de sección cuadrada redondeada, asa hueca integrada, cuello y tapa; etiqueta como
    banda de material del cuerpo."""
    mb = MB()
    lv = [(0.0, 0.135, 0.135), (0.004, 0.142, 0.142), (0.02, 0.145, 0.145), (0.11, 0.145, 0.145), (0.2, 0.145, 0.145),
          (0.235, 0.13, 0.13), (0.26, 0.08, 0.08), (0.27, 0.05, 0.05)]
    loops = [[(x, y, z) for (x, y) in rr_pts(a, b, min(a, b) * 0.3, 2)] for (z, a, b) in lv]
    skin(mb, loops, mat, mats=[mat, mat, label, mat, mat, mat, mat])
    revolve(mb, [(0.019, 0.268), (0.019, 0.285), (0.0205, 0.287), (0.0205, 0.305), (0.018, 0.307), (0.0, 0.307)], cap, seg=8,
            caps=False)
    mb.tube([(0.03, 0.03, 0.25), (0.066, 0.066, 0.262), (0.08, 0.08, 0.24), (0.079, 0.079, 0.21), (0.052, 0.052, 0.19)], 0.011,
            seg=6, mat=mat)
    return mb


def carton(w, d, h, seed=0, tape=True, mat="cardboard", tape_mat="paper", open_flaps=None, crush=0.0):
    """Caja de cartón corrugado cerrada: cuerpo con cantos un poco aplastados y costados abombados, tapas superiores (dos
    solapas largas con junta de 3 mm al centro), cinta canela sobre la junta que baja por los costados, ceja de la solapa
    de unión en una esquina. open_flaps=(a1, a2): solapas abiertas (grados) y caja hueca con fondo."""
    r = rng(seed)
    mb = MB()
    hb = h - 0.004
    if open_flaps is None:
        slab(mb, _T(0, 0, 0), w, d, hb, rc=0.004, re=0.004 + crush, mat=mat, nc=1, ne=1)
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
            for s in (-1, 1):
                yy = s * (d / 2 + 0.0012)
                mb.box((-tw / 2, min(yy, yy - s * 0.0011), hb - 0.06), (tw / 2, max(yy, yy - s * 0.0011), zt + 0.0004), tape_mat,
                       bevel=0.0)
        mb.box((w / 2 - 0.0005, -d / 2 + 0.012, 0.01), (w / 2 + 0.003, d / 2 - 0.012, hb - 0.012), mat, bevel=0.0008, seg=1)  # ceja
    else:
        t = 0.004
        cupw = [(x, y) for (x, y) in rr_pts(w, d, 0.004, 1)]
        cupi = [(x, y) for (x, y) in rr_pts(w - 2 * t, d - 2 * t, 0.002, 1)]
        loops = [[(x, y, 0.0) for (x, y) in cupw], [(x, y, hb) for (x, y) in cupw], [(x, y, hb) for (x, y) in cupi],
                 [(x, y, t) for (x, y) in cupi]]
        skin(mb, loops, mat)
        for (s, ax, L_, ang) in ((-1, "y", d, open_flaps[0]), (1, "y", d, open_flaps[1])):
            Mf = _T(s * (w / 2 - t / 2), 0, hb) @ _Ry(s * (90 - ang))
            board(mb, -t / 2, t / 2, -d / 2 + 0.002, d / 2 - 0.002, 0.0, w / 2 - 0.004, mat, rc=0.002, re=0.0015, M=Mf)
        for (s, ang) in ((-1, open_flaps[0] * 0.8), (1, open_flaps[1] * 1.1)):
            Mf = _T(0, s * (d / 2 - t / 2), hb) @ _Rx(-s * (90 - ang))
            board(mb, -w / 2 + 0.003, w / 2 - 0.003, -t / 2, t / 2, 0.0, d / 2 - 0.004, mat, rc=0.002, re=0.0015, M=Mf)
    return mb


def tp_pack(mat="plastic", band="sign_blue", n=12):
    """Paquete de 4 rollos de papel higiénico (2 × 2, de pie) envuelto en plástico: contorno de 4 lóbulos con hundidos entre
    rollos, envoltura doblada arriba y abajo con hundido de los canutos; franja impresa como banda del cuerpo."""
    mb = MB()
    Rr = 0.054
    Hh = 0.102

    def ring(z, inset, dent=0.035):
        out = []
        for k in range(n):
            a = 2 * PI * k / n + PI / n
            c, s_ = math.cos(a), math.sin(a)
            ex = 3.2
            x = (2 * Rr - inset) * math.copysign(abs(c) ** (2 / ex), c)
            y = (2 * Rr - inset) * math.copysign(abs(s_) ** (2 / ex), s_)
            f = 1 - dent * math.cos(2 * a) ** 2
            out.append((x * f, y * f, z))
        return out
    lv = [(0.0, 0.016), (0.004, 0.006), (0.012, 0.0), (0.04, 0.0), (0.062, 0.0), (Hh - 0.012, 0.0), (Hh - 0.004, 0.006),
          (Hh, 0.016), (Hh - 0.004, 0.06)]
    loops = [ring(z, i_) for (z, i_) in lv]
    mats = [mat, mat, mat, band, mat, mat, mat, mat]
    skin(mb, loops, mat, mats=mats)
    return mb


def jar_candle(print_mat="sign_white", R=0.029, H=0.2, seg=8):
    """Veladora: vaso de vidrio con fondo grueso, manga impresa (material del tramo), labio, cera rehundida y pabilo."""
    mb = MB()
    prof = [(0.0, 0.004), (R * 0.9, 0.0), (R, 0.006), (R, 0.022), (R, H - 0.016), (R, H), (R - 0.0022, H), (R - 0.0022, H - 0.013),
            (0.0, H - 0.013)]
    revolve(mb, prof, ["glass", "glass", "glass", print_mat, "glass", "glass", "glass", "plastic"], seg=seg)
    mb.cyl((0, 0, H - 0.0135), (0.0008, 0, H - 0.003), 0.0009, seg=4, mat="cable")
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
    mb.tube(pts, rr, seg=5, mat=mat)
    zt = rr * (1 + 0.6 * turns) + rr
    for a in (0.7, 3.9):                                        # amarres
        c, s_ = math.cos(a), math.sin(a)
        loop = []
        for k in range(9):
            b = 2 * PI * k / 8
            loop.append(((R + (rr + 0.006) * math.cos(b)) * c, (R + (rr + 0.006) * math.cos(b)) * s_,
                         zt / 2 + (zt / 2 + 0.004) * math.sin(b)))
        mb.tube(loop, 0.004, seg=4, mat=mat)
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


def _put(mb, hero, x, y, z, rz=0.0, s=1.0, extra=None):
    M = _T(x, y, z) @ _Rz(rz)
    if s != 1.0:
        M = M @ Matrix.Diagonal((s, s, s, 1.0))
    if extra is not None:
        M = M @ extra
    mb.join(hero, M)


def _stock_canned(mb, r, H, x0, x1, y0, y1, z, zmax, kind):
    """Grupos de latas (frentes de 2-5, de 1 a 3 en fondo, a veces estibadas), huecos de lo vendido; arriba cajas cerradas."""
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
    sizes = [(0.0375, 0.112), (0.033, 0.074), (0.042, 0.122)] if kind != "bottom" else [(0.05, 0.142), (0.0375, 0.112)]
    x = x0 + _f(r.uniform(0.0, 0.015))
    first = True
    while x < x1 - 0.06:
        if not first and r.random() < 0.14:                    # hueco: se vendió
            x += _f(r.uniform(0.05, 0.12))
            continue
        first = False
        R, Hc = sizes[int(r.integers(0, len(sizes)))]
        lab = LABELS[int(r.integers(0, len(LABELS)))]
        pitch = 2 * R + 0.0025
        f = int(r.integers(2, 6))
        f = min(f, int((x1 - x) / pitch))
        if f < 1:
            break
        rows = int(r.integers(1, 4))
        stack = (2 * Hc < zmax - z - 0.01) and r.random() < 0.35
        for fi in range(f):
            cx = x + R + fi * pitch + _jit(r, 0.0015)
            for k in range(rows):
                cy = y0 + 0.004 + R + k * (2 * R + 0.003) + _jit(r, 0.002)
                if cy + R > y1:
                    break
                lod = 0 if k == 0 else 1
                hero = H.get(("can", R, Hc, lab, lod), lambda: can(R, Hc, lab, seg=10 if lod == 0 else 7, lod=lod))
                _put(mb, hero, cx, cy, z, rz=_f(r.uniform(0, 360)))
                if stack and (k == 0 or r.random() < 0.5) and not (fi == f - 1 and r.random() < 0.5):
                    _put(mb, hero, cx + _jit(r, 0.0015), cy + _jit(r, 0.0015), z + Hc - 0.0012, rz=_f(r.uniform(0, 360)))
        x += f * pitch + _f(r.uniform(0.006, 0.025))
    if kind == "bottom":
        pass


def _stock_dry(mb, r, H, x0, x1, y0, y1, z, zmax, kind, lvl):
    """Abarrotes secos: costales abajo, pilas de bolsas de arroz/frijol acostadas, bolsas de papel de harina/azúcar paradas,
    botellas de aceite; arriba cajas y un costal."""
    if kind == "bottom":
        x = x0 + 0.005
        for k in range(2):
            L, W, T = 0.56, 0.34, 0.13
            if x + L > x1 + 0.02:
                break
            hero = H.get(("sack", k), lambda: pillow_bag(L, W, T, mat="burlap", band=None, seed=7 + k, nu=14, nv=8, seal=0.035,
                                                          zr=0.42, wr=0.006, crimp=False))
            _put(mb, hero, x + L / 2, (y0 + y1) / 2 + _jit(r, 0.01), z, rz=_jit(r, 4))
            x += L + 0.015
        return
    if kind == "top":
        x = x0 + 0.01
        hero = H.get(("sack_top",), lambda: pillow_bag(0.5, 0.32, 0.12, mat="burlap", seed=11, nu=14, nv=8, seal=0.035, zr=0.42,
                                                       wr=0.006, crimp=False))
        _put(mb, hero, x + 0.25, (y0 + y1) / 2, z, rz=_jit(r, 8))
        x += 0.53
        cw, cd, ch = 0.3, 0.3, 0.2
        hero = H.get(("carton_dry",), lambda: carton(cw, cd, ch, seed=3))
        if x + cw < x1:
            _put(mb, hero, x + cw / 2, (y0 + y1) / 2, z, rz=_jit(r, 4))
        return
    plan = [("bags", "plastic", "sign_red"), ("paper", "paper", "sign_blue"), ("oil",), ("bags", "plastic", "paint_yellow")]
    sel = plan[lvl % len(plan)]
    sel2 = plan[(lvl + 1) % len(plan)]
    x = x0 + 0.004
    for part, cfg in ((0, sel), (1, sel2)):
        xend = (x0 + x1) / 2 + _jit(r, 0.1) if part == 0 else x1
        if cfg[0] == "bags":                                   # pilas de bolsas de 1 kg acostadas, largo hacia el fondo
            Lb, Wb, Tb = 0.2, 0.13, 0.05
            while x + Wb < xend:
                n = int(r.integers(2, 5))
                n = min(n, int((zmax - z) / (Tb * 0.92)))
                for k in range(n):
                    var = int(r.integers(0, 3))
                    hero = H.get(("bag", cfg[1], cfg[2], var), lambda: pillow_bag(Lb, Wb, Tb, mat=cfg[1], band=cfg[2], seed=21 + var,
                                                                                   nu=9, nv=5, seal=0.018))
                    _put(mb, hero, x + Wb / 2 + _jit(r, 0.006), y0 + Lb / 2 + 0.005 + _jit(r, 0.008), z + k * Tb * 0.9, rz=90 + _jit(r, 7))
                if r.random() < 0.4 and y1 - y0 > 2 * Lb:             # segunda pila detrás
                    for k in range(int(r.integers(1, n + 1))):
                        hero = H.get(("bag", cfg[1], cfg[2], 0), lambda: pillow_bag(Lb, Wb, Tb, mat=cfg[1], band=cfg[2], seed=21, nu=9,
                                                                                     nv=5, seal=0.018))
                        _put(mb, hero, x + Wb / 2 + _jit(r, 0.006), y0 + 1.5 * Lb + 0.01, z + k * Tb * 0.9, rz=90 + _jit(r, 7))
                x += Wb + _f(r.uniform(0.004, 0.012))
        elif cfg[0] == "paper":                                # bolsas de papel paradas en dos filas
            bw, bd, bh = 0.115, 0.07, 0.23
            while x + bw < xend:
                for k in range(2 if r.random() < 0.7 else 1):
                    var = int(r.integers(0, 2))
                    hero = H.get(("pbag", var), lambda: paper_bag(bw, bd, bh, band=cfg[2], seed=31 + var))
                    _put(mb, hero, x + bw / 2, y0 + bd / 2 + 0.006 + k * (bd + 0.01), z, rz=_jit(r, 5))
                x += bw + _f(r.uniform(0.004, 0.015))
        else:                                                  # aceite: botellas en 2 filas
            while x + 0.085 < xend:
                for k in range(2 if r.random() < 0.75 else 1):
                    hero = H.get(("oil",), lambda: oil_bottle())
                    _put(mb, hero, x + 0.041, y0 + 0.045 + k * 0.085, z, rz=_f(r.uniform(-30, 30)))
                x += 0.084 + _f(r.uniform(0.0, 0.006))
        x = max(x, xend) + 0.01


def _stock_household(mb, r, H, x0, x1, y0, y1, z, zmax, kind, lvl):
    """Mercería y ferretería: garrafas de cloro y soga abajo; paquetes de papel higiénico; veladoras y pilas; herramienta;
    arriba cajas y paquetes."""
    if kind == "bottom":
        x = x0 + 0.005
        for k in range(4):
            hero = H.get(("jug",), lambda: jug())
            _put(mb, hero, x + 0.074, y0 + 0.08 + (0.0 if k % 2 == 0 else 0.15), z, rz=_jit(r, 12) + (0 if k % 2 else 90))
            x += 0.15 if k % 2 else 0.0
            if k % 2 == 0:
                continue
        x += 0.02
        hero = H.get(("rope",), lambda: rope_coil(seed=5))
        _put(mb, hero, x + 0.14, (y0 + y1) / 2, z, rz=_f(r.uniform(0, 360)))
        x += 0.31
        if x + 0.25 < x1:
            hero = H.get(("cart_h",), lambda: carton(0.25, 0.3, 0.2, seed=9, open_flaps=(70, 100)))
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
    sel = lvl % 3
    if sel == 1:                                               # papel higiénico: paquetes de 4 en 2 alturas
        x = x0 + 0.003
        while x + 0.22 < x1:
            n = 2 if (zmax - z) > 0.22 else 1
            for k in range(n):
                for j in range(2 if (r.random() < 0.4 and k == 0) else 1):
                    _put(mb, H.get(("tp",), lambda: tp_pack()), x + 0.108, y0 + 0.11 + j * 0.22, z + k * 0.1, rz=_jit(r, 4))
            x += 0.222
    elif sel == 2:                                             # veladoras y exhibidor de pilas
        x = x0 + 0.005
        for k in range(int(r.integers(6, 10))):
            pm = ("sign_white", "sign_red", "sign_green")[k % 3]
            hero = H.get(("candle", pm), lambda: jar_candle(pm))
            for j in range(2 if r.random() < 0.5 else 1):
                _put(mb, hero, x + 0.03, y0 + 0.035 + j * 0.065, z, rz=_f(r.uniform(0, 360)))
            x += 0.062
        x += 0.03
        _put(mb, H.get(("batt",), lambda: battery_box(seed=2)), x + 0.075, y0 + 0.06, z, rz=_jit(r, 5))
        x += 0.18
        if x + 0.25 < x1:                                      # paquetes de velas de parafina envueltos en papel
            hero = H.get(("candles_pk",), lambda: pillow_bag(0.24, 0.07, 0.035, mat="paper", band="sign_red", seed=71, nu=7, nv=4,
                                                             seal=0.02, zr=0.45, wr=0.0012))
            for k in range(4):
                _put(mb, hero, x + 0.12 + _jit(r, 0.01), y0 + 0.05 + (k % 2) * 0.08, z + (k // 2) * 0.033, rz=_jit(r, 6))
    else:                                                      # herramienta: machetes al frente, martillos detrás, clavos, soga
        x = x0 + 0.16
        for k in range(2):
            _put(mb, H.get(("mach",), lambda: machete()), x + k * 0.03, y0 + 0.03 + k * 0.022, z + 0.0011 + k * 0.0102,
                 rz=_jit(r, 2) + k * 3)
        for k in range(2):
            _put(mb, H.get(("ham",), lambda: hammer()), x0 + 0.1 + k * 0.17, y0 + 0.075, z + 0.0118, rz=90 + _jit(r, 6))
        x = x0 + 0.68
        for k in range(2):
            _put(mb, H.get(("nails",), lambda: carton(0.12, 0.08, 0.07, seed=60, tape=False)), x + 0.06, y0 + 0.05 + k * 0.1, z,
                 rz=_jit(r, 8))
        x += 0.15
        if x + 0.24 < x1:
            _put(mb, H.get(("rope2",), lambda: rope_coil(seed=6, R=0.1, rr=0.007, turns=5.5, mat="burlap")), x + 0.12,
                 (y0 + y1) / 2, z, rz=_f(r.uniform(0, 360)))


def grocery_shelving(w=1.2, d=0.40, h=2.0, seed=0, stock="canned"):
    """Anaquel de remache de lámina gris (sin tornillos) contra el muro: postes de ángulo ranurado, largueros con remaches,
    entrepaños de lámina con canal, regatones y escuadra antivuelco; surtido según `stock`:
    "canned" latas (grupos con frentes, fondo, estibas y huecos; cajas arriba), "dry" costales, bolsas de arroz/frijol, bolsas de
    papel de harina, aceite; "household" garrafas de cloro, soga, papel higiénico, veladoras, pilas, herramienta.
    La mercancía son unas cuantas mallas héroe instanciadas con jitter por semilla."""
    r = rng(seed)
    mb = MB()
    levels = snap_levels(h, 5, z_first=0.10, z_top=h - 0.08)
    shelving_frame(mb, w, d, h, levels)
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
    return mb

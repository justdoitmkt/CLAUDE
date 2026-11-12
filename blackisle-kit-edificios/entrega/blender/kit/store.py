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
from kit.clinic_equipo import angle_l, loft_rings, revolve, sweep_frame, weld  # noqa: F401
from kit.clinic_equipo import chain as echain
from kit.clinic_equipo import rtube_lo, screw_lo
from kit.clinic_equipo import text as etext
from kit.clinic_servicios import foot_leveler, holed, hose, louver_grille, rr_pts, rrframe, skin, slab  # noqa: F401
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


def can(R=0.037, H=0.11, label="sign_red", seg=14, lod=0):
    """Lata de conserva: fondo con ceja, doble engargolado arriba, tapa rehundida; la etiqueta es un tramo del perfil
    (material propio, sin calcomanía). seg >= 13: el sombreado suave del kit (30°) no la facetea. lod=1: fila trasera."""
    mb = MB()
    if lod == 0:
        prof = [(R * 0.95, 0.0), (R * 0.985, 0.006), (R * 0.97, 0.0095), (R * 0.97, H - 0.0095), (R, H - 0.0058), (R, H - 0.0012),
                (R * 0.89, H - 0.0045), (0.0, H - 0.0045)]
        mats = ["steel", "steel", label, "steel", "steel", "steel", "steel"]
    else:
        prof = [(R * 0.985, 0.0), (R * 0.985, H - 0.0095), (R, H - 0.0025), (R * 0.88, H - 0.0045), (0.0, H - 0.0045)]
        mats = [label, "steel", "steel", "steel"]
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
    mb.tube([(0.03, 0.03, 0.25), (0.066, 0.066, 0.262), (0.08, 0.08, 0.24), (0.079, 0.079, 0.21), (0.052, 0.052, 0.19)], 0.011,
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
        rows = int(r.choice([1, 1, 2, 2, 2, 3]))
        stack = (2 * Hc < zmax - z - 0.01) and r.random() < 0.3
        for fi in range(f):
            cx = x + R + fi * pitch + _jit(r, 0.0015)
            for k in range(rows):
                cy = y0 + 0.004 + R + k * (2 * R + 0.003) + _jit(r, 0.002)
                if cy + R > y1:
                    break
                lod = 0 if k == 0 else 1
                hero = H.get(("can", R, Hc, lab, lod), lambda: can(R, Hc, lab, seg=14 if lod == 0 else 13, lod=lod))
                i0 = _put(mb, hero, cx, cy, z, rz=_f(r.uniform(0, 360)), prio=2 if k else 0)
                if stack and (k == 0 or r.random() < 0.5) and not (fi == f - 1 and r.random() < 0.5):
                    _put(mb, hero, cx + _jit(r, 0.0015), cy + _jit(r, 0.0015), z + Hc - 0.0012, rz=_f(r.uniform(0, 360)),
                         prio=2 if k else 1, on=i0)
        x += f * pitch + _f(r.uniform(0.006, 0.025))


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
    plan = {1: (("paper", "paper", "sign_blue"), ("bags", "plastic", "sign_red")),
            2: (("oil",), ("bags", "plastic", "paint_yellow")),
            3: (("bags", "plastic", "sign_green"), ("paper", "paper", "sign_red"))}
    sel, sel2 = plan[1 + (lvl - 1) % 3]
    x = x0 + 0.004
    for part, cfg in ((0, sel), (1, sel2)):
        xend = (x0 + x1) / 2 + _jit(r, 0.1) if part == 0 else x1
        if cfg[0] == "bags":                                   # pilas de bolsas de 1 kg acostadas, largo hacia el fondo
            Lb, Wb, Tb = 0.2, 0.13, 0.05
            while x + Wb < xend:
                n = int(r.integers(2, 4))
                n = min(n, int((zmax - z) / (Tb * 0.92)))
                below = None
                for k in range(n):
                    var = int(r.integers(0, 3))
                    hero = H.get(("bag", cfg[1], cfg[2], var), lambda: pillow_bag(Lb, Wb, Tb, mat=cfg[1], band=cfg[2], seed=21 + var,
                                                                                   nu=11, nv=7, seal=0.018))
                    below = _put(mb, hero, x + Wb / 2 + _jit(r, 0.006), y0 + Lb / 2 + 0.005 + _jit(r, 0.008), z + k * Tb * 0.9,
                                 rz=90 + _jit(r, 7), prio=1 if k else 0, on=below)
                if r.random() < 0.3 and y1 - y0 > 2 * Lb:             # segunda pila detrás
                    below = None
                    for k in range(int(r.integers(1, n + 1))):
                        hero = H.get(("bag", cfg[1], cfg[2], 0), lambda: pillow_bag(Lb, Wb, Tb, mat=cfg[1], band=cfg[2], seed=21, nu=11,
                                                                                     nv=7, seal=0.018))
                        below = _put(mb, hero, x + Wb / 2 + _jit(r, 0.006), y0 + 1.5 * Lb + 0.01, z + k * Tb * 0.9, rz=90 + _jit(r, 7),
                                     prio=2, on=below)
                x += Wb + _f(r.uniform(0.004, 0.012))
        elif cfg[0] == "paper":                                # bolsas de papel paradas en dos filas
            bw, bd, bh = 0.115, 0.07, 0.23
            while x + bw < xend:
                for k in range(2 if r.random() < 0.4 else 1):
                    var = int(r.integers(0, 2))
                    hero = H.get(("pbag", var), lambda: paper_bag(bw, bd, bh, band=cfg[2], seed=31 + var))
                    _put(mb, hero, x + bw / 2, y0 + bd / 2 + 0.006 + k * (bd + 0.01), z, rz=_jit(r, 5), prio=2 if k else 0)
                x += bw + _f(r.uniform(0.004, 0.015))
        else:                                                  # aceite: botellas en 2 filas
            while x + 0.085 < xend:
                for k in range(2 if r.random() < 0.5 else 1):
                    hero = H.get(("oil",), lambda: oil_bottle())
                    _put(mb, hero, x + 0.041, y0 + 0.045 + k * 0.085, z, rz=_f(r.uniform(-30, 30)), prio=2 if k else 0)
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
    sel = lvl % 3
    if sel == 1:                                               # papel higiénico: paquetes de 4 en 2 alturas
        x = x0 + 0.003
        while x + 0.22 < x1:
            n = 2 if (zmax - z) > 0.22 else 1
            below = None
            for k in range(n):
                for j in range(2 if (y1 - y0 > 0.44 and k == 0) else 1):
                    i_ = _put(mb, H.get(("tp",), lambda: tp_pack()), x + 0.108, y0 + 0.11 + j * 0.22, z + k * 0.1, rz=_jit(r, 4),
                              prio=2 if j else (1 if k else 0), on=below if j == 0 else None)
                    if j == 0:
                        below = i_
            x += 0.222
    elif sel == 2:                                             # veladoras y exhibidor de pilas
        x = x0 + 0.005
        for k in range(int(r.integers(6, 10))):
            pm = ("sign_white", "sign_red", "sign_green")[k % 3]
            hero = H.get(("candle", pm), lambda: jar_candle(pm))
            for j in range(2 if r.random() < 0.5 else 1):
                _put(mb, hero, x + 0.03, y0 + 0.035 + j * 0.065, z, rz=_f(r.uniform(0, 360)), prio=2 if j else 0)
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
            _put(mb, H.get(("ham",), lambda: hammer()), x0 + 0.1 + k * 0.17, y0 + 0.062, z + 0.0118, rz=90 + _jit(r, 5))
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
    mb.flush(r, 19500)
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
    mb.tube([(cx + x, cy + y, z) for (x, y) in rim] + [(cx + rim[0][0], cy + rim[0][1], z)], R, seg=5, mat="steel")
    mb.tube([(x0 + 0.004, y0, z + lip), (x1 - 0.004, y0, z + lip)], R, seg=5, mat="steel")                 # tope frontal
    for x in (x0 + 0.004, x1 - 0.004):
        mb.tube([(x, y0, z), (x, y0, z + lip)], R * 0.8, seg=4, mat="steel")
    for yy in (y0 + 0.12, y1 - 0.12):
        mb.cyl((x0 + 0.002, yy, z - R - 0.0018), (x1 - 0.002, yy, z - R - 0.0018), 0.002, seg=4, mat="steel")
    n = int((x1 - x0 - 0.02) / pitch)
    for i in range(1, n + 1):
        x = x0 + (x1 - x0) * i / (n + 1)
        mb.cyl((x, y0 + 0.002, z), (x, y1 - 0.002, z), rw, seg=4, mat="steel")


def beer_cooler(seed=0):
    """Refrigerador vertical de puerta de vidrio para bebidas, 0,65 × 0,65 × 2,0 (origen al centro de la huella, frente -Y):
    gabinete de lámina con cantos redondeados, marco frontal, puerta de perfil de aluminio con doble vidrio, empaque magnético,
    jaladera de barra con bases, bisagras de pivote y chapa; interior con forro, cremalleras y 4 parrillas de alambre llenas de
    botellas ámbar y latas sin etiqueta (frentes completos, fondo a medias); copete superior iluminado con la palabra COLD en
    relieve, rejilla inferior de persianas, patas niveladoras y cordón."""
    r = rng(seed)
    base = MB()
    mb = base
    W, D, Hc = 0.65, 0.65, 2.0
    zb, zc = 0.13, 1.79                                          # zoclo y copete
    yf = -D / 2
    # gabinete: costados, espalda, techo y piso de lámina (forro interior blanco = mismas piezas, cara interior)
    for s in (-1, 1):
        board(mb, min(s * W / 2, s * (W / 2 - 0.045)), max(s * W / 2, s * (W / 2 - 0.045)), yf + 0.035, D / 2, 0.0, zc, "enamel",
              rc=(0.0, 0.0, 0.0, 0.0), re=0.004)
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, D / 2 - 0.05, D / 2, 0.0, zc, "enamel", rc=0.002, re=0.003)
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, yf + 0.035, D / 2 - 0.05, zc - 0.05, zc, "enamel", rc=0.002, re=0.002)
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, yf + 0.035, D / 2 - 0.05, zb, zb + 0.05, "enamel", rc=0.002, re=0.002)
    board(mb, -W / 2 + 0.045, W / 2 - 0.045, yf + 0.06, D / 2 - 0.05, 0.03, zb, "cable", rc=0.002, re=0.002)       # cuarto de máquina
    # marco frontal (perímetro del vano) y copete
    Mf = _T(0, yf + 0.035, 0) @ _Rx(90)
    zf0 = 0.03
    rrframe(mb, Mf, (0, (zf0 + zc) / 2, W, zc - zf0, 0.012), (0, (zb + 0.06 + zc - 0.05) / 2, W - 0.09, zc - 0.05 - zb - 0.06, 0.008),
            0.035, re_o=0.006, re_i=0.003, n=3, ne=2, mat="enamel")
    slab(mb, _T(0, 0.0, zc), W + 0.01, D, Hc - zc, rc=(0.014, 0.014, 0.02, 0.02), re=0.008, re0=0.003, mat="enamel", nc=3, ne=2)
    # caja de luz del copete: marco + acrílico + letras COLD en relieve
    yl = -D / 2
    rrframe(mb, _T(0, yl, 0) @ _Rx(90), (0, zc + (Hc - zc) / 2, W - 0.03, Hc - zc - 0.04, 0.008),
            (0, zc + (Hc - zc) / 2, W - 0.09, Hc - zc - 0.08, 0.004), 0.012, re_o=0.004, re_i=0.002, n=2, ne=2, mat="aluminium")
    board(mb, -W / 2 + 0.05, W / 2 - 0.05, yl - 0.006, yl + 0.002, zc + 0.045, Hc - 0.045, "sign_white", rc=0.002, re=0.001)
    etext(mb, "COLD", 0.085, 0.0035, "sign_blue", _T(0, yl - 0.006, zc + (Hc - zc) / 2 - 0.03) @ _Rx(90), res=2, back=False,
          bold=True)
    # zoclo: rejilla de persianas
    louver_grille(mb, _T(0, yf, (zf0 + zb) / 2 + 0.002) @ _Rx(90), W - 0.12, zb - zf0 - 0.025, 5, mat="enamel", back_mat="cable",
                  t=0.01, frame=0.01, slat_ang=40, depth=-0.0005, nr=24)
    for x in (-W / 2 + 0.06, W / 2 - 0.06):
        for y in (yf + 0.07, D / 2 - 0.07):
            foot_leveler(mb, _T(x, y, 0.0), r=0.02, h=0.035, lite=True)
    # puerta: perfil de aluminio con doble vidrio, empaque, jaladera, bisagras y chapa
    yd = yf - 0.008                                              # cara trasera de la puerta (el empaque llena la holgura)
    dz0, dz1 = zb + 0.012, zc - 0.012
    Md = _T(0, yd, 0) @ _Rx(90)
    zcd = (dz0 + dz1) / 2
    rrframe(mb, Md, (0, zcd, W - 0.012, dz1 - dz0, 0.01), (0, zcd + 0.01, W - 0.012 - 0.11, dz1 - dz0 - 0.15, 0.006), 0.042,
            re_o=0.006, re_i=0.004, n=3, ne=2, mat="aluminium")
    for gy in (yd - 0.012, yd - 0.030):
        board(mb, -W / 2 + 0.06, W / 2 - 0.06, gy - 0.004, gy, dz0 + 0.06, dz1 - 0.04, "glass", rc=0.004, re=0.0015)
    path = [(x, yf - 0.004, zcd + z) for (x, z) in rr_pts(W - 0.04, dz1 - dz0 - 0.03, 0.014, 2)]
    mb.sweep([(u, v) for (u, v) in rr_pts(0.016, 0.009, 0.0035, 1)], path, mat="rubber", closed_path=True, normal=(0, 1, 0))
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
                hm = H.get(("c" if cans else "b", lod), lambda: fn(lod=lod, seg=14 if lod == 0 else 13))
                _put(P, hm, x, y, zs, rz=_f(r.uniform(0, 360)), prio=0 if row == 0 else (1 if row < 3 else 2))
                if cans and r.random() < 0.6 and i == 1:                     # latas estibadas
                    _put(P, hm, x, y, zs + 0.1222 - 0.004, rz=_f(r.uniform(0, 360)), prio=2)
    # cordón de corriente por detrás
    hose(mb, [(0.2, D / 2 - 0.02, 0.09), (0.2, D / 2 + 0.03, 0.09), (0.22, D / 2 + 0.035, 0.0045), (0.3, D / 2 + 0.03, 0.0045),
              (0.31, D / 2 - 0.04, 0.0045)], 0.0045, bend=0.03, mat="cable", seg=6, nseg=4)
    P.flush(r, 17600)
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
    mb.cyl((-W / 2 + 0.018, yh, zh), (W / 2 - 0.018, yh, zh), 0.0018, seg=8, mat="steel")
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


def chalkboard(w=0.9, h=1.2, seed=0):
    """Pizarrón de muro (origen: cara del muro, centro del canto inferior; sale hacia -Y): tablero verde de 12 mm dentro de un
    marco de moldura con ingletes y galce, pijas en las esquinas, repisa para gises con ceja y dos ménsulas; lista de precios
    escrita con gis (letras en relieve de 1,3 mm, renglones un poco chuecos, como a mano), gises (uno roto) y borrador."""
    r = rng(seed)
    mb = MB()
    zt0 = 0.03                                                   # la repisa ocupa los primeros 3 cm
    fw = 0.045                                                   # ancho de la moldura
    x0, x1, z0, z1 = -w / 2, w / 2, zt0, h
    # tablero (entra 14 mm bajo el galce del marco)
    board(mb, x0 + 0.025 + 0.0055, x1 - 0.025 - 0.0055, -0.012, -0.0002, z0 + 0.025 + 0.0055, z1 - 0.025 - 0.0055,
          "paint_green", rc=0.002, re=0.001)
    # marco de moldura (barrido con ingletes): perfil x hacia adentro, y hacia el muro (+Y) / cuarto (-Y)
    prof = [(-0.025, 0.0), (-0.025, -0.017), (-0.0235, -0.0215), (-0.019, -0.024), (-0.004, -0.024), (0.006, -0.0205), (0.016, -0.0178),
            (0.02, -0.0158), (0.02, -0.0125), (0.004, -0.0125), (0.004, 0.0)]
    cx0, cx1, cz0, cz1 = x0 + 0.025, x1 - 0.025, z0 + 0.025, z1 - 0.025
    mb.sweep(prof, [(cx0, 0.0, cz0), (cx1, 0.0, cz0), (cx1, 0.0, cz1), (cx0, 0.0, cz1)], mat="wood_dark", closed_path=True,
             normal=(0, 1, 0))
    for (x, z) in ((cx0, cz0), (cx1, cz0), (cx0, cz1), (cx1, cz1)):
        revolve(mb, [(0.0042, -0.0003), (0.0042, 0.0006), (0.0, 0.0012)], "steel", seg=8,
                M=_T(x - math.copysign(0.004, x), -0.024 + 0.0003 * 0, z - math.copysign(0.004, z - (z0 + z1) / 2)) @ _Rx(90))
    # repisa del gis con ceja + ménsulas
    tp = [(0.0, 0.0), (-0.075, 0.0), (-0.0785, 0.0035), (-0.0785, 0.018), (-0.0755, 0.0205), (-0.072, 0.018), (-0.0715, 0.009),
          (-0.012, 0.009), (-0.012, 0.03), (0.0, 0.03)]
    lofts(mb, [(x, [(y, z) for (y, z) in tp]) for x in (x0 - 0.01, x1 + 0.01)], "wood_dark")
    for x in (x0 + 0.08, x1 - 0.08):
        Mb_ = _T(x - 0.009, 0.0, 0.0) @ Matrix(((0, 0, 1, 0), (-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        mb.plate([(0.0, -0.0003), (0.05, -0.0003), (0.0, -0.075)], 0.018, "wood_dark", m=Mb_)
    # gises y borrador en la repisa (piso de la repisa en z = 0,009)
    for (xc, L, a) in ((-0.2, 0.08, 4.0), (-0.05, 0.034, -11.0), (0.05, 0.062, 2.0)):
        mb.cyl(_T(xc, -0.045, 0.009 + 0.0048) @ _Rz(a) @ Vector((-L / 2, 0, 0)), _T(xc, -0.045, 0.009 + 0.0048) @ _Rz(a) @ Vector((L / 2, 0, 0)),
               0.0048, seg=8, mat="sign_white")
    Me = _T(0.25, -0.042, 0.009) @ _Rz(-6)
    board(mb, -0.065, 0.065, -0.024, 0.024, 0.0, 0.006, "linen", rc=0.006, re=0.0025, M=Me)
    board(mb, -0.064, 0.064, -0.023, 0.023, 0.006, 0.024, "wood", rc=0.008, re=0.006, nc=2, ne=2, M=Me)
    # lista de precios con gis
    yb = -0.012
    xl, xr = x0 + fw + 0.04, x1 - fw - 0.04
    top = z1 - fw - 0.03
    tsz = min(0.075, (z1 - z0) * 0.062)
    zz = top - tsz
    M = _T(0, yb + 0.0003, zz) @ _Rx(90) @ _Rz(_jit(r, 0.8)) @ Matrix(((1, 0.12, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    etext(mb, "PRICE LIST", tsz, 0.0016, "sign_white", M, align="CENTER", res=2, back=False, bold=True)
    wt = 0.5 * w
    mb.box((-wt / 2, -0.0035, -0.0012), (wt / 2, 0.0015, 0.0013), "sign_white", bevel=0.0, m=_T(0, yb, zz - 0.016) @ _Rx(90) @
           _Rz(_jit(r, 0.6)))
    n = len(PRICES)
    lh = (zz - 0.03 - (z0 + fw + 0.04)) / n
    sz = min(lh * 0.62, 0.06)
    shear = Matrix(((1, 0.16, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))     # gis a mano: letra inclinada
    for i, (item, price) in enumerate(PRICES):
        zl = zz - 0.04 - (i + 1) * lh + lh * 0.25
        rot = _jit(r, 0.9)
        s_ = sz * _f(r.uniform(0.93, 1.05))
        etext(mb, item, s_, 0.0016, "sign_white", _T(xl + _jit(r, 0.006), yb + 0.0003, zl + _jit(r, 0.003)) @ _Rx(90) @ _Rz(rot) @
              shear, align="LEFT", res=2, back=False)
        etext(mb, price, s_, 0.0016, "sign_white", _T(xr + _jit(r, 0.004), yb + 0.0003, zl + _jit(r, 0.003)) @ _Rx(90) @
              _Rz(rot * 0.5) @ shear, align="RIGHT", res=2, back=False)
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
        tmp.tube([(0.006 * math.cos(2 * PI * k / 8), 0.0, 0.007 + 0.006 * math.sin(2 * PI * k / 8)) for k in range(9)], 0.0012, seg=4,
                 mat="steel")
        tmp.cyl((0, 0, -0.006), (0, 0, 0.0015), 0.0012, seg=4, mat="steel")
        mb.join(tmp, _T(x, yc, zc + hh / 2))
    pts = [(-0.1, yc, zc + hh / 2 + 0.013), (-0.05, yc + 0.003, -0.06), (0.0, -0.006, -0.004), (0.05, yc + 0.003, -0.06),
           (0.1, yc, zc + hh / 2 + 0.013)]
    mb.tube(pts, 0.0011, seg=4, mat="steel")
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
        mb.tube([(xh, -0.06, Hh - 0.02), (xh, 0.06, Hh - 0.02)], 0.011, seg=8, mat=mat)                 # travesaño del asa
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

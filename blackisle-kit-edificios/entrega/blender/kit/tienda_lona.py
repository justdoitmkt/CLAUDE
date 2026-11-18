"""kit/tienda_lona.py — tienda de campaña de armazón tipo TEMPER 20 × 32 ft (6,1 × 9,75 m) para MIL_2_avanzada (expendio de
munición y armas del puesto avanzado). Segunda pasada AAA (R-AAA): reemplaza a kit.campaign.frame_tent con la MISMA firma,
origen, orientación y huella.

Construcción (todo con su espesor real, sin cajas ni cilindros sueltos):
- Armazón de aluminio: 5 arcos de tubo de 1,75" (Ø 44,5 mm) de patas, cabios y codos fundidos (rodilla de alero y cumbrera)
  con casquillos de labio, jefe para el larguero, perno pasante con tuerca y pasador de seguridad con argolla; 5 líneas de
  largueros de Ø 38 mm (cumbrera, 2 aleros, 2 bases) con collarín remachado en cada punta; placa base galvanizada de 6 mm con
  casquillo soldado (cordón de soldadura), casquillos de larguero de base y 2 estacas forjadas hincadas.
- Cubierta de lona de poliéster recubierto de una capa (material `canvas`, de dos caras; vista por dentro y por fuera):
  malla densa (Catmull-Clark no hace falta: la superficie se muestrea a 1,2–4 cm con sombreado suave) con su peso: caída
  entre arcos y largueros con cresta sobre cada miembro, panzas por viento ligero (de +Y), arrugas de tensión en abanico desde
  las esquinas de cada paño y los amarres de los vientos, pliegues de cizalla diagonales, arrugas finas de compresión junto a
  las costuras, ruido de lona pesada; traslape de 95 mm de la cubierta de cada sección sobre el arco con su dobladillo y
  pespunte, amarrado al arco con cordón que pasa por pares de ojillos; costura doble (felled seam) a media agua con relieve y
  aristas reales; banda de refuerzo de cumbrera; faldón (valance) con dobladillo enrollado y ojillos; campanas sobre los
  testeros; parches de refuerzo con gaza de reata, argolla D y costura de caja con X donde amarran los vientos.
- Paredes: la del fondo cuelga cerrada del larguero de alero (lazada con cordón por ojillos) con festón, pliegues por
  gravedad, panza de viento y faldón (sod cloth) que toca el piso y se arruga, estacado con gazas de cordón a estacas; dos
  ventanas con ribete, malla mosquitera y cortina (solapa) enrollada y atada (una) o cerrada y atada (otra). La del frente
  enrollada hasta el alero: rollo real en espiral (capas visibles en las puntas, escalonadas), panzas, cintura bajo cada
  cinta, arrugas helicoidales y de pellizco; cintas de reata con hebilla de escalera.
- Testeros: lona tensada al arco extremo (lazada al tubo), esquinas lazadas con la pared del fondo, ventila de gablete con
  malla y solapa, puerta de 1,5 × 1,98 m: abierta (-X, hoja enrollada y atada sobre el vano, cremalleras de dientes moldeados
  a la vista en ambos lados del vano) o cerrada (+X, cremalleras bajo solapas de tormenta, una solapa doblada hacia atrás abajo
  que deja ver los dientes engranados, la corredera y el jalador).
- 12 vientos de cuerda de 3/8" + 2 de cumbrera: as de guía en la argolla, tensor de aluminio de 3 ojos, gaza a la estaca
  forjada de 18" × 5/8" con cabeza de hongo, chicote con nudo.

Ejes (como kit.campaign.frame_tent): origen en el piso al centro; largo L en X, ancho W en Y; FRENTE = pared larga en -Y,
FONDO = +Y; testeros (puertas) en -X y +X. Lona: cumbrera 3,20 m, alero 2,06 m. Piso interior: la tienda no trae piso; el de
triplay (z 0..0,108) cabe en x ±4,75, y ±2,9 sin tocar placas base ni lona (la lona baja hasta el suelo por fuera).

MEDIDAS (fuentes en el reporte / ESTADO.md):
- TEMPER tipo IV 20 × 32 ft: cumbrera 10'6", alero 6'9", secciones de 8 ft, 5 largueros por sección (cumbrera, 2 aleros,
  2 bases), armazón de aluminio plegable con cubierta de poliéster recubierto (DLA 4green.pdf; TM 10-8340-224-13).
- Ventanas TEMPER: abertura con malla, cierre de cremallera en 3 lados, cortina enrollable con cintas de amarre y solapa de
  oscurecimiento cosida arriba (TM 10-8340-224-13 / TM 10-8340-211-13).
- Estaca forjada 18" × 5/8" (NSN 8340-00-823-7461, usada en TEMPER); cuerda de viento 3/8".
- Cremallera de dientes moldeados #10 (paso ~3,6 mm, cadena ~10 mm), reata de 1" con hebilla de escalera.
"""
import math

import bmesh  # noqa: F401
import bpy  # noqa: F401  (bpy antes que mathutils)
import numpy as np
from mathutils import Matrix, Vector, noise

from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rr_profile  # noqa: F401
from kit.clinic import rng as _rng0
from kit.clinic_equipo import loop_tube, revolve, sweep_frame, weld  # noqa: F401
from kit.clinic_servicios import holed, rrframe, slab  # noqa: F401

SEG = 32          # tubos del armazón (se ven a < 1 m desde dentro)
SEG_M = 24        # cilindros visibles medianos
SEG_T = 14        # cuerdas y tubos delgados (con el suavizado de 30° del kit no se facetan)
SEG_F = 24        # piezas fundidas, casquillos y labios
R_A = 0.0222      # tubo de arco 1,75" (Ø 44,5 mm)
R_P = 0.0190      # larguero Ø 38 mm
R_F = R_A + 0.0055            # cuerpo de los codos fundidos (pared de 5,5 mm)
R_S = R_P + 0.0035            # casquillo de larguero
O = R_A + 0.0075              # eje del tubo -> cara de la lona sobre los codos
P_OFF = O - 0.001 - R_S       # eje del larguero de alero / cumbrera, desplazado hacia afuera del eje del arco
RK, RR = 0.075, 0.11          # radio del eje en el codo de alero y en el de cumbrera (piezas fundidas)
ARM = 0.13                    # largo de cada brazo de casquillo de los codos
EAVE, RIDGE = 2.06, 3.20
E_EMB = 0.00025               # empotramiento de capas sobrepuestas en la lona (bajo la cuerda de la malla)


# ======================================================================================================== utilidades
def rng(seed):
    return _rng0(abs(int(seed)) % 2147483647)


def _f(x):
    return float(x)


def _jit(r, a):
    return _f(r.uniform(-a, a))


def _ss(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _cosspace(a, b, n):
    t = np.linspace(0.0, 1.0, n + 1)
    return a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * t))


def _merge(base, forced, eps=0.0025):
    """Une muestras: las forzadas quedan exactas y se quitan las base a menos de eps de alguna forzada."""
    forced = sorted(set(round(_f(v), 7) for v in forced))
    fa = np.array(forced) if forced else np.zeros(0)
    out = [v for v in base if fa.size == 0 or np.min(np.abs(fa - v)) > eps] + forced
    out = sorted(out)
    res = [out[0]]
    for v in out[1:]:
        if v - res[-1] > 2e-5:
            res.append(v)
    return np.array(res)


def _frame_z(p, z_axis, x_hint=(1, 0, 0)):
    """Matriz con origen p y eje Z local = z_axis (X local lo más cerca de x_hint)."""
    Z = Vector(z_axis).normalized()
    X = Vector(x_hint)
    X = X - Z * X.dot(Z)
    if X.length < 1e-6:
        X = Vector((0, 1, 0)) - Z * Z.y
    X.normalize()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p[0]), (X.y, Y.y, Z.y, p[1]), (X.z, Y.z, Z.z, p[2]), (0, 0, 0, 1)))


def _frame_x(p, x_axis, up=(0, 0, 1)):
    """Matriz con origen p, X local = x_axis y Z local lo más cerca de `up`."""
    X = Vector(x_axis).normalized()
    U = Vector(up)
    if abs(X.dot(U.normalized())) > 0.995:
        U = Vector((0, 1, 0)) if abs(X.y) < 0.9 else Vector((1, 0, 0))
    Z = (U - X * X.dot(U)).normalized()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p[0]), (X.y, Y.y, Z.y, p[1]), (X.z, Y.z, Z.z, p[2]), (0, 0, 0, 1)))


def _lathe(mb, prof, M, mat, seg=SEG_M, closed=False, soft=False, caps=True):
    if soft:
        with mb.soft():
            revolve(mb, prof, mat, seg=seg, M=M, closed=closed, caps=caps)
    else:
        revolve(mb, prof, mat, seg=seg, M=M, closed=closed, caps=caps)


def _cyl(mb, p0, p1, r, mat, seg=SEG_M, caps=True):
    mb.cyl(p0, p1, r, seg=seg, mat=mat, caps=caps)


def _tube(mb, pts, r, mat="fabric", seg=SEG_T, caps=True, rad=None, nseg=4, soft=False):
    """Cuerda / tubo por una polilínea (con esquinas redondeadas a radio `rad`)."""
    P = [tuple(_f(c) for c in p) for p in pts]
    if rad:
        P = fillet(P, rad, nseg)
    Q = [P[0]]
    for p in P[1:]:
        if (Vector(p) - Vector(Q[-1])).length > 1e-5:
            Q.append(p)
    if len(Q) < 2:
        return
    if soft:
        with mb.soft():
            mb.tube(Q, r, seg=seg, mat=mat, caps=caps)
    else:
        mb.tube(Q, r, seg=seg, mat=mat, caps=caps)


def _cord(mb, pts, r=0.0028, mat="fabric", rad=0.006, caps=True):
    """Cordón de amarre (<= 6 mm): 12 lados con sombreado continuo."""
    _tube(mb, pts, r, mat=mat, seg=12, caps=caps, rad=rad, soft=True)


def _noise2(A, B, f, seed, C=None):
    A = np.asarray(A, float)
    B = np.asarray(B, float)
    Cc = np.zeros_like(A) if C is None else np.broadcast_to(np.asarray(C, float), A.shape)
    nz = noise.noise
    o1, o2 = seed * 7.31 + 0.37, -seed * 3.7 + 0.11
    out = np.fromiter((nz(Vector((a * f + o1, b * f + o2, c * f + 0.5))) for a, b, c in zip(A.ravel(), B.ravel(), Cc.ravel())),
                      float, count=A.size)
    return out.reshape(A.shape)


def _grid(mb, P, mat, mask=None):
    """Rejilla de cuadriláteros (nu, nv, 3); mask[i, j] = emitir la celda (i, j). Solo crea los vértices usados."""
    nu, nv = P.shape[0], P.shape[1]
    if mask is None:
        mask = np.ones((nu - 1, nv - 1), bool)
    used = np.zeros((nu, nv), bool)
    used[:-1, :-1] |= mask
    used[1:, :-1] |= mask
    used[1:, 1:] |= mask
    used[:-1, 1:] |= mask
    idx = -np.ones((nu, nv), np.int64)
    pts = P[used]
    idx[used] = np.arange(len(pts))
    bm = mb.bm
    vs = [bm.verts.new(tuple(p)) for p in pts.tolist()]
    mi = mb.mi(mat)
    I, J = np.nonzero(mask)
    a = idx[I, J]
    b = idx[I + 1, J]
    c = idx[I + 1, J + 1]
    d = idx[I, J + 1]
    for q in zip(a.tolist(), b.tolist(), c.tolist(), d.tolist()):
        f = bm.faces.new((vs[q[0]], vs[q[1]], vs[q[2]], vs[q[3]]))
        f.material_index = mi
        f.smooth = True
    return idx, vs


def _grid_normals(P):
    N = np.cross(np.gradient(P, axis=0), np.gradient(P, axis=1))
    return N / np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)


def _curl(P, N, axis, end, r=0.0012, ret=0.013):
    """Dobladillo enrollado en un borde de la rejilla: la lona sigue más allá del borde, da media vuelta de radio r hacia el
    lado -N (adentro) y regresa `ret` por debajo (orilla del dobladillo a la vista por dentro). Devuelve P ampliada."""
    Pm = np.moveaxis(P, axis, 0)
    Nm = np.moveaxis(N, axis, 0)
    if end < 0:
        Pb, Pp, Nb = Pm[-1], Pm[-2], Nm[-1]
    else:
        Pb, Pp, Nb = Pm[0], Pm[1], Nm[0]
    T = Pb - Pp
    T /= np.maximum(np.linalg.norm(T, axis=-1, keepdims=True), 1e-12)
    rows = []
    for th in (PI / 4, PI / 2, 3 * PI / 4, PI):
        rows.append(Pb + T * (r * math.sin(th)) - Nb * (r * (1 - math.cos(th))))
    rows.append(Pb - T * (ret * 0.45) - Nb * (2 * r))
    rows.append(Pb - T * ret - Nb * (2 * r))
    R = np.stack(rows, 0)
    out = np.concatenate([Pm, R], 0) if end < 0 else np.concatenate([R[::-1], Pm], 0)
    return np.moveaxis(out, 0, axis)


def _grow_mask(mask, axis, end, n):
    """Amplía la máscara de celdas al agregar n filas/columnas de dobladillo en un borde."""
    if mask is None:
        return None
    Mm = np.moveaxis(mask, axis, 0)
    edge = Mm[-1:] if end < 0 else Mm[:1]
    ext = np.repeat(edge, n, 0)
    out = np.concatenate([Mm, ext], 0) if end < 0 else np.concatenate([ext, Mm], 0)
    return np.moveaxis(out, 0, axis)


def _bilerp(xv, yv, F, X, Y):
    """Interpolación bilineal de F (nx, ny[, k]) en puntos (X, Y)."""
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    i = np.clip(np.searchsorted(xv, X) - 1, 0, len(xv) - 2)
    j = np.clip(np.searchsorted(yv, Y) - 1, 0, len(yv) - 2)
    tx = np.clip((X - xv[i]) / (xv[i + 1] - xv[i]), 0, 1)
    ty = np.clip((Y - yv[j]) / (yv[j + 1] - yv[j]), 0, 1)
    if F.ndim == 3:
        tx, ty = tx[..., None], ty[..., None]
    return F[i, j] * (1 - tx) * (1 - ty) + F[i + 1, j] * tx * (1 - ty) + F[i, j + 1] * (1 - tx) * ty + F[i + 1, j + 1] * tx * ty


def _packets(U, V, specs):
    """Paquetes de arrugas de tensión: crestas paralelas (onda coseno) que nacen en (u0, v0), se abren en abanico a lo largo
    de la dirección `ang` y se desvanecen. spec = (u0, v0, ang, largo, ancho, lam, amp, fan)."""
    D = np.zeros(np.broadcast(U, V).shape)
    for (u0, v0, ang, ln, w, lam, A, fan) in specs:
        du, dv = U - u0, V - v0
        ca, sa = math.cos(ang), math.sin(ang)
        al = du * ca + dv * sa
        pe = -du * sa + dv * ca
        t = al / ln
        env = _ss(0.02, 0.3, t) * (1 - _ss(0.5, 1.0, t))
        grow = 0.8 + 0.4 * np.clip(t, 0, 1) * fan
        env = env * np.exp(-1.6 * (pe / (w * grow)) ** 2)
        D += A * env * np.cos(2 * PI * pe / (lam * grow))
    return D


def _ridges(U, V, specs):
    """Crestas sueltas (gaussianas) que se adelgazan hacia las puntas. spec = (cu, cv, ángulo, largo, ancho, alto)."""
    D = np.zeros(np.broadcast(U, V).shape)
    for (cu, cv, ang, length, w, A) in specs:
        du, dv = U - cu, V - cv
        ca, sa = math.cos(ang), math.sin(ang)
        al, pe = du * ca + dv * sa, -du * sa + dv * ca
        env = np.clip(1 - (2 * al / length) ** 2, 0, 1)
        we = w * (0.45 + 0.55 * np.sqrt(env))
        D += A * np.exp(-(pe / np.maximum(we, 1e-4)) ** 2) * env ** 1.5
    return D


def _rr_loop(cu, cv, au, av, rc, d, nc=4, step=0.012, su=1.0, sv=1.0):
    """Contorno de rectángulo redondeado en el espacio de parámetros (u, v) a `d` hacia dentro (antihorario), con número de
    puntos fijo (misma topología para todos los d): centro (cu, cv), medio ancho au, medio alto av (en metros reales);
    su, sv = metros por unidad de parámetro (para pasar a parámetros)."""
    a, b = au - d, av - d
    r = max(rc - d, 0.0004)
    r = min(r, a - 1e-5, b - 1e-5)
    mu = max(1, int(math.ceil(2 * (au - rc) / step)))
    mv = max(1, int(math.ceil(2 * (av - rc) / step)))
    pts = []
    corners = ((a - r, b - r, 0.0), (-a + r, b - r, PI / 2), (-a + r, -b + r, PI), (a - r, -b + r, 1.5 * PI))
    for k, (cx, cy, a0) in enumerate(corners):
        for i in range(nc + 1):
            ang = a0 + PI / 2 * i / nc
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        # tramo recto hasta la siguiente esquina
        nx_, ny_ = corners[(k + 1) % 4][:2]
        a1 = corners[(k + 1) % 4][2]
        p0 = (cx + r * math.cos(a0 + PI / 2), cy + r * math.sin(a0 + PI / 2))
        p1 = (nx_ + r * math.cos(a1), ny_ + r * math.sin(a1))
        m = mu if k % 2 == 0 else mv
        for i in range(1, m):
            t = i / m
            pts.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
    return [(cu + x / su, cv + y / sv) for (x, y) in pts]


# ======================================================================================================== geometría
def _geo(L, W):
    """Eje del armazón (analítico por longitud de arco s), posiciones de arcos y largueros."""
    g = {}
    hw = W / 2 - 0.05
    o = O
    rc = RR + o
    za = RIDGE
    al = 0.36
    for _ in range(10):
        al = math.atan2(za - EAVE, hw + o)
        za = RIDGE + rc * (1 / math.cos(al) - 1)
    zk = EAVE + math.tan(al) * o - o / math.cos(al)          # rodilla aguda del eje
    zr = za - o / math.cos(al)                                # cumbrera aguda del eje
    thk = PI / 2 - al
    tk = RK * math.tan(thk / 2)
    tr = RR * math.tan(al)
    Lr = math.hypot(hw, zr - zk)
    s_ks = zk - tk
    s_ke = s_ks + RK * thk
    s_rs = s_ke + (Lr - tk - tr)
    s_r = s_rs + RR * al
    ck = (-hw + RK, s_ks)
    pke = (ck[0] - RK * math.sin(al), ck[1] + RK * math.cos(al))
    prs = (pke[0] + (s_rs - s_ke) * math.cos(al), pke[1] + (s_rs - s_ke) * math.sin(al))
    cr = (prs[0] + RR * math.sin(al), prs[1] - RR * math.cos(al))
    g.update(hw=hw, o=o, al=al, zk=zk, zr=zr, thk=thk, s_ks=s_ks, s_ke=s_ke, s_rs=s_rs, s_r=s_r, s_tot=2 * s_r, ck=ck, pke=pke,
             prs=prs, cr=cr)
    g["s_e"] = (s_ks + s_ke) / 2                              # larguero de alero: a media rodilla
    g["s_e1"] = 2 * s_r - g["s_e"]
    xa = L / 2 - 0.045
    g["xa"] = xa
    g["xs"] = [float(v) for v in np.linspace(-xa, xa, 5)]
    g["Yw"] = hw + 0.033                                      # plano de las paredes laterales (arriba)
    g["Xe"] = xa + 0.032                                      # plano de los testeros (arriba)
    g["FL"] = 0.05                                            # abocinado de las paredes al pie
    g["s_vb"] = s_ks - 0.19                                   # dobladillo del faldón
    g["z_wt"] = s_ks - 0.075                                  # remate superior de la pared lateral
    return g


def _pf(g, s):
    """Eje del arco en (y, z) y su tangente para la longitud de arco s (arreglos). s < s_ks: pata (incluye s < 0)."""
    s = np.asarray(s, float)
    shp = s.shape
    s = s.ravel()
    m = s > g["s_r"]
    sl = np.where(m, 2 * g["s_r"] - s, s)
    hw, al = g["hw"], g["al"]
    y = np.empty_like(sl)
    z = np.empty_like(sl)
    ty = np.empty_like(sl)
    tz = np.empty_like(sl)
    a = sl < g["s_ks"]
    y[a], z[a], ty[a], tz[a] = -hw, sl[a], 0.0, 1.0
    b = (sl >= g["s_ks"]) & (sl < g["s_ke"])
    ph = PI - (sl[b] - g["s_ks"]) / RK
    y[b] = g["ck"][0] + RK * np.cos(ph)
    z[b] = g["ck"][1] + RK * np.sin(ph)
    ty[b], tz[b] = np.sin(ph), -np.cos(ph)
    c = (sl >= g["s_ke"]) & (sl < g["s_rs"])
    y[c] = g["pke"][0] + (sl[c] - g["s_ke"]) * math.cos(al)
    z[c] = g["pke"][1] + (sl[c] - g["s_ke"]) * math.sin(al)
    ty[c], tz[c] = math.cos(al), math.sin(al)
    d = sl >= g["s_rs"]
    ps = PI / 2 + al - (sl[d] - g["s_rs"]) / RR
    y[d] = g["cr"][0] + RR * np.cos(ps)
    z[d] = g["cr"][1] + RR * np.sin(ps)
    ty[d], tz[d] = np.sin(ps), -np.cos(ps)
    y = np.where(m, -y, y)
    tz = np.where(m, -tz, tz)
    ny, nz = -tz, ty                                          # normal hacia afuera
    return y.reshape(shp), z.reshape(shp), ny.reshape(shp), nz.reshape(shp)


def _pf_pt(g, s, off=0.0, x=0.0):
    y, z, ny, nz = _pf(g, np.array([s]))
    return Vector((x, _f(y[0] + ny[0] * off), _f(z[0] + nz[0] * off)))


def _pf_tn(g, s):
    y, z, ny, nz = _pf(g, np.array([s]))
    return Vector((0.0, _f(nz[0]), _f(-ny[0]))), Vector((0.0, _f(ny[0]), _f(nz[0])))


# ======================================================================================================== armazón
def _lip(mb, M, r_out, r_in, mat="aluminium", seg=SEG_F):
    """Boca de casquillo: labio redondeado de la pieza fundida (z local hacia afuera del casquillo, origen en la boca)."""
    _lathe(mb, [(r_in, 0.0003), (r_out - 0.0009, 0.0016), (r_out + 0.0011, 0.0001), (r_out + 0.0011, -0.006),
                (r_out - 0.0004, -0.0098)], M, mat, seg=seg, caps=False)


def _hex_bolt(mb, p, axis, length, d=0.008, mat="steel"):
    """Perno de cabeza hexagonal con arandela, tuerca y punta de rosca: cabeza en p, vástago hacia `axis`."""
    ax = Vector(axis).normalized()
    M0 = _frame_z(p, -ax)
    s = d * 1.6
    _lathe(mb, [(d * 0.5, -0.0003), (s * 0.95, -0.0003), (s * 0.95, 0.0011), (d * 0.5, 0.0011)], M0, mat, seg=12, caps=False)
    _lathe(mb, [(0.0, 0.0011), (s * 0.8, 0.0011), (s * 0.83, 0.0022), (s * 0.83, d * 0.62), (s * 0.7, d * 0.7), (0.0, d * 0.7)],
           M0 @ _Rz(30), mat, seg=6)
    p1 = Vector(p) + ax * length
    _cyl(mb, tuple(Vector(p) - ax * 0.0002), tuple(p1 + ax * 0.004), d * 0.5, mat, seg=12, caps=False)
    M1 = _frame_z(p1, ax)
    _lathe(mb, [(d * 0.5, -0.0003), (s * 0.95, -0.0003), (s * 0.95, 0.0011), (d * 0.5, 0.0011)], M1, mat, seg=12, caps=False)
    _lathe(mb, [(d * 0.5, 0.0011), (s * 0.8, 0.0011), (s * 0.83, 0.002), (s * 0.83, d * 0.75), (s * 0.68, d * 0.82),
                (d * 0.5, d * 0.82)], M1 @ _Rz(30), mat, seg=6, caps=False)
    _lathe(mb, [(d * 0.5, d * 0.82), (d * 0.47, d * 0.82 + 0.003), (d * 0.3, d * 0.82 + 0.0042), (0.0, d * 0.82 + 0.0044)], M1, mat,
           seg=12)


def _detent_pin(mb, p, axis, length, r_ring=0.011, sway=0.0):
    """Pasador de seguridad: vástago de 6 mm con cabeza y argolla de alambre colgando."""
    ax = Vector(axis).normalized()
    M0 = _frame_z(p, -ax)
    _lathe(mb, [(0.003, -0.0002), (0.0064, 0.0004), (0.0062, 0.0036), (0.0034, 0.0052), (0.0, 0.0053)], M0,
           "steel", seg=12)
    p1 = Vector(p) + ax * length
    _cyl(mb, tuple(Vector(p) - ax * 0.0002), tuple(p1), 0.003, "steel", seg=12, caps=False)
    _lathe(mb, [(0.003, 0.0), (0.0026, 0.002), (0.0012, 0.0032), (0.0, 0.0034)], _frame_z(p1, ax), "steel", seg=12)
    # argolla que cuelga del ojo de la cabeza
    eye = Vector(p) - ax * 0.0058
    down = Vector((0, 0, -1)) - ax * ax.z
    if down.length < 1e-3:
        down = Vector((0, 1, 0))
    down.normalize()
    side = ax.cross(down).normalized()
    c = eye + down * (r_ring + 0.001) + side * sway
    nrm = side * math.cos(0.5) + ax * math.sin(0.5)
    u = down
    v = nrm.cross(u).normalized()
    ring = [c + (u * math.cos(2 * PI * k / 16) + v * math.sin(2 * PI * k / 16)) * r_ring for k in range(16)]
    with mb.soft():
        loop_tube(mb, ring, 0.0013, seg=8, mat="steel", normal=tuple(nrm))


def _rivet(mb, p, n, r=0.0032):
    _lathe(mb, [(r, -0.0004), (r * 0.85, 0.0011), (r * 0.4, 0.0017), (0.0, 0.0018)], _frame_z(p, n), "aluminium", seg=10, caps=False)


def _elbow(mb, g, x, s0, s1, boss_s, boss_axis_off, sockets, seed=0):
    """Codo fundido de aluminio: cuerpo curvo (eje del armazón de s0 a s1) con casquillos y labios en ambos extremos,
    jefe con casquillo(s) de larguero a lo largo de X en `boss_s`, perno pasante y pasadores de seguridad en los brazos."""
    ss = [s0] + list(np.linspace(s0 + ARM - 0.004, s1 - ARM + 0.004, 14)) + [s1]
    pts = [_pf_pt(g, s, 0.0, x) for s in ss]
    _tube(mb, pts, R_F, mat="aluminium", seg=SEG_F, caps=True)
    for s, sg in ((s0, -1), (s1, 1)):
        t, n = _pf_tn(g, s)
        _lip(mb, _frame_z(_pf_pt(g, s, 0.0, x), t * sg), R_F, R_A + 0.0004)
    # nervio de colada en el lado exterior de la curva (costilla de 6 mm)
    rib = [_pf_pt(g, s, -(R_F - 0.0015), x) for s in np.linspace(s0 + ARM * 0.55, s1 - ARM * 0.55, 12)]
    sweep_frame(mb, rr_profile(0.006, 0.006, 0.0022, n=2), [tuple(p) for p in rib], "aluminium",
                up=(1, 0, 0))
    # jefe del larguero
    pb = _pf_pt(g, boss_s, boss_axis_off, x)
    t, n = _pf_tn(g, boss_s)
    for sx in sockets:
        a = Vector((sx, 0, 0))
        _cyl(mb, tuple(pb - a * 0.004), tuple(pb + a * 0.062), R_S, "aluminium", seg=SEG_F, caps=False)
        _lip(mb, _frame_z(pb + a * 0.0655, a), R_S + 0.0003, R_P + 0.0004)
        # perno pasante del casquillo (a lo largo de la tangente del arco)
        pc = pb + a * 0.042
        _hex_bolt(mb, pc - t * (R_S + 0.0003), t, 2 * R_S + 0.0006, d=0.008)
    if len(sockets) == 1:                                     # tapa ciega del lado exterior (arco extremo)
        a = Vector((-sockets[0], 0, 0))
        _lathe(mb, [(0.0, 0.0), (R_S - 0.002, 0.0), (R_S + 0.0004, -0.0025), (R_S + 0.0004, -0.012)],
               _frame_z(pb + a * 0.012, a), "aluminium", seg=SEG_F)
    # pasadores de seguridad en cada brazo (eje a lo largo de X)
    r = rng(seed)
    for s in ((s0 + ARM * 0.5,) if boss_s < g["s_r"] - 0.01 else (s1 - ARM * 0.5,) if boss_s > g["s_r"] + 0.01 else (s0 + ARM * 0.5,)):
        p = _pf_pt(g, s, 0.0, x)
        _detent_pin(mb, p - Vector((R_F + 0.0002, 0, 0)), (1, 0, 0), 2 * R_F + 0.006, sway=_jit(r, 0.004))


def _stake_pin(mb, p, lean=(0, 0, 0), h=0.11, r=0.0079, seed=0, mat="gunmetal"):
    """Estaca forjada de 18" × 5/8" hincada: vástago con cabeza de hongo forjada (irregular). Devuelve (punto bajo la cabeza,
    eje)."""
    rr_ = rng(seed)
    ax = (Vector((0, 0, 1)) + Vector(lean)).normalized()
    b = Vector(p)
    top = b + ax * h
    _cyl(mb, tuple(b - ax * 0.05), tuple(top - ax * 0.008), r, mat, seg=SEG_M, caps=True)
    ph = [_f(v) for v in rr_.uniform(0, 2 * PI, 3)]

    def rmod(a):
        return 1.0 + 0.04 * math.sin(3 * a + ph[0]) + 0.025 * math.sin(5 * a + ph[1])
    revolve(mb, [(r, -0.0085), (r * 1.25, -0.0055), (0.0175, -0.0028), (0.0188, -0.0008), (0.0182, 0.0012), (0.0150, 0.0035),
                 (0.0090, 0.0052), (0.0, 0.0058)], mat, seg=SEG_M, M=_frame_z(top, ax, (1, 0, 0)) @ _Rz(_f(rr_.uniform(0, 360))),
            rmod=rmod)
    return top - ax * 0.012, ax


def _baseplate(mb, g, x, y, sockets, seed=0):
    """Pie del arco: placa galvanizada de 6 mm (140 × 140, esquinas R20, canto matado) con casquillo vertical soldado (cordón),
    casquillos de larguero de base hacia el interior, perno de la pata y dos estacas forjadas por las perforaciones."""
    r = rng(seed)
    slab(mb, _T(x, y, 0.0), 0.14, 0.14, 0.006, rc=0.02, re=0.0018, mat="galvanized", nc=4, ne=2)
    rv = R_A + 0.0045
    _lathe(mb, [(rv, 0.0055), (rv, 0.112), (rv - 0.0012, 0.1155), (R_A + 0.0006, 0.1158)], _T(x, y, 0.0),
           "galvanized", seg=SEG_F, caps=False)
    weld(mb, _T(x, y, 0.0065), rv, w=0.0035, seg=SEG_F, mat="galvanized")
    sy = 1 if y > 0 else -1
    _hex_bolt(mb, Vector((x, y - sy * (rv + 0.0002), 0.088)), (0, sy, 0), 2 * rv + 0.0004, d=0.008, mat="steel")
    for sx in sockets:
        a = Vector((sx, 0, 0))
        pc = Vector((x, y, 0.062))
        _cyl(mb, tuple(pc), tuple(pc + a * 0.075), R_S, "galvanized", seg=SEG_F, caps=False)
        _lip(mb, _frame_z(pc + a * 0.0785, a), R_S + 0.0003, R_P + 0.0004, mat="galvanized")
        weld(mb, _frame_z(pc + a * (rv - 0.0008), a), R_S, w=0.003, seg=SEG_F, mat="galvanized")
        _rivet(mb, pc + a * 0.05 + Vector((0, 0, R_S - 0.0002)), (0, 0, 1), r=0.0045)
    # estacas por las perforaciones de las esquinas exteriores
    for (dx, dy) in ((0.045, 0.045), (-0.045, 0.045)):
        px, py = x + dx, y + sy * dy
        _stake_pin(mb, (px, py, 0.006), lean=(_jit(r, 0.03), _jit(r, 0.03), 0), h=0.026, r=0.0079, seed=int(r.integers(1e6)))


def _purlin(mb, p0, p1, r=R_P, mat="aluminium"):
    """Larguero: tubo con collarín remachado en cada punta (entra en el casquillo del codo)."""
    p0, p1 = Vector(p0), Vector(p1)
    a = (p1 - p0).normalized()
    _cyl(mb, tuple(p0), tuple(p1), r, mat, seg=SEG, caps=False)
    up = Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((0, 1, 0))
    side = a.cross(up).normalized()
    upn = side.cross(a).normalized()
    for (p, sg) in ((p0, 1), (p1, -1)):
        c0 = p + a * sg * 0.0115
        M = _frame_z(c0, a * sg)
        _lathe(mb, [(r - 0.0004, -0.0003), (r + 0.0014, 0.0012), (r + 0.0014, 0.024), (r - 0.0004, 0.0265)], M, mat, seg=SEG,
               caps=False)
        for k in (-1, 1):
            q = c0 + a * sg * 0.013
            nn = (upn * math.cos(0.9 * k) + side * math.sin(0.9 * k)).normalized()
            _rivet(mb, q + nn * (r + 0.0012), nn)


def _frame(mb, g, seed):
    xs, hw = g["xs"], g["hw"]
    s_ks, s_ke, s_rs, s_r = g["s_ks"], g["s_ke"], g["s_rs"], g["s_r"]
    s_e, s_e1 = g["s_e"], g["s_e1"]
    for k, x in enumerate(xs):
        socks = (-1, 1) if 0 < k < 4 else ((1,) if k == 0 else (-1,))
        # patas y cabios (tubos rectos; sus puntas quedan dentro de los casquillos)
        for sg in (-1, 1):
            y = sg * hw
            _cyl(mb, (x, y, 0.03), (x, y, s_ks - ARM + 0.03), R_A, "aluminium", seg=SEG, caps=False)
            a = _pf_pt(g, s_ke + ARM - 0.03 if sg < 0 else 2 * s_r - s_ke - ARM + 0.03, 0.0, x)
            b = _pf_pt(g, s_rs - ARM + 0.03 if sg < 0 else 2 * s_r - s_rs + ARM - 0.03, 0.0, x)
            _cyl(mb, tuple(a), tuple(b), R_A, "aluminium", seg=SEG, caps=False)
        # codos de alero y de cumbrera
        _elbow(mb, g, x, s_ks - ARM, s_ke + ARM, s_e, P_OFF, socks, seed + 3 * k)
        _elbow(mb, g, x, 2 * s_r - s_ke - ARM, 2 * s_r - s_ks + ARM, s_e1, P_OFF, socks, seed + 3 * k + 1)
        _elbow(mb, g, x, s_rs - ARM, 2 * s_r - s_rs + ARM, s_r, P_OFF, socks, seed + 3 * k + 2)
        for sg in (-1, 1):
            _baseplate(mb, g, x, sg * hw, socks, seed=seed + 50 + 2 * k + (sg > 0))
    # largueros
    for s in (s_e, s_r, s_e1):
        p = _pf_pt(g, s, P_OFF, 0.0)
        for k in range(4):
            _purlin(mb, (xs[k] + 0.0575, p.y, p.z), (xs[k + 1] - 0.0575, p.y, p.z))
    for sg in (-1, 1):
        for k in range(4):
            _purlin(mb, (xs[k] + 0.071, sg * hw, 0.062), (xs[k + 1] - 0.071, sg * hw, 0.062), mat="aluminium")



# ======================================================================================================== capas de lona
def _strip(mb, F, X, s_c, prof, mat="canvas", caps=True):
    """Capa cosida encima de una superficie paramétrica F(X, S) -> (P, N): tira a lo largo de X (muestras X) con sección
    prof = [(dv, h)] (dv en parámetro S alrededor de s_c, h sobre la superficie; los extremos se empotran)."""
    dv = np.array([p[0] for p in prof])
    h = np.array([p[1] for p in prof])
    XX = np.asarray(X, float)[:, None] + 0 * dv[None, :]
    SS = s_c + dv[None, :] + 0 * XX
    P, N = F(XX, SS)
    Q = P + N * h[None, :, None]
    _grid(mb, Q, mat)
    if caps:
        mi = mb.mi(mat)
        for row, rev in ((Q[0], True), (Q[-1], False)):
            vs = [mb.bm.verts.new(tuple(p)) for p in row.tolist()]
            f = mb.bm.faces.new(vs[::-1] if rev else vs)
            f.material_index = mi
            f.smooth = True
    return Q


def _patch(mb, F, cu, cv, au, av, rc, su=1.0, sv=1.0, t=0.0014, groove=0.0065, mat="canvas", step=0.012, nc=4):
    """Parche de refuerzo cosido (rectángulo redondeado en el espacio de parámetros) que sigue la superficie F: canto de
    doblez redondeado con su espesor, pespunte perimetral hundido y anillos concéntricos hasta el centro (sin n-gonos
    grandes). au, av, rc en metros reales; su, sv = metros por unidad de parámetro."""
    lv = [(0.0, -E_EMB), (0.0, t * 0.45), (0.0005, t * 0.8), (0.0014, t), (groove - 0.0011, t), (groove, t * 0.62),
          (groove + 0.0011, t)]
    d = groove + 0.008
    lim = min(au, av) - 0.004
    while d < lim:
        lv.append((d, t))
        d = d + max(0.008, d * 0.6)
    loops = []
    for (dd, hh) in lv:
        pts = _rr_loop(cu, cv, au, av, rc, dd, nc=nc, step=step, su=su, sv=sv)
        U = np.array([p[0] for p in pts])
        V = np.array([p[1] for p in pts])
        P, N = F(U, V)
        loops.append(P + N * hh)
    vs = [[mb.bm.verts.new(tuple(p)) for p in L_.tolist()] for L_ in loops]
    mi = mb.mi(mat)
    n = len(vs[0])
    for i in range(len(vs) - 1):
        A, B = vs[i], vs[i + 1]
        for k in range(n):
            f = mb.bm.faces.new((A[k], A[(k + 1) % n], B[(k + 1) % n], B[k]))
            f.material_index = mi
            f.smooth = True
    c = loops[-1].mean(0)
    cvx = mb.bm.verts.new(tuple(c))
    A = vs[-1]
    for k in range(n):
        f = mb.bm.faces.new((A[k], A[(k + 1) % n], cvx))
        f.material_index = mi
        f.smooth = True


def _grommet(mb, p, n, ro=0.0105, ri=0.0055, mat="brass", back=True):
    """Ojillo de latón con su espesor: ceja abombada que sobresale 1,7 mm, boca oscura y arandela por el reverso."""
    M = _frame_z(p, n)
    _lathe(mb, [(ri, 0.0005), (ro, -0.0003), (ro - 0.0013, 0.0014), (ri + 0.0012, 0.0018)], M, mat, seg=12, closed=True)
    _lathe(mb, [(0.0, 0.00075), (ri + 0.0004, 0.00075)], M, "cable", seg=12, caps=False)
    if back:
        Mb = _frame_z(Vector(p), -Vector(n))
        _lathe(mb, [(ri + 0.0003, 0.0004), (ro - 0.0006, -0.0003), (ri + 0.0015, 0.0012)], Mb, mat, seg=12, closed=True)


# ======================================================================================================== cubierta
class _Roof:
    """Cubierta del techo: superficie paramétrica (x, s) con s = longitud de arco del eje del armazón. La lona queda a
    O + D(x, s) por la normal del eje; el faldón cuelga abocinado bajo la rodilla y las campanas doblan sobre los testeros."""

    def __init__(self, g, L, seed):
        self.g, self.L, self.seed = g, L, seed
        r = rng(seed + 11)
        xs = g["xs"]
        self.xs = xs
        self.x_hb = g["xa"] + 0.006
        self.r_h = 0.039
        self.h_f = 0.085
        self.e_r = PI / 2 * self.r_h
        self.e_max = self.e_r + self.h_f
        s_r = g["s_r"]
        span = g["s_rs"] - g["s_ke"]
        self.span = span
        sc = g["s_ke"] + span * 0.5
        self.seams = [sc, 2 * s_r - sc]
        self.rb = 0.075                                       # medio ancho de la banda de cumbrera (en s)
        fr = (0.2, 0.78)
        ts = [g["s_ke"] + span * f for f in fr]
        self.tie_s = sorted(ts + [2 * s_r - v for v in ts])
        self.x_edge = [xs[k] - 0.095 for k in (1, 2, 3)]
        # paños: caída (+ viento de +Y: el fondo se hunde más, el frente se alivia) y sesgo del punto más bajo
        self.sag = [[_f(r.uniform(0.030, 0.042)) * 0.8, _f(r.uniform(0.034, 0.046)) * 1.3] for _ in range(4)]
        self.skew = [[(_jit(r, 0.35), _jit(r, 0.25)) for _ in range(2)] for _ in range(4)]
        pk = []
        for k in range(4):
            x0, x1 = xs[k], xs[k + 1]
            for side in (0, 1):
                s0, s1 = (g["s_e"], s_r) if side == 0 else (s_r, g["s_e1"])
                se = s0 if side == 0 else s1                   # línea del alero de este paño
                xm, sm = (x0 + x1) / 2, (s0 + s1) / 2
                for (xc, scn) in ((x0, s0), (x1, s0), (x0, s1), (x1, s1)):
                    base = math.atan2(sm - scn, xm - xc)
                    eave = abs(scn - se) < 1e-6
                    if r.uniform() < (0.95 if eave else 0.6):
                        a = base + _jit(r, 0.3)
                        off = _f(r.uniform(0.12, 0.3))
                        pk.append((xc + math.cos(a) * off, scn + math.sin(a) * off, a, _f(r.uniform(0.9, 1.7)),
                                   _f(r.uniform(0.2, 0.3)), _f(r.uniform(0.16, 0.24)),
                                   _f(r.uniform(0.004, 0.0075)) * (1.15 if eave else 0.85), _f(r.uniform(0.4, 0.9))))
                if r.uniform() < 0.8:                          # pliegue de cizalla diagonal, largo y suave
                    sg = 1 if r.uniform() < 0.5 else -1
                    xc = x0 if sg > 0 else x1
                    a = math.atan2(s1 - s0, (x1 - x0) * sg) + _jit(r, 0.12)
                    pk.append((xc + math.cos(a) * 0.25, s0 + math.sin(a) * 0.25, a, _f(r.uniform(1.9, 2.6)), 0.17,
                               _f(r.uniform(0.45, 0.6)), _f(r.uniform(0.009, 0.014)), 0.3))
        self.pk = pk
        self.pucker = [(_f(r.uniform(0.08, 0.13)), _f(r.uniform(0, 6.3)), _f(r.uniform(0.05, 0.08)), _f(r.uniform(0, 6.3)))
                       for _ in self.seams]
        self.val_waves = [(_f(r.uniform(0.28, 0.7)), _f(r.uniform(0, 6.3)), _f(r.uniform(0.0015, 0.004))) for _ in range(5)]

    # ------------------------------------------------------------------ campo de desplazamiento
    def val_off(self, S):
        g = self.g
        Sl = np.minimum(S, g["s_tot"] - S)
        t = np.clip((g["s_ks"] - Sl) / (g["s_ks"] - g["s_vb"]), 0.0, 1.0)
        return 0.012 * _ss(0.0, 0.35, t) + 0.022 * t ** 1.4

    def D(self, X, S):
        g, xs = self.g, self.xs
        X = np.clip(np.asarray(X, float), -self.x_hb, self.x_hb)
        S = np.asarray(S, float)
        X, S = np.broadcast_arrays(X, S)
        s_ks, s_ke, s_rs, s_r, s_e, s_e1 = g["s_ks"], g["s_ke"], g["s_rs"], g["s_r"], g["s_e"], g["s_e1"]
        st = g["s_tot"]
        Sl = np.minimum(S, st - S)
        dxa = np.min(np.abs(X[..., None] - np.array(xs)), axis=-1)
        # apoyos: lona sobre el tubo (-6,5 mm), sobre los codos (0) y sobre los largueros (-3,5 mm)
        K = np.maximum(_ss(s_ks - ARM - 0.03, s_ks - ARM - 0.001, Sl) * (1 - _ss(s_ke + ARM + 0.001, s_ke + ARM + 0.03, Sl)),
                       _ss(s_rs - ARM - 0.03, s_rs - ARM - 0.001, Sl))
        A = -0.0065 * (1 - K)
        wa = 1 - _ss(0.11, 0.2, dxa)
        wp = sum(np.exp(-((S - sl) / 0.03) ** 2) for sl in (s_e, s_r, s_e1))
        D = -0.0065 + (A + 0.0065) * wa + 0.003 * np.minimum(wp, 1.0) * (1 - wa)
        inP = (S > s_e) & (S < s_e1)
        ds = np.minimum(np.minimum(np.abs(S - s_e), np.abs(S - s_r)), np.abs(S - s_e1))
        # caída de cada paño (seno en ambos sentidos, con sesgo), cresta marcada sobre arcos y largueros
        for k in range(4):
            x0, x1 = xs[k], xs[k + 1]
            u = np.clip((X - x0) / (x1 - x0), 0, 1)
            for side in (0, 1):
                s0, s1 = (s_e, s_r) if side == 0 else (s_r, s_e1)
                v = np.clip((S - s0) / (s1 - s0), 0, 1)
                ku, kv = self.skew[k][side]
                uu = u + ku * u * (1 - u)
                vv = v + kv * v * (1 - v)
                m = (X > x0) & (X < x1) & (S > s0) & (S < s1)
                D -= np.where(m, self.sag[k][side] * np.sin(PI * uu) ** 0.9 * np.sin(PI * vv) ** 0.85, 0.0)
        D -= 0.004 * (1 - np.exp(-dxa / 0.05)) * (1 - np.exp(-ds / 0.05)) * inP
        M = _ss(0.035, 0.11, dxa) * _ss(0.02, 0.09, ds) * inP
        D += _packets(X, S, self.pk) * M
        D += (0.0028 * _noise2(X, S, 0.85, self.seed) + 0.0011 * _noise2(X, S, 2.9, self.seed + 3)) * M
        # costuras: relieve de la costura doble (se ve por dentro) y arrugas finas de compresión a sus lados
        for sc, (lam, ph, lam2, ph2) in zip(self.seams, self.pucker):
            D += 0.0011 * (1 - _ss(0.0062, 0.0082, np.abs(S - sc)))
            amp = 0.0011 * (0.55 + 0.45 * np.sin(X * 1.7 + ph2))
            D += amp * (np.sin(2 * PI * X / lam + ph) + 0.5 * np.sin(2 * PI * X / lam2 + ph2)) * \
                np.exp(-((S - sc) / 0.028) ** 2) * _ss(0.05, 0.13, dxa)
        # traslape de la cubierta de cada sección sobre el arco: capa de arriba con orilla viva, se levanta entre amarres
        ties = [g["s_vb"]] + self.tie_s + [st - g["s_vb"]]
        lift = np.zeros_like(S)
        for a, b in zip(ties[:-1], ties[1:]):
            lift += np.where((S >= a) & (S < b), np.sin(PI * np.clip((S - a) / (b - a), 0, 1)) ** 1.2, 0.0)
        for xk, xe in zip(xs[1:4], self.x_edge):
            t_ov = 0.0012 + 0.0024 * lift
            D += t_ov * _ss(xe - 0.0004, xe + 0.0004, X) * (1 - _ss(xk + 0.03, xk + 0.085, X))
            D -= 0.00045 * np.exp(-((X - (xe + 0.014)) / 0.0011) ** 2)
        # faldón: pliegues verticales que crecen hacia el dobladillo; pespunte del dobladillo
        tv = np.clip((s_ks - Sl) / (s_ks - g["s_vb"]), 0, 1)
        wv = sum(a * np.sin(2 * PI * X / lam + ph) for (lam, ph, a) in self.val_waves)
        endf = 1 - _ss(self.x_hb - 0.25, self.x_hb - 0.02, np.abs(X))
        D += wv * tv ** 1.3 * endf
        D -= 0.0004 * np.exp(-((Sl - (g["s_vb"] + 0.0135)) / 0.0011) ** 2)
        return D

    def P(self, X, S, D):
        g = self.g
        X, S, D = np.broadcast_arrays(np.asarray(X, float), np.asarray(S, float), np.asarray(D, float))
        y, z, ny, nz = _pf(g, S)
        off = O + D + self.val_off(S)
        ax = np.abs(X)
        sg = np.sign(X)
        e = np.maximum(ax - self.x_hb, 0.0)
        ph = np.minimum(e / self.r_h, PI / 2)
        ex = self.r_h * np.sin(ph)
        en = -self.r_h * (1 - np.cos(ph)) - np.maximum(e - self.e_r, 0.0)
        hood = ax > self.x_hb
        xx = np.where(hood, sg * (self.x_hb + ex), X)
        off = off + np.where(hood, en, 0.0)
        return np.stack([xx, y + ny * off, z + nz * off], -1)

    def F(self, X, S, eps=0.0015):
        """Superficie construida (D interpolado de la malla) y normal hacia afuera."""
        def ev(x, s):
            return self.P(x, s, _bilerp(self.xv, self.sv, self.Dg, x, s))
        X = np.asarray(X, float)
        S = np.asarray(S, float)
        P = ev(X, S)
        dX = ev(X + eps, S) - ev(X - eps, S)
        dS = ev(X, S + eps) - ev(X, S - eps)
        N = np.cross(dX, dS)
        N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)
        return P, N

    # ------------------------------------------------------------------ malla
    def build(self, mb):
        g, xs = self.g, self.xs
        xb = []
        for k in range(4):
            n = 58
            xb += list(0.42 * _cosspace(xs[k], xs[k + 1], n) + 0.58 * np.linspace(xs[k], xs[k + 1], n + 1))
        forced = list(xs) + [-self.x_hb, self.x_hb]
        for xk, xe in zip(xs[1:4], self.x_edge):
            forced += [xe - 0.0004, xe + 0.0004, xe + 0.004, xe + 0.0128, xe + 0.014, xe + 0.0152, xk + 0.03, xk + 0.085]
        xm = _merge([v for v in xb if abs(v) < self.x_hb - 0.003], forced, 0.006)
        hood = [self.x_hb + self.e_r * f for f in (0.15, 0.35, 0.55, 0.75, 1.0)] + \
            [self.x_hb + self.e_r + self.h_f * f for f in (0.3, 0.6, 0.84)] + \
            [self.x_hb + self.e_max - 0.0147, self.x_hb + self.e_max - 0.0135, self.x_hb + self.e_max - 0.0123, self.x_hb + self.e_max]
        xv = np.array(sorted([-h for h in hood] + list(xm) + hood))
        s_ks, s_ke, s_rs, s_r = g["s_ks"], g["s_ke"], g["s_rs"], g["s_r"]
        svb = g["s_vb"]
        half = [svb, svb + 0.0055, svb + 0.0123, svb + 0.0135, svb + 0.0147] + list(np.linspace(svb + 0.032, s_ks, 8)[:-1])
        half += list(np.linspace(s_ks, s_ke, 12)[:-1])
        n = 78
        half += list((0.6 * np.linspace(s_ke, s_rs, n + 1) + 0.4 * _cosspace(s_ke, s_rs, n))[:-1])
        half += list(np.linspace(s_rs, s_r, 5))
        sv = np.array(half + [2 * s_r - v for v in half[::-1][1:]])
        fs = []
        for sc in self.seams:
            fs += [sc - 0.0082, sc - 0.0062, sc - 0.003, sc, sc + 0.003, sc + 0.0062, sc + 0.0082]
        sv = _merge(list(sv), fs, 0.007)
        self.xv, self.sv = xv, sv
        Xg, Sg = np.meshgrid(xv, sv, indexing="ij")
        Dg = self.D(Xg, Sg)
        # festón y ondas del borde de las campanas
        e = np.maximum(np.abs(Xg) - self.x_hb, 0.0)
        Dg += 0.0025 * np.clip((e - self.e_r) / self.h_f, 0, 1) * np.sin(2 * PI * Sg / 0.37 + np.sign(Xg) * 1.3)
        self.Dg = Dg
        P = self.P(Xg, Sg, Dg)
        N = _grid_normals(P)
        P2 = _curl(P, N, 1, -1)
        P2 = _curl(P2, _grid_normals(P2), 1, 0)
        P3 = _curl(P2, _grid_normals(P2), 0, -1)
        P3 = _curl(P3, _grid_normals(P3), 0, 0)
        _grid(mb, P3, "canvas")
        self.P_grid = P

    # ------------------------------------------------------------------ capas cosidas, ojillos y amarres
    def details(self, mb):
        g, xs = self.g, self.xs
        x_end = self.x_hb + self.e_max - 0.017
        base = list(np.arange(-x_end, x_end, 0.03)) + [x_end]
        forced = [v for v in self.xv if any(xk - 0.11 < v < xk + 0.1 for xk in xs[1:4])]
        hood = [v for v in self.xv if self.x_hb - 0.01 < abs(v) < x_end]
        Xs = _merge(base, forced + hood, 0.004)
        Xs = Xs[np.abs(Xs) <= x_end + 1e-6]
        # costura doble (felled seam): 15 mm de ancho, dos pespuntes hundidos, cantos de doblez redondeados
        w = 0.0075
        prof = [(-w, -E_EMB), (-w, 0.0008), (-0.0066, 0.0015), (-0.0042, 0.0016), (-0.0035, 0.001), (-0.0028, 0.0016),
                (0.0028, 0.0016), (0.0035, 0.001), (0.0042, 0.0016), (0.0066, 0.0015), (w, 0.0008), (w, -E_EMB)]
        for sc in self.seams:
            _strip(mb, self.F, Xs, sc, prof)
        # banda de refuerzo de la cumbrera (doble lona con pespunte doble en cada orilla)
        b = self.rb
        e1 = [(-b, -E_EMB), (-b, 0.0007), (-b + 0.0012, 0.0014), (-b + 0.0058, 0.0014), (-b + 0.0066, 0.0009), (-b + 0.0074, 0.0014),
              (-b + 0.0148, 0.0014), (-b + 0.0156, 0.0009), (-b + 0.0164, 0.0014)]
        mid = [(v, 0.0014) for v in np.linspace(-b + 0.035, b - 0.035, 5)]
        prof = e1 + mid + [(-a, h) for (a, h) in e1[::-1]]
        _strip(mb, self.F, Xs, g["s_r"], prof)
        # dobladillo del traslape (orilla enrollada) y amarres al arco por pares de ojillos
        st = g["s_tot"]
        for k, (xk, xe) in enumerate(zip(xs[1:4], self.x_edge)):
            Ss = self.sv[(self.sv > g["s_vb"] + 0.004) & (self.sv < st - g["s_vb"] - 0.004)]
            P, N = self.F(np.full_like(Ss, xe + 0.0013), Ss)
            _tube(mb, P + N * 0.0011, 0.0012, mat="canvas", seg=8, soft=True)
            for st_ in self.tie_s:
                self._lash(mb, xk, st_, seed=k * 17 + int(st_ * 100))
        # ojillos del dobladillo del faldón (donde amarran las cintas del rollo y los vientos del faldón)
        self.val_gr = {}
        for side, sg in ((0, 1), (1, -1)):
            s_g = g["s_vb"] + 0.032 if side == 0 else st - g["s_vb"] - 0.032
            for x in self.tie_x():
                P, N = self.F(np.array([x]), np.array([s_g]))
                _grommet(mb, Vector(P[0]), Vector(N[0]))
                self.val_gr[(side, round(x, 4))] = (Vector(P[0]), Vector(N[0]))

    def tie_x(self):
        xs = self.xs
        return [xs[1], xs[2], xs[3]] + [(xs[k] + xs[k + 1]) / 2 for k in range(4)]

    def _lash(self, mb, xk, s_t, seed=0):
        """Amarre de la cubierta al arco: cordón que pasa por dos ojillos a ambos lados del arco, cruza por fuera sobre la
        cresta y por dentro rodea el tubo por abajo; nudo bajo el tubo."""
        r = rng(seed)
        xa, xb = xk - 0.058, xk + 0.058
        PA, NA = self.F(np.array([xa]), np.array([s_t]))
        PB, NB = self.F(np.array([xb]), np.array([s_t]))
        pa, na, pb, nb = Vector(PA[0]), Vector(NA[0]), Vector(PB[0]), Vector(NB[0])
        _grommet(mb, pa, na)
        _grommet(mb, pb, nb)
        rc = 0.0026
        # puente exterior sobre la cresta (siempre 3,5 mm sobre la lona)
        xx = np.linspace(xa, xb, 6)
        Pq, Nq = self.F(xx, np.full_like(xx, s_t))
        bridge = [Vector(p) + Vector(nn) * (rc + 0.0009 + 0.0012 * math.sin(PI * i / 5)) for i, (p, nn) in enumerate(zip(Pq, Nq))]
        # lazo interior bajo el tubo
        t, n = _pf_tn(g := self.g, s_t)
        c = _pf_pt(g, s_t, 0.0, xk)
        X = Vector((1, 0, 0))
        R = R_A + rc + 0.0003
        under = []
        for th in np.linspace(-PI + 0.35, -0.35, 7):
            under.append(c + (X * math.cos(th) + n * math.sin(th)) * R + t * (0.002 * math.sin(th * 3)))
        a_in = pa - na * (rc + 0.002)
        b_in = pb - nb * (rc + 0.002)
        path = [under[3]] + under[4:] + [b_in, pb + nb * 0.001] + bridge[::-1] + [pa + na * 0.001, a_in] + under[:4]
        _tube(mb, [tuple(p) for p in path], rc, mat="fabric", seg=12, rad=0.004, nseg=2, soft=True)
        # nudo (dos vueltas apretadas) bajo el tubo
        kc = c - n * R
        _lathe(mb, [(0.0, -0.007), (0.0034, -0.0058), (0.0046, -0.002), (0.0042, 0.0024), (0.0032, 0.0058), (0.0, 0.0068)],
               _frame_z(kc, X, (0, 0, 1)) @ _Rz(_f(r.uniform(0, 360))), "fabric", seg=12, soft=True)
        tail = [kc + t * 0.003, kc - n * 0.03 + t * (0.006 + _jit(r, 0.004)) + X * _jit(r, 0.006),
                kc - n * 0.05 + t * _jit(r, 0.01)]
        _cord(mb, [tuple(p) for p in tail], r=rc * 0.95, rad=0.01)



# ======================================================================================================== superficies de pared
class _PSurf:
    """Superficie de una rejilla ya construida (P en parámetros u, v): interpolación bilineal y normal hacia `out` (signo del
    producto du × dv)."""

    def __init__(self, uv, vv, P, sgn):
        self.uv, self.vv, self.Pg, self.sgn = uv, vv, P, sgn

    def F(self, U, V, eps=0.0015):
        U = np.asarray(U, float)
        V = np.asarray(V, float)
        P = _bilerp(self.uv, self.vv, self.Pg, U, V)
        dU = _bilerp(self.uv, self.vv, self.Pg, U + eps, V) - _bilerp(self.uv, self.vv, self.Pg, U - eps, V)
        dV = _bilerp(self.uv, self.vv, self.Pg, U, V + eps) - _bilerp(self.uv, self.vv, self.Pg, U, V - eps)
        N = np.cross(dU, dV) * self.sgn
        N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)
        return P, N

    def FT(self, V, U):
        return self.F(U, V)

    def pt(self, u, v):
        P, N = self.F(np.array([u]), np.array([v]))
        return Vector(P[0]), Vector(N[0])


def _flare(g, z):
    return g["FL"] * np.clip(1 - np.asarray(z, float) / g["z_wt"], 0, 1) ** 2


V_B, R_B = 0.034, 0.03        # arranque del doblez al pie de la pared y su radio
V_G = V_B - PI / 2 * R_B      # fin del doblez (la lona ya en el piso)
SOD = 0.17                    # ancho del faldón tendido en el piso


def _sod_rows():
    return [V_G - SOD, V_G - SOD + 0.0055, V_G - SOD + 0.0123, V_G - SOD + 0.0135, V_G - SOD + 0.0147] + \
        list(np.linspace(V_G - SOD + 0.034, V_G, 7)[:-1]) + list(np.linspace(V_G, V_B, 5)[:-1])


def _foot(g, V, Xn, seed, H):
    """Pie de la pared: doblez hacia afuera y faldón tendido en el piso. Devuelve (dist hacia afuera desde el plano del pie,
    z) para V < V_B. H = altura de las arrugas del faldón (>= 0)."""
    V = np.asarray(V, float)
    ph = np.clip((V_B - V) / R_B, 0, PI / 2)
    d_b = R_B * (1 - np.cos(ph))
    z_b = V_B - R_B * np.sin(ph)
    gnd = V < V_G
    d = np.where(gnd, R_B + (V_G - V), d_b)
    z = np.where(gnd, 0.004 + H, z_b + H * _ss(V_G + 0.012, V_G - 0.004, V))
    return d, z


def _sod_specs(r, a, b):
    """Pliegues del faldón en el piso: lona amontonada en crestas anchas (5–8 cm, 0,8–2,4 cm de alto) casi perpendiculares
    al muro, algunas diagonales, y bolsas bajas."""
    sp = []
    x = a + _f(r.uniform(0.0, 0.12))
    while x < b:
        sp.append((x, SOD * _f(r.uniform(0.45, 0.65)), PI / 2 + _jit(r, 0.45), _f(r.uniform(0.16, 0.34)), _f(r.uniform(0.045, 0.075)),
                   _f(r.uniform(0.008, 0.024))))
        if r.uniform() < 0.35:
            sp.append((x + _jit(r, 0.05), SOD * 0.5, PI / 2 + _jit(r, 1.1), _f(r.uniform(0.1, 0.2)), 0.035, _f(r.uniform(0.004, 0.01))))
        x += _f(r.uniform(0.14, 0.32))
    return sp


def _sod_H(U, V, seed, specs):
    """Arrugas del faldón en el piso: pliegues amontonados (crestas hacia afuera), ruido y orilla ondulada; siempre >= 0."""
    t = np.clip((V_G - V) / SOD, 0, 1)
    H = _ridges(U, t * SOD, specs)
    H += 0.003 * (0.5 + 0.5 * _noise2(U, V, 6.0, seed)) * _ss(0.0, 0.3, t)
    return np.maximum(H, 0.0) * (V < V_G + 0.012)


class _SideWall:
    """Pared lateral cerrada (side = +1 fondo, -1 frente): cuelga lazada bajo el alero, festón y caída en V bajo cada punto de
    lazada, panza de viento (de +Y, hacia dentro en el fondo), pliegues por gravedad abajo, arrugas diagonales desde las
    esquinas de las ventanas y los pies; abajo dobla hacia afuera y el faldón queda tendido y arrugado en el piso."""

    def __init__(self, g, L, side, seed, wins):
        self.g, self.L, self.side, self.seed, self.wins = g, L, side, seed, wins
        r = rng(seed)
        self.zt = g["z_wt"]
        self.xw = g["Xe"] + 0.025
        self.lace = list(np.arange(-self.xw + 0.07, self.xw - 0.05, 0.3))
        self.folds = [(_f(r.uniform(0.22, 0.6)), _f(r.uniform(0, 6.3)), _f(r.uniform(0.003, 0.0065))) for _ in range(7)]
        vd = []
        for x in self.lace:
            vd.append((x + _jit(r, 0.02), self.zt - 0.16, -PI / 2 + _jit(r, 0.2), _f(r.uniform(0.22, 0.38)), 0.022,
                       _f(r.uniform(0.002, 0.0042))))
        self.vdrape = vd
        pk = []
        for (xa, xb, za, zb, kind) in wins:
            for (cx, cz, a0) in ((xa, za, -PI * 0.75), (xb, za, -PI * 0.25), (xa, zb, PI * 0.75), (xb, zb, PI * 0.25)):
                a = a0 + _jit(r, 0.2)
                pk.append((cx + math.cos(a) * 0.03, cz + math.sin(a) * 0.03, a, _f(r.uniform(0.35, 0.6)), 0.09,
                           _f(r.uniform(0.08, 0.11)), _f(r.uniform(0.0025, 0.004)), 1.0))
        for xk in g["xs"]:
            for sx in (-1, 1):
                a = -PI / 2 + sx * _f(r.uniform(0.5, 0.9))
                pk.append((xk + sx * 0.05, self.zt - 0.03, a, _f(r.uniform(0.5, 0.9)), 0.12, _f(r.uniform(0.1, 0.15)),
                           _f(r.uniform(0.003, 0.005)), 0.8))
                a = PI / 2 + sx * _f(r.uniform(0.4, 0.8))
                pk.append((xk + sx * 0.05, 0.1, a, _f(r.uniform(0.35, 0.6)), 0.1, _f(r.uniform(0.09, 0.13)),
                           _f(r.uniform(0.0025, 0.004)), 0.8))
        self.pk = pk
        self.sod = _sod_specs(r, -self.xw + 0.08, self.xw - 0.08)
        self.wind = -0.02 if side > 0 else 0.008

    def D(self, X, Z):
        g, xs = self.g, self.g["xs"]
        X, Z = np.broadcast_arrays(np.asarray(X, float), np.asarray(Z, float))
        zt = self.zt
        legs = [-self.xw] + xs[1:-1] + [self.xw]
        B = np.zeros_like(X)
        for k in range(len(legs) - 1):
            a, b = legs[k], legs[k + 1]
            B += np.sin(PI * np.clip((X - a) / (b - a), 0, 1)) * ((X > a) & (X < b))
        fz = np.clip((Z - 0.12) / (zt - 0.12), 0, 1)
        D = self.wind * B * np.sin(PI * fz) ** 0.8
        low = (1 - fz) ** 1.5 * np.sqrt(B)
        for (lam, ph, a) in self.folds:
            D += a * np.sin(X * 2 * PI / lam + ph + 2.2 * Z) * low
        D += _ridges(X, Z, self.vdrape) * fz ** 2
        D += _packets(X, Z, self.pk)
        D += (0.0025 * _noise2(X, Z, 1.5, self.seed) + 0.001 * _noise2(X, Z, 4.2, self.seed + 1)) * np.sqrt(B) * fz
        for (xa, xb, za, zb, kind) in self.wins:
            dx = np.maximum(np.maximum(xa - X, X - xb), 0)
            dz = np.maximum(np.maximum(za - Z, Z - zb), 0)
            D *= _ss(0.02, 0.14, np.hypot(dx, dz))
        D *= _ss(self.xw, self.xw - 0.16, np.abs(X)) * _ss(0.05, 0.16, Z) * _ss(zt + 0.002, zt - 0.08, Z)
        if self.side > 0:                                    # adentro: nunca toca las patas (lona por fuera de ellas)
            D = np.maximum(D, -0.0095 - 0.03 * (1 - np.exp(-np.min(np.abs(X[..., None] - np.array(xs)), axis=-1) / 0.06)))
        # festón del remate entre puntos de lazada
        return D

    def build(self, mb):
        g, side = self.g, self.side
        xs = g["xs"]
        legs = [-self.xw] + list(xs[1:-1]) + [self.xw]
        xb = []
        for k in range(len(legs) - 1):
            n = max(8, int((legs[k + 1] - legs[k]) / 0.041))
            xb += list(0.35 * _cosspace(legs[k], legs[k + 1], n) + 0.65 * np.linspace(legs[k], legs[k + 1], n + 1))
        forced = list(xs[1:-1]) + [-self.xw, self.xw, -self.xw + 0.0135, self.xw - 0.0135]
        zf = [self.zt, self.zt - 0.0135, self.zt - 0.0147, self.zt - 0.0123]
        for (xa, xb_, za, zb, kind) in self.wins:
            forced += [xa, xb_]
            zf += [za, zb]
        xv = _merge([v for v in xb if abs(v) < self.xw], forced, 0.01)
        zr = _merge(list(np.linspace(V_B, self.zt, 54)), zf, 0.012)
        vv = np.array(_sod_rows() + list(zr))
        U, V = np.meshgrid(xv, vv, indexing="ij")
        Z = np.maximum(V, V_B)
        Dw = self.D(U, Z)
        fest = np.abs(np.sin(PI * (U + self.xw - 0.07) / 0.3))
        Zs = Z - 0.007 * fest * np.exp(-(self.zt - Z) / 0.07)
        H = _sod_H(U, V, self.seed + 7, self.sod)
        d, zf_ = _foot(g, V, U, self.seed, H)
        fl = _flare(g, Z)
        yv = g["Yw"] + fl + Dw
        y = np.where(V >= V_B, yv, g["Yw"] + g["FL"] + d)
        y = y + 0.006 * _noise2(U, V, 3.0, self.seed + 9) * (V < V_G) * np.clip((V_G - V) / SOD, 0, 1)
        z = np.where(V >= V_B, Zs, zf_)
        xx = U + np.sign(U) * fl * (np.abs(U) / self.xw) ** 6
        P = np.stack([xx, side * y, z], -1)
        self.uv, self.vv = xv, vv
        mask = np.ones((len(xv) - 1, len(vv) - 1), bool)
        for (xa, xb_, za, zb, kind) in self.wins:
            ia, ib = int(np.argmin(np.abs(xv - xa))), int(np.argmin(np.abs(xv - xb_)))
            ja, jb = int(np.argmin(np.abs(vv - za))), int(np.argmin(np.abs(vv - zb)))
            mask[ia:ib, ja:jb] = False
        self.S = _PSurf(xv, vv, P, -side)
        N = _grid_normals(P) * (-side)
        P2 = _curl(P, N, 1, -1)
        m2 = _grow_mask(mask, 1, -1, 6)
        P2 = _curl(P2, _grid_normals(P2) * (-side), 1, 0)
        m2 = _grow_mask(m2, 1, 0, 6)
        P3 = _curl(P2, _grid_normals(P2) * (-side), 0, -1)
        m3 = _grow_mask(m2, 0, -1, 6)
        P3 = _curl(P3, _grid_normals(P3) * (-side), 0, 0)
        m3 = _grow_mask(m3, 0, 0, 6)
        _grid(mb, P3, "canvas", m3)

    def details(self, mb, roof):
        g, side = self.g, self.side
        S = self.S
        r = rng(self.seed + 5)
        # ventanas
        for (xa, xb, za, zb, kind) in self.wins:
            _window(mb, S, xa, xb, za, zb, kind, side, self.seed + int(xa * 10))
        # lazada del remate: ojillos y gazas de cordón a lengüetas cosidas por dentro de la rodilla
        for x in self.lace[::3] + self.lace[1::3]:
            p, n = S.pt(x, self.zt - 0.026)
            _grommet(mb, p, n, ro=0.0095, ri=0.005)
            sk = g["s_ks"] + 0.03 if side < 0 else g["s_tot"] - g["s_ks"] - 0.03
            lo, qn = _inner_tab(mb, roof, x, sk, side)
            inn = p - n * 0.003
            path = [p + n * 0.003, inn, lo - qn * 0.002, lo + Vector((0, 0, 0.006)) - qn * 0.004, inn + Vector((0.008, 0, 0.004)) - n * 0.004]
            _tube(mb, [tuple(v) for v in path], 0.0024, mat="fabric", seg=12, rad=0.004, nseg=2, soft=True)
        # gazas de estacado al pie: ojillo, cordón y estaca forjada
        xs = g["xs"]
        for x in list(xs) + [(xs[k] + xs[k + 1]) / 2 for k in range(4)]:
            x = max(min(x, self.xw - 0.12), -self.xw + 0.12) + (0.06 if abs(x) < self.xw - 0.2 else 0.0)
            _stake_loop(mb, S, x, side, seed=int(r.integers(1e6)), axis="y")


def _inner_tab(mb, roof, x, sk, side):
    """Lengüeta de reata cosida por dentro de la rodilla (sigue la lona) con su gaza libre abajo; devuelve el punto de la
    gaza y la normal de la lona."""
    sgn = 1 if side < 0 else -1
    ss = np.linspace(sk + 0.016 * sgn, sk - 0.03 * sgn, 6)
    P, N = roof.F(np.full_like(ss, x), ss)
    pts = [Vector(p) - Vector(n) * 0.0011 for p, n in zip(P, N)]
    n_ = Vector(N[-1])
    pts[-1] = pts[-1] - n_ * 0.005
    pts[-2] = pts[-2] - n_ * 0.0012
    _strap(mb, [tuple(v) for v in pts], w=0.02, t=0.0014, up=(1, 0, 0))
    return pts[-1] - n_ * 0.001, n_


def _stake_loop(mb, S, u, side, seed=0, axis="y", end=1):
    """Gaza de estacado: ojillo en el pie de la pared (z 0,075), cordón doble que pasa sobre el faldón y abraza una estaca
    forjada hincada a 0,3 m (cabeza de hongo)."""
    r = rng(seed)
    p, n = S.pt(u, 0.062)
    _grommet(mb, p, n, ro=0.0095, ri=0.005)
    out = Vector((0, side, 0)) if axis == "y" else Vector((end, 0, 0))
    lat = Vector((1, 0, 0)) if axis == "y" else Vector((0, 1, 0))
    sb = p + out * (0.25 + _jit(r, 0.03)) + lat * _jit(r, 0.03)
    sb.z = 0.0
    top, ax = _stake_pin(mb, sb, lean=tuple(out * 0.28), h=0.075, seed=int(r.integers(1e6)))
    rr = 0.0024
    for k in (-1, 1):
        a = top + lat * (k * 0.0105) - out * 0.003
        path = [p - n * 0.0035 + lat * (k * 0.002), p + n * 0.004 + lat * (k * 0.003) - Vector((0, 0, 0.004)),
                (p + a) * 0.5 + Vector((0, 0, 0.012)) + lat * (k * 0.006), a + Vector((0, 0, 0.002))]
        _tube(mb, [tuple(v) for v in path], rr, mat="fabric", seg=12, rad=0.008, nseg=2, soft=True)
    ring = [top + (lat * math.cos(2 * PI * j / 14) + out * math.sin(2 * PI * j / 14)) * 0.0108 for j in range(14)]
    with mb.soft():
        loop_tube(mb, ring, rr, seg=12, mat="fabric", normal=(0, 0, 1))


def _strap(mb, path, w=0.025, t=0.0016, up=(1, 0, 0), side=None, mat="fabric"):
    """Reata plana (w de ancho a lo largo de `up`, t de espesor) barrida por una trayectoria."""
    P = [Vector(p) for p in path]
    if len(P) == 2:
        P = [P[0], P[0].lerp(P[1], 0.5), P[1]]
    sweep_frame(mb, rr_profile(t, w, min(t * 0.45, 0.0007), n=1), [tuple(p) for p in P], mat, up=up)


def _window(mb, S, xa, xb, za, zb, kind, side, seed):
    """Ventana TEMPER: vano con ribete que envuelve la orilla, malla mosquitera, y solapa de oscurecimiento cosida arriba:
    enrollada y atada con dos cintas (open) o bajada y atada a los lados (closed)."""
    r = rng(seed)
    rc = 0.022
    # ribete (cinta doblada sobre la orilla del vano), con esquinas redondeadas
    path = []
    cs = ((xb - rc, zb - rc, 0.0), (xa + rc, zb - rc, PI / 2), (xa + rc, za + rc, PI), (xb - rc, za + rc, 1.5 * PI))
    for k, (cx, cz, a0) in enumerate(cs):
        for i in range(5):
            a = a0 + PI / 2 * i / 4
            path.append((cx + rc * math.cos(a), cz + rc * math.sin(a), math.cos(a), math.sin(a)))
        nx_, nz_, a1 = cs[(k + 1) % 4]
        p0 = (cx + rc * math.cos(a0 + PI / 2), cz + rc * math.sin(a0 + PI / 2))
        p1 = (nx_ + rc * math.cos(a1), nz_ + rc * math.sin(a1))
        m = max(2, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / 0.03))
        for i in range(1, m):
            t = i / m
            ang = a0 + PI / 2
            path.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t, math.cos(ang), math.sin(ang)))
    U = np.array([p[0] for p in path])
    V = np.array([p[1] for p in path])
    P, N = S.F(U, V)
    dU = np.array([p[2] for p in path])
    dV = np.array([p[3] for p in path])
    P2, _ = S.F(U + dU * 0.01, V + dV * 0.01)
    Out = P2 - P                                          # hacia el vano
    Out /= np.maximum(np.linalg.norm(Out, axis=-1, keepdims=True), 1e-12)
    prof = [(-0.016, 0.001), (0.0, 0.0012), (0.0018, 0.0006), (0.0022, 0.0), (0.0018, -0.0006), (0.0, -0.0012), (-0.016, -0.001),
            (-0.0165, 0.0)]
    rings = [[Vector(P[i] + Out[i] * a + N[i] * b) for (a, b) in prof] for i in range(len(P))]
    _loop_rings(mb, rings, "fabric")
    # malla mosquitera (4 mm hacia dentro, bajo el ribete)
    uu = np.linspace(xa - 0.01, xb + 0.01, 10)
    vv = np.linspace(za - 0.01, zb + 0.01, 7)
    Uu, Vv = np.meshgrid(uu, vv, indexing="ij")
    Pm, Nm = S.F(Uu, Vv)
    _slab_grid(mb, Pm, Nm, -0.0046, -0.004, "net")
    zs = zb + 0.12
    if kind == "open":
        R = 0.03
        p0, n0 = S.pt(xa - 0.035, zs)
        p1, n1 = S.pt(xb + 0.035, zs)
        Lr = (p1 - p0).length
        M = _frame_x(p0 - Vector((0, 0, R + 0.012)), p1 - p0, up=(0, 0, 1))
        M = M @ Matrix(((1, 0, 0, 0), (0, -side, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))) if False else M
        y_out = Vector((0, side, 0))
        Mloc = _roll_frame(p0, (p1 - p0).normalized(), y_out)
        rad = _roll(mb, Mloc, Lr, R, seed, lambda x: -(R + 0.012) - 0.005 * math.sin(PI * x / Lr), top=0.0,
                    ties=(0.12, Lr - 0.12), dx=0.03, na=26, nst_cap=18)
        for xt in (0.12, Lr - 0.12):
            _tie_wrap(mb, Mloc, rad, xt, -(R + 0.012), top=0.04, w=0.02, seed=seed + int(xt * 100))
    else:
        # solapa bajada: lona doble que cuelga 6 mm fuera de la pared, cosida arriba, atada a los lados
        uu = np.linspace(xa - 0.05, xb + 0.05, 30)
        vv = np.linspace(za - 0.05, zs, 22)
        Uu, Vv = np.meshgrid(uu, vv, indexing="ij")
        Pw, Nw = S.F(Uu, Vv)
        fu = (Uu - uu[0]) / (uu[-1] - uu[0])
        fv = (Vv - vv[0]) / (vv[-1] - vv[0])
        off = 0.006 + 0.004 * np.sin(PI * fu) * np.sin(PI * fv) ** 0.7 + 0.0025 * np.sin(fu * 2 * PI * 3.3 + 1.1) * (1 - fv) ** 2
        off = off * _ss(1.0, 0.92, fv) + 0.0016 * _ss(0.92, 1.0, fv)
        Pf = Pw + Nw * off[..., None]
        Nf = _grid_normals(Pf) * (-side) * (1 if True else -1)
        Pf2 = _curl(Pf, Nf, 1, 0)
        Pf2 = _curl(Pf2, _grid_normals(Pf2) * (-side), 0, 0)
        Pf2 = _curl(Pf2, _grid_normals(Pf2) * (-side), 0, -1)
        _grid(mb, Pf2, "canvas")
        # costura de arriba (cordón de puntada) y lazos atados en las esquinas de abajo
        pts = [S.pt(u, zs - 0.004)[0] + S.pt(u, zs - 0.004)[1] * 0.0018 for u in np.linspace(xa - 0.045, xb + 0.045, 14)]
        _tube(mb, pts, 0.0009, mat="canvas", seg=8, soft=True)
        for u in (xa - 0.03, xb + 0.03):
            p, n = S.pt(u, za - 0.035)
            _bow(mb, p + n * (0.0075), n, seed=seed + int(u * 50))


def _loop_rings(mb, rings, mat):
    """Une anillos (listas de Vector, perfil cerrado) a lo largo de un lazo cerrado."""
    V = [[mb.bm.verts.new(tuple(p)) for p in ring] for ring in rings]
    mi = mb.mi(mat)
    n, k = len(V), len(V[0])
    for i in range(n):
        A, B = V[i], V[(i + 1) % n]
        for j in range(k):
            f = mb.bm.faces.new((A[j], A[(j + 1) % k], B[(j + 1) % k], B[j]))
            f.material_index = mi
            f.smooth = True


def _open_rings(mb, rings, mat, caps=True):
    V = [[mb.bm.verts.new(tuple(p)) for p in ring] for ring in rings]
    mi = mb.mi(mat)
    n, k = len(V), len(V[0])
    for i in range(n - 1):
        A, B = V[i], V[i + 1]
        for j in range(k):
            f = mb.bm.faces.new((A[j], A[(j + 1) % k], B[(j + 1) % k], B[j]))
            f.material_index = mi
            f.smooth = True
    if caps:
        for ring, rev in ((V[0], True), (V[-1], False)):
            f = mb.bm.faces.new(ring[::-1] if rev else ring)
            f.material_index = mi


def _slab_grid(mb, P, N, t0, t1, mat):
    """Sólido delgado cerrado que sigue una superficie (malla mosquitera, parches)."""
    A = P + N * t0
    B = P + N * t1
    _grid(mb, B, mat)
    _grid(mb, A[:, ::-1], mat)
    for (ra, rb) in ((A[0], B[0]), (B[-1], A[-1]), (A[:, 0], B[:, 0]), (B[:, -1], A[:, -1])):
        _grid(mb, np.stack([ra, rb], 1), mat)


def _bow(mb, p, n, seed=0, w=0.012):
    """Moño de cinta de amarre (nudo, dos orejas y dos chicotes colgando)."""
    r = rng(seed)
    n = Vector(n).normalized()
    up = Vector((0, 0, 1))
    side = up.cross(n).normalized()
    if side.length < 1e-3:
        side = Vector((1, 0, 0))
    upn = n.cross(side).normalized()
    _lathe(mb, [(0.0, -0.006), (0.006, -0.004), (0.0075, 0.0), (0.006, 0.004), (0.0, 0.006)], _frame_z(p, side) @ _Rz(30), "fabric",
           seg=12, soft=True)
    for sx in (-1, 1):
        a = _jit(r, 0.2)
        c = p + side * (sx * 0.026) + upn * (0.006 + a * 0.01)
        loop = [p + side * (sx * 0.004) + upn * 0.002, c + upn * 0.012 + n * 0.002, c + side * (sx * 0.016), c - upn * 0.01 + n * 0.002,
                p + side * (sx * 0.004) - upn * 0.002]
        _strap(mb, [tuple(v) for v in fillet([tuple(v) for v in loop], 0.008, 3)], w=w, t=0.0012, up=tuple(n))
        tail = [p + side * (sx * 0.003) - upn * 0.004, p + side * (sx * 0.012) - upn * 0.04 + n * 0.003,
                p + side * (sx * (0.02 + _jit(r, 0.008))) - upn * (0.075 + _jit(r, 0.015)) + n * 0.004]
        _strap(mb, [tuple(v) for v in fillet([tuple(v) for v in tail], 0.02, 3)], w=w, t=0.0012, up=tuple(n))


# ======================================================================================================== lona enrollada
def _roll_frame(p0, xdir, out):
    """Marco local de un rollo: origen p0 (en el muro, arriba del rollo), x = eje, y = hacia afuera del muro, z = arriba."""
    X = Vector(xdir).normalized()
    Y = Vector(out) - X * Vector(out).dot(X)
    Y.normalize()
    Z = X.cross(Y)
    if Z.z < 0:
        Z = -Z
    return Matrix(((X.x, Y.x, Z.x, p0[0]), (X.y, Y.y, Z.y, p0[1]), (X.z, Y.z, Z.z, p0[2]), (0, 0, 0, 1)))


def _roll(mb, M, L, R, seed, zc_fn, top=None, ties=(), dx=0.026, na=34, step=0.0042, gap=0.0016, nst_cap=None, mat="canvas"):
    """Lona enrollada real (local: x = eje de 0 a L, y = hacia afuera del muro (muro en y = 0), z = arriba). La tira baja del
    remate (z = top) por el muro, entra tangente al rollo por el lado del muro y da vuelta en espiral (la última vuelta se mete
    bajo la primera); bultos del enrollado flojo, achatado por su peso, arrugas helicoidales, cintura y pellizcos bajo cada
    cinta; en las puntas, cara con las capas de la espiral escalonadas (telescopio) y sus juntas. Devuelve rad(x, θ)."""
    r = rng(seed)
    ph = [_f(v) for v in r.uniform(0, 2 * PI, 6)]
    hel = []
    for _ in range(max(5, int(L / 0.22))):
        sg = 1 if r.uniform() < 0.5 else -1
        hel.append((_f(r.uniform(0, L)), _f(r.uniform(0, 2 * PI * R)), sg * _f(r.uniform(0.35, 0.95)), _f(r.uniform(0.2, 0.55)),
                    _f(r.uniform(0.007, 0.013)), _f(r.uniform(0.0025, 0.005))))
    for _ in range(max(3, int(L / 0.5))):                       # pliegues largos aplastados a lo largo del rollo
        hel.append((_f(r.uniform(0, L)), _f(r.uniform(0, 2 * PI * R)), _jit(r, 0.12), _f(r.uniform(0.4, 1.3)),
                    _f(r.uniform(0.005, 0.009)), _f(r.uniform(0.002, 0.004)) * (1 if r.uniform() < 0.7 else -1)))
    pinch = []
    for xt in ties:
        for sx in (-1, 1):
            for _ in range(5):
                pinch.append((xt + sx * _f(r.uniform(0.04, 0.07)), _f(r.uniform(0, 2 * PI * R)), _jit(r, 0.25),
                              _f(r.uniform(0.05, 0.11)), _f(r.uniform(0.004, 0.007)), _f(r.uniform(0.0012, 0.0024))))

    def rad(x, th):
        x = np.asarray(x, float)
        th = np.asarray(th, float)
        lump = 1.0 + 0.07 * np.sin(2 * th + ph[0] + x * 3.1) + 0.045 * np.sin(3 * th + ph[1] - x * 5.3) + \
            0.05 * np.sin(x * 4.3 + ph[2]) + 0.03 * np.sin(x * 11.0 + ph[3]) + 0.025 * np.sin(th + x * 7.7 + ph[5])
        rr = R * lump - step * th / (2 * PI)
        arc = np.mod(th, 2 * PI) * R
        rr = rr + _ridges(x, arc, hel) + _ridges(x, arc, pinch)
        for xt in ties:
            rr = rr - 0.16 * R * np.exp(-((x - xt) / 0.028) ** 2)
        return rr

    xs_ = list(np.arange(0.0, L, dx)) + [L]
    for xt in ties:
        xs_ += list(xt + np.linspace(-0.09, 0.09, 11))
    xv = _merge([v for v in xs_ if 0.0 <= v <= L], [0.0, L], 0.004)
    th = np.concatenate([np.linspace(0.0, 2 * PI, na + 1), 2 * PI + np.array([0.18, 0.36, 0.5])])
    rows = []
    zc = np.array([zc_fn(x) for x in xv])
    r0 = rad(xv, 0.0)
    yc = gap + r0
    if top is not None:
        for f in np.linspace(0.0, 1.0, 5)[:-1]:
            zz = top + (zc - top) * f
            yy = gap * f + 0.0004 * np.sin(xv * 9 + ph[4]) * f
            rows.append(np.stack([xv, yy, zz], -1))
    Xg, Tg = np.meshgrid(xv, th, indexing="ij")
    Rg = rad(Xg, Tg)
    Yg = yc[:, None] - np.cos(Tg) * Rg
    Zg = zc[:, None] - np.sin(Tg) * Rg * 0.93
    for j in range(len(th)):
        rows.append(np.stack([xv, Yg[:, j], Zg[:, j]], -1))
    P = np.stack(rows, 1)
    Pw = (np.concatenate([P, np.ones(P.shape[:2] + (1,))], -1) @ np.array(M).T)[..., :3]
    _grid(mb, Pw, mat)
    # caras de las puntas: capas de la espiral escalonadas
    tele = [_f(v) for v in r.uniform(-0.004, 0.01, 40)]
    for (xe, sx) in ((0.0, -1), (L, 1)):
        nr = nst_cap or int(R / 0.0016)
        na2 = 32
        ycx = gap + _f(rad(np.array([xe]), np.array([0.0]))[0])
        zcx = zc_fn(xe)
        an = np.linspace(0, 2 * PI, na2, endpoint=False)
        rout = rad(np.full(na2, xe), an) + step * an / (2 * PI) - step - 0.0008
        rmax = _f(np.min(rout))
        rr_ = np.linspace(0.004 / rmax, 1.0, nr)
        Rf, An = np.meshgrid(rr_, an, indexing="ij")
        Rr = Rf * rout[None, :]
        RO = rout[None, :]
        lay = (RO - Rr) / step + An / (2 * PI)
        k = np.floor(lay).astype(int)
        fr = lay - k
        tl = np.array(tele)
        h = tl[np.clip(k, 0, 39)] * (1 - _ss(0.82, 1.0, fr)) + tl[np.clip(k + 1, 0, 39)] * _ss(0.82, 1.0, fr)
        h = h - 0.0016 * np.exp(-((np.minimum(fr, 1 - fr)) / 0.08) ** 2)
        h = h * _ss(RO, RO - 0.006, Rr) - 0.012 * (1 - Rf) ** 2
        Xc = xe + sx * h
        Yc = ycx - np.cos(An) * Rr
        Zc = zcx - np.sin(An) * Rr * 0.93
        Pc = np.stack([Xc, Yc, Zc], -1)
        Pc = np.concatenate([Pc, Pc[:, :1]], 1)
        Pcw = (np.concatenate([Pc, np.ones(Pc.shape[:2] + (1,))], -1) @ np.array(M).T)[..., :3]
        _grid(mb, Pcw, mat)
        c = (np.array(M) @ np.array([xe + sx * (tl[0] - 0.012), ycx, zcx, 1.0]))[:3]
        cv = mb.bm.verts.new(tuple(c))
        ring = [mb.bm.verts.new(tuple(p)) for p in Pcw[0, :-1].tolist()]
        mi = mb.mi(mat)
        for j in range(na2):
            f = mb.bm.faces.new((ring[j], ring[(j + 1) % na2], cv))
            f.material_index = mi
            f.smooth = True
        # dobladillo lateral de la vuelta exterior (orilla de la pared enrollada)
        tt = np.linspace(0.0, 2 * PI + 0.4, 30)
        rr2 = rad(np.full_like(tt, xe), tt)
        loc = [(xe - sx * 0.0012, ycx - math.cos(a) * (q + 0.0002), zcx - math.sin(a) * (q + 0.0002) * 0.93) for a, q in zip(tt, rr2)]
        _tube(mb, [tuple(M @ Vector(p)) for p in loc], 0.0013, mat=mat, seg=8, soft=True)
    return rad


def _tie_wrap(mb, M, rad, xt, zc, top, w=0.025, seed=0, buckle=False, G=None):
    """Cinta que abraza un rollo (local del rollo): baja por el lado del muro, da la vuelta por abajo, sube por fuera y termina
    arriba (en G si se da, con hebilla de escalera y chicote colgando; si no, se amarra en un moño arriba del rollo)."""
    r = rng(seed)
    th = np.linspace(0.0, 2 * PI * 0.78, 22)
    rr = rad(np.full_like(th, xt), th) + 0.0011
    y0 = _f(rad(np.array([xt]), np.array([0.0]))[0]) + 0.0016
    pts = [(xt, -0.0012, top)]
    pts.append((xt, -0.0012, zc + 0.02))
    for a, q in zip(th, rr):
        pts.append((xt, y0 - math.cos(a) * q, zc - math.sin(a) * q * 0.93))
    if G is not None:
        pts.append(tuple(G))
    else:
        pts.append((xt, y0 * 0.45, zc + _f(rr[-1]) * 1.2 + 0.006))
    world = [tuple(M @ Vector(p)) for p in pts]
    ax = tuple(M.to_3x3() @ Vector((1, 0, 0)))
    _strap(mb, world, w=w, t=0.0016, up=ax)
    if G is None:
        p = M @ Vector((xt, y0 * 0.45, zc + _f(rr[-1]) * 1.2 + 0.012))
        _bow(mb, p, M.to_3x3() @ Vector((0, 1, 0.6)), seed=seed, w=w * 0.8)
    return world



# ======================================================================================================== testeros
DW, DH = 0.75, 1.98           # medio ancho y altura de la puerta
VENT = (0.25, 2.42, 2.68)     # ventila de gablete: medio ancho, z abajo, z arriba
Z_LO = 1.80                   # arriba de esta altura las filas siguen el contorno del gablete


class _EndWall:
    """Testero (end = -1 en -X, +1 en +X): lona tensada al arco extremo (lazada en espiral al tubo bajo la campana), abombado
    leve, pliegues por gravedad abajo, arrugas diagonales desde las esquinas de la puerta y de la ventila, orillas laterales
    que doblan hacia dentro (retorno bajo la pared lateral), pie doblado hacia afuera con faldón en el piso."""

    def __init__(self, g, roof, L, end, seed, door_open):
        self.g, self.roof, self.L, self.end, self.seed, self.door_open = g, roof, L, end, seed, door_open
        r = rng(seed)
        self.Ye = g["Yw"] - 0.016
        self.rc = 0.012
        self.e_max = PI / 2 * self.rc + 0.045
        y_, z_, ny, nz = _pf(g, np.linspace(g["s_ks"], g["s_r"], 400))
        cy, cz = y_ + ny * O, z_ + nz * O
        self.top_y, self.top_z = -cy[::-1], cz[::-1]                # |y| creciente
        self.folds = [(_f(r.uniform(0.25, 0.6)), _f(r.uniform(0, 6.3)), _f(r.uniform(0.003, 0.006))) for _ in range(6)]
        pk = []
        for sx in (-1, 1):
            a = PI / 2 - sx * (PI / 2 - _f(r.uniform(0.6, 0.9)))
            pk.append((sx * DW + sx * 0.02, DH + 0.02, a, _f(r.uniform(0.6, 0.95)), 0.13, _f(r.uniform(0.11, 0.15)),
                       _f(r.uniform(0.006, 0.009)), 1.0))
            a = -PI / 2 + sx * _f(r.uniform(0.2, 0.5))
            pk.append((sx * (DW + 0.03), 0.1, PI / 2 + sx * _f(r.uniform(0.3, 0.6)), _f(r.uniform(0.5, 0.8)), 0.12, 0.13,
                       _f(r.uniform(0.004, 0.006)), 0.8))
            a = PI / 2 - sx * (PI / 2 - _f(r.uniform(0.6, 0.9)))
            pk.append((sx * VENT[0] + sx * 0.02, VENT[2] + 0.02, a, _f(r.uniform(0.3, 0.45)), 0.08, 0.09, 0.003, 1.0))
            a = -PI / 2 - sx * _f(r.uniform(0.5, 0.8))
            pk.append((sx * (self.Ye - 0.1), 1.95, a, _f(r.uniform(0.6, 0.9)), 0.12, _f(r.uniform(0.12, 0.16)),
                       _f(r.uniform(0.003, 0.005)), 0.8))
        self.pk = pk
        self.sod = _sod_specs(r, -self.Ye + 0.05, self.Ye - 0.05)

    def z_top(self, y):
        return np.interp(np.abs(y), self.top_y, self.top_z) - 0.045

    def D(self, Y, Z, ZT):
        Y, Z = np.broadcast_arrays(np.asarray(Y, float), np.asarray(Z, float))
        Ye = self.Ye
        fy = np.clip((Y + Ye) / (2 * Ye), 0, 1)
        fz = np.clip((Z - 0.12) / np.maximum(ZT - 0.12, 0.1), 0, 1)
        D = 0.007 * np.sin(PI * fy) * np.sin(PI * fz) ** 0.8
        low = (1 - fz) ** 1.8 * np.sin(PI * fy) ** 0.5
        for (lam, ph, a) in self.folds:
            D += a * np.sin(Y * 2 * PI / lam + ph + 1.5 * Z) * low
        D += _packets(Y, Z, self.pk)
        D += 0.0012 * _noise2(Y, Z, 1.7, self.seed + 5) * np.sin(PI * fy) * np.sin(PI * fz)
        # cerca de la puerta y la ventila: tensa
        dd = np.hypot(np.maximum(np.abs(Y) - DW, 0), np.maximum(Z - DH, 0))
        D *= _ss(0.0, 0.08, dd) if self.door_open else 1.0
        dv = np.hypot(np.maximum(np.abs(Y) - VENT[0], 0), np.maximum(np.maximum(VENT[1] - Z, Z - VENT[2]), 0))
        D *= _ss(0.0, 0.06, dv)
        D *= _ss(Ye, Ye - 0.15, np.abs(Y)) * _ss(0.05, 0.15, Z) * _ss(ZT, ZT - 0.1, Z)
        return np.maximum(D, 0.0) * _ss(ZT - 0.02, ZT - 0.25, Z) + D * (1 - _ss(ZT - 0.02, ZT - 0.25, Z))

    def build(self, mb):
        g, end = self.g, self.end
        Ye, rc = self.Ye, self.rc
        yb = list(np.linspace(-Ye, Ye, int(2 * Ye / 0.041) + 1))
        forced = [-Ye, Ye, -DW, DW, -VENT[0], VENT[0], 0.0, -DW - 0.0135, DW + 0.0135]
        ym = _merge(yb, forced, 0.01)
        ret = [self.rc * PI / 2 * f for f in (0.33, 0.66, 1.0)] + [PI / 2 * rc + d for d in (0.018, 0.032, 0.045)]
        uv = np.array(sorted([-(Ye + e) for e in ret] + list(ym) + [Ye + e for e in ret]))
        # filas: faldón + doblez (v < V_B), parte baja a z fija, parte alta siguiendo el gablete por nudos
        lo = list(_merge(list(np.linspace(V_B, Z_LO, 42)), [], 0.001))
        seg_n = (5, 11, 7, 12)
        kz = [Z_LO, DH, VENT[1], VENT[2]]
        taus = [0.0]
        tot = sum(seg_n)
        acc = 0
        for n in seg_n:
            for k in range(1, n + 1):
                taus.append((acc + k) / tot)
            acc += n
        taus = np.array(taus)
        ktau = np.array([0.0] + [sum(seg_n[:k + 1]) / tot for k in range(4)])
        vv = np.array(_sod_rows() + lo[:-1] + list(Z_LO + taus * 1.4))
        self.uv, self.vv = uv, vv
        nlo = len(_sod_rows()) + len(lo) - 1
        U, V = np.meshgrid(uv, vv, indexing="ij")
        yy = np.clip(U, -Ye, Ye)
        ZT = self.z_top(yy)
        # z de las filas altas
        Zup = np.zeros_like(U[:, nlo:])
        wl = _ss(0.85, 1.45, np.abs(yy[:, nlo:]))
        for i in range(len(uv)):
            zt = ZT[i, 0]
            kzc = [Z_LO] + [min(k, zt - (4 - j) * 0.01) for j, k in enumerate(kz[1:], 1)] + [zt]
            ex = np.interp(taus, ktau, kzc)
            lin = Z_LO + taus * (zt - Z_LO)
            Zup[i] = ex * (1 - wl[i]) + lin * wl[i]
        Z = np.concatenate([np.maximum(V[:, :nlo], V_B), Zup], 1)
        self.Zg = Z
        fl = _flare(g, Z)
        Dw = self.D(yy, Z, ZT)
        H = _sod_H(yy, V, self.seed + 7, self.sod)
        d, zf = _foot(g, V, yy, self.seed, H)
        low = V < V_B
        xo = np.where(low, g["Xe"] + g["FL"] + d, g["Xe"] + fl + Dw)
        z = np.where(low, zf, Z)
        e = np.maximum(np.abs(U) - Ye, 0.0)
        ph = np.minimum(e / rc, PI / 2)
        yw = np.sign(U) * (np.minimum(np.abs(U), Ye) + fl * (np.abs(yy) / Ye) ** 6 + rc * np.sin(ph))
        xo = xo - rc * (1 - np.cos(ph)) - np.maximum(e - PI / 2 * rc, 0.0)
        yw = yw + np.sign(U) * np.where(low & (e > 0), d, 0.0) * 0
        P = np.stack([end * xo, yw, z], -1)
        mask = np.ones((len(uv) - 1, len(vv) - 1), bool)
        ia, ib = int(np.argmin(np.abs(uv + DW))), int(np.argmin(np.abs(uv - DW)))
        if self.door_open:
            jb = int(np.argmin(np.abs(Z[len(uv) // 2] - DH)))
            mask[ia:ib, 0:jb] = False
        va, vb_ = int(np.argmin(np.abs(uv + VENT[0]))), int(np.argmin(np.abs(uv - VENT[0])))
        zc = Z[len(uv) // 2]
        ja, jb2 = int(np.argmin(np.abs(zc - VENT[1]))), int(np.argmin(np.abs(zc - VENT[2])))
        mask[va:vb_, ja:jb2] = False
        # en las orillas laterales del retorno no hay faldón (la lona sube recta)
        retm = np.abs(U[:-1, 0] + U[1:, 0]) / 2 > Ye + 0.001
        mask[retm, :len(_sod_rows()) - 1] = False
        self.mask = mask
        sg = end
        self.S = _PSurf(uv, vv, P, sg)
        P2 = _curl(P, _grid_normals(P) * sg, 1, -1)
        m2 = _grow_mask(mask, 1, -1, 6)
        P2 = _curl(P2, _grid_normals(P2) * sg, 1, 0)
        m2 = _grow_mask(m2, 1, 0, 6)
        P3 = _curl(P2, _grid_normals(P2) * sg, 0, -1)
        m3 = _grow_mask(m2, 0, -1, 6)
        P3 = _curl(P3, _grid_normals(P3) * sg, 0, 0)
        m3 = _grow_mask(m3, 0, 0, 6)
        _grid(mb, P3, "canvas", m3)

    def v_of(self, y, z):
        """Parámetro v de la altura z en la columna y (interpolando la rejilla de alturas)."""
        i = int(np.clip(np.searchsorted(self.uv, y) - 1, 0, len(self.uv) - 2))
        t = (y - self.uv[i]) / (self.uv[i + 1] - self.uv[i])
        zc = self.Zg[i] * (1 - t) + self.Zg[i + 1] * t
        nsod = len(_sod_rows())
        return _f(np.interp(z, zc[nsod:], self.vv[nsod:]))

    def pt(self, y, z):
        return self.S.pt(y, self.v_of(y, z))

    def details(self, mb):
        g, end, S = self.g, self.end, self.S
        r = rng(self.seed + 3)
        # ventila de gablete: ribete, malla y solapa sostenida por dos varillas
        self._vent(mb)
        # puerta
        if self.door_open:
            self._door_open(mb)
        else:
            self._door_closed(mb)
        # gazas de estacado al pie (fuera de la puerta)
        for y in (-2.6, -1.6, 1.6, 2.6):
            _stake_loop(mb, S, y, 0, seed=int(r.integers(1e6)), axis="x", end=end)
        # lazada en espiral al tubo del arco extremo (bajo la campana)
        self._lacing(mb)

    def _hole_binding(self, mb, pts_uv, out_uv, closed):
        U = np.array([p[0] for p in pts_uv])
        V = np.array([self.v_of(p[0], p[1]) for p in pts_uv])
        P, N = self.S.F(U, V)
        V2 = np.array([self.v_of(p[0] + o[0] * 0.01, p[1] + o[1] * 0.01) for p, o in zip(pts_uv, out_uv)])
        P2, _ = self.S.F(U + np.array([o[0] for o in out_uv]) * 0.01, V2)
        Out = P2 - P
        Out /= np.maximum(np.linalg.norm(Out, axis=-1, keepdims=True), 1e-12)
        prof = [(-0.016, 0.001), (0.0, 0.0012), (0.0018, 0.0006), (0.0022, 0.0), (0.0018, -0.0006), (0.0, -0.0012), (-0.016, -0.001),
                (-0.0165, 0.0)]
        rings = [[Vector(P[i] + Out[i] * a + N[i] * b) for (a, b) in prof] for i in range(len(P))]
        (_loop_rings if closed else _open_rings)(mb, rings, "fabric")
        return P, N, Out

    def _vent(self, mb):
        hw_, za, zb = VENT
        rc = 0.02
        pts, outs = [], []
        cs = ((hw_ - rc, zb - rc, 0.0), (-hw_ + rc, zb - rc, PI / 2), (-hw_ + rc, za + rc, PI), (hw_ - rc, za + rc, 1.5 * PI))
        for k, (cx, cz, a0) in enumerate(cs):
            for i in range(5):
                a = a0 + PI / 2 * i / 4
                pts.append((cx + rc * math.cos(a), cz + rc * math.sin(a)))
                outs.append((math.cos(a), math.sin(a)))
            nx_, nz_, a1 = cs[(k + 1) % 4]
            p0 = (cx + rc * math.cos(a0 + PI / 2), cz + rc * math.sin(a0 + PI / 2))
            p1 = (nx_ + rc * math.cos(a1), nz_ + rc * math.sin(a1))
            m = max(2, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / 0.03))
            for i in range(1, m):
                t = i / m
                pts.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
                outs.append((math.cos(a0 + PI / 2), math.sin(a0 + PI / 2)))
        self._hole_binding(mb, pts, outs, True)
        uu = np.linspace(-hw_ - 0.01, hw_ + 0.01, 8)
        zz = np.linspace(za - 0.01, zb + 0.01, 5)
        Pm = np.array([[tuple(self.pt(u, z)[0]) for z in zz] for u in uu])
        Nm = np.array([[tuple(self.pt(u, z)[1]) for z in zz] for u in uu])
        _slab_grid(mb, Pm, Nm, -0.0046, -0.004, "net")
        # solapa: cosida 4 cm sobre el vano, abierta 28° hacia afuera, dos varillas de aluminio la sostienen
        end = self.end
        zh = zb + 0.04
        out = Vector((end, 0, 0))
        ang = math.radians(28)
        dn = Vector((0, 0, -math.cos(ang))) + out * math.sin(ang)
        uu = np.linspace(-hw_ - 0.06, hw_ + 0.06, 22)
        ww = np.linspace(0.0, 0.33, 14)
        rows = []
        for w in ww:
            row = []
            for u in uu:
                p0, n0 = self.pt(u, zh)
                fu = (u - uu[0]) / (uu[-1] - uu[0])
                fw = w / ww[-1]
                bow = 0.018 * math.sin(PI * fu) ** 0.8 * math.sin(PI * fw) + 0.005 * math.sin(fu * 2 * PI * 2.3 + 0.7) * fw
                q = p0 + n0 * 0.002 + dn * w - Vector((0, 0, 1)) * bow - out * bow * 0.35
                q = q - Vector((0, 0, 0.022 * math.sin(PI * fu) ** 0.7 * fw * fw))
                row.append(tuple(q))
            rows.append(row)
        Pf = np.array(rows).transpose(1, 0, 2)
        Nf = _grid_normals(Pf)
        if Nf[Nf.shape[0] // 2, -1].dot(np.array([end, 0, 0.5])) < 0:
            Nf = -Nf
        sgn = 1
        P2 = _curl(Pf, Nf, 1, -1)
        Nf2 = _grid_normals(P2)
        if Nf2[Nf2.shape[0] // 2, -3].dot(np.array([end, 0, 0.5])) < 0:
            sgn = -1
        P2 = _curl(P2, Nf2 * sgn, 0, 0)
        P2 = _curl(P2, _grid_normals(P2) * sgn, 0, -1)
        _grid(mb, P2, "canvas")
        # fuelles laterales (triángulos de lona entre el muro y la orilla de la solapa)
        for j in (0, -1):
            rows = []
            for fw in np.linspace(0.0, 1.0, 9):
                ed = Vector(Pf[j, int(round(fw * (len(ww) - 1)))])
                pw, nw = self.pt(uu[j], zh - fw * 0.33 * math.cos(ang))
                row = []
                for ft in np.linspace(0.0, 1.0, 6):
                    q = pw + nw * 0.0015 + (ed - pw - nw * 0.0015) * ft
                    q = q + Vector((0, -np.sign(uu[j]) * 0.01 * math.sin(PI * ft) * math.sin(PI * fw), 0))
                    row.append(tuple(q))
                rows.append(row)
            _grid(mb, np.array(rows), "canvas")
        for u in (-hw_ + 0.02, hw_ - 0.02):
            a, na = self.pt(u, za - 0.05)
            b = Vector(Pf[int(np.argmin(np.abs(uu - u))), -1]) - Vector((0, 0, 0.004))
            _cyl(mb, tuple(a + na * 0.004), tuple(b), 0.004, "aluminium", seg=SEG_T)
            _lathe(mb, [(0.0, -0.002), (0.0056, -0.0016), (0.0062, 0.003), (0.0048, 0.006), (0.0, 0.0065)], _frame_z(a + na * 0.002, na),
                   "rubber", seg=14)

    def _door_open(self, mb):
        """Puerta abierta: ribete en U, medias cremalleras con dientes en ambos costados del vano, hoja enrollada sobre el
        dintel y atada con dos cintas."""
        end = self.end
        rc = 0.03
        pts, outs = [], []
        for z in np.linspace(V_G - SOD + 0.002, V_B, 6)[:-1]:
            pts.append((-DW, None, z))
        # costado izquierdo, dintel y costado derecho (en u, z reales)
        P_ = [(-DW, z) for z in np.arange(0.02, DH - rc, 0.03)]
        P_ += [(-DW + rc - rc * math.cos(a), DH - rc + rc * math.sin(a)) for a in np.linspace(0, PI / 2, 5)]
        P_ += [(u, DH) for u in np.arange(-DW + rc + 0.03, DW - rc - 0.01, 0.03)]
        P_ += [(DW - rc + rc * math.sin(a), DH - rc + rc * math.cos(a)) for a in np.linspace(0, PI / 2, 5)]
        P_ += [(DW, z) for z in np.arange(DH - rc - 0.03, 0.019, -0.03)]
        O_ = []
        for (u, z) in P_:
            if abs(z - DH) < 1e-6 or z > DH - rc:
                if abs(u) < DW - rc:
                    O_.append((0.0, -1.0))
                else:
                    cx = np.sign(u) * (DW - rc)
                    d = np.array([u - cx, z - (DH - rc)])
                    d /= max(np.linalg.norm(d), 1e-9)
                    O_.append((-d[0], -d[1]))
            else:
                O_.append((1.0 if u < 0 else -1.0, 0.0))
        self._hole_binding(mb, P_, O_, False)
        # medias cremalleras: cinta y dientes moldeados que asoman del ribete hacia el vano
        for sx in (-1, 1):
            zz = np.arange(0.03, DH - 0.05, 0.0036)
            for z in zz:
                p, n = self.pt(sx * DW, z)
                q, _ = self.pt(sx * DW - sx * 0.01, z)
                d = (q - p).normalized()
                _tooth(mb, p + d * 0.0012, d, n, 0.0052)
            # tope inferior de la cremallera
            p, n = self.pt(sx * DW, 0.022)
            slab(mb, _frame_z(p, n) @ _T(0, 0, -0.0016), 0.009, 0.006, 0.0032, rc=0.0015, re=0.0008, mat="steel", nc=2, ne=1)
        # hoja enrollada sobre el dintel
        R = 0.05
        za = DH + 0.15
        p0, n0 = self.pt(-DW - 0.04, za)
        p1, n1 = self.pt(DW + 0.04, za)
        Lr = (p1 - p0).length
        M = _roll_frame(p0, p1 - p0, Vector((end, 0, 0)))
        rad = _roll(mb, M, Lr, R, self.seed + 9, lambda x: -(R + 0.012) - 0.008 * math.sin(PI * x / Lr), top=0.0,
                    ties=(0.18, Lr - 0.18), dx=0.032, na=26, nst_cap=24)
        for xt in (0.18, Lr - 0.18):
            _tie_wrap(mb, M, rad, xt, -(R + 0.012) - 0.008 * math.sin(PI * xt / Lr), top=0.05, w=0.025, seed=self.seed + int(xt * 99))

    def _door_closed(self, mb):
        """Puerta cerrada: cremalleras a ambos costados bajo solapas de tormenta; abajo la solapa termina y deja ver los
        dientes engranados, la corredera y su jalador; parches de refuerzo en las esquinas del dintel."""
        for sx in (-1, 1):
            # cintas de la cremallera y dientes engranados (los 0,42 m de abajo, a la vista)
            for z in np.arange(0.035, 0.44, 0.0036):
                p, n = self.pt(sx * DW, z)
                q, _ = self.pt(sx * DW + 0.01, z)
                d = (q - p).normalized()
                _tooth(mb, p - d * 0.0047 + n * 0.0021, d, n, 0.0052)
                p2, _ = self.pt(sx * DW, z + 0.0018)
                _tooth(mb, p2 + d * 0.0047 + n * 0.0021, -d, n, 0.0052)
            prof = [(-0.0175, -E_EMB), (-0.0175, 0.0006), (-0.016, 0.0009), (-0.0042, 0.0009), (-0.004, 0.0006), (-0.004, -E_EMB)]
            V = np.array([self.v_of(sx * DW, z) for z in np.linspace(0.02, DH - 0.02, 60)])
            for side_ in (-1, 1):
                pr = [(side_ * a, h) for (a, h) in prof]
                if side_ < 0:
                    pr = pr[::-1]
                _strip(mb, self.S.FT, V, sx * DW, [(a, h) for (a, h) in (pr if side_ > 0 else pr[::-1])][::-1] if False else pr)
            # corredera con jalador (abajo: cerrada hacia abajo)
            p, n = self.pt(sx * DW, 0.05)
            _zip_slider(mb, p + n * 0.0025, n, Vector((0, 0, 1)), seed=self.seed + sx)
            # solapa de tormenta (8 cm) cosida del lado de la pared, de 0,44 m al dintel
            w = 0.08
            Vs = np.array([self.v_of(sx * DW, z) for z in np.linspace(0.44, DH + 0.03, 70)])
            fl = [(-0.012, -E_EMB), (-0.012, 0.0024), (-0.0105, 0.0042), (-0.008, 0.0046), (-0.0065, 0.0040), (-0.005, 0.0046),
                  (w - 0.012, 0.0052), (w - 0.0105, 0.0047), (w - 0.0095, 0.0036), (w - 0.0102, 0.0026), (w - 0.012, 0.0022)]
            fl = [(-sx * a, h) for (a, h) in fl]
            if sx > 0:
                fl = fl[::-1]
            _strip(mb, self.S.FT, Vs, sx * DW, fl)
        # costura del dintel (la hoja de la puerta va cosida arriba)
        w = 0.0075
        prof = [(-w, -E_EMB), (-w, 0.0008), (-0.0066, 0.0015), (-0.0042, 0.0016), (-0.0035, 0.001), (-0.0028, 0.0016),
                (0.0028, 0.0016), (0.0035, 0.001), (0.0042, 0.0016), (0.0066, 0.0015), (w, 0.0008), (w, -E_EMB)]
        vh = self.v_of(0.0, DH)
        _strip(mb, self.S.F, np.linspace(-DW - 0.045, DW + 0.045, 50), vh, [(a * 0.1, h) for (a, h) in prof])
        # parches en las esquinas del dintel
        for sx in (-1, 1):
            v0 = self.v_of(sx * (DW + 0.06), DH + 0.06)
            v1 = self.v_of(sx * (DW + 0.06), DH + 0.16)
            _patch(mb, self.S.F, sx * (DW + 0.06), v0, 0.075, 0.075, 0.03, su=1.0, sv=0.1 / max(v1 - v0, 1e-4), t=0.0013)

    def _lacing(self, mb):
        """Remate superior lazado en espiral al tubo del arco extremo: pasa por cada ojillo, sube sobre el tubo y baja por
        dentro (oculto por la campana desde afuera, a la vista desde dentro)."""
        g, end = self.g, self.end
        xa = end * g["xa"]
        ss = []
        for s0, s1 in ((g["s_ke"] + ARM + 0.06, g["s_rs"] - ARM - 0.05), (2 * g["s_r"] - g["s_rs"] + ARM + 0.05, 2 * g["s_r"] - g["s_ke"] - ARM - 0.06)):
            n = int((s1 - s0) / 0.5)
            ss += list(np.linspace(s0, s1, n + 1))
        Xo = Vector((end, 0, 0))
        for k, s in enumerate(ss):
            c = _pf_pt(g, s, 0.0, xa)
            t, n = _pf_tn(g, s)
            y = c.y
            p, nw = self.pt(y, _f(self.z_top(np.array([y]))[0]) - 0.022)
            _grommet(mb, p, nw, ro=0.0095, ri=0.005)
            R = R_A + 0.0034
            path = [p + nw * 0.0034, p - nw * 0.004]
            for th in np.linspace(-PI * 0.55, PI * 1.05, 6):
                path.append(c + (Xo * math.cos(th) + n * math.sin(th)) * R * (1.0 if th < PI * 0.5 else 1.0) + t * (0.03 * (th + PI * 0.55) / (PI * 1.6)))
            q, nq = self.pt(y + (t.y * 0.06), _f(self.z_top(np.array([y + t.y * 0.06]))[0]) - 0.022)
            path += [q - nq * 0.004, q + nq * 0.0035]
            _tube(mb, [tuple(v) for v in path], 0.0025, mat="fabric", seg=12, rad=0.005, nseg=2, soft=True)


def _tooth(mb, c, d, n, length, width=0.0027, thick=0.0036, mat="polymer"):
    """Diente moldeado de cremallera #10: base en c, sale `length` hacia d, cabeza más angosta y delgada."""
    d = Vector(d).normalized()
    n = Vector(n).normalized()
    w = n.cross(d).normalized()
    c = Vector(c)
    vs = []
    for (L_, sw, st) in ((0.0, 1.0, 1.0), (length, 0.62, 0.7)):
        for (a, b) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vs.append(mb.bm.verts.new(tuple(c + d * L_ + w * (a * width * 0.5 * sw) + n * (b * thick * 0.5 * st))))
    mi = mb.mi(mat)
    for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        f = mb.bm.faces.new([vs[i] for i in q])
        f.material_index = mi


def _zip_slider(mb, p, n, along, seed=0):
    """Corredera de cremallera (cuerpo de dos placas con nariz) y jalador de lámina con cordón."""
    r = rng(seed)
    M = _frame_z(p, n, tuple(along))
    slab(mb, M @ _T(0, 0, -0.002), 0.024, 0.016, 0.0065, rc=(0.007, 0.007, 0.0025, 0.0025), re=0.0015, mat="gunmetal", nc=3, ne=1)
    _lathe(mb, [(0.0, 0.0045), (0.0032, 0.0045), (0.0032, 0.0068), (0.0024, 0.0078), (0.0, 0.0079)], M @ _T(0.004, 0, 0), "gunmetal",
           seg=12)
    tab = M @ _T(0.004, 0, 0.0075) @ _Ry(-100 + _jit(r, 8))
    slab(mb, tab @ _T(0.017, 0, -0.0009), 0.03, 0.0095, 0.0018, rc=0.0035, re=0.0006, mat="gunmetal", nc=2, ne=1)
    p0 = tab @ Vector((0.031, 0, 0))
    dn = (tab.to_3x3() @ Vector((1, 0, 0))).normalized()
    _cord(mb, [tuple(p0), tuple(p0 + dn * 0.025 + Vector(n) * 0.004), tuple(p0 + dn * 0.05 + Vector(n) * (0.006 + _jit(r, 0.003)))],
          r=0.0022, mat="cable", rad=0.01)
    _lathe(mb, [(0.0, -0.006), (0.0035, -0.004), (0.004, 0.003), (0.0028, 0.006), (0.0, 0.007)],
           _frame_z(p0 + dn * 0.056 + Vector(n) * 0.006, dn), "polymer", seg=12)



# ======================================================================================================== costado enrollado
def _buckle(mb, p, along, nrm, mat="polymer"):
    """Hebilla de escalera (ladder-lock) de polímero: marco redondeado de 34 × 30 mm con dos barras."""
    M = _frame_x(p, along, up=nrm)
    Mf = M @ _Rx(90) if False else M
    Mz = _frame_z(p - Vector(nrm) * 0.0016, nrm, tuple(along))
    rrframe(mb, Mz, (0.0, 0.0, 0.03, 0.036, 0.005), (0.0, 0.0, 0.022, 0.028, 0.0025), 0.0034, re_o=0.0012, re_i=0.0008, n=3, ne=1,
            mat=mat)
    for dx in (-0.004, 0.0045):
        slab(mb, Mz @ _T(dx, 0.0, 0.0002), 0.0034, 0.029, 0.0028, rc=0.0012, re=0.0008, mat=mat, nc=2, ne=1)
    del Mf


def _rolled_wall(mb, g, roof, L, side, seed):
    """Pared lateral enrollada hasta el alero: tira que baja del remate al rollo, rollo en espiral con caída entre cintas, y
    cintas de reata que abrazan el rollo, suben al ojillo del faldón y cierran con hebilla de escalera y chicote."""
    r = rng(seed)
    Yw = g["Yw"]
    xw = g["Xe"] + 0.025
    R = 0.056
    zt = g["z_wt"]
    zc0 = g["s_vb"] - R - 0.012
    ties = [x for x in roof.tie_x()]
    ties = sorted(ties)
    x0, x1 = -xw, xw
    kn = [x0] + ties + [x1]

    def zc_w(x):
        for k in range(len(kn) - 1):
            a, b = kn[k], kn[k + 1]
            if a <= x <= b:
                if k == 0:
                    return zc0 - 0.024 * ((b - x) / (b - a)) ** 1.6
                if k == len(kn) - 2:
                    return zc0 - 0.024 * ((x - a) / (b - a)) ** 1.6
                return zc0 - 0.016 * math.sin(PI * (x - a) / (b - a)) - 0.004 * math.sin(2 * PI * (x - a) / (b - a) + seed)
        return zc0
    if side < 0:
        p0 = Vector((x0, side * Yw, zt))
        M = _roll_frame(p0, Vector((1, 0, 0)), Vector((0, side, 0)))
        loc = lambda xw_: xw_ - x0  # noqa: E731
    else:
        p0 = Vector((x1, side * Yw, zt))
        M = _roll_frame(p0, Vector((-1, 0, 0)), Vector((0, side, 0)))
        loc = lambda xw_: x1 - xw_  # noqa: E731
    Lr = x1 - x0
    tl = [loc(x) for x in ties]
    wz = lambda xl: zc_w(x0 + xl if side < 0 else x1 - xl) - zt  # noqa: E731
    rad = _roll(mb, M, Lr, R, seed, wz, top=0.0, ties=tl, dx=0.032, na=30)
    # dobladillo superior de la tira (se ve desde dentro) y lazada al alero
    pts = [M @ Vector((xl, 0.0003, -0.0012)) for xl in np.linspace(0.0, Lr, 120)]
    _tube(mb, pts, 0.0013, mat="canvas", seg=8, soft=True)
    Minv = M.inverted()
    for xt, xw_ in zip(tl, ties):
        G, Gn = roof.val_gr[(0 if side < 0 else 1, round(xw_, 4))]
        Gl = Minv @ (G - Gn * 0.004)
        zc = wz(xt)
        world = _tie_wrap(mb, M, rad, xt, zc, top=-0.07, w=0.025, seed=seed + int(xt * 31), G=Gl)
        # hebilla en el tramo que sube al faldón, chicote colgando
        a, b = Vector(world[-2]), Vector(world[-1])
        pb = a.lerp(b, 0.45)
        u = (b - a).normalized()
        nrm = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
        nrm = (nrm - u * nrm.dot(u)).normalized()
        _buckle(mb, pb + nrm * 0.0012, u, nrm)
        ax = (M.to_3x3() @ Vector((1, 0, 0))).normalized()
        tail = [pb - u * 0.012 + nrm * 0.0042, pb - u * 0.03 + nrm * 0.008, pb - u * 0.05 + nrm * 0.012 - Vector((0, 0, 0.03)),
                pb + nrm * 0.016 - Vector((0, 0, 0.11 + _jit(r, 0.02))) + ax * _jit(r, 0.01)]
        _strap(mb, fillet([tuple(v) for v in tail], 0.025, 4), w=0.025, t=0.0016, up=tuple(ax))
        # punta de la cinta (dobladillo con remate) en el chicote
        # gaza del faldón: la cinta entra al ojillo
    # lazada del remate de la tira al alero (por dentro)
    for xw_ in np.arange(-xw + 0.07, xw - 0.05, 0.45):
        p = Vector((xw_, side * (Yw - 0.0003), zt - 0.026))
        n = Vector((0, side, 0))
        _grommet(mb, p, n, ro=0.0095, ri=0.005)
        sk = g["s_ks"] + 0.03 if side < 0 else g["s_tot"] - g["s_ks"] - 0.03
        lo, qn = _inner_tab(mb, roof, xw_, sk, side)
        inn = p - n * 0.003
        path = [p + n * 0.003, inn, lo - qn * 0.002, lo + Vector((0, 0, 0.006)) - qn * 0.004, inn + Vector((0.008, 0, 0.004)) - n * 0.004]
        _tube(mb, [tuple(v) for v in path], 0.0024, mat="fabric", seg=12, rad=0.004, nseg=2, soft=True)


# ======================================================================================================== vientos
def _tensioner(mb, c, u, nrm):
    """Tensor de aluminio de 3 ojos (95 × 26 × 4 mm), canto matado."""
    M = _frame_z(c, nrm, tuple(u))
    w = 0.0317
    for k in (-1, 0, 1):
        rc = (0.0, 0.0, 0.0, 0.0)
        if k == 1:
            rc = (0.011, 0.0005, 0.0005, 0.011)
        elif k == -1:
            rc = (0.0005, 0.011, 0.011, 0.0005)
        else:
            rc = (0.0005, 0.0005, 0.0005, 0.0005)
        holed(mb, M @ _T(k * w, 0, -0.002), (0.0, 0.0, w / 2 + (0.00005 if k == 0 else 0.0), 0.013, rc), (0.0, 0.0, 0.0056, 0.0056, 0.0056),
              0.004, re_o=0.0008, re_i=0.0007, n=16, ne=1, mat="aluminium", re_b=0.0006)
    return [M @ Vector((k * w, 0, 0)) for k in (-1, 0, 1)]


def _tieout(mb, roof, x, side, seed):
    """Parche de refuerzo cosido en la rodilla (caja con pespunte perimetral), lengüeta de reata con costura de caja con X y
    argolla D colgando hacia el viento. Devuelve (punto de la argolla, dirección hacia afuera)."""
    g = roof.g
    r = rng(seed)
    s_c = g["s_e"] - 0.012 if side < 0 else g["s_e1"] + 0.012
    sv = (RK + O) / RK
    _patch(mb, roof.F, x, s_c, 0.085, 0.075, 0.028, su=1.0, sv=sv, t=0.0013, step=0.028, nc=3)
    ss = np.linspace(s_c + 0.025 * (1 if side < 0 else -1), s_c - 0.05 * (1 if side < 0 else -1), 8)
    P, N = roof.F(np.full_like(ss, x), ss)
    path = [Vector(p) + Vector(n) * 0.0021 for p, n in zip(P, N)]
    out = (path[-1] - path[-2]).normalized()
    nn = Vector(N[-1])
    tip = path[-1] + out * 0.02 - nn * 0.002
    path.append(tip)
    path.append(tip + (out - nn * 0.3).normalized() * 0.022)
    _strap(mb, [tuple(v) for v in path], w=0.025, t=0.0022, up=(1, 0, 0))
    # costura de caja con X sobre la lengüeta (hilo)
    pa, pb = path[1], path[4]
    ax = Vector((1, 0, 0))
    nA, nB = Vector(N[1]), Vector(N[4])
    c = [pa - ax * 0.0095 + nA * 0.0011, pa + ax * 0.0095 + nA * 0.0011, pb + ax * 0.0095 + nB * 0.0011, pb - ax * 0.0095 + nB * 0.0011]
    with mb.soft():
        loop_tube(mb, [v for k in range(4) for v in (c[k], c[k].lerp(c[(k + 1) % 4], 0.5))], 0.0005, seg=6, mat="fabric",
                  normal=tuple(nA))
        for (a, b) in ((c[0], c[2]), (c[1], c[3])):
            mb.tube([tuple(a), tuple(a.lerp(b, 0.5) + nA * 0.0002), tuple(b)], 0.0005, seg=6, mat="fabric")
    # argolla D de acero (alambre de 5 mm) en la gaza
    dpt = path[-1] + (out - nn * 0.3).normalized() * 0.004
    dd = (out - nn * 0.3).normalized()
    side_ = ax
    ring = []
    for k in range(16):
        a = 2 * PI * k / 16
        if math.cos(a) < 0:
            q = dpt + side_ * (0.016 * math.sin(a)) + dd * 0.0
        else:
            q = dpt + side_ * (0.016 * math.sin(a)) + dd * (0.026 * math.cos(a))
        ring.append(q)
    with mb.soft():
        loop_tube(mb, fillet([tuple(v) for v in ring] + [tuple(ring[0])], 0.004, 2)[:-1], 0.0025, seg=12, mat="steel",
                  normal=tuple(dd.cross(side_)))
    del r
    return dpt + dd * 0.026, dd


def _guy(mb, pa, dd, stake_base, lean, seed, tensioner=True):
    """Viento de cuerda de 3/8" (Ø 9,5 mm): gaza amarrada a la argolla D (as de guía con su nudo), tramo con su catenaria,
    tensor de 3 ojos a 0,4 m de la estaca, dos ramales que abrazan la estaca forjada bajo la cabeza, chicote con nudo."""
    r = rng(seed)
    rr = 0.00475
    top, ax = _stake_pin(mb, Vector(stake_base), lean=tuple(Vector(lean) * 0.36), h=0.13, seed=int(r.integers(1e6)))
    pa = Vector(pa)
    knot = pa + Vector(dd) * 0.05
    d = top - knot
    Lg = d.length
    u = d.normalized()
    side = u.cross(Vector((0, 0, 1))).normalized()
    up = side.cross(u).normalized()
    pt = top - u * 0.42
    # gaza en la argolla y nudo
    loop = [knot + side * 0.004, pa + side * 0.012 + Vector(dd) * 0.006, pa - Vector(dd) * 0.004 + up * 0.006,
            pa - side * 0.012 + Vector(dd) * 0.006, knot - side * 0.004]
    _tube(mb, [tuple(v) for v in fillet([tuple(v) for v in loop], 0.008, 3)], rr * 0.95, mat="fabric", seg=SEG_T)
    _lathe(mb, [(0.0, -0.014), (rr * 1.9, -0.012), (rr * 2.4, -0.004), (rr * 2.3, 0.006), (rr * 1.7, 0.012), (0.0, 0.0145)],
           _frame_z(knot, u) @ _Rz(_f(r.uniform(0, 360))), "fabric", seg=SEG_T,
           )
    n = max(6, int(Lg / 0.22))
    cat = [knot.lerp(pt, k / n) - Vector((0, 0, 0.004 * Lg * 4 * (k / n) * (1 - k / n))) for k in range(n + 1)]
    holes = _tensioner(mb, pt + up * 0.0, u, up) if tensioner else [pt - u * 0.03, pt, pt + u * 0.03]
    hA, hB, hC = holes[0], holes[1], holes[2]
    std = cat[:-1] + [hA + up * 0.008, hA, hA - up * 0.008]
    ring_c = top + ax * 0.0
    s1 = [hA - up * 0.008, hA - up * 0.012 + u * 0.06, ring_c - u * 0.012 + side * 0.004]
    _tube(mb, [tuple(v) for v in fillet([tuple(v) for v in std[-4:] + s1[1:]], 0.02, 2)], rr, mat="fabric", seg=SEG_T)
    _tube(mb, [tuple(v) for v in std[:-3]], rr, mat="fabric", seg=SEG_T, caps=False)
    ring = [top + (side * math.cos(2 * PI * k / 12) + u * math.sin(2 * PI * k / 12)) * 0.0125 for k in range(12)]
    loop_tube(mb, ring, rr, seg=SEG_T, mat="fabric", normal=tuple(ax))
    s2 = [ring_c - u * 0.012 - side * 0.004, hC - up * 0.012 + u * 0.03, hC - up * 0.008, hC, hC + up * 0.008, hB + up * 0.008,
          hB, hB - up * 0.008, hB - up * 0.02 - u * 0.01, hB - up * 0.05 - u * 0.004 - Vector((0, 0, 0.03 + _jit(r, 0.01)))]
    _tube(mb, [tuple(v) for v in fillet([tuple(v) for v in s2], 0.01, 2)], rr, mat="fabric", seg=SEG_T)
    tk = s2[-1]
    _lathe(mb, [(0.0, -0.008), (rr * 1.6, -0.006), (rr * 2.0, 0.0), (rr * 1.5, 0.006), (0.0, 0.008)],
           _frame_z(tk, Vector((0, 0, 1))), "fabric", seg=SEG_T)


# ======================================================================================================== ensamble
def frame_tent(L=9.75, W=6.1, seed=0, open_front=True, rolled_sides=("front",)):
    """Tienda militar de armazón tipo TEMPER 20 × 32 ft (6,1 × 9,75 m) armada como expendio del puesto avanzado (MIL_2).

    Misma firma, origen, orientación y huella que kit.campaign.frame_tent: origen en el piso al centro; largo L en X, ancho W
    en Y; FRENTE = pared lateral larga en -Y, FONDO = +Y; testeros (puertas) en -X y +X. Cumbrera 3,20 m, alero 2,06 m.
    - rolled_sides: paredes laterales ("front" y/o "back") enrolladas hasta el alero y atadas con cintas de hebilla; las no
      enrolladas cuelgan cerradas con dos ventanas (una con la solapa enrollada y la malla a la vista, otra con la solapa de
      oscurecimiento bajada y atada).
    - open_front: la puerta del testero -X (entrada) abierta con su hoja enrollada sobre el dintel; la del testero +X cerrada.
    Huella: lona y armazón dentro de x ±(L/2 + 0,17), y ±(W/2 + 0,15) al piso (faldones); vientos y estacas hasta
    y ±(W/2 + 1,45) y x ±(L/2 + 2,7). Interior libre a ras de piso: x ±(L/2 - 0,125), y ±(W/2 - 0,13) (cabe el piso de
    triplay de 9,5 × 5,8 m, cara superior a 0,108 m)."""
    mb = MB()
    g = _geo(L, W)
    xs = g["xs"]
    _frame(mb, g, seed)
    rf = _Roof(g, L, seed)
    rf.build(mb)
    rf.details(mb)
    wx = [(xs[1] + xs[2]) / 2, (xs[2] + xs[3]) / 2]
    for side, name in ((-1, "front"), (1, "back")):
        if name in rolled_sides:
            _rolled_wall(mb, g, rf, L, side, seed + (3 if side > 0 else 0) + 101)
        else:
            wins = [(wx[0] - 0.45, wx[0] + 0.45, 1.05, 1.6, "open" if side > 0 else "closed"),
                    (wx[1] - 0.45, wx[1] + 0.45, 1.05, 1.6, "closed" if side > 0 else "open")]
            sw = _SideWall(g, L, side, seed + (5 if side > 0 else 9), wins)
            sw.build(mb)
            sw.details(mb, rf)
    for end in (-1, 1):
        ew = _EndWall(g, rf, L, end, seed + (13 if end > 0 else 17), bool(open_front) and end < 0)
        ew.build(mb)
        ew.details(mb)
    # vientos: 10 en la rodilla (uno por arco y lado) y 2 de cumbrera
    for k, x in enumerate(xs):
        for sy in (-1, 1):
            xp = x + (0.03 if k == 0 else -0.03 if k == 4 else 0.02)
            pa, dd = _tieout(mb, rf, xp, sy, seed + 7 * k + (sy > 0))
            lean = Vector((0.25 * (-1 if k == 0 else 1 if k == 4 else 0), sy, 0)).normalized()
            base = Vector((x + lean.x * 1.45, sy * (W / 2 + 1.35), 0.0))
            _guy(mb, pa, dd, base, lean, seed + k * 3 + (sy > 0))
    for end in (-1, 1):
        x_c = end * (rf.x_hb + rf.r_h * 0.6)
        P, N = rf.F(np.array([end * (rf.x_hb + rf.e_r * 0.5)]), np.array([g["s_r"]]))
        c, n = Vector(P[0]), Vector(N[0])
        out = Vector((end, 0, -0.35)).normalized()
        tab = [c + n * 0.0018 - Vector((end, 0, 0)) * 0.03, c + n * 0.0022, c + n * 0.003 + out * 0.03]
        _strap(mb, [tuple(v) for v in tab], w=0.025, t=0.0022, up=(0, 1, 0))
        ring = [tab[-1] + out * 0.004 + (Vector((0, 1, 0)) * math.sin(2 * PI * k / 14) + out * (0.013 * (1 - math.cos(2 * PI * k / 14)) / 0.016)) * 0.016
                for k in range(14)]
        with mb.soft():
            loop_tube(mb, ring, 0.0025, seg=12, mat="steel", normal=tuple(Vector((0, 1, 0)).cross(out)))
        pa = tab[-1] + out * 0.03
        _guy(mb, pa, out, Vector((end * (L / 2 + 2.6), 0.0, 0.0)), Vector((end, 0, 0)), seed + 40 + end)
        del x_c
    return mb


def _test_frame(L=9.75, W=6.1, seed=0):
    mb = MB()
    _frame(mb, _geo(L, W), seed)
    return mb


def _test_roof(L=9.75, W=6.1, seed=0, frame=True):
    mb = MB()
    g = _geo(L, W)
    if frame:
        _frame(mb, g, seed)
    rf = _Roof(g, L, seed)
    rf.build(mb)
    rf.details(mb)
    return mb


def _test_back(L=9.75, W=6.1, seed=0):
    mb = MB()
    g = _geo(L, W)
    _frame(mb, g, seed)
    rf = _Roof(g, L, seed)
    rf.build(mb)
    xs = g["xs"]
    wx = [(xs[1] + xs[2]) / 2, (xs[2] + xs[3]) / 2]
    wins = [(wx[0] - 0.45, wx[0] + 0.45, 1.05, 1.6, "open"), (wx[1] - 0.45, wx[1] + 0.45, 1.05, 1.6, "closed")]
    sw = _SideWall(g, L, 1, seed + 5, wins)
    sw.build(mb)
    sw.details(mb, rf)
    return mb


def _test_ends(L=9.75, W=6.1, seed=0):
    mb = MB()
    g = _geo(L, W)
    _frame(mb, g, seed)
    rf = _Roof(g, L, seed)
    rf.build(mb)
    for end in (-1, 1):
        ew = _EndWall(g, rf, L, end, seed + 13 + end, end < 0)
        ew.build(mb)
        ew.details(mb)
    return mb

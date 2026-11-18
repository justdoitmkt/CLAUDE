"""kit/armory.py — armamento y municiones para MIL_1_almacen (almacén de armamento pesado) y MIL_2_avanzada (tienda de campaña
que vende munición y armas). Equipo militar contemporáneo, limpio, de poco uso. Calidad AAA (regla R-AAA): perfiles reales,
uniones, tornillería, holguras, nada de cajas sueltas ni curvas facetadas (cilindros visibles >= 24 lados, tubos >= 14).

Diseños GENÉRICOS y ficticios con proporciones de equipo real (no réplica de ningún modelo comercial o reglamentario): sin
marcas, logotipos ni insignias; solo estarcidos inocuos en inglés (R4: nunca los números 13, 14 ni 18).

Convenciones (todas las funciones devuelven un MB de kit.clinic; metros, Z arriba):
- piezas de piso / mesa: origen en el plano de apoyo (z = 0), centradas en X e Y, eje largo a lo largo de +X;
- armas largas y cortas (rifle, pistol, magazine): x = 0 en la cara trasera (cantonera / trasera de la corredera), z = 0 en el
  punto más bajo de la culata (o de la empuñadura), y = 0 plano de simetría; el cañón apunta a +X. Cada docstring da la altura
  del eje del ánima (BORE_Z) para que los armeros de otro agente las sostengan (ver RIFLE_* abajo);
- piezas de muro (vest): origen en la cara del muro (y = 0) en el gancho; la pieza crece hacia -Y.
Materiales: steel, aluminium, rubber, cable, plastic, paint_yellow, sign_white, sign_red, cardboard, fabric, gunmetal (acero
fosfatado oscuro), polymer (polímero gris oscuro), wood_od (madera de caja pintada verde olivo), paint_od (acero pintado verde
olivo), paint_tan (acero pintado arena), brass, canvas (lona / cinta verde olivo).

Fuentes de medidas (consultadas 2026-11): ver docstring de cada función.
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
from mathutils import Matrix, Vector

from kit import port
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rng, rr_profile
from kit.clinic_equipo import arc_solid, loft_rings, revolve, sweep_frame
from kit.clinic_equipo import text as _ce_text
from kit.clinic_servicios import _edge_levels, cup, hexnut, label, lathe, pslab, rpoly_pts, rr_pts, screw, skin, slab

IN = 0.0254
SEG = 24          # lados de todo cilindro visible
SEG_B = 32        # cilindros grandes (proyectiles, tubos de mortero)
SEG_T = 14        # tubos delgados, alambres, cuerdas

# ---------------------------------------------------------------------------------------- datos para armeros (otro agente)
# rifle(kind): x = 0 cantonera, z = 0 talón inferior de la culata; ánima a lo largo de +X a la altura BORE_Z.
RIFLE_BORE_Z = 0.102
RIFLE_LEN = {"carbine": 0.858, "assault": 0.918, "dmr": 1.012}


# ======================================================================================================== utilidades
def _ax(x, y=0.0, z=0.0):
    """Marco con el eje Z local a lo largo de +X mundial (para torneados de cañones, tubos y proyectiles horizontales)."""
    return _T(x, y, z) @ _Ry(90)


def _ccw(P, R):
    P = [tuple(p) for p in P]
    R = list(R) if isinstance(R, (list, tuple)) else [R] * len(P)
    a = sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))
    if a < 0:
        P, R = P[::-1], R[::-1]
    return P, R


def rpoly_n(P, R, delta=0.0, n=3):
    """Como clinic_servicios.rpoly_pts pero con segmentos por esquina según el radio: R < 0,8 mm -> esquina viva (1 punto),
    R < 2,5 mm -> chaflán (2 puntos), si no n + 1 puntos. Lazos compatibles entre desplazamientos (mismo número de puntos)."""
    m = len(P)
    P = [Vector((float(p[0]), float(p[1]))) for p in P]
    N = []
    for i in range(m):
        d = (P[(i + 1) % m] - P[i]).normalized()
        N.append(Vector((-d.y, d.x)))
    Q = [P[i] + (N[i - 1] + N[i]) * (delta / (1 + N[i - 1].dot(N[i]))) for i in range(m)]
    out = []
    for i in range(m):
        ni = 0 if R[i] < 0.0008 else (1 if R[i] < 0.0025 else n)
        q, a, b = Q[i], Q[i - 1], Q[(i + 1) % m]
        if ni == 0:
            out.append((q.x, q.y))
            continue
        e0, e1 = q - a, b - q
        convex = (e0.x * e1.y - e0.y * e1.x) > 0
        rho = max((R[i] - delta) if convex else (R[i] + delta), 2e-4)
        d0, d1 = (a - q).normalized(), (b - q).normalized()
        ang = math.acos(max(-1.0, min(1.0, d0.dot(d1))))
        if ang > PI - 1e-3:                     # esquina colineal: un solo punto (consistente entre desplazamientos)
            out.append((q.x, q.y))
            continue
        t = min(rho / math.tan(ang / 2), (a - q).length * 0.49, (b - q).length * 0.49)
        rho = t * math.tan(ang / 2)
        C = q + (d0 + d1).normalized() * (rho / math.sin(ang / 2))
        v0, v1 = q + d0 * t - C, q + d1 * t - C
        a0 = math.atan2(v0.y, v0.x)
        da = math.atan2(v1.y, v1.x) - a0
        while da > PI:
            da -= 2 * PI
        while da < -PI:
            da += 2 * PI
        for k in range(ni + 1):
            aa = a0 + da * k / ni
            out.append((C.x + rho * math.cos(aa), C.y + rho * math.sin(aa)))
    return out


def pslab_n(mb, M, P, R, L, re=0.004, mat="steel", n=3, ne=2, re0=None):
    """Prisma de contorno poligonal con filetes por esquina (rpoly_n) extruido de z = 0 a L con cantos re / re0."""
    re0 = re if re0 is None else re0
    lv = _edge_levels(L, min(re, L * 0.49), min(re0, L * 0.49), ne) if re > 0 else [(0.0, 0.0), (0.0, L)]
    loops = [[(x, y, z) for (x, y) in rpoly_n(P, R, dl, n)] for (dl, z) in lv]
    return skin(mb, loops, mat, M)


def side(mb, P, R, wid, mat, y0=0.0, re=0.0015, n=3, ne=2, M=None):
    """Silueta lateral [(x, z)] (vista desde -Y) con filete R por esquina, extruida a lo ancho (Y) `wid` centrada en y0,
    cantos redondeados re. Cuerpos de culatas, armazones, empuñaduras planas, palancas."""
    P, R = _ccw(P, R)
    Mx = (M if M is not None else Matrix()) @ _T(0, y0 + wid / 2, 0) @ _Rx(90)
    return pslab_n(mb, Mx, P, R, wid, re=min(re, wid * 0.45), mat=mat, n=n, ne=ne)


def plan(mb, P, R, t, mat, z0=0.0, re=0.0015, n=3, ne=2, M=None):
    """Contorno en planta [(x, y)] extruido en +Z de z0 a z0 + t (placas, chapas, herrajes)."""
    P, R = _ccw(P, R)
    Mx = (M if M is not None else Matrix()) @ _T(0, 0, z0)
    return pslab_n(mb, Mx, P, R, t, re=min(re, t * 0.45), mat=mat, n=n, ne=ne)


def xloft(mb, st, mat, n=4, M=None, caps=(True, True)):
    """Cuerpo a lo largo de X por secciones rectangulares redondeadas [(x, ancho_y, alto_z, z_centro, radio)];
    radio escalar o por esquina (+y+z, -y+z, -y-z, +y-z)."""
    loops = [[(x, y, zc + z) for (y, z) in rr_pts(w, h, r, n)] for (x, w, h, zc, r) in st]
    return skin(mb, loops, mat, M, cap0=caps[0], cap1=caps[1])


def board(mb, mn, mx, mat="wood_od", ch=0.0025, M=None):
    """Tabla / listón con cantos chaflanados (1 segmento): madera cepillada de caja de munición."""
    d = min(abs(mx[0] - mn[0]), abs(mx[1] - mn[1]), abs(mx[2] - mn[2]))
    mb.box(mn, mx, mat, bevel=min(ch, d * 0.3), seg=1, m=M)


def stencil(mb, s, size, M, mat="paint_yellow", depth=0.0004):
    """Estarcido de pintura (relieve de 0,4 mm, hundido 0,3 mm en la superficie): M = plano de la superficie, +Z hacia afuera."""
    _ce_text(mb, s, size, depth + 0.0003, mat, M @ _T(0, 0, -0.0003), res=3 if size >= 0.03 else (2 if size >= 0.016 else 1),
             back=False)


def strap(mb, path, w, t, mat="canvas", up=(0, 0, 1), r=None, caps=True, n=1):
    """Cinta plana (correa, fleje) de ancho w y espesor t a lo largo de una polilínea; `up` = normal de la cara ancha."""
    prof = [(x, y) for (x, y) in rr_profile(w, t, r if r is not None else t * 0.45, n=n)]
    return sweep_frame(mb, prof, path, mat, up=up, caps=caps)


def wire(mb, pts, r, mat="steel", bend=0.01, nseg=4, seg=SEG_T, caps=True):
    """Alambre / varilla / cuerda por una polilínea con dobleces de radio real."""
    P = fillet(pts, bend, nseg) if len(pts) > 2 else pts
    out = [P[0]]
    for p in P[1:]:
        if (Vector(p) - Vector(out[-1])).length > 1e-6:
            out.append(p)
    mb.tube(out, r, seg=seg, mat=mat, caps=caps)


def spline(pts, n=3):
    """Curva Catmull-Rom que pasa por los puntos (n subdivisiones por tramo): cuerdas, cables y correas sin quiebres."""
    P = [Vector(p) for p in pts]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return [tuple(p) for p in out]


def rr_torus(mb, M, w, d, rc, rb, mat, nc=4, nb=6, z=0.0, phase=0.3):
    """Cordón cerrado de sección redonda rb que sigue un rectángulo redondeado w × d (radio rc) en el plano z: bordes
    rolados de latas, empaques, vivos."""
    loops = []
    for k in range(nb):
        a = 2 * PI * k / nb + phase
        o = rb * math.cos(a)
        loops.append([(x, y, z + rb * math.sin(a)) for (x, y) in rr_pts(w + 2 * o, d + 2 * o, rc + o, nc)])
    return skin(mb, loops, mat, M, closed=True)


def _levels(h, re_t, ne_t, re_b, ne_b):
    lv = []
    if re_b > 0 and ne_b > 0:
        for j in range(ne_b + 1):
            p = PI / 2 * j / ne_b
            lv.append((re_b * (1 - math.sin(p)), re_b * (1 - math.cos(p))))
    else:
        lv.append((0.0, 0.0))
    if re_t > 0 and ne_t > 0:
        for j in range(ne_t + 1):
            p = PI / 2 * j / ne_t
            lv.append((re_t * (1 - math.cos(p)), h - re_t + re_t * math.sin(p)))
    else:
        lv.append((0.0, h))
    return lv


def slab2(mb, M, w, d, h, rc, mat, re_t=0.0, ne_t=0, re_b=0.0, ne_b=0, nc=4):
    """Caja de planta redondeada (radio rc, nc segmentos por esquina) de z = 0 a h, con canto superior e inferior
    independientes (radio y número de segmentos): los cantos ocultos no gastan triángulos."""
    rcs = rc if isinstance(rc, (tuple, list)) else (rc,) * 4
    loops = [[(x, y, z) for (x, y) in rr_pts(w - 2 * dl, d - 2 * dl, tuple(max(q - dl, 3e-4) for q in rcs), nc)]
             for (dl, z) in _levels(h, min(re_t, h * 0.49), ne_t, min(re_b, h * 0.49), ne_b)]
    return skin(mb, loops, mat, M)


def shell(mb, M, w, d, h, t, rc, mat, re=0.0, ne=0, nc=4, mat_in=None):
    """Caja hueca de lámina (tapa, cuerpo de lata): boca en z = 0, fondo en z = h, pared t; canto exterior del fondo re."""
    def lp(dl, z, rr):
        return [(x, y, z) for (x, y) in rr_pts(w - 2 * dl, d - 2 * dl, max(rr - dl, 3e-4), nc)]
    inner = [lp(t, h - t, rc), lp(t, 0.0, rc)]
    outer = [lp(dl, z, rc) for (dl, z) in _levels(h, min(re, h * 0.49), ne, 0.0, 0)]
    mats = None
    if mat_in:
        mats = [mat_in, mat] + [mat] * (len(outer) - 1)
    return skin(mb, inner + outer, mat, M, mats=mats)


def rivet(mb, M, d=0.006, mat="steel", seg=12):
    """Cabeza de remache / tornillo de cabeza de gota sobre z = 0 local (hundida 0,2 mm; sin cara inferior)."""
    revolve(mb, [(d / 2, -0.0002), (d * 0.42, d * 0.2), (0.0, d * 0.3)], mat, seg=seg, M=M, caps=False)


def plank(mb, mn, mx, mat="wood_od", ch=0.0025):
    """Tabla aserrada: prisma a lo largo de su eje mayor con las 4 aristas largas chaflanadas (las cabezas quedan vivas,
    como un corte de sierra). 28 triángulos."""
    ext = [mx[i] - mn[i] for i in range(3)]
    a = max(range(3), key=lambda i: ext[i])
    b, c = [i for i in range(3) if i != a]
    ch = min(ch, ext[b] * 0.3, ext[c] * 0.3)
    b0, b1, c0, c1 = mn[b], mx[b], mn[c], mx[c]
    prof = [(b0 + ch, c0), (b1 - ch, c0), (b1, c0 + ch), (b1, c1 - ch), (b1 - ch, c1), (b0 + ch, c1), (b0, c1 - ch), (b0, c0 + ch)]
    rings = []
    for av in (mn[a], mx[a]):
        ring = []
        for (pb, pc) in prof:
            v = [0.0, 0.0, 0.0]
            v[a], v[b], v[c] = av, pb, pc
            ring.append(Vector(v))
        rings.append(ring)
    loft_rings(mb, rings, mat)


def cartridge(mb, M, cal=0.0057, case_len=0.045, bullet=0.012, seg=12, mat_case="brass", mat_bullet="brass", neck=True,
              lite=False):
    """Cartucho metálico a lo largo de Z local (culote en z = 0): culote con ranura de extractor, vaina con hombro y
    cuello, proyectil ojival. cal = diámetro del proyectil."""
    rb = cal * 0.86 if neck else cal / 2 * 1.06
    rh = rb * 1.0
    if neck:
        rbody = cal * 0.84
        prof = [(0.0, 0.0), (rh * 0.98, 0.0), (rh, 0.0012), (rbody * 0.82, 0.0016), (rbody * 0.82, 0.0028), (rbody, 0.0034),
                (rbody * 0.97, case_len * 0.76), (cal * 0.56, case_len * 0.86), (cal * 0.56, case_len)]
    else:
        rbody = cal / 2 * 1.06
        prof = [(0.0, 0.0), (rbody * 1.02, 0.0), (rbody * 1.02, 0.0012), (rbody * 0.86, 0.0016), (rbody * 0.86, 0.0024),
                (rbody, 0.003), (rbody, case_len)]
    if lite:
        prof = [(0.0, 0.0), (rh, 0.0), (rh, 0.0012), (prof[-3][0], case_len * 0.76), (cal * 0.56, case_len * 0.86),
                (cal * 0.56, case_len)] if neck else [(0.0, 0.0), (rbody * 1.02, 0.0), (rbody, 0.003), (rbody, case_len)]
    revolve(mb, prof, mat_case, seg=seg, M=M, caps=False)
    rr = cal / 2
    z0 = case_len - 0.0006
    bp = [(rr * 0.98, z0), (rr, z0 + 0.0012), (rr, z0 + bullet * 0.35), (rr * 0.8, z0 + bullet * 0.7), (rr * 0.42, z0 + bullet * 0.93),
          (0.0, z0 + bullet)]
    if lite:
        bp = [(rr, z0), (rr, z0 + bullet * 0.35), (rr * 0.72, z0 + bullet * 0.75), (0.0, z0 + bullet)]
    revolve(mb, bp, mat_bullet, seg=seg, M=M, caps=True)


# ======================================================================================================== cargador
def _mag_body(mb, M, n_ring=4, lite=False):
    """Cuerpo del cargador curvo de 30 tiros en el marco M: z = 0 boca superior (centro de la sección), crece hacia -Z, el
    frente mira a +X. Tramo recto de 30 mm (dentro del brocal) y curva de radio 0,62 m hacia adelante."""
    H = 0.172
    D, W, R = 0.0635, 0.0235, 0.0045
    Rc = 0.62
    ns = 4 if lite else 5
    sta = []
    for i in range(ns + 1):
        s = H * i / ns
        th = max(s - 0.03, 0.0) / Rc
        cx = Rc * (1 - math.cos(th))
        cz = -(min(s, 0.03) + Rc * math.sin(th))
        sta.append((cx, cz, math.cos(th), math.sin(th)))       # centro y normal "hacia adelante"
    loops = [[(cx + nx * u, v, cz + nz * u) for (u, v) in rr_pts(D, W, R, n_ring)] for (cx, cz, nx, nz) in sta]
    skin(mb, loops, "polymer", M, cap0=True, cap1=True)
    th_end = (H - 0.03) / Rc
    cx, cz = sta[-1][0], sta[-1][1]
    Mb = M @ _T(cx, 0, cz) @ _Ry(-math.degrees(th_end))
    slab2(mb, Mb @ _T(0.002, 0, -0.0075), 0.0715, 0.0275, 0.0088, 0.006, "polymer", re_t=0.0, ne_t=0, re_b=0.0025, ne_b=1, nc=3)


def _mag(mb, M, lite=False):
    """Cargador completo en el marco M (ver _mag_body): cuerpo, base, labios de alimentación y cartucho superior
    (lite: insertado en el arma, sin labios ni cartucho, que quedan dentro del brocal)."""
    _mag_body(mb, M, lite=lite)
    if lite:
        return
    for sy in (-1, 1):
        side(mb, [(-0.026, -0.001), (0.012, -0.001), (0.012, 0.004), (-0.022, 0.006)], [0.0, 0.0, 0.0015, 0.0015], 0.0018,
             "polymer", y0=sy * 0.0105, re=0.0, M=M)
    cartridge(mb, M @ _T(-0.026, 0, 0.0035) @ _Ry(90), cal=0.0057, case_len=0.0445, bullet=0.0125, seg=12, lite=True)


def _drop(mb):
    """Traslada el MB para que su punto más bajo quede en z = 0."""
    z = min(v.co.z for v in mb.bm.verts)
    mb.transform(_T(0, 0, -z))
    return mb


def magazine(seed=0, lite=False):
    """Cargador curvo de polímero de 30 tiros, genérico (sección ~ 64 × 23,5 mm, ~ 19 cm de alto, curva hacia adelante como
    los cargadores de 5,56 mm): cuerpo curvo de sección redondeada, base con labio inferior, labios de alimentación y
    cartucho superior a la vista. Origen: x = 0 cara trasera de la boca, z = 0 apoyo (de pie sobre la base), y = 0 centro;
    el frente mira a +X. Fuentes: en.wikipedia.org/wiki/STANAG_magazine ; magpul.com/firearm-accessories/
    pmag30ar-m4genm3window-5-56x45.html (forma y largo de referencia)."""
    mb = MB()
    _mag(mb, _T(0.03175, 0, 0), lite=lite)
    return _drop(mb)


# ======================================================================================================== lata de munición
def _can_dims(size):
    # M2A1 (.50) ~ 11,75 × 6 × 7,5 in; M19A1 (.30 / 7,62) ~ 11 × 3,9 × 7 in (exteriores)
    return (0.2985, 0.1524, 0.1905) if size == "large" else (0.2770, 0.0990, 0.1780)


def _can_handle(mb, M, span, mat="paint_od"):
    """Asa plegable de fleje de acero estampado abatida sobre la tapa (M: plano de apoyo, +Z arriba) con sus dos orejas
    remachadas (el eje de giro va a lo largo de X)."""
    hx = span / 2
    path = fillet([(-hx, 0.0, 0.0), (-hx, 0.030, 0.0), (hx, 0.030, 0.0), (hx, 0.0, 0.0)], 0.012, 3)
    strap(mb, [M @ Vector(p) for p in path], 0.010, 0.0028, mat=mat, up=M.to_3x3() @ Vector((0, 0, 1)), r=0.0011)
    for sx in (-1, 1):
        x = sx * (hx + 0.0042)
        side(mb, [(-0.009, -0.0028), (0.009, -0.0028), (0.006, 0.0062), (-0.006, 0.0062)], [0.0, 0.0, 0.004, 0.004], 0.003,
             mat, y0=0.0, re=0.0, n=3, M=M @ _T(x, 0.0, 0.0) @ _Rz(90))
        revolve(mb, [(0.0024, -0.0002), (0.002, 0.0008), (0.0, 0.0013)], "steel", seg=12,
                M=M @ _T(x + sx * 0.0015, 0.0, 0.0012) @ _Ry(90 * sx))


def ammo_can(size="large", seed=0, open=False):
    """Lata metálica de munición genérica con tapa abisagrada de cierre por palanca (clase .50 «large» 298 × 152 × 191 mm;
    clase 7,62 «small» 277 × 99 × 178 mm). Cuerpo de lámina con esquinas redondeadas y costura rolada inferior; tapa con
    panel estampado y canto redondeado, empaque de hule (visible abierta), bisagra de pasador en un extremo (nudillos de
    lámina enrollada), palanca de leva con su gancho en el otro, asa de fleje plegable remachada y estarcido «AMMO» + lote.
    open=True: tapa girada 105° sobre la bisagra, cuerpo y tapa huecos. Origen: centro de la base (z = 0 apoyo); largo en
    X (bisagra en -X, palanca en +X), costado con estarcido hacia -Y.
    Fuentes: bulkammo.com/m19a1-30-cal-m2a1-50-cal-ammo-cans-green-brand-new-2 ; alloutdoor.com/?p=475777 (medidas M2A1 /
    M19A1 exteriores e interiores)."""
    r = rng(seed)
    mb = MB()
    L, W, H = _can_dims(size)
    big = size == "large"
    lid_h = 0.042 if big else 0.038
    Lb, Wb = L - 0.010, W - 0.006          # cuerpo (la tapa lo abraza por fuera)
    zl0 = H - lid_h                        # borde inferior de la tapa
    zb = zl0 + 0.022                       # tope del cuerpo (entra 22 mm en la tapa)
    rc = 0.009
    # ---- cuerpo y costura rolada inferior
    if open:
        shell(mb, _T(0, 0, zb) @ _Rx(180), Lb, Wb, zb - 0.004, 0.0012, rc, "paint_od")
    else:
        slab2(mb, _T(0, 0, 0.004), Lb, Wb, zb - 0.004, rc, "paint_od")
    slab2(mb, Matrix(), Lb + 0.003, Wb + 0.003, 0.0065, rc + 0.0015, "paint_od", re_t=0.0025, ne_t=1, re_b=0.0015, ne_b=1)
    # ---- tapa
    hx = -L / 2 - 0.0042                   # eje de la bisagra
    hz = zl0 + 0.004
    lid = MB()
    if open:
        shell(lid, _T(0, 0, zl0), L, W, lid_h - 0.003, 0.0012, rc + 0.003, "paint_od", re=0.005, ne=4)
        rr_torus(lid, _T(0, 0, H - 0.0072), L - 0.0095, W - 0.0095, rc - 0.001, 0.0038, "rubber", nc=4, nb=4, phase=PI / 4)
    else:
        slab2(lid, _T(0, 0, zl0), L, W, lid_h - 0.003, rc + 0.003, "paint_od", re_t=0.005, ne_t=4)
    slab2(lid, _T(0, 0, H - 0.0045), L - 0.050, W - 0.040, 0.0045, 0.012, "paint_od", re_t=0.0025, ne_t=2)
    _can_handle(lid, _T(0, -0.015 if big else -0.012, H - 0.0003), 0.15 if big else 0.14)
    yk, wkl = (0.030, 0.018) if big else (0.022, 0.018)
    for sy in (-1, 1):                     # nudillos de la tapa (lámina enrollada sobre el pasador)
        side(lid, [(-L / 2 + 0.001, zl0 + 0.024), (hx + 0.0005, hz + 0.0035), (hx + 0.0005, hz - 0.0035),
                   (-L / 2 + 0.001, hz - 0.0035)], 0.0, wkl - 0.0006, "paint_od", y0=sy * yk, re=0.0)
        revolve(lid, [(0.0042, -wkl / 2), (0.0042, wkl / 2)], "paint_od", seg=SEG_T, M=_T(hx, sy * yk, hz) @ _Rx(90))
    # palanca de leva (extremo +X): placa con pivote enrollado arriba, oreja del pivote en la tapa
    xl = L / 2 + 0.0004
    lev = MB()
    plan(lev, [(0.006, -0.017), (0.083, -0.014), (0.090, -0.010), (0.090, 0.010), (0.083, 0.014), (0.006, 0.017)],
         [0.0, 0.004, 0.003, 0.003, 0.004, 0.0], 0.0026, "paint_od", re=0.0, n=2)
    revolve(lev, [(0.0045, -0.019), (0.0045, 0.019)], "paint_od", seg=SEG_T, M=_T(0.0015, 0, 0.0045) @ _Rx(90))
    lid.join(lev, _T(xl, 0, H - 0.012) @ _Ry(90 - (2.0 if not open else 22.0)))
    side(lid, [(L / 2 - 0.002, H - 0.019), (xl + 0.0035, H - 0.017), (xl + 0.0055, H - 0.009), (L / 2 - 0.002, H - 0.005)],
         0.0, 0.044, "paint_od", re=0.0)
    # ---- cuerpo: gancho de la palanca, nudillo central y pasador con cabeza
    xc0 = Lb / 2 - 0.001
    side(mb, [(xc0, zl0 - 0.052), (xl + 0.0035, zl0 - 0.050), (xl + 0.0045, zl0 - 0.036), (xc0, zl0 - 0.030)], 0.0, 0.024,
         "paint_od", re=0.0)
    wk = 0.034 if big else 0.024
    side(mb, [(-Lb / 2 + 0.001, zl0 - 0.022), (hx + 0.0005, hz - 0.0035), (hx + 0.0005, hz + 0.0035),
              (-Lb / 2 + 0.001, hz + 0.0035)], 0.0, wk - 0.0006, "paint_od", re=0.0)
    revolve(mb, [(0.0042, -wk / 2), (0.0042, wk / 2)], "paint_od", seg=SEG_T, M=_T(hx, 0, hz) @ _Rx(90))
    hl = yk + wkl / 2 + 0.0025
    revolve(mb, [(0.0027, -hl), (0.0027, -hl + 0.0016), (0.0018, -hl + 0.0016), (0.0018, hl)], "steel", seg=SEG_T,
            M=_T(hx, 0, hz) @ _Rx(90))
    if open:
        lid.transform(_T(hx, 0, hz) @ _Ry(-105) @ _T(-hx, 0, -hz))
    mb.join(lid)
    # ---- estarcidos (costado -Y)
    yf = -Wb / 2
    stencil(mb, "AMMO", 0.034 if big else 0.028, _T(0, yf, zl0 * 0.55) @ _Rx(90), "paint_yellow")
    if not open:
        lot = ("LOT 27-05", "LOT 22-09", "LOT 31-02")[int(r.integers(0, 3))]
        stencil(mb, lot, 0.011, _T(0, yf, zl0 * 0.55 - 0.020) @ _Rx(90), "paint_yellow")
    return mb


# ======================================================================================================== caja de cartón
def cardboard_ammo_box(seed=0):
    """Caja de cartón de 20 cartuchos de fusil (~ 112 × 72 × 45 mm, cajas comerciales de 5,56 de 20 tiros): cuerpo de
    cartón con aristas suaves y ligeramente abombadas, solapa de cierre metida en un extremo con su pestaña, línea de
    doblez y etiqueta «20 CTG RIFLE». Origen: centro de la base; largo en X.
    Fuente de proporción: listados de cajas de 50 / 20 tiros (ar15discounts.com, planooutdoors.com)."""
    r = rng(seed)
    mb = MB()
    L, W, H = 0.112, 0.072, 0.045
    s = 1.0 + float(r.uniform(-0.02, 0.02))
    slab(mb, Matrix(), L * s, W, H, rc=0.0025, re=0.0018, re0=0.0016, mat="cardboard", nc=3, ne=2)
    # solapa del extremo +X: tapa doblada con su pestaña metida (leve abombado)
    side(mb, [(L * s / 2 - 0.0006, 0.002), (L * s / 2 + 0.0014, 0.0025), (L * s / 2 + 0.0016, H - 0.0035),
              (L * s / 2 - 0.0006, H - 0.002)], [0.0, 0.0008, 0.0008, 0.0], W - 0.004, "cardboard", re=0.0004, n=1, ne=1)
    # pestaña de la tapa superior que dobla sobre el extremo (cara superior)
    plan(mb, [(L * s / 2 - 0.022, -W / 2 + 0.003), (L * s / 2 - 0.0008, -W / 2 + 0.003), (L * s / 2 - 0.0008, W / 2 - 0.003),
              (L * s / 2 - 0.022, W / 2 - 0.003)], [0.0, 0.0006, 0.0006, 0.0], 0.0009, "cardboard", z0=H - 0.0004, re=0.0003, n=1,
         ne=1)
    # etiqueta en la tapa
    plan(mb, [(-0.045, -0.026), (0.03, -0.026), (0.03, 0.026), (-0.045, 0.026)], 0.003, 0.0007, "sign_white", z0=H - 0.0003,
         re=0.0)
    stencil(mb, "20 CTG", 0.011, _T(-0.0075, 0.004, H + 0.0004), "cable", depth=0.0003)
    stencil(mb, "RIFLE", 0.008, _T(-0.0075, -0.012, H + 0.0004), "cable", depth=0.0003)
    return mb


# ======================================================================================================== cajas de madera
CRATE_DIMS = {"wood": (0.66, 0.36, 0.30), "long": (1.65, 0.42, 0.27), "small": (0.46, 0.30, 0.24)}


def _rope_handle(mb, x, zc, sx, hw=0.05):
    """Asa de cuerda (Ø 12 mm) que sale de dos barrenos del travesaño del extremo y cuelga en U."""
    pts = [(x - sx * 0.010, -hw, zc), (x + sx * 0.007, -hw - 0.003, zc - 0.008), (x + sx * 0.014, -hw + 0.008, zc - 0.040),
           (x + sx * 0.017, 0.0, zc - 0.054), (x + sx * 0.014, hw - 0.008, zc - 0.040), (x + sx * 0.007, hw + 0.003, zc - 0.008),
           (x - sx * 0.010, hw, zc)]
    pts = [pts[0], pts[1], pts[2], pts[3], pts[4], pts[5], pts[6]]
    path = spline([pts[0], pts[1], pts[2], pts[3], pts[4], pts[5], pts[6]], 1)
    path = [path[0]] + spline(path[1:-1], 2) + [path[-1]]
    mb.tube(path, 0.006, seg=SEG_T, mat="fabric", caps=False)


def _bail_handle(mb, x, zc, sx, hw=0.05):
    """Asa abatible de varilla Ø 11 mm con placa base remachada y dos orejas (cajas de madera de armas / cohetes)."""
    M = _T(x, 0, zc) @ _Rz(0 if sx > 0 else 180) @ _Ry(90)    # Z local hacia fuera del extremo, X local hacia -Z mundial
    plan(mb, [(-0.022, -hw - 0.016), (0.022, -hw - 0.016), (0.022, hw + 0.016), (-0.022, hw + 0.016)], 0.0, 0.003, "steel",
         z0=-0.0005, re=0.0, M=M)
    for y in (-hw, hw):
        side(mb, [(-0.010, 0.0), (0.006, 0.0), (0.004, 0.012), (-0.004, 0.012)], [0.0, 0.0, 0.003, 0.003], 0.004, "steel",
             y0=y, re=0.0, n=2, M=M @ _T(0, 0, 0.002) @ _Rx(90) @ _Rx(-90))
        rivet(mb, M @ _T(0.014, y * 1.22, 0.0025), d=0.007)
    a = math.radians(12.0)
    dz, dx = math.cos(a), math.sin(a)          # la asa cuelga casi pegada al extremo
    path = fillet([(-0.002, -hw, 0.009), (0.045 * dz, -hw, 0.009 + 0.045 * dx), (0.045 * dz, hw, 0.009 + 0.045 * dx),
                   (-0.002, hw, 0.009)], 0.012, 1)
    mb.tube([tuple(M @ Vector(p)) for p in path], 0.0055, seg=SEG_T, mat="steel", caps=False)


def _crate(L, D, H, kind, seed=0, open=False, stencils=True, contents=True):
    r = rng(seed)
    mb = MB()
    tb = 0.016 if kind == "small" else 0.019
    hr = 0.022                                  # patines inferiores
    z0, zt = hr, H - 2 * tb                     # paredes de z0 a zt; tapa zt..zt+tb; listones de tapa hasta H
    g = 0.0015                                  # junta entre tablas
    W = "wood_od"
    nb = 2 if (zt - z0) < 0.26 else 3
    bh = ((zt - z0) - (nb - 1) * g) / nb
    for sy in (-1, 1):                          # costados largos (frente -Y / espalda +Y)
        y0, y1 = (-D / 2, -D / 2 + tb) if sy < 0 else (D / 2 - tb, D / 2)
        for k in range(nb):
            za = z0 + k * (bh + g)
            plank(mb, (-L / 2, y0, za), (L / 2, y1, za + bh), W)
    for sx in (-1, 1):                          # extremos
        x0, x1 = (-L / 2, -L / 2 + tb) if sx < 0 else (L / 2 - tb, L / 2)
        for k in range(nb):
            za = z0 + k * (bh + g)
            plank(mb, (x0, -D / 2 + tb, za), (x1, D / 2 - tb, za + bh), W)
    mb.box((-L / 2 + tb, -D / 2 + tb, z0), (L / 2 - tb, D / 2 - tb, z0 + tb), W, bevel=0.0)        # fondo
    nr = 3 if L > 1.0 else 2
    for i in range(nr):                         # patines bajo el fondo
        x = -L / 2 + 0.07 + (L - 0.14) * i / (nr - 1) - 0.035
        plank(mb, (x, -D / 2, 0.0), (x + 0.07, D / 2, z0 + 0.0005), W)
    xc = L / 2 - 0.058                          # postes de esquina en los costados largos
    for sx in (-1, 1):
        for sy in (-1, 1):
            xa, xb_ = sorted((sx * xc, sx * L / 2))
            ya, yb = sorted((sy * (D / 2 - 0.0005), sy * (D / 2 + tb)))
            plank(mb, (xa, ya, z0), (xb_, yb, zt), W)
    zc = z0 + (zt - z0) * 0.58                  # travesaño de la asa en cada extremo (entre los postes de esquina)
    for sx in (-1, 1):
        xa2, xb2 = sorted((sx * (L / 2 - 0.0005), sx * (L / 2 + tb - 0.003)))
        plank(mb, (xa2, -D / 2 - tb + 0.002, zc - 0.045), (xb2, D / 2 + tb - 0.002, zc + 0.045), W)
    # tapa: tablas a lo largo de X y listones transversales; bisagras atrás (+Y), pasadores al frente (-Y)
    lid = MB()
    nl = 3
    lw = (D - (nl - 1) * g) / nl
    for k in range(nl):
        ya = -D / 2 + k * (lw + g)
        plank(lid, (-L / 2, ya, zt), (L / 2, ya + lw, zt + tb), W)
    nbat = 3 if L > 1.0 else 2
    for i in range(nbat):
        x = -L / 2 + 0.035 + (L - 0.07 - 0.06) * i / (nbat - 1)
        plank(lid, (x, -D / 2, zt + tb - 0.0005), (x + 0.06, D / 2, H), W)
    xh = [-L / 2 + 0.17, L / 2 - 0.17] if L > 0.5 else [-L / 2 + 0.12, L / 2 - 0.12]
    yk, zk = D / 2 + 0.0035, zt
    for x in xh:                                # bisagras de fleje remachadas
        plan(lid, [(x - 0.016, D / 2 - 0.11), (x + 0.016, D / 2 - 0.11), (x + 0.016, D / 2 + 0.001), (x - 0.016, D / 2 + 0.001)],
             [0.006, 0.006, 0.0, 0.0], 0.002, "steel", z0=zt + tb - 0.0003, re=0.0, n=2)
        side(mb, [(x - 0.016, zt - 0.10), (x + 0.016, zt - 0.10), (x + 0.016, zt - 0.003), (x - 0.016, zt - 0.003)],
             [0.006, 0.006, 0.0, 0.0], 0.002, "steel", y0=D / 2 + 0.0007, re=0.0, n=2)
        revolve(lid, [(0.0042, -0.0155), (0.0042, 0.0155)], "steel", seg=SEG_T, M=_T(x, yk, zk) @ _Ry(90))
        side(lid, [(x - 0.016, zt - 0.0005), (x + 0.016, zt - 0.0005), (x + 0.016, zt + tb + 0.0011), (x - 0.016, zt + tb + 0.0011)],
             0.0, 0.0022, "steel", y0=D / 2 + 0.0009, re=0.0)
        rivet(mb, _T(x, D / 2 + 0.0017, zt - 0.06) @ _Rx(-90), d=0.007)
        rivet(lid, _T(x, D / 2 - 0.07, zt + tb + 0.0017), d=0.007)
    for x in xh:                                # pasadores: hasp ranurado colgado de un nudillo + grapa en la pared
        side(lid, [(x - 0.018, zt + 0.003), (x + 0.018, zt + 0.003), (x + 0.018, zt + tb - 0.003), (x - 0.018, zt + tb - 0.003)],
             0.0, 0.0025, "steel", y0=-D / 2 - 0.0009, re=0.0)
        revolve(lid, [(0.0038, -0.014), (0.0038, 0.014)], "steel", seg=SEG_T, M=_T(x, -D / 2 - 0.0042, zt + 0.003) @ _Ry(90))
        hasp = [(x - 0.013, zt + 0.003), (x - 0.013, zt - 0.072), (x - 0.0045, zt - 0.072), (x - 0.0045, zt - 0.050),
                (x + 0.0045, zt - 0.050), (x + 0.0045, zt - 0.072), (x + 0.013, zt - 0.072), (x + 0.013, zt + 0.003)]
        side(lid, hasp, [0.0, 0.002, 0.0, 0.0, 0.0, 0.0, 0.002, 0.0], 0.0024, "steel", y0=-D / 2 - 0.0045, re=0.0, n=2)
        side(mb, [(x - 0.016, zt - 0.088), (x + 0.016, zt - 0.088), (x + 0.016, zt - 0.040), (x - 0.016, zt - 0.040)],
             0.0, 0.002, "steel", y0=-D / 2 - 0.0007, re=0.0)
        mb.tube([(x - 0.0035, -D / 2 + 0.0005, zt - 0.061), (x - 0.0035, -D / 2 - 0.011, zt - 0.061),
                 (x + 0.0035, -D / 2 - 0.011, zt - 0.061), (x + 0.0035, -D / 2 + 0.0005, zt - 0.061)], 0.0022, seg=SEG_T,
                mat="steel", caps=False)
    if open:
        lid.transform(_T(0, yk, zk) @ _Rx(-102) @ _T(0, -yk, -zk))
    mb.join(lid)
    for sx in (-1, 1):                          # asas en los extremos
        xf = sx * (L / 2 + tb - 0.004)
        if kind == "wood":
            _rope_handle(mb, xf, zc, sx)
        else:
            _bail_handle(mb, xf, zc + 0.012, sx)
    if stencils:
        h = 0.07 if kind == "long" else (0.055 if kind == "wood" else 0.045)
        yf = -D / 2 - 0.0002
        zs = z0 + (zt - z0) * 0.5
        stencil(mb, "AMMO", h, _T(0.0, yf, zs - h * 0.15) @ _Rx(90), "paint_yellow")
        if not open:
            lot = ("LOT 2705", "LOT 2209", "LOT 3102", "LOT 0926")[int(r.integers(0, 4))]
            stencil(mb, lot, 0.017, _T(0.0, yf, zs - h * 0.15 - 0.028) @ _Rx(90), "paint_yellow")
    if open and contents:
        if kind == "long":                       # cunas de madera para el tubo
            for x in (-L / 2 + 0.25, L / 2 - 0.25):
                y0, y1, zz = -D / 2 + tb + 0.002, D / 2 - tb - 0.002, z0 + tb - 0.001
                prof = [(y0, zz), (y1, zz), (y1, z0 + 0.12)]
                prof += [(0.065 * math.cos(a), z0 + 0.13 + 0.065 * math.sin(a)) for a in [-PI * k / 10 for k in range(11)]]
                prof += [(y0, z0 + 0.12)]
                side(mb, prof, 0.0, 0.05, "wood_od", re=0.0, M=_T(x, 0, 0) @ _Rz(90))
        else:                                    # cajas de cartón de munición
            bw, bd, bh2 = 0.112, 0.072, 0.045
            for i in range(3):
                for j in range(2):
                    x = -0.13 + i * 0.13
                    y = -0.045 + j * 0.09
                    slab2(mb, _T(x, y, z0 + tb - 0.0005) @ _Rz(float(r.uniform(-2.5, 2.5))), bw, bd, bh2, 0.002, "cardboard",
                          re_t=0.0015, ne_t=1, nc=1)
    return mb


def ammo_crate(kind="wood", seed=0, open=False):
    """Caja de munición de madera pintada verde olivo (genérica). kind: «wood» 0,66 × 0,36 × 0,30 m (cartuchería / granadas,
    asas de cuerda), «long» 1,65 × 0,42 × 0,27 m (cohetes / armas, asas abatibles de varilla), «small» 0,46 × 0,30 × 0,24 m
    (asas abatibles). Construcción: tablas de 19 mm (16 mm en «small») con juntas y cantos chaflanados, postes de esquina,
    marcos de extremo con travesaño de asa, fondo con patines, tapa de 3 tablas con listones transversales, 2 bisagras de
    fleje remachadas atrás, 2 pasadores ranurados con grapa al frente, estarcidos amarillos. open=True: tapa girada 102° sobre
    las bisagras y contenido (cajas de cartón; cunas para tubo en «long»).
    Origen: centro de la base (z = 0 bajo los patines); largo en X, frente (estarcidos, pasadores) hacia -Y.
    Fuentes: everyspec.com/MIL-SPECS/MIL-SPECS-MIL-S/MIL-S-23389B_14382 (familia de cajas de munición); varusteleka.com
    (caja de 40 mm de madera); referencia visual MIL_mat.png (poste de esquina, asa de acero, tablas)."""
    L, D, H = CRATE_DIMS.get(kind, CRATE_DIMS["wood"])
    return _crate(L, D, H, kind, seed=seed, open=open)


# ======================================================================================================== tarimas
def holed_board(mb, M, nx, ny, px, py, r, t, mat="wood_od", n=24, ch=0.003):
    """Tablero de nx × ny celdas (paso px × py) con un barreno redondo de radio r por celda, de z = 0 a t (cara vista +Z).
    Malla soldada (vértices compartidos entre celdas), paredes de barreno, canto perimetral chaflanado ch arriba."""
    V = {}

    def vert(x, y, z):
        k = (round(x, 7), round(y, 7), round(z, 7))
        if k not in V:
            p = Vector((x, y, z))
            V[k] = mb.bm.verts.new((M @ p) if M is not None else p)
        return V[k]
    X0, Y0 = -nx * px / 2, -ny * py / 2
    X1, Y1 = -X0, -Y0

    def edge_pt(cx, cy, a):
        c, s = math.cos(a), math.sin(a)
        tt = min(px / 2 / abs(c) if abs(c) > 1e-9 else 1e9, py / 2 / abs(s) if abs(s) > 1e-9 else 1e9)
        x, y = cx + c * tt, cy + s * tt
        if abs(x - X0) < 1e-6 or abs(x - X1) < 1e-6 or abs(y - Y0) < 1e-6 or abs(y - Y1) < 1e-6:
            return x, y, True
        return x, y, False
    for i in range(nx):
        for j in range(ny):
            cx, cy = X0 + px * (i + 0.5), Y0 + py * (j + 0.5)
            angs = [2 * PI * k / n for k in range(n)]
            sq = [edge_pt(cx, cy, a) for a in angs]
            # insertar las esquinas del cuadrado entre los rayos
            ring, onb = [], []
            for k in range(n):
                a0, a1 = angs[k], angs[(k + 1) % n] + (2 * PI if k == n - 1 else 0.0)
                ring.append(("r", k))
            for k in range(n):
                kk = (k + 1) % n
                xa, ya, ba = sq[k]
                xb, yb, bb = sq[kk]
                ca, sa = math.cos(angs[k]), math.sin(angs[k])
                cb, sb = math.cos(angs[kk]), math.sin(angs[kk])
                ha, hb = (cx + r * ca, cy + r * sa), (cx + r * cb, cy + r * sb)
                # cara superior / inferior: el tramo de borde puede doblar una esquina del cuadrado
                corner = None
                if abs(xa - xb) > 1e-7 and abs(ya - yb) > 1e-7:
                    corner = (xb if abs(abs(xb - cx) - px / 2) < 1e-6 else xa, yb if abs(abs(yb - cy) - py / 2) < 1e-6 else ya)
                for z, flip in ((t, False), (0.0, True)):
                    pts = [vert(xa, ya, z)] + ([vert(corner[0], corner[1], z)] if corner else []) + [vert(xb, yb, z),
                                                                                                   vert(hb[0], hb[1], z),
                                                                                                   vert(ha[0], ha[1], z)]
                    mb.face(list(reversed(pts)) if not flip else pts, mat)
                mb.face([vert(ha[0], ha[1], t), vert(hb[0], hb[1], t), vert(hb[0], hb[1], 0.0), vert(ha[0], ha[1], 0.0)], mat)
                # paredes del perímetro
                segs = [(xa, ya), corner, (xb, yb)] if corner else [(xa, ya), (xb, yb)]
                for (p, q) in zip(segs[:-1], segs[1:]):
                    mx_, my_ = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
                    if abs(mx_ - X0) < 1e-6 or abs(mx_ - X1) < 1e-6 or abs(my_ - Y0) < 1e-6 or abs(my_ - Y1) < 1e-6:
                        mb.face([vert(p[0], p[1], 0.0), vert(q[0], q[1], 0.0), vert(q[0], q[1], t), vert(p[0], p[1], t)], mat)


def pallet_gma(mb, M=None, mat="wood_od"):
    """Tarima de largueros 48 × 40 in (1219 × 1016 mm, ~ 135 mm de alto): 3 largueros de 38 × 100 mm a lo largo de X con
    dos muescas de entrada parcial a 4 vías, 7 tablas de cubierta superior (las de orilla más anchas) y 5 inferiores.
    Origen: centro en el piso. Fuentes: interlakemecalux.com/blog/gma-pallet ; mecalux.com/blog/american-pallet."""
    Mx = M if M is not None else Matrix()
    Lx, Ly = 1.219, 1.016
    tb, tt, hs = 0.016, 0.019, 0.100
    sub = MB()
    for k in range(5):                                     # tablas inferiores
        w = 0.14 if k in (0, 4) else 0.089
        x = -Lx / 2 + w / 2 + (Lx - w) * k / 4 if k in (0, 4) else -0.30 + 0.30 * (k - 1)
        plank(sub, (x - w / 2, -Ly / 2, 0.0), (x + w / 2, Ly / 2, tb), mat)
    for y in (-Ly / 2 + 0.019, 0.0, Ly / 2 - 0.019):        # largueros con muescas
        P = [(-Lx / 2, tb - 0.0005), (-0.43, tb - 0.0005), (-0.43, tb + 0.038), (-0.20, tb + 0.038), (-0.20, tb - 0.0005),
             (0.20, tb - 0.0005), (0.20, tb + 0.038), (0.43, tb + 0.038), (0.43, tb - 0.0005), (Lx / 2, tb - 0.0005),
             (Lx / 2, tb + hs + 0.0005), (-Lx / 2, tb + hs + 0.0005)]
        R = [0.0, 0.0, 0.012, 0.012, 0.0, 0.0, 0.012, 0.012, 0.0, 0.0, 0.0, 0.0]
        side(sub, P, R, 0.038, mat, y0=y, re=0.003, n=3, ne=1)
    xs = [-Lx / 2 + 0.07] + [-0.385 + 0.1925 * k for k in range(5)] + [Lx / 2 - 0.07]
    for k, x in enumerate(xs):                              # cubierta superior
        w = 0.14 if k in (0, 6) else 0.089
        plank(sub, (x - w / 2, -Ly / 2, tb + hs), (x + w / 2, Ly / 2, tb + hs + tt), mat)
    mb.join(sub, Mx)
    return tb + hs + tt


def _projectile(mb, M, seg=SEG):
    """Proyectil de artillería clase 155 mm (genérico) de pie sobre z = 0 local: culote con cola de bote, banda de
    conducción de latón, cuerpo, ojiva secante y tapón de izaje con argolla (~ 0,80 m)."""
    R = 0.0775
    prof = [(0.0, 0.0), (0.060, 0.0), (0.064, 0.004), (0.0745, 0.052), (R, 0.064), (R, 0.086)]
    prof += [(R, 0.126), (R, 0.14), (R, 0.415), (R, 0.43)]
    zo0, zo1, rn = 0.43, 0.755, 0.027
    for k in range(1, 8):                                    # ojiva secante
        u = k / 7
        rr = rn + (R - rn) * math.cos(u * PI / 2) ** 1.25
        prof.append((rr, zo0 + (zo1 - zo0) * math.sin(u * PI / 2) ** 0.9))
    prof += [(0.0, zo1)]
    mats = ["paint_od"] * (len(prof) - 1)
    revolve(mb, prof, mats, seg=seg, M=M)
    revolve(mb, [(R - 0.001, 0.084), (R + 0.0012, 0.088), (R + 0.0012, 0.122), (R - 0.001, 0.126)], "brass", seg=seg, M=M,
            caps=False)
    # tapón de izaje: cuerpo roscado con collarín y argolla
    revolve(mb, [(0.0262, zo1 - 0.003), (0.0262, zo1 + 0.012), (0.024, zo1 + 0.016), (0.012, zo1 + 0.018), (0.0, zo1 + 0.018)],
            "steel", seg=seg, M=M, caps=False)
    ring = [(0.004, -0.0045), (0.011, -0.0045), (0.0135, -0.002), (0.0135, 0.002), (0.011, 0.0045), (0.004, 0.0045)]
    revolve(mb, [(rr_ + 0.0, z) for (rr_, z) in ring], "steel", seg=16, M=M @ _T(0, 0, zo1 + 0.016 + 0.0135) @ _Rx(90),
            closed=True)


def shell_pallet(seed=0):
    """Tarima de 8 proyectiles de artillería clase 155 mm (2 × 4, de pie, ~ 0,80 m con tapón de izaje) como se embarcan:
    base de madera (2 patines, cubierta y tablero con 8 cunas), marco superior de madera con 8 barrenos que abraza las ojivas,
    4 tirantes roscados de esquina con tuercas, 2 flejes de acero longitudinales con sellos y un fleje horizontal que ciñe
    los cuerpos. Proyectil: culote con cola de bote, banda de latón, cuerpo pintado verde olivo, ojiva y tapón de izaje
    con argolla. Huella 765 × 360 mm. Origen: centro en el piso; largo en X.
    Fuentes: msm.sk/en/produkt/155-mm-he-m107-en (tarima de 8 proyectiles 765 × 360 mm); gd-ots.com 155mm-M107-HE_US.pdf
    (tarima de madera de 8, tapón de izaje roscado); constructionloader.tpub.com/TM-55-607 (8 proyectiles por tarima,
    unitizados con fleje de acero)."""
    r = rng(seed)
    mb = MB()
    px, py = 0.19, 0.18
    Lx, Ly = 4 * px, 2 * py
    W = "wood_od"
    hs, td, tbd = 0.075, 0.019, 0.040
    for y in (-0.12, 0.12):                                  # patines
        plank(mb, (-Lx / 2, y - 0.045, 0.0), (Lx / 2, y + 0.045, hs + 0.0005), W)
    for k in range(5):                                       # cubierta
        x = -Lx / 2 + 0.06 + (Lx - 0.12) * k / 4
        plank(mb, (x - 0.06, -Ly / 2, hs), (x + 0.06, Ly / 2, hs + td), W)
    zb = hs + td
    holed_board(mb, _T(0, 0, zb - 0.0005), 4, 2, px, py, 0.0705, tbd, W, n=SEG)
    zp = zb - 0.0003                                         # el culote se asienta en la cubierta, dentro de la cuna
    for i in range(4):
        for j in range(2):
            x, y = -Lx / 2 + px * (i + 0.5), -Ly / 2 + py * (j + 0.5)
            _projectile(mb, _T(x, y, zp) @ _Rz(float(r.uniform(0, 360))))
    # marco superior: tablero con barrenos que abraza la ojiva donde su radio es ~ 46 mm
    zf = zp + 0.43 + (0.755 - 0.43) * 0.62
    holed_board(mb, _T(0, 0, zf), 4, 2, px, py, 0.0485, 0.032, W, n=SEG)
    ztop = zf + 0.032
    # tirantes de esquina: varilla roscada de 16 mm que atraviesa el tablero de cunas y el marco superior, con tuercas
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (Lx / 2 - 0.016), sy * (Ly / 2 - 0.016)
            revolve(mb, [(0.008, zb + 0.002), (0.008, ztop + 0.028)], "steel", seg=SEG_T, M=_T(x, y, 0))
            for z in (zb - 0.0005 + tbd, ztop):
                hexnut(mb, _T(x, y, z - 0.0003), s=0.024, h=0.014)
    # flejes longitudinales (plano XZ, y = 0): sobre el marco superior y bajo la cubierta, entre patines
    for yy in (0.0,):
        xe = Lx / 2 + 0.0255
        path = fillet([(-xe, yy, hs - 0.0004), (xe, yy, hs - 0.0004), (xe, yy, ztop + 0.0004), (-xe, yy, ztop + 0.0004)], 0.008, 3)
        mb.sweep([(-0.0004, -0.0095), (0.0004, -0.0095), (0.0004, 0.0095), (-0.0004, 0.0095)], path, mat="steel",
                 closed_path=True, normal=(0, 1, 0))
        plan(mb, [(-0.035, -0.0115), (0.035, -0.0115), (0.035, 0.0115), (-0.035, 0.0115)], 0.0, 0.0022, "steel",
             z0=ztop + 0.0006, re=0.0, M=_T(0.10, yy, 0))
    # fleje horizontal que ciñe los 8 cuerpos
    zh = zp + 0.30
    loop = [(x, y, zh) for (x, y) in rr_pts(Lx - 2 * px / 2 + 2 * 0.0775 + 0.0016 - 0.0, 2 * 0.0775 + py + 0.0016, 0.0783, 6)]
    loop = [(x, y, z) for (x, y, z) in loop]
    mb.sweep([(-0.0004, -0.0095), (0.0004, -0.0095), (0.0004, 0.0095), (-0.0004, 0.0095)], loop, mat="steel", closed_path=True,
             normal=(0, 0, 1))
    plan(mb, [(-0.0115, -0.035), (0.0115, -0.035), (0.0115, 0.035), (-0.0115, 0.035)], 0.0, 0.0022, "steel", re=0.0,
         M=_T(Lx / 2 - px / 2 + 0.0775 + 0.0009, 0.0, zh) @ _Ry(90) @ _Rz(90) @ _T(0, 0, 0))
    stencil(mb, "LOT 2705", 0.022, _T(0.0, -Ly / 2, zb + 0.008) @ _Rx(90), "paint_yellow")
    return mb


def crate_pallet(n=6, kind="wood", seed=0, straps=None):
    """Cajas de munición de madera (ammo_crate «wood» o «small») estibadas en una tarima de 48 × 40 in y amarradas:
    flejes de acero con sello engargolado (straps="steel") o cinchos de matraca de lona con su matraca (straps="ratchet";
    por omisión según la semilla), con esquineros de cartón en las aristas superiores. n cajas (capas de 3 «wood» girada
    90° o de 6 «small»). Origen: centro de la tarima en el piso; largo de la tarima (48 in) en X.
    Fuentes: interlakemecalux.com/blog/gma-pallet (48 × 40 in); referencia visual MIL_interior.png (estibas flejadas)."""
    r = rng(seed)
    mb = MB()
    zp = pallet_gma(mb)
    kind = kind if kind in ("wood", "small") else "wood"
    L, D, H = CRATE_DIMS[kind]
    if kind == "wood":                     # 3 por capa, girada 90°: largo de la caja a lo largo de Y
        slots = [(-0.41, 0.0, 90.0), (0.0, 0.0, 90.0), (0.41, 0.0, 90.0)]
        ys = 0.22                          # fleje entre bisagra y poste de esquina
        xe = 0.41 + D / 2
    else:                                  # 6 por capa: 2 × 3, largo a lo largo de X
        slots = [(sx * 0.29, (j - 1) * 0.335, 0.0) for sx in (-1, 1) for j in range(3)]
        ys = 0.0
        xe = 0.29 + L / 2
    per = len(slots)
    nl = max(1, -(-n // per))
    crate_src = {}
    k = 0
    for layer in range(nl):
        for (x, y, rz) in slots:
            if k >= n:
                break
            sd = int(r.integers(0, 4))
            if sd not in crate_src:
                crate_src[sd] = _crate(L, D, H, kind, seed=sd)
            mb.join(crate_src[sd], _T(x, y, zp + layer * H) @ _Rz(rz + (180.0 if r.random() < 0.5 else 0.0)))
            k += 1
    ztop = zp + nl * H
    full_top = n >= per * nl
    if not full_top:
        ztop = zp + (nl - 1) * H if nl > 1 else ztop
    # amarres: lazos en el plano XZ que pasan bajo la cubierta superior (entre largueros) y sobre la carga
    kind_s = straps or ("steel" if seed % 2 == 0 else "ratchet")
    zu = zp - 0.019 - 0.0006
    ztt = ztop - (0.019 if kind == "wood" else 0.0)       # sobre la tapa (junto a los listones)
    xo = max(xe, 0.6095) + 0.0012
    for yy in ((-ys, ys) if ys else (-0.22, 0.22)):
        if kind_s == "steel":
            w, t = 0.019, 0.0008
            mat = "steel"
        else:
            w, t = 0.05, 0.0018
            mat = "canvas"
        path = fillet([(-0.6095 - t, yy, zu), (0.6095 + t, yy, zu), (0.6095 + t, yy, zp + 0.004), (xo + 0.004, yy, zp + 0.03),
                       (xo + 0.004, yy, ztt + 0.0033 + t / 2), (-xo - 0.004, yy, ztt + 0.0033 + t / 2), (-xo - 0.004, yy, zp + 0.03),
                       (-0.6095 - t, yy, zp + 0.004)], 0.01, 3)
        mb.sweep([(-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)], path, mat=mat, closed_path=True,
                 normal=(0, 1, 0))
        for sx in (-1, 1):                 # esquineros de cartón en las aristas superiores
            x0 = sx * (xo - 0.0005)
            xa, xb = sorted((x0, x0 - sx * 0.05))
            plank(mb, (xa, yy - 0.04, ztt - 0.0002), (xb, yy + 0.04, ztt + 0.0035), "cardboard", ch=0.001)
            xa, xb = sorted((x0 - sx * 0.0005, x0 + sx * 0.0035))
            plank(mb, (xa, yy - 0.04, ztt - 0.05), (xb, yy + 0.04, ztt + 0.0035), "cardboard", ch=0.001)
        if kind_s == "steel":              # sello engargolado
            xl = float(r.uniform(-0.2, 0.2))
            plan(mb, [(xl - 0.032, yy - 0.012), (xl + 0.032, yy - 0.012), (xl + 0.032, yy + 0.012), (xl - 0.032, yy + 0.012)], 0.0,
                 0.0026, "steel", z0=ztt + 0.0035, re=0.0)
            for dx in (-0.016, 0.0, 0.016):
                plan(mb, [(xl + dx - 0.004, yy - 0.012), (xl + dx + 0.004, yy - 0.012), (xl + dx + 0.004, yy + 0.012),
                          (xl + dx - 0.004, yy + 0.012)], 0.0, 0.0012, "steel", z0=ztt + 0.0057, re=0.0)
        else:                              # matraca en el costado +X: placas laterales, carrete, palanca con mango de hule
            xs, zr = xo + 0.004 + t / 2 - 0.0004, zp + 0.24
            for sy in (-1, 1):
                side(mb, [(xs, zr - 0.06), (xs + 0.012, zr - 0.06), (xs + 0.028, zr - 0.02), (xs + 0.028, zr + 0.045),
                          (xs + 0.010, zr + 0.056), (xs, zr + 0.056)], [0.0, 0.006, 0.008, 0.008, 0.006, 0.0], 0.003, "steel",
                     y0=yy + sy * 0.0295, re=0.0, n=2)
            revolve(mb, [(0.011, -0.0335), (0.011, 0.0335)], "steel", seg=SEG, M=_T(xs + 0.015, yy, zr) @ _Rx(90))
            side(mb, [(xs + 0.026, zr - 0.105), (xs + 0.034, zr - 0.105), (xs + 0.038, zr + 0.012), (xs + 0.026, zr + 0.012)],
                 [0.003, 0.003, 0.003, 0.0], 0.050, "steel", y0=yy, re=0.0012, n=2, ne=1)
            slab2(mb, _T(xs + 0.034, yy, zr - 0.095) @ _Ry(90), 0.03, 0.056, 0.008, 0.004, "rubber", re_t=0.003, ne_t=2)
    return mb


# ======================================================================================================== armas: piezas
def rail(mb, x0, x1, z, mat="gunmetal", M=None, y=0.0):
    """Riel tipo MIL-STD-1913 a lo largo de X sobre el plano z (base embebida 1 mm): cabeza de 21,2 mm con flancos a 45°,
    cuello de 15,6 mm y ranuras transversales de 5,23 mm a paso de 10,01 mm (3 mm de profundidad)."""
    base = [(-0.0078, -0.001), (0.0078, -0.001), (0.0078, 0.0025), (0.0106, 0.0053), (0.0106, 0.0065), (-0.0106, 0.0065),
            (-0.0106, 0.0053), (-0.0078, 0.0025)]
    Mx = (M if M is not None else Matrix()) @ _T(0, y, z)
    loft_rings(mb, [[Vector((x, py, pz)) for (py, pz) in base] for x in (x0, x1)], mat, M=Mx)
    tooth = [(-0.0104, 0.0063), (0.0104, 0.0063), (0.0084, 0.0095), (-0.0084, 0.0095)]
    pitch, tl = 0.01001, 0.00478
    n = int((x1 - x0 - 0.002) // pitch)
    off = x0 + (x1 - x0 - (n - 1) * pitch - tl) / 2
    for k in range(n):
        xa = off + k * pitch
        loft_rings(mb, [[Vector((x, py, pz)) for (py, pz) in tooth] for x in (xa, xa + tl)], mat, M=Mx)


def _hg_ring(w, h, r, n, band):
    """Contorno (y, z) antihorario del guardamanos: rectángulo redondeado con cortes en los costados y abajo (ranuras)."""
    cut = band > 0
    pts = [(-w / 2 + r, -h / 2)] + ([(-band, -h / 2), (band, -h / 2)] if cut else [])
    arc = lambda cy, cz, a0: [(cy + r * math.cos(a0 + PI / 2 * k / n), cz + r * math.sin(a0 + PI / 2 * k / n)) for k in range(n + 1)]  # noqa
    pts += arc(w / 2 - r, -h / 2 + r, -PI / 2)
    pts += [(w / 2, -band), (w / 2, band)] if cut else []
    pts += arc(w / 2 - r, h / 2 - r, 0.0)
    pts += arc(-w / 2 + r, h / 2 - r, PI / 2)
    pts += [(-w / 2, band), (-w / 2, -band)] if cut else []
    pts += arc(-w / 2 + r, -h / 2 + r, PI)[:-1]
    m = len(pts)
    tags = []
    for j in range(m):
        a, b = pts[j], pts[(j + 1) % m]
        my, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        tags.append(cut and ((abs(mz + h / 2) < 1e-7 and abs(my) < band) or (abs(abs(my) - w / 2) < 1e-7 and abs(mz) < band)))
    return pts, tags


def slotted_tube(mb, x0, x1, w, h, r, t, zc, slots, band=0.0035, n=4, mat="gunmetal"):
    """Guardamanos flotante de aluminio: tubo de sección rectangular redondeada (pared t) a lo largo de X con ranuras
    pasantes de 2·band de alto en ambos costados y abajo, en los tramos `slots` [(xa, xb)]. Sólido cerrado y soldado
    (las paredes de cada ranura se ven por dentro)."""
    po, tags = _hg_ring(w, h, r, n, band)
    pi, _ = _hg_ring(w - 2 * t, h - 2 * t, r - t, n, band)
    xs = [x0]
    sl = []
    for (a, b) in slots:
        xs += [a, b]
    xs.append(x1)
    for i in range(len(xs) - 1):
        sl.append(any(abs(xs[i] - a) < 1e-9 and abs(xs[i + 1] - b) < 1e-9 for (a, b) in slots))
    O = [[mb.bm.verts.new((x, y, zc + z)) for (y, z) in po] for x in xs]
    I = [[mb.bm.verts.new((x, y, zc + z)) for (y, z) in pi] for x in xs]
    m = len(po)
    F = mb.face
    for i in range(len(xs) - 1):
        for j in range(m):
            jj = (j + 1) % m
            if sl[i] and tags[j]:
                F([O[i][j], O[i + 1][j], I[i + 1][j], I[i][j]], mat)
                F([O[i][jj], I[i][jj], I[i + 1][jj], O[i + 1][jj]], mat)
                F([O[i][j], I[i][j], I[i][jj], O[i][jj]], mat)
                F([O[i + 1][j], O[i + 1][jj], I[i + 1][jj], I[i + 1][j]], mat)
            else:
                F([O[i][j], O[i][jj], O[i + 1][jj], O[i + 1][j]], mat)
                F([I[i][j], I[i + 1][j], I[i + 1][jj], I[i][jj]], mat)
    for i in (0, len(xs) - 1):
        for j in range(m):
            jj = (j + 1) % m
            F([O[i][j], I[i][j], I[i][jj], O[i][jj]], mat)


def _qd_swivel(mb, M, ang=0.0, mat="gunmetal"):
    """Argolla de correa desmontable (QD): copa con botón y asa de alambre en D. M: z local hacia fuera del montaje."""
    revolve(mb, [(0.0075, -0.0003), (0.0075, 0.006), (0.0058, 0.0088), (0.0, 0.0094)], mat, seg=20, M=M, caps=False)
    Ml = M @ _T(0, 0, 0.0055) @ _Rz(ang)
    pts = []
    for k in range(7):                      # asa en D en el plano XZ local: pasa por la copa y se abre hacia +Z
        a = PI * k / 6
        pts.append(Ml @ Vector((0.016 * math.cos(a), 0.0, 0.004 + 0.016 * math.sin(a) * 0.9)))
    pts += [Ml @ Vector((-0.008, 0.0, 0.0)), Ml @ Vector((0.008, 0.0, 0.0))]
    from kit.clinic_equipo import loop_tube
    loop_tube(mb, pts, 0.0021, seg=SEG_T, mat=mat, normal=Ml.to_3x3() @ Vector((0, 1, 0)))


def _flash_hider(mb, x, z, r=0.0105, mat="gunmetal"):
    """Apagallamas de 6 púas (ranuras abiertas al frente) con collarín, sobre el eje (x, 0, z) hacia +X."""
    M = _ax(x, 0, z)
    revolve(mb, [(0.0098, -0.004), (r, -0.002), (r, 0.013)], mat, seg=SEG, M=M)
    for k in range(6):
        a0 = 2 * PI * k / 6 + 0.21
        arc_solid(mb, 0.0068, r - 0.0002, 0.0125, 0.052, a0, a0 + 2 * PI / 6 - 0.42, 3, mat, M=M)


def _brake(mb, x, z, r=0.0118, mat="gunmetal"):
    """Freno de boca de 3 ventanas por lado: collarín roscado, lomos superior e inferior corridos y deflectores laterales
    (las ventanas atraviesan hasta el ánima); eje (x, 0, z) hacia +X."""
    M = _ax(x, 0, z)                              # ángulo local: 0 = -Z (abajo), π/2 = +Y, π = +Z, 3π/2 = -Y
    revolve(mb, [(0.0105, -0.004), (r, -0.001), (r, 0.012)], mat, seg=SEG, M=M)
    for ac in (0.0, PI):                          # lomos
        arc_solid(mb, 0.0068, r - 0.0002, 0.0115, 0.066, ac - 0.62, ac + 0.62, 6, mat, M=M)
    for (z0, z1) in ((0.0115, 0.0165), (0.0265, 0.0315), (0.0415, 0.0465), (0.0565, 0.066)):
        for ac in (PI / 2, 1.5 * PI):             # deflectores laterales
            arc_solid(mb, 0.0070, r - 0.0005, z0, z1, ac - (PI / 2 - 0.57), ac + (PI / 2 - 0.57), 4, mat, M=M)


def _red_dot(mb, x, z, mat="gunmetal"):
    """Mira de punto rojo de tubo Ø 30 mm sobre montaje alto: abrazadera al riel con perilla, tubo con lentes rehundidas,
    torretas de elevación y deriva con tapas, tapa de batería. x = frente del montaje, z = cara superior del riel."""
    zo = z + 0.0375                          # eje óptico (cowitness absoluto ~ 66 mm sobre el ánima)
    plan(mb, [(x - 0.040, -0.0125), (x, -0.0125), (x, 0.0125), (x - 0.040, 0.0125)], [0.002] * 4, 0.007, mat, z0=z - 0.0035,
         re=0.0015, ne=1)
    side(mb, [(x - 0.036, z + 0.003), (x - 0.004, z + 0.003), (x - 0.008, zo - 0.010), (x - 0.032, zo - 0.010)],
         [0.0, 0.0, 0.004, 0.004], 0.016, mat, re=0.002, ne=1, n=2)
    revolve(mb, [(0.0, -0.0025), (0.0075, -0.0025), (0.0075, 0.007), (0.0060, 0.0085), (0.0, 0.0085)], mat, seg=SEG,
            M=_T(x - 0.020, 0.0125, z - 0.001) @ _Rx(-90))
    M = _ax(x - 0.060, 0, zo)
    prof = [(0.0, 0.004), (0.0118, 0.004), (0.0118, 0.0018), (0.0148, 0.0), (0.0155, 0.003), (0.0155, 0.060), (0.0148, 0.064),
            (0.0118, 0.064), (0.0118, 0.0615), (0.0, 0.0615)]
    mats = ["cable", "gunmetal", mat, mat, mat, mat, mat, "gunmetal", "cable"]
    revolve(mb, prof, mats, seg=SEG, M=M)
    for (yy, zz, rot) in ((0.0, 0.0155, None), (0.0155, 0.0, "y"), (-0.0155, 0.0, "-y")):
        Mt = _T(x - 0.030, yy, zo + zz) @ (Matrix() if rot is None else (_Rx(-90) if rot == "y" else _Rx(90)))
        revolve(mb, [(0.0, -0.004), (0.0095, -0.004), (0.0095, 0.008), (0.0085, 0.0095), (0.0, 0.0095)], mat, seg=SEG, M=Mt)


def _scope(mb, x, z, mat="gunmetal"):
    """Mira telescópica de aumento variable (1-6×, tubo de 30 mm, ~ 26 cm): objetivo, tubo, silla de torretas con
    elevación (arriba), deriva (derecha) e iluminación (izquierda), anillo de aumentos con palanca, ocular; montaje de una
    pieza con 2 anillos partidos. x = frente del montaje sobre el riel, z = cara superior del riel. Objetivo hacia +X."""
    zo = z + 0.040
    plan(mb, [(x - 0.100, -0.0125), (x, -0.0125), (x, 0.0125), (x - 0.100, 0.0125)], [0.002] * 4, 0.007, mat, z0=z - 0.0035,
         re=0.0015, ne=1)
    xa = x + 0.050                                  # cara del objetivo
    for pz in (0.060, 0.135):                       # anillos: pie + abrazadera
        xr = xa - pz
        side(mb, [(xr - 0.011, z + 0.003), (xr + 0.011, z + 0.003), (xr + 0.011, zo - 0.012), (xr - 0.011, zo - 0.012)],
             [0.0, 0.0, 0.003, 0.003], 0.018, mat, re=0.002, ne=1, n=2)
        revolve(mb, [(0.0149, -0.0115), (0.0190, -0.0115), (0.0190, 0.0115), (0.0149, 0.0115)], mat, seg=SEG,
                M=_T(xr, 0, zo) @ _Ry(90), closed=True)
    prof = [(0.0, 0.003), (0.0176, 0.003), (0.0186, 0.0), (0.0186, 0.026), (0.0152, 0.044), (0.0152, 0.080), (0.0172, 0.082),
            (0.0172, 0.110), (0.0152, 0.112), (0.0152, 0.158), (0.0182, 0.160), (0.0182, 0.184), (0.0212, 0.226),
            (0.0212, 0.262), (0.0, 0.262)]
    mats = ["cable"] + [mat] * (len(prof) - 3) + ["cable"]
    revolve(mb, prof, mats, seg=SEG, M=_T(xa, 0, zo) @ _Ry(-90))
    xt = xa - 0.096
    for (yy, zz, Mr) in ((0.0, 0.0172, Matrix()), (0.0172, 0.0, _Rx(-90))):
        revolve(mb, [(0.0112, -0.006), (0.0112, 0.006), (0.0126, 0.0075), (0.0126, 0.0165), (0.0, 0.0175)], mat, seg=SEG,
                M=_T(xt, yy, zo + zz) @ Mr, caps=False)
    revolve(mb, [(0.0098, -0.006), (0.0098, 0.009), (0.0, 0.010)], mat, seg=SEG, M=_T(xt, -0.0172, zo) @ _Rx(90), caps=False)
    xl = xa - 0.171                                 # palanca del anillo de aumentos
    side(mb, [(xl - 0.004, zo + 0.016), (xl + 0.004, zo + 0.016), (xl + 0.003, zo + 0.031), (xl - 0.003, zo + 0.031)],
         [0.0, 0.0, 0.003, 0.003], 0.007, mat, re=0.0)


def _buis(mb, x, z, front=False, mat="gunmetal"):
    """Mira de respaldo abatible (plegada) sobre riel: base con abrazadera y tornillo, hoja plegada hacia atrás."""
    plan(mb, [(x - 0.026, -0.0118), (x, -0.0118), (x, 0.0118), (x - 0.026, 0.0118)], [0.002] * 4, 0.009, mat, z0=z - 0.0025,
         re=0.0015, ne=1)
    lp = [(x - 0.024, z + 0.0065), (x - 0.002, z + 0.0065), (x - 0.006, z + 0.0125), (x - 0.024, z + 0.0115)]
    side(mb, lp, [0.0, 0.002, 0.002, 0.0], 0.019 if not front else 0.012, mat, re=0.0)
    revolve(mb, [(0.0, -0.001), (0.0042, -0.001), (0.0042, 0.003), (0.0, 0.003)], mat, seg=16,
            M=_T(x - 0.013, 0.0118, z + 0.002) @ _Rx(-90))



def _holo(mb, x, z, mat="gunmetal"):
    """Mira holográfica / de punto de caja: base con compartimiento de pila y botones, capuchón rectangular abierto con su
    ventana, abrazadera con perilla. x = frente de la base, z = cara superior del riel."""
    xloft(mb, [(x - 0.088, 0.030, 0.016, z + 0.009, 0.004), (x - 0.084, 0.034, 0.020, z + 0.010, 0.005),
               (x - 0.004, 0.034, 0.020, z + 0.010, 0.005), (x, 0.030, 0.016, z + 0.009, 0.004)], mat, n=4)
    zc = z + 0.0355
    slotted_tube(mb, x - 0.062, x - 0.004, 0.040, 0.034, 0.007, 0.0028, zc, [], band=0.0, mat=mat)
    side(mb, [(x - 0.060, z + 0.015), (x - 0.010, z + 0.015), (x - 0.010, zc - 0.012), (x - 0.060, zc - 0.012)], 0.0, 0.026, mat,
         re=0.0)
    mb.box((x - 0.0215, -0.0168, zc - 0.0138), (x - 0.0195, 0.0168, zc + 0.0138), "cable", bevel=0.0)
    for k, yy in enumerate((-0.007, 0.007)):        # botones traseros
        revolve(mb, [(0.0, -0.002), (0.004, -0.002), (0.004, 0.002), (0.0032, 0.003), (0.0, 0.003)], "rubber", seg=16,
                M=_T(x - 0.088, yy, z + 0.010) @ _Ry(-90))
    revolve(mb, [(0.0, -0.002), (0.008, -0.002), (0.008, 0.007), (0.0068, 0.0085), (0.0, 0.0085)], mat, seg=SEG,
            M=_T(x - 0.040, 0.017, z + 0.006) @ _Rx(-90))


# ======================================================================================================== fusil
def rifle(seed=0, kind="assault", sling=False, mag=True):
    """Fusil de asalto genérico de cerrojo rotativo y sistema de gas (aspecto militar actual, no réplica). kind:
    «carbine» (cañón 368 mm, ~ 0,86 m, punto rojo de tubo), «assault» (cañón 420 mm, ~ 0,91 m, mira holográfica de caja),
    «dmr» (cañón 508 mm, ~ 1,01 m, mira 1-6× en montaje de una pieza, culata fija con carrillera, freno de boca y bípode
    plegado). Construcción: culata de polímero (lofts de sección redondeada) con cantonera de hule sobre tubo de amortiguador
    con tuerca castillo y placa portafusil; cajón inferior de aluminio con brocal, guardamonte, disparador, selector, retén
    del cargador, retén del cerrojo y pasadores; empuñadura ergonómica; cajón superior con riel ranurado, tapa de expulsión
    con bisagra, asistente de cierre, deflector y palanca de carga en T; guardamanos flotante con ranuras pasantes a ambos
    costados y abajo y riel superior corrido; cañón con bloque de gas (visible por las ranuras) y apagallamas de 6 púas o
    freno; miras de respaldo plegadas; argollas QD (placa trasera y guardamanos); cargador curvo (mag=False lo quita);
    correa de cinta opcional (sling=True). Muebles en polímero negro (semilla par) o arena (impar).
    ORIGEN: x = 0 cara de la cantonera, z = 0 talón inferior de la cantonera, y = 0 plano de simetría; cañón hacia +X, arriba
    +Z. Eje del ánima a z = RIFLE_BORE_Z = 0,102 m; largo total RIFLE_LEN[kind]; el cargador y la empuñadura bajan de z = 0
    (hasta ~ -0,10 m con cargador). Para un armero: la cantonera apoya en x = 0 y el cañón se sujeta a ~ 0,6-0,8 m.
    Fuentes: en.wikipedia.org/wiki/M4_carbine y americanspecialops.com (largo 838 / 1003 mm, cañones 368 / 508 mm);
    en.wikipedia.org/wiki/Picatinny_rail (ranura 5,23 mm a paso 10,01 mm, 3 mm de profundidad)."""
    r = rng(seed)
    del r
    mb = MB()
    kind = kind if kind in RIFLE_LEN else "assault"
    BZ = RIFLE_BORE_Z
    ZPL = BZ - 0.011                    # línea de partición superior / inferior
    ZB = BZ - 0.040                     # fondo del cajón inferior (zona del disparador)
    GM = "gunmetal"
    F = "polymer" if seed % 2 == 0 else "paint_tan"
    Lb, Lh = {"carbine": (0.368, 0.26), "assault": (0.42, 0.30), "dmr": (0.508, 0.34)}[kind]
    xm = 0.43 + Lb                      # boca del cañón (cara del cerrojo en x = 0,43)
    xh0, xh1 = 0.513, 0.513 + Lh
    # ---------------- culata y cantonera
    if kind == "dmr":
        st = [(0.011, 0.044, 0.130, 0.068, 0.012), (0.04, 0.044, 0.128, 0.069, 0.012), (0.10, 0.042, 0.126, 0.070, 0.012),
              (0.13, 0.040, 0.085, 0.091, 0.012), (0.17, 0.040, 0.056, 0.100, 0.012), (0.212, 0.036, 0.046, 0.100, 0.010)]
        xloft(mb, st, F, n=4)
        xloft(mb, [(0.032, 0.030, 0.020, 0.141, 0.006), (0.040, 0.034, 0.024, 0.143, 0.009), (0.150, 0.034, 0.024, 0.143, 0.009),
                   (0.160, 0.028, 0.018, 0.140, 0.006)], F, n=4)
        revolve(mb, [(0.009, -0.002), (0.009, 0.008), (0.0, 0.0095)], GM, seg=SEG, M=_T(0.09, -0.020, 0.105) @ _Rx(90),
                caps=False)                                                             # perilla de la carrillera
    else:
        # culata retráctil: cuerpo deslizante sobre el tubo, talón alto y pata inferior en diagonal (ventana pasante)
        xloft(mb, [(0.034, 0.040, 0.046, BZ - 0.001, 0.013), (0.050, 0.044, 0.052, BZ - 0.002, 0.015),
                   (0.172, 0.044, 0.050, BZ - 0.003, 0.015), (0.196, 0.038, 0.042, BZ - 0.002, 0.012)], F, n=4)
        xloft(mb, [(0.010, 0.044, 0.128, 0.067, 0.012), (0.034, 0.044, 0.126, 0.068, 0.012), (0.056, 0.040, 0.104, 0.080, 0.012),
                   (0.066, 0.034, 0.060, 0.102, 0.012)], F, n=4)
        p0, p1 = Vector((0.020, 0.0, 0.018)), Vector((0.168, 0.0, BZ - 0.024))
        Ml, _ = port.frame_on(p0, p1, up=(0, 0, 1))
        port.loft(mb, [(0.0, 0.034, 0.030, 0.0), (0.03, 0.030, 0.022, 0.0), (0.12, 0.028, 0.020, 0.0), (0.155, 0.030, 0.024, 0.002)],
                  seg=16, mat=F, M=Ml, ex=2.8)
        side(mb, [(0.135, BZ - 0.033), (0.172, BZ - 0.030), (0.172, BZ - 0.024), (0.135, BZ - 0.024)], [0.004, 0.002, 0.0, 0.0],
             0.012, F, re=0.0015, ne=1, n=2)                                           # palanca de ajuste
    xloft(mb, [(0.0, 0.040, 0.126, 0.067, 0.011), (0.003, 0.046, 0.134, 0.067, 0.014), (0.0125, 0.046, 0.134, 0.067, 0.014)],
          "rubber", n=4)
    for zz in ((0.035, 0.065, 0.095) if kind != "dmr" else ()):                       # estrías de la cantonera
        plank(mb, (-0.0008, -0.019, zz - 0.0018), (0.0006, 0.019, zz + 0.0018), "rubber", ch=0.0006)
    revolve(mb, [(0.0153, 0.03), (0.0153, 0.247), (0.0185, 0.2482), (0.0185, 0.2555), (0.0153, 0.2565)], GM, seg=SEG,
            M=_T(0, 0, BZ) @ _Ry(90), caps=False)                                                  # tubo del amortiguador + tuerca castillo
    xloft(mb, [(0.2555, 0.040, 0.048, BZ - 0.002, 0.012), (0.2580, 0.040, 0.048, BZ - 0.002, 0.012)], GM, n=4)
    _qd_swivel(mb, _T(0.2568, -0.020, BZ - 0.004) @ _Rx(90), ang=90.0)
    # ---------------- cajón inferior
    P = [(0.256, BZ + 0.016), (0.256, BZ - 0.018), (0.264, BZ - 0.030), (0.272, ZB), (0.395, ZB), (0.395, BZ - 0.086),
         (0.398, BZ - 0.095), (0.481, BZ - 0.095), (0.484, BZ - 0.086), (0.481, ZB + 0.004), (0.493, BZ - 0.033),
         (0.493, ZPL + 0.0005), (0.276, ZPL + 0.0005), (0.268, BZ + 0.016)]
    R = [0.006, 0.006, 0.01, 0.003, 0.004, 0.003, 0.004, 0.004, 0.003, 0.008, 0.006, 0.0, 0.006, 0.006]
    side(mb, P, R, 0.0296, GM, re=0.0012, n=3, ne=1)
    slab2(mb, _T(0.4395, 0, BZ - 0.0965), 0.093, 0.034, 0.012, 0.005, GM, re_t=0.0, ne_t=0, re_b=0.002, ne_b=1)  # boca del brocal
    strap(mb, fillet([(0.288, 0.0, ZB + 0.003), (0.296, 0.0, ZB - 0.013), (0.388, 0.0, ZB - 0.013), (0.394, 0.0, ZB + 0.002)],
                     0.006, 2), 0.004, 0.013, GM, up=(0, 1, 0), r=0.0012)              # guardamonte
    side(mb, [(0.333, ZB + 0.001), (0.339, ZB + 0.001), (0.341, ZB - 0.006), (0.338, ZB - 0.0115), (0.334, ZB - 0.010),
              (0.3355, ZB - 0.005)], [0.0, 0.0, 0.003, 0.002, 0.0, 0.003], 0.006, GM, re=0.0)                     # disparador
    for (xx, zz) in ((0.266, BZ - 0.012), (0.487, BZ - 0.024)):                         # pasadores de desarme / pivote
        revolve(mb, [(0.0034, -0.0156), (0.0034, 0.0156)], GM, seg=16, M=_T(xx, 0, zz) @ _Rx(90))
    revolve(mb, [(0.0, -0.0003), (0.0062, -0.0003), (0.0062, 0.0025), (0.0, 0.0025)], GM, seg=SEG,
            M=_T(0.300, -0.0148, BZ - 0.022) @ _Rx(90))                                 # selector (izq.)
    side(mb, [(0.297, BZ - 0.0255), (0.319, BZ - 0.0235), (0.321, BZ - 0.0195), (0.297, BZ - 0.0185)], [0.002, 0.002, 0.002, 0.002],
         0.0022, GM, y0=-0.0148 - 0.0035, re=0.0, n=2)
    revolve(mb, [(0.0048, -0.0003), (0.0048, 0.002), (0.0, 0.0028)], GM, seg=20, M=_T(0.405, 0.0148, BZ - 0.030) @ _Rx(-90),
            caps=False)                                 # retén del cargador (der.)
    side(mb, [(0.398, BZ - 0.028), (0.418, BZ - 0.026), (0.418, BZ - 0.016), (0.400, BZ - 0.014)], [0.001, 0.003, 0.003, 0.001],
         0.0024, GM, y0=-0.0148 - 0.001, re=0.0, n=2)                                   # retén del cerrojo (izq.)
    # ---------------- empuñadura
    a = math.radians(18.0)
    p0 = Vector((0.285, 0.0, ZB + 0.008))
    p1 = p0 + Vector((-math.sin(a), 0.0, -math.cos(a))) * 0.115
    Mg, _ = port.frame_on(p0, p1, up=(1, 0, 0))
    port.loft(mb, [(0.0, 0.026, 0.045, 0.001), (0.014, 0.029, 0.050, 0.0), (0.04, 0.0305, 0.053, -0.001), (0.065, 0.031, 0.051, 0.001),
                   (0.09, 0.031, 0.051, -0.002), (0.108, 0.029, 0.047, -0.003), (0.115, 0.020, 0.034, -0.003)], seg=SEG, mat=F, M=Mg,
              ex=2.5)
    # ---------------- cajón superior
    xloft(mb, [(0.262, 0.030, 0.030, ZPL + 0.015, 0.004), (0.512, 0.030, 0.030, ZPL + 0.015, 0.004)], GM, n=4)
    rail(mb, 0.266, 0.508, BZ + 0.019, GM)
    side(mb, [(0.335, BZ - 0.0075), (0.395, BZ - 0.0075), (0.395, BZ + 0.0085), (0.335, BZ + 0.0085)], [0.0015] * 4, 0.0014, GM,
         y0=0.0153, re=0.0)                                                             # tapa de expulsión
    revolve(mb, [(0.0016, 0.333), (0.0016, 0.397)], GM, seg=SEG_T, M=_T(0, 0.0162, BZ - 0.0085) @ _Ry(90))
    side(mb, [(0.316, BZ + 0.001), (0.332, BZ + 0.001), (0.332, BZ + 0.013), (0.322, BZ + 0.013)], [0.0, 0.0, 0.003, 0.004], 0.006,
         GM, y0=0.016, re=0.0012, ne=1, n=2)                                            # deflector de vainas
    pa, pb = Vector((0.318, 0.011, BZ + 0.004)), Vector((0.282, 0.024, BZ + 0.004))
    Mf, _ = port.frame_on(pa, pb)
    revolve(mb, [(0.0085, 0.0), (0.0085, 0.020), (0.0068, 0.0225), (0.0068, 0.032), (0.0, 0.0335)], GM, seg=SEG,
            M=Mf @ _Ry(90), caps=False)                                                 # asistente de cierre
    plan(mb, [(0.244, -0.022), (0.253, -0.022), (0.259, -0.008), (0.263, -0.008), (0.263, 0.008), (0.259, 0.008), (0.253, 0.022),
              (0.244, 0.022)], [0.003, 0.002, 0.002, 0.0, 0.0, 0.002, 0.002, 0.003], 0.0075, GM, z0=BZ + 0.0156, re=0.0015, ne=1,
         n=2)                                                                            # palanca de carga
    revolve(mb, [(0.017, 0.5112), (0.017, 0.5138)], GM, seg=SEG, M=_T(0, 0, BZ) @ _Ry(90))   # tuerca del cañón
    # ---------------- guardamanos, cañón, bloque de gas, boca
    n_sl = int((Lh - 0.06) / 0.058) if kind != "dmr" else 3
    pit = 0.058 if kind != "dmr" else 0.088
    slots = [(xh0 + 0.034 + k * pit, xh0 + 0.066 + k * pit) for k in range(n_sl)]
    slotted_tube(mb, xh0, xh1, 0.046, 0.048, 0.011, 0.003, BZ - 0.005, slots)
    rail(mb, xh0 + 0.002 + (0.12 if kind == "dmr" else 0.0), xh1 - 0.002, BZ + 0.019, GM)
    xg = xh1 - 0.075
    revolve(mb, [(0.0105, 0.43), (0.0105, xg - 0.03), (0.0095, xg - 0.028), (0.0095, xm)], GM, seg=SEG,
            M=_T(0, 0, BZ) @ _Ry(90), caps=False)
    revolve(mb, [(0.0135, -0.012), (0.0135, 0.012)], GM, seg=SEG, M=_ax(xg, 0, BZ))
    if kind == "dmr":
        _brake(mb, xm - 0.004, BZ)
    else:
        _flash_hider(mb, xm - 0.004, BZ)
    # ---------------- miras
    zr = BZ + 0.0285                                                                    # cara superior de los rieles
    if kind != "dmr":                                                                  # el DMR usa solo la mira telescópica
        _buis(mb, 0.300, zr)
        _buis(mb, xh1 - 0.004, zr, front=True)
    if kind == "carbine":
        _red_dot(mb, 0.420, zr)
    elif kind == "assault":
        _holo(mb, 0.430, zr)
    else:
        _scope(mb, 0.470, zr)
    # ---------------- argolla delantera, bípode, cargador, correa
    xs = xh1 - 0.045
    _qd_swivel(mb, _T(xs, -0.0228, BZ - 0.005) @ _Rx(90), ang=90.0)
    if mag:
        _mag(mb, _T(0.4385, 0, BZ - 0.024), lite=True)
    if sling:
        pts = [(xs, -0.031, BZ - 0.010), (xs - 0.03, -0.033, BZ - 0.060), (xs - 0.12, -0.034, BZ - 0.135), (0.45, -0.035, BZ - 0.165),
               (0.33, -0.035, BZ - 0.150), (0.28, -0.034, BZ - 0.090), (0.262, -0.031, BZ - 0.012)]
        path = spline(pts, 2)
        strap(mb, path, 0.025, 0.0022, "canvas", up=(0, 1, 0), r=0.0009)
        i = len(path) // 3                                                              # hebilla de ajuste
        Mh, _ = port.frame_on(Vector(path[i]), Vector(path[i + 1]), up=(0, 1, 0))
        plan(mb, [(-0.012, -0.016), (0.012, -0.016), (0.012, 0.016), (-0.012, 0.016)], [0.004] * 4, 0.004, "plastic",
             z0=-0.002, re=0.001, ne=1, n=2, M=Mh @ _Rx(90) @ _Rx(-90))
    return mb


# ======================================================================================================== pistola y funda
PISTOL_BORE_Z = 0.1135


def _pistol(mb, lite=False, F="polymer"):
    """Pistola de armazón de polímero y percutor lanzado, genérica (~ 190 × 135 × 31 mm): corredera de acero con aristas
    redondeadas y estrías traseras y delanteras, alza de cola de milano y guion, capuchón del cañón visible en la ventana
    de expulsión, boca con corona y guía del resorte; armazón con riel de accesorios de 3 ranuras, guardamonte cuadrado,
    disparador con seguro de lámina, palanca de desarme, retén de corredera, retén del cargador y empuñadura con lomo y
    base del cargador. lite = sin lo que tapa la funda (estrías delanteras, guion, riel, boca)."""
    BZ = PISTOL_BORE_Z
    GM = "gunmetal"
    zs0, zs1 = 0.097, 0.130                              # corredera
    xloft(mb, [(0.0, 0.022, 0.030, 0.1135, (0.005, 0.005, 0.0015, 0.0015)), (0.004, 0.0250, 0.033, 0.1135, (0.006, 0.006, 0.0015, 0.0015)),
               (0.176, 0.0250, 0.033, 0.1135, (0.006, 0.006, 0.0015, 0.0015)), (0.190, 0.0225, 0.029, 0.1130, (0.006, 0.006, 0.002, 0.002))],
          GM, n=4)
    for k in range(6):                                   # estrías traseras (y delanteras)
        for x0 in ([0.012 + k * 0.0042] + ([0.150 + k * 0.0042] if not lite else [])):
            for sy in (-1, 1):
                side(mb, [(x0, zs0 + 0.004), (x0 + 0.0019, zs0 + 0.004), (x0 + 0.0024, zs1 - 0.007), (x0 + 0.0005, zs1 - 0.007)], 0.0,
                     0.0012, GM, y0=sy * 0.01245, re=0.0)
    side(mb, [(0.006, zs1 - 0.001), (0.020, zs1 - 0.001), (0.019, zs1 + 0.0055), (0.0145, zs1 + 0.0055), (0.0145, zs1 + 0.0035),
              (0.0115, zs1 + 0.0035), (0.0115, zs1 + 0.0055), (0.0075, zs1 + 0.0055)], [0.0, 0.0, 0.001, 0.0, 0.0006, 0.0006, 0.0, 0.001],
         0.021, GM, re=0.0)                              # alza (vista de lado: escalón con muesca transversal)
    plan(mb, [(0.075, 0.0005), (0.122, 0.0005), (0.122, 0.0105), (0.075, 0.0105)], [0.0, 0.0015, 0.0015, 0.0], 0.0008, GM,
         z0=zs1 - 0.0012, re=0.0)                        # capuchón del cañón (ventana de expulsión)
    side(mb, [(0.074, zs1 - 0.0015), (0.123, zs1 - 0.0015), (0.123, zs1 - 0.0095), (0.074, zs1 - 0.0095)], 0.0, 0.0010, GM,
         y0=0.01255, re=0.0)                             # borde de la ventana (lado derecho)
    if not lite:
        side(mb, [(0.181, zs1 - 0.001), (0.187, zs1 - 0.001), (0.186, zs1 + 0.0045), (0.182, zs1 + 0.0045)], [0.0, 0.0, 0.001, 0.001],
             0.0035, GM, re=0.0)                         # guion
        revolve(mb, [(0.0, 0.1885), (0.0045, 0.1885), (0.0058, 0.1902), (0.0064, 0.1905)], ["cable", GM, GM], seg=SEG,
                M=_T(0, 0, BZ) @ _Ry(90), caps=False)    # boca: ánima oscura y corona
        revolve(mb, [(0.0, 0.1875), (0.0028, 0.1875), (0.0028, 0.1905)], GM, seg=16, M=_T(0, 0, BZ - 0.0115) @ _Ry(90), caps=False)
    # armazón: rieles y cubrepolvo, riel de accesorios
    side(mb, [(0.004, 0.086), (0.060, 0.086), (0.070, 0.080), (0.104, 0.080), (0.110, 0.084), (0.186, 0.084), (0.186, 0.0985),
              (0.004, 0.0985)], [0.004, 0.003, 0.004, 0.003, 0.003, 0.004, 0.0, 0.0], 0.0236, F, re=0.0015, ne=1, n=2)
    if not lite:
        rail(mb, 0.125, 0.165, 0.0845, F, M=_T(0, 0, 0.1685) @ _Rx(180))
    # guardamonte cuadrado y disparador
    strap(mb, fillet([(0.104, 0.0, 0.083), (0.112, 0.0, 0.060), (0.104, 0.0, 0.053), (0.062, 0.0, 0.053), (0.055, 0.0, 0.062)], 0.008, 3),
          0.0045, 0.0105, F, up=(0, 1, 0), r=0.0015)
    side(mb, [(0.080, 0.0805), (0.0855, 0.0805), (0.0835, 0.070), (0.0805, 0.0625), (0.0770, 0.0640), (0.0790, 0.071)],
         [0.0, 0.0, 0.003, 0.0015, 0.0, 0.003], 0.0055, F, re=0.0)
    # empuñadura con lomo y base del cargador
    a = math.radians(17.0)
    p0 = Vector((0.036, 0.0, 0.090))
    p1 = p0 + Vector((-math.sin(a), 0.0, -math.cos(a))) * 0.086
    Mg, _ = port.frame_on(p0, p1, up=(1, 0, 0))
    port.loft(mb, [(0.0, 0.024, 0.046, 0.0), (0.010, 0.0285, 0.047, 0.0), (0.030, 0.0300, 0.0475, 0.0008), (0.058, 0.0300, 0.046, -0.0005),
                   (0.080, 0.0295, 0.045, -0.001), (0.087, 0.0285, 0.044, -0.001)], seg=SEG, mat=F, M=Mg, ex=2.7)
    slab2(mb, Mg @ _T(0.086, 0.0, -0.001) @ _Ry(90) @ _T(0, 0, -0.0005), 0.047, 0.031, 0.008, 0.006, F, re_t=0.0025, ne_t=2)
    side(mb, [(-0.004, 0.088), (0.012, 0.088), (0.016, 0.098), (0.006, 0.0985), (-0.004, 0.094)], [0.002, 0.0, 0.0, 0.002, 0.004],
         0.022, F, re=0.0015, ne=1, n=2)                 # cola de castor
    # palancas y botones (izquierda)
    side(mb, [(0.068, 0.0925), (0.080, 0.0925), (0.080, 0.0975), (0.068, 0.0975)], [0.001] * 4, 0.0016, GM, y0=-0.0126, re=0.0)
    side(mb, [(0.032, 0.0905), (0.060, 0.0905), (0.062, 0.0965), (0.034, 0.0965)], [0.001, 0.002, 0.002, 0.001], 0.0016, GM,
         y0=-0.0126, re=0.0)
    side(mb, [(0.056, 0.074), (0.062, 0.074), (0.062, 0.084), (0.056, 0.084)], [0.0015] * 4, 0.0024, F, y0=-0.0148, re=0.0)


def pistol(seed=0):
    """Pistola de servicio genérica (polímero + corredera de acero), ~ 190 mm de largo, 135 mm de alto, 31 mm de ancho
    (proporción de las pistolas de servicio de 9 mm). Ver _pistol. ORIGEN: x = 0 trasera de la corredera, z = 0 base del
    cargador, y = 0 plano de simetría; cañón hacia +X (eje del ánima a z = PISTOL_BORE_Z = 0,1135).
    Fuente de proporción: ficha de largo / alto de pistolas de servicio de 9 mm (≈ 186-203 mm × 128-140 mm)."""
    mb = MB()
    _pistol(mb, F="polymer" if seed % 2 == 0 else "paint_tan")
    return _drop(mb)



def holster(seed=0):
    """Funda rígida de polímero moldeado con la pistola enfundada (pistol, versión sin lo que tapa la funda): concha que
    copia corredera, cubrepolvo y guardamonte, con boca reforzada y labio, capuchón de retención en U sobre la trasera de la
    corredera con sus pivotes, botón de liberación, plataforma de montaje MOLLE / cinturón atornillada (4 tornillos) en la
    espalda y barreno de drenaje. ORIGEN: punta inferior de la funda (z = 0), centrada en X e Y; la pistola va con la boca
    hacia -Z (de pie, como se porta) y la plataforma de montaje (lado del cuerpo) mira a +Y."""
    mb = MB()
    F = "polymer" if seed % 2 == 0 else "paint_tan"
    _pistol(mb, lite=True, F="polymer")
    # concha: lazos exterior / interior a lo largo de X (boca abierta en x = 0,045; punta cerrada en x = 0,203)
    st = [(0.045, 0.034, 0.064, 0.106), (0.060, 0.034, 0.083, 0.097), (0.105, 0.034, 0.090, 0.093), (0.118, 0.034, 0.064, 0.106),
          (0.192, 0.033, 0.062, 0.106), (0.203, 0.030, 0.056, 0.106)]
    outer = [[(x, y, zc + z) for (y, z) in rr_pts(w, h, 0.009, 4)] for (x, w, h, zc) in st]
    inner = [[(x, y, zc + z) for (y, z) in rr_pts(w - 0.006, h - 0.006, 0.006, 4)] for (x, w, h, zc) in st[:-1]]
    inner.append([(0.198, y, st[-1][3] + z) for (y, z) in rr_pts(st[-1][1] - 0.006, st[-1][2] - 0.006, 0.006, 4)])
    skin(mb, list(reversed(inner)) + outer, F, cap0=True, cap1=True)
    # labio de la boca (cordón)
    rr_torus(mb, _T(0.0455, 0, 0.106) @ _Ry(90), 0.064, 0.034, 0.009, 0.0022, F, nc=4, nb=4, phase=PI / 4)
    # capuchón de retención: arco en U sobre la corredera, pivotes en la concha
    arc = [(0.024, 0.0215 * math.cos(t), 0.115 + 0.026 * math.sin(t)) for t in [PI * k / 10 for k in range(11)]]
    path = [(0.052, 0.0215, 0.106), (0.034, 0.0215, 0.112)] + arc + [(0.034, -0.0215, 0.112), (0.052, -0.0215, 0.106)]
    strap(mb, spline(path, 1), 0.0035, 0.012, F, up=(1, 0, 0), r=0.0012)
    for sy in (-1, 1):
        revolve(mb, [(0.0065, -0.002), (0.0065, 0.0035), (0.0055, 0.0045), (0.0, 0.0047)], F, seg=SEG,
                M=_T(0.052, sy * 0.017, 0.106) @ _Rx(-90 * sy), caps=False)
    revolve(mb, [(0.0072, -0.002), (0.0072, 0.003), (0.0062, 0.0042), (0.0, 0.0045)], "rubber", seg=SEG,
            M=_T(0.070, 0.017, 0.128) @ _Rx(-90), caps=False)                         # botón de liberación
    # plataforma de montaje en la espalda (-Y del arma; tras girar queda hacia +Y)
    side(mb, [(0.060, 0.066), (0.180, 0.066), (0.180, 0.142), (0.060, 0.142)], [0.010] * 4, 0.006, F, y0=-0.0195, re=0.002, ne=1)
    for (x, z) in ((0.075, 0.078), (0.165, 0.078), (0.075, 0.130), (0.165, 0.130)):
        rivet(mb, _T(x, -0.0225, z) @ _Rx(90), d=0.008, mat="steel")
    for z in (0.084, 0.124):                                                            # correas MOLLE de la plataforma
        plank(mb, (0.055, -0.0245, z - 0.0125), (0.185, -0.0215, z + 0.0125), "canvas", ch=0.0008)
    revolve(mb, [(0.0035, 0.199), (0.0035, 0.2035)], "cable", seg=16, M=_T(0, 0, 0.106) @ _Ry(90), caps=False)  # drenaje
    mb.transform(_Rz(180) @ _Ry(90))
    bb = [v.co for v in mb.bm.verts]
    cx = (min(c.x for c in bb) + max(c.x for c in bb)) / 2
    cy = (min(c.y for c in bb) + max(c.y for c in bb)) / 2
    mb.transform(_T(-cx, -cy, 0))
    return _drop(mb)


# ======================================================================================================== ametralladora
def _belt_round(mb, M, link=True, k=0):
    """Cartucho clase 12,7 mm (vaina de latón ~ 99 mm, proyectil ~ 40 mm) con su eslabón de acero, a lo largo de Z local."""
    revolve(mb, [(0.0, 0.0), (0.0103, 0.0), (0.0103, 0.003), (0.0086, 0.004), (0.0086, 0.006), (0.0104, 0.0075), (0.0100, 0.078),
                 (0.0075, 0.090), (0.0072, 0.099)], "brass", seg=16, M=M, caps=False)
    revolve(mb, [(0.0065, 0.098), (0.0065, 0.112), (0.0050, 0.128), (0.0, 0.140)], "brass", seg=16, M=M, caps=False)
    if link:                                    # eslabón: dos abrazaderas de fleje y lengüeta
        for zc in (0.030, 0.064):
            revolve(mb, [(0.0106, zc - 0.006), (0.0118, zc - 0.006), (0.0118, zc + 0.006), (0.0106, zc + 0.006)], "steel", seg=16,
                    M=M, closed=True)
        z0 = 0.026 if k % 2 == 0 else 0.046                       # lengüetas alternadas (no se encimen)
        plan(mb, [(0.0105, -0.006), (0.024, -0.006), (0.024, 0.006), (0.0105, 0.006)], [0.0, 0.003, 0.003, 0.0], 0.018, "steel",
             z0=z0, re=0.0, M=M @ _Rz(90))


def machine_gun_tripod(seed=0):
    """Ametralladora pesada genérica de cajón remachado (~ 1,69 m, cañón pesado de ~ 1,14 m) sobre trípode bajo con
    mecanismo de puntería en dirección y elevación (T&E). Arma: cajón de lámina con placas laterales remachadas, tapa de
    alimentación abisagrada con su cerrojo, placa trasera con dos empuñaduras de pala de hule y gatillo de mariposa, alza
    de hoja plegada, guion, palanca de carga a la derecha, manguito portacañón con ventilas, cañón con asa de transporte y
    apagallamas; bandeja de alimentación a la izquierda con 7 cartuchos eslabonados que suben de una lata de munición abierta
    sujeta a la cuna. Montaje: cuna en U con perno, pivote en la cabeza del trípode, T&E (tornillo de elevación con volante y
    corredera de dirección con volante) sobre la barra de puntería en arco graduado; trípode de 3 patas tubulares (delantera
    y 2 traseras) con charnelas, seguros y zapatas. ORIGEN: piso bajo el pivote de la cabeza del trípode; cañón hacia +X.
    Fuentes: navweaps.com/Weapons/WNUS_50cal-M2_MG.php e imfdb.org/wiki/Browning_M2 (1654 mm, cañón 1143 mm, 38 kg);
    inetres.com/gp/military/infantry/mg/M2.html (trípode M3 con T&E ~ 20 kg, arma a ~ 0,3 m del suelo)."""
    r = rng(seed)
    mb = MB()
    GM, OD = "gunmetal", "paint_od"
    zh = 0.330                                   # cabeza del trípode (asiento del pivote)
    zr0, zr1 = 0.385, 0.545                      # cajón: fondo / tapa
    BZ = 0.475                                   # eje del cañón
    xr0, xr1 = -0.40, 0.16
    # ---------------- cajón
    xloft(mb, [(xr0, 0.104, zr1 - zr0, (zr0 + zr1) / 2, 0.006), (xr1, 0.104, zr1 - zr0, (zr0 + zr1) / 2, 0.006)], GM, n=4)
    for sy in (-1, 1):                           # placas laterales y filas de remaches
        side(mb, [(xr0 + 0.02, zr0 + 0.012), (xr1 - 0.02, zr0 + 0.012), (xr1 - 0.02, zr1 - 0.04), (xr0 + 0.02, zr1 - 0.04)],
             [0.004] * 4, 0.003, GM, y0=sy * 0.0525, re=0.0008, ne=1, n=2)
        for xx in [xr0 + 0.04 + k * 0.055 for k in range(10)]:
            for zz in (zr0 + 0.022, zr1 - 0.052):
                rivet(mb, _T(xx, sy * 0.054, zz) @ _Rx(-90 * sy), d=0.009)
    # tapa de alimentación con bisagra delantera y cerrojo trasero
    xloft(mb, [(-0.21, 0.098, 0.022, zr1 + 0.008, (0.006, 0.006, 0.0, 0.0)), (-0.20, 0.104, 0.026, zr1 + 0.010, (0.008, 0.008, 0.0, 0.0)),
               (0.10, 0.104, 0.026, zr1 + 0.010, (0.008, 0.008, 0.0, 0.0)), (0.11, 0.098, 0.022, zr1 + 0.008, (0.006, 0.006, 0.0, 0.0))],
          GM, n=4)
    revolve(mb, [(0.008, -0.056), (0.008, 0.056)], GM, seg=SEG, M=_T(0.112, 0, zr1 + 0.006) @ _Rx(90))
    side(mb, [(-0.235, zr1 + 0.002), (-0.205, zr1 + 0.002), (-0.205, zr1 + 0.026), (-0.228, zr1 + 0.020)], [0.0, 0.0, 0.003, 0.004],
         0.03, GM, re=0.0015, ne=1, n=2)                        # cerrojo de la tapa
    for xx in (-0.15, -0.08, -0.01, 0.06):                    # nervaduras de la tapa
        plank(mb, (xx - 0.004, -0.045, zr1 + 0.022), (xx + 0.004, 0.045, zr1 + 0.0255), GM, ch=0.0015)
    # alza de hoja plegada (atrás) y guion (manguito)
    side(mb, [(-0.40, zr1 - 0.001), (-0.33, zr1 - 0.001), (-0.33, zr1 + 0.012), (-0.40, zr1 + 0.012)], [0.0, 0.0, 0.004, 0.004],
         0.034, GM, re=0.0015, ne=1, n=2)
    side(mb, [(-0.395, zr1 + 0.011), (-0.30, zr1 + 0.014), (-0.30, zr1 + 0.019), (-0.395, zr1 + 0.017)], [0.002] * 4, 0.022, GM,
         re=0.0)
    # placa trasera, empuñaduras de pala y gatillo de mariposa
    xloft(mb, [(xr0 - 0.035, 0.10, 0.15, (zr0 + zr1) / 2, 0.012), (xr0 + 0.002, 0.11, 0.165, (zr0 + zr1) / 2, 0.012)], GM, n=4)
    for sy in (-1, 1):
        p0 = Vector((xr0 - 0.02, sy * 0.040, zr0 + 0.030))
        p1 = Vector((xr0 - 0.145, sy * 0.050, zr0 + 0.010))
        wire(mb, [tuple(p0), (xr0 - 0.06, sy * 0.044, zr0 + 0.025), tuple(p1)], 0.010, GM, bend=0.02, nseg=4, seg=SEG)
        Mg, L = port.frame_on(Vector((xr0 - 0.065, sy * 0.045, zr0 + 0.022)), p1)
        revolve(mb, [(0.0128, 0.0), (0.0145, 0.006), (0.0145, L - 0.012), (0.0125, L - 0.002), (0.0, L + 0.002)], "rubber", seg=SEG,
                M=Mg @ _Ry(90))
    side(mb, [(xr0 - 0.050, zr0 + 0.055), (xr0 - 0.035, zr0 + 0.055), (xr0 - 0.035, zr0 + 0.075), (xr0 - 0.054, zr0 + 0.072)],
         [0.003] * 4, 0.050, GM, re=0.0015, ne=1, n=2)              # gatillo de mariposa
    # palanca de carga (derecha) con corredera
    plank(mb, (-0.30, 0.0535, BZ - 0.014), (-0.05, 0.0575, BZ - 0.004), GM, ch=0.0012)
    side(mb, [(-0.105, BZ - 0.016), (-0.075, BZ - 0.016), (-0.075, BZ + 0.002), (-0.105, BZ + 0.002)], [0.003] * 4, 0.018, GM,
         y0=0.064, re=0.0015, ne=1, n=2)
    revolve(mb, [(0.0, 0.0), (0.0125, 0.0), (0.0135, 0.008), (0.0125, 0.030), (0.0, 0.034)], GM, seg=SEG,
            M=_T(-0.09, 0.073, BZ - 0.007) @ _Rx(-90))
    # bandeja de alimentación (izquierda) y cartuchos eslabonados que suben de la lata
    side(mb, [(-0.10, BZ - 0.020), (0.02, BZ - 0.020), (0.02, BZ + 0.035), (-0.10, BZ + 0.035)], [0.003] * 4, 0.040, GM,
         y0=-0.072, re=0.0015, ne=1, n=2)
    # ---------------- manguito portacañón con ventilas, cañón, asa, apagallamas, guion
    Mb = _ax(xr1 - 0.004, 0, BZ)
    revolve(mb, [(0.030, 0.0), (0.036, 0.004), (0.036, 0.030)], GM, seg=SEG, M=Mb, caps=False)
    zz = [0.030, 0.062, 0.074, 0.106, 0.118, 0.150, 0.162, 0.200]
    for i in range(len(zz) - 1):
        if i % 2 == 0:                           # tramos con 6 ventilas
            for k in range(6):
                a0 = 2 * PI * k / 6 + 0.2
                arc_solid(mb, 0.031, 0.0358, zz[i] - 0.0005, zz[i + 1] + 0.0005, a0, a0 + 2 * PI / 6 - 0.4, 3, GM, M=Mb)
        else:
            revolve(mb, [(0.031, zz[i]), (0.036, zz[i]), (0.036, zz[i + 1]), (0.031, zz[i + 1])], GM, seg=SEG, M=Mb, closed=True)
    revolve(mb, [(0.031, 0.200), (0.036, 0.200), (0.036, 0.212), (0.031, 0.212)], GM, seg=SEG, M=Mb, closed=True)
    side(mb, [(xr1 + 0.17, BZ + 0.034), (xr1 + 0.20, BZ + 0.034), (xr1 + 0.195, BZ + 0.072), (xr1 + 0.183, BZ + 0.072)],
         [0.0, 0.0, 0.002, 0.002], 0.006, GM, re=0.0)                 # guion
    xm = xr1 + 0.880
    revolve(mb, [(0.0225, xr1 + 0.15), (0.0225, xm - 0.15), (0.0205, xm - 0.14), (0.0205, xm)], GM, seg=SEG, M=_T(0, 0, BZ) @ _Ry(90),
            caps=False)
    revolve(mb, [(0.0205, -0.004), (0.0255, -0.002), (0.0255, 0.070), (0.0215, 0.074), (0.0, 0.074)], GM, seg=SEG,
            M=_ax(xm - 0.004, 0, BZ))                                # apagallamas cónico
    revolve(mb, [(0.0, 0.0738), (0.010, 0.0738), (0.010, 0.0745)], "cable", seg=SEG, M=_ax(xm - 0.004, 0, BZ), caps=False)
    xa = xr1 + 0.30                                                  # asa de transporte con abrazadera
    revolve(mb, [(0.0225, -0.018), (0.031, -0.016), (0.031, 0.016), (0.0225, 0.018)], GM, seg=SEG, M=_ax(xa, 0, BZ), closed=True)
    hp = [(xa, 0.0, BZ + 0.028), (xa, 0.0, BZ + 0.075), (xa - 0.10, 0.0, BZ + 0.085), (xa - 0.12, 0.0, BZ + 0.040)]
    wire(mb, hp, 0.007, GM, bend=0.025, nseg=4, seg=SEG_T)
    Mh, Lh = port.frame_on(Vector((xa - 0.012, 0, BZ + 0.0785)), Vector((xa - 0.088, 0, BZ + 0.0835)))
    revolve(mb, [(0.0115, 0.0), (0.0125, 0.004), (0.0125, Lh - 0.004), (0.0115, Lh)], "polymer", seg=SEG, M=Mh @ _Ry(90))
    # ---------------- cuna, pivote, mecanismo T&E
    for sy in (-1, 1):
        side(mb, [(xr1 - 0.10, zr0 - 0.045), (xr1 - 0.01, zr0 - 0.045), (xr1 - 0.01, zr0 + 0.05), (xr1 - 0.06, zr0 + 0.05),
                  (xr1 - 0.10, zr0 - 0.01)], [0.006, 0.006, 0.006, 0.006, 0.01], 0.010, OD, y0=sy * 0.058, re=0.002, ne=1, n=2)
    plank(mb, (xr1 - 0.10, -0.063, zr0 - 0.052), (xr1 - 0.01, 0.063, zr0 - 0.036), OD, ch=0.003)
    revolve(mb, [(0.0, -0.071), (0.010, -0.071), (0.010, 0.071), (0.0, 0.071)], "steel", seg=SEG, M=_T(xr1 - 0.035, 0, zr0 + 0.025) @ _Rx(90))
    revolve(mb, [(0.0185, zh - 0.06), (0.0185, zr0 - 0.050), (0.026, zr0 - 0.048)], "steel", seg=SEG, M=_T(xr1 - 0.055, 0, 0) @ _Rz(0),
            caps=False)                                              # pivote
    xp = xr1 - 0.055
    # T&E: abrazadera trasera del cajón, tornillo de elevación, volantes y corredera en la barra
    xt = xr0 + 0.04
    plank(mb, (xt - 0.025, -0.035, zr0 - 0.022), (xt + 0.025, 0.035, zr0 + 0.0005), OD, ch=0.003)
    zb = 0.200                                                        # barra de puntería
    revolve(mb, [(0.0145, zb + 0.02), (0.0145, zr0 - 0.040)], OD, seg=SEG, M=_T(xt, 0, 0), caps=False)
    revolve(mb, [(0.0095, zr0 - 0.045), (0.0095, zr0 - 0.018)], "steel", seg=SEG, M=_T(xt, 0, 0), caps=False)
    def handwheel(M, R=0.045, rr=0.006, spokes=3, knob=True):
        revolve(mb, [(R - rr, -rr), (R + rr, -rr), (R + rr, rr), (R - rr, rr)], OD, seg=32, M=M, closed=True)
        revolve(mb, [(0.0, -0.012), (0.013, -0.012), (0.013, 0.010), (0.0, 0.010)], OD, seg=SEG, M=M)
        for k in range(spokes):
            a = 2 * PI * k / spokes
            pa, pb = M @ Vector((0.012 * math.cos(a), 0.012 * math.sin(a), 0)), M @ Vector(((R - rr) * math.cos(a), (R - rr) * math.sin(a), 0))
            mb.tube([tuple(pa), tuple(pb)], 0.0045, seg=SEG_T, mat=OD)
        if knob:
            a = 0.5
            revolve(mb, [(0.0065, 0.0), (0.0075, 0.004), (0.0075, 0.030), (0.0055, 0.035), (0.0, 0.036)], "polymer", seg=SEG_T,
                    M=M @ _T(R * math.cos(a), R * math.sin(a), rr * 0.6))
    handwheel(_T(xt, 0.0, zb + 0.105) @ _Rx(90) @ _T(0, 0, -0.035), R=0.048)
    plank(mb, (xt - 0.035, -0.03, zb - 0.012), (xt + 0.035, 0.03, zb + 0.022), OD, ch=0.004)        # corredera de dirección
    handwheel(_T(xt, 0.045, zb + 0.005) @ _Rx(-90), R=0.038, spokes=3)
    # ---------------- trípode
    # cabeza
    revolve(mb, [(0.0, zh - 0.075), (0.040, zh - 0.075), (0.048, zh - 0.060), (0.048, zh - 0.010), (0.034, zh), (0.0215, zh),
                 (0.0215, zh + 0.002)], OD, seg=SEG, M=_T(xp, 0, 0), caps=False)
    feet = [(xp + 0.78, 0.0), (xp - 0.62, -0.52), (xp - 0.62, 0.52)]
    for k, (fx, fy) in enumerate(feet):
        top = Vector((xp, 0, zh - 0.045))
        d = Vector((fx - xp, fy, 0.0)).normalized()
        hinge = top + d * 0.058 + Vector((0, 0, -0.005))
        foot = Vector((fx, fy, 0.03))
        # charnela: orejas y perno
        side(mb, [(-0.012, -0.022), (0.040, -0.022), (0.040, 0.022), (-0.012, 0.022)], [0.004, 0.012, 0.012, 0.004], 0.036, OD,
             re=0.002, ne=1, n=2, M=_T(*(top + d * 0.025)) @ _Rz(math.degrees(math.atan2(d.y, d.x))) @ _T(0, 0, 0))
        revolve(mb, [(0.0065, -0.024), (0.0065, 0.024)], "steel", seg=SEG_T,
                M=_T(*hinge) @ _Rz(math.degrees(math.atan2(d.y, d.x))) @ _Rx(90))
        Ml, Ll = port.frame_on(hinge, foot)
        revolve(mb, [(0.0, -0.010), (0.0195, -0.008), (0.0195, Ll - 0.08), (0.0165, Ll - 0.07), (0.0165, Ll)], OD, seg=SEG,
                M=Ml @ _Ry(90), caps=False)
        revolve(mb, [(0.023, Ll * 0.45 - 0.02), (0.023, Ll * 0.45 + 0.02)], OD, seg=SEG, M=Ml @ _Ry(90))     # manguito de seguro
        revolve(mb, [(0.0, 0.0), (0.008, 0.0), (0.008, 0.035), (0.0, 0.036)], "polymer", seg=SEG_T,
                M=Ml @ _T(Ll * 0.45, 0, 0.022))
        # zapata: placa con espolón
        ang = math.degrees(math.atan2(d.y, d.x))
        plan(mb, [(-0.05, -0.04), (0.06, -0.04), (0.08, 0.0), (0.06, 0.04), (-0.05, 0.04)], [0.01, 0.012, 0.02, 0.012, 0.01], 0.008,
             OD, z0=0.0, re=0.002, ne=1, n=2, M=_T(fx, fy, 0) @ _Rz(ang))
        revolve(mb, [(0.0225, 0.004), (0.0225, 0.040), (0.0175, 0.050)], OD, seg=SEG, M=_T(fx, fy, 0), caps=False)
        if k > 0:
            side(mb, [(-0.045, 0.006), (0.0, 0.006), (0.0, 0.070), (-0.02, 0.060)], [0.0, 0.0, 0.004, 0.008], 0.008, OD, re=0.0,
                 M=_T(fx, fy, 0) @ _Rz(ang))
    # barra de puntería en arco graduado entre las patas traseras
    Rb = xp - xt
    arc = []
    a0, a1 = math.radians(152), math.radians(208)
    for k in range(13):
        a = a0 + (a1 - a0) * k / 12
        arc.append((xp + Rb * math.cos(a), Rb * math.sin(a), zb))
    for end, sy in ((arc[0], 1), (arc[-1], -1)):
        pass
    sweep_frame(mb, rr_profile(0.008, 0.030, 0.002, n=2), arc, OD, up=(0, 0, 1))
    for i in range(1, 12):                                            # graduación
        x, y, z = arc[i]
        plan(mb, [(-0.001, -0.004), (0.001, -0.004), (0.001, 0.004), (-0.001, 0.004)], 0.0, 0.0008, "sign_white", z0=z + 0.0147,
             re=0.0, M=_T(x, y, 0) @ _Rz(math.degrees(math.atan2(y, x - xp))))
    for (fx, fy) in feet[1:]:                                         # tirantes de la barra a las patas traseras
        sgn = 1 if fy > 0 else -1
        e = arc[0] if sgn > 0 else arc[-1]
        top = Vector((xp, 0, zh - 0.045))
        dd = Vector((fx - xp, fy, 0.03 - (zh - 0.045)))
        tleg = (zb - (zh - 0.045)) / dd.z
        pleg = top + dd * tleg
        wire(mb, [e, tuple(pleg)], 0.010, OD, seg=SEG_T)
    # ---------------- lata de munición abierta en la cuna (izquierda) y cinta
    can = ammo_can("large", seed=seed, open=True)
    can.transform(_T(-0.03, -0.155, zh - 0.12) @ _Rz(0))
    mb.join(can)
    plank(mb, (-0.10, -0.085, zh - 0.125), (0.04, -0.06, zh - 0.10), OD, ch=0.003)
    plank(mb, (-0.098, -0.0835, zh - 0.127), (-0.084, -0.0615, zr0 - 0.01), OD, ch=0.003)
    belt = spline([(-0.04, -0.155, zh + 0.03), (-0.04, -0.140, zh + 0.10), (-0.04, -0.110, BZ - 0.01), (-0.04, -0.080, BZ + 0.012)], 2)
    for i in range(len(belt) - 1):
        p, q = Vector(belt[i]), Vector(belt[i + 1])
        t = (q - p).normalized()
        Mr, _ = port.frame_on(p - Vector((0.07, 0, 0)), p + Vector((0.07, 0, 0)), up=tuple(t.cross(Vector((1, 0, 0))) * -1))
        _belt_round(mb, Mr @ _Ry(90), link=True, k=i)
    del r
    return mb

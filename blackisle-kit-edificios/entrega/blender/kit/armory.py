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
    _ce_text(mb, s, size, depth + 0.0003, mat, M @ _T(0, 0, -0.0003), res=2 if size >= 0.02 else 1, back=False)


def strap(mb, path, w, t, mat="canvas", up=(0, 0, 1), r=None, caps=True):
    """Cinta plana (correa, fleje) de ancho w y espesor t a lo largo de una polilínea; `up` = normal de la cara ancha."""
    prof = [(x, y) for (x, y) in rr_profile(w, t, r if r is not None else t * 0.45, n=2)]
    return sweep_frame(mb, prof, path, mat, up=up, caps=caps)


def wire(mb, pts, r, mat="steel", bend=0.01, nseg=4, seg=SEG_T, caps=True):
    """Alambre / varilla / cuerda por una polilínea con dobleces de radio real."""
    P = fillet(pts, bend, nseg) if len(pts) > 2 else pts
    out = [P[0]]
    for p in P[1:]:
        if (Vector(p) - Vector(out[-1])).length > 1e-6:
            out.append(p)
    mb.tube(out, r, seg=seg, mat=mat, caps=caps)


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


def rivet(mb, M, d=0.006, mat="steel", seg=10):
    """Cabeza de remache abombada sobre z = 0 local (hundida 0,2 mm)."""
    revolve(mb, [(d / 2, -0.0002), (d / 2, d * 0.12), (d * 0.36, d * 0.27), (d * 0.18, d * 0.33), (0.0, d * 0.35)], mat, seg=seg,
            M=M)


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
    if False:                                      # nervaduras: fuera de presupuesto (<= 600 triángulos)
        prof = [(-0.003, -0.0004), (0.003, -0.0004), (0.0022, 0.0009), (-0.0022, 0.0009)]
        for sy in (-1, 1):
            for u0 in (-0.012, 0.008):
                rings = []
                for (cx, cz, nx, nz) in sta[1:]:
                    rings.append([Vector((cx + nx * (u0 + x), sy * (W / 2 + y), cz + nz * (u0 + x))) for (x, y) in prof])
                loft_rings(mb, rings, "polymer", M=M)
    th_end = (H - 0.03) / Rc
    cx, cz = sta[-1][0], sta[-1][1]
    Mb = M @ _T(cx, 0, cz) @ _Ry(-math.degrees(th_end))
    slab2(mb, Mb @ _T(0.002, 0, -0.0075), 0.0715, 0.0275, 0.0088, 0.006, "polymer", re_t=0.0, ne_t=0, re_b=0.0025, ne_b=1, nc=3)


def _mag(mb, M, lite=False):
    """Cargador completo en el marco M (ver _mag_body): cuerpo, base, labios de alimentación y cartucho superior."""
    _mag_body(mb, M, lite=lite)
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
    lid.join(lev, _T(xl, 0, H - 0.012) @ _Ry(90 - (2.0 if not open else 75.0)))
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

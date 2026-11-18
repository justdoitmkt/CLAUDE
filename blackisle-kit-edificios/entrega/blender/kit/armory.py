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

Piezas: rifle (carbine / assault / dmr), pistol, holster, magazine, machine_gun_tripod, mortar, launcher_tube, ammo_can
(large / small, open), ammo_crate (wood / long / small, open), cardboard_ammo_box, shell_pallet, crate_pallet, vest, hard_case.
Utilidades reutilizables: side / plan (siluetas con filete por esquina), xloft, slab2 / shell, rail (MIL-STD-1913),
slotted_tube (guardamanos ranurado), plank / board, holed_board, pallet_gma, strap / wire / spline, stencil, rivet.
Fuentes de medidas (consultadas 2026-11): ver docstring de cada función.
"""
import math

import bpy  # noqa: F401  (bpy antes que mathutils)
from mathutils import Matrix, Vector

from kit import port
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rng, rr_profile
from kit.clinic_equipo import arc_solid, loft_rings, revolve, sweep_frame
from kit.clinic_equipo import text as _ce_text
from kit.clinic_servicios import _edge_levels, hexnut, holed, rr_pts, skin, slab

IN = 0.0254
SEG = 24          # lados de todo cilindro visible
SEG_B = 32        # cilindros grandes (proyectiles, tubos de mortero)
SEG_T = 14        # tubos delgados, alambres, cuerdas

# ---------------------------------------------------------------------------------------- datos para armeros (otro agente)
# rifle(kind): x = 0 cantonera, z = 0 talón inferior de la culata; ánima a lo largo de +X a la altura BORE_Z.
RIFLE_BORE_Z = 0.102
RIFLE_LEN = {"carbine": 0.844, "assault": 0.896, "dmr": 1.015}


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
def gridskin(mb, P, mat, M=None, closed=True, cap0=False, cap1=False, matf=None):
    """Malla de cuadriláteros sobre la rejilla P[i][j] (i = estaciones, j = puntos de la sección, lazo cerrado si closed).
    matf(i, j) -> material de la cara entre las estaciones i, i + 1 y los puntos j, j + 1 (ventanas, insertos)."""
    V = [[mb.bm.verts.new((M @ Vector(p)) if M is not None else Vector(p)) for p in row] for row in P]
    nj = len(P[0])
    jr = nj if closed else nj - 1
    for i in range(len(V) - 1):
        A, B = V[i], V[i + 1]
        for j in range(jr):
            jj = (j + 1) % nj
            mb.face([A[j], A[jj], B[jj], B[j]], matf(i, j) if matf else mat)
    if cap0:
        mb.face(list(reversed(V[0])), mat)
    if cap1:
        mb.face(V[-1], mat)
    return V


def rr_sec(D, W, r, n=4, a_side=(), b_end=()):
    """Sección de rectángulo redondeado D (eje a, frente +a) × W (eje b), antihoraria, con muestras extra sobre los costados
    (a_side: valores de a en las caras ±b) y sobre frente / trasera (b_end: valores de b en las caras ±a). Devuelve
    [(a, b, na, nb, cara)] con la normal exterior y la cara: 'F' frente, 'B' trasera, 'R' (+b), 'L' (-b), 'C' esquina."""
    ha, hb = D / 2 - r, W / 2 - r
    bs = sorted({-hb, hb} | {b for b in b_end if -hb < b < hb})
    as_ = sorted({-ha, ha} | {a for a in a_side if -ha < a < ha})
    out = [(D / 2, b, 1.0, 0.0, "F") for b in bs]

    def corner(ca, cb, a0):
        for k in range(1, n):
            t = a0 + PI / 2 * k / n
            out.append((ca + r * math.cos(t), cb + r * math.sin(t), math.cos(t), math.sin(t), "C"))
    corner(ha, hb, 0.0)
    out += [(a, W / 2, 0.0, 1.0, "R") for a in reversed(as_)]
    corner(-ha, hb, PI / 2)
    out += [(-D / 2, b, -1.0, 0.0, "B") for b in reversed(bs)]
    corner(-ha, -hb, PI)
    out += [(a, -W / 2, 0.0, -1.0, "L") for a in as_]
    corner(ha, -hb, 1.5 * PI)
    return out


def _bx(x, x0, x1, e):
    """Trapecio 0..1 entre x0 y x1 con rampas de ancho e (relieves y rebajes con chaflán)."""
    if x <= x0 or x >= x1:
        return 0.0
    return max(0.0, min(1.0, (x - x0) / e, (x1 - x) / e))


def _feat_rows(spans, e):
    """Estaciones de un rasgo con chaflán: [(x0, x1)] -> x0, x0 + e, x1 - e, x1."""
    out = []
    for (x0, x1) in spans:
        out += [x0, x0 + e, x1 - e, x1]
    return out


def _uniq(vals, tol=2e-5):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def round_556(mb, M, seg=24, lite=False, mat_case="brass", mat_bullet="copper"):
    """Cartucho clase 5,56 × 45 a lo largo de Z local (culote en z = 0): culote con pistón y bisel, ranura de extractor,
    vaina cónica (Ø 9,58 → 9,00 mm), hombro de 23°, cuello Ø 6,43 mm, proyectil Ø 5,70 mm con ojiva tangente (largo total
    57,4 mm). Fuente: SAAMI / C.I.P. 5,56 × 45 mm (en.wikipedia.org/wiki/5.56%C3%9745mm_NATO)."""
    if lite:
        case = [(0.0, 0.0002), (0.0046, 0.0), (0.0048, 0.0003), (0.0048, 0.0008), (0.0042, 0.0012), (0.0042, 0.0017),
                (0.00478, 0.0023), (0.0045, 0.0396), (0.00322, 0.0412), (0.00322, 0.0447), (0.0029, 0.0447)]
    else:
        case = [(0.0, 0.0003), (0.0019, 0.0003), (0.0021, 0.0001), (0.0024, 0.0), (0.0046, 0.0), (0.0048, 0.0002),
                (0.0048, 0.0008), (0.0043, 0.0011), (0.0042, 0.0013), (0.0042, 0.0016), (0.00478, 0.0022),
                (0.00473, 0.012), (0.00462, 0.026), (0.0045, 0.0396), (0.00322, 0.0412), (0.00322, 0.0447), (0.0029, 0.0447)]
    revolve(mb, case, mat_case, seg=seg, M=M, caps=False)
    zt = 0.0574
    bl = [(0.0029, 0.0447), (0.00285, 0.0452), (0.00285, 0.0486)]
    nk = 5 if lite else 8
    for k in range(1, nk + 1):                            # ojiva tangente (radio 7 calibres)
        u = k / nk
        z = 0.0486 + (zt - 0.0003 - 0.0486) * u
        bl.append((max(0.00285 * (1 - u ** 1.85) ** 0.62, 0.0004), z))
    bl.append((0.0, zt))
    revolve(mb, bl, mat_bullet, seg=seg, M=M, caps=False)


def _mag(mb, M, lite=False, inserted=False, cal="556", seed=0):
    """Cargador de polímero de doble hilera, genérico, en el marco M: z = 0 borde superior de las paredes (centro de la
    sección), crece hacia -Z, el frente mira a +X. 5,56: sección 63,5 × 23,5 mm, lomo de 172 mm con tramo recto de 30 mm y
    curva de radio 0,62 m hacia adelante; 7,62 («762»): 74,5 × 26,5 mm, 150 mm, casi recto.
    Cuerpo en una sola rejilla (gridskin) con: hombro de tope de inserción, ranura del retén en el costado izquierdo, ventana
    testigo vertical en ambos costados (inserto «glass»), panel de marcaje rebajado, 5 costillas de agarre que rodean la parte
    baja, ensanche de la pestaña de la base y paredes huecas arriba (labios de alimentación curvados, seguidor / cartucho
    superior y el siguiente en hilera alterna). Base (lengüeta delantera, talón, botón de retención, estrías) aparte.
    lite: menos estaciones (cargadores de mesa); inserted: dentro del brocal (sin la parte alta oculta ni cartuchos).
    Devuelve (centro de la base, eje 'arriba' de la base) en el marco M."""
    if cal == "762":
        H, D, W, r, Rc, s_st = 0.150, 0.0745, 0.0265, 0.0045, 1.60, 0.03
    else:
        H, D, W, r, Rc, s_st = 0.172, 0.0635, 0.0235, 0.0042, 0.62, 0.03
    e = 0.0005
    t_wall = 0.0013
    s_sh = 0.058 if cal != "762" else 0.054
    win_a = (-D / 2 + 0.0075, -D / 2 + 0.0145)
    win_s = (0.068, H - 0.026)
    pan_a = (-D / 2 + 0.021, D / 2 - 0.0085)
    pan_s = (0.080, min(0.128, H - 0.040))
    nt_a = (D / 2 - 0.024, D / 2 - 0.014)
    nt_s = (0.036, 0.046)
    ribs = [(H - 0.031 + k * 0.0048, H - 0.031 + k * 0.0048 + 0.0021) for k in range(5)]
    marg = D / 2 - r - 0.004
    # ---- muestras de la sección
    a_side = _feat_rows([win_a, pan_a, nt_a], e) + [-marg, marg, -marg - e, marg + e]
    if not lite:
        a_side += [(-D / 2 + r) * f for f in (0.25, -0.25)]
    b_end = [0.0] + ([] if lite else [-(W / 2 - r) * 0.5, (W / 2 - r) * 0.5])
    sec = rr_sec(D, W, r, 4 if not lite else 3, a_side, b_end)
    # ---- estaciones a lo largo del lomo
    s0 = 0.014 if inserted else 0.0
    st = [s0, s_sh, s_sh + 0.0015, H - 0.010, H - 0.004, H]
    st += _feat_rows([win_s, pan_s] + ribs, e) + ([] if inserted else _feat_rows([nt_s], e))
    step = 0.012 if lite else 0.007
    st += [s0 + step * k for k in range(int((H - s0) / step) + 1)]
    st = [s for s in _uniq(st) if s0 - 1e-9 <= s <= H + 1e-9]

    def spine(s):
        th = max(s - s_st, 0.0) / Rc
        c = Vector((Rc * (1 - math.cos(th)), 0.0, -(min(s, s_st) + Rc * math.sin(th))))
        return c, Vector((math.cos(th), 0.0, math.sin(th)))

    def off(a, b, fc, s):
        o = 0.0005 * max(0.0, min(1.0, (s - s_sh) / 0.0015))
        o += 0.0007 * max(0.0, min(1.0, (s - (H - 0.010)) / 0.006))
        if fc in ("R", "L"):
            o -= 0.0009 * _bx(a, *win_a, e) * _bx(s, *win_s, e)
            o -= 0.00045 * _bx(a, *pan_a, e) * _bx(s, *pan_s, e)
            if fc == "L":
                o -= 0.0018 * _bx(a, *nt_a, e) * _bx(s, *nt_s, e)
            wr = 1.0 if abs(a) >= marg + e - 1e-7 else (0.0 if abs(a) <= marg + 1e-7 else 0.5)
        else:
            wr = 1.0
        if wr > 0:
            o += 0.0007 * wr * max(_bx(s, a0, a1, 0.0006) for (a0, a1) in ribs)
        return o

    P = []
    for s in st:
        c, nv = spine(s)
        row = []
        for (a, b, na, nb, fc) in sec:
            o = off(a, b, fc, s)
            q = c + nv * (a + na * o) + Vector((0, 1, 0)) * (b + nb * o)
            row.append(tuple(q))
        P.append(row)
    win_j = {j for j, (a, b, na, nb, fc) in enumerate(sec) if fc in ("R", "L") and win_a[0] + e - 1e-7 <= a <= win_a[1] - e - 1e-7}
    win_i = {i for i, s in enumerate(st) if win_s[0] + e - 1e-7 <= s <= win_s[1] - e - 1e-7}
    matf = (lambda i, j: "glass" if (i in win_i and j in win_j and i + 1 < len(st) and st[i + 1] <= win_s[1] - e + 1e-7)
            else "polymer")
    if inserted:
        gridskin(mb, P, "polymer", M, cap0=True, cap1=True, matf=matf)
    else:
        # paredes huecas arriba: lazo interior a la profundidad del seguidor, borde interior, y el cuerpo
        zf = 0.0072
        inner = [(a - na * t_wall, b - nb * t_wall) for (a, b, na, nb, fc) in sec]
        rows = [[(a, b, -zf) for (a, b) in inner], [(a, b, 0.0) for (a, b) in inner]]   # s = 0: tramo recto (a = x, b = y)
        gridskin(mb, rows + P, "polymer", M, cap0=True, cap1=True,
                 matf=lambda i, j: "polymer" if i < 2 else matf(i - 2, j))
    # ---- base (perpendicular al final del lomo)
    c, nv = spine(H)
    up = nv.cross(Vector((0, 1, 0)))
    Mb = Matrix(((nv.x, 0.0, up.x, c.x), (nv.y, 1.0, up.y, c.y), (nv.z, 0.0, up.z, c.z), (0, 0, 0, 1)))
    Mb = M @ Mb
    o_b = 0.0012                                       # la base abraza la pestaña del cuerpo
    lv = [(0.0016, 0.0024), (0.0006, 0.0022), (0.0, 0.0014), (-0.0004, -0.0040), (-0.0006, -0.0066), (0.0002, -0.0078),
          (0.0016, -0.0082)]
    Db, Wb = D + 2 * o_b, W + 2 * o_b

    def bl(dl, z):
        q = rr_pts(Db - 2 * dl + 0.0035, Wb - 2 * dl, (r + o_b - dl + 0.001, r + o_b - dl, r + o_b - dl, r + o_b - dl + 0.001),
                   4 if not lite else 3)
        return [(x + 0.0012, y, z) for (x, y) in q]
    skin(mb, [bl(dl, z) for (dl, z) in lv], "polymer", Mb)
    zb = -0.0082
    # lengüeta delantera (talón para sacar el cargador de la bolsa) y talón trasero
    side(mb, [(D / 2 + o_b + 0.001, zb + 0.0006), (D / 2 + o_b + 0.0058, zb + 0.0004), (D / 2 + o_b + 0.0064, zb + 0.0052),
              (D / 2 + o_b + 0.0016, zb + 0.0076)], [0.0, 0.0012, 0.0015, 0.0], W - 0.004, "polymer", re=0.0009, n=2, ne=1,
         M=Mb @ _Rx(0))
    if not lite:
        for k in range(3):                             # estrías de la lengüeta
            xk = D / 2 + o_b + 0.0042 - k * 0.0014
            plank(mb, (xk - 0.0004, -W / 2 + 0.004, zb - 0.0002), (xk + 0.0004, W / 2 - 0.004, zb + 0.0002), "polymer", ch=0.0002)
        # botón de retención de la base y nervio central
        revolve(mb, [(0.0, -0.0005), (0.0034, -0.0005), (0.0034, 0.0004), (0.0029, 0.0009), (0.0, 0.0009)], "polymer", seg=24,
                M=Mb @ _T(-D / 2 + 0.014, 0.0, zb) @ _Rx(180))
        plan(mb, [(-D / 2 + 0.022, -0.0015), (D / 2 - 0.006, -0.0015), (D / 2 - 0.006, 0.0015), (-D / 2 + 0.022, 0.0015)],
             [0.0, 0.001, 0.001, 0.0], 0.0007, "polymer", z0=-0.0004, re=0.0002, n=2, ne=1, M=Mb @ _T(0, 0, zb) @ _Rx(180))
    if inserted:
        return Mb
    # ---- labios de alimentación (mitad trasera) y cartuchos
    for sb in (-1, 1):
        cl = [(W / 2 - 0.0009, -0.0012), (W / 2 - 0.0010, 0.0016), (W / 2 - 0.0022, 0.0031), (W / 2 - 0.0048, 0.0034),
              (W / 2 - 0.0071, 0.0024)]
        o_ = 0.00062
        Pp = []
        for k, (b, z) in enumerate(cl):
            a0 = cl[max(k - 1, 0)]
            a1 = cl[min(k + 1, len(cl) - 1)]
            tb, tz = a1[0] - a0[0], a1[1] - a0[1]
            ln = math.hypot(tb, tz)
            nb_, nz_ = -tz / ln, tb / ln
            Pp.append((b + nb_ * o_, z + nz_ * o_))
        for k, (b, z) in reversed(list(enumerate(cl))):
            a0 = cl[max(k - 1, 0)]
            a1 = cl[min(k + 1, len(cl) - 1)]
            tb, tz = a1[0] - a0[0], a1[1] - a0[1]
            ln = math.hypot(tb, tz)
            nb_, nz_ = -tz / ln, tb / ln
            Pp.append((b - nb_ * o_, z - nz_ * o_))
        Pp = [(sb * b, z) for (b, z) in Pp]
        Rr = [0.0] * len(Pp)
        Pp, Rr = _ccw(Pp, Rr)
        La = 0.029
        Ml = M @ Matrix(((0, 0, 1, -D / 2 + 0.0016), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        pslab_n(mb, Ml, Pp, Rr, La, re=0.0006, mat="polymer", n=2, ne=1)
    sd = 1 if seed % 2 == 0 else -1
    round_556(mb, M @ _T(-D / 2 + 0.0022, sd * 0.0024, -0.0014) @ _Ry(90), seg=24, lite=lite)
    if not lite:
        round_556(mb, M @ _T(-D / 2 + 0.0022, -sd * 0.0026, -0.0056) @ _Ry(90), seg=24, lite=True)
    return Mb


def _drop(mb):
    """Traslada el MB para que su punto más bajo quede en z = 0."""
    z = min(v.co.z for v in mb.bm.verts)
    mb.transform(_T(0, 0, -z))
    return mb


def magazine(seed=0, lite=False):
    """Cargador curvo de polímero de 30 tiros, genérico (ver _mag; sección 63,5 × 23,5 mm, ~ 19 cm de alto), de pie sobre su
    base (inclinado hacia atrás lo que pide su curva, como queda parado en una mesa), con el cartucho superior a la vista
    entre los labios. lite = cargadores de exhibición en serie (menos estaciones, ~ 4-5 k triángulos; el completo ~ 9 k).
    Origen: x = 0 cara trasera de la boca (punto más atrasado), z = 0 apoyo de la base, y = 0 plano medio; el frente mira a
    +X; el centro de la base queda en x ~ 0,047 (huella total 88 × 27 mm, base 68 × 26 mm).
    Fuentes: en.wikipedia.org/wiki/STANAG_magazine ; magpul.com (PMAG 30 AR/M4 GEN M3: largo 7,5-7,6 in, ventana testigo,
    base con lengüeta); bigtexordnance.com/product/pmag-30-ar-m4-gen-m3-5-56x45mm-nato (proporciones)."""
    mb = MB()
    Mb = _mag(mb, Matrix(), lite=lite, seed=seed)
    inv = Mb.inverted()
    mb.transform(inv)                                   # base en el plano XY local, 'arriba' = +Z
    mb.transform(_T(-0.0012, 0, 0))
    x0 = min(v.co.x for v in mb.bm.verts)
    mb.transform(_T(-x0, 0, 0))                         # x = 0 cara trasera de la boca (como antes)
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
              (L * s / 2 - 0.0006, H - 0.002)], 0.0, W - 0.004, "cardboard", re=0.0004, n=1, ne=1)
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
            lot = ("LOT 275", "LOT 229", "LOT 312", "LOT 926")[int(r.integers(0, 4))]
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
_YZX = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))     # perfil en (Y, Z) extruido a lo largo de +X


def prism_x(mb, M, P, R, L, re=0.0004, mat="gunmetal", n=2, ne=1):
    """Prisma de perfil P [(y, z)] (filetes R) extruido a lo largo de X de 0 a L, cantos de los extremos re."""
    P, R = _ccw(P, R)
    return pslab_n(mb, M @ _YZX, P, R, L, re=re, mat=mat, n=n, ne=ne)


def pic_rail(mb, x0, x1, M=None, mat="gunmetal"):
    """Riel MIL-STD-1913 a lo largo de X local sobre el plano z = 0 (base embebida 1 mm): alma con flancos a 45° y cantos
    chaflanados, dientes de 4,78 mm a paso de 10,01 mm (ranuras de 5,23 mm, 3 mm de hondo) con chaflán en todas sus aristas;
    ancho 21,2 mm, alto 9,5 mm. Fuente: en.wikipedia.org/wiki/Picatinny_rail."""
    M = M if M is not None else Matrix()
    sp = [(-0.0078, -0.001), (0.0078, -0.001), (0.0078, 0.0028), (0.0106, 0.0056), (0.0106, 0.0062), (-0.0106, 0.0062),
          (-0.0106, 0.0056), (-0.0078, 0.0028)]
    prism_x(mb, M @ _T(x0, 0, 0), sp, [0.0, 0.0, 0.0009, 0.0009, 0.0, 0.0, 0.0009, 0.0009], x1 - x0, re=0.0008, mat=mat)
    th = [(-0.0104, 0.0059), (0.0104, 0.0059), (0.0106, 0.0068), (0.0091, 0.0083), (0.0091, 0.0095), (-0.0091, 0.0095),
          (-0.0091, 0.0083), (-0.0106, 0.0068)]
    pitch, tl = 0.01001, 0.00478
    n = max(1, int((x1 - x0 - tl - 0.001) / pitch) + 1)
    off = x0 + (x1 - x0 - (n - 1) * pitch - tl) / 2
    for k in range(n):
        prism_x(mb, M @ _T(off + k * pitch, 0, 0), th, [0.0, 0.0, 0.001, 0.001, 0.0009, 0.0009, 0.001, 0.001], tl, re=0.00035,
                mat=mat)


def rail(mb, x0, x1, z, mat="gunmetal", M=None, y=0.0):
    """Compatibilidad: riel 1913 a lo largo de X sobre el plano z (ver pic_rail)."""
    pic_rail(mb, x0, x1, (M if M is not None else Matrix()) @ _T(0, y, z), mat)


def mlok_tube(mb, x0, x1, a, t, rc, slot_fn, M=None, mat="gunmetal", nc=3, ch=0.0008, Lc=0.040, Ls=0.032, ws=0.007,
              rs=0.0024, e0=0.010):
    """Guardamanos flotante octagonal de aluminio a lo largo de X (eje en y = z = 0 local): 8 caras planas de apotema a con
    esquinas de radio rc, pared t, chaflán ch en las bocas y ranuras M-LOK pasantes (32 × 7 mm, esquinas de 2,4 mm, paso de
    40 mm) donde slot_fn(cara, celda) es verdadero; cara 0 = +Y (derecha), 2 = +Z (arriba), 4 = -Y, 6 = -Z. Malla soldada:
    cada ranura lleva un marco de caras hasta el borde de su celda, paredes interiores y las mismas columnas que las bandas
    de esquina. Fuente: en.wikipedia.org/wiki/M-LOK (ranura ~ 32 × 7 mm, separación 8 mm)."""
    V = {}

    def vert(p):
        key = (round(p[0], 7), round(p[1], 7), round(p[2], 7))
        v = V.get(key)
        if v is None:
            v = V[key] = mb.bm.verts.new((M @ Vector(p)) if M is not None else Vector(p))
        return v
    tq = math.tan(PI / 8)
    hw = (a - rc) * tq
    rci = max(rc - t, 0.0006)
    hwi = (a - t - rci) * tq
    ncell = max(0, int((x1 - x0 - 2 * e0) / Lc))
    xs0 = x0 + (x1 - x0 - ncell * Lc) / 2
    sl = rr_pts(Ls, ws, rs, 3)
    sl = list(reversed(sl)) if sum(sl[i][0] * sl[i - 1][1] - sl[i - 1][0] * sl[i][1] for i in range(len(sl))) > 0 else sl
    sl = list(reversed(sl))                                   # antihorario en (dx, v)
    # marco de la ranura: puntos del borde de la celda (normalizados) y esquinas insertadas
    ring = []
    for (dx, v) in sl:
        u, w = dx / (Ls / 2), v / (ws / 2)
        m = max(abs(u), abs(w))
        ring.append((u / m, w / m))
    frame = []                                                # por punto de la ranura: lista de puntos del borde (1 o 2)
    for i in range(len(ring)):
        u0, w0 = ring[i]
        u1, w1 = ring[(i + 1) % len(ring)]
        e0_ = "u" if abs(abs(u0) - 1) < 1e-9 else "w"
        e1_ = "u" if abs(abs(u1) - 1) < 1e-9 else "w"
        extra = []
        if e0_ != e1_:
            extra = [(math.copysign(1.0, u0 if e0_ == "u" else u1), math.copysign(1.0, w0 if e0_ == "w" else w1))]
        frame.append(extra)
    dxs = sorted({round(u * Lc / 2, 7) for (u, w) in ring if abs(abs(w) - 1) < 1e-9} | {-Lc / 2, Lc / 2})
    X = [x0, x0 + ch]
    for c in range(ncell):
        xc = xs0 + (c + 0.5) * Lc
        X += [xc + d for d in dxs]
    X += [x1 - ch, x1]
    X = _uniq(X, 1e-6)
    cells = [(xs0 + c * Lc, xs0 + (c + 1) * Lc) for c in range(ncell)]

    def cell_of(xa, xb):
        for c, (ca, cb) in enumerate(cells):
            if xa >= ca - 1e-7 and xb <= cb + 1e-7:
                return c
        return None

    def fpt(k, apo, x, v):
        th = k * PI / 4
        return (x, math.cos(th) * apo - math.sin(th) * v, math.sin(th) * apo + math.cos(th) * v)

    def arcpts(k, apo, rcc, x):
        thc = k * PI / 4 + PI / 8
        R0 = (apo - rcc) / math.cos(PI / 8)
        cy, cz = math.cos(thc) * R0, math.sin(thc) * R0
        return [(x, cy + rcc * math.cos(k * PI / 4 + PI / 4 * j / nc), cz + rcc * math.sin(k * PI / 4 + PI / 4 * j / nc))
                for j in range(1, nc)]
    F = mb.face
    for surf in ("o", "i"):
        hwx = hw if surf == "o" else hwi

        def apo_at(x):
            if surf == "i":
                return a - t
            return a - ch if (abs(x - x0) < 1e-9 or abs(x - x1) < 1e-9) else a

        def rc_at(x):
            if surf == "i":
                return rci
            return rc - ch if (abs(x - x0) < 1e-9 or abs(x - x1) < 1e-9) else rc
        for k in range(8):
            for i in range(len(X) - 1):
                xa, xb = X[i], X[i + 1]
                c = cell_of(xa, xb)
                if c is None or not slot_fn(k, c):
                    F([vert(fpt(k, apo_at(xa), xa, -hwx)), vert(fpt(k, apo_at(xb), xb, -hwx)), vert(fpt(k, apo_at(xb), xb, hwx)),
                       vert(fpt(k, apo_at(xa), xa, hwx))], mat)
                # banda de esquina hacia la cara k + 1
                ka = (k + 1) % 8
                ca = [vert(fpt(k, apo_at(xa), xa, hwx))] + [vert(p) for p in arcpts(k, apo_at(xa), rc_at(xa), xa)] + \
                    [vert(fpt(ka, apo_at(xa), xa, -hwx))]
                cb = [vert(fpt(k, apo_at(xb), xb, hwx))] + [vert(p) for p in arcpts(k, apo_at(xb), rc_at(xb), xb)] + \
                    [vert(fpt(ka, apo_at(xb), xb, -hwx))]
                for j in range(len(ca) - 1):
                    F([ca[j], cb[j], cb[j + 1], ca[j + 1]], mat)
            for c, (ca_, cb_) in enumerate(cells):
                if not slot_fn(k, c):
                    continue
                xc = (ca_ + cb_) / 2
                apo = a if surf == "o" else a - t
                inner = [vert(fpt(k, apo, xc + dx, v)) for (dx, v) in sl]
                outer = [vert(fpt(k, apo, xc + u * Lc / 2, w * hwx)) for (u, w) in ring]
                for i in range(len(sl)):
                    ii = (i + 1) % len(sl)
                    F([inner[i], inner[ii], outer[ii]] + [vert(fpt(k, apo, xc + u * Lc / 2, w * hwx)) for (u, w) in frame[i]] +
                      [outer[i]], mat)
    # paredes de las ranuras
    for k in range(8):
        for c, (ca_, cb_) in enumerate(cells):
            if not slot_fn(k, c):
                continue
            xc = (ca_ + cb_) / 2
            po = [vert(fpt(k, a, xc + dx, v)) for (dx, v) in sl]
            pi = [vert(fpt(k, a - t, xc + dx, v)) for (dx, v) in sl]
            for i in range(len(sl)):
                ii = (i + 1) % len(sl)
                F([po[i], pi[i], pi[ii], po[ii]], mat)
    # bocas
    for x in (x0, x1):
        lo, li = [], []
        for k in range(8):
            ka = (k + 1) % 8
            lo += [vert(fpt(k, a - ch, x, -hw)), vert(fpt(k, a - ch, x, hw))] + [vert(p) for p in arcpts(k, a - ch, rc - ch, x)]
            li += [vert(fpt(k, a - t, x, -hwi)), vert(fpt(k, a - t, x, hwi))] + [vert(p) for p in arcpts(k, a - t, rci, x)]
        for j in range(len(lo)):
            jj = (j + 1) % len(lo)
            F([lo[j], lo[jj], li[jj], li[j]], mat)


def revk(mb, prof, mat, seg=48, M=None, knurl=None, caps=True):
    """Torneado alrededor de Z local con moleteado recto: knurl = (n_dientes, hondo, {índices de anillo}); los anillos
    indicados llevan n estrías en V (seg = 2n). Perillas, tambores de torreta, tuercas de ajuste."""
    rings = []
    if knurl:
        nt, dp, idx = knurl
        seg = 2 * nt
    for i, (rr, z) in enumerate(prof):
        if rr < 1e-7:
            p = Vector((0.0, 0.0, z))
            rings.append([mb.bm.verts.new(M @ p if M is not None else p)])
            continue
        ring = []
        for k in range(seg):
            ang = 2 * PI * k / seg
            r_ = rr - (dp if (knurl and i in idx and k % 2) else 0.0)
            p = Vector((r_ * math.cos(ang), r_ * math.sin(ang), z))
            ring.append(mb.bm.verts.new(M @ p if M is not None else p))
        rings.append(ring)
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        if len(A) == 1 and len(B) == 1:
            continue
        for k in range(seg):
            kk = (k + 1) % seg
            if len(A) == 1:
                mb.face([A[0], B[kk], B[k]], mat)
            elif len(B) == 1:
                mb.face([A[k], A[kk], B[0]], mat)
            else:
                mb.face([A[k], A[kk], B[kk], B[k]], mat)
    if caps:
        if len(rings[0]) > 1:
            mb.face(list(reversed(rings[0])), mat)
        if len(rings[-1]) > 1:
            mb.face(rings[-1], mat)


def _knob_k(mb, M, r, h, mat="gunmetal", nt=24, dp=0.0005, cap=True, mark=None):
    """Perilla moleteada sobre z = 0 local (eje +Z): faldón liso, tambor moleteado, canto chaflanado, tapa con marca."""
    revk(mb, [(r * 0.86, -0.0003), (r * 0.94, 0.0), (r, h * 0.12), (r, h * 0.85), (r * 0.9, h), (0.0, h)] if cap else
         [(r * 0.86, -0.0003), (r * 0.94, 0.0), (r, h * 0.12), (r, h * 0.85), (r * 0.9, h)], mat, M=M, knurl=(nt, dp, {2, 3}),
         caps=False)
    if mark:
        plan(mb, [(0.0, -0.0004), (r * 0.7, -0.0004), (r * 0.7, 0.0004), (0.0, 0.0004)], 0.0, 0.0003, mark, z0=h - 0.0001,
             re=0.0, M=M)


def _screw_h(mb, M, d=0.004, mat="gunmetal", hexs=True, h=None):
    """Tornillo Allen de cabeza cilíndrica sobre z = 0 local: cabeza con chaflán y hexágono hundido (oscuro)."""
    h = h if h is not None else d * 0.55
    revolve(mb, [(d / 2 * 0.96, -0.0003), (d / 2, 0.0002), (d / 2, h * 0.8), (d / 2 * 0.88, h), (d * 0.3, h)], mat, seg=24, M=M,
            caps=False)
    if hexs:
        revolve(mb, [(d * 0.3, h), (d * 0.3, h - d * 0.25), (0.0, h - d * 0.3)], "cable", seg=6, M=M, caps=False)
    else:
        revolve(mb, [(d * 0.3, h), (0.0, h)], mat, seg=24, M=M, caps=False)


def _qd_swivel(mb, M, ang=0.0, mat="gunmetal"):
    """Argolla de correa desmontable (QD): copa del receptáculo, cuerpo con botón pulsador y asa de alambre en D.
    M: z local hacia fuera del montaje."""
    revolve(mb, [(0.0082, -0.0004), (0.0082, 0.0012), (0.0074, 0.0020), (0.0050, 0.0020), (0.0050, 0.0010), (0.0, 0.0010)],
            mat, seg=24, M=M, caps=False)
    revolve(mb, [(0.0058, 0.0010), (0.0062, 0.0030), (0.0062, 0.0085), (0.0055, 0.0095), (0.0032, 0.0098)], mat, seg=24, M=M,
            caps=False)
    revolve(mb, [(0.0032, 0.0092), (0.0030, 0.0118), (0.0026, 0.0123), (0.0, 0.0124)], "steel", seg=20, M=M, caps=False)
    Ml = M @ _T(0, 0, 0.0055) @ _Rz(ang)
    pts = []
    for k in range(13):                     # asa en D en el plano XZ local: pasa por el cuerpo y se abre hacia +Z
        a = PI * k / 12
        pts.append(Ml @ Vector((0.0145 * math.cos(a), 0.0, 0.006 + 0.0135 * math.sin(a) * 0.9)))
    pts += [Ml @ Vector((-0.0145 + 0.003, 0.0, 0.0)), Ml @ Vector((0.0145 - 0.003, 0.0, 0.0))]
    from kit.clinic_equipo import loop_tube
    with mb.soft():
        loop_tube(mb, pts, 0.0019, seg=12, mat="steel", normal=Ml.to_3x3() @ Vector((0, 1, 0)))


def _birdcage(mb, x, z, mat="gunmetal"):
    """Apagallamas de jaula (tipo A2: Ø 22 mm, 57 mm) sobre el eje (x, 0, z) hacia +X: collarín trasero con planos de
    llave, 5 ventanas arriba y a los costados, fondo cerrado (compensa el salto), anillo delantero con ánima y corona."""
    M = _ax(x, 0, z)                              # ángulo local: 0 = -Z (abajo)
    R = 0.011
    revolve(mb, [(0.0082, -0.0015), (0.0098, -0.0012), (R - 0.0004, 0.0), (R, 0.0006), (R, 0.0125), (0.0080, 0.0125)], mat,
            seg=32, M=M, caps=False)
    revolve(mb, [(0.0080, 0.0395), (R, 0.0395), (R, 0.0448), (R - 0.0009, 0.0458), (0.0058, 0.0458), (0.0045, 0.0450),
                 (0.0045, 0.040)], [mat] * 4 + ["cable"] * 2, seg=32, M=M, caps=False)
    revolve(mb, [(0.0045, 0.040), (0.0080, 0.0395)], "cable", seg=32, M=M, caps=False)
    w = 2 * PI / 6
    for k in range(6):                            # 5 barras entre ventanas + fondo cerrado ancho
        ac = k * w
        half = (w / 2 + 0.22) if k == 0 else 0.30
        arc_solid(mb, 0.0080, R - 0.0002, 0.0120, 0.0398, ac - half, ac + half, 6 if k == 0 else 3, mat, M=M)
    revolve(mb, [(0.0045, 0.0120), (0.0045, 0.0400)], "cable", seg=24, M=M, caps=False)


def _brake(mb, x, z, r=0.0122, mat="gunmetal"):
    """Freno de boca de 3 ventanas por costado (Ø 24 mm, 62 mm): collarín roscado, lomos superior e inferior corridos,
    deflectores laterales con canto chaflanado y cara frontal con corona; eje (x, 0, z) hacia +X."""
    M = _ax(x, 0, z)                              # ángulo local: 0 = -Z (abajo), π/2 = +Y, π = +Z, 3π/2 = -Y
    revolve(mb, [(0.0100, -0.002), (0.0112, -0.0015), (r - 0.0005, 0.0), (r, 0.0008), (r, 0.0115), (0.0072, 0.0115)], mat,
            seg=32, M=M, caps=False)
    for ac in (0.0, PI):                          # lomos
        arc_solid(mb, 0.0070, r - 0.0002, 0.0112, 0.0570, ac - 0.62, ac + 0.62, 6, mat, M=M)
    for (z0, z1) in ((0.0112, 0.0170), (0.0262, 0.0320), (0.0412, 0.0470)):
        for ac in (PI / 2, 1.5 * PI):             # deflectores laterales
            arc_solid(mb, 0.0070, r - 0.0004, z0, z1, ac - (PI / 2 - 0.58), ac + (PI / 2 - 0.58), 4, mat, M=M)
    revolve(mb, [(0.0070, 0.0565), (r, 0.0565), (r, 0.0605), (r - 0.0012, 0.062), (0.0052, 0.062), (0.0048, 0.0605),
                 (0.0048, 0.0565)], [mat] * 4 + ["cable"] * 2, seg=32, M=M, caps=False)
    revolve(mb, [(0.0048, 0.0565), (0.0070, 0.0565)], mat, seg=32, M=M, caps=False)
    revolve(mb, [(0.0040, 0.0115), (0.0040, 0.0565)], "cable", seg=24, M=M, caps=False)


def _buis(mb, x, zr, front=False, mat="gunmetal"):
    """Mira de respaldo abatible, plegada, sobre el riel (x = frente de la base, zr = cara superior del riel): base con
    abrazadera de cola de milano, tornillo moleteado al costado izquierdo, orejas protectoras, hoja plegada (trasera: con
    su abertura redonda; delantera: poste con su capuchón) sobre el pivote con resorte."""
    L = 0.036 if not front else 0.030
    xb = x - L
    # base y abrazadera (abraza el riel por los flancos)
    side(mb, [(xb, zr - 0.0055), (x, zr - 0.0055), (x, zr + 0.0045), (x - 0.004, zr + 0.0075), (xb + 0.003, zr + 0.0075),
              (xb, zr + 0.0045)], [0.001, 0.001, 0.0015, 0.0012, 0.0012, 0.0015], 0.0248, mat, re=0.0007, n=2, ne=1)
    for sy in (-1, 1):                            # labios de la cola de milano bajo los flancos del riel
        side(mb, [(xb + 0.001, zr - 0.0072), (x - 0.001, zr - 0.0072), (x - 0.001, zr - 0.0052), (xb + 0.001, zr - 0.0052)],
             [0.0008] * 4, 0.0030, mat, y0=sy * 0.0109, re=0.0004, n=2, ne=1)
    _knob_k(mb, _T(x - L / 2, -0.0124, zr - 0.0010) @ _Rx(90), 0.0052, 0.0045, mat, nt=20, dp=0.0004)
    revolve(mb, [(0.0028, 0.0), (0.0028, 0.0008)], mat, seg=16, M=_T(x - L / 2, 0.0124, zr - 0.0010) @ _Rx(-90))
    # orejas protectoras
    for sy in (-1, 1):
        side(mb, [(xb + 0.004, zr + 0.007), (x - 0.006, zr + 0.007), (x - 0.009, zr + 0.0135), (xb + 0.010, zr + 0.0135)],
             [0.0, 0.0, 0.0018, 0.0018], 0.0028, mat, y0=sy * 0.0105, re=0.0006, n=2, ne=1)
    # pivote y hoja plegada hacia atrás
    xp = x - 0.007
    revolve(mb, [(0.0022, -0.0092), (0.0022, 0.0092)], "steel", seg=16, M=_T(xp, 0, zr + 0.0098) @ _Rx(90))
    if not front:
        lf = MB()
        holed(lf, _T(0, 0, -0.0013), (0.0095, 0.0, 0.0135, 0.0080, 0.0022), (0.0175, 0.0, 0.0012, 0.0012, 0.0012), 0.0026,
              re_o=0.0006, re_i=0.0004, n=32, mat=mat, ne=1)
        revolve(lf, [(0.0034, 0.0012), (0.0034, 0.0022), (0.0026, 0.0026), (0.0013, 0.0026), (0.0012, 0.0012)], mat, seg=24,
                M=_T(0.0175, 0, 0), caps=False)
        mb.join(lf, _T(xp, 0, zr + 0.0098) @ _Rz(180))
    else:
        side(mb, [(xp - 0.022, zr + 0.0085), (xp + 0.002, zr + 0.0085), (xp + 0.002, zr + 0.0112), (xp - 0.020, zr + 0.0112)],
             [0.0015, 0.0015, 0.0015, 0.0015], 0.012, mat, re=0.0004, n=2, ne=1)
        for sy in (-1, 1):                        # alas del capuchón del poste (plegadas)
            side(mb, [(xp - 0.020, zr + 0.0095), (xp - 0.010, zr + 0.0095), (xp - 0.011, zr + 0.0140), (xp - 0.019, zr + 0.0140)],
                 [0.0, 0.0, 0.0012, 0.0012], 0.0018, mat, y0=sy * 0.0045, re=0.0004, n=2, ne=1)


def _lens(mb, M, r, depth, mat="glass", rim="gunmetal"):
    """Lente rehundida: anillo de retención oscuro y disco de vidrio ligeramente abombado a `depth` del borde (z = 0)."""
    revolve(mb, [(r, 0.0), (r * 0.94, -0.0006), (r * 0.94, -depth + 0.0004)], rim, seg=32, M=M, caps=False)
    revolve(mb, [(r * 0.94, -depth + 0.0004), (r * 0.6, -depth + 0.0002), (0.0, -depth + 0.0)], mat, seg=32, M=M, caps=False)


def _flip_cap(mb, M, r, ang=100.0, mat="polymer"):
    """Tapa de lente abatible (abierta `ang`°): aro elástico sobre el tubo (z local = eje óptico, hacia afuera), bisagra
    arriba y tapa con su lengüeta. M en la boca del tubo (se gira sobre su eje para que la bisagra quede arriba)."""
    up = M.to_3x3().inverted() @ Vector((0.0, 0.0, 1.0))
    M = M @ _Rz(math.degrees(math.atan2(up.y, up.x)) - 90.0)
    revolve(mb, [(r + 0.0002, -0.008), (r + 0.0016, -0.0075), (r + 0.0016, 0.0015), (r + 0.0002, 0.002)], mat, seg=32, M=M,
            closed=False, caps=False)
    zh = r + 0.0035
    revolve(mb, [(0.0024, -0.006), (0.0024, 0.006)], mat, seg=16, M=M @ _T(0, zh, 0.0012) @ _Ry(90))
    lid = MB()
    slab2(lid, Matrix(), 2 * r + 0.004, 2 * r + 0.004, 0.0028, r + 0.002, mat, re_t=0.001, ne_t=2, re_b=0.0006, ne_b=1, nc=6)
    side(lid, [(-0.006, -0.0005), (0.006, -0.0005), (0.0045, 0.0018), (-0.0045, 0.0018)], 0.0, 0.0050, mat, re=0.0, M=_Rx(0)
         @ _T(0, -(r + 0.006), 0) @ _Rz(0))
    lid.transform(_T(0, -zh, 0))
    mb.join(lid, M @ _T(0, zh, 0.0012) @ _Rx(-ang))


def _mount_base(mb, x0, x1, zr, ztop, w=0.024, mat="gunmetal", lever=False, bolts=(), nuts=True):
    """Base de montaje sobre riel 1913 (x0..x1, zr = cara superior del riel) hasta ztop: cuerpo con cantos redondeados,
    mordazas de cola de milano, tornillos transversales con tuerca (izq.) y cabeza (der.) o palanca de apriete rápido."""
    side(mb, [(x0, zr - 0.0052), (x1, zr - 0.0052), (x1, ztop - 0.002), (x1 - 0.003, ztop), (x0 + 0.003, ztop), (x0, ztop - 0.002)],
         [0.0012, 0.0012, 0.002, 0.002, 0.002, 0.002], w, mat, re=0.0012, n=2, ne=2)
    for sy in (-1, 1):
        side(mb, [(x0 + 0.0008, zr - 0.0074), (x1 - 0.0008, zr - 0.0074), (x1 - 0.0008, zr - 0.005), (x0 + 0.0008, zr - 0.005)],
             [0.0008] * 4, 0.0034, mat, y0=sy * (0.0108 + 0.0006), re=0.0004, n=2, ne=1)
    for xb in bolts:
        if nuts:
            hexnut(mb, _T(xb, -w / 2 + 0.0002, zr - 0.0025) @ _Rx(90), s=0.0095, h=0.004, mat=mat)
        _screw_h(mb, _T(xb, w / 2 - 0.0002, zr - 0.0025) @ _Rx(-90), d=0.0075, mat=mat)
    if lever:
        xl = (x0 + x1) / 2
        revolve(mb, [(0.0045, 0.0), (0.0045, 0.0025), (0.0038, 0.0032)], mat, seg=24, M=_T(xl, -w / 2 + 0.0002, zr - 0.0025) @
                _Rx(90))
        side(mb, [(xl - 0.004, zr - 0.006), (xl + 0.0035, zr - 0.006), (xl + 0.030, zr - 0.0035), (xl + 0.031, zr + 0.0005),
                  (xl + 0.003, zr + 0.001), (xl - 0.004, zr + 0.001)], [0.002, 0.002, 0.002, 0.002, 0.002, 0.002], 0.0028, mat,
             y0=-w / 2 - 0.0028, re=0.0008, n=2, ne=1)


def _ring(mb, x, zr, zo, ro, w=0.020, mat="gunmetal"):
    """Anillo de mira partido: cuerpo con 4 tornillos de tapa (2 por lado) sobre orejas, alrededor de un tubo de radio ro
    con eje a la altura zo; asentado en el riel (zr)."""
    rt = ro + 0.0032
    revolve(mb, [(ro + 0.0001, -w / 2), (rt - 0.0008, -w / 2), (rt, -w / 2 + 0.0008), (rt, w / 2 - 0.0008), (rt - 0.0008, w / 2),
                 (ro + 0.0001, w / 2)], mat, seg=40, M=_ax(x, 0, zo), closed=True)
    side(mb, [(x - w / 2, zr - 0.0052), (x + w / 2, zr - 0.0052), (x + w / 2, zo - ro * 0.6), (x - w / 2, zo - ro * 0.6)],
         [0.0012, 0.0012, 0.0, 0.0], 0.022, mat, re=0.0012, n=2, ne=2)
    for sy in (-1, 1):
        side(mb, [(x - w / 2 + 0.001, zo - 0.0035), (x + w / 2 - 0.001, zo - 0.0035), (x + w / 2 - 0.001, zo + 0.0030),
                  (x - w / 2 + 0.001, zo + 0.0030)], [0.0015] * 4, 0.0072, mat, y0=sy * (rt + 0.0012), re=0.0007, n=2, ne=1)
        for dx in (-w / 4, w / 4):
            _screw_h(mb, _T(x + dx, sy * (rt + 0.0012), zo + 0.0030), d=0.0042, mat=mat)
    hexnut(mb, _T(x, -0.011, zr - 0.0025) @ _Rx(90), s=0.0095, h=0.004, mat=mat)
    _screw_h(mb, _T(x, 0.011, zr - 0.0025) @ _Rx(-90), d=0.0075, mat=mat)


def _red_dot(mb, x, zr, mat="gunmetal"):
    """Mira de punto rojo de tubo (clase 30 mm, ~ 12 cm): cuerpo con capuchones de objetivo y ocular, lentes rehundidas,
    torretas de elevación (arriba) y deriva (derecha) con tapas moleteadas, perilla de intensidad / batería a la izquierda,
    tapas abatibles abiertas, anillo sobre base de palanca rápida. x = frente de la base, zr = cara superior del riel."""
    zo = zr + 0.039
    xb0 = x - 0.042
    _mount_base(mb, xb0, x, zr, zo - 0.0185, w=0.024, mat=mat, lever=True)
    _ring(mb, x - 0.021, zr, zo, 0.0160, w=0.026, mat=mat)
    x1, x0 = x + 0.040, x - 0.082                     # boca del objetivo / ocular
    prof = [(0.0172, 0.0), (0.0196, 0.0006), (0.0198, 0.0025), (0.0198, 0.0175), (0.0180, 0.0205), (0.0160, 0.0225),
            (0.0160, 0.1000), (0.0180, 0.1020), (0.0194, 0.1045), (0.0194, x1 - x0 - 0.0006), (0.0172, x1 - x0)]
    revolve(mb, prof, mat, seg=48, M=_ax(x0, 0, zo), caps=False)
    _lens(mb, _ax(x1, 0, zo), 0.0172, 0.007)
    _lens(mb, _ax(x0, 0, zo) @ _Rx(180), 0.0172, 0.007)
    xt = x - 0.030
    for (yy, zz, Mr) in ((0.0, 0.0160, Matrix()), (0.0160, 0.0, _Rx(-90))):
        revolve(mb, [(0.0118, -0.006), (0.0118, 0.0035), (0.0108, 0.0045)], mat, seg=40, M=_T(xt, yy, zo + zz) @ Mr, caps=False)
        _knob_k(mb, _T(xt, yy, zo + zz) @ Mr @ _T(0, 0, 0.0043), 0.0100, 0.0070, mat, nt=30, dp=0.0005, mark="sign_white")
    revolve(mb, [(0.0118, -0.006), (0.0118, 0.0035), (0.0108, 0.0045)], mat, seg=40, M=_T(xt, -0.0160, zo) @ _Rx(90), caps=False)
    _knob_k(mb, _T(xt, -0.0160, zo) @ _Rx(90) @ _T(0, 0, 0.0043), 0.0112, 0.0095, mat, nt=32, dp=0.0005, mark="sign_white")
    _flip_cap(mb, _ax(x1 - 0.002, 0, zo), 0.0196, ang=150.0)
    _flip_cap(mb, _ax(x0 + 0.002, 0, zo) @ _Rx(180), 0.0194, ang=150.0)


def _holo(mb, x, zr, mat="gunmetal"):
    """Mira holográfica de caja (~ 96 × 53 × 65 mm): base con abrazadera de tuerca moleteada, compartimiento de pila
    transversal con tapa moleteada, botones de hule traseros, capuchón de lámina en arco sobre la ventana (vidrio inclinado
    con su marco) y ventana trasera. x = frente de la base, zr = cara superior del riel."""
    xb0 = x - 0.096
    zt = zr + 0.0115                                  # cara superior de la base
    side(mb, [(xb0, zr - 0.0052), (x, zr - 0.0052), (x, zt - 0.003), (x - 0.004, zt), (xb0 + 0.004, zt), (xb0, zt - 0.004)],
         [0.0015, 0.0015, 0.004, 0.003, 0.003, 0.004], 0.034, mat, re=0.002, n=3, ne=2)
    for sy in (-1, 1):
        side(mb, [(xb0 + 0.010, zr - 0.0074), (xb0 + 0.050, zr - 0.0074), (xb0 + 0.050, zr - 0.005), (xb0 + 0.010, zr - 0.005)],
             [0.0008] * 4, 0.0034, mat, y0=sy * 0.0114, re=0.0004, n=2, ne=1)
    _knob_k(mb, _T(xb0 + 0.030, -0.0170, zr - 0.001) @ _Rx(90), 0.0085, 0.0085, mat, nt=28, dp=0.0006)
    _screw_h(mb, _T(xb0 + 0.030, 0.0170, zr - 0.001) @ _Rx(-90), d=0.007, mat=mat)
    # compartimiento de pila (transversal) al frente
    revolve(mb, [(0.0096, -0.0172), (0.0100, -0.0168), (0.0100, 0.0168), (0.0096, 0.0172)], mat, seg=40,
            M=_T(x - 0.012, 0, zt + 0.0042) @ _Rx(90))
    _knob_k(mb, _T(x - 0.012, 0.0172, zt + 0.0042) @ _Rx(-90), 0.0092, 0.0055, mat, nt=30, dp=0.0005)
    # botones traseros
    side(mb, [(xb0 - 0.0015, zt - 0.009), (xb0 + 0.002, zt - 0.009), (xb0 + 0.002, zt - 0.001), (xb0 - 0.0015, zt - 0.001)],
         [0.001] * 4, 0.026, mat, re=0.0006, n=2, ne=1)
    for yy in (-0.0065, 0.0065):
        revolve(mb, [(0.0, 0.0), (0.0034, 0.0), (0.0034, 0.0016), (0.0028, 0.0024), (0.0, 0.0026)], "rubber", seg=24,
                M=_T(xb0 - 0.0013, yy, zt - 0.005) @ _Ry(-90), caps=False)
    # capuchón: aro de lámina en arco (sección hueca) sobre la ventana
    xh0, xh1 = xb0 + 0.010, x - 0.026
    hood = MB()
    holed(hood, Matrix(), (0.0, 0.0, 0.0215, 0.0215, (0.0065, 0.0065, 0.002, 0.002)),
          (0.0, -0.0004, 0.0185, 0.0183, (0.004, 0.004, 0.0005, 0.0005)), xh1 - xh0, re_o=0.0012, re_i=0.0008, n=64, mat=mat, ne=2)
    mb.join(hood, _T(xh0, 0, zt + 0.0195) @ _Ry(90) @ _Rz(90))
    # ventana: vidrio inclinado con marco
    xw = xh0 + 0.032
    Mw = _T(xw, 0, zt + 0.019) @ _Ry(-8)
    side(mb, [(-0.0008, -0.0185), (0.0008, -0.0185), (0.0008, 0.0175), (-0.0008, 0.0175)], 0.0, 0.0374, "glass", re=0.0, M=Mw)
    for sy in (-1, 1):
        side(mb, [(-0.0022, -0.0185), (0.0022, -0.0185), (0.0022, 0.0175), (-0.0022, 0.0175)], [0.0008] * 4, 0.0024, mat,
             y0=sy * 0.0176, re=0.0004, n=2, ne=1, M=Mw)


def _scope(mb, x, zr, mat="gunmetal"):
    """Mira telescópica de aumento variable (clase 1-6 × 24, tubo de 30 mm, ~ 26 cm): objetivo con su lente, tubo, silla
    de torretas con elevación (arriba), deriva (derecha) e iluminación (izquierda) moleteadas con tapas, anillo de
    aumentos moleteado con palanca de giro, ocular con anillo de enfoque estriado y lente; tapas abatibles abiertas;
    montaje voladizo de una pieza con 2 anillos partidos (8 tornillos) y 2 tornillos transversales.
    x = frente del montaje sobre el riel, zr = cara superior del riel. Objetivo hacia +X."""
    zo = zr + 0.0385
    ro = 0.015
    xm0 = x - 0.110
    _mount_base(mb, xm0, x, zr, zo - 0.012, w=0.022, mat=mat, bolts=(xm0 + 0.025, x - 0.025))
    xa = x + 0.060                                    # cara del objetivo
    for pz in (0.068, 0.170):
        _ring(mb, xa - pz, zr, zo, ro, w=0.021, mat=mat)
    L = 0.262
    prof = [(0.0170, 0.0), (0.0178, 0.0008), (0.0178, 0.030), (0.0168, 0.034), (0.0152, 0.046), (0.0152, 0.085),
            (0.0168, 0.087), (0.0175, 0.090), (0.0175, 0.118), (0.0168, 0.121), (0.0152, 0.123), (0.0152, 0.168),
            (0.0168, 0.171), (0.0182, 0.174), (0.0182, 0.200), (0.0190, 0.214), (0.0218, 0.224), (0.0222, 0.228),
            (0.0222, L - 0.0008), (0.0212, L)]
    revolve(mb, prof, mat, seg=48, M=_T(xa, 0, zo) @ _Ry(-90), caps=False)
    revk(mb, [(0.0185, 0.176), (0.0185, 0.198)], mat, M=_T(xa, 0, zo) @ _Ry(-90), knurl=(40, 0.0006, {0, 1}), caps=False)
    revk(mb, [(0.0226, 0.232), (0.0226, 0.250)], mat, M=_T(xa, 0, zo) @ _Ry(-90), knurl=(44, 0.0007, {0, 1}), caps=False)
    _lens(mb, _ax(xa, 0, zo), 0.0170, 0.009)
    _lens(mb, _ax(xa - L, 0, zo) @ _Rx(180), 0.0212, 0.008)
    xt = xa - 0.104                                   # silla de torretas
    revolve(mb, [(0.0168, -0.016), (0.0175, -0.015), (0.0175, 0.015), (0.0168, 0.016)], mat, seg=48, M=_ax(xt - 0.0, 0, zo))
    xloft(mb, [(xt - 0.014, 0.034, 0.034, zo, 0.009), (xt + 0.014, 0.034, 0.034, zo, 0.009)], mat, n=4)
    for (yy, zz, Mr, rk, hk) in ((0.0, 0.017, Matrix(), 0.0125, 0.013), (0.017, 0.0, _Rx(-90), 0.0125, 0.011),
                                  (-0.017, 0.0, _Rx(90), 0.0110, 0.012)):
        Mt = _T(xt, yy, zo + zz) @ Mr
        revolve(mb, [(0.0105, -0.002), (0.0105, 0.004), (0.0118, 0.0045)], mat, seg=40, M=Mt, caps=False)
        _knob_k(mb, Mt @ _T(0, 0, 0.0042), rk, hk, mat, nt=36, dp=0.0006, mark="sign_white")
    xl = xa - 0.186                                   # palanca del anillo de aumentos
    side(mb, [(xl - 0.0045, zo + 0.017), (xl + 0.0045, zo + 0.017), (xl + 0.0035, zo + 0.032), (xl - 0.0035, zo + 0.032)],
         [0.0, 0.0, 0.0025, 0.0025], 0.0075, mat, re=0.0012, n=2, ne=1)
    _flip_cap(mb, _ax(xa - 0.002, 0, zo), 0.0178, ang=150.0)
    _flip_cap(mb, _ax(xa - L + 0.002, 0, zo) @ _Rx(180), 0.0222, ang=150.0)


# ======================================================================================================== fusil
# Plantilla de un fusil de sistema AR (calibre 5,56) en coordenadas del arma: x = 0 cantonera, z = 0 talón de la culata,
# ánima a z = RIFLE_BORE_Z. El DMR (calibre 7,62, receptores clase AR-10) usa el mismo grupo de receptores escalado 1,09
# alrededor de (0,262, 0, ánima).
_ZPL = -0.0115                      # línea de partición superior / inferior (relativa al ánima)
_ZB = -0.040                        # fondo del cajón inferior en la zona del disparador
_ZMW = -0.077                       # boca inferior del brocal
_XU0, _XU1 = 0.268, 0.452           # cajón superior
_RT = 0.031                         # cara superior del riel sobre el ánima (~ 1,215 in)


def _upper_sec(x, W=0.0300, zb=_ZPL + 0.0004, zt=0.0215, port=None):
    """Sección del cajón superior (y, z relativo al ánima), antihoraria vista desde +X; port = rebaje de la ventana de
    expulsión en el costado derecho (+Y) en esta estación (0..1)."""
    rt, rb = 0.0055, 0.0012
    pts = []
    zs = [zb + rb, -0.0085, -0.0080, 0.0080, 0.0085, zt - rt]
    for z in zs:                                            # costado derecho, de abajo hacia arriba
        dy = -0.0016 * port if (port and -0.0080 - 1e-9 <= z <= 0.0080 + 1e-9) else 0.0
        pts.append((W / 2 + dy, z))
    for k in range(1, 5):
        a = PI / 2 * k / 5
        pts.append((W / 2 - rt + rt * math.cos(a), zt - rt + rt * math.sin(a)))
    pts += [(W / 2 - rt, zt), (0.0, zt), (-W / 2 + rt, zt)]
    for k in range(1, 5):
        a = PI / 2 + PI / 2 * k / 5
        pts.append((-W / 2 + rt + rt * math.cos(a), zt - rt + rt * math.sin(a)))
    for z in reversed(zs):
        pts.append((-W / 2, z))
    for k in range(1, 3):
        a = PI + PI / 2 * k / 3
        pts.append((-W / 2 + rb + rb * math.cos(a), zb + rb + rb * math.sin(a)))
    pts += [(-W / 2 + rb, zb), (W / 2 - rb, zb)]
    for k in range(1, 3):
        a = 1.5 * PI + PI / 2 * k / 3
        pts.append((W / 2 - rb + rb * math.cos(a), zb + rb + rb * math.sin(a)))
    return pts


def _upper(mb, BZ, GM):
    """Cajón superior forjado: cuerpo con chaflanes en las bocas, ventana de expulsión rebajada con su tapa (nervio,
    bisagra y orejas), deflector de vainas, asistente de cierre inclinado con botón moleteado, riel corrido y palanca de
    carga en T con su seguro."""
    x0, x1 = _XU0, _XU1
    p0, p1 = 0.3830, 0.4370
    xs = [x0, x0 + 0.0009, x0 + 0.004, p0 - 0.0006, p0, p1, p1 + 0.0006, x1 - 0.004, x1 - 0.0009, x1]
    xs += [x0 + 0.02 * k for k in range(1, 10)]
    xs = [x for x in _uniq(xs) if x0 <= x <= x1]
    P = []
    for x in xs:
        pf = 1.0 if p0 <= x <= p1 else 0.0
        ins = 0.0009 if x in (x0, x1) else 0.0
        sec = _upper_sec(x, W=0.0300 - 2 * ins, zb=_ZPL + 0.0004 + ins, zt=0.0215 - ins, port=pf)
        P.append([(x, y, BZ + z) for (y, z) in sec])
    gridskin(mb, P, GM, cap0=True, cap1=True)
    pic_rail(mb, x0 + 0.002, x1 - 0.0015, M=_T(0, 0, BZ + 0.0215))
    # tapa de la ventana de expulsión (cerrada), nervio, bisagra y orejas
    yW = 0.0150
    side(mb, [(p0 + 0.0008, BZ - 0.0076), (p1 - 0.0008, BZ - 0.0076), (p1 - 0.0008, BZ + 0.0076), (p0 + 0.0008, BZ + 0.0076)],
         [0.0012] * 4, 0.0011, GM, y0=yW - 0.0007, re=0.0004, n=2, ne=1)
    side(mb, [(p0 + 0.006, BZ + 0.0030), (p1 - 0.006, BZ + 0.0030), (p1 - 0.006, BZ + 0.0052), (p0 + 0.006, BZ + 0.0052)],
         [0.0010] * 4, 0.0010, GM, y0=yW - 0.0001, re=0.0004, n=2, ne=1)
    side(mb, [(p0 + 0.003, BZ - 0.0062), (p0 + 0.008, BZ - 0.0062), (p0 + 0.008, BZ - 0.0030), (p0 + 0.003, BZ - 0.0030)],
         [0.0006] * 4, 0.0009, GM, y0=yW - 0.0002, re=0.0003, n=2, ne=1)        # pestaña del pestillo
    revolve(mb, [(0.0013, p0 - 0.004), (0.0013, p1 + 0.004)], "steel", seg=16, M=_T(0, yW - 0.0001, BZ - 0.0094) @ _Ry(90))
    for (xa, xb) in ((p0 - 0.0055, p0 - 0.0006), (p1 + 0.0006, p1 + 0.0055)):
        side(mb, [(xa, BZ - 0.0112), (xb, BZ - 0.0112), (xb, BZ - 0.0076), (xa, BZ - 0.0076)], [0.0008] * 4, 0.0028, GM,
             y0=yW + 0.0002, re=0.0005, n=2, ne=1)
    # deflector de vainas
    side(mb, [(0.3655, BZ + 0.0172), (0.3700, BZ + 0.0172), (0.3826, BZ + 0.0045), (0.3826, BZ - 0.0020), (0.3785, BZ - 0.0020)],
         [0.0015, 0.003, 0.002, 0.0012, 0.004], 0.0068, GM, y0=yW + 0.0022, re=0.0012, n=2, ne=2)
    # asistente de cierre: alojamiento inclinado, raíz con filete y botón moleteado
    pa, pb = Vector((0.360, 0.0095, BZ + 0.0035)), Vector((0.322, 0.0235, BZ + 0.0062))
    Mf, Lf = port.frame_on(pa, pb, up=(0, 0, 1))
    Mf = Mf @ _Ry(90)
    revolve(mb, [(0.0118, -0.004), (0.0104, 0.004), (0.0096, 0.010), (0.0096, Lf - 0.010), (0.0090, Lf - 0.009),
                 (0.0072, Lf - 0.009)], GM, seg=40, M=Mf, caps=False)
    revk(mb, [(0.0072, Lf - 0.0095), (0.0078, Lf - 0.0085), (0.0078, Lf + 0.0010), (0.0072, Lf + 0.0020), (0.0060, Lf + 0.0024),
              (0.0, Lf + 0.0021)], GM, M=Mf, knurl=(20, 0.0007, {1, 2}), caps=False)
    # palanca de carga en T (atrás, sobre el tubo del amortiguador) con seguro a la izquierda y estrías
    plan(mb, [(0.2575, -0.0212), (0.2640, -0.0212), (0.2690, -0.0080), (0.2690, 0.0080), (0.2640, 0.0212), (0.2575, 0.0212)],
         [0.0032, 0.0025, 0.002, 0.002, 0.0025, 0.0032], 0.0078, GM, z0=BZ + 0.0150, re=0.0016, n=3, ne=2)
    plan(mb, [(0.2688, -0.0055), (0.2780, -0.0055), (0.2780, 0.0055), (0.2688, 0.0055)], [0.0, 0.0012, 0.0012, 0.0], 0.0060,
         GM, z0=BZ + 0.0160, re=0.0008, n=2, ne=1)
    plan(mb, [(0.2585, -0.0275), (0.2635, -0.0275), (0.2648, -0.0205), (0.2585, -0.0190)], [0.0015, 0.0015, 0.001, 0.001],
         0.0050, GM, z0=BZ + 0.0165, re=0.0008, n=2, ne=1)                                   # seguro
    for k in range(4):
        y = -0.0185 + k * 0.0030
        for s in (-1, 1):
            prism_x(mb, _T(0.2569, s * y, BZ + 0.0168), [(-0.0005, 0.0), (0.0005, 0.0), (0.0005, 0.0046), (-0.0005, 0.0046)],
                    [0.0, 0.0, 0.0004, 0.0004], 0.0012, re=0.0002)


def _lower(mb, BZ, GM, mw0=0.382, seed=0):
    """Cajón inferior forjado: aro del tubo del amortiguador, cuerpo, brocal con su reborde y ensanche hueco, guardamonte
    integral, disparador curvo, pasadores de desarme / pivote y del mecanismo, selector, retén del cerrojo con su paleta
    estriada y su saliente, retén del cargador con guarda."""
    ZPL, ZB, ZMW = BZ + _ZPL, BZ + _ZB, BZ + _ZMW
    mw1 = 0.4535
    revolve(mb, [(0.0147, 0.2620), (0.0186, 0.2620), (0.0196, 0.2630), (0.0196, 0.2738), (0.0188, 0.2748), (0.0147, 0.2748)], GM,
            seg=48, M=_T(0, 0, BZ) @ _Ry(90), closed=True)
    side(mb, [(0.2722, ZPL), (0.2722, BZ - 0.018), (0.2785, BZ - 0.031), (0.2900, ZB), (0.3836, ZB), (0.3836, ZPL - 0.010),
              (0.4548, ZPL - 0.010), (0.4548, ZPL)], [0.0012, 0.006, 0.006, 0.003, 0.0, 0.0, 0.0015, 0.0015], 0.0248, GM,
         re=0.0012, n=3, ne=2)
    side(mb, [(mw0, ZMW + 0.0095), (mw1, ZMW + 0.0095), (mw1, ZPL - 0.0018), (mw0 + 0.004, ZPL - 0.0018), (mw0, ZPL - 0.006)],
         [0.0, 0.0, 0.003, 0.002, 0.003], 0.0305, GM, re=0.0012, n=3, ne=2)
    side(mb, [(mw0 + 0.010, ZPL - 0.0062), (mw1 - 0.001, ZPL - 0.0062), (mw1 - 0.001, ZPL - 0.0026), (mw0 + 0.010, ZPL - 0.0026)],
         [0.0008] * 4, 0.0320, GM, re=0.0006, n=2, ne=1)                                   # reborde superior del brocal
    cx = (mw0 + mw1) / 2
    holed(mb, _T(cx, 0, ZMW + 0.0098) @ _Rx(180), (0.0, 0.0, (mw1 - mw0) / 2 + 0.0016, 0.0170, 0.0045),
          (0.0, 0.0, (mw1 - mw0) / 2 - 0.0016, 0.0128, 0.0040), 0.0098, re_o=0.0018, re_i=0.0012, n=72, mat=GM, ne=2)
    # guardamonte integral
    strap(mb, fillet([(mw0 + 0.0015, 0.0, ZB + 0.002), (mw0 - 0.002, 0.0, ZB - 0.013), (mw0 - 0.010, 0.0, ZB - 0.0205),
                      (0.312, 0.0, ZB - 0.0210), (0.3045, 0.0, ZB - 0.012), (0.3010, 0.0, ZB + 0.0015)], 0.007, 4),
          0.0050, 0.0122, GM, up=(0, 1, 0), r=0.0019, n=2)
    # disparador
    side(mb, [(0.3330, ZB + 0.0035), (0.3405, ZB + 0.0035), (0.3420, ZB - 0.0055), (0.3400, ZB - 0.0120), (0.3372, ZB - 0.0158),
              (0.3352, ZB - 0.0150), (0.3366, ZB - 0.0108), (0.3370, ZB - 0.0060), (0.3352, ZB - 0.0005)],
         [0.0, 0.0, 0.004, 0.004, 0.0012, 0.0012, 0.004, 0.003, 0.0], 0.0058, GM, re=0.0008, n=3, ne=1)
    # pasadores: desarme / pivote (cabeza a la izq.), disparador / martillo
    for (xx, zz, r_h) in ((0.2828, ZPL - 0.0042, 0.0042), (0.4468, ZPL - 0.0048, 0.0042)):
        revolve(mb, [(0.0, -0.0128), (r_h - 0.0004, -0.0128), (r_h, -0.0131), (r_h, -0.0139), (r_h - 0.0008, -0.0145),
                     (0.0012, -0.0147), (0.0, -0.0145)], "steel", seg=24, M=_T(xx, 0, zz) @ _Rx(-90) @ _Rx(180), caps=False)
        revolve(mb, [(0.0, 0.0122), (0.0031, 0.0122), (0.0031, 0.0127), (0.0026, 0.0130), (0.0, 0.0130)], "steel", seg=20,
                M=_T(xx, 0, zz) @ _Rx(-90) @ _Rx(180), caps=False)
    for (xx, zz) in ((0.3375, BZ - 0.0300), (0.3220, BZ - 0.0228)):
        for s in (-1, 1):
            revolve(mb, [(0.0, 0.0), (0.0024, 0.0), (0.0024, 0.0003), (0.0019, 0.0006), (0.0, 0.0006)], "steel", seg=16,
                    M=_T(xx, s * 0.0121, zz) @ _Rx(-90 * s), caps=False)
    # selector (izq.) en SAFE, con su eje del lado derecho
    revolve(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0062, 0.0012), (0.0055, 0.0018), (0.0, 0.0018)], GM, seg=32,
            M=_T(0.3075, -0.0122, BZ - 0.0215) @ _Rx(90), caps=False)
    side(mb, [(0.3060, BZ - 0.0242), (0.3250, BZ - 0.0233), (0.3268, BZ - 0.0215), (0.3250, BZ - 0.0197), (0.3060, BZ - 0.0188)],
         [0.002, 0.0015, 0.0018, 0.0015, 0.002], 0.0024, GM, y0=-0.0122 - 0.0028, re=0.0007, n=2, ne=1)
    for k in range(3):
        xr = 0.3195 + k * 0.0022
        side(mb, [(xr, BZ - 0.0235), (xr + 0.0009, BZ - 0.0235), (xr + 0.0009, BZ - 0.0195), (xr, BZ - 0.0195)], [0.0004] * 4,
             0.0010, GM, y0=-0.0122 - 0.0043, re=0.0002, n=2, ne=1)
    revolve(mb, [(0.0, 0.0), (0.0040, 0.0), (0.0040, 0.0006), (0.0034, 0.0010), (0.0, 0.0010)], GM, seg=24,
            M=_T(0.3075, 0.0122, BZ - 0.0215) @ _Rx(-90), caps=False)
    # retén del cerrojo (izq.): saliente, palanca con paleta estriada y su pasador
    revolve(mb, [(0.0036, ZPL - 0.0010), (0.0036, ZPL - 0.0135), (0.0030, ZPL - 0.0145)], GM, seg=24, M=_T(mw0 - 0.0062, -0.0124, 0))
    side(mb, [(mw0 - 0.0108, ZPL - 0.0055), (mw0 - 0.0016, ZPL - 0.0055), (mw0 - 0.0016, ZB - 0.0030), (mw0 - 0.0050, ZB - 0.0052),
              (mw0 - 0.0110, ZB - 0.0050), (mw0 - 0.0112, ZB + 0.0060)], [0.001, 0.0012, 0.0015, 0.002, 0.0015, 0.003], 0.0022, GM,
         y0=-0.0124 - 0.0010, re=0.0006, n=2, ne=1)
    for k in range(3):
        zr_ = ZB - 0.0042 + k * 0.0026
        side(mb, [(mw0 - 0.0108, zr_), (mw0 - 0.0022, zr_), (mw0 - 0.0022, zr_ + 0.0010), (mw0 - 0.0108, zr_ + 0.0010)],
             [0.0004] * 4, 0.0009, GM, y0=-0.0124 - 0.0024, re=0.0002, n=2, ne=1)
    # retén del cargador (der.) con guarda en U
    xm_, zm_ = mw0 - 0.0045, BZ - 0.0335
    revolve(mb, [(0.0, 0.0), (0.0050, 0.0), (0.0052, 0.0006), (0.0052, 0.0020), (0.0046, 0.0026), (0.0, 0.0026)], GM, seg=32,
            M=_T(xm_, 0.0124, zm_) @ _Rx(-90), caps=False)
    for k in range(4):
        dz = -0.003 + k * 0.002
        hw_ = math.sqrt(max(0.0046 ** 2 - dz ** 2, 0.0)) * 0.9
        prism_x(mb, _T(xm_ - hw_, 0.0124 + 0.0024, zm_ + dz), [(-0.0002, -0.0004), (0.0004, -0.0004), (0.0004, 0.0004),
                                                                (-0.0002, 0.0004)], [0.0] * 4, 2 * hw_, re=0.0002)
    arc = [(xm_ + 0.0082 * math.cos(a), 0.0, zm_ + 0.0082 * math.sin(a)) for a in [PI * (1.08 + 0.84 * k / 10) for k in range(11)]]
    strap(mb, [(p[0], p[1] + 0.0124 + 0.0010, p[2]) for p in arc], 0.0020, 0.0030, GM, up=(0, 1, 0), r=0.0008)


def _grip(mb, BZ, F, seed=0):
    """Empuñadura de polímero (clase AR, 18-22°): lofts superelípticos con lomo, base de palma y ceja; costados con
    textura piramidal (rejilla 1,5 mm), frente con estrías horizontales y bulto del dedo medio, tapa inferior con su
    muesca y tornillo de sujeción oculto."""
    ZB = BZ + _ZB
    a = math.radians(21.0)
    p0 = Vector((0.2995, 0.0, ZB + 0.004))
    L = 0.112
    p1 = p0 + Vector((-math.sin(a), 0.0, -math.cos(a))) * L
    Mg, _ = port.frame_on(p0, p1, up=(1, 0, 0))             # x local: hacia abajo; z local: hacia el frente del arma
    st = [(0.000, 0.0250, 0.044, 0.0005), (0.006, 0.0272, 0.047, 0.0005), (0.016, 0.0292, 0.050, 0.0008),
          (0.030, 0.0304, 0.0515, 0.0016), (0.040, 0.0306, 0.0505, 0.0010), (0.052, 0.0310, 0.0505, 0.0004),
          (0.070, 0.0314, 0.0510, 0.0000), (0.090, 0.0312, 0.0505, -0.0006), (0.102, 0.0304, 0.0490, -0.0008),
          (0.109, 0.0296, 0.0475, -0.0008), (0.112, 0.0280, 0.0455, -0.0008)]

    def interp(x):
        for i in range(len(st) - 1):
            if st[i][0] <= x <= st[i + 1][0]:
                f = (x - st[i][0]) / (st[i + 1][0] - st[i][0])
                return [st[i][j] + (st[i + 1][j] - st[i][j]) * f for j in range(4)]
        return list(st[-1])
    g = 0.0015
    tx0, tx1 = 0.020, 0.100
    xs = [0.0, 0.003, 0.006, 0.010, 0.014] + [tx0 + g * k for k in range(int((tx1 - tx0) / g) + 1)] + [0.104, 0.108, 0.111, 0.112]
    xs = _uniq(xs)
    nseg = 72
    ex = 2.7
    P = []
    for i, x in enumerate(xs):
        _, w, h, zc = interp(x)
        row = []
        for k in range(nseg):
            t = 2 * PI * k / nseg
            c, s = math.cos(t), math.sin(t)
            yy = w / 2 * math.copysign(abs(c) ** (2 / ex), c)
            zz = zc + h / 2 * math.copysign(abs(s) ** (2 / ex), s)
            o = 0.0
            if tx0 <= x <= tx1:
                fx = min(1.0, (x - tx0) / 0.004, (tx1 - x) / 0.004)
                if abs(c) > 0.82 and abs(s) < 0.52:                   # costados: pirámides
                    o += 0.00038 * fx * (1.0 if (i + k) % 2 == 0 else 0.0)
                elif s > 0.86 and 0.028 <= x <= 0.096:                 # frente: estrías horizontales
                    o += 0.00045 * (1.0 if (i // 2) % 2 == 0 else 0.0)
            if 0.036 <= x <= 0.046 and s > 0.6:                        # bulto del dedo medio
                o += 0.0016 * math.sin(PI * (x - 0.036) / 0.010) * (s - 0.6) / 0.4
            ln = math.hypot(yy, zz - zc) or 1.0
            row.append((x, yy + yy / ln * o, zz + (zz - zc) / ln * o))
        P.append(row)
    gridskin(mb, P, F, M=Mg, cap0=False, cap1=True)
    # tapa inferior con muesca y ceja de la palma (beavertail) hacia el cajón
    slab2(mb, Mg @ _T(0.1118, 0, -0.0008) @ _Ry(90), 0.044, 0.026, 0.0022, 0.009, F, re_t=0.0008, ne_t=1, re_b=0.0, ne_b=0, nc=4)
    xloft(mb, [(0.2735, 0.0200, 0.010, ZB + 0.008, 0.0045), (0.280, 0.0240, 0.014, ZB + 0.004, 0.006),
               (0.296, 0.0250, 0.016, ZB + 0.002, 0.006), (0.302, 0.0220, 0.012, ZB + 0.004, 0.005)], F, n=4)


def _stock_ctr(mb, BZ, F):
    """Culata retráctil de polímero (genérica): cuerpo que envuelve el tubo, talón con almenas laterales, puntal inferior,
    palanca de ajuste con su pasador, copas QD a ambos costados y cantonera de hule con estrías. Ocupa x = 0..0,192."""
    xloft(mb, [(0.036, 0.0380, 0.044, BZ - 0.0015, 0.010), (0.046, 0.0425, 0.050, BZ - 0.0020, 0.0135),
               (0.168, 0.0425, 0.048, BZ - 0.0020, 0.0135), (0.184, 0.0405, 0.045, BZ - 0.0015, 0.012),
               (0.192, 0.0365, 0.040, BZ - 0.0010, 0.010)], F, n=5)
    xloft(mb, [(0.0125, 0.0440, 0.1262, 0.0655, 0.0095), (0.020, 0.0446, 0.1270, 0.0660, 0.0105),
               (0.034, 0.0440, 0.1230, 0.0670, 0.0105), (0.048, 0.0385, 0.0880, 0.0840, 0.0100),
               (0.058, 0.0360, 0.0560, 0.0985, 0.0100)], F, n=5)
    p0, p1 = Vector((0.026, 0.0, 0.020)), Vector((0.172, 0.0, BZ - 0.024))
    Ml, _ = port.frame_on(p0, p1, up=(0, 0, 1))
    port.loft(mb, [(0.0, 0.034, 0.030, 0.0), (0.018, 0.032, 0.024, 0.0), (0.060, 0.030, 0.0215, 0.0), (0.120, 0.030, 0.0215, 0.0),
                   (0.150, 0.032, 0.026, 0.002), (0.160, 0.030, 0.022, 0.003)], seg=32, mat=F, M=Ml, ex=2.8)
    # palanca de ajuste con pasador y estrías
    side(mb, [(0.128, BZ - 0.0300), (0.172, BZ - 0.0262), (0.176, BZ - 0.0225), (0.168, BZ - 0.0200), (0.128, BZ - 0.0222)],
         [0.003, 0.002, 0.002, 0.002, 0.003], 0.0120, F, re=0.0015, n=2, ne=2)
    revolve(mb, [(0.0, -0.0075), (0.0026, -0.0075), (0.0026, 0.0075), (0.0, 0.0075)], "steel", seg=16,
            M=_T(0.170, 0, BZ - 0.0222) @ _Rx(90))
    for k in range(4):
        xr = 0.134 + k * 0.0055
        side(mb, [(xr, BZ - 0.0306 + (xr - 0.128) * 0.085), (xr + 0.0018, BZ - 0.0306 + (xr - 0.126) * 0.085),
                  (xr + 0.0018, BZ - 0.0285), (xr, BZ - 0.0285)], [0.0006] * 4, 0.0100, F, re=0.0005, n=2, ne=1)
    # copas QD
    for s in (-1, 1):
        revolve(mb, [(0.0072, 0.0), (0.0072, 0.0012), (0.0062, 0.0018), (0.0046, 0.0018), (0.0046, 0.0004), (0.0, 0.0004)],
                ["steel", "steel", "steel", "steel", "cable"], seg=32, M=_T(0.064, s * 0.0210, BZ - 0.004) @ _Rx(-90 * s), caps=False)
    # cantonera de hule con estrías
    xloft(mb, [(0.0, 0.0418, 0.1300, 0.0660, 0.0110), (0.0022, 0.0460, 0.1340, 0.0660, 0.0130),
               (0.0130, 0.0460, 0.1340, 0.0660, 0.0130)], "rubber", n=5)
    for k in range(10):
        zr_ = 0.012 + k * 0.0115
        prism_x(mb, _T(-0.0007, 0, zr_), [(-0.0165, -0.0014), (0.0165, -0.0014), (0.0165, 0.0014), (-0.0165, 0.0014)],
                [0.0013] * 4, 0.0012, re=0.0003, mat="rubber")


def _stock_fixed(mb, BZ, F):
    """Culata fija de precisión (genérica): cuerpo de polímero de cantos redondeados con gancho inferior para la mano de
    apoyo, carrillera ajustable sobre 2 postes con perilla moleteada, 2 espaciadores de largo de tiro, cantonera de hule
    estriada, copas QD y riel inferior corto para monópode. Ocupa x = 0..0,262."""
    P = [(0.0185, 0.0040), (0.068, 0.0030), (0.080, 0.016), (0.090, 0.034), (0.118, BZ - 0.052), (0.170, BZ - 0.034),
         (0.2625, BZ - 0.0195), (0.2625, BZ + 0.0145), (0.0185, BZ + 0.0145)]
    side(mb, P, [0.003, 0.010, 0.014, 0.016, 0.025, 0.020, 0.004, 0.004, 0.003], 0.0400, F, re=0.0055, n=4, ne=3)
    xloft(mb, [(0.050, 0.0300, 0.016, BZ + 0.0245, (0.007, 0.007, 0.002, 0.002)),
               (0.058, 0.0360, 0.020, BZ + 0.0265, (0.009, 0.009, 0.002, 0.002)),
               (0.168, 0.0360, 0.020, BZ + 0.0265, (0.009, 0.009, 0.002, 0.002)),
               (0.178, 0.0300, 0.016, BZ + 0.0245, (0.007, 0.007, 0.002, 0.002))], F, n=4)
    for xp in (0.078, 0.150):
        revolve(mb, [(0.0042, BZ + 0.0130), (0.0042, BZ + 0.0180)], "steel", seg=24, M=_T(xp, 0, 0))
    _knob_k(mb, _T(0.114, -0.0200, BZ + 0.002) @ _Rx(90), 0.0095, 0.0085, F, nt=24, dp=0.0007)
    for k, (x0_, x1_) in enumerate(((0.0130, 0.0157), (0.0157, 0.0187))):
        xloft(mb, [(x0_, 0.0430 - k * 0.0006, 0.1290, 0.0670, 0.010), (x1_, 0.0430 - k * 0.0006, 0.1290, 0.0670, 0.010)], F, n=4)
    xloft(mb, [(0.0, 0.0418, 0.1300, 0.0670, 0.0110), (0.0022, 0.0460, 0.1340, 0.0670, 0.0130),
               (0.0132, 0.0460, 0.1340, 0.0670, 0.0130)], "rubber", n=5)
    for k in range(10):
        zr_ = 0.013 + k * 0.0115
        prism_x(mb, _T(-0.0007, 0, zr_), [(-0.0165, -0.0014), (0.0165, -0.0014), (0.0165, 0.0014), (-0.0165, 0.0014)],
                [0.0013] * 4, 0.0012, re=0.0003, mat="rubber")
    for (xq, zq) in ((0.050, 0.024), (0.205, BZ - 0.012)):
        for s in (-1, 1):
            revolve(mb, [(0.0072, 0.0), (0.0072, 0.0012), (0.0062, 0.0018), (0.0046, 0.0018), (0.0046, 0.0004), (0.0, 0.0004)],
                    ["steel", "steel", "steel", "steel", "cable"], seg=32, M=_T(xq, s * 0.0198, zq) @ _Rx(-90 * s), caps=False)
    pic_rail(mb, 0.026, 0.062, M=_T(0, 0, 0.0040) @ _Rx(180))


def _buffer_tube(mb, BZ, GM, x_end=0.036):
    """Tubo del amortiguador (Ø 1,148 in) con tapa trasera, nervio inferior con 6 barrenos de posición, tuerca castillo
    con 3 muescas y placa portafusil con receptáculo QD y argolla."""
    revolve(mb, [(0.0, x_end), (0.0120, x_end), (0.0140, x_end + 0.0012), (0.01458, x_end + 0.004), (0.01458, 0.2508)], GM, seg=48,
            M=_T(0, 0, BZ) @ _Ry(90), caps=False)
    prism_x(mb, _T(x_end + 0.006, 0, BZ - 0.0132), [(-0.0040, -0.0040), (0.0040, -0.0040), (0.0040, 0.0020), (-0.0040, 0.0020)],
            [0.0012, 0.0012, 0.0, 0.0], 0.2490 - x_end - 0.006, re=0.0012, mat=GM)
    for k in range(6):
        xh = 0.112 + k * 0.0163
        revolve(mb, [(0.0, 0.0), (0.0021, 0.0), (0.0021, 0.0007), (0.0026, 0.0010)], ["cable", GM, GM], seg=20,
                M=_T(xh, 0, BZ - 0.0172) @ _Rx(180) @ _T(0, 0, -0.0011), caps=False)
    nt = 3

    def notch(a):
        for j in range(nt):
            c = 2 * PI * j / nt + PI / 2
            d = (a - c + PI) % (2 * PI) - PI
            if abs(d) < 0.16:
                return 0.90
        return 1.0
    revolve(mb, [(0.0147, 0.2505), (0.0170, 0.2505), (0.0178, 0.2512), (0.0178, 0.2583), (0.0170, 0.2590), (0.0147, 0.2590)],
            GM, seg=96, M=_T(0, 0, BZ) @ _Ry(90), rmod=notch, closed=True)
    revolve(mb, [(0.0147, 0.2590), (0.0168, 0.2590), (0.0168, 0.2620), (0.0147, 0.2620)], GM, seg=48, M=_T(0, 0, BZ) @ _Ry(90),
            closed=True)
    side(mb, [(0.2590, BZ - 0.0228), (0.2620, BZ - 0.0228), (0.2620, BZ - 0.0120), (0.2590, BZ - 0.0120)], [0.0008] * 4, 0.0180,
         GM, re=0.0004, n=2, ne=1)
    revolve(mb, [(0.0058, 0.0), (0.0058, 0.0035)], GM, seg=32, M=_T(0.2605, -0.0160, BZ - 0.0060) @ _Rx(90), caps=True)
    _qd_swivel(mb, _T(0.2605, -0.0195, BZ - 0.0060) @ _Rx(90), ang=90.0)


def _bipod_folded(mb, x, zb, mat="gunmetal"):
    """Bípode plegado bajo el guardamanos (x = abrazadera, zb = cara inferior del guardamanos): abrazadera M-LOK con 2
    tornillos, cuerpo con eje de giro, 2 patas telescópicas plegadas hacia adelante con resortes, zapatas de hule."""
    side(mb, [(x - 0.022, zb - 0.0105), (x + 0.022, zb - 0.0105), (x + 0.022, zb + 0.0012), (x - 0.022, zb + 0.0012)],
         [0.003, 0.003, 0.0, 0.0], 0.0300, mat, re=0.0015, n=2, ne=2)
    for dx in (-0.012, 0.012):
        _screw_h(mb, _T(x + dx, 0, zb - 0.0105) @ _Rx(180), d=0.0055, mat=mat)
    revolve(mb, [(0.0050, -0.024), (0.0050, 0.024)], "steel", seg=24, M=_T(x + 0.010, 0, zb - 0.0170) @ _Rx(90))
    for s in (-1, 1):
        y = s * 0.0185
        side(mb, [(x + 0.002, zb - 0.0230), (x + 0.018, zb - 0.0230), (x + 0.018, zb - 0.0110), (x + 0.002, zb - 0.0110)],
             [0.003] * 4, 0.0070, mat, y0=y, re=0.0012, n=2, ne=1)
        xs, xe = x + 0.012, x + 0.185
        revolve(mb, [(0.0068, 0.0), (0.0068, 0.110), (0.0060, 0.112)], mat, seg=32, M=_T(xs, y, zb - 0.0165) @ _Ry(90), caps=True)
        revolve(mb, [(0.0050, 0.108), (0.0050, xe - xs - 0.016)], "steel", seg=32, M=_T(xs, y, zb - 0.0165) @ _Ry(90), caps=False)
        revolve(mb, [(0.0, -0.0005), (0.0062, 0.0), (0.0075, 0.006), (0.0075, 0.016), (0.0060, 0.020), (0.0, 0.021)], "rubber",
                seg=32, M=_T(xe - 0.016, y, zb - 0.0165) @ _Ry(90), caps=False)
        pts = []
        for k in range(14 * 6 + 1):                                  # resorte de retorno (alambre de 1,2 mm)
            t = k / (14 * 6)
            a_ = 2 * PI * 14 * t
            pts.append((x + 0.004 + 0.034 * t, y + 0.0035 * math.cos(a_) * s, zb - 0.0060 + 0.0035 * math.sin(a_)))
        mb.tube(pts, 0.0006, seg=8, mat="steel", caps=False)


def rifle(seed=0, kind="assault", sling=False, mag=True):
    """Fusil de asalto genérico de cerrojo rotativo y toma de gases (sistema AR, aspecto militar actual, no réplica).
    kind: «carbine» (cañón 368 mm, guardamanos de 305 mm, punto rojo de tubo), «assault» (cañón 420 mm, guardamanos de 381
    mm, mira holográfica de caja), «dmr» (cañón 508 mm, receptores clase 7,62 escalados 1,09, culata fija de precisión,
    mira 1-6× en montaje voladizo, freno de boca, bípode plegado, cargador recto de 20). Construcción (ver cada función):
    cajón superior (_upper) con ventana de expulsión, tapa, deflector, asistente de cierre y palanca de carga; cajón inferior
    (_lower) con brocal y su ensanche hueco, guardamonte, disparador, pasadores, selector, retenes; empuñadura texturizada
    (_grip); culata retráctil (_stock_ctr) sobre tubo del amortiguador con tuerca castillo y placa portafusil, o fija
    (_stock_fixed); guardamanos octagonal M-LOK (mlok_tube) con riel 1913 corrido; cañón con bloque y tubo de gases;
    apagallamas de jaula (_birdcage) o freno (_brake); miras de respaldo plegadas (_buis); óptica; argollas QD; cargador
    (_mag, insertado). Metal «gunmetal»; muebles en polímero negro (semilla par) o arena (impar).
    ORIGEN: x = 0 cara de la cantonera, z = 0 talón inferior de la culata, y = 0 plano de simetría; cañón hacia +X, arriba
    +Z. Eje del ánima a z = RIFLE_BORE_Z = 0,102 m; largo total RIFLE_LEN[kind]; empuñadura y cargador bajan de z = 0 (hasta
    ~ -0,09 m). Para un armero: la cantonera apoya en x = 0 y el guardamanos se sujeta a ~ 0,6-0,8 m.
    Fuentes: en.wikipedia.org/wiki/M4_carbine (838 mm, cañón 368 mm); en.wikipedia.org/wiki/M16_rifle (M16A4 cañón 508 mm);
    en.wikipedia.org/wiki/M110_semi-automatic_sniper_system (1029 mm, cañón 508 mm); en.wikipedia.org/wiki/Picatinny_rail;
    en.wikipedia.org/wiki/M-LOK (ranuras 32 × 7 mm a paso de 40 mm); forum.308ar.com/topic/23364 (riel ~ 1,215 in sobre el
    ánima en AR-15); tubo del amortiguador Ø 1,148 in (especificación militar); apagallamas A2 Ø 0,865 × 2,25 in."""
    mb = MB()
    kind = kind if kind in RIFLE_LEN else "assault"
    BZ = RIFLE_BORE_Z
    GM = "gunmetal"
    F = "polymer" if seed % 2 == 0 else "paint_tan"
    dmr = kind == "dmr"
    S = 1.09 if dmr else 1.0
    Lb, Lh, xgb = {"carbine": (0.368, 0.305, 0.608), "assault": (0.420, 0.381, 0.659), "dmr": (0.508, 0.381, 0.745)}[kind]
    # ---------------- grupo de receptores (coordenadas AR-15; el DMR se escala alrededor de (0,262, 0, ánima))
    rx = MB()
    mw0 = 0.3805 if dmr else 0.382
    _upper(rx, BZ, GM)
    _lower(rx, BZ, GM, mw0=mw0, seed=seed)
    _grip(rx, BZ, F, seed=seed)
    Ms = _T(0.262, 0, BZ) @ Matrix.Diagonal((S, S, S, 1.0)) @ _T(-0.262, 0, -BZ)
    mb.join(rx, Ms)
    xf = 0.262 + (_XU1 - 0.262) * S                 # cara delantera del cajón superior
    xbf = 0.262 + (0.430 - 0.262) * S               # cara del cerrojo
    zr = BZ + _RT * S                               # cara superior del riel
    # ---------------- culata
    if dmr:
        _stock_fixed(mb, BZ, F)
    else:
        _buffer_tube(mb, BZ, GM)
        _stock_ctr(mb, BZ, F)
    # ---------------- guardamanos, cañón, gases, boca
    a_hg = zr - 0.0095 - BZ
    xh0, xh1 = xf + 0.0006, xf + 0.0006 + Lh

    def slot_fn(k, c):
        if k in (0, 4, 6):
            return True
        if k in (5, 7):
            return c % 2 == 1
        return False
    mlok_tube(mb, xh0, xh1, a_hg, 0.0024, 0.0042, slot_fn, M=_T(0, 0, BZ), mat=GM)
    pic_rail(mb, xh0 + 0.0025, xh1 - 0.0025, M=_T(0, 0, BZ + a_hg))
    xm = xbf + Lb
    revolve(mb, [(0.0095, xf - 0.010), (0.0095, xgb + 0.020), (0.0093, xgb + 0.040), (0.0090, xm - 0.020), (0.0089, xm - 0.0008),
                 (0.0070, xm)], GM, seg=40, M=_T(0, 0, BZ) @ _Ry(90), caps=False)
    revolve(mb, [(0.0095, -0.0125), (0.0120, -0.0125), (0.0128, -0.0115), (0.0128, 0.0115), (0.0120, 0.0125), (0.0095, 0.0125)],
            GM, seg=40, M=_ax(xgb, 0, BZ), closed=True)
    for dx in (-0.006, 0.006):
        revolve(mb, [(0.0, 0.0), (0.0022, 0.0), (0.0022, 0.0004), (0.0, 0.0004)], "cable", seg=12,
                M=_T(xgb + dx, 0, BZ - 0.0127) @ _Rx(180), caps=False)
    with mb.soft():
        mb.tube([(xgb - 0.010, 0, BZ + 0.0123), (xf - 0.004, 0, BZ + 0.0123)], 0.0024, seg=12, mat="steel", caps=True)
    if dmr:
        _brake(mb, xm, BZ)
    else:
        _birdcage(mb, xm, BZ)
    # ---------------- miras y óptica
    if not dmr:
        _buis(mb, 0.306, zr)
        _buis(mb, xh1 - 0.004, zr, front=True)
    if kind == "carbine":
        _red_dot(mb, 0.410, zr)
    elif kind == "assault":
        _holo(mb, 0.448, zr)
    else:
        _scope(mb, 0.462, zr)
        _bipod_folded(mb, xh1 - 0.050, BZ - a_hg)
    # ---------------- argolla delantera (montaje M-LOK QD a la izquierda), cargador, correa
    xs = xh1 - 0.060
    plan(mb, [(-0.010, -0.0060), (0.010, -0.0060), (0.010, 0.0060), (-0.010, 0.0060)], [0.002] * 4, 0.0060, GM, z0=-0.0004,
         re=0.0012, n=2, ne=1, M=_T(xs, -a_hg, BZ) @ _Rx(90))
    _qd_swivel(mb, _T(xs, -a_hg - 0.0055, BZ) @ _Rx(90), ang=90.0)
    if mag:
        xmag = 0.262 + ((mw0 + 0.4535) / 2 - 0.262) * S
        _mag(mb, _T(xmag, 0, BZ - 0.018 * S), lite=True, inserted=True, cal="762" if dmr else "556", seed=seed)
    if sling:
        pts = [(xs, -0.031, BZ - 0.010), (xs - 0.03, -0.033, BZ - 0.060), (xs - 0.12, -0.034, BZ - 0.135), (0.45, -0.035, BZ - 0.165),
               (0.33, -0.035, BZ - 0.150), (0.28, -0.034, BZ - 0.090), (0.262, -0.031, BZ - 0.012)]
        path = spline(pts, 3)
        with mb.soft():
            strap(mb, path, 0.025, 0.0022, "canvas", up=(0, 1, 0), r=0.0009)
    return mb


# ======================================================================================================== pistola y funda
PISTOL_BORE_Z = 0.1135
_PS_ZB, _PS_ZT, _PS_W, _PS_L = 0.0985, 0.1270, 0.0255, 0.186     # corredera: fondo, lomo, ancho, largo


def tex_loft(mb, M, st, mat, nseg=64, ex=2.7, g=0.0015, tx=(0.0, 0.0), dp=0.00035, ends=(), cap0=False, cap1=True):
    """Empuñadura por secciones superelípticas a lo largo de X local [(x, ancho_y, fondo_z, z_centro)] con textura
    piramidal (vértices alternos levantados dp en una rejilla de paso g) entre tx[0] y tx[1]; ends = estaciones extra."""
    def interp(x):
        for i in range(len(st) - 1):
            if st[i][0] <= x <= st[i + 1][0]:
                f = (x - st[i][0]) / (st[i + 1][0] - st[i][0])
                return [st[i][j] + (st[i + 1][j] - st[i][j]) * f for j in range(4)]
        return list(st[-1] if x > st[-1][0] else st[0])
    xs = [s[0] for s in st] + list(ends) + [tx[0] + g * k for k in range(int((tx[1] - tx[0]) / g) + 1)]
    xs = _uniq(xs)
    P = []
    for i, x in enumerate(xs):
        _, w, h, zc = interp(x)
        row = []
        for k in range(nseg):
            t = 2 * PI * k / nseg
            c, s = math.cos(t), math.sin(t)
            yy = w / 2 * math.copysign(abs(c) ** (2 / ex), c)
            zz = zc + h / 2 * math.copysign(abs(s) ** (2 / ex), s)
            o = 0.0
            if tx[0] < x < tx[1]:
                fx = min(1.0, (x - tx[0]) / 0.003, (tx[1] - x) / 0.003)
                o = dp * fx * (1.0 if (i + k) % 2 == 0 else 0.0)
            ln = math.hypot(yy, zz - zc) or 1.0
            row.append((x, yy + yy / ln * o, zz + (zz - zc) / ln * o))
        P.append(row)
    return gridskin(mb, P, mat, M=M, cap0=cap0, cap1=cap1)


def _slide_sec(W, zb, zt, port=0.0, ser=(0.0, 0.0)):
    """Sección de la corredera (y, z), antihoraria vista desde +X, con muestras para estrías y la ventana de expulsión.
    port: rebaje (m) del cuarto superior derecho; ser = (hondo de estría, desplazamiento x por curvatura) -> se aplica fuera."""
    pts = []
    zs_side = [zb + 0.0008, zb + 0.0030, zb + 0.0080, zt - 0.0110, zt - 0.0104, zt - 0.0062, zt - 0.0045]
    for z in zs_side:
        pts.append((W / 2, z, "R"))
    pts += [(W / 2 - 0.0005, zt - 0.0036, "C"), (W / 2 - 0.0028, zt - 0.0011, "C"), (W / 2 - 0.0042, zt - 0.0001, "C"),
            (W / 2 - 0.0050, zt, "T"), (0.0040, zt, "T"), (-0.0018, zt, "T"), (-0.0024, zt, "T"), (-0.0060, zt, "T"),
            (-W / 2 + 0.0050, zt, "T"), (-W / 2 + 0.0042, zt - 0.0001, "C"), (-W / 2 + 0.0028, zt - 0.0011, "C"),
            (-W / 2 + 0.0005, zt - 0.0036, "C")]
    for z in reversed(zs_side):
        pts.append((-W / 2, z, "L"))
    pts += [(-W / 2 + 0.0007, zb, "B"), (W / 2 - 0.0007, zb, "B")]
    return pts


def _pistol(mb, lite=False, F="polymer"):
    """Pistola de armazón de polímero y percutor lanzado, genérica (~ 190 × 133 × 31 mm, corredera 186 × 25,5 mm).
    Corredera en una rejilla (gridskin): chaflanes superiores, nariz redondeada, estrías curvas traseras y delanteras,
    ventana de expulsión rebajada con el capuchón del cañón y la cara de la recámara, extractor con su pasador, placa
    trasera, alza de cola de milano con muesca en U y 2 puntos blancos, guion con punto, boca con corona del cañón y guía
    del resorte. Armazón: guardapolvo con riel 1913 corto, guardamonte cuadrado con gancho, disparador con seguro de lámina,
    retén de corredera, palanca de desarme, retén del cargador estriado, pasadores, empuñadura texturizada (pirámides) con
    cola de castor y boca del cargador abocinada, base del cargador con lengüeta. lite = sin lo que tapa la funda."""
    BZ = PISTOL_BORE_Z
    GM = "gunmetal"
    W, zb, zt, L = _PS_W, _PS_ZB, _PS_ZT, _PS_L
    # ---------------- corredera
    e = 0.0004
    gr = [0.0110 + k * 0.0034 for k in range(8)]                     # estrías traseras
    gf = [] if lite else [0.1460 + k * 0.0034 for k in range(7)]       # delanteras
    xs = [0.0, 0.0006, 0.0018, 0.004, 0.083, 0.0836, 0.1338, 0.1344, 0.178, 0.1815, 0.1840, 0.1854, L]
    for g0 in gr + gf:
        xs += [g0, g0 + e, g0 + 0.0016 - e, g0 + 0.0016]
    xs += [0.02 * k for k in range(1, 9)]
    xs = _uniq(xs)
    zm, hz = (zb + zt - 0.006) / 2, (zt - 0.006 - zb) / 2
    P = []
    for x in xs:
        ins = {0.0: 0.0011, 0.0006: 0.0004, L: 0.0026, 0.1854: 0.0013, 0.1840: 0.0006, 0.1815: 0.0002}.get(round(x, 4), 0.0)
        pf = 1.0 if 0.0836 - 1e-9 <= x <= 0.1338 + 1e-9 else 0.0
        groove = any(g0 + e - 1e-9 <= x <= g0 + 0.0016 - e + 1e-9 for g0 in gr + gf)
        in_ser = (0.0105 <= x <= 0.0398) or (bool(gf) and 0.1455 <= x <= 0.1700)
        row = []
        for (y, z, fc) in _slide_sec(W, zb, zt):
            yy, zz, xx = y, z, x
            if ins:                                              # chaflán / nariz: contracción hacia el eje
                yy -= math.copysign(ins, y) if fc in ("R", "L", "C") else 0.0
                zz -= ins if fc in ("T", "C") else 0.0
                zz += ins * 0.6 if fc == "B" else 0.0
            if pf and ((fc == "T" and y > -0.0020) or (fc == "C" and y > 0) or (fc == "R" and z > zt - 0.0105)):
                yy -= 0.0024 if fc in ("R", "C") else 0.0
                zz -= 0.0024 if fc in ("T", "C") else 0.0
            if in_ser and fc in ("R", "L") and zb + 0.0029 <= z <= zt - 0.0061:
                xx = x + 0.0018 * ((z - zm) / hz) ** 2               # estrías curvas
                if groove:
                    yy -= math.copysign(0.0006, y)
            row.append((xx, yy, zz))
        P.append(row)
    gridskin(mb, P, GM, cap0=True, cap1=True)
    # capuchón del cañón en la ventana, cara de la recámara y extractor
    side(mb, [(0.0842, zt - 0.0120), (0.1332, zt - 0.0120), (0.1332, zt - 0.0007), (0.0842, zt - 0.0007)],
         [0.0, 0.0, 0.0008, 0.0008], 0.0138, GM, y0=0.0029, re=0.0006, n=2, ne=1)
    revolve(mb, [(0.0, 0.0), (0.0048, 0.0), (0.0048, 0.0004)], "cable", seg=24, M=_T(0.0842, 0, BZ) @ _Ry(-90), caps=False)
    side(mb, [(0.0700, zt - 0.0095), (0.0815, zt - 0.0095), (0.0822, zt - 0.0060), (0.0700, zt - 0.0060)],
         [0.0008, 0.0006, 0.0006, 0.0008], 0.0012, GM, y0=W / 2 + 0.0002, re=0.0004, n=2, ne=1)
    revolve(mb, [(0.0, 0.0), (0.0011, 0.0), (0.0011, 0.0004), (0.0, 0.0004)], "steel", seg=12,
            M=_T(0.0715, W / 2 + 0.0008, zt - 0.0078) @ _Rx(-90), caps=False)
    # placa trasera
    side(mb, [(-0.0008, zb + 0.0030), (0.0004, zb + 0.0030), (0.0004, zt - 0.0060), (-0.0008, zt - 0.0060)], [0.0006] * 4,
         0.0170, GM, re=0.0004, n=2, ne=1)
    # alza (cola de milano) con muesca en U y 2 puntos; guion con punto
    ya = 0.0105
    side(mb, [(0.0040, zt - 0.0012), (0.0150, zt - 0.0012), (0.0150, zt + 0.0018), (0.0128, zt + 0.0056), (0.0040, zt + 0.0056)],
         [0.0, 0.0, 0.0012, 0.0012, 0.0008], 0.0050, GM, y0=ya - 0.0025 - 0.0005, re=0.0005, n=2, ne=1)
    side(mb, [(0.0040, zt - 0.0012), (0.0150, zt - 0.0012), (0.0150, zt + 0.0018), (0.0128, zt + 0.0056), (0.0040, zt + 0.0056)],
         [0.0, 0.0, 0.0012, 0.0012, 0.0008], 0.0050, GM, y0=-ya + 0.0025 + 0.0005, re=0.0005, n=2, ne=1)
    side(mb, [(0.0040, zt - 0.0012), (0.0150, zt - 0.0012), (0.0150, zt + 0.0018), (0.0040, zt + 0.0018)],
         [0.0, 0.0, 0.0008, 0.0008], 0.0110, GM, re=0.0004, n=2, ne=1)
    for s in (-1, 1):
        revolve(mb, [(0.0, 0.0), (0.0011, 0.0), (0.0011, 0.0003), (0.0, 0.0004)], "sign_white", seg=16,
                M=_T(0.0040, s * 0.0058, zt + 0.0036) @ _Ry(-90), caps=False)
    if not lite:
        side(mb, [(0.1735, zt - 0.0010), (0.1795, zt - 0.0010), (0.1785, zt + 0.0048), (0.1748, zt + 0.0048)],
             [0.0, 0.0, 0.0008, 0.0008], 0.0034, GM, re=0.0005, n=2, ne=1)
        revolve(mb, [(0.0, 0.0), (0.0011, 0.0), (0.0011, 0.0003), (0.0, 0.0004)], "sign_white", seg=16,
                M=_T(0.1748, 0, zt + 0.0030) @ _Ry(-90), caps=False)
        # boca: corona del cañón (ánima oscura) y guía del resorte
        revolve(mb, [(0.0068, L - 0.003), (0.0068, L + 0.0002), (0.0060, L + 0.0008), (0.0048, L + 0.0008), (0.0045, L + 0.0004),
                     (0.0045, L - 0.004)], [GM, GM, GM, GM, "cable"], seg=32, M=_T(0, 0, BZ) @ _Ry(90), caps=False)
        revolve(mb, [(0.0, L - 0.003), (0.0045, L - 0.003)], "cable", seg=32, M=_T(0, 0, BZ) @ _Ry(90), caps=False)
        revolve(mb, [(0.0042, L - 0.003), (0.0042, L + 0.0004), (0.0030, L + 0.0006), (0.0030, L - 0.0005), (0.0, L - 0.0005)],
                ["cable", "cable", GM, GM], seg=24, M=_T(0, 0, BZ - 0.0122) @ _Ry(90), caps=False)
    # ---------------- armazón
    side(mb, [(-0.0045, 0.0912), (0.0040, 0.0992), (0.1805, 0.0992), (0.1825, 0.0968), (0.1805, 0.0868), (0.1080, 0.0862),
              (0.0640, 0.0862), (0.0300, 0.0862), (0.0100, 0.0880), (0.0000, 0.0880)],
         [0.003, 0.002, 0.0015, 0.002, 0.003, 0.0, 0.0, 0.0, 0.004, 0.003], 0.0236, F, re=0.0015, n=3, ne=2)
    if not lite:
        pic_rail(mb, 0.1360, 0.1770, M=_T(0, 0, 0.0868) @ _Rx(180), mat=F)
    strap(mb, fillet([(0.1080, 0.0, 0.0880), (0.1110, 0.0, 0.0640), (0.1105, 0.0, 0.0600), (0.1050, 0.0, 0.0583),
                      (0.0680, 0.0, 0.0583), (0.0600, 0.0, 0.0650)], 0.006, 4), 0.0060, 0.0112, F, up=(0, 1, 0), r=0.0018, n=2)
    side(mb, [(0.1098, 0.0610), (0.1128, 0.0618), (0.1132, 0.0592), (0.1102, 0.0584)], [0.0, 0.001, 0.001, 0.0], 0.0090, F,
         re=0.0006, n=2, ne=1)                                                          # gancho del guardamonte
    side(mb, [(0.0800, 0.0880), (0.0870, 0.0880), (0.0862, 0.0790), (0.0838, 0.0715), (0.0812, 0.0668), (0.0790, 0.0676),
              (0.0812, 0.0730), (0.0826, 0.0800)], [0.0, 0.0, 0.004, 0.003, 0.0012, 0.0012, 0.003, 0.004], 0.0072, F, re=0.0008,
         n=3, ne=1)                                                                    # disparador
    side(mb, [(0.0826, 0.0820), (0.0852, 0.0820), (0.0846, 0.0732), (0.0826, 0.0700), (0.0818, 0.0705), (0.0834, 0.0745)],
         [0.0, 0.0, 0.003, 0.001, 0.0, 0.003], 0.0022, GM, re=0.0003, n=2, ne=1)      # seguro de lámina
    # empuñadura texturizada
    a = math.radians(20.0)
    p0 = Vector((0.0405, 0.0, 0.0900))
    Lg = 0.0815
    p1 = p0 + Vector((-math.sin(a), 0.0, -math.cos(a))) * Lg
    Mg, _ = port.frame_on(p0, p1, up=(1, 0, 0))
    st = [(0.000, 0.0218, 0.042, 0.0005), (0.006, 0.0258, 0.0470, 0.0005), (0.014, 0.0288, 0.0495, 0.0005),
          (0.040, 0.0298, 0.0500, 0.0000), (0.068, 0.0300, 0.0495, -0.0005), (0.077, 0.0306, 0.0505, -0.0005),
          (0.0815, 0.0318, 0.0520, -0.0005)]
    tex_loft(mb, Mg, st, F, nseg=96, g=0.0013, tx=(0.014, 0.072), dp=0.00045, ends=(0.074, 0.079, 0.0805), cap0=True)
    # base del cargador con lengüeta delantera
    Mbp = Mg @ _T(Lg, 0, -0.0005) @ _Ry(90)
    slab2(mb, Mbp @ _T(0, 0, -0.0005), 0.0525, 0.0300, 0.0085, 0.010, F, re_t=0.0025, ne_t=2, re_b=0.0005, ne_b=1, nc=5)
    side(mb, [(-0.0012, 0.0012), (0.0040, 0.0012), (0.0040, 0.0078), (-0.0012, 0.0078)], [0.0, 0.0015, 0.0015, 0.0], 0.0200,
         F, re=0.0008, n=2, ne=1, M=Mbp @ _T(-0.0300, 0, 0))                           # lengüeta delantera de la base
    # retén del cargador (izq.), retén de corredera, palanca de desarme y pasadores
    side(mb, [(0.0598, 0.0770), (0.0660, 0.0770), (0.0660, 0.0840), (0.0598, 0.0840)], [0.0012] * 4, 0.0024, F,
         y0=-0.0136, re=0.0006, n=2, ne=1)
    for k in range(3):
        side(mb, [(0.0602, 0.0782 + k * 0.0020), (0.0656, 0.0782 + k * 0.0020), (0.0656, 0.0790 + k * 0.0020),
                  (0.0602, 0.0790 + k * 0.0020)], [0.0003] * 4, 0.0008, F, y0=-0.0150, re=0.0002, n=2, ne=1)
    side(mb, [(0.0360, 0.0918), (0.0640, 0.0918), (0.0662, 0.0945), (0.0640, 0.0968), (0.0370, 0.0962)],
         [0.001, 0.0015, 0.0012, 0.0015, 0.001], 0.0016, GM, y0=-0.0126, re=0.0004, n=2, ne=1)
    for s in (-1, 1):
        side(mb, [(0.0860, 0.0902), (0.0935, 0.0902), (0.0935, 0.0930), (0.0860, 0.0930)], [0.0008] * 4, 0.0012, GM,
             y0=s * 0.0124, re=0.0003, n=2, ne=1)
        for (xp, zp) in ((0.0738, 0.0915), (0.0995, 0.0938)):
            revolve(mb, [(0.0, 0.0), (0.0016, 0.0), (0.0016, 0.0003), (0.0, 0.0004)], "steel", seg=16,
                    M=_T(xp, s * 0.0117, zp) @ _Rx(-90 * s), caps=False)


def pistol(seed=0):
    """Pistola de servicio genérica (polímero + corredera de acero), ~ 190 mm de largo, 133 mm de alto, 31 mm de ancho
    (proporción de las pistolas de servicio de 9 mm). Ver _pistol (~ 20 k triángulos). ORIGEN: x = 0 trasera de la
    corredera, z = 0 base del cargador, y = 0 plano de simetría; cañón hacia +X (eje del ánima a z = PISTOL_BORE_Z
    respecto del armado, antes de bajar al apoyo).
    Fuentes: us.glock.com/en/Pistols/G17-Gen5-FS-US (202 × 139 × 34 mm, corredera 25,5 mm, cañón 114 mm) y eu.glock.com
    (G17 Gen5) como clase de proporción; en.wikipedia.org/wiki/Picatinny_rail."""
    mb = MB()
    _pistol(mb, F="polymer" if seed % 2 == 0 else "paint_tan")
    return _drop(mb)


def holster(seed=0):
    """Funda rígida de polímero moldeado con la pistola enfundada (pistol, versión sin lo que tapa la funda): concha de
    pared de 3 mm que copia corredera, guardapolvo y guardamonte (rejilla con nervio de moldeo sobre la corredera), boca
    con labio enrollado, capuchón de retención en U sobre la trasera de la corredera con pivotes y resortes, botón de
    liberación estriado, plataforma de montaje de cintura / MOLLE atornillada (4 tornillos Allen con arandela) con 2 cintas
    de 25 mm cosidas y presillas, barreno de drenaje en la punta. ORIGEN: punta inferior de la funda (z = 0), centrada en X e
    Y; la pistola va con la boca hacia -Z (de pie, como se porta) y la plataforma de montaje mira a +Y.
    Fuente de proporción: fundas rígidas de retención nivel 2 (safariland.com, modelos de servicio)."""
    mb = MB()
    F = "polymer" if seed % 2 == 0 else "paint_tan"
    _pistol(mb, lite=True, F="polymer")
    # concha: lazos exteriores / interiores a lo largo de X (boca abierta en x = 0,046; punta cerrada en x = 0,203)
    t = 0.0030

    def sec(x):
        top = _PS_ZT + 0.0035
        if x < 0.118:                                           # cubre el guardamonte
            bot = 0.0545 + 0.006 * max(0.0, min(1.0, (0.070 - x) / 0.022))
        else:
            bot = 0.0825 - 0.006 * max(0.0, min(1.0, (0.128 - x) / 0.010))
        w = 0.0345 if x < 0.190 else 0.0345 - (x - 0.190) * 0.25
        return w, top - bot, (top + bot) / 2
    xs = [0.046, 0.0475, 0.050, 0.060, 0.070, 0.080, 0.092, 0.104, 0.112, 0.118, 0.124, 0.128, 0.140, 0.160, 0.180, 0.190,
          0.196, 0.200, 0.2025, 0.2040]
    outer, inner = [], []
    for x in xs:
        w, h, zc = sec(x)
        rr = (0.010, 0.006, 0.006, 0.010)
        outer.append([(x, b, zc + a_) for (a_, b) in [(p[0], p[1]) for p in rr_pts(h, w, rr, 4)]])
        if x <= 0.199:
            inner.append([(x, b, zc + a_) for (a_, b) in rr_pts(h - 2 * t, w - 2 * t, (0.007, 0.003, 0.003, 0.007), 4)])
    inner[-1] = [(0.199, p[1], p[2]) for p in inner[-1]]
    # boca: labio enrollado (el lazo exterior en x = 0,046 se retrae; el interior también)
    gridskin(mb, list(reversed(inner)) + outer, F, cap0=True, cap1=True)
    # nervio de moldeo a lo largo de la corredera (ambos costados)
    for s in (-1, 1):
        prism_x(mb, _T(0.060, s * (0.0345 / 2 - 0.0003), _PS_ZT - 0.0080), [(-0.0008, -0.0016), (0.0008, -0.0016),
                (0.0008, 0.0016), (-0.0008, 0.0016)], [0.0007] * 4, 0.128, re=0.0012, mat=F)
    # capuchón de retención: arco en U sobre la trasera de la corredera, pivotes con resorte, botón estriado
    arc = [(0.024, 0.0205 * math.cos(tt), 0.1145 + 0.0215 * math.sin(tt)) for tt in [PI * k / 14 for k in range(15)]]
    path = [(0.054, 0.0205, 0.1055), (0.040, 0.0205, 0.1095), (0.030, 0.0205, 0.1125)] + arc + \
        [(0.030, -0.0205, 0.1125), (0.040, -0.0205, 0.1095), (0.054, -0.0205, 0.1055)]
    strap(mb, spline(path, 2), 0.0035, 0.0125, F, up=(1, 0, 0), r=0.0014, n=2)
    for s in (-1, 1):
        revolve(mb, [(0.0068, -0.0020), (0.0068, 0.0032), (0.0058, 0.0042), (0.0, 0.0045)], F, seg=32,
                M=_T(0.054, s * 0.0185, 0.1055) @ _Rx(-90 * s), caps=False)
        _screw_h(mb, _T(0.054, s * 0.0229, 0.1055) @ _Rx(-90 * s), d=0.0045, mat="steel")
    revk(mb, [(0.0074, -0.002), (0.0074, 0.0030), (0.0066, 0.0042), (0.0, 0.0046)], "rubber",
         M=_T(0.068, 0.0175, 0.1290) @ _Rx(-90) @ _Rx(0), knurl=(16, 0.0005, {0, 1}), caps=False)
    # plataforma de montaje en la espalda (-Y del arma; tras girar queda hacia +Y)
    side(mb, [(0.056, 0.064), (0.184, 0.064), (0.184, 0.140), (0.056, 0.140)], [0.012] * 4, 0.0060, F, y0=-0.0198, re=0.0022,
         n=4, ne=2)
    for (x, z) in ((0.072, 0.077), (0.168, 0.077), (0.072, 0.127), (0.168, 0.127)):
        revolve(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0062, 0.0008), (0.0, 0.0008)], "steel", seg=24, M=_T(x, -0.0228, z) @ _Rx(90),
                caps=False)
        _screw_h(mb, _T(x, -0.0236, z) @ _Rx(90), d=0.0080, mat="steel")
    for z in (0.0855, 0.1185):                                                        # cintas de 25 mm con costura
        prism_x(mb, _T(0.051, -0.0237, z), [(-0.0009, -0.0125), (0.0009, -0.0125), (0.0009, 0.0125), (-0.0009, 0.0125)],
                [0.0006] * 4, 0.138, re=0.0007, mat="canvas")
        for xs_ in (0.060, 0.120, 0.180):
            prism_x(mb, _T(xs_, -0.0248, z), [(-0.0003, -0.0105), (0.0003, -0.0105), (0.0003, 0.0105), (-0.0003, 0.0105)],
                    [0.0] * 4, 0.006, re=0.0001, mat="fabric")                        # presilla cosida (barra)
    revolve(mb, [(0.0034, 0.1985), (0.0034, 0.2045)], "cable", seg=16, M=_T(0, 0, 0.106) @ _Ry(90), caps=False)  # drenaje
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
                 (0.0075, 0.090), (0.0072, 0.099)], "brass", seg=24, M=M, caps=False)
    revolve(mb, [(0.0065, 0.098), (0.0065, 0.112), (0.0058, 0.120), (0.0046, 0.129), (0.0028, 0.136), (0.0, 0.140)], "copper", seg=24,
            M=M, caps=False)
    if link:                                    # eslabón: dos abrazaderas de fleje y lengüeta
        for zc in ((0.030, 0.064) if k % 2 == 0 else (0.047,)):          # eslabones alternados: 2 asas / 1 asa
            revolve(mb, [(0.0106, zc - 0.006), (0.0118, zc - 0.006), (0.0118, zc + 0.006), (0.0106, zc + 0.006)], "steel", seg=24,
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
    # ---------------- cajón: cuerpo de cantos redondeados, bloque del muñón al frente, banda trasera, placas laterales
    side(mb, [(xr0, zr0), (xr1, zr0), (xr1, zr1), (xr0, zr1)], [0.005] * 4, 0.100, GM, re=0.0030, n=3, ne=2)
    side(mb, [(xr1 - 0.078, zr0 - 0.004), (xr1 + 0.004, zr0 - 0.004), (xr1 + 0.004, zr1 - 0.006), (xr1 - 0.078, zr1 - 0.006)],
         [0.004] * 4, 0.1076, GM, re=0.0025, n=3, ne=2)                                # bloque del muñón
    side(mb, [(xr0 - 0.002, zr0 + 0.004), (xr0 + 0.030, zr0 + 0.004), (xr0 + 0.030, zr1 - 0.004), (xr0 - 0.002, zr1 - 0.004)],
         [0.004] * 4, 0.1060, GM, re=0.0020, n=3, ne=2)                                # banda de la placa trasera
    for sy in (-1, 1):                           # placas laterales y filas de remaches
        side(mb, [(xr0 + 0.034, zr0 + 0.010), (xr1 - 0.082, zr0 + 0.010), (xr1 - 0.082, zr1 - 0.040), (xr0 + 0.034, zr1 - 0.040)],
             [0.004] * 4, 0.0030, GM, y0=sy * 0.0512, re=0.0009, ne=1, n=2)
        for xx in [xr0 + 0.046 + k * 0.0494 for k in range(9)]:
            for zz in (zr0 + 0.020, zr1 - 0.050):
                rivet(mb, _T(xx, sy * 0.0526, zz) @ _Rx(-90 * sy), d=0.0085, seg=16)
        for xx in (xr1 - 0.064, xr1 - 0.040, xr1 - 0.016):
            for zz in (zr0 + 0.016, (zr0 + zr1) / 2 - 0.010, zr1 - 0.030):
                rivet(mb, _T(xx, sy * 0.0538, zz) @ _Rx(-90 * sy), d=0.0095, seg=16)
        prism_x(mb, _T(xr0 + 0.030, sy * 0.0500, zr0 + 0.0045), [(-0.0012, -0.0008), (0.0012, -0.0008), (0.0012, 0.0008),
                (-0.0012, 0.0008)], [0.0006] * 4, xr1 - xr0 - 0.108, re=0.0006, mat=GM)  # costura de la placa inferior
    # ventana de alimentación (izq.) y de expulsión de eslabones (der.): marco y fondo oscuro
    for (sy, x0_, x1_, z0_, z1_) in ((-1, -0.108, 0.022, BZ - 0.016, BZ + 0.034), (1, -0.090, 0.004, BZ - 0.018, BZ + 0.010)):
        holed(mb, _T((x0_ + x1_) / 2, sy * 0.0500, (z0_ + z1_) / 2) @ _Rx(-90 * sy), (0.0, 0.0, (x1_ - x0_) / 2 + 0.006,
              (z1_ - z0_) / 2 + 0.006, 0.006), (0.0, 0.0, (x1_ - x0_) / 2, (z1_ - z0_) / 2, 0.003), 0.0035, re_o=0.0012,
              re_i=0.0008, n=48, mat=GM, ne=1)
        side(mb, [(x0_ + 0.001, z0_ + 0.001), (x1_ - 0.001, z0_ + 0.001), (x1_ - 0.001, z1_ - 0.001), (x0_ + 0.001, z1_ - 0.001)],
             [0.0025] * 4, 0.0012, "cable", y0=sy * 0.0498, re=0.0, n=2)
    # tapa de alimentación con bisagra delantera, cerrojo trasero y nervios redondeados
    xloft(mb, [(-0.212, 0.096, 0.020, zr1 + 0.007, (0.006, 0.006, 0.0, 0.0)), (-0.205, 0.103, 0.025, zr1 + 0.0095, (0.008, 0.008, 0.0, 0.0)),
               (0.102, 0.103, 0.025, zr1 + 0.0095, (0.008, 0.008, 0.0, 0.0)), (0.110, 0.096, 0.020, zr1 + 0.007, (0.006, 0.006, 0.0, 0.0))],
          GM, n=5)
    revolve(mb, [(0.0080, -0.050), (0.0085, -0.049), (0.0085, 0.049), (0.0080, 0.050)], GM, seg=SEG, M=_T(0.112, 0, zr1 + 0.006) @ _Rx(90))
    for sy in (-1, 1):
        revolve(mb, [(0.0, 0.0), (0.0058, 0.0), (0.0058, 0.0025), (0.0048, 0.0035), (0.0, 0.0038)], "steel", seg=SEG,
                M=_T(0.112, sy * 0.050, zr1 + 0.006) @ _Rx(-90 * sy), caps=False)
    side(mb, [(-0.238, zr1 + 0.002), (-0.205, zr1 + 0.002), (-0.205, zr1 + 0.027), (-0.214, zr1 + 0.030), (-0.231, zr1 + 0.022)],
         [0.0, 0.0, 0.004, 0.004, 0.005], 0.030, GM, re=0.0018, ne=2, n=3)            # cerrojo de la tapa
    for k in range(4):
        side(mb, [(-0.236 + k * 0.006, zr1 + 0.024 - k * 0.002), (-0.234 + k * 0.006, zr1 + 0.024 - k * 0.002),
                  (-0.234 + k * 0.006, zr1 + 0.027 - k * 0.002), (-0.236 + k * 0.006, zr1 + 0.027 - k * 0.002)],
             [0.0005] * 4, 0.026, GM, re=0.0004, n=2, ne=1)
    for xx in (-0.15, -0.08, -0.01, 0.06):                    # nervaduras de la tapa
        prism_x(mb, _T(xx - 0.005, 0, zr1 + 0.0215), [(-0.044, 0.0), (0.044, 0.0), (0.043, 0.0035), (-0.043, 0.0035)],
                [0.0, 0.0, 0.0015, 0.0015], 0.010, re=0.0025, mat=GM)
    # alza de hoja plegada (atrás) con base, tambor de deriva moleteado y hoja con su abertura
    side(mb, [(-0.398, zr1 - 0.001), (-0.335, zr1 - 0.001), (-0.335, zr1 + 0.010), (-0.343, zr1 + 0.013), (-0.398, zr1 + 0.013)],
         [0.0, 0.0, 0.003, 0.003, 0.003], 0.040, GM, re=0.0018, ne=2, n=3)
    for sy in (-1, 1):
        _knob_k(mb, _T(-0.360, sy * 0.020, zr1 + 0.008) @ _Rx(-90 * sy), 0.0090, 0.0075, GM, nt=24, dp=0.0006)
    lf = MB()
    holed(lf, Matrix(), (0.045, 0.0, 0.047, 0.012, 0.004), (0.080, 0.0, 0.0018, 0.0018, 0.0018), 0.0028, re_o=0.0008, re_i=0.0004,
          n=40, mat=GM, ne=1, ctr=(0.080, 0.0))
    mb.join(lf, _T(-0.345, 0, zr1 + 0.0135) @ _Rz(180))
    # placa trasera con canto redondeado, empuñaduras de pala (marcos y hule de dedos), gatillo de mariposa y botón
    side(mb, [(xr0 - 0.036, zr0 - 0.002), (xr0 + 0.001, zr0 - 0.002), (xr0 + 0.001, zr1 + 0.004), (xr0 - 0.036, zr1 + 0.002)],
         [0.010, 0.004, 0.004, 0.010], 0.110, GM, re=0.0040, n=3, ne=2)
    revolve(mb, [(0.0, 0.0), (0.0075, 0.0), (0.0075, 0.004), (0.0065, 0.0055), (0.0, 0.006)], GM, seg=SEG,
            M=_T(xr0 - 0.020, 0, zr1 + 0.002), caps=False)                         # liberador del cerrojo
    for sy in (-1, 1):
        y = sy * 0.042
        p0 = Vector((xr0 - 0.030, y, zr0 + 0.034))
        p1 = Vector((xr0 - 0.150, sy * 0.048, zr0 + 0.016))
        side(mb, [(xr0 - 0.040, zr0 + 0.020), (xr0 - 0.034, zr0 + 0.020), (xr0 - 0.066, zr0 + 0.046), (xr0 - 0.072, zr0 + 0.040)],
             [0.003] * 4, 0.012, GM, y0=y, re=0.0015, n=2, ne=1)                # marco de la empuñadura
        wire(mb, [tuple(p0), (xr0 - 0.062, y, zr0 + 0.030), tuple(p1)], 0.0105, GM, bend=0.02, nseg=5, seg=SEG)
        Mg, L = port.frame_on(Vector((xr0 - 0.068, sy * 0.0445, zr0 + 0.0255)), p1)
        prof = [(0.0115, -0.002), (0.0140, 0.004)]
        for k in range(4):
            z0 = 0.010 + k * (L - 0.024) / 4
            prof += [(0.0152, z0 + 0.004), (0.0160, z0 + 0.010), (0.0152, z0 + 0.017)]
        prof += [(0.0145, L - 0.008), (0.0120, L), (0.0060, L + 0.003), (0.0, L + 0.0035)]
        revolve(mb, prof, "rubber", seg=32, M=Mg @ _Ry(90), caps=False)
    side(mb, [(xr0 - 0.046, zr0 + 0.044), (xr0 - 0.036, zr0 + 0.046), (xr0 - 0.036, zr0 + 0.070), (xr0 - 0.050, zr0 + 0.074),
              (xr0 - 0.058, zr0 + 0.062), (xr0 - 0.052, zr0 + 0.056)], [0.002, 0.002, 0.003, 0.006, 0.004, 0.004], 0.056, GM,
         re=0.0020, ne=2, n=3)                                                      # gatillo de mariposa
    # palanca de carga (derecha): corredera, palanca y perilla torneada
    prism_x(mb, _T(-0.305, 0.0555, BZ - 0.009), [(-0.0025, -0.0055), (0.0025, -0.0055), (0.0025, 0.0055), (-0.0025, 0.0055)],
            [0.0012] * 4, 0.255, re=0.0015, mat=GM)
    side(mb, [(-0.108, BZ - 0.017), (-0.074, BZ - 0.017), (-0.070, BZ - 0.010), (-0.074, BZ + 0.003), (-0.108, BZ + 0.003)],
         [0.004, 0.004, 0.004, 0.004, 0.004], 0.016, GM, y0=0.066, re=0.0025, ne=2, n=3)
    revolve(mb, [(0.0, 0.0), (0.0095, 0.0), (0.0110, 0.004), (0.0135, 0.012), (0.0135, 0.028), (0.0120, 0.033), (0.0, 0.035)], GM,
            seg=SEG_B, M=_T(-0.091, 0.074, BZ - 0.007) @ _Rx(-90), caps=False)
    # bandeja de alimentación (izquierda) con guía de la cinta
    side(mb, [(-0.104, BZ - 0.022), (0.018, BZ - 0.022), (0.018, BZ - 0.016), (-0.104, BZ - 0.016)], [0.002] * 4, 0.040, GM,
         y0=-0.072, re=0.0012, ne=1, n=2)
    for xx in (-0.098, 0.012):
        side(mb, [(xx - 0.004, BZ - 0.020), (xx + 0.004, BZ - 0.020), (xx + 0.004, BZ + 0.030), (xx - 0.004, BZ + 0.030)],
             [0.002] * 4, 0.040, GM, y0=-0.072, re=0.0012, ne=1, n=2)
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
    _handwheel(mb, _T(xt, 0.0, zb + 0.105) @ _Rx(90) @ _T(0, 0, -0.035), R=0.048, mat=OD)
    plank(mb, (xt - 0.035, -0.03, zb - 0.012), (xt + 0.035, 0.03, zb + 0.022), OD, ch=0.004)        # corredera de dirección
    _handwheel(mb, _T(xt, 0.045, zb + 0.005) @ _Rx(-90), R=0.038, spokes=3, mat=OD)
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
    zc0 = zh - 0.115                                                  # fondo de la lata (bandeja de la cuna)
    can.transform(_T(-0.03, -0.235, zc0) @ _Rz(90))                   # tapa abisagrada hacia fuera (-Y)
    mb.join(can)
    plank(mb, (-0.12, -0.39, zc0 - 0.012), (0.06, -0.075, zc0 + 0.0005), OD, ch=0.003)          # bandeja
    for xx in (-0.115, 0.055):
        plank(mb, (xx - 0.005, -0.392, zc0 - 0.006), (xx + 0.005, -0.075, zc0 + 0.03), OD, ch=0.002)  # topes
    plank(mb, (0.035, -0.080, zc0 - 0.012), (0.060, -0.0625, zr0 - 0.01), OD, ch=0.003)      # brazo a la cuna
    fine = [Vector(p) for p in spline([(-0.04, -0.205, zc0 + 0.15), (-0.04, -0.175, zc0 + 0.215), (-0.04, -0.120, BZ - 0.004),
                                       (-0.04, -0.080, BZ + 0.012)], 12)]
    belt, acc, nxt = [tuple(fine[0])], 0.0, 0.027                      # paso de eslabón constante (27 mm)
    for a_, b_ in zip(fine[:-1], fine[1:]):
        acc += (b_ - a_).length
        if acc >= nxt:
            belt.append(tuple(b_))
            nxt += 0.027
    for i in range(len(belt) - 1):
        p, q = Vector(belt[i]), Vector(belt[i + 1])
        t = (q - p).normalized()
        Mr, _ = port.frame_on(p - Vector((0.07, 0, 0)), p + Vector((0.07, 0, 0)), up=tuple(t.cross(Vector((1, 0, 0))) * -1))
        _belt_round(mb, Mr @ _Ry(90), link=True, k=i)
    del r
    return mb


# ======================================================================================================== mortero
def _handwheel(mb, M, R=0.045, rr=0.006, spokes=3, mat="paint_od", knob=True):
    """Volante de mando: aro de sección redonda (32 lados), maza, rayos y perilla giratoria; plano XY local, eje +Z."""
    revolve(mb, [(R - rr, 0.0), (R, -rr), (R + rr, 0.0), (R, rr)], mat, seg=32, M=M, closed=True)
    revolve(mb, [(0.013, -0.012), (0.013, 0.010), (0.0, 0.012)], mat, seg=SEG, M=M)
    for k in range(spokes):
        a = 2 * PI * k / spokes
        pa = M @ Vector((0.011 * math.cos(a), 0.011 * math.sin(a), 0))
        pb = M @ Vector(((R - rr * 0.5) * math.cos(a), (R - rr * 0.5) * math.sin(a), 0))
        mb.tube([tuple(pa), tuple(pb)], 0.0045, seg=SEG_T, mat=mat)
    if knob:
        a = 0.5
        revolve(mb, [(0.0065, 0.0), (0.0078, 0.004), (0.0078, 0.032), (0.0055, 0.037), (0.0, 0.038)], "polymer", seg=SEG_T,
                M=M @ _T(R * math.cos(a), R * math.sin(a), rr * 0.6))


def _chain_round(mb, pts, link=0.028, wire=0.0032, mat="steel"):
    """Cadena de eslabones de alambre redondo (12 lados, sombreado continuo) alternados 90°, a paso constante."""
    from kit.clinic_equipo import loop_tube
    P = [Vector(p) for p in pts]
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    pitch = link - 2 * wire * 1.1
    n = max(int(round(acc[-1] / pitch)), 1)
    step = acc[-1] / n

    def at(sv):
        i = next((k for k in range(1, len(acc)) if acc[k] >= sv), len(acc) - 1)
        t = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-9)
        return P[i - 1].lerp(P[i], t)
    with mb.soft():
        for k in range(n):
            a_, b_ = at(k * step), at((k + 1) * step)
            c = (a_ + b_) / 2
            dd = (b_ - a_).normalized()
            Mk, _ = port.frame_on(c - dd * link / 2, c + dd * link / 2, up=(0, 0, 1) if abs(dd.z) < 0.9 else (1, 0, 0))
            Mk = Mk @ _Rx(90 * (k % 2))
            hw = link * 0.3
            path = [Mk @ Vector((link - hw + hw * math.cos(-PI / 2 + PI * q / 6), hw * math.sin(-PI / 2 + PI * q / 6), 0)) for q in range(7)]
            path += [Mk @ Vector((hw + hw * math.cos(PI / 2 + PI * q / 6), hw * math.sin(PI / 2 + PI * q / 6), 0)) for q in range(7)]
            loop_tube(mb, path, wire, seg=12, mat=mat, normal=Mk.to_3x3() @ Vector((0, 0, 1)))


def mortar(seed=0, elev=60.0):
    """Mortero de infantería clase 81 mm, genérico: tubo de 1,27 m (Ø ext. ~ 100 mm) con recámara de aletas de enfriamiento,
    culata con rótula esférica y anillo atenuador en la boca; bípode con collarín de 2 mitades atornilladas, 2 amortiguadores,
    horquilla sobre el mecanismo de dirección (tornillo horizontal con volante), columna de elevación con manivela,
    patas tubulares con zapatas de espolón, mecanismo de nivelación con perilla y cadena de abertura; soporte de cola de
    milano con aparato de puntería (cuerpo, burbuja, ocular acodado); placa base circular de ~ 0,52 m con nervaduras
    radiales, rótula con anillo de cierre y asa abatible. Tubo a `elev` grados. ORIGEN: piso, centro de la huella (placa
    base + zapatas); el tubo apunta a +X.
    Fuentes: en.wikipedia.org/wiki/M252_mortar ; man.fas.org/dod-101/sys/land/m252.htm (tubo de 1,27 m / 50 in, bípode
    ~ 12 kg, placa base ~ 11,6 kg, conjunto ~ 40 kg); army.mil/article/139736 (M252A1, tubo con aletas)."""
    r = rng(seed)
    mb = MB()
    OD, GM, ST = "paint_od", "gunmetal", "steel"
    th = math.radians(elev)
    d = Vector((math.cos(th), 0.0, math.sin(th)))                 # eje del tubo
    nb = Vector((math.sin(th), 0.0, -math.cos(th)))              # perpendicular "bajo el tubo"
    B = Vector((0.0, 0.0, 0.078))                                 # centro de la rótula
    Mt = _T(*B) @ Matrix.Rotation(PI / 2 - th, 4, "Y")          # z local = eje del tubo
    # ---------------- placa base
    Rp = 0.26
    revolve(mb, [(0.0, 0.002), (Rp - 0.012, 0.0), (Rp, 0.006), (Rp, 0.020), (Rp - 0.008, 0.026), (0.20, 0.034), (0.11, 0.050),
                 (0.075, 0.056)], OD, seg=64, caps=False)
    revolve(mb, [(0.075, 0.056), (0.078, 0.062), (0.060, 0.086), (0.0, 0.090)], OD, seg=SEG, caps=False)
    revolve(mb, [(0.064, 0.060), (0.084, 0.060), (0.084, 0.074), (0.064, 0.080)], ST, seg=SEG, closed=True)   # anillo de cierre
    for k in range(3):                                           # orejas del anillo
        a = 2 * PI * k / 3 + 0.3
        side(mb, [(0.078, 0.062), (0.104, 0.064), (0.104, 0.074), (0.078, 0.076)], [0.0, 0.004, 0.004, 0.0], 0.016, ST, re=0.0,
             M=_Rz(math.degrees(a)))
    for k in range(8):                                           # nervaduras radiales
        a = 2 * PI * k / 8 + PI / 8
        P = [(0.085, 0.050), (0.235, 0.020), (0.252, 0.022), (0.252, 0.030), (0.090, 0.068)]
        side(mb, P, [0.0, 0.0, 0.003, 0.003, 0.004], 0.012, OD, re=0.0, n=2, M=_Rz(math.degrees(a)))
    for sy in (-1, 1):                                           # asa abatible (atrás)
        plan(mb, [(-0.02, -0.012), (0.02, -0.012), (0.02, 0.012), (-0.02, 0.012)], [0.004] * 4, 0.014, OD, z0=0.019, re=0.002,
             ne=1, n=2, M=_T(-Rp + 0.03, sy * 0.10, 0))
    wire(mb, [(-Rp + 0.03, -0.10, 0.028), (-Rp - 0.04, -0.10, 0.030), (-Rp - 0.04, 0.10, 0.030), (-Rp + 0.03, 0.10, 0.028)],
         0.0065, ST, bend=0.02, nseg=4, seg=SEG_T)
    # ---------------- tubo
    prof = [(0.0, -0.034), (0.022, -0.033), (0.034, -0.026), (0.040, -0.014), (0.044, 0.000), (0.058, 0.000), (0.060, 0.010),
            (0.060, 0.050), (0.052, 0.058)]
    z = 0.058
    for k in range(8):                                           # aletas de enfriamiento de la recámara
        prof += [(0.050, z + 0.004), (0.062, z + 0.006), (0.062, z + 0.014), (0.050, z + 0.016)]
        z += 0.024
    prof += [(0.050, z + 0.006), (0.0505, z + 0.03), (0.0485, 1.17), (0.0485, 1.235), (0.056, 1.240), (0.056, 1.268),
             (0.050, 1.272), (0.0415, 1.272), (0.0415, 1.240)]
    mats = [ST] * 5 + [OD] * (len(prof) - 6) + ["cable"]
    revolve(mb, prof, mats, seg=48, M=Mt, caps=False)
    # ---------------- collarín, amortiguadores, horquilla, dirección, elevación, patas
    sc = 0.90
    C = B + d * sc
    Mc = Mt @ _T(0, 0, sc)
    revolve(mb, [(0.0482, -0.035), (0.062, -0.035), (0.064, -0.030), (0.064, 0.030), (0.062, 0.035), (0.0482, 0.035)], OD, seg=SEG,
            M=Mc, closed=True)
    for sy in (-1, 1):                                           # orejas atornilladas del collarín (2 mitades)
        ya, yb = sorted((sy * 0.056, sy * 0.086))
        board(mb, (-0.011, ya, -0.028), (0.011, yb, 0.028), OD, ch=0.002, M=Mc)
        revolve(mb, [(0.006, -0.040), (0.006, 0.040)], ST, seg=SEG_T, M=Mc @ _T(0, sy * 0.074, 0))
        for zz, rot in ((0.028, Matrix()), (-0.028, _Rx(180))):
            hexnut(mb, Mc @ _T(0, sy * 0.074, zz) @ rot, s=0.017, h=0.008)
    for sy in (-1, 1):                                           # amortiguadores paralelos al tubo
        p0 = C + nb * 0.070 + Vector((0, sy * 0.045, 0)) + d * 0.02
        p1 = p0 - d * 0.20
        Ma, La = port.frame_on(p1, p0)
        revolve(mb, [(0.0, -0.012), (0.022, -0.008), (0.022, 0.12), (0.010, 0.125), (0.010, La)], OD, seg=SEG, M=Ma @ _Ry(90),
                caps=False)
        revolve(mb, [(0.012, La - 0.012), (0.012, La + 0.012)], ST, seg=SEG, M=Ma @ _Ry(90))
        hel = [tuple(Ma @ _Ry(90) @ Vector((0.0145 * math.cos(2 * PI * t * 9), 0.0145 * math.sin(2 * PI * t * 9),
                                             0.127 + (La - 0.141) * t))) for t in [k / (9 * 16) for k in range(9 * 16 + 1)]]
        with mb.soft():
            mb.tube(hel, 0.0022, seg=10, mat=ST, caps=True)
        mb.tube([tuple(C + nb * 0.045 + Vector((0, sy * 0.045, 0)) + d * 0.02), tuple(p0 + nb * 0.004)], 0.012, seg=SEG, mat=OD)
    Y0 = C + nb * 0.070 - d * 0.20                               # extremo inferior de los amortiguadores: horquilla
    side(mb, [(Y0.x - 0.035, Y0.z - 0.035), (Y0.x + 0.035, Y0.z - 0.035), (Y0.x + 0.035, Y0.z + 0.025), (Y0.x - 0.035, Y0.z + 0.025)],
         [0.010] * 4, 0.124, OD, re=0.005, n=3, ne=2)
    # mecanismo de dirección: caja horizontal (Y) con tornillo y volante a la derecha
    Tz = Y0.z - 0.055
    revolve(mb, [(0.026, -0.13), (0.028, -0.125), (0.028, 0.125), (0.026, 0.13)], OD, seg=SEG, M=_T(Y0.x, 0, Tz) @ _Rx(90))
    revolve(mb, [(0.012, 0.13), (0.012, 0.175)], ST, seg=SEG, M=_T(Y0.x, 0, Tz) @ _Rx(-90))
    _handwheel(mb, _T(Y0.x, 0.178, Tz) @ _Rx(-90), R=0.055)
    side(mb, [(Y0.x - 0.018, Tz + 0.010), (Y0.x + 0.018, Tz + 0.010), (Y0.x + 0.018, Y0.z - 0.030), (Y0.x - 0.018, Y0.z - 0.030)],
         [0.006] * 4, 0.060, OD, re=0.004, n=3, ne=2)
    # columna de elevación y manivela
    Az = 0.26
    revolve(mb, [(0.030, Az - 0.04), (0.032, Az - 0.035), (0.032, Tz - 0.03), (0.026, Tz - 0.02)], OD, seg=SEG, M=_T(Y0.x, 0, 0))
    revolve(mb, [(0.036, Az + 0.02), (0.036, Az + 0.08)], OD, seg=SEG, M=_T(Y0.x, 0, 0))         # collar de las patas
    revolve(mb, [(0.010, Az - 0.10), (0.010, Az - 0.04)], ST, seg=SEG, M=_T(Y0.x, 0, 0))
    wire(mb, [(Y0.x, 0.0, Az - 0.10), (Y0.x + 0.075, 0.0, Az - 0.10), (Y0.x + 0.075, 0.0, Az - 0.13)], 0.007, ST, bend=0.012, nseg=3,
         seg=SEG_T)
    revolve(mb, [(0.0, 0.0), (0.0095, 0.002), (0.0095, 0.038), (0.007, 0.042), (0.0, 0.043)], "polymer", seg=SEG_T,
            M=_T(Y0.x + 0.075, 0.0, Az - 0.13) @ _Rx(180))
    feet = []
    for sy in (-1, 1):                                           # patas
        top = Vector((Y0.x + 0.02, sy * 0.03, Az + 0.05))
        foot = Vector((Y0.x + 0.17, sy * 0.36, 0.035))
        feet.append(foot)
        Ml, Ll = port.frame_on(top, foot)
        revolve(mb, [(0.0, -0.01), (0.0175, -0.008), (0.0175, Ll)], OD, seg=SEG, M=Ml @ _Ry(90), caps=False)
        revolve(mb, [(0.0, 0.0), (0.040, 0.0), (0.042, 0.006), (0.030, 0.012), (0.020, 0.040), (0.0175, 0.045)], OD, seg=SEG,
                M=_T(foot.x, foot.y, 0.0), caps=False)                  # zapata
        if sy < 0:                                                # mecanismo de nivelación en la pata izquierda
            Pm = top + (foot - top) * 0.30
            revolve(mb, [(0.026, -0.05), (0.026, 0.05)], OD, seg=SEG, M=Ml @ _T(Ll * 0.30, 0, 0) @ _Ry(90))
            revolve(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.03), (0.0, 0.032)], "polymer", seg=SEG,
                    M=_T(*Pm) @ _Rx(90) @ _T(0, 0, 0.024))
    # cadena de abertura entre las patas
    pa = Vector((Y0.x + 0.02, -0.03, Az + 0.05)) + (feet[0] - Vector((Y0.x + 0.02, -0.03, Az + 0.05))) * 0.55
    pb = Vector((Y0.x + 0.02, 0.03, Az + 0.05)) + (feet[1] - Vector((Y0.x + 0.02, 0.03, Az + 0.05))) * 0.55
    mid = (pa + pb) / 2 - Vector((0, 0, 0.03))
    _chain_round(mb, spline([tuple(pa), tuple(mid), tuple(pb)], 6), link=0.028, wire=0.0032, mat=ST)
    # ---------------- soporte y aparato de puntería (izquierda de la horquilla): ménsula de cola de milano con perilla,
    # cuerpo de cantos redondeados, cabeza del objetivo con ventana, ocular acodado con copa de hule, perillas de deflexión
    # y elevación moleteadas con tambores micrométricos graduados, 2 niveles de burbuja
    S0 = Vector((Y0.x, -0.062, Y0.z))
    side(mb, [(S0.x - 0.020, S0.z - 0.020), (S0.x + 0.020, S0.z - 0.020), (S0.x + 0.020, S0.z + 0.062), (S0.x - 0.020, S0.z + 0.062)],
         [0.006] * 4, 0.028, OD, y0=-0.076, re=0.003, n=3, ne=2)
    _knob_k(mb, _T(S0.x, -0.090, S0.z + 0.010) @ _Rx(90), 0.011, 0.010, "polymer", nt=20, dp=0.0008)
    zs = S0.z + 0.062
    yc = -0.084
    side(mb, [(S0.x - 0.060, zs), (S0.x + 0.060, zs), (S0.x + 0.060, zs + 0.060), (S0.x - 0.060, zs + 0.060)],
         [0.008, 0.008, 0.012, 0.012], 0.046, GM, y0=yc, re=0.005, n=3, ne=3)
    revolve(mb, [(0.0175, 0.0), (0.0175, 0.028), (0.0160, 0.032), (0.0, 0.033)], GM, seg=48, M=_T(S0.x + 0.020, yc, zs + 0.058))
    side(mb, [(-0.010, 0.006), (0.010, 0.006), (0.010, 0.022), (-0.010, 0.022)], [0.003] * 4, 0.0016, "glass", re=0.0,
         M=_T(S0.x + 0.0372, yc, zs + 0.058) @ _Rz(90))
    Me = _T(S0.x - 0.050, yc, zs + 0.040) @ _Ry(-125)                            # ocular acodado hacia atrás y arriba
    revolve(mb, [(0.0, -0.004), (0.0130, -0.004), (0.0130, 0.040), (0.0150, 0.044), (0.0150, 0.052)], GM, seg=48, M=Me, caps=False)
    revolve(mb, [(0.0150, 0.052), (0.0175, 0.056), (0.0190, 0.072), (0.0165, 0.074), (0.0120, 0.068), (0.0090, 0.064), (0.0, 0.063)],
            ["rubber"] * 5 + ["glass"], seg=48, M=Me, caps=False)
    for (yy, Mr, nm) in ((yc - 0.023, _Rx(90), "def"), (yc + 0.023, _Rx(-90), "ele")):
        Mk = _T(S0.x - 0.012 if nm == "def" else S0.x + 0.010, yy, zs + 0.030) @ Mr
        revk(mb, [(0.0165, 0.0), (0.0165, 0.010)], GM, M=Mk, knurl=(48, 0.0003, set()), caps=False)
        for k in range(24):                                                     # graduación del tambor
            a = 2 * PI * k / 24
            plan(mb, [(-0.0004, 0.0), (0.0004, 0.0), (0.0004, 0.004 if k % 4 == 0 else 0.0025), (-0.0004, 0.004 if k % 4 == 0 else 0.0025)],
                 0.0, 0.0003, "sign_white", z0=-0.0001, re=0.0, M=Mk @ _Rz(math.degrees(a)) @ _T(0.0165, 0, 0.001) @ _Ry(90))
        _knob_k(mb, Mk @ _T(0, 0, 0.010), 0.0135, 0.014, "polymer", nt=24, dp=0.0008)
    for (dx, rot) in ((-0.030, 0.0), (0.0, 90.0)):                               # niveles de burbuja
        Mv = _T(S0.x + dx, yc, zs + 0.061) @ _Rz(rot)
        side(mb, [(-0.016, 0.0), (0.016, 0.0), (0.016, 0.009), (-0.016, 0.009)], [0.0, 0.0, 0.003, 0.003], 0.012, GM, re=0.0012, n=2,
             ne=1, M=Mv)
        revolve(mb, [(0.0, -0.013), (0.0042, -0.012), (0.0042, 0.012), (0.0, 0.013)], "glass", seg=24, M=Mv @ _T(0, 0, 0.0085) @
                _Ry(90), caps=False)
    # ---------------- estarcido en el tubo y centrado de la huella
    bb = [v.co for v in mb.bm.verts]
    cx = (min(c.x for c in bb) + max(c.x for c in bb)) / 2
    mb.transform(_T(-cx, 0, 0))
    del r
    return mb


# ======================================================================================================== lanzacohetes desechable
def cyl_text(mb, s, size, R, M, ang, mat="paint_yellow", font="stencil", depth=0.0004, z0=0.0):
    """Estarcido (kit.fonts) envuelto sobre un cilindro de radio R cuyo eje es Z local de M: el texto corre a lo largo del
    eje (centrado en z0) y su línea base sigue el perímetro en el ángulo ang (rad, 0 = +X local)."""
    from kit.fonts import text_font
    tmp = MB()
    text_font(tmp, s, size, depth, mat, Matrix(), font=font, res=3 if size > 0.012 else 2)
    vs = list(tmp.bm.verts)
    if not vs:
        return
    ys = [v.co.y for v in vs]
    yc = (min(ys) + max(ys)) / 2
    for v in vs:
        u, w, d = v.co.x, v.co.y - yc, v.co.z
        a = ang - w / R
        r = R + d
        v.co = Vector((r * math.cos(a), r * math.sin(a), z0 + u))
    mb.join(tmp, M)


def launcher_tube(seed=0):
    """Lanzacohetes desechable genérico (tubo de lanzamiento de fibra de vidrio pintado, ~ 1,02 m, Ø 101 mm, ~ 104 mm
    sobre las bandas): tubo con 4 bandas de refuerzo de canto redondeado, tapa delantera de hule con lengüeta y nervios,
    amortiguador trasero de la tobera con 8 nervios de apoyo, mecanismo de disparo superior (carcasa moldeada, palanca de
    armado acodada con estrías, seguro de palanca, botón rojo con anillo de guarda, pasador de seguridad de transporte con
    argolla y cordón), alza y guion bajo tapas corredizas estriadas, hombrera plegada que sigue la curva del tubo (hule
    estriado) y empuñadura delantera plegada sobre su pivote, correa de transporte con abrazaderas, hebilla y costuras de
    barra, estarcidos envueltos «FRONT», «REAR» y lote (kit.fonts). Pintado verde olivo (semilla par) o arena (impar).
    ORIGEN: piso bajo el centro del tubo (reposa en las tapas); eje del tubo a lo largo de X, boca hacia +X, mecanismo
    arriba. Fuentes: en.wikipedia.org/wiki/AT4 y man.fas.org/dod-101/sys/land/at4.htm (1020 mm, 6,7 kg, calibre 84 mm)."""
    mb = MB()
    P = "paint_od" if seed % 2 == 0 else "paint_tan"
    L = 1.016
    R = 0.0505
    zc = 0.0585                                       # eje (las tapas de Ø 117 mm apoyan en el piso)
    M = _T(-L / 2, 0, zc) @ _Ry(90)                    # z local = +X ; x local = -Z mundial ; y local = +Y
    prof = [(R - 0.004, 0.052), (R, 0.052)]
    for (z0, z1) in ((0.080, 0.130), (0.330, 0.360), (0.650, 0.680), (0.880, 0.930)):
        prof += [(R, z0 - 0.004), (R + 0.0012, z0 - 0.002), (R + 0.0026, z0), (R + 0.0028, z0 + 0.002), (R + 0.0028, z1 - 0.002),
                 (R + 0.0026, z1), (R + 0.0012, z1 + 0.002), (R, z1 + 0.004)]
    prof += [(R, 0.962), (R - 0.004, 0.962)]
    revolve(mb, prof, P, seg=64, M=M, caps=False)
    revolve(mb, [(R - 0.004, 0.052), (R - 0.004, 0.962)], "cable", seg=48, M=M, caps=False)          # interior oscuro
    # amortiguador trasero de la tobera: copa de polímero con nervios
    revolve(mb, [(R - 0.006, 0.075), (0.0545, 0.072), (0.0562, 0.068), (0.0565, 0.060), (0.0565, 0.014), (0.0555, 0.004),
                 (0.0530, 0.0), (0.030, -0.004), (0.0, -0.005)], "polymer", seg=64, M=M)
    for k in range(8):
        a = 2 * PI * k / 8 + PI / 8
        arc_solid(mb, 0.0555, 0.0585, 0.018, 0.056, a - 0.07, a + 0.07, 2, "polymer", M=M)
        revolve(mb, [(0.0, 0.0), (0.0012, 0.0), (0.0012, 0.0006)], "polymer", seg=8,
                M=M @ _T(0.0585 * math.cos(a), 0.0585 * math.sin(a), 0.037) @ _Rz(math.degrees(a)) @ _Ry(90), caps=False)
    # tapa delantera de hule con nervios y lengüeta
    revolve(mb, [(R - 0.006, 0.940), (0.0560, 0.944), (0.0585, 0.956), (0.0585, 1.004), (0.0570, 1.011), (0.0545, 1.014),
                 (0.030, 1.018), (0.0, 1.019)], "rubber", seg=64, M=M)
    for z0 in (0.962, 0.978, 0.994):
        revolve(mb, [(0.0583, z0), (0.0596, z0 + 0.002), (0.0596, z0 + 0.006), (0.0583, z0 + 0.008)], "rubber", seg=64, M=M,
                caps=False)
    side(mb, [(L / 2 - 0.004, zc + 0.050), (L / 2 + 0.010, zc + 0.053), (L / 2 + 0.016, zc + 0.068), (L / 2 + 0.004, zc + 0.073)],
         [0.0, 0.005, 0.006, 0.006], 0.020, "rubber", re=0.0025, n=3, ne=2)
    # ---- mecanismo de disparo (arriba)
    xm0, xm1 = -0.02, 0.17
    zt = zc + R
    xloft(mb, [(xm0, 0.040, 0.026, zt + 0.004, (0.010, 0.010, 0.002, 0.002)), (xm0 + 0.004, 0.044, 0.032, zt + 0.006, (0.012, 0.012, 0.002, 0.002)),
               (xm0 + 0.014, 0.047, 0.036, zt + 0.008, (0.013, 0.013, 0.002, 0.002)), (xm1 - 0.014, 0.047, 0.036, zt + 0.008, (0.013, 0.013, 0.002, 0.002)),
               (xm1 - 0.004, 0.044, 0.032, zt + 0.006, (0.012, 0.012, 0.002, 0.002)), (xm1, 0.040, 0.026, zt + 0.004, (0.010, 0.010, 0.002, 0.002))],
          "polymer", n=5)
    for s in (-1, 1):                                  # costuras de moldeo de la carcasa
        prism_x(mb, _T(xm0 + 0.016, s * 0.0236, zt + 0.0035), [(-0.0005, -0.0008), (0.0005, -0.0008), (0.0005, 0.0008),
                (-0.0005, 0.0008)], [0.0004] * 4, xm1 - xm0 - 0.032, re=0.0004, mat="polymer")
    # palanca de armado acodada, con pivote y estrías
    revolve(mb, [(0.0055, -0.003), (0.0055, 0.004), (0.0045, 0.005)], P, seg=24, M=_T(xm0 + 0.030, -0.0236, zt + 0.020) @ _Rx(90))
    side(mb, [(xm0 + 0.024, zt + 0.023), (xm0 + 0.100, zt + 0.024), (xm0 + 0.112, zt + 0.028), (xm0 + 0.112, zt + 0.034),
              (xm0 + 0.098, zt + 0.035), (xm0 + 0.030, zt + 0.031)], [0.004, 0.006, 0.003, 0.003, 0.006, 0.006], 0.012, P,
         y0=-0.012, re=0.0015, n=3, ne=2)
    for k in range(5):
        xr = xm0 + 0.082 + k * 0.0055
        side(mb, [(xr, zt + 0.0335), (xr + 0.0022, zt + 0.0335), (xr + 0.0022, zt + 0.0362), (xr, zt + 0.0362)], [0.0008] * 4,
             0.011, P, y0=-0.012, re=0.0005, n=2, ne=1)
    # seguro (palanca derecha) y botón rojo con anillo de guarda
    side(mb, [(xm1 - 0.080, zt + 0.0225), (xm1 - 0.048, zt + 0.0225), (xm1 - 0.050, zt + 0.0305), (xm1 - 0.078, zt + 0.0305)],
         [0.002, 0.002, 0.003, 0.003], 0.010, "polymer", y0=0.0165, re=0.0015, n=2, ne=1)
    revolve(mb, [(0.0115, -0.002), (0.0115, 0.0062), (0.0105, 0.0072), (0.0092, 0.0072), (0.0092, 0.0030), (0.0, 0.0030)],
            "polymer", seg=40, M=_T(xm1 - 0.030, 0.0, zt + 0.0255), caps=False)
    revolve(mb, [(0.0, 0.0020), (0.0078, 0.0020), (0.0078, 0.0070), (0.0068, 0.0082), (0.0, 0.0085)], "sign_red", seg=40,
            M=_T(xm1 - 0.030, 0.0, zt + 0.0255), caps=False)
    # pasador de seguridad de transporte con argolla y cordón
    revolve(mb, [(0.0, 0.0), (0.0019, 0.0), (0.0019, 0.040), (0.0, 0.041)], "steel", seg=16,
            M=_T(xm0 + 0.060, -0.030, zt + 0.014) @ _Rx(-90) @ _T(0, 0, -0.012), caps=False)
    ring = [(xm0 + 0.060 + 0.0085 * math.cos(a), -0.0352, zt + 0.0055 + 0.0085 * math.sin(a)) for a in
            [2 * PI * k / 24 for k in range(24)]]
    from kit.clinic_equipo import loop_tube
    with mb.soft():
        loop_tube(mb, ring, 0.0011, seg=10, mat="steel", normal=(0, 1, 0))
    # ---- alza (atrás) y guion (adelante) bajo tapas corredizas
    for (x0, x1, h) in ((-0.30, -0.20, 0.026), (0.30, 0.37, 0.022)):
        xloft(mb, [(x0, 0.026, h - 0.002, zt + h / 2 - 0.004, (0.005, 0.005, 0.001, 0.001)),
                   (x0 + 0.004, 0.030, h + 0.002, zt + h / 2 - 0.005, (0.006, 0.006, 0.001, 0.001)),
                   (x1 - 0.004, 0.030, h + 0.002, zt + h / 2 - 0.005, (0.006, 0.006, 0.001, 0.001)),
                   (x1, 0.026, h - 0.002, zt + h / 2 - 0.004, (0.005, 0.005, 0.001, 0.001))], "polymer", n=4)
        side(mb, [(x0 + 0.006, zt + h - 0.0065), (x1 - 0.010, zt + h - 0.0065), (x1 - 0.010, zt + h - 0.0035),
                  (x0 + 0.006, zt + h - 0.0035)], [0.0012] * 4, 0.032, P, re=0.0010, n=2, ne=1)
        for k in range(5):
            xx = x0 + 0.012 + k * 0.0055
            side(mb, [(xx, zt + h - 0.0040), (xx + 0.0022, zt + h - 0.0040), (xx + 0.0022, zt + h - 0.0018), (xx, zt + h - 0.0018)],
                 [0.0008] * 4, 0.026, P, re=0.0004, n=2, ne=1)
    # ---- hombrera plegada (costado -Y): concha de hule que sigue la curva del tubo, con estrías
    Ms = M @ _Rz(-90)                                 # ángulo 0 = -Y mundial
    arc_solid(mb, R + 0.0010, R + 0.0130, 0.255, 0.390, -0.42, 0.42, 16, "rubber", M=Ms)
    for k in range(9):
        z0 = 0.262 + k * 0.0145
        arc_solid(mb, R + 0.0125, R + 0.0145, z0, z0 + 0.0060, -0.36, 0.36, 14, "rubber", M=Ms)
    arc_solid(mb, R + 0.0005, R + 0.0060, 0.390, 0.405, -0.25, 0.25, 8, P, M=Ms)                   # bisagra
    revolve(mb, [(0.0035, -0.016), (0.0035, 0.016)], "steel", seg=20, M=_T(-L / 2 + 0.398, -R - 0.0035, zc) @ _Rx(0) @ _Ry(0))
    # ---- empuñadura delantera plegada (abajo a la izquierda) sobre su pivote
    Mg = M @ _Rz(-45)                                 # ángulo 0 = abajo-izquierda
    arc_solid(mb, R + 0.0005, R + 0.0060, 0.555, 0.600, -0.30, 0.30, 8, P, M=Mg)
    rg = R + 0.0175
    Xg, Zg = Vector((1, 0, 0)), Vector((0, -0.7071, -0.7071))
    Yg = Zg.cross(Xg)
    Mgr = Matrix(((Xg.x, Yg.x, Zg.x, -L / 2 + 0.572), (Xg.y, Yg.y, Zg.y, -rg * 0.7071), (Xg.z, Yg.z, Zg.z, zc - rg * 0.7071),
                  (0, 0, 0, 1)))
    port.loft(mb, [(0.0, 0.020, 0.016, 0.0), (0.010, 0.026, 0.024, 0.0), (0.080, 0.028, 0.026, 0.0), (0.092, 0.024, 0.020, 0.0),
                   (0.098, 0.016, 0.012, 0.0)], seg=32, mat="polymer", M=Mgr, ex=2.6)
    for k in range(4):                                # estrías de los dedos
        revolve(mb, [(0.0136, -0.002), (0.0146, 0.0), (0.0136, 0.002)], "polymer", seg=32, M=Mgr @ _T(0.026 + k * 0.016, 0, 0) @
                _Ry(90), caps=False)
    # ---- abrazaderas de la correa y correa a lo largo del costado +Y, con hebilla y costuras
    for x in (-0.38, 0.40):
        revolve(mb, [(R + 0.0026, -0.011), (R + 0.0048, -0.010), (R + 0.0048, 0.010), (R + 0.0026, 0.011)], "steel", seg=64,
                M=_ax(x, 0, zc), closed=True)
        side(mb, [(x - 0.012, zc - 0.006), (x + 0.012, zc - 0.006), (x + 0.012, zc + 0.012), (x - 0.012, zc + 0.012)], [0.003] * 4,
             0.010, "steel", y0=R + 0.008, re=0.0012, n=2, ne=1)
        _screw_h(mb, _T(x, R + 0.013, zc + 0.003) @ _Rx(-90), d=0.0055, mat="steel")
        with mb.soft():
            wire(mb, [(x - 0.008, R + 0.012, zc + 0.012), (x - 0.008, R + 0.018, zc + 0.020), (x + 0.008, R + 0.018, zc + 0.020),
                      (x + 0.008, R + 0.012, zc + 0.012)], 0.0022, "steel", bend=0.004, nseg=3, seg=12)
    sl = spline([(-0.388, R + 0.0185, zc + 0.024), (-0.30, R + 0.024, zc + 0.002), (0.0, R + 0.026, zc - 0.012),
                 (0.30, R + 0.024, zc + 0.002), (0.408, R + 0.0185, zc + 0.024)], 4)
    with mb.soft():
        strap(mb, sl, 0.030, 0.0022, "canvas", up=(0, 1, 0), r=0.0009)
    for xe in (-0.362, 0.382):
        prism_x(mb, _T(xe - 0.004, R + 0.0262, zc + 0.012), [(-0.0002, -0.0125), (0.0004, -0.0125), (0.0004, 0.0125),
                                                             (-0.0002, 0.0125)], [0.0] * 4, 0.008, re=0.0001, mat="fabric")
    plan(mb, [(-0.022, -0.020), (0.022, -0.020), (0.022, 0.020), (-0.022, 0.020)], [0.004] * 4, 0.0066, "plastic", z0=-0.0033,
         re=0.0012, ne=2, n=3, M=_T(0.10, R + 0.0262, zc - 0.009) @ _Rx(-90))
    for k in range(3):
        plan(mb, [(-0.018, -0.0025), (0.018, -0.0025), (0.018, 0.0025), (-0.018, 0.0025)], [0.001] * 4, 0.0012,
             "plastic", z0=0.0028, re=0.0004, n=2, ne=1, M=_T(0.10, R + 0.0262, zc - 0.009 - 0.011 + k * 0.011) @ _Rx(-90))
    # ---- estarcidos envueltos (kit.fonts)
    cyl_text(mb, "FRONT", 0.022, R + 0.0002, M, -PI / 2, z0=0.80)
    cyl_text(mb, "REAR", 0.022, R + 0.0002, M, -PI / 2, z0=0.20)
    cyl_text(mb, "LOT 27-05  RKT LAUNCHER", 0.0085, R + 0.0002, M, -PI / 2 + 0.30, font="stencil2", z0=0.50)
    cyl_text(mb, "FIRE FROM SHOULDER ONLY", 0.0075, R + 0.0002, M, -PI / 2 - 0.30, font="stencil2", z0=0.50)
    return mb


# ======================================================================================================== chaleco portaplacas
def _pad(mb, M, P, R, T, crown_f, crown_b, mat="canvas", nin_f=3, nin_b=2, ne=8, n=4, inset=0.05, wrinkle=0.0, seed=0):
    """Bolsa acolchada (portaplaca, almohadilla): contorno P (antihorario, plano XY local, x derecha, y arriba) con filetes R,
    canto completamente redondeado (semicírculo de radio T/2 en ne pasos), cara frontal (+Z) abombada crown_f y trasera
    crown_b en lazos concéntricos (malla subdividida, sombreado suave); wrinkle = amplitud de arrugas (ruido)."""
    from mathutils import noise
    re = T / 2
    loops = []
    for k in range(nin_b, 0, -1):                       # cara trasera, del centro hacia el canto
        u = k / nin_b
        loops.append((re + inset * u, -re - crown_b * u ** 0.5))
    for j in range(ne + 1):                             # canto redondo
        a = -PI / 2 + PI * j / ne
        loops.append((re * (1 - math.cos(a)), re * math.sin(a)))
    for k in range(1, nin_f + 1):                       # cara frontal, del canto hacia el centro
        u = k / nin_f
        loops.append((re + inset * u, re + crown_f * u ** 0.5))
    rings = []
    for li, (dl, z) in enumerate(loops):
        ring = []
        for (x, y) in rpoly_n(P, R, dl, n):
            zz = z
            if wrinkle and abs(z) >= re * 0.999 and 0 < li < len(loops) - 1:
                zz += wrinkle * noise.noise(Vector((x * 18.0 + seed, y * 18.0, z * 5.0)))
            ring.append((x, y, zz))
        rings.append(ring)
    skin(mb, rings, mat, M, cap0=True, cap1=True)


def _surface_z(tree, x, y, z0=1.0):
    """Altura de la cara frontal de un acolchado (rayo desde +Z en su marco local)."""
    loc, nrm, idx, d = tree.ray_cast(Vector((x, y, z0)), Vector((0, 0, -1)), 5.0)
    return loc.z if loc is not None else 0.0


def _binding(mb, M, P, R, r=0.0024, mat="canvas", n=4):
    """Cinta de ribete (vivo) que envuelve el canto de un acolchado _pad: tubo cerrado sobre el contorno en el plano medio."""
    from kit.clinic_equipo import loop_tube
    pts = [tuple(M @ Vector((x, y, 0.0))) for (x, y) in rpoly_n(P, R, r * 0.35, n)]
    with mb.soft():
        loop_tube(mb, pts, r, seg=12, mat=mat, normal=M.to_3x3() @ Vector((0, 0, 1)))


def _stitch(mb, M, pts2d, tree, lift=0.00025, r=0.00055, closed=True, mat="fabric"):
    """Pespunte: hilo fino (tubo suave) que sigue la cara de un acolchado (rayo contra su BVH) por los puntos (x, y)."""
    P = [(x, y, _surface_z(tree, x, y) + lift) for (x, y) in pts2d]
    if closed:
        P.append(P[0])
    with mb.soft():
        mb.tube([tuple(M @ Vector(p)) for p in P], r, seg=6, mat=mat, caps=not closed)


def _resample2(pts, step, closed=True):
    P = [Vector((p[0], p[1])) for p in pts] + ([Vector((pts[0][0], pts[0][1]))] if closed else [])
    out = [P[0]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(1, int((b - a).length / step))
        out += [a.lerp(b, k / n) for k in range(1, n + 1)]
    if closed:
        out = out[:-1]
    return [(p.x, p.y) for p in out]


def _webbing(mb, M, tree, x0, x1, y, w=0.025, t=0.0016, pitch=0.0381, mat="canvas"):
    """Hilera de cinta PALS sobre la cara de un acolchado: se abomba entre presillas y lleva costura de barra (rectángulo
    de hilo) en cada presilla."""
    pts = []
    nt = max(1, int(round((x1 - x0) / pitch)))
    for k in range(nt * 4 + 1):
        x = x0 + (x1 - x0) * k / (nt * 4)
        ph = (k % 4) / 4.0
        lift = 0.0021 * math.sin(PI * ph) if k % 4 else 0.0
        pts.append((x, y, _surface_z(tree, x, y) + t / 2 + 0.0002 + lift))
    with mb.soft():
        strap(mb, [tuple(M @ Vector(p)) for p in pts], w, t, mat, up=tuple(M.to_3x3() @ Vector((0, 0, 1))), r=t * 0.45)
    for k in range(nt + 1):                                   # costuras de barra
        x = x0 + (x1 - x0) * k / nt
        z = _surface_z(tree, x, y) + t + 0.0002
        plan(mb, [(x - 0.0016, y - w / 2 + 0.002), (x + 0.0016, y - w / 2 + 0.002), (x + 0.0016, y + w / 2 - 0.002),
                  (x - 0.0016, y + w / 2 - 0.002)], [0.0] * 4, 0.0007, "fabric", z0=z - 0.0001, re=0.0002, n=2, ne=1, M=M)


def _ladder_lock(mb, M, w=0.030, mat="plastic"):
    """Hebilla de escalera (ladder lock) de plástico en el plano XY local: marco con 2 barras y orejas."""
    holed(mb, M @ _T(0, 0, -0.0016), (0.0, 0.0, w / 2 + 0.003, 0.012, 0.0035), (0.0, -0.004, w / 2 - 0.001, 0.0028, 0.0012),
          0.0032, re_o=0.0010, re_i=0.0006, n=32, mat=mat, ne=1, ctr=(0.0, -0.004))
    plan(mb, [(-w / 2 + 0.001, 0.0030), (w / 2 - 0.001, 0.0030), (w / 2 - 0.001, 0.0058), (-w / 2 + 0.001, 0.0058)],
         [0.0008] * 4, 0.0030, mat, z0=-0.0015, re=0.0006, n=2, ne=1, M=M)


def _strap_tail(mb, p0, d0, L, w=0.025, t=0.0016, sag=0.0, side=(1, 0, 0), mat="canvas", n=10, curl=0.0):
    """Punta de cinta suelta que cuelga por gravedad desde p0 (dirección inicial d0): se dobla hacia abajo, punta
    sellada (termofundida) con su costura."""
    p = Vector(p0)
    d = Vector(d0).normalized()
    g = Vector((0, 0, -1))
    pts = [tuple(p)]
    seg = L / n
    for k in range(n):
        d = (d + g * 0.22 + Vector(side) * curl).normalized()
        p = p + d * seg
        pts.append(tuple(p))
    up = Vector(side).cross(Vector((0, 0, -1)))
    with mb.soft():
        strap(mb, pts, w, t, mat, up=tuple(up if up.length > 0.1 else Vector((0, -1, 0))), r=t * 0.45)
    return pts


def vest(seed=0):
    """Chaleco portaplacas colgado de un gancho de muro: bolsas de placa delantera y trasera acolchadas (malla subdividida,
    canto redondo, abombado y arrugas; corte de hombro para placa de 9,5 × 12,5 in) con ribete en todo el canto y pespunte
    a 8 mm; hombreras acolchadas con ribete, hebillas de escalera y puntas de cinta que cuelgan por gravedad; faja
    (cummerbund) elástica a los costados con 2 hileras PALS; 6 hileras de cinta PALS de 25 mm al frente con costuras de
    barra cada 38 mm (la cinta se abomba entre presillas); triple portacargador alto con cargadores reales (base arriba),
    ribetes, banda elástica, cordones elásticos y tiradores; panel de velcro con pespunte; asa de arrastre cosida colgada
    del gancho; gancho de acero en J con placa, 2 tornillos y tapón de hule. ORIGEN: cara del muro (y = 0) en el centro del
    gancho (z = 0); el chaleco cuelga hacia -Z y sobresale hacia -Y (frente del chaleco hacia -Y).
    Fuentes: en.wikipedia.org/wiki/MOLLE (cinta de 1 in, hileras a 1 in, presillas cada 1,5 in); shellbacktactical.com
    (placa SAPI mediana 9,5 × 12,5 in); magpul.com (cargador de 30, 7,5 in)."""
    from mathutils.bvhtree import BVHTree
    r = rng(seed)
    mb = MB()
    C = "canvas"
    W, H, T = 0.275, 0.345, 0.030
    cut = 0.05
    P = [(-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, H / 2 - cut), (W / 2 - cut, H / 2), (-W / 2 + cut, H / 2), (-W / 2, H / 2 - cut)]
    R = [0.03, 0.03, 0.02, 0.02, 0.02, 0.02]
    Mv = _Rx(90)                                        # local x -> X, y -> Z, z -> -Y (frente del chaleco)
    zb_top, yb = -0.050, -0.024                         # placa trasera: borde superior y plano medio
    zf_top, yf = -0.085, -0.122                         # placa delantera
    Mb = _T(0, yb, zb_top - H / 2) @ Mv
    Mf = _T(0, yf, zf_top - H / 2) @ Mv @ _Rz(float(r.uniform(-1.5, 1.5)))
    _pad(mb, Mb, P, R, T, 0.005, 0.0, C, nin_f=3, nin_b=0, wrinkle=0.0012, seed=float(seed))
    _binding(mb, Mb, P, R)
    front = MB()
    _pad(front, Matrix(), P, R, T, 0.008, 0.002, C, nin_f=6, nin_b=1, ne=8, inset=0.07, wrinkle=0.0018, seed=float(seed) + 7.0)
    tree = BVHTree.FromBMesh(front.bm)
    _binding(front, Matrix(), P, R)
    _stitch(front, Matrix(), _resample2(rpoly_n(P, R, 0.008, 3), 0.004), tree)
    # cinta PALS: 3 hileras bajo el portacargadores y 3 visibles arriba
    x0, x1 = -W / 2 + 0.030, W / 2 - 0.030
    for yr in [-0.146 + 0.0254 * k for k in range(3)] + [0.005 + 0.0254 * k for k in range(3)]:
        _webbing(front, Matrix(), tree, x0, x1, yr)
    # triple portacargador alto (bolsas blandas) con cargadores reales invertidos
    hp = 0.150
    yp0 = -0.160
    zs = max(_surface_z(tree, 0.0, -0.146), _surface_z(tree, 0.0, -0.095)) + 0.0036
    for i in range(3):
        xc = (i - 1) * 0.074
        Pp = [(-0.0355, -hp / 2), (0.0355, -hp / 2), (0.0355, hp / 2), (-0.0355, hp / 2)]
        Rp = [0.012, 0.012, 0.006, 0.006]
        Mp = _T(xc, yp0 + hp / 2, zs + 0.0150)
        _pad(front, Mp, Pp, Rp, 0.030, 0.0012, 0.0, C, nin_f=3, nin_b=0, inset=0.010, wrinkle=0.0005, seed=float(seed + i))
        _binding(front, Mp, Pp, Rp, r=0.0018)
        # banda elástica en la boca
        slab2(front, _T(xc, yp0 + hp - 0.016, zs + 0.0295) @ _Rx(0), 0.066, 0.022, 0.0016, 0.004, C, re_t=0.0007, ne_t=1, nc=3)
        # cargador invertido: la base asoma 45 mm sobre la boca
        mg = MB()
        Mbp = _mag(mg, Matrix(), lite=True, inserted=True, cal="556", seed=seed + i)
        mg.transform(Mbp.inverted())
        mg.transform(_Rx(180))
        front.join(mg, _T(xc, yp0 + hp + 0.044, zs + 0.0150) @ _Rx(-90) @ _Rz(0))
        # cordón elástico sobre la base con tirador
        ytop = yp0 + hp + 0.0525
        cord = [(xc - 0.031, yp0 + hp - 0.004, zs + 0.0302), (xc - 0.030, ytop - 0.004, zs + 0.0285), (xc - 0.018, ytop, zs + 0.0270),
                (xc, ytop + 0.0008, zs + 0.0265), (xc + 0.018, ytop, zs + 0.0270), (xc + 0.030, ytop - 0.004, zs + 0.0285),
                (xc + 0.031, yp0 + hp - 0.004, zs + 0.0302)]
        with front.soft():
            front.tube(spline(cord, 4), 0.0021, seg=12, mat="cable", caps=False)
        plan(front, [(-0.009, 0.0), (0.009, 0.0), (0.009, 0.016), (-0.009, 0.016)], [0.0, 0.0, 0.004, 0.004], 0.0022, "plastic",
             z0=zs + 0.0255, re=0.0008, n=2, ne=1, M=_T(xc, ytop, 0))
    # panel de velcro (parte alta) con pespunte
    zv = _surface_z(tree, 0.0, 0.110)
    slab2(front, _T(0, 0.110, zv - 0.0012), 0.15, 0.065, 0.0034, 0.006, C, re_t=0.0014, ne_t=2, nc=4)
    sp = _resample2(rr_pts(0.140, 0.055, 0.004, 3), 0.004)
    with front.soft():
        front.tube([(x, 0.110 + y, zv + 0.0024) for (x, y) in sp] + [(sp[0][0], 0.110 + sp[0][1], zv + 0.0024)], 0.0005, seg=6,
                   mat="fabric", caps=False)
    mb.join(front, Mf)
    # hombreras acolchadas: de las esquinas superiores de la trasera, sobre el gancho, a las de la delantera
    for sx in (-1, 1):
        x = sx * 0.085
        path = spline([(x, yb - 0.006, zb_top - 0.020), (x, yb - 0.016, zb_top + 0.018), (x, (yb + yf) / 2, zb_top + 0.032),
                       (x, yf + 0.020, zf_top + 0.012), (x, yf - 0.002, zf_top - 0.030)], 5)
        sec = [(0.026 * math.copysign(abs(math.cos(t)) ** 0.45, math.cos(t)), 0.0065 * math.copysign(abs(math.sin(t)) ** 0.7,
                math.sin(t))) for t in [2 * PI * k / 28 for k in range(28)]]
        with mb.soft():
            sweep_frame(mb, sec, path, C, up=(1, 0, 0))
        # hebilla de escalera al frente y punta de cinta que cuelga
        pb = Vector(path[-3])
        _ladder_lock(mb, _T(x, pb.y - 0.0085, pb.z) @ _Rx(90), w=0.026)
        _strap_tail(mb, (x + sx * 0.002, pb.y - 0.0115, pb.z - 0.010), (0.0, -0.25, -1.0), 0.085 + 0.01 * sx, w=0.025,
                    side=(sx * 1.0, 0, 0), curl=0.02)
    # faja (cummerbund) elástica a los costados, con 2 hileras PALS y puntas sueltas
    for sx in (-1, 1):
        zc = zf_top - H * 0.70
        path = spline([(sx * (W / 2 - 0.015), yf + 0.004, zc), (sx * (W / 2 + 0.018), yf + 0.030, zc + 0.004),
                       (sx * (W / 2 + 0.026), (yb + yf) / 2, zc + 0.010), (sx * (W / 2 + 0.012), yb - 0.010, zc + 0.018),
                       (sx * (W / 2 - 0.015), yb - 0.002, zc + 0.022)], 4)
        sec = [(0.0045 * math.copysign(abs(math.cos(t)) ** 0.6, math.cos(t)), 0.064 * math.copysign(abs(math.sin(t)) ** 0.3,
                math.sin(t))) for t in [2 * PI * k / 24 for k in range(24)]]
        with mb.soft():
            sweep_frame(mb, sec, path, C, up=(0, 0, 1))
        Pp = [Vector(q) for q in path]
        acc = [0.0]
        for a_, b_ in zip(Pp[:-1], Pp[1:]):
            acc.append(acc[-1] + (b_ - a_).length)
        for dz in (-0.022, 0.006):
            pts = []
            s0, s1 = 0.02, acc[-1] - 0.02
            nt = max(2, int(round((s1 - s0) / 0.0095)))
            for k in range(nt + 1):
                sv = s0 + (s1 - s0) * k / nt
                i = next(j for j in range(1, len(acc)) if acc[j] >= sv - 1e-9)
                f = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-9)
                q = Pp[i - 1].lerp(Pp[i], f)
                tng = (Pp[i] - Pp[i - 1]).normalized()
                nrm = Vector((tng.y, -tng.x, 0.0)).normalized()
                if nrm.x * sx < 0:
                    nrm = -nrm
                lift = 0.0019 * math.sin(PI * (k % 4) / 4) if k % 4 else 0.0
                pts.append(tuple(q + nrm * (0.0053 + lift) + Vector((0, 0, dz))))
            with mb.soft():
                strap(mb, pts, 0.0016, 0.025, C, up=(0, 0, 1), r=0.0006)
        _strap_tail(mb, (sx * (W / 2 - 0.008), yf - 0.004, zc - 0.050), (sx * 0.4, -0.2, -1.0), 0.11, w=0.025, side=(0, -1, 0),
                    curl=0.01 * sx)
    # asa de arrastre (cinta) colgada del brazo del gancho, con costura de barra
    loop = spline([(-0.030, yb - 0.004, zb_top - 0.004), (-0.020, yb - 0.004, -0.012), (-0.0095, yb - 0.004, 0.004),
                   (0.0, yb - 0.004, 0.0105), (0.0095, yb - 0.004, 0.004), (0.020, yb - 0.004, -0.012), (0.030, yb - 0.004, zb_top - 0.004)], 4)
    with mb.soft():
        strap(mb, loop, 0.0028, 0.026, C, up=(0, 1, 0), r=0.0012)
    for sx in (-1, 1):
        plan(mb, [(-0.012, -0.0016), (0.012, -0.0016), (0.012, 0.0016), (-0.012, 0.0016)], [0.0] * 4, 0.0005, "fabric",
             z0=-0.0001, re=0.0, M=_T(sx * 0.0295, yb - 0.0055, zb_top - 0.010) @ _Rx(90) @ _Rz(90))
    # gancho en J: placa al muro con 2 tornillos, brazo de varilla Ø 14 mm y tapón de hule
    plan(mb, [(-0.022, -0.035), (0.022, -0.035), (0.022, 0.035), (-0.022, 0.035)], [0.006] * 4, 0.004, "steel", z0=0.0, re=0.0012,
         ne=1, n=2, M=_T(0, 0, 0) @ _Rx(90))
    for zz in (-0.024, 0.024):
        _screw_h(mb, _T(0, -0.0040, zz) @ _Rx(90), d=0.0085, mat="steel", hexs=False)
    wire(mb, [(0, -0.003, 0.0), (0, -0.060, 0.0), (0, -0.068, 0.030)], 0.007, "steel", bend=0.014, nseg=6, seg=24)
    Mr, _ = port.frame_on(Vector((0, -0.066, 0.024)), Vector((0, -0.069, 0.032)))
    revolve(mb, [(0.0, -0.002), (0.0085, 0.0), (0.0095, 0.008), (0.0085, 0.014), (0.0, 0.016)], "rubber", seg=32, M=Mr @ _Ry(90))
    return mb


# ======================================================================================================== maleta rígida
def _case_handle(mb, M, span=0.120, mat="polymer"):
    """Asa abatible (abatida) de maleta en el plano XZ local (cara del casco en y = 0, crece hacia -Y): 2 alojamientos de
    pivote, asa de varilla con empuñadura de hule de dedos marcados."""
    hs = span / 2
    for s in (-1, 1):
        side(mb, [(s * hs - 0.011, -0.020), (s * hs + 0.011, -0.020), (s * hs + 0.011, 0.008), (s * hs - 0.011, 0.008)],
             [0.004, 0.004, 0.004, 0.004], 0.0140, mat, y0=-0.0068, re=0.0025, n=3, ne=2, M=M)
        revolve(mb, [(0.0045, -0.008), (0.0045, 0.008)], "steel", seg=24, M=M @ _T(s * hs, -0.0120, -0.006) @ _Ry(90))
    path = fillet([(-hs, -0.0120, -0.006), (-hs + 0.004, -0.0150, -0.040), (hs - 0.004, -0.0150, -0.040), (hs, -0.0120, -0.006)],
                  0.010, 4)
    mb.tube([tuple(M @ Vector(p)) for p in path], 0.0055, seg=24, mat=mat, caps=False)
    prof = [(0.0090, -0.046), (0.0110, -0.044)]
    for k in range(4):
        z0 = -0.040 + k * 0.022
        prof += [(0.0112, z0), (0.0104, z0 + 0.010), (0.0112, z0 + 0.020)]
    prof += [(0.0110, 0.046), (0.0090, 0.048)]
    revolve(mb, prof, "rubber", seg=32, M=M @ _T(0, -0.0150, -0.040) @ _Ry(90), caps=False)


def _case_latch(mb, x, yf, zp, mat="polymer"):
    """Cierre de doble acción en la cara frontal (yf, crece hacia -Y): orejas y pasador en el casco, palanca curva con
    estrías y gancho sobre la uña de la tapa; guardas laterales moldeadas a ambos lados."""
    for s in (-1, 1):                                    # guardas laterales (nervios del casco y de la tapa)
        plan(mb, [(x + s * 0.030 - 0.005, yf + 0.001), (x + s * 0.030 + 0.005, yf + 0.001), (x + s * 0.030 + 0.004, yf - 0.011),
                  (x + s * 0.030 - 0.004, yf - 0.011)], [0.0, 0.0, 0.003, 0.003], zp - 0.0145 - 0.016, mat, z0=0.016, re=0.003,
             n=3, ne=2)
        plan(mb, [(x + s * 0.030 - 0.005, yf + 0.001), (x + s * 0.030 + 0.005, yf + 0.001), (x + s * 0.030 + 0.004, yf - 0.011),
                  (x + s * 0.030 - 0.004, yf - 0.011)], [0.0, 0.0, 0.003, 0.003], 0.030, mat, z0=zp + 0.0145, re=0.003, n=3, ne=2)
    for s in (-1, 1):                                    # orejas del pivote
        side(mb, [(x + s * 0.0215 - 0.003, zp - 0.054), (x + s * 0.0215 + 0.003, zp - 0.054), (x + s * 0.0215 + 0.003, zp - 0.036),
                  (x + s * 0.0215 - 0.003, zp - 0.036)], [0.0015] * 4, 0.012, mat, y0=yf - 0.005, re=0.0012, n=2, ne=1)
    revolve(mb, [(0.0030, -0.0245), (0.0030, 0.0245)], "steel", seg=20, M=_T(x, yf - 0.0075, zp - 0.046) @ _Ry(90))
    side(mb, [(x - 0.018, zp - 0.050), (x + 0.018, zp - 0.050), (x + 0.020, zp + 0.020), (x + 0.017, zp + 0.025),
              (x - 0.017, zp + 0.025), (x - 0.020, zp + 0.020)], [0.004, 0.004, 0.003, 0.002, 0.002, 0.003], 0.0068, mat,
         y0=yf - 0.0135, re=0.0022, n=3, ne=2)
    for k in range(5):
        zr = zp - 0.040 + k * 0.0055
        side(mb, [(x - 0.014, zr), (x + 0.014, zr), (x + 0.014, zr + 0.0022), (x - 0.014, zr + 0.0022)], [0.001] * 4, 0.0016, mat,
             y0=yf - 0.0175, re=0.0006, n=2, ne=1)
    side(mb, [(x - 0.017, zp + 0.014), (x + 0.017, zp + 0.014), (x + 0.017, zp + 0.025), (x - 0.017, zp + 0.025)],
         [0.0015] * 4, 0.0075, mat, y0=yf - 0.0075, re=0.0015, n=2, ne=1)                # gancho sobre la uña
    side(mb, [(x - 0.016, zp + 0.010), (x + 0.016, zp + 0.010), (x + 0.016, zp + 0.016), (x - 0.016, zp + 0.016)],
         [0.0015] * 4, 0.0060, mat, y0=yf - 0.0030, re=0.0012, n=2, ne=1)                # uña de la tapa


def hard_case(seed=0, L=1.0):
    """Maleta rígida de polímero para arma larga (L × 0,37 × 0,14 m; L = 1,0 por omisión, clase «42 in»): casco inferior y
    tapa moldeados de esquinas redondeadas, rebordes de lengüeta y ranura en la línea de cierre con empaque oscuro visible,
    nervios verticales de refuerzo, panel superior realzado con patas de apilado, esquinas reforzadas, 4 cierres de doble
    acción con guardas y estrías, 2 asas frontales y 1 de extremo abatibles con hule de dedos, 2 bisagras de nudillos con
    pasador atrás, 2 portacandados con barreno, válvula de presión moleteada, ruedas con eje en el extremo -X dentro de sus
    alojamientos, patines y patas de hule. ORIGEN: centro de la base en el piso; largo en X, frente (cierres, asas) hacia -Y.
    Fuentes: pelican.com (1720 / 1750: cierres de doble acción, válvula de presión, ruedas, portacandados); planooutdoors.com
    (All Weather 2 42": 44,4 × 16,8 × 6,4 in); 511tactical.com (Hard Case 42: 42,5 × 14,5 × 5,5 in)."""
    mb = MB()
    PL = "polymer" if seed % 2 == 0 else "paint_tan"
    D, H = 0.37, 0.14
    zp = 0.084                                           # línea de cierre
    rc = 0.032
    Lb, Db = L - 0.008, D - 0.008
    slab2(mb, _T(0, 0, 0.007), Lb, Db, zp - 0.0125 - 0.007, rc, PL, re_b=0.014, ne_b=4, nc=6)      # casco inferior
    slab2(mb, _T(0, 0, zp + 0.0125), Lb, Db, H - zp - 0.0125, rc, PL, re_t=0.018, ne_t=5, nc=6)     # tapa
    slab2(mb, _T(0, 0, zp - 0.0135), L, D, 0.0115, rc + 0.004, PL, re_t=0.0018, ne_t=2, re_b=0.004, ne_b=2, nc=6)
    slab2(mb, _T(0, 0, zp + 0.0020), L, D, 0.0115, rc + 0.004, PL, re_t=0.004, ne_t=2, re_b=0.0018, ne_b=2, nc=6)
    slab2(mb, _T(0, 0, zp - 0.0030), L - 0.006, D - 0.006, 0.0060, rc + 0.001, "rubber", nc=6)     # empaque
    slab2(mb, _T(0, 0, H - 0.0012), L - 0.17, D - 0.11, 0.0040, 0.022, PL, re_t=0.0025, ne_t=2, nc=6)   # panel realzado
    for sx in (-1, 1):
        for sy in (-1, 1):                               # patas de apilado (tapa) y esquinas reforzadas
            slab2(mb, _T(sx * (L / 2 - 0.055), sy * (D / 2 - 0.045), H - 0.0035), 0.050, 0.040, 0.0050, 0.012, PL, re_t=0.002,
                  ne_t=2, nc=4)
    # nervios verticales de refuerzo (frente y espalda) entre cierres
    xl = [-L / 2 + 0.10 + (L - 0.20) * k / 3 for k in range(4)]
    for sy in (-1, 1):
        yf = sy * Db / 2
        for k in ((1,) if sy < 0 else (0, 1, 2)):
            xm = (xl[k] + xl[k + 1]) / 2
            for dx in (-0.020, 0.020):
                P = [(xm + dx - 0.004, yf), (xm + dx + 0.004, yf), (xm + dx + 0.003, yf + sy * 0.0055), (xm + dx - 0.003, yf + sy * 0.0055)]
                plan(mb, P, [0.0, 0.0, 0.0022, 0.0022], zp - 0.0145 - 0.018, PL, z0=0.018, re=0.003, n=3, ne=2)
    # cierres
    for x in xl:
        _case_latch(mb, x, -Db / 2, zp, PL)
    # asas frontales y de extremo
    for x in ((xl[0] + xl[1]) / 2, (xl[2] + xl[3]) / 2):
        _case_handle(mb, _T(x, -Db / 2, zp - 0.022), 0.120, PL)
    _case_handle(mb, _T(L / 2 - 0.004 + 0.004, 0, zp - 0.020) @ _Rz(90) @ _T(0, 0.004, 0), 0.110, PL)
    # bisagras de nudillos atrás (+Y)
    yb = Db / 2 + 0.0068
    for xc in (-L / 2 + 0.22, L / 2 - 0.22):
        for k in range(5):
            xa = xc - 0.065 + k * 0.026
            lid_k = k % 2 == 1
            revolve(mb, [(0.0062, xa + 0.0006), (0.0068, xa + 0.0016), (0.0068, xa + 0.0244), (0.0062, xa + 0.0254)], PL, seg=32,
                    M=_T(0, yb, zp) @ _Ry(90), caps=True)
            za, zb_ = (zp + 0.002, zp + 0.024) if lid_k else (zp - 0.024, zp - 0.002)
            side(mb, [(xa + 0.0010, za), (xa + 0.0250, za), (xa + 0.0250, zb_), (xa + 0.0010, zb_)], [0.002] * 4, 0.0070, PL,
                 y0=Db / 2 + 0.0026, re=0.0015, n=2, ne=1)
        revolve(mb, [(0.0, -0.002), (0.0035, -0.002), (0.0035, 0.0), (0.0021, 0.0), (0.0021, 0.132), (0.0035, 0.132),
                     (0.0035, 0.134), (0.0, 0.134)], "steel", seg=20, M=_T(xc - 0.066, yb, zp) @ _Ry(90), caps=False)
    # portacandados (tapa + casco) en los extremos del frente
    for s in (-1, 1):
        x = s * (L / 2 - 0.050)
        for (z0, z1) in ((zp - 0.032, zp - 0.003), (zp + 0.003, zp + 0.032)):
            holed(mb, _T(x, -Db / 2 + 0.0005, (z0 + z1) / 2) @ _Rx(90), (0.0, 0.0, 0.0090, (z1 - z0) / 2, 0.004),
                  (0.0, (0.008 if z0 < zp else -0.008), 0.0042, 0.0042, 0.0042), 0.0110, re_o=0.0018, re_i=0.0012, n=40,
                  mat=PL, ne=2, ctr=(0.0, 0.0))
    # válvula de presión (frente del casco, a la izquierda)
    Mv = _T((xl[1] + xl[2]) / 2 - 0.075, -Db / 2, zp - 0.040) @ _Rx(90)
    revolve(mb, [(0.0135, -0.001), (0.0135, 0.0020), (0.0120, 0.0032), (0.0, 0.0032)], PL, seg=6, M=Mv, caps=False, phase=PI / 6)
    _knob_k(mb, Mv @ _T(0, 0, 0.0030), 0.0110, 0.0080, PL, nt=28, dp=0.0007)
    revolve(mb, [(0.0, 0.0), (0.0030, 0.0), (0.0030, 0.0004), (0.0, 0.0004)], "cable", seg=16, M=Mv @ _T(0, 0, 0.0108), caps=False)
    # ruedas en el extremo -X dentro de sus alojamientos
    xw, zw = -L / 2 + 0.034, 0.033
    for sy in (-1, 1):
        y = sy * 0.122
        slab2(mb, _T(xw + 0.004, y, 0.006), 0.090, 0.050, 0.074, 0.018, PL, re_t=0.010, ne_t=3, re_b=0.004, ne_b=2, nc=5)
        Mw = _T(xw - 0.012, y + sy * 0.0265, zw) @ _Rx(-90 * sy)
        prof = [(0.0150, 0.0), (0.0270, 0.0), (0.0315, 0.0030), (0.0332, 0.0080), (0.0332, 0.0170), (0.0315, 0.0220),
                (0.0270, 0.0250), (0.0150, 0.0250)]
        revolve(mb, prof, "rubber", seg=40, M=Mw, closed=True)
        revolve(mb, [(0.0040, -0.001), (0.0150, -0.001), (0.0150, 0.026), (0.0040, 0.026)], "plastic", seg=40, M=Mw, closed=True)
        for k in range(5):                               # rayos de la maza
            a = 2 * PI * k / 5
            side(mb, [(0.0042, -0.0095), (0.0152, -0.0095), (0.0152, 0.0095), (0.0042, 0.0095)], 0.0, 0.0030, "plastic",
                 re=0.0006, n=2, ne=1, M=Mw @ _T(0, 0, 0.0125) @ _Rz(math.degrees(a)))
    revolve(mb, [(0.0, -0.152), (0.0045, -0.152), (0.0045, 0.152), (0.0, 0.152)], "steel", seg=20,
            M=_T(xw - 0.012, 0, zw) @ _Rx(90), caps=False)
    # patines inferiores y patas de hule
    for y in (-0.095, 0.095):
        plan(mb, [(-L / 2 + 0.10, y - 0.012), (L / 2 - 0.06, y - 0.012), (L / 2 - 0.06, y + 0.012), (-L / 2 + 0.10, y + 0.012)],
             [0.010] * 4, 0.0060, PL, z0=0.0040, re=0.0025, n=3, ne=2)
    for (x, y) in ((L / 2 - 0.07, -0.13), (L / 2 - 0.07, 0.13), (-L / 2 + 0.16, -0.13), (-L / 2 + 0.16, 0.13)):
        revolve(mb, [(0.0, 0.0), (0.0120, 0.0), (0.0145, 0.0025), (0.0150, 0.0080)], "rubber", seg=32, M=_T(x, y, 0), caps=False)
    return mb

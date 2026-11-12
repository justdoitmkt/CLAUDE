"""kit/antennas.py — equipo de telecomunicaciones del sitio celular COM_1_antena (2026, actual, no futurista), calidad AAA (R-AAA).

Piezas (todas devuelven un MB; metros, Z arriba):
- panel_antenna(): panel pasivo multibanda de 8 puertos clase 2,6 m (2688 × 301 × 181 mm, 22,3 kg; CommScope 8P-2L6M-D4-V5)
  con soportes superior/inferior de inclinación mecánica y abrazaderas al tubo.
- aau(): unidad activa 5G massive-MIMO 64T64R (795 × 395 × 220 mm, Huawei AAU5613) con disipador de aletas, asa, bahía de
  conectores con tapa, soporte de inclinación y abrazaderas.
- rru(): radio remota 4T4R (480 × 270 × 140 mm, Huawei RRU3256) con aletas verticales, bahía de mantenimiento, asa y soporte.
- mw_dish(): antena de microondas de 0,6 / 0,9 m con faldón (shroud), radomo de tela gris tensado con fleje, reflector,
  montaje a tubo con ajuste fino de azimut y elevación, ODU de montaje directo con asa y su cable con gaza de goteo.
- obstruction_light(): baliza roja de baja intensidad tipo L-810 (LED), base fundida, prensaestopas, niple y placa.
- lightning_rod(): pararrayos Franklin (punta de cobre, mástil galvanizado, base y conductor de bajada de cobre).
- jumper(): cable puente (jumper) con gaza de goteo por una polilínea con dobleces de radio real y conectores 4.3-10.
- pipe_mount(): tubo vertical Ø 76 mm galvanizado con sus dos brazos separadores a la plataforma (abrazaderas U, placas, tuercas).
- panel_ports(), rru_ports(), aau_tail_ends(), drip_loop_points(): puntos para tender jumpers entre equipos.

Convenciones del equipo montado a tubo (panel_antenna, aau, rru, mw_dish):
- El tubo de montaje (Ø 76 mm) es vertical y su EJE ES EL EJE Z LOCAL (x = 0, y = 0). La pieza no incluye el tubo.
- El equipo cuelga del lado -Y del tubo y radia hacia -Y (cara frontal = -Y, hacia fuera de la plataforma).
- z = 0: ver el docstring de cada función (normalmente la base del cuerpo del equipo).
Materiales: galvanized, steel (tornillería inoxidable), aluminium, plastic, radome, rubber, cable, copper, enamel, sign_white,
sign_red, paint_yellow.
"""
import math

import bpy  # noqa: F401  (bpy antes que mathutils)
from mathutils import Matrix, Vector

from kit import port
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rng, rr_profile
from kit.clinic_equipo import loft_rings, revolve

PIPE_R = 0.038            # tubo de montaje: 3" nominal, Ø 76 mm (OD)
GALV = "galvanized"
SS = "steel"


# ======================================================================================================== utilidades
def _V(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def _washer(mb, M, d, seg=16, mat=SS):
    """Arandela plana sobre z = 0 local (eje +Z); devuelve su espesor."""
    t = max(0.0015, d * 0.16)
    revolve(mb, [(d * 1.05, -0.0004), (d * 1.05, t)], mat, seg=seg, M=M)
    return t


def _hex(mb, M, d, h=None, mat=SS, z=0.0):
    """Prisma hexagonal con chaflán (tuerca o cabeza de tornillo) de rosca nominal d, sobre z local."""
    h = h if h is not None else 0.8 * d
    R = 0.8 * d / math.cos(PI / 6)
    revolve(mb, [(0.86 * R, z), (R, z + 0.14 * h), (R, z + 0.86 * h), (0.86 * R, z + h)], mat, seg=6, M=M, phase=PI / 6)
    return h


def _nut(mb, M, d=0.012, washer=True, mat=SS):
    """Tuerca hexagonal con arandela apoyada en el plano z = 0 local (eje +Z hacia fuera de la superficie)."""
    z = -0.0003
    if washer:
        z = _washer(mb, M, d, mat=mat) - 0.0003
    return z + _hex(mb, M, d, mat=mat, z=z)


def _rod(mb, p0, p1, r, seg=14, mat=SS):
    mb.cyl(_V(p0), _V(p1), r, seg=seg, mat=mat)


def _stadium(L, r, n=6, round0=False):
    """Contorno de solera de x = 0 a x = L, ancho 2r, extremo redondo en x = L (y en x = 0 si round0). Antihorario."""
    if round0:
        out = [(r * math.cos(PI / 2 + PI * k / n), r * math.sin(PI / 2 + PI * k / n)) for k in range(n + 1)]
    else:
        out = [(0.0, r), (0.0, -r)]
    out += [(L + r * math.cos(-PI / 2 + PI * k / n), r * math.sin(-PI / 2 + PI * k / n)) for k in range(n + 1)]
    return out


def _bar(mb, p0, p1, r, t, x_off, mat=GALV, round0=True, n=6, M=None):
    """Solera vertical (en el plano YZ del marco M) de p0 a p1 (puntos (y, z)), ancho 2r, espesor t a partir de x_off
    (de x_off a x_off + t, o hacia -x si t < 0). Extremos redondos (orejas de pivote)."""
    a = Vector((x_off, p0[0], p0[1]))
    b = Vector((x_off, p1[0], p1[1]))
    Mf, L = port.frame_on(a, b, up=(1, 0, 0))
    lo = min(0.0, t)
    mb.plate(_stadium(L, r, n=n, round0=round0), abs(t), mat, m=(M if M is not None else Matrix()) @ Mf @ _T(0, 0, lo))


def _offset(prof, d):
    """Desplaza un contorno cerrado antihorario d hacia fuera (d < 0 hacia dentro), con inglete en los vértices."""
    n = len(prof)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(prof[i - 1]), Vector(prof[i]), Vector(prof[(i + 1) % n])
        e0, e1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n0, n1 = Vector((e0.y, -e0.x)), Vector((e1.y, -e1.x))
        m = (n0 + n1)
        m = m.normalized() if m.length > 1e-9 else n0
        c = max(m.dot(n0), 0.35)
        q = p1 + m * (d / c)
        out.append((q.x, q.y))
    return out


def _ring(prof, z, d=0.0):
    pr = _offset(prof, d) if d else prof
    return [Vector((x, y, z)) for (x, y) in pr]


# ======================================================================================================== abrazadera
def _clamp(mb, M, w=0.16, h=0.05, t=0.005, gap=0.012, rod_x=0.062, rod_d=0.012, mat=GALV, lug=None):
    """Abrazadera de dos mordazas en V (lámina doblada galvanizada) alrededor del tubo Ø 76, apretada con dos espárragos M12
    con tuercas y arandelas a ambos lados. M: marco con el eje del tubo = Z local y el centro de la abrazadera en z = 0.
    lug = (tipo, y_pivote): oreja soldada al vértice de la mordaza delantera (-Y) hasta el pivote: 'single' (una solera
    de 10 mm centrada) o 'double' (dos soleras a ±6..14 mm). Devuelve la y de la cara exterior del vértice delantero."""
    k = math.sqrt(2.0) * (PIPE_R + t / 2)
    yw = gap / 2 + t / 2
    xb = k - yw
    N = M.to_3x3() @ Vector((0, 0, 1))
    for s in (-1, 1):
        path = fillet([(-w / 2, s * yw, 0.0), (-xb, s * yw, 0.0), (0.0, s * k, 0.0), (xb, s * yw, 0.0), (w / 2, s * yw, 0.0)], 0.008, 2)
        mb.sweep(rr_profile(t, h, 0.0013, n=1), [M @ Vector(p) for p in path], mat=mat, normal=N)
    yo = yw + t / 2
    for x in (-rod_x, rod_x):
        hh = _hex(mb, M @ _T(x, -yo, 0) @ _Rx(90), rod_d, h=0.65 * rod_d, z=-0.0003)
        top = _nut(mb, M @ _T(x, yo, 0) @ _Rx(-90), rod_d)
        _rod(mb, M @ Vector((x, -yo - hh + 0.003, 0)), M @ Vector((x, yo + top + 0.004, 0)), rod_d / 2, seg=14, mat=SS)
    ya = -(k + t / 2)
    if lug:
        kind, ypiv = lug[0], lug[1]
        rl = 0.019
        if kind == "single":
            _bar(mb, (ya + 0.006, 0.0), (ypiv, 0.0), rl, 0.010, -0.005, mat=mat, round0=False, M=M)
        else:
            x0, x1 = lug[2] if len(lug) > 2 else (0.006, 0.014)
            for sx in (1, -1):                                   # arranca dentro de la lámina de la mordaza en V
                _bar(mb, (-(k - x1) - 0.001, 0.0), (ypiv, 0.0), rl, sx * (x1 - x0), sx * x0, mat=mat, round0=False, M=M)
    return ya


def _pivot_bolt(mb, M, p, x_out, d=0.012):
    """Tornillo de pivote a lo largo de X por p = (y, z) del marco M, a través de placas que ocupan |x| <= x_out: cabeza
    hexagonal apoyada en -x_out, tuerca de seguridad (sin arandela) en +x_out y 3 mm de espárrago visible."""
    hh = _hex(mb, M @ _T(-x_out, p[0], p[1]) @ _Ry(-90), d, h=0.6 * d, z=-0.0003)
    nh = _hex(mb, M @ _T(x_out, p[0], p[1]) @ _Ry(90), d, h=0.9 * d, z=-0.0003)
    _rod(mb, M @ Vector((-x_out - hh + 0.003, p[0], p[1])), M @ Vector((x_out + nh + 0.003, p[0], p[1])), d / 2, seg=14)


# ======================================================================================================== panel pasivo
def _panel_profile(W=0.301, D=0.181, rails=True):
    """Sección del radomo (x lateral, y profundidad; espalda en y = 0, frente en y = -D), antihorario visto desde +Z.
    Frente abombado (sagita 14 mm), esquinas delanteras de radio amplio, costados con leve conicidad hacia la espalda,
    espalda plana con dos rieles ranurados (x = ±75 mm) para los soportes."""
    def bez(a, c, b, n):
        return [tuple(Vector(a).lerp(Vector(c), k / n).lerp(Vector(c).lerp(Vector(b), k / n), k / n)) for k in range(n + 1)]

    hw = W / 2
    xa = hw - 0.024
    sag = 0.014
    Rf = (xa * xa + sag * sag) / (2 * sag)
    right = []
    # frente (de x = 0 hacia +x), esquina delantera, costado, esquina trasera, espalda con riel (hacia x = 0)
    for k in range(5):
        x = xa * k / 5
        right.append((x, -D + (Rf - math.sqrt(Rf * Rf - x * x))))
    right += bez((xa, -D + sag), (hw, -D + sag + 0.004), (hw, -D + 0.05), 5)
    right += [(hw - 0.0015, -0.10)]
    right += bez((hw - 0.003, -0.016), (hw - 0.003, 0.0), (hw - 0.019, 0.0), 3)
    if rails:
        right += [(0.092, 0.0), (0.090, -0.0015), (0.090, -0.006), (0.060, -0.006), (0.060, -0.0015), (0.058, 0.0)]
    else:
        right += [(0.058, 0.0)]
    right += [(0.0, 0.0)]
    clean = []
    for p in right:
        if not clean or (Vector(p) - Vector(clean[-1])).length > 1e-6:
            clean.append(p)
    half = clean[:-1]                       # de (0, -D) a (0.058, 0): frente, costado y espalda del lado derecho
    lhalf = [(-x, y) for (x, y) in reversed(half[1:])]
    outline = half + [(0.0, 0.0)] + lhalf
    return outline


def _end_cap(mb, MA, prof, z0, z1, top, mat="plastic"):
    """Tapa moldeada del extremo: sobrepasa 2,5 mm el contorno del radomo, canto redondeado hacia la cara del extremo;
    abraza el radomo (escalón visible de 2,5 mm) y su cara interna queda dentro del radomo. prof: contorno sin ranuras."""
    if top:
        rings = [_ring(prof, z0, -0.0015), _ring(prof, z0, 0.0025), _ring(prof, z1 - 0.0065, 0.0025), _ring(prof, z1 - 0.0015, -0.002),
                 _ring(prof, z1, -0.012)]
    else:
        rings = [_ring(prof, z0, -0.012), _ring(prof, z0 + 0.0015, -0.002), _ring(prof, z0 + 0.0065, 0.0025), _ring(prof, z1, 0.0025),
                 _ring(prof, z1, -0.0015)]
    loft_rings(mb, rings, mat, M=MA)


def _port_43_10(mb, M, seg=16):
    """Puerto hembra 4.3-10 de panel (eje +Z local hacia fuera): contratuerca hexagonal y cuerpo roscado con boca."""
    _hex(mb, M, 0.0155, h=0.0065, mat=SS, z=-0.001)
    revolve(mb, [(0.0098, 0.004), (0.0098, 0.0235), (0.0087, 0.0262), (0.0060, 0.0262), (0.0056, 0.020), (0.0, 0.020)], SS,
            seg=seg, M=M)


def _aisg_port(mb, M, seg=16):
    """Puerto AISG de 8 pines con su tapa protectora de hule (eje +Z hacia fuera)."""
    _hex(mb, M, 0.0135, h=0.005, mat=SS, z=-0.001)
    revolve(mb, [(0.0105, 0.0035), (0.0105, 0.020), (0.0094, 0.0225), (0.0, 0.0232)], "rubber", seg=seg, M=M)
    mb.tube([M @ Vector((0.0104, 0.0, 0.012)), M @ Vector((0.016, 0.0, 0.010)), M @ Vector((0.019, 0.0, 0.0)),
             M @ Vector((0.018, 0.0, -0.0008))], 0.0018, seg=6, mat="rubber")


def _antenna_bracket(mb, MA, zp, ypiv, plate_w=0.21, plate_h=0.12, bolts_x=(-0.075, 0.075), bolts_dz=(-0.04, 0.04), hh=0.055,
                     mat="aluminium"):
    """Soporte fundido atornillado a la espalda del equipo: placa con cantos redondos, dos orejas (cartelas) a ±6..14 mm hasta
    el pivote (y = ypiv exacto) y 4 tornillos M8. Coordenadas del cuerpo (espalda y = 0, z a lo largo)."""
    from kit.clinic_servicios import slab
    t = 0.010
    slab(mb, MA @ _T(0, -0.001, zp) @ _Rx(-90), plate_w, plate_h, t + 0.001, rc=0.012, re=0.003, mat=mat, nc=2, ne=1)
    u0 = t - 0.002
    up = ypiv - u0
    for xo, tt in ((0.006, 0.008), (-0.006, -0.008)):
        outline = [(0.0, -hh), (up - 0.004, -0.019)]
        outline += [(up + 0.019 * math.cos(-PI / 2 + PI * k / 6), 0.019 * math.sin(-PI / 2 + PI * k / 6)) for k in range(1, 6)]
        outline += [(up - 0.004, 0.019), (0.0, hh)]
        perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # (u, v, w) -> (y, z, x)
        lo = min(0.0, tt)
        mb.plate(outline, abs(tt), mat, m=MA @ _T(xo + lo, u0, zp) @ perm)
    for x in bolts_x:
        for dz in bolts_dz:
            _hex(mb, MA @ _T(x, t, zp + dz) @ _Rx(-90), 0.008, h=0.0055, z=-0.0004)


def _tilt_mount(mb, MA, Pb, zt_body, ypiv, La, yc=-0.098):
    """Abrazadera inferior con pivote + abrazadera superior con brazo de inclinación telescópico (dos pares de soleras con
    tornillo de bloqueo). MA: marco del cuerpo ya inclinado; Pb: pivote inferior (mundo); zt_body: z del pivote superior en el
    cuerpo. El brazo de largo La sube del pivote del cuerpo a la oreja doble de la abrazadera superior."""
    _clamp(mb, _T(0, 0, Pb.z), lug=("single", Pb.y))
    _pivot_bolt(mb, Matrix(), (Pb.y, Pb.z), 0.014)
    Pt = MA @ Vector((0.0, ypiv, zt_body))
    dy = abs(Pt.y - yc)
    La = max(La, dy * 1.3)                          # a mucha inclinación el brazo se extiende (sube a ≥ 40° del tubo)
    zc = Pt.z + math.sqrt(La * La - dy * dy)
    _clamp(mb, _T(0, 0, zc), lug=("double", yc, (0.0135, 0.0215)))
    Pc = Vector((0.0, yc, zc))
    u = (Pc - Pt).normalized()
    for sx in (-1, 1):
        m1 = Pt + u * (La * 0.62)
        m0 = Pc - u * (La * 0.62)
        _bar(mb, (Pt.y, Pt.z), (m1.y, m1.z), 0.016, sx * 0.006, sx * 0.0155, round0=True)
        _bar(mb, (m0.y, m0.z), (Pc.y, Pc.z), 0.016, sx * 0.006, sx * 0.0215, round0=True)
    _pivot_bolt(mb, Matrix(), (Pt.y, Pt.z), 0.0215, d=0.010)
    for p in (Pc, (Pt + Pc) / 2):
        _pivot_bolt(mb, Matrix(), (p.y, p.z), 0.0275, d=0.010)
    return Pt, Pc


def panel_antenna(seed=0, tilt_deg=4.0):
    """Panel pasivo multibanda de 8 puertos, clase 2,6 m: 2688 × 301 × 181 mm (CommScope 8P-2L6M-D4-V5: 22,3 kg, 8 × 4.3-10
    hembra, RET interno con AISG). Radomo extruido de frente abombado con rieles ranurados en la espalda, tapas moldeadas en los
    extremos, 8 puertos 4.3-10 y 2 AISG en la tapa inferior, soportes fundidos arriba y abajo, abrazaderas en V con espárragos
    M12 al tubo, pivote inferior y brazo de inclinación telescópico arriba (inclinación mecánica `tilt_deg` hacia abajo).

    Origen: EJE DEL TUBO Ø 76 = eje Z (x = 0, y = 0); z = 0 = cara inferior del cuerpo con inclinación 0 (los puertos bajan
    ~30 mm más). Frente radiante hacia -Y; espalda del radomo a 165 mm del eje del tubo."""
    r = rng(seed)
    mb = MB()
    L, W, D = 2.688, 0.301, 0.181
    yb = -0.165                                  # espalda del radomo (inclinación 0)
    zbp, ztp = 0.32, L - 0.30                    # pivotes (coordenadas del cuerpo)
    ypiv = 0.05                                  # pivote a 50 mm detrás de la espalda
    Pb = Vector((0.0, yb + ypiv, zbp))
    MA = _T(*Pb) @ _Rx(tilt_deg) @ _T(*(-Pb)) @ _T(0, yb, 0)
    prof = _panel_profile(W, D)
    hc = 0.045
    # radomo (extrusión) metido 10 mm en cada tapa
    loft_rings(mb, [_ring(prof, hc - 0.012), _ring(prof, L - hc + 0.012)], "radome", M=MA)
    pcap = _panel_profile(W, D, rails=False)
    _end_cap(mb, MA, pcap, 0.0, hc, top=False)
    _end_cap(mb, MA, pcap, L - hc, L, top=True)
    # tapa inferior: 8 puertos 4.3-10 (2 filas de 4), 2 AISG y tapón de ventilación
    for row, y in enumerate((-0.045, -0.100)):
        for x in (-0.105, -0.035, 0.035, 0.105):
            _port_43_10(mb, MA @ _T(x, y, 0.0) @ _Rx(180))
    for x in (-0.06, 0.06):
        _aisg_port(mb, MA @ _T(x, -0.148, 0.0) @ _Rx(180) @ _Rz(float(r.uniform(0, 360))))
    revolve(mb, [(0.006, -0.001), (0.006, 0.004), (0.0045, 0.0055), (0.0, 0.0058)], "plastic", seg=12, M=MA @ _T(0, -0.148, 0) @ _Rx(180))
    # placa de identificación en la espalda
    mb.box((-0.045, -0.0015, 0.42), (0.045, 0.0016, 0.48), "sign_white", bevel=0.0006, seg=1, m=MA)
    # soportes del cuerpo
    _antenna_bracket(mb, MA, zbp, ypiv)
    _antenna_bracket(mb, MA, ztp, ypiv)
    # abrazadera inferior con pivote; brazo de inclinación a la abrazadera superior
    _tilt_mount(mb, MA, Pb, ztp, ypiv, La=0.24)
    return mb


def _crown_slab(mb, M, w, d, h, rc, re, re0, crown, mat, nc=5, ne=3, steps=(0.82, 0.55, 0.25), groove=None):
    """Como clinic_servicios.slab (rectángulo redondeado w × d en XY local, de z = 0 a h, cantos re arriba / re0 abajo) pero
    con la cara superior abombada `crown` (radomo moldeado): anillos concéntricos hacia el centro. groove = (margen, ancho,
    hondo): ranura moldeada perimetral a `margen` del canto (marco del radomo)."""
    from kit.clinic_servicios import _edge_levels, rr_pts, skin
    loops = []
    for (dl, z) in _edge_levels(h, re, re0, ne):
        loops.append([(x, y, z) for (x, y) in rr_pts(w - 2 * dl, d - 2 * dl, max(rc - dl, 3e-4), nc)])
    w2, d2, r2 = w - 2 * re, d - 2 * re, max(rc - re, 3e-4)
    if groove:
        g0, gw, gd = groove
        for (ins, dz) in ((g0, 0.0), (g0 + 0.0008, -gd), (g0 + gw - 0.0008, -gd), (g0 + gw, 0.0)):
            sfx = 1.0 - 2 * ins / w2
            z = h + crown * (1.0 - sfx * sfx) + dz
            loops.append([(x, y, z) for (x, y) in rr_pts(w2 - 2 * ins, d2 - 2 * ins, max(r2 - ins, 0.004), nc)])
    for sf in steps:
        z = h + crown * (1.0 - sf * sf)
        loops.append([(x, y, z) for (x, y) in rr_pts(w2 * sf, d2 * sf, r2 * sf, nc)])
    skin(mb, loops, mat, M)


# ======================================================================================================== AAU 5G
def _fin(mb, M, x, y0, y1, z0, z1, t0=0.0045, t1=0.0024, taper=0.035, mat="aluminium"):
    """Aleta de disipador fundida (vertical): sección que se afila de t0 en la raíz (y0, embebida 1 mm) a t1 con punta
    redonda en y1; extremos superior e inferior en chaflán (la punta es más corta que la raíz)."""
    s = 1.0 if y1 > y0 else -1.0
    D = abs(y1 - y0)

    def ring(z, k):
        tip = y0 + s * D * k
        e = min(0.002, D * k * 0.4)
        return [Vector((x - t0 / 2, y0, z)), Vector((x + t0 / 2, y0, z)), Vector((x + t1 / 2, tip - s * e, z)), Vector((x, tip, z)),
                Vector((x - t1 / 2, tip - s * e, z))]

    loft_rings(mb, [ring(z0, 0.3), ring(z0 + taper, 1.0), ring(z1 - taper, 1.0), ring(z1, 0.3)], mat, M=M)


def _tail(mb, M, pts, r, mat="cable", seg=14, bend=0.04, nseg=5):
    """Cola de cable que sale del equipo por un pasacables (extremo libre tapado: ahí lo continúa un jumper())."""
    mb.tube([M @ _V(p) for p in fillet(pts, bend, nseg)], r, seg=seg, mat=mat)


def _grommet(mb, M, r_cable, mat="rubber"):
    """Pasacables de hule (prensaestopa de domo) en z = 0 local, eje +Z hacia fuera."""
    ro = r_cable + 0.006
    revolve(mb, [(ro, -0.001), (ro, 0.0045), (r_cable + 0.0013, 0.0095), (r_cable + 0.0003, 0.0095)], mat, seg=16, M=M)


def _ground_lug(mb, M, mat="copper"):
    """Terminal de tierra: zapata de cobre de un ojo sobre espárrago con tuerca, y el cable verde de tierra saliendo hacia -Z
    local (marco M: plano de la superficie XY, +Z fuera; el cable baja por -Y local)."""
    revolve(mb, [(0.0085, -0.0004), (0.0085, 0.0018), (0.0068, 0.0026), (0.0, 0.0026)], mat, seg=16, M=M)       # ojo
    mb.box((-0.0055, -0.024, -0.0004), (0.0055, -0.0072, 0.0016), mat, bevel=0.0006, seg=1, m=M)              # lengüeta
    revolve(mb, [(0.0045, -0.0215), (0.0062, -0.0225), (0.0062, -0.036), (0.0048, -0.037)], mat, seg=16,
            M=M @ _T(0, 0, 0.0058) @ _Rx(-90))                                                                 # barril
    _hex(mb, M @ _T(0, 0, 0.0022), 0.006, h=0.005)
    _rod(mb, M @ Vector((0, 0, -0.003)), M @ Vector((0, 0, 0.0095)), 0.003)


def aau(seed=0, tilt_deg=2.0, tails=True):
    """AAU 5G massive-MIMO 64T64R (Huawei AAU5613: 795 × 395 × 220 mm, 40 kg). Radomo frontal moldeado (abombado 5 mm, ranura
    perimetral de marco, cantos redondos) con junta perimetral contra la carcasa fundida, disipador de 24 aletas verticales afiladas en la espalda con espina central
    de montaje, asa tubular arriba, bahía de cables inferior con tapa atornillada y pasacables (cola de alimentación negra y dos
    de fibra amarillas), terminal de tierra, placa de datos; adaptador con orejas, pivote inferior, brazo de inclinación
    (`tilt_deg` hacia abajo) y dos abrazaderas en V al tubo.

    Origen: EJE DEL TUBO Ø 76 = eje Z (x = 0, y = 0); z = 0 = base del cuerpo con inclinación 0 (la tapa de cables baja 25 mm y
    las colas de cable ~0,3 m). Frente radiante hacia -Y; puntas de las aletas a 130 mm del eje del tubo.
    Extremos libres de las colas (para continuarlas con jumper()): aau_tail_ends(seed, tilt_deg); con 2° ≈ (-0.05, -0.19, -0.30)
    alimentación, (0.03 / 0.05, -0.19, -0.30) fibras, (0.14, -0.19, -0.30) tierra."""
    from kit.clinic_servicios import slab
    r = rng(seed)
    mb = MB()
    H, W = 0.795, 0.395                          # fondo total 0,220 (radomo 0,07 + carcasa 0,049 + aletas 0,105)
    yb = -0.130                                  # puntas de aletas (inclinación 0)
    zbp, ztp = 0.15, H - 0.15
    ypiv = 0.022                                 # pivote 22 mm detrás de las aletas (cuerpo: espina en y = -0.035)
    Pb = Vector((0.0, yb + ypiv, zbp))
    MA = _T(*Pb) @ _Rx(tilt_deg) @ _T(*(-Pb)) @ _T(0, yb, 0)
    # radomo frontal y carcasa fundida (junta de 2 mm entre ambos)
    _crown_slab(mb, MA @ _T(0, -0.150, H / 2) @ _Rx(90), W, H, 0.065, rc=0.030, re=0.012, re0=0.003, crown=0.005, mat="radome",
                groove=(0.014, 0.005, 0.0022))
    slab(mb, MA @ _T(0, -0.1045, H / 2) @ _Rx(90), W - 0.006, H - 0.006, 0.0490, rc=0.027, re=0.002, re0=0.005, mat="aluminium",
         nc=5, ne=2)
    # aletas del disipador (dos grupos de 12 a los lados de la espina central)
    for k in range(12):
        for sx in (-1, 1):
            _fin(mb, MA, sx * (0.050 + 0.0125 * k), -0.1055, 0.0, 0.045, H - 0.045)
    # espina de montaje: nervio central fundido con dos almohadillas para el adaptador
    slab(mb, MA @ _T(0, -0.108, H / 2) @ _Rx(-90), 0.064, H - 0.11, 0.073, rc=0.008, re=0.004, re0=0.0, mat="aluminium", nc=2, ne=2)
    # adaptador galvanizado sobre la espina (cuerpo: espalda de la espina en y = -0.035)
    MS = MA @ _T(0, -0.035, 0)
    _antenna_bracket(mb, MS, zbp, ypiv + 0.035, plate_w=0.11, plate_h=0.13, bolts_x=(-0.04, 0.04), bolts_dz=(-0.045, 0.045),
                     mat=GALV)
    _antenna_bracket(mb, MS, ztp, ypiv + 0.035, plate_w=0.11, plate_h=0.13, bolts_x=(-0.04, 0.04), bolts_dz=(-0.045, 0.045),
                     mat=GALV)
    _tilt_mount(mb, MA, Pb, ztp, ypiv, La=0.17)
    # asa superior: tubo Ø 18 doblado con dos bases torneadas
    yh = -0.128
    mb.tube([MA @ _V(p) for p in fillet([(-0.085, yh, H - 0.004), (-0.085, yh, H + 0.042), (0.085, yh, H + 0.042), (0.085, yh, H - 0.004)],
                                         0.022, 4)], 0.009, seg=16, mat="aluminium")
    for sx in (-1, 1):
        revolve(mb, [(0.017, -0.002), (0.017, 0.004), (0.012, 0.010), (0.0, 0.011)], "aluminium", seg=20, M=MA @ _T(sx * 0.085, yh, H))
    # bahía de cables inferior: tapa con 2 tornillos cautivos, pasacables y colas
    slab(mb, MA @ _T(0, -0.160, 0.002) @ _Rx(180), 0.25, 0.085, 0.026, rc=0.010, re=0.004, re0=0.0, mat="aluminium", nc=3, ne=2)
    for sx in (-1, 1):
        revolve(mb, [(0.0065, -0.0004), (0.0065, 0.003), (0.004, 0.0055), (0.0, 0.006)], SS, seg=16,
                M=MA @ _T(sx * 0.10, -0.2025, -0.012) @ _Rx(90))
    cab = [(-0.05, 0.0075, "cable"), (0.03, 0.0035, "paint_yellow"), (0.05, 0.0035, "paint_yellow")]
    for (x, rc, mat) in cab:
        _grommet(mb, MA @ _T(x, -0.135, -0.024) @ _Rx(180), rc)
        if tails:
            _tail(mb, MA, [(x, -0.135, -0.03), (x, -0.135, -0.13), (x + float(r.uniform(-0.006, 0.006)), -0.072, -0.30)], rc, mat=mat,
                  bend=0.09)
    # tierra en el costado derecho de la carcasa y placa de datos en el costado izquierdo
    _ground_lug(mb, MA @ _T(W / 2 - 0.003, -0.128, 0.09) @ _Ry(90) @ _Rz(90))
    if tails:
        _tail(mb, MA, [(W / 2 + 0.0028, -0.128, 0.0575), (W / 2 + 0.0028, -0.128, -0.05), (W / 2 - 0.06, -0.07, -0.30)], 0.004,
              mat="cable", bend=0.08)
    xs = -(W - 0.006) / 2
    mb.box((xs - 0.0016, -0.140, 0.30), (xs + 0.0006, -0.112, 0.36), "sign_white", bevel=0.0005, seg=1, m=MA)
    return mb


# ======================================================================================================== RRU 4T4R
def rru(seed=0, tails=True):
    """Radio remota 4T4R (Huawei RRU3256: 480 × 270 × 140 mm, ≤ 19,5 kg). Cuerpo fundido de cantos redondos, 21 aletas
    verticales afiladas en el frente con extremos en chaflán, tapa superior con asa abatible de solera, en la base 4 puertos
    RF 4.3-10 y un AISG con tapa, bahía de mantenimiento con tapa atornillada, pasacables y colas de alimentación (negra) y
    fibra (amarilla), terminal de tierra en el costado, placa de datos; atrás placa adaptadora con ganchos sobre el soporte
    principal galvanizado (canal) con dos abrazaderas en V al tubo.

    Origen: EJE DEL TUBO Ø 76 = eje Z (x = 0, y = 0); z = 0 = base del cuerpo (los puertos bajan ~30 mm y las colas ~0,3 m).
    Aletas (frente) hacia -Y; espalda del cuerpo a 78 mm del eje del tubo.
    Extremos libres de las colas: alimentación ≈ (-0.06, -0.10, -0.30), fibra ≈ (-0.03, -0.10, -0.30), tierra ≈ (0.12, -0.10, -0.30)."""
    from kit.clinic_servicios import slab
    r = rng(seed)
    mb = MB()
    H, W, D = 0.480, 0.270, 0.140
    yb = -0.078
    MC = _T(0, yb, 0)
    Dc = 0.086                                         # cuerpo macizo (sin aletas)
    slab(mb, MC @ _T(0, 0.0, H / 2) @ _Rx(90), W, H, Dc, rc=0.016, re=0.006, re0=0.008, mat="aluminium", nc=4, ne=2)
    # aletas del frente
    n = 21
    for k in range(n):
        x = (k - (n - 1) / 2) * 0.0114
        _fin(mb, MC, x, -Dc + 0.001, -D, 0.075, H - 0.03, t0=0.0036, t1=0.002, taper=0.03)
    # tapa superior moldeada (más ancha que el cuerpo, ceja de 3 mm) y asa abatible
    slab(mb, MC @ _T(0, -0.044, H - 0.008), W + 0.006, Dc + 0.008, 0.022, rc=0.018, re=0.006, re0=0.002, mat="aluminium", nc=4, ne=2)
    yh = -0.044
    for sx in (-1, 1):
        revolve(mb, [(0.011, -0.001), (0.011, 0.012), (0.009, 0.016), (0.0, 0.0165)], "aluminium", seg=16,
                M=MC @ _T(sx * 0.075, yh, H + 0.012) @ _Ry(90 * sx))
    mb.sweep(rr_profile(0.024, 0.006, 0.0025, n=1), [MC @ _V(p) for p in fillet(
        [(-0.085, yh, H + 0.023), (-0.085, yh - 0.045, H + 0.036), (0.085, yh - 0.045, H + 0.036), (0.085, yh, H + 0.023)], 0.018, 4)],
        mat=SS, normal=(1e-4, 0.276, 0.961))
    # base: puertos RF y AISG (fila delantera), bahía de mantenimiento con tapa (atrás)
    for x in (-0.096, -0.048, 0.048, 0.096):
        _port_43_10(mb, MC @ _T(x, -0.060, 0.0) @ _Rx(180))
    _aisg_port(mb, MC @ _T(0.0, -0.060, 0.0) @ _Rx(180) @ _Rz(float(r.uniform(0, 360))))
    slab(mb, MC @ _T(0, -0.022, 0.002) @ _Rx(180), 0.236, 0.034, 0.022, rc=0.008, re=0.004, re0=0.0, mat="aluminium", nc=3, ne=2)
    for sx in (-1, 1):
        revolve(mb, [(0.0065, -0.0004), (0.0065, 0.003), (0.004, 0.0055), (0.0, 0.006)], SS, seg=16,
                M=MC @ _T(sx * 0.095, -0.039, -0.010) @ _Rx(90))
    cab = [(-0.06, 0.0075, "cable"), (-0.03, 0.0035, "paint_yellow")]
    for (x, rc, mat) in cab:
        _grommet(mb, MC @ _T(x, -0.022, -0.020) @ _Rx(180), rc)
        if tails:
            _tail(mb, MC, [(x, -0.022, -0.026), (x, -0.022, -0.12), (x + float(r.uniform(-0.006, 0.006)), -0.022, -0.30)], rc, mat=mat,
                  bend=0.06, nseg=3)
    # tierra en el costado derecho y placa de datos en el izquierdo
    _ground_lug(mb, MC @ _T(W / 2 + 0.0002, -0.040, 0.075) @ _Ry(90) @ _Rz(90))
    if tails:
        _tail(mb, MC, [(W / 2 + 0.006, -0.040, 0.0405), (W / 2 + 0.006, -0.040, -0.04), (W / 2 - 0.015, -0.022, -0.30)], 0.004,
              mat="cable", bend=0.07, nseg=4)
    mb.box((-W / 2 - 0.0017, -0.065, 0.22), (-W / 2 + 0.0006, -0.022, 0.30), "sign_white", bevel=0.0005, seg=1, m=MC)
    # placa adaptadora en la espalda con dos ganchos y soporte principal (canal galvanizado) con dos abrazaderas
    slab(mb, MC @ _T(0, -0.002, H / 2) @ _Rx(-90), 0.17, 0.36, 0.008, rc=0.01, re=0.002, re0=0.0, mat=GALV, nc=2, ne=1)
    # canal: base de y = 0.0145 a 0.0215 (el vértice redondeado de la mordaza delantera de cada abrazadera queda soldado contra
    # su espalda), alas hacia el tubo hasta y = 0.037
    prof = [(-0.085, 0.0145), (0.085, 0.0145), (0.085, 0.037), (0.079, 0.037), (0.079, 0.0215), (-0.079, 0.0215), (-0.079, 0.037),
            (-0.085, 0.037)]
    zc0, zc1 = 0.06, H - 0.06
    loft_rings(mb, [[MC @ Vector((x, y, z)) for (x, y) in prof] for z in (zc0, zc1)], GALV)
    for sx in (-1, 1):                                 # ganchos de solera doblada: la placa del equipo cuelga del canto del canal
        path = fillet([(0.001, zc1 + 0.002), (0.0245, zc1 + 0.002), (0.0245, zc1 - 0.03)], 0.006, 3)
        mb.sweep(rr_profile(0.005, 0.012, 0.0015, n=1), [MC @ Vector((sx * 0.053, y, z)) for (y, z) in path], mat=GALV,
                 normal=(1, 0, 0))
    for zc in (0.13, H - 0.13):
        _clamp(mb, _T(0, 0, zc), w=0.15)
        for sx in (-1, 1):                             # cordones de soldadura mordaza-canal
            mb.tube([MC @ Vector((sx * 0.0045, 0.0212, zc + dz)) for dz in (-0.023, 0.023)], 0.0022, seg=6, mat=GALV)
    return mb


# ======================================================================================================== microondas
def _polar(mb, M, prof, seg, mat, mod=None, mats=None):
    """Superficie de revolución alrededor de Z local con modulación libre: mod(i, a, r, z) -> (r, z) (arrugas, frunces).
    prof [(r, z)]; r = 0 -> polo. mats: material por banda (opcional)."""
    from kit.clinic_servicios import skin
    loops = []
    for i, (r0, z0) in enumerate(prof):
        if r0 < 1e-7:
            loops.append([(0.0, 0.0, z0)])
            continue
        L = []
        for k in range(seg):
            a = 2 * PI * k / seg
            rr, zz = mod(i, a, r0, z0) if mod else (r0, z0)
            L.append((rr * math.cos(a), rr * math.sin(a), zz))
        loops.append(L)
    return skin(mb, loops, mat, M, mats=mats)


def _odu(mb, M, W=0.259, H=0.321, D=0.108, seed=0):
    """ODU de microondas de montaje directo (Ericsson MINI-LINK 6352: 321 × 259 × 108 mm, 4 kg). Marco M: cara frontal (la que
    se acopla al cubo de la antena) en z = 0 local, el cuerpo crece hacia +Z local; X = ancho, Y = alto.
    Carcasa fundida de esquinas redondas con tapa trasera nervada, asa lateral, 4 broches al cubo, conectores con
    prensaestopas abajo y terminal de tierra."""
    from kit.clinic_servicios import slab
    slab(mb, M @ _T(0, 0, -0.002), W, H, D * 0.72, rc=0.028, re=0.006, re0=0.004, mat="enamel", nc=4, ne=2)
    slab(mb, M @ _T(0, 0, D * 0.72 - 0.004), W - 0.008, H - 0.008, D * 0.28 + 0.004, rc=0.024, re=0.012, re0=0.0, mat="enamel", nc=4,
         ne=2)
    for k in range(5):                                   # nervios de la tapa trasera
        y = (k - 2) * 0.05
        mb.box((-W / 2 + 0.035, y - 0.006, D - 0.003), (W / 2 - 0.035, y + 0.006, D + 0.004), "enamel", bevel=0.003, seg=1, m=M)
    # asa lateral (+X): tubo Ø 16 con dos bases
    xa = W / 2
    pts = fillet([(xa - 0.004, -0.09, D * 0.55), (xa + 0.035, -0.09, D * 0.55), (xa + 0.035, 0.09, D * 0.55), (xa - 0.004, 0.09, D * 0.55)],
                 0.02, 4)
    mb.tube([M @ _V(p) for p in pts], 0.008, seg=14, mat="aluminium")
    # broches (4) al anillo del cubo
    for a in (45, 135, 225, 315):
        Ma = M @ _Rz(a) @ _T(0.098, 0, 0)
        mb.box((-0.012, -0.014, -0.018), (0.008, 0.014, 0.012), SS, bevel=0.003, seg=1, m=Ma)
        mb.box((0.002, -0.006, -0.03), (0.016, 0.006, 0.016), SS, bevel=0.002, seg=1, m=Ma)
    # conectores abajo (-Y): alimentación/datos con prensaestopa y tapa de puerto óptico
    for (x, rr, mat) in ((-0.05, 0.0105, "plastic"), (0.035, 0.009, "rubber")):
        revolve(mb, [(rr * 1.3, -0.002), (rr * 1.3, 0.006), (rr, 0.009), (rr, 0.024), (rr * 0.85, 0.027), (rr * 0.55, 0.027)], mat, seg=16,
                M=M @ _T(x, -H / 2, D * 0.45) @ _Rx(90))
    _ground_lug(mb, M @ _T(-W / 2 - 0.0002, -0.08, D * 0.45) @ _Ry(-90) @ _Rz(180))


def _htab(mb, M, L, r, t, mat=GALV, n=6):
    """Oreja horizontal: solera de largo L (de x = 0 a L local, extremo redondo de radio r) y espesor t en +Z local."""
    mb.plate(_stadium(L, r, n=n), t, mat, m=M)


def mw_dish(d=0.9, seed=0, cable=True):
    """Antena de microondas punto a punto de alto desempeño con faldón (0,6 o 0,9 m; CommScope VHLP3: 0,9 m, 17 kg neto,
    radomo gris). Reflector parabólico (f/D 0,30) de aluminio rechazado con brida de 10 tornillos al faldón cilíndrico de
    borde enrollado; radomo de tela gris tensado sobre el frente con arrugas radiales en la orilla, faldón de tela fruncido y
    fleje con tensor; cubo fundido al centro con la ODU de montaje directo (MINI-LINK 6352, 321 × 259 × 108 mm) con asa,
    broches, conectores y tierra; bastidor trasero de PTR con 4 separadores al reflector, brazos superior e inferior con
    pivote de elevación en orejas de la placa de montaje, tornillo de ajuste fino de elevación (arriba), collarín al tubo con
    tornillo de ajuste fino de azimut (abajo) y dos abrazaderas en V al tubo; cable de la ODU con gaza de goteo.

    Origen: EJE DEL TUBO Ø 76 = eje Z (x = 0, y = 0); z = 0 = altura del eje del plato. El plato apunta a -Y; su eje pasa por
    x = 0 (la ODU queda entre el reflector y el tubo). Frente del radomo a ≈ 0,75 m (0,9) / 0,59 m (0,6) del eje del tubo.
    Extremo libre del cable de la ODU ≈ (0.06, -0.06, -0.75)."""
    from kit.clinic_equipo import rtube_lo
    from kit.clinic_servicios import slab
    r = rng(seed)
    mb = MB()
    Rr = d / 2                                   # reflector
    Rs = Rr + 0.015                              # faldón
    h = d / 4.8                                  # profundidad del paraboloide (f/D = 0,30)
    Ls = 0.30 if d >= 0.75 else 0.20             # largo del faldón
    seg = 48
    yv = -0.228                                  # vértice trasero del reflector
    MD = _T(0, yv, 0) @ _Rx(90)                  # z local = hacia el frente (-Y); x local = X; y local = +Z
    zc = h + 0.008 + Ls                          # borde delantero del faldón
    # reflector + brida + faldón + borde enrollado + disco frontal (oculto tras la tela), un solo sólido
    prof = [(0.0, -0.002)] + [(Rr * f, h * f * f) for f in (0.25, 0.5, 0.72, 0.9)]
    prof += [(Rr, h), (Rs + 0.012, h + 0.001), (Rs + 0.012, h + 0.009), (Rs, h + 0.0095), (Rs, zc - 0.012), (Rs + 0.0045, zc - 0.007),
             (Rs + 0.004, zc - 0.001), (Rs - 0.002, zc), (0.0, zc)]
    _polar(mb, MD, prof, seg, "aluminium")
    for k in range(10):                          # tornillos de la brida reflector-faldón
        a = 2 * PI * (k + 0.5) / 10
        Mb = MD @ _T((Rs + 0.0055) * math.cos(a), (Rs + 0.0055) * math.sin(a), h + 0.0008) @ _Rx(180)
        _hex(mb, Mb, 0.008, h=0.0055, z=-0.0004)
    # radomo de tela: frente abombado con arrugas radiales cerca de la orilla, vuelta sobre el labio, faldón fruncido
    bul = 0.010 + 0.006 * d
    nf = seg // 4
    ph = float(r.uniform(0, 2 * PI))
    fprof = [(0.0, zc + 0.006 + bul)] + [(Rs * f, zc + 0.006 + bul * (1 - f * f)) for f in (0.4, 0.72, 0.88, 0.96)]
    fprof += [(Rs - 0.003, zc + 0.0045), (Rs + 0.006, zc - 0.001), (Rs + 0.0068, zc - 0.012), (Rs + 0.0035, zc - 0.022),
              (Rs + 0.0030, zc - 0.058), (Rs - 0.002, zc - 0.058), (Rs - 0.002, zc - 0.002), (0.0, zc + 0.002)]

    def fab(i, a, rr, z):
        if 1 <= i <= 5:                              # ondulación suave del paño + arrugas radiales de tensión en la orilla
            w = (0.1, 0.3, 0.75, 0.9, 0.3)[i - 1]
            z += 0.0045 * w * math.sin(nf * a + ph + 0.5 * math.sin(3 * a + ph))
            z += 0.0025 * (1.0, 0.9, 0.6, 0.3, 0.1)[i - 1] * math.sin(2 * a + 1.3 * ph)
        if i in (7, 8):                              # frunces del faldón entre el labio y el fleje
            rr += (0.0024 if i == 7 else 0.0012) * (0.5 + 0.5 * math.sin(nf * a + ph))
        return rr, z
    _polar(mb, MD, fprof, seg, "radome", mod=fab)
    # fleje de tensión alrededor del faldón y tensor (tornillo en T) abajo
    zb0, zb1 = zc - 0.050, zc - 0.028
    revolve(mb, [(Rs + 0.0026, zb0), (Rs + 0.0054, zb0 + 0.001), (Rs + 0.0054, zb1 - 0.001), (Rs + 0.0026, zb1)], SS, seg=seg, M=MD)
    a_t = -PI / 2 + 0.25
    Mt = MD @ _T((Rs + 0.0050) * math.cos(a_t), (Rs + 0.0050) * math.sin(a_t), (zb0 + zb1) / 2) @ _Rz(math.degrees(a_t)) @ _Ry(90)
    mb.box((-0.013, -0.022, -0.001), (0.013, 0.022, 0.016), SS, bevel=0.003, seg=1, m=Mt)
    _rod(mb, Mt @ Vector((0, -0.04, 0.010)), Mt @ Vector((0, 0.04, 0.010)), 0.0035)
    _hex(mb, Mt @ _T(0, 0.022, 0.010) @ _Rx(-90), 0.007, h=0.006, z=-0.0003)
    # cubo fundido al centro del reflector y ODU
    revolve(mb, [(0.092, 0.012), (0.092, -0.010), (0.086, -0.017), (0.074, -0.018), (0.074, -0.030), (0.0, -0.030)], "aluminium", seg=32,
            M=MD)
    yo = yv + 0.029                                  # cara frontal de la ODU (2 mm dentro del cubo)
    Mo = _T(0, yo, 0) @ _Rx(-90) @ Matrix(((1, 0, 0, 0), (0, -1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    _odu(mb, Mo, seed=seed)
    # bastidor trasero de PTR 40 × 40 alrededor de la ODU, con 4 separadores al reflector
    yf = -0.200
    xs, zs = 0.172, 0.205
    for sz in (-1, 1):                               # travesaños 40 × 40; largueros 36 × 36 metidos 5 mm (caras a 2 mm)
        rtube_lo(mb, (-xs - 0.02, yf, sz * zs), (xs + 0.02, yf, sz * zs), 0.04, 0.04, GALV, up=(0, 1, 0), r=0.003, n=1)
    for sx in (-1, 1):
        rtube_lo(mb, (sx * xs, yf, -zs + 0.015), (sx * xs, yf, zs - 0.015), 0.036, 0.036, GALV, up=(0, 1, 0), r=0.003, n=1)
    rc_ = math.hypot(xs, zs)
    ybowl = yv - h * (rc_ / Rr) ** 2
    for sx in (-1, 1):
        for sz in (-1, 1):
            rtube_lo(mb, (sx * xs, ybowl - 0.012, sz * zs), (sx * xs, yf - 0.019, sz * zs), 0.034, 0.034, GALV, up=(0, 0, 1), r=0.003, n=1)
    # placa de montaje frente al tubo (soldada a las mordazas delanteras de dos abrazaderas)
    zp = 0.29
    yp0, yp1 = -0.0565, -0.0655                      # espalda / frente de la placa
    slab(mb, _T(0, yp0, 0) @ _Rx(90), 0.12, 2 * zp, yp0 - yp1, rc=0.012, re=0.003, mat=GALV, nc=2, ne=1)
    for zc_ in (-0.17, 0.17):
        _clamp(mb, _T(0, 0, zc_), w=0.15)
    # brazos (PTR 50 × 30) del bastidor a orejas dobles de la placa; pivote de elevación en cada uno (eje X, y = -0.084)
    ypv = -0.084
    for sz in (-1, 1):
        rtube_lo(mb, (0, yf + 0.008, sz * zs), (0, -0.106, sz * zs), 0.05, 0.03, GALV, up=(0, 0, 1), r=0.003, n=1)
        _bar(mb, (-0.110, sz * zs), (ypv, sz * zs), 0.017, 0.010, -0.005, M=Matrix(), round0=False)        # lengüeta del brazo
        for sx in (-1, 1):
            _bar(mb, (yp1 + 0.003, sz * zs), (ypv, sz * zs), 0.019, sx * 0.007, sx * 0.0055, M=Matrix(), round0=False)
        _pivot_bolt(mb, Matrix(), (ypv, sz * zs), 0.0125, d=0.012)
    # ajuste fino de elevación: oreja horizontal arriba de la placa, bloque soldado sobre el brazo superior, espárrago M16
    yr_ = -0.126
    zt = zp - 0.014
    _htab(mb, _T(0, yp1 + 0.004, zt) @ _Rz(-90), -yr_ + yp1 + 0.004, 0.021, 0.008)
    mb.box((-0.013, yr_ - 0.013, zs + 0.0145), (0.013, yr_ + 0.013, zs + 0.034), GALV, bevel=0.002)
    _rod(mb, (0, yr_, zs + 0.02), (0, yr_, zt + 0.008 + 0.0128 + 0.006), 0.008)
    _nut(mb, _T(0, yr_, zt + 0.008), 0.016)
    _nut(mb, _T(0, yr_, zt) @ _Rx(180), 0.016, washer=False)
    _nut(mb, _T(0, yr_, zs + 0.034), 0.016, washer=False)
    # ajuste fino de azimut: collarín partido al tubo bajo la placa, oreja del collarín y oreja de la placa, espárrago M12
    za = -zp - 0.045
    revolve(mb, [(0.0378, za - 0.02), (0.049, za - 0.02), (0.051, za - 0.017), (0.051, za + 0.017), (0.049, za + 0.02), (0.0378, za + 0.02)],
            GALV, seg=32, M=Matrix(), closed=True)
    for sx in (-1, 1):                               # orejas del corte del collarín con su tornillo
        mb.box((sx * 0.0045 - 0.0035, 0.044, za - 0.018), (sx * 0.0045 + 0.0035, 0.068, za + 0.018), GALV, bevel=0.002)
    _rod(mb, (-0.022, 0.058, za), (0.024, 0.058, za), 0.005)
    _hex(mb, _T(-0.008, 0.058, za) @ _Ry(-90), 0.010, h=0.006, z=-0.0003)
    _hex(mb, _T(0.008, 0.058, za) @ _Ry(90), 0.010, h=0.008, z=-0.0003)
    ya_ = -0.092
    _bar(mb, (-0.042, za), (ya_ - 0.008, za), 0.016, 0.010, 0.020, M=Matrix(), round0=False)           # oreja del collarín
    ol = [(yp1 + 0.003, -zp + 0.024), (yp1 + 0.003, -zp), (ya_ + 0.014, -zp)]                       # oreja en L de la placa
    ol += [(ya_ + 0.014 * math.cos(PI * k / 6), za - 0.014 * math.sin(PI * k / 6)) for k in range(7)]
    ol += [(ya_ - 0.014, -zp + 0.024)]
    perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # (u, v, w) -> (y, z, x)
    mb.plate(ol, 0.010, GALV, m=_T(0.050, 0, 0) @ perm)
    _rod(mb, (0.006, ya_, za), (0.072, ya_, za), 0.006)
    for x, sgn in ((0.020, -1), (0.030, 1), (0.050, -1), (0.060, 1)):
        _hex(mb, _T(x, ya_, za) @ _Ry(90 * sgn), 0.012, h=0.008, z=-0.0003)
    # cable de la ODU con gaza de goteo hasta el tubo
    if cable:
        x0, y0 = -0.05, yo + 0.108 * 0.45
        pts = [(x0, y0, -0.1605 - 0.026), (x0, y0, -0.27), (x0 + 0.03, y0 + 0.01, -0.40), (x0 + 0.08, y0 + 0.025, -0.36),
               (0.055, -0.062, -0.42), (0.06, -0.062, -0.75)]
        mb.tube(fillet(pts, 0.05, 4), 0.0045, seg=14, mat="cable")
    return mb


# ======================================================================================================== baliza, pararrayos
def obstruction_light(mount="pipe"):
    """Baliza de obstrucción roja de baja intensidad tipo L-810 LED (FAA AC 150/5345-43; Ø 120-145 mm × ~200 mm, 1,5 kg):
    lente de policarbonato rojo con anillos fresnel y domo, aro de sujeción con tornillos, base fundida con 4 aletas,
    prensaestopa lateral con su cable que baja, niple de conduit de 3/4".
    mount = "pipe": capuchón adaptador a la punta del tubo Ø 76 con 2 opresores (origen: centro de la boca del tubo,
    z = 0 = canto superior del tubo; el capuchón baja 70 mm y el cable ~0,2 m). mount = "plate": placa base de 150 × 150 con
    4 tornillos (origen: centro de la cara inferior de la placa)."""
    mb = MB()
    if mount == "pipe":
        revolve(mb, [(0.0438, -0.070), (0.0438, 0.004), (0.016, 0.012)], "aluminium", seg=28)
        revolve(mb, [(0.0045, -0.0006), (0.0045, 0.003)], SS, seg=6, M=_T(0.0436, 0, -0.04) @ _Ry(90))   # opresor
        z0 = 0.010
    else:
        mb.box((-0.075, -0.075, 0.0), (0.075, 0.075, 0.008), "galvanized", bevel=0.002, seg=1)
        for sx in (-1, 1):
            for sy in (-1, 1):
                revolve(mb, [(0.0092, 0.0076), (0.0092, 0.0156)], SS, seg=6, phase=PI / 6, M=_T(sx * 0.055, sy * 0.055, 0.0))
        revolve(mb, [(0.03, 0.0), (0.017, 0.018)], "galvanized", seg=24, M=_T(0, 0, 0.007))
        z0 = 0.024
    revolve(mb, [(0.0134, z0 - 0.002), (0.0134, z0 + 0.052)], "galvanized", seg=24)      # niple 3/4" (Ø 26,7)
    # base fundida: cuello, cono, cuerpo y ceja para el aro; 6 aletas radiales sobre el cono
    zb = z0 + 0.048
    revolve(mb, [(0.0165, zb - 0.002), (0.022, zb + 0.004), (0.054, zb + 0.022), (0.062, zb + 0.054), (0.0605, zb + 0.061)], "aluminium",
            seg=28)
    perm = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))          # (u, v, w) -> (x, z, y)
    for k in range(4):
        a = 2 * PI * (k + 0.5) / 4
        mb.plate([(0.020, zb + 0.008), (0.030, zb + 0.003), (0.058, zb + 0.018), (0.068, zb + 0.030), (0.068, zb + 0.046),
                  (0.054, zb + 0.048)], 0.004, "aluminium", m=_Rz(math.degrees(a)) @ _T(0, -0.002, 0) @ perm)
    # aro de sujeción y 2 tornillos
    za = zb + 0.058
    revolve(mb, [(0.0600, za), (0.0672, za + 0.002), (0.0672, za + 0.012)], "aluminium", seg=32)
    for k in range(2):
        a = PI * k + 0.3
        revolve(mb, [(0.0046, -0.0004), (0.0046, 0.0036)], SS, seg=6, phase=PI / 6,
                M=_T(0.0670 * math.cos(a), 0.0670 * math.sin(a), za + 0.006) @ _Rz(math.degrees(a)) @ _Ry(90))
    # lente roja: 3 anillos fresnel (diente de sierra) + domo
    zl = za + 0.010
    prof = [(0.0598, za + 0.002)]
    for k in range(2):
        prof += [(0.0612, zl + k * 0.024), (0.0586, zl + k * 0.024 + 0.022)]
    zt = zl + 2 * 0.024
    for ang in (0.0, 22.0, 44.0, 64.0, 80.0):               # domo semielíptico (bandas < 25°: sombreado liso)
        prof.append((0.0586 * math.cos(math.radians(ang)), zt + 0.046 * math.sin(math.radians(ang))))
    prof.append((0.0, zt + 0.046))
    revolve(mb, prof, "sign_red", seg=40)
    # prensaestopa lateral M20 (en -Y) y cable que baja
    Mg = _Rz(-90) @ _T(0.054, 0, zb + 0.030) @ _Ry(90)
    revolve(mb, [(0.012, -0.008), (0.012, 0.007), (0.0105, 0.016), (0.0050, 0.021)], "plastic", seg=16, M=Mg)
    p0 = Mg @ Vector((0, 0, 0.018))
    mb.tube(fillet([p0, p0 + Vector((0, -0.035, 0)), Vector((0.0, p0.y - 0.045, -0.20))], 0.035, 3), 0.0042, seg=14, mat="cable")
    return mb


def lightning_rod(h=2.0):
    """Pararrayos Franklin: punta de cobre Ø 16 mm (5/8") de 0,6 m afilada en cono, adaptador reductor sobre mástil de tubo
    galvanizado Ø 48 (1½"), placa base de 160 × 160 con 4 tuercas, y conductor de bajada de cobre desnudo Ø 10 con grapa al
    pie de la punta, abrazadera al mástil y zapata atornillada a la placa. Origen: centro de la cara inferior de la placa;
    eje Z; el bajante corre por +Y."""
    mb = MB()
    mb.box((-0.08, -0.08, 0.0), (0.08, 0.08, 0.010), "galvanized", bevel=0.002, seg=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            revolve(mb, [(0.0111, 0.0096), (0.0111, 0.0192)], SS, seg=6, phase=PI / 6, M=_T(sx * 0.06, sy * 0.06, 0.0))
    zm = h - 0.62
    revolve(mb, [(0.0241, 0.006), (0.0241, zm)], "galvanized", seg=24)                                   # mástil
    for k in range(4):                                                                               # cartelas
        port.gusset(mb, _Rz(45 + 90 * k) @ _T(0.022, 0, 0.0095), 0.045, 0.09, t=0.006, mat="galvanized", chamfer=0.012)
    revolve(mb, [(0.0262, zm - 0.03), (0.0262, zm + 0.03)], "galvanized", seg=24)                         # reductor
    revolve(mb, [(0.008, zm + 0.04), (0.008, h - 0.10), (0.0042, h - 0.02), (0.0, h)], "copper", seg=24)  # punta
    ys = 0.040
    zc = zm + 0.10
    revolve(mb, [(0.0135, zc - 0.012), (0.0135, zc + 0.012)], "copper", seg=16)                          # grapa
    mb.box((-0.006, 0.011, zc - 0.012), (0.006, ys + 0.009, zc + 0.012), "copper", bevel=0.002, seg=1)
    pts = [(0.0, ys, zc), (0.0, ys, 0.06), (0.0, ys + 0.03, 0.0165)]
    mb.tube(fillet(pts, 0.035, 3), 0.005, seg=14, mat="copper")
    z = zm * 0.5                                                                                     # abrazadera al mástil
    revolve(mb, [(0.0275, z - 0.010), (0.0275, z + 0.010)], "galvanized", seg=24)
    mb.box((-0.009, 0.026, z - 0.010), (0.009, ys + 0.0065, z + 0.010), "galvanized", bevel=0.002, seg=1)
    mb.box((-0.011, ys + 0.022, 0.0095), (0.011, ys + 0.055, 0.016), "copper", bevel=0.002, seg=1)         # zapata
    revolve(mb, [(0.0074, 0.0157), (0.0074, 0.0217)], SS, seg=6, phase=PI / 6, M=_T(0, ys + 0.045, 0.0))
    return mb


# ======================================================================================================== jumper
def _connector_43_10(mb, M, r_cable, band=None):
    """Conector macho 4.3-10 de jumper: cara de acople en z = 0 local, el cable sale por +Z local. Tuerca de acople hexagonal,
    cuerpo, bota de hule cónica y banda de color (código de puerto) termocontráctil."""
    _hex(mb, M, 0.0175, h=0.016, z=0.0)
    revolve(mb, [(0.0118, 0.015), (0.0118, 0.030), (0.0105, 0.032), (0.0105, 0.038)], SS, seg=24, M=M)
    rb = max(r_cable + 0.0025, 0.0095)
    revolve(mb, [(0.0122, 0.036), (0.0122, 0.046), (rb, 0.066), (r_cable + 0.0008, 0.074)], "rubber", seg=24, M=M)
    if band:
        revolve(mb, [(r_cable + 0.0019, 0.078), (r_cable + 0.0019, 0.094)], band, seg=16, M=M)


def _spline(pts, step=0.025):
    """Remuestrea una polilínea con Catmull-Rom centrípeta (curvatura continua: cuelga como cable, no en V) a paso ~step."""
    P = [Vector(p) for p in pts]
    if len(P) < 3:
        return [tuple(p) for p in P]
    out = [P[0]]
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        if i == 0:
            p0 = p1 - (p2 - p1)
        if i == len(P) - 2:
            p3 = p2 + (p2 - p1)

        def tj(ti, a, b):
            return ti + max((b - a).length, 1e-6) ** 0.5
        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        n = max(1, math.ceil((p2 - p1).length / step))
        for k in range(1, n + 1):
            t = t1 + (t2 - t1) * k / n
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            out.append(b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1)))
    return [tuple(p) for p in out]


def drip_loop_points(p0, p1, sag=0.20, drop=0.12, out=(0.0, -1.0, 0.0)):
    """Polilínea típica de jumper con gaza de goteo de p0 (puerto: el cable sale hacia abajo) a p1 (puerto o cola, el cable
    llega desde abajo): baja `drop` en vertical desde cada extremo y une las dos caídas con una U semielíptica que cuelga `sag`
    por debajo de la caída más baja, abierta un poco hacia `out` (lejos del tubo)."""
    a, b = Vector(p0), Vector(p1)
    A, B = a - Vector((0, 0, drop)), b - Vector((0, 0, drop))
    zl = min(A.z, B.z) - sag
    o = Vector(out).normalized() * 0.04
    pts = [a, A]
    for k in range(1, 6):
        th = PI * k / 6
        w = (1 - math.cos(th)) / 2
        q = A.lerp(B, w)
        q.z = q.z + (zl - q.z) * math.sin(th) ** 0.8
        pts.append(q + o * math.sin(th))
    pts += [B, b]
    return [tuple(p) for p in pts]


def jumper(points, r=0.008, ends=(True, True), band="sign_red", seg=14, bend=None, spline=True):
    """Cable puente (jumper) coaxial ½" superflexible (Ø 16 mm con cubierta) que sigue `points` (lista de puntos 3D en
    coordenadas de mundo/kit) con dobleces de radio real (filete, radio mínimo ≈ 5 × Ø) y conectores 4.3-10 machos en los
    extremos (tuerca, cuerpo, bota de hule, banda de color de puerto). spline=True: la trayectoria es una Catmull-Rom
    centrípeta por los puntos (curvatura continua, cuelga como cable); spline=False: polilínea con esquinas fileteadas de
    radio `bend` (tramos rectos peinados en escalerilla). Si se dan solo 2 puntos se genera la gaza de goteo
    con drip_loop_points(). El primer y el último punto son las caras de acople de los conectores: el cable sale de cada
    conector en la dirección del segmento contiguo. seg ≥ 14 (con el suavizado a 30° del kit, 12 lados se ven facetados)."""
    mb = MB()
    P = [Vector(p) for p in (drip_loop_points(points[0], points[1]) if len(points) == 2 else points)]
    bend = bend if bend is not None else max(0.05, 5 * r)
    ends = tuple(ends)
    clen = 0.074
    d0 = (P[1] - P[0]).normalized()
    d1 = (P[-2] - P[-1]).normalized()
    Q = list(P)
    if ends[0]:
        Q[0] = P[0] + d0 * (clen - 0.004)
    if ends[1]:
        Q[-1] = P[-1] + d1 * (clen - 0.004)
    path = _spline([tuple(q) for q in Q], step=max(0.02, 2.5 * r)) if spline else fillet([tuple(q) for q in Q], bend, 8)
    clean = [path[0]]
    for p in path[1:]:
        if (Vector(p) - Vector(clean[-1])).length > 1e-5:
            clean.append(p)
    mb.tube(clean, r, seg=max(seg, 12), mat="cable")
    for k, (pp, dd) in enumerate(((P[0], d0), (P[-1], d1))):
        if ends[k]:
            Mc = Matrix.Translation(pp) @ dd.to_track_quat("Z", "Y").to_matrix().to_4x4()
            _connector_43_10(mb, Mc, r, band=band)
    return mb


# ======================================================================================================== tubo de montaje
def _ubolt(mb, M, R, rod_d=0.012, leg=0.06, plate_t=0.010, mat=SS):
    """Abrazadera U: rodea un tubo de radio R cuyo eje es X local en el origen; el arco abraza el lado -Y, las piernas van
    hacia +Y paralelas a ±Z y atraviesan una placa cuya cara cercana está en y = R (espesor plate_t). Tuercas con arandela
    en la cara lejana de la placa (y = R + plate_t)."""
    rr = rod_d / 2
    Rc = R + rr + 0.0005
    yb = R + plate_t
    yl = yb + 0.0016 + 0.0096 + 0.008
    pts = [(0.0, yl, Rc)] + [(0.0, -Rc * math.sin(PI * k / 8), Rc * math.cos(PI * k / 8)) for k in range(9)] + [(0.0, yl, -Rc)]
    mb.tube([M @ _V(p) for p in pts], rr, seg=14, mat=mat)
    for sz in (-1, 1):
        _nut(mb, M @ _T(0, yb, sz * Rc) @ _Rx(-90), rod_d)
    return Rc


def pipe_mount(length=3.0, standoff=0.30, clamp_z=(0.35, None), rail_d=0.0603):
    """Tubo vertical de montaje Ø 76 mm (pared 4 mm) galvanizado con capuchones en las puntas y dos brazos separadores
    (standoff) a la plataforma. Cada brazo: PTR 40 × 40 galvanizado; en el tubo una placa de 130 × 100 × 10 con abrazadera U
    M12 que rodea el tubo por el lado -Y (lado del equipo); en el otro extremo otra placa con abrazadera U M12 que abraza el
    larguero horizontal de la plataforma (tubo Ø rail_d, eje paralelo a X).

    Origen: eje del tubo = eje Z (x = 0, y = 0); z = 0 = extremo inferior del tubo. Los brazos van hacia +Y (hacia el
    interior de la plataforma). Largueros de la plataforma que se abrazan: eje X en y = standoff, z = clamp_z[i]
    (clamp_z por omisión: 0.35 y length - 0.65)."""
    mb = MB()
    R = PIPE_R
    zc = [clamp_z[0], clamp_z[1] if clamp_z[1] is not None else length - 0.65]
    # tubo con pared visible bajo los capuchones y capuchones domados de hule
    revolve(mb, [(R - 0.004, 0.004), (R, 0.004), (R, length - 0.004), (R - 0.004, length - 0.004)], GALV, seg=32, closed=True)
    for (z, sg) in ((length - 0.025, 1), (0.025, -1)):           # capuchones de hule (abrazan 25 mm del tubo)
        prof = [(R + 0.0028, z), (R + 0.0028, z + sg * 0.026), (R - 0.004, z + sg * 0.033), (0.0, z + sg * 0.035)]
        revolve(mb, prof if sg > 0 else list(reversed(prof)), "rubber", seg=32)
    rr = rail_d / 2
    for z in zc:
        # placa en el tubo (lado +Y) con abrazadera U alrededor del tubo
        mb.box((-0.065, R - 0.0005, z - 0.05), (0.065, R + 0.010, z + 0.05), GALV, bevel=0.002, seg=1)
        _ubolt(mb, Matrix(((0, 0, -1, 0), (0, 1, 0, 0), (1, 0, 0, z), (0, 0, 0, 1))), R)
        # brazo
        from kit.clinic_equipo import rtube_lo
        rtube_lo(mb, (0, R + 0.008, z), (0, standoff - rr - 0.008, z), 0.04, 0.04, GALV, up=(0, 0, 1), r=0.003, n=1)
        for sx in (-1, 1):
            mb.tube([(sx * 0.0205, R + 0.0105, z - 0.018), (sx * 0.0205, R + 0.0105, z + 0.018)], 0.0022, seg=6, mat=GALV)
        # placa contra el larguero (lado -Y del larguero) con abrazadera U por el lado +Y
        mb.box((-0.05, standoff - rr - 0.010, z - 0.065), (0.05, standoff - rr + 0.0005, z + 0.065), GALV, bevel=0.002, seg=1)
        _ubolt(mb, _T(0, standoff, z) @ _Rz(180), rr)
    return mb


# ======================================================================================================== puntos de conexión
def _tilt_frame(yb, ypiv, zbp, tilt_deg):
    Pb = Vector((0.0, yb + ypiv, zbp))
    return _T(*Pb) @ _Rx(tilt_deg) @ _T(*(-Pb)) @ _T(0, yb, 0)


def panel_ports(tilt_deg=4.0):
    """Puntos de acople (en coordenadas locales de panel_antenna con esa inclinación) para el primer punto de un jumper() en
    cada uno de los 8 puertos 4.3-10 (fila trasera x = -0.105..0.105, luego fila delantera): la tuerca del conector cubre la
    rosca del puerto. El cable debe salir hacia abajo (segundo punto ~0,1 m más abajo)."""
    MA = _tilt_frame(-0.165, 0.05, 0.32, tilt_deg)
    return [tuple(MA @ Vector((x, y, -0.010))) for y in (-0.045, -0.100) for x in (-0.105, -0.035, 0.035, 0.105)]


def rru_ports():
    """Puntos de acople de los 4 puertos RF 4.3-10 de rru() (coordenadas locales), de -x a +x; el cable sale hacia abajo."""
    return [(x, -0.078 - 0.060, -0.010) for x in (-0.096, -0.048, 0.048, 0.096)]


def aau_tail_ends(seed=0, tilt_deg=2.0):
    """Extremos libres de las colas de aau() (coordenadas locales): alimentación, fibra 1, fibra 2, tierra."""
    r = rng(seed)
    MA = _tilt_frame(-0.130, 0.022, 0.15, tilt_deg)
    out = []
    for x in (-0.05, 0.03, 0.05):
        out.append(tuple(MA @ Vector((x + float(r.uniform(-0.006, 0.006)), -0.072, -0.30))))
    out.append(tuple(MA @ Vector((0.395 / 2 - 0.06, -0.07, -0.30))))
    return out

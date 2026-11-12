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


def _frame(p0, p1, up=(0, 0, 1)):
    return port.frame_on(_V(p0), _V(p1), up)


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
            for sx in (1, -1):
                _bar(mb, (ya + 0.006, 0.0), (ypiv, 0.0), rl, sx * (x1 - x0), sx * x0, mat=mat, round0=False, M=M)
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
    zc = Pt.z + math.sqrt(max(La * La - (Pt.y - yc) ** 2, 0.01))
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


def _crown_slab(mb, M, w, d, h, rc, re, re0, crown, mat, nc=5, ne=3, steps=(0.82, 0.55, 0.25)):
    """Como clinic_servicios.slab (rectángulo redondeado w × d en XY local, de z = 0 a h, cantos re arriba / re0 abajo) pero
    con la cara superior abombada `crown` (radomo moldeado): anillos concéntricos hacia el centro."""
    from kit.clinic_servicios import _edge_levels, rr_pts, skin
    loops = []
    for (dl, z) in _edge_levels(h, re, re0, ne):
        loops.append([(x, y, z) for (x, y) in rr_pts(w - 2 * dl, d - 2 * dl, max(rc - dl, 3e-4), nc)])
    w2, d2, r2 = w - 2 * re, d - 2 * re, max(rc - re, 3e-4)
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
            M=M @ _T(0, 0, 0.0058) @ _Rx(90))                                                                  # barril
    _hex(mb, M @ _T(0, 0, 0.0022), 0.006, h=0.005)
    _rod(mb, M @ Vector((0, 0, -0.003)), M @ Vector((0, 0, 0.0095)), 0.003)


def aau(seed=0, tilt_deg=2.0, tails=True):
    """AAU 5G massive-MIMO 64T64R (Huawei AAU5613: 795 × 395 × 220 mm, 40 kg). Radomo frontal plano de cantos redondos con
    junta perimetral contra la carcasa fundida, disipador de 24 aletas verticales afiladas en la espalda con espina central
    de montaje, asa tubular arriba, bahía de cables inferior con tapa atornillada y pasacables (cola de alimentación negra y dos
    de fibra amarillas), terminal de tierra, placa de datos; adaptador con orejas, pivote inferior, brazo de inclinación
    (`tilt_deg` hacia abajo) y dos abrazaderas en V al tubo.

    Origen: EJE DEL TUBO Ø 76 = eje Z (x = 0, y = 0); z = 0 = base del cuerpo con inclinación 0 (la tapa de cables baja 25 mm y
    las colas de cable ~0,3 m). Frente radiante hacia -Y; puntas de las aletas a 130 mm del eje del tubo.
    Extremos libres de las colas (para continuarlas con jumper()): alimentación ≈ (-0.05, -0.07, -0.30), fibras ≈ (0.03 / 0.05,
    -0.07, -0.30)."""
    from kit.clinic_servicios import slab
    r = rng(seed)
    mb = MB()
    H, W, D = 0.795, 0.395, 0.220
    yb = -0.130                                  # puntas de aletas (inclinación 0)
    zbp, ztp = 0.15, H - 0.15
    ypiv = 0.022                                 # pivote 22 mm detrás de las aletas (cuerpo: espina en y = -0.035)
    Pb = Vector((0.0, yb + ypiv, zbp))
    MA = _T(*Pb) @ _Rx(tilt_deg) @ _T(*(-Pb)) @ _T(0, yb, 0)
    # radomo frontal y carcasa fundida (junta de 2 mm entre ambos)
    _crown_slab(mb, MA @ _T(0, -0.150, H / 2) @ _Rx(90), W, H, 0.065, rc=0.030, re=0.012, re0=0.003, crown=0.005, mat="radome")
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

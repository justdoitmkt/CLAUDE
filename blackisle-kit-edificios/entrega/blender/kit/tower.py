"""kit/tower.py — COM_1_antena: torre autosoportada de telecomunicaciones de 3 patas tubulares (sitio celular 2026, costa de México).

Pieza protagonista del sitio. Construcción real (TIA-222-G, galvanizado por inmersión en caliente):
- 3 dados de concreto Ø1,0 m (0,45 m sobre el suelo) con mortero de nivelación, placa base redonda con 8 cartelas y 8 anclas
  con arandela de placa y doble tuerca; cable de tierra de cobre en cada pata.
- Patas de tubo redondo que adelgazan por tramo (Ø219 → Ø114) en tramos de 6 m unidos por bridas con 8 tornillos, cartelas y
  cordón de soldadura; quiebre a vertical en el tramo recto superior (1,6 m de cara desde ~30 m).
- Arriostramiento en X (tramos cónicos) y en zigzag (tramo recto) de tubo, con placas de nudo (cartelas) soldadas a la pata,
  orejas ranuradas en cada extremo del tubo y 2 tornillos por oreja; placa de cruce en cada X; horizontales en cada nudo.
- Escalera de ascenso interior con riel rígido anticaídas, escalones de pie (step bolts 5/8") alternados en la pata -Y,
  escalerilla de cables con 16 cables negros + 2 de fibra amarilla sujetos con abrazaderas de bloque, vigas soporte de canal.
- Plataforma de sectores triangular (rejilla electroforjada de barras reales, rodapié, barandal con pasamanos y rodillera,
  3 tubos de montaje por cara con placas de cruce y abrazaderas en U), plataforma de microondas a ~32 m con 2 tubos para
  platos, mástil con pararrayos y ménsula de baliza de obstrucción en la cima, barra de tierra de cobre al pie.
Convención: origen en el centroide de la torre a nivel de suelo (z = 0), Z arriba, metros; una pata apunta a -Y.
Materiales: galvanized, steel, aluminium, metal_rust, concrete, rubber, cable, plastic, paint_yellow, sign_red, sign_white,
copper. Todo devuelve un MB (kit.common) listo para `finish()`.
"""
import math

import bpy  # noqa: F401  (bmesh/mathutils requieren bpy importado primero)
import bmesh  # noqa: F401
from mathutils import Matrix, Vector

from kit.common import MB, rng
from kit.clinic import fillet
from kit.clinic_servicios import lathe, skin

PI = math.pi
SQ3 = math.sqrt(3.0)
GALV = "galvanized"
LEG_ANG = (-90.0, 30.0, 150.0)          # pata 0 apunta a -Y
FACE_ANG = (330.0, 90.0, 210.0)         # normal exterior de la cara k (entre pata k y pata k+1)


# ================================================================================================== utilidades geométricas
def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def V3(x, y=None, z=None):
    if y is None:
        return Vector((float(x[0]), float(x[1]), float(x[2])))
    return Vector((float(x), float(y), float(z)))


def frame(zax, xhint=None, org=(0.0, 0.0, 0.0)):
    """Matriz 4x4 con Z local a lo largo de `zax`, X lo más cerca de `xhint`, origen `org`."""
    Z = V3(zax).normalized()
    X = V3(xhint) if xhint is not None else (Vector((1, 0, 0)) if abs(Z.x) < 0.9 else Vector((0, 1, 0)))
    X = X - Z * X.dot(Z)
    if X.length < 1e-6:
        X = Vector((1, 0, 0)) if abs(Z.x) < 0.9 else Vector((0, 1, 0))
        X = X - Z * X.dot(Z)
    X.normalize()
    Y = Z.cross(X)
    o = V3(org)
    return Matrix(((X.x, Y.x, Z.x, o.x), (X.y, Y.y, Z.y, o.y), (X.z, Y.z, Z.z, o.z), (0, 0, 0, 1)))


def frame_xz(xax, zhint, org):
    """Matriz con X local a lo largo de `xax` y Z lo más cerca de `zhint`."""
    X = V3(xax).normalized()
    Z = V3(zhint)
    Z = (Z - X * X.dot(Z)).normalized()
    Y = Z.cross(X)
    o = V3(org)
    return Matrix(((X.x, Y.x, Z.x, o.x), (X.y, Y.y, Z.y, o.y), (X.z, Y.z, Z.z, o.z), (0, 0, 0, 1)))


def ang2(deg):
    a = math.radians(deg)
    return Vector((math.cos(a), math.sin(a), 0.0))


def clip_poly(poly, n, c):
    """Recorta un polígono convexo 2D [(x, y)] con el semiplano dot(p, n) <= c (Sutherland-Hodgman)."""
    out = []
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]
        da = a[0] * n[0] + a[1] * n[1] - c
        db = b[0] * n[0] + b[1] * n[1] - c
        if da <= 0:
            out.append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def offset_poly(poly, d):
    """Desplaza un polígono convexo antihorario `d` hacia afuera (d < 0: hacia adentro), esquinas a inglete."""
    k = len(poly)
    out = []
    for i in range(k):
        a, b, c = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % k])
        e0, e1 = (b - a).normalized(), (c - b).normalized()
        n0, n1 = Vector((e0.y, -e0.x)), Vector((e1.y, -e1.x))
        m = (n0 + n1).normalized()
        s = d / max(m.dot(n0), 0.2)
        out.append((b.x + m.x * s, b.y + m.y * s))
    return out


def poly_ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return poly if a > 0 else list(reversed(poly))


def line_interval(poly, o, d):
    """Intervalo [t0, t1] de la recta p = o + t·d dentro del polígono convexo antihorario `poly` (None si no corta)."""
    t0, t1 = -1e9, 1e9
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]
        nx, ny = (b[1] - a[1]), -(b[0] - a[0])              # normal exterior del lado (polígono antihorario)
        den = nx * d[0] + ny * d[1]
        num = nx * (a[0] - o[0]) + ny * (a[1] - o[1])     # dentro: n·(p - a) <= 0  ->  den·t <= num
        if abs(den) < 1e-12:
            if num < 0:
                return None
            continue
        t = num / den
        if den > 0:
            t1 = min(t1, t)
        else:
            t0 = max(t0, t)
    return (t0, t1) if t1 > t0 else None


def ring_extrude(mb, outer, inner, z0, z1, mat):
    """Anillo prismático entre dos contornos 2D con el mismo número de vértices (marcos, rodapiés, bandas de rejilla)."""
    lo = [mb.bm.verts.new((x, y, z0)) for x, y in outer]
    hi = [mb.bm.verts.new((x, y, z1)) for x, y in outer]
    li = [mb.bm.verts.new((x, y, z0)) for x, y in inner]
    hii = [mb.bm.verts.new((x, y, z1)) for x, y in inner]
    k = len(outer)
    for i in range(k):
        j = (i + 1) % k
        mb.face([lo[i], lo[j], hi[j], hi[i]], mat)
        mb.face([li[j], li[i], hii[i], hii[j]], mat)
        mb.face([hi[i], hi[j], hii[j], hii[i]], mat)
        mb.face([lo[j], lo[i], li[i], li[j]], mat)


def prism(mb, prof, M, x0, x1, mat, planes=None, caps=True):
    """Barra prismática: perfil 2D (y, z) en el marco M (eje X local), de x0 a x1. `planes` = (plano0, plano1) opcional, cada
    plano (punto, normal) en mundo: los extremos se cortan oblicuos sobre esos planos (cortes a inglete contra placas)."""
    ax = Vector((M[0][0], M[1][0], M[2][0]))
    rings = []
    for k, xe in enumerate((x0, x1)):
        ring = []
        for (py, pz) in prof:
            p = M @ Vector((xe, py, pz))
            if planes is not None and planes[k] is not None:
                q, n = planes[k]
                den = ax.dot(n)
                if abs(den) > 1e-6:
                    p = p + ax * ((q - p).dot(n) / den)
            ring.append(p)
        rings.append(ring)
    return skin(mb, rings, mat, cap0=caps, cap1=caps)


def tube_seg(mb, p0, p1, r, mat=GALV, seg=16, caps=True):
    """Tubo recto (cilindro) de p0 a p1."""
    mb.cyl(V3(p0), V3(p1), r, seg=seg, mat=mat, caps=caps)


def rr_pts2(w, h, r, n=3):
    """Rectángulo redondeado centrado (antihorario)."""
    pts = []
    r = min(r, w / 2 - 1e-4, h / 2 - 1e-4)
    for (cx, cy, a0) in ((w / 2 - r, h / 2 - r, 0.0), (-w / 2 + r, h / 2 - r, PI / 2), (-w / 2 + r, -h / 2 + r, PI),
                         (w / 2 - r, -h / 2 + r, 1.5 * PI)):
        for k in range(n + 1):
            a = a0 + PI / 2 * k / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def plate_m(mb, outline, t, mat, M, center=True):
    """Placa: contorno 2D (x, y) en el plano XY de M, espesor t a lo largo de Z local (centrada si center)."""
    mb.plate(outline, t, mat, m=M @ _T(0, 0, -t / 2 if center else 0.0))


def weld_ring(mb, M, r, w=0.006, seg=32, mat=GALV):
    """Cordón de soldadura perimetral (sección redondeada) alrededor de un tubo de radio r, apoyado en z = 0 local hacia +Z."""
    prof = [(r - 0.0008, w * 1.05), (r + w * 0.45, w * 0.75), (r + w * 0.9, -0.0004)]
    lathe(mb, prof, seg=seg, mat=mat, M=M, closed=False, caps=False)


# ================================================================================================== tornillería (prefabs)
_PF = {}


def _lat(mb, prof, seg, mat=GALV, M=None, cap0=True, cap1=True, phase=0.0):
    """Torneado con tapas opcionales por extremo (las tapas ocultas dentro de otra pieza no se modelan)."""
    loops = [[(r * math.cos(phase + 2 * PI * k / seg), r * math.sin(phase + 2 * PI * k / seg), z) for k in range(seg)]
             for (r, z) in prof]
    return skin(mb, loops, mat, M, cap0=cap0, cap1=cap1)


def _hex(mb, z0, h, s, M=None, mat=GALV, top=True, bot=False):
    """Hexágono (cabeza o tuerca) de entrecaras s, alto h desde z0, con chaflán superior (y opcionalmente inferior)."""
    R = s / 2 / math.cos(PI / 6)
    prof = [(R * 0.88, z0), (R, z0 + h * 0.16)] if bot else [(R, z0)]
    prof += [(R, z0 + h * 0.84), (R * 0.88, z0 + h)] if top else [(R, z0 + h)]
    _lat(mb, prof, 6, mat, M, phase=PI / 6)


def _stub(mb, z0, z1, rs, seg=12, mat=GALV, M=None):
    """Punta roscada que sobresale de una tuerca: de z0 (oculto) a z1 con chaflán de 2,5 mm."""
    sg = 1.0 if z1 > z0 else -1.0
    _lat(mb, [(rs, z0), (rs, z1 - sg * 0.0022), (rs * 0.74, z1)], seg, mat, M, cap0=False, cap1=True)


def bolt_pf(d, grip, mat=GALV, stub=0.55, head_washer=False, wseg=12):
    """Tornillo hexagonal galvanizado ensamblado. Eje +Z local; z = 0 en la cara del lado de la tuerca, z = grip en la cara del
    lado de la cabeza. Arandela + tuerca + punta roscada con chaflán hacia -Z; cabeza hexagonal en z >= grip."""
    key = ("b", round(d, 4), round(grip, 4), mat, stub, head_washer, wseg)
    if key in _PF:
        return _PF[key]
    b = MB()
    s = 1.5 * d
    tw = max(0.1 * d, 0.0025)
    rw = 1.0 * d
    _lat(b, [(rw, -tw), (rw, 0.0003)], wseg, mat)
    hn = 0.8 * d
    _hex(b, -tw - hn, hn + 0.0003, s, mat=mat)
    if stub > 0:
        _stub(b, -tw - hn + 0.001, -tw - hn - stub * d, d * 0.47, mat=mat, seg=12)
    z0 = grip - 0.0003
    if head_washer:
        _lat(b, [(rw, z0), (rw, z0 + tw)], wseg, mat)
        z0 += tw
    _hex(b, z0, 0.65 * d, s, mat=mat)
    _PF[key] = b
    return b


def nut_pf(d, mat=GALV, washer=True, stub=0.5, wseg=12):
    """Tuerca (con arandela) apoyada en z = 0 hacia +Z, con punta roscada que sobresale (pernos en U, ganchos, anclas).
    Con stub = 0 sirve también como cabeza de tornillo con arandela."""
    key = ("n", round(d, 4), mat, washer, stub, wseg)
    if key in _PF:
        return _PF[key]
    b = MB()
    z = -0.0003
    if washer:
        tw = max(0.1 * d, 0.0025)
        _lat(b, [(d, z), (d, z + tw)], wseg, mat)
        z += tw
    hn = 0.8 * d
    _hex(b, z, hn + 0.0003, 1.5 * d, mat=mat)
    if stub > 0:
        _stub(b, z + hn - 0.001, z + hn + stub * d, d * 0.47, mat=mat, seg=12)
    _PF[key] = b
    return b


def put(mb, pf, M):
    mb.join(pf, M)


def bolt_at(mb, p_nut_face, axis_to_head, d, grip, xhint=None, **kw):
    """Coloca un tornillo: `p_nut_face` = punto en la cara del lado de la tuerca, `axis_to_head` = dirección hacia la cabeza."""
    mb.join(bolt_pf(d, grip, **kw), frame(axis_to_head, xhint, p_nut_face))


def ubolt(mb, M, rp, d=0.012, reach=0.03, mat=GALV, seg=12, bend_seg=9):
    """Perno en U alrededor de un tubo de radio rp. Local: el tubo va a lo largo de Y por el origen; la U lo abraza por el lado
    -X y sus dos patas salen hacia +X, atraviesan una placa cuya cara trasera está en x = reach y llevan tuerca y arandela."""
    rb = rp + d / 2 + 0.0008
    L = reach + 0.0035 + 0.8 * d + 0.012
    pts = [(L, 0.0, rb), (0.0, 0.0, rb)]
    for k in range(1, bend_seg):
        a = PI / 2 + PI * k / bend_seg
        pts.append((rb * math.cos(a), 0.0, rb * math.sin(a)))
    pts += [(0.0, 0.0, -rb), (L, 0.0, -rb)]
    mb.tube([M @ Vector(p) for p in pts], d / 2, seg=seg, mat=mat)
    nf = nut_pf(d, mat=mat, stub=0.0, washer=False, wseg=12)
    for zz in (rb, -rb):
        mb.join(nf, M @ frame((1, 0, 0), (0, 0, 1), (reach, 0.0, zz)))


# ================================================================================================== geometría de la torre
class Geo:
    """Geometría de líneas de trabajo: ancho de cara w(z) en los ejes de las patas, nudos, tramos y diámetros."""

    def __init__(self, h=42.0, base_w=5.0, top_w=1.6):
        k = h / 42.0
        self.h, self.bw, self.tw, self.k = h, base_w, top_w, k
        self.z_pier, self.z_grout, self.z_bp = 0.45, 0.50, 0.54           # cara superior: dado, mortero, placa base
        self.zk = 30.35 * k                                                # quiebre: arriba de aquí la torre es recta
        self.joints = [6.0 * k * i for i in range(1, 7)]                   # bridas
        self.zsec = [self.z_bp] + self.joints + [h]
        self.od_leg = [0.2191, 0.1937, 0.1683, 0.1683, 0.1413, 0.1143, 0.1143]
        self.nodes = [0.9, 3.0] + [z * k for z in (6.35, 9.2, 12.35, 15.2, 18.35, 21.2, 24.35, 27.2, 30.35, 31.9, 34.1, 36.35,
                                                    38.0, 39.1, 41.75)]
        self.z_mw = 32.5 * k                                               # piso de la plataforma de microondas
        self.z_top = 39.9 * k                                              # piso de la plataforma de sectores
        # escaleras interiores (verticales, junto a la cara +Y)
        self.y_beam = 0.33        # cara frontal del alma de las vigas soporte
        self.y_lad = 0.22         # plano de peldaños de la escalera de ascenso y de la escalerilla de cables
        self.x_lad = -0.34        # centro de la escalera de ascenso (ancho 0,45 entre ejes de largueros)
        self.x_cab = 0.30         # centro de la escalerilla de cables (0,50 exterior)
        self.z_exit = 2.6         # salida horizontal de cables (fila superior) hacia el puente de hielo
        self.y_exit = None
        self.z_cl0 = 2.95         # arranque de la escalerilla de cables

    def w(self, z):
        t = min(max(z, 0.0), self.zk) / self.zk
        return self.bw + (self.tw - self.bw) * t

    def R(self, z):
        return self.w(z) / SQ3

    def rin(self, z):
        return self.w(z) / (2 * SQ3)

    def P(self, i, z):
        """Punto del eje de la pata i a la altura z."""
        return ang2(LEG_ANG[i]) * self.R(z) + Vector((0, 0, z))

    def leg_dir(self, i, z):
        if z >= self.zk - 1e-6:
            return Vector((0, 0, 1))
        return (self.P(i, self.zk) - self.P(i, 0.0)).normalized()

    def sec_of(self, z):
        for s in range(len(self.zsec) - 1):
            if z < self.zsec[s + 1] + 1e-6:
                return s
        return len(self.zsec) - 2

    def r_leg(self, z):
        return self.od_leg[self.sec_of(z)] / 2

    def face_n(self, f, z=None):
        """Normal exterior (3D, inclinada por el ahusamiento) del plano de la cara f (entre pata f y f+1)."""
        a, b = self.P(f, 0.0 if z is None or z < self.zk else self.zk), self.P((f + 1) % 3, 0.0 if z is None or z < self.zk else self.zk)
        if z is not None and z >= self.zk:
            return ang2(FACE_ANG[f])
        c = self.P(f, self.zk)
        n = (b - a).cross(c - a).normalized()
        if n.dot(ang2(FACE_ANG[f])) < 0:
            n = -n
        return n


# ================================================================================================== cimentación y patas
def _rib(mb, base, u, r_in, r_out, h_in, h_out, t, mat=GALV, shift=None):
    """Cartela vertical radial: base = punto en la cara de apoyo, u = dirección horizontal hacia afuera."""
    u = V3(u).normalized()
    up = Vector((0, 0, 1))
    side = up.cross(u)
    sh = shift if shift is not None else 0.0
    M = Matrix(((u.x, up.x, side.x, base.x), (u.y, up.y, side.y, base.y), (u.z, up.z, side.z, base.z), (0, 0, 0, 1)))
    ch = 0.015                                                  # despunte de esquina (paso del cordón de soldadura)
    o2 = [(r_in, ch), (r_in + ch, 0.0), (r_out, 0.0), (r_out, h_out), (r_in + sh, h_in)]
    mb.plate(o2, t, mat, m=M @ _T(0, 0, -t / 2))


def _anchor_pf():
    key = ("anchor",)
    if key in _PF:
        return _PF[key]
    b = MB()
    b.box((-0.04, -0.04, -0.0003), (0.04, 0.04, 0.012), GALV, bevel=0.002, seg=2)       # arandela de placa
    d = 0.036
    _hex(b, 0.0117, 0.032, 1.6 * d, bot=True)                                             # tuerca pesada
    _hex(b, 0.0434, 0.026, 1.6 * d, bot=True)                                             # contratuerca
    _stub(b, 0.068, 0.122, d * 0.47, seg=16)
    _PF[key] = b
    return b


def build_base(mb, G, seed=0):
    r = rng(seed + 11)
    for i in range(3):
        c = G.P(i, G.z_bp)
        cx, cy = c.x, c.y
        Mc = _T(cx, cy, 0.0)
        # dado de concreto Ø1,0 con chaflán, desplantado bajo el suelo
        lathe(mb, [(0.5, -0.6), (0.5, 0.428), (0.497, 0.4405), (0.4885, 0.4475), (0.476, 0.45)], seg=64, mat="concrete", M=Mc)
        # mortero de nivelación (grout) con talud
        lathe(mb, [(0.372, 0.4497), (0.352, 0.476), (0.338, 0.4985), (0.3305, 0.5003)], seg=48, mat="concrete", M=Mc)
        # placa base redonda Ø0,58 × 40 mm
        lathe(mb, [(0.288, 0.4995), (0.29, 0.502), (0.29, 0.538), (0.288, G.z_bp)], seg=64, mat=GALV, M=Mc)
        rl = G.od_leg[0] / 2
        dirl = G.leg_dir(i, 1.0)
        for k in range(8):
            u = ang2(45.0 * k + LEG_ANG[i])
            sh = (G.P(i, G.z_bp + 0.24) - c).dot(u)
            _rib(mb, Vector((cx, cy, G.z_bp - 0.0005)), u, rl - 0.006, 0.272, 0.24, 0.035, 0.016, shift=sh)
            ua = ang2(45.0 * k + 22.5 + LEG_ANG[i])
            pa = Vector((cx, cy, G.z_bp)) + ua * 0.232
            mb.join(_anchor_pf(), _T(*pa) @ Matrix.Rotation(math.radians(45.0 * k + 22.5 + LEG_ANG[i] + float(r.uniform(-4, 4))), 4, "Z"))
        weld_ring(mb, frame(dirl, None, G.P(i, G.z_bp) - dirl * 0.0) @ _T(0, 0, 0.0), rl, w=0.008, seg=32)
        # tierra: oreja soldada a la pata, zapata de cobre de 2 barrenos y cable desnudo que baja por el dado al terreno
        ug = ang2(LEG_ANG[i] + 12.0)
        side = Vector((0, 0, 1)).cross(ug)
        zt = 0.86
        pc = G.P(i, zt)
        pc = Vector((pc.x, pc.y, zt))
        rlz = G.od_leg[0] / 2
        Mt = Matrix(((ug.x, 0, side.x, 0), (ug.y, 0, side.y, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        mb.plate([(rlz - 0.006, -0.05), (rlz + 0.07, -0.05), (rlz + 0.085, -0.035), (rlz + 0.085, 0.05), (rlz - 0.006, 0.05)],
                 0.010, GALV, m=_T(*pc) @ Mt @ _T(0, 0, -0.005))
        Ml = _T(*pc) @ Mt @ _T(0, 0, 0.0052)
        mb.plate([(rlz + 0.012, -0.013), (rlz + 0.07, -0.013), (rlz + 0.07, 0.013), (rlz + 0.012, 0.013)], 0.004, "copper", m=Ml)
        for xx in (rlz + 0.024, rlz + 0.052):
            q = _T(*pc) @ Mt @ Vector((xx, 0.0, -0.0052))
            bolt_at(mb, q, side, 0.010, 0.0144, ug, stub=0.4)
        pb = _T(*pc) @ Mt @ Vector((rlz + 0.07, 0.0, 0.0052 + 0.0095))
        lathe(mb, [(0.0092, 0.0), (0.0092, 0.03), (0.0065, 0.036)], seg=16, mat="copper", M=frame(ug, (0, 0, 1), pb))
        c0 = Vector((cx, cy, 0.0))
        path = [pb + ug * 0.032, pb + ug * 0.09 + Vector((0, 0, -0.01)), c0 + ug * 0.40 + side * pb.dot(side) * 0 + Vector((0, 0, 0.70)),
                c0 + ug * 0.523 + Vector((0, 0, 0.42)), c0 + ug * 0.511 + Vector((0, 0, 0.12)), c0 + ug * 0.53 + Vector((0, 0, -0.15))]
        so = side * (pb - c0).dot(side)
        path = [path[0], path[1]] + [p + so for p in path[2:]]
        mb.tube(fillet(path, 0.07, 6), 0.0055, seg=12, mat="copper")


def _Rx180():
    return Matrix.Rotation(PI, 4, "X")


def _flange(mb, M, rf, tf, rt, n_rib=8, up=True, rib_h=0.10, phase=0.0):
    """Brida: disco de radio rf y espesor tf con su cara de contacto en z = 0 local; el tubo (radio rt) sale hacia +Z (up) o -Z.
    Lleva cartelas entre tornillos y cordón de soldadura en la unión con el tubo."""
    s = 1.0 if up else -1.0
    ch = 0.0025
    prof = [(rf - ch, 0.0), (rf, s * ch), (rf, s * (tf - ch)), (rf - ch, s * tf)]
    if not up:
        prof = list(reversed(prof))
    lathe(mb, prof, seg=48, mat=GALV, M=M)
    for k in range(n_rib):
        a = phase + 2 * PI * k / n_rib
        u = Vector((math.cos(a), math.sin(a), 0.0))
        side = Vector((-u.y, u.x, 0.0))
        Mr = M @ Matrix(((u.x, 0, side.x, 0), (u.y, 0, side.y, 0), (0, s, 0, 0), (0, 0, 0, 1)))
        pts = [(rt - 0.004, tf - 0.0005), (rf - 0.008, tf - 0.0005), (rf - 0.008, tf + 0.02), (rt + 0.012, tf + rib_h),
               (rt - 0.004, tf + rib_h)]
        mb.plate(pts, 0.012, GALV, m=Mr @ _T(0, 0, -0.006))
    Mw = M @ (_T(0, 0, s * tf) if up else _T(0, 0, -tf)) @ (Matrix() if up else _Rx180())
    weld_ring(mb, Mw, rt, w=0.007, seg=32)


def build_legs(mb, G):
    tf = 0.025
    gap = 0.0015
    bolt_d = 0.024
    for i in range(3):
        for s in range(len(G.zsec) - 1):
            z0, z1 = G.zsec[s], G.zsec[s + 1]
            rt = G.od_leg[s] / 2
            seg = 32 if s < 3 else 24
            d0 = G.leg_dir(i, z0 + 0.01)
            p0 = G.P(i, z0)
            if s == 0:
                start = p0 - d0 * 0.012
            else:
                start = p0 + d0 * (gap / 2 + tf - 0.004)
            if s == len(G.zsec) - 2:
                end = G.P(i, z1) - Vector((0, 0, 0.012))
            else:
                dj = G.leg_dir(i, z1 - 0.01)
                end = G.P(i, z1) - dj * (gap / 2 + tf - 0.004)
            if z0 < G.zk < z1:
                pk = G.P(i, G.zk)
                path = fillet([start, pk, end], 1.2, 10)
                mb.tube(path, rt, seg=seg, mat=GALV)
            else:
                mb.tube([start, end], rt, seg=seg, mat=GALV)
        # bridas en cada junta: disco inferior (del tramo de abajo) + disco superior + 8 tornillos M24
        for j, zj in enumerate(G.joints):
            dj = G.leg_dir(i, zj - 0.01)
            pj = G.P(i, zj)
            rlo, rhi = G.od_leg[j] / 2, G.od_leg[j + 1] / 2
            rf = rlo + 0.088
            rb = rlo + 0.046
            ph = math.radians(LEG_ANG[i])
            Mlo = frame(dj, ang2(LEG_ANG[i]), pj - dj * (gap / 2))
            Mhi = frame(dj, ang2(LEG_ANG[i]), pj + dj * (gap / 2))
            _flange(mb, Mlo, rf, tf, rlo, up=False, phase=ph)
            _flange(mb, Mhi, rf, tf, rhi, up=True, phase=ph)
            for k in range(8):
                a = ph + 2 * PI * (k + 0.5) / 8
                q = Mlo @ Vector((rb * math.cos(a), rb * math.sin(a), gap + tf))
                mb.join(bolt_pf(bolt_d, 2 * tf + gap, stub=0.6, wseg=12), frame(-dj, None, q))
        # remate superior: tapa abombada soldada
        pt = G.P(i, G.h) - Vector((0, 0, 0.012))
        rt = G.od_leg[-1] / 2
        lathe(mb, [(rt + 0.0012, -0.01), (rt + 0.0016, 0.008), (rt * 0.8, 0.016), (rt * 0.4, 0.021), (0.0, 0.022)], seg=24, mat=GALV,
              M=_T(*pt))


def build_step_bolts(mb, G, leg=0, z0=1.25, step=0.40):
    """Escalones de pie 5/8" × 9" alternados a ±50° de la dirección radial de la pata, cada 0,40 m (0,80 m por lado)."""
    d = 0.0159
    boss = MB()
    _lat(boss, [(0.017, -0.006), (0.017, 0.022), (0.0155, 0.0245)], 12, GALV, cap0=False)
    head = MB()
    lathe(head, [(d * 0.47, 0.0), (d * 0.47, 0.176)], seg=12, mat=GALV, caps=False)
    _hex(head, 0.176, 0.011, 0.024)
    _hex(head, 0.0242, 0.013, 0.024)                                         # contratuerca contra el buje
    n = int((G.h - 0.6 - z0) / step) + 1
    for k in range(n):
        z = z0 + k * step
        sgn = 1 if k % 2 == 0 else -1
        u = ang2(LEG_ANG[leg] + sgn * 50.0)
        rl = G.r_leg(z)
        # evitar bridas y nudos
        if any(abs(z - zj) < 0.16 for zj in G.joints) or any(abs(z - zn) < 0.24 for zn in G.nodes):
            continue
        c = G.P(leg, z)
        M = frame(u, (0, 0, 1), c + u * (rl - 0.004))
        mb.join(boss, M)
        mb.join(head, M)


# ================================================================================================== arriostramiento
def hull2(pts):
    P = sorted(set((round(p[0], 6), round(p[1], 6)) for p in pts))
    if len(P) < 3:
        return P

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 1e-12:
            lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 1e-12:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _dist_line(p, a, d):
    """Distancia de p a la recta a + t·d (d unitario)."""
    v = p - a
    return (v - d * v.dot(d)).length


T_PL = 0.010                  # espesor de cartelas y orejas
OFF = T_PL + 0.0005           # desfase del eje de las barras respecto del plano de la cartela
KN_L = 0.185                  # largo de oreja
KN_IN = 0.125                 # la oreja entra al tubo desde aquí
BOLT_S = (0.032, 0.088)       # posiciones de tornillos sobre la oreja


def _sizes(z_lo):
    """(OD diagonal, OD horizontal, diámetro de tornillo) según la altura."""
    if z_lo < 6.0:
        return 0.0889, 0.0761, 0.020
    if z_lo < 18.0:
        return 0.0761, 0.0603, 0.016
    if z_lo < 30.0:
        return 0.0603, 0.0483, 0.016
    return 0.0483, 0.0483, 0.016


def build_bracing(mb, G):
    N = G.nodes
    zk = G.zk

    def nrm(f, z):
        return ang2(FACE_ANG[f]) if z >= zk - 1e-6 else G.face_n(f)

    members = []        # dict(w0, w1, od, bd, e0, e1)   e = ("node", leg, f, n) | ("cross", f, n)
    zig = 0
    for n in range(len(N) - 1):
        z0, z1 = N[n], N[n + 1]
        od_d, od_h, bd = _sizes(z0)
        for f in range(3):
            a, b = f, (f + 1) % 3
            if z1 <= zk + 1e-6:
                members.append(dict(w0=G.P(a, z0), w1=G.P(b, z1), od=od_d, bd=bd, e0=("node", a, f, n), e1=("node", b, f, n + 1),
                                    cont=True))
                members.append(dict(w0=G.P(b, z0), w1=G.P(a, z1), od=od_d, bd=bd, e0=("node", b, f, n), e1=("node", a, f, n + 1),
                                    cont=False))
            else:
                if zig % 2 == 0:
                    members.append(dict(w0=G.P(a, z0), w1=G.P(b, z1), od=od_d, bd=bd, e0=("node", a, f, n), e1=("node", b, f, n + 1)))
                else:
                    members.append(dict(w0=G.P(b, z0), w1=G.P(a, z1), od=od_d, bd=bd, e0=("node", b, f, n), e1=("node", a, f, n + 1)))
        if z1 > zk + 1e-6:
            zig += 1
    for n in range(1, len(N)):
        od_d, od_h, bd = _sizes(N[n])
        for f in range(3):
            a, b = f, (f + 1) % 3
            members.append(dict(w0=G.P(a, N[n]), w1=G.P(b, N[n]), od=od_h, bd=bd, e0=("node", a, f, n), e1=("node", b, f, n),
                                horiz=True))
    # cruces de las X: el tubo continuo pasa; el otro se parte en dos mitades con orejas a la placa de cruce
    final = []
    pairs = {}
    for m in members:
        if "cont" in m:
            key = (m["e0"][2], m["e0"][3])
            pairs.setdefault(key, [None, None])[0 if m["cont"] else 1] = m
        else:
            final.append(m)
    cross = {}
    for (f, n), (A, B) in pairs.items():
        dA = (A["w1"] - A["w0"]).normalized()
        dB = (B["w1"] - B["w0"]).normalized()
        # punto más cercano entre las dos rectas
        w = A["w0"] - B["w0"]
        a_, b_, c_ = dA.dot(dA), dA.dot(dB), dB.dot(dB)
        d_, e_ = dA.dot(w), dB.dot(w)
        den = a_ * c_ - b_ * b_
        sA = (b_ * e_ - c_ * d_) / den
        C = A["w0"] + dA * sA
        cross[(f, n)] = dict(C=C, A=A, f=f, n=n)
        A2 = dict(A)
        A2["thru"] = (f, n)
        final.append(A2)
        final.append(dict(w0=B["w0"], w1=C, od=B["od"], bd=B["bd"], e0=B["e0"], e1=("cross", f, n), rA=A["od"] / 2))
        final.append(dict(w0=C, w1=B["w1"], od=B["od"], bd=B["bd"], e0=("cross", f, n), e1=B["e1"], rA=A["od"] / 2))
    horiz_at = {}
    for m in final:
        if m.get("horiz"):
            for e in (m["e0"], m["e1"]):
                horiz_at[(e[1], e[2], e[3])] = m

    def end_info(e, wp, d_out, m):
        """Devuelve (normal del plano, a0) para el extremo e con punto de trabajo wp y dirección d_out hacia la barra."""
        if e[0] == "node":
            leg, f, n = e[1], e[2], e[3]
            z = N[n]
            nn = nrm(f, z)
            rl = G.r_leg(z + (0.02 if d_out.z > 0.05 else -0.02 if d_out.z < -0.05 else 0.0))
            rl = max(rl, G.r_leg(z))
            dl = G.leg_dir(leg, z + 0.01 * (1 if d_out.z >= 0 else -1))
            md = (d_out - nn * d_out.dot(nn)).normalized()
            lat = nn.cross(md).normalized()
            w = m["od"] + 0.02
            H = horiz_at.get((leg, f, n))
            s = rl + 0.02
            while s < 1.2:
                ok = True
                for sg in (-1, 1):
                    k = wp + md * s + lat * (sg * w / 2)
                    if _dist_line(k, wp, dl) < rl + 0.016:
                        ok = False
                    if H is not None and H is not m and not m.get("horiz"):
                        dh = (H["w1"] - H["w0"]).normalized()
                        if _dist_line(k, wp, dh) < (H["od"] + 0.02) / 2 + 0.014:
                            ok = False
                if ok:
                    break
                s += 0.005
            return nn, s
        f, n = e[1], e[2]
        cr = cross[(f, n)]
        nn = G.face_n(f)
        A = cr["A"]
        dA = (A["w1"] - A["w0"]).normalized()
        md = (d_out - nn * d_out.dot(nn)).normalized()
        lat = nn.cross(md).normalized()
        w = m["od"] + 0.02
        s = 0.03
        while s < 1.0:
            if all(_dist_line(wp + md * s + lat * (sg * w / 2), wp, dA) >= m["rA"] + 0.012 for sg in (-1, 1)):
                break
            s += 0.005
        return nn, s

    plates = {}         # clave de nudo/cruce -> lista de puntos 3D a cubrir
    for m in final:
        w0, w1 = m["w0"], m["w1"]
        d = (w1 - w0).normalized()
        n0, a0 = end_info(m["e0"], w0, d, m)
        n1, a1 = end_info(m["e1"], w1, -d, m)
        r = m["od"] / 2
        o0, o1 = n0 * OFF, n1 * OFF
        two = m["od"] > 0.061
        kn_l, kn_in, bs = (KN_L, KN_IN, BOLT_S) if two else (0.135, 0.075, (0.038,))
        p0 = w0 + o0 + d * (a0 + kn_in)
        p1 = w1 + o1 - d * (a1 + kn_in)
        seg = 16
        mb.tube([p0, p1], r, seg=seg, mat=GALV)
        for (e, wp, nn, a, dd) in ((m["e0"], w0, n0, a0, d), (m["e1"], w1, n1, a1, -d)):
            md = (dd - nn * dd.dot(nn)).normalized()
            lat = nn.cross(md).normalized()
            w = m["od"] + 0.02
            ch = 0.014
            M = Matrix(((md.x, lat.x, nn.x, 0), (md.y, lat.y, nn.y, 0), (md.z, lat.z, nn.z, 0), (0, 0, 0, 1)))
            M = _T(*(wp + nn * (T_PL / 2 + 0.0005))) @ M
            outline = [(a + ch, -w / 2), (a + kn_l, -w / 2), (a + kn_l, w / 2), (a + ch, w / 2), (a, w / 2 - ch), (a, -w / 2 + ch)]
            mb.plate(outline, T_PL, GALV, m=M)
            for sb in bs:
                q = wp + md * (a + sb) - nn * (T_PL / 2)
                bolt_at(mb, q, nn, m["bd"], 2 * T_PL + 0.0005, md)
            key = e if e[0] == "cross" else e
            pts = plates.setdefault(key, [])
            for (s_, l_) in ((a - 0.012, w / 2 + 0.018), (a + kn_in - 0.015, w / 2 + 0.018)):
                for sg in (-1, 1):
                    pts.append(wp + md * s_ + lat * (sg * l_))
    # cartelas de nudo
    for key, pts in plates.items():
        if key[0] == "node":
            leg, f, n = key[1], key[2], key[3]
            z = N[n]
            wp = G.P(leg, z)
            nn = nrm(f, z)
            other = G.P((f + 1) % 3 if leg == f else f, z)
            ein = other - wp
            ein = (ein - nn * ein.dot(nn)).normalized()
            ev = nn.cross(ein).normalized()
            if ev.z < 0:
                ev = -ev
            rl = G.r_leg(z)
            q2 = [((p - wp).dot(ein), (p - wp).dot(ev)) for p in pts]
            vmin = min(q[1] for q in q2) - 0.02
            vmax = max(q[1] for q in q2) + 0.02
            dlo = G.leg_dir(leg, z - 0.01)
            dhi = G.leg_dir(leg, z + 0.01)
            if any(abs(z - zj) < 0.5 for zj in G.joints):
                vmin = max(vmin, -0.21)
            if z >= G.h - 0.3:
                vmax = min(vmax, G.h - z - 0.03)
            ebot = wp + ein * (rl - 0.004) + dlo * (vmin / max(dlo.dot(ev), 0.5))
            etop = wp + ein * (rl - 0.004) + dhi * (vmax / max(dhi.dot(ev), 0.5))
            q2 += [((ebot - wp).dot(ein), (ebot - wp).dot(ev)), ((etop - wp).dot(ein), (etop - wp).dot(ev))]
            q2 = [(max(x, (rl - 0.004)), y) for (x, y) in q2]
            hl = hull2(q2)
            M = Matrix(((ein.x, ev.x, nn.x, 0), (ein.y, ev.y, nn.y, 0), (ein.z, ev.z, nn.z, 0), (0, 0, 0, 1)))
            mb.plate(hl, T_PL, GALV, m=_T(*wp) @ M @ _T(0, 0, -T_PL / 2))
            # cordones de soldadura a lo largo de la línea pata-cartela (ambas caras)
            xs = [p for p in hl if abs(p[0] - (rl - 0.004)) < 1e-4]
            if len(xs) >= 2:
                ya, yb = min(p[1] for p in xs), max(p[1] for p in xs)
                for sg in (-1, 1):
                    prof = [(0.0, 0.0), (0.0065, 0.0), (0.0, 0.0065)]
                    Mw = _T(*(wp + ein * (rl - 0.003) + nn * (sg * T_PL / 2))) @ Matrix(
                        ((ev.x, ein.x, nn.x * sg, 0), (ev.y, ein.y, nn.y * sg, 0), (ev.z, ein.z, nn.z * sg, 0), (0, 0, 0, 1)))
                    prism(mb, prof, Mw, ya + 0.004, yb - 0.004, GALV)
        else:
            cr = cross[(key[1], key[2])]
            C = cr["C"]
            nn = G.face_n(key[1])
            A = cr["A"]
            dA = (A["w1"] - A["w0"]).normalized()
            e1 = (dA - nn * dA.dot(nn)).normalized()
            e2 = nn.cross(e1)
            q2 = [((p - C).dot(e1), (p - C).dot(e2)) for p in pts]
            q2 += [(0.09, 0.0), (-0.09, 0.0)]
            hl = hull2(q2)
            M = Matrix(((e1.x, e2.x, nn.x, 0), (e1.y, e2.y, nn.y, 0), (e1.z, e2.z, nn.z, 0), (0, 0, 0, 1)))
            mb.plate(hl, T_PL, GALV, m=_T(*C) @ M @ _T(0, 0, -T_PL / 2))
    return dict(nodes=N)


# ================================================================================================== escaleras y soportes
def support_levels(G):
    return [z for z in G.nodes if z >= 2.9 and abs(z - G.z_mw) > 0.6 and abs(z - G.z_top) > 0.6 and z < G.h - 0.5]


def _rtube(mb, p0, p1, w, h, up, mat=GALV, r=0.006, n=3, planes=None):
    """Tubo rectangular (PTR) de esquinas redondeadas de p0 a p1; w lateral, h en `up`."""
    M = frame_xz(V3(p1) - V3(p0), up, p0)
    L = (V3(p1) - V3(p0)).length
    prism(mb, rr_pts2(w, h, r, n), M, 0.0, L, mat, planes=planes)


def build_supports(mb, G):
    """Marcos soporte de las escaleras: travesaño PTR 80×40 detrás de ambas escaleras + 2 brazos PTR hasta el horizontal de la
    cara +Y, con placa extrema y 2 pernos en U por brazo."""
    yb = G.y_beam
    for zs in support_levels(G):
        n1 = ang2(FACE_ANG[1]) if zs >= G.zk - 1e-6 else G.face_n(1)
        ph = G.P(1, zs) + n1 * OFF
        od_d, od_h, bd = _sizes(zs)
        rh = od_h / 2
        yh, zh = ph.y, ph.z
        x0, x1 = -0.66, 0.62
        _rtube(mb, (x0, yb + 0.02, zh), (x1, yb + 0.02, zh), 0.04, 0.08, (0, 0, 1))
        for xe in (x0, x1):                                                     # tapas soldadas
            mb.box((xe - 0.003 if xe < 0 else xe - 0.0005, yb - 0.0005, zh - 0.0405), (xe + 0.0005 if xe < 0 else xe + 0.003, yb + 0.0405, zh + 0.0405), GALV)
        yp = yh - rh - 0.0025                                                   # cara frontal de la placa extrema
        for xa in (-0.25, 0.25):
            _rtube(mb, (xa, yb + 0.039, zh), (xa, yp - 0.0115, zh), 0.05, 0.08, (0, 0, 1))
            mb.box((xa - 0.055, yp - 0.012, zh - 0.07), (xa + 0.055, yp, zh + 0.07), GALV, bevel=0.002, seg=1)
            for dx in (-0.04, 0.04):
                M = Matrix(((0, 1, 0, xa + dx), (-1, 0, 0, yh), (0, 0, 1, zh), (0, 0, 0, 1)))
                ubolt(mb, M, rh, d=0.010, reach=rh + 0.0025 + 0.012, seg=12, bend_seg=7)
        # ménsulas de los largueros de la escalera de ascenso (ángulo de clip: ala contra el larguero, ala contra el travesaño)
        for sgn in (-1, 1):
            xr = G.x_lad + sgn * 0.225
            xa = xr + sgn * 0.0065
            xb = xa + sgn * 0.008
            mb.box((min(xa, xb), G.y_lad - 0.02, zh - 0.05), (max(xa, xb), yb - 0.0005, zh + 0.05), GALV, bevel=0.0015, seg=1)
            xc_ = xa + sgn * 0.075
            mb.box((min(xb, xc_), yb - 0.0085, zh - 0.05), (max(xb, xc_), yb - 0.0005, zh + 0.05), GALV, bevel=0.0015, seg=1)
            bolt_at(mb, Vector((xr - sgn * 0.006, G.y_lad + 0.005, zh)), Vector((sgn, 0, 0)), 0.012, 0.0205, (0, 0, 1))
            bolt_at(mb, Vector((xa + sgn * 0.045, yb + 0.004, zh)), Vector((0, -1, 0)), 0.012, 0.0125, (0, 0, 1), stub=0.3)
        # separadores de la escalerilla de cables (canal en Z desde el ala trasera del larguero hasta el travesaño)
        for sgn in (-1, 1):
            xm = G.x_cab + sgn * 0.272
            yr = G.y_lad + 0.025
            mb.box((xm - 0.004, yr + 0.0085, zh - 0.05), (xm + 0.004, yb - 0.0085, zh + 0.05), GALV, bevel=0.0015, seg=1)
            mb.box((xm - 0.022, yr + 0.0005, zh - 0.05), (xm + 0.022, yr + 0.0085, zh + 0.05), GALV, bevel=0.0015, seg=1)
            mb.box((xm - 0.022, yb - 0.0085, zh - 0.05), (xm + 0.022, yb - 0.0005, zh + 0.05), GALV, bevel=0.0015, seg=1)
            bolt_at(mb, Vector((xm - sgn * 0.0135, yr - 0.005, zh)), Vector((0, 1, 0)), 0.010, 0.0135, (0, 0, 1), stub=0.3)
            bolt_at(mb, Vector((xm + sgn * 0.0135, yb + 0.004, zh)), Vector((0, -1, 0)), 0.010, 0.0125, (0, 0, 1), stub=0.3)


def build_climb_ladder(mb, G):
    """Escalera de ascenso: largueros de solera 60×12, peldaños Ø25 cada 0,30 m, empalmes atornillados, pie sobre dado de
    concreto, riel rígido anticaídas central con abrazaderas en U a los peldaños y salida 1,15 m sobre la plataforma superior."""
    xl, yl = G.x_lad, G.y_lad
    ztop = G.z_top + 1.15
    for sx in (-1, 1):
        xr = xl + sx * 0.225
        z0 = 0.06
        # largueros en tramos de 6 m con placas de empalme
        cuts = [z0] + [6.0 * k + 1.5 for k in range(1, 8) if 6.0 * k + 1.5 < ztop - 1.0] + [ztop]
        for a, b in zip(cuts[:-1], cuts[1:]):
            mb.box((xr - 0.006, yl - 0.03, a + 0.002), (xr + 0.006, yl + 0.03, b - 0.002), GALV, bevel=0.002, seg=1)
        for zc in cuts[1:-1]:
            for side in (-1, 1):
                x0 = xr + side * 0.0065
                mb.box((min(x0, x0 + side * 0.008), yl - 0.027, zc - 0.16), (max(x0, x0 + side * 0.008), yl + 0.027, zc + 0.16), GALV,
                       bevel=0.002)
            for dz in (-0.11, -0.05, 0.05, 0.11):
                bolt_at(mb, Vector((xr - sx * 0.0145, yl, zc + dz)), Vector((sx, 0, 0)), 0.012, 0.029, (0, 0, 1), stub=0.35)
    # peldaños
    z = 0.30
    while z < ztop - 0.12:
        if not any(abs(z - c) < 0.17 for c in [6.0 * k + 1.5 for k in range(1, 8)]):
            mb.cyl((xl - 0.225 - 0.0095, yl, z), (xl + 0.225 + 0.0095, yl, z), 0.0125, seg=16, mat=GALV)
        z += 0.30
    # pie: dado de concreto y ángulos de anclaje
    mb.box((xl - 0.42, yl - 0.2, -0.12), (xl + 0.42, yl + 0.16, 0.10), "concrete", bevel=0.012, seg=2)
    for sx in (-1, 1):
        xr = xl + sx * 0.225
        xo = xr + sx * 0.0065
        mb.box((min(xo, xo + sx * 0.008), yl - 0.035, 0.1075), (max(xo, xo + sx * 0.008), yl + 0.035, 0.2), GALV, bevel=0.0015, seg=1)
        mb.box((min(xo, xo + sx * 0.08), yl - 0.035, 0.1), (max(xo, xo + sx * 0.08), yl + 0.035, 0.108), GALV, bevel=0.0015, seg=1)
        mb.join(nut_pf(0.012, stub=0.8), _T(xo + sx * 0.05, yl, 0.108))
        for dz in (0.13, 0.17):
            bolt_at(mb, Vector((xr - sx * 0.0065, yl, dz)), Vector((sx, 0, 0)), 0.010, 0.0215, (0, 0, 1), stub=0.35)
    # riel rígido anticaídas (perfil C con labios) al centro, frente a los peldaños
    prof = [(-0.02, 0.0), (0.02, 0.0), (0.02, 0.03), (0.009, 0.03), (0.009, 0.026), (0.016, 0.026), (0.016, 0.004), (-0.016, 0.004),
            (-0.016, 0.026), (-0.009, 0.026), (-0.009, 0.03), (-0.02, 0.03)]
    yr = yl - 0.0125 - 0.003
    M = Matrix(((0, 1, 0, xl), (0, 0, -1, yr), (1, 0, 0, 0), (0, 0, 0, 1)))
    prism(mb, prof, M, 0.9, ztop - 0.05, GALV)
    z = 0.30
    k = 0
    while z < ztop - 0.12:
        if z > 1.0 and k % 6 == 0 and not any(abs(z - c) < 0.17 for c in [6.0 * j + 1.5 for j in range(1, 8)]):
            mb.box((xl - 0.045, yl + 0.0128, z - 0.035), (xl + 0.045, yl + 0.0208, z + 0.035), GALV, bevel=0.0015, seg=1)
            mb.box((xl - 0.045, yr - 0.0005, z - 0.035), (xl + 0.045, yr + 0.0025, z + 0.035), GALV, bevel=0.001, seg=1)
            for dz in (-0.023, 0.023):
                bolt_at(mb, Vector((xl, yl + 0.0208, z + dz)), Vector((0, -1, 0)), 0.008, yl + 0.0208 - yr + 0.004, (0, 0, 1),
                        stub=0.0)
        z += 0.30
        k += 1
    # tope superior del riel y escuadra de salida
    mb.box((xl - 0.022, yr - 0.034, ztop - 0.05), (xl + 0.022, yr + 0.002, ztop - 0.04), GALV, bevel=0.002, seg=1)


def build_cable_ladder(mb, G):
    """Escalerilla vertical de cables: largueros de ángulo 50×50×5, peldaños de canal unicanal 41×21 cada 0,40 m atornillados."""
    xc, yl = G.x_cab, G.y_lad
    z0, z1 = G.z_cl0, G.z_top - 0.20
    for sx in (-1, 1):
        xi = xc + sx * 0.245
        prof = [(0.0, 0.0), (0.005, 0.0), (0.005, 0.045), (0.05, 0.045), (0.05, 0.05), (0.0, 0.05)]
        prof = [(sx * px, py) for (px, py) in prof]
        M = Matrix(((0, 1, 0, xi), (0, 0, 1, yl - 0.025), (1, 0, 0, 0), (0, 0, 0, 1)))
        prism(mb, prof, M, z0, z1, GALV)
    rungs = []
    z = z0 + 0.05
    prof = rr_pts2(0.021, 0.041, 0.003, 2)
    while z < z1 - 0.02:
        M = Matrix(((1, 0, 0, xc - 0.2445), (0, 1, 0, yl), (0, 0, 1, z), (0, 0, 0, 1)))
        prism(mb, prof, M, 0.0, 0.489, GALV)
        for sx in (-1, 1):
            mb.join(nut_pf(0.010, stub=0.0), frame((sx, 0, 0), (0, 0, 1), (xc + sx * 0.25, yl, z)))
        rungs.append(z)
        z += 0.40
    return rungs


# ================================================================================================== cables
def cable_layout(G):
    """Posición en planta de los 18 cables: 2 filas × 9 al frente (-Y) de los peldaños de la escalerilla.
    Fila A (junto a los peldaños): 9 negros; fila B: B0 y B8 fibra amarilla Ø13, B1..B7 negros Ø26."""
    yrf = G.y_lad - 0.0105
    out = []
    for row, yy in (("A", yrf - 0.0235), ("B", yrf - 0.0705)):
        for k in range(9):
            x = G.x_cab - 0.168 + 0.042 * k
            yellow = row == "B" and k in (0, 8)
            out.append(dict(id=f"{row}{k}", x=x, y=yy, r=0.0065 if yellow else 0.013, mat="paint_yellow" if yellow else "cable",
                            row=row, k=k))
    return out


def _box_body(mb, x0, x1, y0, y1, z0, z1, mat="aluminium", lid_side=-1):
    """Gabinete de aluminio con tapa frontal (junta perimetral hundida), bisagras y 2 pestillos."""
    mb.box((x0, y0 + 0.012, z0), (x1, y1, z1), mat, bevel=0.005, seg=2)
    mb.box((x0 + 0.004, y0, z0 + 0.004), (x1 - 0.004, y0 + 0.0128, z1 - 0.004), mat, bevel=0.004, seg=2)
    xh = x0 - 0.004 if lid_side < 0 else x1 + 0.004
    for zz in (z0 + 0.06, z1 - 0.09):
        mb.cyl((xh, y0 + 0.008, zz), (xh, y0 + 0.008, zz + 0.03), 0.0045, seg=12, mat="steel")
    xl = x1 - 0.002 if lid_side < 0 else x0 + 0.002
    for zz in ((z0 + z1) / 2 - 0.06, (z0 + z1) / 2 + 0.04):
        mb.box((xl - 0.008, y0 - 0.006, zz), (xl + 0.008, y0 + 0.002, zz + 0.022), "steel", bevel=0.002, seg=1)


def build_cables(mb, G):
    """Cables troncales: suben por la escalerilla sujetos por abrazaderas de bloque cada 1,2 m, salen al pie en una curva de
    R 0,30 m hacia +Y sobre una charola corta (inicio del puente de hielo), 2 se desvían a ~31 m hacia los tubos de los
    platos de microondas y 16 terminan en 3 cajas de distribución bajo la plataforma de sectores."""
    cab = cable_layout(G)
    yA = cab[0]["y"]
    RA = 0.30
    zA = G.z_exit
    G.y_exit = G.rin(zA) + 0.30
    zbb = G.z_top - 1.0                     # fondo de las cajas de distribución
    rungs = [G.z_cl0 + 0.05 + 0.4 * k for k in range(200) if G.z_cl0 + 0.05 + 0.4 * k < G.z_top - 0.22]
    clamps = [z for i, z in enumerate(rungs) if i % 3 == 1 and z > zA + RA + 0.1 and z < zbb - 0.12]
    z_run = 31.15 * G.k
    r = rng(5)
    mw_ids = {"A0": -1, "A8": 1}
    boxes = [(G.x_cab - 0.13, ("A1", "A2", "B0", "B1", "B2")), (G.x_cab, ("A3", "A4", "A5", "B3", "B4", "B5")),
             (G.x_cab + 0.13, ("A6", "A7", "B6", "B7", "B8"))]
    ends = {}
    for c in cab:
        x, y, rc = c["x"], c["y"], c["r"]
        R = RA + (yA - y)
        zh = zA - (yA - y) + (0.0 if c["r"] > 0.01 else 0.0)
        cy, cz = y + R, zh + R                                  # centro común de la curva inferior
        pts = [(x, G.y_exit - 0.004 * (c["k"] % 3), zh)]
        pts.append((x, cy + 0.0, zh))
        for j in range(1, 10):
            a = -PI / 2 - (PI / 2) * j / 10
            pts.append((x, cy + R * math.cos(a), cz + R * math.sin(a)))
        pts.append((x, y, cz))
        top = None
        if c["id"] in mw_ids:
            top = z_run - 0.45
        else:
            top = zbb - 0.015
        for zc in clamps[::2]:
            if cz + 0.05 < zc < top - 0.1:
                pts.append((x + float(r.uniform(-0.0012, 0.0012)), y + float(r.uniform(-0.001, 0.001)), zc))
        pts.append((x, y, top))
        if c["id"] in mw_ids:
            sg = mw_ids[c["id"]]
            am = math.radians(90.0 - sg * 60.0)
            pc = Vector((math.cos(am), math.sin(am), 0.0)) * 1.88
            tv = Vector((-math.sin(am), math.cos(am), 0.0)) * sg
            pend = pc + tv * 0.075
            xr = x if sg > 0 else -0.45
            tail = [(x, y, z_run), (x, 0.40, z_run)] if sg < 0 else [(x, y, z_run)]
            tail += [(xr, 0.40 if sg < 0 else 0.75, z_run)]
            if sg < 0:
                tail += [(xr, 0.75, z_run)]
            mid = Vector(((xr + pend.x) / 2, (0.75 + pend.y) / 2, z_run - 0.03))
            tail += [tuple(mid), (pend.x, pend.y, z_run + 0.1), (pend.x, pend.y, G.z_mw + 0.13)]
            path = pts[:-1] + fillet([pts[-2]] + tail, 0.1, 8)[1:]
            mb.tube(path, 0.0095, seg=14, mat=c["mat"])
            ends[c["id"]] = (pend.x, pend.y, G.z_mw + 0.13, tv.x, tv.y)
        else:
            mb.tube(pts, rc, seg=14, mat=c["mat"])
    # abrazaderas de bloque en la escalerilla
    yrf = G.y_lad - 0.0105
    xc = G.x_cab
    for zc in clamps:
        mb.box((xc - 0.215, yrf - 0.047, zc - 0.02), (xc + 0.215, yrf - 0.0005, zc + 0.02), "rubber", bevel=0.004, seg=1)
        mb.box((xc - 0.215, yrf - 0.0945, zc - 0.02), (xc + 0.215, yrf - 0.0475, zc + 0.02), "rubber", bevel=0.004, seg=1)
        mb.box((xc - 0.22, yrf - 0.0985, zc - 0.017), (xc + 0.22, yrf - 0.0948, zc + 0.017), "steel", bevel=0.0012, seg=1)
        for sx in (-1, 1):
            mb.cyl((xc + sx * 0.2, yrf + 0.021, zc), (xc + sx * 0.2, yrf - 0.0985, zc), 0.004, seg=12, mat="steel", caps=False)
            mb.join(nut_pf(0.008, mat="steel", stub=0.9, wseg=12), frame((0, -1, 0), (0, 0, 1), (xc + sx * 0.2, yrf - 0.0985, zc)))
            mb.join(nut_pf(0.008, mat="steel", stub=0.0, washer=False), frame((0, 1, 0), (0, 0, 1), (xc + sx * 0.2, yrf + 0.021, zc)))
    # cajas de distribución (OVP) con prensaestopas, colgadas del peldaño
    zt = zbb + 0.42
    for (bx, ids) in boxes:
        x0, x1 = bx - 0.0625, bx + 0.0625
        mb.box((x0 + 0.01, yrf - 0.004, zbb - 0.03), (x1 - 0.01, yrf - 0.0005, zt + 0.03), "steel", bevel=0.0012, seg=1)
        _box_body(mb, x0, x1, yrf - 0.104, yrf - 0.0045, zbb, zt, lid_side=-1 if bx < xc else 1)
        for c in cab:
            if c["id"] in ids:
                lathe(mb, [(c["r"] + 0.006, zbb + 0.002), (c["r"] + 0.006, zbb - 0.012), (c["r"] + 0.003, zbb - 0.016),
                           (c["r"] + 0.0015, zbb - 0.03)], seg=16, mat="plastic", M=_T(c["x"], c["y"], 0.0), caps=True)
        for zz in (zbb - 0.02, zt + 0.02):
            mb.join(nut_pf(0.008, mat="steel", stub=0.0, wseg=12), frame((0, -1, 0), (0, 0, 1), (bx, yrf - 0.004, zz)))
    # conduit de la baliza: sale por arriba de la caja central
    lathe(mb, [(0.016, zt - 0.002), (0.016, zt + 0.02), (0.0125, zt + 0.026)], seg=16, mat="plastic", M=_T(xc, yrf - 0.054, 0.0))
    G.conduit0 = Vector((xc, yrf - 0.054, zt + 0.02))
    # charola horizontal corta al pie (arranque del puente de hielo) colgada con varillas roscadas
    ztr = zA - 0.047 - 0.013 - 0.0225
    y0t, y1t = 0.34, G.y_exit - 0.02
    for sx in (-1, 1):
        xi = xc + sx * 0.245
        prof = [(0.0, 0.0), (0.005, 0.0), (0.005, 0.045), (0.05, 0.045), (0.05, 0.05), (0.0, 0.05)]
        prof = [(sx * px, -py + 0.025) for (px, py) in prof]
        M = Matrix(((0, 1, 0, xi), (1, 0, 0, 0), (0, 0, 1, ztr), (0, 0, 0, 1)))
        prism(mb, [(a_, b_) for (a_, b_) in prof], M, y0t, y1t, GALV)
    yy = y0t + 0.05
    while yy < y1t - 0.03:
        prism(mb, rr_pts2(0.041, 0.021, 0.003, 2), _T(xc - 0.2445, yy, ztr - 0.0005), 0.0, 0.489, GALV)
        yy += 0.30
    for yc in (0.95, y1t - 0.12):
        zc = ztr + 0.0205
        mb.box((xc - 0.215, yc - 0.02, zc + 0.0005), (xc + 0.215, yc + 0.02, zc + 0.047), "rubber", bevel=0.004, seg=1)
        mb.box((xc - 0.215, yc - 0.02, zc + 0.0475), (xc + 0.215, yc + 0.02, zc + 0.0945), "rubber", bevel=0.004, seg=1)
        mb.box((xc - 0.22, yc - 0.017, zc + 0.0948), (xc + 0.22, yc + 0.017, zc + 0.0985), "steel", bevel=0.0012, seg=1)
    n1 = G.face_n(1)
    ph = G.P(1, 3.0) + n1 * OFF
    for (yh, zt2) in ((0.35, 2.965), (ph.y, ph.z)):
        for sx in (-1, 1):
            xr_ = xc + sx * 0.272
            ztop_ = zt2
            mb.cyl((xr_, yh, ztr - 0.03), (xr_, yh, ztop_), 0.005, seg=12, mat=GALV, caps=True)
            mb.join(nut_pf(0.010, stub=0.0), frame((0, 0, -1), (1, 0, 0), (xr_, yh, ztr - 0.025 + 0.0)))
    # barra de tierra de la torre (TGB) en la escalera de ascenso, lado +Y
    zg = 1.25
    xl = G.x_lad
    for sx in (-1, 1):
        mb.box((xl + sx * 0.225 - 0.03, 0.2505, zg - 0.04), (xl + sx * 0.225 + 0.03, 0.2585, zg + 0.04), GALV, bevel=0.0015, seg=1)
    mb.box((xl - 0.26, 0.2585, zg - 0.025), (xl + 0.26, 0.2665, zg + 0.025), GALV, bevel=0.0015, seg=1)
    for sx in (-1, 1):
        lathe(mb, [(0.016, 0.0), (0.018, 0.004), (0.018, 0.04), (0.015, 0.045)], seg=16, mat="plastic",
              M=frame((0, 1, 0), (1, 0, 0), (xl + sx * 0.19, 0.2665, zg)))
    mb.box((xl - 0.25, 0.3115, zg - 0.05), (xl + 0.25, 0.3179, zg + 0.05), "copper", bevel=0.0012, seg=1)
    lugs = [(xl - 0.15, "down"), (xl - 0.09, "down"), (xl + 0.03, "ladder"), (xl + 0.15, "leg")]
    for k in range(8):
        xx = xl - 0.21 + 0.06 * k
        yy0 = 0.3219 if any(abs(xx - q[0]) < 1e-6 for q in lugs) else 0.3179
        for zz in (zg - 0.022, zg + 0.022):
            mb.join(nut_pf(0.010, mat="steel", stub=0.0, wseg=12), frame((0, 1, 0), (1, 0, 0), (xx, yy0, zz)))
    for (xx, kind) in lugs:
        mb.box((xx - 0.011, 0.3179, zg - 0.035), (xx + 0.011, 0.3219, zg + 0.035), "copper", bevel=0.001, seg=1)
        lathe(mb, [(0.0085, 0.0), (0.0085, 0.03), (0.006, 0.036)], seg=12, mat="copper",
              M=frame((0, 0, -1), (1, 0, 0), (xx, 0.3299, zg - 0.035)))
        p0 = Vector((xx, 0.3299, zg - 0.068))
        if kind == "down":
            path = [p0, p0 + Vector((0, 0.02, -0.3)), Vector((xx + 0.05, 0.42, 0.25)), Vector((xx + 0.07, 0.44, -0.15))]
        elif kind == "ladder":
            zl = G.z_cl0 + 0.25
            path = [p0, p0 + Vector((0, 0.03, -0.12)), Vector((xc - 0.29, 0.36, zg - 0.05)),
                    Vector((xc - 0.29, 0.30, 2.2)), Vector((xc - 0.28, 0.2665, zl - 0.06))]
            mb.box((xc - 0.291, 0.2455, zl - 0.012), (xc - 0.269, 0.2495, zl + 0.05), "copper", bevel=0.001, seg=1)
            lathe(mb, [(0.0085, 0.0), (0.0085, 0.03), (0.006, 0.036)], seg=12, mat="copper",
                  M=frame((0, 0, -1), (1, 0, 0), (xc - 0.28, 0.258, zl - 0.012)))
            mb.join(nut_pf(0.010, mat="steel", stub=0.0, wseg=12), frame((0, 1, 0), (1, 0, 0), (xc - 0.28, 0.2495, zl + 0.025)))
            path[-1] = Vector((xc - 0.28, 0.258, zl - 0.045))
        else:
            path = [p0, p0 + Vector((0, 0.05, -0.15)), Vector((xx + 0.2, 0.5, 0.6)), Vector((xx + 0.25, 0.55, -0.15))]
        mb.tube(fillet(path, 0.08, 6), 0.0055, seg=12, mat="copper")
    G.cable_ends = ends
    G.clamps = clamps
    return ends


# ================================================================================================== plataformas
def closed_tube(mb, pts, r, seg=16, mat=GALV):
    """Tubo cerrado sobre un lazo horizontal (pasamanos perimetral sin costura)."""
    P = [V3(p) for p in pts]
    n = len(P)
    U = Vector((0, 0, 1))
    rings = []
    for i in range(n):
        T = (P[(i + 1) % n] - P[i - 1]).normalized()
        B = T.cross(U).normalized()
        rings.append([mb.bm.verts.new(P[i] + (U * math.cos(2 * PI * k / seg) + B * math.sin(2 * PI * k / seg)) * r) for k in range(seg)])
    for i in range(n):
        A, Bq = rings[i], rings[(i + 1) % n]
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([A[k], A[kk], Bq[kk], Bq[k]], mat)


def round_loop(poly, rad, z, nseg=6):
    """Contorno 2D cerrado con esquinas redondeadas de radio rad, a la altura z."""
    out = []
    k = len(poly)
    for i in range(k):
        a, b, c = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % k])
        d0, d1 = (a - b).normalized(), (c - b).normalized()
        ang = math.acos(max(min(d0.dot(d1), 1.0), -1.0))
        t = min(rad / math.tan(ang / 2), (a - b).length * 0.45, (c - b).length * 0.45)
        p0, p1 = b + d0 * t, b + d1 * t
        for j in range(nseg + 1):
            u = j / nseg
            q = p0.lerp(b, u).lerp(b.lerp(p1, u), u)
            out.append((q.x, q.y, z))
    return out


def poly_area(poly):
    return 0.5 * abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                         for i in range(len(poly))))


def grating(mb, poly, z_f, d, pitch=0.033, cpitch=0.1):
    """Rejilla electroforjada: banda perimetral 5×30, soleras portantes 5×30 cada 33 mm a lo largo de `d` y varillas
    transversales 5×6 cada 100 mm (2 mm bajo la cara superior)."""
    poly = poly_ccw([tuple(p[:2]) for p in poly])
    if len(poly) < 3 or poly_area(poly) < 0.004:
        return
    inner = offset_poly(poly, -0.005)
    ring_extrude(mb, poly, inner, z_f - 0.03, z_f, GALV)
    e = offset_poly(poly, -0.006)
    d = Vector((d[0], d[1])).normalized()
    p = Vector((-d.y, d.x))
    for (dd, pp, pt, h0, h1, w) in ((d, p, pitch, z_f - 0.03, z_f, 0.005), (p, d, cpitch, z_f - 0.008, z_f - 0.002, 0.005)):
        proj = [x * pp.x + y * pp.y for x, y in e]
        o = min(proj) + pt / 2
        while o < max(proj):
            org = (pp.x * o, pp.y * o)
            iv = line_interval(e, org, (dd.x, dd.y))
            if iv and iv[1] - iv[0] > 0.02:
                a = Vector(org) + dd * iv[0]
                b = Vector(org) + dd * iv[1]
                q = [a - pp * (w / 2), b - pp * (w / 2), b + pp * (w / 2), a + pp * (w / 2)]
                mb.plate([(v.x, v.y) for v in q], h1 - h0, GALV, m=_T(0, 0, h0))
            o += pt


def split_holes(poly, holes, gap=0.005):
    pieces = [poly]
    for (x0, x1, y0, y1) in holes:
        new = []
        for pc in pieces:
            L = clip_poly(pc, (1, 0), x0 - gap)
            R = clip_poly(pc, (-1, 0), -(x1 + gap))
            mid = clip_poly(clip_poly(pc, (-1, 0), -(x0 + gap)), (1, 0), x1 - gap)
            B = clip_poly(mid, (0, 1), y0)
            Tp = clip_poly(mid, (0, -1), -y1)
            for q in (L, R, B, Tp):
                if len(q) >= 3 and poly_area(q) > 0.002:
                    new.append(q)
        pieces = new
    return pieces


IBEAM = [(-0.05, -0.13), (0.05, -0.13), (0.05, -0.122), (0.003, -0.122), (0.003, -0.038), (0.05, -0.038), (0.05, -0.03),
         (-0.05, -0.03), (-0.05, -0.038), (-0.003, -0.038), (-0.003, -0.122), (-0.05, -0.122)]
WEB = [(-0.003, -0.1215), (0.003, -0.1215), (0.003, -0.0385), (-0.003, -0.0385)]
ANG50 = [(0.0, -0.08), (0.005, -0.08), (0.005, -0.035), (0.05, -0.035), (0.05, -0.03), (0.0, -0.03)]


def _leg_ring(mb, G, i, z0, z1, ear_dir):
    """Abrazadera partida alrededor de la pata (aro de solera con orejas atornilladas)."""
    c = G.P(i, (z0 + z1) / 2)
    rl = G.r_leg((z0 + z1) / 2)
    lathe(mb, [(rl + 0.0008, z0), (rl + 0.012, z0), (rl + 0.012, z1), (rl + 0.0008, z1)], seg=32, mat=GALV, M=_T(c.x, c.y, 0.0),
          closed=True, caps=False)
    e = V3(ear_dir).normalized()
    side = Vector((0, 0, 1)).cross(e)
    for sg in (-1, 1):
        u = side * sg
        for off in (-0.008, 0.008):
            base = Vector((c.x, c.y, z0)) + e * off
            M = Matrix(((u.x, 0, e.x, base.x), (u.y, 0, e.y, base.y), (0, 1, 0, base.z), (0, 0, 0, 1)))
            mb.plate([(rl + 0.006, 0.006), (rl + 0.055, 0.006), (rl + 0.055, z1 - z0 - 0.006), (rl + 0.006, z1 - z0 - 0.006)], 0.006,
                     GALV, m=M @ _T(0, 0, -0.003))
        q = Vector((c.x, c.y, (z0 + z1) / 2)) + u * (rl + 0.035) - e * 0.011
        bolt_at(mb, q, e, 0.012, 0.022, (0, 0, 1), stub=0.4)


def _crossover(mb, n, t, base_xy, v_rail, z_c, rr, rp, pw=0.17, rr_ref=0.0241):
    """Placa de cruce: une el pasamanos (eje horizontal a lo largo de t) con un tubo de montaje vertical, con 2 pernos en U
    por lado. Devuelve la posición del eje del tubo."""
    n = Vector((n.x, n.y, 0.0)).normalized()
    t = Vector((t.x, t.y, 0.0)).normalized()
    up = Vector((0, 0, 1))
    b0 = Vector((base_xy[0], base_xy[1], z_c))
    vc = v_rail + rr_ref + 0.002 + 0.006
    pc = b0 + n * vc
    M = Matrix(((t.x, up.x, n.x, pc.x), (t.y, up.y, n.y, pc.y), (0, 1, 0, pc.z), (0, 0, 0, 1)))
    mb.box((-pw / 2, -pw / 2, -0.006), (pw / 2, pw / 2, 0.006), GALV, bevel=0.002, seg=2, m=M)
    vp = v_rail + rr_ref + 0.002 + 0.012 + 0.0005 + rp
    ux = max(rp + 0.016, 0.06)
    for su in (-1, 1):
        o = b0 + n * v_rail + t * (su * ux)
        Mu = Matrix(((n.x, t.x, 0, o.x), (n.y, t.y, 0, o.y), (0, 0, 1, o.z), (0, 0, 0, 1)))
        ubolt(mb, Mu, rr, d=0.010, reach=vc + 0.006 - v_rail, seg=12, bend_seg=7)
    for sz in (-1, 1):
        o = b0 + n * vp + up * (sz * 0.06)
        Mu = Matrix(((-n.x, 0, t.x, o.x), (-n.y, 0, t.y, o.y), (0, 1, 0, o.z), (0, 0, 0, 1)))
        ubolt(mb, Mu, rp, d=0.012, reach=rp + 0.0005 + 0.012, seg=12, bend_seg=7)
    return b0 + n * vp


def _mount_pipe(mb, p, z0, z1, rp):
    lathe(mb, [(rp, z0 + 0.004), (rp, z1 - 0.004)], seg=24, mat=GALV, M=_T(p.x, p.y, 0.0), caps=False)
    lathe(mb, [(0.0, z0 - 0.002), (rp * 0.7, z0 - 0.0015), (rp + 0.0025, z0 + 0.002), (rp + 0.0025, z0 + 0.03), (rp, z0 + 0.031)],
          seg=24, mat="plastic", M=_T(p.x, p.y, 0.0), caps=False)
    lathe(mb, [(rp, z1 - 0.031), (rp + 0.0025, z1 - 0.03), (rp + 0.0025, z1 - 0.004), (rp * 0.75, z1 + 0.006), (0.0, z1 + 0.009)],
          seg=24, mat="plastic", M=_T(p.x, p.y, 0.0), caps=False)


def build_platform(mb, G, z_f, v_out, cut, holes, knee_dz, pipes):
    """Plataforma triangular de esquinas recortadas alrededor del tramo recto. pipes: lista de (n, t, v_edge, u, rp, z0, z1).
    Devuelve las posiciones de los tubos de montaje."""
    rin = G.rin(z_f)
    R = G.R(z_f)
    tri = [tuple((ang2(LEG_ANG[i]) * 2 * v_out)[:2]) for i in range(3)]
    clip = 2 * v_out - cut
    P = tri
    for i in range(3):
        a = ang2(LEG_ANG[i])
        P = clip_poly(P, (a.x, a.y), clip)
    P = poly_ccw(P)
    v_in = rin + 0.075
    # --- rejilla de sectores (2 tableros por cara, divididos sobre la viga media)
    for k in range(3):
        n = ang2(FACE_ANG[k])
        t = Vector((-n.y, n.x, 0))
        m1, m2 = ang2(FACE_ANG[k] - 30.0), ang2(FACE_ANG[k] + 30.0)
        q = clip_poly(P, (-n.x, -n.y), -v_in)
        q = clip_poly(q, (-m1.x, -m1.y), -0.006)
        q = clip_poly(q, (-m2.x, -m2.y), -0.006)
        for sg in (-1, 1):
            h = clip_poly(q, (sg * t.x, sg * t.y), -0.005)
            grating(mb, h, z_f, (t.x, t.y))
    # --- rejilla interior con escotilla y pasos
    ri = rin - 0.065
    tri_i = [tuple((ang2(LEG_ANG[i]) * 2 * ri)[:2]) for i in range(3)]
    for i in range(3):
        a = ang2(LEG_ANG[i])
        tri_i = clip_poly(tri_i, (a.x, a.y), 2 * ri - 0.07)
    tri_i = poly_ccw(tri_i)
    for pc in split_holes(tri_i, holes):
        grating(mb, pc, z_f, (1, 0))
    # bandas de los huecos: ángulos de apoyo bajo los bordes de corte (x = const)
    for (x0, x1, y0, y1) in holes:
        for xx in (x0 - 0.03, x1 + 0.03):
            iv = line_interval(offset_poly(tri_i, -0.056), (xx, 0.0), (0.0, 1.0))
            if iv:
                M = Matrix(((0, 1, 0, xx), (1, 0, 0, 0), (0, 0, 1, z_f), (0, 0, 0, 1)))
                prism(mb, [(-0.025 + a_, b_) for (a_, b_) in ANG50], M, iv[0], iv[1], GALV)
    # --- estructura: perímetro de canal C100, vigas I en esquinas y al centro de cada cara, ángulo interior
    prof = [(0.0, -0.13), (0.0, -0.03), (-0.05, -0.03), (-0.05, -0.038), (-0.006, -0.038), (-0.006, -0.122), (-0.05, -0.122),
            (-0.05, -0.13)]
    mb.sweep(list(reversed(prof)), [(x, y, z_f) for (x, y) in P], mat=GALV, closed_profile=True, closed_path=True, normal=(0, 0, 1))
    for i in range(3):
        a = ang2(LEG_ANG[i])
        r0 = R + G.r_leg(z_f) + 0.012
        M = frame_xz(a, (0, 0, 1), a * r0 + Vector((0, 0, z_f)))
        prism(mb, IBEAM, M, 0.0, clip - 0.051 - r0, GALV)
        prism(mb, WEB, M, clip - 0.0515 - r0, clip - 0.0055 - r0, GALV)
        _leg_ring(mb, G, i, z_f - 0.135, z_f - 0.025, Vector((-a.y, a.x, 0)))
        # tornapunta inferior a la pata
        zk_ = z_f - knee_dz
        _leg_ring(mb, G, i, zk_ - 0.05, zk_ + 0.05, Vector((-a.y, a.x, 0)))
        rk = R + 0.65 * (clip - R)
        pa = a * (R + G.r_leg(zk_) + 0.012) + Vector((0, 0, zk_))
        pb = a * rk + Vector((0, 0, z_f - 0.13))
        dk = (pb - pa).normalized()
        mb.tube([pa + dk * 0.035, pb - dk * 0.02], 0.0302, seg=16, mat=GALV)
        mb.plate([(-0.05, -0.04), (0.05, -0.04), (0.05, 0.04), (-0.05, 0.04)], 0.01, GALV,
                 m=frame((0, 0, 1), a, pb - Vector((0, 0, 0.01))))
        mb.plate([(0.0, -0.03), (0.07, -0.03), (0.07, 0.03), (0.0, 0.03)], 0.01, GALV,
                 m=frame(Vector((-a.y, a.x, 0)), a, pa - a * 0.004) @ _T(0, 0, -0.005))
        # cartela interior: une el ángulo interior con el aro
        ai = a * (2 * ri - 0.07)
        mb.box((-0.005, 0.0, -0.08), (0.005, (R - G.r_leg(z_f) - 0.012) - (2 * ri - 0.07) + 0.004, -0.0355), GALV, bevel=0.0,
               m=_T(ai.x, ai.y, z_f) @ Matrix(((-a.y, a.x, 0, 0), (a.x, a.y, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))))
    for k in range(3):
        n = ang2(FACE_ANG[k])
        t = Vector((-n.y, n.x, 0))
        M = frame_xz(n, (0, 0, 1), n * v_in + Vector((0, 0, z_f)))
        prism(mb, IBEAM, M, 0.0505, v_out - 0.051 - v_in, GALV)
        prism(mb, WEB, M, v_out - 0.0515 - v_in, v_out - 0.0055 - v_in, GALV)
        # ángulo bajo el borde interior del sector, cortado contra las vigas de esquina
        Ms = Matrix(((t.x, n.x, 0, n.x * v_in), (t.y, n.y, 0, n.y * v_in), (0, 0, 1, z_f), (0, 0, 0, 1)))
        L = SQ3 * v_in
        m1, m2 = ang2(FACE_ANG[k] - 30.0), ang2(FACE_ANG[k] + 30.0)
        prism(mb, ANG50, Ms, -L, L, GALV, planes=((m2 * 0.052, m2), (m1 * 0.052, m1)))
        # ángulo interior (apoyo de la rejilla interior)
        Mi = Matrix(((t.x, -n.x, 0, n.x * ri), (t.y, -n.y, 0, n.y * ri), (0, 0, 1, z_f), (0, 0, 0, 1)))
        Li = SQ3 * ri - 0.08
        prism(mb, ANG50, Mi, -Li, Li, GALV)
    # --- rodapié y barandal
    ring_extrude(mb, offset_poly(P, 0.0075), offset_poly(P, 0.0015), z_f - 0.035, z_f + 0.10, GALV)
    rail = offset_poly(P, 0.033)
    for (zz, rr) in ((z_f + 1.1, 0.0241), (z_f + 0.55, 0.0211)):
        closed_tube(mb, round_loop(rail, 0.12, zz, 6), rr, seg=16)
    posts = []
    kq = len(P)
    for i in range(kq):
        a, b = Vector(P[i]), Vector(P[(i + 1) % kq])
        L = (b - a).length
        ns = max(1, int(math.ceil(L / 1.45)))
        for j in range(ns):
            posts.append((a.lerp(b, j / ns), (b - a).normalized(), j == 0))
    for (p, tdir, corner) in posts:
        nout = Vector((tdir.y, -tdir.x))
        if corner:
            continue
        pp = p + nout * 0.033
        mb.tube([(pp.x, pp.y, z_f - 0.125), (pp.x, pp.y, z_f + 1.1)], 0.0241, seg=16, mat=GALV)
        q = p + nout * 0.0005
        M = Matrix(((tdir.x, 0, nout.x, q.x), (tdir.y, 0, nout.y, q.y), (0, 1, 0, z_f - 0.125), (0, 0, 0, 1)))
        mb.plate([(-0.045, 0.0), (0.045, 0.0), (0.045, 0.085), (-0.045, 0.085)], 0.0085, GALV, m=M)
        for (dz, su) in ((0.025, 1), (0.06, -1)):
            bolt_at(mb, Vector((q.x, q.y, z_f - 0.125 + dz)) - Vector((nout.x, nout.y, 0)) * 0.0065 + Vector((tdir.x, tdir.y, 0)) * (0.036 * su),
                    Vector((nout.x, nout.y, 0)), 0.010, 0.015, (0, 0, 1), stub=0.3)
    # postes de esquina (en los vértices del recorte, sobre la bisectriz)
    for i in range(kq):
        a, b, c = Vector(P[i - 1]), Vector(P[i]), Vector(P[(i + 1) % kq])
        n0 = Vector(((b - a).y, -(b - a).x)).normalized()
        n1 = Vector(((c - b).y, -(c - b).x)).normalized()
        m = (n0 + n1).normalized()
        s = 0.033 / max(m.dot(n0), 0.3)
        pp = b + m * s
        mb.tube([(pp.x, pp.y, z_f - 0.125), (pp.x, pp.y, z_f + 1.1)], 0.0241, seg=16, mat=GALV)
        q = b + m * 0.0005
        tdir = Vector((-m.y, m.x))
        M = Matrix(((tdir.x, 0, m.x, q.x), (tdir.y, 0, m.y, q.y), (0, 1, 0, z_f - 0.125), (0, 0, 0, 1)))
        mb.plate([(-0.018, 0.0), (0.018, 0.0), (0.018, 0.085), (-0.018, 0.085)], 0.0085 / max(m.dot(n0), 0.3) + 0.004, GALV, m=M)
    # --- tubos de montaje con placas de cruce al pasamanos y a la rodillera
    out = []
    for (n, t, v_edge, u, rp, z0, z1) in pipes:
        base = n * 0.0 + t * u
        v_rail = v_edge + 0.033
        pa = None
        for (zz, rr) in ((z_f + 1.1, 0.0241), (z_f + 0.55, 0.0211)):
            pa = _crossover(mb, n, t, (base.x, base.y), v_rail, zz, rr, rp, pw=0.17 if rp < 0.05 else 0.2)
        _mount_pipe(mb, pa, z0, z1, rp)
        out.append(dict(pos=(round(pa.x, 4), round(pa.y, 4)), z0=round(z0, 3), z1=round(z1, 3), od=round(2 * rp, 4),
                        facing=(round(n.x, 4), round(n.y, 4), 0.0)))
    return out


# ================================================================================================== remate superior
def build_top(mb, G):
    """Mástil central (tubo Ø114 sobre 3 brazos PTR a las patas), pararrayos de 2 m, ménsula de baliza, conduit de la baliza
    y bajada de pararrayos de cobre por la pata 2 hasta la oreja de tierra."""
    za = G.h - 0.08
    rm = 0.057
    for i in range(3):
        a = ang2(LEG_ANG[i])
        R = G.R(za)
        rl = G.r_leg(za)
        _leg_ring(mb, G, i, za - 0.06, za + 0.06, Vector((-a.y, a.x, 0)))
        M = frame_xz(a, (0, 0, 1), Vector((0, 0, za)))
        prism(mb, rr_pts2(0.06, 0.06, 0.006, 3), M, rm - 0.004, R - rl - 0.0118, GALV)
        mb.plate([(rm - 0.002, -0.0305), (rm + 0.10, -0.0305), (rm - 0.002, -0.11)], 0.008, GALV,
                 m=M @ Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1))) @ _T(0, 0, -0.004))
    z0m, z1m = G.h - 0.45, G.h + 1.0
    lathe(mb, [(rm, z0m), (rm, z1m)], seg=24, mat=GALV, caps=True)
    weld_ring(mb, _T(0, 0, z1m), rm, w=0.006, seg=24)
    lathe(mb, [(0.098, z1m), (0.1, z1m + 0.002), (0.1, z1m + 0.014), (0.098, z1m + 0.016)], seg=32, mat=GALV)
    for k in range(4):
        u = ang2(45.0 + 90.0 * k)
        _rib(mb, Vector((0, 0, z1m)), u, rm - 0.003, 0.094, -0.09, -0.004, 0.008)
    zr = z1m + 0.016
    lathe(mb, [(0.032, zr - 0.001), (0.032, zr + 0.03), (0.022, zr + 0.045), (0.016, zr + 0.06)], seg=24, mat=GALV)
    for k in range(3):
        a = 2 * PI * k / 3
        mb.join(nut_pf(0.010, stub=0.4), _T(0.075 * math.cos(a), 0.075 * math.sin(a), zr))
    lathe(mb, [(0.0115, zr + 0.055), (0.0095, zr + 1.0), (0.0075, zr + 1.92), (0.0045, zr + 1.97), (0.0, zr + 1.985)], seg=16,
          mat="copper", caps=True)
    # ménsula de la baliza de obstrucción
    dL = ang2(-30.0)
    sL = Vector((0, 0, 1)).cross(dL)
    zb = z1m - 0.1
    M = frame_xz(dL, (0, 0, 1), Vector((0, 0, zb)))
    prism(mb, rr_pts2(0.05, 0.05, 0.005, 3), M, rm - 0.004, 0.42, GALV)
    mb.box((0.418, -0.026, -0.026), (0.424, 0.026, 0.026), GALV, bevel=0.0015, seg=1, m=M)
    pl = dL * 0.36 + Vector((0, 0, zb + 0.025))
    lathe(mb, [(0.083, pl.z - 0.0003), (0.085, pl.z + 0.002), (0.085, pl.z + 0.01), (0.083, pl.z + 0.012)], seg=32, mat=GALV,
          M=_T(pl.x, pl.y, 0.0))
    for k in range(4):
        a = PI / 4 + PI / 2 * k
        mb.join(nut_pf(0.008, stub=0.6), _T(pl.x + 0.062 * math.cos(a), pl.y + 0.062 * math.sin(a), pl.z + 0.012))
    kb0 = Vector((0, 0, zb - 0.28)) + dL * (rm - 0.003)
    kb1 = Vector((0, 0, zb - 0.025)) + dL * 0.26
    _rtube(mb, kb0, kb1, 0.04, 0.008, sL, r=0.0025, n=2)
    G.light = (round(pl.x, 4), round(pl.y, 4), round(pl.z + 0.012, 4))
    # caja de conexión bajo la ménsula y conduit desde la caja de distribución
    jb = dL * 0.25 + Vector((0, 0, zb - 0.025))
    mb.box((jb.x - 0.04, jb.y - 0.04, jb.z - 0.085), (jb.x + 0.04, jb.y + 0.04, jb.z - 0.0005), "aluminium", bevel=0.004, seg=2)
    c0 = G.conduit0
    rc = 0.0105
    am = math.radians(60.0)
    mside = Vector((math.cos(am), math.sin(am), 0)) * (rm + rc + 0.002)
    zt = G.z_top
    path = [c0, Vector((c0.x, c0.y, G.h - 0.62)), Vector((mside.x, mside.y, G.h - 0.62)), Vector((mside.x, mside.y, zb - 0.06))]
    for k in range(1, 6):
        a = am - math.radians(90.0) * k / 5
        path.append(Vector((math.cos(a) * (rm + rc + 0.002), math.sin(a) * (rm + rc + 0.002), zb - 0.06)))
    path.append(jb + Vector((0, 0, -0.06)) - dL * 0.04)
    mb.tube(fillet([tuple(p) for p in path], 0.08, 6), rc, seg=12, mat="steel")
    lathe(mb, [(rc + 0.0015, zt + 0.0055), (rc + 0.006, zt + 0.006), (rc + 0.006, zt + 0.03), (rc + 0.0015, zt + 0.035)], seg=16,
          mat="rubber", M=_T(c0.x, c0.y, 0.0))
    mb.box((c0.x - 0.045, c0.y - 0.045, zt - 0.0003), (c0.x + 0.045, c0.y + 0.045, zt + 0.006), GALV, bevel=0.0015, seg=1)
    for (dx, dy) in ((-0.035, -0.035), (0.035, -0.035), (-0.035, 0.035), (0.035, 0.035)):
        mb.join(nut_pf(0.006, mat="steel", stub=0.0, wseg=12), _T(c0.x + dx, c0.y + dy, zt + 0.006))
    for zz in (G.h + 0.25, G.h + 0.7):
        mb.box((mside.x - 0.016, mside.y - 0.016, zz - 0.012), (mside.x + 0.016, mside.y + 0.016, zz + 0.012), "steel", bevel=0.003,
               seg=1, m=None)
    # bajada de pararrayos (cobre desnudo Ø11) por la pata 2, engrapada cada 1,5 m, hasta la oreja de tierra
    a2 = LEG_ANG[2]
    ad = math.radians(a2 + 45.0)
    dirc = Vector((math.cos(ad), math.sin(ad), 0))
    rcu = 0.0055

    def on_leg(z, extra=0.0, ang=None):
        d = dirc if ang is None else ang2(ang)
        return G.P(2, z) + d * (G.r_leg(z) + 0.024 + extra)
    a120 = ang2(120.0)
    Z = Vector((0, 0, 1))
    pts = [a120 * 0.0385 + Z * (zr + 0.02), a120 * 0.118 + Z * (zr + 0.014), a120 * 0.112 + Z * (z1m - 0.1),
           a120 * (rm + 0.0065) + Z * (z1m - 0.22), a120 * (rm + 0.0065) + Z * (za + 0.07)]
    a150 = ang2(150.0)
    rl2 = G.r_leg(za)
    pts.append(a150 * 0.2 + Z * (za + 0.03 + rcu + 0.0015))
    pts.append(a150 * (G.R(za) - rl2 - 0.11) + Z * (za + 0.03 + rcu + 0.0015))
    cL = G.P(2, za)
    for ang in (180.0, 120.0, 60.0):
        q = Vector((cL.x, cL.y, 0)) + ang2(a2 + ang) * (rl2 + 0.03)
        pts.append(Vector((q.x, q.y, G.h + 0.004)))
    pts.append(on_leg(za - 0.2, 0.0, a2 + 45.0))
    flz = [zj for zj in G.joints]
    z = za - 0.6
    while z > 1.1:
        near = [zj for zj in flz if abs(z - zj) < 0.4]
        if not near:
            pts.append(on_leg(z))
        z -= 0.75
    # jogs alrededor de las bridas
    full = []
    for p in pts:
        full.append(p)
    pts2 = []
    for i, p in enumerate(full):
        pts2.append(p)
        if i + 1 < len(full):
            q = full[i + 1]
            for zj in flz:
                if q.z < zj < p.z:
                    rf = G.od_leg[G.joints.index(zj)] / 2 + 0.088
                    for dz in (0.2, 0.13, -0.13, -0.2):
                        ext = (rf + 0.016) - (G.r_leg(zj + dz) + 0.024) if abs(dz) < 0.15 else 0.0
                        pts2.append(on_leg(zj + dz, ext))
    tabz = 0.915
    rl0 = G.od_leg[0] / 2
    pt_tab = G.P(2, tabz) + ang2(a2 + 12.0) * (rl0 + 0.05)
    pts2 += [on_leg(1.25), on_leg(1.0, 0.0, a2 + 25.0), Vector((pt_tab.x, pt_tab.y, tabz + rcu - 0.001))]
    path = fillet([tuple(p) for p in pts2], 0.05, 4)
    mb.tube(path, rcu, seg=12, mat="copper")
    for p in pts2[7:-3:2]:
        c = G.P(2, p.z)
        u = (Vector((p.x, p.y, 0)) - Vector((c.x, c.y, 0))).normalized()
        sd = Vector((0, 0, 1)).cross(u)
        rlz = G.r_leg(p.z)
        if (Vector((p.x, p.y, 0)) - Vector((c.x, c.y, 0))).length > rlz + 0.04:
            continue
        Mc = Matrix(((u.x, sd.x, 0, c.x), (u.y, sd.y, 0, c.y), (0, 0, 1, p.z), (0, 0, 0, 1)))
        mb.box((rlz - 0.003, -0.013, -0.014), (rlz + 0.024 + rcu + 0.004, 0.013, 0.014), "copper", bevel=0.003, seg=1, m=Mc)


def build_sign(mb, G):
    """Letrero de advertencia en la pata 0 (inglés), con abrazaderas de banda."""
    from kit.clinic_servicios import text3d
    z0, z1 = 0.97, 1.21
    c = G.P(0, (z0 + z1) / 2)
    rl = G.od_leg[0] / 2
    u = ang2(LEG_ANG[0])
    for zz in (z0 + 0.04, z1 - 0.04):
        cc = G.P(0, zz)
        lathe(mb, [(rl + 0.0006, zz - 0.012), (rl + 0.0026, zz - 0.012), (rl + 0.0026, zz + 0.012), (rl + 0.0006, zz + 0.012)],
              seg=32, mat="steel", M=_T(cc.x, cc.y, 0.0), closed=True, caps=False)
    d = rl + 0.012
    side = Vector((0, 0, 1)).cross(u)
    M = Matrix(((side.x, 0, u.x, c.x + u.x * d), (side.y, 0, u.y, c.y + u.y * d), (0, 1, 0, c.z), (0, 0, 0, 1)))
    w, h = 0.30, 0.24
    mb.box((-w / 2, -h / 2, -0.0015), (w / 2, h / 2, 0.0015), "sign_white", bevel=0.001, seg=1, m=M)
    mb.box((-w / 2 + 0.008, h / 2 - 0.07, 0.0015), (w / 2 - 0.008, h / 2 - 0.008, 0.0025), "sign_red", bevel=0.0, m=M)
    mb.box((-0.03, -h / 2 + 0.01, -0.012), (0.03, h / 2 - 0.01, -0.0015), "steel", bevel=0.001, seg=1, m=M)
    text3d(mb, "DANGER", 0.042, 0.0012, "sign_white", M @ _T(0, h / 2 - 0.058, 0.0024), res=2, bold=True)
    for k, line in enumerate(("RF RADIATION", "NO CLIMBING", "AUTHORIZED PERSONNEL ONLY")):
        text3d(mb, line, 0.022 if k < 2 else 0.0155, 0.001, "cable", M @ _T(0, h / 2 - 0.105 - 0.04 * k, 0.0014), res=2,
               bold=k < 2)
    for sx in (-1, 1):
        mb.join(nut_pf(0.006, mat="steel", stub=0.0, wseg=12), M @ _T(sx * 0.12, 0.0, 0.0015))


# ================================================================================================== ensamble y montajes
def _platform_specs(G):
    """Datos de las dos plataformas y sus tubos de montaje (los mismos números para construir y para reportar)."""
    top = dict(z_f=G.z_top, v_out=1.5, cut=0.45, knee=G.z_top - (G.nodes[-3] + G.nodes[-2]) / 2)
    pipes_t = []
    for k in range(3):
        n = ang2(FACE_ANG[k])
        t = Vector((-n.y, n.x, 0))
        for u in (-1.4, 0.0, 1.4):
            pipes_t.append((n, t, top["v_out"], u, 0.0365, G.z_top - 0.95, G.z_top + 2.55))
    top["pipes"] = pipes_t
    top["holes"] = [(G.x_lad - 0.30, G.x_lad + 0.30, G.y_lad - 0.60, G.y_lad + 0.045), (G.x_cab - 0.03, G.x_cab + 0.03, 0.1255, 0.1855)]
    mw = dict(z_f=G.z_mw, v_out=1.05, cut=0.35, knee=G.z_mw - (G.nodes[-7] + G.nodes[-6]) / 2)
    clip_m = 2 * mw["v_out"] - mw["cut"]
    pipes_m = []
    for i in (1, 2):
        a = ang2(LEG_ANG[i])
        t = Vector((-a.y, a.x, 0))
        pipes_m.append((a, t, clip_m, 0.0, 0.0381, G.z_mw - 0.6, G.z_mw + 1.4))      # Ø76,2: el de las monturas de plato del kit
    mw["pipes"] = pipes_m
    mw["holes"] = [(G.x_lad - 0.30, G.x_lad + 0.30, G.y_lad - 0.60, G.y_lad + 0.045),
                   (G.x_cab - 0.31, G.x_cab + 0.31, G.y_lad - 0.13, G.y_lad + 0.045)]
    return top, mw


def _pipe_axis(n, t, v_edge, u, rp):
    vp = v_edge + 0.033 + 0.0241 + 0.002 + 0.012 + 0.0005 + rp
    p = n * vp + t * u
    return Vector((p.x, p.y, 0.0))


def _mw_boxes(mb, G, specs):
    """Caja de remate (supresor/tierra) del cable de cada plato, abrazada al tubo de montaje por su costado."""
    for (n, t, v_edge, u, rp, z0, z1) in specs["pipes"]:
        pa = _pipe_axis(n, t, v_edge, u, rp)
        sg = 1 if pa.x > 0 else -1
        am = math.atan2(pa.y, pa.x)
        tv = Vector((-math.sin(am), math.cos(am), 0.0)) * sg
        nn = Vector((math.cos(am), math.sin(am), 0.0))
        zb = G.z_mw + 0.15
        c = pa + tv * (rp + 0.003 + 0.05)
        M = Matrix(((nn.x, tv.x, 0, c.x), (nn.y, tv.y, 0, c.y), (0, 0, 1, 0), (0, 0, 0, 1)))
        mb.box((-0.06, -0.05, zb), (0.06, 0.05, zb + 0.24), "aluminium", bevel=0.006, seg=2, m=M)
        lathe(mb, [(0.0155, zb + 0.002), (0.0155, zb - 0.014), (0.012, zb - 0.02), (0.0105, zb - 0.032)], seg=16, mat="plastic",
              M=_T(pa.x + tv.x * 0.075, pa.y + tv.y * 0.075, 0.0))
        for zz in (zb + 0.05, zb + 0.19):
            lathe(mb, [(rp + 0.0005, zz - 0.009), (rp + 0.0025, zz - 0.009), (rp + 0.0025, zz + 0.009), (rp + 0.0005, zz + 0.009)],
                  seg=32, mat="steel", M=_T(pa.x, pa.y, 0.0), closed=True, caps=False)


def lattice_tower(h=42.0, base_w=5.0, top_w=1.6, seed=0):
    """Torre autosoportada de 3 patas tubulares (ver docstring del módulo). Origen en el centroide al nivel del suelo."""
    G = Geo(h, base_w, top_w)
    mb = MB()
    build_base(mb, G, seed)
    build_legs(mb, G)
    build_step_bolts(mb, G)
    build_bracing(mb, G)
    build_supports(mb, G)
    build_climb_ladder(mb, G)
    build_cable_ladder(mb, G)
    build_cables(mb, G)
    top, mw = _platform_specs(G)
    for sp in (mw, top):
        build_platform(mb, G, sp["z_f"], sp["v_out"], sp["cut"], sp["holes"], sp["knee"], sp["pipes"])
    _mw_boxes(mb, G, mw)
    build_top(mb, G)
    build_sign(mb, G)
    mb.meta = tower_mounts(h, base_w, top_w)
    return mb


def tower_mounts(h=42.0, base_w=5.0, top_w=1.6):
    """Puntos de montaje para el ensamblador del sitio (metros, mundo de la torre; facing = normal horizontal hacia afuera).
    sector: 3 sectores × 3 tubos Ø73 (x, y, z0..z1) con altura sugerida del centro de la antena (antenna_z).
    rru: un RRU por tubo, colgado del mismo tubo bajo el piso (centro rru_z), mirando hacia afuera.
    dish: 2 tubos Ø76 en las esquinas de la plataforma de microondas (centro del plato dish_z).
    light: base de la baliza (cara superior de la placa). cable_exit: centro del haz de cables donde inicia el puente de hielo."""
    G = Geo(h, base_w, top_w)
    top, mw = _platform_specs(G)
    out = dict(sector=[], rru=[], dish=[], light=[], cable_exit=[])
    for j, (n, t, v_edge, u, rp, z0, z1) in enumerate(top["pipes"]):
        pa = _pipe_axis(n, t, v_edge, u, rp)
        az = FACE_ANG[j // 3]
        base = dict(sector=j // 3, azimuth_deg=az, pipe_pos=(round(pa.x, 4), round(pa.y, 4)), pipe_z=(round(z0, 3), round(z1, 3)),
                    pipe_od=round(2 * rp, 4), pipe_len=round(z1 - z0, 3), facing=(round(n.x, 4), round(n.y, 4), 0.0))
        out["sector"].append(dict(base, antenna_z=round(G.z_top + 1.30, 3),
                                  pos=(round(pa.x + n.x * rp, 4), round(pa.y + n.y * rp, 4), round(G.z_top + 1.30, 3))))
        out["rru"].append(dict(base, rru_z=round(G.z_top - 0.45, 3),
                               pos=(round(pa.x + n.x * rp, 4), round(pa.y + n.y * rp, 4), round(G.z_top - 0.45, 3))))
    for (n, t, v_edge, u, rp, z0, z1) in mw["pipes"]:
        pa = _pipe_axis(n, t, v_edge, u, rp)
        out["dish"].append(dict(pipe_pos=(round(pa.x, 4), round(pa.y, 4)), pipe_z=(round(z0, 3), round(z1, 3)), pipe_od=round(2 * rp, 4),
                                pipe_len=round(z1 - z0, 3), facing=(round(n.x, 4), round(n.y, 4), 0.0), dish_z=round(G.z_mw + 0.75, 3),
                                pos=(round(pa.x + n.x * rp, 4), round(pa.y + n.y * rp, 4), round(G.z_mw + 0.75, 3))))
    zb = G.h + 1.0 - 0.1
    pl = ang2(-30.0) * 0.36
    out["light"].append(dict(pos=(round(pl.x, 4), round(pl.y, 4), round(zb + 0.025 + 0.012, 4)), up=(0.0, 0.0, 1.0),
                             plate_d=0.17, bolt_circle=0.124))
    ye = G.rin(G.z_exit) + 0.30
    out["cable_exit"].append(dict(pos=(round(G.x_cab, 4), round(ye, 4), round(G.z_exit - 0.0235, 4)), dir=(0.0, 1.0, 0.0),
                                  bundle_w=0.40, bundle_h=0.075, tray_top_z=round(G.z_exit - 0.047 - 0.013 - 0.0225 + 0.0105, 4),
                                  n_cables=18, n_black=16, n_yellow_fiber=2))
    return out

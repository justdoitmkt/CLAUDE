"""kit/fortif_equipo.py — equipo de sitio de la base militar (MIL_1_almacen / MIL_2_avanzada) a calidad AAA (regla R-AAA,
segunda pasada): bidón OTAN de 20 L, grupo electrógeno táctico de 10 kW, pluma de acceso, reflector en trípode y torre de
iluminación sobre remolque. Reemplaza a las funciones del mismo nombre de kit/fortif.py (que no se toca) con las MISMAS
firmas, origen, orientación y huella.

Convenciones (todas las funciones devuelven un MB de kit.clinic, que bisela box() por omisión):
- metros, Z arriba, origen en el piso (z = 0);
- drop_arm_barrier corre a lo largo de +X desde el poste pivote en x = 0; frente hacia -Y;
- jerry_can, tactical_generator, floodlight_tripod, light_tower: centradas en planta en el origen, frente hacia -Y
  (light_tower: origen al centro del eje, lanza hacia -X).
Equipo de una base EN SERVICIO: limpio, mantenido, poco desgaste. Sin grafiti ni placas de pandilla. Textos en inglés con
kit.fonts (esténcil pintado: "stencil"; marcas chicas: "stencil2"; letreros y placas: "sign").
Suavizado: el kit marca dura toda arista de más de 30°. Cilindros visibles >= 24 lados; tubos/cables >= 14; alambres y
cables de <= 6 mm de diámetro: 12 lados dentro de `mb.soft()`. Todo canto rígido lleva radio o bisel real.
Medidas verificadas contra fuentes reales: ver el bloque de cada función (y el reporte de la segunda pasada en ESTADO.md).
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
import numpy as np
from mathutils import Matrix, Vector

from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rbox, rng, rr_profile, rtube  # noqa: F401
from kit.clinic_equipo import loft_rings, revolve, sweep_frame  # noqa: F401
from kit.clinic_servicios import holed, lathe, rpoly_pts, rr_pts, skin, slab  # noqa: F401
from kit.fonts import text_font as _text_font
from kit.fortif import _v, tube_path  # utilidades genéricas (sin cambios)

SEG = 24          # lados de todo cilindro visible
SEG_T = 14        # lados de tubos delgados / cables / cuerdas
SEG_W = 12        # alambres de <= 6 mm (dentro de mb.soft())


# ====================================================================================================== utilidades
class MBX(MB):
    """MB de kit.clinic que arma cada caja biselada en una malla temporal y la une: bmesh.ops.bevel recorre TODA la malla en
    cada llamada, y con cientos de cajas sobre una pieza de 300 k triángulos el armado tardaba 10 s de más."""

    def box(self, mn, mx, mat="concrete", bevel=None, seg=2, m=None):
        t = MB()
        MB.box(t, mn, mx, mat, bevel=bevel, seg=seg, m=m)
        self.join(t)
        t.bm.free()


def text_font(mb, *a, **k):
    """kit.fonts.text_font armado en una malla temporal (sus operadores bmesh también recorren toda la malla)."""
    t = MB()
    w = _text_font(t, *a, **k)
    mb.join(t)
    t.bm.free()
    return w


def ngon(mb, verts, mat, smooth=True):
    """Cara plana de n lados (sin triangular aquí: el n-gono plano no deja astillas con vértices colineales)."""
    return mb.face(verts, mat)


def face_M(o, n, up=(0, 0, 1)):
    """Matriz de una cara: origen o, +Z local = normal n (hacia afuera), +Y local lo más cerca de `up`."""
    Z = _v(n).normalized()
    U = _v(up)
    if abs(U.dot(Z)) > 0.99:
        U = Vector((0, 1, 0)) if abs(Z.y) < 0.9 else Vector((1, 0, 0))
    Y = (U - Z * U.dot(Z)).normalized()
    X = Y.cross(Z)
    o = _v(o)
    return Matrix(((X.x, Y.x, Z.x, o.x), (X.y, Y.y, Z.y, o.y), (X.z, Y.z, Z.z, o.z), (0, 0, 0, 1)))


def axis_M(p0, p1, up=(0, 0, 1)):
    """Matriz con +Z local de p0 hacia p1 (origen p0) y +Y lo más cerca de `up`. Devuelve (M, largo)."""
    p0, p1 = _v(p0), _v(p1)
    return face_M(p0, p1 - p0, up), (p1 - p0).length


def torus(mb, M, R, r, mat="steel", n=24, seg=12, a0=0.0, a1=2 * PI, rmod=None):
    """Toro (o arco) en el plano XY local: argollas, asas, ojos de izaje. rmod(t) -> factor del radio de sección."""
    full = abs(a1 - a0 - 2 * PI) < 1e-6
    cnt = n if full else n + 1
    rings = []
    for i in range(cnt):
        a = a0 + (a1 - a0) * i / n
        rr = r * (rmod(i / n) if rmod else 1.0)
        c = Vector((R * math.cos(a), R * math.sin(a), 0.0))
        rd = Vector((math.cos(a), math.sin(a), 0.0))
        rings.append([mb.bm.verts.new(M @ (c + rd * (rr * math.cos(2 * PI * k / seg)) + Vector((0, 0, rr * math.sin(2 * PI * k / seg)))))
                      for k in range(seg)])
    for i in range(cnt if full else cnt - 1):
        A, B = rings[i], rings[(i + 1) % cnt]
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([A[k], B[k], B[kk], A[kk]], mat)
    if not full:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)


def hollow_rect(mb, M, w, h, t, L, mat="steel", r=0.004, n=3):
    """Tubo rectangular HUECO (boca visible: bolsas de montacargas) a lo largo de X local, de 0 a L, sección w (Y) × h (Z)."""
    po = rr_profile(w, h, r, n=n)
    pi_ = rr_profile(w - 2 * t, h - 2 * t, max(r - t, 0.0008), n=n)
    O = [[mb.bm.verts.new(M @ Vector((x, a, b))) for (a, b) in po] for x in (0.0, L)]
    I_ = [[mb.bm.verts.new(M @ Vector((x, a, b))) for (a, b) in pi_] for x in (0.0, L)]
    k = len(po)
    for j in range(k):
        jj = (j + 1) % k
        mb.face([O[0][j], O[0][jj], O[1][jj], O[1][j]], mat)
        mb.face([I_[0][jj], I_[0][j], I_[1][j], I_[1][jj]], mat)
        mb.face([O[0][jj], O[0][j], I_[0][j], I_[0][jj]], mat)
        mb.face([O[1][j], O[1][jj], I_[1][jj], I_[1][j]], mat)


def weld_ring(mb, M, r, w=0.003, seg=SEG, mat="steel", ripple=0.0, sink=0.0004):
    """Cordón de soldadura de filete alrededor de un tubo / perno de radio r que nace del plano z = 0 local (eje +Z): sección
    de cuarto de elipse convexa (pie de w sobre la placa, garganta 0,9 w sobre el tubo); ripple = rizado del cordón."""
    prof = [(r - sink, -sink)]
    for j in range(7):
        th = PI / 2 * j / 6
        prof.append((r + w * math.cos(th), max(w * 0.9 * math.sin(th), 0.0) - sink * (1 - math.sin(th))))
    prof.append((r - sink, w * 0.9))
    rm = (lambda a: 1.0 + ripple * math.cos(a * 2 * PI * r / 0.0035) ** 2) if ripple else None
    revolve(mb, list(reversed(prof)), mat, seg=max(seg, int(2 * PI * r / 0.0025)) if ripple else seg, M=M, closed=True, rmod=rm)


def weld_bead(mb, pts, r=0.0025, mat="steel", pitch=0.0035, ripple=0.18, seg=10):
    """Cordón de soldadura a lo largo de una polilínea: tubo con rizado de paso `pitch` (escamas del cordón)."""
    P = [_v(p) for p in pts]
    out = [P[0]]
    for i in range(1, len(P)):
        L = (P[i] - P[i - 1]).length
        n = max(1, int(math.ceil(L / (pitch / 3))))
        for k in range(1, n + 1):
            out.append(P[i - 1].lerp(P[i], k / n))
    s, radii = 0.0, []
    for i, q in enumerate(out):
        if i:
            s += (q - out[i - 1]).length
        radii.append(r * (1.0 - ripple * (0.5 - 0.5 * math.cos(2 * PI * s / pitch))))
    radii[0] = radii[-1] = r * 0.55
    with mb.soft():
        mb.tube([tuple(p) for p in out], r, seg=seg, mat=mat, radii=radii)


def bolt(mb, M, d=0.012, L=0.03, mat="galvanized", washer=True, nut=False):
    """Perno de cabeza hexagonal (o espárrago con tuerca si nut=True) sobre el plano z = 0 local, eje +Z: arandela plana,
    cabeza / tuerca con chaflán de 30° y punta roscada con chaflán (rosca indicada con anillos)."""
    s = d * 1.5                                            # entre caras (ISO 4032: M12 -> 18 mm)
    R = s / 2 / math.cos(PI / 6)
    z = -0.0003
    if washer:
        lathe(mb, [(d * 0.55, z), (d * 1.05, z), (d * 1.08, z + d * 0.04), (d * 1.08, z + d * 0.13), (d * 1.05, z + d * 0.16),
                   (d * 0.55, z + d * 0.16)], seg=SEG, mat=mat, M=M, closed=True)
        z += d * 0.16
    h = d * (0.8 if nut else 0.65)
    lathe(mb, [(0.0, z), (R * 0.87, z), (R, z + h * 0.16), (R, z + h * 0.84), (R * 0.87, z + h), (0.0, z + h)] if not nut else
          [(d * 0.5, z), (R * 0.87, z), (R, z + h * 0.16), (R, z + h * 0.84), (R * 0.87, z + h), (d * 0.5, z + h)], seg=6,
          mat=mat, M=M, phase=PI / 6, closed=nut)
    if nut:                                                # espárrago roscado que sobresale de la tuerca
        zt = z + h
        prof = [(d * 0.5, zt - 0.001)]
        n = max(2, int(L / (d * 0.15)))
        for k in range(n):
            zz = zt + k * (L / n)
            prof += [(d * 0.5, zz), (d * 0.46, zz + L / n * 0.5)]
        prof += [(d * 0.5, zt + L - d * 0.08), (d * 0.42, zt + L), (0.0, zt + L)]
        lathe(mb, prof, seg=SEG, mat=mat, M=M)


def rivet(mb, M, d=0.005, mat="aluminium"):
    """Remache de cabeza redonda sobre z = 0 local (hundido 0,3 mm)."""
    r = d / 2
    lathe(mb, [(r * 1.0, -0.0003), (r, r * 0.12), (r * 0.9, r * 0.38), (r * 0.62, r * 0.56), (r * 0.3, r * 0.64), (0.0, r * 0.66)],
          seg=16, mat=mat, M=M)


def small_chain(mb, pts, link=0.011, wire=0.0011, mat="steel", seed=0):
    """Cadenita de eslabones ovalados alternados (90°) a paso constante sobre una polilínea; alambre redondo de 12 lados con
    sombreado continuo (mb.soft)."""
    r = rng(seed)
    P = [_v(p) for p in (fillet([tuple(p) for p in pts], link * 1.2, 6) if len(pts) > 2 else pts)]
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    pitch = link - 1.8 * wire                           # eslabones trabados: el alambre de uno muerde 0,2 Ø en el siguiente
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
            M = face_M(c, dd, up=(0, 0, 1) if abs(dd.z) < 0.9 else (1, 0, 0)) @ _Ry(90)
            M = M @ _Rx(90 * (k % 2) + float(r.uniform(-12, 12)))
            hw = link * 0.32
            path = []
            for q in range(5):
                ang = -PI / 2 + PI * q / 4
                path.append(M @ Vector((link / 2 - hw + hw * math.cos(ang), hw * math.sin(ang), 0)))
            for q in range(5):
                ang = PI / 2 + PI * q / 4
                path.append(M @ Vector((-link / 2 + hw + hw * math.cos(ang), hw * math.sin(ang), 0)))
            _loop_tube(mb, path, wire, SEG_W, mat, M.to_3x3() @ Vector((0, 0, 1)))


def _loop_tube(mb, pts, r, seg, mat, normal):
    P = [_v(p) for p in pts]
    n = len(P)
    N = _v(normal).normalized()
    R = []
    for i in range(n):
        T = (P[(i + 1) % n] - P[i - 1]).normalized()
        B = T.cross(N).normalized()
        R.append([mb.bm.verts.new(P[i] + (N * math.cos(2 * PI * k / seg) + B * math.sin(2 * PI * k / seg)) * r) for k in range(seg)])
    for i in range(n):
        A, B_ = R[i], R[(i + 1) % n]
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([A[k], A[kk], B_[kk], B_[k]], mat)


def stamp_fill(mb, outer, holes, mat, normal):
    """Rellena una cara plana delimitada por el lazo de vértices `outer` con los lazos `holes` como huecos (triangulación
    BEAUTY): lámina estampada con realces que nacen de la misma cara (sin piezas encimadas)."""
    E = []
    for L in [outer] + holes:
        n = len(L)
        for i in range(n):
            e = mb.bm.edges.get((L[i], L[(i + 1) % n])) or mb.bm.edges.new((L[i], L[(i + 1) % n]))
            E.append(e)
    res = bmesh.ops.triangle_fill(mb.bm, use_beauty=True, use_dissolve=False, edges=E, normal=_v(normal))
    mi = mb.mi(mat)
    for g in res["geom"]:
        if isinstance(g, bmesh.types.BMFace):
            g.material_index = mi


def emboss_loops(P, R, d0, w, h, n=5, steps=6, depth_fn=None):
    """Lazos (2D + altura) de un realce estampado de contorno poligonal redondeado P/R: base a d0 hacia adentro sobre la
    cara (altura 0), flanco en S de ancho w y alto h (h < 0: bajorrelieve). Devuelve [(pts2d, altura)]."""
    out = []
    for k in range(steps + 1):
        t = k / steps
        out.append((rpoly_pts(P, R, d0 + w * t, n), h * (1 - math.cos(PI * t)) / 2))
    return out


# ============================================================================================================ bidón
def jerry_can(seed=0, color="od"):
    """Bidón de 20 L tipo OTAN ("jerry can") de lámina de acero: 470 × 345 × 165 mm totales (Wavian / Artemis Overland:
    18-1/2" × 13-1/2" × 6-1/2"). Dos mitades estampadas unidas por una costura de pestaña soldada que da la vuelta a todo el
    perímetro (sobresale 4,5 mm, raíz con radio); X estampada en ambas caras (cuatro paneles realzados 3,5 mm con flanco en S
    que nacen de la misma lámina: lo que da rigidez y deja dilatar al combustible); tres asas de tubo Ø 17 soldadas con
    cordón sobre la tapa; boca a bayoneta en la esquina, inclinada 15°, con tapa abombada, empaque, bisagra de pasador,
    palanca de leva de canal, oreja con pasador de seguridad y cadenita a la asa; marcas estampadas en la franja superior y
    esténcil pintado. Pintura verde olivo (od) o arena (tan). Origen: centro de la base; caras anchas hacia ±Y."""
    r = rng(seed)
    paint = "paint_od" if color == "od" else "paint_tan"
    ink = "sign_white" if color == "od" else "cable"
    mb = MBX()
    W, D = 0.345, 0.165
    FL, FT, RF = 0.0045, 0.0024, 0.0018                    # pestaña de la costura: vuelo, espesor (2 láminas), radio de raíz
    z0 = FL                                                # la costura inferior apoya en el piso
    Hb = 0.4245                                            # cuerpo; con las asas: 0,47 m
    zc, ztop = z0 + Hb / 2, z0 + Hb
    re = 0.016                                             # radio del canto cara-costado
    rc = (0.036, 0.03, 0.03, 0.03)                         # esquinas en la vista de frente (+x+z con la boca, -x+z, -x-z, +x-z)
    NC = 8

    def outline(dl, y):
        return [(x, y, zc + z) for (x, z) in rr_pts(W - 2 * dl, Hb - 2 * dl, tuple(max(c - dl, 0.002) for c in rc), n=NC)]
    # ---- cuerpo: secciones (dl hacia adentro, y) de la cara delantera a la trasera, con la costura de pestaña al centro
    half = []
    for j in range(7):                                     # canto redondo de la cara
        a = PI / 2 * j / 6
        half.append((re * (1 - math.sin(a)), -D / 2 + re * (1 - math.cos(a))))
    half.append((0.0, -FT / 2 - RF - 0.004))
    for j in range(5):                                     # raíz cóncava de la pestaña
        th = PI - PI / 2 * j / 4
        half.append((-(RF + RF * math.cos(th)), -FT / 2 - RF + RF * math.sin(th)))
    tipc = FL - FT / 2
    for j in range(4):                                     # punta redonda (mitad delantera)
        ph = -PI / 2 + PI / 2 * j / 4
        half.append((-(tipc + FT / 2 * math.cos(ph)), FT / 2 * math.sin(ph)))
    prof = half + [(-FL, 0.0)] + [(dl, -y) for (dl, y) in reversed(half)]
    V = skin(mb, [outline(dl, y) for (dl, y) in prof], paint, cap0=False, cap1=False)
    # ---- caras con la X estampada (paneles que nacen de la lámina; relleno plano con huecos)
    x0, x1 = -W / 2 + 0.034, W / 2 - 0.034
    zf0, zf1 = z0 + 0.040, ztop - 0.050
    C = ((x0 + x1) / 2, (zf0 + zf1) / 2)
    tris = [[(x0, zf1), C, (x1, zf1)], [(x1, zf1), C, (x1, zf0)], [(x1, zf0), C, (x0, zf0)], [(x0, zf0), C, (x0, zf1)]]
    Rk = [0.018, 0.011, 0.018]
    EH, EW, G = 0.0035, 0.0075, 0.0055                     # alto del realce, ancho del flanco, medio canal de la X en la base
    for side, Vf in ((-1, V[0]), (1, V[-1])):
        yf = side * D / 2
        holes = []
        for tri in tris:
            loops = emboss_loops(tri, Rk, G, EW, EH, n=6, steps=6)
            pts3 = [[(p[0], yf + side * hh, p[1]) for p in L] for (L, hh) in loops]
            VV = [[mb.bm.verts.new(_v(p)) for p in L] for L in pts3]
            for i in range(len(VV) - 1):
                A, B = VV[i], VV[i + 1]
                k = len(A)
                for j in range(k):
                    q = [A[j], A[(j + 1) % k], B[(j + 1) % k], B[j]]
                    mb.face(q if side > 0 else list(reversed(q)), paint)
            ngon(mb, VV[-1] if side > 0 else list(reversed(VV[-1])), paint)
            holes.append(VV[0])
        stamp_fill(mb, Vf, holes, paint, (0, side, 0))
    # marcas estampadas en la franja superior (cara delantera) y esténcil pintado en el panel superior
    Mfr = face_M((0, -D / 2, 0), (0, -1, 0))
    yr_ = int(r.integers(14, 25))
    text_font(mb, "20L", 0.013, 0.0006, paint, Mfr @ _T(-0.085, ztop - 0.035, 0.0), font="stencil2", res=2)
    text_font(mb, f"{int(r.integers(1, 13)):02d} {yr_}", 0.011, 0.0006, paint, Mfr @ _T(0.075, ztop - 0.035, 0.0), font="stencil2",
              res=2)
    word = ("DIESEL", "FUEL", "DIESEL", None)[int(r.integers(0, 4))]
    if word:
        text_font(mb, word, 0.03, 0.0005, ink, Mfr @ _T(0.0, zf1 - 0.045, EH), font="stencil", res=2)
    # ---- asas: tres tubos Ø 17 doblados con radio real, soldados con cordón sobre la tapa (pasan por encima de la costura)
    xs_h = (-0.118, -0.04, 0.038)
    for xh in xs_h:
        path = [(xh, -0.052, ztop - 0.004), (xh, -0.052, ztop + 0.032), (xh, 0.052, ztop + 0.032), (xh, 0.052, ztop - 0.004)]
        tube_path(mb, path, 0.0085, seg=20, mat=paint, bend=0.017, nseg=8, caps=True)
        for yy in (-0.052, 0.052):
            weld_ring(mb, _T(xh, yy, ztop), 0.0085, w=0.0028, seg=24, mat=paint)
    # ---- boca a bayoneta: cuello soldado en la esquina, inclinado 15° hacia +X
    xs_, ang = 0.112, 15.0
    Ms = _T(xs_, 0.0, ztop + 0.018) @ _Ry(ang)              # origen: borde del cuello; +Z = eje de la boca
    lathe(mb, [(0.0235, -0.06), (0.0235, -0.0045), (0.0252, -0.0035), (0.0258, -0.0015), (0.0252, 0.0), (0.0215, 0.0),
               (0.0215, -0.02), (0.0, -0.02)], seg=36, mat=paint, M=Ms)
    weld_ring(mb, _T(xs_ - 0.0, 0.0, ztop) @ _Ry(ang * 0.5), 0.0245, w=0.0035, seg=36, mat=paint)
    lathe(mb, [(0.0208, 0.0), (0.0262, 0.0), (0.0266, 0.0012), (0.0262, 0.0024), (0.0208, 0.0024)], seg=36, mat="rubber", M=Ms,
          closed=True)                                     # empaque
    # tapa abombada con faldón enrollado y anillo estampado
    lathe(mb, [(0.0, 0.0128), (0.008, 0.0127), (0.0105, 0.0136), (0.0125, 0.0136), (0.015, 0.0124), (0.022, 0.0116),
               (0.0272, 0.0102), (0.0298, 0.0082), (0.0306, 0.0058), (0.0306, 0.0030), (0.0298, 0.0019), (0.0275, 0.0017),
               (0.0, 0.0017)], seg=36, mat=paint, M=Ms)
    # bisagra: dos orejas en el cuello, lengüeta de la tapa entre ellas y pasador remachado (eje Y local)
    xh_, zh_ = 0.0335, 0.0055
    for sy in (-1, 1):
        Mc = Ms @ _T(0.0, sy * 0.0085, 0.0) @ _Rx(90)
        slab(mb, Mc @ _T(0.0297, -0.00425, -0.00125), 0.0175, 0.0275, 0.0025, rc=(0.0058, 0.002, 0.002, 0.002), re=0.0006,
             mat=paint, nc=4, ne=1)
    slab(mb, Ms @ _Rx(90) @ _T(0.031, 0.0055, -0.0055), 0.012, 0.009, 0.011, rc=0.003, re=0.0008, mat=paint, nc=3, ne=1)
    lathe(mb, [(0.0, -0.0118), (0.0026, -0.0116), (0.0029, -0.0108), (0.0022, -0.0104), (0.0022, 0.0104), (0.0029, 0.0108),
               (0.0026, 0.0116), (0.0, 0.0118)], seg=16, mat="steel", M=Ms @ _T(xh_, 0.0, zh_) @ _Rx(90))
    # palanca de leva (fleje de canal 13 × 3,2 mm): nace en la bisagra, cruza la tapa y baja hacia la oreja del seguro
    p_h = Ms @ Vector((xh_ + 0.003, 0.0, zh_ + 0.004))
    p_a = Ms @ Vector((0.024, 0.0, 0.0172))
    p_b = Ms @ Vector((-0.026, 0.0, 0.0172))
    p_c = Vector((0.066, 0.0, ztop + 0.0205))
    p_d = Vector((0.05, 0.0, ztop + 0.0165))
    lev = fillet([tuple(p_h), tuple(p_a), tuple(p_b), tuple(p_c), tuple(p_d)], 0.008, 6)
    prof = [(-0.0065, -0.0016), (0.0065, -0.0016), (0.0065, 0.0002), (0.0061, 0.0011), (0.0053, 0.0016), (0.0028, 0.0016),
            (0.0021, 0.0019), (0.0016, 0.0025), (0.0008, 0.0028), (-0.0008, 0.0028), (-0.0016, 0.0025), (-0.0021, 0.0019),
            (-0.0028, 0.0016), (-0.0053, 0.0016), (-0.0061, 0.0011), (-0.0065, 0.0002)]   # fleje con nervio estampado
    sweep_frame(mb, prof, lev, paint, up=(0, 0, 1))
    torus(mb, _T(p_d.x + 0.0005, 0.0, p_d.z - 0.003) @ _Rx(90), 0.0035, 0.0016, mat=paint, n=10, seg=SEG_T, a0=PI * 0.5,
          a1=PI * 1.6)                                     # punta enrollada de la palanca
    # oreja del seguro (placa con agujero, soldada a la tapa del bidón) y pasador con argolla + cadenita a la asa
    Mo = _T(0.058, 0.0, ztop) @ _Rx(90)
    holed(mb, Mo @ _T(0.0, 0.0, -0.0015), (0.0, 0.0155, 0.0075, 0.0145, (0.0075, 0.0075, 0.0015, 0.0015)),
          (0.0, 0.0255, 0.0021, 0.0021, 0.0021), 0.003, re_o=0.0007, re_i=0.0005, n=32, mat=paint, ne=2, ctr=(0.0, 0.0255))
    for sy in (-1, 1):                                     # la oreja va soldada sobre la pestaña de la costura
        weld_bead(mb, [(0.0508, sy * 0.0017, ztop + 0.0037), (0.0652, sy * 0.0017, ztop + 0.0037)], r=0.0011, mat=paint)
    pz = ztop + 0.0255
    with mb.soft():
        mb.cyl((0.058, -0.014, pz - 0.00035), (0.058, 0.012, pz - 0.00035), 0.0018, seg=SEG_W, mat="steel")
    lathe(mb, [(0.0, 0.0), (0.0024, 0.0), (0.0024, 0.0016), (0.0, 0.0021)], seg=16, mat="steel",
          M=_T(0.058, 0.012, pz - 0.00035) @ _Rx(-90))
    torus(mb, _T(0.058, -0.0215, pz) @ _Rz(90) @ _Rx(90) @ _Rz(0), 0.0075, 0.0011, mat="steel", n=24, seg=SEG_W)
    xa = xs_h[2]
    small_chain(mb, [(0.058, -0.0215, pz - 0.0082), (0.057, -0.036, ztop + 0.0045), (0.05, -0.046, ztop + 0.0042),
                     (xa + 0.0105, -0.052, ztop + 0.006)], link=0.009, wire=0.0009, mat="steel", seed=seed)
    return mb


# ======================================================================================= lámina, herrajes y tablero
def rr_loop(w, h, r, dl, z, n=4, cx=0.0, cy=0.0):
    """Lazo 3D de rectángulo redondeado w × h (radio r o 4 radios) desplazado dl hacia adentro, a la altura z."""
    rcs = r if isinstance(r, (tuple, list)) else (r,) * 4
    return [(cx + x, cy + y, z) for (x, y) in rr_pts(w - 2 * dl, h - 2 * dl, tuple(max(q - dl, 4e-4) for q in rcs), n)]


def shell_box(mb, M, w, d, h, rc, mat, openings=(), re=0.02, re0=0.004, ne=3, nc=6):
    """Gabinete de lámina: planta w × d centrada (esquinas verticales rc), z de 0 a h, cantos re (arriba) y re0 (abajo), con
    VANOS REALES en sus caras: openings = [(cara, u0, u1, z0, z1, hondo, mat_fondo)], cara '-y' | '+y' (u = x) o '-x' | '+x'
    (u = y). Cada vano lleva su túnel (jamba de lámina) hacia adentro y un fondo; nada de calcomanías encimadas.
    Devuelve, por vano, la matriz de la cara en su centro (+Z hacia afuera, +Y arriba) y su ancho y alto."""
    levels = []
    for j in range(ne + 1):
        p = PI / 2 * j / ne
        levels.append((re0 * (1 - math.sin(p)), re0 * (1 - math.cos(p))))
    zs = sorted({round(o[3], 6) for o in openings} | {round(o[4], 6) for o in openings})
    levels += [(0.0, z) for z in zs]
    for j in range(ne + 1):
        p = PI / 2 * j / ne
        levels.append((re * (1 - math.cos(p)), h - re + re * math.sin(p)))
    ins = {f: sorted({round(o[1], 6) for o in openings if o[0] == f} | {round(o[2], 6) for o in openings if o[0] == f})
           for f in ("+y", "-x", "-y", "+x")}

    def loop(dl, z):
        P = rr_pts(w - 2 * dl, d - 2 * dl, max(rc - dl, 4e-4), nc)
        k = nc + 1
        out = []
        for c, f in enumerate(("+y", "-x", "-y", "+x")):
            out += [(x, y, z) for (x, y) in P[c * k:(c + 1) * k]]
            us = ins[f]
            if f == "+y":
                out += [(u, d / 2 - dl, z) for u in sorted(us, reverse=True)]
            elif f == "-x":
                out += [(-w / 2 + dl, u, z) for u in sorted(us, reverse=True)]
            elif f == "-y":
                out += [(u, -d / 2 + dl, z) for u in sorted(us)]
            else:
                out += [(w / 2 - dl, u, z) for u in sorted(us)]
        return out
    L = [loop(dl, z) for (dl, z) in levels]
    V = skin(mb, L, mat, M, cap0=True, cap1=True)
    res = []
    for (f, u0, u1, z0, z1, depth, bmat) in openings:
        li0 = next(i for i, (dl, z) in enumerate(levels) if abs(z - z0) < 1e-6 and dl == 0.0)
        li1 = next(i for i, (dl, z) in enumerate(levels) if abs(z - z1) < 1e-6 and dl == 0.0)
        coord = (lambda p: p[0]) if f in ("+y", "-y") else (lambda p: p[1])
        side = (lambda p: abs(p[1] - (d / 2 if f == "+y" else -d / 2)) < 1e-6) if f in ("+y", "-y") else \
               (lambda p: abs(p[0] - (w / 2 if f == "+x" else -w / 2)) < 1e-6)
        ks = [k for k, p in enumerate(L[li0]) if side(p) and min(u0, u1) - 1e-6 <= coord(p) <= max(u0, u1) + 1e-6]
        ks.sort()
        kk = [k for k in ks]
        dead = []
        for li in range(li0, li1):
            for a, b in zip(kk[:-1], kk[1:]):
                q = {V[li][a], V[li][b], V[li + 1][b], V[li + 1][a]}
                for fc in V[li][a].link_faces:
                    if set(fc.verts) == q:
                        dead.append(fc)
        bmesh.ops.delete(mb.bm, geom=dead, context="FACES")
        rim = [V[li0][k] for k in kk] + [V[li][kk[-1]] for li in range(li0 + 1, li1)] + [V[li1][k] for k in reversed(kk)] + \
              [V[li][kk[0]] for li in range(li1 - 1, li0, -1)]
        nrm = {"+y": Vector((0, 1, 0)), "-y": Vector((0, -1, 0)), "+x": Vector((1, 0, 0)), "-x": Vector((-1, 0, 0))}[f]
        nw = (M.to_3x3() @ nrm).normalized()
        inner = [mb.bm.verts.new(v.co - nw * depth) for v in rim]
        n = len(rim)
        for i in range(n):
            mb.face([rim[i], rim[(i + 1) % n], inner[(i + 1) % n], inner[i]], mat)
        mb.face(list(reversed(inner)), bmat or mat)
        uc, zc = (u0 + u1) / 2, (z0 + z1) / 2
        o = {"+y": (uc, d / 2, zc), "-y": (uc, -d / 2, zc), "+x": (w / 2, uc, zc), "-x": (-w / 2, uc, zc)}[f]
        res.append((M @ face_M(o, nrm), abs(u1 - u0), z1 - z0))
    return res


def pan_door(mb, M, w, h, mat, rc=0.008, t=0.0, re=0.0016, ret=0.022, field=(0.035, 0.003, 0.008, 0.012), beads=(), nc=4, ne=3):
    """Hoja de puerta de lámina estampada (charola): local XY = plano de la cara (+Z afuera), cara en z = t, pestaña de retorno
    de `ret` hacia adentro, canto redondo re. field = (borde, hondo, flanco, radio): campo estampado hundido; beads = [(cx, cy,
    ancho, alto, realce)] nervios realzados dentro del campo. Devuelve la z del campo."""
    loops = [rr_loop(w, h, rc, 0.0, t - ret, nc), rr_loop(w, h, rc, 0.0, t - re, nc)]
    for j in range(1, ne + 1):
        a = PI / 2 * j / ne
        loops.append(rr_loop(w, h, rc, re * (1 - math.cos(a)), t - re + re * math.sin(a), nc))
    zf = t
    if field:
        b, dep, fw, rf = field
        for j in range(7):
            tt = j / 6
            loops.append(rr_loop(w - 2 * b, h - 2 * b, rf, fw * tt, t - dep * (1 - math.cos(PI * tt)) / 2, nc))
        zf = t - dep
    V = skin(mb, loops, mat, M, cap0=True, cap1=False)
    holes = []
    for (cx, cy, bw, bh, hg) in beads:
        fw = min(bw, bh) * 0.3
        rb = min(bw, bh) / 2 - 1e-4
        BL = [rr_loop(bw, bh, rb, fw * k / 5, zf + hg * (1 - math.cos(PI * k / 5)) / 2, 6, cx, cy) for k in range(6)]
        VB = skin(mb, BL, mat, M, cap0=False, cap1=False)
        ngon(mb, VB[-1], mat)
        holes.append(VB[0])
    stamp_fill(mb, V[-1], holes, mat, M.to_3x3() @ Vector((0, 0, 1)))
    return zf


def louver_hood(mb, M, lw, lh, hz=0.006, mat="paint_od", mouth="cable"):
    """Persiana troquelada (lanceta formada) en el plano XY local: capucha que sale hasta hz en su boca inferior (y = -lh/2) y
    nace a ras arriba, costados formados; boca oscura. Hundida 0,4 mm en la lámina."""
    us = [-1.0, -0.975, -0.93, -0.86, -0.74, -0.5, -0.25, 0.0, 0.25, 0.5, 0.74, 0.86, 0.93, 0.975, 1.0]
    vs = [0.0, 0.12, 0.3, 0.5, 0.7, 0.86, 1.0]
    sk = -0.0004

    def P(u, v):
        e = min(1.0, (1 - abs(u)) / 0.12)
        s = math.sin(PI / 2 * e)
        z = hz * math.sin(PI / 2 * v) ** 0.8 * s
        return Vector((u * lw / 2, lh / 2 - v * lh, z + sk * (1 - s * (v > 0))))
    G = [[mb.bm.verts.new(M @ P(u, v)) for u in us] for v in vs]
    for j in range(len(vs) - 1):
        for i in range(len(us) - 1):
            mb.face([G[j][i], G[j][i + 1], G[j + 1][i + 1], G[j + 1][i]], mat)
    B = [mb.bm.verts.new(M @ Vector((u * lw / 2 * 0.985, -lh / 2 + 0.0004, sk))) for u in us]
    for i in range(len(us) - 1):
        mb.face([G[-1][i + 1], G[-1][i], B[i], B[i + 1]], mouth)
    rimv = G[0] + [G[j][-1] for j in range(1, len(vs))] + list(reversed(B)) + [G[j][0] for j in range(len(vs) - 1, 0, -1)]
    mb.face(list(reversed(rimv)), mat)                     # fondo oculto (n-gono plano, sin astillas)


def piano_hinge(mb, M, L, r=0.0042, kn=0.028, gap=0.0007, leaf=0.02, mat="paint_od", pitch=0.09):
    """Bisagra de piano a lo largo de Y local (-L/2..L/2), eje en x = 0 sobre el plano z = 0: hoja de la puerta hacia -x, hoja
    del marco hacia +x (1,5 mm, remachadas), nudillos alternados con holgura y pasador con cabeza."""
    zc = r + 0.0004
    n = max(3, int(round(L / kn)))
    kl = L / n
    for i in range(n):
        y0 = -L / 2 + i * kl + gap / 2
        ln = kl - gap
        lathe(mb, [(r * 0.82, 0.0), (r, 0.0008), (r, ln - 0.0008), (r * 0.82, ln)], seg=SEG, mat=mat,
              M=M @ _T(0, y0, zc) @ _Rx(-90))
        sx = -1 if i % 2 == 0 else 1                       # lengüeta que une el nudillo a su hoja
        mb.box((min(0, sx * r * 1.1), y0 + 0.001, 0.0006), (max(0, sx * r * 1.1), y0 + ln - 0.001, zc), mat, bevel=0.0005, seg=1, m=M)
    for s_ in (-1, 1):
        mb.box((min(s_ * leaf, s_ * r * 0.6), -L / 2, -0.0003), (max(s_ * leaf, s_ * r * 0.6), L / 2, 0.0015), mat, bevel=0.0006, seg=1,
               m=M)
        y = -L / 2 + 0.03
        while y < L / 2 - 0.02:
            rivet(mb, M @ _T(s_ * leaf * 0.6, y, 0.0015), d=0.0048, mat=mat)
            y += pitch
    mb.cyl(M @ Vector((0, -L / 2 - 0.0002, zc)), M @ Vector((0, L / 2 + 0.0002, zc)), r * 0.42, seg=16, mat="steel")   # pasador
    for e in (-1, 1):
        lathe(mb, [(0.0, 0.0), (r * 0.62, 0.0), (r * 0.62, 0.0012), (r * 0.4, 0.002), (0.0, 0.0022)], seg=16, mat="steel",
              M=M @ _T(0, e * (L / 2 - 0.0002), zc) @ _Rx(-90 * e))


def comp_latch(mb, M, mat="steel", ang=0.0, L=0.075):
    """Cerrojo de compresión con manija en L: roseta, maza con cilindro de llave y palanca de fleje que se curva hacia la
    puerta. Base en z = 0 local, eje +Z; la palanca apunta a `ang` grados desde +X local."""
    lathe(mb, [(0.0, -0.0003), (0.019, -0.0003), (0.0206, 0.0008), (0.0206, 0.0022), (0.019, 0.0035), (0.0, 0.0038)], seg=36,
          mat=mat, M=M)
    lathe(mb, [(0.0, 0.003), (0.0112, 0.003), (0.0112, 0.0158), (0.0102, 0.0176), (0.0, 0.0179)], seg=32, mat=mat, M=M)
    lathe(mb, [(0.0, 0.0172), (0.0056, 0.0172), (0.0058, 0.0182), (0.0, 0.0184)], seg=24, mat="brass", M=M)
    mb.box((-0.0036, -0.0006, 0.0179), (0.0036, 0.0006, 0.019), "cable", bevel=0.0, m=M)
    Mh = M @ _Rz(ang)
    path = fillet([(0.0, 0.0, 0.0104), (0.03, 0.0, 0.0104), (L, 0.0, 0.0072)], 0.05, 6)
    path = [tuple(Mh @ Vector(p)) for p in path]
    sweep_frame(mb, rr_profile(0.016, 0.0062, 0.0028, n=3), path, mat, up=M.to_3x3() @ Vector((0, 0, 1)))
    lathe(mb, [(0.0, 0.0), (0.008, 0.0), (0.0083, 0.0025), (0.0075, 0.0042), (0.0, 0.0046)], seg=24, mat=mat,
          M=Mh @ _T(L - 0.004, 0.0, 0.0072 + 0.0028))     # remate redondo de la palanca


def vane_grille(mb, Mo, ow, oh, mat, nb=12, mesh_z=-0.052):
    """Rejilla de álabes doblados dentro de un vano real (Mo = cara del vano, +Z afuera): marco de lámina atornillado que tapa
    el corte, nb álabes de perfil quebrado (1,6 mm) con labio de goteo, y malla de alambre de 1,8 mm detrás."""
    holed(mb, Mo @ _T(0, 0, -0.0004), (0, 0, ow / 2 + 0.03, oh / 2 + 0.03, 0.012), (0, 0, ow / 2 - 0.004, oh / 2 - 0.004, 0.005), 0.006,
          re_o=0.0022, re_i=0.0016, n=72, mat=mat, ne=2)
    nu, nv = max(2, int(round(ow / 0.15))), max(2, int(round(oh / 0.15)))
    pts = [(u, v) for u in (-1, 1) for v in np.linspace(-1, 1, nv + 1)] + [(u, v) for v in (-1, 1) for u in np.linspace(-1, 1, nu + 1)[1:-1]]
    for (u, v) in pts:
        bolt(mb, Mo @ _T(u * (ow / 2 + 0.016), v * (oh / 2 + 0.016), 0.0056), d=0.006, washer=False, mat="steel")
    pitch = (oh - 0.008) / nb
    bt = 0.0016
    cl = [(-pitch * 0.42, -0.003), (-pitch * 0.12, -0.016), (pitch * 0.12, -0.026), (pitch * 0.5, -0.044)]   # (y, z) eje del álabe
    blade = [(yy, zz + bt / 2) for (yy, zz) in cl] + [(yy, zz - bt / 2) for (yy, zz) in reversed(cl)]
    for k in range(nb):
        yk = -oh / 2 + 0.004 + pitch * (k + 0.5)
        rings = [[Mo @ Vector((x, yk + yy, zz)) for (yy, zz) in blade] for x in (-ow / 2 - 0.001, ow / 2 + 0.001)]
        loft_rings(mb, rings, mat)
        rbox(mb, (-ow / 2, yk - pitch * 0.46, -0.003 - bt * 0.6), (ow / 2, yk - pitch * 0.38, -0.003 + bt * 0.6), mat, r=0.0007,
             m=Mo)                                         # labio redondo del borde de goteo
    with mb.soft():                                        # malla de protección detrás de los álabes
        for k in range(int(ow / 0.012)):
            x = -ow / 2 + 0.006 + k * 0.012
            mb.cyl(Mo @ Vector((x, -oh / 2, mesh_z)), Mo @ Vector((x, oh / 2, mesh_z)), 0.0009, seg=SEG_W, mat="steel")
        for k in range(int(oh / 0.012)):
            y = -oh / 2 + 0.006 + k * 0.012
            mb.cyl(Mo @ Vector((-ow / 2, y, mesh_z - 0.0015)), Mo @ Vector((ow / 2, y, mesh_z - 0.0015)), 0.0009, seg=SEG_W, mat="steel")


def lift_lug(mb, M, w=0.07, h=0.085, t=0.012, hole=0.0135, mat="steel"):
    """Ojo de izaje: placa de 12 mm de cabeza redonda con barreno de canto redondeado, parada sobre una placa de refuerzo y
    soldada por ambos lados. Local: placa en el plano XZ (normal Y), base en z = 0."""
    slab(mb, M @ _T(0, 0, -0.001), w * 1.5, t * 4.5, 0.007, rc=0.008, re=0.002, mat=mat, nc=4, ne=2)
    Mp = M @ _T(0, 0, 0.006) @ _Rx(90)
    holed(mb, Mp @ _T(0, 0, -t / 2), (0.0, h / 2, w / 2, h / 2, (w / 2, w / 2, 0.003, 0.003)), (0.0, h - w / 2, hole, hole, hole), t,
          re_o=0.003, re_i=0.0025, n=48, mat=mat, ne=2, ctr=(0.0, h - w / 2))
    for s_ in (-1, 1):
        weld_bead(mb, [M @ Vector((-w / 2 + 0.004, s_ * (t / 2 + 0.001), 0.0072)), M @ Vector((w / 2 - 0.004, s_ * (t / 2 + 0.001), 0.0072))],
                  r=0.0026, mat=mat)


def gauge_dial(mb, M, r=0.034, needle=30.0):
    """Instrumento de carátula redonda: caja embutida, bisel cromado, carátula blanca rehundida con escala, aguja y cristal."""
    lathe(mb, [(0.0, -0.0003), (r * 1.12, -0.0003), (r * 1.15, 0.002), (r * 1.13, 0.0065), (r * 1.06, 0.0095), (r * 0.97, 0.009),
               (r * 0.95, 0.004), (r * 0.93, 0.003), (0.0, 0.003)], seg=48, mat="steel", M=M,
          mats=["steel"] * 7 + ["sign_white"])
    for k in range(11):
        a = math.radians(225 - 27 * k)
        L_ = 0.16 if k % 5 == 0 else 0.1
        Mt = M @ _T(0, 0, 0.003) @ _Rz(math.degrees(a) - 90)
        mb.box((-0.0006, r * (0.84 - L_), -0.0002), (0.0006, r * 0.84, 0.0005), "cable", bevel=0.0, m=Mt)
    mb.box((-0.0007, -r * 0.12, 0.0008), (0.0007, r * 0.76, 0.0016), "sign_red", bevel=0.0002, seg=1, m=M @ _T(0, 0, 0.003) @
           _Rz(needle))
    lathe(mb, [(0.0, 0.003), (0.0032, 0.003), (0.0032, 0.0048), (0.0, 0.0054)], seg=16, mat="cable", M=M)
    lathe(mb, [(r * 0.975, 0.0074), (r * 0.5, 0.0081), (0.0, 0.0083), (0.0, 0.0076), (r * 0.5, 0.0074), (r * 0.975, 0.0067)], seg=48,
          mat="glass", M=M, closed=True)


def toggle_switch(mb, M, guard=False, up=True):
    """Interruptor de palanca de tablero: tuerca hexagonal, buje roscado y palanca de bola; guard=True: guarda abatible
    (tapa roja de seguridad) cerrada sobre la palanca, con su bisagra."""
    from kit.clinic_servicios import hexnut
    hexnut(mb, M, s=0.014, h=0.003, mat="steel")
    lathe(mb, [(0.0, 0.0), (0.006, 0.0), (0.006, 0.009), (0.0055, 0.0098), (0.0, 0.0098)], seg=24, mat="steel", M=M,
          rmod=lambda i, a, rr, z: rr - 0.0003 * (math.cos(20 * a) > 0.3) if i in (1, 2) else rr)
    tip = M @ Vector((0.0, 0.009 if up else -0.009, 0.026))
    with mb.soft():
        mb.cyl(M @ Vector((0, 0, 0.009)), tip, 0.0022, seg=SEG_W, mat="steel", r1=0.0016)
    lathe(mb, [(0.0, -0.0028), (0.0021, -0.0024), (0.0029, 0.0), (0.0021, 0.0024), (0.0, 0.0028)], seg=16, mat="steel",
          M=face_M(tip, tip - (M @ Vector((0, 0, 0.009)))))
    if guard:
        Mg = M @ _T(0, -0.016, 0.0)
        mb.box((-0.013, -0.004, -0.0003), (0.013, 0.004, 0.006), "steel", bevel=0.0012, seg=2, m=Mg)
        with mb.soft():
            mb.cyl(Mg @ Vector((-0.015, 0, 0.0045)), Mg @ Vector((0.015, 0, 0.0045)), 0.0018, seg=SEG_W, mat="steel")
        from kit.clinic_servicios import cup
        cup(mb, M @ _T(0, 0.004, 0.034) @ _Rx(180), 0.026, 0.044, 0.032, 0.0015, rc=0.005, re=0.004, mat="sign_red", nc=3, ne=2)


def e_stop(mb, M):
    """Botón de paro de emergencia: placa leyenda amarilla, collarín de guarda con dos escotes y hongo rojo de 40 mm."""
    lathe(mb, [(0.0, -0.0003), (0.042, -0.0003), (0.0428, 0.0006), (0.042, 0.0013), (0.0, 0.0013)], seg=48, mat="paint_yellow", M=M)
    from kit.clinic_equipo import arc_solid
    for a0 in (0.35, PI + 0.35):
        arc_solid(mb, 0.0245, 0.0285, 0.0, 0.022, a0, a0 + PI - 0.7, 20, "steel", M=M)
    lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.013), (0.0, 0.013)], seg=32, mat="cable", M=M)
    lathe(mb, [(0.0, 0.013), (0.012, 0.013), (0.012, 0.018), (0.019, 0.0185), (0.0205, 0.021), (0.0205, 0.0255), (0.018, 0.03),
               (0.011, 0.0325), (0.0, 0.033)], seg=48, mat="sign_red", M=M)


def panel_label(mb, M, s, w, size=0.0075, h=0.014):
    """Placa grabada de tablero (aluminio anodizado con letras negras en relieve de 0,4 mm)."""
    slab(mb, M @ _T(0, 0, -0.0003), w, h, 0.0011, rc=0.0015, re=0.0004, mat="aluminium", nc=2, ne=1)
    text_font(mb, s, size, 0.0006, "cable", M @ _T(0, -size * 0.36, 0.0008), font="sign", bold=True, res=2)


# ======================================================================================================= generador táctico
def tactical_generator(seed=0, color="od"):
    """Grupo electrógeno táctico de 10 kW sobre patín (tipo AMMPS MEP-1040 / 10RMP-1040A: 1403 × 816 × 918 mm, 458 kg en seco;
    Cummins Rugged Mobile Power, ficha 10 kW; MARCORSYSCOM). Largo en X, frente de servicio -Y.
    Patín de canales C 110 × 65 × 5 mm cortados por dos bolsas de montacargas pasantes (tubo 210 × 75 × 5, boca hueca y
    placas de refuerzo soldadas), travesaños, 4 argollas de amarre en D con su grapa soldada. Gabinete de lámina con esquinas
    de radio real, base y tapa sobrepuesta (gotero) atornilladas, VANOS REALES con jamba: 2 puertas por costado (charolas de
    lámina estampada con nervios, holgura de 3 mm, bisagra de piano, cerrojo de compresión de manija en L; la de la toma de
    aire con persianas troqueladas), rejilla de álabes doblados en el extremo -X, tablero de control empotrado en +X bajo
    visera (2 instrumentos, pantalla con teclado, interruptor maestro, BATTLE SHORT con guarda, paro de emergencia, breaker
    principal de 3 polos, pilotos, contacto con tapa, placas grabadas), y abajo borne de tierra, receptáculo de arranque
    auxiliar (NATO) con tapa y cadena, puerta del tablero de cargas y toma de combustible auxiliar con tapón. Techo: 4 ojos de
    izaje, escape con guarda de barras y tapa contra lluvia de charnela, boca de combustible con dique y tapón con cadena.
    Placa de datos remachada y esténciles."""
    r = rng(seed)
    paint = "paint_od" if color == "od" else "paint_tan"
    ink = "sign_white" if color == "od" else "cable"
    mb = MBX()
    Lx, Wy, Hz = 1.40, 0.81, 0.915
    zs = 0.11                                              # alto del patín
    # ------------------------------------------------------------------ patín
    yR = Wy / 2 - 0.0025                                   # cara del alma de los largueros
    cprof = [(0.0, 0.0), (0.065, 0.0), (0.065, 0.005), (0.009, 0.005), (0.006, 0.0058), (0.0052, 0.009), (0.005, 0.012),
             (0.005, 0.098), (0.0052, 0.101), (0.006, 0.1042), (0.009, 0.105), (0.065, 0.105), (0.065, 0.11), (0.0, 0.11)]
    cprof = [(-x, y) for (x, y) in cprof]                  # alas hacia adentro (x local negativa = hacia el centro)
    xp = (-0.36, 0.36)
    pw, ph, pz0 = 0.21, 0.075, 0.014
    cuts = [-Lx / 2 + 0.003] + [v for x in xp for v in (x - pw / 2, x + pw / 2)] + [Lx / 2 - 0.003]
    for sy in (-1, 1):
        for a, b in zip(cuts[0::2], cuts[1::2]):
            prof = [((x if sy > 0 else -x), y) for (x, y) in cprof]
            path = [(a, sy * yR, 0.0), (b, sy * yR, 0.0)]
            rings = [[Vector((p[0], p[1], 0.0)) + Vector((0, px, py)) for (px, py) in prof] for p in path]
            loft_rings(mb, rings, paint)
        for x in xp:                                       # alma sobre / bajo la bolsa (tramo de lámina soldado)
            y0_, y1_ = sorted((sy * yR, sy * (yR - 0.005)))
            mb.box((x - pw / 2 - 0.002, y0_, pz0 + ph - 0.002), (x + pw / 2 + 0.002, y1_, zs), paint, bevel=0.0015)
            mb.box((x - pw / 2 - 0.002, y0_, 0.0), (x + pw / 2 + 0.002, y1_, pz0 + 0.002), paint, bevel=0.0015)
    for x in xp:                                           # bolsas de montacargas pasantes con placa de refuerzo en la boca
        hollow_rect(mb, _T(x, -Wy / 2 - 0.006, pz0 + ph / 2) @ _Rz(90), pw, ph, 0.005, Wy + 0.012, mat=paint, r=0.006, n=3)
        for sy in (-1, 1):
            Mb_ = face_M((x, sy * (Wy / 2 + 0.0005), pz0 + ph / 2), (0, sy, 0))
            holed(mb, Mb_ @ _T(0, 0, -0.0015), (0, 0, pw / 2 + 0.022, ph / 2 + 0.014, 0.008), (0, 0, pw / 2 - 0.0005, ph / 2 - 0.0005,
                  0.0065), 0.006, re_o=0.0018, re_i=0.0012, n=56, mat=paint, ne=2)
    for sx in (-1, 1):                                     # travesaños extremos (canal con el alma hacia afuera)
        x = sx * (Lx / 2 - 0.0025)
        rings = [[Vector((x + sx * px, y, 0.005 + py * 0.1 / 0.11)) for (px, py) in cprof] for y in (-yR + 0.005, yR - 0.005)]
        loft_rings(mb, rings, paint)
        for sy in (-1, 1):                                 # cordón de soldadura vertical en la esquina del patín
            weld_bead(mb, [(x - sx * 0.0045, sy * (yR - 0.0045), 0.006), (x - sx * 0.0045, sy * (yR - 0.0045), zs - 0.006)], r=0.0028,
                      mat=paint)
    mb.box((-Lx / 2 + 0.06, -Wy / 2 + 0.06, 0.004), (Lx / 2 - 0.06, Wy / 2 - 0.06, 0.008), paint, bevel=0.002)   # charola de derrames
    # argollas de amarre en D con grapa soldada al alma (cerca de las 4 esquinas)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x = sx * (Lx / 2 - 0.085)
            Mw = face_M((x, sy * yR, 0.062), (0, sy, 0))       # sobre el alma del larguero; +Z hacia afuera
            for e in (-1, 1):                              # orejas soldadas con barreno para el perno de la argolla
                rbox(mb, (e * 0.024 - 0.0032, -0.013, -0.001), (e * 0.024 + 0.0032, 0.013, 0.03), paint, r=0.003, m=Mw)
                weld_bead(mb, [Mw @ Vector((e * 0.024 - 0.0045, -0.012, 0.0005)), Mw @ Vector((e * 0.024 - 0.0045, 0.012, 0.0005))],
                          r=0.002, mat=paint)
                weld_bead(mb, [Mw @ Vector((e * 0.024 + 0.0045, -0.012, 0.0005)), Mw @ Vector((e * 0.024 + 0.0045, 0.012, 0.0005))],
                          r=0.002, mat=paint)
            Mbar = Mw @ _T(0, 0, 0.019)
            mb.cyl(Mbar @ Vector((-0.031, 0, 0)), Mbar @ Vector((0.031, 0, 0)), 0.0068, seg=SEG, mat="steel")
            for e in (-1, 1):
                lathe(mb, [(0.0, 0.0), (0.0095, 0.0), (0.0095, 0.004), (0.006, 0.0058), (0.0, 0.006)], seg=SEG, mat="steel",
                      M=Mbar @ _T(e * 0.031, 0, 0) @ _Ry(90 * e))
            dpath = [Mbar @ (_Rx(-22) @ Vector((-0.0185 * math.cos(PI * k / 16), -0.046 * math.sin(PI * k / 16), 0.0))) for k in range(17)]
            mb.tube([tuple(p) for p in dpath], 0.0068, seg=SEG_T, mat="steel", caps=True)
    # ------------------------------------------------------------------ gabinete con vanos reales
    hb = Hz - 0.035 - zs
    zd0, zd1 = 0.08, 0.63                                  # vanos de puertas (z local del gabinete)
    xd = [(-0.635, -0.04), (0.04, 0.635)]
    ops = []
    for f in ("-y", "+y"):
        for (a, b) in xd:
            ops.append((f, a, b, zd0, zd1, 0.034, "cable"))
    ops.append(("-x", -0.29, 0.29, 0.15, 0.6, 0.06, "cable"))           # rejilla del radiador
    ops.append(("+x", -0.29, 0.29, 0.28, 0.66, 0.065, paint))           # tablero de control empotrado
    ops.append(("+x", 0.115, 0.3, 0.05, 0.22, 0.03, "cable"))           # tablero de cargas (puerta chica)
    Mg = _T(0, 0, zs)
    frames = shell_box(mb, Mg, Lx, Wy, hb, 0.03, paint, ops, re=0.006, re0=0.003, ne=2, nc=6)
    # base sobrepuesta (faldón atornillado) y tapa con gotero
    slab(mb, _T(0, 0, zs - 0.004), Lx + 0.008, Wy + 0.008, 0.042, rc=0.034, re=0.0025, mat=paint, nc=6, ne=2)
    pan_door(mb, _T(0, 0, Hz), Lx + 0.01, Wy + 0.01, paint, rc=0.035, t=0.0, re=0.022, ret=0.048, field=None, nc=8, ne=6,
             beads=[(x, 0.0, 0.05, Wy - 0.24, 0.0035) for x in (-0.2, 0.2)])   # tapa con gotero y nervios estampados
    for (y, nrm) in ((-Wy / 2 - 0.005, (0, -1, 0)), (Wy / 2 + 0.005, (0, 1, 0))):
        for x in np.linspace(-0.62, 0.62, 9):
            Mf = face_M((x, y, Hz - 0.026), nrm)
            bolt(mb, Mf, d=0.006, washer=True, mat="steel")
        for x in np.linspace(-0.62, 0.62, 7):
            Mf = face_M((x, y - 0.001 if y > 0 else y + 0.001, zs + 0.018), nrm)
            bolt(mb, Mf, d=0.008, washer=True, mat="steel")
    for (x, nrm) in ((-Lx / 2 - 0.005, (-1, 0, 0)), (Lx / 2 + 0.005, (1, 0, 0))):
        for y in np.linspace(-0.33, 0.33, 5):
            bolt(mb, face_M((x, y, Hz - 0.026), nrm), d=0.006, washer=True, mat="steel")
    # ---- puertas de los costados
    for i, (Mo, ow, oh) in enumerate(frames[:4]):
        f = ops[i][0]
        left = (ops[i][1] < 0)
        # bisagra en el canto exterior de cada hoja (en coords de la cara: x local hacia +X mundial en -y, hacia -X en +y)
        outer_sign = (-1 if left else 1) * (1 if f == "-y" else -1)
        g = 0.003
        dw, dh = ow - 2 * g, oh - 2 * g
        intake = left
        if intake:
            zf = pan_door(mb, Mo, dw, dh, paint, field=(0.03, 0.0025, 0.007, 0.01))
            for row in range(8):
                for col in (-1, 1):
                    louver_hood(mb, Mo @ _T(col * 0.115, 0.19 - row * 0.05, zf), 0.18, 0.03, hz=0.0065, mat=paint)
        else:
            zf = pan_door(mb, Mo, dw, dh, paint, field=(0.03, 0.0025, 0.007, 0.01),
                          beads=[(0.0, 0.13, dw - 0.13, 0.034, 0.003), (0.0, -0.13, dw - 0.13, 0.034, 0.003)])
        piano_hinge(mb, Mo @ _T(outer_sign * (ow / 2), 0, 0.0) @ _Rz(0 if outer_sign > 0 else 180), dh - 0.03, mat=paint)
        comp_latch(mb, Mo @ _T(-outer_sign * (dw / 2 - 0.06), 0.0, zf - 0.0002), mat="steel", ang=90.0 if outer_sign < 0 else -90.0)
    # ---- rejilla del radiador (extremo -X): marco atornillado, álabes doblados, fondo oscuro con malla
    Mo, ow, oh = frames[4]
    vane_grille(mb, Mo, ow, oh, paint, nb=12)
    # ---- tablero de control empotrado (+X)
    Mo, ow, oh = frames[5]
    Mb = Mo @ _T(0, 0, -0.065)
    _gen_panel(mb, Mb, ow, oh, paint, r)
    # visera de lámina sobre el nicho (techo + mejillas con canto enrollado)
    vz = oh / 2 + 0.012
    slab(mb, Mo @ _T(0, vz, 0.0) @ _Rx(-90) @ _T(0, -0.05, -0.0015), ow + 0.06, 0.1, 0.003, rc=(0.0, 0.0, 0.006, 0.006), re=0.0012,
         mat=paint, nc=3, ne=1)
    tube_path(mb, [tuple(Mo @ Vector((-ow / 2 - 0.03, vz - 0.001, 0.1))), tuple(Mo @ Vector((ow / 2 + 0.03, vz - 0.001, 0.1)))], 0.004,
              seg=SEG_T, mat=paint, caps=True)
    from kit.clinic_servicios import pslab
    for s_ in (-1, 1):                                     # mejillas (cartabones) de la visera
        pslab(mb, Mo @ _T(s_ * (ow / 2 + 0.027) - 0.0015, 0, 0) @ _Ry(90), [(0.0, vz + 0.0015), (-0.098, vz + 0.0015), (0.0, vz - 0.12)],
              [0.003, 0.006, 0.006], 0.003, re=0.0012, mat=paint, n=3, ne=1)
        for k in range(3):
            bolt(mb, Mo @ _T(s_ * (ow / 2 + 0.027 + 0.0015 * s_), vz - 0.02 - k * 0.035, 0.008) @ _Ry(90 * s_), d=0.005, washer=False,
                 mat="steel")
    # ---- tablero de cargas: puerta chica con cerrojo de cuarto de vuelta
    Mo, ow, oh = frames[6]
    zft = pan_door(mb, Mo, ow - 0.006, oh - 0.006, paint, field=(0.02, 0.002, 0.006, 0.008))
    piano_hinge(mb, Mo @ _T(0, oh / 2, 0) @ _Rz(90), ow - 0.03, mat=paint)
    comp_latch(mb, Mo @ _T(0, -oh / 2 + 0.053, zft - 0.0002), mat="steel", ang=180.0, L=0.06)
    panel_label(mb, Mo @ _T(0, 0.025, zft), "LOAD TERMINALS", 0.11, size=0.0095, h=0.018)
    # ---- extremo +X abajo: borne de tierra, receptáculo NATO de arranque auxiliar, toma de combustible auxiliar
    Me = face_M((Lx / 2, 0, 0), (1, 0, 0))
    # borne de tierra
    Mgd = Me @ _T(-0.25, zs + 0.13, 0.0)
    lathe(mb, [(0.0, -0.0003), (0.026, -0.0003), (0.026, 0.004), (0.0, 0.004)], seg=SEG, mat="brass", M=Mgd)
    bolt(mb, Mgd @ _T(0, 0, 0.004), d=0.012, L=0.04, nut=True, mat="brass")
    from kit.clinic_servicios import hexnut
    lathe(mb, [(0.0065, 0.022), (0.016, 0.022), (0.016, 0.0245), (0.0065, 0.0245)], seg=SEG, mat="brass", M=Mgd, closed=True)
    lathe(mb, [(0.006, 0.0245), (0.009, 0.0245), (0.009, 0.034), (0.006, 0.034)], seg=SEG, mat="brass", M=Mgd, closed=True)
    for e in (-1, 1):                                      # alas de la tuerca de mariposa
        slab(mb, Mgd @ _T(e * 0.015, 0, 0.0245) @ _Rx(90) @ _T(0, 0.012, -0.002), 0.016, 0.022, 0.004, rc=(0.007, 0.007, 0.002, 0.002),
             re=0.0012, mat="brass", nc=3, ne=1)
    panel_label(mb, Me @ _T(-0.25, zs + 0.075, 0.0), "GROUND", 0.07, size=0.0095, h=0.018)
    # receptáculo de arranque auxiliar con tapa y cadena
    Mn = Me @ _T(-0.06, zs + 0.13, 0.0)
    slab(mb, Mn @ _T(0, 0, -0.0003), 0.085, 0.085, 0.004, rc=0.01, re=0.0015, mat="steel", nc=4, ne=1)
    for (u, v) in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        bolt(mb, Mn @ _T(u * 0.032, v * 0.032, 0.0037), d=0.005, washer=False, mat="steel")
    lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.03), (0.032, 0.031), (0.032, 0.036), (0.0, 0.036)], seg=SEG * 2, mat="steel", M=Mn)
    lathe(mb, [(0.0, 0.0355), (0.0335, 0.0355), (0.0345, 0.04), (0.0345, 0.052), (0.033, 0.055), (0.025, 0.057), (0.0, 0.0575)],
          seg=SEG * 2, mat="rubber", M=Mn, rmod=lambda i, a, rr, z: rr + 0.0012 * (math.cos(12 * a) > 0.6) if i in (2, 3) else rr)
    small_chain(mb, [tuple(Mn @ Vector((0.0, -0.0345, 0.047))), tuple(Mn @ Vector((0.014, -0.05, 0.028))),
                     tuple(Mn @ Vector((0.032, -0.034, 0.0075)))], link=0.012, wire=0.0012, seed=seed + 3)
    panel_label(mb, Me @ _T(-0.06, zs + 0.075, 0.0), "SLAVE", 0.06, size=0.0095, h=0.018)
    # toma de combustible auxiliar (conexión rápida con tapón guardapolvo y cadena)
    Mq = Me @ _T(0.335, zs + 0.1, 0.0)
    hexnut(mb, Mq, s=0.03, h=0.012, mat="brass")
    lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.011, 0.03), (0.0125, 0.032), (0.0125, 0.037), (0.0, 0.037)], seg=SEG, mat="brass", M=Mq)
    lathe(mb, [(0.0, 0.032), (0.016, 0.032), (0.0168, 0.036), (0.0168, 0.05), (0.015, 0.053), (0.0, 0.054)], seg=SEG * 2, mat="rubber",
          M=Mq)
    small_chain(mb, [tuple(Mq @ Vector((0.0, 0.015, 0.045))), tuple(Mq @ Vector((0.01, 0.03, 0.03))), tuple(Mq @ Vector((0.0, 0.036, 0.008)))],
                link=0.01, wire=0.001, seed=seed + 5)
    text_font(mb, "AUX FUEL", 0.016, 0.0005, ink, Mq @ _T(0, -0.035, -0.0003), font="stencil", res=2)
    # ------------------------------------------------------------------ techo
    for sx in (-1, 1):
        for sy in (-1, 1):
            Me_ = _T(sx * (Lx / 2 - 0.1), sy * (Wy / 2 - 0.1), Hz - 0.001) @ _Rz(45 * sx * sy)
            lift_lug(mb, Me_, mat="steel")
    # escape: brida, tubo, guarda de barras y tapa de charnela
    xe, ye = -0.42, 0.18
    Mx_ = _T(xe, ye, Hz)
    lathe(mb, [(0.0, -0.002), (0.062, -0.002), (0.062, 0.006), (0.058, 0.009), (0.0, 0.009)], seg=48, mat="steel", M=Mx_)
    for k in range(6):
        a = 2 * PI * k / 6
        bolt(mb, Mx_ @ _T(0.05 * math.cos(a), 0.05 * math.sin(a), 0.009), d=0.006, washer=False, mat="steel")
    lathe(mb, [(0.034, 0.0), (0.038, 0.0), (0.038, 0.135), (0.0365, 0.137), (0.034, 0.137)], seg=48, mat="metal_rust", M=Mx_,
          closed=True)
    lathe(mb, [(0.0, 0.03), (0.0342, 0.03)], seg=48, mat="cable", M=Mx_, caps=False)
    for zr in (0.016, 0.118):                              # guarda: dos anillos de solera y barras verticales
        torus(mb, Mx_ @ _T(0, 0, zr), 0.058, 0.0035, mat="steel", n=48, seg=SEG_T)
    for k in range(14):
        a = 2 * PI * (k + 0.5) / 14
        p0 = Mx_ @ Vector((0.058 * math.cos(a), 0.058 * math.sin(a), 0.006))
        p1 = Mx_ @ Vector((0.058 * math.cos(a), 0.058 * math.sin(a), 0.124))
        mb.tube([tuple(p0), tuple(p1)], 0.0032, seg=SEG_T, mat="steel")
    for k in range(3):                                     # tirantes de la guarda al tubo
        a = 2 * PI * k / 3
        mb.tube([tuple(Mx_ @ Vector((0.037 * math.cos(a), 0.037 * math.sin(a), 0.1))), tuple(Mx_ @ Vector((0.058 * math.cos(a),
                 0.058 * math.sin(a), 0.118)))], 0.003, seg=SEG_T, mat="steel")
    Mrc = Mx_ @ _T(0.041, 0, 0.142) @ _Ry(-6)               # tapa de charnela (cerrada, bisagra del lado +X)
    lathe(mb, [(0.0, 0.0035), (0.03, 0.0033), (0.042, 0.0022), (0.0445, 0.0), (0.0445, -0.004), (0.042, -0.0045), (0.0, -0.0045)],
          seg=48, mat="steel", M=Mrc @ _T(-0.041, 0, 0))
    mb.cyl(Mrc @ Vector((0.0, -0.012, -0.002)), Mrc @ Vector((0.0, 0.012, -0.002)), 0.0042, seg=SEG, mat="steel")
    rbox(mb, (-0.004, -0.008, -0.03), (0.006, 0.008, -0.0005), "steel", r=0.002, m=Mrc)
    rbox(mb, (0.0, -0.007, 0.0), (0.03, 0.007, 0.012), "steel", r=0.003, m=Mrc @ _T(0.004, 0, -0.0035) @ _Ry(-25))   # contrapeso
    text_font(mb, "HOT", 0.03, 0.0005, ink, _T(xe + 0.12, ye, Hz) @ _Rz(90), font="stencil", res=2)
    # boca de combustible con dique, tapón con cadena y esténcil
    xf_, yf_ = 0.42, -0.2
    Mfl = _T(xf_, yf_, Hz)
    lathe(mb, [(0.0, -0.002), (0.075, -0.002), (0.075, 0.012), (0.071, 0.014), (0.068, 0.012), (0.068, 0.004), (0.0, 0.004)], seg=64,
          mat=paint, M=Mfl)
    lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.03), (0.0325, 0.032), (0.0325, 0.036), (0.0, 0.036)], seg=48, mat=paint, M=Mfl)
    lathe(mb, [(0.0, 0.034), (0.039, 0.034), (0.041, 0.037), (0.041, 0.054), (0.038, 0.058), (0.03, 0.061), (0.0, 0.062)], seg=72,
          mat="steel", M=Mfl, rmod=lambda i, a, rr, z: rr - 0.0018 * max(0.0, math.cos(12 * a)) ** 6 if i in (2, 3) else rr)
    lathe(mb, [(0.0, 0.06), (0.011, 0.06), (0.011, 0.068), (0.0, 0.069)], seg=32, mat="steel", M=Mfl)
    torus(mb, Mfl @ _T(0.046, 0, 0.044) @ _Rx(90), 0.006, 0.0014, mat="steel", n=20, seg=SEG_W)
    rbox(mb, (xf_ + 0.084, yf_ - 0.006, Hz - 0.001), (xf_ + 0.1, yf_ + 0.006, Hz + 0.016), "steel", r=0.002)
    small_chain(mb, [(xf_ + 0.052, yf_, Hz + 0.04), (xf_ + 0.07, yf_ + 0.004, Hz + 0.012), (xf_ + 0.092, yf_, Hz + 0.012)], link=0.011,
                wire=0.0011, seed=seed + 7)
    text_font(mb, "DIESEL ONLY", 0.032, 0.0005, ink, _T(xf_ - 0.01, yf_ + 0.12, Hz), font="stencil", res=2)
    text_font(mb, "NO STEP", 0.045, 0.0005, ink, _T(-0.02, -0.1, Hz) @ _Rz(0), font="stencil", res=2)
    # ------------------------------------------------------------------ placa de datos, esténciles y marcas de izaje/amarre
    Mdp = face_M((0.33, -Wy / 2, zs + 0.71), (0, -1, 0))
    slab(mb, Mdp @ _T(0, 0, -0.0003), 0.24, 0.085, 0.0012, rc=0.004, re=0.0004, mat="aluminium", nc=3, ne=1)
    for (u, v) in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        rivet(mb, Mdp @ _T(u * 0.111, v * 0.034, 0.0009), d=0.005)
    lines = ["GENERATOR SET  DIESEL ENGINE DRIVEN", "10 KW  120/208 V  3 PH  60 HZ  0.8 PF", f"SERIAL NO  {int(r.integers(1000, 9999))}",
             "WEIGHT DRY 1010 LB"]
    for k, s_ in enumerate(lines):
        text_font(mb, s_, 0.0085, 0.0004, "cable", Mdp @ _T(0.0, 0.022 - k * 0.016, 0.0008), font="sign", bold=(k == 0), res=2)
    for (sy, nrm) in ((-1, (0, -1, 0)), (1, (0, 1, 0))):
        Mst = face_M((0.0, sy * Wy / 2, 0.0), nrm)
        Msk = face_M((0.0, sy * yR, 0.0), nrm)
        xs_ = -0.33 if sy < 0 else 0.33
        text_font(mb, "10 KW", 0.05, 0.0005, ink, Mst @ _T(xs_ if sy < 0 else -xs_, zs + 0.69, 0.0), font="stencil", res=2)
        for sx in (-1, 1):
            text_font(mb, "TIE DOWN", 0.014, 0.0005, ink, Msk @ _T(sx * (Lx / 2 - 0.085) * (1 if sy < 0 else -1), 0.092, 0.0),
                      font="stencil", res=2)
        for x in xp:
            text_font(mb, "FORK", 0.013, 0.0005, ink, Msk @ _T(x * (1 if sy < 0 else -1), pz0 + ph + 0.0035, 0.0), font="stencil", res=2)
    return mb


def _gen_panel(mb, M, w, h, paint, r):
    """Tablero de control del generador sobre el fondo del nicho (plano XY local, +Z hacia afuera, x hacia +Y mundial)."""
    from kit.clinic_servicios import knob, rrframe
    # placa del tablero atornillada (aluminio pintado negro mate = "cable") con tornillos en el perímetro
    slab(mb, M @ _T(0, 0, -0.0005), w - 0.024, h - 0.024, 0.004, rc=0.006, re=0.0012, mat="cable", nc=3, ne=1)
    zp = 0.0032                                            # todo lo montado se hunde 0,3 mm en la placa
    for u in np.linspace(-1, 1, 5):
        for v in (-1, 1):
            bolt(mb, M @ _T(u * (w / 2 - 0.024), v * (h / 2 - 0.024), zp), d=0.005, washer=False, mat="steel")
    P = M @ _T(0, 0, zp)
    # instrumentos de carátula
    for k, (x, lab) in enumerate(((-0.205, "AC VOLTS"), (-0.105, "AC AMPS"))):
        gauge_dial(mb, P @ _T(x, 0.095, 0), r=0.034, needle=float(r.uniform(-40, 10)))
        panel_label(mb, P @ _T(x, 0.044, 0), lab, 0.07)
    # pantalla del controlador con bisel y teclado de membrana
    Md = P @ _T(0.07, 0.1, 0)
    rrframe(mb, Md, (0, 0, 0.16, 0.1, 0.008), (0, 0, 0.118, 0.072, 0.004), 0.008, re_o=0.0018, re_i=0.0012, n=4, ne=2, mat="plastic")
    slab(mb, Md @ _T(0, 0, 0.0), 0.12, 0.074, 0.0055, rc=0.004, re=0.0005, mat="glass", nc=3, ne=1)
    slab(mb, P @ _T(0.205, 0.1, 0), 0.07, 0.1, 0.004, rc=0.006, re=0.0012, mat="plastic", nc=3, ne=1)
    for i in range(3):
        for j in range(2):
            slab(mb, P @ _T(0.19 + j * 0.03 - 0.0, 0.135 - i * 0.033, 0.0035), 0.022, 0.022, 0.0035, rc=0.004, re=0.0014, mat="rubber",
                 nc=3, ne=2)
    panel_label(mb, P @ _T(0.07, 0.037, 0), "ENGINE CONTROLLER", 0.13)
    # interruptor maestro rotativo con faldón y escala
    Mk = P @ _T(-0.205, -0.02, 0)
    lathe(mb, [(0.0, 0.0), (0.04, 0.0), (0.04, 0.0012), (0.0, 0.0012)], seg=64, mat="aluminium", M=Mk @ _T(0, 0, -0.0003))
    for k, s_ in enumerate(("OFF", "RUN", "START")):
        a = math.radians(150 - 60 * k)
        text_font(mb, s_, 0.0065, 0.0004, "cable", Mk @ _T(0.031 * math.cos(a), 0.031 * math.sin(a) - 0.002, 0.0009), font="sign",
                  bold=True, res=2)
    knob(mb, Mk @ _T(0, 0, 0.0009), r=0.013, h=0.018, mat="cable", skirt=(0.019, 0.006), ribs=18, rib_d=0.0008, fin=True,
         pointer_mat="sign_white")
    panel_label(mb, P @ _T(-0.205, -0.065, 0), "MASTER SWITCH", 0.085)
    # BATTLE SHORT con guarda roja cerrada y luz del tablero
    toggle_switch(mb, P @ _T(-0.105, -0.015, 0), guard=True)
    panel_label(mb, P @ _T(-0.105, -0.065, 0), "BATTLE SHORT", 0.085)
    toggle_switch(mb, P @ _T(-0.035, -0.02, 0), guard=False, up=bool(r.integers(0, 2)))
    panel_label(mb, P @ _T(-0.035, -0.065, 0), "PANEL LT", 0.05)
    # pilotos
    for k, m_ in enumerate(("sign_green", "paint_yellow", "sign_red")):
        Ml = P @ _T(0.035 + k * 0.035, -0.02, 0)
        from kit.clinic_servicios import hexnut
        hexnut(mb, Ml, s=0.017, h=0.003, mat="steel")
        lathe(mb, [(0.0, 0.0), (0.0085, 0.0), (0.0085, 0.006), (0.0078, 0.0075), (0.0, 0.0075)], seg=32, mat="steel", M=Ml)
        lathe(mb, [(0.0, 0.0072), (0.0068, 0.0072), (0.0068, 0.0095), (0.005, 0.0122), (0.0, 0.013)], seg=32, mat=m_, M=Ml)
    panel_label(mb, P @ _T(0.07, -0.05, 0), "RUN   LOW FUEL   FAULT", 0.13)
    # paro de emergencia
    e_stop(mb, P @ _T(0.205, -0.02, 0))
    panel_label(mb, P @ _T(0.205, -0.078, 0), "EMERGENCY STOP", 0.09)
    # breaker principal de 3 polos con barra de unión
    Mbk = P @ _T(-0.15, -0.135, 0)
    rbox(mb, (-0.055, -0.03, -0.0005), (0.055, 0.03, 0.022), "cable", r=0.003, m=Mbk)
    for k in range(3):
        rbox(mb, (-0.007, -0.013, 0.02), (0.007, 0.013, 0.026), "plastic", r=0.0015, m=Mbk @ _T(-0.036 + k * 0.036, 0, 0))
        rbox(mb, (-0.0045, -0.004, 0.0), (0.0045, 0.004, 0.022), "cable", r=0.0015, m=Mbk @ _T(-0.036 + k * 0.036, 0.004, 0.024) @
             _Rx(-20))
    rbox(mb, (-0.046, -0.003, -0.0025), (0.046, 0.003, 0.0025), "steel", r=0.0012, m=Mbk @ _T(0, 0.012, 0.045))
    panel_label(mb, P @ _T(-0.15, -0.178, 0) @ _T(0, 0.0, 0), "MAIN BREAKER", 0.09)
    # contacto de conveniencia con tapa de resorte
    Mr_ = P @ _T(0.1, -0.135, 0)
    slab(mb, Mr_ @ _T(0, 0, -0.0003), 0.075, 0.075, 0.003, rc=0.006, re=0.001, mat="steel", nc=3, ne=1)
    lathe(mb, [(0.0, 0.0), (0.027, 0.0), (0.027, 0.012), (0.0, 0.012)], seg=48, mat="cable", M=Mr_)
    lathe(mb, [(0.0, 0.012), (0.03, 0.012), (0.031, 0.015), (0.031, 0.019), (0.029, 0.021), (0.0, 0.0215)], seg=48, mat="steel",
          M=Mr_)
    mb.cyl(Mr_ @ Vector((-0.012, 0.033, 0.017)), Mr_ @ Vector((0.012, 0.033, 0.017)), 0.004, seg=SEG, mat="steel")
    rbox(mb, (-0.008, 0.02, 0.012), (0.008, 0.033, 0.02), "steel", r=0.002, m=Mr_)
    panel_label(mb, P @ _T(0.1, -0.188, 0), "120 V", 0.045)
    rbox(mb, (-0.02, -0.035, -0.0005), (0.02, 0.035, 0.016), "cable", r=0.003, m=P @ _T(0.205, -0.135, 0))   # horómetro
    slab(mb, P @ _T(0.205, -0.128, 0.0158), 0.03, 0.012, 0.0012, rc=0.001, re=0.0003, mat="glass", nc=2, ne=1)
    panel_label(mb, P @ _T(0.205, -0.188, 0), "HOURS", 0.05)


# ================================================================================================== pluma de acceso
def _anchor_plate(mb, x, y, w, d, t, mat, bolts, M=None):
    """Placa base de 20 mm con cantos redondos y anclas químicas de espárrago (tuerca, arandela y rosca saliente)."""
    M = M or Matrix()
    slab(mb, M @ _T(x, y, -0.001), w, d, t + 0.001, rc=0.012, re=0.003, mat=mat, nc=4, ne=2)
    for (u, v) in bolts:
        bolt(mb, M @ _T(x + u, y + v, t), d=0.016, L=0.026, nut=True, mat="galvanized")


def drop_arm_barrier(L=5.0, seed=0):
    """Pluma de acceso con gabinete y contrapeso (tipo pluma vehicular de brazo: ELKA / Automatic Systems BL10 — plumas de 3 a
    8 m con contrapeso de placas de acero en el eje; Avon: brazo hasta 7 m, apoyo final y faldón como accesorios; SafeSite /
    Bollard Security: apoyo final con candado para 6 m). Pedestal-gabinete de lámina de 0,32 × 0,30 × 0,88 m sobre placa base
    con 4 anclas, VANO REAL con puerta (charola estampada, bisagra de piano, cerrojo de manija con llave, persianas
    troqueladas), tapa con gotero; horquilla de placas de 12 mm con chumaceras de brida de 4 pernos y graseras, flecha Ø 40 con
    collarines; porta-pluma de tubo rectangular con contrapeso de 5 placas atornilladas y abrazadera partida de 4 pernos;
    pluma de aluminio Ø 90 con láminas reflejantes rojo/blanco de 0,5 m (en relieve de 0,4 mm), tope de hule en la punta,
    defensa de hule espuma bajo la pluma y FALDÓN articulado (colgantes de tubo Ø 20 con abrazaderas y pasadores + barra
    inferior); apoyo final con horquilla en Y, cojín de hule, cartabones, portacandado con candado; letrero STOP octagonal
    con orilla blanca estampada y letras Overpass, montado con abrazaderas en U. Corre a lo largo de +X desde x = 0; frente
    -Y; pluma bajada (horizontal) con eje a 1,0 m."""
    r = rng(seed)
    mb = MBX()
    Y = "paint_yellow"
    zb = 1.0                                               # eje de la pluma y de la flecha
    Rb = 0.045
    # ---- placa base y gabinete con puerta
    _anchor_plate(mb, 0.0, 0.0, 0.42, 0.4, 0.02, Y, [(u, v) for u in (-0.17, 0.17) for v in (-0.16, 0.16)])
    hc = 0.84
    frames = shell_box(mb, _T(0, 0, 0.02), 0.32, 0.3, hc, 0.022, Y,
                       [("-y", -0.105, 0.105, 0.1, 0.72, 0.03, "cable")], re=0.004, re0=0.002, ne=2, nc=6)
    for (sx, sy) in ((-1, -1), (-1, 1), (1, -1), (1, 1)):  # cordón de soldadura gabinete-placa en las esquinas
        weld_bead(mb, [(sx * 0.16 - sx * 0.02, sy * 0.1505, 0.022), (sx * 0.1505, sy * 0.13, 0.022)], r=0.003, mat=Y)
    Mo, ow, oh = frames[0]
    zf = pan_door(mb, Mo, ow - 0.006, oh - 0.006, Y, field=(0.025, 0.0025, 0.007, 0.01))
    for k in range(4):
        louver_hood(mb, Mo @ _T(0, -oh / 2 + 0.075 + k * 0.042, zf), 0.13, 0.026, hz=0.0055, mat=Y)
    piano_hinge(mb, Mo @ _T(-ow / 2, 0, 0) @ _Rz(180), oh - 0.04, mat=Y)
    comp_latch(mb, Mo @ _T(ow / 2 - 0.058, 0.05, zf - 0.0002), mat="steel", ang=-90.0, L=0.07)
    Mpl = Mo @ _T(0, oh / 2 - 0.07, zf)
    slab(mb, Mpl @ _T(0, 0, -0.0003), 0.13, 0.05, 0.0011, rc=0.003, re=0.0004, mat="aluminium", nc=3, ne=1)
    for (u, v) in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        rivet(mb, Mpl @ _T(u * 0.058, v * 0.018, 0.0008), d=0.004)
    text_font(mb, "AUTHORIZED", 0.011, 0.0005, "cable", Mpl @ _T(0, 0.004, 0.0008), font="sign", bold=True, res=2)
    text_font(mb, "PERSONNEL ONLY", 0.011, 0.0005, "cable", Mpl @ _T(0, -0.013, 0.0008), font="sign", bold=True, res=2)
    for sx in (-1, 1):                                     # persianas de ventilación en los costados
        for k in range(3):
            louver_hood(mb, face_M((sx * 0.16, 0.0, 0.62 + k * 0.045), (sx, 0, 0)), 0.16, 0.028, hz=0.0055, mat=Y)
    ztop = 0.02 + hc
    pan_door(mb, _T(0, 0, ztop + 0.014), 0.336, 0.316, Y, rc=0.028, t=0.0, re=0.006, ret=0.04, field=None, nc=6, ne=4)   # tapa
    # ---- horquilla: placas de 12 mm con chumaceras de brida, flecha Ø 40 con collarines
    zt = ztop + 0.014
    slab(mb, _T(0, 0, zt - 0.001), 0.26, 0.24, 0.013, rc=0.01, re=0.003, mat=Y, nc=4, ne=2)
    for sy in (-1, 1):
        y0 = sy * 0.08
        Mpl_ = _T(0, y0, zt) @ _Rx(90)
        holed(mb, Mpl_ @ _T(0, 0, -0.006), (0.0, (zb - zt + 0.11) / 2 + 0.0, 0.11, (zb - zt + 0.11) / 2 + 0.0, (0.11, 0.11, 0.004, 0.004)),
              (0.0, zb - zt, 0.0215, 0.0215, 0.0215), 0.012, re_o=0.003, re_i=0.002, n=64, mat=Y, ne=2, ctr=(0.0, zb - zt))
        for sx in (-1, 1):
            weld_bead(mb, [(sx * 0.105, y0 + sy * 0.0075, zt + 0.012), (sx * 0.005, y0 + sy * 0.0075, zt + 0.012)], r=0.0035, mat=Y)
            weld_bead(mb, [(sx * 0.105, y0 - sy * 0.0075, zt + 0.012), (sx * 0.005, y0 - sy * 0.0075, zt + 0.012)], r=0.0035, mat=Y)
        Mbr = face_M((0, y0 + sy * 0.006, zb), (0, sy, 0))       # chumacera de brida de 4 pernos (lado exterior)
        slab(mb, Mbr @ _T(0, 0, -0.0003), 0.11, 0.11, 0.014, rc=0.022, re=0.004, mat="steel", nc=5, ne=2)
        lathe(mb, [(0.0, 0.013), (0.045, 0.013), (0.045, 0.026), (0.04, 0.034), (0.026, 0.036), (0.0, 0.036)], seg=48, mat="steel", M=Mbr)
        for (u, v) in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            bolt(mb, Mbr @ _T(u * 0.038, v * 0.038, 0.014), d=0.012, washer=True, mat="galvanized")
        lathe(mb, [(0.0, 0.0), (0.004, 0.0), (0.004, 0.006), (0.0032, 0.007), (0.0032, 0.01), (0.0042, 0.0115), (0.0, 0.0125)], seg=16,
              mat="brass", M=Mbr @ _T(0.0, 0.03, 0.03) @ _Rx(-60))   # grasera
        lathe(mb, [(0.0, 0.034), (0.03, 0.034), (0.03, 0.05), (0.028, 0.052), (0.0, 0.052)], seg=48, mat="steel", M=Mbr)  # collarín
        lathe(mb, [(0.0, 0.0), (0.0035, 0.0), (0.0035, 0.009), (0.0, 0.0095)], seg=16, mat="steel",
              M=Mbr @ _T(0.0, 0.03, 0.043) @ _Rx(-90))                # opresor del collarín
    lathe(mb, [(0.0, -0.13), (0.02, -0.13), (0.02, 0.13), (0.0, 0.13)], seg=48, mat="steel", M=_T(0, 0, zb) @ _Rx(90))
    # ---- porta-pluma (tubo rectangular 120 × 100) con contrapeso y abrazadera partida
    rtube(mb, (-0.74, 0, zb), (0.36, 0, zb), 0.1, 0.12, Y, up=(0, 0, 1), r=0.009)
    for k in range(5):                                     # placas de contrapeso de 25 mm
        x0 = -0.72 + k * 0.052
        rbox(mb, (x0, -0.135, zb - 0.16), (x0 + 0.049, 0.135, zb + 0.13), "steel", r=0.004)
    for sy in (-1, 1):
        for sz in (-1, 1):
            p0, p1 = (-0.7225, sy * 0.095, zb + sz * 0.09), (-0.46, sy * 0.095, zb + sz * 0.09)
            mb.cyl(p0, p1, 0.008, seg=SEG, mat="galvanized")
            bolt(mb, face_M((-0.7202, sy * 0.095, zb + sz * 0.09), (-1, 0, 0)), d=0.016, L=0.03, nut=True, mat="galvanized")
            bolt(mb, face_M((-0.4632, sy * 0.095, zb + sz * 0.09), (1, 0, 0)), d=0.016, washer=True, mat="galvanized")
    text_font(mb, "220 KG", 0.034, 0.0005, "sign_white", face_M((-0.7202, 0.0, zb - 0.02), (-1, 0, 0)), font="stencil", res=2)
    for sz in (-1, 1):                                     # abrazadera partida (dos mitades con holgura de 3 mm)
        z0_, z1_ = (zb - 0.075, zb - 0.0015) if sz < 0 else (zb + 0.0015, zb + 0.075)
        rbox(mb, (0.3, -0.07, z0_), (0.5, 0.07, z1_), Y, r=0.008)
    for (u, v) in ((0.33, -0.055), (0.33, 0.055), (0.47, -0.055), (0.47, 0.055)):
        mb.cyl((u, v, zb - 0.09), (u, v, zb + 0.09), 0.0075, seg=SEG, mat="galvanized")
        bolt(mb, _T(u, v, zb + 0.075), d=0.014, washer=True, mat="galvanized")
        bolt(mb, _T(u, v, zb - 0.075) @ _Rx(180), d=0.014, L=0.012, nut=True, mat="galvanized")
    # ---- pluma con láminas reflejantes (relieve de 0,4 mm, bandas de 0,5 m), tope de hule
    x0b, x1b = 0.32, L - 0.03
    prof, mats = [(0.0, x0b)], []
    xs = [x0b] + [0.5 * k for k in range(1, int(L / 0.5) + 1) if x0b + 0.1 < 0.5 * k < x1b - 0.1] + [x1b]
    for i in range(len(xs) - 1):
        a, b = xs[i], xs[i + 1]
        red = (i % 2 == 0)
        rr = Rb + (0.0004 if red else 0.0)
        prof += [(Rb, a + 0.0004), (rr, a + 0.0008), (rr, b - 0.0008), (Rb, b - 0.0004)]
    prof += [(Rb, x1b), (0.0, x1b)]
    for i in range(len(prof) - 1):
        z_ = (prof[i][1] + prof[i + 1][1]) / 2
        seg_i = max(0, min(len(xs) - 2, next((k for k in range(len(xs) - 1) if xs[k] <= z_ <= xs[k + 1]), 0)))
        mats.append("sign_red" if seg_i % 2 == 0 else "sign_white")
    lathe(mb, prof, seg=48, mat="sign_white", M=_T(0, 0, zb) @ _Ry(90), mats=mats)
    lathe(mb, [(0.0, x1b - 0.03), (Rb + 0.003, x1b - 0.03), (Rb + 0.004, x1b - 0.02), (Rb + 0.004, x1b + 0.008), (0.038, x1b + 0.02),
               (0.022, x1b + 0.026), (0.0, x1b + 0.027)], seg=48, mat="rubber", M=_T(0, 0, zb) @ _Ry(90))
    # ---- faldón articulado y defensa de hule espuma entre colgantes
    xh0, xh1 = 0.85, L - 0.75
    nh = max(2, int(round((xh1 - xh0) / 0.42)) + 1)
    xsg = L * 0.55                                         # letrero STOP (el faldón se interrumpe detrás de él)
    hx = [xh0 + (xh1 - xh0) * k / (nh - 1) for k in range(nh)]
    hx = [x for x in hx if abs(x - xsg) > 0.13]
    zr = zb - 0.66                                         # barra inferior del faldón
    for x in hx:
        lathe(mb, [(Rb - 0.0004, -0.014), (Rb + 0.003, -0.0135), (Rb + 0.0035, -0.012), (Rb + 0.0035, 0.012), (Rb + 0.003, 0.0135),
                   (Rb - 0.0004, 0.014)], seg=48, mat="aluminium", M=_T(x, 0, zb) @ _Ry(90), closed=True)   # abrazadera
        slab(mb, _T(x, 0, zb - Rb - 0.021) @ _Rx(90) @ _T(0, 0, -0.003), 0.028, 0.038, 0.006, rc=(0.002, 0.002, 0.012, 0.012),
             re=0.0012, mat="aluminium", nc=3, ne=1)       # oreja colgante
        mb.cyl((x, -0.008, zb - Rb - 0.03), (x, 0.008, zb - Rb - 0.03), 0.004, seg=SEG_T, mat="steel")
        for e in (-1, 1):
            lathe(mb, [(0.0, 0.0), (0.0065, 0.0), (0.0065, 0.002), (0.0, 0.0025)], seg=SEG_T, mat="steel",
                  M=_T(x, e * 0.008, zb - Rb - 0.03) @ _Rx(-90 * e))
        tube_path(mb, [(x, 0.0, zb - Rb - 0.0215), (x, 0.0, zr + 0.018)], 0.01, seg=20, mat="aluminium", caps=True)
        lathe(mb, [(0.0, 0.0), (0.0115, 0.0), (0.0115, 0.012), (0.0, 0.014)], seg=20, mat="rubber", M=_T(x, 0, zb - Rb - 0.045) @ _Rx(180))
        torus(mb, _T(x, 0, zr) @ _Ry(90), 0.0145, 0.0035, mat="aluminium", n=24, seg=SEG_T)   # argolla a la barra inferior
    tube_path(mb, [(xh0 - 0.06, 0.0, zr), (xh1 + 0.06, 0.0, zr)], 0.0125, seg=24, mat="sign_white", caps=False)
    for e, xe in ((-1, xh0 - 0.06), (1, xh1 + 0.06)):
        lathe(mb, [(0.0, 0.0), (0.0128, 0.0), (0.0132, 0.012), (0.011, 0.017), (0.0, 0.018)], seg=24, mat="rubber",
              M=_T(xe, 0, zr) @ _Ry(90 * e))
    dprof = [(0.021, 0.004), (-0.021, 0.004)] + [(-0.021 * math.cos(PI * k / 12), -0.022 * math.sin(PI * k / 12)) for k in range(13)]
    gaps = sorted([(x - 0.03, x + 0.03) for x in hx] + [(xsg - 0.1, xsg + 0.1), (L - 0.25 - 0.09, L - 0.25 + 0.09)])
    edges = [x0b + 0.3] + [v for g in gaps for v in g] + [x1b - 0.06]
    for a, b in zip(edges[0::2], edges[1::2]):
        if b - a < 0.05:
            continue
        rings = []
        for x in (a, a + 0.008, b - 0.008, b):
            sh = 0.85 if x in (a, b) else 1.0
            rings.append([Vector((x, px * sh, zb - Rb + 0.006 + py * sh)) for (px, py) in dprof])
        loft_rings(mb, rings, "rubber")
    # ---- letrero STOP con abrazaderas en U
    Ms = face_M((xsg, -Rb - 0.03, zb), (0, -1, 0))
    oct_ = lambda rr: [(rr * math.cos(PI / 8 + k * PI / 4), rr * math.sin(PI / 8 + k * PI / 4)) for k in range(8)]  # noqa: E731
    from kit.clinic_servicios import pslab
    Rf = 0.19 / math.cos(PI / 8)                          # 380 mm entre caras
    pslab(mb, Ms @ _T(0, 0, -0.002), oct_(Rf), [0.02] * 8, 0.002, re=0.0009, mat="sign_red", n=4, ne=2)
    R1 = rpoly_pts(oct_(Rf - 0.008), [0.014] * 8, 0.0, 4)
    R2 = rpoly_pts(oct_(Rf - 0.008), [0.014] * 8, 0.014, 4)
    loops = [[(x, y, z) for (x, y) in P] for (P, z) in ((R1, -0.0003), (R1, 0.0006), (rpoly_pts(oct_(Rf - 0.008), [0.014] * 8, 0.0012, 4),
             0.0011), (rpoly_pts(oct_(Rf - 0.008), [0.014] * 8, 0.0128, 4), 0.0011), (R2, 0.0006), (R2, -0.0003))]
    skin(mb, loops, "sign_white", Ms, closed=True)         # orilla blanca estampada
    text_font(mb, "STOP", 0.118, 0.0008, "sign_white", Ms @ _T(0, -0.043, 0.0), font="sign", bold=True, res=3)
    for e in (-1, 1):                                      # abrazaderas en U al tubo de la pluma, con placa y tuercas
        xu = xsg + e * 0.08
        upath = [(xu, -Rb - 0.026, zb + Rb + 0.0045), (xu, 0.0, zb + Rb + 0.0045)] + \
                [(xu, (Rb + 0.0045) * math.sin(PI * k / 12), zb + (Rb + 0.0045) * math.cos(PI * k / 12)) for k in range(1, 12)] + \
                [(xu, 0.0, zb - Rb - 0.0045), (xu, -Rb - 0.026, zb - Rb - 0.0045)]
        tube_path(mb, upath, 0.0045, seg=SEG_T, mat="galvanized", caps=True)
        rbox(mb, (xu - 0.012, -Rb - 0.0285, zb - Rb - 0.012), (xu + 0.012, -Rb - 0.022, zb + Rb + 0.012), "galvanized", r=0.002)
    # ---- apoyo final con horquilla en Y, cojín de hule, portacandado y candado
    xr = L - 0.25
    _anchor_plate(mb, xr, 0.0, 0.3, 0.3, 0.018, Y, [(u, v) for u in (-0.115, 0.115) for v in (-0.115, 0.115)])
    zpt = zb - Rb - 0.03                                   # tope del poste (fondo de la horquilla)
    lathe(mb, [(0.0, 0.017), (0.0445, 0.017), (0.0445, zpt), (0.0, zpt)], seg=48, mat=Y, M=_T(xr, 0, 0))
    weld_ring(mb, _T(xr, 0, 0.018), 0.0445, w=0.006, seg=48, mat=Y)
    for k in range(4):                                     # cartabones
        a = PI / 4 + PI / 2 * k
        Mg_ = _T(xr, 0, 0.018) @ _Rz(math.degrees(a)) @ _Rx(90)
        pslab(mb, Mg_ @ _T(0, 0, -0.004), [(0.04, 0.0), (0.13, 0.0), (0.04, 0.12)], [0.002, 0.006, 0.004], 0.008, re=0.0015, mat=Y,
              n=3, ne=1)
    slab(mb, _T(xr, 0, zpt - 0.002), 0.13, 0.13, 0.012, rc=0.01, re=0.003, mat=Y, nc=4, ne=2)
    for sy in (-1, 1):                                     # placas de la Y abocinadas hacia arriba
        pslab(mb, _T(xr, sy * (Rb + 0.014), zpt + 0.01) @ _Rx(90) @ _T(0, 0, -0.005),
              [(-0.06, 0.0), (0.06, 0.0), (0.06, 0.07), (0.075, 0.13), (-0.075, 0.13), (-0.06, 0.07)],
              [0.004, 0.004, 0.02, 0.012, 0.012, 0.02], 0.01, re=0.0025, mat=Y, n=4, ne=2)
        rbox(mb, (-0.07, -0.005, -0.004), (0.07, 0.005, 0.045), Y, r=0.0025,
             m=_T(xr, sy * (Rb + 0.014), zpt + 0.138) @ _Rx(-sy * 30))          # labio abocinado de la Y
        for e in (-1, 1):
            weld_bead(mb, [(xr + e * 0.055, sy * (Rb + 0.014) + sy * 0.0055, zpt + 0.011), (xr + e * 0.055, sy * (Rb + 0.014) + sy * 0.0055,
                           zpt + 0.06)], r=0.0025, mat=Y)
    slab(mb, _T(xr, 0, zpt + 0.009), 0.11, 2 * Rb + 0.014, 0.022, rc=0.006, re=0.006, mat="rubber", nc=3, ne=2)   # cojín
    # portacandado: oreja en la horquilla y aldaba con candado
    Mh = face_M((xr + 0.062, -Rb - 0.02, zb + 0.02), (1, 0, 0))
    holed(mb, Mh @ _T(0, 0, -0.008), (0.0, 0.0, 0.016, 0.02, 0.008), (0.0, 0.006, 0.006, 0.006, 0.006), 0.008, re_o=0.0018, re_i=0.0015,
          n=40, mat=Y, ne=2, ctr=(0.0, 0.006))
    Mlk = _T(xr + 0.058, -Rb - 0.02, zb + 0.0307)
    torus(mb, Mlk @ _Rx(90) @ _T(0, -0.012, 0), 0.0095, 0.0033, mat="steel", n=24, seg=SEG_T, a0=0.0, a1=PI)
    for e in (-1, 1):
        mb.cyl(Mlk @ Vector((e * 0.0095, -0.0, -0.012)), Mlk @ Vector((e * 0.0095, 0.0, -0.03)), 0.0033, seg=SEG_T, mat="steel")
    rbox(mb, (-0.022, -0.009, -0.075), (0.022, 0.009, -0.028), "brass", r=0.004, m=Mlk)
    lathe(mb, [(0.0, 0.0), (0.0045, 0.0), (0.0045, 0.0012), (0.0, 0.0012)], seg=24, mat="steel", M=Mlk @ _T(0, 0, -0.075) @ _Rx(180))
    del r
    return mb


# =========================================================================================================== trípode
def star_knob(mb, M, r=0.02, h=0.016, lobes=5, mat="plastic"):
    """Perilla de estrella (lóbulos redondos) con buje, sobre z = 0 local, eje +Z."""
    def rm(i, a, rr, z):
        if i in (1, 2, 3):
            return rr * (0.8 + 0.2 * math.cos(lobes * a)) ** 0.6
        return rr
    lathe(mb, [(0.0, 0.0), (r * 0.55, 0.0), (r * 0.96, 0.0015), (r, h * 0.35), (r * 0.96, h * 0.8), (r * 0.6, h), (r * 0.45, h * 1.02),
               (0.0, h * 1.03)], seg=60, mat=mat, M=M, rmod=rm)


def led_flood(mb, M, w=0.3, h=0.22, d=0.07, fins=13, yoke=True, yoke_drop=0.05, tilt=0.0, knob=star_knob, hang=False):
    """Reflector LED de aluminio fundido: carcasa redondeada, bisel atornillado, cristal templado, módulo de LEDs con lentes,
    aletas de disipación reales en la espalda, prensaestopa, y horquilla de solera doblada con perillas de ajuste.
    M: centro de giro (eje X local de las perillas); el reflector mira a -Y local; la horquilla baja hasta -(h/2 + yoke_drop)
    (hang=True: la horquilla sube y el reflector cuelga de ella)."""
    Mb = M @ _Rx(tilt)
    Mf = Mb @ _Rx(90)                                      # plano XY = frente; +Z local = -Y (hacia donde alumbra)
    from kit.clinic_servicios import cup, rrframe
    cup(mb, Mf @ _T(0, 0, d / 2 - 0.0095) @ _Rx(180), w, h, d - 0.0095, 0.004, rc=0.022, re=0.01, mat="aluminium", nc=5, ne=3)
    rrframe(mb, Mf @ _T(0, 0, d / 2 - 0.0105), (0, 0, w + 0.004, h + 0.004, 0.023), (0, 0, w - 0.036, h - 0.036, 0.008), 0.0105,
            re_o=0.003, re_i=0.0025, n=5, ne=2, mat="aluminium")
    slab(mb, Mf @ _T(0, 0, d / 2 - 0.0075), w - 0.034, h - 0.034, 0.004, rc=0.009, re=0.0012, mat="glass", nc=3, ne=1)
    slab(mb, Mf @ _T(0, 0, d / 2 - 0.022), w - 0.007, h - 0.007, 0.004, rc=0.018, re=0.001, mat="sign_white", nc=4, ne=1)   # placa de LEDs
    nx, ny = 4, 3
    for i in range(nx):
        for j in range(ny):
            px = (i - (nx - 1) / 2) * (w - 0.08) / (nx - 1)
            py = (j - (ny - 1) / 2) * (h - 0.08) / (ny - 1)
            lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.003), (0.013, 0.006), (0.007, 0.0085), (0.0, 0.009)], seg=32, mat="plastic",
                  M=Mf @ _T(px, py, d / 2 - 0.0185))
    for (u, v) in [(sx * (w / 2 - 0.009), sy * (h / 2 - 0.009)) for sx in (-1, 1) for sy in (-1, 1)] + \
                  [(0.0, sy * (h / 2 - 0.009)) for sy in (-1, 1)]:
        lathe(mb, [(0.0, -0.0003), (0.0032, -0.0003), (0.0032, 0.0012), (0.0024, 0.0019), (0.0, 0.002)], seg=16, mat="steel",
              M=Mf @ _T(u, v, d / 2))
    Mr = Mf @ _T(0, 0, -d / 2 + 0.002)                    # aletas en la espalda (hacia +Y local)
    for k in range(fins):
        x = -w / 2 + 0.03 + k * (w - 0.06) / (fins - 1)
        pslab_fin(mb, Mr @ _T(x, 0, 0), h - 0.03, 0.028)
    lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.011, 0.008), (0.0095, 0.012), (0.0095, 0.018), (0.0065, 0.022), (0.0, 0.022)], seg=24,
          mat="plastic", M=Mb @ _T(0.06, 0.0, -h / 2 + 0.004) @ _Rx(180))  # prensaestopa
    if yoke:
        yw = w / 2 + 0.014
        sg = 1.0 if hang else -1.0
        zy = sg * (h / 2 + yoke_drop)
        path = fillet([(-yw, 0.0, 0.0), (-yw, 0.0, zy), (yw, 0.0, zy), (yw, 0.0, 0.0)], 0.02, 6)
        path = [tuple(M @ Vector(p)) for p in [(-yw, 0.0, -sg * 0.03)] + path[1:-1] + [(yw, 0.0, -sg * 0.03)]]
        sweep_frame(mb, rr_profile(0.005, 0.03, 0.0022, n=3), path, "steel", up=M.to_3x3() @ Vector((0, 1, 0)))
        for sx in (-1, 1):
            Mk = M @ _T(sx * (yw + 0.0025), 0, 0) @ _Ry(90 * sx)
            lathe(mb, [(0.0, -0.0175), (0.017, -0.0175), (0.017, -0.0042), (0.0, -0.0042)], seg=32, mat="aluminium", M=Mk)  # maza
            knob(mb, Mk @ _T(0, 0, -0.0004), r=0.022, h=0.018, mat="plastic")
    return Mb


def pslab_fin(mb, M, L, dep, t=0.0026):
    """Aleta de disipación: lámina vertical de largo L (Z local del marco del cuerpo = vertical), que sale `dep` hacia +Y local
    con canto exterior redondo y extremos achaflanados."""
    from kit.clinic_servicios import pslab
    P = [(-L / 2, 0.0), (L / 2, 0.0), (L / 2 - 0.006, dep), (-L / 2 + 0.006, dep)]
    R = Matrix(((0, 0, -1, 0), (1, 0, 0, 0), (0, -1, 0, 0), (0, 0, 0, 1)))   # x -> vertical, y -> hacia atrás, z -> lateral
    pslab(mb, M @ R @ _T(0, 0, -t / 2), [(p[0], p[1]) for p in P], [0.001, 0.001, 0.003, 0.003], t, re=t * 0.45, mat="aluminium",
          n=2, ne=1)


def floodlight_tripod(seed=0):
    """Trípode de iluminación de obra con dos reflectores LED (tipo trípode de doble cabezal: 1,75–1,9 m, huella de patas
    ~0,8–1,2 m; Defender LEDDF1200, Luceco, Draper 4400 lm): columna telescópica de aluminio Ø 35 / Ø 28 con collarín y perilla
    de apriete, cabeza de patas de fundición con 3 horquillas y pernos, patas Ø 22 con regatones de hule articulados, collarín
    deslizable con perilla y tirantes de solera remachados, barra en T con conexión de abrazadera, dos reflectores LED
    (carcasa redondeada con aletas reales, bisel atornillado, cristal, lentes, horquilla de solera doblada y perillas de
    estrella), caja de conexiones con prensaestopas, cables con caída y cinchos, cable al piso enrollado en vueltas sueltas y
    clavija. Origen: centro de las patas."""
    r = rng(seed)
    mb = MBX()
    zh = 0.585                                             # pernos de las patas
    zt = 1.84                                              # barra en T
    # ---- columna telescópica
    lathe(mb, [(0.0, 0.16), (0.0175, 0.16), (0.0175, 1.27), (0.0, 1.27)], seg=32, mat="aluminium")
    lathe(mb, [(0.0, 1.2), (0.014, 1.2), (0.014, zt - 0.03), (0.0, zt - 0.03)], seg=32, mat="aluminium")
    lathe(mb, [(0.0145, 1.255), (0.021, 1.255), (0.0225, 1.26), (0.0225, 1.3), (0.021, 1.305), (0.0145, 1.305)], seg=32, mat="plastic",
          closed=True)                                     # collarín del tramo
    mb.cyl((0.02, 0, 1.282), (0.046, 0, 1.282), 0.004, seg=SEG_T, mat="steel")
    star_knob(mb, _T(0.046, 0, 1.282) @ _Ry(90), r=0.016, h=0.014)
    lathe(mb, [(0.0, 0.155), (0.0185, 0.155), (0.019, 0.165), (0.0, 0.166)], seg=32, mat="rubber")   # tapón inferior
    # ---- cabeza de patas: cuerpo de fundición con tres horquillas
    lathe(mb, [(0.0172, zh - 0.05), (0.03, zh - 0.05), (0.034, zh - 0.044), (0.034, zh + 0.03), (0.03, zh + 0.036), (0.0172, zh + 0.036)],
          seg=48, mat="aluminium", closed=True)
    mb.cyl((0.033, 0, zh + 0.0), (0.05, 0, zh + 0.0), 0.004, seg=SEG_T, mat="steel")
    star_knob(mb, _T(0.05, 0, zh) @ _Ry(90), r=0.015, h=0.013)
    feet = []
    for k in range(3):
        a = math.radians(90 + 120 * k + float(r.uniform(-3, 3)))
        ca, sa = math.cos(a), math.sin(a)
        piv = Vector((0.046 * ca, 0.046 * sa, zh))
        foot = Vector((0.62 * ca, 0.62 * sa, 0.03))
        feet.append((a, piv, foot))
        Mc = face_M(piv, (ca, sa, 0))                       # horquilla (dos orejas) + perno con tuerca
        for e in (-1, 1):
            rbox(mb, (e * 0.0125 - 0.003, -0.015, -0.03), (e * 0.0125 + 0.003, 0.015, 0.012), "aluminium", r=0.0028, m=Mc)
        Mpin = Mc @ _T(0, 0, 0.0)
        mb.cyl(Mpin @ Vector((-0.019, 0, 0)), Mpin @ Vector((0.019, 0, 0)), 0.003, seg=16, mat="steel")
        from kit.clinic_servicios import hexnut
        hexnut(mb, Mpin @ _T(0.0155, 0, 0) @ _Ry(90), s=0.008, h=0.005, mat="steel")
        lathe(mb, [(0.0, 0.0), (0.0055, 0.0), (0.0055, 0.0015), (0.003, 0.0028), (0.0, 0.003)], seg=16, mat="steel",
              M=Mpin @ _T(-0.0155, 0, 0) @ _Ry(-90))
        # pata con ojo en la horquilla y regatón articulado
        d = (foot - piv).normalized()
        lathe(mb, [(0.0, -0.012), (0.011, -0.012), (0.011, (foot - piv).length - 0.02), (0.0, (foot - piv).length - 0.02)], seg=24,
              mat="aluminium", M=face_M(piv, d, up=(0, 0, 1)))
        Mft = face_M(foot, d)
        lathe(mb, [(0.0, -0.035), (0.0125, -0.035), (0.0125, 0.0), (0.0, 0.0)], seg=24, mat="steel", M=Mft)
        mb.cyl(Mft @ Vector((-0.016, 0, 0.004)), Mft @ Vector((0.016, 0, 0.004)), 0.0035, seg=16, mat="steel")
        lathe(mb, [(0.0, 0.0), (0.028, 0.0), (0.03, 0.004), (0.03, 0.012), (0.024, 0.02), (0.016, 0.026), (0.0, 0.027)], seg=40,
              mat="rubber", M=_T(foot.x, foot.y, -0.0005))   # zapata de hule
    # ---- collarín deslizable con perilla y tirantes de solera
    zc_ = 0.31
    lathe(mb, [(0.0172, zc_ - 0.03), (0.029, zc_ - 0.03), (0.032, zc_ - 0.026), (0.032, zc_ + 0.026), (0.029, zc_ + 0.03),
               (0.0172, zc_ + 0.03)], seg=48, mat="aluminium", closed=True)
    mb.cyl((0.0, -0.03, zc_), (0.0, -0.05, zc_), 0.004, seg=SEG_T, mat="steel")
    star_knob(mb, _T(0, -0.05, zc_) @ _Rx(90), r=0.015, h=0.013)
    for (a, piv, foot) in feet:
        ca, sa = math.cos(a), math.sin(a)
        p0 = Vector((0.04 * ca, 0.04 * sa, zc_))
        p1 = piv.lerp(foot, 0.42) - Vector((0, 0, 0.0))
        side = Vector((-sa, ca, 0.0))
        for e in (-1, 1):
            q0, q1 = p0 + side * e * 0.0125, p1 + side * e * 0.0125
            sweep_frame(mb, rr_profile(0.0035, 0.014, 0.0015, n=2), [tuple(q0), tuple(q1)], "steel", up=(0, 0, 1))
        for (pp, rr_) in ((p0, 0.0), (p1, 0.0)):
            mb.cyl(pp - side * 0.017, pp + side * 0.017, 0.0028, seg=16, mat="steel")
            for e in (-1, 1):
                lathe(mb, [(0.0, 0.0), (0.0048, 0.0), (0.0048, 0.0012), (0.003, 0.0024), (0.0, 0.0026)], seg=16, mat="steel",
                      M=face_M(pp + side * e * 0.017, side * e))
        Mlug = face_M(p0 - Vector((0.008 * ca, 0.008 * sa, 0)), (ca, sa, 0))
        rbox(mb, (-0.0085, -0.01, -0.008), (0.0085, 0.01, 0.016), "aluminium", r=0.003, m=Mlug)
        Mlg = face_M(p1, (foot - piv).normalized())
        lathe(mb, [(0.0, -0.012), (0.0135, -0.012), (0.0135, 0.012), (0.0, 0.012)], seg=24, mat="steel", M=Mlg)
    # ---- barra en T con conexión, reflectores
    Mtee = _T(0, 0, zt)
    lathe(mb, [(0.0, -0.075), (0.0185, -0.075), (0.0205, -0.07), (0.0205, 0.014), (0.0, 0.014)], seg=32, mat="aluminium", M=Mtee)
    lathe(mb, [(0.0, -0.035), (0.021, -0.035), (0.021, 0.035), (0.0, 0.035)], seg=40, mat="aluminium", M=Mtee @ _Ry(90))
    mb.cyl(Mtee @ Vector((0, -0.02, -0.05)), Mtee @ Vector((0, -0.044, -0.05)), 0.004, seg=SEG_T, mat="steel")
    star_knob(mb, Mtee @ _T(0, -0.044, -0.05) @ _Rx(90), r=0.015, h=0.013)
    lathe(mb, [(0.0, -0.33), (0.0128, -0.33), (0.014, -0.325), (0.014, 0.325), (0.0128, 0.33), (0.0, 0.33)], seg=32, mat="steel",
          M=Mtee @ _Ry(90))
    for e in (-1, 1):
        lathe(mb, [(0.0, 0.0), (0.0148, 0.0), (0.0148, 0.008), (0.012, 0.012), (0.0, 0.013)], seg=32, mat="rubber",
              M=Mtee @ _T(e * 0.328, 0, 0) @ _Ry(90 * e))
    heads = []
    for sx in (-1, 1):
        x = sx * 0.22
        Mh = _T(x, 0, zt + 0.014 + 0.11 + 0.035) @ _Rz(sx * 12.0)
        led_flood(mb, Mh, w=0.3, h=0.22, d=0.07, fins=13, yoke_drop=0.035, tilt=15.0)
        lathe(mb, [(0.0, -0.002), (0.016, -0.002), (0.016, 0.006), (0.0, 0.006)], seg=32, mat="steel", M=_T(x, 0, zt + 0.0125))
        from kit.clinic_servicios import hexnut
        hexnut(mb, _T(x, 0, zt + 0.0162), s=0.017, h=0.008, mat="steel")
        heads.append(Mh)
    # ---- caja de conexiones, cables con caída y cinchos, cable al piso enrollado y clavija
    Mjb = _T(0, 0.012, zt - 0.17)
    rbox(mb, (-0.055, 0.0, -0.06), (0.055, 0.06, 0.06), "plastic", r=0.008, m=Mjb)
    rbox(mb, (-0.05, 0.059, -0.055), (0.05, 0.064, 0.055), "plastic", r=0.004, m=Mjb)
    for (u, v) in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        lathe(mb, [(0.0, -0.0003), (0.0035, -0.0003), (0.0035, 0.0012), (0.0025, 0.002), (0.0, 0.0021)], seg=16, mat="steel",
              M=Mjb @ _T(u * 0.043, 0.064, v * 0.043) @ _Rx(-90))
    for e in (-1, 1):                                      # abrazaderas de la caja a la columna
        with mb.soft():
            torus(mb, _T(0, 0, zt - 0.17 + e * 0.04), 0.0155, 0.0025, mat="steel", n=32, seg=SEG_W)
    glands = []
    for e in (-1, 0, 1):
        Mg_ = Mjb @ _T(e * 0.032, 0.035, -0.06) @ _Rx(180)
        lathe(mb, [(0.0, -0.002), (0.009, -0.002), (0.009, 0.006), (0.0075, 0.009), (0.0075, 0.015), (0.0055, 0.019), (0.0, 0.019)],
              seg=24, mat="plastic", M=Mg_)
        glands.append(Mg_ @ Vector((0, 0, 0.018)))
    for sx, gl in ((-1, glands[0]), (1, glands[2])):
        Mh = heads[0 if sx < 0 else 1]
        g = Mh @ _Rx(15.0) @ Vector((0.06, 0.0, -0.11 - 0.02))
        pts = [tuple(gl), tuple(gl + Vector((0, 0.005, -0.05))), (sx * 0.09, 0.05, zt - 0.27), (sx * 0.2, 0.06, zt - 0.12),
               tuple(g + Vector((0, 0.0, -0.06))), tuple(g)]
        tube_path(mb, fillet(pts, 0.05, 4), 0.004, seg=SEG_T, mat="cable", caps=True)
    gm = glands[1]
    down = [tuple(gm), tuple(gm + Vector((0, 0.004, -0.06))), (0.0, 0.026, zt - 0.38), (0.0, 0.0255, 1.32), (0.0, 0.0225, 1.25),
            (0.0, 0.0225, 0.75), (0.006, 0.0225, zh + 0.06), (0.06, 0.03, 0.42), (0.2, 0.12, 0.13), (0.35, 0.22, 0.008),
            (0.62, 0.32, 0.0055)]
    tube_path(mb, fillet(down, 0.06, 5), 0.0045, seg=SEG_T, mat="cable", caps=True)
    for z, rin in ((1.05, 0.0172), (0.8, 0.0172), (zt - 0.5, 0.0137)):   # cinchos de velcro
        lathe(mb, [(rin, -0.012), (rin + 0.0096, -0.012), (rin + 0.0103, -0.009), (rin + 0.0103, 0.009), (rin + 0.0096, 0.012),
                   (rin, 0.012)], seg=32, mat="fabric", M=_T(0, 0.004, z), closed=True)
    # rollo de cable: vueltas sueltas que se encaballan sobre el piso
    cx, cy = 0.9, 0.42
    pts = [(0.62, 0.32, 0.0055)]
    nturn = 3
    for k in range(1, nturn * 24 + 1):
        a = PI + 2 * PI * k / 24
        rr_ = 0.15 + 0.012 * math.sin(k * 0.7) + 0.01 * (k / 24)
        zz = 0.0045 + 0.009 * (k / (nturn * 24)) + 0.003 * max(0.0, math.sin(a * 1.0 + k * 0.05))
        pts.append((cx + rr_ * math.cos(a), cy + rr_ * math.sin(a) * 0.92, zz))
    end = Vector(pts[-1])
    tail = [tuple(end), tuple(end + Vector((0.06, -0.05, -0.008))), tuple(end + Vector((0.14, -0.06, -0.011)))]
    tube_path(mb, fillet(pts[:-1] + tail, 0.03, 3), 0.0045, seg=SEG_T, mat="cable", caps=True)
    tip = Vector(tail[-1])
    dd = (Vector(tail[-1]) - Vector(tail[-2])).normalized()
    Mpl = face_M(tip + Vector((0, 0, 0.012)), dd)
    lathe(mb, [(0.0, -0.035), (0.0055, -0.035), (0.0075, -0.025), (0.011, -0.012), (0.017, 0.0), (0.019, 0.004), (0.019, 0.032),
               (0.017, 0.036), (0.0, 0.036)], seg=32, mat="rubber", M=Mpl,
          rmod=lambda i, a, rr, z: rr - 0.0009 * (math.cos(10 * a) > 0.5) if i in (5, 6) else rr)
    for e in (-1, 1):
        mb.cyl(Mpl @ Vector((e * 0.0095, 0, 0.034)), Mpl @ Vector((e * 0.0095, 0, 0.052)), 0.0024, seg=16, mat="brass")
    return mb


# ============================================================================================================ torre de luz
def trailer_wheel(mb, M, R=0.31, w=0.165, rim_mat="paint_tan", seed=0):
    """Rueda de remolque 165R14 (Ø nominal 626 × 165 mm; radio bajo carga ~310 mm): llanta con costados abombados, protector de ceja, hombros redondos y dibujo
    de tacos (dos canales circunferenciales de 8 mm, ranuras laterales alternadas en los hombros y laminillas en la costilla
    central, paredes verticales reales), rin de acero de disco de 14" con ceja, plato rehundido, 6 ventanas de ventilación,
    5 birlos con tuerca cónica (círculo de 114,3 mm), tapón central y válvula. Eje = Z local (+Z hacia afuera)."""
    zt_ = [-0.061, -0.057, -0.046, -0.034, -0.0245, -0.0235, -0.0165, -0.0155, -0.008, 0.0, 0.008, 0.0155, 0.0165, 0.0235, 0.0245,
           0.034, 0.046, 0.057, 0.061]
    side = [(0.18, -0.069), (0.186, -0.075), (0.196, -0.0785), (0.212, -0.0805), (0.235, -0.0825), (0.258, -0.0828), (0.278, -0.0805),
            (0.292, -0.0755), (0.3015, -0.0695), (0.3065, -0.0645)]
    prof = side + [(R, z) for z in zt_] + [(r_, -z) for (r_, z) in reversed(side)]
    ntr = len(side)
    npitch = 26
    fr = [0.0, 0.18, 0.36, 0.42, 0.45, 0.55, 0.58, 0.64, 0.82]
    angs = [2 * PI * (p + f) / npitch for p in range(npitch) for f in fr]

    def depth(j, k):
        if j < ntr or j >= ntr + len(zt_):
            return 0.0
        z = zt_[j - ntr]
        f = fr[k % len(fr)]
        if 0.0165 <= abs(z) <= 0.0235:
            return 0.008
        if abs(z) >= 0.0245:
            ff = f if z < 0 else (f + 0.5) % 1.0
            return 0.008 if 0.44 <= ff <= 0.56 else 0.0
        return 0.0035 if (0.44 <= (f + 0.25) % 1.0 <= 0.56) else 0.0
    G = []
    for k, a in enumerate(angs):
        ca, sa = math.cos(a), math.sin(a)
        G.append([mb.bm.verts.new(M @ Vector(((r_ - depth(j, k)) * ca, (r_ - depth(j, k)) * sa, z))) for j, (r_, z) in enumerate(prof)])
    n = len(angs)
    for k in range(n):
        A, B = G[k], G[(k + 1) % n]
        for j in range(len(prof) - 1):
            mb.face([A[j], B[j], B[j + 1], A[j + 1]], "rubber")
        mb.face([A[-1], B[-1], B[0], A[0]], "rubber")      # base de las cejas (oculta por el rin): sólido cerrado
    # rin de disco: ceja, asiento, plato rehundido con ventanas y maza
    lathe(mb, [(0.177, -0.071), (0.193, -0.074), (0.196, -0.068), (0.19, -0.062), (0.178, -0.06), (0.172, -0.05), (0.172, 0.05),
               (0.178, 0.06), (0.19, 0.062), (0.196, 0.068), (0.193, 0.074), (0.177, 0.071), (0.165, 0.058), (0.16, 0.035),
               (0.15, 0.03), (0.125, 0.028), (0.105, 0.036), (0.085, 0.04), (0.06, 0.04), (0.045, 0.036), (0.034, 0.036), (0.034, 0.02),
               (0.0, 0.02)], seg=72, mat=rim_mat, M=M)
    for k in range(6):                                     # ventanas: cejas embutidas con fondo oscuro
        a = 2 * PI * (k + 0.5) / 6
        Mv = M @ _T(0.135 * math.cos(a), 0.135 * math.sin(a), 0.0285) @ _Rz(math.degrees(a))
        slab(mb, Mv @ _T(0, 0, -0.004), 0.034, 0.022, 0.0045, rc=0.0108, re=0.0015, mat="cable", nc=5, ne=1)
        torus_pts = [Mv @ Vector((x, y, 0.0006)) for (x, y) in rr_pts(0.04, 0.028, 0.0138, 6)]
        _loop_tube(mb, torus_pts, 0.0022, SEG_T, rim_mat, Mv.to_3x3() @ Vector((0, 0, 1)))
    for k in range(5):                                     # birlos y tuercas cónicas
        a = 2 * PI * k / 5
        Mn = M @ _T(0.05715 * math.cos(a), 0.05715 * math.sin(a), 0.0398)
        lathe(mb, [(0.0, 0.0), (0.0105, 0.0), (0.0105, 0.004), (0.0, 0.004)], seg=24, mat="steel", M=Mn)
        from kit.clinic_servicios import hexnut
        hexnut(mb, Mn @ _T(0, 0, 0.0038), s=0.019, h=0.011, mat="steel")
        lathe(mb, [(0.0, 0.014), (0.006, 0.014), (0.006, 0.02), (0.0045, 0.022), (0.0, 0.0222)], seg=16, mat="steel", M=Mn)
    lathe(mb, [(0.0, 0.019), (0.031, 0.019), (0.031, 0.034), (0.027, 0.041), (0.016, 0.045), (0.0, 0.046)], seg=48, mat="steel", M=M)
    Mvs = M @ _T(0.168, 0.0, 0.035) @ _Ry(-20)            # válvula
    lathe(mb, [(0.0, -0.004), (0.0055, -0.004), (0.0055, 0.008), (0.0038, 0.012), (0.0038, 0.022), (0.0045, 0.024), (0.0045, 0.032),
               (0.0, 0.033)], seg=16, mat="rubber", M=Mvs)


def leaf_spring(mb, x0, x1, y, z_bot, n=4, arch=0.045, mat="steel"):
    """Muelle de hojas: n hojas de 60 × 8 mm de largo decreciente con arco, ojo enrollado en la hoja maestra, abrazadera de
    alineación; corre de x0 a x1 en el plano y, panza sobre z_bot."""
    L = x1 - x0
    xc = (x0 + x1) / 2
    for i in range(n):
        Li = L * (1 - 0.22 * i) if i else L
        pts = []
        for k in range(25):
            t = -1 + 2 * k / 24
            x = xc + t * Li / 2
            z = z_bot + 0.008 * (n - 1 - i) + 0.004 + arch * (t * Li / L) ** 2
            pts.append((x, y, z))
        sweep_frame(mb, rr_profile(0.06, 0.0085, 0.0025, n=2), pts, mat, up=(0, 0, 1))
    for e in (-1, 1):                                      # ojos de la hoja maestra
        xe = xc + e * L / 2
        ze = z_bot + 0.008 * (n - 1) + 0.004 + arch
        torus(mb, _T(xe + e * 0.004, y, ze + 0.0125) @ _Rx(90), 0.0125, 0.0045, mat=mat, n=20, seg=SEG_T, a0=(PI * 1.5 if e > 0 else -PI * 0.5),
              a1=(PI * 1.5 if e > 0 else -PI * 0.5) + 2 * PI * 0.92)
    ztop_ = z_bot + 0.008 * (n - 1) + 0.004 + arch * 0.36 + 0.00425
    rbox(mb, (xc + L * 0.3 - 0.012, y - 0.036, z_bot - 0.002), (xc + L * 0.3 + 0.012, y + 0.036, ztop_ + 0.004), mat, r=0.002)   # grapa


def screw_jack(mb, x, y, z_top, crank_dir=(1, 0, 0), foot=True, mat="paint_tan"):
    """Gato de estabilizador: tubo exterior cuadrado 70 con tapa, husillo con manivela en Z y perilla giratoria, tubo interior
    con pasador de altura y zapata giratoria de Ø 220 con rótula. Del piso a z_top."""
    rtube(mb, (x, y, 0.3), (x, y, z_top), 0.07, 0.07, mat, up=(1, 0, 0), r=0.006)
    slab(mb, _T(x, y, z_top - 0.002), 0.082, 0.082, 0.008, rc=0.008, re=0.002, mat=mat, nc=3, ne=1)
    rtube(mb, (x, y, 0.07), (x, y, 0.34), 0.058, 0.058, "galvanized", up=(1, 0, 0), r=0.005)
    mb.cyl((x - 0.045, y, 0.33), (x + 0.045, y, 0.33), 0.006, seg=SEG_T, mat="steel")        # pasador de altura
    with mb.soft():
        torus(mb, _T(x + 0.04, y, 0.33 - 0.0135) @ _Rx(90), 0.014, 0.0022, mat="steel", n=24, seg=SEG_W)
    lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.011, 0.035), (0.0, 0.035)], seg=24, mat="steel", M=_T(x, y, z_top + 0.006))
    d = Vector(crank_dir).normalized()
    p0 = Vector((x, y, z_top + 0.035))
    crank = [tuple(p0), tuple(p0 + Vector((0, 0, 0.03))), tuple(p0 + Vector((0, 0, 0.03)) + d * 0.16),
             tuple(p0 + Vector((0, 0, 0.11)) + d * 0.16)]
    tube_path(mb, fillet(crank, 0.025, 6), 0.0075, seg=SEG_T, mat="steel", caps=True)
    lathe(mb, [(0.0, 0.0), (0.0125, 0.0), (0.0135, 0.01), (0.0135, 0.07), (0.012, 0.08), (0.0, 0.081)], seg=24, mat="plastic",
          M=_T(*(p0 + Vector((0, 0, 0.1)) + d * 0.16)))
    if foot:
        lathe(mb, [(0.0, 0.055), (0.024, 0.055), (0.024, 0.08), (0.0, 0.08)], seg=24, mat="steel", M=_T(x, y, 0.0))
        lathe(mb, [(0.0, 0.032), (0.026, 0.034), (0.03, 0.045), (0.024, 0.058), (0.0, 0.061)], seg=32, mat="steel", M=_T(x, y, 0.0))
        lathe(mb, [(0.0, -0.0005), (0.108, -0.0005), (0.11, 0.004), (0.108, 0.012), (0.06, 0.03), (0.0, 0.034)], seg=64, mat="steel",
              M=_T(x, y, 0.0))


def light_tower(seed=0):
    """Torre de iluminación sobre remolque de un eje (tipo MOSA TF 4 × LED, mástil de 9 m: 3920 × 1410 × 2240 mm cerrada,
    9000 mm de altura máxima, 790 kg en seco, 4 estabilizadores, viento 80 km/h; manelservice / mygenerator, fichas TF).
    Remolque: largueros de PTR 100 × 60 con travesaños y lanza en A soldada con cartabones, argolla (lunette) militar Ø 76,2
    (VG 74059 / STANAG 4101),
    cadenas de seguridad con gancho, gato de apoyo lateral con manivela; eje de tubo Ø 70 sobre muelles de hojas con
    abrazaderas en U, colgadores y grilletes; ruedas 165R14 con dibujo y rin de disco con birlos; salpicaderas con cejas
    enrolladas y soportes; tanque de combustible bajo el chasís con flejes; 4 estabilizadores telescópicos con pasador y gato
    de husillo con manivela y zapata giratoria. Gabinete del generador con VANOS REALES: 2 puertas por costado (una con
    persianas troqueladas), bisagras de piano, cerrojos de compresión, rejilla de álabes en +X, tablero de control empotrado en
    -X (controlador, paro de emergencia, interruptor de llave, 4 breakers de lámparas, botón de mástil, horómetro, voltímetro,
    contactos con tapa), tapón de combustible con cadena, escape con tapa de charnela, ojo de izaje central y tapa con
    nervios. Mástil telescópico de 4 tramos (PTR galvanizado 160/135/110/85 con collarines atornillados, cojinetes de nylon,
    poleas y cable de acero), malacate con tambor, trinquete y manivela, cable de potencia en espiral alrededor del mástil,
    y cabezal giratorio con 2 barras y 4 reflectores LED colgados (aletas reales, horquillas y perillas). Largo en X (lanza
    hacia -X), tablero hacia -X. Origen: centro del eje en el piso."""
    r = rng(seed)
    paint = "paint_tan"
    mb = MBX()
    zc = 0.47                                              # eje de los largueros
    # ------------------------------------------------------------------ chasís, lanza, argolla, cadenas y gato
    for sy in (-1, 1):
        rtube(mb, (-1.05, sy * 0.48, zc), (1.4, sy * 0.48, zc), 0.06, 0.1, paint, up=(0, 0, 1), r=0.006)
        rtube(mb, (-1.0, sy * 0.46, zc), (-2.0, sy * 0.035, zc), 0.06, 0.08, paint, up=(0, 0, 1), r=0.006)
        Mg = _T(-1.12, sy * 0.4, zc + 0.04)
        from kit.clinic_servicios import pslab
        pslab(mb, Mg @ _T(0, 0, -0.003), [(0.0, -sy * 0.0), (0.14, 0.0), (-0.12, -sy * 0.2)] if sy > 0 else [(0.0, 0.0), (-0.12, 0.2), (0.14, 0.0)],
              [0.004, 0.01, 0.01], 0.006, re=0.0015, mat=paint, n=3, ne=1)            # cartabón de la unión lanza-larguero
        weld_bead(mb, [(-1.05, sy * 0.45, zc + 0.04), (-1.05, sy * 0.51, zc + 0.04)], r=0.003, mat=paint)
    for x in (-1.0, -0.3, 0.45, 1.375):
        rtube(mb, (x, -0.45, zc), (x, 0.45, zc), 0.05, 0.08, paint, up=(0, 0, 1), r=0.005)
    slab(mb, _T(-2.02, 0, zc - 0.045), 0.16, 0.13, 0.09, rc=0.012, re=0.005, mat=paint, nc=4, ne=2)        # cabeza de la lanza
    rtube(mb, (-2.26, 0, zc), (-1.955, 0, zc), 0.07, 0.07, paint, up=(0, 0, 1), r=0.006)
    slab(mb, _T(-2.24, 0, zc) @ _Ry(90) @ _T(0, 0, -0.008), 0.11, 0.11, 0.016, rc=0.012, re=0.003, mat=paint, nc=4, ne=2)
    for (u, v) in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        bolt(mb, face_M((-2.255, u * 0.038, zc + v * 0.038), (-1, 0, 0)), d=0.012, washer=True, mat="steel")
    lathe(mb, [(0.0, -0.06), (0.024, -0.06), (0.024, 0.06), (0.0, 0.06)], seg=SEG, mat="steel", M=_T(-2.25, 0, zc) @ _Ry(-90))
    torus(mb, _T(-2.33, 0, zc), 0.058, 0.02, mat="steel", n=48, seg=SEG_T)                # argolla (lunette) horizontal
    for sy in (-1, 1):                                     # cadenas de seguridad con gancho
        hook0 = Vector((-2.12, sy * 0.038, zc - 0.03))
        torus(mb, _T(*hook0) @ _Rx(90), 0.01, 0.004, mat="steel", n=20, seg=SEG_T)      # ojo soldado a la lanza
        tail = [hook0 + Vector((0.0, 0.0, -0.011)), Vector((-2.16, sy * 0.07, zc - 0.13)), Vector((-2.24, sy * 0.085, zc - 0.21)),
                Vector((-2.27, sy * 0.08, zc - 0.21)), Vector((-2.3, sy * 0.07, zc - 0.17))]
        P = [tuple(p) for p in tail]
        small_chain(mb, P, link=0.04, wire=0.0042, mat="steel", seed=seed + (3 if sy > 0 else 4))
        hk = Vector(P[-1])                                 # gancho colgando del último eslabón
        torus(mb, _T(*(hk + Vector((0.0, 0, -0.022)))) @ _Rx(90), 0.022, 0.006, mat="steel", n=24, seg=SEG_T, a0=-PI * 0.75,
              a1=PI * 0.75)
    # gato de apoyo lateral con manivela y zapata (por fuera del brazo de la lanza)
    xj, yj = -1.72, 0.222
    Mj = _T(xj, yj, 0.0)
    rbox(mb, (-0.045, -0.072, zc - 0.05), (0.045, -0.026, zc + 0.05), paint, r=0.006, m=Mj)              # abrazadera
    for e in (-1, 1):
        bolt(mb, Mj @ _T(e * 0.03, -0.05, zc + 0.05), d=0.012, washer=True, mat="steel")
    lathe(mb, [(0.0, zc - 0.33), (0.031, zc - 0.33), (0.031, zc + 0.24), (0.026, zc + 0.255), (0.0, zc + 0.256)], seg=SEG, mat=paint, M=Mj)
    lathe(mb, [(0.0, 0.025), (0.025, 0.025), (0.025, zc - 0.31), (0.0, zc - 0.31)], seg=SEG, mat="galvanized", M=Mj)
    lathe(mb, [(0.0, 0.0), (0.075, 0.0), (0.076, 0.006), (0.07, 0.014), (0.03, 0.03), (0.0, 0.032)], seg=48, mat="steel", M=Mj)
    lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.045), (0.0, 0.045)], seg=24, mat="steel", M=Mj @ _T(0, 0, zc + 0.2) @ _Rx(-90))
    crank = [(0.0, 0.04, zc + 0.2), (0.0, 0.07, zc + 0.2), (0.14, 0.07, zc + 0.2), (0.14, 0.13, zc + 0.2)]
    tube_path(mb, [tuple(Mj @ Vector(p)) for p in fillet(crank, 0.025, 6)], 0.0075, seg=SEG_T, mat="steel", caps=True)
    lathe(mb, [(0.0, 0.0), (0.0125, 0.0), (0.0135, 0.01), (0.0135, 0.07), (0.012, 0.08), (0.0, 0.081)], seg=24, mat="plastic",
          M=Mj @ _T(0.14, 0.125, zc + 0.2) @ _Rx(-90))
    # ------------------------------------------------------------------ eje, muelles, ruedas, salpicaderas
    lathe(mb, [(0.0, -0.63), (0.035, -0.63), (0.035, 0.63), (0.0, 0.63)], seg=48, mat="steel", M=_T(0, 0, 0.31) @ _Rx(-90))
    for sy in (-1, 1):
        y = sy * 0.48
        leaf_spring(mb, -0.42, 0.42, y, 0.345, n=4, arch=0.032, mat="steel")
        for (xe, kind) in ((-0.42, "fixed"), (0.42, "shackle")):     # colgador fijo y grillete
            ze = 0.345 + 0.024 + 0.004 + 0.032 + 0.0125
            for e in (-1, 1):
                if kind == "fixed":
                    rbox(mb, (xe - 0.03, y + e * 0.036 - 0.004, ze - 0.02), (xe + 0.01, y + e * 0.036 + 0.004, zc - 0.045), paint, r=0.002)
                else:
                    rbox(mb, (xe - 0.006 + 0.012, y + e * 0.036 - 0.004, ze - 0.016), (xe + 0.018 + 0.012, y + e * 0.036 + 0.004, zc - 0.03),
                         "steel", r=0.003)
            px = xe if kind == "fixed" else xe + 0.024
            mb.cyl((px, y - 0.045, ze), (px, y + 0.045, ze), 0.007, seg=SEG, mat="steel")
            from kit.clinic_servicios import hexnut
            hexnut(mb, _T(px, y + 0.044, ze) @ _Rx(-90), s=0.019, h=0.01, mat="steel")
            if kind != "fixed":
                rbox(mb, (xe - 0.01, y - 0.05, zc - 0.07), (xe + 0.05, y + 0.05, zc - 0.045), paint, r=0.004)
                mb.cyl((px, y - 0.045, zc - 0.035 - 0.018), (px, y + 0.045, zc - 0.035 - 0.018), 0.007, seg=SEG, mat="steel")
        for e in (-1, 1):                                  # abrazaderas en U sobre el tubo del eje
            xu = e * 0.045
            up = [(xu, y - 0.04, 0.44), (xu, y - 0.04, 0.31)] + [(xu, y - 0.04 * math.cos(PI * k / 10), 0.31 - 0.04 * math.sin(PI * k / 10))
                                                               for k in range(1, 10)] + [(xu, y + 0.04, 0.31), (xu, y + 0.04, 0.44)]
            tube_path(mb, up, 0.0065, seg=SEG_T, mat="steel", caps=True)
            for sy2 in (-1, 1):
                bolt(mb, _T(xu, y + sy2 * 0.04, 0.4155), d=0.013, L=0.025, nut=True, mat="steel")
        rbox(mb, (-0.07, y - 0.055, 0.4), (0.07, y + 0.055, 0.416), "steel", r=0.003)
        trailer_wheel(mb, _T(0, sy * 0.7, 0.31) @ _Rx(-90 * sy), rim_mat=paint, seed=seed + sy)
        lathe(mb, [(0.0, -0.05), (0.07, -0.05), (0.075, -0.04), (0.075, 0.0), (0.06, 0.012), (0.0, 0.012)], seg=48, mat="steel",
              M=_T(0, sy * 0.635, 0.31) @ _Rx(-90 * sy))            # maza
        # salpicadera: lámina curva con cejas enrolladas y dos soportes a la caja
        arc = [(0.36 * math.cos(a), sy * 0.708, 0.31 + 0.36 * math.sin(a)) for a in np.linspace(PI * 0.97, PI * 0.03, 40)]
        sweep_frame(mb, [(-0.0012, -0.105), (0.0012, -0.105), (0.0012, 0.105), (-0.0012, 0.105)], arc, paint, up=(0, 1, 0))
        for e in (-1, 1):
            tube_path(mb, [(p[0], p[1] + e * 0.105, p[2]) for p in arc], 0.0042, seg=SEG_T, mat=paint, caps=True)
        for xb in (-0.25, 0.25):
            a = math.acos(max(-1.0, min(1.0, xb / 0.36)))
            zz = 0.31 + 0.36 * math.sin(a)
            rbox(mb, (xb - 0.015, sy * 0.6 - (0.0 if sy > 0 else 0.012), zz - 0.06), (xb + 0.015, sy * 0.6 + (0.012 if sy > 0 else 0.0), zz),
                 paint, r=0.003)
            sweep_frame(mb, rr_profile(0.03, 0.004, 0.0015, n=2), [(xb, sy * 0.603, zz - 0.05), (xb, sy * 0.66, zz - 0.002)], paint,
                        up=(1, 0, 0))
    # tanque de combustible bajo el chasís con flejes
    slab(mb, _T(-0.68, 0, 0.215), 0.56, 0.72, 0.19, rc=0.04, re=0.03, mat=paint, nc=6, ne=4)
    for xs_ in (-0.85, -0.51):
        path = [(xs_, -0.45, zc - 0.05), (xs_, -0.362, zc - 0.05), (xs_, -0.362, 0.21), (xs_, 0.362, 0.21), (xs_, 0.362, zc - 0.05),
                (xs_, 0.45, zc - 0.05)]
        sweep_frame(mb, rr_profile(0.04, 0.003, 0.0012, n=2), fillet(path, 0.035, 5), "steel", up=(1, 0, 0))
    lathe(mb, [(0.0, 0.0), (0.014, 0.0), (0.014, 0.006), (0.0, 0.006)], seg=6, mat="steel", M=_T(-0.68, 0.1, 0.216) @ _Rx(180))
    # ------------------------------------------------------------------ estabilizadores telescópicos con gato de husillo
    for (x, sy) in ((-0.95, -1), (-0.95, 1), (1.17, -1), (1.17, 1)):
        rtube(mb, (x, sy * 0.38, zc - 0.088), (x, sy * 0.76, zc - 0.088), 0.08, 0.08, paint, up=(0, 0, 1), r=0.006)
        for e in (-1, 1):
            weld_bead(mb, [(x + e * 0.042, sy * 0.45, zc - 0.05), (x + e * 0.042, sy * 0.51, zc - 0.05)], r=0.003, mat=paint)
        slab(mb, _T(x, sy * 0.76, zc - 0.09) @ _Rx(-90 * sy) @ _T(0, 0, -0.004), 0.092, 0.092, 0.008, rc=0.008, re=0.002, mat=paint, nc=3, ne=1)
        rtube(mb, (x, sy * 0.6, zc - 0.09), (x, sy * 0.975, zc - 0.09), 0.064, 0.064, "galvanized", up=(0, 0, 1), r=0.005)
        mb.cyl((x, sy * 0.72, zc - 0.09 + 0.055), (x, sy * 0.72, zc - 0.09 - 0.055), 0.0065, seg=SEG_T, mat="steel")
        torus(mb, _T(x, sy * 0.72, zc - 0.09 + 0.062) @ _Rx(90), 0.014, 0.0022, mat="steel", n=24, seg=SEG_W)
        screw_jack(mb, x, sy * 0.995, zc + 0.05, crank_dir=(1 if x > 0 else -1, 0, 0), mat=paint)
        rbox(mb, (x - 0.04, sy * 0.975 - 0.012, zc - 0.13), (x + 0.04, sy * 0.975 + 0.012, zc - 0.05), "galvanized", r=0.003)
    # ------------------------------------------------------------------ gabinete del generador con vanos reales
    zb = zc + 0.05
    Lh, Wh, Hh = 2.0, 1.2, 1.3
    xh = 0.1
    ops = []
    for f in ("-y", "+y"):
        for (a, b) in ((-0.86, -0.06), (0.06, 0.86)):
            ops.append((f, a, b, 0.22, 1.18, 0.035, "cable"))
    ops.append(("+x", -0.34, 0.34, 0.45, 1.05, 0.06, "cable"))
    ops.append(("-x", -0.36, 0.36, 0.55, 1.08, 0.07, paint))
    ops.append(("-x", 0.1, 0.42, 0.14, 0.44, 0.03, "cable"))
    frames = shell_box(mb, _T(xh, 0, zb), Lh, Wh, Hh - 0.04, 0.035, paint, ops, re=0.006, re0=0.003, ne=2, nc=6)
    slab(mb, _T(xh, 0, zb - 0.004), Lh + 0.008, Wh + 0.008, 0.045, rc=0.039, re=0.0025, mat=paint, nc=6, ne=2)
    pan_door(mb, _T(xh, 0, zb + Hh), Lh + 0.01, Wh + 0.01, paint, rc=0.04, t=0.0, re=0.024, ret=0.05, field=None, nc=8, ne=6,
             beads=[(x, 0.0, 0.05, Wh - 0.3, 0.0035) for x in (-0.3, 0.45)])
    for (y, nrm) in ((-Wh / 2 - 0.005, (0, -1, 0)), (Wh / 2 + 0.005, (0, 1, 0))):
        for x in np.linspace(xh - 0.92, xh + 0.92, 11):
            bolt(mb, face_M((x, y, zb + Hh - 0.027), nrm), d=0.006, washer=True, mat="steel")
            bolt(mb, face_M((x, y + (0.001 if y < 0 else -0.001), zb + 0.02), nrm), d=0.008, washer=True, mat="steel")
    for i, (Mo, ow, oh) in enumerate(frames[:4]):
        f = ops[i][0]
        left = ops[i][1] < 0
        outer_sign = (-1 if left else 1) * (1 if f == "-y" else -1)
        dw, dh = ow - 0.006, oh - 0.006
        if left:
            zf = pan_door(mb, Mo, dw, dh, paint, field=(0.035, 0.0025, 0.008, 0.012))
            for row in range(12):
                for col in (-1, 1):
                    louver_hood(mb, Mo @ _T(col * 0.152, 0.33 - row * 0.06, zf), 0.26, 0.034, hz=0.007, mat=paint)
        else:
            zf = pan_door(mb, Mo, dw, dh, paint, field=(0.035, 0.0025, 0.008, 0.012),
                          beads=[(0.0, v, dw - 0.16, 0.036, 0.003) for v in (-0.28, 0.0, 0.28)])
        piano_hinge(mb, Mo @ _T(outer_sign * (ow / 2), 0, 0.0) @ _Rz(0 if outer_sign > 0 else 180), dh - 0.03, mat=paint)
        for v in (0.0, 0.37):
            comp_latch(mb, Mo @ _T(-outer_sign * (dw / 2 - 0.066), v, zf - 0.0002), mat="steel", ang=90.0 if outer_sign < 0 else -90.0)
    Mo, ow, oh = frames[4]
    vane_grille(mb, Mo, ow, oh, paint, nb=15)
    Mo, ow, oh = frames[5]                                 # tablero de control empotrado (-X)
    _tower_panel(mb, Mo @ _T(0, 0, -0.07), ow, oh, paint, r)
    vz = oh / 2 + 0.012
    slab(mb, Mo @ _T(0, vz, 0.0) @ _Rx(-90) @ _T(0, -0.05, -0.0015), ow + 0.06, 0.1, 0.003, rc=(0.0, 0.0, 0.006, 0.006), re=0.0012,
         mat=paint, nc=3, ne=1)
    tube_path(mb, [tuple(Mo @ Vector((-ow / 2 - 0.03, vz - 0.001, 0.1))), tuple(Mo @ Vector((ow / 2 + 0.03, vz - 0.001, 0.1)))], 0.004,
              seg=SEG_T, mat=paint, caps=True)
    from kit.clinic_servicios import pslab
    for s_ in (-1, 1):
        pslab(mb, Mo @ _T(s_ * (ow / 2 + 0.027) - 0.0015, 0, 0) @ _Ry(90), [(0.0, vz + 0.0015), (-0.098, vz + 0.0015), (0.0, vz - 0.12)],
              [0.003, 0.006, 0.006], 0.003, re=0.0012, mat=paint, n=3, ne=1)
    Mo, ow, oh = frames[6]                                 # puerta de contactos
    zft = pan_door(mb, Mo, ow - 0.006, oh - 0.006, paint, field=(0.022, 0.002, 0.006, 0.008))
    piano_hinge(mb, Mo @ _T(0, oh / 2, 0) @ _Rz(90), ow - 0.03, mat=paint)
    comp_latch(mb, Mo @ _T(0, -oh / 2 + 0.056, zft - 0.0002), mat="steel", ang=180.0, L=0.06)
    panel_label(mb, Mo @ _T(0, 0.04, zft), "OUTLETS 230 V", 0.11, size=0.0095, h=0.018)
    # tapón de combustible con cadena y esténcil (frente -X, abajo a la izquierda)
    Me = face_M((xh - Lh / 2, 0, 0), (-1, 0, 0))
    Mfl = Me @ _T(0.3, zb + 0.3, 0.0)
    lathe(mb, [(0.0, -0.0003), (0.06, -0.0003), (0.06, 0.006), (0.056, 0.008), (0.0, 0.008)], seg=48, mat=paint, M=Mfl)
    lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.03), (0.0325, 0.032), (0.0325, 0.036), (0.0, 0.036)], seg=48, mat=paint, M=Mfl)
    lathe(mb, [(0.0, 0.034), (0.039, 0.034), (0.041, 0.037), (0.041, 0.054), (0.038, 0.058), (0.03, 0.061), (0.0, 0.062)], seg=72,
          mat="steel", M=Mfl, rmod=lambda i, a, rr, z: rr - 0.0018 * max(0.0, math.cos(12 * a)) ** 6 if i in (2, 3) else rr)
    rbox(mb, (-0.006, -0.088, -0.001), (0.006, -0.072, 0.012), "steel", r=0.002, m=Mfl)          # oreja de la cadena
    small_chain(mb, [tuple(Mfl @ Vector((0.0, -0.041, 0.044))), tuple(Mfl @ Vector((0.0, -0.068, 0.03))), tuple(Mfl @ Vector((0.0, -0.08, 0.008)))],
                link=0.011, wire=0.0011, seed=seed + 9)
    text_font(mb, "DIESEL", 0.034, 0.0005, "cable", Me @ _T(0.3, zb + 0.19, 0.0), font="stencil", res=2)
    # ------------------------------------------------------------------ techo: escape, ojo de izaje central, esténciles
    Mx_ = _T(xh - 0.6, -0.36, zb + Hh)
    lathe(mb, [(0.0, -0.002), (0.062, -0.002), (0.062, 0.006), (0.058, 0.009), (0.0, 0.009)], seg=48, mat="steel", M=Mx_)
    for k in range(6):
        a = 2 * PI * k / 6
        bolt(mb, Mx_ @ _T(0.05 * math.cos(a), 0.05 * math.sin(a), 0.009), d=0.006, washer=False, mat="steel")
    lathe(mb, [(0.034, 0.0), (0.038, 0.0), (0.038, 0.16), (0.0365, 0.162), (0.034, 0.162)], seg=48, mat="metal_rust", M=Mx_, closed=True)
    lathe(mb, [(0.0, 0.03), (0.0342, 0.03)], seg=48, mat="cable", M=Mx_, caps=False)
    Mrc = Mx_ @ _T(0.041, 0, 0.167) @ _Ry(-5)
    lathe(mb, [(0.0, 0.0035), (0.03, 0.0033), (0.042, 0.0022), (0.0445, 0.0), (0.0445, -0.004), (0.042, -0.0045), (0.0, -0.0045)],
          seg=48, mat="steel", M=Mrc @ _T(-0.041, 0, 0))
    mb.cyl(Mrc @ Vector((0.0, -0.012, -0.002)), Mrc @ Vector((0.0, 0.012, -0.002)), 0.0042, seg=SEG, mat="steel")
    rbox(mb, (-0.004, -0.008, -0.03), (0.006, 0.008, -0.0005), "steel", r=0.002, m=Mrc)
    lift_lug(mb, _T(xh + 0.12, 0.0, zb + Hh - 0.001), w=0.09, h=0.11, t=0.016, hole=0.022, mat="steel")
    text_font(mb, "LIFT", 0.04, 0.0005, "cable", _T(xh + 0.12, -0.12, zb + Hh), font="stencil", res=2)
    text_font(mb, "NO STEP", 0.05, 0.0005, "cable", _T(xh + 0.15, 0.3, zb + Hh), font="stencil", res=2)
    for (sy, nrm) in ((-1, (0, -1, 0)), (1, (0, 1, 0))):
        Mst = face_M((xh, sy * Wh / 2, 0.0), nrm)
        text_font(mb, "LIGHT TOWER", 0.06, 0.0005, "cable", Mst @ _T(0.0, zb + Hh - 0.1, 0.0), font="stencil", res=2)
    # ------------------------------------------------------------------ mástil: pedestal, tornamesa, malacate, 4 tramos
    xm, ym = xh + Lh / 2 + 0.165, 0.0
    rtube(mb, (xm, 0, zc + 0.035), (xm, 0, zb + 0.1), 0.24, 0.24, paint, up=(1, 0, 0), r=0.012)
    slab(mb, _T(xm, 0, zb + 0.1), 0.3, 0.3, 0.016, rc=0.02, re=0.004, mat=paint, nc=4, ne=2)
    lathe(mb, [(0.0, zb + 0.116), (0.14, zb + 0.116), (0.142, zb + 0.13), (0.13, zb + 0.142), (0.0, zb + 0.142)], seg=72, mat="steel",
          M=_T(xm, 0, 0))                                  # tornamesa
    for k in range(8):
        a = 2 * PI * (k + 0.5) / 8
        bolt(mb, _T(xm + 0.12 * math.cos(a), 0.12 * math.sin(a), zb + 0.1415), d=0.01, washer=False, mat="steel")
    mb.cyl((xm, -0.13, zb + 0.13), (xm, -0.19, zb + 0.13), 0.008, seg=SEG_T, mat="steel")   # perno de giro
    star_knob(mb, _T(xm, -0.19, zb + 0.13) @ _Rx(90), r=0.02, h=0.016)
    secs = [(0.16, zb + 0.14, zb + 2.55), (0.135, zb + 2.35, zb + 4.75), (0.11, zb + 4.55, zb + 6.85), (0.085, zb + 6.65, 8.75)]
    for k, (wm, z0, z1) in enumerate(secs):
        rtube(mb, (xm, ym, z0), (xm, ym, z1), wm, wm, "galvanized", up=(1, 0, 0), r=0.012)
        rtube(mb, (xm, ym, z1 - 0.11), (xm, ym, z1), wm + 0.016, wm + 0.016, "galvanized", up=(1, 0, 0), r=0.014)   # collarín
        for (nx_, ny_) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dz in (-0.075, -0.035):
                bolt(mb, face_M((xm + nx_ * (wm / 2 + 0.008), ym + ny_ * (wm / 2 + 0.008), z1 + dz), (nx_, ny_, 0)), d=0.008, washer=False,
                     mat="steel")
        if k < 3:                                          # cojinetes de nylon visibles sobre el collarín y polea
            for (nx_, ny_) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rbox(mb, (-0.025, -0.004, -0.004), (0.025, 0.004, 0.012), "plastic", r=0.002,
                     m=_T(xm + nx_ * (wm / 2 - 0.0), ym + ny_ * (wm / 2 - 0.0), z1 - 0.004) @ _Rz(90 if nx_ else 0))
            Mpu = _T(xm + wm / 2 + 0.03, ym, z1 - 0.05)
            for e in (-1, 1):
                rbox(mb, (-0.035, e * 0.022 - 0.003, -0.03), (0.02, e * 0.022 + 0.003, 0.03), "galvanized", r=0.003, m=Mpu)
            lathe(mb, [(0.006, -0.012), (0.03, -0.012), (0.03, -0.008), (0.024, -0.003), (0.024, 0.003), (0.03, 0.008), (0.03, 0.012),
                       (0.006, 0.012)], seg=48, mat="steel", M=Mpu @ _Rx(90), closed=True)
            mb.cyl(Mpu @ Vector((0, -0.028, 0)), Mpu @ Vector((0, 0.028, 0)), 0.006, seg=SEG_T, mat="steel")
            # pasador de seguridad del tramo (perilla de jalar)
            Mpin = face_M((xm, ym - wm / 2 - 0.008, z1 - 0.055), (0, -1, 0))
            lathe(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.03), (0.0, 0.03)], seg=24, mat="steel", M=Mpin)
            star_knob(mb, Mpin @ _T(0, 0, 0.03), r=0.017, h=0.015, mat="sign_red")
    # malacate con tambor, cable enrollado, trinquete y manivela (cara +X del primer tramo)
    zw = zb + 1.05
    Mw = _T(xm + 0.08, 0, zw)
    for e in (-1, 1):
        slab(mb, Mw @ _T(0.055, e * 0.06, 0.0) @ _Rx(90) @ _T(0, 0, -0.003), 0.12, 0.2, 0.006, rc=0.03, re=0.0015, mat=paint, nc=4, ne=1)
    lathe(mb, [(0.0, -0.062), (0.06, -0.062), (0.06, -0.055), (0.03, -0.052), (0.03, 0.052), (0.06, 0.055), (0.06, 0.062), (0.0, 0.062)],
          seg=48, mat="steel", M=Mw @ _T(0.07, 0, 0) @ _Rx(90))
    hel = []
    for k in range(9 * 24 + 1):
        a = 2 * PI * k / 24
        hel.append((0.07 + 0.0335 * math.cos(a), -0.048 + 0.096 * k / (9 * 24), 0.0335 * math.sin(a)))
    with mb.soft():
        mb.tube([tuple(Mw @ Vector(p)) for p in hel], 0.0028, seg=SEG_W, mat="steel")
    mb.cyl(Mw @ Vector((0.07, -0.072, 0.0)), Mw @ Vector((0.07, 0.082, 0.0)), 0.012, seg=SEG, mat="steel")   # flecha del tambor
    nt = 24
    ring = []
    for k in range(nt * 2):
        a = 2 * PI * k / (nt * 2)
        rr_ = 0.056 if k % 2 == 0 else 0.048
        ring.append((rr_ * math.cos(a), rr_ * math.sin(a)))
    Mrt = Mw @ _T(0.07, 0.068, 0) @ _Rx(-90)
    loops = [[(x, y, z) for (x, y) in ring] for z in (0.0, 0.01)]
    skin(mb, loops, "steel", Mrt)                          # rueda de trinquete
    slab(mb, Mw @ _T(0.125, 0.064, 0.03) @ _Rx(-90) @ _Rz(-25), 0.05, 0.014, 0.006, rc=0.006, re=0.0015, mat="steel", nc=3, ne=1)  # uñeta
    mb.cyl(Mw @ Vector((0.145, 0.06, 0.04)), Mw @ Vector((0.145, 0.075, 0.04)), 0.005, seg=SEG_T, mat="steel")
    crank = [tuple(Mw @ Vector((0.07, 0.07, 0.0))), tuple(Mw @ Vector((0.07, 0.105, 0.0))), tuple(Mw @ Vector((0.07, 0.105, -0.17))),
             tuple(Mw @ Vector((0.07, 0.16, -0.17)))]
    tube_path(mb, fillet(crank, 0.02, 6), 0.008, seg=SEG_T, mat="steel", caps=True)
    lathe(mb, [(0.0, 0.0), (0.0135, 0.0), (0.0145, 0.01), (0.0145, 0.075), (0.013, 0.085), (0.0, 0.086)], seg=24, mat="plastic",
          M=_T(*(Mw @ Vector((0.07, 0.15, -0.17)))) @ _Rx(-90))
    # cable de acero: del tambor a las poleas de cada tramo
    rope = [Mw @ Vector((0.07 + 0.0335, 0.0, 0.0))]
    for k in range(3):
        wm, z0, z1 = secs[k]
        rope.append(Vector((xm + wm / 2 + 0.03 + 0.027, ym, z1 - 0.05)))
    with mb.soft():
        for a_, b_ in zip(rope[:-1], rope[1:]):
            mb.tube([tuple(a_), tuple(b_)], 0.0025, seg=SEG_W, mat="steel")
    # caja de conexiones inferior y cable de potencia en espiral alrededor del mástil
    rbox(mb, (xm - 0.13, -0.17, zb + 0.75), (xm - 0.078, -0.07, zb + 0.9), "plastic", r=0.008)
    rbox(mb, (xm + 0.04, -0.035, 8.56), (xm + 0.09, 0.035, 8.68), "plastic", r=0.006)     # caja de paso en el último tramo
    pts = [(xm - 0.13, -0.12, zb + 0.82), (xm - 0.16, -0.12, zb + 0.95)]
    turns = 8.5
    z0s, z1s = zb + 1.05, 8.55
    nsp = int(turns * 40)
    for k in range(nsp + 1):
        t = k / nsp
        a = PI + t * 2 * PI * turns
        rr_ = 0.14 + 0.006 * math.sin(t * 57)
        pts.append((xm + rr_ * math.cos(a), ym + rr_ * math.sin(a), z0s + (z1s - z0s) * t ** 1.08))
    pts.append((xm + 0.065, ym - 0.01, 8.6))
    tube_path(mb, pts, 0.0095, seg=SEG_T, mat="cable", caps=True)
    # ------------------------------------------------------------------ cabezal giratorio con 4 reflectores LED colgados
    zt = 8.75
    lathe(mb, [(0.0, zt - 0.01), (0.07, zt - 0.01), (0.07, zt + 0.02), (0.05, zt + 0.03), (0.0, zt + 0.03)], seg=48, mat="steel", M=_T(xm, ym, 0))
    lathe(mb, [(0.0, zt), (0.045, zt), (0.045, zt + 0.66), (0.04, zt + 0.665), (0.0, zt + 0.666)], seg=48, mat="steel", M=_T(xm, ym, 0))
    rbox(mb, (xm + 0.04, -0.09, zt + 0.3), (xm + 0.13, 0.09, zt + 0.46), "plastic", r=0.01)     # caja de conexiones superior
    for zbar in (zt + 0.15, zt + 0.62):
        rtube(mb, (xm - 0.74, ym - 0.06, zbar), (xm + 0.74, ym - 0.06, zbar), 0.05, 0.05, "steel", up=(0, 0, 1), r=0.005)
        for e in (-1, 1):
            slab(mb, _T(xm + e * 0.74, ym - 0.06, zbar) @ _Ry(90 * e) @ _T(0, 0, -0.001), 0.056, 0.056, 0.004, rc=0.006, re=0.0015,
                 mat="rubber", nc=3, ne=1)
        rbox(mb, (xm - 0.06, ym - 0.09, zbar - 0.035), (xm + 0.06, ym - 0.03, zbar + 0.035), "steel", r=0.006)   # abrazadera
        for sx in (-1, 1):
            xx = xm + sx * 0.49
            tilt = 14.0 if zbar > zt + 0.3 else 24.0
            Mh = _T(xx, ym - 0.06, zbar - 0.025 - 0.2275) @ _Rz(sx * 8)
            led_flood(mb, Mh, w=0.42, h=0.3, d=0.075, fins=17, yoke_drop=0.0775, tilt=tilt, hang=True)
            bolt(mb, _T(xx, ym - 0.06, zbar + 0.025), d=0.012, washer=True, mat="steel")
            g = Mh @ _Rx(tilt) @ Vector((0.06, 0.0, -0.15 - 0.02))
            box = Vector((xm + 0.085, -0.09, zt + 0.32))
            cab = [tuple(box), tuple(box + Vector((sx * 0.05, -0.02, -0.08))), tuple(g + Vector((-sx * 0.1, 0.0, -0.12))),
                   tuple(g + Vector((0, 0, -0.05))), tuple(g)]
            tube_path(mb, fillet(cab, 0.06, 4), 0.005, seg=SEG_T, mat="cable", caps=True)
    del r
    return mb


def _tower_panel(mb, M, w, h, paint, r):
    """Tablero de la torre (plano XY local, +Z afuera): controlador con pantalla, voltímetro, horómetro, interruptor de
    llave, paro de emergencia, 4 breakers de lámparas, botón de subir/bajar mástil y placas grabadas."""
    from kit.clinic_servicios import rrframe
    slab(mb, M @ _T(0, 0, -0.0005), w - 0.024, h - 0.024, 0.004, rc=0.006, re=0.0012, mat="cable", nc=3, ne=1)
    zp = 0.0032
    for u in np.linspace(-1, 1, 5):
        for v in (-1, 1):
            bolt(mb, M @ _T(u * (w / 2 - 0.024), v * (h / 2 - 0.024), zp), d=0.005, washer=False, mat="steel")
    P = M @ _T(0, 0, zp)
    Md = P @ _T(-0.17, 0.11, 0)
    rrframe(mb, Md, (0, 0, 0.2, 0.13, 0.01), (0, 0, 0.15, 0.095, 0.005), 0.009, re_o=0.002, re_i=0.0012, n=4, ne=2, mat="plastic")
    slab(mb, Md, 0.152, 0.097, 0.006, rc=0.005, re=0.0005, mat="glass", nc=3, ne=1)
    for i in range(5):
        slab(mb, P @ _T(-0.25 + i * 0.04, 0.025, 0.0), 0.028, 0.02, 0.0035, rc=0.004, re=0.0014, mat="rubber", nc=3, ne=2)
    panel_label(mb, P @ _T(-0.17, -0.005, 0), "LIGHT TOWER CONTROLLER", 0.16)
    gauge_dial(mb, P @ _T(0.06, 0.12, 0), r=0.03, needle=float(r.uniform(-30, 20)))
    panel_label(mb, P @ _T(0.06, 0.074, 0), "VOLTS", 0.05)
    rbox(mb, (-0.022, -0.016, -0.0005), (0.022, 0.016, 0.014), "cable", r=0.003, m=P @ _T(0.15, 0.12, 0))
    slab(mb, P @ _T(0.15, 0.123, 0.0138), 0.03, 0.011, 0.0012, rc=0.001, re=0.0003, mat="glass", nc=2, ne=1)
    panel_label(mb, P @ _T(0.15, 0.085, 0), "HOURS", 0.05)
    e_stop(mb, P @ _T(0.26, 0.11, 0))
    panel_label(mb, P @ _T(0.26, 0.055, 0), "E-STOP", 0.06)
    Mk = P @ _T(0.06, 0.0, 0)                               # interruptor de llave
    lathe(mb, [(0.0, 0.0), (0.024, 0.0), (0.025, 0.004), (0.022, 0.009), (0.0, 0.01)], seg=48, mat="steel", M=Mk)
    lathe(mb, [(0.0, 0.009), (0.011, 0.009), (0.011, 0.013), (0.0, 0.013)], seg=32, mat="brass", M=Mk)
    rbox(mb, (-0.0016, -0.008, 0.012), (0.0016, 0.008, 0.03), "steel", r=0.0008, m=Mk)
    rbox(mb, (-0.002, -0.014, 0.028), (0.002, 0.014, 0.05), "steel", r=0.003, m=Mk)
    for k, s_ in enumerate(("OFF", "ON", "START")):
        a = math.radians(150 - 60 * k)
        text_font(mb, s_, 0.0065, 0.0006, "cable", Mk @ _T(0.034 * math.cos(a), 0.034 * math.sin(a) - 0.002, 0.0), font="sign", bold=True, res=2)
    panel_label(mb, P @ _T(0.06, -0.05, 0), "IGNITION", 0.07)
    toggle_switch(mb, P @ _T(0.17, 0.0, 0), guard=True)
    panel_label(mb, P @ _T(0.17, -0.05, 0), "MAST UP / DOWN", 0.09)
    for k in range(4):                                     # breakers de las 4 lámparas
        Mbk = P @ _T(-0.27 + k * 0.05, -0.12, 0)
        rbox(mb, (-0.018, -0.04, -0.0005), (0.018, 0.04, 0.02), "cable", r=0.003, m=Mbk)
        rbox(mb, (-0.007, -0.012, 0.018), (0.007, 0.012, 0.024), "plastic", r=0.0015, m=Mbk)
        rbox(mb, (-0.0045, -0.004, 0.0), (0.0045, 0.004, 0.022), "cable", r=0.0015, m=Mbk @ _T(0, 0.004, 0.022) @ _Rx(-20 if k != 2 else 20))
        text_font(mb, f"L{k + 1}", 0.009, 0.0006, "sign_white", Mbk @ _T(0, -0.036, 0.02), font="sign", bold=True, res=2)
    panel_label(mb, P @ _T(-0.195, -0.178, 0), "LAMP BREAKERS", 0.1)
    for k, m_ in enumerate(("sign_green", "sign_red")):
        Ml = P @ _T(0.06 + k * 0.04, -0.12, 0)
        lathe(mb, [(0.0, 0.0), (0.0085, 0.0), (0.0085, 0.006), (0.0078, 0.0075), (0.0, 0.0075)], seg=32, mat="steel", M=Ml)
        lathe(mb, [(0.0, 0.0072), (0.0068, 0.0072), (0.0068, 0.0095), (0.005, 0.0122), (0.0, 0.013)], seg=32, mat=m_, M=Ml)
    panel_label(mb, P @ _T(0.08, -0.155, 0), "RUN    FAULT", 0.09)

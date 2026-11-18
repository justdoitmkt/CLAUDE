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
from kit.fonts import text_font
from kit.fortif import _v, ngon, tube_path  # utilidades genéricas (sin cambios)

SEG = 24          # lados de todo cilindro visible
SEG_T = 14        # lados de tubos delgados / cables / cuerdas
SEG_W = 12        # alambres de <= 6 mm (dentro de mb.soft())


# ====================================================================================================== utilidades
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
    lathe(mb, [(d * 0.5, z), (R * 0.87, z), (R, z + h * 0.16), (R, z + h * 0.84), (R * 0.87, z + h), (d * 0.5, z + h)], seg=6,
          mat=mat, M=M, phase=PI / 6, closed=True)
    if nut:                                                # espárrago roscado que sobresale de la tuerca
        zt = z + h
        prof = [(d * 0.5, zt - 0.001)]
        n = max(2, int(L / (d * 0.15)))
        for k in range(n):
            zz = zt + k * (L / n)
            prof += [(d * 0.5, zz), (d * 0.46, zz + L / n * 0.5)]
        prof += [(d * 0.5, zt + L - d * 0.08), (d * 0.42, zt + L), (0.0, zt + L)]
        lathe(mb, prof, seg=SEG, mat=mat, M=M)
    else:
        lathe(mb, [(0.0, z + h - 0.0004), (R * 0.82, z + h - 0.0004), (R * 0.8, z + h + 0.0003), (0.0, z + h + 0.0003)], seg=SEG,
              mat=mat, M=M)


def rivet(mb, M, d=0.005, mat="aluminium"):
    """Remache de cabeza redonda sobre z = 0 local (hundido 0,3 mm)."""
    r = d / 2
    lathe(mb, [(r * 1.0, -0.0003), (r, r * 0.12), (r * 0.9, r * 0.38), (r * 0.62, r * 0.56), (r * 0.3, r * 0.64), (0.0, r * 0.66)],
          seg=16, mat=mat, M=M)


def small_chain(mb, pts, link=0.011, wire=0.0011, mat="steel", seed=0):
    """Cadenita de eslabones ovalados alternados (90°) a paso constante sobre una polilínea; alambre redondo de 12 lados con
    sombreado continuo (mb.soft)."""
    r = rng(seed)
    P = [_v(p) for p in pts]
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    pitch = link - 1.9 * wire                           # eslabones en contacto (se tocan, no flotan)
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
    mb = MB()
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


# ============================================================================== (temporal) resto de las piezas
def tactical_generator(seed=0, color="od"):
    from kit import fortif
    return fortif.tactical_generator(seed=seed, color=color)


def drop_arm_barrier(L=5.0, seed=0):
    from kit import fortif
    return fortif.drop_arm_barrier(L=L, seed=seed)


def floodlight_tripod(seed=0):
    from kit import fortif
    return fortif.floodlight_tripod(seed=seed)


def light_tower(seed=0):
    from kit import fortif
    return fortif.light_tower(seed=seed)

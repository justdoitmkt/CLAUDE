"""kit/clinic.py — mobiliario y equipo de un hospital rural EN USO (limpio, gastado por el uso, no abandonado).

Convención de todas las piezas: devuelven un MB en coordenadas locales, origen en el piso al centro de la pieza, frente hacia -Y
(el lado desde el que se usa), Z arriba, metros. Las piezas de muro (letreros, lámparas, gabinetes) tienen el origen en la cara
del muro y crecen hacia -Y (fuera del muro).
Materiales del kit: steel, plastic, plastic_blue, linen, vinyl, rubber, sign_*, paint_*, wood, wood_dark, glass, paper, aluminium.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from kit import port
from kit.common import MB as _MB
from kit.common import rng


class MB(_MB):
    """MB del mobiliario: toda caja lleva bisel real (regla R-AAA: nada de aristas de cartón). bevel=0 explícito lo quita."""

    def box(self, mn, mx, mat="concrete", bevel=None, seg=2, m=None):
        if bevel is None:
            d = min(abs(mx[0] - mn[0]), abs(mx[1] - mn[1]), abs(mx[2] - mn[2]))
            bevel = min(0.004, d * 0.22) if d > 0.002 else 0.0
        return super().box(mn, mx, mat, bevel=bevel, seg=seg, m=m)

PI = math.pi


def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def _Rz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def _Rx(deg):
    return Matrix.Rotation(math.radians(deg), 4, "X")


def _Ry(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def remap(mb, table):
    """Cambia materiales de un MB ya construido (p. ej. puertas del kit de madera -> pintura menta)."""
    new = []
    idx = []
    for n in mb.mats:
        n2 = table.get(n, n)
        if n2 not in new:
            new.append(n2)
        idx.append(new.index(n2))
    for f in mb.bm.faces:
        f.material_index = idx[f.material_index]
    mb.mats = new
    return mb


# ------------------------------------------------------------------------------------------------------------- texto 3D
def text(mb, s, size, depth, mat, M=None, align="CENTER", spacing=1.0, bold=False):
    """Letras 3D (fuente del sistema de Blender) en el plano XY local, de cara a +Z, con `depth` de relieve desde z = 0.
    align: LEFT | CENTER | RIGHT sobre x = 0; la línea base queda en y = 0. Devuelve el ancho del texto."""
    cu = bpy.data.curves.new("_txt", "FONT")
    cu.body = s
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = align
    cu.space_character = spacing
    if bold:
        cu.offset = size * 0.018
    ob = bpy.data.objects.new("_txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    M2 = (M if M is not None else Matrix()) @ _T(0, 0, depth / 2)
    vs = [mb.bm.verts.new(M2 @ v.co) for v in me.vertices]
    xs = [v.co.x for v in me.vertices] or [0.0]
    mi = mb.mi(mat)
    for p in me.polygons:
        try:
            f = mb.bm.faces.new([vs[i] for i in p.vertices])
            f.material_index = mi
        except ValueError:
            pass
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return max(xs) - min(xs)


def sign_plate(s, w, h, bg="sign_white", fg="sign_green", t=0.012, size=None, standoff=0.0, frame=None):
    """Placa de letrero sobre muro (origen: cara del muro, centro inferior; la placa sale hacia -Y). Texto centrado en relieve."""
    mb = MB()
    mb.box((-w / 2, -standoff - t, 0.0), (w / 2, -standoff, h), bg)
    if frame:
        f = 0.012
        for (a, b) in (((-w / 2, 0), (w / 2, f)), ((-w / 2, h - f), (w / 2, h)), ((-w / 2, 0), (-w / 2 + f, h)), ((w / 2 - f, 0), (w / 2, h))):
            mb.box((a[0], -standoff - t - 0.004, a[1]), (b[0], -standoff - t, b[1]), frame)
    sz = size or h * 0.55
    M = _T(0, -standoff - t, h / 2 - sz * 0.36) @ _Rx(90)
    text(mb, s, sz, 0.003, fg, M)
    for x in (-w / 2 + 0.03, w / 2 - 0.03):
        port.bolt(mb, _T(x, -standoff - t, h / 2) @ _Rx(90), d=0.006, stud=0.0005, mat="steel")
    return mb


def hanging_sign(s, w=1.1, h=0.26, drop=0.32, bg="sign_white", fg="sign_green"):
    """Letrero colgante de dos caras con varillas al plafón (origen: plafón, centro; cuelga hacia -Z)."""
    mb = MB()
    zt = -drop
    mb.box((-w / 2, -0.009, zt - h), (w / 2, 0.009, zt), bg)
    for sgn in (-1, 1):
        sz = h * 0.52
        M = _T(0, sgn * 0.009, zt - h / 2 - sz * 0.36) @ _Rx(90 * sgn) @ (Matrix() if sgn < 0 else _Rz(180))
        text(mb, s, sz, 0.002, fg, M)
    for x in (-w / 2 + 0.08, w / 2 - 0.08):
        mb.cyl((x, 0, zt), (x, 0, 0), 0.003, seg=5, mat="steel")
        mb.cyl((x, 0, -0.004), (x, 0, 0), 0.015, seg=8, mat="steel")
    return mb


def exit_sign(lit=True):
    """Letrero luminoso de salida (caja 0,36 × 0,07 × 0,16, letras blancas en fondo verde). Origen: cara del muro, centro inferior."""
    mb = MB()
    mb.box((-0.18, -0.07, 0.0), (0.18, 0.0, 0.16), "sign_white")
    mb.box((-0.165, -0.072, 0.012), (0.165, -0.07, 0.148), "sign_green")
    text(mb, "EXIT", 0.085, 0.002, "sign_white", _T(0, -0.072, 0.05) @ _Rx(90))
    return mb


# ------------------------------------------------------------------------------------------------------------ utilidades
def _catmull(prof, n=4):
    P = [Vector((0.0, y, z)) for y, z in prof]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return [(p.y, p.z) for p in out]


def shell_strip(mb, prof, width, t, mat, m=None, taper=None, smooth_n=4, edge_seg=5):
    """Concha moldeada (asiento, respaldo, lona): perfil [(y, z)] suavizado y barrido a lo ancho en X (±width/2) con canto
    redondo de espesor t (semicírculos en los bordes laterales). taper(s) con s en 0..1 a lo largo del perfil -> factor de ancho."""
    prof = _catmull(prof, smooth_n) if smooth_n > 1 else prof
    pts = [Vector((0.0, y, z)) for y, z in prof]
    n = len(pts)
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        d = (b - a).normalized()
        nrm = Vector((0.0, -d.z, d.y))
        k = taper(i / (n - 1)) if taper else 1.0
        hw = width / 2 * k - t / 2
        ring = []
        for j in range(edge_seg + 1):                       # canto derecho (x+), de cara inferior a superior
            ang = -PI / 2 + PI * j / edge_seg
            ring.append(Vector((hw + t / 2 * math.cos(ang), 0, 0)) + p + nrm * (t / 2 + t / 2 * math.sin(ang)))
        for j in range(edge_seg + 1):                       # canto izquierdo (x-)
            ang = PI / 2 + PI * j / edge_seg
            ring.append(Vector((-hw + t / 2 * math.cos(ang), 0, 0)) + p + nrm * (t / 2 + t / 2 * math.sin(ang)))
        rings.append([mb.bm.verts.new((m @ v) if m is not None else v) for v in ring])
    kk = len(rings[0])
    for i in range(n - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(kk):
            j2 = (j + 1) % kk
            f = mb.face([A[j], A[j2], B[j2], B[j]], mat)
            f.smooth = True
    for ring, rev in ((rings[0], True), (rings[-1], False)):
        c = sum((v.co for v in ring), Vector()) / kk
        cv = mb.bm.verts.new(c)
        for j in range(kk):
            q = [cv, ring[j], ring[(j + 1) % kk]]
            f = mb.face(list(reversed(q)) if rev else q, mat)
            f.smooth = True


def rbox(mb, mn, mx, mat, r=0.01, m=None):
    """Caja con las 12 aristas redondeadas (muebles de lámina, laminados, cojines firmes)."""
    mb.box(mn, mx, mat, bevel=r, seg=3, m=m)


def cushion(mb, M, w, d, h, mat="vinyl", r=None, crown=0.008, piping=True, seg=(24, 18)):
    """Cojín tapizado: sección de esquinas redondeadas, abombado superior y vivo perimetral. Origen: centro de la base."""
    from kit import softgoods as sg
    r = r if r is not None else min(h * 0.45, 0.03)
    rings = sg._rounded_slab(d, w, h, r, crown, seg_l=seg[0], seg_w=seg[1])
    nr = len(rings[0])
    vs = [[mb.bm.verts.new(M @ Vector(p)) for p in ring] for ring in rings]
    for i in range(len(vs) - 1):
        for k in range(nr):
            f = mb.face([vs[i][k], vs[i][(k + 1) % nr], vs[i + 1][(k + 1) % nr], vs[i + 1][k]], mat)
            f.smooth = True
    for ring, rev in ((vs[0], False), (vs[-1], True)):
        c = sum((v.co for v in ring), Vector()) / nr
        cv = mb.bm.verts.new(c)
        for k in range(nr):
            a_, b_ = ring[k], ring[(k + 1) % nr]
            f = mb.face([cv, b_, a_] if not rev else [cv, a_, b_], mat)
            f.smooth = True
    if piping:
        pts = []
        cr = r * 1.02
        for (cx, cy, a0) in ((w / 2 - cr, -d / 2 + cr, -PI / 2), (w / 2 - cr, d / 2 - cr, 0.0), (-w / 2 + cr, d / 2 - cr, PI / 2),
                             (-w / 2 + cr, -d / 2 + cr, PI)):
            for k in range(7):
                a = a0 + PI / 2 * k / 6
                pts.append((cx + cr * math.cos(a), cy + cr * math.sin(a)))
        pts.append(pts[0])
        mb.tube([tuple(M @ Vector((x, y, h - r * 0.35))) for (x, y) in pts], 0.0035, seg=6, mat=mat)


def caster(mb, p, r=0.04, mat="rubber", swivel=0.0):
    """Rueda giratoria: horquilla, eje y llanta."""
    x, y, z = p
    M = _T(x, y, z) @ _Rz(swivel)
    mb.cyl(M @ Vector((0, 0, 2 * r + 0.02)), M @ Vector((0, 0, 2 * r + 0.045)), 0.012, seg=8, mat="steel")
    for s in (-1, 1):
        mb.box(M @ Vector((s * 0.018 - 0.003, -0.01, r)), M @ Vector((s * 0.018 + 0.003, r * 0.9, 2 * r + 0.025)), "steel")
    mb.box(M @ Vector((-0.021, -0.012, 2 * r + 0.015)), M @ Vector((0.021, r * 0.9, 2 * r + 0.025)), "steel")
    port.lathe(mb, [(0.004, -0.014), (r * 0.85, -0.014), (r, -0.008), (r, 0.008), (r * 0.85, 0.014), (0.004, 0.014)], seg=14,
               mat=mat, M=M @ _T(0, r * 0.45, r) @ _Ry(90))


# -------------------------------------------------------------------------------------------------------------- asientos
def seat_shell(mb, M, w=0.46):
    """Asiento moldeado de polipropileno: asiento con borde de cascada + respaldo inclinado unidos por la curva."""
    prof = [(-0.22, 0.025), (-0.235, 0.0), (-0.20, -0.012), (-0.08, -0.02), (0.05, -0.018), (0.15, -0.005), (0.19, 0.03),
            (0.215, 0.12), (0.235, 0.24), (0.255, 0.36), (0.262, 0.42), (0.25, 0.45)]
    shell_strip(mb, prof, w, 0.008, "plastic_blue", m=M,
                taper=lambda s_: 0.9 + 0.1 * math.sin(PI * min(1.0, s_ * 1.15)) ** 0.35)


def chair_row(n=4, seed=0, empty=()):
    """Bancada de n asientos (sala de espera): viga de PTR 60×40 con tapones, 2 patas en T de PTR con regatones de hule,
    ménsulas atornilladas bajo cada concha, soporte de respaldo por detrás, conchas de polipropileno de canto redondo y
    descansabrazos moldeados en los extremos y entre asientos."""
    r = rng(seed)
    mb = MB()
    pitch = 0.53
    L = n * pitch
    x0 = -L / 2
    zb = 0.33
    rtube(mb, (x0 + 0.02, 0.0, zb), (x0 + L - 0.02, 0.0, zb), 0.04, 0.06, "steel", up=(0, 0, 1), r=0.005)
    for x in (x0 + 0.02, x0 + L - 0.02):
        rbox(mb, (x - 0.006 if x > 0 else x - 0.0, -0.022, zb - 0.032), (x + (0.0 if x > 0 else 0.006), 0.022, zb + 0.032), "plastic", r=0.004)
    for xl in (x0 + 0.38, x0 + L - 0.38):
        rtube(mb, (xl, 0.0, 0.035), (xl, 0.0, zb - 0.03), 0.05, 0.04, "steel", up=(0, 1, 0), r=0.004)
        rtube(mb, (xl, -0.27, 0.02), (xl, 0.27, 0.02), 0.05, 0.035, "steel", up=(0, 0, 1), r=0.004)
        for yy in (-0.25, 0.25):
            port.lathe(mb, [(0.0, -0.002), (0.024, -0.002), (0.026, 0.004), (0.024, 0.012), (0.0, 0.012)], seg=14, mat="rubber",
                       M=_T(xl, yy, -0.0))
        for s_ in (-1, 1):
            port.gusset(mb, _T(xl, s_ * 0.02, zb - 0.03) @ _Rz(90 * s_) @ _Rx(180), 0.11, 0.09, t=0.005, mat="steel")
    seat_xs = []
    for i in range(n):
        xc = x0 + pitch * (i + 0.5)
        seat_xs.append(xc)
        if i in empty:
            continue
        rbox(mb, (xc - 0.09, -0.12, zb + 0.03), (xc + 0.09, 0.12, zb + 0.045), "steel", r=0.004)
        for (dx, dy) in ((-0.07, -0.09), (0.07, -0.09), (-0.07, 0.09), (0.07, 0.09)):
            port.bolt(mb, _T(xc + dx, dy, zb + 0.045), d=0.008, stud=0.002, mat="steel")
        # soporte de respaldo: solera doblada que sube POR DETRÁS de la concha
        mb.sweep(rr_profile(0.05, 0.008, 0.003), fillet([(xc, 0.12, zb + 0.038), (xc, 0.255, zb + 0.038), (xc, 0.30, zb + 0.15),
                                                         (xc, 0.315, zb + 0.36)], 0.04, 8), mat="steel", normal=(1, 0, 0))
        seat_shell(mb, _T(xc, 0.0, zb + 0.07) @ _Rz(float(r.uniform(-0.6, 0.6))))
    for k in range(n + 1):                                        # descansabrazos en extremos y entre asientos
        xa = x0 + pitch * k + (0.03 if k == 0 else (-0.03 if k == n else 0.0))
        mb.sweep(rr_profile(0.03, 0.012, 0.004), fillet([(xa, 0.02, zb + 0.032), (xa, -0.06, zb + 0.032), (xa, -0.12, zb + 0.24)], 0.04, 8),
                 mat="steel", normal=(1, 0, 0))
        cushion(mb, _T(xa, -0.04, zb + 0.24), 0.05, 0.3, 0.03, mat="plastic_blue", r=0.012, crown=0.002, piping=False, seg=(12, 10))
    return mb


def office_chair(seed=0):
    """Silla secretarial: base de 5 brazos (perfil de nylon), rodajas dobles, pistón con fuelle telescópico, mecanismo con palanca,
    asiento y respaldo tapizados (cojines con vivo), soporte de respaldo de solera doblada y descansabrazos de tubo con cojín."""
    r = rng(seed)
    mb = MB()
    for k in range(5):
        a = 2 * PI * k / 5 + float(r.uniform(0, 0.2))
        d = Vector((math.cos(a), math.sin(a), 0))
        st = [(0.04, 0.05, 0.05, 0.085), (0.18, 0.045, 0.04, 0.075), (0.29, 0.04, 0.035, 0.07)]
        port.loft(mb, st, seg=10, mat="cable", M=Matrix(((d.x, -d.y, 0, 0), (d.y, d.x, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))), ex=2.6)
        p = d * 0.3
        mb.cyl((p.x, p.y, 0.055), (p.x, p.y, 0.07), 0.012, seg=8, mat="steel")
        for sx in (-1, 1):
            Mc = _T(p.x, p.y, 0.025) @ Matrix.Rotation(a + float(r.uniform(-0.4, 0.4)), 4, "Z") @ _T(sx * 0.012, 0, 0) @ _Ry(90)
            port.lathe(mb, [(0.004, -0.007), (0.024, -0.007), (0.025, 0.0), (0.024, 0.007), (0.004, 0.007)], seg=16, mat="cable", M=Mc)
        rbox(mb, (p.x - 0.008, p.y - 0.018, 0.035), (p.x + 0.008, p.y + 0.018, 0.06), "cable", r=0.004)
    port.lathe(mb, [(0.0, 0.05), (0.045, 0.05), (0.045, 0.1), (0.0, 0.1)], seg=16, mat="cable")
    port.lathe(mb, [(0.03, 0.1), (0.03, 0.2), (0.026, 0.205), (0.026, 0.3), (0.022, 0.305), (0.022, 0.37)], seg=16, mat="cable",
               caps=False)
    mb.cyl((0, 0, 0.37), (0, 0, 0.41), 0.014, seg=12, mat="steel")
    rbox(mb, (-0.09, -0.11, 0.405), (0.09, 0.11, 0.44), "cable", r=0.008)
    mb.tube([(0.08, -0.05, 0.42), (0.17, -0.12, 0.41)], 0.005, seg=6, mat="steel")
    port.lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.012, 0.03), (0.0, 0.035)], seg=10, mat="cable", M=_T(0.17, -0.12, 0.41) @ _Ry(90))
    rbox(mb, (-0.22, -0.21, 0.44), (0.22, 0.21, 0.455), "cable", r=0.006)
    cushion(mb, _T(0, 0, 0.455), 0.47, 0.45, 0.07, mat="vinyl", r=0.03, crown=0.01, seg=(18, 18))
    mb.sweep(rr_profile(0.06, 0.008, 0.003), fillet([(0, 0.12, 0.43), (0, 0.27, 0.43), (0, 0.29, 0.55), (0, 0.28, 0.72)], 0.05, 8),
             mat="cable", normal=(1, 0, 0))
    cushion(mb, _T(0, 0.255, 0.86) @ _Rx(-82), 0.44, 0.40, 0.06, mat="vinyl", r=0.028, crown=0.008, seg=(16, 18))
    for s_ in (-1, 1):
        x = s_ * 0.25
        mb.tube(fillet([(s_ * 0.2, 0.0, 0.44), (x, 0.0, 0.47), (x, 0.0, 0.62), (x, -0.12, 0.64)], 0.03, 6), 0.011, seg=10, mat="cable")
        cushion(mb, _T(x, -0.02, 0.635), 0.06, 0.24, 0.028, mat="cable", r=0.012, crown=0.0, piping=False, seg=(12, 10))
    return mb


def folding_chair(seed=0):
    """Silla plegable de lámina (cocina del personal)."""
    mb = MB()
    for s in (-1, 1):
        mb.tube([(s * 0.2, -0.22, 0.0), (s * 0.2, 0.05, 0.44), (s * 0.2, 0.16, 0.86)], 0.011, seg=6, mat="steel")
        mb.tube([(s * 0.2, 0.2, 0.0), (s * 0.2, -0.12, 0.44)], 0.011, seg=6, mat="steel")
        for y in (-0.22, 0.2):
            mb.cyl((s * 0.2, y, 0.0), (s * 0.2, y, 0.015), 0.014, seg=6, mat="rubber")
    rbox(mb, (-0.21, -0.2, 0.44), (0.21, 0.18, 0.46), "metal_paint", r=0.03)
    mb.box((-0.2, 0.09, 0.66), (0.2, 0.11, 0.84), "metal_paint", m=_T(0, 0.1, 0.75) @ _Rx(-12) @ _T(0, -0.1, -0.75))
    return mb


# --------------------------------------------------------------------------------------------------------------- camas
def fillet(pts, rad, nseg=8):
    """Polilínea 3D con las esquinas redondeadas (radio de doblez real de tubo)."""
    P = [Vector(p) for p in pts]
    if len(P) < 3:
        return [tuple(p) for p in P]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d0, d1 = (a - b).normalized(), (c - b).normalized()
        ang = d0.angle(d1)
        if ang > math.pi - 1e-3:
            out.append(b)
            continue
        t = rad / math.tan(ang / 2)
        t = min(t, (a - b).length * 0.49, (c - b).length * 0.49)
        p0, p1 = b + d0 * t, b + d1 * t
        for k in range(nseg + 1):
            u = k / nseg
            q = p0.lerp(b, u).lerp(b.lerp(p1, u), u)          # bezier cuadrática (arco aproximado)
            out.append(q)
    out.append(P[-1])
    return [tuple(p) for p in out]


def rr_profile(w, h, r, n=4):
    """Perfil de tubo rectangular con esquinas de radio r (sentido antihorario)."""
    pts = []
    for (cx, cy, a0) in ((w / 2 - r, h / 2 - r, 0.0), (-w / 2 + r, h / 2 - r, PI / 2), (-w / 2 + r, -h / 2 + r, PI),
                         (w / 2 - r, -h / 2 + r, 1.5 * PI)):
        for k in range(n + 1):
            a = a0 + PI / 2 * k / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rtube(mb, p0, p1, w, h, mat, up=(0, 0, 1), r=0.004, caps=True):
    """Tubo rectangular de esquinas redondeadas (PTR) de p0 a p1; w en el eje lateral, h en `up`."""
    M, L = port.frame_on(p0, p1, up)
    prof = rr_profile(w, h, r)
    rings = []
    for x in (0.0, L):
        rings.append([mb.bm.verts.new(M @ Vector((x, py, pz))) for (py, pz) in prof])
    k = len(prof)
    for j in range(k):
        jj = (j + 1) % k
        f = mb.face([rings[0][j], rings[0][jj], rings[1][jj], rings[1][j]], mat)
        f.smooth = True
    if caps:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[1], mat)


def _spoke(r):
    sp = MB()
    sp.box((0.018, -0.0035, 0.0), (r * 0.66, 0.0035, 0.0045), "plastic", bevel=0.0)
    return sp


def caster_pro(mb, M, d=0.125, brake=False, swivel=0.0, mat_tire="rubber"):
    """Rodaja hospitalaria de 125 mm: placa/espiga, horquilla de lámina embutida, rueda con banda de rodadura, rin y tapón;
    pedal de freno opcional. Origen: piso bajo el eje (z = 0 en el piso)."""
    r = d / 2
    Mz = M @ _Rz(swivel)
    off = r * 0.55                                     # avance de la rueda respecto de la espiga
    zt = d + 0.035
    port.lathe(mb, [(0.0, 0.0), (0.032, 0.0), (0.032, 0.006), (0.0, 0.006)], seg=16, mat="steel", M=Mz @ _T(0, 0, zt))
    port.lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.012), (0.026, 0.016), (0.0, 0.016)], seg=16, mat="steel", M=Mz @ _T(0, 0, zt - 0.016))
    mb.cyl(Mz @ Vector((0, 0, zt + 0.006)), Mz @ Vector((0, 0, zt + 0.045)), 0.011, seg=10, mat="steel")
    for s in (-1, 1):
        prof = [(-0.024, zt - 0.016), (0.024, zt - 0.016), (off + 0.018, r + 0.012), (off + 0.016, r - 0.01), (off - 0.016, r - 0.01),
                (-0.018, zt - 0.03)]
        perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # local (y, z, espesor) -> mundo (x espesor)
        mb.plate([(y, z) for (y, z) in prof], 0.003, "steel", m=Mz @ _T(s * 0.024 - (0.003 if s > 0 else 0), 0, 0) @ perm)
    mb.box(Mz @ Vector((-0.027, -0.024, zt - 0.02)), Mz @ Vector((0.027, 0.024, zt - 0.014)), "steel")
    Mw = Mz @ _T(0, off, r) @ _Ry(90)
    # llanta de poliuretano: banda con dos ranuras perimetrales, hombros redondeados; rin de nylon con 6 rayos rehundidos y maza
    prof = [(r * 0.72, -0.0185), (r * 0.9, -0.017), (r - 0.004, -0.0145), (r - 0.0008, -0.011), (r, -0.006), (r - 0.0025, -0.0045),
            (r - 0.0025, -0.0025), (r, -0.0015), (r, 0.0015), (r - 0.0025, 0.0025), (r - 0.0025, 0.0045), (r, 0.006),
            (r - 0.0008, 0.011), (r - 0.004, 0.0145), (r * 0.9, 0.017), (r * 0.72, 0.0185)]
    port.lathe(mb, prof, seg=32, mat=mat_tire, M=Mw, caps=False)
    port.lathe(mb, [(0.016, -0.019), (r * 0.72, -0.0185), (r * 0.72, 0.0185), (0.016, 0.019)], seg=32, mat="plastic", M=Mw,
               caps=False)
    for sgn in (-1, 1):                               # cara del rin rehundida con rayos
        port.lathe(mb, [(0.016, sgn * 0.019), (0.02, sgn * 0.012), (r * 0.66, sgn * 0.012), (r * 0.72, sgn * 0.0185)], seg=32,
                   mat="plastic", M=Mw, caps=False)
        for k in range(6):
            a = 2 * PI * k / 6
            mb.join(_spoke(r), Mw @ Matrix.Rotation(a, 4, "Z") @ _T(0, 0, sgn * 0.012 - (0.0045 if sgn > 0 else 0)))
    port.lathe(mb, [(0.0, -0.024), (0.016, -0.024), (0.016, 0.024), (0.0, 0.024)], seg=16, mat="steel", M=Mw)
    mb.cyl(Mz @ Vector((-0.03, off, r)), Mz @ Vector((0.03, off, r)), 0.005, seg=8, mat="steel")
    if brake:                                          # pedal de freno: palanca roja con cojín de hule estriado
        mb.box(Mz @ Vector((-0.012, -0.03, zt - 0.03)), Mz @ Vector((0.012, -0.012, zt - 0.02)), "steel")
        rbox(mb, (-0.032, -0.085, zt - 0.032), (0.032, -0.03, zt - 0.02), "sign_red", r=0.008, m=Mz)
        for k in range(5):
            y = -0.08 + k * 0.011
            mb.box(Mz @ Vector((-0.028, y, zt - 0.02)), Mz @ Vector((0.028, y + 0.006, zt - 0.016)), "rubber")


def _bars_board(mb, x0, x1, y, z0, z1, mat_tube="sign_white", rad=0.07, bar_step=0.085):
    """Cabecera/piecera de tubo doblado Ø 25 con barrotes Ø 13 soldados, travesaño inferior y tapones."""
    path = fillet([(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)], rad, nseg=10)
    mb.tube(path, 0.0127, seg=12, mat=mat_tube, caps=True)
    zl = z0 + 0.14
    mb.tube([(x0 + 0.012, y, zl), (x1 - 0.012, y, zl)], 0.0105, seg=10, mat=mat_tube)
    n = int((x1 - x0 - 0.1) / bar_step)
    for i in range(1, n + 1):
        x = x0 + 0.05 + (x1 - x0 - 0.1) * i / (n + 1)
        mb.tube([(x, y, zl + 0.008), (x, y, z1 - 0.012)], 0.0065, seg=8, mat=mat_tube, caps=False)
        for zz in (zl + 0.01, z1 - 0.014):                        # cordón de soldadura
            port.lathe(mb, [(0.0065, -0.004), (0.0095, 0.0), (0.0065, 0.004)], seg=8, mat=mat_tube, caps=False, M=_T(x, y, zz))
    for x in (x0, x1):
        port.lathe(mb, [(0.0, 0.0), (0.0135, 0.0), (0.0135, 0.02), (0.0, 0.022)], seg=12, mat="plastic", M=_T(x, y, z0 - 0.02))


def _wire_deck(mb, x0, x1, y0, y1, z, M=None, step=0.055, mat="steel"):
    """Sección de plataforma: marco de PTR 25×25 y malla electrosoldada (alambre Ø 4 mm) en las dos direcciones."""
    M = M if M is not None else Matrix()
    for (a, b) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        rtube(mb, M @ Vector((a[0], a[1], z)), M @ Vector((b[0], b[1], z)), 0.025, 0.025, mat, up=tuple((M.to_3x3() @ Vector((0, 0, 1)))),
              r=0.003)
    x = x0 + step
    while x < x1 - 0.02:
        mb.cyl(M @ Vector((x, y0 + 0.012, z + 0.006)), M @ Vector((x, y1 - 0.012, z + 0.006)), 0.002, seg=5, mat=mat)
        x += step
    y = y0 + step
    while y < y1 - 0.02:
        mb.cyl(M @ Vector((x0 + 0.012, y, z + 0.0105)), M @ Vector((x1 - 0.012, y, z + 0.0105)), 0.002, seg=5, mat=mat)
        y += step


def _side_rail(mb, xs, ya, yb, z_deck, up=True, mat="sign_white"):
    """Barandal abatible: 3 tubos Ø 20 con remates doblados, 2 postes con eslabones de pivote, perilla de seguro."""
    zb = z_deck + (0.14 if up else -0.30)
    zt = zb + 0.38
    path = fillet([(xs, ya, zb + 0.05), (xs, ya, zt), (xs, yb, zt), (xs, yb, zb + 0.05)], 0.05, nseg=8)
    mb.tube(path, 0.0105, seg=10, mat=mat)
    for z in (zb + 0.13, zb + 0.25):
        mb.tube([(xs, ya, z), (xs, yb, z)], 0.0095, seg=10, mat=mat, caps=False)
    for y in (ya + 0.12, yb - 0.12):
        sgn = 1 if xs > 0 else -1
        mb.tube([(xs, y, zb + 0.05), (xs - sgn * 0.01, y, zb - 0.05), (xs - sgn * 0.035, y, z_deck - 0.02)], 0.009, seg=8, mat=mat)
        mb.box((xs - sgn * 0.035 - 0.012, y - 0.02, z_deck - 0.05), (xs - sgn * 0.035 + 0.012, y + 0.02, z_deck - 0.0), "steel")
        port.lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.014, 0.01), (0.012, 0.02), (0.0, 0.022)], seg=10, mat="sign_red",
                   M=_T(xs + sgn * 0.012, y, zb + 0.09) @ _Ry(90 * sgn))


def _crank(mb, x, y, z, ang=0.0):
    """Manivela plegable: flecha, cardán, brazo doblado y empuñadura giratoria (al pie de la cama)."""
    mb.cyl((x, y + 0.25, z), (x, y, z), 0.008, seg=10, mat="steel")
    port.lathe(mb, [(0.0, 0.0), (0.014, 0.0), (0.016, 0.02), (0.014, 0.04), (0.0, 0.04)], seg=12, mat="steel",
               M=_T(x, y, z) @ _Rx(90))
    M = _T(x, y - 0.04, z) @ Matrix.Rotation(math.radians(ang), 4, "Y")
    arm = [M @ Vector(p) for p in [(0.0, 0.0, 0.0), (0.0, -0.03, 0.0), (0.09, -0.03, 0.0), (0.12, -0.03, -0.02)]]
    mb.tube(fillet([tuple(a) for a in arm], 0.02, 6), 0.007, seg=8, mat="steel")
    port.lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.013, 0.02), (0.013, 0.07), (0.011, 0.09), (0.0, 0.09)], seg=12, mat="plastic",
               M=M @ _T(0.12, -0.03, -0.02) @ _Rx(90))


def hospital_bed(seed=0, rails_up=True, fowler=0.0, blanket=True, made=True, rails=(True, True)):
    """Cama hospitalaria manual de 2 manivelas (≈ 2,10 × 0,98; colchón arriba a 0,66): bastidor de PTR 50×30, patas de PTR
    40×40, rodajas de 125 mm (2 con freno), plataforma de 4 secciones con malla electrosoldada (respaldo con ángulo `fowler`),
    cabecera y piecera de tubo doblado con barrotes, barandales abatibles, defensas giratorias, portasueros, manivelas;
    colchón de vinilo con vivos, sábana y cobija simuladas, almohada inflada por presión.
    Cabecera hacia +Y, pie hacia -Y."""
    from kit import softgoods as sg
    r = rng(seed)
    mb = MB()
    L, W = 1.96, 0.90
    zf = 0.42                     # bastidor
    zd = 0.505                    # cara superior de la plataforma
    xr = W / 2 + 0.01
    # patas y rodajas
    for (sx, sy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        x, y = sx * (xr - 0.02), sy * (L / 2 - 0.02)
        rtube(mb, (x, y, 0.165), (x, y, zf + 0.03), 0.04, 0.04, "sign_white", up=(1, 0, 0), r=0.004)
        caster_pro(mb, _T(x, y, 0.0), brake=(sy < 0), swivel=float(r.uniform(-30, 30)) + (180 if sy > 0 else 0))
        mb.cyl((x - sx * 0.035, y + sy * 0.035, zf - 0.01), (x - sx * 0.035, y + sy * 0.035, zf + 0.04), 0.032, seg=16, mat="rubber")
    # largueros, travesaños y soportes de plataforma
    for sx in (-1, 1):
        rtube(mb, (sx * xr, -L / 2 - 0.02, zf), (sx * xr, L / 2 + 0.02, zf), 0.03, 0.05, "sign_white", up=(0, 0, 1), r=0.004)
    for y in (-L / 2 + 0.03, -0.35, 0.25, L / 2 - 0.03):
        rtube(mb, (-xr + 0.015, y, zf - 0.005), (xr - 0.015, y, zf - 0.005), 0.03, 0.03, "sign_white", up=(0, 0, 1), r=0.003)
    # plataforma de 4 secciones (malla)
    hinge = 0.22
    _wire_deck(mb, -W / 2 + 0.02, W / 2 - 0.02, -L / 2 + 0.03, -0.52, zd - 0.0125)
    _wire_deck(mb, -W / 2 + 0.02, W / 2 - 0.02, -0.5, -0.12, zd - 0.0125)
    _wire_deck(mb, -W / 2 + 0.02, W / 2 - 0.02, -0.10, hinge - 0.02, zd - 0.0125)
    Mb = _T(0, hinge, zd) @ _Rx(fowler) @ _T(0, -hinge, -zd)
    _wire_deck(mb, -W / 2 + 0.02, W / 2 - 0.02, hinge, L / 2 - 0.03, zd - 0.0125, M=Mb)
    for x in (-W / 2 + 0.06, W / 2 - 0.06):                   # bisagras
        port.lathe(mb, [(0.0, -0.03), (0.011, -0.03), (0.011, 0.03), (0.0, 0.03)], seg=10, mat="steel", M=_T(x, hinge - 0.01, zd - 0.012) @ _Ry(90))
    if fowler > 0:                                             # brazo del mecanismo bajo el respaldo
        mb.tube([(0.0, hinge + 0.05, zf), (0.0, hinge + 0.25, zd - 0.02 + 0.25 * math.sin(math.radians(fowler)))], 0.012, seg=8, mat="steel")
    for sx in (-1, 1):                                         # retenes del colchón
        for y in (-0.7, 0.0):
            mb.box((sx * (W / 2 - 0.005) - 0.004, y - 0.03, zd - 0.01), (sx * (W / 2 - 0.005) + 0.004, y + 0.03, zd + 0.06), "steel")
    # cabecera y piecera
    _bars_board(mb, -W / 2 + 0.005, W / 2 - 0.005, L / 2 + 0.005, zf + 0.02, 1.02)
    _bars_board(mb, -W / 2 + 0.005, W / 2 - 0.005, -L / 2 - 0.005, zf + 0.02, 0.90)
    for sx in (-1, 1):                                         # portasueros
        mb.tube([(sx * (W / 2 + 0.04), L / 2 + 0.03, zf - 0.03), (sx * (W / 2 + 0.04), L / 2 + 0.03, zf + 0.09)], 0.011, seg=10, mat="steel")
        mb.tube([(sx * (W / 2 + 0.04), L / 2 + 0.03, zf + 0.0), (sx * xr, L / 2 + 0.01, zf + 0.0)], 0.006, seg=6, mat="steel")
    # barandales
    for k, sx in enumerate((-1, 1)):
        if rails[k]:
            _side_rail(mb, sx * (W / 2 + 0.035), -0.15, 0.62, zd + 0.13, up=rails_up)
    # manivelas al pie
    for x in (-0.18, 0.18):
        _crank(mb, x, -L / 2 - 0.03, zf - 0.02, ang=float(r.uniform(-20, 60)))
    # colchón, sábana, cobija, almohada
    Lm, Wm, Hm = 1.90, 0.86, 0.13
    Mm = _T(0, 0.0, zd)
    sg.mattress(mb, Mm, Lm, Wm, Hm, seed=seed, fowler=fowler, hinge=hinge)
    if made:
        # las telas se simulan sobre el colchón plano y luego siguen el quiebre del respaldo (como una sábana ajustable)
        col = sg.mattress_collider_arrays(Lm, Wm, Hm)
        bend = (lambda co: sg.bend_fowler(co, fowler, hinge)) if fowler > 0 else None
        sg.drape(mb, Mm, "sabana", (Wm + 0.22, Lm + 0.16), (38, 68), Hm + 0.04, lambda: [col], "linen", seed=seed % 3, stiff=10.0,
                 frames=55, post=bend)
        if blanket:
            off = np.array([0, -0.32, 0], np.float32)
            sg.drape(mb, Mm @ _T(0, -0.32, 0), "cobija", (Wm + 0.34, 1.25), (34, 46), Hm + 0.08,
                     lambda: [(col[0] - off, col[1], col[2])], "wool_blue", seed=seed % 3, stiff=18.0,
                     frames=55, thickness=0.006, pre_fold=0.42,
                     post=(lambda co: sg.bend_fowler(co + off, fowler, hinge) - off) if fowler > 0 else None)
        a = math.radians(fowler)
        yp, zp = 0.68, Hm + 0.016
        if fowler > 0:
            dy = yp - hinge
            yp, zp = hinge + dy * math.cos(a) - zp * math.sin(a), dy * math.sin(a) + zp * math.cos(a)
        sg.pillow(mb, Mm @ _T(float(r.uniform(-0.03, 0.03)), yp, zp) @ _Rx(fowler) @ _Rz(float(r.uniform(-5, 5))), seed=seed % 4)
    return mb


def bedside_cabinet(seed=0):
    """Buró de hospital laminado: cajón, puerta, cubierta con borde y un vaso con jarra."""
    r = rng(seed)
    mb = MB()
    rbox(mb, (-0.22, -0.21, 0.08), (0.22, 0.21, 0.78), "plastic", r=0.01)
    rbox(mb, (-0.235, -0.225, 0.78), (0.235, 0.225, 0.80), "plastic", r=0.015)
    for (x, y) in ((-0.18, -0.17), (0.18, -0.17), (-0.18, 0.17), (0.18, 0.17)):
        caster(mb, (x, y, 0.0), r=0.025)
    mb.box((-0.2, -0.214, 0.62), (0.2, -0.21, 0.76), "plastic")
    mb.box((-0.2, -0.214, 0.12), (0.2, -0.21, 0.60), "plastic")
    for z in (0.69, 0.5):
        mb.box((-0.06, -0.235, z - 0.008), (0.06, -0.214, z + 0.008), "steel")
    if r.random() < 0.8:
        port.lathe(mb, [(0.0, 0.0), (0.045, 0.0), (0.05, 0.03), (0.042, 0.2), (0.02, 0.24), (0.0, 0.24)], seg=12, mat="plastic",
                   M=_T(0.1, 0.05, 0.80))
        mb.cyl((-0.08, 0.02, 0.80), (-0.08, 0.02, 0.89), 0.032, seg=10, mat="glass", r1=0.036)
    return mb


def iv_stand(seed=0, bag=True):
    """Portasueros: base de 5 patas con rodajas, poste de 1,9 m, cabeza de 4 ganchos y bolsa de solución."""
    r = rng(seed)
    mb = MB()
    for k in range(5):
        a = 2 * PI * k / 5 + float(r.uniform(0, 1))
        p = (0.27 * math.cos(a), 0.27 * math.sin(a))
        mb.tube([(0, 0, 0.1), (p[0], p[1], 0.075)], 0.011, seg=6, mat="steel")
        caster(mb, (p[0], p[1], 0.0), r=0.025, swivel=math.degrees(a))
    mb.cyl((0, 0, 0.06), (0, 0, 0.13), 0.03, seg=10, mat="steel")
    mb.cyl((0, 0, 0.13), (0, 0, 1.95), 0.012, seg=8, mat="steel")
    for k in range(4):
        a = PI / 2 * k
        mb.tube([(0, 0, 1.93), (0.11 * math.cos(a), 0.11 * math.sin(a), 1.95), (0.13 * math.cos(a), 0.13 * math.sin(a), 2.0)],
                0.004, seg=5, mat="steel")
    if bag:
        port.loft(mb, [(-0.11, 0.0, 0.0, 0.0), (-0.09, 0.11, 0.04, 0.0), (0.06, 0.12, 0.045, 0.0), (0.1, 0.06, 0.02, 0.0)], seg=8,
                  mat="plastic", M=_T(0.13, 0, 1.86) @ _Ry(90), ex=2.2)
        mb.tube([(0.13, 0, 1.76), (0.11, 0.02, 1.4), (0.05, 0.1, 1.1), (0.0, 0.25, 0.95)], 0.002, seg=4, mat="plastic")
    return mb


def curtain_track(mb, pts, z, drop, r, open_runs=(), mat="linen"):
    """Riel de cortina al plafón: perfil C de aluminio con soportes atornillados, carros deslizantes con ganchos y cortina
    simulada (kit.softgoods.curtain). pts: polilínea en planta; open_runs: tramos con la cortina recogida junto al inicio."""
    from kit import softgoods as sg
    for (a, b) in zip(pts[:-1], pts[1:]):
        A, B = Vector((a[0], a[1], z - 0.02)), Vector((b[0], b[1], z - 0.02))
        Mf, L = port.frame_on(A, B, (0, 0, 1))
        prof = [(-0.012, -0.012), (0.012, -0.012), (0.012, 0.012), (0.004, 0.012), (0.004, 0.009), (0.009, 0.009), (0.009, -0.009),
                (-0.009, -0.009), (-0.009, 0.009), (-0.004, 0.009), (-0.004, 0.012), (-0.012, 0.012)]
        rings = [[mb.bm.verts.new(Mf @ Vector((x, py, pz))) for (py, pz) in prof] for x in (0.0, L)]
        k = len(prof)
        for j in range(k):
            mb.face([rings[0][j], rings[0][(j + 1) % k], rings[1][(j + 1) % k], rings[1][j]], "aluminium")
        mb.face(list(reversed(rings[0])), "aluminium")
        mb.face(rings[1], "aluminium")
        n_sup = max(2, int(L / 0.9) + 1)
        for i in range(n_sup):
            p = A.lerp(B, (i + 0.5) / n_sup)
            mb.cyl((p.x, p.y, z - 0.008), (p.x, p.y, z), 0.02, seg=12, mat="aluminium")
            mb.cyl((p.x, p.y, z - 0.008), (p.x, p.y, z - 0.002), 0.005, seg=6, mat="steel")
    for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
        A, B = Vector((a[0], a[1], 0)), Vector((b[0], b[1], 0))
        L = (B - A).length
        d = (B - A).normalized()
        hang = 0.35 if i in open_runs else max(0.4, L - 0.05)
        M = Matrix(((d.x, -d.y, 0, A.x), (d.y, d.x, 0, A.y), (0, 0, 1, z - 0.045), (0, 0, 0, 1)))
        sg.curtain(mb, M, hang, z - 0.045 - drop, seed=int(r.integers(0, 3)), gathered=(2.6 if i in open_runs else 1.7), mat=mat)
        n = max(2, int(hang / 0.11))
        for k in range(n + 1):
            p = A + d * (hang * k / n)
            mb.box((p.x - 0.006, p.y - 0.006, z - 0.032), (p.x + 0.006, p.y + 0.006, z - 0.022), "plastic")
            mb.tube([(p.x, p.y, z - 0.032), (p.x, p.y, z - 0.042), (p.x + d.x * 0.006, p.y + d.y * 0.006, z - 0.047)], 0.0012, seg=4,
                    mat="steel")


def exam_table(seed=0):
    """Mesa de exploración: gabinete de lámina con 3 cajones y puerta (jaladeras, rodapié), colchoneta tapizada en dos secciones
    (asiento y cabecera reclinada 28° con mecanismo), vivos, rollo de papel con su despachador y la hoja corriendo sobre la
    colchoneta, estribos plegables y banco de dos peldaños con huella de hule estriada."""
    mb = MB()
    rbox(mb, (-0.30, -0.9, 0.06), (0.30, 0.9, 0.62), "plastic", r=0.012)
    mb.box((-0.29, -0.89, 0.0), (0.29, 0.89, 0.06), "rubber")
    for (y0, y1) in ((-0.86, -0.46), (-0.42, -0.02), (0.02, 0.42), (0.46, 0.86)):
        rbox(mb, (-0.312, y0, 0.36), (-0.3, y1, 0.58), "plastic", r=0.004)
        rbox(mb, (-0.335, (y0 + y1) / 2 - 0.07, 0.535), (-0.312, (y0 + y1) / 2 + 0.07, 0.55), "steel", r=0.004)
    rbox(mb, (-0.312, -0.86, 0.09), (-0.3, 0.86, 0.33), "plastic", r=0.004)
    rbox(mb, (-0.33, 0.6, 0.18), (-0.312, 0.62, 0.28), "steel", r=0.003)
    rbox(mb, (-0.31, -0.92, 0.615), (0.31, 0.47, 0.64), "plastic", r=0.006)
    cushion(mb, _T(0, -0.225, 0.64), 0.6, 1.36, 0.075, mat="vinyl", r=0.03, crown=0.006, seg=(34, 18))
    Mh = _T(0, 0.47, 0.64) @ _Rx(28)
    cushion(mb, Mh @ _T(0, 0.27, 0), 0.6, 0.54, 0.075, mat="vinyl", r=0.03, crown=0.006, seg=(16, 18))
    for x in (-0.24, 0.24):
        mb.tube([(x, 0.5, 0.6), (x, 0.62, 0.66), (x, 0.72, 0.75)], 0.01, seg=8, mat="steel")
    # despachador y rollo de papel en la cabecera
    Mr = Mh @ _T(0, 0.58, 0.04)
    for x in (-0.29, 0.29):
        rbox(mb, (x - 0.008, -0.03, -0.05), (x + 0.008, 0.03, 0.08), "steel", r=0.003, m=Mr)
    mb.cyl(Mr @ Vector((-0.3, 0, 0.04)), Mr @ Vector((0.3, 0, 0.04)), 0.008, seg=8, mat="steel")
    port.lathe(mb, [(0.008, -0.27), (0.055, -0.27), (0.057, -0.265), (0.057, 0.265), (0.055, 0.27), (0.008, 0.27)], seg=24, mat="paper",
               M=Mr @ _T(0, 0, 0.04) @ _Ry(90))
    # hoja de papel corriendo sobre la colchoneta (sigue cabecera y asiento, con ondulaciones y borde rasgado al pie)
    r = rng(seed)
    nx, ny = 16, 60
    pts = []
    for j in range(ny + 1):
        t = j / ny
        if t < 0.25:
            q = Mh @ Vector((0, 0.54 - 0.54 * t / 0.25, 0.0785))
        else:
            q = Vector((0, 0.47 - (0.47 + 0.86) * (t - 0.25) / 0.75, 0.7185))
        pts.append(q)
    top, bot = [], []
    for j, q in enumerate(pts):
        rt, rb = [], []
        for i in range(nx + 1):
            x = -0.25 + 0.5 * i / nx
            wob = 0.0025 * math.sin(j * 0.7 + i * 0.4 + seed) * (0.3 + 0.7 * abs(x) / 0.25)
            yy = q.y - (float(r.uniform(0, 0.025)) if j == ny else 0.0)
            rt.append(mb.bm.verts.new((x, yy, q.z + 0.0018 + wob)))
            rb.append(mb.bm.verts.new((x, yy, q.z + 0.001 + wob)))
        top.append(rt)
        bot.append(rb)
    for j in range(ny):                                    # hoja con espesor (sólido cerrado)
        for i in range(nx):
            f = mb.face([top[j][i], top[j][i + 1], top[j + 1][i + 1], top[j + 1][i]], "paper")
            f.smooth = True
            f = mb.face([bot[j + 1][i], bot[j + 1][i + 1], bot[j][i + 1], bot[j][i]], "paper")
            f.smooth = True
    for j in range(ny):
        for (i, k) in ((0, 0), (nx, 1)):
            q = [top[j][i], top[j + 1][i], bot[j + 1][i], bot[j][i]]
            mb.face(q if k == 0 else list(reversed(q)), "paper")
    for (j, k) in ((0, 0), (ny, 1)):
        for i in range(nx):
            q = [top[j][i], bot[j][i], bot[j][i + 1], top[j][i + 1]]
            mb.face(q if k == 0 else list(reversed(q)), "paper")
    # estribos plegados
    for x in (-0.18, 0.18):
        mb.tube(fillet([(x, -0.92, 0.6), (x, -1.02, 0.6), (x, -1.02, 0.5)], 0.02, 6), 0.007, seg=8, mat="steel")
        port.lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.035, 0.03), (0.03, 0.06), (0.0, 0.06)], seg=12, mat="rubber",
                   M=_T(x, -1.02, 0.5) @ _Rx(90))
    # banco de dos peldaños
    for (y0, y1, z1) in ((-1.42, -1.0, 0.2), (-1.24, -1.0, 0.4)):
        for x in (-0.24, 0.22):
            rbox(mb, (x, y0, 0.0), (x + 0.02, y1, z1), "steel", r=0.004)
        rbox(mb, (-0.24, y0, z1 - 0.02), (0.24, y1, z1), "steel", r=0.004)
        k = 0
        y = y0 + 0.015
        while y < y1 - 0.02:
            rbox(mb, (-0.22, y, z1), (0.22, y + 0.012, z1 + 0.006), "rubber", r=0.002)
            y += 0.022
            k += 1
    return mb


def _tire(mb, M, R, rt, n=72, m=12, tread=True, mat="rubber"):
    """Llanta tórica con dibujo: anillo de radio R y sección rt; el dibujo alterna salientes sobre la banda."""
    rings = []
    for i in range(n):
        a = 2 * PI * i / n
        ring = []
        for j in range(m):
            b = 2 * PI * j / m
            rr = rt
            if tread and math.cos(b) > 0.55 and (i % 2 == 0):
                rr *= 1.07
            p = Vector(((R + rr * math.cos(b)) * math.cos(a), (R + rr * math.cos(b)) * math.sin(a), rr * math.sin(b)))
            ring.append(mb.bm.verts.new(M @ p))
        rings.append(ring)
    for i in range(n):
        A, B = rings[i], rings[(i + 1) % n]
        for j in range(m):
            f = mb.face([A[j], A[(j + 1) % m], B[(j + 1) % m], B[j]], mat)
            f.smooth = True


def wheelchair(seed=0):
    """Silla de ruedas plegable estándar: bastidor de tubo Ø 22 con dobleces reales, tijera plegable bajo el asiento, lonas de
    vinilo con comba y costuras, descansabrazos acolchados, guardafangos, ruedas traseras de 24" (llanta con dibujo, rin, 18
    rayos cruzados por lado, aro de impulso con 4 separadores y eje rápido), frenos de palanca, horquillas con ruedas de 8",
    descansapiés abatibles con estribos estriados y talonera, manerales con puños y antivuelco."""
    r = rng(seed)
    mb = MB()
    W = 0.46
    ty = 0.0111
    for s_ in (-1, 1):
        x = s_ * W / 2
        # costado: barra inferior, poste delantero, riel de asiento, respaldo con manubrio
        mb.tube(fillet([(x, -0.30, 0.17), (x, 0.17, 0.17), (x, 0.21, 0.5), (x, 0.24, 0.94), (x, 0.36, 0.99)], 0.05, 8), ty, seg=12,
                mat="steel")
        mb.tube(fillet([(x, -0.30, 0.17), (x, -0.30, 0.52), (x, 0.19, 0.52)], 0.04, 8), ty, seg=12, mat="steel")
        port.lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.017, 0.01), (0.016, 0.11), (0.015, 0.12), (0.0, 0.12)], seg=14, mat="rubber",
                   M=_T(x, 0.28, 0.99) @ _Rx(-90))                                      # puño del manubrio
        # descansabrazos
        mb.tube(fillet([(x, -0.22, 0.52), (x, -0.22, 0.70), (x, 0.13, 0.70), (x, 0.15, 0.52)], 0.03, 6), 0.0095, seg=10, mat="steel")
        cushion(mb, _T(x, -0.04, 0.705), 0.055, 0.32, 0.03, mat="vinyl", r=0.012, crown=0.003, piping=False, seg=(14, 10))
        rbox(mb, (x - 0.003 * s_ - 0.002, -0.12, 0.53), (x - 0.003 * s_ + 0.002, 0.12, 0.69), "plastic", r=0.01)
        # rueda trasera 24"
        xw = s_ * (W / 2 + 0.055)
        Mw = _T(xw, 0.12, 0.305) @ _Ry(90)
        _tire(mb, Mw, 0.286, 0.0165, n=96, m=12)
        port.lathe(mb, [(0.262, -0.012), (0.27, -0.012), (0.272, -0.006), (0.272, 0.006), (0.27, 0.012), (0.262, 0.012), (0.258, 0.0),
                        (0.262, -0.012)], seg=72, mat="aluminium", M=Mw, caps=False)
        port.lathe(mb, [(0.0, -0.035), (0.022, -0.035), (0.022, 0.035), (0.0, 0.035)], seg=16, mat="aluminium", M=Mw)
        for fl in (-0.03, 0.03):
            port.lathe(mb, [(0.0, fl - 0.002), (0.034, fl - 0.002), (0.034, fl + 0.002), (0.0, fl + 0.002)], seg=18, mat="aluminium", M=Mw)
        for k in range(18):
            fl = -0.03 if k % 2 else 0.03
            a = 2 * PI * k / 18
            a2 = a + (0.35 if k % 2 else -0.35)
            p0 = Mw @ Vector((0.03 * math.cos(a), 0.03 * math.sin(a), fl))
            p1 = Mw @ Vector((0.259 * math.cos(a2), 0.259 * math.sin(a2), 0.0))
            mb.cyl(p0, p1, 0.0011, seg=4, mat="steel")
        Mp = _T(xw + s_ * 0.035, 0.12, 0.305) @ _Ry(90)
        _tire(mb, Mp, 0.268, 0.0085, n=72, m=8, tread=False, mat="aluminium")
        for k in range(4):
            a = PI / 2 * k + PI / 4
            mb.cyl(Mp @ Vector((0.268 * math.cos(a), 0.268 * math.sin(a), 0.0)), Mw @ Vector((0.266 * math.cos(a), 0.266 * math.sin(a), 0.0)),
                   0.004, seg=6, mat="aluminium")
        mb.cyl((xw - s_ * 0.05, 0.12, 0.305), (xw + s_ * 0.04, 0.12, 0.305), 0.006, seg=8, mat="steel")
        port.lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.008), (0.006, 0.012), (0.0, 0.012)], seg=10, mat="steel",
                   M=_T(xw + s_ * 0.04, 0.12, 0.305) @ _Ry(90 * s_))
        # freno de palanca
        mb.box((x + s_ * 0.012 - 0.008, -0.05, 0.43), (x + s_ * 0.012 + 0.008, 0.0, 0.47), "steel")
        mb.tube([(x + s_ * 0.02, -0.02, 0.45), (x + s_ * 0.04, -0.09, 0.56)], 0.006, seg=8, mat="steel")
        port.lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.012, 0.05), (0.0, 0.06)], seg=10, mat="rubber",
                   M=_T(x + s_ * 0.04, -0.09, 0.56) @ Matrix.Rotation(math.atan2(-0.07, 0.11), 4, "X"))
        mb.box((x + s_ * 0.035, 0.02, 0.4), (x + s_ * 0.045, 0.08, 0.42), "steel")
        # horquilla y rueda delantera 8"
        port.lathe(mb, [(0.0, 0.0), (0.018, 0.0), (0.018, 0.06), (0.0, 0.06)], seg=12, mat="steel", M=_T(x, -0.30, 0.17))
        yaw = float(r.uniform(-25, 25))
        Mf = _T(x, -0.30, 0.17) @ _Rz(yaw)
        for sx in (-1, 1):
            mb.tube([tuple(Mf @ Vector((sx * 0.022, 0.0, -0.005))), tuple(Mf @ Vector((sx * 0.022, -0.04, -0.07)))], 0.005, seg=6, mat="steel")
        _tire(mb, Mf @ _T(0, -0.04, -0.07) @ _Ry(90), 0.085, 0.016, n=40, m=10, tread=False)
        port.lathe(mb, [(0.0, -0.016), (0.075, -0.016), (0.075, 0.016), (0.0, 0.016)], seg=28, mat="plastic", M=Mf @ _T(0, -0.04, -0.07) @ _Ry(90))
        # descansapiés abatible
        mb.tube(fillet([(x, -0.27, 0.48), (x - s_ * 0.0, -0.40, 0.35), (x - s_ * 0.02, -0.45, 0.14)], 0.05, 6), 0.0095, seg=10, mat="steel")
        Mfp = _T(x - s_ * 0.02, -0.47, 0.13) @ _Rz(float(r.uniform(-8, 8)))
        xa, xb = sorted((0.0, -s_ * 0.17))
        rbox(mb, (xa, -0.08, 0.0), (xb, 0.07, 0.012), "plastic", r=0.004, m=Mfp)
        for k in range(6):
            yy = -0.07 + k * 0.025
            mb.box((xa + 0.01, yy, 0.012), (xb - 0.01, yy + 0.008, 0.016), "plastic", m=Mfp)
        mb.tube([tuple(Mfp @ Vector((xa + 0.02, 0.07, 0.012))), tuple(Mfp @ Vector((xa + 0.02, 0.1, 0.09))),
                 tuple(Mfp @ Vector((xb - 0.02, 0.1, 0.09))), tuple(Mfp @ Vector((xb - 0.02, 0.07, 0.012)))], 0.004, seg=6, mat="rubber")
        # antivuelco
        mb.tube(fillet([(x, 0.19, 0.18), (x, 0.32, 0.12), (x, 0.38, 0.1)], 0.03, 6), 0.0095, seg=10, mat="steel")
        port.lathe(mb, [(0.0, -0.01), (0.022, -0.01), (0.022, 0.01), (0.0, 0.01)], seg=12, mat="rubber", M=_T(x, 0.38, 0.09) @ _Ry(90))
    # tijera plegable bajo el asiento
    for (y0, y1) in ((-0.2, 0.15), (0.15, -0.2)):
        mb.tube([(-W / 2, y0, 0.52), (W / 2, y1, 0.2)], 0.0105, seg=10, mat="steel")
    mb.cyl((-0.01, -0.025, 0.36), (0.01, -0.025, 0.36), 0.014, seg=10, mat="steel")
    # lonas: asiento con comba y respaldo, con dobladillo y costura
    shell_strip(mb, [(-0.28, 0.0), (-0.2, -0.018), (-0.05, -0.032), (0.08, -0.03), (0.17, -0.012), (0.2, 0.0)], W + 0.02, 0.006, "vinyl",
                m=_T(0, 0, 0.525), smooth_n=4)
    shell_strip(mb, [(0.0, 0.0), (0.035, 0.12), (0.045, 0.25), (0.04, 0.38), (0.03, 0.44)], W + 0.02, 0.006, "vinyl",
                m=_T(0, 0.2, 0.52) @ _Rx(-6), smooth_n=4)
    for x in (-W / 2 - 0.004, W / 2 + 0.004):
        mb.tube([(x, -0.27, 0.528), (x, 0.19, 0.528)], 0.003, seg=5, mat="vinyl")
    return mb


def stretcher(seed=0):
    """Camilla de traslado: base con cubierta de plástico, columna hidráulica con fuelle, 4 rodajas de 150 mm (dos con freno),
    bastidor con colchoneta tapizada y sábana, barandales abatibles, manerales y portasueros plegado."""
    r = rng(seed)
    mb = MB()
    L, W = 1.95, 0.64
    for (sx, sy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        caster_pro(mb, _T(sx * (W / 2 - 0.06), sy * (L / 2 - 0.12), 0.0), d=0.15, brake=(sy > 0), swivel=float(r.uniform(-40, 40)))
    rbox(mb, (-W / 2 + 0.03, -L / 2 + 0.06, 0.19), (W / 2 - 0.03, L / 2 - 0.06, 0.24), "steel", r=0.012)
    rbox(mb, (-W / 2 + 0.05, -L / 2 + 0.1, 0.24), (W / 2 - 0.05, L / 2 - 0.1, 0.31), "sign_white", r=0.03)
    for y in (-0.45, 0.45):
        port.lathe(mb, [(0.0, 0.0), (0.06, 0.0), (0.06, 0.02)] + [(0.05 + 0.008 * (k % 2), 0.02 + 0.02 * k) for k in range(12)] +
                   [(0.05, 0.26), (0.0, 0.26)], seg=16, mat="rubber", M=_T(0, y, 0.31))
        mb.cyl((0, y, 0.57), (0, y, 0.61), 0.05, seg=16, mat="steel")
    rbox(mb, (-W / 2, -L / 2, 0.61), (W / 2, L / 2, 0.64), "steel", r=0.008)
    cushion(mb, _T(0, 0, 0.64), W - 0.04, L - 0.06, 0.075, mat="vinyl", r=0.03, crown=0.006, seg=(40, 18))
    rbox(mb, (-W / 2 + 0.01, -L / 2 + 0.06, 0.712), (W / 2 - 0.01, L / 2 - 0.35, 0.718), "linen", r=0.003)
    for s_ in (-1, 1):
        xr = s_ * (W / 2 + 0.02)
        mb.tube(fillet([(xr, -0.62, 0.62), (xr, -0.62, 0.92), (xr, 0.62, 0.92), (xr, 0.62, 0.62)], 0.05, 8), 0.0105, seg=10,
                mat="steel")
        for z in (0.72, 0.82):
            mb.tube([(xr, -0.62, z), (xr, 0.62, z)], 0.008, seg=8, mat="steel", caps=False)
    for yy in (-L / 2 - 0.08, L / 2 + 0.08):
        sg_ = 1 if yy > 0 else -1
        mb.tube(fillet([(-W / 2 + 0.07, yy - sg_ * 0.07, 0.62), (-W / 2 + 0.07, yy, 0.82), (W / 2 - 0.07, yy, 0.82),
                        (W / 2 - 0.07, yy - sg_ * 0.07, 0.62)], 0.05, 8), 0.013, seg=12, mat="steel")
        for x in (-W / 2 + 0.07, W / 2 - 0.07):
            port.lathe(mb, [(0.0, 0.0), (0.019, 0.0), (0.019, 0.1), (0.0, 0.1)], seg=12, mat="rubber",
                       M=_T(x, yy - sg_ * 0.035, 0.73) @ Matrix.Rotation(-sg_ * 0.6, 4, "X"))
    mb.tube([(W / 2 - 0.02, L / 2 - 0.02, 0.6), (W / 2 - 0.02, L / 2 - 0.02, 1.05)], 0.011, seg=10, mat="steel")
    return mb


def desk(w=1.4, d=0.7, seed=0, monitor=True, papers=True):
    """Escritorio metálico con cubierta laminada, pedestal de cajones, monitor, teclado, teléfono, carpetas y papeles."""
    r = rng(seed)
    mb = MB()
    h = 0.75
    rbox(mb, (-w / 2, -d / 2, h - 0.03), (w / 2, d / 2, h), "wood", r=0.01)
    rbox(mb, (w / 2 - 0.42, -d / 2 + 0.03, 0.02), (w / 2 - 0.02, d / 2 - 0.03, h - 0.03), "metal_paint", r=0.005)
    for k, z in enumerate((0.05, 0.27, 0.5)):
        mb.box((w / 2 - 0.41, -d / 2 + 0.026, z), (w / 2 - 0.03, -d / 2 + 0.03, z + 0.2), "metal_paint")
        mb.box((w / 2 - 0.27, -d / 2 + 0.01, z + 0.15), (w / 2 - 0.17, -d / 2 + 0.026, z + 0.165), "steel")
    mb.box((-w / 2 + 0.02, -d / 2 + 0.03, 0.0), (-w / 2 + 0.05, d / 2 - 0.03, h - 0.03), "metal_paint")
    mb.box((-w / 2 + 0.05, d / 2 - 0.05, 0.3), (w / 2 - 0.42, d / 2 - 0.03, h - 0.03), "metal_paint")
    if monitor:
        x = float(r.uniform(-0.15, 0.15))
        mb.box((x - 0.1, 0.05, h), (x + 0.1, 0.2, h + 0.015), "plastic")
        mb.box((x - 0.02, 0.15, h + 0.015), (x + 0.02, 0.18, h + 0.15), "plastic")
        rbox(mb, (x - 0.27, 0.09, h + 0.1), (x + 0.27, 0.13, h + 0.43), "plastic", r=0.01)
        mb.box((x - 0.255, 0.088, h + 0.115), (x + 0.255, 0.09, h + 0.415), "cable")
        rbox(mb, (x - 0.22, -0.2, h), (x + 0.22, -0.05, h + 0.02), "plastic", r=0.008)
        mb.box((x + 0.27, -0.15, h), (x + 0.33, -0.08, h + 0.02), "plastic")
    rbox(mb, (-w / 2 + 0.1, 0.05, h), (-w / 2 + 0.3, 0.27, h + 0.08), "cable", r=0.02)
    mb.tube([(-w / 2 + 0.2, 0.05, h + 0.04), (-w / 2 + 0.25, -0.05, h + 0.003), (-w / 2 + 0.32, -0.08, h + 0.003)], 0.004, seg=4, mat="cable")
    if papers:
        for k in range(int(r.integers(2, 5))):
            xx, yy = float(r.uniform(-w / 2 + 0.3, w / 2 - 0.3)), float(r.uniform(-d / 2 + 0.1, -0.05))
            mb.box((xx - 0.105, yy - 0.15, h), (xx + 0.105, yy + 0.15, h + 0.003 + 0.002 * k), "paper",
                   m=_T(xx, yy, 0) @ _Rz(float(r.uniform(-25, 25))) @ _T(-xx, -yy, 0))
        for k in range(int(r.integers(3, 7))):
            xx = w / 2 - 0.4 + k * 0.055
            mat = ("plastic_blue", "sign_red", "sign_green", "plastic")[int(r.integers(0, 4))]
            mb.box((xx, 0.12, h), (xx + 0.05, 0.4, h + 0.31), mat)
    return mb


def filing_cabinet(seed=0, n=4):
    """Archivero metálico de n cajones con jaladeras y portaetiquetas."""
    mb = MB()
    h = 0.33 * n + 0.04
    rbox(mb, (-0.235, -0.31, 0.0), (0.235, 0.31, h), "metal_paint", r=0.008)
    for k in range(n):
        z = 0.04 + k * 0.33
        mb.box((-0.225, -0.314, z), (0.225, -0.31, z + 0.32), "metal_paint")
        mb.box((-0.07, -0.33, z + 0.19), (0.07, -0.314, z + 0.21), "steel")
        mb.box((-0.04, -0.318, z + 0.24), (0.04, -0.314, z + 0.27), "paper")
    return mb


def shelving(w=1.0, d=0.4, h=2.0, shelves=5, seed=0, stock=True, stock_kind="pharmacy"):
    """Anaquel de ángulo ranurado con entrepaños de lámina, lleno de cajas de medicamento, frascos y rollos (farmacia) o de
    sábanas dobladas (lavandería)."""
    r = rng(seed)
    mb = MB()
    for (x, y) in ((-w / 2, -d / 2), (w / 2, -d / 2), (-w / 2, d / 2), (w / 2, d / 2)):
        port.angle_bar(mb, (x, y, 0.0), (x, y, h), leg=0.035, t=0.002, mat="steel",
                       up=(1 if x < 0 else -1, 0, 0), flip=y > 0)
        mb.cyl((x, y, 0.0), (x, y, 0.01), 0.02, seg=6, mat="rubber")
    zs = [0.1 + i * (h - 0.15) / (shelves - 1) for i in range(shelves)]
    for z in zs:
        mb.box((-w / 2, -d / 2, z - 0.025), (w / 2, d / 2, z), "steel")
    if not stock:
        return mb
    for z in zs[:-1] + ([zs[-1]] if r.random() < 0.5 else []):
        x = -w / 2 + 0.03
        top = (zs[zs.index(z) + 1] - 0.04) if z != zs[-1] else z + 0.3
        while x < w / 2 - 0.08:
            if stock_kind == "linen":
                bw = 0.36
                n = int(r.integers(3, 7))
                for k in range(n):
                    rbox(mb, (x, -d / 2 + 0.03, z + k * 0.045), (x + bw, d / 2 - 0.04, z + (k + 1) * 0.045 - 0.003),
                         "linen", r=0.02)
                x += bw + 0.04
                continue
            kind = r.random()
            if kind < 0.6:
                bw = float(r.uniform(0.08, 0.2))
                bh = min(float(r.uniform(0.06, 0.2)), top - z - 0.01)
                bd = float(r.uniform(0.12, d - 0.05))
                mat = ("sign_white", "paper", "plastic", "sign_blue", "sign_white", "sign_red")[int(r.integers(0, 6))]
                for k in range(int(r.integers(1, 3))):
                    zz = z + k * bh
                    if zz + bh > top:
                        break
                    mb.box((x, -d / 2 + 0.03, zz), (x + bw, -d / 2 + 0.03 + bd, zz + bh - 0.002), mat)
                x += bw + 0.008
            elif kind < 0.85:
                rr = float(r.uniform(0.025, 0.045))
                hh = min(float(r.uniform(0.09, 0.18)), top - z - 0.03)
                for k in range(int(r.integers(2, 5))):
                    cx = x + rr + k * (2 * rr + 0.004)
                    if cx > w / 2 - 0.05:
                        break
                    mat = ("plastic", "glass", "sign_white")[int(r.integers(0, 3))]
                    port.lathe(mb, [(0.0, 0.0), (rr, 0.0), (rr, hh * 0.8), (rr * 0.5, hh * 0.9), (rr * 0.5, hh), (0.0, hh)], seg=10, mat=mat,
                               M=_T(cx, -d / 2 + 0.06, z))
                    mb.cyl((cx, -d / 2 + 0.06, z + hh), (cx, -d / 2 + 0.06, z + hh + 0.02), rr * 0.55, seg=10, mat="sign_white")
                x += 0.2
            else:
                x += float(r.uniform(0.05, 0.15))
    return mb


def counter(w=2.4, d=0.6, h=1.05, seed=0, top="wood", front="plastic"):
    """Mostrador de enfermería / farmacia: frente laminado con zoclo, cubierta con faldón y repisa interior de trabajo a 0,75."""
    mb = MB()
    mb.box((-w / 2, -d / 2 + 0.02, 0.0), (w / 2, -d / 2 + 0.06, 0.1), "rubber")
    mb.box((-w / 2, -d / 2 + 0.02, 0.1), (w / 2, -d / 2 + 0.05, h - 0.03), front)
    for s in (-1, 1):
        mb.box((s * w / 2 - (0.03 if s > 0 else 0), -d / 2 + 0.02, 0.0), (s * w / 2 + (0.0 if s > 0 else 0.03), d / 2, h - 0.03), front)
    rbox(mb, (-w / 2 - 0.02, -d / 2 - 0.05, h - 0.03), (w / 2 + 0.02, -d / 2 + 0.25, h), top, r=0.015)
    mb.box((-w / 2 + 0.03, -d / 2 + 0.05, 0.72), (w / 2 - 0.03, d / 2, 0.75), top)
    return mb


def clock(seed=0):
    """Reloj de pared Ø 0,3 (origen: cara del muro, centro)."""
    mb = MB()
    M = _Rx(90)
    port.lathe(mb, [(0.0, 0.0), (0.15, 0.0), (0.155, 0.01), (0.15, 0.045), (0.0, 0.045)], seg=28, mat="plastic", M=_T(0, 0, 0) @ M)
    mb.cyl((0, -0.045, 0), (0, -0.046, 0), 0.135, seg=28, mat="sign_white")
    for k in range(12):
        a = 2 * PI * k / 12
        mb.box((0.118 * math.cos(a) - 0.003, -0.048, 0.118 * math.sin(a) - 0.003), (0.118 * math.cos(a) + 0.003, -0.046, 0.118 * math.sin(a) + 0.003),
               "cable")
    mb.box((-0.004, -0.05, -0.004), (0.06, -0.048, 0.004), "cable", m=_Ry(-40))
    mb.box((-0.003, -0.052, -0.003), (0.1, -0.05, 0.003), "cable", m=_Ry(-160))
    return mb


def notice_board(w=0.9, h=0.6, seed=0, posters=()):
    """Tablero de corcho con marco de aluminio, hojas clavadas y carteles con texto (origen: muro, centro inferior)."""
    r = rng(seed)
    mb = MB()
    mb.box((-w / 2, -0.02, 0.0), (w / 2, 0.0, h), "wood")
    for (a, b) in (((-w / 2, 0), (w / 2, 0.02)), ((-w / 2, h - 0.02), (w / 2, h)), ((-w / 2, 0), (-w / 2 + 0.02, h)), ((w / 2 - 0.02, 0), (w / 2, h))):
        mb.box((a[0], -0.03, a[1]), (b[0], -0.02, b[1]), "aluminium")
    for k in range(int(r.integers(4, 8))):
        pw, ph = float(r.uniform(0.15, 0.22)), float(r.uniform(0.2, 0.3))
        x = float(r.uniform(-w / 2 + 0.05 + pw / 2, w / 2 - 0.05 - pw / 2))
        z = float(r.uniform(0.05 + ph / 2, h - 0.05 - ph / 2))
        mb.box((x - pw / 2, -0.022, z - ph / 2), (x + pw / 2, -0.0205 - 0.0004 * k, z + ph / 2), "paper",
               m=_T(x, 0, z) @ _Ry(float(r.uniform(-6, 6))) @ _T(-x, 0, -z))
        mb.cyl((x, -0.025 - 0.0004 * k, z + ph / 2 - 0.02), (x, -0.02, z + ph / 2 - 0.02), 0.006, seg=6,
               mat=("sign_red", "sign_blue", "sign_green")[k % 3])
    for k, s in enumerate(posters):
        x = -w / 2 + 0.2 + k * 0.45
        mb.box((x - 0.15, -0.026, h * 0.3), (x + 0.15, -0.024, h * 0.3 + 0.36), "sign_white")
        text(mb, s, 0.03, 0.001, "sign_blue", _T(x, -0.026, h * 0.3 + 0.28) @ _Rx(90))
        mb.box((x - 0.1, -0.0262, h * 0.3 + 0.06), (x + 0.1, -0.026, h * 0.3 + 0.22), "plastic_blue")
    return mb


def poster(s, w=0.42, h=0.6, bg="sign_white", fg="sign_blue", art="plastic_blue"):
    """Cartel de salud pegado al muro (hoja + texto + bloque de ilustración)."""
    mb = MB()
    mb.box((-w / 2, -0.002, 0.0), (w / 2, 0.0, h), bg)
    text(mb, s, w * 0.09, 0.0008, fg, _T(0, -0.002, h * 0.82) @ _Rx(90))
    mb.box((-w * 0.35, -0.0026, h * 0.15), (w * 0.35, -0.002, h * 0.72), art)
    return mb


def water_dispenser():
    """Despachador de garrafón: gabinete blanco, dos llaves, charola y garrafón azul translúcido."""
    mb = MB()
    rbox(mb, (-0.16, -0.16, 0.0), (0.16, 0.16, 1.0), "sign_white", r=0.02)
    mb.box((-0.12, -0.165, 0.62), (0.12, -0.16, 0.8), "plastic")
    for x, m in ((-0.05, "sign_blue"), (0.05, "sign_red")):
        mb.box((x - 0.015, -0.19, 0.74), (x + 0.015, -0.165, 0.77), m)
    mb.box((-0.1, -0.2, 0.6), (0.1, -0.16, 0.615), "plastic")
    port.lathe(mb, [(0.0, 0.0), (0.04, 0.0), (0.04, 0.05), (0.13, 0.1), (0.135, 0.36), (0.12, 0.42), (0.0, 0.43)], seg=16, mat="glass",
               M=_T(0, 0, 1.0) @ _Rx(180) @ _T(0, 0, -0.43))
    return mb


def potted_plant(seed=0, h=0.9):
    """Maceta de barro con planta de hojas largas (vegetación de doble cara)."""
    r = rng(seed)
    mb = MB()
    port.lathe(mb, [(0.0, 0.0), (0.13, 0.0), (0.18, 0.32), (0.19, 0.34), (0.19, 0.36), (0.0, 0.36)], seg=16, mat="brick")
    mb.cyl((0, 0, 0.33), (0, 0, 0.34), 0.175, seg=16, mat="rubble")
    for k in range(int(r.integers(9, 14))):
        a = float(r.uniform(0, 2 * PI))
        L = float(r.uniform(0.35, h * 0.8))
        el = float(r.uniform(35, 75))
        pts = []
        for i in range(7):
            t = i / 6
            rad = L * t * math.cos(math.radians(el)) * (1 + 0.25 * t)
            z = 0.34 + L * t * math.sin(math.radians(el)) * (1 - 0.45 * t * t)
            pts.append((rad * math.cos(a), rad * math.sin(a), z))
        wd = float(r.uniform(0.03, 0.06))
        side = Vector((-math.sin(a), math.cos(a), 0)) * wd
        vs = []
        for i, p in enumerate(pts):
            k2 = math.sin(PI * min(1.0, i / 5.5)) if i else 0.15
            c = Vector(p)
            vs.append((mb.bm.verts.new(c - side * k2), mb.bm.verts.new(c + side * k2)))
        for i in range(len(vs) - 1):
            mb.face([vs[i][0], vs[i][1], vs[i + 1][1], vs[i + 1][0]], "vegetation")
    return mb


def trash_bin(seed=0, pedal=True):
    """Bote de basura de pedal (consultorio) o de tapa basculante."""
    mb = MB()
    port.lathe(mb, [(0.0, 0.0), (0.13, 0.0), (0.15, 0.45), (0.0, 0.45)], seg=16, mat="sign_white" if pedal else "plastic")
    port.lathe(mb, [(0.0, 0.45), (0.155, 0.45), (0.155, 0.47), (0.12, 0.5), (0.0, 0.5)], seg=16, mat="steel" if pedal else "plastic")
    if pedal:
        mb.box((-0.05, -0.19, 0.01), (0.05, -0.12, 0.03), "steel")
    return mb


def sanitizer(seed=0):
    """Despachador de gel en muro (origen: cara del muro, centro inferior)."""
    mb = MB()
    rbox(mb, (-0.06, -0.1, 0.0), (0.06, 0.0, 0.25), "sign_white", r=0.01)
    mb.box((-0.04, -0.105, 0.03), (0.04, -0.1, 0.08), "plastic_blue")
    mb.box((-0.03, -0.102, 0.12), (0.03, -0.1, 0.2), "glass")
    return mb


def extinguisher(seed=0):
    """Extintor PQS de 6 kg colgado de su gancho con letrero arriba (origen: cara del muro, piso)."""
    mb = MB()
    zb = 1.0
    port.lathe(mb, [(0.0, 0.0), (0.075, 0.0), (0.08, 0.02), (0.08, 0.42), (0.06, 0.47), (0.02, 0.5), (0.0, 0.5)], seg=16, mat="sign_red",
               M=_T(0, -0.1, zb))
    mb.cyl((0, -0.1, zb + 0.5), (0, -0.1, zb + 0.56), 0.016, seg=8, mat="steel")
    mb.box((-0.05, -0.115, zb + 0.55), (0.06, -0.085, zb + 0.57), "rubber")
    mb.tube([(0.02, -0.1, zb + 0.54), (0.09, -0.11, zb + 0.5), (0.1, -0.12, zb + 0.2), (0.08, -0.12, zb + 0.12)], 0.008, seg=6, mat="rubber")
    mb.box((-0.04, -0.03, zb + 0.35), (0.04, 0.0, zb + 0.45), "steel")
    mb.box((-0.02, -0.05, zb + 0.4), (0.02, -0.025, zb + 0.43), "steel")
    mb.box((-0.06, -0.181, zb + 0.15), (0.06, -0.18, zb + 0.32), "sign_white")
    mb.join(sign_plate("FIRE", 0.24, 0.12, bg="sign_red", fg="sign_white", t=0.004), _T(0, 0, zb + 0.75))
    return mb


def fluorescent(L=1.22, W=0.30, recessed=False):
    """Luminaria fluorescente de sobreponer con difusor de acrílico (origen: plafón, centro; cuelga hacia -Z)."""
    mb = MB()
    if recessed:
        mb.box((-L / 2 - 0.02, -W / 2 - 0.02, -0.006), (L / 2 + 0.02, W / 2 + 0.02, 0.0), "sign_white")
        mb.box((-L / 2, -W / 2, -0.008), (L / 2, W / 2, -0.006), "plastic")
        return mb
    rbox(mb, (-L / 2, -W / 2, -0.07), (L / 2, W / 2, 0.0), "sign_white", r=0.01)
    rbox(mb, (-L / 2 + 0.02, -W / 2 + 0.02, -0.085), (L / 2 - 0.02, W / 2 - 0.02, -0.07), "plastic", r=0.02)
    return mb


def ceiling_fan(seed=0, drop=0.35):
    """Ventilador de techo: tubo, motor, 3 aspas de madera sobre brazos (origen: losa, cuelga hacia -Z)."""
    r = rng(seed)
    mb = MB()
    mb.cyl((0, 0, 0), (0, 0, -0.05), 0.06, seg=12, mat="sign_white", r1=0.04)
    mb.cyl((0, 0, -0.05), (0, 0, -drop), 0.012, seg=8, mat="steel")
    port.lathe(mb, [(0.0, 0.0), (0.07, 0.0), (0.11, -0.03), (0.11, -0.08), (0.08, -0.11), (0.0, -0.12)], seg=16, mat="sign_white",
               M=_T(0, 0, -drop))
    a0 = float(r.uniform(0, 120))
    for k in range(3):
        a = math.radians(a0 + 120 * k)
        M = _T(0, 0, -drop - 0.07) @ Matrix.Rotation(a, 4, "Z")
        mb.box((0.08, -0.015, -0.006), (0.2, 0.015, 0.0), "steel", m=M)
        mb.box((0.18, -0.065, -0.012), (0.68, 0.065, -0.004), "wood_dark", m=M @ _Rx(10))
    return mb


def split_indoor(seed=0):
    """Minisplit (unidad interior) 0,8 × 0,2 × 0,28 con rejilla y lama, tubería forrada que sale por el muro (origen: muro, centro)."""
    mb = MB()
    rbox(mb, (-0.4, -0.2, 0.0), (0.4, 0.0, 0.28), "sign_white", r=0.03)
    for k in range(12):
        x = -0.33 + k * 0.055
        mb.box((x, -0.205, 0.03), (x + 0.04, -0.2, 0.08), "plastic")
    mb.box((-0.37, -0.215, 0.0), (0.37, -0.195, 0.025), "plastic", m=_T(0, -0.2, 0.02) @ _Rx(25) @ _T(0, 0.2, -0.02))
    mb.box((0.27, -0.202, 0.2), (0.33, -0.2, 0.22), "sign_green")
    return mb


def wall_lamp():
    """Arbotante exterior tipo farol (limpio, funcionando): placa, brazo, farol de vidrio con capuchón (origen: muro, centro)."""
    mb = MB()
    mb.box((-0.06, -0.02, -0.1), (0.06, 0.0, 0.1), "metal_paint")
    mb.tube([(0, -0.02, 0.0), (0, -0.12, 0.04), (0, -0.16, 0.12)], 0.012, seg=6, mat="metal_paint")
    port.lathe(mb, [(0.0, 0.0), (0.05, 0.0), (0.075, 0.2), (0.0, 0.2)], seg=6, mat="glass", M=_T(0, -0.16, -0.08))
    port.lathe(mb, [(0.0, 0.0), (0.09, 0.0), (0.03, 0.06), (0.0, 0.08)], seg=6, mat="metal_paint", M=_T(0, -0.16, 0.12))
    port.lathe(mb, [(0.0, 0.0), (0.055, 0.0), (0.055, 0.02), (0.0, 0.02)], seg=6, mat="metal_paint", M=_T(0, -0.16, -0.1))
    return mb


def window_grille(w, h, seed=0, mat="paint_green"):
    """Reja de herrería pintada (limpia): marco de solera, barrotes cuadrados y adornos de voluta en la parte alta
    (local u 0..w, v 0..h, plano y = -0,03..0 por fuera del vano)."""
    mb = MB()
    t = 0.012
    for (a, b) in (((0, 0), (w, 0.03)), ((0, h - 0.03), (w, h)), ((0, 0), (0.03, h)), ((w - 0.03, 0), (w, h))):
        mb.box((a[0], -0.03, a[1]), (b[0], -0.03 + t, b[1]), mat)
    n = max(3, int(round(w / 0.13)))
    for i in range(1, n):
        x = i * w / n
        mb.box((x - 0.007, -0.03, 0.03), (x + 0.007, -0.016, h - 0.03), mat)
    zm = h * 0.72
    mb.box((0.03, -0.03, zm - 0.012), (w - 0.03, -0.018, zm + 0.012), mat)
    for i in range(n):
        x0 = i * w / n
        c = Vector((x0 + w / n / 2, -0.024, zm + (h - 0.03 - zm) / 2))
        rad = min(w / n, h - 0.03 - zm) * 0.38
        pts = [(c.x + rad * math.cos(a), c.y, c.z + rad * math.sin(a)) for a in [k * 2 * PI / 10 for k in range(11)]]
        mb.tube(pts, 0.005, seg=4, mat=mat)
    for z in (0.15, h - 0.15):
        for x in (0.0, w):
            mb.box((x - 0.02, -0.02, z - 0.01), (x + 0.02, 0.05, z + 0.01), mat)
    return mb


def zloft(mb, stations, seg=20, mat="sign_white", M=None, ex=2.4, caps=True):
    """Sólido por anillos superelípticos horizontales [(z, ancho_x, largo_y, centro_y)] de abajo hacia arriba."""
    rings = []
    for (z, wx, wy, cy) in stations:
        ring = []
        for k in range(seg):
            a = 2 * PI * k / seg
            c, s_ = math.cos(a), math.sin(a)
            x = wx / 2 * math.copysign(abs(c) ** (2 / ex), c)
            y = cy + wy / 2 * math.copysign(abs(s_) ** (2 / ex), s_)
            p = Vector((x, y, z))
            ring.append(mb.bm.verts.new((M @ p) if M is not None else p))
        rings.append(ring)
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(seg):
            mb.face([A[k], A[(k + 1) % seg], B[(k + 1) % seg], B[k]], mat)
    if caps:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)


def toilet(seed=0):
    """Inodoro de cerámica (taza ovalada sobre pedestal, tanque, asiento y tapa levantada). Frente -Y, respaldo en y = +0,36."""
    mb = MB()
    zloft(mb, [(0.0, 0.22, 0.34, 0.06), (0.03, 0.21, 0.33, 0.06), (0.2, 0.24, 0.38, 0.03), (0.33, 0.34, 0.5, -0.01),
               (0.38, 0.37, 0.53, -0.015), (0.39, 0.36, 0.52, -0.015)], seg=24, mat="sign_white", ex=2.2)
    zloft(mb, [(0.39, 0.37, 0.5, -0.02), (0.415, 0.37, 0.5, -0.02)], seg=24, mat="plastic", ex=2.2)
    zloft(mb, [(0.0, 0.35, 0.025, 0.0), (0.4, 0.33, 0.025, 0.0)], seg=16, mat="plastic", ex=2.2,
          M=_T(0, 0.17, 0.415) @ _Rx(-5))                                                     # tapa levantada
    rbox(mb, (-0.19, 0.2, 0.40), (0.19, 0.36, 0.80), "sign_white", r=0.03)
    rbox(mb, (-0.2, 0.19, 0.80), (0.2, 0.37, 0.83), "sign_white", r=0.03)
    mb.box((0.12, 0.185, 0.72), (0.17, 0.2, 0.74), "steel")
    mb.cyl((0.1, 0.36, 0.2), (0.1, 0.45, 0.2), 0.012, seg=6, mat="steel")
    return mb


def sink(seed=0, mirror=True):
    """Lavabo de pared de cerámica con llave, desagüe cromado y espejo (origen: cara del muro, piso; sale hacia -Y)."""
    mb = MB()
    rbox(mb, (-0.25, -0.45, 0.72), (0.25, 0.0, 0.85), "sign_white", r=0.04)
    mb.box((-0.19, -0.38, 0.84), (0.19, -0.07, 0.851), "steel")
    mb.cyl((0, -0.05, 0.85), (0, -0.05, 0.95), 0.014, seg=8, mat="steel")
    mb.tube([(0, -0.05, 0.95), (0, -0.14, 0.97), (0, -0.18, 0.93)], 0.01, seg=6, mat="steel")
    mb.box((0.05, -0.07, 0.94), (0.11, -0.05, 0.96), "steel")
    mb.tube([(0, -0.25, 0.72), (0, -0.25, 0.55), (0, -0.1, 0.5), (0, 0.0, 0.5)], 0.016, seg=8, mat="steel")
    if mirror:
        mb.box((-0.25, -0.012, 1.15), (0.25, 0.0, 1.75), "steel")
        mb.box((-0.27, -0.008, 1.13), (0.27, 0.0, 1.77), "aluminium")
    return mb


def fridge(seed=0):
    """Refrigerador doméstico de dos puertas con jaladeras (frente -Y)."""
    mb = MB()
    rbox(mb, (-0.32, -0.32, 0.03), (0.32, 0.34, 1.65), "sign_white", r=0.03)
    mb.box((-0.31, -0.325, 1.12), (0.31, -0.32, 1.125), "plastic")
    for (z0, z1) in ((1.18, 1.5), (0.5, 1.05)):
        mb.box((0.24, -0.36, z0), (0.27, -0.325, z1), "steel")
    for x in (-0.28, 0.28):
        mb.box((x - 0.02, -0.28, 0.0), (x + 0.02, -0.2, 0.03), "rubber")
    return mb


def stove(seed=0):
    """Estufa de 4 quemadores con horno (frente -Y)."""
    mb = MB()
    rbox(mb, (-0.38, -0.3, 0.0), (0.38, 0.3, 0.9), "sign_white", r=0.01)
    mb.box((-0.38, -0.3, 0.9), (0.38, 0.3, 0.91), "steel")
    for (x, y) in ((-0.18, -0.12), (0.18, -0.12), (-0.18, 0.12), (0.18, 0.12)):
        port.lathe(mb, [(0.0, 0.0), (0.09, 0.0), (0.09, 0.012), (0.0, 0.012)], seg=12, mat="cable", M=_T(x, y, 0.91))
        for k in range(4):
            a = PI / 4 + PI / 2 * k
            mb.box((x - 0.006, y - 0.11, 0.922), (x + 0.006, y + 0.11, 0.935), "cable", m=_T(x, y, 0) @ _Rz(math.degrees(a)) @ _T(-x, -y, 0))
    mb.box((-0.3, -0.305, 0.12), (0.3, -0.3, 0.68), "cable")
    mb.box((-0.25, -0.33, 0.66), (0.25, -0.305, 0.68), "steel")
    rbox(mb, (-0.38, 0.27, 0.91), (0.38, 0.3, 1.05), "sign_white", r=0.005)
    for k in range(5):
        x = -0.3 + k * 0.15
        mb.cyl((x, -0.3, 0.8), (x, -0.33, 0.8), 0.018, seg=10, mat="cable")
    return mb


def washer(seed=0, front_load=True):
    """Lavadora de carga frontal: gabinete, ojo de buey con vidrio, panel de control (frente -Y)."""
    mb = MB()
    rbox(mb, (-0.3, -0.3, 0.0), (0.3, 0.3, 0.85), "sign_white", r=0.02)
    mb.box((-0.29, -0.305, 0.72), (0.29, -0.3, 0.83), "plastic")
    for x in (-0.2, 0.15):
        mb.cyl((x, -0.3, 0.775), (x, -0.32, 0.775), 0.025, seg=10, mat="plastic")
    M = _T(0, -0.3, 0.42) @ _Rx(90)
    port.lathe(mb, [(0.0, 0.0), (0.2, 0.0), (0.21, -0.03), (0.15, -0.045), (0.0, -0.045)], seg=24, mat="plastic", M=M)
    mb.cyl((0, -0.344, 0.42), (0, -0.346, 0.42), 0.14, seg=24, mat="glass")
    return mb


def mop_bucket(seed=0):
    """Cubeta con exprimidor y trapeador (lavandería)."""
    mb = MB()
    rbox(mb, (-0.2, -0.15, 0.06), (0.2, 0.15, 0.4), "paint_yellow", r=0.05)
    for (x, y) in ((-0.16, -0.11), (0.16, -0.11), (-0.16, 0.11), (0.16, 0.11)):
        caster(mb, (x, y, 0.0), r=0.025)
    mb.box((0.02, -0.12, 0.4), (0.18, 0.12, 0.58), "paint_yellow")
    mb.cyl((-0.08, 0.0, 0.25), (0.05, 0.05, 1.35), 0.012, seg=6, mat="steel")
    return mb


def cylinder_rack(n=2, seed=0, medical=True):
    """Tanques de oxígeno medicinal (verde y blanco) en carrito con cadena, o de gas LP en jaula (patio de servicio)."""
    mb = MB()
    for k in range(n):
        x = (k - (n - 1) / 2) * 0.27
        mat = "sign_green" if medical else "steel"
        port.lathe(mb, [(0.0, 0.0), (0.11, 0.0), (0.115, 0.03), (0.115, 1.25), (0.08, 1.35), (0.03, 1.4), (0.0, 1.4)], seg=16, mat=mat,
                   M=_T(x, 0, 0.02))
        if medical:
            port.lathe(mb, [(0.03, 1.36), (0.08, 1.33), (0.115, 1.25), (0.116, 1.2), (0.03, 1.2)], seg=16, mat="sign_white", M=_T(x, 0, 0.02),
                       caps=False)
        mb.cyl((x, 0, 1.42), (x, 0, 1.5), 0.02, seg=8, mat="steel")
        mb.cyl((x - 0.05, 0, 1.47), (x + 0.05, 0, 1.47), 0.012, seg=6, mat="steel")
        mb.cyl((x, 0, 1.53), (x, 0, 1.55), 0.035, seg=10, mat="sign_green" if medical else "cable")
    for z in (0.25, 1.0):
        mb.tube([(-(n - 1) * 0.135 - 0.13, -0.12, z), ((n - 1) * 0.135 + 0.13, -0.12, z)], 0.005, seg=4, mat="steel")
    mb.box((-(n - 1) * 0.135 - 0.15, -0.15, 0.0), ((n - 1) * 0.135 + 0.15, 0.15, 0.02), "steel")
    return mb


def xray_unit(seed=0):
    """Rayos X convencional: mesa flotante con colchoneta, columna de piso con brazo y cabezal con colimador, bucky de pared."""
    mb = MB()
    rbox(mb, (-0.35, -0.5, 0.0), (0.35, 0.5, 0.62), "sign_white", r=0.03)
    rbox(mb, (-0.4, -1.1, 0.62), (0.4, 1.1, 0.7), "plastic", r=0.03)
    rbox(mb, (-0.36, -1.0, 0.7), (0.36, 1.0, 0.74), "vinyl", r=0.03)
    mb.box((-0.06, -1.25, 0.0), (0.06, -1.1, 0.04), "steel")
    mb.box((0.62, -0.1, 0.0), (0.82, 0.1, 0.03), "steel")
    mb.box((0.66, -0.08, 0.03), (0.78, 0.08, 2.1), "sign_white")
    mb.box((0.0, -0.1, 1.6), (0.66, 0.1, 1.72), "sign_white")
    rbox(mb, (-0.17, -0.2, 1.38), (0.17, 0.2, 1.6), "plastic", r=0.04)
    rbox(mb, (-0.12, -0.12, 1.24), (0.12, 0.12, 1.38), "plastic", r=0.01)
    mb.box((-0.08, -0.08, 1.235), (0.08, 0.08, 1.24), "glass")
    mb.box((0.05, -0.13, 1.28), (0.1, -0.12, 1.34), "sign_green")
    return mb


def wall_bucky():
    """Bucky de pared: columna y portachasis (origen: muro, centro)."""
    mb = MB()
    mb.box((-0.1, -0.08, 0.0), (0.1, 0.0, 2.0), "sign_white")
    rbox(mb, (-0.25, -0.2, 0.9), (0.25, -0.08, 1.45), "plastic", r=0.02)
    mb.box((-0.2, -0.205, 0.98), (0.2, -0.2, 1.38), "cable")
    return mb


def lead_screen():
    """Mampara plomada con mirilla (cuarto de rayos X)."""
    mb = MB()
    mb.box((-0.5, -0.03, 0.08), (0.5, 0.03, 1.95), "sign_white")
    mb.box((-0.2, -0.032, 1.4), (0.2, 0.032, 1.7), "glass")
    for x in (-0.45, 0.45):
        mb.box((x - 0.04, -0.3, 0.0), (x + 0.04, 0.3, 0.08), "steel")
    return mb

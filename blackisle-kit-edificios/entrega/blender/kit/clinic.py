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
        # cara -y: Rx(90) (texto mirando a -y, legible desde -y); cara +y: Rz(180) @ Rx(90) (legible desde +y)
        M = _T(0, sgn * 0.009, zt - h / 2 - sz * 0.36) @ (_Rx(90) if sgn < 0 else _Rz(180) @ _Rx(90))
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
    colchón de vinilo con vivos, tendido a la medida (bajera remetida, cobija con esquinas de hospital, embozo de la
    sábana superior), almohada inflada por presión.
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
    sg.mattress(mb, Mm, Lm, Wm, Hm, seed=seed, fowler=fowler, hinge=hinge, covered=made)
    if made:
        sg.bed_linens(mb, Mm, Lm, Wm, Hm, seed=seed, blanket=blanket, fowler=fowler, hinge=hinge)
        a = math.radians(fowler)
        yp, zp = 0.68, Hm + 0.016
        if fowler > 0:
            dy = yp - hinge
            yp, zp = hinge + dy * math.cos(a) - zp * math.sin(a), dy * math.sin(a) + zp * math.cos(a)
        sg.pillow(mb, Mm @ _T(float(r.uniform(-0.03, 0.03)), yp, zp) @ _Rx(fowler) @ _Rz(float(r.uniform(-5, 5))), seed=seed % 4)
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


def poster(s, w=0.42, h=0.6, bg="sign_white", fg="sign_blue", art="plastic_blue"):
    """Cartel de salud pegado al muro (hoja + texto + bloque de ilustración)."""
    mb = MB()
    mb.box((-w / 2, -0.002, 0.0), (w / 2, 0.0, h), bg)
    text(mb, s, w * 0.09, 0.0008, fg, _T(0, -0.002, h * 0.82) @ _Rx(90))
    mb.box((-w * 0.35, -0.0026, h * 0.15), (w * 0.35, -0.002, h * 0.72), art)
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


# ======================================================================================================== vanos limpios
# Las ventanas y puertas de kit/openings vienen rotas (edificios abandonados). Un hospital en uso lleva todo entero.
def _al_frame(mb, w, h, y0, y1, prof_w=0.045, mat="aluminium"):
    """Marco perimetral de aluminio dentro del vano (local u 0..w, v 0..h), de y0 a y1, con canal y esquinas a inglete."""
    d = y1 - y0
    # marco como cuatro barras rectangulares con canal (más simple y exacto en las esquinas)
    for (u0, v0, u1, v1) in ((0.0, 0.0, w, prof_w), (0.0, h - prof_w, w, h), (0.0, 0.0, prof_w, h), (w - prof_w, 0.0, w, h)):
        mb.box((u0, y0, v0), (u1, y1, v1), mat, bevel=0.002)
    for (u0, v0, u1, v1) in ((prof_w, prof_w - 0.006, w - prof_w, prof_w), (prof_w, h - prof_w, w - prof_w, h - prof_w + 0.006)):
        for yy in (y0 + d * 0.33, y0 + d * 0.62):
            mb.box((u0, yy, v0), (u1, yy + 0.004, v1), mat, bevel=0.0)


def _al_sash_clean(mb, x0, x1, z0, z1, y, mat="aluminium", t=0.022, sw=0.035, mid=None):
    """Hoja de aluminio con vidrio entero de 6 mm, empaque de hule y travesaño opcional."""
    for (u0, v0, u1, v1) in ((x0, z0, x1, z0 + sw), (x0, z1 - sw, x1, z1), (x0, z0, x0 + sw, z1), (x1 - sw, z0, x1, z1)):
        mb.box((u0, y - t / 2, v0), (u1, y + t / 2, v1), mat, bevel=0.002)
    lites = [(z0 + sw, z1 - sw)]
    if mid:
        mb.box((x0 + sw, y - t / 2 + 0.002, mid - 0.015), (x1 - sw, y + t / 2 - 0.002, mid + 0.015), mat, bevel=0.002)
        lites = [(z0 + sw, mid - 0.015), (mid + 0.015, z1 - sw)]
    for (a, b) in lites:
        mb.box((x0 + sw - 0.008, y - 0.003, a - 0.008), (x1 - sw + 0.008, y + 0.003, b + 0.008), "glass", bevel=0.0)
        for (u0, v0, u1, v1) in ((x0 + sw, a, x1 - sw, a + 0.006), (x0 + sw, b - 0.006, x1 - sw, b), (x0 + sw, a, x0 + sw + 0.006, b),
                                 (x1 - sw - 0.006, a, x1 - sw, b)):
            for s_ in (-1, 1):
                mb.box((u0, y + s_ * 0.0035 - 0.0012, v0), (u1, y + s_ * 0.0035 + 0.0012, v1), "rubber", bevel=0.0)


def window_clean(w, h, depth=0.2, seed=0, open_frac=None, sill=True):
    """Ventana corrediza de aluminio en uso: marco con rieles, dos hojas con vidrio entero (una entreabierta), traslape con
    cerrojo de media luna, jaladera, y alféizar de concreto con gotero por fuera. Local: u 0..w, v 0..h, muro y 0..depth."""
    r = rng(seed)
    mb = MB()
    fy0, fy1 = depth * 0.35, depth * 0.35 + 0.065
    _al_frame(mb, w, h, fy0, fy1)
    pw = 0.045
    half = (w - 2 * pw) / 2 + 0.03
    of = float(r.uniform(0.0, 0.35)) if open_frac is None else open_frac
    mid = h * 0.5 if h > 1.0 else None
    ya, yb = fy0 + 0.018, fy0 + 0.045
    _al_sash_clean(mb, pw, pw + half, pw, h - pw, ya, mid=mid)
    xo = pw + half - 0.06 - of * (half - 0.1)
    xo = max(pw, min(xo, w - pw - half))
    _al_sash_clean(mb, xo + 0.0, xo + half, pw, h - pw, yb, mid=mid)
    zl = h * 0.5
    mb.box((pw + half - 0.03, ya + 0.011, zl - 0.04), (pw + half - 0.01, ya + 0.02, zl + 0.04), "aluminium", bevel=0.002)
    mb.box((xo + half - 0.03, yb - 0.02, zl - 0.06), (xo + half - 0.015, yb - 0.011, zl + 0.06), "aluminium", bevel=0.002)
    if sill:
        mb.box((-0.04, -0.06, -0.05), (w + 0.04, fy0, 0.0), "concrete", bevel=0.008)
        mb.box((-0.04, -0.06, -0.065), (w + 0.04, -0.045, -0.05), "concrete", bevel=0.002)
    mb.box((0.0, fy1, -0.02), (w, depth, 0.0), "paint_white", bevel=0.004)                 # repisa interior
    return mb


def door_glass_double(w, h, depth=0.2, seed=0, angles=(0.0, 0.0), transom=0.3):
    """Puerta doble de aluminio y vidrio (entrada): marco con travesaño y fijo superior, hojas con zoclo pateador alto,
    travesaño medio, vidrio entero, jaladeras verticales de tubo, cierrapuertas aéreos y topes de piso.
    Local: u 0..w, v 0..h (v = 0 piso terminado), muro y 0..depth; las hojas abren hacia +Y (adentro)."""
    mb = MB()
    fy0, fy1 = depth * 0.3, depth * 0.3 + 0.1
    pw = 0.05
    hd = h - transom
    for (u0, v0, u1, v1) in ((0.0, 0.0, pw, h), (w - pw, 0.0, w, h), (0.0, h - pw, w, h), (pw, hd - 0.03, w - pw, hd + 0.03)):
        mb.box((u0, fy0, v0), (u1, fy1, v1), "aluminium", bevel=0.003)
    mb.box((pw, (fy0 + fy1) / 2 - 0.003, hd + 0.03), (w - pw, (fy0 + fy1) / 2 + 0.003, h - pw), "glass", bevel=0.0)
    mb.box((pw, fy0 - 0.005, -0.01), (w - pw, fy1 + 0.005, 0.0), "aluminium", bevel=0.001)
    lw = (w - 2 * pw - 0.006) / 2
    for k, (hx, sgn) in enumerate(((pw, 1), (w - pw, -1))):
        leaf = MB()
        T, sw, kick = 0.045, 0.1, 0.22
        for (u0, v0, u1, v1) in ((0.0, 0.006, sw, hd - 0.035), (lw - sw, 0.006, lw, hd - 0.035), (0.0, hd - 0.035 - sw, lw, hd - 0.035),
                                 (0.0, 0.006, lw, kick), (0.0, 0.98, lw, 1.06)):
            leaf.box((u0, -T / 2, v0), (u1, T / 2, v1), "aluminium", bevel=0.003)
        for (a, b) in ((kick, 0.98), (1.06, hd - 0.035 - sw)):
            leaf.box((sw - 0.01, -0.003, a - 0.01), (lw - sw + 0.01, 0.003, b + 0.01), "glass", bevel=0.0)
        leaf.box((0.0, -T / 2 - 0.0015, 0.006), (lw, -T / 2, kick), "steel", bevel=0.0)
        hxl = lw - 0.07
        for s_ in (-1, 1):
            leaf.cyl((hxl, s_ * (T / 2 + 0.05), 0.8), (hxl, s_ * (T / 2 + 0.05), 1.4), 0.014, seg=12, mat="steel")
            for z in (0.85, 1.35):
                leaf.cyl((hxl, s_ * T / 2, z), (hxl, s_ * (T / 2 + 0.05), z), 0.008, seg=8, mat="steel")
        leaf.box((0.03, T / 2, hd - 0.1), (0.3, T / 2 + 0.04, hd - 0.05), "aluminium", bevel=0.004)
        leaf.box((0.25, T / 2 + 0.01, hd - 0.085), (0.5, T / 2 + 0.025, hd - 0.07), "aluminium", bevel=0.002)
        ang = angles[k]
        if sgn > 0:
            M = _T(hx + 0.003, (fy0 + fy1) / 2, 0.0) @ _Rz(ang)
        else:
            M = _T(hx - 0.003, (fy0 + fy1) / 2, 0.0) @ _Rz(-ang) @ Matrix.Scale(-1, 4, Vector((1, 0, 0)))
        mb.join(leaf, M)
        port.lathe(mb, [(0.0, 0.0), (0.025, 0.0), (0.02, 0.05), (0.0, 0.06)], seg=12, mat="rubber",
                   M=_T(hx + sgn * (lw - 0.1), fy1 + 0.6, 0.0))
    return mb


def door_panel(w, h=2.1, depth=0.12, seed=0, ang=45.0, mat="paint_mint", frame_mat="paint_green", kick=True):
    """Puerta interior de tablero (4 tableros con bisel), chambrana a ambos lados, marco, 3 bisagras, manija de palanca con
    roseta, placa pateadora de acero y tope de piso. Local: u 0..w, v 0..h, muro y 0..depth; la hoja abre hacia +Y."""
    mb = MB()
    jw = 0.035
    for (u0, v0, u1, v1) in ((-0.002, 0.0, jw, h + 0.002), (w - jw, 0.0, w + 0.002, h + 0.002), (-0.002, h - jw, w + 0.002, h + 0.002)):
        mb.box((u0, -0.002, v0), (u1, depth + 0.002, v1), frame_mat, bevel=0.003)
    for (y0, y1) in ((-0.018, 0.0), (depth, depth + 0.018)):        # chambranas
        for (u0, v0, u1, v1) in ((-0.07, 0.0, 0.0, h + 0.07), (w, 0.0, w + 0.07, h + 0.07), (-0.07, h, w + 0.07, h + 0.07)):
            mb.box((u0, y0, v0), (u1, y1, v1), frame_mat, bevel=0.004)
    lw, lh, T = w - 2 * jw - 0.006, h - jw - 0.008, 0.04
    leaf = MB()
    st, rl = 0.11, 0.12
    for (u0, v0, u1, v1) in ((0.0, 0.0, st, lh), (lw - st, 0.0, lw, lh), (0.0, lh - rl, lw, lh), (0.0, 0.0, lw, 0.2),
                             (0.0, lh * 0.45, lw, lh * 0.45 + rl), (lw / 2 - 0.05, 0.2, lw / 2 + 0.05, lh - rl)):
        leaf.box((u0, -T / 2, v0), (u1, T / 2, v1), mat, bevel=0.004)
    for (a, b) in ((0.2, lh * 0.45), (lh * 0.45 + rl, lh - rl)):
        for (c, d) in ((st, lw / 2 - 0.05), (lw / 2 + 0.05, lw - st)):
            leaf.box((c, -T / 2 + 0.008, a), (d, T / 2 - 0.008, b), mat, bevel=0.0)
            for s_ in (-1, 1):                                    # tablero realzado con bisel
                leaf.box((c + 0.03, s_ * (T / 2 - 0.008) - (0.006 if s_ > 0 else 0.0), a + 0.03),
                         (d - 0.03, s_ * (T / 2 - 0.008) + (0.0 if s_ > 0 else 0.006), b - 0.03), mat, bevel=0.012)
    if kick:
        for s_ in (-1, 1):
            leaf.box((0.02, s_ * T / 2 - (0.0015 if s_ < 0 else 0.0), 0.02), (lw - 0.02, s_ * T / 2 + (0.0015 if s_ > 0 else 0.0), 0.22),
                     "steel", bevel=0.0)
    hx = lw - 0.065
    for s_ in (-1, 1):
        port.lathe(leaf, [(0.0, 0.0), (0.028, 0.0), (0.028, 0.006), (0.02, 0.012), (0.0, 0.012)], seg=16, mat="steel",
                   M=_T(hx, s_ * T / 2, 1.0) @ Matrix.Rotation(-s_ * PI / 2, 4, "X"))
        leaf.tube([(hx, s_ * (T / 2 + 0.01), 1.0), (hx, s_ * (T / 2 + 0.055), 1.0), (hx - 0.12, s_ * (T / 2 + 0.06), 1.0)], 0.009,
                  seg=10, mat="steel")
    for z in (0.22, lh / 2, lh - 0.22):
        leaf.cyl((0.0, -T / 2 - 0.004, z - 0.05), (0.0, -T / 2 - 0.004, z + 0.05), 0.007, seg=8, mat="steel")
    M = _T(jw + 0.003, depth / 2, 0.004) @ _Rz(ang)
    mb.join(leaf, M)
    a = math.radians(ang)
    port.lathe(mb, [(0.0, 0.0), (0.018, 0.0), (0.014, 0.03), (0.0, 0.035)], seg=12, mat="rubber",
               M=_T(jw + (lw - 0.08) * math.cos(a), depth / 2 + (lw - 0.08) * math.sin(a) + 0.05, 0.0))
    del seed
    return mb


def door_steel(w, h=2.1, depth=0.2, seed=0, ang=0.0, panic=True, mat="paint_green"):
    """Puerta de servicio de acero: marco de lámina, hoja lisa con refuerzos, barra de pánico por dentro, manija por fuera,
    cierrapuertas, mirilla de vidrio armado y placa pateadora. Local: u 0..w, v 0..h, muro y 0..depth; abre hacia -Y (afuera)."""
    mb = MB()
    jw = 0.05
    for (u0, v0, u1, v1) in ((0.0, 0.0, jw, h), (w - jw, 0.0, w, h), (0.0, h - jw, w, h)):
        mb.box((u0, depth * 0.2, v0), (u1, depth * 0.8, v1), mat, bevel=0.003)
    lw, lh, T = w - 2 * jw - 0.006, h - jw - 0.006, 0.045
    leaf = MB()
    leaf.box((0.0, -T / 2, 0.0), (lw, T / 2, lh), mat, bevel=0.004)
    for v in (0.35, 1.05, 1.75):
        leaf.box((0.04, -T / 2 - 0.002, v - 0.02), (lw - 0.04, -T / 2, v + 0.02), mat, bevel=0.001)
    leaf.box((lw / 2 - 0.12, -T / 2 - 0.004, 1.45), (lw / 2 + 0.12, T / 2 + 0.004, 1.75), mat, bevel=0.003)
    leaf.box((lw / 2 - 0.1, -0.003, 1.47), (lw / 2 + 0.1, 0.003, 1.73), "glass", bevel=0.0)
    leaf.box((0.02, -T / 2 - 0.0015, 0.02), (lw - 0.02, -T / 2, 0.25), "steel", bevel=0.0)
    if panic:
        leaf.box((0.08, T / 2, 0.92), (lw - 0.06, T / 2 + 0.07, 0.98), "steel", bevel=0.01)
        leaf.box((lw - 0.16, T / 2, 0.88), (lw - 0.04, T / 2 + 0.08, 1.02), "sign_red", bevel=0.01)
    leaf.tube([(lw - 0.06, -T / 2, 1.0), (lw - 0.06, -T / 2 - 0.05, 1.0), (lw - 0.18, -T / 2 - 0.055, 1.0)], 0.009, seg=10, mat="steel")
    leaf.box((0.03, -T / 2 - 0.04, lh - 0.12), (0.32, -T / 2, lh - 0.06), "steel", bevel=0.005)
    M = _T(jw + 0.003, depth * 0.5, 0.004) @ _Rz(-ang)
    mb.join(leaf, M)
    del seed
    return mb


# ------------------------------------------------------------------------------------------------ pasamanos y mesa de cocina
def handrail(L, seed=0, depth=0.075):
    """Pasamanos de madera barnizada para muro (origen: muro, x de 0 a L, a la altura del eje del riel; sale hacia -Y):
    riel de sección ovalada 60 x 50 mm con ranura de agarre a los costados, remates curvos que regresan al muro con roseta,
    ménsulas de barra doblada cada <= 1,2 m con placa de muro, 2 pijas y silleta atornillada al riel."""
    r = rng(seed)
    mb = MB()
    prof = []
    n = 22
    for k in range(n):
        a = 2 * PI * k / n
        c, s = math.cos(a), math.sin(a)
        x = 0.030 * math.copysign(abs(c) ** (2 / 2.6), c)
        y = 0.025 * math.copysign(abs(s) ** (2 / 2.6), s)
        if abs(s) < 0.35:                                     # ranura de agarre a media altura
            x *= 1 - 0.06 * (1 - abs(s) / 0.35)
        if s < -0.8:                                          # asiento plano para las silletas
            y = max(y, -0.022)
        prof.append((x, y))
    prof.reverse()
    path = fillet([(0.0, -0.014, 0.0), (0.0, -depth, 0.0), (L, -depth, 0.0), (L, -0.014, 0.0)], 0.045, nseg=10)
    mb.sweep(prof, path, mat="wood_varnish", normal=(0, 0, 1))
    for x in (0.0, L):                                        # rosetas en el muro
        mb.cyl((x, -0.004, 0.0), (x, -0.014, 0.0), 0.034, seg=18, mat="steel")
        mb.cyl((x, 0.0, 0.0), (x, -0.004, 0.0), 0.037, seg=18, mat="steel")
    nb = max(2, int(math.ceil((L - 0.3) / 1.2)) + 1)
    for i in range(nb):
        x = 0.15 + (L - 0.3) * i / (nb - 1) + float(r.uniform(-0.01, 0.01))
        rbox(mb, (x - 0.03, -0.006, -0.10), (x + 0.03, 0.0, -0.035), "steel", r=0.008)       # placa de muro
        for z in (-0.088, -0.047):
            mb.cyl((x, -0.006, z), (x, -0.009, z), 0.0055, seg=8, mat="steel")
            mb.box((x - 0.004, -0.0095, z - 0.0007), (x + 0.004, -0.0088, z + 0.0007), "cable", bevel=0.0)
        arm = fillet([(x, -0.006, -0.066), (x, -depth, -0.066), (x, -depth, -0.030)], 0.022, nseg=5)
        mb.tube(arm, 0.0065, seg=8, mat="steel")
        mb.cyl((x, -0.006, -0.066), (x, -0.012, -0.066), 0.011, seg=12, mat="steel")       # cubo de la ménsula
        rbox(mb, (x - 0.028, -depth - 0.012, -0.0255), (x + 0.028, -depth + 0.012, -0.0215), "steel", r=0.003)  # silleta
        for dx in (-0.018, 0.018):
            mb.cyl((x + dx, -depth, -0.0255), (x + dx, -depth, -0.0275), 0.003, seg=6, mat="steel")
    return mb


def kitchen_table(w=1.6, d=0.9, h=0.75, seed=0):
    """Mesa de comedor del personal: cubierta de aglomerado con laminado y canto de PVC de 2 mm, faldón de PTR 40 x 20
    soldado a patas de tubo de 1 1/4" con regatones de hule y niveladores, cartelas en las esquinas con tornillos; encima un
    servilletero de lámina con servilletas, salero y una taza (origen: piso, centro)."""
    r = rng(seed)
    mb = MB()
    t = 0.028
    rbox(mb, (-w / 2, -d / 2, h - t), (w / 2, d / 2, h - 0.002), "wood_varnish", r=0.004)
    # canto de PVC: banda perimetral 2 mm más alta que el laminado, esquinas redondeadas
    rr = 0.02
    out = []
    for (cx, cy, a0) in ((w / 2 - rr, -d / 2 + rr, -PI / 2), (w / 2 - rr, d / 2 - rr, 0.0), (-w / 2 + rr, d / 2 - rr, PI / 2),
                         (-w / 2 + rr, -d / 2 + rr, PI)):
        for k in range(7):
            a = a0 + PI / 2 * k / 6
            out.append((cx + (rr + 0.0025) * math.cos(a), cy + (rr + 0.0025) * math.sin(a), h - t / 2 - 0.001))
    out.append(out[0])
    mb.sweep([(-0.0012, -t / 2 - 0.0005), (0.0012, -t / 2 - 0.0005), (0.0012, t / 2 + 0.0005), (-0.0012, t / 2 + 0.0005)], out,
             mat="plastic", closed_profile=True, normal=(0, 0, 1))
    zb = h - t - 0.001
    li, wi = 0.07, 0.07
    legs = [(sx * (w / 2 - li), sy * (d / 2 - wi)) for sx in (-1, 1) for sy in (-1, 1)]
    for (x, y) in legs:
        mb.cyl((x, y, 0.025), (x, y, zb), 0.0159, seg=20, mat="steel")
        mb.cyl((x, y, 0.012), (x, y, 0.03), 0.0165, seg=20, mat="rubber")                  # regatón
        mb.cyl((x, y, 0.0), (x, y, 0.012), 0.012, seg=16, mat="rubber")                    # nivelador
        mb.cyl((x, y, 0.012), (x, y, 0.016), 0.0045, seg=8, mat="steel")
    for sy in (-1, 1):                                                                     # faldón largo
        rtube(mb, (-w / 2 + li, sy * (d / 2 - wi), zb - 0.02), (w / 2 - li, sy * (d / 2 - wi), zb - 0.02), 0.02, 0.04, "steel",
              r=0.002)
    for sx in (-1, 1):                                                                     # faldón corto
        rtube(mb, (sx * (w / 2 - li), -d / 2 + wi, zb - 0.02), (sx * (w / 2 - li), d / 2 - wi, zb - 0.02), 0.02, 0.04, "steel",
              r=0.002)
    for (x, y) in legs:                                                                    # cartelas y tornillos
        sx, sy = math.copysign(1, x), math.copysign(1, y)
        for (ax, ay) in ((-sx, 0), (0, -sy)):
            p = (x + ax * 0.08, y + ay * 0.08)
            mb.tube([(x + ax * 0.02, y + ay * 0.02, zb - 0.04), (p[0], p[1], zb - 0.004)], 0.004, seg=6, mat="steel")
        for (ax, ay) in ((-sx, 0), (0, -sy)):
            q = (x + ax * 0.12, y + ay * 0.12)
            mb.cyl((q[0], q[1], zb + 0.0005), (q[0], q[1], zb - 0.004), 0.005, seg=10, mat="steel")
    # servilletero de lámina doblada con servilletas
    sx0, sy0 = float(r.uniform(-0.15, 0.05)), float(r.uniform(-0.05, 0.05))
    base = h
    for s in (-1, 1):
        rbox(mb, (sx0 - 0.065, sy0 + s * 0.035 - 0.0012, base), (sx0 + 0.065, sy0 + s * 0.035 + 0.0012, base + 0.09), "aluminium",
             r=0.0011)
    rbox(mb, (sx0 - 0.065, sy0 - 0.037, base), (sx0 + 0.065, sy0 + 0.037, base + 0.006), "aluminium", r=0.002)
    for k in range(9):
        y = sy0 - 0.028 + k * 0.007
        rbox(mb, (sx0 - 0.055, y - 0.0028, base + 0.006), (sx0 + 0.055, y + 0.0028, base + 0.105 + 0.004 * math.sin(k * 1.7)),
             "paper", r=0.0012)
    # salero
    mb.cyl((sx0 + 0.14, sy0, base), (sx0 + 0.14, sy0, base + 0.07), 0.018, seg=20, mat="glass")
    mb.cyl((sx0 + 0.14, sy0, base + 0.07), (sx0 + 0.14, sy0, base + 0.085), 0.0185, seg=20, mat="aluminium")
    # taza con asa
    cx, cy = float(r.uniform(0.3, 0.55)), float(r.uniform(-0.25, 0.2))
    mb.cyl((cx, cy, base), (cx, cy, base + 0.004), 0.03, seg=24, mat="sign_white")
    mb.cyl((cx, cy, base + 0.004), (cx, cy, base + 0.095), 0.041, seg=28, mat="sign_white")
    mb.cyl((cx, cy, base + 0.08), (cx, cy, base + 0.0905), 0.037, seg=28, mat="wood_dark")
    ang = float(r.uniform(0, 2 * PI))
    hx, hy = math.cos(ang), math.sin(ang)
    hp = [(cx + hx * (0.041 + 0.02 * math.sin(PI * k / 10)), cy + hy * (0.041 + 0.02 * math.sin(PI * k / 10)),
           base + 0.075 - 0.05 * k / 10) for k in range(11)]
    mb.tube(hp, 0.006, seg=10, mat="sign_white")
    return mb


# ---------------------------------------------------------------------------------------------- piezas AAA (regla R-AAA)
# Reconstruidas con su construcción real (2026-11-12); la implementación vive en kit/clinic_servicios.py (electrodomésticos y
# sanitarios), kit/clinic_oficina.py (mobiliario de oficina y servicio) y kit/clinic_equipo.py (equipo médico, luminarias y
# accesorios). Se importan al llamarlas para evitar la importación circular (esos módulos usan los ayudantes de aquí).
def _impl(mod, name):
    def f(*a, **k):
        import importlib
        return getattr(importlib.import_module("kit." + mod), name)(*a, **k)
    f.__name__ = name
    f.__doc__ = f"Ver kit/{mod}.py::{name}."
    return f


washer = _impl("clinic_servicios", "washer")
fridge = _impl("clinic_servicios", "fridge")
stove = _impl("clinic_servicios", "stove")
water_dispenser = _impl("clinic_servicios", "water_dispenser")
sink = _impl("clinic_servicios", "sink")
toilet = _impl("clinic_servicios", "toilet")
mop_bucket = _impl("clinic_servicios", "mop_bucket")
trash_bin = _impl("clinic_servicios", "trash_bin")
sanitizer = _impl("clinic_servicios", "sanitizer")
desk = _impl("clinic_oficina", "desk")
filing_cabinet = _impl("clinic_oficina", "filing_cabinet")
counter = _impl("clinic_oficina", "counter")
folding_chair = _impl("clinic_oficina", "folding_chair")
office_chair = _impl("clinic_oficina", "office_chair")
bedside_cabinet = _impl("clinic_oficina", "bedside_cabinet")
notice_board = _impl("clinic_oficina", "notice_board")
clock = _impl("clinic_oficina", "clock")
potted_plant = _impl("clinic_oficina", "potted_plant")
fluorescent = _impl("clinic_equipo", "fluorescent")
ceiling_fan = _impl("clinic_equipo", "ceiling_fan")
split_indoor = _impl("clinic_equipo", "split_indoor")
extinguisher = _impl("clinic_equipo", "extinguisher")
cylinder_rack = _impl("clinic_equipo", "cylinder_rack")
xray_unit = _impl("clinic_equipo", "xray_unit")
wall_bucky = _impl("clinic_equipo", "wall_bucky")
lead_screen = _impl("clinic_equipo", "lead_screen")
wall_lamp = _impl("clinic_equipo", "wall_lamp")

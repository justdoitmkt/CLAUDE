"""kit/clinic.py — mobiliario y equipo de un hospital rural EN USO (limpio, gastado por el uso, no abandonado).

Convención de todas las piezas: devuelven un MB en coordenadas locales, origen en el piso al centro de la pieza, frente hacia -Y
(el lado desde el que se usa), Z arriba, metros. Las piezas de muro (letreros, lámparas, gabinetes) tienen el origen en la cara
del muro y crecen hacia -Y (fuera del muro).
Materiales del kit: steel, plastic, plastic_blue, linen, vinyl, rubber, sign_*, paint_*, wood, wood_dark, glass, paper, aluminium.
"""
import math

import bpy
from mathutils import Matrix, Vector

from kit import port
from kit.common import MB, rng

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
def shell_strip(mb, prof, width, t, mat, m=None, taper=None):
    """Concha delgada (asiento moldeado, respaldo): perfil [(y, z)] barrido a lo ancho en X (±width/2), espesor t hacia el lado
    izquierdo del recorrido. taper(i) -> factor de ancho por punto (esquinas redondeadas)."""
    pts = [Vector((0.0, y, z)) for y, z in prof]
    n = len(pts)
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        d = (b - a).normalized()
        nrm = Vector((0.0, -d.z, d.y))
        k = taper(i) if taper else 1.0
        hw = width / 2 * k
        q = p + nrm * t
        ring = [Vector((-hw, p.y, p.z)), Vector((hw, p.y, p.z)), Vector((hw, q.y, q.z)), Vector((-hw, q.y, q.z))]
        rings.append([mb.bm.verts.new((m @ v) if m is not None else v) for v in ring])
    for i in range(n - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(4):
            k2 = (j + 1) % 4
            mb.face([A[j], A[k2], B[k2], B[j]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[-1], mat)


def rbox(mb, mn, mx, mat, r=0.01, m=None):
    """Caja con aristas verticales achaflanadas (muebles de lámina y laminado)."""
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    c = min(r, (x1 - x0) / 3, (y1 - y0) / 3)
    outline = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]
    M = (m if m is not None else Matrix()) @ _T(0, 0, z0)
    mb.plate(outline, z1 - z0, mat, m=M)


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
    n = len(prof)
    shell_strip(mb, prof, w, 0.007, "plastic_blue", m=M,
                taper=lambda i: 0.86 if i in (0, n - 1) else (0.95 if i in (1, n - 2) else 1.0))


def chair_row(n=4, seed=0, empty=()):
    """Bancada de n asientos sobre viga de acero (sala de espera): viga 60x60, 2 patas en T con regatones, ménsulas."""
    r = rng(seed)
    mb = MB()
    pitch = 0.53
    L = n * pitch
    x0 = -L / 2
    zb = 0.33
    mb.box((x0 + 0.05, -0.03, zb - 0.03), (x0 + L - 0.05, 0.03, zb + 0.03), "steel")
    for xl in (x0 + 0.35, x0 + L - 0.35):
        mb.box((xl - 0.025, -0.025, 0.03), (xl + 0.025, 0.025, zb - 0.03), "steel")
        mb.box((xl - 0.02, -0.26, 0.0), (xl + 0.02, 0.26, 0.04), "steel")
        for yy in (-0.24, 0.24):
            mb.cyl((xl, yy, 0.0), (xl, yy, 0.012), 0.022, seg=8, mat="rubber")
        port.gusset(mb, _T(xl, 0, zb - 0.03) @ _Rz(90) @ _Rx(180), 0.12, 0.1, t=0.006, mat="steel")
    for i in range(n):
        if i in empty:
            continue
        xc = x0 + pitch * (i + 0.5)
        mb.box((xc - 0.02, -0.12, zb + 0.03), (xc + 0.02, 0.12, zb + 0.045), "steel")
        mb.box((xc - 0.02, 0.15, zb + 0.03), (xc + 0.02, 0.19, zb + 0.30), "steel")
        seat_shell(mb, _T(xc, 0.0, zb + 0.07) @ _Rz(float(r.uniform(-0.6, 0.6))))
        if i < n - 1 and i % 2 == 1:     # brazo entre asientos
            xa = xc + pitch / 2
            mb.box((xa - 0.012, -0.18, zb + 0.03), (xa + 0.012, -0.15, zb + 0.24), "steel")
            mb.box((xa - 0.02, -0.24, zb + 0.24), (xa + 0.02, 0.08, zb + 0.27), "plastic_blue")
    return mb


def office_chair(seed=0):
    """Silla de oficina: estrella de 5 brazos con rodajas, pistón, asiento y respaldo tapizados (vinilo)."""
    r = rng(seed)
    mb = MB()
    for k in range(5):
        a = 2 * PI * k / 5 + float(r.uniform(0, 0.3))
        p = (0.30 * math.cos(a), 0.30 * math.sin(a))
        mb.tube([(0, 0, 0.09), (p[0] * 0.9, p[1] * 0.9, 0.075)], 0.016, seg=6, mat="plastic")
        caster(mb, (p[0], p[1], 0.0), r=0.026, swivel=math.degrees(a))
    mb.cyl((0, 0, 0.07), (0, 0, 0.12), 0.04, seg=12, mat="plastic")
    mb.cyl((0, 0, 0.12), (0, 0, 0.40), 0.02, seg=10, mat="steel")
    mb.box((-0.07, -0.08, 0.40), (0.07, 0.08, 0.43), "plastic")
    rbox(mb, (-0.23, -0.22, 0.43), (0.23, 0.22, 0.49), "vinyl", r=0.05)
    mb.box((-0.03, 0.19, 0.43), (0.03, 0.23, 0.70), "plastic")
    rbox(mb, (-0.21, 0.21, 0.62), (0.21, 0.27, 0.95), "vinyl", r=0.05, m=_T(0, 0.24, 0.62) @ _Rx(-8) @ _T(0, -0.24, -0.62))
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
def hospital_bed(seed=0, rails_up=True):
    """Cama de hospital de tubo: bastidor con 4 rodajas, cabecera y piecera de tubo con barrotes, colchón de vinilo con sábana,
    almohada, cobija doblada al pie y barandales abatibles. 2,05 × 0,95; colchón a 0,58."""
    r = rng(seed)
    mb = MB()
    L, W = 2.0, 0.92
    zf = 0.44
    for (x, y) in ((-W / 2 + 0.04, -L / 2 + 0.06), (W / 2 - 0.04, -L / 2 + 0.06), (-W / 2 + 0.04, L / 2 - 0.06), (W / 2 - 0.04, L / 2 - 0.06)):
        caster(mb, (x, y, 0.0), r=0.05, swivel=float(r.uniform(0, 360)))
        mb.cyl((x, y, 0.14), (x, y, zf), 0.018, seg=8, mat="steel")
    for s in (-1, 1):
        mb.box((s * W / 2 - 0.03, -L / 2 + 0.03, zf - 0.04), (s * W / 2, L / 2 - 0.03, zf + 0.02), "steel")
    for y in (-L / 2 + 0.06, -0.3, 0.3, L / 2 - 0.06):
        mb.box((-W / 2, y - 0.015, zf - 0.03), (W / 2, y + 0.015, zf + 0.01), "steel")
    mb.box((-W / 2 + 0.03, -L / 2 + 0.05, zf + 0.01), (W / 2 - 0.03, L / 2 - 0.05, zf + 0.025), "steel")
    # cabecera (y+) y piecera (y-)
    for (yb, hgt) in ((L / 2 - 0.02, 1.02), (-L / 2 + 0.02, 0.88)):
        pts = [(-W / 2 + 0.02, yb, zf - 0.05), (-W / 2 + 0.02, yb, hgt - 0.06), (-W / 2 + 0.08, yb, hgt), (W / 2 - 0.08, yb, hgt),
               (W / 2 - 0.02, yb, hgt - 0.06), (W / 2 - 0.02, yb, zf - 0.05)]
        mb.tube(pts, 0.016, seg=8, mat="steel")
        mb.tube([(-W / 2 + 0.02, yb, zf + 0.14), (W / 2 - 0.02, yb, zf + 0.14)], 0.012, seg=6, mat="steel")
        x = -W / 2 + 0.12
        while x < W / 2 - 0.1:
            mb.cyl((x, yb, zf + 0.14), (x, yb, hgt - 0.01), 0.008, seg=6, mat="steel")
            x += 0.1
    # colchón y ropa
    zt = zf + 0.155
    rbox(mb, (-W / 2 + 0.04, -L / 2 + 0.07, zf + 0.025), (W / 2 - 0.04, L / 2 - 0.07, zt), "vinyl", r=0.04)
    rbox(mb, (-W / 2 + 0.025, -L / 2 + 0.06, zt - 0.02), (W / 2 - 0.025, L / 2 - 0.08, zt + 0.012), "linen", r=0.05)
    port.loft(mb, [(-0.28, 0.0, 0.10, 0.0), (-0.2, 0.55, 0.13, 0.0), (0.0, 0.6, 0.15, 0.0), (0.2, 0.55, 0.13, 0.0), (0.28, 0.0, 0.1, 0.0)],
              seg=10, mat="linen", M=_T(float(r.uniform(-0.03, 0.03)), L / 2 - 0.3, zt + 0.07), ex=2.8)
    rbox(mb, (-W / 2 + 0.06, -L / 2 + 0.12, zt + 0.012), (W / 2 - 0.06, -L / 2 + 0.5, zt + 0.07), "fabric", r=0.04)
    # barandales
    if rails_up:
        for s in (-1, 1):
            xr = s * (W / 2 + 0.02)
            mb.tube([(xr, -0.35, zt + 0.02), (xr, -0.35, zt + 0.30), (xr, 0.55, zt + 0.30), (xr, 0.55, zt + 0.02)], 0.011, seg=6,
                    mat="steel")
            mb.tube([(xr, -0.35, zt + 0.16), (xr, 0.55, zt + 0.16)], 0.008, seg=6, mat="steel")
    # manivela al pie
    mb.cyl((0.0, -L / 2 - 0.02, zf - 0.02), (0.0, -L / 2 - 0.09, zf - 0.02), 0.01, seg=6, mat="steel")
    mb.cyl((0.0, -L / 2 - 0.09, zf - 0.02), (0.09, -L / 2 - 0.09, zf - 0.02), 0.008, seg=6, mat="steel")
    mb.cyl((0.09, -L / 2 - 0.09, zf - 0.02), (0.09, -L / 2 - 0.13, zf - 0.02), 0.012, seg=8, mat="plastic")
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
    """Riel de cortina al plafón (perfil de aluminio con colgantes) y cortina plisada que cuelga hasta `drop` sobre el piso.
    pts: polilínea en planta; open_runs: índices de tramos con la cortina recogida (solo un paño plegado junto al extremo)."""
    for (a, b) in zip(pts[:-1], pts[1:]):
        mb.box((min(a[0], b[0]) - 0.012, min(a[1], b[1]) - 0.012, z - 0.03), (max(a[0], b[0]) + 0.012, max(a[1], b[1]) + 0.012, z - 0.012),
               "aluminium")
    for p in pts[::max(1, len(pts) - 1)]:
        mb.cyl((p[0], p[1], z - 0.012), (p[0], p[1], z), 0.006, seg=5, mat="aluminium")
    for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
        A, B = Vector((a[0], a[1], 0)), Vector((b[0], b[1], 0))
        L = (B - A).length
        d = (B - A).normalized()
        nrm = Vector((-d.y, d.x, 0))
        if i in open_runs:
            L2, A2 = 0.35, A
        else:
            L2, A2 = L * float(r.uniform(0.85, 1.0)), A
        n = max(4, int(L2 / 0.06))
        top, bot = z - 0.04, drop
        rows = []
        for k in range(n + 1):
            t = k / n
            amp = 0.035 if i not in open_runs else 0.06
            off = nrm * (amp * math.sin(t * n * PI / 2 * 2))
            p = A2 + d * (L2 * t) + off
            rows.append([(p.x, p.y, top), (p.x, p.y, bot)])
        th = 0.004
        vf, vb = [], []
        for (pt, pb) in rows:
            vf.append((mb.bm.verts.new(pt), mb.bm.verts.new(pb)))
            vb.append((mb.bm.verts.new((pt[0] + nrm.x * th, pt[1] + nrm.y * th, pt[2])),
                       mb.bm.verts.new((pb[0] + nrm.x * th, pb[1] + nrm.y * th, pb[2]))))
        for k in range(n):
            mb.face([vf[k][1], vf[k + 1][1], vf[k + 1][0], vf[k][0]], mat)
            mb.face([vb[k][0], vb[k + 1][0], vb[k + 1][1], vb[k][1]], mat)
            mb.face([vf[k][0], vf[k + 1][0], vb[k + 1][0], vb[k][0]], mat)
            mb.face([vb[k][1], vb[k + 1][1], vf[k + 1][1], vf[k][1]], mat)
        mb.face([vf[0][0], vb[0][0], vb[0][1], vf[0][1]], mat)
        mb.face([vf[n][1], vb[n][1], vb[n][0], vf[n][0]], mat)
        for k in range(0, n + 1, 2):
            p = rows[k][0]
            mb.cyl((p[0], p[1], top), (p[0], p[1], z - 0.012), 0.002, seg=4, mat="aluminium")


def exam_table(seed=0):
    """Mesa de exploración: gabinete de lámina con cajones, colchoneta de vinilo con cabecera levantada, rollo de papel y banco
    de dos peldaños."""
    mb = MB()
    rbox(mb, (-0.30, -0.9, 0.0), (0.30, 0.9, 0.62), "plastic", r=0.02)
    for (y0, y1) in ((-0.85, -0.45), (-0.4, 0.0), (0.05, 0.45)):
        mb.box((-0.304, y0, 0.08), (-0.30, y1, 0.55), "plastic")
        mb.box((-0.32, (y0 + y1) / 2 - 0.06, 0.48), (-0.304, (y0 + y1) / 2 + 0.06, 0.5), "steel")
    rbox(mb, (-0.31, -0.92, 0.62), (0.31, 0.45, 0.72), "vinyl", r=0.04)
    rbox(mb, (-0.31, 0.0, 0.0), (0.31, 0.5, 0.1), "vinyl", r=0.04, m=_T(0, 0.45, 0.66) @ _Rx(28))
    mb.box((-0.27, -0.88, 0.72), (0.27, 0.42, 0.722), "paper")
    mb.cyl((-0.26, 0.95, 0.75), (0.26, 0.95, 0.75), 0.05, seg=12, mat="paper")
    for x in (-0.28, 0.28):
        mb.box((x - 0.01, 0.88, 0.62), (x + 0.01, 0.96, 0.78), "steel")
    rbox(mb, (-0.25, -1.35, 0.0), (0.25, -1.0, 0.2), "steel", r=0.01)
    rbox(mb, (-0.25, -1.2, 0.2), (0.25, -1.0, 0.4), "steel", r=0.01)
    mb.box((-0.24, -1.34, 0.2), (0.24, -1.2, 0.205), "rubber")
    mb.box((-0.24, -1.19, 0.4), (0.24, -1.01, 0.405), "rubber")
    return mb


def wheelchair(seed=0):
    """Silla de ruedas: bastidor de tubo, asiento y respaldo de vinilo (lona), ruedas traseras de 24" con aro y rayos, ruedas
    delanteras giratorias, descansapiés y descansabrazos."""
    r = rng(seed)
    mb = MB()
    W = 0.46
    for s in (-1, 1):
        x = s * W / 2
        mb.tube([(x, -0.32, 0.12), (x, -0.28, 0.5), (x, 0.2, 0.5), (x, 0.24, 0.95), (x, 0.32, 0.98)], 0.011, seg=6, mat="steel")
        mb.tube([(x, -0.3, 0.16), (x, 0.18, 0.16), (x, 0.2, 0.5)], 0.011, seg=6, mat="steel")
        mb.tube([(x, -0.25, 0.68), (x, 0.12, 0.68)], 0.011, seg=6, mat="steel")
        mb.box((x - 0.025, -0.2, 0.68), (x + 0.025, 0.1, 0.71), "vinyl")
        mb.cyl((x, 0.30, 0.98), (x, 0.36, 0.985), 0.016, seg=8, mat="rubber")
        # rueda trasera
        xw = s * (W / 2 + 0.05)
        Mw = _T(xw, 0.1, 0.3) @ _Ry(90)
        port.lathe(mb, [(0.27, -0.012), (0.3, -0.012), (0.3, 0.012), (0.27, 0.012)], seg=36, mat="rubber", M=Mw, caps=False)
        port.lathe(mb, [(0.255, -0.008), (0.27, -0.008), (0.27, 0.008), (0.255, 0.008)], seg=36, mat="steel", M=Mw, caps=False)
        for k in range(12):
            a = 2 * PI * k / 12
            mb.cyl(Mw @ Vector((0.03 * math.cos(a), 0.03 * math.sin(a), 0)), Mw @ Vector((0.256 * math.cos(a + 0.2), 0.256 * math.sin(a + 0.2), 0)),
                   0.0015, seg=3, mat="steel")
        mb.cyl(Mw @ Vector((0, 0, -0.03)), Mw @ Vector((0, 0, 0.03)), 0.03, seg=10, mat="steel")
        Mp = _T(xw + s * 0.03, 0.1, 0.3) @ _Ry(90)
        port.lathe(mb, [(0.255, -0.006), (0.265, -0.006), (0.265, 0.006), (0.255, 0.006)], seg=28, mat="steel", M=Mp, caps=False)
        caster(mb, (x, -0.3, 0.0), r=0.065, swivel=float(r.uniform(-20, 20)))
        mb.tube([(x, -0.28, 0.45), (x, -0.42, 0.14)], 0.01, seg=6, mat="steel")
        xa, xb = sorted((x, x - s * 0.17))
        mb.box((xa, -0.5, 0.12), (xb, -0.36, 0.13), "plastic")
    # lona de asiento y respaldo (combas)
    shell_strip(mb, [(-0.27, 0.0), (-0.1, -0.025), (0.08, -0.025), (0.19, 0.0)], W - 0.02, 0.005, "vinyl", m=_T(0, 0, 0.5))
    shell_strip(mb, [(0.0, 0.0), (0.03, 0.2), (0.035, 0.42)], W - 0.02, 0.005, "vinyl", m=_T(0, 0.21, 0.52))
    return mb


def stretcher(seed=0):
    """Camilla de traslado: bastidor de tubo, base con 4 rodajas, colchoneta de vinilo, barandales y manerales."""
    r = rng(seed)
    mb = MB()
    L, W = 1.95, 0.62
    for (x, y) in ((-W / 2 + 0.05, -L / 2 + 0.1), (W / 2 - 0.05, -L / 2 + 0.1), (-W / 2 + 0.05, L / 2 - 0.1), (W / 2 - 0.05, L / 2 - 0.1)):
        caster(mb, (x, y, 0.0), r=0.06, swivel=float(r.uniform(0, 360)))
    mb.box((-W / 2 + 0.03, -L / 2 + 0.08, 0.17), (W / 2 - 0.03, L / 2 - 0.08, 0.2), "steel")
    for y in (-0.5, 0.5):
        mb.box((-0.04, y - 0.04, 0.2), (0.04, y + 0.04, 0.6), "steel")
    mb.box((-W / 2, -L / 2, 0.6), (W / 2, L / 2, 0.63), "steel")
    rbox(mb, (-W / 2 + 0.02, -L / 2 + 0.02, 0.63), (W / 2 - 0.02, L / 2 - 0.02, 0.71), "vinyl", r=0.05)
    rbox(mb, (-W / 2 + 0.01, -L / 2 + 0.04, 0.70), (W / 2 - 0.01, L / 2 - 0.3, 0.712), "linen", r=0.05)
    for s in (-1, 1):
        xr = s * (W / 2 + 0.015)
        mb.tube([(xr, -0.6, 0.63), (xr, -0.6, 0.9), (xr, 0.6, 0.9), (xr, 0.6, 0.63)], 0.01, seg=6, mat="steel")
    for yy in (-L / 2 - 0.08, L / 2 + 0.08):
        mb.tube([(-W / 2 + 0.06, yy * 0.95, 0.6), (-W / 2 + 0.06, yy, 0.8), (W / 2 - 0.06, yy, 0.8), (W / 2 - 0.06, yy * 0.95, 0.6)],
                0.012, seg=6, mat="steel")
    return mb


# ----------------------------------------------------------------------------------------------------------- muebles
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
        pts = [(c.x + rad * math.cos(a), c.y, c.z + rad * math.sin(a)) for a in [k * 2 * PI / 12 for k in range(13)]]
        mb.tube(pts, 0.005, seg=5, mat=mat)
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

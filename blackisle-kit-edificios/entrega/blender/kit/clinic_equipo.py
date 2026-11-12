"""kit/clinic_equipo.py — reconstrucción AAA (regla R-AAA) de equipo del hospital HOS_1_pueblo: luminaria fluorescente,
ventilador de techo, minisplit, extintor, carro de cilindros (oxígeno / gas LP), rayos X con columna, bucky de pared, mampara
plomada y arbotante de muro.

Mismos nombres, firmas, origen, orientación y tamaño que las versiones de kit/clinic.py (que no se tocan):
- piezas de plafón (fluorescent, ceiling_fan): origen en el plafón, cuelgan hacia -Z;
- piezas de muro (split_indoor, extinguisher, wall_bucky, wall_lamp): origen en la cara del muro, crecen hacia -Y;
- piezas de piso (cylinder_rack, xray_unit, lead_screen): origen en el piso al centro, frente hacia -Y.
Equipo de un hospital rural EN OPERACIÓN: limpio, mantenido, modelos sencillos y algo viejos. El detalle sale de la geometría
(lámina doblada, uniones, tornillos, holguras, cordones de soldadura, cables con caída), no de texturas.
"""
import math

import bpy  # noqa: F401  (bpy antes que mathutils)
from mathutils import Matrix, Vector

from kit import port
from kit.clinic import MB, _Rx, _Ry, _Rz, _T, caster_pro, fillet, rbox, rng, rr_profile, rtube  # noqa: F401

PI = math.pi


# ======================================================================================================== utilidades
def rrect(w, h, r, n=4, cx=0.0, cy=0.0, z=None):
    """Contorno de rectángulo w × h con esquinas de radio r, antihorario, centrado en (cx, cy); con z da puntos 3D."""
    pts = []
    r = min(r, w / 2 - 1e-5, h / 2 - 1e-5)
    for (x, y, a0) in ((w / 2 - r, -h / 2 + r, -PI / 2), (w / 2 - r, h / 2 - r, 0.0), (-w / 2 + r, h / 2 - r, PI / 2),
                       (-w / 2 + r, -h / 2 + r, PI)):
        for k in range(n + 1):
            a = a0 + PI / 2 * k / n
            pts.append((cx + x + r * math.cos(a), cy + y + r * math.sin(a)) if z is None else
                       (cx + x + r * math.cos(a), cy + y + r * math.sin(a), z))
    return pts


def revolve(mb, prof, mats, seg=16, M=None, caps=True, phase=0.0, rmod=None, a0=0.0, a1=None, closed=False):
    """Sólido de revolución alrededor de Z local con material POR TRAMO del perfil (sin calcomanías coplanares).
    prof: [(r, z)]; mats: str o lista de len(prof) - 1. Un punto con r = 0 es un polo (un solo vértice, abanico de triángulos:
    nada de caras degeneradas). rmod(a) -> factor de radio (moleteado, estrías). a0/a1: barrido parcial abierto (radianes).
    closed=True: el perfil es un lazo cerrado (anillos, cordones de soldadura, aros): une el último tramo con el primero."""
    if isinstance(mats, str):
        mats = [mats] * (len(prof) if closed else len(prof) - 1)
    full = a1 is None
    nring = seg if full else seg + 1
    rings = []
    for (rr, z) in prof:
        if rr < 1e-6:
            p = Vector((0.0, 0.0, z))
            rings.append([mb.bm.verts.new(M @ p if M is not None else p)])
            continue
        ring = []
        for k in range(nring):
            a = (2 * PI * k / seg + phase) if full else (a0 + (a1 - a0) * k / seg)
            f = rmod(a) if rmod is not None else 1.0
            p = Vector((rr * f * math.cos(a), rr * f * math.sin(a), z))
            ring.append(mb.bm.verts.new(M @ p if M is not None else p))
        rings.append(ring)
    nr = len(rings) if closed else len(rings) - 1
    for i in range(nr):
        A, B = rings[i], rings[(i + 1) % len(rings)]
        if len(A) == 1 and len(B) == 1:
            continue
        for k in range(seg):
            kk = (k + 1) % nring
            if len(A) == 1:
                mb.face([A[0], B[kk], B[k]], mats[i])
            elif len(B) == 1:
                mb.face([A[k], A[kk], B[0]], mats[i])
            else:
                mb.face([A[k], A[kk], B[kk], B[k]], mats[i])
    if caps and full and not closed:
        if len(rings[0]) > 1:
            mb.face(list(reversed(rings[0])), mats[0])
        if len(rings[-1]) > 1:
            mb.face(rings[-1], mats[-1])
    return rings


def lathe(mb, prof, seg=16, mat="steel", M=None, caps=True, phase=0.0):
    """port.lathe sin caras degeneradas en los polos."""
    return revolve(mb, prof, mat, seg=seg, M=M, caps=caps, phase=phase)


def arc_solid(mb, r0, r1, z0, z1, a0, a1, seg, mat, M=None):
    """Sector de anillo grueso (radios r0..r1, alturas z0..z1, ángulos a0..a1): postes de capuchones, collarines, etiquetas."""
    prof = [(r0, z0), (r1, z0), (r1, z1), (r0, z1)]
    rings = []
    for k in range(seg + 1):
        a = a0 + (a1 - a0) * k / seg
        c, s = math.cos(a), math.sin(a)
        ring = [mb.bm.verts.new((M @ Vector((r * c, r * s, z))) if M is not None else Vector((r * c, r * s, z))) for (r, z) in prof]
        rings.append(ring)
    for k in range(seg):
        for j in range(4):
            jj = (j + 1) % 4
            mb.face([rings[k][j], rings[k][jj], rings[k + 1][jj], rings[k + 1][j]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[-1], mat)


def screw(mb, M, d=0.007, mat="steel", recess="cable", seg=10):
    """Tornillo de cabeza de gota (pan head) con ranura de cruz, apoyado en z = 0 local, eje +Z."""
    h = d * 0.38
    lathe(mb, [(0.0, -0.0004), (d / 2, -0.0004), (d / 2, h * 0.35), (d * 0.42, h * 0.75), (d * 0.25, h), (0.0, h)], seg=seg,
               mat=mat, M=M)
    if recess:
        for rz in (0.0, 90.0):
            mb.box((-d * 0.3, -d * 0.055, h * 0.45), (d * 0.3, d * 0.055, h + 0.0005), recess, bevel=0.0, m=M @ _Rz(rz + 20.0))


def hexnut(mb, M, d=0.01, h=None, mat="steel", washer=True):
    """Tuerca hexagonal con chaflán y arandela, apoyada en z = 0 local."""
    h = h if h is not None else d * 0.8
    z = 0.0
    if washer:
        lathe(mb, [(d * 0.3, 0.0), (d * 1.0, 0.0), (d * 1.0, d * 0.12), (d * 0.3, d * 0.12)], seg=12, mat=mat, M=M)
        z = d * 0.12
    lathe(mb, [(d * 0.3, z), (d * 0.82, z), (d * 0.82, z + h * 0.85), (d * 0.7, z + h), (d * 0.3, z + h)], seg=6, mat=mat, M=M,
               phase=PI / 6)


def text(mb, s, size, depth, mat, M=None, align="CENTER", spacing=1.0, bold=False, res=3, back=True):
    """Como kit.clinic.text (letras 3D de la fuente de Blender, de cara a +Z, línea base en y = 0) pero con resolución de curva
    controlada (res) para no gastar triángulos en letreros chicos. back=False omite la cara trasera de las letras (cuando van
    asentadas/embutidas en una placa o etiqueta y nunca se ve)."""
    cu = bpy.data.curves.new("_txt", "FONT")
    cu.body = s
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = align
    cu.space_character = spacing
    cu.resolution_u = res
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
    new = []
    for p in me.polygons:
        if not back and p.normal.z < -0.9:
            continue
        try:
            f = mb.bm.faces.new([vs[i] for i in p.vertices])
            f.material_index = mi
            new.append(f)
        except ValueError:
            pass
    import bmesh
    bad = [f for f in new if f.calc_area() < 1e-8]                     # astillas de < 0,01 mm² de la fuente (las suelda el merge)
    if bad:
        bmesh.ops.delete(mb.bm, geom=bad, context="FACES_ONLY")
    loose = [v for v in vs if v.is_valid and not v.link_faces]           # vértices que solo usaba la cara trasera
    if loose:
        bmesh.ops.delete(mb.bm, geom=loose, context="VERTS")
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return max(xs) - min(xs)


def text_cyl(mb, s, size, depth, mat, R, zc, ang=-PI / 2, M=None, bold=False, spacing=1.0, res=3, back=True):
    """Texto en relieve envuelto sobre un cilindro de radio R (eje Z local), centrado en el ángulo `ang` y altura zc
    (ang = -90° = cara -Y). Cada letra sigue la curvatura: nada flota ni se entierra."""
    tmp = MB()
    text(tmp, s, size, depth, mat, None, align="CENTER", bold=bold, spacing=spacing, res=res, back=back)
    for v in tmp.bm.verts:
        x, y, z = v.co
        a = ang + x / R
        rr = R + z
        p = Vector((rr * math.cos(a), rr * math.sin(a), zc + y - size * 0.36))
        v.co = (M @ p) if M is not None else p
    # la cara frontal del glifo mira hacia afuera: reconstruimos sobre el MB destino
    mb.join(tmp)


def hose(mb, pts, r, mat="rubber", seg=10, rib=None, rad=0.03, nseg=8):
    """Manguera/cable con dobleces de radio real; rib=(paso, amplitud) la hace corrugada."""
    P = fillet(pts, rad, nseg) if len(pts) > 2 else pts
    if rib is None:
        mb.tube(P, r, seg=seg, mat=mat)
        return
    # remuestreo uniforme para el corrugado
    Q = [Vector(P[0])]
    step = rib[0] / 4
    for i in range(1, len(P)):
        a, b = Vector(P[i - 1]), Vector(P[i])
        L = (b - a).length
        n = max(1, int(math.ceil(L / step)))
        for k in range(1, n + 1):
            Q.append(a.lerp(b, k / n))
    s = 0.0
    radii = []
    for i, q in enumerate(Q):
        if i:
            s += (q - Q[i - 1]).length
        radii.append(r * (1.0 + rib[1] * (0.5 + 0.5 * math.cos(2 * PI * s / rib[0]))))
    mb.tube([tuple(q) for q in Q], r, seg=seg, mat=mat, radii=radii)


def bmesh_subdiv(mb, cuts):
    """Subdivide todas las aristas de un MB (para que una placa se pueda curvar sobre una superficie)."""
    import bmesh
    bmesh.ops.subdivide_edges(mb.bm, edges=list(mb.bm.edges), cuts=cuts, use_grid_fill=True)


def loft_rings(mb, rings_pts, mats, M=None, cap0=True, cap1=True, closed=True):
    """Une anillos de igual número de puntos (listas de Vector) con quads; mats: str o lista por tramo del anillo."""
    k = len(rings_pts[0])
    if isinstance(mats, str):
        mats = [mats] * k
    R = [[mb.bm.verts.new((M @ p) if M is not None else p) for p in ring] for ring in rings_pts]
    jr = k if closed else k - 1
    for i in range(len(R) - 1):
        for j in range(jr):
            jj = (j + 1) % k
            mb.face([R[i][j], R[i][jj], R[i + 1][jj], R[i + 1][j]], mats[j])
    if cap0:
        mb.face(list(reversed(R[0])), mats[0])
    if cap1:
        mb.face(R[-1], mats[0])
    return R


# ============================================================================================ luminaria fluorescente
def _louver_blade_prof(h, t0=0.0011, t1=0.0055, n=2):
    """Sección de aleta parabólica: canto inferior redondo que se abre en curva hasta t1 arriba (lámina doblada)."""
    right = [(t0 + (t1 - t0) * (k / n) ** 2, h * k / n) for k in range(n + 1)]
    left = [(-x, z) for (x, z) in reversed(right)]
    return [(0.0, -0.0006)] + right + left


def screw_lo(mb, M, d=0.007, mat="steel", seg=6):
    """Cabeza de tornillo económica (gota de 6 lados) para piezas que se instancian mucho o se ven de lejos."""
    h = d * 0.38
    lathe(mb, [(0.0, -0.0004), (d / 2, -0.0004), (d / 2, h * 0.4), (d * 0.3, h), (0.0, h)], seg=seg, mat=mat, M=M)


def fluorescent(L=1.22, W=0.30, recessed=False):
    """Luminaria fluorescente 2 × T8 de sobreponer (o empotrada con marco) con rejilla parabólica de aluminio.
    Gabinete de lámina doblada con escalón formado, puerta-marco a inglete con holgura y tornillos, reflectores laterales
    inclinados y cubierta central del balastro, 4 portalámparas tipo lápida, 2 tubos T8 con casquillos, rejilla de celdas
    (aletas parabólicas cruzadas) y tornillos de fijación al plafón.
    Presupuesto (se instancia ~70 veces): solo lo que se ve desde abajo; nada de detalle sobre el plafón ni dentro del balastro.
    Origen: plafón, centro; cuelga hacia -Z. El cuerpo de los tubos (lo que emite) va en 'plastic', como el difusor anterior."""
    mb = MB()
    zb = -0.085 if not recessed else -0.008          # fondo de la puerta-marco
    zh = zb + 0.017                                  # unión gabinete / puerta
    ztop = 0.0 if not recessed else zb + 0.095       # respaldo del gabinete
    rc = 0.0085
    # --- gabinete: pared de lámina con escalón formado a 1 cm del plafón y labio inferior redondeado
    path = rrect(L, W, rc, n=2, z=0.0)
    prof = [(0.0, ztop), (0.0, ztop - 0.010), (-0.0025, ztop - 0.013), (-0.0035, zh + 0.004), (-0.0065, zh + 0.0002),
            (-0.0077, zh + 0.0012), (-0.0047, zh + 0.0045), (-0.0037, ztop)]
    mb.sweep(prof, path, mat="sign_white", closed_path=True, normal=(0, 0, 1))
    mb.box((-L / 2 + 0.0045, -W / 2 + 0.0045, ztop - 0.0022), (L / 2 - 0.0045, W / 2 - 0.0045, ztop - 0.0002), "sign_white",
           bevel=0.0)                                                                         # respaldo
    if recessed:                                     # marco de plafón (empotrada): moldura de 2 cm con canto redondo
        fl = [(0.0, 0.0), (0.0, -0.004), (-0.003, -0.006), (-0.022, -0.006), (-0.022, 0.0)]
        mb.sweep(fl, rrect(L + 0.044, W + 0.044, 0.024, n=2, z=0.0), mat="sign_white", closed_path=True, normal=(0, 0, 1))
    # --- puerta-marco (lámina blanca) con 1,5 mm de holgura respecto del gabinete
    pin = [(-L / 2 + 0.0015, -W / 2 + 0.0015, 0.0), (L / 2 - 0.0015, -W / 2 + 0.0015, 0.0), (L / 2 - 0.0015, W / 2 - 0.0015, 0.0),
           (-L / 2 + 0.0015, W / 2 - 0.0015, 0.0)]               # marco a inglete (esquinas soldadas)
    dprof = [(0.0, zh - 0.0015), (0.0, zb + 0.003), (-0.003, zb), (-0.019, zb), (-0.0205, zb + 0.0015), (-0.0205, zb + 0.009),
             (-0.0195, zb + 0.009), (-0.0195, zb + 0.0012), (-0.0045, zb + 0.0012), (-0.0012, zb + 0.004), (-0.0012, zh - 0.0015)]
    mb.sweep(dprof, pin, mat="sign_white", closed_path=True, normal=(0, 0, 1))
    xi, yi = L / 2 - 0.0215, W / 2 - 0.0215          # claro interior de la rejilla
    for sx in (-1, 1):                               # tornillos de la puerta en las cabeceras
        for yk in (-W / 4, W / 4):
            screw_lo(mb, _T(sx * (L / 2 - 0.011), yk, zb) @ _Rx(180), d=0.0065)
    # --- rejilla parabólica: aleta longitudinal central y aletas transversales
    hb = 0.032
    z0 = zb + 0.0012
    bp = _louver_blade_prof(hb)
    mb.sweep(_louver_blade_prof(hb - 0.0025), [(-xi, 0.0, z0), (xi, 0.0, z0)], mat="aluminium", normal=(0, 0, 1))
    for sy in (-1, 1):                               # aletas perimetrales (medias aletas contra el marco)
        y = sy * (yi - 0.0035)
        mb.sweep([(0.0, 0.0), (0.0012, 0.0), (0.0012, hb - 0.0045), (0.0, hb - 0.0045)], [(-xi, y, z0), (xi, y, z0)], mat="aluminium",
                 normal=(0, 0, 1))
    ncell = max(2, int(round(2 * xi / 0.11)))
    for k in range(1, ncell):
        x = -xi + 2 * xi * k / ncell
        mb.sweep(bp, [(x, -yi, z0), (x, yi, z0)], mat="aluminium", normal=(0, 0, 1))
    for sx in (-1, 1):
        x = sx * (xi - 0.0035)
        mb.sweep([(0.0, 0.0), (0.0012, 0.0), (0.0012, hb - 0.0045), (0.0, hb - 0.0045)], [(x, -yi, z0), (x, yi, z0)], mat="aluminium",
                 normal=(0, 0, 1))
    # --- reflector: laterales inclinados y cubierta central del balastro (lámina blanca)
    zr = ztop - 0.0022
    xr = L / 2 - 0.045
    for sy in (-1, 1):
        a = Vector((0, sy * (W / 2 - 0.0013), zh + 0.012))
        b = Vector((0, sy * (W / 2 - 0.05), zr - 0.0005))
        n = Vector((0, -(b - a).z, (b - a).y)).normalized() * 0.0009 * sy
        q = [(a.y, a.z), (b.y, b.z), (b.y + n.y, b.z + n.z), (a.y + n.y, a.z + n.z)]
        rings = [[Vector((x, yy, zz)) for (yy, zz) in q] for x in (-xr, xr)]
        loft_rings(mb, rings, "sign_white")
    ridge = [(-0.034, zr), (-0.03, zr - 0.004), (-0.004, zr - 0.021), (0.0, zr - 0.0225), (0.004, zr - 0.021), (0.03, zr - 0.004),
             (0.034, zr)]
    rings = [[Vector((x, yy, zz)) for (yy, zz) in ridge] for x in (-xr, xr)]
    loft_rings(mb, rings, "sign_white")
    for sx in (-1, 1):                               # tornillos de fijación al plafón, a la vista entre portalámparas
        screw_lo(mb, _T(sx * (L / 2 - 0.028), 0.0, zr) @ _Rx(180), d=0.008)
    # --- portalámparas tipo lápida y tubos T8
    zt = zr - 0.031
    rt = 0.0128
    perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    for sy in (-1, 1):
        yt = sy * W / 4
        for sx in (-1, 1):
            xl = sx * (L / 2 - 0.024)
            out = [(yt + 0.011, zr), (yt + 0.011, zt)] + [(yt + 0.011 * math.cos(a), zt - 0.011 * math.sin(a))
                                                         for a in (PI / 4, PI / 2, 3 * PI / 4)] + [(yt - 0.011, zt), (yt - 0.011, zr)]
            mb.plate(out, 0.011, "sign_white", m=_T(xl - (0.011 if sx > 0 else 0.0), 0, 0) @ perm)
        x0 = -L / 2 + 0.036
        x1 = L / 2 - 0.036
        Lt = x1 - x0
        prof = [(0.0, 0.0), (rt + 0.0004, 0.0), (rt + 0.0004, 0.013), (rt, 0.0135), (rt, Lt - 0.0135), (rt + 0.0004, Lt - 0.013),
                (rt + 0.0004, Lt), (0.0, Lt)]
        mats = ["aluminium", "aluminium", "aluminium", "plastic", "aluminium", "aluminium", "aluminium"]
        revolve(mb, prof, mats, seg=10, M=_T(x0, yt, zt) @ _Ry(90))
    return mb


# ======================================================================================================== ventilador
def sweep_frame(mb, prof, path, mat, up=(0, 0, 1), twist=None, scale=None, caps=True):
    """Barre un perfil 2D (x lateral, y en `up`) por una polilínea suave, con giro twist(s) [rad] y escala scale(s) -> (sx, sy),
    s = 0..1 por longitud de arco. Brazos de aspas, asas, flejes que cambian de ancho o se tuercen."""
    P = [Vector(p) for p in path]
    n = len(P)
    U = Vector(up)
    acc = [0.0]
    for i in range(1, n):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    tot = acc[-1] or 1.0
    rings = []
    for i in range(n):
        T = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized()
        N = (U - T * U.dot(T))
        N = N.normalized() if N.length > 1e-6 else Vector((1, 0, 0))
        B = T.cross(N)
        s = acc[i] / tot
        tw = twist(s) if twist else 0.0
        sx, sy = scale(s) if scale else (1.0, 1.0)
        c, sn = math.cos(tw), math.sin(tw)
        ring = []
        for (x, y) in prof:
            x, y = x * sx, y * sy
            xr, yr = x * c - y * sn, x * sn + y * c
            ring.append(P[i] + B * xr + N * yr)
        rings.append(ring)
    return loft_rings(mb, rings, mat, cap0=caps, cap1=caps)


def _fan_blade(mb, M, r0=0.18, r1=0.68, w=0.122, t=0.0095, mat="wood_varnish"):
    """Aspa de madera contrachapada: planta con esquinas de raíz redondeadas y punta de radio amplio, cantos redondos
    (sección de estadio con ligera corona), espesor que adelgaza hacia la punta. Local: x radial, y cuerda, z espesor (arriba = 0)."""
    rr, rt = 0.008, 0.045
    xs = [r0, r0 + rr * 0.5, r0 + rr] + [r0 + rr + (r1 - rt - r0 - rr) * k / 3 for k in range(1, 4)]
    xs += [r1 - rt + rt * math.sin(PI / 2 * k / 4) for k in range(1, 5)]
    rings = []
    for x in xs:
        hw = w / 2
        if x < r0 + rr:
            hw = w / 2 - rr + math.sqrt(max(rr * rr - (r0 + rr - x) ** 2, 0.0))
        elif x > r1 - rt:
            hw = w / 2 - rt + math.sqrt(max(rt * rt - (x - (r1 - rt)) ** 2, 0.0))
        tt = t * (1.0 - 0.22 * (x - r0) / (r1 - r0))
        hw = max(hw, tt * 0.6)
        e = tt / 2
        ring = []
        for k in range(4):                                       # canto +y
            a = -PI / 2 + PI * k / 3
            ring.append(Vector((x, hw - e + e * math.cos(a), -e + e * math.sin(a))))
        ring.append(Vector((x, 0.0, 0.0006)))                    # cara superior con corona
        for k in range(4):                                       # canto -y
            a = PI / 2 + PI * k / 3
            ring.append(Vector((x, -(hw - e) + e * math.cos(a), -e + e * math.sin(a))))
        ring.append(Vector((x, 0.0, -tt)))                       # cara inferior
        rings.append(ring)
    loft_rings(mb, rings, mat, M=M)


def ceiling_fan(seed=0, drop=0.35):
    """Ventilador de techo sencillo de 3 aspas (Ø 1,36 m), en uso: florón con tornillos de sujeción, tubo bajante de 3/4" con
    perno pasador y chaveta en el yugo, carcasa superior fija con ranuras de ventilación (estator visible), junta de giro,
    carcasa inferior giratoria con moldura, tapa de interruptor con remate y tornillos, 3 brazos de lámina troquelada con giro
    hacia el ángulo de ataque, empaques de hule y aspas de madera con espesor, cantos redondos y 3 tornillos con arandela.
    Origen: losa, centro; cuelga hacia -Z."""
    r = rng(seed)
    mb = MB()
    # --- florón (cubre la caja de conexión) con aro y tornillos de sujeción
    revolve(mb, [(0.068, -0.0001), (0.068, -0.0055), (0.0655, -0.0075), (0.0655, -0.0105), (0.062, -0.017),
                 (0.054, -0.036), (0.042, -0.055), (0.03, -0.066), (0.022, -0.0705), (0.0168, -0.0705), (0.0168, -0.058),
                 (0.0, -0.058)], "sign_white", seg=24, caps=False)                       # tapa superior contra la losa: no se modela
    for k in range(2):
        a = PI * k + 0.4
        n = Vector((math.cos(a), math.sin(a), 0))
        p = Vector((0.0645 * math.cos(a), 0.0645 * math.sin(a), -0.0135))
        Mx = Matrix.Translation(p) @ n.to_track_quat("Z", "Y").to_matrix().to_4x4()
        screw_lo(mb, Mx, d=0.0075)
    # --- tubo bajante con rosca, yugo, perno y chaveta
    z0 = -drop
    rd = 0.0133
    mb.cyl((0, 0, -0.057), (0, 0, z0 + 0.012), rd, seg=12, mat="steel", caps=False)           # extremos ocultos en florón y yugo
    zy = z0 + 0.012                                       # yugo (collar del motor)
    revolve(mb, [(0.0, z0 + 0.001), (0.03, z0 + 0.001), (0.03, z0 + 0.004), (0.026, z0 + 0.008), (0.026, zy + 0.034),
                 (0.0235, zy + 0.037), (0.0145, zy + 0.037), (0.0145, zy + 0.03), (0.0, zy + 0.03)], "sign_white", seg=16)
    zp = zy + 0.022
    revolve(mb, [(0.0, 0.0), (0.0055, 0.0), (0.0055, 0.0028), (0.0035, 0.0038), (0.0, 0.0038)], "steel", seg=8,
            M=_T(-0.0262, 0, zp) @ _Ry(-90))                                       # cabeza del perno
    mb.cyl((-0.0262, 0, zp), (0.033, 0, zp), 0.0028, seg=8, mat="steel")
    hp = [(0.031, 0.0, zp), (0.031, -0.004, zp - 0.003), (0.03, -0.012, zp - 0.006), (0.026, -0.02, zp - 0.008),
          (0.02, -0.024, zp - 0.008)]
    mb.tube(fillet([(0.031, 0.0, zp + 0.001)] + [(x, y, z) for (x, y, z) in hp], 0.003, 2), 0.0011, seg=4, mat="steel")
    for a in (PI / 2 + 0.6, -PI / 2 - 0.6):                                       # opresores del yugo
        n = Vector((math.cos(a), math.sin(a), 0))
        Mx = Matrix.Translation(n * 0.0262 + Vector((0, 0, zy + 0.008))) @ n.to_track_quat("Z", "Y").to_matrix().to_4x4()
        hexnut(mb, Mx, d=0.0045, washer=False)
    # --- carcasa superior fija, banda de ventilación y estator
    zc = z0
    revolve(mb, [(0.0, zc), (0.0335, zc), (0.036, zc - 0.002), (0.058, zc - 0.009), (0.082, zc - 0.02), (0.097, zc - 0.03),
                 (0.1045, zc - 0.037), (0.106, zc - 0.041), (0.096, zc - 0.041), (0.0, zc - 0.041)], "sign_white", seg=32)
    revolve(mb, [(0.0955, zc - 0.039), (0.0955, zc - 0.064)], "cable", seg=20, caps=False)       # estator (solo se ve su costado)
    nv = 20
    for k in range(nv):
        a = 2 * PI * k / nv
        arc_solid(mb, 0.094, 0.106, zc - 0.0563, zc - 0.0407, a, a + 2 * PI / nv * 0.52, 1, "sign_white")
    revolve(mb, [(0.094, zc - 0.0565), (0.106, zc - 0.0565), (0.106, zc - 0.0585), (0.094, zc - 0.0585)],
            "sign_white", seg=32, closed=True)
    # --- carcasa inferior giratoria (2,5 mm de junta) con moldura
    zr = zc - 0.061
    revolve(mb, [(0.0, zr), (0.105, zr), (0.111, zr - 0.004), (0.1155, zr - 0.011), (0.1165, zr - 0.017), (0.1145, zr - 0.019),
                 (0.1165, zr - 0.021), (0.116, zr - 0.029), (0.1125, zr - 0.036), (0.105, zr - 0.0425), (0.099, zr - 0.0445),
                 (0.0, zr - 0.0445)], "sign_white", seg=32)
    zb = zr - 0.0445
    # --- tapa del interruptor con tornillos y remate
    revolve(mb, [(0.0, zb + 0.0002), (0.069, zb + 0.0002), (0.069, zb - 0.0035), (0.066, zb - 0.008), (0.058, zb - 0.016),
                 (0.044, zb - 0.023), (0.026, zb - 0.0265), (0.0, zb - 0.0275)], "sign_white", seg=32)
    for k in range(3):
        a = 2 * PI * k / 3 + 0.5
        n = Vector((math.cos(a) * 0.8, math.sin(a) * 0.8, -0.6)).normalized()
        p = Vector((0.0598 * math.cos(a), 0.0598 * math.sin(a), zb - 0.0135))
        screw_lo(mb, Matrix.Translation(p - n * 0.0006) @ n.to_track_quat("Z", "Y").to_matrix().to_4x4(), d=0.0065)
    revolve(mb, [(0.0, zb - 0.026), (0.0105, zb - 0.026), (0.012, zb - 0.029), (0.0115, zb - 0.0335), (0.008, zb - 0.0375),
                 (0.004, zb - 0.0395), (0.0, zb - 0.04)], "aluminium", seg=12)
    # --- brazos, empaques, aspas y tornillos
    pitch = 12.0
    a0 = float(r.uniform(0, 120))
    zi = zb - 0.0025                                       # eje del brazo (lámina de 5 mm bajo la carcasa)
    for k in range(3):
        a = math.radians(a0 + 120 * k)
        Rz = Matrix.Rotation(a, 4, "Z")
        path = fillet([(0.0715, 0, zi), (0.108, 0, zi), (0.152, 0, zi - 0.0115), (0.205, 0, zi - 0.0145), (0.292, 0, zi - 0.0145)], 0.025, 3)
        path = [tuple(Rz @ Vector(p)) for p in path]
        tw = math.radians(pitch)
        sweep_frame(mb, rr_profile(0.034, 0.005, 0.0018, n=1), path, "steel", up=(0, 0, 1),
                    twist=lambda s, tw=tw: -tw * min(1.0, max(0.0, (s - 0.35) / 0.3)),
                    scale=lambda s: (1.0 + 0.75 * min(1.0, max(0.0, (s - 0.55) / 0.25)) - 0.35 * max(0.0, (s - 0.9) / 0.1), 1.0))
        for xs in (0.08, 0.096):                                                 # tornillos a la carcasa (desde abajo)
            screw_lo(mb, Rz @ _T(xs, 0, zi - 0.0025) @ _Rx(180), d=0.007)
        Mb = Rz @ _T(0, 0, zi - 0.0145) @ _Rx(pitch)
        mb.plate(rrect(0.085, 0.052, 0.012, n=1, cx=0.247), 0.0019, "rubber", m=Mb @ _T(0, 0, -0.0025 - 0.0017))   # empaque
        _fan_blade(mb, Mb @ _T(0, 0, -0.0025 - 0.0015), r0=0.18, r1=0.68, w=0.122, t=0.0095)
        for (xs, ys) in ((0.215, 0.0), (0.262, -0.016), (0.262, 0.016)):
            zt = -0.0025 - 0.0015 - 0.0095 * (1.0 - 0.22 * (xs - 0.18) / 0.5)
            Mt = Mb @ _T(xs, ys, zt) @ _Rx(180)
            lathe(mb, [(0.0035, -0.0002), (0.0065, -0.0002), (0.0065, 0.001), (0.0035, 0.001)], seg=8, mat="rubber", M=Mt)
            screw(mb, Mt @ _T(0, 0, 0.001), d=0.0082, seg=8, recess=None)
    return mb


# ======================================================================================================== minisplit
def loft_shared(mb, rings, mats, M=None, cap0=True, cap1=True, tol=1e-7):
    """Como loft_rings, pero los puntos que coinciden entre anillos consecutivos comparten vértice: dos anillos en la misma x
    con un rasgo 'colapsado' y 'activo' generan solo las paredes del rasgo (ranuras, canales, ductos), sin caras degeneradas."""
    k = len(rings[0])
    if isinstance(mats, str):
        mats = [mats] * k
    cache = {}

    def V(p):
        key = (round(p.x / tol), round(p.y / tol), round(p.z / tol))
        v = cache.get(key)
        if v is None:
            v = mb.bm.verts.new((M @ p) if M is not None else p)
            cache[key] = v
        return v

    R = [[V(p) for p in ring] for ring in rings]
    for i in range(len(R) - 1):
        for j in range(k):
            jj = (j + 1) % k
            q = [R[i][j], R[i][jj], R[i + 1][jj], R[i + 1][j]]
            u = []
            for v in q:
                if v not in u:
                    u.append(v)
            if len(u) >= 3:
                try:
                    mb.face(u, mats[j])
                except ValueError:
                    pass
    for ring, rev, do in ((R[0], True, cap0), (R[-1], False, cap1)):
        if do:
            u = []
            for v in ring:
                if v not in u:
                    u.append(v)
            mb.face(list(reversed(u)) if rev else u, mats[0])
    return R


def _split_contour(features):
    """Sección (y, z) de la unidad interior, con rasgos activables: 'top' (canal de toma superior), 'gt'/'gb' (juntas del
    frente) y 'out' (ducto de descarga). Devuelve (puntos, materiales por tramo)."""
    pts, mats = [], []

    def add(seq, mat="sign_white"):
        for p in seq:
            pts.append(p)
            mats.append(mat)

    def lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    add([(-0.006, 0.006), (-0.006, 0.274), (-0.0075, 0.2785), (-0.010, 0.28)])
    add([(-0.030, 0.28)], "cable" if "top" in features else "sign_white")
    if "top" in features:
        add([(-0.0318, 0.2665), (-0.1482, 0.2665)], "cable")
    else:
        add([(-0.0318, 0.28), (-0.1482, 0.28)])
    add([(-0.150, 0.28), (-0.160, 0.2797), (-0.168, 0.2788), (-0.176, 0.2765), (-0.1835, 0.2725), (-0.190, 0.266)])
    a, b = (-0.190, 0.266), (-0.196, 0.250)
    if "gt" in features:
        add([(-0.1925, 0.2605), (-0.1912, 0.2583), (-0.1938, 0.2558)])
    else:
        add([lerp(a, b, 0.33), lerp(a, b, 0.48), lerp(a, b, 0.62)])
    add([(-0.196, 0.250), (-0.1995, 0.220), (-0.2012, 0.190), (-0.2015, 0.160), (-0.2005, 0.130), (-0.198, 0.100)])
    a, b = (-0.198, 0.100), (-0.193, 0.074)
    if "gb" in features:
        add([(-0.1971, 0.0905), (-0.1953, 0.0878), (-0.1961, 0.0850)])
    else:
        add([lerp(a, b, 0.37), lerp(a, b, 0.48), lerp(a, b, 0.58)])
    add([(-0.193, 0.074)])
    add([(-0.1895, 0.066)], "cable" if "out" in features else "sign_white")
    if "out" in features:
        add([(-0.181, 0.069), (-0.168, 0.0735), (-0.152, 0.0735), (-0.136, 0.067), (-0.122, 0.054), (-0.111, 0.034),
             (-0.106, 0.012)], "cable")
    else:
        add([(-0.183, 0.054), (-0.175, 0.042), (-0.165, 0.031), (-0.152, 0.021), (-0.137, 0.013), (-0.122, 0.0078),
             (-0.110, 0.0052)])
    add([(-0.100, 0.0038), (-0.070, 0.0012), (-0.040, 0.0), (-0.014, 0.0), (-0.009, 0.0012), (-0.0068, 0.0035)])
    return pts, mats


def split_indoor(seed=0):
    """Minisplit (unidad interior) 0,80 × 0,20 × 0,28 en operación: carcasa de lámina plástica con tapas laterales redondeadas y
    junta perimetral, panel frontal abombado con juntas, canal de toma superior con rejilla de barras (fondo oscuro real),
    ducto de descarga con 15 aletas verticales y barra de enlace, deflector horizontal curvo abierto con pernos, ventana de
    display con LEDs y receptor IR, placa de montaje visible en la holgura del muro, haz de tubería forrado con cinta en espiral
    y manguera de condensado corrugada que entran al muro por un chapetón (origen: muro, centro inferior)."""
    r = rng(seed)
    mb = MB()
    xe, re_ = 0.4, 0.018
    full = {"top", "gt", "gb", "out"}

    def ring(x, feats, d=0.0):
        """Sección en x; d > 0 la encoge hacia su centro (tapas redondeadas y junta), escalando sin autointersecciones."""
        pts, _ = _split_contour(feats)
        cy, cz = -0.1035, 0.14
        ky, kz = 1.0 - 2 * d / 0.1955, 1.0 - 2 * d / 0.28
        return [Vector((x, cy + (y - cy) * ky, cz + (z - cz) * kz)) for (y, z) in pts]

    stations = []                                          # (x, rasgos, desplazamiento hacia dentro)
    for k in range(5):                                     # tapa lateral redondeada
        th = PI / 2 * (4 - k) / 4
        stations.append((xe - re_ + re_ * math.sin(th), set(), re_ * (1 - math.cos(th))))
    stations += [(0.3755, set(), 0.0), (0.3742, set(), 0.0013), (0.3729, set(), 0.0),       # junta tapa / cuerpo
                 (0.366, set(), 0.0), (0.366, {"gt", "gb"}, 0.0), (0.352, {"gt", "gb"}, 0.0), (0.352, {"gt", "gb", "top"}, 0.0),
                 (0.335, {"gt", "gb", "top"}, 0.0), (0.335, full, 0.0)]
    rings = [ring(x, f, d) for (x, f, d) in stations]
    rings += [ring(-x, f, d) for (x, f, d) in reversed(stations)]
    _, mats = _split_contour(full)
    loft_shared(mb, rings, mats)
    # placa de montaje en la holgura con el muro
    mb.box((-0.36, -0.0062, 0.03), (0.36, -0.0003, 0.255), "steel", bevel=0.0015)
    # rejilla del canal de toma: barras a lo largo de y, apoyadas en dos travesaños
    xb = -0.344
    while xb < 0.344:
        mb.box((xb, -0.1478, 0.2665 - 0.0002), (xb + 0.0032, -0.0322, 0.2795), "sign_white", bevel=0.0)
        xb += 0.0072
    for yb in (-0.07, -0.11):
        mb.box((-0.35, yb - 0.002, 0.2663), (0.35, yb + 0.002, 0.2765), "sign_white", bevel=0.0006)
    # aletas verticales del ducto de descarga + barra de enlace
    vane = [(-0.176, 0.0655), (-0.152, 0.0705), (-0.133, 0.0645), (-0.1205, 0.047), (-0.131, 0.031), (-0.158, 0.043)]
    perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    sw = float(r.uniform(-14, 14))
    for k in range(15):
        x = -0.3 + 0.6 * k / 14
        Mv = _T(x, -0.15, 0.0) @ _Rz(sw) @ _T(0, 0.15, 0) @ _T(-0.00075, 0, 0) @ perm
        mb.plate(vane, 0.0015, "sign_white", m=Mv)
    mb.box((-0.305, -0.1255, 0.046), (0.305, -0.1215, 0.05), "sign_white", bevel=0.0008)
    # deflector horizontal (curvo, abierto hacia abajo) con pernos a las paredes del ducto
    fl = []
    for k in range(9):
        t = k / 8
        y = -0.178 + 0.05 * t
        z = 0.008 + 0.046 * t - 0.007 * math.sin(PI * t)
        fl.append((y, z))
    sec = fl + [(y + 0.0022, z - 0.0022) for (y, z) in reversed(fl)]
    rings = [[Vector((x, y, z)) for (y, z) in sec] for x in (-0.333, 0.333)]
    loft_rings(mb, rings, "sign_white")
    for sx in (-1, 1):
        mb.cyl((sx * 0.333, -0.153, 0.032), (sx * 0.3365, -0.153, 0.032), 0.003, seg=8, mat="steel")
    # ventana de display con LEDs y receptor IR (sobresale 1,2 mm del frente)
    Md = _T(0.255, -0.2008, 0.128) @ _Rx(90)
    mb.plate(rrect(0.078, 0.024, 0.006, n=3), 0.002, "glass", m=Md @ _T(0, 0, -0.0008))
    for k, mat in enumerate(("sign_green", "sign_blue", "paint_yellow")):
        lathe(mb, [(0.0, 0.0), (0.0016, 0.0), (0.0016, 0.0006), (0.0, 0.0009)], seg=8, mat=mat, M=Md @ _T(-0.025 + k * 0.012, -0.004, 0.0012))
    lathe(mb, [(0.0, 0.0), (0.0042, 0.0), (0.0042, 0.0005), (0.0, 0.0022)], seg=12, mat="cable", M=Md @ _T(0.024, 0.0, 0.0012))
    # haz de tubería con cinta en espiral + manguera de condensado, entrando al muro por un chapetón ovalado
    hose(mb, [(0.30, -0.032, 0.03), (0.30, -0.032, -0.006), (0.30, 0.002, -0.006)], 0.0155, mat="vinyl", seg=12,
         rib=(0.019, 0.07), rad=0.016, nseg=8)
    hose(mb, [(0.336, -0.03, 0.03), (0.336, -0.03, -0.004), (0.336, 0.002, -0.004)], 0.0068, mat="plastic", seg=8,
         rib=(0.009, 0.13), rad=0.012, nseg=6)
    esc = [(p[0] + 0.317, -0.0045, p[1] - 0.006) for p in rrect(0.09, 0.05, 0.024, n=3)]
    mb.sweep([(0.0, 0.0), (0.0, 0.0044), (0.003, 0.0044), (0.008, 0.0016), (0.008, 0.0)],
             [(x, -0.0045, z) for (x, _, z) in esc], mat="sign_white", closed_path=True, normal=(0, 1, 0))
    return mb


# ======================================================================================================== extintor
def gauge(mb, M, r=0.016, depth=0.011, zone_mat="sign_green", needle=-3.0):
    """Manómetro de carátula: caja embutida, bisel, carátula blanca rehundida, arco de zona de carga, aguja y eje.
    Local: la carátula mira a +Z, base en z = 0."""
    revolve(mb, [(0.0, 0.0), (r * 0.93, 0.0), (r, depth * 0.25), (r, depth * 0.8), (r * 1.06, depth * 0.84), (r * 1.06, depth),
                 (r * 0.9, depth), (r * 0.9, depth - 0.0015), (0.0, depth - 0.0015)],
            ["steel", "steel", "steel", "steel", "steel", "steel", "steel", "sign_white"], seg=16, M=M)
    zf = depth - 0.0015
    arc_solid(mb, r * 0.55, r * 0.78, zf - 0.0002, zf + 0.0005, math.radians(60), math.radians(120), 6, zone_mat, M=M)
    for k in range(7):                                                  # marcas de escala
        a = math.radians(-30 + 40 * k)
        mb.box((-0.0004, r * 0.8, -0.0002), (0.0004, r * 0.88, 0.0004), "cable", bevel=0.0,
               m=M @ _T(0, 0, zf) @ Matrix.Rotation(a - PI / 2, 4, "Z"))
    mb.box((-0.0005, -0.002, 0.0003), (0.0005, r * 0.72, 0.0009), "cable", bevel=0.0,
           m=M @ _T(0, 0, zf) @ Matrix.Rotation(math.radians(needle), 4, "Z"))  # aguja en zona verde
    lathe(mb, [(0.0, -0.0002), (0.0014, -0.0002), (0.0014, 0.0012), (0.0, 0.0014)], seg=8, mat="cable", M=M @ _T(0, 0, zf))


def extinguisher(seed=0):
    """Extintor PQS de 6 kg colgado de su gancho, con letrero arriba (origen: cara del muro, piso).
    Cilindro con pie embutido y domo, etiqueta envolvente de 1,2 mm con letras en relieve y renglones de instrucciones,
    tuerca moleteada de cuello, cuerpo de válvula, manija de transporte y palanca de disparo de lámina troquelada en canal,
    pasador de seguridad con argolla y cincho de garantía, manómetro con bisel y aguja, salida con conexión hexagonal,
    manguera con casquillos prensados y boquilla sujeta por un fleje con clip; gancho de lámina atornillado al muro."""
    r = rng(seed)
    mb = MB()
    yc, zb = -0.1, 1.0
    R = 0.08
    Mc = _T(0, yc, zb)
    # --- cilindro
    body = [(0.072, 0.0), (0.0775, 0.0025), (0.0795, 0.008), (R, 0.014), (R, 0.398),
            (0.0786, 0.413), (0.0745, 0.428), (0.067, 0.443), (0.056, 0.455), (0.043, 0.464), (0.03, 0.47), (0.0205, 0.4725),
            (0.0185, 0.4735), (0.0185, 0.49)]                       # fondo plano (no se ve) y cuello tapado por la tuerca
    revolve(mb, body, "sign_red", seg=28, M=Mc)
    # etiqueta envolvente (sobresale 1,2 mm) con texto y renglones
    a0, a1 = math.radians(-90 - 78), math.radians(-90 + 78)
    arc_solid(mb, R - 0.0006, R + 0.0016, 0.13, 0.372, a0, a1, 20, "sign_white", M=Mc)
    text_cyl(mb, "FIRE", 0.042, 0.0015, "sign_red", R + 0.0014, 0.318, M=Mc, bold=True, res=2, back=False)
    text_cyl(mb, "EXTINGUISHER", 0.0155, 0.0013, "cable", R + 0.0014, 0.29, M=Mc, res=2, back=False)
    text_cyl(mb, "ABC  6 KG", 0.016, 0.0013, "sign_red", R + 0.0014, 0.262, M=Mc, bold=True, res=2, back=False)
    for k in range(5):                                                  # renglones de instrucciones
        zl = 0.228 - k * 0.0145
        half = math.radians(52 if k % 3 else 38)
        arc_solid(mb, R + 0.0014, R + 0.0034, zl, zl + 0.0042, -PI / 2 - half, -PI / 2 + half * (0.9 if k % 2 else 1.0), 7, "cable",
                  M=Mc)
    arc_solid(mb, R + 0.0014, R + 0.0034, 0.142, 0.152, -PI / 2 - math.radians(70), -PI / 2 + math.radians(70), 12, "sign_red", M=Mc)
    # fleje porta-boquilla
    revolve(mb, [(R - 0.0005, 0.085), (R + 0.0016, 0.085), (R + 0.0016, 0.099), (R - 0.0005, 0.099)], "steel", seg=28, M=Mc,
            closed=True)
    # --- válvula
    zt = zb + 0.49
    nut = lambda a: 1.0 + 0.045 * (0.5 + 0.5 * math.cos(18 * a))
    revolve(mb, [(0.0, 0.0), (0.0235, 0.001), (0.0235, 0.012), (0.0, 0.013)], "steel", seg=36, M=_T(0, yc, zt - 0.001), rmod=nut)
    revolve(mb, [(0.0165, 0.012), (0.0165, 0.02), (0.0145, 0.024), (0.0145, 0.036), (0.016, 0.04)],
            "steel", seg=16, M=_T(0, yc, zt))
    zh = zt + 0.038
    mb.box((-0.012, yc - 0.022, zh), (0.012, yc + 0.03, zh + 0.021), "steel", bevel=0.003, seg=2)
    # manija de transporte (fija, hacia el muro) y palanca de disparo: lámina en canal con nervio
    ch = [(-0.0125, -0.0045), (0.0125, -0.0045), (0.0125, 0.0045), (0.0105, 0.0045), (0.0105, -0.0025), (-0.0105, -0.0025),
          (-0.0105, 0.0045), (-0.0125, 0.0045)]
    sweep_frame(mb, ch, fillet([(0, yc + 0.02, zh + 0.006), (0, yc + 0.05, zh + 0.004), (0, yc + 0.088, zh - 0.004)], 0.03, 3),
                "steel", up=(0, 0, 1))
    revolve(mb, [(0.0, 0.0), (0.0135, 0.0), (0.0135, 0.004), (0.0, 0.004)], "plastic", seg=8,
            M=_T(0, yc + 0.088, zh - 0.004) @ _Rx(-90))                                  # tapón del extremo
    sweep_frame(mb, [(x, -y) for (x, y) in ch], fillet([(0, yc - 0.016, zh + 0.026), (0, yc + 0.03, zh + 0.035),
                                                         (0, yc + 0.092, zh + 0.05)], 0.04, 3), "steel", up=(0, 0, 1))
    for sx in (-1, 1):                                                  # orejas y perno del pivote
        mb.box((sx * 0.0125 - 0.0015, yc - 0.024, zh + 0.012), (sx * 0.0125 + 0.0015, yc - 0.008, zh + 0.032), "steel", bevel=0.0007,
               seg=1)
    mb.cyl((-0.016, yc - 0.016, zh + 0.026), (0.016, yc - 0.016, zh + 0.026), 0.0022, seg=8, mat="steel")
    # pasador de seguridad con argolla y cincho de garantía
    zp = zh + 0.017
    mb.cyl((-0.018, yc + 0.006, zp), (0.016, yc + 0.006, zp), 0.0016, seg=8, mat="steel")
    ring = [(-0.018 - 0.011 + 0.011 * math.cos(a), yc + 0.006, zp + 0.011 * math.sin(a)) for a in [2 * PI * k / 10 for k in range(10)]]
    loop_tube(mb, ring, 0.0013, seg=5, mat="steel", normal=(0, 1, 0))
    seal = [(-0.03, yc + 0.006, zp + 0.011), (-0.026, yc + 0.012, zp + 0.02), (-0.012, yc + 0.03, zp + 0.024),
            (0.0, yc + 0.034, zp + 0.019), (0.012, yc + 0.03, zp + 0.016)]
    mb.tube(fillet(seal, 0.006, 2), 0.0008, seg=4, mat="paint_yellow")
    mb.box((-0.0025, yc + 0.026, zp + 0.012), (0.0035, yc + 0.034, zp + 0.016), "paint_yellow", bevel=0.0006, seg=1)
    # manómetro al frente
    mb.cyl((0, yc - 0.012, zt + 0.026), (0, yc - 0.026, zt + 0.026), 0.0045, seg=8, mat="steel", caps=False)
    hexnut(mb, _T(0, yc - 0.017, zt + 0.026) @ _Rx(90), d=0.0055, washer=False)
    gauge(mb, _T(0, yc - 0.026, zt + 0.026) @ _Rx(90), r=0.0155, depth=0.0105, needle=float(r.uniform(-9.0, 6.0)))
    # salida, manguera y boquilla con clip
    hexnut(mb, _T(0.0145, yc, zt + 0.02) @ _Ry(90), d=0.008, h=0.009, washer=False)
    mb.cyl((0.02, yc, zt + 0.02), (0.04, yc, zt + 0.02), 0.0088, seg=10, mat="steel")
    for k in range(3):
        xk = 0.024 + k * 0.006
        mb.cyl((xk, yc, zt + 0.02), (xk + 0.0025, yc, zt + 0.02), 0.0101, seg=10, mat="steel")
    hp = [(0.039, yc, zt + 0.02), (0.06, yc + 0.002, zt + 0.012), (0.0915, yc + 0.006, zt - 0.06), (0.0925, yc + 0.004, zb + 0.30),
          (0.0915, yc - 0.002, zb + 0.16), (0.0905, yc - 0.006, zb + 0.13)]
    hose(mb, hp, 0.0076, mat="rubber", seg=8, rad=0.05, nseg=3)
    pe = Vector(hp[-1])
    dn = (pe - Vector(hp[-2])).normalized()
    Mn = Matrix.Translation(pe) @ dn.to_track_quat("Z", "Y").to_matrix().to_4x4()
    revolve(mb, [(0.0, -0.004), (0.0092, -0.004), (0.0092, 0.012), (0.0085, 0.014), (0.0068, 0.016), (0.0068, 0.05),
                 (0.0058, 0.066), (0.0035, 0.066), (0.0035, 0.06), (0.0, 0.06)], ["steel", "steel", "steel", "cable", "cable", "cable",
                                                                                    "cable", "cable", "cable"], seg=8, M=Mn)
    # clip del fleje que sujeta la boquilla
    ang = math.atan2(pe.y - yc, pe.x)
    cpos = Vector((R * math.cos(ang), yc + R * math.sin(ang), zb + 0.092))
    nrm = Vector((math.cos(ang), math.sin(ang), 0))
    Mk = Matrix.Translation(cpos) @ nrm.to_track_quat("Z", "Y").to_matrix().to_4x4()
    clip = [(-0.006, 0.0, 0.0), (-0.006, 0.0, 0.004), (-0.0085, 0.0, 0.0105), (-0.006, 0.0, 0.0175), (0.0, 0.0, 0.0195),
            (0.006, 0.0, 0.0175), (0.0085, 0.0, 0.0105), (0.0072, 0.0, 0.006)]
    sweep_frame(mb, rr_profile(0.0012, 0.012, 0.0005, n=1), [tuple(Mk @ Vector(p)) for p in clip], "steel",
                up=tuple(Mk.to_3x3() @ Vector((0, 1, 0))))
    # --- gancho de lámina atornillado al muro
    plate = rrect(0.034, 0.2, 0.012, n=2)
    mb.plate(plate, 0.003, "steel", m=_T(0, -0.0002, zb + 0.45) @ _Rx(90))
    for zs in (zb + 0.385, zb + 0.515):                                # tapados casi por completo por el cilindro
        screw_lo(mb, _T(0, -0.0032, zs) @ _Rx(90), d=0.0085)
    hook = [(0, -0.002, zh - 0.03), (0, -0.012, zh - 0.03), (0, -0.034, zh - 0.026), (0, -0.04, zh - 0.012), (0, -0.038, zh - 0.004)]
    sweep_frame(mb, rr_profile(0.026, 0.003, 0.0012, n=1), fillet(hook, 0.008, 2), "steel", up=(0, 1, 0))
    for sx in (-1, 1):                                                  # pestañas laterales del gancho
        mb.box((sx * 0.013 - 0.0015, -0.03, zh - 0.026), (sx * 0.013 + 0.0015, -0.002, zh - 0.012), "steel", bevel=0.0006, seg=1)
    # --- letrero: placa de 3 mm con esquinas redondeadas, separadores y texto en relieve
    zs = zb + 0.75
    Mp = _T(0, -0.008, zs + 0.06) @ _Rx(90)
    mb.plate(rrect(0.24, 0.12, 0.01, n=2), 0.003, "sign_red", m=Mp @ _T(0, 0, 0.0))
    fr = rrect(0.226, 0.106, 0.006, n=2)                                # filete blanco perimetral
    loop_tube(mb, [tuple(Mp @ Vector((x, y, 0.003))) for (x, y) in fr], 0.0011, seg=4, mat="sign_white")
    text(mb, "FIRE", 0.05, 0.0017, "sign_white", Mp @ _T(0, -0.002, 0.0028), bold=True, res=2, back=False)
    text(mb, "EXTINGUISHER", 0.019, 0.0015, "sign_white", Mp @ _T(0, -0.036, 0.0028), res=1, back=False)
    for sx in (-1, 1):
        mb.cyl((sx * 0.1, -0.0002, zs + 0.06), (sx * 0.1, -0.0082, zs + 0.06), 0.006, seg=8, mat="steel", caps=False)
        lathe(mb, [(0.0, 0.0), (0.0065, 0.0), (0.0065, 0.002), (0.005, 0.0035), (0.0, 0.0038)], seg=8, mat="steel",
              M=_T(sx * 0.1, -0.011, zs + 0.06) @ _Rx(90))
    return mb


# ======================================================================================================== cilindros
def loop_tube(mb, pts, r, seg=6, mat="steel", normal=None):
    """Alambre cerrado (eslabón, argolla, aro) barrido a lo largo de un lazo PLANO de puntos (sin repetir el primero)."""
    P = [Vector(p) for p in pts]
    n = len(P)
    if normal is None:
        c = sum(P, Vector()) / n
        N = (P[0] - c).cross(P[n // 4] - c).normalized()
    else:
        N = Vector(normal).normalized()
    rings = []
    for i in range(n):
        T = (P[(i + 1) % n] - P[i - 1]).normalized()
        B = T.cross(N).normalized()
        rings.append([P[i] + (N * math.cos(2 * PI * k / seg) + B * math.sin(2 * PI * k / seg)) * r for k in range(seg)])
    R = [[mb.bm.verts.new(p) for p in ring] for ring in rings]
    for i in range(n):
        A, B_ = R[i], R[(i + 1) % n]
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([A[k], A[kk], B_[kk], B_[k]], mat)


def chain(mb, pts, link=0.04, wire=0.0035, mat="steel", r=None):
    """Cadena de eslabones alternados (90°) repartidos a paso constante por longitud de arco a lo largo de una polilínea
    (sin amontonarse en las curvas); eslabón = estadio cerrado de alambre redondo."""
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

    for k in range(n):
        a_, b_ = at(k * step), at((k + 1) * step)
        c = (a_ + b_) / 2
        d = (b_ - a_).normalized()
        M, _ = port.frame_on(c - d * link / 2, c + d * link / 2, up=(0, 0, 1) if abs(d.z) < 0.9 else (1, 0, 0))
        M = M @ _Rx(90 * (k % 2) + (float(r.uniform(-10, 10)) if r is not None else 0.0))
        hw = link * 0.3
        path = []
        for q in range(4):
            ang = -PI / 2 + PI * q / 3
            path.append(M @ Vector((link - hw + hw * math.cos(ang), hw * math.sin(ang), 0)))
        for q in range(4):
            ang = PI / 2 + PI * q / 3
            path.append(M @ Vector((hw + hw * math.cos(ang), hw * math.sin(ang), 0)))
        loop_tube(mb, path, wire, seg=4, mat=mat, normal=M.to_3x3() @ Vector((0, 0, 1)))


def rtube_lo(mb, p0, p1, w, h, mat, up=(0, 0, 1), r=0.004, n=2, caps=True):
    """PTR de esquinas redondeadas como kit.clinic.rtube pero con n segmentos por esquina (n=2 basta a > 0,5 m)."""
    M, L = port.frame_on(p0, p1, up)
    prof = rr_profile(w, h, r, n=n)
    rings = [[Vector((x, py, pz)) for (py, pz) in prof] for x in (0.0, L)]
    loft_rings(mb, rings, mat, M=M, cap0=caps, cap1=caps)


def weld(mb, M, r, w=0.004, seg=12, mat="steel"):
    """Cordón de soldadura perimetral (anillo de sección redonda) alrededor de un tubo de radio r, en el plano z = 0 local."""
    revolve(mb, [(r - 0.0005, -w), (r + w * 0.45, -w * 0.4), (r + w * 0.55, 0.0), (r + w * 0.45, w * 0.4), (r - 0.0005, w)], mat,
            seg=seg, M=M, closed=True)


def _o2_valve(mb, M, cap=False, outlet=True):
    """Válvula de cilindro (latón cromado): cuerpo, salida al frente (-Y) con niple roscado, disco de seguridad, vástago y volante
    moleteado. Local: z = 0 en la boca del cuello."""
    revolve(mb, [(0.017, -0.01), (0.017, 0.006)], "aluminium", seg=12, M=M, caps=False)        # espiga (extremos ocultos)
    mb.box(M @ Vector((-0.0215, -0.019, 0.006)), M @ Vector((0.0215, 0.019, 0.062)), "aluminium", bevel=0.005, seg=2)
    revolve(mb, [(0.0, 0.062), (0.012, 0.062), (0.012, 0.074), (0.009, 0.077), (0.0, 0.077)], "aluminium", seg=6, M=M,
            phase=PI / 6)                                                                     # tuerca del bonete
    if not cap:                                       # bajo el capuchón el volante y el vástago quedan dentro del domo
        mb.cyl(M @ Vector((0, 0, 0.077)), M @ Vector((0, 0, 0.088)), 0.005, seg=8, mat="steel", caps=False)
        wheel = lambda a: 1.0 + 0.06 * max(0.0, math.cos(12 * a)) ** 3
        revolve(mb, [(0.0, 0.086), (0.026, 0.086), (0.029, 0.089), (0.029, 0.097), (0.026, 0.1), (0.0, 0.101)], "cable",
                seg=36, M=M, rmod=wheel)
        hexnut(mb, M @ _T(0, 0, 0.101), d=0.006, washer=False)
    if outlet:                                                                                # niple de salida al frente
        Mo = M @ _T(0, -0.019, 0.034) @ _Rx(90)
        revolve(mb, [(0.0125, -0.001), (0.0125, 0.008)] + [(0.0118 if k % 2 else 0.0128, 0.008 + 0.0045 * k) for k in range(1, 4)]
                + [(0.0105, 0.026), (0.0, 0.026)], "aluminium", seg=12, M=Mo)
        revolve(mb, [(0.0, 0.026), (0.004, 0.026), (0.004, 0.0262), (0.0, 0.0262)], "cable", seg=8, M=Mo)
    hexnut(mb, M @ _T(0.0215, 0, 0.03) @ _Ry(90), d=0.0085, h=0.008, washer=False)            # disco de ruptura
    revolve(mb, [(0.0, 0.0), (0.004, 0.0), (0.004, 0.012), (0.0, 0.012)], "aluminium", seg=8, M=M @ _T(0.029, 0, 0.03) @ _Ry(90))


def _o2_cap(mb, M, h=0.15):
    """Capuchón ventilado (tulipán) roscado al collarín: anillo, 3 postes con ventanas, domo con canto rolado."""
    revolve(mb, [(0.0405, 0.0), (0.047, 0.0), (0.047, 0.024), (0.0405, 0.024)], "steel", seg=16, M=M, closed=True)
    zd = h - 0.038
    for k in range(3):
        a = math.radians(-30 + 120 * k)
        arc_solid(mb, 0.0435, 0.047, 0.0238, zd + 0.0002, a - math.radians(30), a + math.radians(30), 4, "steel", M=M)
    revolve(mb, [(0.0435, zd), (0.047, zd), (0.0475, zd + 0.004), (0.046, zd + 0.016), (0.04, zd + 0.028), (0.026, zd + 0.0355),
                 (0.0, zd + 0.038), (0.0, zd + 0.035), (0.03, zd + 0.03), (0.0435, zd + 0.013)], "steel",
            seg=16, M=M, closed=True)


def _o2_regulator(mb, M, rr):
    """Regulador con flujómetro de tubo Thorpe y vaso humidificador. Local: origen en la punta del niple de salida, -Y hacia
    afuera. Tuerca CGA, cuerpo del regulador, manómetro de contenido al frente, flujómetro vertical con perilla, humidificador
    roscado y manguera de oxígeno colgando."""
    Mo = M @ _Rx(90)
    revolve(mb, [(0.0, -0.006), (0.0155, -0.006), (0.0155, 0.012), (0.0, 0.012)], "aluminium", seg=6, M=Mo, phase=PI / 6)  # tuerca
    revolve(mb, [(0.0, 0.012), (0.024, 0.012), (0.026, 0.016), (0.026, 0.05), (0.024, 0.054), (0.0, 0.054)], "aluminium", seg=16, M=Mo)
    revolve(mb, [(0.0, 0.054), (0.009, 0.054), (0.009, 0.06), (0.0, 0.06)], "aluminium", seg=8, M=Mo)
    gauge(mb, M @ _T(0, -0.06, 0.0) @ _Rx(90), r=0.022, depth=0.014)
    # flujómetro sobre el regulador
    zf = 0.024
    Mf = M @ _T(0, -0.034, zf)
    revolve(mb, [(0.014, 0.0), (0.014, 0.018), (0.011, 0.022), (0.0, 0.022)], "aluminium", seg=12, M=Mf)
    revolve(mb, [(0.0125, 0.022), (0.0125, 0.112)], "glass", seg=12, M=Mf, caps=False)
    revolve(mb, [(0.0, 0.0), (0.0035, 0.0), (0.0035, 0.004), (0.0, 0.004)], "sign_green", seg=8, M=Mf @ _T(0, -0.0128, 0.06))
    for z in (0.04, 0.056, 0.072, 0.088):                                                      # escala grabada (en relieve)
        mb.box((-0.004, -0.0132, z), (0.004, -0.0122, z + 0.0012), "sign_white", bevel=0.0, m=Mf)
    revolve(mb, [(0.0, 0.112), (0.0135, 0.112), (0.0135, 0.126), (0.011, 0.13), (0.0, 0.13)], "aluminium", seg=12, M=Mf)
    knob = lambda a: 1.0 + 0.08 * max(0.0, math.cos(10 * a)) ** 2
    revolve(mb, [(0.0105, 0.1294), (0.0125, 0.134), (0.0125, 0.145), (0.009, 0.149), (0.0, 0.149)], "sign_green", seg=30,
            M=Mf, rmod=knob)
    # salida lateral con espiga y humidificador
    Mh = Mf @ _T(0.014, 0, 0.012) @ _Ry(90)
    revolve(mb, [(0.006, 0.0), (0.006, 0.022)], "aluminium", seg=8, M=Mh, caps=False)
    Mb = Mf @ _T(0.05, 0, 0.012)
    revolve(mb, [(0.0, 0.0), (0.02, 0.0), (0.021, -0.004), (0.021, -0.018), (0.02, -0.02), (0.0, -0.02)], "sign_white", seg=24,
            M=Mb, rmod=lambda a: 1.0 + 0.03 * (math.cos(12 * a) > 0.5))                       # tapa estriada
    revolve(mb, [(0.019, -0.02), (0.0205, -0.026), (0.0205, -0.11), (0.018, -0.118), (0.0, -0.12)], "plastic", seg=16, M=Mb)
    for z in (-0.04, -0.06, -0.08):                                                            # marcas de nivel
        arc_solid(mb, 0.0203, 0.0213, z, z + 0.0014, -PI / 2 - 0.4, -PI / 2 + 0.4, 3, "sign_blue", M=Mb)
    revolve(mb, [(0.0045, 0.0), (0.0045, 0.014), (0.003, 0.016), (0.0, 0.016)], "sign_white", seg=8,
            M=Mb @ _T(0.019, 0, -0.008) @ _Ry(90))
    p0 = Mb @ Vector((0.033, 0, -0.008))
    tub = [p0, p0 + Vector((0.02, -0.01, -0.03)), p0 + Vector((0.03, -0.04, -0.2)), p0 + Vector((0.015, -0.05, -0.4)),
           p0 + Vector((-0.02, -0.035, -0.43)), p0 + Vector((-0.05, -0.02, -0.38))]
    hose(mb, [tuple(p) for p in tub], 0.0028, mat="sign_green", seg=5, rad=0.05, nseg=3)


def _o2_cylinder(mb, x, z0, cap, reg, rr):
    """Cilindro de oxígeno medicinal (Ø 230 × 1,33 m): pie embutido, cuerpo verde, hombro blanco, collarín roscado, válvula,
    etiqueta con letras en relieve y marbete de estado colgado del cuello."""
    M = _T(x, 0, z0)
    R = 0.115
    zs = 1.13
    prof = [(0.108, 0.0), (0.113, 0.006), (R, 0.02), (R, zs), (0.1145, zs + 0.015),                # fondo dentro del aro
            (0.112, zs + 0.035), (0.106, zs + 0.06), (0.096, zs + 0.082), (0.082, zs + 0.102), (0.065, zs + 0.117),
            (0.048, zs + 0.126), (0.034, zs + 0.13), (0.031, zs + 0.132), (0.031, zs + 0.135)]  # boca tapada por la válvula
    mats = ["sign_green"] * 3 + ["sign_white"] * 10
    revolve(mb, prof, mats, seg=24, M=M)
    zn = zs + 0.133
    thr = [(0.0375 + (0.0012 if k % 2 else 0.0), zn + 0.006 + 0.0055 * k) for k in range(4)]
    revolve(mb, [(0.0425, zn), (0.0425, zn + 0.004)] + [(p[0] + 0.004, p[1]) for p in thr] +
            [(0.0405, zn + 0.03), (0.0305, zn + 0.03)], "steel", seg=16, M=M)                        # collarín roscado
    _o2_valve(mb, M @ _T(0, 0, zn + 0.03), cap=cap, outlet=True)
    if cap:
        _o2_cap(mb, M @ _T(0, 0, zn + 0.004))
    if reg:
        _o2_regulator(mb, M @ _T(0, -0.045, zn + 0.064), rr)
    # etiqueta frontal (1,3 mm) con texto
    arc_solid(mb, R - 0.0006, R + 0.0013, 0.82, 1.04, -PI / 2 - 0.62, -PI / 2 + 0.62, 14, "sign_white", M=M)
    text_cyl(mb, "O2", 0.085, 0.0018, "sign_green", R + 0.0011, 0.96, M=M, bold=True, res=2, back=False)
    text_cyl(mb, "MEDICAL OXYGEN", 0.017, 0.0015, "cable", R + 0.0011, 0.865, M=M, res=2, back=False)
    # marbete de estado: argolla en el cuello, alambre y tarjeta de plástico apoyada en el hombro (sigue la curvatura)
    zt = zn - 0.003
    ring = [(x + 0.0325 * math.cos(a), 0.0325 * math.sin(a), z0 + zt + 0.0012 * math.sin(3 * a)) for a in [2 * PI * k / 10 for k in range(10)]]
    loop_tube(mb, ring, 0.0012, seg=4, mat="steel", normal=(0, 0, 1))
    shp = [(R, zs), (0.1145, zs + 0.015), (0.112, zs + 0.035), (0.106, zs + 0.06), (0.096, zs + 0.082), (0.082, zs + 0.102),
           (0.065, zs + 0.117), (0.048, zs + 0.126)]
    acc = [0.0]
    for i in range(1, len(shp)):
        acc.append(acc[-1] + math.hypot(shp[i][0] - shp[i - 1][0], shp[i][1] - shp[i - 1][1]))
    s_c = acc[4] + 0.6 * (acc[5] - acc[4])                         # centro de la tarjeta (r ≈ 0,088)
    ang0 = -PI / 2 + 0.25

    def wrap(u, v, w):
        sv = s_c + v
        i = max(1, min(len(acc) - 1, next((k for k in range(1, len(acc)) if acc[k] >= sv), len(acc) - 1)))
        t = (sv - acc[i - 1]) / (acc[i] - acc[i - 1])
        (r0_, z0_), (r1_, z1_) = shp[i - 1], shp[i]
        tr, tz = (r1_ - r0_), (z1_ - z0_)
        ln = math.hypot(tr, tz)
        tr, tz = tr / ln, tz / ln
        rr_ = r0_ + (r1_ - r0_) * t + (w + 0.0003) * tz
        zz = z0 + z0_ + (z1_ - z0_) * t - (w + 0.0003) * tr
        a = ang0 + u / rr_
        return Vector((x + rr_ * math.cos(a), rr_ * math.sin(a), zz))

    tmp = MB()
    tmp.box((-0.0215, -0.03, 0.0), (0.0215, 0.03, 0.0012), "paint_yellow", bevel=0.0)
    bmesh_subdiv(tmp, 2)
    text(tmp, "IN USE" if reg else "FULL", 0.0095, 0.0006, "cable", _T(0, -0.008, 0.0011), bold=True, res=1, back=False)
    for v in tmp.bm.verts:
        v.co = wrap(*v.co)
    mb.join(tmp)
    loop_tube(mb, [tuple(wrap(0.0045 * math.cos(a), 0.024 + 0.0045 * math.sin(a), 0.0016)) for a in [2 * PI * k / 6 for k in range(6)]],
              0.0009, seg=4, mat="steel")
    p1 = wrap(0.0, 0.0285, 0.0016)
    p0 = Vector((x + 0.0325 * math.cos(ang0), 0.0325 * math.sin(ang0), z0 + zt))
    mb.tube([tuple(p0), tuple(p0.lerp(p1, 0.5) + Vector((0, 0, 0.004))), tuple(p1)], 0.0008, seg=4, mat="steel")


def _lp_tank(mb, x, y, rr, mat):
    """Tanque de gas LP de 30 kg (Ø 0,36 × 1,18 m): base de anillo con escotaduras, cabezas elípticas, cordón de soldadura
    circunferencial, collarín protector con 3 asas, válvula POL con volante y salida lateral, letras troqueladas."""
    M = _T(x, y, 0.0) @ _Rz(float(rr.uniform(-25, 25)))
    R = 0.178
    # base: anillo de lámina con 3 escotaduras (arcos)
    for k in range(3):
        a = 2 * PI * k / 3
        arc_solid(mb, 0.142, 0.147, 0.0015, 0.07, a + 0.22, a + 2 * PI / 3 - 0.22, 6, mat, M=M)
        arc_solid(mb, 0.1423, 0.1467, 0.045, 0.0698, a - 0.23, a + 0.23, 2, mat, M=M)
    revolve(mb, [(0.138, 0.0), (0.151, 0.0), (0.151, 0.003), (0.138, 0.003)], mat, seg=24, M=M, closed=True)
    prof = [(0.128, 0.066), (0.16, 0.088), (0.173, 0.108), (R, 0.135), (R, 0.55)]                 # cabeza inferior dentro de la base
    prof += [(R + 0.0035, 0.556), (R + 0.0035, 0.564), (R, 0.57)]                                # cordón de soldadura
    prof += [(R, 0.98), (0.173, 1.006), (0.16, 1.027), (0.135, 1.045), (0.09, 1.058), (0.04, 1.064), (0.0, 1.065)]
    revolve(mb, prof, mat, seg=24, M=M)
    # collarín protector con 3 asas (ventanas) y canto rolado
    zc0, zc1 = 1.035, 1.2
    revolve(mb, [(0.112, zc0), (0.117, zc0), (0.117, zc0 + 0.06), (0.112, zc0 + 0.06)], mat, seg=24, M=M, closed=True)
    for k in range(3):
        a = 2 * PI * k / 3 + PI / 2
        arc_solid(mb, 0.112, 0.117, zc0 + 0.0598, zc1 - 0.0, a - 0.5, a + 0.5, 4, mat, M=M)
        arc_solid(mb, 0.1123, 0.1167, zc1 - 0.035, zc1 - 0.0002, a + 0.49, a + 2 * PI / 3 - 0.49, 4, mat, M=M)
    revolve(mb, [(0.112, zc1 - 0.0002), (0.117, zc1 - 0.0002), (0.121, zc1 + 0.004), (0.119, zc1 + 0.009), (0.112, zc1 + 0.006)], mat,
            seg=24, M=M, closed=True)
    # válvula POL: cuerpo, volante de latón y salida lateral con rosca izquierda
    revolve(mb, [(0.0, 1.06), (0.022, 1.06), (0.022, 1.075), (0.017, 1.08), (0.017, 1.13), (0.012, 1.135), (0.0, 1.135)],
            "aluminium", seg=6, M=M, phase=PI / 6)
    mb.cyl(M @ Vector((0, 0, 1.135)), M @ Vector((0, 0, 1.152)), 0.005, seg=6, mat="steel", caps=False)
    wheel = lambda a: 1.0 + 0.07 * max(0.0, math.cos(10 * a)) ** 2
    revolve(mb, [(0.0, 1.148), (0.034, 1.148), (0.036, 1.153), (0.033, 1.163), (0.0, 1.166)],
            "aluminium", seg=30, M=M, rmod=wheel)
    Mo = M @ _T(0.017, 0, 1.105) @ _Ry(90)
    revolve(mb, [(0.011, -0.001), (0.011, 0.012)] + [(0.0095 if k % 2 else 0.0108, 0.012 + 0.004 * k) for k in range(1, 4)]
            + [(0.0, 0.028)], "aluminium", seg=10, M=Mo)
    # letras troqueladas en relieve (sin cara trasera: van embutidas en el cuerpo)
    text_cyl(mb, "LP GAS", 0.07, 0.0019, mat, R - 0.0002, 0.72, ang=-PI / 2 - math.radians(float(rr.uniform(-10, 10))), M=M, bold=True,
             res=2, back=False)
    text_cyl(mb, "30 KG", 0.045, 0.0019, mat, R - 0.0002, 0.64, ang=-PI / 2, M=M, bold=True, res=2, back=False)
    return M


def cylinder_rack(n=2, seed=0, medical=True):
    """medical=True: cilindros de oxígeno medicinal (n) en portacilindros de piso: bastidor de PTR soldado con cartelas, plataforma
    de lámina, aros de contención, 2 postes con arco superior, travesaños con cunas, cadena con armella y gancho, cordones de
    soldadura; el primero lleva regulador con flujómetro y humidificador, los demás capuchón ventilado.
    medical=False: tanques de gas LP de 30 kg (patio de servicio) sobre bastidor de ángulo con 2 postes, cadena, colas de
    cochino a un múltiple con regulador y tubo de cobre que baja al firme. Origen: piso, centro; frente -Y."""
    r = rng(seed)
    mb = MB()
    if not medical:
        return _lp_rack(mb, n, r)
    pitch = 0.27
    xs = [(k - (n - 1) / 2) * pitch for k in range(n)]
    X = xs[-1] + 0.145
    Y = 0.14
    zt = 0.045
    # bastidor de piso: PTR 40×30, cartelas en esquinas, regatones de hule
    for (a, b) in (((-X, -Y), (X, -Y)), ((-X, Y), (X, Y))):
        rtube_lo(mb, (a[0], a[1], 0.0275), (b[0], b[1], 0.0275), 0.03, 0.035, "steel", up=(0, 0, 1), r=0.004)
    for x in [-X + 0.015, X - 0.015] + [(xs[k] + xs[k + 1]) / 2 for k in range(n - 1)]:
        rtube_lo(mb, (x, -Y + 0.012, 0.0275), (x, Y - 0.012, 0.0275), 0.03, 0.033, "steel", up=(0, 0, 1), r=0.004,
                 caps=False)                                         # extremos metidos 3 mm en los largueros
    mb.box((-X + 0.004, -Y + 0.004, zt - 0.0002), (X - 0.004, Y - 0.004, zt + 0.004), "steel", bevel=0.0015)
    for sx in (-1, 1):
        for sy in (-1, 1):
            lathe(mb, [(0.02, -0.0003), (0.021, 0.006), (0.019, 0.01), (0.0, 0.01)], seg=6, mat="rubber",
                  M=_T(sx * (X - 0.02), sy * (Y - 0.02), 0.0))
    for x in xs:                                                         # aros de contención soldados a la plataforma
        revolve(mb, [(0.121, zt + 0.004), (0.126, zt + 0.004), (0.126, zt + 0.055), (0.121, zt + 0.055)],
                "steel", seg=20, M=_T(x, 0, 0), closed=True)
    # postes y arco superior (tubo Ø 32 doblado), travesaños con cunas y soldaduras
    yp = 0.125
    xp = X - 0.035
    zt2 = 1.17
    mb.tube(fillet([(-xp, yp, zt + 0.002), (-xp, yp, zt2), (xp, yp, zt2), (xp, yp, zt + 0.002)], 0.08, 6), 0.016, seg=10, mat="steel")
    for sx in (-1, 1):
        weld(mb, _T(sx * xp, yp, zt + 0.004), 0.016, w=0.004, seg=10)
        port.gusset(mb, _T(sx * xp, yp - 0.016, zt + 0.004) @ _Rz(-90), 0.07, 0.09, t=0.004, mat="steel", chamfer=0.015)
    for zr in (0.3, 1.0):
        mb.tube([(-xp + 0.012, yp, zr), (xp - 0.012, yp, zr)], 0.0125, seg=10, mat="steel", caps=False)   # extremos en los postes
        for x in xs:                                                     # cuna de solera rolada detrás de cada cilindro
            arc_solid(mb, 0.1205, 0.1245, zr - 0.02, zr + 0.02, math.radians(28), math.radians(152), 6, "steel", M=_T(x, 0, 0))
            mb.box((x - 0.012, 0.118, zr - 0.012), (x + 0.012, yp - 0.006, zr + 0.012), "steel", bevel=0.003, seg=1)
    # cadena frontal con armella y gancho
    zc = 1.02
    for sx in (-1, 1):
        mb.cyl((sx * xp, yp - 0.014, zc), (sx * (xp + 0.004), yp - 0.034, zc), 0.004, seg=6, mat="steel")
        ring = [(sx * (xp + 0.006) + 0.0, yp - 0.042 + 0.009 * math.cos(a), zc + 0.009 * math.sin(a)) for a in [2 * PI * k / 8 for k in range(8)]]
        loop_tube(mb, ring, 0.0025, seg=5, mat="steel", normal=(1, 0, 0))
    cpts = [(-xp - 0.006, yp - 0.05, zc), (-X + 0.0, -0.06, zc - 0.01), (xs[0] - 0.05, -0.128, zc - 0.015)]
    cpts += [(x, -0.126 if k % 2 == 0 else -0.124, zc - 0.035) for k, x in enumerate(xs)]
    cpts += [(xs[-1] + 0.05, -0.128, zc - 0.015), (X - 0.0, -0.06, zc - 0.01), (xp + 0.006, yp - 0.05, zc)]
    chain(mb, fillet(cpts, 0.05, 3), link=0.064, wire=0.0042, mat="steel", r=r)
    # cilindros
    for k, x in enumerate(xs):
        reg = (k == 0)
        _o2_cylinder(mb, x, zt + 0.004, cap=not reg, reg=reg, rr=r)
    return mb


def angle_l(mb, p0, p1, leg, t, up=(0, 0, 1), s=1, mat="steel", rf=0.003):
    """Ángulo de lados iguales (perfil L de una pieza con filete interior) de p0 a p1; un ala hacia `up`, la otra hacia el
    costado (s = ±1 respecto de tangente × up)."""
    prof = [(0.0, 0.0), (s * leg, 0.0), (s * leg, t), (s * (t + rf), t), (s * (t + rf * 0.3), t + rf * 0.3), (s * t, t + rf),
            (s * t, leg), (0.0, leg)]
    sweep_frame(mb, prof, [p0, p1], mat, up=up)


def _lp_rack(mb, n, r):
    pitch = 0.37
    xs = [(k - (n - 1) / 2) * pitch for k in range(n)]
    X = xs[-1] + 0.19
    # bastidor de ángulo 1 1/2" con travesaños y placas de anclaje
    for y in (-0.162, 0.162):
        angle_l(mb, (-X, y, 0.0), (X, y, 0.0), 0.038, 0.004, up=(0, 0, 1), s=-1 if y > 0 else 1)
    for x in [-X + 0.02, X - 0.02] + [(xs[k] + xs[k + 1]) / 2 for k in range(n - 1)]:
        angle_l(mb, (x, -0.16, 0.0005), (x, 0.16, 0.0005), 0.036, 0.004, up=(0, 0, 1), s=1 if x > 0.3 else -1)
    Ms = []
    for k, x in enumerate(xs):
        mat = "paint_white" if r.uniform() < 0.65 else "steel"
        Ms.append(_lp_tank(mb, x, 0.0, r, mat))
    # postes traseros de ángulo, travesaño superior y múltiple
    yb = 0.235
    zt = 1.34
    for sx in (-1, 1):
        angle_l(mb, (sx * (X - 0.03), yb, 0.0045), (sx * (X - 0.03), yb, zt), 0.04, 0.004, up=(0, -1, 0), s=-1)
        mb.box((sx * (X - 0.03) - 0.05, yb - 0.05, 0.0), (sx * (X - 0.03) + 0.05, yb + 0.05, 0.006), "steel", bevel=0.002, seg=1)
        for (dx, dy) in ((-0.03, -0.03), (0.03, 0.03)):
            hexnut(mb, _T(sx * (X - 0.03) + dx, yb + dy, 0.006), d=0.009, washer=False)
        rtube_lo(mb, (sx * (X - 0.03), yb - 0.004, 0.05), (sx * (X - 0.03), 0.15, 0.05), 0.03, 0.03, "steel", up=(0, 0, 1), r=0.003)
    angle_l(mb, (-X + 0.03, yb, zt - 0.04), (X - 0.03, yb, zt - 0.04), 0.04, 0.004, up=(0, 0, 1), s=-1)
    zm = zt - 0.09
    ym = yb - 0.02
    mb.cyl((-X + 0.08, ym, zm), (X - 0.12, ym, zm), 0.0135, seg=10, mat="steel")               # múltiple de 1/2"
    for x in (-X + 0.12, X - 0.16):                                                              # abrazaderas en U
        mb.tube(fillet([(x, ym + 0.02, zm + 0.0), (x, ym + 0.02, zm + 0.017), (x, ym - 0.017, zm + 0.017), (x, ym - 0.017, zm - 0.03),
                        (x, ym + 0.02, zm - 0.03)], 0.012, 2), 0.003, seg=5, mat="steel")
    revolve(mb, [(0.0, 0.0), (0.015, 0.0), (0.015, 0.012), (0.0, 0.012)], "steel", seg=6, M=_T(-X + 0.08, ym, zm) @ _Ry(-90))
    for k, x in enumerate(xs):                                                                   # tes y colas de cochino
        hexnut(mb, _T(x, ym, zm - 0.0135) @ _Rx(180), d=0.012, h=0.014, washer=False)
        Mt = Ms[k]
        revolve(mb, [(0.0, 0.0), (0.0095, 0.0), (0.0095, 0.022), (0.0, 0.022)], "aluminium", seg=6, M=Mt @ _T(0.067, 0, 1.105) @ _Ry(-90),
                phase=PI / 6)                                                                    # tuerca POL
        loc = [Vector((0.066, 0.0, 1.105)), Vector((0.084, 0.0, 1.11)), Vector((0.088, 0.0, 1.16)), Vector((0.07, 0.03, 1.235))]
        pts = [Mt @ p for p in loc] + [Vector((x + 0.02, ym - 0.03, zm - 0.06)), Vector((x, ym, zm - 0.04)), Vector((x, ym, zm - 0.024))]
        hose(mb, [tuple(p) for p in pts], 0.0065, mat="rubber", seg=8, rad=0.03, nseg=3)
        mb.cyl(tuple(Mt @ Vector((0.064, 0, 1.105))), tuple(Mt @ Vector((0.074, 0, 1.105))), 0.0075, seg=8, mat="aluminium")
    # regulador de baja presión (campana con venteo) y tubo de cobre al firme
    xr = X - 0.12
    Mr = _T(xr + 0.03, ym, zm)
    revolve(mb, [(0.0, -0.03), (0.04, -0.03), (0.046, -0.02), (0.046, 0.0), (0.035, 0.012), (0.0, 0.016)], "paint_white", seg=20,
            M=Mr @ _Rx(-90))
    revolve(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.008), (0.0, 0.008)], "paint_white", seg=20, M=Mr @ _T(0, 0.03, 0) @ _Rx(-90))
    hexnut(mb, Mr @ _T(0, -0.016, 0.046), d=0.008, washer=False)
    revolve(mb, [(0.0, 0.0), (0.008, 0.0), (0.008, 0.012), (0.0, 0.014)], "cable", seg=10, M=Mr @ _T(0, -0.016, 0.046 + 0.006))
    cu = [(xr + 0.03, ym, zm - 0.046), (xr + 0.03, ym, 0.12), (xr + 0.03, ym + 0.05, 0.08), (xr + 0.03, ym + 0.05, -0.03)]
    hose(mb, cu, 0.0065, mat="steel", seg=8, rad=0.04, nseg=4)
    for z in (0.35, 0.8):                                                                         # grapas al poste
        mb.box((xr + 0.02, ym - 0.008, z), (X - 0.027, ym + 0.008, z + 0.012), "steel", bevel=0.001, seg=1)
    # cadena al frente de los tanques
    zc = 0.88
    xp = X - 0.03
    cp = [(-xp, yb - 0.02, zc), (-X + 0.0, 0.0, zc - 0.01), (xs[0] - 0.1, -0.188, zc - 0.02)]
    cp += [(x, -0.188, zc - 0.03) for x in xs] + [(xs[-1] + 0.1, -0.188, zc - 0.02), (X, 0.0, zc - 0.01), (xp, yb - 0.02, zc)]
    chain(mb, fillet(cp, 0.08, 3), link=0.064, wire=0.0045, mat="steel", r=r)
    return mb


# ======================================================================================================== rayos X
def _knob(mb, M, r=0.012, h=0.014, mat="cable", flutes=12):
    """Perilla moleteada con faldón y tapa, base en z = 0 local."""
    revolve(mb, [(0.0, 0.0), (r * 1.08, 0.0), (r * 1.08, h * 0.18), (r, h * 0.25), (r, h * 0.85), (r * 0.8, h), (0.0, h)], mat,
            seg=max(20, flutes * 2), M=M, rmod=lambda a: 1.0 + 0.06 * max(0.0, math.cos(flutes * a)) ** 2)


def _panel_seams(mb, x0, x1, y0, y1, z0, z1, axis, side, gap=0.002, mat="sign_white", n=2):
    """Paneles de lámina atornillados sobre una cara plana (axis 'x' o 'y', side ±1): tableros 1,5 mm sobre la cara con holgura
    entre ellos y 4 tornillos cada uno."""
    if axis == "y":
        span = (x0, x1)
    else:
        span = (y0, y1)
    w = (span[1] - span[0]) / n
    for k in range(n):
        a = span[0] + k * w + gap / 2
        b = span[0] + (k + 1) * w - gap / 2
        if axis == "y":
            yf = y0 if side < 0 else y1
            mb.box((a, yf - side * 0.0002 - (0.0015 if side < 0 else 0), z0), (b, yf + (0.0015 if side > 0 else 0) - side * 0.0002, z1), mat,
                   bevel=0.0009, seg=1)
            for (u, v) in ((a + 0.02, z0 + 0.02), (b - 0.02, z0 + 0.02), (a + 0.02, z1 - 0.02), (b - 0.02, z1 - 0.02)):
                screw(mb, _T(u, yf + side * 0.0013, v) @ _Rx(-90 * side), d=0.0065, seg=6, recess=None)
        else:
            xf = x0 if side < 0 else x1
            mb.box((xf - side * 0.0002 - (0.0015 if side < 0 else 0), a, z0), (xf + (0.0015 if side > 0 else 0) - side * 0.0002, b, z1), mat,
                   bevel=0.0009, seg=1)
            for (u, v) in ((a + 0.02, z0 + 0.02), (b - 0.02, z0 + 0.02), (a + 0.02, z1 - 0.02), (b - 0.02, z1 - 0.02)):
                screw(mb, _T(xf + side * 0.0013, u, v) @ _Ry(90 * side), d=0.0065, seg=6, recess=None)


def xray_unit(seed=0):
    """Rayos X convencional de piso, modelo sencillo y con años (en uso): mesa de tablero flotante sobre pedestal de lámina con
    paneles atornillados, zoclo y rejillas, rieles de accesorios en los costados, charola del bucky con jaladera, colchoneta de
    vinilo con vivo, pedal de freno con cable; columna portatubo sobre riel de piso con topes, carro de la columna, pista de
    contrapeso cubierta, carro vertical con rodillos y perilla de freno, brazo telescópico, cabezal (coraza del tubo) con
    tapas, receptáculos de alta tensión y tuercas moleteadas, anillo giratorio, colimador con perillas, botón de luz,
    cinta métrica, ventana de luz con retícula y asas; cables de alta tensión con caída hasta una caja de piso; caja de
    control con botones y llave sobre la columna. Origen: piso, centro de la mesa; columna hacia +X."""
    from kit.clinic import cushion
    r = rng(seed)
    mb = MB()
    # ------------------------------------------------------------------ mesa: pedestal
    rbox(mb, (-0.30, -0.43, 0.0), (0.30, 0.43, 0.06), "steel", r=0.008)                     # zoclo
    rbox(mb, (-0.32, -0.45, 0.055), (0.32, 0.45, 0.585), "sign_white", r=0.028)               # gabinete
    _panel_seams(mb, -0.29, 0.29, -0.45, 0.45, 0.09, 0.56, "y", -1, n=2)
    _panel_seams(mb, -0.29, 0.29, -0.45, 0.45, 0.09, 0.56, "y", 1, n=2)
    _panel_seams(mb, -0.32, 0.32, -0.42, 0.42, 0.09, 0.56, "x", -1, n=2)
    for k in range(9):                                                                        # rejilla de ventilación (+x)
        z = 0.14 + k * 0.022
        mb.box((0.3195, -0.16, z), (0.3225, 0.16, z + 0.011), "cable", bevel=0.0)
        mb.box((0.32, -0.162, z + 0.011), (0.326, 0.162, z + 0.014), "sign_white", bevel=0.001, seg=1)
    rbox(mb, (-0.34, -0.47, 0.585), (0.34, 0.47, 0.605), "steel", r=0.006)                    # placa de apoyo
    # ------------------------------------------------------------------ tablero flotante
    for sx in (-1, 1):                                                                        # largueros de aluminio
        rtube(mb, (sx * 0.355, -1.08, 0.635), (sx * 0.355, 1.08, 0.635), 0.05, 0.05, "aluminium", up=(0, 0, 1), r=0.004)
    for y in (-0.42, 0.42):                                                                   # rodamientos del flotante
        for sx in (-1, 1):
            mb.box((sx * 0.355 - 0.03, y - 0.05, 0.6), (sx * 0.355 + 0.03, y + 0.05, 0.612), "steel", bevel=0.002, seg=1)
    rbox(mb, (-0.39, -1.1, 0.659), (0.39, 1.1, 0.695), "plastic", r=0.012)                    # tablero radiotransparente
    for sx in (-1, 1):                                                                        # rieles de accesorios
        mb.box((sx * 0.4105 - 0.0045, -0.98, 0.662), (sx * 0.4105 + 0.0045, 0.98, 0.688), "steel", bevel=0.0018, seg=2)
        for y in (-0.9, -0.3, 0.3, 0.9):
            xa, xb = sorted((sx * 0.389, sx * 0.406))
            mb.box((xa, y - 0.015, 0.667), (xb, y + 0.015, 0.683), "steel", bevel=0.002, seg=1)
            screw(mb, _T(sx * 0.415, y, 0.675) @ _Ry(90 * sx), d=0.008, seg=8)
        for y in (-0.98, 0.98):
            lathe(mb, [(0.0, -0.002), (0.0068, -0.002), (0.0072, 0.004), (0.0, 0.006)], seg=8, mat="cable",
                  M=_T(sx * 0.4105, y, 0.675) @ _Rx(90 if y < 0 else -90))
    cushion(mb, _T(0, 0.0, 0.695), 0.72, 2.0, 0.045, mat="vinyl", r=0.018, crown=0.006, seg=(18, 8))
    # charola del bucky bajo el tablero, con jaladera al lado -x
    rbox(mb, (-0.3, -0.3, 0.612), (0.3, 0.22, 0.655), "sign_white", r=0.006)
    mb.box((-0.312, -0.06, 0.618), (-0.3, 0.06, 0.65), "plastic", bevel=0.002, seg=1)
    mb.tube(fillet([(-0.312, -0.045, 0.634), (-0.345, -0.045, 0.634), (-0.345, 0.045, 0.634), (-0.312, 0.045, 0.634)], 0.012, 5),
            0.0055, seg=8, mat="steel")
    # pedal de freno del tablero en el piso, con cable a la base
    rbox(mb, (-0.07, -1.25, 0.0), (0.07, -1.11, 0.03), "sign_white", r=0.008)
    for k in range(6):
        y = -1.235 + k * 0.022
        mb.box((-0.06, y, 0.03), (0.06, y + 0.012, 0.038), "rubber", bevel=0.0015, seg=1)
    hose(mb, [(0.0, -1.11, 0.015), (0.03, -1.0, 0.007), (0.08, -0.75, 0.007), (0.1, -0.5, 0.007), (0.1, -0.44, 0.04)], 0.006,
         mat="cable", seg=8, rad=0.05, nseg=4)
    # ------------------------------------------------------------------ riel de piso y columna
    xc = 0.72
    mb.sweep([(-0.055, 0.0), (0.055, 0.0), (0.05, 0.014), (0.016, 0.016), (0.016, 0.024), (-0.016, 0.024), (-0.016, 0.016),
              (-0.05, 0.014)], [(xc, -0.98, 0.0), (xc, 0.98, 0.0)], mat="aluminium", normal=(0, 0, 1))
    for y in (-0.98, 0.98):
        mb.box((xc - 0.04, y - 0.012 if y < 0 else y - 0.01, 0.0), (xc + 0.04, y + 0.01 if y < 0 else y + 0.012, 0.05), "cable",
               bevel=0.004, seg=2)
    for y in (-0.8, -0.4, 0.0, 0.4, 0.8):
        for sx in (-1, 1):
            hexnut(mb, _T(xc + sx * 0.038, y, 0.0135), d=0.0065, washer=False)
    rbox(mb, (xc - 0.08, -0.13, 0.024), (xc + 0.08, 0.13, 0.13), "sign_white", r=0.02)        # carro de la columna
    for sy in (-1, 1):
        mb.box((xc - 0.06, sy * 0.1305 - 0.003, 0.03), (xc + 0.06, sy * 0.1305 + 0.003, 0.09), "rubber", bevel=0.0015, seg=1)  # topes
    mb.tube(fillet([(xc - 0.08, 0.06, 0.1), (xc - 0.13, 0.06, 0.1), (xc - 0.13, 0.0, 0.1)], 0.02, 4), 0.006, seg=8, mat="steel")
    _knob(mb, _T(xc - 0.13, 0.0, 0.1) @ _Ry(-90), r=0.012, h=0.02, mat="sign_red")             # freno del carro
    zc0, zc1 = 0.13, 2.07
    rtube(mb, (xc, 0.0, zc0), (xc, 0.0, zc1), 0.16, 0.12, "sign_white", up=(1, 0, 0), r=0.012)
    rbox(mb, (xc - 0.064, -0.084, zc1 - 0.002), (xc + 0.064, 0.084, 2.1), "sign_white", r=0.012)  # tapa superior
    for sy in (-1, 1):                                                                         # pistas del carro (cara -x)
        mb.box((xc - 0.064, sy * 0.05 - 0.009, 0.16), (xc - 0.058, sy * 0.05 + 0.009, 2.04), "aluminium", bevel=0.002)
    mb.box((xc - 0.0616, -0.03, 0.16), (xc - 0.0592, 0.03, 2.04), "cable", bevel=0.0)        # ranura central (tira de hule)
    mb.box((xc + 0.058, -0.06, 0.2), (xc + 0.0625, 0.06, 1.98), "sign_white", bevel=0.0015, seg=1)   # tapa del contrapeso
    for z in (0.24, 0.7, 1.16, 1.62, 1.94):
        for sy in (-1, 1):
            screw(mb, _T(xc + 0.0625, sy * 0.045, z) @ _Ry(90), d=0.0065, seg=6, recess=None)
    for z in (0.5, 1.3):                                                                        # junta entre tramos de lámina
        mb.sweep([(-0.0004, 0.0), (0.0016, 0.0), (0.0016, 0.0016), (-0.0004, 0.0016)],
                 [(p[0], p[1], z) for p in rrect(0.12, 0.16, 0.012, n=3, cx=xc, z=0.0)], mat="cable", closed_path=True, normal=(0, 0, 1))
    # carro vertical con rodillos, freno y brazo telescópico
    zk = 1.56
    rbox(mb, (xc - 0.1, -0.11, zk), (xc + 0.085, 0.11, zk + 0.24), "sign_white", r=0.025)
    for sy in (-1, 1):
        for z in (zk + 0.04, zk + 0.2):
            Mr = _T(xc + 0.02, sy * 0.11, z) @ _Rx(-90 * sy)
            lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.004), (0.011, 0.007), (0.0, 0.007)], seg=12, mat="steel", M=Mr)
            hexnut(mb, Mr @ _T(0, 0, 0.007), d=0.006, washer=False)
    _knob(mb, _T(xc - 0.01, -0.11, zk + 0.12) @ _Rx(90), r=0.02, h=0.025, mat="cable", flutes=8)
    mb.cyl((xc - 0.01, -0.11, zk + 0.12), (xc - 0.01, -0.118, zk + 0.12), 0.006, seg=8, mat="steel")
    za = zk + 0.07
    rtube(mb, (xc - 0.1, 0.0, za), (0.2, 0.0, za), 0.11, 0.1, "sign_white", up=(0, 0, 1), r=0.012)   # brazo exterior
    mb.box((0.19, -0.058, za - 0.053), (0.215, 0.058, za + 0.053), "sign_white", bevel=0.005, seg=2)  # boca del brazo
    rtube(mb, (0.21, 0.0, za), (0.03, 0.0, za), 0.09, 0.08, "aluminium", up=(0, 0, 1), r=0.008)      # brazo interior
    _knob(mb, _T(0.3, 0.0, za + 0.05), r=0.018, h=0.022, mat="cable", flutes=8)               # freno del brazo
    # ------------------------------------------------------------------ cabezal: yugo, coraza del tubo, colimador
    zt = 1.47
    rbox(mb, (-0.022, -0.062, za - 0.046), (0.062, 0.062, za + 0.047), "sign_white", r=0.01)  # yugo
    revolve(mb, [(0.0, 0.0), (0.05, 0.0), (0.05, 0.03), (0.045, 0.034), (0.0, 0.034)], "sign_white", seg=28,
            M=_T(0.0, 0.0, za - 0.074))                                                         # pivote giratorio
    for k in range(12):                                                                         # escala de ángulo
        a = 2 * PI * k / 12
        mb.box((-0.0006, 0.049, 0.008), (0.0006, 0.0515, 0.024 if k % 3 == 0 else 0.016), "cable", bevel=0.0,
               m=_T(0, 0, za - 0.074) @ Matrix.Rotation(a, 4, "Z"))
    for sy in (-1, 1):                                                                          # abrazaderas de la coraza
        revolve(mb, [(0.0838, -0.025), (0.093, -0.025), (0.093, 0.025), (0.0838, 0.025)], "sign_white", seg=32,
                M=_T(0, sy * 0.1, zt) @ _Rx(90), closed=True)
        for sx in (-1, 1):                                                                      # tornillos de cierre
            screw(mb, _T(sx * 0.093, sy * 0.1, zt) @ _Ry(90 * sx), d=0.008, seg=8)
    rbox(mb, (-0.03, -0.105, zt + 0.0775), (0.03, 0.105, zt + 0.097), "sign_white", r=0.006)  # silla sobre la coraza
    hous = [(0.0, -0.215), (0.03, -0.214), (0.055, -0.209), (0.07, -0.2), (0.08, -0.188), (0.085, -0.17), (0.085, -0.163),
            (0.0835, -0.161), (0.0835, -0.157), (0.085, -0.155), (0.085, 0.155), (0.0835, 0.157), (0.0835, 0.161), (0.085, 0.163),
            (0.085, 0.17), (0.08, 0.188), (0.07, 0.2), (0.055, 0.209), (0.03, 0.214), (0.0, 0.215)]
    revolve(mb, hous, "sign_white", seg=32, M=_T(0, 0, zt) @ _Rx(-90))
    cab = []
    for sy in (-1, 1):                                                                          # receptáculos de alta tensión
        Mh = _T(0.0, sy * 0.2, zt + 0.035) @ _Rx(-90 * sy)
        revolve(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.022), (0.0, 0.022)], "sign_white", seg=20, M=Mh)
        revolve(mb, [(0.0, 0.022), (0.031, 0.022), (0.031, 0.044), (0.0, 0.044)], "steel", seg=27, M=Mh,
                rmod=lambda a: 1.0 + 0.05 * max(0.0, math.cos(18 * a)))
        revolve(mb, [(0.0, 0.044), (0.02, 0.044), (0.016, 0.075), (0.013, 0.09), (0.0, 0.09)], "rubber", seg=16, M=Mh)
        cab.append(Mh @ Vector((0, 0, 0.088)))
    # placa de advertencia sobre la coraza, curvada sobre el cilindro y de cara al técnico (-x)
    tmp = MB()
    tmp.box((-0.065, -0.02, -0.0004), (0.065, 0.02, 0.0018), "paint_yellow", bevel=0.0)
    bmesh_subdiv(tmp, 4)
    text(tmp, "CAUTION", 0.018, 0.0015, "cable", _T(0, -0.0075, 0.0016), bold=True, res=2)
    for v in tmp.bm.verts:
        tx, ty, tz = v.co
        phi = ty / 0.085 + 0.35
        rr_ = 0.0846 + tz
        v.co = Vector((-rr_ * math.cos(phi), -tx, zt + rr_ * math.sin(phi)))
    mb.join(tmp)
    # anillo giratorio y colimador
    revolve(mb, [(0.0, 0.0), (0.072, 0.0), (0.072, 0.012), (0.066, 0.016), (0.066, 0.024), (0.0, 0.024)], "steel", seg=32,
            M=_T(0, 0, zt - 0.104))
    zc = 1.24
    rbox(mb, (-0.11, -0.11, zc + 0.006), (0.11, 0.11, zt - 0.1), "sign_white", r=0.018)
    mb.box((-0.104, -0.104, zc), (0.104, 0.104, zc + 0.012), "plastic", bevel=0.004, seg=2)     # marco de la ventana
    mb.box((-0.075, -0.075, zc - 0.0015), (0.075, 0.075, zc + 0.002), "glass", bevel=0.001, seg=1)
    for (a, b) in (((-0.07, -0.0006), (-0.0006, 0.0006)), ((0.0006, -0.0006), (0.07, 0.0006))):     # retícula
        mb.box((a[0], a[1], zc - 0.0032), (b[0], b[1], zc - 0.0012), "cable", bevel=0.0)
    mb.box((-0.0006, -0.07, zc - 0.0032), (0.0006, 0.07, zc - 0.0012), "cable", bevel=0.0)
    for sx in (-1, 1):                                                                          # rieles para filtros
        mb.box((sx * 0.092 - 0.006, -0.1, zc - 0.012), (sx * 0.092 + 0.006, 0.1, zc + 0.001), "steel", bevel=0.002)
    for k, x in enumerate((-0.055, 0.055)):                                                     # perillas de campo
        _knob(mb, _T(x, -0.11, zc + 0.09) @ _Rx(90), r=0.017, h=0.02, mat="cable", flutes=10)
        mb.box((x - 0.0006, -0.1302, zc + 0.104), (x + 0.0006, -0.1295, zc + 0.11), "sign_white", bevel=0.0)
    lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.011, 0.006), (0.009, 0.011), (0.0, 0.012)], seg=16, mat="sign_green",
          M=_T(0.0, -0.11, zc + 0.05) @ _Rx(90))                                                # botón de luz
    mb.box((0.035, -0.114, zc + 0.03), (0.08, -0.108, zc + 0.045), "steel", bevel=0.0015, seg=1)  # cinta métrica
    mb.box((0.04, -0.1156, zc + 0.036), (0.075, -0.1136, zc + 0.039), "cable", bevel=0.0)
    for sx in (-1, 1):                                                                          # asas laterales
        mb.tube(fillet([(sx * 0.11, -0.07, zc + 0.03), (sx * 0.145, -0.07, zc + 0.03), (sx * 0.145, 0.07, zc + 0.03),
                        (sx * 0.11, 0.07, zc + 0.03)], 0.02, 6), 0.009, seg=10, mat="cable")
    # ------------------------------------------------------------------ cables de alta tensión con caída
    for k, (sy, p0) in enumerate(zip((-1, 1), cab)):
        y = sy * 0.03
        sag = 0.02 * k + float(r.uniform(0.0, 0.012))
        pts = [tuple(p0), (0.0, sy * 0.35, zt + 0.06), (0.03, sy * 0.37, za + 0.03), (0.13, sy * 0.27, za + 0.1 - sag),
               (0.36, sy * 0.14, za + 0.075 - sag), (0.56, sy * 0.13, za + 0.16), (xc - 0.03, sy * 0.14, zk + 0.27),
               (xc + 0.106, sy * 0.07, zk + 0.2), (xc + 0.104, y, zk - 0.06), (xc + 0.08, y, zk - 0.32), (xc + 0.075, y, 0.6),
               (xc + 0.072, y, 0.16)]
        hose(mb, pts, 0.011, mat="cable", seg=8, rad=0.07, nseg=4)
    for z in (0.5, 1.0, 1.4):                                                                     # grapas de los cables
        mb.tube([(xc + 0.0625, -0.05, z), (xc + 0.09, -0.05, z), (xc + 0.09, 0.05, z), (xc + 0.0625, 0.05, z)], 0.003, seg=6,
                mat="steel")
    # caja de piso por donde bajan los cables (al generador)
    mb.box((xc + 0.02, -0.07, 0.13), (xc + 0.1, 0.07, 0.15), "steel", bevel=0.003, seg=2)
    # ------------------------------------------------------------------ caja de control en la columna
    rbox(mb, (xc - 0.055, -0.15, 1.12), (xc + 0.055, -0.0798, 1.3), "sign_white", r=0.01)
    mb.box((xc - 0.045, -0.1515, 1.2), (xc + 0.045, -0.149, 1.285), "cable", bevel=0.001)      # carátula
    for k, (z, mat) in enumerate(((1.26, "sign_green"), (1.26, "sign_red"), (1.225, "plastic"))):
        x = xc + (-0.022 + 0.044 * (k % 2)) if k < 2 else xc
        lathe(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.006), (0.007, 0.009), (0.0, 0.0095)], seg=14, mat=mat,
              M=_T(x, -0.151, z) @ _Rx(90))
    lathe(mb, [(0.0, 0.0), (0.008, 0.0), (0.008, 0.004), (0.0, 0.004)], seg=12, mat="steel", M=_T(xc - 0.025, -0.15, 1.16) @ _Rx(90))
    mb.box((xc - 0.0262, -0.1545, 1.157), (xc - 0.0238, -0.15, 1.163), "cable", bevel=0.0)     # llave
    lathe(mb, [(0.0, 0.0), (0.006, 0.0), (0.006, 0.006), (0.0, 0.007)], seg=10, mat="paint_yellow", M=_T(xc + 0.025, -0.15, 1.16) @ _Rx(90))
    hose(mb, [(xc, -0.115, 1.12), (xc, -0.115, 1.06), (xc + 0.0, -0.096, 0.9), (xc, -0.088, 0.4), (xc, -0.088, 0.15)], 0.0055,
         mat="cable", seg=8, rad=0.04, nseg=4)
    for z in (0.35, 0.75):
        mb.box((xc - 0.012, -0.096, z), (xc + 0.012, -0.0798, z + 0.012), "steel", bevel=0.002)
    return mb


# ======================================================================================================== bucky de pared
def wall_bucky():
    """Bucky de pared (estativo de tórax): columna de aluminio pintado sobre placa de piso, sujeta al muro con ménsulas
    atornilladas; 2 pistas frontales y ranura del contrapeso; carro con rodillos y palanca de freno con botón; receptor con
    tapa radiotransparente de canto redondo, retícula de centrado y marcas de campo, 2 asas laterales de tubo, charola de
    chasis con jaladera saliendo por el costado; cable del motor de la rejilla bajando por la columna a una caja en el muro.
    Origen: cara del muro, piso; crece hacia -Y."""
    mb = MB()
    xc, yc = 0.0, -0.055
    # columna y placa de piso
    rtube(mb, (xc, yc, 0.012), (xc, yc, 1.985), 0.17, 0.085, "sign_white", up=(0, 1, 0), r=0.01)
    rbox(mb, (-0.1, yc - 0.05, 1.98), (0.1, yc + 0.045, 2.0), "sign_white", r=0.008)           # tapa superior
    rbox(mb, (-0.13, -0.11, 0.0), (0.13, -0.004, 0.014), "steel", r=0.004)                    # placa de piso
    for sx in (-1, 1):
        hexnut(mb, _T(sx * 0.105, -0.075, 0.014), d=0.0085)
        hexnut(mb, _T(sx * 0.105, -0.03, 0.014), d=0.0085)
    for z in (0.35, 1.75):                                                                       # ménsulas al muro
        mb.box((-0.12, -0.0135, z - 0.045), (0.12, -0.0005, z + 0.045), "steel", bevel=0.003)
        for sx in (-1, 1):
            screw(mb, _T(sx * 0.1, -0.0135, z) @ _Rx(90), d=0.011, seg=10)
    for sx in (-1, 1):
        mb.box((sx * 0.055 - 0.009, yc - 0.0425 - 0.006, 0.08), (sx * 0.055 + 0.009, yc - 0.0425 + 0.0005, 1.94), "aluminium",
               bevel=0.002)
    for (za_, zb_) in ((0.08, 0.5975), (0.6035, 1.4975), (1.5035, 1.94)):                        # ranura del contrapeso
        mb.box((-0.022, yc - 0.0443, za_), (0.022, yc - 0.042, zb_), "cable", bevel=0.0)
    for z in (0.6, 1.5):                                                                         # juntas de lámina
        mb.sweep([(-0.0004, 0.0), (0.0016, 0.0), (0.0016, 0.0016), (-0.0004, 0.0016)],
                 [(p[0], p[1], z) for p in rrect(0.17, 0.085, 0.01, n=3, cy=yc, z=0.0)], mat="cable", closed_path=True, normal=(0, 0, 1))
    # carro con rodillos y freno
    zk = 1.0
    rbox(mb, (-0.125, yc - 0.068, zk), (0.125, yc - 0.0405, zk + 0.36), "sign_white", r=0.012)
    for sx in (-1, 1):
        for z in (zk + 0.05, zk + 0.31):
            M = _T(sx * 0.125, yc - 0.055, z) @ _Ry(90 * sx)
            lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.004), (0.008, 0.007), (0.0, 0.007)], seg=12, mat="steel", M=M)
    pv = Vector((0.125, yc - 0.06, zk + 0.18))
    lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.008), (0.0, 0.008)], seg=12, mat="steel", M=_T(*pv) @ _Ry(90))
    lever = fillet([tuple(pv + Vector((0.006, 0, 0))), tuple(pv + Vector((0.012, -0.03, 0.0))), tuple(pv + Vector((0.016, -0.05, -0.1)))],
                   0.02, 5)
    sweep_frame(mb, rr_profile(0.006, 0.016, 0.0025, n=2), lever, "steel", up=(1, 0, 0))
    lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.012, 0.03), (0.01, 0.045), (0.0, 0.048)], seg=12, mat="sign_red",
          M=_T(*(pv + Vector((0.016, -0.05, -0.1)))) @ _Rx(180) @ _Rx(-10))
    # receptor (bucky)
    yb0, yb1 = yc - 0.068, -0.205
    z0, z1 = 0.9, 1.45
    rbox(mb, (-0.245, yb1 + 0.012, z0), (0.245, yb0, z1), "sign_white", r=0.02)                 # caja
    rbox(mb, (-0.235, yb1, z0 + 0.012), (0.235, yb1 + 0.016, z1 - 0.012), "plastic", r=0.008)    # tapa radiotransparente
    yf = yb1 - 0.0004
    zm = (z0 + z1) / 2
    mb.box((-0.0006, yf - 0.0011, zm - 0.16), (0.0006, yf + 0.0004, zm + 0.16), "cable", bevel=0.0)   # retícula
    for (xa, xb) in ((-0.16, -0.0006), (0.0006, 0.16)):
        mb.box((xa, yf - 0.0011, zm - 0.0006), (xb, yf + 0.0004, zm + 0.0006), "cable", bevel=0.0)
    for (w, h) in ((0.35, 0.43), (0.24, 0.3)):                                                   # marcas de campo
        e = 0.0012
        for (a, b) in (((-w / 2, -h / 2), (-w / 2 + 0.03, -h / 2 + e)), ((w / 2 - 0.03, -h / 2), (w / 2, -h / 2 + e)),
                       ((-w / 2, h / 2 - e), (-w / 2 + 0.03, h / 2)), ((w / 2 - 0.03, h / 2 - e), (w / 2, h / 2)),
                       ((-w / 2, -h / 2 + e + 0.0003), (-w / 2 + e, -h / 2 + 0.03)), ((w / 2 - e, -h / 2 + e + 0.0003), (w / 2, -h / 2 + 0.03)),
                       ((-w / 2, h / 2 - 0.03), (-w / 2 + e, h / 2 - e - 0.0003)), ((w / 2 - e, h / 2 - 0.03), (w / 2, h / 2 - e - 0.0003))):
            mb.box((a[0], yf - 0.0011, zm + a[1]), (b[0], yf + 0.0004, zm + b[1]), "cable", bevel=0.0)
    for sx in (-1, 1):                                                                           # asas laterales
        x = sx * 0.245
        mb.tube(fillet([(x - sx * 0.004, -0.17, z0 + 0.1), (x + sx * 0.022, -0.17, z0 + 0.1), (x + sx * 0.022, -0.17, z1 - 0.1),
                        (x - sx * 0.004, -0.17, z1 - 0.1)], 0.016, 6), 0.0095, seg=10, mat="cable")
    # charola de chasis por el costado +x con jaladera
    zt = zm - 0.02
    mb.box((0.2449, -0.19, zt - 0.012), (0.246, -0.09, zt + 0.012), "cable", bevel=0.0)       # boca de la charola
    rbox(mb, (0.24, -0.185, zt - 0.009), (0.252, -0.095, zt + 0.009), "plastic", r=0.003)
    mb.tube(fillet([(0.252, -0.175, zt), (0.268, -0.175, zt), (0.268, -0.105, zt), (0.252, -0.105, zt)], 0.008, 4), 0.0045, seg=8,
            mat="steel")
    # cable del motor: del receptor a la columna, baja por la columna y entra a una caja en el muro
    pts = [(-0.18, yb0 + 0.004, z0 + 0.02), (-0.2, -0.08, z0 - 0.06), (-0.12, -0.03, z0 - 0.25), (-0.095, -0.02, 0.6),
           (-0.095, -0.02, 0.32), (-0.13, -0.012, 0.22)]
    hose(mb, pts, 0.0055, mat="cable", seg=8, rad=0.05, nseg=5)
    for z in (0.5, 0.75):                                                                        # grapas del cable
        mb.box((-0.104, -0.03, z), (-0.086, -0.0098, z + 0.012), "steel", bevel=0.002)
    rbox(mb, (-0.19, -0.04, 0.16), (-0.12, -0.0002, 0.26), "sign_white", r=0.006)              # caja de registro
    for z in (0.17, 0.25):
        screw(mb, _T(-0.155, -0.04, z) @ _Rx(90), d=0.0065, seg=8)
    return mb


# ======================================================================================================== mampara plomada
def _small_caster(mb, M, d=0.075, brake=False):
    """Rodaja de 75 mm: placa giratoria con 4 tornillos, horquilla de lámina, rueda de hule con rin y eje con tuerca.
    Origen: piso bajo el eje; la placa queda arriba (z = d + 0.03)."""
    r = d / 2
    zt = d + 0.026
    mb.box((-0.035, -0.035, zt), (0.035, 0.035, zt + 0.004), "steel", bevel=0.0015, seg=1, m=M)
    lathe(mb, [(0.0, 0.0), (0.024, 0.0), (0.024, 0.008), (0.0, 0.008)], seg=16, mat="steel", M=M @ _T(0, 0, zt - 0.008))
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        hexnut(mb, M @ _T(sx * 0.026, sy * 0.026, zt + 0.004), d=0.0045, washer=False)
    off = r * 0.45
    for s in (-1, 1):
        prof = [(-0.02, zt - 0.008), (0.02, zt - 0.008), (off + 0.014, r + 0.01), (off + 0.012, r - 0.008), (off - 0.012, r - 0.008),
                (-0.016, zt - 0.02)]
        perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        mb.plate([(y, z) for (y, z) in prof], 0.0025, "steel", m=M @ _T(s * 0.019 - (0.0025 if s > 0 else 0), 0, 0) @ perm)
    Mw = M @ _T(0, off, r) @ _Ry(90)
    revolve(mb, [(r * 0.62, -0.0135), (r * 0.9, -0.0135), (r, -0.008), (r, 0.008), (r * 0.9, 0.0135), (r * 0.62, 0.0135)], "rubber",
            seg=20, M=Mw, closed=True)
    revolve(mb, [(0.0, -0.014), (r * 0.62, -0.014), (r * 0.62, 0.014), (0.0, 0.014)], "plastic", seg=20, M=Mw)
    mb.cyl(M @ Vector((-0.024, off, r)), M @ Vector((0.024, off, r)), 0.004, seg=8, mat="steel")
    for s in (-1, 1):
        hexnut(mb, M @ _T(s * 0.0215, off, r) @ _Ry(90 * s), d=0.006, washer=False)
    if brake:
        rbox(mb, (-0.016, -0.055, zt - 0.02), (0.016, -0.02, zt - 0.012), "sign_red", r=0.004, m=M)


def lead_screen():
    """Mampara plomada móvil (cuarto de rayos X): tablero forrado de plomo con piel de lámina pintada, mirilla de vidrio
    plomado de 15 mm con marcos atornillados en ambas caras, perfil perimetral de acero con esquinas redondeadas, zoclo de
    lámina, 2 asas de tubo con postes, placa de advertencia, base de 2 patas de PTR con cartelas y 4 rodajas (2 con freno).
    Origen: piso, centro; frente -Y."""
    from kit.common import wall_with_openings
    mb = MB()
    W, z0, z1 = 0.94, 0.165, 1.915
    t = 0.04
    wx0, wx1, wz0, wz1 = -0.2, 0.2, 1.4, 1.7
    wall_with_openings(mb, W, z1 - z0, t, [(wx0 + W / 2, wx1 + W / 2, wz0 - z0, wz1 - z0)], mat_out="paint_white", mat_in="paint_white",
                       mat_reveal="steel", m=_T(-W / 2, -t / 2, z0))
    # perfil perimetral (canal de acero que abraza el tablero)
    path = [(p[0], 0.0, p[1] + (z0 + z1) / 2) for p in rrect(W + 0.008, z1 - z0 + 0.008, 0.02, n=4)]
    ch = [(0.0, -0.027), (0.0, 0.027), (0.006, 0.0275), (0.012, 0.024), (0.012, 0.021), (-0.012, 0.021), (-0.012, -0.021),
          (0.012, -0.021), (0.012, -0.024), (0.006, -0.0275)]
    mb.sweep([(x - 0.004, y) for (x, y) in ch], path, mat="steel", closed_path=True, normal=(0, 1, 0))
    # mirilla: vidrio plomado y marcos atornillados en las dos caras
    mb.box((wx0 - 0.004, -0.0075, wz0 - 0.004), (wx1 + 0.004, 0.0075, wz1 + 0.004), "glass", bevel=0.002)
    for sy in (-1, 1):
        yf = sy * t / 2
        fp = [(p[0], yf, p[1] + (wz0 + wz1) / 2) for p in rrect(wx1 - wx0 + 0.07, wz1 - wz0 + 0.07, 0.012, n=3)]
        prof = [(0.0, 0.0), (0.0, 0.006), (0.004, 0.009), (0.03, 0.009), (0.035, 0.005), (0.035, -0.0003), (0.0, -0.0003)]
        mb.sweep([(-x, sy * y) for (x, y) in prof], fp, mat="aluminium", closed_path=True, normal=(0, 1, 0))
        for k in range(10):
            if k < 4:
                p = (wx0 - 0.0175 + (wx1 - wx0 + 0.035) * k / 3, wz0 - 0.0175)
            elif k < 8:
                p = (wx0 - 0.0175 + (wx1 - wx0 + 0.035) * (k - 4) / 3, wz1 + 0.0175)
            else:
                p = (wx0 - 0.0175 if k == 8 else wx1 + 0.0175, (wz0 + wz1) / 2)
            screw(mb, _T(p[0], yf + sy * 0.009, p[1]) @ _Rx(-90 * sy), d=0.0075, seg=6)
    # zoclo de lámina en ambas caras
    for sy in (-1, 1):
        ya, yb = sorted((sy * t / 2, sy * (t / 2 + 0.0015)))
        mb.box((-W / 2 + 0.01, ya - sy * 0.0002, z0 + 0.01), (W / 2 - 0.01, yb - sy * 0.0002, z0 + 0.16), "steel", bevel=0.001, seg=1)
        for x in (-0.4, 0.0, 0.4):
            screw(mb, _T(x, sy * (t / 2 + 0.0013), z0 + 0.13) @ _Rx(-90 * sy), d=0.0065, seg=6, recess=None)
    # placa de advertencia (cara frontal)
    Mp = _T(0, -t / 2 - 0.0012, 1.2) @ _Rx(90)
    mb.plate(rrect(0.26, 0.07, 0.008, n=3), 0.0014, "paint_yellow", m=Mp @ _T(0, 0, -0.0002))
    text(mb, "CAUTION", 0.03, 0.0008, "cable", Mp @ _T(0, 0.002, 0.0011), bold=True, res=2)
    text(mb, "LEAD SHIELD", 0.014, 0.0008, "cable", Mp @ _T(0, -0.026, 0.0011), res=2)
    for x in (-0.115, 0.115):
        screw(mb, Mp @ _T(x, 0, 0.0011), d=0.006, seg=6, recess=None)
    # asas de tubo con postes (cara posterior +Y)
    for sx in (-1, 1):
        x = sx * 0.4
        mb.tube(fillet([(x, t / 2, 0.9), (x, t / 2 + 0.06, 0.92), (x, t / 2 + 0.06, 1.28), (x, t / 2, 1.3)], 0.025, 6), 0.0125, seg=12,
                mat="steel")
        for z in (0.9, 1.3):
            lathe(mb, [(0.0, 0.0), (0.022, 0.0), (0.022, 0.004), (0.016, 0.007), (0.0, 0.007)], seg=14, mat="steel",
                  M=_T(x, t / 2 - 0.0005, z) @ _Rx(-90))
    # base: patas de PTR, postes del perfil y cartelas, rodajas
    for sx in (-1, 1):
        x = sx * 0.42
        rtube(mb, (x, -0.29, 0.13), (x, 0.29, 0.13), 0.05, 0.035, "steel", up=(0, 0, 1), r=0.004)
        for y in (-0.29, 0.29):
            rbox(mb, (x - 0.027, y - 0.006 if y > 0 else y - 0.004, 0.1105), (x + 0.027, y + 0.004 if y > 0 else y + 0.006, 0.1495),
                 "plastic", r=0.005)
        rtube(mb, (x, 0.0, 0.147), (x, 0.0, z0 + 0.02), 0.034, 0.03, "steel", up=(1, 0, 0), r=0.004)
        for sy in (-1, 1):
            port.gusset(mb, _T(x, sy * 0.015, 0.1475) @ _Rz(90 if sy > 0 else -90), 0.09, 0.05, t=0.004, mat="steel", chamfer=0.012)
        for k, y in enumerate((-0.25, 0.25)):
            _small_caster(mb, _T(x, y, 0.0) @ _Rz(float(37 * sx + 90 * k)), d=0.075, brake=(k == 0))
    return mb


# ======================================================================================================== arbotante
def wall_lamp():
    """Arbotante exterior tipo farol (limpio, funcionando): placa de muro moldurada con 2 tornillos de cabeza decorativa y
    roseta, brazo de tubo con remate en gancho y voluta de solera como tirante, farol hexagonal ahusado con 6 postes, aros
    superior e inferior, cristales embutidos, techo piramidal con alero y chimenea ventilada, charola inferior con remate,
    portalámparas y foco a la vista. Origen: cara del muro, centro; crece hacia -Y."""
    mb = MB()
    # placa de muro (óvalo alargado con canto moldurado)
    out = rrect(0.12, 0.2, 0.05, n=6)
    mb.plate(out, 0.0062, "enamel", m=_Rx(90) @ _T(0, 0, 0.0001))
    mb.plate(rrect(0.1, 0.18, 0.042, n=6), 0.005, "enamel", m=_Rx(90) @ _T(0, 0, 0.0061))
    for z in (-0.068, 0.068):
        lathe(mb, [(0.0, 0.0), (0.0085, 0.0), (0.0085, 0.0025), (0.006, 0.006), (0.0025, 0.0075), (0.0, 0.0075)], seg=12, mat="enamel",
              M=_T(0, -0.0108, z) @ _Rx(90))
    lathe(mb, [(0.0, 0.0), (0.026, 0.0), (0.026, 0.005), (0.019, 0.01), (0.014, 0.018), (0.0, 0.018)], seg=20, mat="enamel",
          M=_T(0, -0.0108, 0.03) @ _Rx(90))                                                       # roseta del brazo
    # farol
    yl = -0.16
    zb, zt = -0.088, 0.088                                                                       # aro inferior / superior
    rb, rt_ = 0.05, 0.073
    ph = PI / 6
    for k in range(6):                                                                           # postes
        a = ph + PI / 3 * k
        p0 = Vector((rb * math.cos(a), yl + rb * math.sin(a), zb))
        p1 = Vector((rt_ * math.cos(a), yl + rt_ * math.sin(a), zt))
        mb.tube([tuple(p0), tuple(p1)], 0.0042, seg=4, mat="enamel")
    for k in range(6):                                                                           # cristales
        a0, a1 = ph + PI / 3 * k, ph + PI / 3 * (k + 1)
        am = (a0 + a1) / 2
        n = Vector((math.cos(am), math.sin(am), 0.0))
        q = []
        for (rr_, z) in ((rb, zb + 0.008), (rt_, zt - 0.006)):
            for a in (a0, a1):
                q.append(Vector((rr_ * math.cos(a), yl + rr_ * math.sin(a), z)))
        c0 = (q[0] + q[1]) / 2
        c1 = (q[2] + q[3]) / 2
        sh = 0.95
        pts = [c0 + (q[0] - c0) * sh, c0 + (q[1] - c0) * sh, c1 + (q[3] - c1) * sh, c1 + (q[2] - c1) * sh]
        bot = [p - n * 0.0012 for p in pts]
        top = [p + n * 0.0012 for p in pts]
        V0 = [mb.bm.verts.new(p) for p in bot]
        V1 = [mb.bm.verts.new(p) for p in top]
        mb.face(list(reversed(V0)), "glass")
        mb.face(V1, "glass")
        for i in range(4):
            j = (i + 1) % 4
            mb.face([V0[i], V0[j], V1[j], V1[i]], "glass")
    revolve(mb, [(rb - 0.004, zb - 0.004), (rb + 0.006, zb - 0.004), (rb + 0.006, zb + 0.008), (rb - 0.004, zb + 0.008)], "enamel",
            seg=6, M=_T(0, yl, 0), phase=ph, closed=True)
    revolve(mb, [(rt_ - 0.004, zt - 0.008), (rt_ + 0.006, zt - 0.008), (rt_ + 0.006, zt + 0.004), (rt_ - 0.004, zt + 0.004)], "enamel",
            seg=6, M=_T(0, yl, 0), phase=ph, closed=True)
    # techo piramidal con alero, chimenea ventilada y remate
    revolve(mb, [(0.0, zt + 0.004), (0.088, zt + 0.004), (0.09, zt + 0.009), (0.086, zt + 0.012), (0.05, zt + 0.042), (0.026, zt + 0.056),
                 (0.0, zt + 0.056)], "enamel", seg=6, M=_T(0, yl, 0), phase=ph)
    for k in range(6):                                                                           # nervios de las limatesas
        a = ph + PI / 3 * k
        c, s_ = math.cos(a), math.sin(a)
        mb.tube([(0.086 * c, yl + 0.086 * s_, zt + 0.0125), (0.027 * c, yl + 0.027 * s_, zt + 0.0575)], 0.0028, seg=6, mat="enamel")
    for k in range(6):
        a = ph + PI / 3 * k
        arc_solid(mb, 0.019, 0.023, zt + 0.055, zt + 0.07, a - 0.18, a + 0.18, 2, "enamel", M=_T(0, yl, 0))
    revolve(mb, [(0.0, zt + 0.069), (0.032, zt + 0.069), (0.033, zt + 0.073), (0.02, zt + 0.081), (0.0, zt + 0.083)], "enamel", seg=6,
            M=_T(0, yl, 0), phase=ph)
    revolve(mb, [(0.0, zt + 0.082), (0.007, zt + 0.082), (0.009, zt + 0.088), (0.006, zt + 0.094), (0.0, zt + 0.096)], "enamel", seg=10,
            M=_T(0, yl, 0))
    # charola inferior con remate
    revolve(mb, [(0.0, zb - 0.004), (rb + 0.004, zb - 0.004), (rb - 0.004, zb - 0.011), (0.02, zb - 0.014), (0.0, zb - 0.014)],
            "enamel", seg=6, M=_T(0, yl, 0), phase=ph)
    revolve(mb, [(0.0, zb - 0.013), (0.009, zb - 0.013), (0.006, zb - 0.017), (0.004, zb - 0.02), (0.0, zb - 0.021)], "enamel", seg=10,
            M=_T(0, yl, 0))
    # portalámparas y foco
    revolve(mb, [(0.0, zb - 0.004), (0.016, zb - 0.004), (0.016, zb + 0.04), (0.0135, zb + 0.044), (0.0, zb + 0.044)], "cable", seg=14,
            M=_T(0, yl, 0))
    revolve(mb, [(0.0, zb + 0.044), (0.0125, zb + 0.044), (0.014, zb + 0.052), (0.022, zb + 0.07), (0.03, zb + 0.095),
                 (0.03, zb + 0.11), (0.024, zb + 0.125), (0.012, zb + 0.133), (0.0, zb + 0.135)], "plastic", seg=18, M=_T(0, yl, 0))
    # brazo: tubo de la roseta al remate del techo, con gancho; voluta de solera como tirante
    za = zt + 0.096 + 0.006
    arm = fillet([(0, -0.012, 0.03), (0, -0.05, 0.035), (0, -0.09, za + 0.004), (0, yl + 0.012, za + 0.004), (0, yl - 0.004, za - 0.002),
                  (0, yl, zt + 0.092)], 0.02, 6)
    mb.tube(arm, 0.0068, seg=10, mat="enamel")
    curl = []
    for k in range(22):                                                                          # voluta: espiral + recta
        th = 2.6 * PI * k / 21
        rr_ = 0.028 * (1 - 0.72 * k / 21)
        curl.append((0.0, -0.05 + rr_ * math.sin(th), -0.035 + 0.028 - rr_ * math.cos(th)))
    vol = list(reversed(curl)) + [(0.0, -0.06, -0.0), (0.0, -0.09, za - 0.012), (0.0, -0.11, za - 0.004)]
    sweep_frame(mb, rr_profile(0.004, 0.011, 0.0015, n=2), vol, "enamel", up=(1, 0, 0))
    mb.box((-0.0055, -0.0108 - 0.012, -0.062), (0.0055, -0.0105, -0.03), "enamel", bevel=0.002)   # asiento de la voluta
    return mb

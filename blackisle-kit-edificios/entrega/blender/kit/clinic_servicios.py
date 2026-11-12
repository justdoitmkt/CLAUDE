"""kit/clinic_servicios.py — electrodomésticos y sanitarios del hospital rural HOS_1_pueblo reconstruidos a calidad AAA (regla R-AAA).

Mismas firmas, origen, orientación y tamaño que las versiones de kit/clinic.py (frente -Y, piso en z = 0; las piezas de muro
tienen el origen en la cara del muro y crecen hacia -Y). Lo que cambia es la construcción: gabinetes de lámina con aristas
redondeadas y juntas de 1-3 mm entre paneles, empaques, bisagras, tornillos, rejillas con ranuras reales, perillas con faldón y
estrías, mangueras con dobleces de radio real, niveladores, charolas con rejilla, etc. Todo con materiales del kit (casi colores
planos): el detalle sale de la geometría.

Primitivas propias (además de las de kit.clinic):
- skin(): une anillos (lazos de igual número de vértices, o polos de un vértice) en un sólido cerrado.
- lathe(): torneado con polos reales (sin anillos degenerados), perfil abierto o cerrado y modulación angular (estrías).
- slab(): caja de esquinas redondeadas en planta (radio por esquina) y cantos redondeados arriba/abajo.
- holed(): placa con hueco (ojo de buey, ventana): contorno exterior e interior por SDF de rectángulo redondeado, cantos curvos.
- knob(), screw(), hexnut(), hose(), louver_grille(), label().
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
from mathutils import Matrix, Vector

from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rng, rr_profile

# ===================================================================================================== primitivas


def _V(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def skin(mb, loops, mat, M=None, cap0=True, cap1=True, closed=False, mats=None):
    """Une lazos consecutivos con cuadriláteros (o triángulos contra un polo de 1 punto). Tapa los extremos con n-gonos.
    loops: listas de puntos 3D con el mismo número de vértices (o [p] = polo). mats: material por banda (opcional)."""
    V = []
    for L in loops:
        V.append([mb.bm.verts.new((M @ _V(p)) if M is not None else _V(p)) for p in L])
    nb = len(V) if closed else len(V) - 1
    for i in range(nb):
        A, B = V[i], V[(i + 1) % len(V)]
        m = mats[i] if mats else mat
        if len(A) == 1 and len(B) == 1:
            continue
        if len(A) == 1:
            n = len(B)
            for k in range(n):
                mb.face([A[0], B[(k + 1) % n], B[k]], m)
        elif len(B) == 1:
            n = len(A)
            for k in range(n):
                mb.face([A[k], A[(k + 1) % n], B[0]], m)
        else:
            n = len(A)
            for k in range(n):
                mb.face([A[k], A[(k + 1) % n], B[(k + 1) % n], B[k]], m)
    if not closed:
        if cap0 and len(V[0]) > 2:
            mb.face(list(reversed(V[0])), mats[0] if mats else mat)
        if cap1 and len(V[-1]) > 2:
            mb.face(V[-1], mats[-1] if mats else mat)
    return V


def lathe(mb, prof, seg=32, mat="steel", M=None, closed=False, phase=0.0, rmod=None, caps=True, mats=None):
    """Torneado alrededor de Z local. prof [(r, z)]; r = 0 -> polo (un solo vértice). closed: el perfil es un lazo cerrado.
    rmod(i, a, r, z) -> radio modificado (estrías, moleteado)."""
    loops = []
    for i, (r, z) in enumerate(prof):
        if r < 1e-7:
            loops.append([(0.0, 0.0, z)])
            continue
        L = []
        for k in range(seg):
            a = phase + 2 * PI * k / seg
            rr = r if rmod is None else rmod(i, a, r, z)
            L.append((rr * math.cos(a), rr * math.sin(a), z))
        loops.append(L)
    return skin(mb, loops, mat, M, cap0=caps, cap1=caps, closed=closed, mats=mats)


def rr_pts(w, h, r, n=4):
    """Contorno de rectángulo redondeado centrado (antihorario desde la esquina +x+y). r escalar o (sd, si, ii, id)."""
    if not isinstance(r, (tuple, list)):
        r = (r, r, r, r)
    pts = []
    cs = ((w / 2, h / 2, 0.0), (-w / 2, h / 2, PI / 2), (-w / 2, -h / 2, PI), (w / 2, -h / 2, 1.5 * PI))
    for (sx, sy, a0), rr in zip(cs, r):
        rr = max(min(rr, w / 2 - 1e-4, h / 2 - 1e-4), 2e-4)
        cx, cy = sx - math.copysign(rr, sx), sy - math.copysign(rr, sy)
        for k in range(n + 1):
            a = a0 + PI / 2 * k / n
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def _edge_levels(h, re, re0, ne):
    lv = []
    if re0 > 0:
        for j in range(ne + 1):
            p = PI / 2 * j / ne
            lv.append((re0 * (1 - math.sin(p)), re0 * (1 - math.cos(p))))
    else:
        lv.append((0.0, 0.0))
    if re > 0:
        for j in range(ne + 1):
            p = PI / 2 * j / ne
            lv.append((re * (1 - math.cos(p)), h - re + re * math.sin(p)))
    else:
        lv.append((0.0, h))
    return lv


def slab(mb, M, w, d, h, rc=0.01, re=0.004, mat="sign_white", nc=4, ne=3, re0=None, cap0=True, cap1=True, mats=None):
    """Caja redondeada: planta w × d centrada (radio de esquina rc, escalar o por esquina), z de 0 a h, canto superior re y
    canto inferior re0 (por omisión = re). cap0/cap1 = tapas inferior/superior (False deja la caja abierta en ese extremo)."""
    re0 = re if re0 is None else re0
    re = min(re, h * 0.49)
    re0 = min(re0, h * 0.49)
    rcs = rc if isinstance(rc, (tuple, list)) else (rc,) * 4
    loops = []
    for (dl, z) in _edge_levels(h, re, re0, ne):
        loops.append([(x, y, z) for (x, y) in rr_pts(w - 2 * dl, d - 2 * dl, tuple(max(r_ - dl, 3e-4) for r_ in rcs), nc)])
    return skin(mb, loops, mat, M, cap0=cap0, cap1=cap1, mats=mats)


def _sdf_rr(x, y, cx, cy, hw, hh, r):
    px, py = x - cx, y - cy
    if isinstance(r, (tuple, list)):
        rr = r[0] if (px >= 0 and py >= 0) else r[1] if (px < 0 <= py) else r[2] if px < 0 else r[3]
    else:
        rr = r
    rr = min(rr, hw, hh)
    qx, qy = abs(px) - hw + rr, abs(py) - hh + rr
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - rr


def _ray(sdf, ox, oy, a, target, tmax=3.0):
    c, s = math.cos(a), math.sin(a)
    lo, hi = 0.0, tmax
    for _ in range(42):
        mid = (lo + hi) / 2
        if sdf(ox + c * mid, oy + s * mid) < target:
            lo = mid
        else:
            hi = mid
    t = (lo + hi) / 2
    return (ox + c * t, oy + s * t)


def holed(mb, M, outer, inner, t, re_o=0.004, re_i=0.004, n=64, mat="sign_white", ne=3, ctr=None, phase=None, re_b=0.0):
    """Placa con un hueco pasante en el plano XY local, espesor de z = 0 a t (cara vista en z = t).
    outer / inner = (cx, cy, medio_ancho, medio_alto, radio | (sd, si, ii, id)). Canto exterior re_o, canto del hueco re_i."""
    so = lambda x, y: _sdf_rr(x, y, *outer)  # noqa: E731
    si = lambda x, y: _sdf_rr(x, y, *inner)  # noqa: E731
    ox, oy = ctr or (inner[0], inner[1])
    ph = PI / n if phase is None else phase
    angs = [ph + 2 * PI * k / n for k in range(n)]
    secs = [("o", re_b, 0.0)] if re_b <= 0 else [("o", re_b * (1 - math.sin(PI / 2 * j / 2)), re_b * (1 - math.cos(PI / 2 * j / 2)))
                                                   for j in range(3)]
    if re_o > 0:
        secs += [("o", re_o * (1 - math.cos(PI / 2 * j / ne)), t - re_o + re_o * math.sin(PI / 2 * j / ne)) for j in range(ne + 1)]
    else:
        secs.append(("o", 0.0, t))
    if re_i > 0:
        secs += [("i", re_i * (1 - math.cos(PI / 2 * (ne - j) / ne)), t - re_i + re_i * math.sin(PI / 2 * (ne - j) / ne))
                 for j in range(ne + 1)]
    else:
        secs.append(("i", 0.0, t))
    secs.append(("i", 0.0, 0.0))
    loops = []
    for (kind, dl, z) in secs:
        if kind == "o":
            loops.append([(*_ray(so, ox, oy, a, -dl), z) for a in angs])
        else:
            loops.append([(*_ray(si, ox, oy, a, dl), z) for a in angs])
    return skin(mb, loops, mat, M, closed=True)


def rrframe(mb, M, outer, inner, t, re_o=0.004, re_i=0.003, n=5, ne=3, mat="sign_white"):
    """Marco rectangular redondeado (puerta con ventana, bisel): outer / inner = (cx, cy, ancho, alto, radio). Lazos de igual
    topología (rr_pts): las rectas siguen siendo rectas y las esquinas redondas. Espesor de z = 0 a t (cara vista en z = t)."""
    def lo(dl, z):
        cx, cy, w, h, rc = outer
        return [(cx + x, cy + y, z) for (x, y) in rr_pts(w - 2 * dl, h - 2 * dl, max(rc - dl, 3e-4), n)]

    def li(dl, z):
        cx, cy, w, h, rc = inner
        return [(cx + x, cy + y, z) for (x, y) in rr_pts(w + 2 * dl, h + 2 * dl, rc + dl, n)]
    loops = [lo(0.0, 0.0)]
    loops += [lo(re_o * (1 - math.cos(PI / 2 * j / ne)), t - re_o + re_o * math.sin(PI / 2 * j / ne)) for j in range(ne + 1)]
    loops += [li(re_i * (1 - math.cos(PI / 2 * (ne - j) / ne)), t - re_i + re_i * math.sin(PI / 2 * (ne - j) / ne)) for j in range(ne + 1)]
    loops.append(li(0.0, 0.0))
    return skin(mb, loops, mat, M, closed=True)


def screw(mb, M, r=0.0035, mat="steel", cross=True, seg=10):
    """Tornillo de cabeza redonda (pan) con cruz, apoyado en z = 0 local (eje +Z); hundido 0,3 mm para no flotar."""
    h = r * 0.75
    M2 = M @ _T(0, 0, -0.0003)
    lathe(mb, [(r * 0.98, 0.0), (r, h * 0.35), (r * 0.82, h * 0.85), (r * 0.5, h), (r * 0.28, h * 0.96), (0.0, h * 0.62)], seg=seg,
          mat=mat, M=M2)
    if cross:
        for ang in (0, 90):
            mb.box((-r * 0.55, -r * 0.09, h * 0.55), (r * 0.55, r * 0.09, h * 0.93), mat, bevel=0.0, m=M2 @ _Rz(ang))


def hexnut(mb, M, s=0.01, h=0.006, mat="steel", hole=0.0):
    """Tuerca hexagonal con chaflán (s = entre caras) sobre z = 0 local."""
    R = s / 2 / math.cos(PI / 6)
    lathe(mb, [(R * 0.86, 0.0), (R, h * 0.18), (R, h * 0.82), (R * 0.86, h)] + ([(hole, h), (hole, h + 0.0005)] if hole else []),
          seg=6, mat=mat, M=M, phase=PI / 6)


def knurl(n, depth, p=3.0):
    """Modulador de radio para estrías: n estrías de profundidad `depth`."""
    return lambda i, a, r, z: r - depth * (0.5 + 0.5 * math.cos(n * a)) ** p


def text3d(mb, s, size, depth, mat, M=None, align="CENTER", res=3, bold=False):
    """Como kit.clinic.text pero con resolución de curva baja (las letras pequeñas no necesitan 12 pasos por curva)."""
    cu = bpy.data.curves.new("_txt", "FONT")
    cu.body = s
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = align
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
    bmesh.ops.remove_doubles(mb.bm, verts=vs, dist=size * 1e-4)              # letras soldadas: sólidos cerrados
    vs = [v for v in vs if v.is_valid]
    edges = list({e for v in vs for e in v.link_edges})
    bmesh.ops.dissolve_degenerate(mb.bm, dist=size * 1e-4, edges=edges)


def label(mb, s, size, mat, M, depth=0.0016, align="CENTER", bold=False, res=None):
    """Letrero en relieve: M = plano de la superficie (XY local, +Z hacia afuera). Sobresale `depth` (>= 1 mm) y se hunde 0,3 mm."""
    res = res or (2 if size < 0.012 else 3)
    return text3d(mb, s, size, depth + 0.0003, mat, M @ _T(0, 0, -0.0003), align=align, res=res, bold=bold)


def resample(pts, step):
    P = [Vector(p) for p in pts]
    out = [P[0]]
    acc = 0.0
    for i in range(1, len(P)):
        a, b = P[i - 1], P[i]
        L = (b - a).length
        if L < 1e-9:
            continue
        d = step - acc
        while d <= L:
            out.append(a.lerp(b, d / L))
            d += step
        acc = L - (d - step)
    if (out[-1] - P[-1]).length > step * 0.3:
        out.append(P[-1])
    else:
        out[-1] = P[-1]
    return [tuple(p) for p in out]


def _dedupe(pts, eps=1e-5):
    out = [pts[0]]
    for p in pts[1:]:
        if (Vector(p) - Vector(out[-1])).length > eps:
            out.append(p)
    return out


def hose(mb, pts, r, bend=0.03, mat="rubber", seg=10, pitch=None, depth=0.12, nseg=8):
    """Manguera / cable por una polilínea con dobleces de radio `bend`. pitch: corrugado (anillos cada `pitch`)."""
    path = _dedupe(fillet(pts, bend, nseg))
    if pitch:
        path = resample(path, pitch / 2)
        radii = [r if (i % 2 == 0) else r * (1 - depth) for i in range(len(path))]
        radii[0] = radii[-1] = r
        mb.tube(path, r, seg=seg, mat=mat, radii=radii)
    else:
        mb.tube(path, r, seg=seg, mat=mat)
    return path


def knob(mb, M, r=0.02, h=0.02, mat="plastic", skirt=None, skirt_mat=None, ribs=0, rib_d=0.001, seg=None, fin=False,
         pointer_mat=None, skirt_seg=48, fin_nc=3, lite=False):
    """Perilla sobre z = 0 local (eje +Z): faldón opcional (r, alto), cuerpo con estrías o con aleta de agarre, tapa abombada
    e indicador en relieve. lite: perfiles con menos anillos y sin las tapas que quedan ocultas (presupuesto)."""
    seg = seg or (max(32, ribs * 4) if ribs else 32)
    M = M @ _T(0, 0, -0.0003)
    z0 = 0.0
    if skirt:
        sr, sh = skirt
        if lite:
            lathe(mb, [(sr * 0.93, 0.0), (sr, sh * 0.3), (sr, sh * 0.75), (r * 1.02, sh * 1.05)], seg=skirt_seg, mat=skirt_mat or mat,
                  M=M, caps=False)
        else:
            lathe(mb, [(sr * 0.93, 0.0), (sr, sh * 0.25), (sr, sh * 0.7), (sr * 0.97, sh), (r * 1.02, sh * 1.05), (r * 0.8, sh * 1.05)],
                  seg=skirt_seg, mat=skirt_mat or mat, M=M)
        z0 = sh * 0.9
    rm = knurl(ribs, rib_d) if ribs else None
    prof = [(r * 0.97, z0), (r, z0 + 0.001), (r, z0 + h * 0.8), (r * 0.96, z0 + h * 0.93), (r * 0.85, z0 + h), (r * 0.5, z0 + h * 1.02),
            (0.0, z0 + h * 1.02)]
    if lite:
        prof = [(r * 0.97, z0), (r, z0 + 0.001), (r, z0 + h * 0.82), (r * 0.86, z0 + h), (0.0, z0 + h * 1.02)]
    rmod = (lambda i, a, rr, z: rm(i, a, rr, z) if 1 <= i <= 2 else rr) if rm else None
    lathe(mb, prof, seg=seg, mat=mat, M=M, rmod=rmod, caps=not lite)
    if fin:
        slab(mb, M @ _T(0, 0, z0 + h * 0.98), r * 1.5, r * 0.42, h * 0.9, rc=r * 0.2, re=r * 0.12, mat=mat, re0=0.0, nc=fin_nc,
             ne=2 if fin_nc > 2 else 1)
        ztop = z0 + h * 0.98 + h * 0.9
        slab(mb, M @ _T(r * 0.45, 0, ztop - 0.0004), r * 0.5, r * 0.08, 0.0012, rc=r * 0.03, re=0.0004, mat=pointer_mat or "sign_white",
             nc=2, ne=1, re0=0.0)
    else:
        slab(mb, M @ _T(r * 0.55, 0, z0 + h * 1.02 - 0.0005), r * 0.55, r * 0.12, 0.0015, rc=r * 0.05, re=0.0005,
             mat=pointer_mat or "sign_white", nc=2, ne=1, re0=0.0)


def louver_grille(mb, M, w, h, n, mat="plastic", back_mat="cable", t=0.006, frame=0.008, slat_ang=35.0, depth=0.01, nr=40):
    """Rejilla con ranuras reales en el plano XY local (cara vista +Z, apoyada en z = 0): marco perimetral (placa con hueco),
    n persianas inclinadas que cruzan el hueco y fondo oscuro rehundido `depth` detrás de las ranuras."""
    holed(mb, M, (0, 0, w / 2, h / 2, min(0.006, h / 4)), (0, 0, w / 2 - frame, h / 2 - frame, 0.002), t, re_o=min(0.002, t * 0.4),
          re_i=0.001, n=nr, mat=mat, ne=2, ctr=(0, 0))
    ih = h - 2 * frame
    pitch = ih / n
    for k in range(n):
        y = -ih / 2 + pitch * (k + 0.5)
        Ms = M @ _T(0, y, t * 0.5) @ _Rx(-slat_ang)
        mb.box((-(w / 2 - frame) - 0.0008, -pitch * 0.42, -0.0009), ((w / 2 - frame) + 0.0008, pitch * 0.42, 0.0009), mat,
               bevel=0.0004, seg=1, m=Ms)
    mb.box((-(w / 2 - frame) + 0.0005, -ih / 2 + 0.0005, -depth), ((w / 2 - frame) - 0.0005, ih / 2 - 0.0005, -depth + 0.002),
           back_mat, bevel=0.0, m=M)


def foot_leveler(mb, M, r=0.018, h=0.022, mat="rubber", lite=False):
    """Pata niveladora: base de hule, espárrago roscado y contratuerca (z = 0 = piso, sube hasta h dentro del gabinete).
    lite: versión de presupuesto (bajo el aparato casi no se ve): base de 10 lados, espárrago liso con 2 hilos, sin fondo."""
    if lite:
        lathe(mb, [(r * 0.86, 0.0), (r, 0.002), (r, 0.0042), (r * 0.42, 0.0065), (0.0, 0.0066)], seg=10, mat=mat, M=M, caps=False)
        rs = r * 0.38
        lathe(mb, [(rs * 0.9, 0.006), (rs, 0.0075), (rs * 0.84, 0.009), (rs, 0.0105), (rs, h), (0.0, h)], seg=6, mat="steel", M=M,
              caps=False)
        hexnut(mb, M @ _T(0, 0, h * 0.45), s=r * 1.2, h=0.005, mat="steel")
        return
    lathe(mb, [(r * 0.85, 0.0), (r, 0.0015), (r, 0.004), (r * 0.8, 0.0062), (r * 0.42, 0.0065), (0.0, 0.0065)], seg=12, mat=mat, M=M)
    rs = r * 0.38
    prof = [(rs * 0.9, 0.006)]
    zz = 0.006
    while zz < h - 0.004:
        prof += [(rs, zz + 0.0015), (rs * 0.84, zz + 0.0032)]
        zz += 0.0032
    prof += [(rs, h), (0.0, h)]
    lathe(mb, prof, seg=8, mat="steel", M=M)
    hexnut(mb, M @ _T(0, 0, h * 0.45), s=r * 1.2, h=0.005, mat="steel")


# ======================================================================================================== lavadora
def _drum_bump(a, z):
    u = 9 * a
    v = 2 * PI * z / 0.034
    return (0.5 + 0.5 * math.cos(u + v)) * (0.5 + 0.5 * math.cos(u - v))


def washer(seed=0, front_load=True):
    """Lavadora de carga frontal (60 × 60 × 85): gabinete de lámina con aristas redondeadas y cubierta superior separada por junta,
    panel frontal con ojo de buey de ceja rolada, puerta con aro, vidrio en cazuela, bisagra atornillada y jaladera; fuelle de
    hule con pliegue y tambor de acero estampado con alzadores; consola con cajón de detergente, display, botones, perilla de
    programas con escala y botón de inicio; tapa del filtro, niveladores, tapa trasera atornillada, válvula de llenado con
    manguera, manguera de desagüe corrugada con gancho guía y cordón. (front_load se conserva por firma; siempre carga frontal.)"""
    r = rng(seed)
    mb = MB()
    # ---- gabinete: envolvente abierto al frente (lazo en XZ barrido hacia +Y), cubierta. Presupuesto (≤ 13k): la espalda va
    # contra el muro, así que ahí solo quedan las mangueras y el cordón (marcan la caja), sin tornillos ni placas.
    yf, yb = -0.283, 0.296
    zb, zt = 0.022, 0.834
    slab(mb, _T(0, yf, (zb + zt) / 2) @ _Rx(-90), 0.598, zt - zb, yb - yf, rc=0.014, re=0.004, re0=0.0, mat="sign_white", nc=4,
         ne=2, cap0=False)
    slab(mb, _T(0, -0.0015, 0.8352), 0.600, 0.6025, 0.0148, rc=0.012, re=0.005, re0=0.0025, mat="sign_white", nc=4, ne=2)
    # ---- panel frontal con ojo de buey (ceja rolada hacia adentro)
    holed(mb, _T(0, -0.284, 0) @ _Rx(90), (0.0, 0.368, 0.299, 0.346, (0.004, 0.004, 0.014, 0.014)), (0.0, 0.42, 0.168, 0.168, 0.168),
          0.014, re_o=0.005, re_i=0.010, n=40, mat="sign_white", ne=2)
    # tapa del filtro de la bomba (abajo a la derecha) con ranura para moneda
    Mh = _T(0.228, -0.298, 0.07) @ _Rx(90)
    slab(mb, Mh @ _T(0, 0, -0.0004), 0.105, 0.07, 0.0024, rc=0.008, re=0.0012, mat="sign_white", nc=3, ne=1)
    slab(mb, Mh @ _T(0.035, 0.0, 0.0018), 0.022, 0.0045, 0.0012, rc=0.002, re=0.0004, mat="plastic", nc=1, ne=1, re0=0.0)
    label(mb, "FILTER", 0.0075, "cable", Mh @ _T(-0.015, -0.004, 0.0020), res=1)
    # ---- consola: cajón de detergente (con jalón) y tablero de mandos, separados por junta de 2,5 mm
    pull = float(r.choice([0.0, 0.0, 0.006, 0.014]))
    Md = _T(-0.2045, -0.284 - pull, 0.775) @ _Rx(90)
    slab(mb, Md, 0.185, 0.116, 0.016, rc=(0.004, 0.014, 0.004, 0.004), re=0.004, re0=0.0015, mat="plastic", nc=3, ne=2)
    if pull > 0:                                                                     # costados de la gaveta a la vista
        for x in (-0.288, -0.121):
            mb.box((x - 0.0015, -0.284 - pull + 0.001, 0.73), (x + 0.0015, -0.24, 0.81), "plastic", bevel=0.0, seg=1)
    holed(mb, Md @ _T(0, -0.035, 0.016), (0, 0, 0.055, 0.009, 0.008), (0, 0, 0.046, 0.0045, 0.004), 0.0035, re_o=0.0015, re_i=0.001,
          n=24, mat="plastic", ne=1)                                                 # jalón: ceja con ranura para los dedos
    mb.box((-0.045, -0.0042, -0.004), (0.045, 0.0042, 0.0016), "cable", bevel=0.0, m=Md @ _T(0, -0.035, 0.016))
    for k, s_ in enumerate(("I", "II")):
        label(mb, s_, 0.009, "cable", Md @ _T(-0.06 + k * 0.025, 0.02, 0.016), res=1)
    Mc = _T(0.09475, -0.284, 0.775) @ _Rx(90)
    slab(mb, Mc, 0.4085, 0.116, 0.016, rc=(0.014, 0.004, 0.004, 0.004), re=0.004, re0=0.0015, mat="plastic", nc=3, ne=2)
    fz = 0.016                                                                       # cara vista de la consola (local z)
    # display con marco, vidrio y dígitos bajo el vidrio
    Mdisp = Mc @ _T(-0.125, 0.008, fz)
    holed(mb, Mdisp @ _T(0, 0, -0.0004), (0, 0, 0.05, 0.021, 0.004), (0, 0, 0.041, 0.013, 0.002), 0.0026, re_o=0.001, re_i=0.0008,
          n=24, mat="plastic", ne=1, ctr=(0, 0))
    mb.box((-0.0415, -0.0135, -0.0022), (0.0415, 0.0135, 0.0016), "glass", bevel=0.0, m=Mdisp)
    text3d(mb, "0:45", 0.013, 0.0008, "sign_green", Mdisp @ _T(0, -0.0055, -0.0016), res=1)
    for k, s_ in enumerate(("TEMP", "SPIN", "RINSE")):                                # botones de función
        x = -0.157 + k * 0.032
        slab(mb, Mc @ _T(x, -0.042, fz - 0.0004), 0.022, 0.0085, 0.0034, rc=0.0035, re=0.0014, mat="plastic", nc=2, ne=1)
        label(mb, s_, 0.0052, "cable", Mc @ _T(x, -0.032, fz), depth=0.0010, res=1)
        lathe(mb, [(0.0012, 0.0), (0.0012, 0.0006), (0.0, 0.0011)], seg=6, mat="sign_green", M=Mc @ _T(x + 0.014, -0.042, fz - 0.0003))
    # perilla de programas: bisel cromado, perilla estriada con faldón, escala de 14 posiciones
    kx = 0.015
    lathe(mb, [(0.038, -0.0003), (0.0395, 0.0006), (0.039, 0.0022), (0.0365, 0.0028), (0.0345, 0.0016), (0.0345, -0.0003)], seg=32,
          mat="aluminium", M=Mc @ _T(kx, 0, fz), closed=True)
    knob(mb, Mc @ _T(kx, 0, fz) @ _Rz(float(r.uniform(-130, 130))), r=0.026, h=0.024, mat="plastic", skirt=(0.0335, 0.004),
         skirt_mat="sign_white", ribs=12, rib_d=0.0013, pointer_mat="cable", seg=36, skirt_seg=24)
    for k in range(14):
        a = math.radians(-125 + 250 * k / 13) + PI / 2
        Mt = Mc @ _T(kx + 0.047 * math.cos(a), 0.047 * math.sin(a), fz) @ _Rz(math.degrees(a))
        mb.box((-0.0035 if k % 3 else -0.0055, -0.0007, -0.0003), (0.0035, 0.0007, 0.0011), "cable", bevel=0.0, m=Mt)
    # botón de inicio con bisel, testigos y leyenda
    Ms = Mc @ _T(0.125, 0.006, fz)
    lathe(mb, [(0.0215, -0.0003), (0.0222, 0.0012), (0.0205, 0.0026), (0.0182, 0.0018), (0.0182, -0.0003)], seg=24, mat="aluminium",
          M=Ms, closed=True)
    lathe(mb, [(0.0172, -0.0003), (0.0174, 0.0035), (0.0158, 0.0058), (0.009, 0.0068), (0.0, 0.0069)], seg=24, mat="plastic", M=Ms)
    label(mb, "START", 0.0068, "cable", Mc @ _T(0.125, -0.033, fz), res=1)
    for k in range(3):
        lathe(mb, [(0.0016, -0.0003), (0.0016, 0.0007), (0.0009, 0.0013), (0.0, 0.0014)], seg=8, mat="sign_green" if k == 0 else "glass",
              M=Mc @ _T(0.165, 0.02 - k * 0.011, fz))
    label(mb, "POWER", 0.0048, "cable", Mc @ _T(0.165, -0.033, fz), depth=0.0010, res=1)
    # ---- fuelle de hule: labio sobre la ceja, pliegue y labio hacia la boca del tambor (se ve por el vidrio)
    Max = _T(0, 0, 0.42) @ _Rx(90)                                                    # eje del tambor; z local = -y mundial
    cl = [(0.1705, 0.3001), (0.1635, 0.294), (0.1615, 0.281), (0.1690, 0.2655), (0.1555, 0.2525), (0.1515, 0.2425),
          (0.1565, 0.2255)]
    lathe(mb, _thick(cl, 0.0045, cap=2), seg=32, mat="rubber", M=Max, closed=True)
    # ---- tambor: boca rolada, envolvente con estampado, alzadores (solo se ve por el vidrio; la cara exterior va oculta)
    prof = [(0.0, -0.166), (0.2405, -0.166)]
    nz = 7
    for i in range(nz + 1):
        prof.append((0.243, -0.152 + (0.192 + 0.152) * i / nz))
    prof += [(0.2405, 0.197), (0.165, 0.208), (0.1505, 0.2145), (0.157, 0.2195), (0.2475, 0.203), (0.2475, -0.172), (0.0, -0.172)]
    q0, q1 = 2, 2 + nz
    lathe(mb, prof, seg=28, mat="steel", M=Max,
          rmod=lambda i, a, rr, z: rr - (0.0016 * _drum_bump(a, z) if q0 <= i <= q1 else 0.0))
    for k in range(3):
        a = PI / 2 + 2 * PI * k / 3
        Ml = Max @ _Rz(math.degrees(a)) @ _T(0.243, 0, 0)
        loops = []
        for zz in (-0.15, -0.146, 0.186, 0.19):
            sc = 0.75 if zz in (-0.15, 0.19) else 1.0
            loops.append([(0.002 - 0.036 * sc * math.sin(PI * j / 6) ** 1.5, 0.026 * sc * math.cos(PI * j / 6), zz) for j in range(7)])
        skin(mb, loops, "steel", Ml)
    # ---- puerta: aro, vidrio en cazuela, bisagra y jaladera
    Mdr = _T(0, -0.3005, 0.42) @ _Rx(90)
    ring = [(0.176, 0.0), (0.236, 0.0), (0.2405, 0.008), (0.241, 0.022), (0.2385, 0.0335), (0.232, 0.0405), (0.222, 0.0443),
            (0.205, 0.0458), (0.186, 0.0452), (0.1725, 0.041), (0.1640, 0.0300), (0.1612, 0.0170), (0.166, 0.003)]
    lathe(mb, ring, seg=40, mat="plastic", M=Mdr, closed=True)
    lathe(mb, _circle_prof(0.2275, 0.0425, 0.0042, 5), seg=40, mat="aluminium", M=Mdr, closed=True)
    lathe(mb, [(0.0, 0.0215), (0.09, 0.0228), (0.1625, 0.0300), (0.1655, 0.0262), (0.152, 0.0005), (0.11, -0.028), (0.05, -0.048),
               (0.0, -0.053)], seg=40, mat="glass", M=Mdr)
    # jaladera (lado derecho): concha con hueco para los dedos
    slab(mb, Mdr @ _T(0.229, 0.0, 0.004) @ _Rz(90), 0.12, 0.034, 0.038, rc=0.012, re=0.007, re0=0.0, mat="plastic", nc=3, ne=2)
    Mj = Mdr @ _T(0.2505, 0.0, 0.019) @ _Rz(90)                                        # barra de agarre con hueco para los dedos
    slab(mb, Mj, 0.15, 0.024, 0.028, rc=0.0105, re=0.008, re0=0.004, mat="plastic", nc=4, ne=2)
    slab(mb, Mj @ _T(0, -0.0035, 0.028 - 0.0004), 0.11, 0.008, 0.0023, rc=0.0035, re=0.0008, mat="aluminium", nc=2, ne=1, re0=0.0)
    # bisagra izquierda: base atornillada al panel, barril vertical y dos brazos a la puerta
    Mb = _T(-0.2585, -0.298, 0.42) @ _Rx(90)
    slab(mb, Mb @ _T(0, 0, -0.0004), 0.03, 0.16, 0.0075, rc=0.006, re=0.002, mat="aluminium", nc=3, ne=2)
    for z in (-0.06, 0.06):
        screw(mb, Mb @ _T(0, z, 0.0071), r=0.004, seg=8)
    lathe(mb, [(0.0, -0.075), (0.0075, -0.075), (0.0085, -0.072), (0.0085, 0.072), (0.0075, 0.075), (0.0, 0.075)], seg=12,
          mat="aluminium", M=_T(-0.2585, -0.3155, 0.42))
    for z in (-0.045, 0.045):
        mb.box((-0.2585, -0.322, 0.42 + z - 0.012), (-0.224, -0.309, 0.42 + z + 0.012), "aluminium", bevel=0.003, seg=1)
    # ---- niveladores
    for (x, y) in ((-0.25, -0.245), (0.25, -0.245), (-0.25, 0.245), (0.25, 0.245)):
        foot_leveler(mb, _T(x, y, 0.0), r=0.019, h=zb + 0.004, lite=True)
    # ---- servicio trasero (contra el muro): válvula con codo y manguera, desagüe con gancho guía, cordón — solo volumen
    yv = yb + 0.0027
    Mv = _T(-0.20, yv, 0.765) @ _Rx(-90)
    slab(mb, Mv @ _T(0, 0, -0.0032), 0.05, 0.04, 0.0102, rc=0.006, re=0.002, mat="plastic", nc=2, ne=1)
    lathe(mb, [(0.0, 0.0068), (0.0062, 0.0068), (0.0062, 0.0135), (0.0, 0.0135)], seg=8, mat="aluminium", M=Mv)
    lathe(mb, [(0.0, 0.0095), (0.0118, 0.0095), (0.0118, 0.0195), (0.0, 0.0195)], seg=6, mat="aluminium", M=Mv, phase=PI / 6)
    ye = yv + 0.0215                                                                  # codo metálico de 90° y casquillo
    mb.tube(_dedupe(fillet([(-0.20, yv + 0.019, 0.765), (-0.20, ye, 0.765), (-0.20, ye, 0.735)], 0.007, 4)), 0.0072, seg=8,
            mat="aluminium")
    lathe(mb, [(0.0, 0.0), (0.0098, 0.0), (0.0098, 0.02), (0.0, 0.02)], seg=8, mat="aluminium", M=_T(-0.20, ye, 0.717))
    hose(mb, [(-0.20, ye, 0.72), (-0.20, ye, 0.40), (-0.205, ye, 0.0088), (-0.311, ye - 0.004, 0.0088)], 0.0082, bend=0.05,
         mat="rubber", seg=6, nseg=4)
    yd = yv + 0.016
    lathe(mb, [(0.0, -0.0003), (0.019, -0.0003), (0.0195, 0.0025), (0.0125, 0.0045), (0.0, 0.0045)], seg=10, mat="rubber",
          M=_T(0.18, yv, 0.11) @ _Rx(-90))                                                               # pasamuros
    hp = [(0.18, yv - 0.02, 0.11), (0.18, yd, 0.11), (0.18, yd, 0.79), (0.235, yd, 0.79), (0.235, yd, 0.70), (0.25, yd, 0.0115),
          (0.312, yd, 0.0115)]
    hose(mb, hp, 0.0115, bend=0.03, mat="plastic", seg=6, nseg=4)
    Mg = _T(0.2075, yv, 0.72) @ _Rx(-90)                                              # gancho guía (dos abrazaderas)
    slab(mb, Mg @ _T(0, 0, -0.0005), 0.095, 0.034, 0.004, rc=0.006, re=0.0015, mat="plastic", nc=1, ne=1)
    for x in (0.18, 0.235):
        st = [(x - 0.0135, yv + 0.003, 0.72)] + [(x - 0.0135 * math.cos(PI * j / 4), yd + 0.0135 * math.sin(PI * j / 4), 0.72)
                                                  for j in range(5)] + [(x + 0.0135, yv + 0.003, 0.72)]
        mb.sweep([(-0.0012, -0.006), (0.0012, -0.006), (0.0012, 0.006), (-0.0012, 0.006)], _dedupe(st), mat="plastic",
                 normal=(0, 0, 1))
    lathe(mb, [(0.0, -0.0003), (0.008, -0.0003), (0.008, 0.008), (0.0055, 0.018), (0.0, 0.018)], seg=8, mat="cable",
          M=_T(-0.06, yv, 0.62) @ _Rx(-90))
    hose(mb, [(-0.06, yv + 0.008, 0.62), (-0.06, yv + 0.021, 0.62), (-0.06, yv + 0.021, 0.20), (-0.09, yv + 0.021, 0.0045),
              (-0.311, yv + 0.019, 0.0045)], 0.0042, bend=0.05, mat="cable", seg=5, nseg=4)
    return mb


def rr_pts_open(w, h):
    """Perfil de fleje (rectángulo de esquinas redondeadas) para mb.sweep: w a lo largo de la normal, h de espesor."""
    return [(y, x) for (x, y) in rr_pts(w, h, min(w, h) * 0.45, 2)]


def rpoly_pts(P, R, delta=0.0, n=4):
    """Contorno de polígono (esquinas P en sentido antihorario) con filetes de radio R por esquina, desplazado `delta` hacia
    adentro (las esquinas cóncavas crecen, las convexas se achican). n + 1 puntos por esquina: lazos compatibles entre sí."""
    m = len(P)
    P = [Vector((float(p[0]), float(p[1]))) for p in P]
    N = []
    for i in range(m):
        d = (P[(i + 1) % m] - P[i]).normalized()
        N.append(Vector((-d.y, d.x)))
    Q = [P[i] + (N[i - 1] + N[i]) * (delta / (1 + N[i - 1].dot(N[i]))) for i in range(m)]
    out = []
    for i in range(m):
        q, a, b = Q[i], Q[i - 1], Q[(i + 1) % m]
        e0, e1 = q - a, b - q
        convex = (e0.x * e1.y - e0.y * e1.x) > 0
        rho = max((R[i] - delta) if convex else (R[i] + delta), 2e-4)
        d0, d1 = (a - q).normalized(), (b - q).normalized()
        ang = math.acos(max(-1.0, min(1.0, d0.dot(d1))))
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
        for k in range(n + 1):
            aa = a0 + da * k / n
            out.append((C.x + rho * math.cos(aa), C.y + rho * math.sin(aa)))
    return out


def pslab(mb, M, P, R, L, re=0.004, mat="sign_white", n=4, ne=3, re0=None, cap0=True, cap1=True):
    """Prisma de contorno poligonal redondeado (rpoly_pts) en el plano XY local, extruido de z = 0 a L con cantos re / re0."""
    re0 = re if re0 is None else re0
    loops = [[(x, y, z) for (x, y) in rpoly_pts(P, R, dl, n)] for (dl, z) in _edge_levels(L, min(re, L * 0.49), min(re0, L * 0.49), ne)]
    return skin(mb, loops, mat, M, cap0=cap0, cap1=cap1)


# matriz de ejes: (u, v, w) locales -> (Y, Z, X) mundiales (perfil lateral en YZ extruido a lo largo de X)
M_YZX = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def _paper_note(mb, M, w, h, rr, mag_mat):
    """Hoja de papel sobre una superficie (plano XY de M, +Z afuera) con imán redondo y renglones escritos."""
    slab(mb, M @ _T(0, 0, -0.0002), w, h, 0.0017, rc=0.0015, re=0.0005, mat="paper", nc=2, ne=1, re0=0.0)
    nl = int(rr.integers(3, 7))
    for k in range(nl):
        L = w * float(rr.uniform(0.45, 0.8))
        y = h / 2 - 0.028 - k * 0.012
        if y < -h / 2 + 0.01:
            break
        mb.box((-w / 2 + 0.012, y, 0.0008), (-w / 2 + 0.012 + L, y + 0.0016, 0.0031), "cable", bevel=0.0, m=M)
    lathe(mb, [(0.0105, 0.0012), (0.0112, 0.0025), (0.0112, 0.0058), (0.0098, 0.0075), (0.0, 0.0077)], seg=14, mat=mag_mat,
          M=M @ _T(0, h / 2 - 0.014, 0))


# ===================================================================================================== refrigerador
def fridge(seed=0):
    """Refrigerador doméstico de dos puertas (congelador arriba), 0,64 × 0,66 × 1,65: gabinete de lámina con perfil en L (nicho
    trasero del compresor), puertas de canto redondeado con empaque magnético de fuelle, jaladeras de barra con bases, bisagras
    superior / intermedia / inferior con pernos, rejilla inferior de ventilación con persianas, niveladores y rodajas traseras,
    condensador de serpentín con alambres, compresor sobre rieles con gromets, filtro deshidratador, tuberías y cordón; notas
    con imanes en la puerta (según semilla)."""
    r = rng(seed)
    mb = MB()
    W = 0.636
    yf, yb, zb, zt = -0.290, 0.335, 0.035, 1.648
    yby, zby = 0.17, 0.25                                                         # nicho del compresor (atrás, abajo)
    prof = [(yf, zb), (yby, zb), (yby, zby), (yb, zby), (yb, zt), (yf, zt)]
    pslab(mb, _T(-W / 2, 0, 0) @ M_YZX, prof, [0.006, 0.006, 0.012, 0.006, 0.016, 0.022], W, re=0.016, mat="sign_white", n=4,
          ne=3)
    for sx in (-1, 1):                                                            # costados del nicho
        x0 = sx * W / 2 - (0.0016 if sx > 0 else 0.0)
        pslab(mb, _T(x0, 0, 0) @ M_YZX, [(yby + 0.004, zb), (yb, zb), (yb, zby - 0.004), (yby + 0.004, zby - 0.004)],
              [0.003, 0.006, 0.006, 0.003], 0.0016, re=0.0005, mat="sign_white", n=2, ne=1)
    # puertas (congelador / alimentos) con empaque de fuelle
    doors = ((1.165, 1.645), (0.125, 1.155))
    for (z0, z1) in doors:
        zc, h = (z0 + z1) / 2, z1 - z0
        slab(mb, _T(0, -0.298, zc) @ _Rx(90), 0.634, h, 0.036, rc=0.02, re=0.011, re0=0.004, mat="sign_white", nc=4, ne=3)
        path = [(x, -0.294, zc + z) for (x, z) in rr_pts(0.634 - 0.036, h - 0.036, 0.014, 3)]
        mb.sweep([(u, v) for (u, v) in rr_pts(0.017, 0.0083, 0.0036, 1)], path, mat="rubber", closed_path=True, normal=(0, 1, 0))
    # jaladeras de barra
    for (za, zz) in ((1.205, 1.395), (0.865, 1.105)):
        hose(mb, [(0.262, -0.331, za), (0.262, -0.3488, za), (0.262, -0.3488, zz), (0.262, -0.331, zz)], 0.0095, bend=0.016,
             mat="aluminium", seg=12, nseg=6)
        for z in (za, zz):
            slab(mb, _T(0.262, -0.3336, z) @ _Rx(90), 0.03, 0.036, 0.0075, rc=0.009, re=0.003, re0=0.0, mat="plastic", nc=2, ne=2)
    # bisagras: superior (placa + tapa), intermedia (en la junta entre puertas), inferior (escuadra atornillada)
    mb.box((-0.318, -0.336, zt - 0.0005), (-0.250, -0.262, zt + 0.0035), "steel", bevel=0.0012, seg=1)
    slab(mb, _T(-0.284, -0.278, zt + 0.0032), 0.064, 0.05, 0.011, rc=0.01, re=0.004, re0=0.0, mat="plastic", nc=3, ne=2)
    for x in (-0.300, -0.268):
        screw(mb, _T(x, -0.322, zt + 0.0035), r=0.0035, seg=8)
    lathe(mb, [(0.0, 1.638), (0.0055, 1.638), (0.0055, zt + 0.004), (0.0045, zt + 0.0055), (0.0, zt + 0.0058)], seg=8, mat="steel",
          M=_T(-0.298, -0.318, 0.0))
    mb.box((-0.318, -0.337, 1.1567), (-0.268, -0.287, 1.1633), "steel", bevel=0.0015, seg=1)
    lathe(mb, [(0.0, 1.148), (0.0052, 1.148), (0.0052, 1.172), (0.0, 1.172)], seg=8, mat="steel", M=_T(-0.298, -0.318, 0.0))
    mb.box((-0.318, -0.337, 0.112), (-0.262, -0.287, 0.118), "steel", bevel=0.0015, seg=1)
    mb.box((-0.318, -0.2935, 0.058), (-0.262, -0.2894, 0.118), "steel", bevel=0.0012, seg=1)
    for z in (0.072, 0.1):
        screw(mb, _T(-0.29, -0.2935, z) @ _Rx(90), r=0.004, seg=8)
    lathe(mb, [(0.0, 0.110), (0.0052, 0.110), (0.0052, 0.132), (0.0, 0.132)], seg=8, mat="steel", M=_T(-0.298, -0.318, 0.0))
    # rejilla inferior (zoclo) con persianas y ranuras reales
    Mg = _T(0.025, -0.2903, 0.078) @ _Rx(90)
    louver_grille(mb, Mg, 0.50, 0.072, 6, mat="plastic", back_mat="cable", t=0.014, frame=0.009, slat_ang=40, depth=-0.0004, nr=24)
    for x in (-0.235, 0.235):
        screw(mb, Mg @ _T(x, 0, 0.0138), r=0.0032, seg=8)
    # patas: niveladores al frente, rodajas atrás (bajo el gabinete)
    for x in (-0.28, 0.28):
        foot_leveler(mb, _T(x, -0.25, 0.0), r=0.017, h=zb + 0.004, lite=True)
        Mw = _T(x, 0.13, 0.0)
        for s_ in (-1, 1):
            mb.box((s_ * 0.0105 - 0.0012, -0.012, 0.012), (s_ * 0.0105 + 0.0012, 0.012, zb + 0.0015), "steel", bevel=0.0, seg=1, m=Mw)
        mb.box((-0.0135, -0.014, zb - 0.003), (0.0135, 0.014, zb + 0.001), "steel", bevel=0.0, seg=1, m=Mw)
        lathe(mb, [(0.004, -0.0085), (0.0145, -0.0085), (0.0162, -0.004), (0.0162, 0.004), (0.0145, 0.0085), (0.004, 0.0085)], seg=12,
              mat="plastic", M=Mw @ _T(0, 0, 0.0162) @ _Ry(90), closed=True)
        mb.cyl(Mw @ Vector((-0.0125, 0, 0.0162)), Mw @ Vector((0.0125, 0, 0.0162)), 0.0035, seg=6, mat="steel")
    # ---- espalda contra el muro (no se ve): condensador, compresor y tuberías en versión de volumen (mantienen la caja)
    yc = 0.3515
    rows = 10
    zs = [0.34 + k * 0.1255 for k in range(rows)]
    pts = []
    for k, z in enumerate(zs):
        xa, xb_ = (-0.235, 0.235) if k % 2 == 0 else (0.235, -0.235)
        pts += [(xa, yc, z), (xb_, yc, z)]
    mb.tube(_dedupe(fillet(pts, 0.06, 3)), 0.0024, seg=4, mat="cable")
    for k in range(12):
        x = -0.2185 + k * 0.0397
        mb.cyl((x, yc + 0.0029, zs[0] - 0.02), (x, yc + 0.0029, zs[-1] + 0.02), 0.0008, seg=3, mat="cable")
    for x in (-0.257, 0.257):
        mb.box((x - 0.006, yc - 0.002, zs[0] - 0.035), (x + 0.006, yc + 0.0035, zs[-1] + 0.035), "cable", bevel=0.0, seg=1)
        for z in (zs[0] - 0.02, zs[-1] + 0.02):
            mb.box((x - 0.004, yb - 0.0005, z - 0.012), (x + 0.004, yc - 0.0015, z + 0.012), "cable", bevel=0.0, seg=1)
    xc, ycm = -0.06, 0.255
    for yr in (0.205, 0.305):
        mb.box((-W / 2 + 0.001, yr - 0.012, zb), (W / 2 - 0.001, yr + 0.012, zb + 0.02), "steel", bevel=0.0, seg=1)
    mb.box((xc - 0.085, ycm - 0.065, zb + 0.02), (xc + 0.085, ycm + 0.065, zb + 0.031), "steel", bevel=0.0, seg=1)
    lathe(mb, [(0.0, zb + 0.03), (0.071, zb + 0.03), (0.0775, 0.09), (0.0775, 0.15), (0.066, 0.19), (0.035, 0.208), (0.0, 0.211)],
          seg=16, mat="cable", M=_T(xc, ycm, 0))
    mb.box((xc + 0.07, ycm - 0.03, 0.10), (xc + 0.098, ycm + 0.03, 0.16), "plastic", bevel=0.004, seg=1)
    for path in ([(xc + 0.02, ycm, 0.205), (xc + 0.02, ycm, 0.232), (xc + 0.02, 0.343, 0.232), (-0.235, 0.343, 0.232),
                  (-0.235, 0.343, 0.30), (-0.235, yc, zs[0])],
                 [(0.12, 0.343, 0.24), (0.12, 0.343, 0.39), (0.235, yc, 0.39), (0.235, yc, zs[-1])]):
        hose(mb, path, 0.0032, bend=0.02, mat="aluminium", seg=4, nseg=3)
    hose(mb, [(xc + 0.09, ycm, 0.115), (xc + 0.12, ycm, 0.115), (xc + 0.12, ycm, 0.006), (0.25, 0.30, 0.0045), (0.25, 0.364, 0.0045)],
         0.0042, bend=0.04, mat="cable", seg=5, nseg=3)
    # notas con imanes (según semilla)
    for k in range(int(r.integers(0, 4))):
        on_freezer = bool(r.random() < 0.35)
        zc = float(r.uniform(1.28, 1.52)) if on_freezer else float(r.uniform(0.75, 1.02))
        x = float(r.uniform(-0.2, 0.12))
        w, h = (0.1, 0.14) if r.random() < 0.5 else (0.076, 0.076)
        _paper_note(mb, _T(x, -0.334, zc) @ _Rx(90) @ _Rz(float(r.uniform(-6, 6))), w, h, r,
                    ("sign_red", "sign_blue", "paint_yellow", "sign_green")[int(r.integers(0, 4))])
    return mb


def cup(mb, M, w, d, h, t, rc=0.02, re=0.01, mat="cable", nc=4, ne=3):
    """Caja hueca con boca en z = 0 (horno, cuba): pared de espesor t, fondo en z = h, esquinas rc y fondo redondeado re.
    Sólido cerrado: las caras interiores miran hacia adentro de la cavidad."""
    rcs = rc if isinstance(rc, (tuple, list)) else (rc,) * 4

    def lp(ww, dd, rr, dl, z):
        return [(x, y, z) for (x, y) in rr_pts(ww - 2 * dl, dd - 2 * dl, tuple(max(q - dl, 3e-4) for q in rr), nc)]
    inner = []
    ri = tuple(max(q - t, 3e-4) for q in rcs)
    rei = max(re - t, 0.002)
    for (dl, z) in reversed(_edge_levels(h - t, rei, 0.0, ne)):
        inner.append(lp(w - 2 * t, d - 2 * t, ri, dl, z))
    outer = [lp(w, d, rcs, dl, z) for (dl, z) in _edge_levels(h, re, 0.0, ne)]
    return skin(mb, inner + outer, mat, M, cap0=True, cap1=True)


# ===================================================================================================== estufa
def stove(seed=0):
    """Estufa de piso de 76 cm, 4 quemadores y horno: patas cromadas con nivelador, gabinete esmaltado, cubierta con canto
    rolado y bandejas de quemador, quemadores de aluminio con puertos de flama, tapas esmaltadas y bujía de encendido, dos
    parrillas de fierro fundido con dedos de apoyo y topes de hule, tablero con 5 perillas de aleta y faldón, diagramas de
    quemador, botón de chispa e interruptor de luz; puerta de horno con ventana de doble vidrio, jaladera de barra y brazos de
    bisagra; cavidad del horno con rieles y parrilla de alambre; cajón inferior; respaldo con rejilla de ventilación; toma de gas
    con tubo y manguera."""
    r = rng(seed)
    mb = MB()
    W = 0.76
    yf, yb = -0.278, 0.30
    z0, ztop = 0.07, 0.878
    # ---- patas
    for (x, y) in ((-0.335, -0.235), (0.335, -0.235), (-0.335, 0.255), (0.335, 0.255)):
        foot_leveler(mb, _T(x, y, 0.0), r=0.017, h=0.024, lite=True)
        lathe(mb, [(0.0105, 0.016), (0.0135, 0.019), (0.0145, 0.03), (0.0155, z0 - 0.004), (0.019, z0 - 0.001), (0.019, z0 + 0.003)],
              seg=12, mat="aluminium", M=_T(x, y, 0.0), caps=False)
    # ---- gabinete abierto al frente, cubierta, respaldo
    slab(mb, _T(0, yf, (z0 + ztop) / 2) @ _Rx(-90), W - 0.002, ztop - z0, yb - yf, rc=0.01, re=0.006, re0=0.0, mat="sign_white",
         nc=4, cap0=False)
    slab(mb, _T(0, -0.016, 0.876), W, 0.568, 0.028, rc=0.014, re=0.009, re0=0.003, mat="sign_white", nc=4)
    slab(mb, _T(0, 0.284, 0.902), W, 0.032, 0.148, rc=0.008, re=0.012, re0=0.0, mat="sign_white", nc=4)
    louver_grille(mb, _T(0, 0.268, 0.93) @ _Rx(90), 0.56, 0.036, 3, mat="sign_white", back_mat="cable", t=0.008, frame=0.007,
                  slat_ang=45, depth=-0.0004, nr=24)
    for x in (-0.26, 0.26):
        screw(mb, _T(x, 0.268, 0.93) @ _Rx(90) @ _T(0, 0, 0.0078), r=0.0032, seg=8)
    # ---- tablero de mandos
    Mp = _T(0, yf, 0.8035) @ _Rx(90)
    slab(mb, Mp, W - 0.004, 0.145, 0.018, rc=(0.004, 0.004, 0.006, 0.006), re=0.004, re0=0.0015, mat="sign_white", nc=3)
    slab(mb, Mp @ _T(0, -0.0695, 0.0175), W - 0.03, 0.005, 0.0016, rc=0.002, re=0.0006, mat="aluminium", nc=2, ne=1, re0=0.0)
    fz = 0.018
    burners = [(-0.18, -0.12, 0.042), (0.18, -0.12, 0.036), (-0.18, 0.12, 0.036), (0.18, 0.12, 0.030)]
    knob_x = [(-0.30, 2), (-0.19, 0), (0.0, None), (0.19, 1), (0.30, 3)]
    for (kx, bi) in knob_x:
        Mk = Mp @ _T(kx, -0.004, fz)
        knob(mb, Mk @ _Rz(float(r.choice([0.0, 0.0, 0.0, 90.0, 140.0])) if bi is not None else float(r.uniform(0, 200))),
             r=0.0185, h=0.012, mat="plastic", skirt=(0.0255, 0.0035), skirt_mat="aluminium", fin=True, pointer_mat="cable", seg=16,
             skirt_seg=16, fin_nc=2, lite=True)
        mb.box((-0.0009, 0.0285, -0.0003), (0.0009, 0.035, 0.0011), "cable", bevel=0.0, m=Mk)          # marca de apagado
        for (ang, rr_) in ((90, 0.0022), (180, 0.0035)):                                               # flama baja / alta
            a = math.radians(ang + 90)
            lathe(mb, [(rr_, -0.0003), (rr_, 0.0008), (0.0, 0.0011)], seg=6, mat="cable",
                  M=Mk @ _T(0.032 * math.cos(a), 0.032 * math.sin(a), 0))
        if bi is not None:                                                                             # diagrama de quemador
            for j, (bx, by, _) in enumerate(burners):
                Md = Mp @ _T(kx + (0.0055 if bx > 0 else -0.0055), 0.054 + (0.0055 if by > 0 else -0.0055), fz)
                if j == bi:
                    lathe(mb, [(0.0034, -0.0003), (0.0034, 0.0009), (0.0, 0.0011)], seg=8, mat="cable", M=Md)
                else:
                    lathe(mb, [(0.0021, -0.0003), (0.0035, -0.0003), (0.0028, 0.001)], seg=6, mat="cable", M=Md, closed=True)
        else:
            label(mb, "OVEN", 0.0075, "cable", Mp @ _T(kx, 0.048, fz), res=1)
    for (bx, s_) in ((-0.095, "SPARK"), (0.095, "LIGHT")):
        lathe(mb, [(0.0115, -0.0003), (0.012, 0.0015), (0.0105, 0.0028), (0.0088, 0.0018), (0.0088, -0.0003)], seg=16,
              mat="aluminium", M=Mp @ _T(bx, -0.004, fz), closed=True)
        if s_ == "SPARK":
            lathe(mb, [(0.0082, -0.0003), (0.0082, 0.005), (0.0072, 0.0068), (0.0, 0.0072)], seg=16, mat="sign_red",
                  M=Mp @ _T(bx, -0.004, fz))
        else:
            slab(mb, Mp @ _T(bx, -0.004, fz - 0.0003) @ _Rx(-8), 0.012, 0.014, 0.006, rc=0.002, re=0.0015, mat="plastic", nc=2, ne=2)
        label(mb, s_, 0.0068, "cable", Mp @ _T(bx, 0.022, fz), res=1)
    # ---- puerta del horno: ventana de doble vidrio, jaladera, brazos de bisagra
    Md = _T(0, -0.279, 0.0) @ _Rx(90)
    rrframe(mb, Md, (0.0, 0.43, 0.744, 0.58, 0.012), (0.0, 0.455, 0.41, 0.21, 0.022), 0.036, re_o=0.008, re_i=0.006, n=4,
            mat="sign_white", ne=3)
    for (yy, t) in ((-0.3075, 0.004), (-0.2835, 0.004)):
        mb.box((-0.212, yy - t, 0.343), (0.212, yy, 0.567), "glass", bevel=0.0, seg=1)
    rrframe(mb, Md @ _T(0, 0, 0.0358), (0.0, 0.455, 0.456, 0.256, 0.03), (0.0, 0.455, 0.41, 0.21, 0.022), 0.0022, re_o=0.0012,
            re_i=0.0008, n=4, mat="cable", ne=1)
    hp = [(-0.30, -0.312, 0.675), (-0.30, -0.3385, 0.675), (0.30, -0.3385, 0.675), (0.30, -0.312, 0.675)]
    hose(mb, hp, 0.0105, bend=0.02, mat="aluminium", seg=12, nseg=6)
    for x in (-0.30, 0.30):
        lathe(mb, [(0.0, -0.0003), (0.017, -0.0003), (0.0175, 0.003), (0.0145, 0.007), (0.012, 0.011), (0.0, 0.011)], seg=12,
              mat="aluminium", M=_T(x, -0.315, 0.675) @ _Rx(90))
    for x in (-0.338, 0.338):
        mb.box((x - 0.006, -0.296, 0.1365), (x + 0.006, -0.24, 0.1405), "steel", bevel=0.0008, seg=1)
    # ---- cavidad del horno (vista por la ventana): cuba esmaltada, rieles laterales, parrilla de alambre
    cup(mb, _T(0, -0.2765, 0.43) @ _Rx(-90), 0.6, 0.52, 0.49, 0.008, rc=0.03, re=0.025, mat="cable", nc=4)
    for z in (0.30, 0.40, 0.50):
        for sx in (-1, 1):
            mb.box((sx * 0.292 - 0.004, -0.25, z - 0.006), (sx * 0.292 + 0.004, 0.18, z + 0.006), "cable", bevel=0.003, seg=1)
    zr = 0.406 + 0.0045
    mb.tube(_dedupe([(x, y, zr) for (x, y) in rr_pts(0.56, 0.42, 0.02, 3)] + [(0.28 - 0.0002, 0.21 - 0.02, zr)]), 0.0028, seg=6,
            mat="steel", caps=True)
    for k in range(13):
        x = -0.252 + k * 0.042
        mb.cyl((x, -0.21, zr + 0.0042), (x, 0.21, zr + 0.0042), 0.0019, seg=5, mat="steel")
    for y in (-0.10, 0.0, 0.10):
        mb.cyl((-0.28, y, zr - 0.004), (0.28, y, zr - 0.004), 0.0019, seg=5, mat="steel")
    # ---- cajón inferior con jalón
    Mc = _T(0, -0.279, 0.105) @ _Rx(90)
    slab(mb, Mc, W - 0.016, 0.059, 0.022, rc=0.005, re=0.005, re0=0.0, mat="sign_white", nc=3)
    holed(mb, Mc @ _T(0, 0.014, 0.022), (0, 0, 0.13, 0.0085, 0.006), (0, 0, 0.12, 0.0035, 0.003), 0.004, re_o=0.0015,
          re_i=0.001, n=24, mat="aluminium", ne=1)
    mb.box((-0.12, 0.0105, 0.018), (0.12, 0.0175, 0.0236), "cable", bevel=0.0, m=Mc)
    # ---- quemadores: bandeja esmaltada, base con puertos de flama, tapa, bujía
    zc = 0.904
    for (bx, by, rq) in burners:
        Mb = _T(bx, by, 0.0)
        lathe(mb, [(rq * 0.86, zc - 0.0012), (rq * 0.9, zc + 0.003), (rq * 0.97, zc + 0.0045), (rq + 0.05, zc - 0.0012)], seg=24,
              mat="enamel", M=Mb, closed=True)
        ports = 10
        lathe(mb, [(rq * 0.8, zc - 0.0005), (rq * 0.8, zc + 0.008), (rq * 0.9, zc + 0.0095), (rq * 0.9, zc + 0.0165), (0.0, zc + 0.0178)],
              seg=30, mat="aluminium", M=Mb, caps=False,
              rmod=lambda i, a, rr, z: rr - (0.0024 * (0.5 + 0.5 * math.cos(ports * a)) ** 6 if i in (2, 3) else 0.0))
        lathe(mb, [(rq * 0.88, zc + 0.0176), (rq * 0.97, zc + 0.0188), (rq * 0.98, zc + 0.022), (rq * 0.9, zc + 0.0262),
                   (rq * 0.6, zc + 0.0282), (0.0, zc + 0.0286)], seg=28, mat="cable", M=Mb, caps=False)
        a = math.radians(-35)
        Mi = Mb @ _T((rq * 0.9 + 0.007) * math.cos(a), (rq * 0.9 + 0.007) * math.sin(a), 0.0)
        lathe(mb, [(0.0042, zc - 0.001), (0.0042, zc + 0.008), (0.0028, zc + 0.012), (0.0, zc + 0.0125)], seg=8,
              mat="sign_white", M=Mi, caps=False)
        mb.tube([tuple(Mi @ Vector((0, 0, zc + 0.011))), tuple(Mi @ Vector((-0.0035 * math.cos(a), -0.0035 * math.sin(a), zc + 0.016)))],
                0.0007, seg=5, mat="steel")
    # ---- parrillas de fierro fundido (2), con dedos de apoyo y topes de hule
    for sx in (-1, 1):
        xc = sx * 0.1875
        frame = [(xc + x, -0.012 + y, 0.9195) for (x, y) in rr_pts(0.352, 0.507, 0.024, 3)]
        mb.sweep(rr_profile(0.016, 0.019, 0.005, n=2), frame, mat="cable", closed_path=True, normal=(0, 0, 1))
        rtube_p(mb, (xc - 0.169, -0.012, 0.9195), (xc + 0.169, -0.012, 0.9195), 0.016, 0.019, "cable", n=1)
        for (bx, by, rq) in burners:
            if (bx > 0) != (sx > 0):
                continue
            tip = 0.05
            yfr, ybk = (-0.2655, -0.012) if by < 0 else (-0.012, 0.2415)
            for (p0, p1) in (((xc - 0.17, by, 0.9205), (bx - tip, by, 0.9300)), ((xc + 0.17, by, 0.9205), (bx + tip, by, 0.9300)),
                             ((bx, yfr, 0.9205), (bx, by - tip, 0.9300)), ((bx, ybk, 0.9205), (bx, by + tip, 0.9300))):
                rtube_p(mb, p0, p1, 0.015, 0.02, "cable", taper=0.72, n=1)
        for (x, y) in ((xc - 0.16, -0.255), (xc + 0.16, -0.255), (xc - 0.16, 0.231), (xc + 0.16, 0.231)):
            lathe(mb, [(0.0068, zc - 0.0005), (0.0072, zc + 0.002), (0.006, zc + 0.0046), (0.0, zc + 0.0048)],
                  seg=8, mat="rubber", M=_T(x, y, 0.0), caps=False)
    # ---- servicio trasero (contra el muro, no se ve): tubo de gas con tuerca y manguera (marca la caja)
    lathe(mb, [(0.0, -0.0003), (0.016, -0.0003), (0.016, 0.004), (0.0, 0.004)], seg=6, mat="steel", M=_T(-0.30, yb, 0.80) @ _Rx(-90),
          phase=PI / 6)
    gp = [(-0.30, yb + 0.002, 0.80), (-0.30, yb + 0.012, 0.80), (-0.30, yb + 0.012, 0.13)]
    mb.tube(_dedupe(fillet(gp, 0.012, 3)), 0.0066, seg=6, mat="steel")
    hexnut(mb, _T(-0.30, yb + 0.012, 0.115), s=0.02, h=0.016, mat="aluminium")
    hose(mb, [(-0.30, yb + 0.012, 0.118), (-0.30, yb + 0.012, 0.05), (-0.33, yb + 0.012, 0.009), (-0.392, yb + 0.012, 0.009)],
         0.009, bend=0.04, mat="paint_yellow", seg=6, nseg=4)
    return mb


def rtube_p(mb, p0, p1, w, h, mat, taper=1.0, r=None, n=2):
    """Barra de sección rectangular redondeada de p0 a p1 (ancho w horizontal, alto h vertical), con ahusamiento opcional hacia p1."""
    p0, p1 = Vector(p0), Vector(p1)
    X = (p1 - p0).normalized()
    Z = Vector((0, 0, 1))
    Z = (Z - X * X.dot(Z)).normalized()
    Y = Z.cross(X)
    M = Matrix(((X.x, Y.x, Z.x, p0.x), (X.y, Y.y, Z.y, p0.y), (X.z, Y.z, Z.z, p0.z), (0, 0, 0, 1)))
    L = (p1 - p0).length
    rr = r if r is not None else min(w, h) * 0.35
    loops = []
    for (x, k) in ((0.0, 1.0), (L * 0.5, 0.5 * (1 + taper)), (L - rr * taper * 0.6, taper)):
        loops.append([(x, a * k, b * k) for (a, b) in rr_pts(w, h, rr, n)])
    loops.append([(L, a * taper * 0.8, b * taper * 0.8) for (a, b) in rr_pts(w, h, rr, n)])
    skin(mb, loops, mat, M)


# ===================================================================================================== despachador de agua
def _bottle_prof():
    """Perfil del garrafón de 20 L invertido (r, z) desde la boca (abajo) hasta el fondo con domo (arriba)."""
    pr = [(0.0, 1.028), (0.0215, 1.028), (0.0228, 1.035), (0.0232, 1.054), (0.0335, 1.056), (0.0338, 1.062), (0.0245, 1.065),
          (0.026, 1.072), (0.04, 1.082), (0.062, 1.094), (0.088, 1.106), (0.112, 1.118), (0.128, 1.13), (0.134, 1.142),
          (0.1345, 1.16)]
    for zg in (1.19, 1.25, 1.31, 1.37):
        pr += [(0.1345, zg - 0.012), (0.131, zg - 0.006), (0.1295, zg), (0.131, zg + 0.006), (0.1345, zg + 0.012)]
    pr += [(0.1345, 1.395), (0.132, 1.41), (0.124, 1.421), (0.108, 1.428), (0.085, 1.4295), (0.066, 1.4285), (0.05, 1.421),
           (0.028, 1.414), (0.0, 1.412)]
    return pr


def water_dispenser():
    """Despachador de garrafón de piso (0,32 × 0,32 × 1,0 + garrafón de 20 L): gabinete con frente de cantos muy redondeados y
    nicho de llaves, llaves de palanca (fría azul / caliente roja con seguro) y boquillas, charola de goteo removible con rejilla
    de ranuras, puerta inferior con jalón y pernos, rejillas laterales, tapa superior con asiento del garrafón; garrafón con
    hombros nervados, anillos, cuello con collarín y tapa estriada; condensador y cordón atrás, interruptores, regatones."""
    mb = MB()
    zt = 0.975
    for (x, y) in ((-0.125, -0.125), (0.125, -0.125), (-0.125, 0.125), (0.125, 0.125)):        # regatones (sin fondo: van al piso)
        lathe(mb, [(0.016, 0.0), (0.018, 0.003), (0.018, 0.012), (0.014, 0.0205), (0.0, 0.0205)], seg=10, mat="rubber",
              M=_T(x, y, 0.0), caps=False)
    slab(mb, _T(0, 0.029, 0.02), 0.316, 0.258, zt - 0.02, rc=(0.03, 0.03, 0.004, 0.004), re=0.006, re0=0.004, mat="sign_white",
         nc=4, ne=2)
    Mf = _T(0, -0.0995, 0.0) @ _Rx(90)                                                 # frente con nicho (local y = z mundial)
    rrframe(mb, Mf, (0.0, (0.02 + zt) / 2, 0.316, zt - 0.02, 0.02), (0.0, 0.725, 0.20, 0.27, 0.035), 0.0585, re_o=0.026,
            re_i=0.008, n=5, ne=4, mat="sign_white")
    slab(mb, _T(0, 0.0, zt - 0.003), 0.318, 0.318, 0.018, rc=0.03, re=0.006, re0=0.002, mat="plastic", nc=4, ne=2)
    lathe(mb, [(0.034, 0.986), (0.034, 0.996), (0.058, 1.0075), (0.07, 1.0085), (0.0775, 1.0035), (0.0785, 0.986)], seg=32,
          mat="plastic", closed=True)
    # garrafón: tapa estriada, cuello con collarín, hombros nervados, anillos, domo del fondo
    lathe(mb, [(0.026, 0.993), (0.0295, 0.997), (0.0295, 1.026), (0.0275, 1.031), (0.0, 1.031)], seg=32, mat="sign_blue", caps=False,
          rmod=lambda i, a, rr, z: rr - (0.0009 * (0.5 + 0.5 * math.cos(16 * a)) ** 2 if i in (1, 2) else 0.0))
    pr = [(0.0, 1.028), (0.0228, 1.03), (0.0232, 1.054), (0.0335, 1.056), (0.0338, 1.062), (0.0245, 1.065), (0.026, 1.072),
          (0.045, 1.085), (0.075, 1.1), (0.105, 1.115), (0.126, 1.128), (0.1345, 1.145)]
    sh0, sh1 = 7, 11
    for zg in (1.19, 1.25, 1.31, 1.37):
        pr += [(0.1345, zg - 0.012), (0.131, zg - 0.006), (0.1295, zg), (0.131, zg + 0.006), (0.1345, zg + 0.012)]
    pr += [(0.1345, 1.395), (0.13, 1.414), (0.115, 1.426), (0.085, 1.4295), (0.06, 1.427), (0.03, 1.414), (0.0, 1.412)]

    def rib(i, a, rr, z):
        if sh0 <= i <= sh1:
            k = math.sin(PI * (i - sh0 + 0.5) / (sh1 - sh0 + 1))
            return rr + 0.0045 * k * (0.5 + 0.5 * math.cos(12 * a)) ** 3
        return rr
    lathe(mb, pr, seg=48, mat="glass", rmod=rib)
    # nicho: llaves de palanca, boquillas, seguro de la caliente, charola con rejilla
    for (x, col) in ((-0.05, "sign_blue"), (0.05, "sign_red")):
        slab(mb, _T(x, -0.1, 0.752) @ _Rx(90), 0.036, 0.052, 0.052, rc=0.009, re=0.007, re0=0.0, mat="plastic", nc=3, ne=2)
        lathe(mb, [(0.0085, 0.0), (0.0085, 0.006), (0.006, 0.01), (0.0058, 0.026), (0.0068, 0.03), (0.0068, 0.034), (0.0045, 0.034),
                   (0.0, 0.031)], seg=12, mat="plastic", M=_T(x, -0.136, 0.731) @ _Rx(180), caps=False)
        Ml = _T(x, -0.1515, 0.776) @ _Rx(-8)
        slab(mb, Ml @ _T(0, -0.026, -0.0005) @ _Rx(90), 0.032, 0.05, 0.0065, rc=0.008, re=0.0028, mat=col, nc=3, ne=2)
        mb.cyl(Ml @ Vector((-0.016, -0.004, 0.0)), Ml @ Vector((0.016, -0.004, 0.0)), 0.0032, seg=8, mat="plastic")
        for k in range(4):
            mb.box((-0.011, -0.04 + k * 0.0055, -0.0075), (0.011, -0.0372 + k * 0.0055, -0.0062), col, bevel=0.0, seg=1, m=Ml)
        if col == "sign_red":
            slab(mb, _T(x, -0.124, 0.778), 0.014, 0.022, 0.006, rc=0.004, re=0.002, re0=0.0, mat="sign_red", nc=2, ne=2)
    ytf, ytb = -0.198, -0.103
    cup(mb, _T(0, (ytf + ytb) / 2, 0.613) @ _Rx(180), 0.19, ytb - ytf, 0.022, 0.0028, rc=(0.006, 0.006, 0.03, 0.03), re=0.004,
        mat="plastic", nc=4, ne=2)
    for k in range(7):
        y = ytf + 0.012 + k * 0.0118
        w = 0.19 - 0.012 - (0.026 * max(0.0, 1 - (y - ytf) / 0.03) if k < 2 else 0.0)
        mb.box((-w / 2, y, 0.6085), (w / 2, y + 0.0058, 0.6115), "plastic", bevel=0.0012, seg=1)
    mb.box((-0.088, ytf + 0.006, 0.6072), (-0.082, ytb - 0.003, 0.6101), "plastic", bevel=0.0, seg=1)
    mb.box((0.082, ytf + 0.006, 0.6072), (0.088, ytb - 0.003, 0.6101), "plastic", bevel=0.0, seg=1)
    # rótulos y testigos sobre el nicho
    Mt = _T(0, -0.158, 0.0) @ _Rx(90)
    label(mb, "COLD", 0.016, "sign_blue", Mt @ _T(-0.055, 0.893, 0.0), bold=True, res=2)
    label(mb, "HOT", 0.016, "sign_red", Mt @ _T(0.055, 0.893, 0.0), bold=True, res=2)
    for (x, col) in ((-0.055, "sign_green"), (0.055, "sign_red")):
        lathe(mb, [(0.0042, -0.0003), (0.0042, 0.0012), (0.003, 0.0026), (0.0, 0.003)], seg=10, mat=col, M=Mt @ _T(x, 0.928, 0.0))
        lathe(mb, [(0.0058, -0.0003), (0.0062, 0.0008), (0.0056, 0.0016), (0.0045, 0.0009), (0.0045, -0.0003)], seg=10,
              mat="aluminium", M=Mt @ _T(x, 0.928, 0.0), closed=True)
    # puerta inferior (gabinete de guardado): panel con junta, jalón y pernos
    Mdr = Mt @ _T(0, 0.31, -0.0004)
    slab(mb, Mdr, 0.244, 0.48, 0.0042, rc=0.012, re=0.0022, re0=0.0, mat="sign_white", nc=3, ne=1)
    rrframe(mb, Mdr @ _T(0, 0.205, 0.0038), (0, 0, 0.11, 0.022, 0.009), (0, 0, 0.09, 0.008, 0.004), 0.004, re_o=0.0016,
            re_i=0.0012, n=3, ne=2, mat="plastic")
    mb.box((-0.045, 0.201, -0.006), (0.045, 0.209, 0.0055), "cable", bevel=0.0, m=Mdr)
    for z in (0.12, 0.48):
        lathe(mb, [(0.0, z - 0.018), (0.0045, z - 0.018), (0.0045, z + 0.018), (0.0, z + 0.018)], seg=8, mat="aluminium",
              M=_T(-0.1215, -0.1625, 0.0))
    # rejillas laterales (persianas reales)
    for sx in (-1, 1):
        Ms = _T(sx * 0.158, 0.03, 0.30) @ (_Ry(90) @ _Rz(90) if sx > 0 else _Ry(-90) @ _Rz(-90))
        louver_grille(mb, Ms, 0.16, 0.12, 6, mat="sign_white", back_mat="cable", t=0.006, frame=0.009, slat_ang=40, depth=-0.0004,
                      nr=16)
    # espalda (contra el muro): condensador y cordón en versión de volumen (mantienen la caja)
    yb = 0.158
    rows = 5
    pts = []
    for k in range(rows):
        z = 0.12 + k * 0.1
        xa, xb_ = (-0.11, 0.11) if k % 2 == 0 else (0.11, -0.11)
        pts += [(xa, yb + 0.014, z), (xb_, yb + 0.014, z)]
    mb.tube(_dedupe(fillet(pts, 0.05, 3)), 0.0024, seg=4, mat="cable")
    for x in (-0.13, 0.13):
        mb.box((x - 0.006, yb - 0.0005, 0.09), (x + 0.006, yb + 0.0175, 0.56), "cable", bevel=0.0, seg=1)
    lathe(mb, [(0.0, -0.0003), (0.009, -0.0003), (0.009, 0.01), (0.006, 0.02), (0.0, 0.02)], seg=8, mat="cable", M=_T(0.09, yb, 0.62) @ _Rx(-90))
    hose(mb, [(0.09, yb + 0.012, 0.62), (0.09, yb + 0.022, 0.62), (0.09, yb + 0.022, 0.12), (0.12, yb + 0.022, 0.0042),
              (0.172, yb + 0.022, 0.0042)], 0.0042, bend=0.05, mat="cable", seg=5, nseg=3)
    return mb


# ===================================================================================================== lavabo
def _dloop(w, d, yb, rf, rb, z, n=7, cx=0.0):
    """Lazo en planta de una pieza adosada al muro: ancho w, fondo d desde y = yb hacia -Y, radios frontal rf y trasero rb."""
    P = [(cx - w / 2, yb - d), (cx + w / 2, yb - d), (cx + w / 2, yb), (cx - w / 2, yb)]
    return [(x, y, z) for (x, y) in rpoly_pts(P, [rf, rf, rb, rb], 0.0, n)]


def _cross_handle(mb, M, col):
    """Maneral de cruz cromado con botón de color (sobre z = 0 local)."""
    lathe(mb, [(0.0135, -0.0004), (0.014, 0.004), (0.012, 0.011), (0.0105, 0.016), (0.0115, 0.02), (0.0, 0.021)],
          seg=12, mat="steel", M=M, caps=False)
    for k in range(4):
        a = PI / 4 + PI / 2 * k
        tip = Vector((0.032 * math.cos(a), 0.032 * math.sin(a), 0.026))
        rtube_p(mb, tuple(M @ Vector((0, 0, 0.017))), tuple(M @ tip), 0.008, 0.007, "steel", taper=0.8, n=1)
        lathe(mb, [(0.0, -0.005), (0.0045, -0.003), (0.0052, 0.0), (0.0045, 0.003), (0.0, 0.005)], seg=6, mat="steel",
              M=M @ _T(*tip))
    lathe(mb, [(0.0085, 0.0195), (0.0085, 0.0225), (0.007, 0.0235), (0.0, 0.0237)], seg=10, mat=col, M=M, caps=False)


def _angle_stop(mb, x, z, y0=0.0, lite=False):
    """Llave de paso angular en el muro (salida hacia arriba): chapetón, niple, cuerpo, maneral oval. Muro en y = y0.
    lite: misma forma con menos lados y sin las tapas que quedan dentro del muro o de otra pieza (presupuesto)."""
    Mw = _T(x, y0, z) @ _Rx(90)                                     # z local -> -Y (sale del muro)
    if lite:
        lathe(mb, [(0.0095, -0.002), (0.025, -0.002), (0.025, 0.0015), (0.022, 0.004), (0.0095, 0.0045)], seg=12, mat="steel", M=Mw,
              closed=True)
        lathe(mb, [(0.0082, 0.004), (0.0082, 0.026)], seg=8, mat="steel", M=Mw, caps=False)
        lathe(mb, [(0.0118, 0.024), (0.0125, 0.03), (0.0125, 0.046), (0.011, 0.05), (0.0, 0.05)], seg=10, mat="steel", M=Mw, caps=False)
        hexnut(mb, _T(x, y0 - 0.037, z + 0.01), s=0.019, h=0.01, mat="steel")
        lathe(mb, [(0.0068, z + 0.019), (0.0068, z + 0.03)], seg=8, mat="steel", M=_T(x, y0 - 0.037, 0), caps=False)
        lathe(mb, [(0.0055, 0.05), (0.0055, 0.06)], seg=6, mat="steel", M=Mw, caps=False)
        slab(mb, Mw @ _T(0, 0, 0.0595), 0.036, 0.016, 0.006, rc=0.007, re=0.002, re0=0.001, mat="sign_white", nc=2, ne=1)
        return
    lathe(mb, [(0.0095, -0.002), (0.025, -0.002), (0.025, 0.0015), (0.022, 0.004), (0.0095, 0.0045)], seg=24, mat="steel", M=Mw)
    lathe(mb, [(0.0, 0.0), (0.0082, 0.0), (0.0082, 0.026), (0.0, 0.026)], seg=14, mat="steel", M=Mw)
    lathe(mb, [(0.0, 0.024), (0.0118, 0.024), (0.0125, 0.03), (0.0125, 0.046), (0.011, 0.05), (0.0, 0.05)], seg=16, mat="steel", M=Mw)
    hexnut(mb, _T(x, y0 - 0.037, z + 0.01), s=0.019, h=0.01, mat="steel")
    lathe(mb, [(0.0, z + 0.008), (0.0068, z + 0.008), (0.0068, z + 0.03), (0.0, z + 0.03)], seg=12, mat="steel", M=_T(x, y0 - 0.037, 0))
    lathe(mb, [(0.0, 0.05), (0.0055, 0.05), (0.0055, 0.06), (0.0, 0.06)], seg=10, mat="steel", M=Mw)
    slab(mb, Mw @ _T(0, 0, 0.0595), 0.036, 0.016, 0.006, rc=0.007, re=0.002, re0=0.001, mat="sign_white", nc=4, ne=2)


def sink(seed=0, mirror=True):
    """Lavabo de pared de cerámica (0,50 × 0,45, borde a 0,85 m) — origen en la cara del muro, piso; sale hacia -Y.
    Taza de una sola piel: faldón, borde rolado, cubierta trasera con perforaciones, cuenca con rebosadero y coladera; mezcladora
    de 4" con cuello de ganso, aireador ranurado, manerales de cruz con botón rojo/azul y varilla de contracanasta; espigas con
    tuercas, mangueras trenzadas a llaves angulares con chapetón; cespol con tubo de cola, tuercas estriadas, trampa en J y
    brazo al muro con chapetón; ménsulas de solera atornilladas al muro; espejo de acero con marco de aluminio, pijas y repisa."""
    r = rng(seed)
    mb = MB()
    zr = 0.85
    yd = -0.235                                                       # eje de la coladera
    outer = [  # (w, d, yb, rf, rb, z) de abajo hacia el borde
        (0.072, 0.072, yd + 0.036, 0.0355, 0.0355, 0.700), (0.20, 0.17, yd + 0.085, 0.08, 0.08, 0.706),
        (0.34, 0.30, -0.075, 0.12, 0.07, 0.726), (0.44, 0.39, -0.02, 0.14, 0.04, 0.758), (0.488, 0.438, -0.0045, 0.15, 0.02, 0.786),
        (0.498, 0.4465, -0.0012, 0.152, 0.012, 0.80), (0.50, 0.448, -0.001, 0.152, 0.01, 0.838), (0.498, 0.4465, -0.001, 0.151, 0.01, 0.846),
        (0.492, 0.443, -0.001, 0.148, 0.008, zr)]
    inner = [
        (0.408, 0.306, -0.112, 0.128, 0.07, zr), (0.398, 0.299, -0.1145, 0.124, 0.066, zr - 0.006), (0.392, 0.293, -0.1165, 0.121, 0.063, zr - 0.02),
        (0.37, 0.276, -0.12, 0.115, 0.06, zr - 0.045), (0.32, 0.238, -0.13, 0.1, 0.06, zr - 0.075), (0.235, 0.178, -0.148, 0.08, 0.06, zr - 0.101),
        (0.13, 0.105, yd + 0.0525, 0.05, 0.05, zr - 0.118), (0.058, 0.058, yd + 0.029, 0.0285, 0.0285, zr - 0.1245),
        (0.044, 0.044, yd + 0.022, 0.0215, 0.0215, zr - 0.127), (0.044, 0.044, yd + 0.022, 0.0215, 0.0215, 0.704)]
    loops = [_dloop(w, d, yb, rf, rb, z, n=6) for (w, d, yb, rf, rb, z) in outer + inner]
    skin(mb, loops, "sign_white", closed=True)
    # rebosadero (dos ranuras al frente de la cuenca)
    for x in (-0.018, 0.018):
        Mo = _T(x, -0.4028, zr - 0.033) @ _Rx(-62)
        slab(mb, Mo @ _T(0, 0, -0.0025), 0.012, 0.022, 0.0045, rc=0.0055, re=0.001, mat="cable", nc=2, ne=1, re0=0.0)
    # coladera: anillo cromado y rejilla
    lathe(mb, [(0.0205, zr - 0.1285), (0.031, zr - 0.1248), (0.0285, zr - 0.1232), (0.0205, zr - 0.126)], seg=24, mat="steel",
          M=_T(0, yd, 0), closed=True)
    for k in range(3):
        mb.box((-0.0208, -0.0016, zr - 0.131), (0.0208, 0.0016, zr - 0.1262), "steel", bevel=0.0005, seg=1,
               m=_T(0, yd, 0) @ _Rz(60 * k))
    lathe(mb, [(0.006, zr - 0.1285), (0.006, zr - 0.1250), (0.0045, zr - 0.1238), (0.0, zr - 0.1236)], seg=8,
          mat="steel", M=_T(0, yd, 0), caps=False)
    # ---- mezcladora de 4": base, cuello de ganso con aireador, manerales, varilla
    yf = -0.056
    slab(mb, _T(0, yf, zr - 0.0006), 0.165, 0.052, 0.013, rc=0.024, re=0.0065, re0=0.001, mat="steel", nc=4, ne=2)
    lathe(mb, [(0.0165, zr + 0.012), (0.0165, zr + 0.016), (0.0135, zr + 0.022), (0.012, zr + 0.06), (0.0105, zr + 0.068)], seg=16,
          mat="steel", M=_T(0, yf, 0), caps=False)
    hose(mb, [(0.0, yf, zr + 0.06), (0.0, yf, zr + 0.13), (0.0, -0.175, zr + 0.13), (0.0, -0.175, zr + 0.075)], 0.0095,
              bend=0.045, mat="steel", seg=12, nseg=8)
    Ma = _T(0.0, -0.175, zr + 0.082)
    lathe(mb, [(0.0068, 0.0), (0.0102, 0.0005), (0.0108, 0.003), (0.0102, 0.0045), (0.0108, 0.006), (0.0108, 0.016), (0.0096, 0.018)],
          seg=16, mat="steel", M=Ma @ _T(0, 0, -0.012), caps=False)
    lathe(mb, [(0.0, -0.0118), (0.0072, -0.0118), (0.0072, -0.0124), (0.0, -0.0124)], seg=12, mat="cable", M=Ma)
    for (x, col) in ((-0.0508, "sign_blue"), (0.0508, "sign_red")):
        lathe(mb, [(0.0145, zr + 0.012), (0.0145, zr + 0.017), (0.0118, zr + 0.021), (0.0118, zr + 0.031)], seg=12, mat="steel",
              M=_T(x, yf, 0), caps=False)
        _cross_handle(mb, _T(x, yf, zr + 0.031) @ _Rz(float(r.uniform(-20, 20))), col)
    lathe(mb, [(0.0028, zr + 0.012), (0.0028, zr + 0.052), (0.0055, zr + 0.054), (0.0058, zr + 0.06), (0.0, zr + 0.0635)], seg=8,
          mat="steel", M=_T(0, -0.033, 0), caps=False)
    # ---- bajo la cubierta: espigas, tuercas, mangueras trenzadas, llaves angulares
    for (x, xs) in ((-0.0508, -0.09), (0.0508, 0.09)):
        lathe(mb, [(0.0085, 0.70), (0.0085, 0.745)], seg=8, mat="steel", M=_T(x, yf, 0), caps=False)
        hexnut(mb, _T(x, yf, 0.722), s=0.026, h=0.012, mat="steel")
        lathe(mb, [(0.0, 0.69), (0.0072, 0.69), (0.0072, 0.704), (0.0, 0.704)], seg=6, mat="steel", M=_T(x, yf, 0), phase=PI / 6)
        _angle_stop(mb, xs, 0.53, lite=True)
        hose(mb, [(x, yf, 0.692), (x, yf, 0.64), (xs, -0.037, 0.60), (xs, -0.037, 0.562)], 0.0048, bend=0.035, mat="steel", seg=6,
             nseg=4)
    # ---- cespol: tubo de cola, tuerca, trampa en J, brazo al muro con chapetón
    lathe(mb, [(0.0165, 0.70), (0.0165, 0.615)], seg=12, mat="steel", M=_T(0, yd, 0), caps=False)
    for zn in (0.70, 0.612):
        lathe(mb, [(0.021, zn - 0.013), (0.0225, zn - 0.011), (0.0225, zn + 0.002), (0.019, zn + 0.004), (0.0165, zn + 0.004)], seg=18,
              mat="steel", M=_T(0, yd, 0), caps=False,
              rmod=lambda i, a, rr, z: rr - (0.0012 * (0.5 + 0.5 * math.cos(9 * a)) ** 2 if i in (1, 2) else 0.0))
    hose(mb, [(0.0, yd, 0.605), (0.0, yd, 0.497), (0.0, -0.163, 0.497), (0.0, -0.163, 0.556), (0.0, -0.10, 0.556), (0.0, -0.001, 0.556)],
         0.0165, bend=0.032, mat="steel", seg=10, nseg=6)
    lathe(mb, [(0.0165, 0.0), (0.0215, 0.0), (0.0225, 0.002), (0.0225, 0.014), (0.019, 0.016), (0.0165, 0.016)], seg=16, mat="steel",
          M=_T(0, -0.098, 0.556) @ _Rx(90), caps=False)
    lathe(mb, [(0.017, -0.0015), (0.038, -0.0015), (0.038, 0.002), (0.034, 0.006), (0.017, 0.007)], seg=16, mat="steel",
          M=_T(0, 0.0, 0.556) @ _Rx(90), closed=True)
    # ---- ménsulas de solera bajo los costados
    for sx in (-1, 1):
        x = sx * 0.19
        slab(mb, _T(x, -0.0003, 0.70) @ _Rx(90), 0.04, 0.10, 0.005, rc=0.006, re=0.0015, mat="steel", nc=2, ne=1, re0=0.0)
        for z in (0.665, 0.735):
            screw(mb, _T(x, -0.005, z) @ _Rx(90), r=0.0045, seg=6, cross=False)
        rtube_p(mb, (x, -0.004, 0.744), (x, -0.105, 0.776), 0.03, 0.006, "steel", taper=0.9, n=1)
        lathe(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.004), (0.0, 0.004)], seg=8, mat="rubber",
              M=_T(x, -0.10, 0.777))
    # ---- espejo de acero inoxidable con marco de aluminio, pijas de seguridad y repisa
    if mirror:
        Mm = _T(0, 0.0, 0.0) @ _Rx(90)
        rrframe(mb, Mm, (0.0, 1.45, 0.54, 0.64, 0.012), (0.0, 1.45, 0.488, 0.588, 0.004), 0.016, re_o=0.004, re_i=0.0025, n=3, ne=2,
                mat="aluminium")
        mb.box((-0.252, -0.0105, 1.148), (0.252, -0.006, 1.752), "steel", bevel=0.0, seg=1)
        for (x, z) in ((-0.255, 1.145), (0.255, 1.145), (-0.255, 1.755), (0.255, 1.755)):
            screw(mb, Mm @ _T(x, z, 0.0158), r=0.004, seg=8)
        Msh = _T(0, 0.0, 1.085)
        mb.box((-0.21, -0.112, 0.0), (0.21, -0.004, 0.006), "glass", bevel=0.002, seg=2, m=Msh)
        for x in (-0.18, 0.18):
            slab(mb, Msh @ _T(x, -0.0003, -0.02) @ _Rx(90), 0.022, 0.05, 0.006, rc=0.006, re=0.002, mat="aluminium", nc=2, ne=1,
                 re0=0.0)
            rtube_p(mb, tuple(Msh @ Vector((x, -0.005, -0.004))), tuple(Msh @ Vector((x, -0.098, -0.004))), 0.014, 0.008, "aluminium",
                    taper=0.85, n=1)
            screw(mb, Msh @ _T(x, -0.0063, -0.03) @ _Rx(90), r=0.0035, seg=6, cross=False)
    return mb


# ===================================================================================================== inodoro
def _tl(w, yf, yb, rf, rb, z, n=10, d=0.0):
    """Lazo en planta del inodoro (frente yf, fondo yb), desplazado d hacia adentro (d < 0: hacia afuera)."""
    return _dloop(w - 2 * d, (yb - yf) - 2 * d, yb - d, max(rf - d, 0.002), max(rb - d, 0.002), z, n=n)


def _ring_seat(mb, M, out, inn, t, mat, n=10, dome=0.003):
    """Aro (asiento) de sección redondeada entre un contorno exterior y uno interior (w, yf, yb, rf, rb); espesor t."""
    mid = tuple((a + b) / 2 for a, b in zip(out, inn))
    L = []
    for (dd, z) in ((0.004, 0.0), (0.0013, 0.0035), (0.0, t * 0.45), (0.0022, t * 0.82), (0.008, t)):
        L.append(_tl(*out, z, n=n, d=dd))
    L.append(_tl(*mid, t + dome, n=n))
    for (dd, z) in ((-0.007, t), (-0.0022, t * 0.82), (0.0, t * 0.45), (-0.0015, 0.003), (-0.004, 0.0)):
        L.append(_tl(*inn, z, n=n, d=dd))
    skin(mb, L, mat, M, closed=True)


def toilet(seed=0):
    """Inodoro de dos piezas de cerámica (frente -Y, muro en y = +0,36): taza de una sola piel con base acampanada, pedestal,
    borde rolado y cuenca hasta la trampa, espejo de agua; tapones de los pijas al piso; asiento de aro con topes de hule y tapa
    levantada recargada en el tanque, bisagras con perno; tanque con empaque y tapa separada por junta; palanca de descarga con
    chapetón; válvula de llenado con tuerca, manguera trenzada y llave angular con chapetón."""
    r = rng(seed)
    mb = MB()
    n = 10
    zr = 0.395
    outer = [(0.226, -0.112, 0.268, 0.105, 0.05, 0.0), (0.25, -0.124, 0.28, 0.115, 0.055, 0.004), (0.25, -0.124, 0.28, 0.115, 0.055, 0.010),
             (0.234, -0.116, 0.272, 0.108, 0.05, 0.022), (0.218, -0.106, 0.262, 0.1, 0.045, 0.045), (0.206, -0.10, 0.252, 0.095, 0.045, 0.11),
             (0.214, -0.118, 0.255, 0.1, 0.045, 0.19), (0.262, -0.19, 0.27, 0.125, 0.05, 0.265), (0.322, -0.248, 0.296, 0.155, 0.055, 0.325),
             (0.352, -0.272, 0.312, 0.17, 0.05, 0.365), (0.358, -0.279, 0.317, 0.173, 0.045, 0.383), (0.354, -0.276, 0.316, 0.171, 0.043, zr - 0.004),
             (0.344, -0.271, 0.312, 0.166, 0.04, zr)]
    inner = [(0.274, -0.248, 0.134, 0.137, 0.1, zr), (0.262, -0.242, 0.129, 0.131, 0.095, zr - 0.006),
             (0.255, -0.238, 0.125, 0.127, 0.092, zr - 0.022), (0.25, -0.232, 0.12, 0.124, 0.09, zr - 0.036),
             (0.222, -0.202, 0.10, 0.11, 0.085, 0.31), (0.172, -0.156, 0.08, 0.086, 0.075, 0.262), (0.12, -0.10, 0.06, 0.06, 0.055, 0.222),
             (0.07, -0.052, 0.04, 0.035, 0.035, 0.19), (0.05, -0.036, 0.026, 0.0245, 0.0245, 0.172)]
    skin(mb, [_tl(*o, n=n) for o in outer] + [_tl(*i, n=n) for i in inner], "sign_white", closed=True)
    skin(mb, [_tl(0.168, -0.152, 0.079, 0.084, 0.074, 0.2545, n=n, d=-0.0015), _tl(0.168, -0.152, 0.079, 0.084, 0.074, 0.2555, n=n, d=-0.0015)],
         "glass")
    for sx in (-1, 1):                                                           # tapones de pijas al piso
        lathe(mb, [(0.0, 0.002), (0.0145, 0.002), (0.015, 0.008), (0.0132, 0.017), (0.009, 0.0225), (0.0, 0.024)], seg=20,
              mat="sign_white", M=_T(sx * 0.122, 0.07, 0.0))
    # asiento con topes y bisagras; tapa levantada
    so = (0.364, -0.283, 0.136, 0.18, 0.06)
    si = (0.216, -0.218, 0.074, 0.106, 0.075)
    _ring_seat(mb, _T(0, 0, zr + 0.005), so, si, 0.021, "plastic", n=n)
    for (x, y) in ((-0.13, -0.12), (0.13, -0.12), (-0.135, 0.07), (0.135, 0.07)):
        lathe(mb, [(0.0, zr - 0.0005), (0.0075, zr - 0.0005), (0.0075, zr + 0.004), (0.006, zr + 0.0058), (0.0, zr + 0.006)], seg=12,
              mat="rubber", M=_T(x, y, 0.0))
    yh, zh = 0.158, zr + 0.031
    for sx in (-1, 1):
        x = sx * 0.075
        slab(mb, _T(x, yh + 0.004, zr - 0.0005), 0.03, 0.034, 0.03, rc=0.008, re=0.006, re0=0.0, mat="plastic", nc=3)
        lathe(mb, [(0.0, -0.022), (0.0045, -0.022), (0.0045, 0.022), (0.0, 0.022)], seg=12, mat="steel", M=_T(x, yh, zh) @ _Ry(90))
        lathe(mb, [(0.0, 0.0), (0.0075, 0.0), (0.0078, 0.003), (0.006, 0.0055), (0.0, 0.006)], seg=14, mat="plastic",
              M=_T(x + sx * 0.0218, yh, zh) @ _Ry(90 * sx))
        rtube_p(mb, (x - sx * 0.022, 0.12, zr + 0.013), (x - sx * 0.022, yh, zh - 0.002), 0.014, 0.012, "plastic", taper=0.9)
    ang = -float(r.uniform(92.0, 95.0))
    Ml = _T(0, yh, zh) @ _Rx(ang) @ _T(0, -yh, -zh)
    lo = (0.368, -0.287, 0.138, 0.182, 0.06)
    L = []
    zl = zr + 0.027
    for (dd, z) in ((0.006, 0.0), (0.0015, 0.004), (0.0, 0.01), (0.003, 0.017), (0.012, 0.0215), (0.04, 0.0245), (0.08, 0.0255)):
        L.append(_tl(*lo, zl + z, n=n, d=dd))
    skin(mb, L, "plastic", Ml)
    for sx in (-1, 1):
        rtube_p(mb, tuple(Ml @ Vector((sx * 0.052, 0.128, zl + 0.012))), tuple(Ml @ Vector((sx * 0.052, yh, zh + 0.002))), 0.014, 0.012,
                "plastic", taper=0.9)
        lathe(mb, [(0.0, 0.0), (0.0065, 0.0), (0.0065, 0.004), (0.0, 0.0045)], seg=10, mat="rubber",
              M=Ml @ _T(sx * 0.12, -0.16, zl) @ _Rx(180))
    # tanque, empaque, tapa, palanca
    slab(mb, _T(0, 0.276, zr + 0.009), 0.38, 0.158, 0.396, rc=0.026, re=0.012, re0=0.008, mat="sign_white", nc=6)
    lathe(mb, [(0.032, zr - 0.0005), (0.05, zr - 0.0005), (0.052, zr + 0.004), (0.05, zr + 0.0095), (0.032, zr + 0.0095)], seg=28,
          mat="rubber", M=_T(0, 0.262, 0.0))
    for x in (-0.085, 0.085):
        lathe(mb, [(0.0, zr - 0.0005), (0.009, zr - 0.0005), (0.009, zr + 0.0095), (0.0, zr + 0.0095)], seg=6, mat="steel",
              M=_T(x, 0.262, 0.0), phase=PI / 6)
    slab(mb, _T(0, 0.275, zr + 0.4075), 0.396, 0.174, 0.028, rc=0.032, re=0.012, re0=0.004, mat="sign_white", nc=6)
    Mlev = _T(-0.19, 0.238, 0.738) @ _Ry(-90)                                      # palanca lateral (costado izquierdo)
    lathe(mb, [(0.0, -0.0004), (0.017, -0.0004), (0.0175, 0.002), (0.0155, 0.006), (0.009, 0.008), (0.0, 0.0085)], seg=24,
          mat="steel", M=Mlev)
    lathe(mb, [(0.0, 0.007), (0.0085, 0.007), (0.0085, 0.017), (0.0, 0.017)], seg=16, mat="steel", M=Mlev)
    rtube_p(mb, tuple(Mlev @ Vector((0.0, 0.0, 0.0145))), tuple(Mlev @ Vector((-0.008, -0.066, 0.0145))), 0.012, 0.007, "steel",
            taper=0.85)
    lathe(mb, [(0.0, -0.0042), (0.0065, -0.0042), (0.0068, 0.0), (0.0065, 0.0042), (0.0, 0.0042)], seg=12, mat="steel",
          M=Mlev @ _T(-0.008, -0.066, 0.0145))
    # alimentación: espiga de la válvula, tuerca estriada, manguera trenzada, llave angular en el muro
    xs = -0.135
    lathe(mb, [(0.0, zr - 0.025), (0.0105, zr - 0.025), (0.0105, zr + 0.009), (0.0, zr + 0.009)], seg=14, mat="plastic",
          M=_T(xs, 0.30, 0.0))
    lathe(mb, [(0.0, zr - 0.05), (0.017, zr - 0.05), (0.0175, zr - 0.046), (0.0175, zr - 0.03), (0.015, zr - 0.026), (0.0, zr - 0.026)],
          seg=32, mat="plastic", M=_T(xs, 0.30, 0.0),
          rmod=lambda i, a, rr, z: rr - (0.0013 * (0.5 + 0.5 * math.cos(16 * a)) ** 2 if i in (2, 3) else 0.0))
    _angle_stop(mb, xs - 0.02, 0.17, y0=0.36)
    hose(mb, [(xs, 0.30, zr - 0.048), (xs, 0.30, 0.30), (xs - 0.02, 0.323, 0.235), (xs - 0.02, 0.323, 0.202)], 0.0048, bend=0.05,
         mat="steel", seg=8, pitch=0.006, depth=0.1)
    return mb


# ===================================================================================================== cubeta de trapeador
def _rl(w, d, r, z, cx=0.0, cy=0.0, n=6):
    return [(cx + x, cy + y, z) for (x, y) in rr_pts(w, d, r, n)]


def _small_caster(mb, M, R=0.025, swivel=0.0):
    """Rodaja de 2": placa, balero de giro, horquilla de lámina, rueda con banda redondeada, maza y eje con tuercas."""
    slab(mb, M @ _T(0, 0, 2 * R + 0.009), 0.042, 0.042, 0.003, rc=0.006, re=0.001, mat="steel", nc=2, ne=1)
    Mz = M @ _Rz(swivel)
    lathe(mb, [(0.016, 2 * R + 0.0035), (0.0175, 2 * R + 0.006), (0.016, 2 * R + 0.0092)], seg=10, mat="steel", M=Mz, caps=False)
    off = R * 0.35
    for sx in (-1, 1):
        prof = [(-0.014, 2 * R + 0.004), (0.014, 2 * R + 0.004), (off + 0.009, R + 0.004), (off + 0.007, R - 0.006), (off - 0.007, R - 0.006),
                (-0.012, R + 0.012)]
        perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        mb.plate(prof, 0.0018, "steel", m=Mz @ _T(sx * 0.0125 - (0.0018 if sx > 0 else 0.0), 0, 0) @ perm)
    Mw = Mz @ _T(0, off, R) @ _Ry(90)
    lathe(mb, [(0.006, -0.0098), (R * 0.88, -0.0098), (R, -0.0055), (R, 0.0055), (R * 0.88, 0.0098), (0.006, 0.0098)], seg=14,
          mat="rubber", M=Mw, closed=True)
    lathe(mb, [(0.0, -0.0106), (0.0062, -0.0106), (0.0062, 0.0106), (0.0, 0.0106)], seg=8, mat="plastic", M=Mw)
    mb.cyl(Mw @ Vector((0, 0, -0.016)), Mw @ Vector((0, 0, 0.016)), 0.0028, seg=6, mat="steel")
    for sz in (-1, 1):
        hexnut(mb, Mw @ _T(0, 0, sz * 0.0143) @ (_Rx(180) if sz < 0 else Matrix()), s=0.0075, h=0.0035, mat="steel")


def mop_bucket(seed=0):
    """Cubeta de trapeador con exprimidor de prensa lateral (0,40 × 0,30 × 0,40 + mecha y palo a 1,35 m): cubeta de plástico
    ahusada con labio rolado, nervaduras, asas moldeadas, agua sucia y marca MAX; 4 rodajas de 2"; asa de alambre abatida
    con puño; exprimidor con cuerpo de embudo, placa fija ranurada, placa móvil con costillas, brazos y eje, ganchos al borde,
    palanca con horquilla y puño estriado; trapeador con palo barnizado, tapón colgador, mordaza con perilla y mechas de algodón
    caídas dentro de la cámara de exprimido."""
    r = rng(seed)
    mb = MB()
    zb, zr = 0.062, 0.398
    # ---- cubeta: pared ahusada con labio rolado (sólido cerrado con interior visible)
    L = [_rl(0.30, 0.20, 0.05, zb), _rl(0.318, 0.218, 0.058, zb + 0.004), _rl(0.326, 0.226, 0.062, zb + 0.014),
         _rl(0.362, 0.262, 0.072, zr - 0.035), _rl(0.366, 0.266, 0.073, zr - 0.024), _rl(0.386, 0.286, 0.08, zr - 0.02),
         _rl(0.392, 0.292, 0.082, zr - 0.012), _rl(0.39, 0.29, 0.081, zr - 0.003), _rl(0.384, 0.284, 0.079, zr),
         _rl(0.372, 0.272, 0.074, zr - 0.002), _rl(0.354, 0.254, 0.068, zr - 0.03), _rl(0.312, 0.212, 0.054, zb + 0.022),
         _rl(0.30, 0.20, 0.05, zb + 0.012)]
    skin(mb, L, "paint_yellow")
    for sx in (-1, 1):                                                             # nervaduras verticales de los costados
        yo = lambda z: 0.113 + 0.018 * (z - 0.076) / 0.287  # noqa: E731  (cara exterior del costado largo)
        for x in (-0.11, -0.04, 0.04, 0.11):
            rtube_p(mb, (x, sx * (yo(zb + 0.03) + 0.0012), zb + 0.03), (x, sx * (yo(zr - 0.04) + 0.0012), zr - 0.04), 0.012, 0.0075,
                    "paint_yellow", taper=0.9, r=0.0025, n=1)
    for sx in (-1, 1):                                                             # asa moldeada en cada extremo
        x = sx * 0.183
        mb.tube(_dedupe(fillet([(x - sx * 0.002, -0.06, zb + 0.05), (x + sx * 0.022, -0.06, zb + 0.05), (x + sx * 0.022, 0.06, zb + 0.05),
                                (x - sx * 0.002, 0.06, zb + 0.05)], 0.015, 4)), 0.008, seg=8, mat="paint_yellow")
    skin(mb, [_rl(0.323, 0.223, 0.056, 0.1395, n=6), _rl(0.323, 0.223, 0.056, 0.1405, n=6)], "glass")      # agua sucia
    yi = lambda z: -(0.106 + (0.127 - 0.106) * (z - 0.084) / (0.368 - 0.084))  # noqa: E731  (pared interior frontal)
    label(mb, "MAX", 0.016, "paint_yellow", _T(-0.10, yi(0.335), 0.335) @ _Rz(180) @ _Rx(90) @ _Rx(-4.2), res=1)
    rtube_p(mb, (-0.135, yi(0.327) + 0.0004, 0.327), (-0.065, yi(0.327) + 0.0004, 0.327), 0.003, 0.0034, "paint_yellow", r=0.001)
    # ---- rodajas
    for (x, y) in ((-0.14, -0.085), (0.14, -0.085), (-0.14, 0.085), (0.14, 0.085)):
        _small_caster(mb, _T(x, y, 0.0), R=0.025, swivel=float(r.uniform(-60, 60)))
    # ---- asa de alambre abatida sobre el extremo -X
    th = math.radians(76.0)
    Mbail = _T(-0.10, 0.0, zr - 0.015) @ Matrix.Rotation(-th, 4, "Y")
    bp = [(0.0, -0.152, 0.0), (0.0, -0.152, 0.03), (0.0, -0.13, 0.09), (0.0, 0.13, 0.09), (0.0, 0.152, 0.03), (0.0, 0.152, 0.0)]
    mb.tube(_dedupe([tuple(Mbail @ Vector(p)) for p in fillet(bp, 0.03, 4)]), 0.0032, seg=6, mat="steel")
    lathe(mb, [(0.0, -0.06), (0.008, -0.06), (0.0095, -0.055), (0.0095, 0.055), (0.008, 0.06), (0.0, 0.06)], seg=10, mat="cable",
          M=Mbail @ _T(0, 0, 0.09) @ _Rx(90))
    for sy in (-1, 1):
        lathe(mb, [(0.011, 0.0), (0.011, 0.006), (0.0075, 0.009), (0.0, 0.009)], seg=10, mat="paint_yellow",
              M=_T(-0.10, sy * 0.141, zr - 0.015) @ _Rx(-90 * sy), caps=False)
    # ---- exprimidor de prensa lateral
    xc = 0.107
    W = [_rl(0.105, 0.16, 0.02, 0.352, cx=xc), _rl(0.122, 0.196, 0.03, 0.42, cx=xc), _rl(0.156, 0.226, 0.03, 0.60, cx=xc),
         _rl(0.162, 0.232, 0.032, 0.606, cx=xc), _rl(0.158, 0.228, 0.031, 0.611, cx=xc), _rl(0.146, 0.216, 0.026, 0.608, cx=xc),
         _rl(0.144, 0.214, 0.025, 0.60, cx=xc), _rl(0.11, 0.184, 0.022, 0.42, cx=xc), _rl(0.094, 0.15, 0.016, 0.36, cx=xc)]
    skin(mb, W, "paint_yellow")
    for sy in (-1, 1):                                                             # nervaduras del cuerpo del exprimidor
        for dx in (-0.045, -0.015, 0.015, 0.045):
            rtube_p(mb, (xc + dx, sy * 0.0975, 0.425), (xc + dx, sy * 0.1125, 0.597), 0.009, 0.007, "paint_yellow", taper=0.85, r=0.002,
                    n=1)
    for k in range(9):                                                             # placa fija ranurada (lado +X)
        y = -0.072 + k * 0.018
        mb.box((xc + 0.044, y - 0.0045, 0.39), (xc + 0.052, y + 0.0045, 0.585), "paint_yellow", bevel=0.0018, seg=1)
    mb.box((xc + 0.050, -0.085, 0.385), (xc + 0.056, 0.085, 0.395), "paint_yellow", bevel=0.002, seg=1)
    Mpp = _T(xc - 0.045, 0.0, 0.49) @ _Ry(-8)                                         # placa móvil con costillas
    slab(mb, Mpp @ _Ry(90), 0.19, 0.15, 0.008, rc=0.012, re=0.003, mat="paint_yellow", nc=3)
    for k in range(6):
        z = -0.075 + k * 0.03
        mb.box((0.007, -0.068, z - 0.003), (0.014, 0.068, z + 0.003), "paint_yellow", bevel=0.0, seg=1, m=Mpp)
    for sy in (-1, 1):
        mb.box((xc - 0.07, sy * 0.117 - 0.003, 0.55), (xc + 0.02, sy * 0.117 + 0.003, 0.585), "steel", bevel=0.0, seg=1,
               m=_T(xc - 0.025, 0, 0.567) @ _Ry(-22) @ _T(-xc + 0.025, 0, -0.567))
        lathe(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.006), (0.0, 0.006)], seg=6, mat="steel", M=_T(xc - 0.055, sy * 0.12, 0.598) @ _Rx(-90 * sy),
              phase=PI / 6)
        # silleta: ala que sale del cuerpo y se apoya sobre el labio del costado largo, con pestaña que abraza el borde
        y0_, y1_ = sorted((sy * 0.098, sy * 0.1535))
        mb.box((xc - 0.052, y0_, zr + 0.0005), (xc + 0.062, y1_, zr + 0.0095), "paint_yellow", bevel=0.003, seg=1)
        y0_, y1_ = sorted((sy * 0.1475, sy * 0.1562))
        mb.box((xc - 0.049, y0_, zr - 0.028), (xc + 0.059, y1_, zr + 0.0072), "paint_yellow", bevel=0.002, seg=1)
        for xg in (xc - 0.03, xc + 0.04):                                         # cartelas bajo el ala
            y0_, y1_ = sorted((sy * 0.096, sy * 0.124))
            mb.box((xg - 0.003, y0_, zr - 0.03), (xg + 0.003, y1_, zr + 0.001), "paint_yellow", bevel=0.0, seg=1,
                   m=_T(xg, sy * 0.096, zr) @ _Rx(sy * 20) @ _T(-xg, -sy * 0.096, -zr))
    mb.cyl((xc - 0.055, -0.128, 0.598), (xc - 0.055, 0.128, 0.598), 0.005, seg=10, mat="steel")
    # palanca: horquilla al eje y tubo con puño estriado
    for sy in (-1, 1):
        mb.tube(_dedupe(fillet([(xc - 0.055, sy * 0.125, 0.598), (xc - 0.048, sy * 0.125, 0.70), (xc - 0.04, sy * 0.012, 0.76)], 0.05, 5)),
                0.0085, seg=8, mat="steel")
    mb.tube([(xc - 0.04, 0.0, 0.755), (xc - 0.012, 0.0, 1.0)], 0.011, seg=10, mat="steel")
    dirv = Vector((0.028, 0.0, 0.245)).normalized()
    Mg = Matrix.Translation(Vector((xc - 0.04, 0.0, 0.755)) + dirv * 0.135) @ dirv.to_track_quat("Z", "Y").to_matrix().to_4x4()
    prof = [(0.0145, 0.0), (0.0155, 0.004)]
    for k in range(5):
        prof += [(0.0155, 0.01 + k * 0.02), (0.0141, 0.019 + k * 0.02)]
    prof += [(0.0155, 0.106), (0.014, 0.112), (0.0, 0.114)]
    lathe(mb, prof, seg=12, mat="rubber", M=Mg, caps=False)
    # ---- trapeador: mecha en la cubeta, palo recargado en el labio del exprimidor, tapón colgador, mordaza con perilla
    p0 = Vector((-0.075, 0.0, 0.262))
    lean = Vector((0.014, 0.03, 0.598)) - p0
    p1 = p0 + lean.normalized() * 1.105
    mb.cyl(p0, p1, 0.0118, seg=14, mat="wood_varnish")
    d = (p1 - p0).normalized()
    Mt = Matrix.Translation(p1) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    lathe(mb, [(0.0135, -0.035), (0.0138, -0.004), (0.012, 0.012), (0.006, 0.0215), (0.0, 0.022)], seg=12, mat="cable",
          M=Mt, caps=False)
    lathe(mb, [(0.0035, -0.004), (0.0075, -0.004), (0.0075, 0.004), (0.0035, 0.004)], seg=8, mat="cable", M=Mt @ _T(0, 0, 0.006) @ _Rx(90),
          closed=True)
    Mc = Matrix.Translation(p0) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    lathe(mb, [(0.022, -0.03), (0.026, -0.02), (0.026, 0.0), (0.016, 0.03), (0.0135, 0.045)], seg=12,
          mat="plastic_blue", M=Mc, caps=False)
    slab(mb, Mc @ _T(0.0, 0.0, -0.058), 0.085, 0.034, 0.03, rc=0.008, re=0.005, mat="plastic_blue", nc=2, ne=2)
    lathe(mb, [(0.006, 0.0), (0.006, 0.018)], seg=8, mat="plastic_blue", M=Mc @ _T(0, -0.017, -0.04) @ _Rx(90), caps=False)
    slab(mb, Mc @ _T(0, -0.037, -0.04) @ _Rx(90), 0.03, 0.012, 0.008, rc=0.005, re=0.003, mat="plastic_blue", nc=2, ne=1)
    # mechas de algodón: caen de la mordaza y se extienden sobre el agua (las puntas se hunden)
    zw = 0.14
    roots = []
    for (w_, h_, rr_, nn, dz, ph) in ((0.074, 0.028, 0.012, 17, 0.0, 0.0), (0.046, 0.012, 0.005, 13, -0.006, 0.5)):
        ring = [Vector((x, y, 0.0)) for (x, y) in rr_pts(w_, h_, rr_, 4)]
        per = sum((ring[(i + 1) % len(ring)] - ring[i]).length for i in range(len(ring)))
        pts_ = resample([tuple(p) for p in ring + [ring[0]]], per / nn)[:nn]
        for j, q in enumerate(pts_):
            roots.append((Vector(q) + Vector((0, 0, -0.056 + dz)), ph))
    for k, (qq, ph) in enumerate(roots):
        q0 = Mc @ qq
        lc = Vector((qq.x, qq.y * 2.2, 0.0))
        dv = Vector((lc.x, lc.y, 0.0)).normalized() if lc.length > 1e-6 else Vector((1.0, 0.0, 0.0))
        dv = (Matrix.Rotation(float(r.uniform(-0.25, 0.25)), 3, "Z") @ dv).normalized()
        L = float(r.uniform(0.07, 0.19))
        drop = float(r.uniform(0.7, 0.95))
        pts = [q0, q0 + dv * 0.012 + Vector((0, 0, -0.03)), q0 + dv * 0.03 + Vector((0, 0, -(q0.z - zw) * drop))]
        wig, curl = float(r.uniform(-1, 1)), float(r.uniform(-1.4, 1.4))
        heading = Vector(dv)
        pp = Vector(pts[-1])
        seg_len = L / 3
        lim = 0.002 + 0.022 * ((k * 7) % 11) / 10.0                                  # cada mecha topa en un punto distinto
        for j in range(3):
            t = (j + 1) / 3
            heading = (Matrix.Rotation(curl * 0.35 * t + wig * 0.25 * math.sin(3 * t + k), 3, "Z") @ heading).normalized()
            pp = pp + heading * seg_len
            pp.x = min(max(pp.x, -0.145 + lim), 0.145 - lim)
            pp.y = min(max(pp.y, -0.097 + lim), 0.097 - lim)
            pz = zw + (0.0072, 0.0064, -0.016)[j] + float(r.uniform(-0.0006, 0.0006))   # flota (≥ 2 mm) y la punta se hunde
            pts.append(Vector((pp.x, pp.y, pz)))
        pts = _dedupe([tuple(p) for p in pts], 1e-4)
        rad = [0.0036, 0.0048] + [0.0056] * (len(pts) - 2)
        mb.tube(pts, 0.0056, seg=4, mat="linen", radii=rad[:len(pts)])
    return mb


# ===================================================================================================== bote de basura
def _bag_fold(mb, r, rbody, z_top, z_hem, mat="cable", seg=40, step=0.02):
    """Bolsa de basura doblada sobre el borde: banda de espesor real que entra al bote, pasa sobre el bordón y cae por fuera
    con pliegues irregulares y dobladillo disparejo."""
    cl = [(rbody(z_top - 0.014) - 0.003, z_top - 0.014), (rbody(z_top) + 0.0035, z_top + 0.0072), (rbody(z_top) + 0.0072, z_top + 0.002),
          (rbody(z_top - 0.012) + 0.0055, z_top - 0.012)]
    zz = z_top - 0.012
    while zz > z_hem + step * 0.6:
        zz = max(zz - step, z_hem)
        cl.append((rbody(zz) + 0.0045, zz))
    prof = _thick(cl, 0.0011, cap=2)
    ph = [float(r.uniform(0, 2 * PI)) for _ in range(3)]
    hem = [float(r.uniform(-0.012, 0.012)) for _ in range(9)]

    def fold(a, z):
        k = max(0.0, min(1.0, (z_top - z) / (z_top - z_hem))) ** 0.8
        w = abs(math.sin(4.5 * a + ph[0] + 0.6 * math.sin(2 * a + ph[1]))) ** 0.6 + 0.35 * math.sin(7 * a + ph[2])
        return 0.0006 + k * 0.011 * max(w, 0.0)
    V = lathe(mb, prof, seg=seg, mat=mat, closed=True,
              rmod=lambda i, a, rr, z: rr + (fold(a, z) if (rr > rbody(z) + 0.0015 and z < z_top - 0.002) else 0.0))
    zmin = min(z for _, z in prof)
    for ring in V:
        for k, v in enumerate(ring):
            if v.co.z < zmin + 0.013:                                            # dobladillo disparejo
                a = 2 * PI * k / seg
                f = a / (2 * PI) * 9
                i0 = int(f) % 9
                t = f - int(f)
                v.co.z += (hem[i0] * (1 - t) + hem[(i0 + 1) % 9] * t) + 0.004 * math.sin(5 * a)


def trash_bin(seed=0, pedal=True):
    """Bote de basura: de pedal (consultorio, lámina pintada) con base de plástico, bordón, tapa abombada con bisagra trasera,
    varilla de levante exterior, pedal estampado con huella de hule y bisagra; o de tapa basculante (plástico, nervado) con
    capuchón, compuerta oscilante y pernos. Ambos con bolsa doblada sobre el borde con pliegues.
    Presupuesto (≤ 4k): sin las caras que tapan la bolsa, la tapa o el piso (bordón superior, fondo de la base, cara inferior
    de la tapa)."""
    r = rng(seed)
    mb = MB()
    if pedal:
        rb = lambda z: 0.130 + 0.018 * (z - 0.02) / 0.425  # noqa: E731
        lathe(mb, [(0.124, 0.0), (0.132, 0.002), (0.135, 0.01), (0.135, 0.022), (0.131, 0.028), (0.0, 0.028)], seg=40, mat="plastic",
              caps=False)
        prof = [(rb(0.026) - 0.002, 0.026), (rb(0.03), 0.03), (rb(0.06), 0.06), (rb(0.066) + 0.0022, 0.066), (rb(0.072), 0.072),
                (rb(0.40), 0.40), (rb(0.445) + 0.003, 0.4475), (rb(0.445) + 0.0035, 0.452), (0.0, 0.455)]
        lathe(mb, prof, seg=40, mat="sign_white", caps=False)
        _bag_fold(mb, r, lambda z: rb(min(z, 0.445)) + (0.0035 if z > 0.44 else 0.0), 0.452, 0.37, mat="cable", seg=40)
        # tapa abombada (bisagra atrás), lengüeta y varilla de levante
        zl = 0.4615
        lathe(mb, [(0.0, 0.497), (0.07, 0.4952), (0.12, 0.4855), (0.146, 0.4745), (0.1555, 0.467), (0.1515, zl), (0.13, 0.466),
                   (0.0, 0.468)], seg=40, mat="steel")
        lathe(mb, [(0.012, 0.0), (0.012, 0.004), (0.0, 0.0045)], seg=10, mat="cable", M=_T(0, 0, 0.4965), caps=False)
        yh = 0.162
        slab(mb, _T(0, rb(0.43) - 0.0025, 0.43) @ _Rx(-90), 0.06, 0.04, 0.004, rc=0.006, re=0.0015, mat="steel", nc=2, ne=1, re0=0.0)
        for x in (-0.02, 0.02):
            lathe(mb, [(0.003, 0.0), (0.0024, 0.0015), (0.0, 0.0018)], seg=6, mat="steel",
                  M=_T(x, rb(0.43) + 0.0012, 0.422) @ _Rx(-90), caps=False)
        for x in (-0.024, 0.024):
            mb.box((x - 0.004, rb(0.43) + 0.001, 0.438), (x + 0.004, yh + 0.004, 0.468), "steel", bevel=0.0, seg=1)
        mb.cyl((-0.032, yh, 0.464), (0.032, yh, 0.464), 0.0035, seg=8, mat="steel")
        mb.box((-0.016, 0.148, 0.462), (0.016, yh + 0.006, 0.468), "steel", bevel=0.0, seg=1)
        mb.tube(_dedupe(fillet([(0.0, yh + 0.004, 0.462), (0.0, yh + 0.004, 0.05), (0.0, 0.14, 0.03)], 0.02, 4)), 0.0025, seg=6,
                mat="steel")
        # pedal: bisagra en la base, palanca bajo el bote, placa estampada con huella de hule estriada
        for x in (-0.03, 0.03):
            mb.box((x - 0.003, -0.142, 0.006), (x + 0.003, -0.118, 0.03), "steel", bevel=0.0, seg=1)
        mb.cyl((-0.036, -0.135, 0.018), (0.036, -0.135, 0.018), 0.0035, seg=8, mat="steel")
        Mp = _T(0, -0.135, 0.018) @ _Rx(-6)
        rtube_p(mb, tuple(Mp @ Vector((0, 0.0, 0.0))), tuple(Mp @ Vector((0, 0.10, 0.0))), 0.03, 0.006, "steel", taper=0.9, n=1)
        for x in (-0.024, 0.024):
            rtube_p(mb, tuple(Mp @ Vector((x, 0.0, 0.0))), tuple(Mp @ Vector((x, -0.04, 0.012))), 0.008, 0.005, "steel", taper=1.0, n=1)
        Mpad = Mp @ _T(0, -0.045, 0.012)
        slab(mb, Mpad, 0.11, 0.048, 0.008, rc=0.012, re=0.003, mat="steel", nc=3, ne=1)
        slab(mb, Mpad @ _T(0, 0, 0.0075), 0.098, 0.038, 0.0025, rc=0.009, re=0.001, mat="rubber", nc=3, ne=1, re0=0.0)
        for k in range(5):
            mb.box((-0.044, -0.015 + k * 0.0075, 0.0095), (0.044, -0.0118 + k * 0.0075, 0.0118), "rubber", bevel=0.0, seg=1, m=Mpad)
    else:
        rb = lambda z: 0.128 + 0.02 * (z - 0.0) / 0.44  # noqa: E731
        prof = [(rb(0.0) - 0.008, 0.0), (rb(0.0), 0.006), (rb(0.012), 0.012), (rb(0.40), 0.40), (rb(0.425) + 0.003, 0.425),
                (rb(0.44) + 0.003, 0.44), (0.0, 0.4425)]
        lathe(mb, prof, seg=40, mat="plastic", caps=False)
        nrib = 14
        for k in range(nrib):                                                     # nervaduras verticales
            a = 2 * PI * k / nrib
            p0 = Vector((math.cos(a), math.sin(a), 0.0))
            rtube_p(mb, tuple(p0 * (rb(0.03) - 0.001) + Vector((0, 0, 0.03))), tuple(p0 * (rb(0.39) - 0.001) + Vector((0, 0, 0.39))),
                    0.008, 0.006, "plastic", taper=1.0, r=0.0022, n=1)
        _bag_fold(mb, r, lambda z: rb(min(z, 0.44)) + (0.003 if z > 0.42 else 0.0), 0.4435, 0.37, mat="cable", seg=36)
        # tapa abombada de corona plana con compuerta oscilante al centro (eje transversal y pernos)
        zt = 0.495
        lathe(mb, [(0.094, 0.4905), (0.094, zt), (0.115, zt - 0.005), (0.138, 0.476), (0.1535, 0.458), (0.1555, 0.452),
                   (0.1525, 0.4465), (0.1, 0.452)], seg=40, mat="plastic", closed=True)
        rrframe(mb, _T(0, 0, zt - 0.0006), (0, 0, 0.2, 0.2, 0.0999), (0, 0, 0.15, 0.086, 0.012), 0.0042, re_o=0.0018, re_i=0.0012,
                n=5, ne=1, mat="plastic")
        lathe(mb, [(0.0955, 0.468), (0.0955, 0.4715), (0.0, 0.4715)], seg=16, mat="cable", caps=False)            # boca oscura
        tilt = float(r.uniform(2.0, 6.0))
        Mf = _T(0, 0, zt + 0.0005) @ _Rx(tilt)
        slab(mb, Mf @ _T(0, 0, -0.004), 0.146, 0.082, 0.0062, rc=0.0105, re=0.0022, mat="plastic", nc=3, ne=1)
        for k in range(4):
            mb.box((-0.05, 0.016 + k * 0.0055, 0.0018), (0.05, 0.0178 + k * 0.0055, 0.0037), "plastic", bevel=0.0, seg=1, m=Mf)
        label(mb, "PUSH", 0.014, "plastic", Mf @ _T(0, -0.026, 0.0021), bold=True, res=1)
        for sx in (-1, 1):
            lathe(mb, [(0.0035, 0.0), (0.0035, 0.008), (0.0, 0.0085)], seg=8, mat="plastic",
                  M=_T(sx * 0.0715, 0, zt - 0.0005) @ _Ry(90 * sx), caps=False)
    return mb


# ===================================================================================================== despachador de gel
def sanitizer(seed=0):
    """Despachador de gel de muro (origen: cara del muro, centro inferior; sale hacia -Y): placa trasera atornillada, carcasa
    redondeada separada por junta, ventana de nivel con marco, cerradura en la parte superior, palanca de empuje articulada con
    estrías y leyenda PUSH, boquilla de descarga y gota de gel."""
    mb = MB()
    slab(mb, _T(0, -0.006, 0.0) @ _Rx(90) @ _T(0, 0.1245, -0.006), 0.112, 0.249, 0.012, rc=0.014, re=0.002, mat="sign_white", nc=4,
         ne=2)
    for z in (0.236, 0.012):
        screw(mb, _T(0, -0.012, z) @ _Rx(90), r=0.0042)
    yb = -0.0132
    L = []
    for (w, d, rf, z) in ((0.08, 0.046, 0.02, 0.016), (0.098, 0.068, 0.03, 0.019), (0.106, 0.078, 0.034, 0.026), (0.108, 0.08, 0.035, 0.034),
                          (0.108, 0.08, 0.035, 0.104), (0.11, 0.086, 0.036, 0.11), (0.11, 0.086, 0.036, 0.205), (0.108, 0.082, 0.035, 0.222),
                          (0.1, 0.07, 0.03, 0.231), (0.084, 0.05, 0.022, 0.2345)):
        L.append(_dloop(w, d, yb, rf, 0.004, z, n=6))
    skin(mb, L, "sign_white")
    # ventana de nivel con marco
    yfr = yb - 0.086
    Mw = _T(0, yfr + 0.0006, 0.163) @ _Rx(90)
    rrframe(mb, Mw, (0, 0, 0.046, 0.066, 0.012), (0, 0, 0.034, 0.054, 0.007), 0.0022, re_o=0.0009, re_i=0.0007, n=4, ne=2,
            mat="sign_white")
    slab(mb, Mw @ _T(0, 0, -0.0004), 0.036, 0.056, 0.0023, rc=0.008, re=0.0004, mat="glass", nc=4, ne=1, re0=0.0)
    for k in range(4):
        mb.box((0.0115, -0.024 + k * 0.012, 0.0012), (0.0155, -0.0232 + k * 0.012, 0.0034), "cable", bevel=0.0, m=Mw)
    # cerradura arriba
    Ml = _T(0, yb - 0.05, 0.2344)
    lathe(mb, [(0.0, -0.0004), (0.0068, -0.0004), (0.007, 0.0016), (0.006, 0.0026), (0.0, 0.0027)], seg=16, mat="aluminium", M=Ml)
    mb.box((-0.0035, -0.0007, 0.0018), (0.0035, 0.0007, 0.0032), "cable", bevel=0.0, m=Ml)
    # palanca de empuje articulada (cubre el frente inferior), estrías y leyenda
    Mp = _T(0, yb - 0.0835, 0.101) @ _Rx(6)                                      # bisagra de la palanca (arriba)
    Mpad = Mp @ _T(0, 0, -0.04) @ _Rx(90)                                          # plano de la paleta (z local -> -Y)
    slab(mb, Mpad, 0.094, 0.078, 0.0075, rc=0.014, re=0.003, re0=0.0012, mat="plastic", nc=5, ne=2)
    for k in range(5):
        y = 0.022 - k * 0.0065
        mb.box((-0.033, y - 0.0016, 0.0068), (0.033, y + 0.0016, 0.0093), "plastic", bevel=0.0006, seg=1, m=Mpad)
    label(mb, "PUSH", 0.0115, "sign_blue", Mpad @ _T(0, -0.03, 0.0072), bold=True)
    for sx in (-1, 1):
        x = sx * 0.0455
        rtube_p(mb, tuple(Mp @ Vector((x, -0.004, -0.004))), (sx * 0.0535, yb - 0.066, 0.1), 0.006, 0.010, "plastic", taper=1.0)
        lathe(mb, [(0.0, 0.0), (0.0042, 0.0), (0.0042, 0.0045), (0.0032, 0.0055), (0.0, 0.0056)], seg=10, mat="plastic",
              M=_T(sx * 0.0545, yb - 0.066, 0.1) @ _Ry(90 * sx) @ _T(0, 0, -0.0012))
    # boquilla y gota
    lathe(mb, [(0.0, 0.02), (0.0065, 0.02), (0.0065, 0.012), (0.0045, 0.008), (0.0035, 0.004), (0.0, 0.0035)], seg=14, mat="plastic",
          M=_T(0, yb - 0.048, 0.0))
    lathe(mb, [(0.0, 0.0035), (0.0018, 0.0028), (0.0026, 0.0012), (0.002, 0.0003), (0.0, 0.0)], seg=10, mat="glass",
          M=_T(0, yb - 0.048, 0.0))
    return mb


def _circle_prof(r0, z0, rad, n):
    return [(r0 + rad * math.cos(2 * PI * k / n), z0 + rad * math.sin(2 * PI * k / n)) for k in range(n)]


def _thick(cl, t, cap=3):
    """Perfil 2D cerrado de espesor t alrededor de una línea central [(r, z)] con remates redondos (fuelles, labios)."""
    P = [Vector((a, b)) for a, b in cl]
    n = len(P)
    N = []
    for i in range(n):
        d = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized()
        N.append(Vector((-d.y, d.x)))
    side_a = [P[i] + N[i] * t / 2 for i in range(n)]
    side_b = [P[i] - N[i] * t / 2 for i in range(n)]
    out = list(side_a)
    d_end = (P[-1] - P[-2]).normalized()
    for k in range(1, cap):
        a = PI * k / cap
        out.append(P[-1] + N[-1] * (t / 2 * math.cos(a)) + d_end * (t / 2 * math.sin(a)))
    out += list(reversed(side_b))
    d_st = (P[0] - P[1]).normalized()
    for k in range(1, cap):
        a = PI * k / cap
        out.append(P[0] - N[0] * (t / 2 * math.cos(a)) + d_st * (t / 2 * math.sin(a)))
    return [(p.x, p.y) for p in out]

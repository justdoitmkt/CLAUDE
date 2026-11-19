"""mil_builder.py — base militar de la costa seca mexicana: MIL_1_almacen (almacén de armamento pesado con su recinto) y
MIL_2_avanzada (puesto de avanzada: tienda de campaña que vende munición y armas; pieza suelta que también va junto al almacén).

Ejes de Blender, metros; frente hacia -Y; pivote a nivel del terreno (z = 0). Sin terreno: se entrega lo construido (losas, grava,
banquetas) y lo que va encima. SIN grafiti ni placas (pedido del usuario). Limpio, poco desgaste, con huellas de intentos de
saqueo (cortina abollada y palanqueada, rayones junto a los candados, un par de impactos) pero sin deterioro.

MIL_1_almacen (pivote al centro del recinto):
  nave     x -20..10 · y 0..18: nave de acero preingeniería de 30 × 18 m (4 crujías de 7,5 m), piso a andén (z 1,2), alero a
           7,2 (6 m libres), cumbrera 7,95 (pendiente 1:12). Muro de concreto hasta z 2,4 y lámina R color arena encima; techo de
           junta alzada galvanizado. Al frente: andén de 1,2 m con 2 cortinas de 14 × 14 ft, puerta de personal con marquesina y
           rampa. Dentro: marcos rígidos, largueros, aislante con cara blanca, racks de tarimas, jaula, montacargas.
  recinto  x -24..22 · y -20..21: muros T al poniente, al fondo y al oriente; al frente malla con navaja, portón y chicana;
           torre de vigilancia; plataforma del puesto de avanzada al oriente (x 11..21 · y 1..17, donde va MIL_2_avanzada).
MIL_2_avanzada (pivote al centro de la tienda): tienda de marco 6,1 × 9,75 m con mostrador, racks, red de camuflaje, HESCO y
  costales. Junto al almacén se coloca en MIL_OUTPOST (x, y, giro) del pivote de MIL_1.
Proporciones de fuentes reales (R-AAA punto 7) en ESTADO.md.
"""
import math

import bpy  # noqa: F401
import numpy as np
from mathutils import Matrix, Vector

from kit import clinic as cl
from kit import clinic_equipo as ce
from kit.common import MB, get_collection, rng, wall_with_openings
from kit.fonts import text_font

# ------------------------------------------------------------------------------------------------------------ nave
WX0, WX1, WY0, WY1 = -20.0, 10.0, 0.0, 18.0
FRAMES = (-20.0, -12.5, -5.0, 2.5, 10.0)
FFL = 1.2                         # piso a altura de andén (48")
KNEE = 2.4                        # tope del muro de concreto
EAVE = FFL + 6.0                  # línea de acero en el alero
SLOPE = 1.0 / 12.0
RIDGE = EAVE + (WY1 - WY0) / 2 * SLOPE
WT = 0.20                         # muro de concreto
RIB_T = 0.035                     # vuelo de la costilla de la lámina R (cara exterior del muro de concreto al paño)
DOORS = ((-16.25, 4.27), (-8.75, 4.27))      # cortinas: (centro x, claro) de 14 × 14 ft
DOOR_H = 4.27
PDOOR_X, PDOOR_W, PDOOR_H = -4.2, 0.914, 2.134
DOCK = (-19.4, -3.0, -3.6, 0.0)  # andén (x0, x1, y0, y1) a z FFL
RAMP = (-3.0, 6.4, -2.0, 0.0)    # rampa de la puerta de personal, baja hacia +x
# ------------------------------------------------------------------------------------------------------------ recinto
CX0, CX1, CY0, CY1 = -24.0, 22.0, -20.0, 21.0
GATE = (-14.0, -8.0)             # portón vehicular (x de los postes) en la malla del frente
APRON = (-20.0, -3.0, -16.0, -3.6)
MIL_OUTPOST = (9.5, -11.1, -90.0)   # dónde va MIL_2_avanzada respecto del pivote de MIL_1 (x, y, giro en z)
MIL_OUTPOST_Z = 0.06                # sobre la grava de MIL_1 (Z_GRAVEL)


def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def _Rz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def _Rx(deg):
    return Matrix.Rotation(math.radians(deg), 4, "X")


def _Ry(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def face_to(d):
    return _Rz({"-y": 0, "+x": 90, "+y": 180, "-x": -90}[d])


def roof_z(y):
    """Línea de acero del techo (cara inferior de la lámina) en y."""
    return EAVE + SLOPE * ((WY1 - WY0) / 2 - abs(y - (WY0 + WY1) / 2))


def cfg_mil1(bid="MIL_1_almacen"):
    return dict(id=bid, seed=131, xs=[CX0, CX1], ys=[CY0, CY1], h=[0.0], band_top=2.6,
                graffiti_bounds=(WX0 - 0.5, WX1 + 0.5, WY0 - 0.5, WY1 + 0.5), graffiti_px_per_m=150.0,
                exterior_footprint=[(WX0, WX1, WY0, WY1)],
                lookdev=dict(base_z=0.0, graffiti_mats=(), paint_tint=(0.88, 0.88, 0.86), wear=0.12, band=None, paint_sat=0.15))


LIGHTS = []
PROXIES = []


def _proxy_box(mn, mx):
    PROXIES.append([[round(c, 3) for c in mn], [round(c, 3) for c in mx]])


def _proxy(piece, M, pad=0.0):
    pts = [M @ v.co for v in piece.bm.verts]
    if pts:
        _proxy_box([min(p[i] for p in pts) - pad for i in range(3)], [max(p[i] for p in pts) + pad for i in range(3)])


# ------------------------------------------------------------------------------------------------------------ lámina R
def r_profile(L, pitch=0.3048, h=RIB_T):
    """Perfil de lámina R (PBR) a lo largo de u = 0..L: valle plano y costilla trapecial cada 12" (base 115 mm, cresta 30 mm,
    1 1/4" de alto) con dos microcostillas en el valle. Devuelve [(u, d)] con d = vuelo hacia afuera."""
    per = [(0.0, 0.0), (0.06, 0.0), (0.066, 0.004), (0.072, 0.0), (0.12, 0.0), (0.126, 0.004), (0.132, 0.0), (0.177, 0.0),
           (0.219, h), (0.249, h), (0.291, 0.0)]
    pts = []
    k = 0
    while True:
        base = k * pitch
        for (a, d) in per:
            u = base + a
            if u > L + 1e-9:
                break
            pts.append((u, d))
        else:
            k += 1
            continue
        break
    if pts[-1][0] < L - 1e-6:
        pts.append((L, _interp(per, L % pitch)))
    return pts


def _interp(per, a):
    for (u0, d0), (u1, d1) in zip(per, per[1:]):
        if u0 <= a <= u1:
            t = (a - u0) / max(u1 - u0, 1e-9)
            return d0 + (d1 - d0) * t
    return 0.0


def _prof_cut(prof, ua, ub):
    """Tramo del perfil entre ua y ub con los extremos interpolados."""
    out = []
    for (u0, d0), (u1, d1) in zip(prof, prof[1:]):
        if u1 < ua or u0 > ub:
            continue
        if u0 <= ua <= u1 and not out:
            t = (ua - u0) / max(u1 - u0, 1e-9)
            out.append((ua, d0 + (d1 - d0) * t))
        if ua < u1 < ub:
            out.append((u1, d1))
        if u0 <= ub <= u1:
            t = (ub - u0) / max(u1 - u0, 1e-9)
            out.append((ub, d0 + (d1 - d0) * t))
            break
    return out


def clad_wall(mb, M, L, z0, ztop, holes=(), mat="cladding_tan", back=0.0008):
    """Lámina R sobre un muro: plano del muro y = 0 local, exterior hacia -y, u = 0..L a lo largo de +x. La lámina va de z0 a
    ztop(u) (función o número) y se corta en los vanos holes [(u0, u1, v0, v1)]. Sólido delgado: cara corrugada + respaldo."""
    zt = ztop if callable(ztop) else (lambda u, z=ztop: z)
    prof = r_profile(L)
    cuts = sorted({0.0, L} | {h[i] for h in holes for i in (0, 1) if 0.0 < h[i] < L})
    for ua, ub in zip(cuts, cuts[1:]):
        um = (ua + ub) / 2
        blocked = sorted((h[2], h[3]) for h in holes if h[0] <= um <= h[1])
        spans = []
        lo = z0
        for (a, b) in blocked:
            if a > lo + 1e-4:
                spans.append((lo, a))
            lo = max(lo, b)
        spans.append((lo, None))
        seg = _prof_cut(prof, ua, ub)
        if len(seg) < 2:
            continue
        for (za, zb) in spans:
            top = (lambda u, zb=zb: zb) if zb is not None else zt
            if zb is None and top(um) <= za + 1e-4:
                continue
            F0 = [mb.bm.verts.new(M @ Vector((u, -d - back, za))) for (u, d) in seg]
            F1 = [mb.bm.verts.new(M @ Vector((u, -d - back, top(u)))) for (u, d) in seg]
            B0 = [mb.bm.verts.new(M @ Vector((u, 0.0, za))) for (u, d) in seg]
            B1 = [mb.bm.verts.new(M @ Vector((u, 0.0, top(u)))) for (u, d) in seg]
            n = len(seg)
            for i in range(n - 1):
                mb.face([F0[i], F0[i + 1], F1[i + 1], F1[i]], mat)
                mb.face([B0[i + 1], B0[i], B1[i], B1[i + 1]], mat)
                mb.face([F0[i + 1], F0[i], B0[i], B0[i + 1]], mat)          # canto inferior
                mb.face([F1[i], F1[i + 1], B1[i + 1], B1[i]], mat)          # canto superior
            mb.face([F0[0], F1[0], B1[0], B0[0]], mat)
            mb.face([F0[-1], B0[-1], B1[-1], F1[-1]], mat)


def wall_frames():
    """Matrices de los 4 muros (exterior hacia -y local) y su largo: frente, oriente, fondo, poniente."""
    return {
        "front": (_T(WX0, WY0, 0), WX1 - WX0),
        "east": (_T(WX1, WY0, 0) @ _Rz(90), WY1 - WY0),
        "back": (_T(WX1, WY1, 0) @ _Rz(180), WX1 - WX0),
        "west": (_T(WX0, WY1, 0) @ _Rz(-90), WY1 - WY0),
    }


def shell_walls(shell):
    """Muro perimetral de concreto (cimiento + muro bajo hasta z 2,4) con los vanos de cortinas y puerta, y lámina R arriba
    hasta el alero (frente y fondo) o hasta el remate inclinado (hastiales)."""
    W = wall_frames()
    for side, (M, L) in W.items():
        holes = []
        if side == "front":
            for (cx, w) in DOORS:
                holes.append((cx - w / 2 - WX0, cx + w / 2 - WX0, FFL, FFL + DOOR_H))
            holes.append((PDOOR_X - PDOOR_W / 2 - 0.054 - WX0, PDOOR_X + PDOOR_W / 2 + 0.054 - WX0, FFL, FFL + PDOOR_H + 0.054))
        # muro de concreto: su cara exterior al paño de las crestas de la lámina
        kw = [(h[0], h[1], h[2], min(h[3], KNEE)) for h in holes if h[2] < KNEE]
        wall_with_openings(shell, L, KNEE, WT, kw, "concrete", "concrete", "concrete", m=M @ _T(0, -RIB_T, 0))
        ztop = (lambda u: EAVE - 0.004) if side in ("front", "back") else \
            (lambda u, L=L, s=side: roof_z(WY0 + (u if s == "east" else L - u)) - 0.004)
        ch = [(h[0], h[1], max(h[2], KNEE), h[3]) for h in holes if h[3] > KNEE]
        clad_wall(shell, M, L, KNEE + 0.002, ztop, ch)


# ------------------------------------------------------------------------------------------------------------ techo
def roof(rf, det):
    """Techo de junta alzada (charolas de 24" con costura engargolada) galvanizado, caballete ventilado, remates de alero y de
    hastial color arena, canalón de caja con ganchos y bajadas, ventiladores de turbina."""
    ov = 0.15                                               # vuelo del techo en aleros y hastiales
    x0, x1 = WX0 - ov, WX1 + ov
    ym = (WY0 + WY1) / 2
    n = int((x1 - x0) / 0.6096)
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    for (ya, yb) in ((WY0 - ov, ym), (ym, WY1 + ov)):
        za, zb = roof_z(ya), roof_z(yb)
        L = math.hypot(yb - ya, zb - za)
        for i in range(n):
            u0, u1 = xs[i] + 0.012, xs[i + 1] - 0.012
            vs = [Vector((u0, ya, za)), Vector((u1, ya, za)), Vector((u1, yb, zb)), Vector((u0, yb, zb))]
            nrm = Vector((0, -(zb - za), (yb - ya))).normalized()
            if nrm.z < 0:
                nrm = -nrm
            _hexa(rf, vs + [v + nrm * 0.0012 for v in vs], "galvanized")
            Mr = _roof_m(u0, ya, za, yb, zb)
            for t in (0.33, 0.66):                           # estrías ligeras de la charola
                xm = (u1 - u0) * t
                rf.box((xm - 0.006, 0.0, 0.0012), (xm + 0.006, L, 0.0042), "galvanized", bevel=0.0, m=Mr)
        for xc in xs:                                       # costuras engargoladas de 2"
            Mr = _roof_m(xc, ya, za, yb, zb)
            cl.rbox(rf, (-0.013, 0.0, 0.0), (0.013, L, 0.012), "galvanized", r=0.003, m=Mr)
            cl.rbox(rf, (-0.006, 0.0, 0.012), (0.006, L, 0.048), "galvanized", r=0.003, m=Mr)
            rf.cyl(tuple(Mr @ Vector((0.002, 0, 0.048))), tuple(Mr @ Vector((0.002, L, 0.048))), 0.007, seg=24, mat="galvanized")
    # caballete ventilado
    zr = roof_z(ym)
    for sgn in (-1, 1):
        q = [Vector((x0, ym, zr + 0.09)), Vector((x1, ym, zr + 0.09)), Vector((x1, ym + sgn * 0.34, zr + 0.06 - 0.34 * SLOPE)),
             Vector((x0, ym + sgn * 0.34, zr + 0.06 - 0.34 * SLOPE))]
        _hexa(rf, q + [v + Vector((0, 0, 0.0015)) for v in q], "paint_tan")
    rf.box((x0, ym - 0.03, zr + 0.06), (x1, ym + 0.03, zr + 0.105), "paint_tan", bevel=0.01)
    # remates de hastial (sobre las charolas, cubren el canto) y canalón de caja
    for xg, sg in ((x0, -1), (x1, 1)):
        for (ya, yb) in ((WY0 - ov, ym), (ym, WY1 + ov)):
            _rake(det, xg, sg, ya, yb)
    for yg, sg in ((WY0 - ov, -1), (WY1 + ov, 1)):
        zg = roof_z(yg) - 0.02
        prof = [(0.0, 0.03), (0.0, -0.13), (0.01, -0.15), (0.14, -0.15), (0.15, -0.13), (0.15, 0.04), (0.16, 0.04),
                (0.16, -0.135), (0.145, -0.16), (0.005, -0.16), (-0.01, -0.135), (-0.01, 0.03)]
        V = [[det.bm.verts.new((x, yg + sg * px, zg + pz)) for (px, pz) in prof] for x in (x0, x1)]
        for j in range(len(prof) - 1):
            det.face([V[0][j], V[0][j + 1], V[1][j + 1], V[1][j]], "paint_tan")
        det.face(V[0], "paint_tan")
        det.face(list(reversed(V[1])), "paint_tan")
        for k in range(14):                                 # ganchos del canalón
            xk = x0 + 0.5 + k * (x1 - x0 - 1.0) / 13
            ya_, yb_ = sorted((yg, yg + sg * 0.15))
            det.box((xk - 0.012, ya_, zg + 0.02), (xk + 0.012, yb_, zg + 0.026), "paint_tan", bevel=0.002)
        # bajadas: en el frente solo en las esquinas (el centro del frente es andén, cortinas, puerta de personal y rampa: una
        # bajada ahí caía dentro del vano de la puerta); atrás, tres. La del poniente del frente va fuera del costado del andén.
        for xd in ((x0 + 0.40, x1 - 0.6) if sg < 0 else (x0 + 0.6, (x0 + x1) / 2 + 0.6, x1 - 0.6)):
            downspout(det, xd, WY0 if sg < 0 else WY1, sg, zg - 0.16, yg + sg * 0.075)
    # ventiladores de turbina en el caballete
    for xv in (-15.0, -7.5, 0.0, 7.5):
        turbine(det, xv, ym + 1.4, roof_z(ym + 1.4))
        turbine(det, xv + 3.75, ym - 1.4, roof_z(ym - 1.4))


def _rake(det, xg, sg, ya, yb):
    """Remate de hastial: lámina doblada en L que cubre el canto de las charolas y baja 17 cm por el muro."""
    for (a, b, c, d) in ((0.0, 0.16, 0.035, 0.050), (0.145, 0.16, -0.17, 0.050)):
        V0 = [Vector((xg - sg * 0.01 + sg * u, ya, roof_z(ya) + z)) for (u, z) in ((a, c), (b, c), (b, d), (a, d))]
        V1 = [Vector((v.x, yb, v.z - roof_z(ya) + roof_z(yb))) for v in V0]
        _hexa(det, [V0[0], V0[1], V1[1], V1[0], V0[3], V0[2], V1[2], V1[3]], "paint_tan")


def _roof_m(x, ya, za, yb, zb):
    """Marco local de un panel: origen en (x, ya, za), +y a lo largo de la pendiente, +z normal al panel."""
    t = Vector((0, yb - ya, zb - za)).normalized()
    n = Vector((0, -t.z, t.y)) if t.y > 0 else Vector((0, t.z, -t.y))
    if n.z < 0:
        n = -n
    X = Vector((1, 0, 0))
    m = Matrix((X, t, n)).transposed().to_4x4()
    m.translation = Vector((x, ya, za))
    return m


def downspout(det, x, yw, sg, ztop, ygut):
    """Bajada pluvial rectangular 3 × 4" del canalón al pie del muro, con codos, abrazaderas y salpicadero de concreto."""
    y = yw + sg * 0.09
    pts = cl.fillet([(x, ygut, ztop + 0.04), (x, ygut, ztop - 0.20), (x, y, ztop - 0.42), (x, y, 0.40), (x, y + sg * 0.22, 0.14),
                     (x, y + sg * 0.42, 0.12)], 0.10, 12)
    rect_sweep(det, pts, 0.076, 0.102, 0.008, "paint_tan", lambda p: (0, sg, 0) if p[2] > 0.5 else (0, 0, 1))
    for z in np.arange(1.0, ztop - 0.6, 2.0):            # abrazadera de fleje en U con orejas atornilladas al muro
        _ds_strap(det, x, yw, y, sg, z)
    _splash_block(det, x, y + sg * 0.25, sg)


def _ds_strap(det, x, yw, y, sg, z, w=0.076, d=0.102, t=0.0012, bw=0.025):
    """Fleje galvanizado de 1" x 18 ga doblado en U alrededor de la bajada (w a lo ancho en x, d de fondo en y), con dos orejas
    planas sobre la lámina y un tornillo de cabeza hexagonal con rondana de neopreno en cada una."""
    yf = y + sg * (d / 2 + t / 2)                         # cara del frente de la bajada
    yb = yw + sg * (0.004 + t / 2)                        # sobre la costilla de la lámina
    xa, xb = x - w / 2 - t / 2, x + w / 2 + t / 2
    path = cl.fillet([(x - w / 2 - 0.05, yb, z), (xa, yb, z), (xa, yf, z), (xb, yf, z), (xb, yb, z), (x + w / 2 + 0.05, yb, z)],
                     0.004, 3)
    prof = [(-t / 2, -bw / 2), (t / 2, -bw / 2), (t / 2, bw / 2), (-t / 2, bw / 2)]
    det.sweep(prof, path, mat="galvanized", normal=(0, 0, 1))
    for xx in (x - w / 2 - 0.028, x + w / 2 + 0.028):
        M = _T(xx, yb + sg * t / 2, z) @ (_Rx(-90) if sg < 0 else _Rx(90))
        ce.lathe(det, [(0.0, 0.0), (0.0085, 0.0), (0.0085, 0.0018), (0.0, 0.0018)], seg=24, mat="rubber", M=M)
        ce.hexnut(det, M @ _T(0, 0, 0.0018), d=0.008, mat="galvanized", washer=True)


def _splash_block(det, x, y0, sg, L=0.60, W=0.33, H=0.075):
    """Salpicadero de concreto precolado (24 x 13"): canal cóncavo con bordes redondeados, abierto hacia fuera del muro."""
    ny, nx = 13, 15
    rows = []
    for j in range(ny):
        v = j / (ny - 1)                                  # 0 en el muro, 1 en la punta
        yy = y0 + sg * L * v
        ring = []
        for i in range(nx):
            u = i / (nx - 1) * 2 - 1                      # -1..1 a lo ancho
            depth = (H - 0.018) * (1 - u * u) ** 1.5 * (0.35 + 0.65 * min(1.0, v * 4)) * (1 - 0.25 * v)
            z = H - depth
            edge = max(0.0, abs(u) - 0.86) / 0.14         # bordes redondeados
            z -= 0.012 * edge * edge
            ring.append(Vector((x + u * W / 2, yy, z)))
        rows.append(ring)
    V = [[det.bm.verts.new(p) for p in ring] for ring in rows]
    B = [[det.bm.verts.new((p.x, p.y, -0.01)) for p in ring] for ring in rows]
    for j in range(ny - 1):
        for i in range(nx - 1):
            q = [V[j][i], V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]]
            det.face(q if sg < 0 else q[::-1], "concrete")
    for j in range(ny - 1):                               # costados
        for i, rev in ((0, sg > 0), (nx - 1, sg < 0)):
            q = [V[j][i], V[j + 1][i], B[j + 1][i], B[j][i]]
            det.face(q[::-1] if rev else q, "concrete")
    for j, rev in ((0, sg > 0), (ny - 1, sg < 0)):        # testeros
        for i in range(nx - 1):
            q = [V[j][i], B[j][i], B[j][i + 1], V[j][i + 1]]
            det.face(q[::-1] if rev else q, "concrete")


def rect_sweep(mb, pts, w, h, rr, mat, hint_fn, caps=True, n=3):
    """Perfil rectangular de esquinas boleadas barrido por una polilínea 3D (hint_fn(p) = normal de apoyo en p)."""
    prof = cl.rr_profile(w, h, rr, n=n)
    P = [Vector(p) for p in pts]
    rings = []
    for i, p in enumerate(P):
        a, b = P[max(i - 1, 0)], P[min(i + 1, len(P) - 1)]
        T = (b - a).normalized()
        N = Vector(hint_fn(p))
        N = (N - T * N.dot(T))
        if N.length < 1e-6:
            N = Vector((1, 0, 0)) - T * T.x
        N.normalize()
        B = T.cross(N)
        rings.append([mb.bm.verts.new(p + B * px + N * py) for (px, py) in prof])
    k = len(prof)
    for i in range(len(rings) - 1):
        for j in range(k):
            jj = (j + 1) % k
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], mat)
    if caps:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)


def turbine(det, x, y, z):
    """Ventilador de turbina de 14" sobre base de lámina: álabes curvos de aluminio, cuello y capuchón."""
    M = _T(x, y, z)
    ce.lathe(det, [(0.0, 0.0), (0.26, 0.0), (0.26, 0.02), (0.20, 0.05), (0.19, 0.09), (0.0, 0.09)], seg=32, mat="galvanized", M=M)
    det.cyl(tuple(M @ Vector((0, 0, 0.09))), tuple(M @ Vector((0, 0, 0.32))), 0.18, seg=32, mat="galvanized", caps=False)
    det.cyl(tuple(M @ Vector((0, 0, 0.32))), tuple(M @ Vector((0, 0, 0.34))), 0.20, seg=32, mat="galvanized")
    nb = 24
    for k in range(nb):
        a = 2 * math.pi * k / nb
        pts = []
        for j in range(7):
            t = j / 6
            ang = a + 0.55 * t
            r = 0.205 + 0.05 * math.sin(math.pi * t)
            pts.append((r * math.cos(ang), r * math.sin(ang), 0.34 + 0.30 * t))
        for p0, p1 in zip(pts[:-1], pts[1:]):
            q0, q1 = M @ Vector(p0), M @ Vector(p1)
            tn = Vector((-p0[1], p0[0], 0)).normalized() * 0.022
            rd = Vector((p0[0], p0[1], 0)).normalized() * 0.0008
            _hexa(det, [q0 - tn - rd, q1 - tn - rd, q1 + tn - rd, q0 + tn - rd, q0 - tn + rd, q1 - tn + rd, q1 + tn + rd,
                        q0 + tn + rd], "aluminium")
    ce.lathe(det, [(0.0, 0.64), (0.215, 0.64), (0.22, 0.655), (0.18, 0.70), (0.10, 0.73), (0.0, 0.74)], seg=32, mat="aluminium", M=M)
    det.cyl(tuple(M @ Vector((0, 0, 0.34))), tuple(M @ Vector((0, 0, 0.64))), 0.012, seg=24, mat="steel")


# ------------------------------------------------------------------------------------------------------------ estructura
def ibeam(mb, p0, p1, d0, d1, bf=0.20, tf=0.012, tw=0.008, up=(0, 0, 1), mat="paint_tan"):
    """Perfil I (alma variable d0 -> d1) de p0 a p1; `up` = dirección del peralte."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0)
    L = ax.length
    t = ax.normalized()
    u = Vector(up)
    u = (u - t * u.dot(t)).normalized()
    s = t.cross(u)

    def P(a, w, h):
        return p0 + t * a + s * w + u * h
    for (a, b) in ((0.0, L),):
        for sgn in (-1, 1):                                  # patines
            h0 = sgn * (d0 / 2 - tf / 2)
            h1 = sgn * (d1 / 2 - tf / 2)
            vs = [P(a, -bf / 2, h0 - tf / 2), P(b, -bf / 2, h1 - tf / 2), P(b, bf / 2, h1 - tf / 2), P(a, bf / 2, h0 - tf / 2),
                  P(a, -bf / 2, h0 + tf / 2), P(b, -bf / 2, h1 + tf / 2), P(b, bf / 2, h1 + tf / 2), P(a, bf / 2, h0 + tf / 2)]
            _hexa(mb, vs, mat)
        vs = [P(a, -tw / 2, -d0 / 2 + tf), P(b, -tw / 2, -d1 / 2 + tf), P(b, tw / 2, -d1 / 2 + tf), P(a, tw / 2, -d0 / 2 + tf),
              P(a, -tw / 2, d0 / 2 - tf), P(b, -tw / 2, d1 / 2 - tf), P(b, tw / 2, d1 / 2 - tf), P(a, tw / 2, d0 / 2 - tf)]
        _hexa(mb, vs, mat)


def _hexa(mb, v, mat):
    """Hexaedro de 8 vértices (0-3 abajo, 4-7 arriba, mismo orden)."""
    V = [mb.bm.verts.new(tuple(p)) for p in v]
    for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        mb.face([V[i] for i in q], mat)


def zsection(mb, p0, p1, d=0.20, f=0.065, t=0.0025, up=(0, 0, 1), side=(1, 0, 0), mat="galvanized"):
    """Larguero Z (polín / larguero de muro) de p0 a p1; peralte d en `up`, patines hacia ±`side` (barrido del perfil)."""
    p0, p1 = Vector(p0), Vector(p1)
    tt = (p1 - p0).normalized()
    u = Vector(up)
    u = (u - tt * u.dot(tt)).normalized()
    s = Vector(side)
    s = (s - tt * s.dot(tt) - u * s.dot(u)).normalized()
    prof = [(-f, -d / 2), (-f, -d / 2 + 0.02), (-f + t, -d / 2 + 0.02), (-f + t, -d / 2 + t), (0.0, -d / 2 + t), (0.0, d / 2),
            (f, d / 2), (f, d / 2 - 0.02), (f - t, d / 2 - 0.02), (f - t, d / 2 - t), (t, d / 2 - t), (t, -d / 2)]
    rings = [[mb.bm.verts.new(tuple(p + s * a + u * b)) for (a, b) in prof] for p in (p0, p1)]
    k = len(prof)
    for j in range(k):
        jj = (j + 1) % k
        mb.face([rings[0][j], rings[0][jj], rings[1][jj], rings[1][j]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[1], mat)


def steel_frame(inter):
    """Marcos rígidos de alma variable en x -12,5 / -5 / 2,5 y marcos de hastial (columnas cada 6 m + viga C) en x -20 y 10;
    placas base con anclas, cartelas de rodilla y de cumbrera atornilladas, largueros Z de techo a 1,5 m, largueros de muro a
    1,5 m sobre el muro de concreto, puntal de alero, contraventeo de varilla con tensores en la crujía 4 (sin vanos)."""
    ym = (WY0 + WY1) / 2
    for x in FRAMES:
        end = x in (WX0, WX1)
        sx = 1 if x == WX0 else (-1 if x == WX1 else 0)
        xo = x + sx * 0.12                                 # el marco de hastial va por dentro de la lámina
        for yw, sy in ((WY0, 1), (WY1, -1)):
            yc = yw + sy * (0.20 + (0.18 if not end else 0.10))
            d0, d1 = (0.30, 0.60) if not end else (0.20, 0.20)
            ibeam(inter, (xo, yc - sy * 0.0, FFL), (xo, yc, EAVE - 0.35), d0, d1, up=(0, sy, 0))
            base_plate(inter, xo, yc, FFL)
            # rodilla: placa de unión columna-viga con 8 tornillos
            inter.box((xo - 0.12, yc - 0.32, EAVE - 0.40), (xo + 0.12, yc + 0.32, EAVE - 0.36), "paint_tan", bevel=0.003)
            for dy in (-0.26, -0.16, 0.16, 0.26):
                for dx in (-0.07, 0.07):
                    ce.hexnut(inter, _T(xo + dx, yc + dy, EAVE - 0.36), d=0.022, mat="steel")
            # viga (rafter) de alma variable de la rodilla a la cumbrera
            za = roof_z(yc) - 0.20
            ibeam(inter, (xo, yc, za - 0.30 if not end else za - 0.10), (xo, ym, roof_z(ym) - 0.20 - (0.20 if not end else 0.10)),
                  0.60 if not end else 0.20, 0.40 if not end else 0.20, up=(0, 0, 1))
        inter.box((xo - 0.13, ym - 0.03, roof_z(ym) - 0.62), (xo + 0.13, ym + 0.03, roof_z(ym) - 0.20), "paint_tan", bevel=0.003)
        if end:
            for yp in (6.0, 12.0):                         # postes del hastial
                ibeam(inter, (xo, yp, FFL), (xo, yp, roof_z(yp) - 0.42), 0.20, 0.20, up=(1, 0, 0))
                base_plate(inter, xo, yp, FFL)
    # largueros de techo (Z de 200 mm a 1,5 m sobre la pendiente) y puntales de alero
    for s in (-1, 1):
        for k in range(7):
            y = ym + s * (0.25 + k * 1.45)
            if not (WY0 + 0.3 <= y <= WY1 - 0.3):
                continue
            zz = roof_z(y) - 0.10
            zsection(inter, (WX0 + 0.02, y, zz), (WX1 - 0.02, y, zz), up=(0, -s * SLOPE, 1), side=(0, s, 0))
    for yw, sy in ((WY0, 1), (WY1, -1)):
        zsection(inter, (WX0 + 0.02, yw + sy * 0.10, EAVE - 0.10), (WX1 - 0.02, yw + sy * 0.10, EAVE - 0.10), d=0.20, up=(0, 0, 1),
                 side=(0, sy, 0))
    # largueros de muro sobre el muro de concreto
    W = wall_frames()
    for side, (M, L) in W.items():
        for z in (KNEE + 0.10, 3.9, 5.4, 6.7):
            if side in ("east", "west"):
                pass
            if side == "front" and z < FFL + DOOR_H + 0.2:
                segs = _gaps(L, [(cx - w / 2 - WX0 - 0.075, cx + w / 2 - WX0 + 0.075) for (cx, w) in DOORS] +
                             [(PDOOR_X - 0.6 - WX0, PDOOR_X + 0.6 - WX0)] if z < FFL + PDOOR_H + 0.2 else
                             [(cx - w / 2 - WX0 - 0.075, cx + w / 2 - WX0 + 0.075) for (cx, w) in DOORS])
            else:
                segs = [(0.3, L - 0.3)]
            for (ua, ub) in segs:
                zsection(inter, tuple(M @ Vector((ua, 0.10, z))), tuple(M @ Vector((ub, 0.10, z))), d=0.20,
                         up=tuple((M.to_3x3() @ Vector((0, 1, 0)))), side=(0, 0, 1))
    # contraventeo de varilla en X (techo y muros laterales) en la primera crujía, con tensores
    for (xa, xb) in ((FRAMES[3] + 0.15, FRAMES[4] - 0.15),):   # crujía 4: el muro del frente no tiene vanos ahí
        for s in (-1, 1):
            ya, yb = (WY0 + 0.4, ym - 0.4) if s < 0 else (ym + 0.4, WY1 - 0.4)
            for (p, q) in (((xa, ya), (xb, yb)), ((xa, yb), (xb, ya))):
                a = (p[0], p[1], roof_z(p[1]) - 0.24)
                b = (q[0], q[1], roof_z(q[1]) - 0.24)
                rod_turnbuckle(inter, a, b)
        for yw, sy in ((WY0, 1), (WY1, -1)):
            for (p, q) in (((xa, FFL + 0.3), (xb, EAVE - 0.5)), ((xa, EAVE - 0.5), (xb, FFL + 0.3))):
                rod_turnbuckle(inter, (p[0], yw + sy * 0.35, p[1]), (q[0], yw + sy * 0.35, q[1]))


def _gaps(L, holes):
    segs, a = [], 0.3
    for (h0, h1) in sorted(holes):
        if h0 > a + 0.1:
            segs.append((a, h0))
        a = max(a, h1)
    if L - 0.3 > a + 0.1:
        segs.append((a, L - 0.3))
    return segs


def rod_turnbuckle(mb, a, b, r=0.010):
    a, b = Vector(a), Vector(b)
    m = (a + b) / 2
    t = (b - a).normalized()
    mb.cyl(tuple(a), tuple(m - t * 0.09), r, seg=24, mat="steel", caps=True)
    mb.cyl(tuple(m + t * 0.09), tuple(b), r, seg=24, mat="steel", caps=True)
    mb.cyl(tuple(m - t * 0.10), tuple(m + t * 0.10), r * 1.9, seg=24, mat="steel")
    for e in (a, b):
        mb.cyl(tuple(e - t * 0.02), tuple(e + t * 0.02), r * 2.2, seg=24, mat="steel")


def base_plate(mb, x, y, z):
    mb.box((x - 0.17, y - 0.22, z), (x + 0.17, y + 0.22, z + 0.025), "paint_tan", bevel=0.003)
    for dx in (-0.11, 0.11):
        for dy in (-0.16, 0.16):
            ce.hexnut(mb, _T(x + dx, y + dy, z + 0.025), d=0.024, mat="galvanized")
            mb.cyl((x + dx, y + dy, z + 0.025), (x + dx, y + dy, z + 0.065), 0.0095, seg=24, mat="galvanized")
    mb.box((x - 0.20, y - 0.25, z - 0.02), (x + 0.20, y + 0.25, z + 0.0005), "concrete", bevel=0.01)     # grout


def liner(inter):
    """Aislante con cara de vinilo blanco tendido entre largueros (techo y muros): paneles con comba suave y juntas."""
    ym = (WY0 + WY1) / 2
    for s in (-1, 1):
        ys = [ym + s * (0.25 + k * 1.45) for k in range(7)]
        ys = [y for y in ys if WY0 + 0.3 <= y <= WY1 - 0.3]
        edge = WY0 + 0.15 if s < 0 else WY1 - 0.15
        ys = sorted(ys + [edge])
        for ya, yb in zip(ys[:-1], ys[1:]):
            for xa, xb in zip(FRAMES[:-1], FRAMES[1:]):
                _sag_panel(inter, xa + 0.15, xb - 0.15, ya, yb, lambda y: roof_z(y) - 0.205, 0.03)
    W = wall_frames()
    for side, (M, L) in W.items():                          # muros: una sola manta continua de la cabeza del concreto al
        _liner_wall(inter, M, L, side)                      # alero, sujeta en cada larguero y con su comba entre ellos


def _sag_panel(mb, xa, xb, ya, yb, zf, sag, nx=6, ny=4):
    V = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            u, v = i / nx, j / ny
            x = xa + (xb - xa) * u
            y = ya + (yb - ya) * v
            z = zf(y) - sag * math.sin(math.pi * v) * (0.6 + 0.4 * math.sin(math.pi * u))
            V[i, j] = mb.bm.verts.new((x, y, z))
    for i in range(nx):
        for j in range(ny):
            mb.face([V[i, j], V[i + 1, j], V[i + 1, j + 1], V[i, j + 1]], "plastic")


LINER_PINS = (KNEE + 0.10, 3.9, 5.4, 6.7)              # largueros de muro: ahí la manta queda sujeta (sin comba)


def _liner_wall(mb, M, L, side):
    """Manta de fibra de vidrio con cara de vinilo blanco (sistema de liner) en un muro: continua de la cabeza del muro de
    concreto al alero (o al remate del hastial), apretada contra la cara de cada larguero y abombada 2,5 cm entre ellos, con
    traslapes verticales engrapados cada 1,22 m (pestaña de vinilo de 5 cm) y cortada alrededor de los vanos: sobre las
    cortinas empieza arriba de la capota del rollo; sobre la puerta de personal, arriba de su marco."""
    z_lo, z_hi = LINER_PINS[0] + 0.02, LINER_PINS[-1] + 0.08
    top = (lambda u: z_hi) if side in ("front", "back") else (lambda u: min(z_hi, roof_z(WY0 + (u if side == "east" else L - u)) - 0.4))
    holes = []
    if side == "front":
        holes = [(cx - w / 2 - WX0 - 0.075, cx + w / 2 - WX0 + 0.075, FFL + DOOR_H + 0.15 + 0.66 + 0.04) for (cx, w) in DOORS] + \
                [(PDOOR_X - 0.6 - WX0, PDOOR_X + 0.6 - WX0, FFL + PDOOR_H + 0.25)]

    def dz(z):
        for za, zb in zip(LINER_PINS[:-1], LINER_PINS[1:]):
            if za <= z <= zb:
                return 0.025 * math.sin(math.pi * (z - za) / (zb - za))
        return 0.0
    cuts = sorted({0.0, L} | {h[i] for h in holes for i in (0, 1)})
    for ua, ub in zip(cuts[:-1], cuts[1:]):
        um = (ua + ub) / 2
        hz = [h[2] for h in holes if h[0] <= um <= h[1]]
        z0 = max([z_lo] + hz)
        if top(um) - z0 < 0.1:
            continue
        nn = max(2, int((ub - ua) / 0.6))
        V = {}
        zs_ = sorted({z0, *(p for p in LINER_PINS if z0 < p < z_hi)} | set(np.linspace(z0, z_hi, 22).tolist()))
        for i in range(nn + 1):
            u = ua + (ub - ua) * i / nn
            zt = top(u)
            col = [z for z in zs_ if z < zt - 0.02] + [zt]
            for j, z in enumerate(col):
                V[i, j] = mb.bm.verts.new(M @ Vector((u, 0.202 + dz(z), z)))
            V[i, "n"] = len(col)
        for i in range(nn):
            m_ = min(V[i, "n"], V[i + 1, "n"])
            for j in range(m_ - 1):
                mb.face([V[i, j], V[i, j + 1], V[i + 1, j + 1], V[i + 1, j]], "plastic")
        # traslapes verticales engrapados (pestaña de 5 cm, 2 mm por dentro de la manta)
        u = ua + 0.61
        while u < ub - 0.3:
            zt = top(u)
            col = [z for z in zs_ if z < zt - 0.02] + [zt]
            A_ = [mb.bm.verts.new(M @ Vector((u - 0.025, 0.2045 + dz(z), z))) for z in col]
            B_ = [mb.bm.verts.new(M @ Vector((u + 0.025, 0.2045 + dz(z), z))) for z in col]
            for j in range(len(col) - 1):
                mb.face([A_[j], A_[j + 1], B_[j + 1], B_[j]], "plastic")
            u += 1.22


def sprinklers(inter):
    """Rociadores (almacén de explosivos): troncal de 4" bajo el caballete con coples ranurados, ramales de 1 1/4" cada 3 m
    hacia los aleros con colgantes de varilla y rociadores colgantes cada 3 m, montante con válvula y manómetro junto a la
    puerta de personal."""
    ym = (WY0 + WY1) / 2
    zt = roof_z(ym) - 0.75
    x0, x1 = WX0 + 0.6, WX1 - 0.6
    inter.cyl((x0, ym, zt), (x1, ym, zt), 0.057, seg=24, mat="sign_red")
    for x in np.arange(x0 + 1.5, x1, 6.0):                  # coples ranurados
        inter.cyl((x - 0.03, ym, zt), (x + 0.03, ym, zt), 0.066, seg=24, mat="sign_red")
    for x in np.arange(x0 + 0.9, x1, 3.0):
        for s in (-1, 1):
            y_end = ym + s * 7.6
            zb = lambda y: roof_z(y) - 0.62                  # el ramal sigue la pendiente del techo
            P = [(x, ym + s * 0.06, zt), (x, ym + s * 0.25, zb(ym + s * 0.25)), (x, y_end, zb(y_end))]
            inter.tube(P, 0.021, seg=24, mat="sign_red")
            inter.cyl((x, ym + s * 0.0, zt - 0.075), (x, ym + s * 0.0, zt + 0.075), 0.03, seg=24, mat="sign_red") if s < 0 else None
            for k in range(1, 3):
                y = ym + s * (k * 3.0 - 0.5)
                z = zb(y)
                inter.cyl((x, y, z), (x, y, z - 0.07), 0.012, seg=24, mat="sign_red")
                ce.lathe(inter, [(0.0, 0.0), (0.011, 0.0), (0.013, -0.01), (0.008, -0.025), (0.004, -0.035), (0.025, -0.040),
                                 (0.026, -0.044), (0.0, -0.045)], seg=24, mat="brass", M=_T(x, y, z - 0.07))
            for y in (ym + s * 2.0, ym + s * 6.0):          # colgantes de varilla a los largueros
                z = zb(y)
                inter.cyl((x, y, z + 0.025), (x, y, roof_z(y) - 0.2), 0.0048, seg=24, mat="steel")
                ce.lathe(inter, [(0.018, -0.006), (0.026, -0.006), (0.026, 0.006), (0.018, 0.006)], seg=24, mat="steel",
                         M=_T(x, y, z + 0.025))
    # montante con válvula de compuerta y manómetro
    xr, yr = PDOOR_X + 1.6, WY0 + 0.45
    inter.cyl((xr, yr, FFL), (xr, yr, zt), 0.057, seg=24, mat="sign_red")
    inter.tube(cl.fillet([(xr, yr, zt), (xr, yr, zt + 0.15), (xr, ym - 0.2, zt + 0.15), (xr, ym, zt)], 0.15, 6), 0.057, seg=24,
               mat="sign_red")
    ce.lathe(inter, [(0.0, 0.0), (0.09, 0.0), (0.09, 0.18), (0.07, 0.20), (0.07, 0.30), (0.0, 0.30)], seg=32, mat="sign_red",
             M=_T(xr, yr, FFL + 1.0))
    inter.cyl((xr, yr, FFL + 1.30), (xr, yr, FFL + 1.75), 0.012, seg=24, mat="steel")
    ce.lathe(inter, [(0.0, 0.0), (0.12, 0.0), (0.12, 0.01), (0.0, 0.02)], seg=32, mat="steel", M=_T(xr, yr, FFL + 1.75))
    ce.lathe(inter, [(0.0, 0.0), (0.05, 0.0), (0.05, 0.03), (0.0, 0.035)], seg=32, mat="glass", M=_T(xr, yr - 0.07, FFL + 1.15) @ _Rx(90))


def floor_slab(inter):
    """Losa del almacén a nivel de andén con juntas de control aserradas cada 7,5 × 6 m y líneas amarillas de pasillo."""
    x0, x1, y0, y1 = WX0 + WT - 0.04, WX1 - WT + 0.04, WY0 + WT - 0.04, WY1 - WT + 0.04
    inter.box((x0, y0, 0.0), (x1, y1, FFL), "concrete", bevel=0.0)
    for x in FRAMES[1:-1]:
        inter.box((x - 0.003, y0, FFL - 0.004), (x + 0.003, y1, FFL + 0.0004), "rubber", bevel=0.0)
    for y in (6.0, 12.0):
        inter.box((x0, y - 0.003, FFL - 0.004), (x1, y + 0.003, FFL + 0.0004), "rubber", bevel=0.0)


# ------------------------------------------------------------------------------------------------------------ frente
def dock(det):
    """Andén de concreto con ángulo de canto, defensas de hule, nivelador de canto, franjas amarillas, topes de llanta y bolardos
    en las jambas; rampa con barandal de tubo amarillo hasta la puerta de personal."""
    x0, x1, y0, y1 = DOCK
    cl.rbox(det, (x0, y0, -0.05), (x1, y1 - 0.01, FFL), "concrete", r=0.02)
    # tapones de grout de los moños de la cimbra (rejilla de 0,6 m), salvo donde van defensas y niveladores
    busy = [(cx - w / 2 + 0.2, cx + w / 2 - 0.2) for (cx, w) in DOORS]
    for z in (0.25, 0.75):
        xk = x0 + 0.30
        while xk < x1 - 0.2:
            if not any(a <= xk <= b for (a, b) in busy):
                ce.lathe(det, [(0.0, 0.0), (0.0175, 0.0), (0.0185, 0.0005), (0.016, 0.0013), (0.0, 0.0015)], seg=24,
                         mat="concrete", M=_T(xk, y0, z) @ _Rx(90))
            xk += 0.60
    det.box((x0, y0 - 0.008, FFL - 0.10), (x1, y0 + 0.002, FFL + 0.004), "steel", bevel=0.002)      # ángulo de canto
    det.box((x0, y0 + 0.002, FFL - 0.006), (x1, y0 + 0.10, FFL + 0.004), "steel", bevel=0.001)
    for (cx, w) in DOORS:
        for dx in (-1.15, 1.15):                            # defensas de hule laminado: dentro del ancho del remolque (2,44-2,6 m),
                                                            # junto a los bordes del nivelador de 2 m (MHI / Blue Giant)
            bump = cl.MB()
            for k in range(8):
                bump.box((-0.125, -0.115 + 0.0, 0.0 + k * 0.057), (0.125, 0.0, 0.052 + k * 0.057), "rubber", bevel=0.004)
            bump.box((-0.14, -0.01, -0.01), (0.14, 0.0, 0.47), "steel", bevel=0.003)
            for zz in (0.06, 0.40):
                for xx in (-0.10, 0.10):
                    ce.hexnut(bump, _T(xx, -0.118, zz) @ _Rx(90), d=0.018, mat="steel")
            det.join(bump, _T(cx + dx, y0, FFL - 0.62))
        # nivelador de canto (placa con labio abatible)
        det.box((cx - 1.0, y0 + 0.0, FFL + 0.0), (cx + 1.0, y0 + 0.45, FFL + 0.012), "steel", bevel=0.002)
        for k in range(18):
            xk = cx - 0.95 + k * 0.11
            det.box((xk, y0 + 0.02, FFL + 0.012), (xk + 0.05, y0 + 0.43, FFL + 0.016), "steel", bevel=0.0008)
        det.box((cx - 1.0, y0 - 0.10, FFL - 0.012), (cx + 1.0, y0 + 0.002, FFL + 0.010), "steel", bevel=0.002)
        # franjas amarillas de seguridad en el canto del andén
        for k in range(10):
            xk = cx - 2.4 + k * 0.48
            if abs(xk + 0.12 - cx) < 1.1:
                continue
            det.box((xk, y0 + 0.11, FFL), (xk + 0.24, y0 + 0.31, FFL + 0.0015), "paint_yellow", bevel=0.0)
        # bolardos en las jambas
        for dx in (-w / 2 - 0.25, w / 2 + 0.25):
            bollard(det, cx + dx, -0.30, FFL)
    # rampa de concreto con barandal
    rx0, rx1, ry0, ry1 = RAMP
    tmp = MB()
    tmp.box((rx0, ry0, -0.05), (rx1, ry1 - 0.01, FFL), "concrete", bevel=0.012, seg=2)   # aristas boleadas de llana
    for v in tmp.bm.verts:
        if v.co.z > FFL - 0.05:                            # la cara de arriba (y su bisel) sigue la pendiente
            dz = FFL - v.co.z
            top = FFL - (FFL) * max(0.0, (v.co.x - (rx0 + 0.9))) / (rx1 - rx0 - 0.9)
            v.co.z = max(top, 0.035) - dz
    det.join(tmp)
    rail_y = ry0 + 0.05
    pts = [(rx0 + 0.05, rail_y), (rx0 + 0.9, rail_y), (rx1 - 0.05, rail_y)]
    def zr(x):
        return FFL - FFL * max(0.0, (x - (rx0 + 0.9))) / (rx1 - rx0 - 0.9)
    for hh in (0.92, 0.50):
        P = [(x, y, max(zr(x), 0.02) + hh) for (x, y) in pts]
        P = [(P[0][0] - 0.25, rail_y, P[0][2])] + P + [(P[-1][0] + 0.30, rail_y, 0.02 + hh)]
        det.tube(cl.fillet(P, 0.12, 6), 0.021, seg=24, mat="paint_yellow")
    for x in np.linspace(rx0 + 0.05, rx1 - 0.05, 6):
        z0 = max(zr(x), 0.02)
        det.cyl((x, rail_y, z0 - 0.02), (x, rail_y, z0 + 0.92), 0.024, seg=24, mat="paint_yellow")
        det.box((x - 0.06, rail_y - 0.06, z0), (x + 0.06, rail_y + 0.06, z0 + 0.008), "steel", bevel=0.002)


STAIR_Y = (-2.9, -1.9)            # escalera de personal del andén (cabecera poniente): ancho libre entre zancas
STAIR_PAD = (-21.45, -19.42, -3.15, -1.65)


def _frame_x(p0, p1, up=(0, 1, 0)):
    """Marco local: +x de p0 a p1, +y = up (proyectado), +z = x × y; origen en p0."""
    X = (Vector(p1) - Vector(p0)).normalized()
    Yv = (Vector(up) - X * X.dot(Vector(up))).normalized()
    M = Matrix((X, Yv, X.cross(Yv))).transposed().to_4x4()
    M.translation = Vector(p0)
    return M


def dock_stair(det):
    """Escalera de acero de personal en la cabecera poniente del andén (IBC 1011: contrahuella <= 178 mm, huella >= 279 mm):
    7 contrahuellas de 157 mm y huellas de 280 mm; zancas de canal MC 200 × 75 galvanizado con placa base anclada al descanso
    de concreto y ángulos de conexión atornillados al canto del andén; peldaños de rejilla electrosoldada (soleras 30 × 3 a
    30 mm, varilla Ø 6 a 100 mm) con nariz de placa antiderrapante y placas de apoyo atornilladas a las zancas; barandales de
    tubo de 42 mm amarillo de seguridad a 0,90 m de las narices con curvas de radio real y prolongación de 0,30 m arriba y
    abajo (pasamanos continuo) e intermedio a 0,45 m, postes atornillados por fuera de las zancas."""
    ys0, ys1 = STAIR_Y
    XT = DOCK[0]
    zp = Z_GRAVEL + 0.04
    N = 7
    rr = (FFL - zp) / N
    g = 0.28
    xn = lambda k: XT - (N - k) * g                     # noqa: E731  nariz del peldaño k (1..N-1); el N es el andén
    slope = rr / g
    ang = math.degrees(math.atan2(rr, g))
    # ---- zancas (canal MC 200 × 75 × 9,5, patines hacia afuera)
    for yw, sg in ((ys0, -1), (ys1, 1)):
        zb_ = lambda x: zp + rr + (x - xn(1)) * slope - 0.05   # noqa: E731  eje de la zanca bajo la línea de narices
        xa = xn(1) - 0.06 - 0.10 / slope
        xb = XT - 0.012
        p0, p1 = (xa, yw, zb_(xa)), (xb, yw, zb_(xb))
        M = _frame_x(p0, p1, up=(0, 0, 1))
        L = (Vector(p1) - Vector(p0)).length
        so = -sg                                          # z local = -y del mundo: el alma y los patines quedan por fuera
        cl.rbox(det, (0.0, -0.10, min(0.0, so * 0.0095)), (L, 0.10, max(0.0, so * 0.0095)), "galvanized", r=0.002, m=M)
        for zf in (-0.10, 0.10 - 0.011):
            cl.rbox(det, (0.0, zf, min(0.0, so * 0.075)), (L, zf + 0.011, max(0.0, so * 0.075)), "galvanized", r=0.002, m=M)
        # placa base al descanso y ángulo de conexión al canto del andén
        cl.rbox(det, (xa - 0.02, yw - 0.09, zp), (xa + 0.24, yw + 0.09, zp + 0.012), "galvanized", r=0.003)
        for (dx, dy) in ((0.03, -0.06), (0.03, 0.06), (0.20, -0.06), (0.20, 0.06)):
            ce.hexnut(det, _T(xa + dx, yw + dy, zp + 0.012), d=0.016, mat="galvanized")
        cl.rbox(det, (XT - 0.010, yw - 0.10, FFL - 0.30), (XT, yw + 0.10, FFL - 0.08), "galvanized", r=0.002)
        cl.rbox(det, (XT - 0.10, min(yw, yw + sg * 0.010), FFL - 0.30), (XT, max(yw, yw + sg * 0.010), FFL - 0.08), "galvanized",
                r=0.002)
        for zz in (FFL - 0.25, FFL - 0.13):
            for dy in (-0.06, 0.06):
                ce.hexnut(det, _T(XT - 0.010, yw + dy, zz) @ _Ry(-90), d=0.016, mat="galvanized")
    # ---- peldaños de rejilla con nariz antiderrapante y placas de apoyo
    w = ys1 - ys0
    for k in range(1, N):
        zt = zp + k * rr
        x0, x1 = xn(k), xn(k) + g + 0.025
        nb = int((x1 - x0) / 0.030)
        for i in range(nb + 1):                           # soleras portantes (a lo ancho, entre zancas)
            xb_ = x0 + 0.012 + i * (x1 - x0 - 0.024) / nb
            det.box((xb_ - 0.0015, ys0 + 0.006, zt - 0.030), (xb_ + 0.0015, ys1 - 0.006, zt), "galvanized", bevel=0.0004)
        for j in range(int(w / 0.10)):                    # varilla transversal hundida a ras
            yv = ys0 + 0.05 + j * 0.10
            det.cyl((x0 + 0.004, yv, zt - 0.003), (x1 - 0.004, yv, zt - 0.003), 0.003, seg=12, mat="galvanized")
        cl.rbox(det, (x0 - 0.002, ys0 + 0.006, zt - 0.032), (x0 + 0.032, ys1 - 0.006, zt + 0.0015), "steel", r=0.002)   # nariz
        for j in range(int(w / 0.025)):                   # gajos del antiderrapante
            yv = ys0 + 0.02 + j * 0.025
            det.box((x0 + 0.004, yv - 0.004, zt + 0.0015), (x0 + 0.028, yv + 0.004, zt + 0.0035), "steel", bevel=0.0008)
        for yw, sg in ((ys0, 1), (ys1, -1)):              # placas de apoyo atornilladas al alma de la zanca
            cl.rbox(det, (x0, min(yw, yw + sg * 0.006), zt - 0.075), (x1, max(yw, yw + sg * 0.006), zt), "galvanized", r=0.002)
            for xx in (x0 + 0.06, x1 - 0.06):
                ce.hexnut(det, _T(xx, yw + sg * 0.006, zt - 0.045) @ (_Rx(-90) if sg > 0 else _Rx(90)), d=0.012, mat="galvanized")
    # ---- barandales (pasamanos continuo con prolongaciones) y postes por fuera de las zancas
    for yw, sg in ((ys0, -1), (ys1, 1)):
        yr = yw + sg * 0.115
        for hh, rad in ((0.90, 0.021), (0.45, 0.0168)):
            P = [(xn(1) - 0.30, yr, zp + rr + hh), (xn(1), yr, zp + rr + hh), (XT, yr, FFL + hh), (XT + 0.30, yr, FFL + hh)]
            P = [(P[0][0], yr, P[0][2] - 0.10)] + P + [(P[-1][0], yr, P[-1][2] - 0.10)] if hh > 0.5 else P
            det.tube(cl.fillet(P, 0.09, 10), rad, seg=24, mat="paint_yellow")
            for e in (P[0], P[-1]):
                ce.lathe(det, [(0.0, 0.0), (rad, 0.0), (rad * 0.7, rad * 0.5), (0.0, rad * 0.6)], seg=24, mat="paint_yellow",
                         M=_T(*e) @ (_Rx(180) if hh > 0.5 else (_Ry(-90) if e[0] < XT else _Ry(90))))
        for k in (1, 4, N - 1):
            xp = xn(k) + 0.14
            zn = zp + rr + (xp - xn(1)) * slope
            det.cyl((xp, yr, zn - 0.24), (xp, yr, zn + 0.90), 0.021, seg=24, mat="paint_yellow")
            ce.lathe(det, [(0.0, 0.0), (0.021, 0.0), (0.0, 0.004)], seg=24, mat="paint_yellow", M=_T(xp, yr, zn - 0.24) @ _Rx(180))
            cl.rbox(det, (xp - 0.05, min(yr, yw + sg * 0.075), zn - 0.22), (xp + 0.05, max(yr, yw + sg * 0.075), zn - 0.08),
                    "paint_yellow", r=0.002)                # placa de fijación lateral sobre las puntas de los patines
            for dx in (-0.032, 0.032):                       # tornillos pasados a la zanca (cabeza en la cara de la placa)
                ce.hexnut(det, _T(xp + dx, yw + sg * 0.075, zn - 0.15) @ (_Rx(-90) if sg < 0 else _Rx(90)),
                          d=0.012, mat="galvanized")
    _proxy_box((xn(1) - 0.35, ys0 - 0.15, 0.0), (XT, ys1 + 0.15, FFL + 1.0))


def bollard(det, x, y, z, h=1.07):
    det.cyl((x, y, z - 0.03), (x, y, z + h - 0.07), 0.0572, seg=32, mat="paint_yellow")
    ce.lathe(det, [(0.0, 0.0), (0.0572, 0.0), (0.052, 0.012), (0.046, 0.04), (0.032, 0.062), (0.016, 0.070), (0.0, 0.072)],
             seg=32, mat="paint_yellow", M=_T(x, y, z + h - 0.07))


Y_JAMB = WY0 + 0.205                # cara interior de las jambas de PTR del vano (al paño de los largueros de muro)


def door_frame(det, cx, w):
    """Vano enmarcado de la cortina (edificio metálico): jambas de canal C 200 × 75 de la cabeza del muro de concreto al
    cerramiento, cerramiento de canal C sobre el vano, ángulos de 100 × 100 anclados a la cara interior del muro de concreto
    (donde se atornillan las guías abajo) y, por fuera, remate de lámina en J que tapa el canto cortado de la lámina R en las
    jambas y la cabeza, con gotero en la cabeza."""
    x0, x1 = cx - w / 2, cx + w / 2
    z1 = FFL + DOOR_H
    for (xa, xb) in ((x0 - 0.075, x0), (x1, x1 + 0.075)):          # jambas de canal C (alma al vano)
        sg = -1 if xa < x0 else 1
        xw = x0 if sg < 0 else x1                                 # alma al paño del vano
        cl.rbox(det, (min(xw, xw + sg * 0.008), WY0 + 0.002, KNEE), (max(xw, xw + sg * 0.008), Y_JAMB, z1 + 0.20), "paint_tan", r=0.002)
        for yf in (WY0 + 0.002, Y_JAMB - 0.010):                 # patines
            cl.rbox(det, (min(xw, xw + sg * 0.075), yf, KNEE), (max(xw, xw + sg * 0.075), yf + 0.008, z1 + 0.20), "paint_tan", r=0.002)
        cl.rbox(det, (min(xw, xw + sg * 0.16), WY0 + 0.0, KNEE - 0.012), (max(xw, xw + sg * 0.16), Y_JAMB, KNEE), "paint_tan", r=0.002)
        for yy in (0.05, 0.15):                                   # anclas de la placa de asiento sobre el muro
            ce.hexnut(det, _T(xw + sg * 0.11, WY0 + yy, KNEE), d=0.016, mat="steel")
        # jamba baja: PTR 100 × 40 anclado a la cara interior del muro de concreto (asiento de las guías bajo la cabeza del muro)
        yc = WY0 - RIB_T + WT
        cl.rbox(det, (min(xw, xw + sg * 0.10), yc, FFL), (max(xw, xw + sg * 0.10), Y_JAMB, KNEE - 0.012), "paint_tan", r=0.003)
        for zz in np.arange(FFL + 0.25, KNEE - 0.1, 0.45):        # taquetes de expansión con tuerca
            ce.hexnut(det, _T(xw + sg * 0.06, Y_JAMB, zz) @ _Rx(-90), d=0.014, mat="steel")
    # cerramiento (canal C) sobre el vano
    cl.rbox(det, (x0 - 0.075, WY0 + 0.002, z1 + 0.20), (x1 + 0.075, Y_JAMB, z1 + 0.208), "paint_tan", r=0.002)
    for yf in (WY0 + 0.002, Y_JAMB - 0.010):
        cl.rbox(det, (x0 - 0.075, yf, z1 + 0.208 - 0.075), (x1 + 0.075, yf + 0.008, z1 + 0.208), "paint_tan", r=0.002)
    cl.rbox(det, (x0 - 0.075, WY0 + 0.002, z1), (x1 + 0.075, Y_JAMB, z1 + 0.008), "paint_tan", r=0.002)
    # remate exterior en J: tapa el canto de la lámina R en jambas y cabeza (la cabeza con gotero)
    ye = WY0 - RIB_T
    for xw, sg in ((x0, -1), (x1, 1)):
        cl.rbox(det, (min(xw, xw + sg * 0.060), ye - 0.010, KNEE + 0.002), (max(xw, xw + sg * 0.060), ye - 0.0005, z1 + 0.03),
                "paint_tan", r=0.0015)
        cl.rbox(det, (min(xw, xw + sg * 0.0012), ye - 0.010, KNEE + 0.002), (max(xw, xw + sg * 0.0012), WY0 + 0.004, z1),
                "paint_tan", r=0.0006)
    cl.rbox(det, (x0 - 0.065, ye - 0.010, z1), (x1 + 0.065, WY0 + 0.004, z1 + 0.0012), "paint_tan", r=0.0006)
    cl.rbox(det, (x0 - 0.065, ye - 0.030, z1 + 0.0012), (x1 + 0.065, ye - 0.0005, z1 + 0.06), "paint_tan", r=0.0015)
    det.box((x0 - 0.065, ye - 0.042, z1 - 0.012), (x1 + 0.065, ye - 0.030, z1 + 0.0012), "paint_tan", bevel=0.0005)


def rollup_door(det, cx, w, seed=0, damaged=False, inside=True):
    """Cortina de acero de 14 × 14 ft MONTADA POR DENTRO (lo normal en un almacén con material sensible: guías, rollo y
    operador no se alcanzan desde el patio): caja del rollo (capota) con tapas laterales sobre el cerramiento, guías de canal
    con burlete atornilladas a las jambas, cortina de duelas curvas entrelazadas con costillas, barra inferior con astrágalo
    de hule, cerrojos de pasador con candado (por dentro), cadena de operación manual con su polea (por dentro).
    damaged: las tres duelas bajas abolladas hacia adentro, marcas de palanca y pintura rayada en la cara de afuera de la
    barra inferior (intento de saqueo que no pasó). inside=False: montaje exterior anterior."""
    r = rng(seed)
    if inside:
        yb, s = Y_JAMB, 1.0                # plano de montaje y sentido hacia el lado de la cortina (adentro)
    else:
        yb, s = WY0 - RIB_T, -1.0

    def Y(off):
        return yb + s * off

    def yy(a, b):
        return (min(Y(a), Y(b)), max(Y(a), Y(b)))
    z0, z1 = FFL, FFL + DOOR_H
    x0, x1 = cx - w / 2, cx + w / 2
    # guías
    for xg, sg in ((x0, -1), (x1, 1)):
        ya, yb_ = yy(0.005, 0.16)
        xa, xb = (xg - 0.11, xg) if sg < 0 else (xg, xg + 0.11)
        det.box((xa, ya, z0), (xb, yb_, z1 + 0.15), "galvanized", bevel=0.004)
        ya, yb_ = yy(0.04, 0.12)
        det.box((xg - 0.004 if sg < 0 else xg, ya, z0), (xg if sg < 0 else xg + 0.004, yb_, z1), "rubber", bevel=0.0)
        for zz in np.arange(z0 + 0.3, z1, 0.6):              # tornillos de la guía a la jamba
            ce.hexnut(det, _T(xg + sg * 0.055, Y(0.16), zz) @ (_Rx(-90) if s > 0 else _Rx(90)), d=0.012, mat="steel")
    # capota del rollo (sobre el cerramiento, del lado del rollo)
    zc = z1 + 0.15
    det.cyl((x0 - 0.15, Y(0.30), zc + 0.30), (x1 + 0.15, Y(0.30), zc + 0.30), 0.30, seg=48, mat="galvanized")
    det.box((x0 - 0.15, yy(0.30, 0.60)[0], zc), (x1 + 0.15, yy(0.30, 0.60)[1], zc + 0.30), "galvanized", bevel=0.004)
    for xs in (x0 - 0.17, x1 + 0.15):
        det.box((xs, yy(0.0, 0.62)[0], zc - 0.02), (xs + 0.02, yy(0.0, 0.62)[1], zc + 0.64), "galvanized", bevel=0.004)
    # cortina: duelas de 3" con costilla
    n = int(DOOR_H / 0.0762)
    zs = np.linspace(z0 + 0.10, z1, n + 1)
    for i in range(n):
        za, zb = zs[i], zs[i + 1]
        dent = 0.0
        if damaged and i < 4:
            dent = (0.05 - 0.012 * i)
        prof = [(-0.020 * math.sin(math.pi * t) ** 0.8 - 0.003 * math.sin(2 * math.pi * t), za + (zb - za) * t)
                for t in np.linspace(0.0, 1.0, 11)]                 # duela curva con costilla central, sin facetas
        nx = 24
        V, B = [], []
        for k in range(nx + 1):
            x = x0 + 0.02 + (w - 0.04) * k / nx
            dd = 0.0
            if dent:
                c = cx + 0.6
                dd = dent * math.exp(-((x - c) / 0.75) ** 2)      # hacia adentro del edificio (+y)
            V.append([det.bm.verts.new((x, Y(0.07) + dy + dd, z)) for (dy, z) in prof])
            B.append([det.bm.verts.new((x, Y(0.07) + dy * 0.55 + dd + 0.0035, z)) for (dy, z) in prof])   # cara de adentro
        for k in range(nx):
            for j in range(len(prof) - 1):
                det.face([V[k][j], V[k][j + 1], V[k + 1][j + 1], V[k + 1][j]], "galvanized")
                det.face([B[k + 1][j], B[k + 1][j + 1], B[k][j + 1], B[k][j]], "galvanized")
            for j in (0, len(prof) - 1):                          # canto de la duela (cierra la lámina)
                q = [V[k][j], V[k + 1][j], B[k + 1][j], B[k][j]]
                det.face(q if j == 0 else list(reversed(q)), "galvanized")
        for k in (0, nx):
            ring = V[k] + list(reversed(B[k]))
            det.face(ring if k == 0 else list(reversed(ring)), "galvanized")
    # barra inferior y astrágalo
    det.box((x0 + 0.02, yy(0.05, 0.11)[0], z0 + 0.03), (x1 - 0.02, yy(0.05, 0.11)[1], z0 + 0.10), "galvanized", bevel=0.006)
    det.box((x0 + 0.02, yy(0.065, 0.095)[0], z0 + 0.002), (x1 - 0.02, yy(0.065, 0.095)[1], z0 + 0.03), "rubber", bevel=0.006)
    # cerrojos de pasador con candado (del lado del rollo: por dentro si va montada por dentro)
    for xl, sg in ((x0 + 0.25, -1), (x1 - 0.25, 1)):
        det.box((xl - 0.08, yy(0.105, 0.125)[0], z0 + 0.12), (xl + 0.08, yy(0.105, 0.125)[1], z0 + 0.20), "steel", bevel=0.003)
        det.cyl((xl - 0.05 * sg, Y(0.14), z0 + 0.16), (xl + 0.22 * sg, Y(0.14), z0 + 0.16), 0.010, seg=24, mat="steel")
        padlock(det, xl + 0.10 * sg, Y(0.17), z0 + 0.12, r)
    if damaged:
        # marcas de palanca en la cara de AFUERA de la barra inferior (la del vano), junto al extremo derecho
        yo = min(Y(0.05), Y(0.11)) if s > 0 else Y(0.11)
        for k in range(5):
            xm = x1 - 0.55 + r.uniform(-0.15, 0.15)
            zm = z0 + 0.04 + r.uniform(0, 0.05)
            a = r.uniform(-30, 30)
            M = _T(xm, yo - 0.0005 if s > 0 else yo - 0.0035, zm) @ _Ry(a)
            det.box((-0.045, -0.0012, -0.004), (0.045, 0.0002, 0.004), "steel", bevel=0.0006, m=M)
    # cadena de operación con polea y gancho de seguro
    xc = x1 + 0.06
    det.cyl((xc, Y(0.25), z1 + 0.30), (xc + 0.04, Y(0.25), z1 + 0.30), 0.10, seg=32, mat="steel")
    ce.chain(det, [(xc + 0.02, Y(0.33), z1 + 0.25), (xc + 0.02, Y(0.33), z0 + 1.0), (xc + 0.02, Y(0.20), z0 + 0.95),
                   (xc + 0.02, Y(0.18), z1 + 0.25)], link=0.03, wire=0.003, mat="steel")
    det.box((xc - 0.01, yy(0.005, 0.20)[0], z0 + 1.0), (xc + 0.05, yy(0.005, 0.20)[1], z0 + 1.06), "steel", bevel=0.003)


def padlock(mb, x, y, z, r):
    """Candado laminado con arco de acero templado."""
    mb.box((x - 0.030, y - 0.014, z), (x + 0.030, y + 0.014, z + 0.050), "steel", bevel=0.004)
    for k in range(6):
        mb.box((x - 0.031, y - 0.0145, z + 0.004 + k * 0.0075), (x + 0.031, y + 0.0145, z + 0.0055 + k * 0.0075), "steel", bevel=0.0)
    pts = [(x - 0.016, y, z + 0.050)] + [(x + 0.016 * math.cos(math.pi * (1 - t)), y, z + 0.060 + 0.022 * math.sin(math.pi * t))
                                         for t in np.linspace(0, 1, 9)] + [(x + 0.016, y, z + 0.050)]
    mb.tube(pts, 0.0045, seg=14, mat="steel")
    mb.cyl((x, y - 0.0146, z + 0.018), (x, y - 0.016, z + 0.018), 0.006, seg=24, mat="brass")


def personnel_door(det, ang=68.0):
    """Puerta de personal de lámina reforzada de 36 × 84" (abierta), marco de lámina, bisagras de nudillo, barra de pánico
    por dentro, manija y cerrojo, teclado de acceso, cierrapuertas, placa de patada (rayada por un intento de forzarla) y
    marquesina de lámina con ménsulas."""
    y0 = WY0 - RIB_T
    x0, x1 = PDOOR_X - PDOOR_W / 2, PDOOR_X + PDOOR_W / 2
    zf = FFL
    for (xa, xb) in ((x0 - 0.05, x0), (x1, x1 + 0.05)):
        cl.rbox(det, (xa, y0 - 0.006, zf), (xb, y0 + WT + 0.006, zf + PDOOR_H), "paint_tan", r=0.003)
    cl.rbox(det, (x0 - 0.05, y0 - 0.006, zf + PDOOR_H), (x1 + 0.05, y0 + WT + 0.006, zf + PDOOR_H + 0.05), "paint_tan", r=0.003)
    for (xa, xb) in ((x0, x0 + 0.016), (x1 - 0.016, x1)):
        cl.rbox(det, (xa, y0 + 0.052, zf), (xb, y0 + 0.068, zf + PDOOR_H), "paint_tan", r=0.002)
    cl.rbox(det, (x0, y0 + 0.052, zf + PDOOR_H - 0.016), (x1, y0 + 0.068, zf + PDOOR_H), "paint_tan", r=0.002)
    cl.rbox(det, (x0, y0 - 0.035, zf), (x1, y0 + WT, zf + 0.010), "aluminium", r=0.003)
    M = _T(x0 + 0.002, y0 + 0.002, zf + 0.006) @ _Rz(-ang)
    leaf = cl.MB()
    W, H, T = 0.905, PDOOR_H - 0.010, 0.045
    cl.rbox(leaf, (0.004, 0.0, 0.0), (W, T, H), "paint_tan", r=0.004)
    leaf.box((0.03, -0.0018, 0.010), (W - 0.03, -0.0002, 0.26), "steel", bevel=0.0007)          # placa de patada
    for k in range(4):                                       # rayones de palanca en la placa y el canto de la cerradura
        leaf.box((W - 0.10 - 0.03 * k, -0.0021, 0.90 + 0.05 * k), (W - 0.02 - 0.03 * k, -0.0017, 0.904 + 0.05 * k), "steel",
                 bevel=0.0)
    for z in (0.20, 1.06, H - 0.30):
        leaf.cyl((0.0, -0.004, z), (0.0, -0.004, z + 0.114), 0.0095, seg=24, mat="steel")
        leaf.box((0.004, -0.0028, z + 0.004), (0.050, -0.0004, z + 0.110), "steel", bevel=0.0008)
    lx = W - 0.068
    for (side, yy) in ((-1, 0.0), (1, T)):
        R = _T(lx, yy, 1.02) @ _Rx(90 if side < 0 else -90)
        ce.lathe(leaf, [(0.0, 0.0), (0.034, 0.0), (0.036, 0.003), (0.034, 0.008), (0.018, 0.012), (0.016, 0.022), (0.0, 0.022)],
                 seg=32, mat="steel", M=R)
        path = cl.fillet([(lx, yy + side * 0.020, 1.02), (lx, yy + side * 0.058, 1.02), (lx - 0.125, yy + side * 0.060, 1.02),
                          (lx - 0.128, yy + side * 0.045, 1.02)], 0.018, 8)
        leaf.tube(path, 0.0085, seg=16, mat="steel")
    # barra de pánico por dentro
    for x in (0.08, W - 0.12):
        cl.rbox(leaf, (x - 0.03, T, 0.96), (x + 0.03, T + 0.07, 1.06), "steel", r=0.008)
    cl.rbox(leaf, (0.10, T + 0.045, 0.985), (W - 0.14, T + 0.085, 1.035), "steel", r=0.012)
    cl.rbox(leaf, (0.10, T, H - 0.15), (0.40, T + 0.055, H - 0.085), "aluminium", r=0.012)        # cierrapuertas
    det.join(leaf, M)
    # teclado de acceso junto al marco
    kp = cl.MB()
    cl.rbox(kp, (-0.045, -0.025, -0.075), (0.045, 0.0, 0.075), "steel", r=0.006)
    for i in range(3):
        for j in range(4):
            kp.box((-0.028 + i * 0.028 - 0.009, -0.029, -0.045 + j * 0.022 - 0.008), (-0.028 + i * 0.028 + 0.009, -0.025, -0.045 + j * 0.022 + 0.008),
                   "rubber", bevel=0.002)
    kp.box((-0.03, -0.0265, 0.045), (0.03, -0.0255, 0.065), "glass", bevel=0.0)
    det.join(kp, _T(x1 + 0.22, y0, zf + 1.25))
    # marquesina de lámina con ménsulas
    cz = zf + PDOOR_H + 0.35
    can = cl.MB()
    cl.rbox(can, (-0.80, -1.05, -0.08), (0.80, 0.0, 0.0), "paint_tan", r=0.008)
    for k in range(9):
        xk = -0.78 + k * 0.195
        can.box((xk - 0.006, -1.04, 0.0), (xk + 0.006, -0.01, 0.022), "paint_tan", bevel=0.002)
    for sx in (-0.68, 0.68):                                 # tornapuntas de PTR 40 × 40 con placas atornilladas al muro
        cl.rtube(can, (sx, -0.03, -0.52), (sx, -0.86, -0.085), 0.04, 0.04, "paint_tan", up=(1, 0, 0), r=0.004)
        cl.rbox(can, (sx - 0.05, -0.012, -0.60), (sx + 0.05, 0.0, -0.44), "paint_tan", r=0.003)
        for zz in (-0.58, -0.46):
            ce.hexnut(can, _T(sx, -0.012, zz) @ _Rx(90), d=0.012, mat="steel")
    can.transform(_Rx(-3.0))
    det.join(can, _T(PDOOR_X, y0, cz))
    return M


def wall_pack(det, x, y0, z, sg=-1):
    wp = cl.MB()
    cl.zloft(wp, [(-0.100, 0.280, 0.150, -0.077), (-0.094, 0.286, 0.156, -0.078), (-0.070, 0.286, 0.156, -0.078),
                  (0.020, 0.262, 0.120, -0.060), (0.058, 0.250, 0.080, -0.040), (0.066, 0.244, 0.072, -0.036)],
             seg=32, mat="paint_tan", ex=5.0)
    cl.rbox(wp, (-0.150, -0.012, -0.110), (0.150, -0.001, 0.090), "paint_tan", r=0.004)
    for k in range(9):
        xk = -0.104 + k * 0.026
        wp.box((xk - 0.0018, -0.068, 0.060), (xk + 0.0018, -0.012, 0.084), "paint_tan", bevel=0.0007)
    cl.rbox(wp, (-0.118, -0.140, -0.108), (0.118, -0.016, -0.098), "plastic", r=0.004)
    det.join(wp, _T(x, y0, z) @ (Matrix.Identity(4) if sg < 0 else _Rz(180)))
    LIGHTS.append([round(x, 3), round(y0 + sg * 0.12, 3), round(z - 0.08, 3)])


def cctv(det, x, y0, z, rot=0.0):
    """Cámara bala exterior (IP67, ~Ø 85 × 230 mm): caja de conexiones redonda en el muro con 3 tornillos, brazo de aluminio
    con rótula, carcasa con visera curva de lámina, cristal frontal con anillo de LED infrarrojos y lente, cable con gaza de
    goteo que entra a la caja."""
    c = cl.MB()
    ce.lathe(c, [(0.0, 0.0), (0.058, 0.0), (0.058, 0.010), (0.054, 0.034), (0.046, 0.042), (0.0, 0.043)], seg=48, mat="plastic",
             M=_Rx(90))                                                                   # caja de conexiones
    for k in range(3):
        a_ = 2 * math.pi * k / 3 + 0.5
        ce.screw(c, _T(0.040 * math.cos(a_), -0.0425, 0.040 * math.sin(a_)) @ _Rx(90), d=0.008, seg=24)
    arm = cl.fillet([(0.0, -0.043, 0.0), (0.0, -0.10, 0.0), (0.0, -0.14, -0.02)], 0.03, 8)
    c.tube(arm, 0.016, seg=24, mat="plastic")
    ce.lathe(c, [(0.0, -0.022), (0.014, -0.019), (0.022, 0.0), (0.014, 0.019), (0.0, 0.022)], seg=32, mat="plastic",
             M=_T(0, -0.15, -0.025))                                                      # rótula
    Mh = _T(0, -0.15, -0.025) @ _Rx(100) @ _T(0, 0.052, -0.07)                          # carcasa sobre la rótula, hacia afuera y abajo
    ce.lathe(c, [(0.0, 0.0), (0.030, 0.0), (0.040, 0.012), (0.042, 0.03), (0.042, 0.205), (0.039, 0.215), (0.0, 0.215)],
             seg=48, mat="plastic", M=Mh)
    ce.lathe(c, [(0.0, 0.2155), (0.035, 0.2155), (0.035, 0.218), (0.0, 0.218)], seg=48, mat="glass", M=Mh)
    ce.lathe(c, [(0.0, 0.212), (0.012, 0.212), (0.012, 0.217), (0.0, 0.217)], seg=32, mat="cable", M=Mh)   # lente
    for k in range(10):                                                                   # LED infrarrojos
        a_ = 2 * math.pi * k / 10
        c.cyl(tuple(Mh @ Vector((0.024 * math.cos(a_), 0.024 * math.sin(a_), 0.211))),
              tuple(Mh @ Vector((0.024 * math.cos(a_), 0.024 * math.sin(a_), 0.2155))), 0.0032, seg=24, mat="cable")
    # visera: lámina curva de 1 mm sobre la carcasa (arco de 150°), un poco más larga que el cuerpo
    ring = []
    for i in range(13):
        t = math.radians(-75 + 150 * i / 12)
        ring.append((0.047 * math.sin(t), 0.047 * math.cos(t)))
    prof = [(px, py) for (px, py) in ring] + [(px * 1.022, py * 1.022) for (px, py) in reversed(ring)]
    Ms = Mh                                                # +y local = arriba: la visera queda encima
    rings = []
    for zz in (0.02, 0.24):
        rings.append([c.bm.verts.new(Ms @ Vector((px, py, zz))) for (px, py) in prof])
    n = len(prof)
    for j in range(n):
        jj = (j + 1) % n
        c.face([rings[0][j], rings[0][jj], rings[1][jj], rings[1][j]], "plastic")
    c.face(list(reversed(rings[0])), "plastic")
    c.face(rings[1], "plastic")
    # cable con gaza de goteo que entra a la caja por abajo
    cab = [tuple(Mh @ Vector((0.0, -0.03, 0.04))), (0.0, -0.13, -0.09), (0.0, -0.07, -0.13), (0.0, -0.03, -0.08), (0.0, -0.02, -0.05)]
    c.tube(cl.fillet(cab, 0.025, 6), 0.0035, seg=14, mat="cable")
    det.join(c, _T(x, y0, z) @ _Rz(rot))


def _lp_clip(det, p, axis, nrm, r=0.0055):
    """Grapa de cobre para el conductor de pararrayos (NFPA 780: sujeción a no más de 0,9 m): base de 2 mm atornillada con
    dos pijas y abrazadera en arco sobre el cable. p: punto de la cara (lámina o techo) bajo el cable; axis: dirección del
    cable; nrm: normal de la cara (hacia afuera)."""
    X = Vector(axis).normalized()
    Z = Vector(nrm).normalized()
    Yv = Z.cross(X).normalized()
    M = Matrix((X, Yv, Z)).transposed().to_4x4()
    M.translation = Vector(p)
    wb = r + 0.0205
    cl.rbox(det, (-0.009, -wb, 0.0), (0.009, wb, 0.002), "copper", r=0.0008, m=M)
    arc = [tuple(M @ Vector((0.0, (r + 0.003) * math.cos(t), 0.002 + r + (r + 0.0012) * math.sin(t))))
           for t in np.linspace(0.0, math.pi, 13)]
    det.tube(arc, 0.0012, seg=12, mat="copper")
    for e in (-1, 1):
        ce.lathe(det, [(0.0, 0.0), (0.0045, 0.0), (0.0042, 0.0012), (0.003, 0.002), (0.0, 0.0022)], seg=24, mat="steel",
                 M=M @ _T(0, e * (r + 0.0135), 0.002))


def lightning(det):
    """Protección contra rayos (almacén de explosivos): puntas de cobre de 0,6 m sobre el caballete con bases atornilladas,
    conductor de cobre trenzado sobre el caballete; en cada extremo baja por la charola junto al remate de hastial, dobla
    sobre el remate y baja PEGADO a la lámina del hastial con grapas de cobre a cada 0,9 m (NFPA 780 §4.10), con tubo
    protector de PVC en los últimos 1,8 m y entra al registro de prueba de la varilla de tierra al pie del muro."""
    ym = (WY0 + WY1) / 2
    zr = roof_z(ym) + 0.10
    xs = np.linspace(WX0 + 0.3, WX1 - 0.3, 6)
    for x in xs:
        det.cyl((x, ym, zr), (x, ym, zr + 0.03), 0.04, seg=24, mat="copper")
        det.cyl((x, ym, zr + 0.03), (x, ym, zr + 0.60), 0.008, seg=24, mat="copper")
        ce.lathe(det, [(0.0, 0.0), (0.008, 0.0), (0.0, 0.03)], seg=24, mat="copper", M=_T(x, ym, zr + 0.60))
    det.tube([(xs[0], ym, zr + 0.05), (xs[-1], ym, zr + 0.05)], 0.0055, seg=14, mat="copper")
    rc = 0.0055
    for (xw, sx, yd, sy) in ((WX0, -1, WY0 + 0.60, -1), (WX1, 1, WY1 - 0.60, 1)):
        xf = xw + sx * (RIB_T + 0.0008)                    # crestas de la lámina del hastial
        xc = xf + sx * (0.002 + rc)                        # eje del cable sobre las grapas
        xin = xw - sx * 0.20                               # sobre la charola, 0,35 m dentro de la orilla del techo
        xo = xw + sx * 0.335                               # por fuera del remate de hastial
        zt = roof_z(yd)
        pts = [(xs[0] if sx < 0 else xs[-1], ym, zr + 0.05), (xin, ym + sy * 0.4, roof_z(ym + sy * 0.4) + 0.0032 + rc),
               (xin, yd - sy * 0.35, roof_z(yd - sy * 0.35) + 0.0032 + rc), (xw + sx * 0.10, yd, zt + 0.07),
               (xo, yd, zt + 0.02), (xo, yd, zt - 0.20), (xc, yd, zt - 0.40), (xc, yd, 0.32), (xc + sx * 0.18, yd, 0.08),
               (xc + sx * 0.55, yd, 0.06)]
        det.tube(cl.fillet(pts, 0.06, 8), rc, seg=14, mat="copper")
        # grapas sobre la charola (cada 0,9 m) y sobre la lámina del hastial
        ya, yb = ym + sy * 0.4, yd - sy * 0.35
        n = max(1, int(abs(yb - ya) / 0.9))
        for k in range(n + 1):
            y = ya + (yb - ya) * k / n
            _lp_clip(det, (xin, y, roof_z(y) + 0.0012), (0, 1, 0), (0, -sy * SLOPE, 1))
        for z in np.arange(2.3, zt - 0.5, 0.9):
            _lp_clip(det, (xf, yd, z), (0, 0, 1), (sx, 0, 0))
        # tubo protector de PVC gris en el tramo bajo (1,8 m), con sus abrazaderas
        rp = 0.0125
        xp = xf + sx * (0.002 + rp)
        det.cyl((xp, yd, 0.30), (xp, yd, 1.95), rp, seg=24, mat="plastic")
        ce.lathe(det, [(0.0, 0.0), (rp + 0.001, 0.0), (rp + 0.001, 0.012), (0.0, 0.012)], seg=24, mat="plastic",
                 M=_T(xp, yd, 1.95))
        for z in (0.55, 1.15, 1.75):
            _lp_clip(det, (xf, yd, z), (0, 0, 1), (sx, 0, 0), r=rp)
        # registro de prueba de la varilla de tierra (caja redonda de polímero al ras de la grava, tapa con dos tornillos)
        xg = xc + sx * 0.62
        ce.lathe(det, [(0.0, -0.10), (0.125, -0.10), (0.13, 0.04), (0.145, 0.05), (0.145, 0.075), (0.0, 0.075)], seg=40,
                 mat="plastic", M=_T(xg, yd, 0.0))
        for e in (-1, 1):
            ce.lathe(det, [(0.0, 0.0), (0.008, 0.0), (0.007, 0.003), (0.0, 0.004)], seg=24, mat="steel",
                     M=_T(xg, yd + e * 0.09, 0.075))
        text_font(det, "GROUND", 0.025, 0.0006, "plastic", M=_T(xg, yd, 0.0752), font="sign", res=3)


def exterior_services(det, r):
    """Medidor y desconectador con tubo conduit, gabinete de extintor rojo, letreros esténcil en el muro de concreto y en
    lámina, arbotantes sobre cada puerta, cámaras en esquinas, un par de impactos de bala (pintura saltada) en la lámina."""
    y0 = WY0 - RIB_T
    for (cx, w) in DOORS:                                  # cortinas montadas por dentro: nada tapa el arbotante sobre el vano
        wall_pack(det, cx, y0, FFL + DOOR_H + 0.55)
    wall_pack(det, PDOOR_X - 1.05, y0, FFL + PDOOR_H + 0.20)   # junto a la puerta, fuera de la sombra de la marquesina
    wall_pack(det, WX1 - 4.0, y0, 5.6)
    cctv(det, WX0 + 1.0, y0, 6.4, rot=-25)                # a 0,75 m de la bajada pluvial de la esquina
    cctv(det, WX1 - 1.0, y0, 6.4, rot=25)
    # esténciles pintados sobre el muro de concreto (letras de 0,14 m, 1 mm de relieve de pintura)
    M = _T(0, y0 - 0.0005, 0) @ _Rx(90)
    for (txt, x, z, s) in (("AUTHORIZED PERSONNEL ONLY", 2.4, 1.85, 0.16), ("NO SMOKING", 6.6, 1.85, 0.16),
                           ("EXPLOSIVES", 2.6, 1.45, 0.20), ("NO OPEN FLAMES", 6.8, 1.45, 0.16)):
        text_font(det, txt, s, 0.0008, "paint_od", M=M @ _T(x, z, 0), font="stencil", res=4)
    # gabinete de extintor rojo junto a la puerta
    cab = cl.MB()
    cl.rbox(cab, (-0.22, -0.20, 0.0), (0.22, 0.0, 0.70), "sign_red", r=0.01)
    cab.box((-0.20, -0.205, 0.02), (0.20, -0.195, 0.68), "sign_red", bevel=0.004)
    cab.box((-0.14, -0.209, 0.10), (0.14, -0.204, 0.60), "glass", bevel=0.002)
    text_font(cab, "FIRE", 0.05, 0.0008, "sign_white", M=_T(0, -0.209, 0.63) @ _Rx(90), font="sign", bold=True, res=4)
    det.join(cab, _T(PDOOR_X + 1.1, y0 - 0.0, FFL + 1.0) @ _Rx(0))
    # medidor y desconectador con conduit
    det.join(meter_disconnect(), _T(WX1 - 2.0, y0, 0.0))
    # impactos de bala con la pintura saltada (dos en la lámina, uno en el muro)
    for (x, z) in ((-11.9, 4.10), (-11.6, 3.72), (-2.1, 2.05)):
        dmg = cl.MB()
        ce.lathe(dmg, [(0.0, -0.004), (0.006, -0.003), (0.010, 0.0), (0.024, 0.0005), (0.032, 0.0)], seg=24, mat="steel",
                 M=_T(0, 0, 0) @ _Rx(90))
        dmg.cyl((0, 0.001, 0), (0, -0.006, 0), 0.005, seg=24, mat="cable")
        det.join(dmg, _T(x, y0 - 0.0012 - (0.0 if z > KNEE else 0.0), z))



def _encl(mb, x0, x1, z0, z1, d, mat="galvanized", r=0.012, lip=0.004):
    """Gabinete NEMA 3R de lámina: caja con cantos redondeados (r) y tapa con ceja que la traslapa 4 mm; frente en -Y, muro en y=0."""
    cl.rbox(mb, (x0, -d, z0), (x1, 0.0, z1), mat, r=r)
    cl.rbox(mb, (x0 - lip, -d - 0.006, z0 - lip), (x1 + lip, -d + 0.012, z1 + lip), mat, r=r * 0.8)


def meter_disconnect():
    """Base de medidor sin anillo (200 A, 11 x 15 1/2 x 4 5/8") con medidor de domo de policarbonato, anillo de sello con
    precinto, desconectador de navajas NEMA 3R (lateral con palanca y portacandado, tapa con bisagra) y conduit rígido de
    1 1/4": niple medidor-desconectador, codo LB con tapa atornillada, abrazaderas de una oreja y bajada al registro con su
    conector a la varilla de tierra. Origen: pie del muro bajo el medidor, cara del muro en y = 0, frente hacia -Y."""
    mb = cl.MB()
    zb = 1.40                                              # fondo de la base del medidor
    W, H, D = 0.279, 0.394, 0.117
    _encl(mb, -W / 2, W / 2, zb, zb + H, D)
    zc = zb + H * 0.56
    # medidor: collar, anillo de sello y domo
    Mm = _T(0, -D - 0.006, zc) @ _Rx(90)
    ce.lathe(mb, [(0.0, 0.0), (0.104, 0.0), (0.104, 0.004), (0.112, 0.006), (0.112, 0.016), (0.104, 0.019), (0.0, 0.019)],
             seg=48, mat="galvanized", M=Mm)                                          # brida de la tapa
    ce.lathe(mb, [(0.0, 0.019), (0.090, 0.019), (0.090, 0.040), (0.0, 0.040)], seg=48, mat="plastic", M=Mm)    # base del medidor
    ce.lathe(mb, [(0.0935, 0.012), (0.0985, 0.014), (0.0985, 0.045), (0.0935, 0.047)], seg=48, mat="steel", M=Mm, caps=False)
    ce.lathe(mb, [(0.0, 0.0405), (0.084, 0.0405), (0.084, 0.13), (0.078, 0.148), (0.062, 0.160), (0.0, 0.164)], seg=48,
             mat="glass", M=Mm)                                                       # domo
    ce.lathe(mb, [(0.0, 0.07), (0.07, 0.07), (0.07, 0.074), (0.0, 0.074)], seg=48, mat="sign_white", M=Mm)    # carátula
    mb.box((-0.030, 0.071, -0.012), (0.030, 0.0745, 0.010), "cable", bevel=0.001, m=Mm @ _Rx(-90) @ _T(0, -0.0, 0.0))
    # precinto del anillo: alambre con sello de plástico
    sp = [(0.098, -D - 0.035, zc - 0.012), (0.115, -D - 0.04, zc - 0.03), (0.108, -D - 0.042, zc - 0.07)]
    mb.tube(cl.fillet(sp, 0.01, 4), 0.0006, seg=12, mat="steel")
    cl.rbox(mb, (0.100, -D - 0.050, zc - 0.090), (0.116, -D - 0.040, zc - 0.068), "sign_red", r=0.002)
    # tornillos de la tapa
    for (xx, zz) in ((-W / 2 + 0.02, zb + 0.02), (W / 2 - 0.02, zb + 0.02)):
        ce.screw(mb, _T(xx, -D - 0.0065, zz) @ _Rx(90), d=0.008, seg=24)
    # desconectador a la derecha
    x0, x1, zd0, zd1, Dd = 0.24, 0.53, 1.45, 1.86, 0.135
    _encl(mb, x0, x1, zd0, zd1, Dd, r=0.010)
    for zz in (zd0 + 0.06, zd1 - 0.06):                    # bisagras de la tapa (lado izquierdo)
        ce.lathe(mb, [(0.0, 0.0), (0.0055, 0.0), (0.0055, 0.05), (0.0, 0.05)], seg=24, mat="galvanized",
                 M=_T(x0 - 0.004, -Dd - 0.004, zz - 0.025))
    # palanca lateral (lado derecho) con portacandado
    Mh = _T(x1 + 0.004, -Dd * 0.55, zd0 + 0.25) @ _Ry(90)
    ce.lathe(mb, [(0.0, 0.0), (0.028, 0.0), (0.028, 0.008), (0.022, 0.014), (0.0, 0.016)], seg=32, mat="steel", M=Mh)
    lever = [(x1 + 0.016, -Dd * 0.55, zd0 + 0.25), (x1 + 0.03, -Dd * 0.55 - 0.012, zd0 + 0.30), (x1 + 0.03, -Dd * 0.55 - 0.02, zd0 + 0.37)]
    cl.rtube(mb, lever[0], lever[1], 0.007, 0.007, "steel", up=(1, 0, 0), r=0.002)
    cl.rtube(mb, lever[1], lever[2], 0.008, 0.008, "sign_red", up=(1, 0, 0), r=0.003)
    cl.rbox(mb, (x1 + 0.004, -Dd * 0.55 - 0.003, zd0 + 0.14), (x1 + 0.034, -Dd * 0.55 + 0.003, zd0 + 0.20), "steel", r=0.0015)
    ce.lathe(mb, [(0.0035, -0.004), (0.0035, 0.004)], seg=24, mat="cable", M=_T(x1 + 0.026, -Dd * 0.55, zd0 + 0.17) @ _Rx(90), caps=False)
    text_font(mb, "MAIN DISCONNECT", 0.017, 0.0006, "sign_white", M=_T((x0 + x1) / 2, -Dd - 0.0065, zd1 - 0.05) @ _Rx(90),
              font="sign", bold=True, res=3)
    cl.rbox(mb, ((x0 + x1) / 2 - 0.07, -Dd - 0.0066, zd1 - 0.064), ((x0 + x1) / 2 + 0.07, -Dd - 0.0062, zd1 - 0.026), "sign_red", r=0.003)
    # conduit 1 1/4" (OD 42 mm): niple base -> desconectador por un costado, y bajada del desconectador al registro
    R = 0.021
    yc = -0.06
    mb.tube([(W / 2 - 0.003, yc, zb + 0.10), (x0 + 0.003, yc, zb + 0.10)], R, seg=24, mat="galvanized")
    for xx in (W / 2 + 0.004, x0 - 0.004):                 # contratuercas
        ce.lathe(mb, [(R, -0.004), (R + 0.007, -0.004), (R + 0.007, 0.004), (R, 0.004)], seg=24, mat="galvanized",
                 M=_T(xx, yc, zb + 0.10) @ _Ry(90))
    xd = (x0 + x1) / 2
    zl = 0.42
    mb.tube([(xd, yc, zd0 - 0.002), (xd, yc, zl + 0.08)], R, seg=24, mat="galvanized")
    # codo LB: cuerpo fundido con tapa atornillada, sale hacia el muro y baja dentro del registro
    cl.rbox(mb, (xd - 0.032, yc - 0.03, zl - 0.06), (xd + 0.032, yc + 0.026, zl + 0.08), "galvanized", r=0.012)
    cl.rbox(mb, (xd - 0.028, yc - 0.034, zl - 0.052), (xd + 0.028, yc - 0.028, zl + 0.072), "galvanized", r=0.006)
    for zz in (zl - 0.04, zl + 0.06):
        ce.screw(mb, _T(xd, yc - 0.034, zz) @ _Rx(90), d=0.007, seg=24)
    mb.tube([(xd, yc + 0.02, zl - 0.02), (xd, -0.005, zl - 0.02)], R * 0.98, seg=24, mat="galvanized")
    # abrazaderas de una oreja sobre la bajada
    for zz in (0.95, 1.30):
        path = cl.fillet([(xd - 0.03, -0.004, zz), (xd - R - 0.0015, -0.004, zz), (xd - R - 0.0015, yc - 0.004, zz),
                          (xd, yc - R - 0.0015, zz), (xd + R + 0.0015, yc - 0.004, zz), (xd + R + 0.0015, -0.012, zz)], 0.008, 4)
        mb.sweep([(-0.0008, -0.009), (0.0008, -0.009), (0.0008, 0.009), (-0.0008, 0.009)], path, mat="galvanized", normal=(0, 0, 1))
        ce.hexnut(mb, _T(xd - 0.022, -0.0048, zz) @ _Rx(90), d=0.007, mat="galvanized")
    return mb

# ------------------------------------------------------------------------------------------------------------ recinto
Z_GRAVEL = 0.06
CURB_W, CURB_TOP = 0.30, 0.18
FENCE_INSET = 0.17                # la malla del frente remata contra el alma de los muros T de los costados


def _rect_in(x, y, rects, pad=0.0):
    return any(a + pad <= x <= b - pad and c + pad <= y <= d - pad for (a, b, c, d) in rects)


def _rock(seed):
    """Piedra de grava triturada (~1 de diámetro, se escala al colocarla): icosaedro subdividido con caras de fractura planas
    (se recorta con 5 planos al azar) y ruido de baja frecuencia; base algo aplanada. ~150 triángulos."""
    import bmesh as _bm
    rr = rng(seed)
    mb = cl.MB()
    tmp = _bm.new()
    _bm.ops.create_icosphere(tmp, subdivisions=2, radius=0.5)
    cuts = [Vector((rr.normal(), rr.normal(), rr.normal())).normalized() for _ in range(5)]
    offs = [float(rr.uniform(0.30, 0.42)) for _ in cuts]
    for v in tmp.verts:
        p = v.co.copy()
        p *= 1.0 + 0.12 * float(np.sin(p.x * 7.3 + seed % 7) * np.cos(p.y * 5.1 + seed % 5))
        for n_, o_ in zip(cuts, offs):                     # caras de fractura: se proyecta sobre el plano de corte
            dd = p.dot(n_) - o_
            if dd > 0:
                p -= n_ * dd
        p.z = max(p.z, -0.22) * (0.85 if p.z < 0 else 1.0)
        v.co = p
    vs = {v: mb.bm.verts.new(v.co) for v in tmp.verts}
    for f in tmp.faces:
        mb.face([vs[v] for v in f.verts], "gravel")
    tmp.free()
    return mb

def site_ground(det, r):
    """Patio: guarnición bajo la malla del frente (en tramos con junta), losa de maniobras de concreto frente al andén y del
    portón, descanso al pie de la rampa, cama de grava compactada ondulada (rejilla de 25 cm) con piedras sueltas junto a
    losas y muros."""
    h = CURB_W / 2
    x0, x1 = CX0, CX1

    def curb_run(a, b):
        n = max(1, int(round(abs(b - a) / 3.0)))
        for k in range(n):
            u0, u1 = a + (b - a) * k / n + 0.004, a + (b - a) * (k + 1) / n - 0.004
            cl.rbox(det, (u0, CY0 - h, -0.05), (u1, CY0 + h, CURB_TOP), "concrete", r=0.012)
    curb_run(x0 + FENCE_INSET - h, GATE[0] + h)
    curb_run(GATE[1] - h, x1 - FENCE_INSET + h)
    slabs = []

    def slab(a, b, c, d, top, panel=4.0):
        nx = max(1, int(round((b - a) / panel)))
        ny = max(1, int(round((d - c) / panel)))
        for i in range(nx):
            for j in range(ny):
                xa, xb = a + (b - a) * i / nx, a + (b - a) * (i + 1) / nx
                ya, yb = c + (d - c) * j / ny, c + (d - c) * (j + 1) / ny
                cl.rbox(det, (xa + 0.004, ya + 0.004, Z_GRAVEL - 0.15), (xb - 0.004, yb - 0.004, top), "concrete", r=0.012)
        slabs.append((a, b, c, d))
    ax0, ax1, ay0, ay1 = APRON
    slab(ax0, ax1, ay0, ay1, Z_GRAVEL + 0.04)
    slab(GATE[0] + h, GATE[1] - h, CY0 - 0.8, ay0, Z_GRAVEL + 0.04)
    slab(RAMP[1], RAMP[1] + 1.6, -2.6, 0.0, Z_GRAVEL + 0.04, panel=2.0)
    slabs.append((WX0 - 0.1, WX1 + 0.1, WY0 - 0.1, WY1 + 0.1))
    slabs.append((DOCK[0], DOCK[1], DOCK[2], 0.0))
    slabs.append((RAMP[0], RAMP[1], RAMP[2], 0.0))
    slab(STAIR_PAD[0], STAIR_PAD[1], STAIR_PAD[2], STAIR_PAD[3], Z_GRAVEL + 0.04, panel=2.0)   # descanso al pie de la escalera
    # grava
    g0x, g1x, g0y, g1y = CX0 + 0.02, CX1 - 0.02, CY0 + h - 0.01, CY1 - 0.02
    step = 0.25
    nx, ny = int(round((g1x - g0x) / step)), int(round((g1y - g0y) / step))
    xs, ys = np.linspace(g0x, g1x, nx + 1), np.linspace(g0y, g1y, ny + 1)
    from PIL import Image
    g = r.random((ny // 8 + 3, nx // 8 + 3))
    nz = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((nx + 1, ny + 1), Image.BICUBIC), np.float64) / 255.0
    bm = det.bm
    mi = det.mi("gravel")
    V = {}

    def vert(i, j):
        if (i, j) not in V:
            x, y = xs[i], ys[j]
            d = 9.0
            for (a, b, c, e) in slabs:
                d = min(d, math.hypot(max(a - x, 0, x - b), max(c - y, 0, y - e)))
            z = Z_GRAVEL + (nz[j, i] - 0.5) * 0.03 + 0.015 * max(0.0, 1 - d / 0.4)
            V[i, j] = bm.verts.new((x, y, z))
        return V[i, j]
    for i in range(nx):
        for j in range(ny):
            cs = [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i], ys[j + 1]), (xs[i + 1], ys[j + 1])]
            if all(_rect_in(x, y, slabs, pad=0.03) for (x, y) in cs):
                continue
            f = bm.faces.new([vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)])
            f.material_index = mi
    stones = [_rock(int(r.integers(1 << 30))) for _ in range(6)]   # piedra triturada: 6 formas angulosas distintas
    placed = tries = 0
    while placed < 2600 and tries < 60000:
        tries += 1
        x, y = r.uniform(g0x, g1x), r.uniform(g0y, g1y)
        if _rect_in(x, y, slabs, pad=-0.01):
            continue
        d = min(math.hypot(max(a - x, 0, x - b), max(c - y, 0, y - e)) for (a, b, c, e) in slabs)
        if d > 0.5 and r.random() > 0.16:
            continue
        sc = r.uniform(0.012, 0.034) * (1.25 if r.random() < 0.08 else 1.0)
        M = _T(x, y, Z_GRAVEL - sc * 0.2) @ _Rz(r.uniform(0, 360)) @ _Rx(r.uniform(-25, 25)) @ \
            Matrix.Diagonal((sc * r.uniform(0.8, 1.3), sc * r.uniform(0.7, 1.1), sc * r.uniform(0.6, 0.9), 1.0))
        det.join(stones[placed % len(stones)], M)
        placed += 1


def _mod(name):
    try:
        return __import__(f"kit.{name}", fromlist=[name])
    except ImportError:
        return None


_NEW_MODS = {"jerry_can": "fortif_equipo", "tactical_generator": "fortif_equipo", "drop_arm_barrier": "fortif_equipo",
             "floodlight_tripod": "fortif_equipo", "light_tower": "fortif_equipo",
             "ammo_can": "municion", "cardboard_ammo_box": "municion", "ammo_crate": "municion", "pallet_gma": "municion",
             "shell_pallet": "municion", "crate_pallet": "municion", "frame_tent": "tienda_lona",
             "plywood_floor": "tienda_mobiliario", "crate_counter": "tienda_mobiliario", "shelving": "tienda_mobiliario",
             "weapon_rack_slots": "tienda_mobiliario", "weapon_rack": "tienda_mobiliario", "pegboard_hooks": "tienda_mobiliario",
             "pegboard": "tienda_mobiliario", "folding_table": "tienda_mobiliario", "folding_chair": "tienda_mobiliario",
             "string_lights": "tienda_mobiliario", "hanging_sign": "tienda_mobiliario"}


def _fn(name, fallback):
    """Pieza de la segunda pasada AAA (módulos fortif_equipo, municion, tienda_lona, tienda_mobiliario) con respaldo al
    módulo original si el nuevo no la tiene."""
    m = _mod(_NEW_MODS[name])
    f = getattr(m, name, None) if m is not None else None
    return f if f is not None else getattr(fallback, name)


def front_fence(furn, r):   # (se le pasa Detalle: la malla va con el exterior; Mobiliario queda para el interior)
    """Malla ciclónica del frente (modo ligero de kit/telecom.py) sobre la guarnición, con portón vehicular doble de 6 m."""
    tel = _mod("telecom")
    if tel is None:
        return
    zg = Z_GRAVEL + 0.05
    gx = (GATE[0] + GATE[1]) / 2
    w = GATE[1] - GATE[0] - 2 * 0.0508
    furn.join(tel.fence_gate(w=w, h=2.4, open_deg=(0, 0), seed=int(r.integers(1e6)), fabric="lite", base="curb", lite_hq=True,
                             fence_lift=CURB_TOP - zg), _T(gx, CY0, zg))
    ft = _mod("fortif")
    for (o, L, ends) in (((CX0 + FENCE_INSET, CY0), GATE[0] - CX0 - FENCE_INSET, (True, None)),
                         ((GATE[1], CY0), CX1 - FENCE_INSET - GATE[1], (None, True))):
        furn.join(tel.fence_run(L, h=2.4, seed=int(r.integers(1e6)), end_posts=ends, fabric="lite", base="curb", lite_hq=True),
                  _T(o[0], o[1], CURB_TOP))
        if ft is not None:                                   # rollo de navajas sobre los brazos de la malla
            furn.join(ft.concertina_fence_top(L, d=0.6, seed=int(r.integers(1e6))), _T(o[0], o[1], CURB_TOP))
    _proxy_box((CX0 - 0.1, CY0 - 0.35, 0.0), (GATE[0] + 0.1, CY0 + 0.3, 2.9))
    _proxy_box((GATE[1] - 0.1, CY0 - 0.35, 0.0), (CX1 + 0.1, CY0 + 0.3, 2.9))


# ------------------------------------------------------------------------------------------------------------ MIL_2
TENT_L, TENT_W = 9.75, 6.1
FLOOR_TOP = 0.108


def cfg_mil2(bid="MIL_2_avanzada"):
    return dict(id=bid, seed=151, xs=[-7.0, 7.0], ys=[-8.5, 5.5], h=[0.0], band_top=2.0,
                graffiti_bounds=(-7.0, 7.0, -8.5, 5.5), graffiti_px_per_m=150.0, exterior_footprint=[],
                lookdev=dict(base_z=0.0, graffiti_mats=(), wear=0.12, band=None))


FLOOD_M = _T(5.6, -7.6, 0.0) @ _Rz(-128)          # reflector en trípode de MIL_2 (apunta al mostrador)


def plywood_sign():
    """Letrero de triplay de 1,2 × 0,6 m (18 mm, cantos lijados) con letras de esténcil blancas SUPPLY, leyenda y flecha hacia
    el mostrador, amarrado con cinchos negros a la malla del HESCO (pasan por encima de los cantos). Origen: centro de la cara
    de atrás al pie (z = 0); cara a -Y; la flecha apunta a -X."""
    mb = cl.MB()
    t = 0.018
    z0, z1 = 0.47, 1.07
    cl.rbox(mb, (-0.6, -t, z0), (0.6, 0.0, z1), "plywood", r=0.003)
    M = _T(0, -t - 0.0002, 0) @ _Rx(90)
    text_font(mb, "SUPPLY", 0.17, 0.0008, "sign_white", M=M @ _T(0.02, 0.83, 0), font="stencil", res=4)
    text_font(mb, "AMMO  -  GEAR  -  PARTS", 0.045, 0.0008, "sign_white", M=M @ _T(0.02, 0.70, 0), font="stencil2", res=3)
    arrow = [(0.22, 0.555), (-0.10, 0.555), (-0.10, 0.525), (-0.22, 0.575), (-0.10, 0.625), (-0.10, 0.595), (0.22, 0.595)]
    F = [mb.bm.verts.new((x, -t - 0.0010, z)) for (x, z) in arrow]
    B = [mb.bm.verts.new((x, -t + 0.0002, z)) for (x, z) in arrow]
    mb.face(F, "sign_white")
    mb.face(list(reversed(B)), "sign_white")
    for i in range(len(arrow)):
        j = (i + 1) % len(arrow)
        mb.face([F[i], F[j], B[j], B[i]], "sign_white")
    for xz in (-0.5, 0.5):                                 # cinchos por encima de los cantos, hasta la malla de atrás
        for zt, sz in ((z1, 1), (z0, -1)):
            P = [(xz, -t - 0.0025, zt - sz * 0.035), (xz, -t - 0.0025, zt + sz * 0.003), (xz, 0.025, zt + sz * 0.003),
                 (xz, 0.025, zt - sz * 0.035), (xz, -t - 0.0025, zt - sz * 0.036)]
            mb.tube(cl.fillet(P, 0.004, 3), 0.0021, seg=12, mat="polymer")
            cl.rbox(mb, (xz - 0.006, -t - 0.0105, zt - sz * 0.03 - 0.005), (xz + 0.006, -t - 0.0025, zt - sz * 0.03 + 0.005),
                    "polymer", r=0.0015)
    return mb


def _flood_plug():
    """Punta y dirección de la clavija del cable del reflector (misma cuenta que fortif_equipo.floodlight_tripod), en las
    coordenadas de MIL_2."""
    k = 72
    a = math.pi + 2 * math.pi * k / 24
    rr_ = 0.15 + 0.012 * math.sin(k * 0.7) + 0.01 * (k / 24)
    zz = 0.0045 + 0.009 + 0.003 * max(0.0, math.sin(a + k * 0.05))
    end = Vector((0.9 + rr_ * math.cos(a), 0.42 + rr_ * math.sin(a) * 0.92, zz))
    t1, t2 = end + Vector((0.06, -0.05, -0.008)), end + Vector((0.14, -0.06, -0.011))
    dd = (t2 - t1).normalized()
    tip = t2 + Vector((0, 0, 0.012))
    return FLOOD_M @ tip, (FLOOD_M.to_3x3() @ dd).normalized()


def generator_power(GX, GY):
    """Instalación del generador: cable de uso rudo (SOOW 10/3, Ø 17 mm) del tablero de cargas al reflector (conector hembra
    acoplado a la clavija de su rollo) y a la serie de focos (sube por el testero cerrado y entra por una manga de lona con
    cordón), tendidos juntos por el piso con su curvatura; protector de cable de dos canales (hule negro, tapa amarilla) en el
    paso del testero; varilla de tierra de cobre Ø 16 con conector de bellota y cable verde al borne GROUND."""
    mb = cl.MB()
    rc = 0.0085
    xd, yd = GX + 0.70, GY + 0.21                        # puerta del tablero de cargas (cara +X del generador)
    tip, dd = _flood_plug()
    F0 = tip + dd * 0.038
    F1 = tip + dd * 0.118
    out = Vector((dd.x, dd.y, 0)).normalized()
    # conector hembra acoplado a la clavija del reflector
    Mf = Matrix(_frame_x(tuple(F0), tuple(F1), up=(0, 0, 1)))
    ce.lathe(mb, [(0.0, 0.0), (0.021, 0.0), (0.023, 0.006), (0.023, 0.058), (0.019, 0.07), (0.011, 0.08), (0.0, 0.08)], seg=32,
             mat="rubber", M=Mf @ _Ry(90))
    for (yoff, zf_, route) in ((0.0, 0.17, "flood"), (0.045, 0.20, "lights")):
        P = [(xd + 0.005, yd + yoff, zf_), (xd + 0.10, yd + yoff, zf_ - 0.03), (xd + 0.24, yd + yoff - 0.03, rc),
             (5.85, GY - 0.10 + yoff, rc), (6.05 + yoff, 3.6, rc + 0.002)]
        if route == "flood":
            P += [(6.05, -1.40, rc), (6.05, -1.55, 0.03), (6.05, -2.45, 0.03), (6.05, -2.60, rc), (5.95, -5.5, rc),
                  tuple(F1 + out * 0.45 + Vector((0, 0, rc - F1.z))), tuple(F1 + out * 0.12), tuple(F1)]
        else:
            P += [(6.10, 1.20, rc), (5.75, 0.62, rc), (5.02, 0.66, rc), (4.97, 0.80, 0.25), (4.95, 1.18, 1.85), (4.98, 1.30, 2.06),
                  (5.03, 1.30, 2.10), (4.80, 1.30, 2.10), (4.70, 1.28, 2.16), (4.62, 0.90, 2.62), (4.52, 0.38, 2.90),
                  (4.32, 0.06, 2.94)]
        mb.tube(cl.fillet(P, 0.12, 8), rc, seg=16, mat="cable")
    # manga de lona en el testero (sale 0,17 m) con su cordón
    ce.lathe(mb, [(0.0, 0.0), (0.036, 0.0), (0.035, 0.09), (0.0245, 0.14), (0.026, 0.165), (0.0, 0.17)], seg=24, mat="canvas",
             M=_T(4.86, 1.30, 2.10) @ _Ry(90))                 # manga fruncida por el cordón alrededor del cable
    ring = [(5.0, 1.30 + 0.027 * math.cos(a), 2.10 + 0.027 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 17)]
    mb.tube(ring, 0.0025, seg=12, mat="canvas")
    mb.tube([(5.0, 1.30, 2.076), (5.004, 1.31, 1.99), (5.0, 1.325, 1.93)], 0.002, seg=12, mat="canvas")
    # conector del extremo de la serie de focos
    ce.lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.018, 0.01), (0.018, 0.06), (0.0, 0.06)], seg=24, mat="rubber",
             M=_T(4.32, 0.06, 2.94) @ _Ry(-90))
    # protector de cable de dos canales a lo largo del cable en el paso del testero (y -2,45 .. -1,55)
    prof = [(-0.25, 0.0), (0.25, 0.0), (0.25, 0.006), (0.13, 0.048), (-0.13, 0.048), (-0.25, 0.006)]
    for (ya, yb, mat_, pr) in ((-2.45, -1.55, "rubber", prof),
                               (-2.44, -1.56, "paint_yellow", [(-0.125, 0.048), (0.125, 0.048), (0.12, 0.054), (-0.12, 0.054)])):
        A_ = [mb.bm.verts.new((6.05 + u, ya, z)) for (u, z) in pr]
        B_ = [mb.bm.verts.new((6.05 + u, yb, z)) for (u, z) in pr]
        for i in range(len(pr)):
            j = (i + 1) % len(pr)
            mb.face([A_[i], A_[j], B_[j], B_[i]], mat_)
        mb.face(list(reversed(A_)), mat_)
        mb.face(B_, mat_)
    for k in range(9):                                   # estrías antiderrapantes de las rampas
        yk = -2.40 + k * 0.1
        for sgn in (-1, 1):
            mb.box((6.05 + sgn * 0.19 - 0.05, yk - 0.008, 0.026 - sgn * 0.0), (6.05 + sgn * 0.19 + 0.05, yk + 0.008, 0.030), "rubber",
                   bevel=0.002)
    # varilla de tierra con conector de bellota y cable verde al borne GROUND (cara +X, 0,25 m hacia -y)
    xr_, yr_ = GX + 1.05, GY - 0.45
    mb.cyl((xr_, yr_, -0.15), (xr_, yr_, 0.15), 0.008, seg=24, mat="copper")     # lo enterrado no se modela completo
    ce.lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.018, 0.012), (0.017, 0.03), (0.011, 0.045), (0.0, 0.048)], seg=24, mat="brass",
             M=_T(xr_, yr_, 0.09))
    ce.hexnut(mb, _T(xr_ + 0.017, yr_, 0.115) @ _Ry(90), d=0.012, mat="brass")
    G = [(GX + 0.74, GY - 0.25, 0.24), (GX + 0.82, GY - 0.27, 0.19), (GX + 0.95, GY - 0.37, 0.012), (xr_ - 0.03, yr_ + 0.01, 0.03),
         (xr_ - 0.004, yr_, 0.115)]
    mb.tube(cl.fillet(G, 0.05, 6), 0.0045, seg=12, mat="sign_green")
    return mb


def outpost(furn, det, r, standalone=True, per=None, cargo=None):
    """Puesto de avanzada: tienda de marco (frente largo enrollado al -y) sobre tarima de triplay, mostrador de cajas con la
    caja de dinero, armeros con fusiles, anaqueles de latas y cajas, tablero con fundas y chalecos, mesa con cargadores y
    cajas de cartuchos, serie de focos, letrero SUPPLY colgado del frente del mostrador, red de camuflaje al frente, HESCO en las esquinas
    del frente, costales al fondo y en los testeros, generador táctico con bidones y reflector en trípode."""
    cp, ft, ar = _mod("campaign"), _mod("fortif"), _mod("armory")
    if cp is None:
        return
    per = per if per is not None else furn                 # fortificación (HESCO, costales)
    cargo = cargo if cargo is not None else furn           # mercancía: armas, munición, cajas

    def put(piece, M, mb=None, solid=True):
        if solid:
            _proxy(piece, M)
        (mb or furn).join(piece, M)
    put(_fn("frame_tent", cp)(L=TENT_L, W=TENT_W, seed=int(r.integers(1e6)), open_front=True, rolled_sides=("front",), ridge_guy=2.0),
        Matrix(), mb=det, solid=False)    # viento de cumbrera del testero cerrado a 2 m: libra los muros T del frente de MIL_1
    for (a, b) in (((-TENT_L / 2 - 0.1, TENT_W / 2 - 0.05), (TENT_L / 2 + 0.1, TENT_W / 2 + 0.25)),
                   ((-TENT_L / 2 - 0.25, -TENT_W / 2), (-TENT_L / 2 + 0.05, TENT_W / 2)),
                   ((TENT_L / 2 - 0.05, -TENT_W / 2), (TENT_L / 2 + 0.25, TENT_W / 2))):
        _proxy_box((a[0], a[1], 0.0), (b[0], b[1], 2.2))
    put(_fn("plywood_floor", cp)(L=9.5, W=5.8, seed=int(r.integers(1e6))), Matrix(), solid=False)
    zf = FLOOR_TOP
    # mostrador y mesa de exhibición al frente
    put(_fn("crate_counter", cp)(L=2.4, seed=int(r.integers(1e6))), _T(-1.2, -2.35, zf))   # entre las patas de los arcos (x -2,41 y 0)
    put(_fn("folding_table", cp)(L=1.83, seed=int(r.integers(1e6))), _T(1.95, -2.30, zf))
    if ar is not None:
        tz = zf + getattr(_mod("tienda_mobiliario"), "TABLE_TOP", 0.737)
        for k in range(6):
            put(ar.magazine(seed=k, lite=True), _T(1.35 + k * 0.055, -2.45, tz) @ _Rz(90), mb=cargo, solid=False)
        for k in range(8):
            i, j = k % 4, k // 4
            put(_fn("cardboard_ammo_box", ar)(seed=k), _T(1.75 + i * 0.12, -2.25 + j * 0.08, tz) @ _Rz(r.uniform(-6, 6)), mb=cargo, solid=False)
        for k in range(2):
            put(_fn("ammo_can", ar)("small", seed=40 + k), _T(2.45, -2.42 + k * 0.17, tz), mb=cargo, solid=False)
        put(_fn("ammo_can", ar)("large", seed=42, open=True), _T(-0.4, -2.25, zf + 0.909), mb=cargo, solid=False)
    # anaqueles, armeros y tablero al fondo (+y)
    yb = TENT_W / 2 - 0.42
    for k, (x, stock) in enumerate(((-4.0, "cans"), (-2.7, "boxes"), (-1.4, "mixed"))):
        put(_fn("shelving", cp)(1.2, seed=60 + k, stock=stock), _T(x, yb + 0.12, zf) @ face_to("-y"))   # libre de la panza de la pared
    for k, x in enumerate((0.15, 1.45)):
        Mr = _T(x, yb, zf)
        put(_fn("weapon_rack", cp)(8, seed=70 + k), Mr)
        if ar is not None:
            for j, Ms in enumerate(_fn("weapon_rack_slots", cp)(8)):
                if (j + k) % 5 == 3:
                    continue                                    # un hueco: ya se vendió
                kind = ("assault", "carbine", "assault", "dmr")[(j + k) % 4]
                put(ar.rifle(seed=100 + 10 * k + j, kind=kind), Mr @ Ms, mb=cargo, solid=False)
    # tablero perforado sobre dos postes de 2×4 con fundas (y chalecos cuando existan)
    xp = 3.05
    for dx in (-0.62, 0.62):
        cl.rbox(furn, (xp + dx - 0.019, yb + 0.02, zf), (xp + dx + 0.019, yb + 0.109, zf + 1.95), "wood", r=0.003)
        cl.rbox(furn, (xp + dx - 0.20, yb - 0.10, zf), (xp + dx + 0.20, yb + 0.25, zf + 0.038), "wood", r=0.003)
    Mp = _T(xp, yb + 0.02, zf + 0.75)
    put(_fn("pegboard", cp)(1.2, 1.0, seed=80, posts=0.62), Mp, solid=False)
    hooks = _fn("pegboard_hooks", cp)(1.2, 1.0)
    for k, Mh in enumerate(hooks):
        P = (Mp @ Mh).translation
        if ar is not None and hasattr(ar, "vest") and k in (0, 1):
            put(ar.vest(seed=90 + k), _T(P.x, P.y, P.z), mb=cargo, solid=False)
        elif ar is not None:
            put(ar.holster(seed=95 + k), _T(P.x, P.y + 0.02, P.z - 0.215), mb=cargo, solid=False)
    # cajas y latas en el piso
    if ar is not None:
        # existencias en el piso contra los testeros (el pasillo entre mostrador y anaqueles queda libre; puertas despejadas)
        put(_fn("ammo_crate", ar)("wood", seed=110), _T(-4.2, -1.6, zf) @ _Rz(8), mb=cargo)
        put(_fn("ammo_crate", ar)("wood", seed=111), _T(-4.2, -1.6, zf + 0.30) @ _Rz(4), mb=cargo)
        put(_fn("ammo_crate", ar)("long", seed=112), _T(4.35, 1.55, zf) @ _Rz(90), mb=cargo)
        for k in range(5):
            put(_fn("ammo_can", ar)("large", seed=120 + k), _T(3.55 + (k % 3) * 0.32, -2.55 + (k // 3) * 0.17, zf), mb=cargo)
        put(ar.hard_case(seed=130, L=1.0), _T(4.35, -1.55, zf) @ _Rz(90), mb=cargo) if hasattr(ar, "hard_case") else None
    # luz: serie de focos bajo la cumbrera
    put(_fn("string_lights", cp)(points=((-4.2, 0.0, 2.95), (-1.4, 0.0, 3.12), (1.4, 0.0, 3.12), (4.2, 0.0, 2.95)), n=8, seed=5, hook_z=3.175 - 0.019), Matrix(),
        solid=False)
    for x in np.linspace(-3.8, 3.8, 8):
        LIGHTS.append([round(float(x), 3), 0.0, 2.85])
    # letrero SUPPLY
    # letrero colgado de la orilla del mostrador, al frente de las cajas: se lee desde el paso y no queda a la altura de la cabeza
    put(_fn("hanging_sign", cp)("SUPPLY", 0.9, seed=6, ink="sign_white"), _T(-1.2, -2.755, zf + 0.909), solid=False)
    if ft is None:
        return
    # HESCO en las esquinas del frente y costales al fondo y en los testeros
    for x0 in (-TENT_L / 2 - 1.3, TENT_L / 2 + 1.3 - 2 * 1.06):    # flanquean el acceso, delante de la red y de sus vientos
        put(ft.hesco_run(2, "MIL1", seed=int(r.integers(1e6))), _T(x0, -TENT_W / 2 - 7.35, 0.0), mb=per)
    put(ft.sandbag_wall(TENT_L - 0.4, rows=4, seed=int(r.integers(1e6))), _T(-TENT_L / 2 + 0.2, TENT_W / 2 + 0.55, 0.0), mb=per)
    for xs, sg in ((-TENT_L / 2 - 0.55, -1), (TENT_L / 2 + 0.55, 1)):
        put(ft.sandbag_wall(2.0, rows=3, seed=int(r.integers(1e6))), _T(xs, TENT_W / 2 - 0.2, 0.0) @ _Rz(-90), mb=per)
    # letrero alto de triplay amarrado a la cara de afuera del HESCO del sur: se lee desde el portón y apunta al mostrador
    det.join(plywood_sign(), _T(TENT_L / 2 + 1.3 - 1.06, -TENT_W / 2 - 7.35 - 0.588, 0.0))
    # generador táctico a 3 m de la pared de atrás (escape vertical hacia afuera), bidones aparte, varilla de tierra, cables al
    # reflector y a la serie de focos (manga de cable en el testero cerrado), protector de cable en el paso del testero
    GX, GY = 1.2, TENT_W / 2 + 3.0
    put(_fn("tactical_generator", ft)(seed=int(r.integers(1e6))), _T(GX, GY, 0.0))     # frente de servicio (-y) hacia la tienda
    for k in range(7):
        put(_fn("jerry_can", ft)(seed=k if k < 3 else 7 + k, color="tan" if k % 2 else "od"),
            _T(-0.55 + (k % 4) * 0.2, GY + (0.22 if k < 4 else -0.22), 0.0) @ _Rz(90))
    put(_fn("floodlight_tripod", ft)(seed=7), FLOOD_M)     # apunta al mostrador, libre de los vientos
    LIGHTS.append([5.6, -7.6, 1.98])
    det.join(generator_power(GX, GY))
    if hasattr(ft, "camo_net"):
        # red centrada en el mostrador: orilla de atrás a 0,45 m del alero, sin vientos hacia la tienda ni amarres al frente, y
        # sin postes a media orilla (solo esquinas, medios costados y los dos separadores, que flanquean el paso de clientes)
        put(ft.camo_net(w=8.0, l=4.5, seed=8, poles=True, back_ties=False, front_ties=False, mid_edge_poles=False),
            _T(-1.2, -TENT_W / 2 - 2.7, 0.0), mb=det, solid=False)


def build_mil2(bid="MIL_2_avanzada", collection_root=None, dress_on=True, **kw):
    cfg = cfg_mil2(bid)
    cid = cfg["id"]
    LIGHTS.clear()
    PROXIES.clear()
    root = collection_root or get_collection(cid)
    keys = ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage", "Furniture", "Fence", "Cargo")
    cols = {k: get_collection(f"{cid}_{k}", root) for k in keys}
    out = {k: [] for k in cols}
    det, furn, per, cargo = MB(), MB(), MB(), MB()
    r = rng(cfg["seed"])
    outpost(furn, det, r, per=per, cargo=cargo)
    for nm, mb in (("Details", det), ("Furniture", furn), ("Fence", per), ("Cargo", cargo)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = dict(interior_dress=dict(bulb_pos=list(LIGHTS)), proxies=list(PROXIES))
    out["cfg"] = cfg
    return out


def perimeter(det, towers, r):
    """Muros T de concreto (3,66 m) al poniente, al fondo y al oriente; torre de vigilancia en la esquina del frente poniente;
    torres de luz; punto de control vehicular afuera del portón (canal, serpentín, pluma y puesto de guardia); HESCO MIL7 tras
    la malla del frente, muros T entre la malla y la tienda de munición y un puesto de tirador de costales junto al portón."""
    ft = _mod("fortif")
    if ft is None:
        return
    seg = 1.52
    tw = [ft.t_wall(seed=k) for k in range(4)]
    # (origen del primer segmento, giro, paso, n): el frente de cada muro T (-y local) mira hacia afuera del recinto
    runs = [((CX0, CY1), -90, Vector((0, -seg, 0)), 27),             # poniente, de la esquina del fondo hacia el frente
            ((CX1, CY1), 180, Vector((-seg, 0, 0)), 30),             # fondo, de oriente a poniente
            ((CX1, CY1 - 27 * seg), 90, Vector((0, seg, 0)), 27)]    # oriente, del frente hacia el fondo
    for (o, rot, step, n) in runs:
        for k in range(n):
            P = Vector((o[0], o[1], 0.0)) + step * k
            det.join(tw[(k * 7 + n) % 4], _T(P.x, P.y, 0.0) @ _Rz(rot))
    for (a, b) in (((CX0 - 0.7, CY0), (CX0 + 0.7, CY1)), ((CX0, CY1 - 0.7), (CX1, CY1 + 0.7)), ((CX1 - 0.7, CY0), (CX1 + 0.7, CY1))):
        _proxy_box((a[0], a[1], 0.0), (b[0], b[1], 3.66))
    put = lambda piece, M, solid=True, mb=None: (_proxy(piece, M) if solid else None, (mb or det).join(piece, M))  # noqa: E731
    put(ft.guard_tower(seed=3), _T(-21.6, -15.4, 0.0), mb=towers)
    put(_fn("light_tower", ft)(seed=4), _T(18.5, 8.0, 0.0) @ _Rz(-90), mb=towers)    # patio oriente, reflectores hacia la nave
    put(_fn("light_tower", ft)(seed=5), _T(19.8, -16.5, 0.0) @ _Rz(-90), mb=towers)
    LIGHTS.extend([[18.5, 8.0, 9.0], [19.8, -16.5, 9.0]])
    ecp(det, put, ft)
    put(ft.hesco_run(3, "MIL7", seed=7), _T(-23.0, -18.6, 0.0))
    # puesto de tirador junto al portón (adentro): muro doble de sacos a la altura del pecho (FM 5-103); la cara cerrada mira
    # al frente (la malla y el acceso de afuera); la entrada, hacia el almacén
    put(ft.sandbag_ring(radius=1.25, rows=12, seed=8, opening_deg=60.0, thickness="double", lod_top=2),
        _T(-5.5, -17.7, Z_GRAVEL) @ _Rz(180), solid=True)
    # muro de muros T detrás de la malla del frente, entre la malla y el testero cerrado de la tienda de munición (MIL_2): la
    # malla ciclónica no detiene esquirlas ni deja de mostrar lo que hay detrás
    for k in range(9):
        put(ft.t_wall(seed=20 + k % 4), _T(TW_X0 + k * 1.52, TW_Y, 0.0))


TW_X0, TW_Y = 3.0, CY0 + 0.15 + 0.686 + 0.03     # muros T del frente (cara exterior hacia -y, junto a la guarnición)
ECP_X = (-15.5, -6.5)                           # ejes de los muros del canal del punto de control vehicular
ECP_ARM_Y = CY0 - 7.6                           # pluma: 7,45 m de zona de revisión hasta la guarnición del portón


def ecp(det, put, ft):
    """Punto de control vehicular afuera del portón (UFC 4-022-01, en chico): canal de barreras Jersey de 8,4 m entre caras
    (6 por lado, conectadas pin-and-loop) que nace en la malla, de modo que al portón solo se llega por el canal; dentro,
    serpentín de dos tramos de 4,9 m que salen alternados de cada muro y se traslapan 1,7 m (ningún carril recto: el vehículo
    tiene que hacer una S lenta con 3,3 m de paso), pluma de 7,6 m a 7,45 m de la guarnición (zona de revisión de un vehículo
    con su gente alrededor) y puesto de guardia de costales junto al gabinete de la pluma, del lado de adentro."""
    jb = [ft.jersey_barrier(3.0, seed=10 + k) for k in range(4)]
    js = [ft.jersey_barrier(2.44, seed=30 + k) for k in range(2)]
    yt = CY0 - CURB_W / 2 - 0.30                       # primera barrera: arranca junto a la guarnición
    pitch = 3.05
    for i, xw in enumerate(ECP_X):
        for k in range(6):
            put(jb[(k + 2 * i) % 4], _T(xw, yt - k * pitch, 0.0) @ _Rz(-90))
    xl, xr = ECP_X[0] + 0.305, ECP_X[1] - 0.305       # caras interiores del canal
    y1, y2 = ECP_ARM_Y - 3.0, ECP_ARM_Y - 8.4
    for k in range(2):                                 # tramo 1: sale del muro poniente (paso por el oriente)
        put(js[k], _T(xl + 0.10 + k * 2.49, y1, 0.0))
    for k in range(2):                                 # tramo 2: sale del muro oriente (paso por el poniente)
        put(js[1 - k], _T(xr - 0.10 - k * 2.49, y2, 0.0) @ _Rz(180))
    put(_fn("drop_arm_barrier", ft)(L=7.6, seed=6), _T(xl + 0.35, ECP_ARM_Y, 0.0))
    put(ft.sandbag_ring(radius=1.0, rows=12, seed=9, opening_deg=60.0, thickness="double", lod_top=2),
        _T(xl + 1.75, ECP_ARM_Y + 2.0, 0.0) @ _Rz(180), solid=True)


LOD_RACK = {}                     # se llena con lod=1 si kit.municion lo acepta (carga de racks ligera: ~2 M en vez de 12 M)
RACK_ROWS = [(16.75, 0), (11.79, 180), (9.92, 0)]        # (y del origen, giro): fila del fondo y doble fila al centro;
                                                          # pasillo del fondo de 3,78 m (montacargas de 5000 lb a 90° con tarima)
RACK_XS = (-15.20, -6.80)                                 # dos racks de 3 claros por fila


def warehouse_interior(furn, r, cargo=None):
    """Almacén: 3 filas de racks selectivos (fondo y doble fila central) con tarimas de cajas de munición flejadas, tarimas de
    proyectiles y cajas largas; jaula de seguridad con armero, fusiles, ametralladoras y morteros; montacargas estacionado
    en la zona de recibo con tarimas en espera; banco de trabajo, estaciones de extintor y luminarias de nave."""
    cp, ar = _mod("campaign"), _mod("armory")
    if cp is None:
        return
    zf = FFL
    import inspect
    mu = _mod("municion")
    LOD_RACK.clear()
    if mu is not None and "lod" in inspect.signature(mu.crate_pallet).parameters:
        LOD_RACK["lod"] = 1

    def put(piece, M, solid=True, mb=None):
        if solid:
            _proxy(piece, M)
        (mb if mb is not None else furn).join(piece, M)
    slots = cp.pallet_rack_slots(3, 3, 1.1, 2.7)
    for ri, (yr, rot) in enumerate(RACK_ROWS):
        for xi, xr in enumerate(RACK_XS):
            Mr = _T(xr, yr, zf) @ _Rz(rot)
            put(cp.pallet_rack(3, 3, 1.1, 2.7, seed=10 * ri + xi), Mr)
            if ar is None:
                continue
            for k, Ms in enumerate(slots):
                lev = (k // 2) % 3
                if r.random() < (0.12, 0.22, 0.35)[lev]:
                    continue                                    # huecos: lo que ya salió
                Mx = Mr @ Ms @ _Rz(180 * int(r.integers(2)))
                if lev == 0:
                    piece = _fn("shell_pallet", ar)(seed=int(r.integers(1e6)), **LOD_RACK) if r.random() < 0.3 else \
                        _fn("crate_pallet", ar)(6, seed=int(r.integers(1e6)), **LOD_RACK)
                elif lev == 1:
                    piece = _fn("crate_pallet", ar)(3, seed=int(r.integers(1e6)), **LOD_RACK)
                else:
                    piece = cl.MB()
                    _fn("pallet_gma", ar)(piece, **LOD_RACK)
                    for j in range(2):
                        piece.join(_fn("ammo_crate", ar)("long", seed=int(r.integers(1e6)), **LOD_RACK),
                                   _T(0, (j - 0.5) * 0.50, 0.135) @ _Rz(0))
                (cargo or furn).join(piece, Mx)
    # líneas amarillas de pasillo frente a cada cara de rack y la de la zona de recibo
    for y in (16.11, 12.42, 9.28, 6.20):
        furn.box((-19.4, y - 0.05, zf), (-2.6 if y > 6.3 else 9.4, y + 0.05, zf + 0.0015), "paint_yellow", bevel=0.0)
    # jaula de armas con su contenido
    cxg, cyg, cw, cd = 6.55, 14.75, 5.5, 4.5
    put(cp.security_cage(cw, cd, 2.6, seed=21), _T(cxg, cyg, zf), solid=False)
    for (a, b) in (((cxg - cw / 2, cyg - cd / 2), (cxg + cw / 2, cyg - cd / 2 + 0.08)), ((cxg - cw / 2, cyg + cd / 2 - 0.08), (cxg + cw / 2, cyg + cd / 2)),
                   ((cxg - cw / 2, cyg - cd / 2), (cxg - cw / 2 + 0.08, cyg + cd / 2)), ((cxg + cw / 2 - 0.08, cyg - cd / 2), (cxg + cw / 2, cyg + cd / 2))):
        _proxy_box((a[0], a[1], zf), (b[0], b[1], zf + 2.6))
    if ar is not None:
        Mw = _T(cxg - 1.4, cyg + cd / 2 - 0.45, zf)
        put(_fn("weapon_rack", cp)(8, seed=22), Mw)
        for j, Ms in enumerate(_fn("weapon_rack_slots", cp)(8)):
            put(ar.rifle(seed=200 + j, kind=("assault", "carbine", "dmr")[j % 3]), Mw @ Ms, solid=False)
        for k, x in enumerate((cxg + 0.4, cxg + 1.7)):
            if hasattr(ar, "machine_gun_tripod"):
                put(ar.machine_gun_tripod(seed=210 + k), _T(x, cyg + 1.2, zf) @ _Rz(-90))
        if hasattr(ar, "mortar"):
            put(ar.mortar(seed=220), _T(cxg + 1.6, cyg - 0.6, zf) @ _Rz(30))
        for k in range(3):
            put(_fn("ammo_crate", ar)("long", seed=230 + k), _T(cxg - 1.6, cyg - 0.9 + 0.0, zf + k * 0.27) @ _Rz(0))
        for k in range(4):
            put(_fn("ammo_can", ar)("large", seed=240 + k), _T(cxg + 0.2 + (k % 2) * 0.32, cyg - 1.4 + (k // 2) * 0.17, zf))
        if hasattr(ar, "hard_case"):
            put(ar.hard_case(seed=250, L=1.2), _T(cxg - 0.2, cyg + 0.2, zf) @ _Rz(90))
        if hasattr(ar, "launcher_tube"):                     # caja larga abierta con dos lanzadores desechables
            Mc = _T(cxg + 1.65, cyg - 1.55, zf)                # 0,2 m libre del panel oriente de la jaula
            put(_fn("ammo_crate", ar)("long", seed=260, open=True), Mc)
            for k in range(2):
                put(ar.launcher_tube(seed=261 + k), Mc @ _T(0.0, (k - 0.5) * 0.17, 0.07), solid=False)
    # zona de recibo: tarimas en espera y montacargas
    if ar is not None:
        for k, (x, y) in enumerate(((-17.2, 3.4), (-15.6, 3.4), (-10.2, 3.6), (-8.4, 2.9))):
            put(_fn("crate_pallet", ar)(6, seed=300 + k) if k != 2 else _fn("shell_pallet", ar)(seed=300 + k), _T(x, y, zf) @ _Rz(90 if k % 2 else 0),
                mb=cargo if cargo is not None else furn)    # versión completa (se ve a < 1 m) en la malla Carga
    put(cp.forklift(seed=31), _T(-3.4, 4.2, zf) @ _Rz(-70))
    # banco de trabajo y estaciones de extintor contra el muro del frente (por dentro)
    yi = WY0 - RIB_T + WT
    put(cp.workbench(seed=32), _T(5.6, yi + 0.40, zf) @ _Rz(180))
    for x in (-12.5, -1.0, 7.0):
        put(cp.extinguisher_station(seed=33), _T(x, yi, zf) @ _Rz(180), solid=False)
    # luminarias de nave colgadas de los largueros
    for x in (-16.0, -9.0, -2.0, 5.0):
        for y in (4.5, 9.0, 13.5):
            z = roof_z(y) - 0.22
            furn.join(cp.high_bay_light(), _T(x, y, z))
            LIGHTS.append([x, y, round(z - 0.25, 3)])


def build_mil1(bid="MIL_1_almacen", collection_root=None, dress_on=True, **kw):
    cfg = cfg_mil1(bid)
    cid = cfg["id"]
    LIGHTS.clear()
    PROXIES.clear()
    root = collection_root or get_collection(cid)
    keys = ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage", "Furniture", "Fence", "Cargo", "Wire")
    cols = {k: get_collection(f"{cid}_{k}", root) for k in keys}
    out = {k: [] for k in cols}
    shell, det, inter, rf, furn, per, cargo, wire = MB(), MB(), MB(), MB(), MB(), MB(), MB(), MB()
    r = rng(cfg["seed"])
    shell_walls(shell)
    roof(rf, det)
    steel_frame(inter)
    liner(inter)
    floor_slab(inter)
    sprinklers(inter)
    dock(det)
    dock_stair(det)
    for k, (cx, w) in enumerate(DOORS):
        door_frame(det, cx, w)
        rollup_door(det, cx, w, seed=k + 3, damaged=(k == 1))
    personnel_door(det)
    exterior_services(det, r)
    lightning(det)
    site_ground(det, r)
    if dress_on and kw.get("dress", True):
        front_fence(wire, r)
        perimeter(per, det, r)
        warehouse_interior(furn, r, cargo)
    for nm, mb in (("Shell", shell), ("Details", det), ("Interior", inter), ("Roof", rf), ("Furniture", furn), ("Fence", per),
                   ("Cargo", cargo), ("Wire", wire)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = dict(interior_dress=dict(bulb_pos=list(LIGHTS)), proxies=list(PROXIES))
    out["cfg"] = cfg
    return out

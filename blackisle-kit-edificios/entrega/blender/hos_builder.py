"""hos_builder.py — HOS_1_pueblo: hospital rural de pueblo costero mexicano, de una planta, en funcionamiento.

Planta (ejes de Blender, metros; fachada principal hacia -Y, pivote al centro del edificio principal a nivel de banqueta z = 0):
  edificio principal x -14..14 · y -10..10 · piso terminado +0,45 · plafón +3,15 · losa +3,45..3,65 · pretil +4,25
    frente  : sala de espera (x -13,8..-2) · recepción (-2..3) · urgencias (3..13,8), pórtico de 4 columnas con escalones y rampa
    pasillo : y -4..-1,8 de lado a lado (salida de emergencia al oeste)
    centro  : consultorios 1 y 2 · pasillo-galería · PATIO interior (x -3..4, y -1,8..4) · farmacia · rayos X
    pasillo : y 4..6 · fondo: encamados (x -13,8..-5, y 4..9,8) · enfermería · 2 baños · cocina · lavandería (puerta de servicio)
  cochera de ambulancias x 16,4..24,4 · y -9..2 (2 cortinas al frente), pasillo cubierto x 14..16,4 con rampa a urgencias
  barda perimetral de block en los costados y el fondo (portón de servicio atrás).
Cumple R-AAA (CLAUDE.md): mobiliario de kit/clinic.py y telas simuladas de kit/softgoods.py.
"""
import math

import bpy  # noqa: F401
import numpy as np
from mathutils import Matrix, Vector

import apt_common as ac
from kit import clinic as cl
from kit import openings as op
from kit import port
from kit import services as sv
from kit.common import MB, get_collection, rng, wall_with_openings

FFL = 0.45
WAIN = 1.0
CEIL = FFL + 2.70
SLAB_B = FFL + 3.00
SLAB_T = SLAB_B + 0.20
PARA = SLAB_T + 0.60
X0, X1, Y0, Y1 = -14.0, 14.0, -10.0, 10.0
TE, TI = 0.20, 0.12
GX0, GX1, GY0, GY1 = 16.4, 24.4, -9.0, 2.0
G_FL, G_SB, G_ST, G_PARA = 0.10, 3.60, 3.80, 4.20
PAVE = 0.10
CXW, CXE, CYS, CYN = -3.0, 4.0, -1.8, 4.0                 # ejes de los muros del patio
BACK_WALL_Y, SIDE_WALL_XW, SIDE_WALL_XE = 13.5, -17.0, 27.0
WIN_Z = (FFL + 1.15, FFL + 2.35)
HIGH_Z = (FFL + 2.0, FFL + 2.5)


def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def _Rz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def face_to(d):
    """Giro en Z para que el frente local (-Y) de una pieza mire hacia d ('-y', '+x', '+y', '-x')."""
    return _Rz({"-y": 0, "+x": 90, "+y": 180, "-x": -90}[d])


def cfg_hos(bid="HOS_1_pueblo"):
    fp = [(X0, X1, Y0, CYS - TE / 2), (X0, X1, CYN + TE / 2, Y1), (X0, CXW - TE / 2, CYS - TE / 2, CYN + TE / 2),
          (CXE + TE / 2, X1, CYS - TE / 2, CYN + TE / 2), (GX0, GX1, GY0, GY1)]
    return dict(id=bid, seed=83, xs=[SIDE_WALL_XW, SIDE_WALL_XE], ys=[-14.5, BACK_WALL_Y], h=[FFL], band_top=2.4,
                graffiti_bounds=(SIDE_WALL_XW - 0.5, SIDE_WALL_XE + 0.5, -15.0, BACK_WALL_Y + 0.5), graffiti_px_per_m=150.0,
                exterior_footprint=fp,
                lookdev=dict(base_z=0.0, graffiti_mats=("plaster", "concrete"), paint_tint=(0.95, 0.91, 0.80), wear=0.08,
                             band=(1.35, (0.03, 0.16, 0.075)), paint_sat=1.0))


# ------------------------------------------------------------------------------------------------------------ registros
GAPS = []          # (eje del muro 'x'|'y', coordenada del eje, a, b) huecos de piso a techo de puertas/pasos (para el lambrín)
DOORS = []         # (M, w, h, tipo, ángulo) puertas para colocar después
LIGHTS = []        # posiciones de luminarias (focos para el motor)
PROXIES = []       # cajas de colisión del mobiliario (el mobiliario va en Detalle; su colisión, simple, en la pieza Colision)


def _proxy(piece, M, pad=0.0):
    pts = [M @ v.co for v in piece.bm.verts]
    if not pts:
        return
    mn = [min(p[i] for p in pts) - pad for i in range(3)]
    mx = [max(p[i] for p in pts) + pad for i in range(3)]
    PROXIES.append([[round(c, 3) for c in mn], [round(c, 3) for c in mx]])


def ext_wall(shell, side, a0, a1, face, ops, z_top, z_split, t=TE, mat_in="paint_white", coping=True, u_trim=0.0):
    """Muro exterior de block aplanado: banda baja con vanos (cara interior pintada) y pretil arriba de z_split, con remate."""
    M = ac.panel_matrix(side, a0, a1, face, 0.0)
    L = a1 - a0
    wall_with_openings(shell, L, z_split, t, ops, mat_out="plaster", mat_in=mat_in, mat_reveal="plaster", m=M)
    wall_with_openings(shell, L, z_top - z_split, t, [], mat_out="plaster", mat_in="plaster", mat_reveal="plaster",
                       m=M @ _T(0, 0, z_split))
    if coping:
        shell.box((u_trim - (0.03 if u_trim == 0 else 0), -0.03, z_top), (L - u_trim + (0.03 if u_trim == 0 else 0), t + 0.03, z_top + 0.05),
                  "concrete", m=M)
    return M


def partition(inter, p0, p1, ops=(), H=SLAB_B - FFL, t=TI, mat="paint_white"):
    """Tabique de block aplanado de eje p0→p1 (paralelo a X o a Y), de piso terminado a losa. Devuelve (M, L)."""
    (xa, ya), (xb, yb) = p0, p1
    if abs(ya - yb) < 1e-6:
        x0_, x1_ = sorted((xa, xb))
        M = _T(x0_, ya - t / 2, FFL)
        L = x1_ - x0_
    else:
        y0_, y1_ = sorted((ya, yb))
        M = _T(xa + t / 2, y0_, FFL) @ _Rz(90)
        L = y1_ - y0_
    wall_with_openings(inter, L, H, t, list(ops), mat_out=mat, mat_in=mat, mat_reveal=mat, m=M)
    return M, L


def door_in(M, u0, w, h=2.1, kind="flush", ang=45.0, depth=TI, z0=0.0, axis=None, line=None, along0=None):
    """Registra una puerta (se coloca al final) y su hueco para el lambrín."""
    DOORS.append((M @ _T(u0, 0, z0), w, h, kind, ang, depth))
    if axis is not None:
        GAPS.append((axis, line, along0 + u0, along0 + u0 + w))


# ------------------------------------------------------------------------------------------------------------ estructura
def build_slabs(inter, roof):
    ring = (CXW - TE / 2, CXE + TE / 2, CYS - TE / 2, CYN + TE / 2)
    xi0, xi1, yi0, yi1 = X0 + TE, X1 - TE, Y0 + TE, Y1 - TE
    parts = [(xi0, xi1, yi0, ring[2]), (xi0, xi1, ring[3], yi1), (xi0, ring[0], ring[2], ring[3]), (ring[1], xi1, ring[2], ring[3])]
    for (a, b, c, d) in parts:
        inter.box((a, c, 0.0), (b, d, FFL), "terrazzo")
        roof.box((a, c, SLAB_B), (b, d, SLAB_T), "concrete")
        inter.box((a, c, CEIL), (b, d, CEIL + 0.015), "ceiling_tile")
    # patio: piso 10 cm abajo, firme de concreto escobillado con rejilla de desagüe
    px0, px1, py0, py1 = CXW + TE / 2, CXE - TE / 2, CYS + TE / 2, CYN - TE / 2
    inter.box((px0, py0, 0.0), (px1, py1, FFL - 0.10), "concrete")
    inter.box(((px0 + px1) / 2 - 0.2, py0 + 0.3, FFL - 0.10), ((px0 + px1) / 2 + 0.2, py0 + 0.5, FFL - 0.095), "steel")
    # cochera
    inter.box((GX0 + TE, GY0 + TE, 0.0), (GX1 - TE, GY1 - TE, G_FL), "concrete")
    roof.box((GX0 + TE, GY0 + TE, G_SB), (GX1 - TE, GY1 - TE, G_ST), "concrete")
    for (bx0, bx1) in ((GX0 + 0.4, GX0 + 3.8), (GX0 + 4.2, GX0 + 7.6)):     # umbral de los vanos de la cochera
        inter.box((bx0, GY0, 0.0), (bx1, GY0 + TE, G_FL), "concrete")


def main_walls(shell):
    def fr(x):
        return x - X0

    def bk(x):
        return X1 - x
    a0s, a1s = Y0 + TE, Y1 - TE

    def we(y):
        return a1s - y

    def ea(y):
        return y - a0s
    w = WIN_Z
    front = [(fr(a), fr(b), *w) for (a, b) in ((-13.2, -11.7), (-4.4, -2.9), (0.2, 1.4), (4.5, 6.0), (8.0, 9.5), (11.5, 13.0))]
    front += [(fr(-8.9), fr(-7.1), FFL, FFL + 2.4)]
    back = [(bk(b), bk(a), *w) for (a, b) in ((-12.8, -11.3), (-8.8, -7.3), (-3.6, -2.1), (5.6, 7.1), (9.6, 10.6))]
    back += [(bk(b), bk(a), *HIGH_Z) for (a, b) in ((0.6, 1.3), (2.7, 3.4))]
    back += [(bk(12.6), bk(11.6), FFL, FFL + 2.1)]
    west = [(we(b), we(a), *w) for (a, b) in ((0.4, 1.9), (5.0, 6.5), (7.7, 9.2))]
    west += [(we(-2.4), we(-3.5), FFL, FFL + 2.1)]
    east = [(ea(-8.2), ea(-6.6), FFL, FFL + 2.4)]
    east += [(ea(a), ea(b), *w) for (a, b) in ((-3.5, -2.3), (4.4, 5.6), (7.4, 8.6))]
    east += [(ea(1.0), ea(2.0), *HIGH_Z)]
    Ms = {}
    Ms["front"] = ext_wall(shell, "front", X0, X1, Y0, front, PARA, SLAB_T)
    Ms["back"] = ext_wall(shell, "back", X0, X1, Y1, back, PARA, SLAB_T)
    Ms["west"] = ext_wall(shell, "west", a0s, a1s, X0, west, PARA, SLAB_T, u_trim=0.03)
    Ms["east"] = ext_wall(shell, "east", a0s, a1s, X1, east, PARA, SLAB_T, u_trim=0.03)
    return Ms, dict(front=front, back=back, west=west, east=east)


def courtyard_walls(shell):
    """Muros del patio (cara aplanada hacia el patio, pintura hacia los cuartos), con pretil de 0,3 sobre la azotea."""
    zt = SLAB_T + 0.30
    w = WIN_Z
    # norte (y = 4, patio al sur -> tipo 'front'), sur (y = -1,8, patio al norte -> 'back'),
    # oeste (x = -3, patio al este -> 'east'), este (x = 4, patio al oeste -> 'west')
    xa, xb = CXW - TE / 2, CXE + TE / 2
    ya, yb = CYS + TE / 2, CYN - TE / 2
    n_ops = [(x - xa, x2 - xa, *w) for (x, x2) in ((-2.2, -0.7), (1.0, 2.5))]
    s_ops = [(xb - x2, xb - x, *w) for (x, x2) in ((-2.4, -0.9), (1.9, 3.4))] + [(xb - 1.0, xb, FFL - 0.1, FFL + 2.0)]
    w_ops = [(y - ya, y2 - ya, *w) for (y, y2) in ((-1.0, 0.6), (1.8, 3.4))]
    e_ops = [(yb - y2, yb - y, *w) for (y, y2) in ((-0.8, 0.7), (1.9, 3.4))]
    Ms = {}
    Ms["n"] = ext_wall(shell, "front", xa, xb, CYN - TE / 2, n_ops, zt, SLAB_T)
    Ms["s"] = ext_wall(shell, "back", xa, xb, CYS + TE / 2, s_ops, zt, SLAB_T)
    Ms["w"] = ext_wall(shell, "east", ya, yb, CXW + TE / 2, w_ops, zt, SLAB_T, u_trim=0.03)
    Ms["e"] = ext_wall(shell, "west", ya, yb, CXE - TE / 2, e_ops, zt, SLAB_T, u_trim=0.03)
    return Ms, dict(n=n_ops, s=s_ops, w=w_ops, e=e_ops)


def garage_walls(shell):
    a0s, a1s = GY0 + TE, GY1 - TE
    front = [(0.4, 3.8, G_FL, G_FL + 3.0), (4.2, 7.6, G_FL, G_FL + 3.0)]
    back = [(GX1 - 21.5, GX1 - 19.5, 2.3, 3.0)]
    west = [(a1s + 3.5, a1s + 4.4, G_FL, G_FL + 2.1)]                     # puerta lateral al pasillo cubierto
    east = [(y - a0s, y2 - a0s, 2.3, 3.0) for (y, y2) in ((-6.0, -4.5), (-1.5, 0.0))]
    Ms = {}
    Ms["front"] = ext_wall(shell, "front", GX0, GX1, GY0, front, G_PARA, G_ST)
    Ms["back"] = ext_wall(shell, "back", GX0, GX1, GY1, back, G_PARA, G_ST)
    Ms["west"] = ext_wall(shell, "west", a0s, a1s, GX0, west, G_PARA, G_ST, u_trim=0.03)
    Ms["east"] = ext_wall(shell, "east", a0s, a1s, GX1, east, G_PARA, G_ST, u_trim=0.03)
    return Ms, dict(front=front, back=back, west=west, east=east)


def partitions(inter):
    """Tabiques interiores con sus puertas, ventanillas y pasos."""
    yC1s, yC1n = -4.0, -1.8
    # y = -4: sala/recepción/urgencias contra el pasillo (paso abierto de 2 m de la sala, puerta de recepción, doble de urgencias)
    M, L = partition(inter, (X0 + TE, yC1s), (X1 - TE, yC1s),
                     [(-6.5 - (X0 + TE), -4.5 - (X0 + TE), 0.0, 2.4), (0.2 - (X0 + TE), 1.1 - (X0 + TE), 0.0, 2.1),
                      (6.0 - (X0 + TE), 7.5 - (X0 + TE), 0.0, 2.1)])
    GAPS.append(("x", yC1s, -6.5, -4.5))
    door_in(M, 0.2 - (X0 + TE), 0.9, axis="x", line=yC1s, along0=X0 + TE, ang=70)
    door_in(M, 6.0 - (X0 + TE), 1.5, kind="flush2", axis="x", line=yC1s, along0=X0 + TE, ang=80)
    # x = -2 (sala | recepción): ventanilla; x = 3 (recepción | urgencias): puerta de servicio
    partition(inter, (-2.0, Y0 + TE), (-2.0, yC1s - TI / 2), [(-8.0 - (Y0 + TE), -6.4 - (Y0 + TE), 1.05, 2.2)])
    M, L = partition(inter, (3.0, Y0 + TE), (3.0, yC1s - TI / 2), [(-5.4 - (Y0 + TE), -4.5 - (Y0 + TE), 0.0, 2.1)])
    door_in(M, -5.4 - (Y0 + TE), 0.9, axis="y", line=3.0, along0=Y0 + TE, ang=30)
    # y = -1,8 oeste (consultorios) y este (farmacia, rayos X)
    M, L = partition(inter, (X0 + TE, yC1n), (-5.0 - TI / 2, yC1n),
                     [(-12.2 - (X0 + TE), -11.3 - (X0 + TE), 0.0, 2.1), (-7.8 - (X0 + TE), -6.9 - (X0 + TE), 0.0, 2.1)])
    door_in(M, -12.2 - (X0 + TE), 0.9, axis="x", line=yC1n, along0=X0 + TE, ang=55)
    door_in(M, -7.8 - (X0 + TE), 0.9, axis="x", line=yC1n, along0=X0 + TE, ang=20)
    x0e = CXE + TE / 2
    M, L = partition(inter, (x0e, yC1n), (X1 - TE, yC1n),
                     [(5.0 - x0e, 5.9 - x0e, 0.0, 2.1), (6.6 - x0e, 8.0 - x0e, 1.05, 1.9), (10.4 - x0e, 11.5 - x0e, 0.0, 2.1)])
    door_in(M, 5.0 - x0e, 0.9, axis="x", line=yC1n, along0=x0e, ang=35)
    door_in(M, 10.4 - x0e, 1.1, axis="x", line=yC1n, along0=x0e, ang=10)
    # x = -9,4 (consultorios), x = -5 (consultorio 2 | galería y encamados | pasillo norte), x = 9 (farmacia | rayos X)
    partition(inter, (-9.4, yC1n + TI / 2), (-9.4, CYN - TI / 2))
    M, L = partition(inter, (-5.0, yC1n + TI / 2), (-5.0, Y1 - TE), [(4.25 - (yC1n + TI / 2), 5.75 - (yC1n + TI / 2), 0.0, 2.1)])
    door_in(M, 4.25 - (yC1n + TI / 2), 1.5, kind="flush2", axis="y", line=-5.0, along0=yC1n + TI / 2, ang=60)
    partition(inter, (9.0, yC1n + TI / 2), (9.0, CYN - TI / 2))
    # y = 4 oeste (consultorios | encamados) y este (farmacia, rayos X | pasillo norte)
    partition(inter, (X0 + TE, CYN), (-5.0 - TI / 2, CYN))
    partition(inter, (CXE + TE / 2, CYN), (X1 - TE, CYN))
    # y = 6 (pasillo norte | enfermería, baños, cocina, lavandería)
    x0n = -5.0 + TI / 2
    ops6 = [(-4.3 - x0n, -1.6 - x0n, 0.95, 2.1), (-1.2 - x0n, -0.3 - x0n, 0.0, 2.1), (0.5 - x0n, 1.3 - x0n, 0.0, 2.1),
            (2.6 - x0n, 3.4 - x0n, 0.0, 2.1), (5.0 - x0n, 5.9 - x0n, 0.0, 2.1), (10.0 - x0n, 10.9 - x0n, 0.0, 2.1)]
    M, L = partition(inter, (x0n, 6.0), (X1 - TE, 6.0), ops6)
    for (a, b, ang) in ((-1.2, -0.3, 40), (0.5, 1.3, 15), (2.6, 3.4, 70), (5.0, 5.9, 50), (10.0, 10.9, 30)):
        door_in(M, a - x0n, b - a, axis="x", line=6.0, along0=x0n, ang=ang)
    for x in (0.0, 2.0, 4.0, 9.0):
        partition(inter, (x, 6.0 + TI / 2), (x, Y1 - TE))


# ------------------------------------------------------------------------------------------------------------ acabados
ROOMS = {   # nombre: (x0, x1, y0, y1, acabado)  caras interiores
    "espera": (X0 + TE, -2.0 - TI / 2, Y0 + TE, -4.0 - TI / 2, "mint"),
    "recepcion": (-2.0 + TI / 2, 3.0 - TI / 2, Y0 + TE, -4.0 - TI / 2, "mint"),
    "urgencias": (3.0 + TI / 2, X1 - TE, Y0 + TE, -4.0 - TI / 2, "mint"),
    "pasillo": (X0 + TE, X1 - TE, -4.0 + TI / 2, -1.8 - TI / 2, "mint"),
    "consultorio1": (X0 + TE, -9.4 - TI / 2, -1.8 + TI / 2, CYN - TI / 2, "mint"),
    "consultorio2": (-9.4 + TI / 2, -5.0 - TI / 2, -1.8 + TI / 2, CYN - TI / 2, "mint"),
    "galeria": (-5.0 + TI / 2, CXW - TE / 2, -1.8 + TI / 2, CYN + TE / 2, "mint"),
    "farmacia": (CXE + TE / 2, 9.0 - TI / 2, -1.8 + TI / 2, CYN - TI / 2, "mint"),
    "rayosx": (9.0 + TI / 2, X1 - TE, -1.8 + TI / 2, CYN - TI / 2, "mint"),
    "pasillo_n": (-5.0 + TI / 2, X1 - TE, CYN + TI / 2, 6.0 - TI / 2, "mint"),
    "encamados": (X0 + TE, -5.0 - TI / 2, CYN + TI / 2, Y1 - TE, "mint"),
    "enfermeria": (-5.0 + TI / 2, 0.0 - TI / 2, 6.0 + TI / 2, Y1 - TE, "mint"),
    "bano1": (0.0 + TI / 2, 2.0 - TI / 2, 6.0 + TI / 2, Y1 - TE, "tile"),
    "bano2": (2.0 + TI / 2, 4.0 - TI / 2, 6.0 + TI / 2, Y1 - TE, "tile"),
    "cocina": (4.0 + TI / 2, 9.0 - TI / 2, 6.0 + TI / 2, Y1 - TE, "mint"),
    "lavanderia": (9.0 + TI / 2, X1 - TE, 6.0 + TI / 2, Y1 - TE, "mint"),
}


def _gaps_on(axis, line, a, b, tol=0.26):
    # 0,26 > grueso del muro exterior (0,20): las puertas exteriores se registran en la cara exterior (Y0, X0...) y los cuartos
    # corren por la cara interior; con 0,16 el lambrín y el zoclo tapaban el metro inferior de las 4 puertas exteriores (y
    # entraban a la colisión: no se podía entrar por la puerta principal)
    out = []
    for (ax, ln, g0, g1) in GAPS:
        if ax == axis and abs(ln - line) < tol and g1 > a and g0 < b:
            out.append((max(g0, a), min(g1, b)))
    return sorted(out)


def _runs(a, b, gaps):
    out, cur = [], a
    for (g0, g1) in gaps:
        if g0 > cur:
            out.append((cur, g0))
        cur = max(cur, g1)
    if b > cur:
        out.append((cur, b))
    return out


def wainscot(inter, name):
    """Lambrín pintado (verde menta a 1,0 m con filete verde oscuro) o azulejo a 1,8 m en baños, por cuarto, cortado en puertas."""
    x0, x1, y0, y1, kind = ROOMS[name]
    if kind == "tile":
        H, mat, line = 1.8, "tile_white", None
        inter.box((x0, y0, FFL), (x1, y1, FFL + 0.008), "tile_white")
    else:
        H, mat, line = WAIN, "paint_mint", "paint_green"
    e = 0.004
    sides = [("x", y0, x0 + e, x1 - e, +1), ("x", y1, x0 + e, x1 - e, -1), ("y", x0, y0 + e, y1 - e, +1), ("y", x1, y0 + e, y1 - e, -1)]
    for (ax, ln, a, b, inward) in sides:
        for (ra, rb) in _runs(a, b, _gaps_on(ax, ln, a, b)):
            if rb - ra < 0.05:
                continue
            c0, c1 = ln + inward * 0.001, ln + inward * 0.004
            c0, c1 = min(c0, c1), max(c0, c1)
            if ax == "x":
                inter.box((ra, c0, FFL), (rb, c1, FFL + H), mat)
                if line:
                    inter.box((ra, min(c0, ln + inward * 0.005), FFL + H), (rb, max(c1, ln + inward * 0.005), FFL + H + 0.025), line)
                inter.box((ra, min(ln, ln + inward * 0.012), FFL), (rb, max(ln, ln + inward * 0.012), FFL + 0.1), "terrazzo")
            else:
                inter.box((c0, ra, FFL), (c1, rb, FFL + H), mat)
                if line:
                    inter.box((min(c0, ln + inward * 0.005), ra, FFL + H), (max(c1, ln + inward * 0.005), rb, FFL + H + 0.025), line)
                inter.box((min(ln, ln + inward * 0.012), ra, FFL), (max(ln, ln + inward * 0.012), rb, FFL + 0.1), "terrazzo")
    # moldura perimetral del plafón (ángulo blanco)
    for (ax, ln, a, b, inward) in sides:
        if ax == "x":
            inter.box((a, min(ln, ln + inward * 0.022), CEIL - 0.022), (b, max(ln, ln + inward * 0.022), CEIL), "sign_white")
        else:
            inter.box((min(ln, ln + inward * 0.022), a, CEIL - 0.022), (max(ln, ln + inward * 0.022), b, CEIL), "sign_white")


def lights(det, name, step=2.4):
    x0, x1, y0, y1, _ = ROOMS[name]
    nx = max(1, int((x1 - x0) / step))
    ny = max(1, int((y1 - y0) / step))
    for i in range(nx):
        for j in range(ny):
            x = x0 + (x1 - x0) * (i + 0.5) / nx
            y = y0 + (y1 - y0) * (j + 0.5) / ny
            rot = 90 if (y1 - y0) > (x1 - x0) else 0
            det.join(cl.fluorescent(), _T(x, y, CEIL) @ _Rz(rot))
            LIGHTS.append([round(x, 3), round(y, 3), round(CEIL - 0.085, 3)])


# ------------------------------------------------------------------------------------------------------------ vanos
def surround(det, M, u0, u1, v0, v1, fw=0.09, proud=0.025, mat="paint_green", bottom=False):
    """Marco de aplanado en relieve alrededor de un vano (como en la referencia: marcos verdes sobre el muro crema)."""
    det.box((u0 - fw, -proud, v0 - (fw if bottom else 0.0)), (u0, 0.0, v1 + fw), mat, bevel=0.006, m=M)
    det.box((u1, -proud, v0 - (fw if bottom else 0.0)), (u1 + fw, 0.0, v1 + fw), mat, bevel=0.006, m=M)
    det.box((u0, -proud, v1), (u1, 0.0, v1 + fw), mat, bevel=0.006, m=M)
    if bottom:
        det.box((u0, -proud, v0 - fw), (u1, 0.0, v0), mat, bevel=0.006, m=M)


def place_windows(det, M, ops, r, depth=TE, grille=True, sill=True, frame=True):
    for (u0, u1, v0, v1) in ops:
        w, h = u1 - u0, v1 - v0
        if v0 <= FFL + 0.05:
            if frame and v0 >= 0.0:
                surround(det, M, u0, u1, v0, v1)
            continue
        if frame:
            surround(det, M, u0, u1, v0, v1)
        det.join(cl.window_clean(w, h, depth=depth, seed=int(r.integers(1e6)), sill=sill), M @ _T(u0, 0, v0))
        if grille:
            det.join(cl.window_grille(w, h - 0.05, seed=int(r.integers(1e6))), M @ _T(u0, 0, v0 + 0.05))


def place_doors(det, r):
    """Puertas limpias de hospital en uso (kit/clinic): tablero pintado, doble de tablero, doble de vidrio y de acero."""
    for (M, w, h, kind, ang, depth) in DOORS:
        if kind == "flush":
            det.join(cl.door_panel(w, h, depth=depth, seed=int(r.integers(1e6)), ang=ang), M)
        elif kind == "flush2":
            leaf = w / 2
            det.join(cl.door_panel(leaf, h, depth=depth, seed=int(r.integers(1e6)), ang=ang), M)
            det.join(cl.door_panel(leaf, h, depth=depth, seed=int(r.integers(1e6)), ang=ang * 0.15),
                     M @ _T(w, 0, 0) @ Matrix.Scale(-1, 4, Vector((1, 0, 0))))
        elif kind == "double_glazed":
            det.join(cl.door_glass_double(w, h, depth=depth, seed=int(r.integers(1e6)), angles=(ang, ang * 0.3),
                                          transom=max(0.0, h - 2.1)), M)
        else:
            det.join(cl.door_steel(w, h, depth=depth, seed=int(r.integers(1e6)), ang=ang), M)


# ------------------------------------------------------------------------------------------------------------ exterior
def wedge(mb, x0, x1, y0, y1, z0a, z0b, mat="concrete", axis="y"):
    """Sólido de rampa: cara superior de z0a (en x0/y0) a z0b (en x1/y1), base en z = 0."""
    if axis == "y":
        pts = [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0), (x0, y0, z0a), (x1, y0, z0a), (x1, y1, z0b), (x0, y1, z0b)]
    else:
        pts = [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0), (x0, y0, z0a), (x1, y0, z0b), (x1, y1, z0b), (x0, y1, z0a)]
    v = [mb.bm.verts.new(p) for p in pts]
    for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        mb.face([v[i] for i in q], mat)


def cornice(shell, x0, x1, y0, y1, z, h=0.1, proud=0.05):
    """Moldura corrida bajo el pretil: frente y fondo de esquina a esquina, costados entre ellos (sin caras encimadas)."""
    shell.box((x0 - proud, y0 - proud, z), (x1 + proud, y0, z + h), "plaster")
    shell.box((x0 - proud, y1, z), (x1 + proud, y1 + proud, z + h), "plaster")
    shell.box((x0 - proud, y0, z), (x0, y1, z + h), "plaster")
    shell.box((x1, y0, z), (x1 + proud, y1, z + h), "plaster")


def site(shell, inter, det, roof, r):
    """Banqueta, pórtico, escalones, rampas, pasillo cubierto de urgencias, plataforma de la cochera, barda y portón."""
    # banquetas (piso propio del modelo, no terreno)
    inter.box((SIDE_WALL_XW, -14.5, 0.0), (X1, Y0, PAVE), "concrete")
    inter.box((GX0, -14.5, 0.0), (SIDE_WALL_XE, Y0, PAVE), "concrete")
    inter.box((GX0, Y0, 0.0), (SIDE_WALL_XE, GY0, PAVE), "concrete")
    for x in np.arange(SIDE_WALL_XW + 1.5, SIDE_WALL_XE, 1.5):          # juntas de la banqueta
        if not (X1 - 0.05 < x < GX0 + 0.05):
            det.box((x - 0.006, -14.49, PAVE - 0.004), (x + 0.006, Y0 - 0.01, PAVE + 0.0005), "mortar")
    # pórtico
    px0, px1, py0 = -11.0, -5.0, -12.4
    inter.box((px0, py0, PAVE), (px1, Y0, FFL), "terrazzo")
    for k in range(3):
        zt = PAVE + (FFL - PAVE) * (k + 1) / 3
        inter.box((-10.2, -13.3 + 0.3 * k, PAVE), (-5.8, py0, zt), "concrete")
        det.box((-10.2, -13.3 + 0.3 * k, zt - 0.003), (-5.8, -13.3 + 0.3 * k + 0.04, zt + 0.002), "paint_yellow")
    for x in (-10.85, -9.15, -6.85, -5.15):
        shell.box((x - 0.15, -12.4, FFL), (x + 0.15, -12.1, 3.25), "plaster")
    shell.box((-11.1, -12.55, 3.0), (-4.9, -12.1, 3.45), "plaster")
    shell.box((-11.1, -12.1, 3.25), (-4.9, Y0, 3.45), "plaster")
    roof.box((-11.08, -12.53, 3.45), (-4.92, Y0, 3.47), "concrete")
    # rampa accesible al oeste del pórtico, con guarniciones y pasamanos
    wedge(inter, -16.6, px0, -12.4, -11.2, PAVE, FFL, axis="x")
    for (ya, yb) in ((-12.5, -12.4), (-11.2, -11.1)):
        wedge(inter, -16.6, px0, ya, yb, PAVE + 0.1, FFL + 0.1, axis="x")
    for y in (-12.45, -11.15):
        port.handrail(det, (-16.5, y, PAVE + 0.1 + 0.0), (px0 - 0.1, y, FFL + 0.1), h=0.9, post_step=1.4, r=r, knee=True, mat="steel")
    # pasillo cubierto de urgencias: rampa, descanso, escalones y firme
    wedge(inter, X1, GX0, -14.5, -9.6, PAVE, FFL, axis="y")
    inter.box((X1, -9.6, 0.0), (GX0, -5.6, FFL), "concrete")
    for k in range(3):
        zt = FFL - (FFL - PAVE) * (k + 1) / 3
        inter.box((X1, -5.6 + 0.3 * k, 0.0), (GX0, -5.6 + 0.3 * (k + 1), zt + (FFL - PAVE) / 3), "concrete")
    inter.box((X1, -4.7, 0.0), (GX0, GY1, PAVE), "concrete")
    y = -14.3
    while y < -9.8:                                                    # estrías antiderrapantes de la rampa
        z = PAVE + (FFL - PAVE) * (y + 14.5) / 4.9
        det.box((X1 + 0.15, y, z - 0.002), (GX0 - 0.15, y + 0.025, z + 0.004), "concrete")
        y += 0.15
    for x in (X1 + 0.06, GX0 - 0.06):
        port.handrail(det, (x, -14.35, PAVE), (x, -10.15, FFL), h=0.9, post_step=1.4, r=r, knee=True, mat="steel")
    # marquesina de lámina sobre el pasillo (vigas canal, postes, largueros, lámina ondulada, canalón)
    zt_back, zt_front = 3.48, 3.22
    zf = lambda y: zt_front + (zt_back - zt_front) * (y + 14.6) / (GY1 + 14.6)  # noqa: E731
    for x in (X1 + 0.06, GX0 - 0.06):
        port.member(det, (x, -14.6, zf(-14.6) - 0.1), (x, GY1, zf(GY1) - 0.1),
                    [(-0.025, 0.025, -0.075, -0.067), (-0.025, 0.025, 0.067, 0.075), (-0.025, -0.017, -0.075, 0.075)], "paint_green",
                    up=(0, 0, 1))
        cl.rtube(det, (x, -14.45, PAVE), (x, -14.45, zf(-14.45) - 0.17), 0.1, 0.1, "paint_green", up=(1, 0, 0), r=0.006)
        det.box((x - 0.12, -14.57, PAVE), (x + 0.12, -14.33, PAVE + 0.012), "steel", bevel=0.002)
        for (dx, dy) in ((-0.09, -0.09), (0.09, -0.09), (-0.09, 0.09), (0.09, 0.09)):
            port.bolt(det, _T(x + dx, -14.45 + dy, PAVE + 0.012), d=0.012, stud=0.01, mat="steel")
    y = -14.4
    while y < GY1:
        cl.rtube(det, (X1 + 0.02, y, zf(y) - 0.02), (GX0 - 0.02, y, zf(y) - 0.02), 0.04, 0.08, "paint_green", up=(0, 0, 1), r=0.003)
        y += 1.3
    _corrugated(det, X1 - 0.05, GX0 + 0.05, -14.7, GY1 + 0.02, zf, mat="roof_metal_light")
    det.tube([(X1 - 0.04, -14.75, zt_front - 0.03), (GX0 + 0.04, -14.75, zt_front - 0.03)], 0.06, seg=12, mat="paint_green")
    det.tube([(GX0 + 0.04, -14.75, zt_front - 0.03), (GX0 + 0.15, -14.75, zt_front - 0.1), (GX0 + 0.15, -14.75, PAVE + 0.15),
              (GX0 + 0.25, -14.78, PAVE + 0.05)], 0.035, seg=10, mat="plastic")
    # barda perimetral de block con castillos y remate; portón de servicio
    walls = [((SIDE_WALL_XW, BACK_WALL_Y), (SIDE_WALL_XE, BACK_WALL_Y)), ((SIDE_WALL_XW, -10.0), (SIDE_WALL_XW, BACK_WALL_Y)),
             ((SIDE_WALL_XE, GY0), (SIDE_WALL_XE, BACK_WALL_Y))]
    gate = (3.0, 7.0)
    for (a, b) in walls:
        ax = "x" if a[1] == b[1] else "y"
        L = abs((b[0] - a[0]) if ax == "x" else (b[1] - a[1]))
        k = 0
        pos = 0.0
        while pos < L - 1e-6:
            seg = min(3.0, L - pos)
            p0 = pos
            p1 = pos + seg
            if ax == "x":
                xa, xb = a[0] + p0, a[0] + p1
                for (g0, g1) in ((-99, gate[0]), (gate[1], 99)):
                    s0, s1 = max(xa, g0), min(xb, g1)
                    if s1 - s0 > 0.01:
                        shell.box((s0, a[1] - 0.075, 0.0), (s1, a[1] + 0.075, 1.8), "concrete")
                        shell.box((s0, a[1] - 0.1, 1.8), (s1, a[1] + 0.1, 1.88), "concrete")
                if not (gate[0] - 0.2 < xa < gate[1] + 0.2):
                    shell.box((xa - 0.1, a[1] - 0.1, 0.0), (xa + 0.1, a[1] + 0.1, 1.85), "concrete")
            else:
                ya, yb = a[1] + p0, a[1] + p1
                shell.box((a[0] - 0.075, ya, 0.0), (a[0] + 0.075, yb, 1.8), "concrete")
                shell.box((a[0] - 0.1, ya, 1.8), (a[0] + 0.1, yb, 1.88), "concrete")
                shell.box((a[0] - 0.1, ya - 0.1, 0.0), (a[0] + 0.1, ya + 0.1, 1.85), "concrete")
            pos += seg
            k += 1
    for x in gate:
        shell.box((x - 0.15, BACK_WALL_Y - 0.15, 0.0), (x + 0.15, BACK_WALL_Y + 0.15, 2.1), "concrete")
    _gate(det, gate[0] + 0.15, gate[1] - 0.15, BACK_WALL_Y, r)


def _corrugated(mb, x0, x1, y0, y1, zf, mat="roof_metal_light", pitch=0.076, amp=0.009, t=0.0008):
    """Lámina ondulada continua (ondas paralelas a Y) con espesor, siguiendo la pendiente zf(y)."""
    nx = int((x1 - x0) / pitch * 8)
    ny = max(2, int((y1 - y0) / 1.0))
    top, bot = [], []
    for j in range(ny + 1):
        y = y0 + (y1 - y0) * j / ny
        rt, rb = [], []
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            z = zf(y) + amp * math.sin(2 * math.pi * (x - x0) / pitch)
            rt.append(mb.bm.verts.new((x, y, z + t)))
            rb.append(mb.bm.verts.new((x, y, z)))
        top.append(rt)
        bot.append(rb)
    for j in range(ny):
        for i in range(nx):
            f = mb.face([top[j][i], top[j][i + 1], top[j + 1][i + 1], top[j + 1][i]], mat)
            f.smooth = True
            f = mb.face([bot[j + 1][i], bot[j + 1][i + 1], bot[j][i + 1], bot[j][i]], mat)
            f.smooth = True
    for j in range(ny):
        for (i, k) in ((0, 0), (nx, 1)):
            q = [top[j][i], top[j + 1][i], bot[j + 1][i], bot[j][i]]
            mb.face(q if k == 0 else list(reversed(q)), mat)
    for (j, k) in ((0, 0), (ny, 1)):
        for i in range(nx):
            q = [top[j][i], bot[j][i], bot[j][i + 1], top[j][i + 1]]
            mb.face(q if k == 0 else list(reversed(q)), mat)


def _gate(det, x0, x1, y, r):
    """Portón de dos hojas de herrería: bastidor de PTR, barrotes cuadrados, lámina en la parte baja, bisagras y pasador."""
    mid = (x0 + x1) / 2
    for (a, b) in ((x0, mid - 0.01), (mid + 0.01, x1)):
        cl.rtube(det, (a, y, 0.05), (a, y, 1.95), 0.05, 0.05, "paint_green", up=(1, 0, 0), r=0.004)
        cl.rtube(det, (b, y, 0.05), (b, y, 1.95), 0.05, 0.05, "paint_green", up=(1, 0, 0), r=0.004)
        for z in (0.07, 0.9, 1.93):
            cl.rtube(det, (a, y, z), (b, y, z), 0.05, 0.04, "paint_green", up=(0, 0, 1), r=0.004)
        det.box((a + 0.02, y - 0.003, 0.09), (b - 0.02, y + 0.003, 0.88), "paint_green", bevel=0.001)
        x = a + 0.12
        while x < b - 0.06:
            det.box((x - 0.008, y - 0.008, 0.92), (x + 0.008, y + 0.008, 1.92), "paint_green", bevel=0.001)
            x += 0.12
        for z in (0.3, 1.6):
            det.cyl((a if a == x0 else b, y - 0.04, z), (a if a == x0 else b, y - 0.04, z + 0.12), 0.012, seg=8, mat="steel")
    det.cyl((mid, y - 0.03, 1.0), (mid + 0.15, y - 0.03, 1.0), 0.01, seg=8, mat="steel")


# ------------------------------------------------------------------------------------------------------------ azotea y servicios
def rooftop(roof, det, r):
    # registro de azotea con tapa de lámina y bisagras
    roof.box((-8.5, 6.2, SLAB_T), (-7.6, 7.1, SLAB_T + 0.35), "concrete", bevel=0.01)
    det.box((-8.55, 6.15, SLAB_T + 0.35), (-7.55, 7.15, SLAB_T + 0.39), "paint_green", bevel=0.006)
    det.box((-8.12, 6.12, SLAB_T + 0.36), (-7.98, 6.16, SLAB_T + 0.38), "steel", bevel=0.002)
    for x in (-8.4, -7.7):
        det.cyl((x, 7.17, SLAB_T + 0.37), (x + 0.08, 7.17, SLAB_T + 0.37), 0.008, seg=8, mat="steel")
    # tubos de ventilación de los baños y la cocina, con sombrerete
    for (x, y) in ((0.9, 8.6), (3.0, 8.6), (6.2, 9.1), (-3.0, 9.1)):
        det.cyl((x, y, SLAB_T), (x, y, SLAB_T + 0.6), 0.05, seg=14, mat="plastic")
        port.lathe(det, [(0.0, 0.0), (0.055, 0.0), (0.055, 0.03), (0.0, 0.03)], seg=14, mat="plastic", M=_T(x, y, SLAB_T))
        port.lathe(det, [(0.0, 0.0), (0.09, 0.0), (0.085, 0.015), (0.05, 0.05), (0.0, 0.06)], seg=14, mat="plastic",
                   M=_T(x, y, SLAB_T + 0.66))
        for k in range(3):
            a = 2 * math.pi * k / 3
            det.cyl((x + 0.05 * math.cos(a), y + 0.05 * math.sin(a), SLAB_T + 0.6),
                    (x + 0.05 * math.cos(a), y + 0.05 * math.sin(a), SLAB_T + 0.66), 0.006, seg=5, mat="plastic")
    # tubería de los tinacos bajando a la azotea y al muro
    det.tube([(9.2, 7.0, SLAB_T + 0.9), (9.2, 7.0, SLAB_T + 0.12), (9.2, 9.6, SLAB_T + 0.12), (9.2, 9.75, SLAB_T - 0.3),
              (9.2, 10.06, SLAB_T - 0.3), (9.2, 10.06, FFL + 0.4)], 0.022, seg=10, mat="plastic")      # bajante entre vanos
    for (x, y) in ((7.4, 7.6), (9.0, 7.6)):
        det.join(sv.water_tank(seed=int(r.integers(1e6)), detail="mid"), _T(x, y, SLAB_T))
    # gárgolas de PVC en el pretil (fondo y costados), cada ~7 m
    for x in (-10.0, -3.0, 4.0, 11.0):
        det.cyl((x, Y1 - 0.25, SLAB_T + 0.05), (x, Y1 + 0.35, SLAB_T + 0.03), 0.05, seg=12, mat="plastic")
    for y in (-6.0, 1.0, 7.0):
        det.cyl((X0 + 0.25, y, SLAB_T + 0.05), (X0 - 0.35, y, SLAB_T + 0.03), 0.05, seg=12, mat="plastic")
        det.cyl((X1 - 0.25, y, SLAB_T + 0.05), (X1 + 0.35, y, SLAB_T + 0.03), 0.05, seg=12, mat="plastic")
    for x in (18.0, 22.5):
        det.cyl((x, GY1 - 0.25, G_ST + 0.05), (x, GY1 + 0.35, G_ST + 0.03), 0.05, seg=12, mat="plastic")
    # mástil de radio de la ambulancia sobre la cochera
    det.cyl((23.4, 1.2, G_ST), (23.4, 1.2, G_ST + 5.0), 0.025, seg=10, mat="steel")
    det.cyl((23.4, 1.2, G_ST + 5.0), (23.4, 1.2, G_ST + 6.4), 0.006, seg=6, mat="steel")
    det.box((23.33, 1.13, G_ST), (23.47, 1.27, G_ST + 0.012), "steel")
    for (dx, dy) in ((1.5, 0.0), (-1.0, 1.0), (-1.0, -1.2)):
        det.cyl((23.4, 1.2, G_ST + 4.2), (23.4 + dx, 1.2 + dy, G_ST), 0.002, seg=4, mat="steel")
    # condensadoras de minisplit en el muro trasero y oriente, con su tubería forrada
    Mb = ac.panel_matrix("back", X0, X1, Y1, 0.0)
    for x in (-10.0, -5.4, 4.6, 8.4, 13.4):                    # entre ventanas y puerta de servicio, nunca sobre un vano
        ac_ = cl.remap(sv.ac_unit("split_outdoor", seed=int(r.integers(1e6)), detail="mid"),
                       {"metal_rust": "enamel", "metal_paint": "sign_white"})            # equipo en servicio: lámina esmaltada
        det.join(ac_, Mb @ _T(X1 - x, 0, 2.05))
        det.tube([tuple(Mb @ Vector((X1 - x + 0.3, -0.12, 2.35))), tuple(Mb @ Vector((X1 - x + 0.3, -0.06, 2.9))),
                  tuple(Mb @ Vector((X1 - x + 0.3, 0.05, 2.95)))], 0.018, seg=8, mat="plastic")
    det.join(cl.remap(sv.meter_box(seed=int(r.integers(1e6)), open_door=False, detail="high"),
                      {"metal_rust": "enamel", "metal_paint": "enamel"}), Mb @ _T(X1 - 3.9, 0, 1.4))
    det.join(cl.remap(sv.conduit([(X1 - 3.9, 0.0, 1.92), (X1 - 3.9, 0.0, 3.3), (X1 - 4.2, 0.0, 3.3), (X1 - 4.2, 0.0, PARA - 0.15)],
                                 seed=int(r.integers(1e6)), detail="high"), {"metal_rust": "steel", "metal_paint": "steel"}), Mb)                # conduit del medidor hacia la azotea


# ------------------------------------------------------------------------------------------------------------ letreros
def signage(det, Ms, r):
    F = Ms["front"]
    cl.text(det, "COMMUNITY HOSPITAL", 0.44, 0.015, "paint_green", F @ _T(-X0, 0, SLAB_T + 0.1) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    det.join(cl.sign_plate("H", 0.7, 0.7, bg="sign_blue", fg="sign_white", size=0.5, frame="sign_white"), F @ _T(-1.25 - X0, 0, 2.2))
    for x in (-9.6, -6.4):
        det.join(cl.wall_lamp(), F @ _T(x - X0, 0, 2.6))
    E = ac.panel_matrix("east", Y0 + TE, Y1 - TE, X1, 0.0)
    det.join(cl.sign_plate("EMERGENCY", 2.0, 0.42, bg="sign_red", fg="sign_white", size=0.24, t=0.08), E @ _T(-7.4 - (Y0 + TE), 0, 2.92))
    det.join(cl.wall_lamp(), E @ _T(-5.9 - (Y0 + TE), 0, 2.55))
    det.join(cl.sign_plate("EMERGENCY", 1.9, 0.38, bg="sign_red", fg="sign_white", size=0.22, t=0.06), _T((X1 + GX0) / 2, -14.78, 2.78))
    G = ac.panel_matrix("front", GX0, GX1, GY0, 0.0)
    cl.text(det, "AMBULANCE ENTRANCE", 0.26, 0.012, "sign_red", G @ _T((GX1 - GX0) / 2, 0, 3.32) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    det.join(cl.sign_plate("AMBULANCE ONLY", 0.62, 0.3, bg="sign_white", fg="sign_red", size=0.075), G @ _T(4.0, 0, 1.7))
    for u in (0.2, 4.0, 7.8):
        det.join(cl.wall_lamp(), G @ _T(u, 0, 2.95))
    for (x0, x1) in ((GX0 + 0.4, GX0 + 3.8), (GX0 + 4.2, GX0 + 7.6)):        # franjas y NO PARKING pintados en la plataforma
        for x in (x0, x1 - 0.1):
            det.box((x, -14.2, PAVE), (x + 0.1, GY0 - 0.2, PAVE + 0.002), "paint_yellow", bevel=0.0)
        cl.text(det, "NO PARKING", 0.42, 0.002, "paint_yellow", _T((x0 + x1) / 2, -12.4, PAVE))      # legible entrando desde la calle
    B = ac.panel_matrix("back", X0, X1, Y1, 0.0)
    det.join(cl.sign_plate("STAFF ONLY", 0.5, 0.15, bg="sign_white", fg="sign_red", size=0.06), B @ _T(X1 - 12.1, 0, FFL + 2.2))
    det.join(cl.wall_lamp(), B @ _T(X1 - 12.95, 0, FFL + 2.35))


# ------------------------------------------------------------------------------------------------------------ interior
def _wall_item(det, piece, x, y, z, facing, solid=False):
    M = _T(x, y, z) @ face_to(facing)
    if solid:
        _proxy(piece, M)
    det.join(piece, M)


def furnish(inter, det, r):
    R = ROOMS
    z = FFL

    def put(mb_dst, piece, x, y, facing="-y", dz=0.0):
        """Coloca una pieza de mobiliario: todo va a Detalle; lo que se pedía en `inter` deja además su caja de colisión."""
        M = _T(x, y, z + dz) @ face_to(facing)
        if mb_dst is inter:
            _proxy(piece, M)
        det.join(piece, M)

    # sala de espera: 3 bancadas hacia la ventanilla, una contra la fachada, plantas, garrafón, tablero, reloj, carteles
    x0, x1, y0, y1, _ = R["espera"]
    for (x, n) in ((-12.6, 5), (-10.4, 5), (-8.2, 4)):
        put(inter, cl.chair_row(n, seed=int(r.integers(1e6))), x, -7.0, "+x")
    put(inter, cl.chair_row(4, seed=int(r.integers(1e6))), -5.0, y0 + 0.45, "+y")
    put(inter, cl.water_dispenser(), x0 + 0.3, y1 - 0.35, "+x")
    for (x, y) in ((x0 + 0.35, y0 + 0.35), (-6.5, y0 + 0.35), (-2.6, y1 - 0.4)):
        put(det, cl.potted_plant(int(r.integers(1e6))), x, y)
    _wall_item(det, cl.notice_board(1.2, 0.8, seed=int(r.integers(1e6))), -10.0, y1, z + 1.25, "-y")
    _wall_item(det, cl.clock(), -8.0, y1, z + 2.25, "-y")
    for k, s in enumerate(("WASH YOUR HANDS", "VACCINATION DAY", "STAY HYDRATED")):
        _wall_item(det, cl.poster(s), -13.1 + k * 0.6, y1, z + 1.35, "-y")
    _wall_item(det, cl.sanitizer(), -8.0, y0, z + 1.2, "+y")
    _wall_item(det, cl.exit_sign(), -8.0, y0, z + 2.5, "+y")
    det.join(cl.hanging_sign("WAITING ROOM", 1.3, 0.28), _T(-8.6, -6.2, CEIL))
    for (x, y) in ((-10.5, -7.0), (-5.5, -7.0)):
        det.join(cl.ceiling_fan(int(r.integers(1e6))), _T(x, y, CEIL))
    put(det, cl.trash_bin(pedal=False), -9.6, y0 + 0.3)
    _wall_item(det, cl.sign_plate("RECEPTION", 1.1, 0.24, size=0.13), x1, -7.2, z + 2.3, "-x")
    _wall_item(det, cl.extinguisher(), x0, -5.0, z, "+x")
    # ventanilla de recepción: cancel de aluminio y repisas a ambos lados
    det.join(cl.window_clean(1.6, 1.15, depth=TI, seed=int(r.integers(1e6)), sill=False, open_frac=0.6),
             _T(-2.0 + TI / 2, -8.0, z + 1.05) @ _Rz(90))
    for sgn in (-1, 1):
        inter.box((-2.0 + sgn * TI / 2 - (0.25 if sgn < 0 else 0), -8.05, z + 1.02), (-2.0 + sgn * TI / 2 + (0.25 if sgn > 0 else 0), -6.35, z + 1.05),
                  "wood_varnish", bevel=0.004)
    # recepción
    x0, x1, y0, y1, _ = R["recepcion"]
    put(inter, cl.desk(1.5, 0.7, seed=int(r.integers(1e6))), -1.2, -7.2, "-x")
    put(inter, cl.office_chair(int(r.integers(1e6))), -0.3, -7.3, "-x")
    for y in (-9.4, -8.9):
        put(inter, cl.filing_cabinet(int(r.integers(1e6))), x1 - 0.35, y, "-x")
    put(inter, cl.shelving(0.9, 0.35, 1.8, 4, seed=int(r.integers(1e6))), x1 - 0.25, -6.2, "-x")
    _wall_item(det, cl.split_indoor(), 0.5, y1, z + 2.35, "-y")
    _wall_item(det, cl.clock(), 0.8, y0, z + 2.25, "+y")
    # urgencias: 2 camas con cortinas, camilla, oxígeno, anaquel, lavabo, carro, silla de ruedas, portasueros
    x0, x1, y0, y1, _ = R["urgencias"]
    for k, x in enumerate((5.2, 9.0)):
        put(inter, cl.hospital_bed(int(r.integers(0, 6)), rails_up=k == 0, fowler=(28.0 if k == 1 else 0.0), blanket=k == 0),
            x, y0 + 1.15, "+y")                                   # cabecera contra la fachada
        put(det, cl.iv_stand(int(r.integers(1e6))), x + 0.75, y0 + 0.5)
        put(inter, cl.bedside_cabinet(int(r.integers(1e6))), x - 0.85, y0 + 0.35, "+y")
        cl.curtain_track(det, [(x - 1.25, y0 + 0.02), (x - 1.25, y0 + 2.6), (x + 1.25, y0 + 2.6), (x + 1.25, y0 + 0.02)], CEIL,
                         z + 0.3, r, open_runs=(1,))
    put(inter, cl.stretcher(int(r.integers(1e6))), 12.4, -6.2, "-x")
    put(inter, cl.cylinder_rack(2, seed=int(r.integers(1e6))), 12.9, y1 - 0.35, "-y")
    put(inter, cl.shelving(1.0, 0.4, 2.0, 5, seed=int(r.integers(1e6))), 7.2, y1 - 0.25, "-y")
    _wall_item(det, cl.sink(), x0, -6.5, z, "+x")
    put(det, cl.wheelchair(int(r.integers(1e6))), 10.8, y1 - 0.5, "+x")
    put(det, cl.trash_bin(), x0 + 0.3, -7.5)
    _wall_item(det, cl.split_indoor(), 9.0, y1, z + 2.35, "-y")
    _wall_item(det, cl.exit_sign(), x1, -7.4, z + 2.6, "-x")
    _wall_item(det, cl.sanitizer(), x1, -5.8, z + 1.2, "-x")
    # pasillo: pasamanos de madera, letreros de puerta, colgante, extintor, camilla y silla de ruedas estacionadas
    x0, x1, y0, y1, _ = R["pasillo"]
    for (yy, d) in ((y0, "+y"), (y1, "-y")):
        segs = _runs(x0 + 0.1, x1 - 0.1, _gaps_on("x", -4.0 if yy == y0 else -1.8, x0, x1) +
                     ([(CXW - TE / 2 - 2.0, CXE + TE / 2)] if yy == y1 else []))
        for (a, b) in segs:
            if b - a < 0.4:
                continue
            rail = cl.handrail(b - a, seed=int(r.integers(1e6)))      # corre en +x local: girado 180° (muro sur) arranca en b
            _wall_item(det, rail, b if d == "+y" else a, yy, z + 0.89, d)
    for (txt, x) in (("EXAM 1", -11.75), ("EXAM 2", -7.35), ("PHARMACY", 5.45), ("X-RAY", 10.95)):
        _wall_item(det, cl.sign_plate(txt, 0.55, 0.15, size=0.075), x, y1, z + 2.25, "-y")
    for (txt, x) in (("RECEPTION", 0.65), ("EMERGENCY ROOM", 6.75)):
        _wall_item(det, cl.sign_plate(txt, 0.75 if len(txt) > 10 else 0.55, 0.15, size=0.07), x, y0, z + 2.3, "+y")
    det.join(cl.hanging_sign("EXAM ROOMS", 1.2, 0.26), _T(-9.5, (y0 + y1) / 2, CEIL))
    det.join(cl.hanging_sign("EXIT", 0.6, 0.2, bg="sign_green", fg="sign_white"), _T(-12.5, (y0 + y1) / 2, CEIL))
    _wall_item(det, cl.extinguisher(), 2.0, y1, z, "-y")
    put(inter, cl.stretcher(int(r.integers(1e6))), 8.2, y1 - 0.45, "-x")
    put(det, cl.wheelchair(int(r.integers(1e6))), -2.0, y0 + 0.45, "-x")
    _wall_item(det, cl.exit_sign(), x0, -2.95, z + 2.35, "+x")
    # consultorios
    for (nm, sx) in (("consultorio1", 1), ("consultorio2", -1)):
        x0, x1, y0, y1, _ = R[nm]
        xm = (x0 + x1) / 2
        put(inter, cl.exam_table(int(r.integers(1e6))), x0 + 0.45 if sx > 0 else x1 - 0.45, (y0 + y1) / 2 + 0.6, "+x" if sx > 0 else "-x")
        put(inter, cl.desk(1.2, 0.6, seed=int(r.integers(1e6))), xm, y0 + 0.5, "+y")
        put(inter, cl.office_chair(int(r.integers(1e6))), xm + 0.1, y0 + 1.15, "-y")
        put(inter, cl.folding_chair(int(r.integers(1e6))), xm - 0.6, y0 + 1.25, "-y")
        _wall_item(det, cl.sink(), x1 if sx > 0 else x0, y1 - 0.6, z, "-x" if sx > 0 else "+x")
        put(det, cl.trash_bin(), x1 - 0.3 if sx > 0 else x0 + 0.3, y1 - 1.3)
        put(det, cl.iv_stand(int(r.integers(1e6)), bag=False), x0 + 0.4 if sx > 0 else x1 - 0.4, y1 - 0.4)
        _wall_item(det, cl.poster("WASH YOUR HANDS"), xm, y1, z + 1.35, "-y")
        cl.curtain_track(det, [(x0 + 1.4 if sx > 0 else x1 - 1.4, y1), (x0 + 1.4 if sx > 0 else x1 - 1.4, y0 + 1.6)], CEIL, z + 0.3, r,
                         open_runs=(0,))
    # galería: banca de espera y planta junto a las ventanas del patio
    x0, x1, y0, y1, _ = R["galeria"]
    put(inter, cl.chair_row(3, seed=int(r.integers(1e6))), x0 + 0.45, 1.2, "+x")
    put(det, cl.potted_plant(int(r.integers(1e6))), x1 - 0.35, y1 - 0.4)
    # farmacia: anaqueles con medicamento, mostrador en la ventanilla, refrigerador de vacunas, escritorio
    x0, x1, y0, y1, _ = R["farmacia"]
    for x in (x0 + 0.6, x0 + 1.7, x0 + 2.8):
        put(inter, cl.shelving(1.0, 0.4, 2.0, 5, seed=int(r.integers(1e6))), x, y1 - 0.25, "-y")
    put(inter, cl.shelving(1.0, 0.4, 2.0, 5, seed=int(r.integers(1e6))), x1 - 0.25, 1.0, "-x")
    put(inter, cl.counter(1.8, 0.6, seed=int(r.integers(1e6))), 7.3, y0 + 0.35, "-y")
    put(inter, cl.fridge(int(r.integers(1e6))), x1 - 0.4, -0.9, "-x")
    put(inter, cl.office_chair(int(r.integers(1e6))), 7.3, y0 + 1.0, "-y")
    _wall_item(det, cl.split_indoor(), x1, 2.5, z + 2.35, "-x")
    # rayos X
    x0, x1, y0, y1, _ = R["rayosx"]
    put(inter, cl.xray_unit(int(r.integers(1e6))), (x0 + x1) / 2 + 0.3, (y0 + y1) / 2, "-x")
    _wall_item(det, cl.wall_bucky(), x1, (y0 + y1) / 2 + 1.3, z, "-x", solid=True)
    put(inter, cl.lead_screen(), x0 + 1.0, y0 + 0.9, "+x")
    put(inter, cl.desk(1.0, 0.55, seed=int(r.integers(1e6))), x0 + 0.5, y0 + 0.45, "+x")
    _wall_item(det, cl.sign_plate("CAUTION X-RAY", 0.6, 0.18, bg="paint_yellow", fg="cable", size=0.06), x0 + 1.95, y0, z + 1.6, "+y")
    # pasillo norte
    x0, x1, y0, y1, _ = R["pasillo_n"]
    for (txt, x) in (("NURSES", -0.75), ("RESTROOM", 0.9), ("RESTROOM", 3.0), ("KITCHEN", 5.45), ("LAUNDRY", 10.45)):
        _wall_item(det, cl.sign_plate(txt, 0.55, 0.15, size=0.07), x, y1, z + 2.25, "-y")
    _wall_item(det, cl.sign_plate("WARD", 0.5, 0.15, size=0.08), x0, 5.0, z + 2.3, "+x")
    put(inter, cl.chair_row(3, seed=int(r.integers(1e6))), 7.0, y0 + 0.45, "+y")
    _wall_item(det, cl.exit_sign(), x1, 5.0, z + 2.35, "-x")
    put(det, cl.mop_bucket(int(r.integers(1e6))), 12.9, y1 - 0.4)
    # encamados: 4 camas con buró, portasueros y cortinas
    x0, x1, y0, y1, _ = R["encamados"]
    for k, x in enumerate((-12.6, -10.35, -8.1, -5.85)):
        put(inter, cl.hospital_bed(int(r.integers(0, 6)), rails_up=k % 2 == 0, fowler=(32.0 if k == 2 else 0.0), blanket=k != 3),
            x, y1 - 1.15, "-y")                                   # cabecera contra el muro del fondo
        put(inter, cl.bedside_cabinet(int(r.integers(1e6))), x + 0.8, y1 - 0.35, "-y")
        put(det, cl.iv_stand(int(r.integers(1e6)), bag=(k % 2 == 1)), x - 0.75, y1 - 0.45)
        if k < 3:
            cl.curtain_track(det, [(x + 1.12, y1), (x + 1.12, y1 - 2.4)], CEIL, z + 0.3, r, open_runs=(0,) if k == 1 else ())
    put(det, cl.wheelchair(int(r.integers(1e6))), -12.8, y0 + 0.8, "+y")
    _wall_item(det, cl.split_indoor(), x0, 7.0, z + 2.35, "+x")
    _wall_item(det, cl.clock(), -9.2, y0, z + 2.25, "+y")
    _wall_item(det, cl.sanitizer(), x1, 7.2, z + 1.2, "-x")
    # enfermería: mostrador al pasillo, escritorio, archivero, anaquel, lavabo, tablero
    x0, x1, y0, y1, _ = R["enfermeria"]
    put(inter, cl.counter(2.7, 0.55, h=1.05, seed=int(r.integers(1e6))), -2.95, y0 + 0.3, "-y")
    put(inter, cl.desk(1.4, 0.65, seed=int(r.integers(1e6))), -2.8, y1 - 0.4, "-y")
    put(inter, cl.office_chair(int(r.integers(1e6))), -2.9, y1 - 1.1, "+y")
    put(inter, cl.office_chair(int(r.integers(1e6))), -3.9, y0 + 0.9, "-y")
    put(inter, cl.filing_cabinet(int(r.integers(1e6))), x0 + 0.35, y1 - 0.35, "+x")
    put(inter, cl.shelving(0.9, 0.35, 1.8, 4, seed=int(r.integers(1e6))), x0 + 0.25, 7.3, "+x")
    _wall_item(det, cl.sink(), x1, 7.2, z, "-x")
    _wall_item(det, cl.notice_board(0.9, 0.6, seed=int(r.integers(1e6))), -1.0, y1, z + 1.3, "-y")
    _wall_item(det, cl.split_indoor(), -3.6, y1, z + 2.35, "-y")
    # baños
    for nm in ("bano1", "bano2"):
        x0, x1, y0, y1, _ = R[nm]
        put(inter, cl.toilet(int(r.integers(1e6))), (x0 + x1) / 2, y1 - 0.36, "-y")
        _wall_item(det, cl.sink(), x0, y0 + 1.4, z, "+x")
        put(det, cl.trash_bin(), x1 - 0.25, y1 - 0.3)
        _wall_item(det, cl.sanitizer(), x0, y0 + 0.9, z + 1.2, "+x")
        det.join(cl.fluorescent(0.6, 0.3), _T((x0 + x1) / 2, (y0 + y1) / 2, CEIL))
        LIGHTS.append([round((x0 + x1) / 2, 3), round((y0 + y1) / 2, 3), round(CEIL - 0.085, 3)])
    # cocina del personal
    x0, x1, y0, y1, _ = R["cocina"]
    put(inter, cl.counter(2.4, 0.6, h=0.9, seed=int(r.integers(1e6)), top="steel", front="plastic"), 6.3, y1 - 0.3, "-y")
    put(inter, cl.stove(int(r.integers(1e6))), x1 - 0.45, y1 - 0.32, "-y")
    put(inter, cl.fridge(int(r.integers(1e6))), x0 + 0.38, y1 - 0.4, "-y")
    put(inter, cl.kitchen_table(1.6, 0.9, 0.75, seed=int(r.integers(1e6))), 6.4, 7.55)
    for (x, y, d) in ((6.0, 6.75, "+y"), (6.8, 6.75, "+y"), (6.0, 8.4, "-y"), (6.8, 8.4, "-y")):
        put(inter, cl.folding_chair(int(r.integers(1e6))), x, y, d)
    # lavandería
    x0, x1, y0, y1, _ = R["lavanderia"]
    for x in (x0 + 0.4, x0 + 1.05):
        put(inter, cl.washer(int(r.integers(1e6))), x, y1 - 0.35, "-y")
    put(inter, cl.shelving(1.2, 0.45, 2.0, 5, seed=int(r.integers(1e6)), stock_kind="linen"), x1 - 0.3, 7.4, "-x")
    put(det, cl.mop_bucket(int(r.integers(1e6))), x0 + 2.2, y0 + 0.5)
    _wall_item(det, cl.exit_sign(), 12.1, y1, z + 2.45, "-y")
    # cochera: banco de trabajo, anaquel, oxígeno de reserva, casilleros, carrete de manguera, conos, llantas, camilla
    zg = G_FL
    gx0, gx1, gy0, gy1 = GX0 + TE, GX1 - TE, GY0 + TE, GY1 - TE
    _place_solid(det, cl.desk(2.0, 0.7, seed=int(r.integers(1e6)), monitor=False), _T(20.4, gy1 - 0.4, zg) @ face_to("-y"))
    _place_solid(det, cl.shelving(1.2, 0.45, 2.0, 5, seed=int(r.integers(1e6))), _T(gx1 - 0.3, -1.0, zg) @ face_to("-x"))
    _place_solid(det, cl.cylinder_rack(3, seed=int(r.integers(1e6))), _T(gx1 - 0.3, -3.3, zg) @ face_to("-x"))
    for k in range(3):
        _place_solid(det, cl.filing_cabinet(int(r.integers(1e6)), n=6), _T(gx0 + 0.35, 0.6 - k * 0.5, zg) @ face_to("+x"))
    _place_solid(det, cl.stretcher(int(r.integers(1e6))), _T(gx0 + 0.6, -5.5, zg) @ face_to("+x"))
    for k in range(3):
        det.join(_cone(), _T(gx1 - 0.4 - k * 0.12, -7.9 + k * 0.05, zg))
    for k in range(3):
        det.join(_tire_flat(), _T(gx1 - 0.6, -6.3, zg + k * 0.2))
    det.join(_hose_reel(), _T(gx0, -2.2, zg + 1.2) @ face_to("+x"))
    det.join(cl.extinguisher(), _T(gx0, -1.0, zg) @ face_to("+x"))
    for (x, y) in ((18.4, -5.0), (22.4, -5.0), (18.4, -1.0), (22.4, -1.0)):
        det.join(cl.fluorescent(), _T(x, y, G_SB) @ _Rz(90))
        LIGHTS.append([x, y, round(G_SB - 0.085, 3)])


def _place_solid(det, piece, M):
    _proxy(piece, M)
    det.join(piece, M)


def _cone():
    mb = cl.MB()
    mb.box((-0.17, -0.17, 0.0), (0.17, 0.17, 0.03), "sign_red", bevel=0.01)
    port.lathe(mb, [(0.0, 0.03), (0.12, 0.03), (0.035, 0.68), (0.0, 0.68)], seg=20, mat="sign_red")
    for (z0, z1) in ((0.3, 0.38), (0.48, 0.55)):
        r0 = 0.12 - 0.085 * (z0 - 0.03) / 0.65
        r1 = 0.12 - 0.085 * (z1 - 0.03) / 0.65
        port.lathe(mb, [(r0 + 0.002, z0), (r1 + 0.002, z1)], seg=20, mat="sign_white", caps=False)
    return mb


def _tire_flat():
    mb = cl.MB()
    cl._tire(mb, Matrix(), 0.27, 0.1, n=48, m=12, tread=True)
    mb.transform(_T(0, 0, 0.1))
    return mb


def _hose_reel():
    mb = cl.MB()
    mb.box((-0.2, -0.04, -0.2), (0.2, 0.0, 0.2), "paint_green", bevel=0.01)
    for x in (-0.12, 0.12):
        port.lathe(mb, [(0.0, -0.005), (0.22, -0.005), (0.22, 0.005), (0.0, 0.005)], seg=24, mat="sign_red",
                   M=_T(x, -0.18, 0.0) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    for k in range(8):
        port.lathe(mb, [(0.12 + 0.012 * k, -0.11), (0.13 + 0.012 * k, -0.11), (0.13 + 0.012 * k, 0.11), (0.12 + 0.012 * k, 0.11)], seg=24,
                   mat="rubber", M=_T(0, -0.18, 0.0) @ Matrix.Rotation(math.pi / 2, 4, "Y"), caps=False)
    mb.tube([(0.1, -0.3, -0.2), (0.15, -0.35, -0.6), (0.3, -0.5, -1.05)], 0.012, seg=8, mat="rubber")
    return mb


def courtyard(inter, det, r):
    """Patio: jardinera de block con palmera, bancas de concreto, macetas."""
    cx, cy = 0.5, 1.1
    port.lathe(inter, [(0.0, 0.0), (0.75, 0.0), (0.75, 0.45), (0.62, 0.45), (0.62, 0.4), (0.0, 0.4)], seg=32, mat="concrete",
               M=_T(cx, cy, FFL - 0.1))
    _palm(det, cx, cy, FFL + 0.3, r)
    for (x, y, rot) in ((-1.9, 2.8, 0), (2.9, -0.6, 90)):
        inter.box((x - 0.8, y - 0.2, FFL - 0.1 + 0.38), (x + 0.8, y + 0.2, FFL - 0.1 + 0.45), "concrete", bevel=0.01,
                  m=_T(x, y, 0) @ _Rz(rot) @ _T(-x, -y, 0))
        for dx in (-0.6, 0.6):
            inter.box((x + dx - 0.1, y - 0.17, FFL - 0.1), (x + dx + 0.1, y + 0.17, FFL - 0.1 + 0.38), "concrete", bevel=0.01,
                      m=_T(x, y, 0) @ _Rz(rot) @ _T(-x, -y, 0))
    for (x, y) in ((-2.5, -1.3), (3.5, 3.5), (-2.5, 3.5)):
        det.join(cl.potted_plant(int(r.integers(1e6)), h=1.1), _T(x, y, FFL - 0.1))


def _palm(det, x, y, z, r):
    """Palmera joven (cocotera): tronco curvo con cicatrices anulares y bota de vainas arriba; 12 frondas pinnadas con raquis
    arqueado y caído, 30 pares de folíolos largos y angostos con pliegue en V que cuelgan; 3 frondas secas colgando."""
    H = 3.4
    lean = Vector((float(r.uniform(-0.3, 0.3)), float(r.uniform(-0.3, 0.3)), 0))
    pts, radii = [], []
    for i in range(41):
        t = i / 40
        pts.append(tuple(Vector((x, y, z + H * t)) + lean * (t * t)))
        radii.append(0.135 - 0.045 * t + (0.009 if i % 2 == 0 else -0.002))
    det.tube(pts, 0.12, seg=16, mat="wood_grey", radii=radii)
    top = Vector(pts[-1])
    port.lathe(det, [(0.0, -0.15), (0.11, -0.15), (0.13, 0.0), (0.1, 0.18), (0.05, 0.28), (0.0, 0.3)], seg=14, mat="wood_varnish",
               M=Matrix.Translation(top))
    for k in range(15):
        a = 2 * math.pi * k / 15 + float(r.uniform(-0.15, 0.15))
        dead = k < 3
        el = float(r.uniform(-55, -35)) if dead else float(r.uniform(5, 50))
        L = float(r.uniform(1.6, 2.1)) * (0.8 if dead else 1.0)
        d = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-d.y, d.x, 0))
        n = 30
        prev = top + Vector((0, 0, 0.12))
        mat_r = "wood_grey" if dead else "vegetation"
        for j in range(1, n + 1):
            t = j / n
            droop = 1.1 * L * t * t * (0.35 if dead else 0.55)
            p = top + Vector((0, 0, 0.12)) + d * (L * t * math.cos(math.radians(el))) + \
                Vector((0, 0, L * t * math.sin(math.radians(el)) - droop))
            det.cyl(tuple(prev), tuple(p), 0.014 * (1 - 0.75 * t) + 0.002, seg=5, mat=mat_r)
            if j > 2:
                tang = (p - prev).normalized()
                for sgn in (-1, 1):
                    lf = (0.55 * math.sin(math.pi * min(1.0, (t - 0.05) / 0.95)) + 0.06) * (0.7 if dead else 1.0)
                    sp = (side * sgn * math.cos(math.radians(28)) + Vector((0, 0, -math.sin(math.radians(28))))).normalized()
                    tip = p + sp * lf + tang * lf * 0.25 + Vector((0, 0, -0.18 * lf))
                    midp = p.lerp(tip, 0.5) + Vector((0, 0, -0.04 * lf))
                    w = 0.022 * (1 - 0.4 * t)
                    up = Vector((0, 0, 1)) * w
                    base0, base1 = p - tang * w, p + tang * w
                    v = [det.bm.verts.new(c) for c in (base0, midp + up * 0.6, tip, midp - up * 0.6 + tang * 0.0, base1)]
                    det.face([v[0], v[1], v[2]], mat_r)
                    det.face([v[0], v[2], v[3]], mat_r)
                    det.face([v[4], v[1], v[0]], mat_r)
            prev = p


def backyard(inter, det, r):
    """Patio de servicio atrás: firme, jaula de cilindros de gas, botes, tendedero."""
    inter.box((-13.5, Y1, 0.0), (-2.0, Y1 + 2.6, 0.08), "concrete")
    gx, gy = -11.0, Y1 + 1.7
    det.join(cl.cylinder_rack(3, seed=int(r.integers(1e6)), medical=False), _T(gx, gy, 0.08))
    for (a, b) in (((gx - 0.6, gy - 0.35), (gx + 0.6, gy - 0.35)), ((gx + 0.6, gy - 0.35), (gx + 0.6, gy + 0.35)),
                   ((gx + 0.6, gy + 0.35), (gx - 0.6, gy + 0.35)), ((gx - 0.6, gy + 0.35), (gx - 0.6, gy - 0.35))):
        for z in (0.1, 0.9, 1.75):
            det.cyl((a[0], a[1], z), (b[0], b[1], z), 0.012, seg=6, mat="paint_green")
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = int(L / 0.1)
        for i in range(n + 1):
            p = (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
            det.cyl((p[0], p[1], 0.1), (p[0], p[1], 1.75), 0.003, seg=4, mat="paint_green")
    for k, x in enumerate((-8.6, -7.8)):
        det.box((x - 0.33, gy - 0.35, 0.08), (x + 0.33, gy + 0.35, 1.05), "sign_green" if k == 0 else "cable", bevel=0.03)
        det.box((x - 0.35, gy - 0.37, 1.05), (x + 0.35, gy + 0.37, 1.1), "sign_green" if k == 0 else "cable", bevel=0.02)
        for sx in (-1, 1):
            det.cyl((x + sx * 0.28, gy + 0.36, 0.1), (x + sx * 0.28, gy + 0.44, 0.1), 0.1, seg=16, mat="rubber")
    det.join(sv.laundry_line(5.5, seed=int(r.integers(1e6)), detail="mid"), _T(-7.0, Y1 + 1.2, 1.75))
    for x in (-7.0, -1.5):
        det.cyl((x, Y1 + 1.2, 0.08), (x, Y1 + 1.2, 1.8), 0.03, seg=8, mat="paint_green")


# ------------------------------------------------------------------------------------------------------------ ensamblado
def build_hos(bid="HOS_1_pueblo", collection_root=None, dress=True):
    cfg = cfg_hos(bid)
    cid = cfg["id"]
    GAPS.clear()
    DOORS.clear()
    LIGHTS.clear()
    PROXIES.clear()
    root = collection_root or get_collection(cid)
    cols = {k: get_collection(f"{cid}_{k}", root) for k in ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage", "Furniture")}
    out = {k: [] for k in cols}
    shell, det, inter, roof = MB(), MB(), MB(), MB()
    furn = MB()          # mobiliario, equipo y luminarias interiores: malla aparte del kit (SM_<ID>_Mobiliario)
    r = rng(cfg["seed"])
    build_slabs(inter, roof)
    Ms, ops = main_walls(shell)
    Mc, ops_c = courtyard_walls(shell)
    Mg, ops_g = garage_walls(shell)
    partitions(inter)
    # puertas exteriores y del patio
    door_in(Ms["front"], -8.9 - X0, 1.8, h=2.4, kind="double_glazed", depth=TE, z0=FFL, ang=0.0)
    door_in(Ms["east"], -8.2 - (Y0 + TE), 1.6, h=2.4, kind="double_glazed", depth=TE, z0=FFL, ang=30.0)
    door_in(Ms["west"], (Y1 - TE) + 2.4, 1.1, h=2.1, kind="metal", depth=TE, z0=FFL, ang=0.0)
    door_in(Ms["back"], X1 - 12.6, 1.0, h=2.1, kind="metal", depth=TE, z0=FFL, ang=0.0)
    door_in(Mc["s"], (CXE + TE / 2) - 1.0, 1.0, h=2.1, kind="double_glazed", depth=TE, z0=FFL - 0.1, ang=0.0)
    door_in(Mg["west"], (GY1 - TE) + 3.5, 0.9, h=2.1, kind="metal", depth=TE, z0=G_FL, ang=15.0)
    GAPS.extend([("x", Y0, -8.9, -7.1), ("y", X1, -8.2, -6.6), ("y", X0, -3.5, -2.4), ("x", Y1, 11.6, 12.6), ("x", CYS, 0.0, 1.0)])
    place_windows(det, Ms["front"], ops["front"], r)
    place_windows(det, Ms["back"], ops["back"], r)
    place_windows(det, Ms["west"], ops["west"], r)
    place_windows(det, Ms["east"], ops["east"], r)
    for k in ("n", "s", "w", "e"):
        place_windows(det, Mc[k], ops_c[k], r, grille=False)
    place_windows(det, Mg["back"], ops_g["back"], r)
    place_windows(det, Mg["east"], ops_g["east"], r)
    for k, (u0, u1, v0, v1) in enumerate(ops_g["front"]):
        sh = op.rolling_shutter(u1 - u0, v1 - v0, seed=int(r.integers(1e6)), dent=0.08, open_frac=(0.96 if k == 0 else 0.22))
        cl.remap(sh, {"metal_rust": "steel", "metal_paint": "steel"})               # lámina galvanizada mantenida
        det.join(sh, Mg["front"] @ _T(u0, 0, v0))
    place_doors(det, r)
    for nm in ROOMS:
        wainscot(inter, nm)
        if not nm.startswith("bano"):
            lights(furn, nm)
    cornice(shell, X0, X1, Y0, Y1, SLAB_T - 0.05)
    cornice(shell, GX0, GX1, GY0, GY1, G_ST - 0.05)
    site(shell, inter, det, roof, r)
    rooftop(roof, det, r)
    signage(det, Ms, r)
    if dress:
        furnish(inter, furn, r)
        courtyard(inter, det, r)
        backyard(inter, det, r)
    for nm, mb in (("Shell", shell), ("Details", det), ("Interior", inter), ("Roof", roof), ("Furniture", furn)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = dict(interior_dress=dict(bulb_pos=list(LIGHTS)), doors=len(DOORS), rooms=len(ROOMS), proxies=list(PROXIES))
    out["cfg"] = cfg
    return out

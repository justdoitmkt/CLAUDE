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
from kit import clinic_equipo as ce
from kit import clinic_servicios as cs
from kit import openings as op
from kit import port
from kit import services as sv
from kit.common import MB, get_collection, rng, wall_with_openings

PI = math.pi
_Rx, _Ry = cl._Rx, cl._Ry

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
RAMP_W = (-16.9, -11.0)            # rampa del pórtico (x): 0,35 m en 5,90 m = 5,9 % (NOM-030: <= 6 %, tramo <= 6,00 m)
RAMP_WY = (-11.95, -10.75)         # ancho de la rampa del pórtico (y): 1,20 m libres, al norte de la columna de la esquina
ER_RAMP = (-12.45, -6.6)           # rampa del pasillo cubierto (y): 5,85 m = 5,98 %; descanso inferior de 2,05 m
ER_DOOR = (-6.0, -4.4)             # puerta de urgencias (muro oriente), sobre el descanso de y -6,6 a -4,0
ER_STEPS = (-4.0, -3.1)            # 3 escalones del descanso al firme de la puerta lateral de la cochera
G_SIDE_DOOR = (-2.6, -1.7)         # puerta lateral de la cochera (muro poniente)


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
                  "concrete", bevel=0.008, seg=2, m=M)                                  # remate colado con aristas boleadas
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
    east = [(ea(ER_DOOR[0]), ea(ER_DOOR[1]), FFL, FFL + 2.4)]
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
    west = [(a1s - G_SIDE_DOOR[1], a1s - G_SIDE_DOOR[0], G_FL, G_FL + 2.1)]  # puerta lateral al pasillo cubierto
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
            det.join(cl.door_panel(leaf, h, depth=depth, seed=int(r.integers(1e6)), ang=ang, jambs=(True, False)), M)
            det.join(cl.door_panel(leaf, h, depth=depth, seed=int(r.integers(1e6)), ang=ang * 0.15, jambs=(True, False)),
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
    shell.box((x0 - proud, y0 - proud, z), (x1 + proud, y0, z + h), "plaster", bevel=0.008, seg=2)
    shell.box((x0 - proud, y1, z), (x1 + proud, y1 + proud, z + h), "plaster", bevel=0.008, seg=2)
    shell.box((x0 - proud, y0, z), (x0, y1, z + h), "plaster", bevel=0.008, seg=2)
    shell.box((x1, y0, z), (x1 + proud, y1, z + h), "plaster", bevel=0.008, seg=2)


def site(shell, inter, det, roof, r):
    """Banqueta, pórtico, escalones, rampas (NOM-030), pasillo cubierto de urgencias con su marquesina, descansos de las
    puertas de servicio, plataforma de la cochera, barda y portón."""
    xw0 = RAMP_W[0] - 1.6                                               # descanso inferior de la rampa del pórtico (1,6 m)
    # banquetas (piso propio del modelo, no terreno)
    inter.box((xw0, -14.5, 0.0), (X1, Y0, PAVE), "concrete")
    inter.box((GX0, -14.5, 0.0), (SIDE_WALL_XE, Y0, PAVE), "concrete")
    inter.box((GX0, Y0, 0.0), (SIDE_WALL_XE, GY0, PAVE), "concrete")
    for x in np.arange(xw0 + 1.5, SIDE_WALL_XE, 1.5):                   # juntas de la banqueta
        if not (X1 - 0.05 < x < GX0 + 0.05):
            det.box((x - 0.006, -14.49, PAVE - 0.004), (x + 0.006, Y0 - 0.01, PAVE + 0.0005), "mortar")
    # pórtico: losa de terrazo, escalones colados con nariz pintada, columnas con zoclo y capitel, trabe y losa
    px0, px1, py0 = -11.0, -5.0, -12.4
    inter.box((px0, py0, PAVE), (px1, Y0, FFL), "terrazzo", bevel=0.01, seg=3)
    _stair(inter, _T(-10.2, -13.3, PAVE), 4.4, 3, 0.3, (FFL - PAVE) / 3)
    for x in (-10.85, -9.15, -6.85, -5.15):
        shell.box((x - 0.15, -12.4, FFL), (x + 0.15, -12.1, 3.02), "plaster", bevel=0.012, seg=3)
        det.box((x - 0.16, -12.41, FFL), (x + 0.16, -12.09, FFL + 0.15), "paint_green", bevel=0.006, seg=2)
        det.box((x - 0.17, -12.42, 2.93), (x + 0.17, -12.08, 3.0), "plaster", bevel=0.008, seg=2)
    shell.box((-11.1, -12.55, 3.0), (-4.9, -12.1, 3.45), "plaster", bevel=0.012, seg=3)
    shell.box((-11.1, -12.1, 3.25), (-4.9, Y0, 3.45), "plaster", bevel=0.012, seg=3)
    roof.box((-11.08, -12.53, 3.45), (-4.92, Y0, 3.47), "concrete", bevel=0.005, seg=2)
    # rampa accesible al poniente del pórtico (5,9 %, 5,90 m, ancho libre 1,26 m), guarniciones, estrías, pasamanos dobles
    xb, xt = RAMP_W

    def zs_w(x):
        return PAVE + (FFL - PAVE) * (x - xb) / (xt - xb)
    ya, yb = RAMP_WY
    wedge(inter, xb, xt, ya, yb, PAVE, FFL, axis="x")
    for c in (ya - 0.05, yb + 0.05):
        _curb(inter, xb, xt, c, 0.10, zs_w, axis="x")
    _grip_strips(det, xb + 0.2, xt - 0.1, ya + 0.01, yb - 0.01, zs_w, axis="x")
    for c in (ya - 0.05, yb + 0.05):
        _ramp_rail(det, (xb, c, zs_w(xb)), (xt, c, zs_w(xt)))
    # pasillo cubierto de urgencias: descanso inferior, rampa (5,98 %, 5,85 m), descanso de la puerta, escalones a la cochera
    y0r, y1r = ER_RAMP

    def zs_e(y):
        return PAVE + (FFL - PAVE) * (y - y0r) / (y1r - y0r)
    inter.box((X1, -14.5, 0.0), (GX0, y0r, PAVE), "concrete")
    wedge(inter, X1, GX0, y0r, y1r, PAVE, FFL, axis="y")
    inter.box((X1, y1r, 0.0), (GX0, ER_STEPS[0], FFL), "concrete")
    rise = (FFL - PAVE) / 3
    _stair(inter, _T(GX0, ER_STEPS[1], PAVE) @ _Rz(180), GX0 - X1, 3, 0.3, rise)
    inter.box((X1, ER_STEPS[1], 0.0), (GX0, GY1, PAVE), "concrete")
    for c in (X1 + 0.06, GX0 - 0.06):
        _curb(inter, y0r, y1r, c, 0.12, zs_e, axis="y")
    _grip_strips(det, y0r + 0.2, y1r - 0.1, X1 + 0.13, GX0 - 0.13, zs_e, axis="y")
    for c in (X1 + 0.07, GX0 - 0.07):
        _ramp_rail(det, (c, y0r, zs_e(y0r)), (c, y1r, zs_e(y1r)), base_dz=0.10)
        _ramp_rail(det, (c, ER_STEPS[1], PAVE + rise), (c, ER_STEPS[1] - 0.6, FFL), posts=[(0.25, PAVE + rise), (1.0833, FFL)])
    _canopy(det, r)
    # descansos con escalones de la salida de emergencia (poniente) y de la puerta de servicio (fondo)
    _stoop(inter, det, _T(X0, -2.95, 0.0) @ _Rz(90), 1.7, 1.3)
    _stoop(inter, det, _T(12.1, Y1, 0.0), 1.8, 1.3)
    # barda perimetral de block con castillos y remate; portón de servicio
    walls = [((SIDE_WALL_XW, BACK_WALL_Y), (SIDE_WALL_XE, BACK_WALL_Y)), ((SIDE_WALL_XW, -10.0), (SIDE_WALL_XW, BACK_WALL_Y)),
             ((SIDE_WALL_XE, GY0), (SIDE_WALL_XE, BACK_WALL_Y))]
    gate = (3.0, 7.0)
    for (a, b) in walls:
        ax = "x" if a[1] == b[1] else "y"
        L = abs((b[0] - a[0]) if ax == "x" else (b[1] - a[1]))
        pos = 0.0
        while pos < L - 1e-6:
            seg = min(3.0, L - pos)
            p0 = pos
            p1 = pos + seg
            if ax == "x":
                xa, xb_ = a[0] + p0, a[0] + p1
                for (g0, g1) in ((-99, gate[0]), (gate[1], 99)):
                    s0, s1 = max(xa, g0), min(xb_, g1)
                    if s1 - s0 > 0.01:
                        shell.box((s0, a[1] - 0.075, 0.0), (s1, a[1] + 0.075, 1.8), "concrete", bevel=0.006, seg=2)
                        shell.box((s0, a[1] - 0.1, 1.8), (s1, a[1] + 0.1, 1.88), "concrete", bevel=0.012, seg=3)
                if not (gate[0] - 0.2 < xa < gate[1] + 0.2):
                    shell.box((xa - 0.1, a[1] - 0.1, 0.0), (xa + 0.1, a[1] + 0.1, 1.8), "concrete", bevel=0.012, seg=3)   # castillo bajo el remate
            else:
                ya, yb = a[1] + p0, a[1] + p1
                shell.box((a[0] - 0.075, ya, 0.0), (a[0] + 0.075, yb, 1.8), "concrete", bevel=0.006, seg=2)
                shell.box((a[0] - 0.1, ya, 1.8), (a[0] + 0.1, yb, 1.88), "concrete", bevel=0.012, seg=3)
                shell.box((a[0] - 0.1, ya - 0.1, 0.0), (a[0] + 0.1, ya + 0.1, 1.8), "concrete", bevel=0.012, seg=3)
            pos += seg
    for x in gate:
        shell.box((x - 0.15, BACK_WALL_Y - 0.15, 0.0), (x + 0.15, BACK_WALL_Y + 0.15, 2.1), "concrete", bevel=0.012, seg=3)
    _gate(det, gate[0] + 0.15, gate[1] - 0.15, BACK_WALL_Y, r)


def _canopy(det, r):
    """Marquesina del pasillo cubierto: largueros de canal de 6" con el alma atornillada a los muros (taquetes cada 0,8 m),
    postes de PTR 4" con placa base, capitel y 4 anclas al frente, fascia de canal, largueros de PTR 2 × 3" encima, lámina
    ondulada, tapajuntas de ángulo contra los muros, canalón media caña con ganchos, bajada pluvial de 3" con codos y
    abrazaderas al poste y letrero EMERGENCY colgado de la fascia con varillas."""
    zt_back, zt_front = 3.48, 3.22
    yf = -14.70

    def zf(y):
        return zt_front + (zt_back - zt_front) * (y - yf) / (GY1 - yf)

    def beam_top(y):
        return zf(y) - 0.088
    hb, tw, bf, tf = 0.152, 0.005, 0.048, 0.0087
    for (xw, sg, ywall) in ((X1 + 0.001, 1, Y0), (GX0 - 0.001, -1, GY0)):
        ya, yb = -14.615, GY1 - 0.02
        p0 = (xw, ya, beam_top(ya) - hb / 2)
        p1 = (xw, yb, beam_top(yb) - hb / 2)
        fl = tuple(sorted((-sg * bf, 0.0)))
        wb = tuple(sorted((-sg * tw, 0.0)))
        port.member(det, p0, p1, [(fl[0], fl[1], -hb / 2, -hb / 2 + tf), (fl[0], fl[1], hb / 2 - tf, hb / 2), (wb[0], wb[1], -hb / 2, hb / 2)],
                    "paint_green", up=(0, 0, 1))
        y = ywall + 0.4
        while y < GY1 - 0.2:
            zc = beam_top(y) - hb / 2
            for dz in (-0.035, 0.035):
                ce.hexnut(det, _T(xw + sg * tw, y, zc + dz) @ Matrix.Rotation(sg * PI / 2, 4, "Y"), d=0.012, mat="steel")
            y += 0.8
        # tapajuntas de ángulo contra el muro, sobre la lámina
        ce.angle_l(det, (xw - sg * 0.0005, ywall, zf(ywall) + 0.013), (xw - sg * 0.0005, GY1, zf(GY1) + 0.013), 0.08, 0.0012,
                   up=(0, 0, 1), s=sg, mat="galvanized")
    # fascia al frente (canal de 3" de pie sobre los largueros)
    yh = -14.658 + tw
    hc = 0.076
    port.member(det, (X1 + bf, yh, beam_top(-14.64) + hc / 2), (GX0 - bf, yh, beam_top(-14.64) + hc / 2),
                [(-tw, 0.0, -hc / 2, hc / 2), (-tw, 0.04, -hc / 2, -hc / 2 + 0.006), (-tw, 0.04, hc / 2 - 0.006, hc / 2)], "paint_green",
                up=(0, 0, 1))
    # postes al frente
    for x in (X1 + 0.06, GX0 - 0.06):
        zt = beam_top(-14.45) - hb
        cl.rtube(det, (x, -14.45, PAVE + 0.012), (x, -14.45, zt - 0.008), 0.1, 0.1, "paint_green", up=(1, 0, 0), r=0.008)
        cs.slab(det, _T(x, -14.45, zt - 0.008), 0.14, 0.14, 0.008, rc=0.01, re=0.0015, mat="paint_green", nc=2, ne=1)
        cs.slab(det, _T(x, -14.45, PAVE), 0.24, 0.24, 0.012, rc=0.015, re=0.002, mat="steel", nc=3, ne=1)
        for (dx, dy) in ((-0.09, -0.09), (0.09, -0.09), (-0.09, 0.09), (0.09, 0.09)):
            ce.hexnut(det, _T(x + dx, -14.45 + dy, PAVE + 0.012), d=0.014, mat="steel")
    # largueros sobre las vigas y lámina ondulada
    y = -14.4
    while y < GY1:
        cl.rtube(det, (X1 + 0.004, y, beam_top(y) + 0.038), (GX0 - 0.004, y, beam_top(y) + 0.038), 0.05, 0.076, "paint_green",
                 up=(0, 0, 1), r=0.004)
        y += 1.3
    _corrugated(det, X1 - 0.05, GX0 + 0.05, yf, GY1 + 0.02, zf, mat="roof_metal_light")
    # canalón, ganchos y bajada pluvial
    yg, zg = -14.66, zf(-14.66) - 0.02
    _gutter(det, X1 + 0.03, GX0 - 0.03, yg, zg)
    x = X1 + 0.25
    while x < GX0 - 0.1:
        _hanger(det, x, yg, zg)
        x += 0.6
    xd = GX0 - 0.06 - 0.05 - 0.038
    zb = zg - 0.075
    ce.lathe(det, [(0.03, -0.03), (0.0405, -0.03), (0.0405, 0.006), (0.05, 0.008), (0.05, 0.011), (0.03, 0.011)], seg=24, mat="galvanized",
             M=_T(xd, yg - 0.075, zb))
    path = cl.fillet([(xd, yg - 0.075, zb - 0.02), (xd, yg - 0.075, zb - 0.12), (xd, -14.45, zb - 0.38), (xd, -14.45, PAVE + 0.3),
                      (xd, -14.62, PAVE + 0.08), (xd, -14.86, PAVE + 0.055)], 0.07, nseg=10)
    det.tube(path, 0.038, seg=24, mat="galvanized")
    for z in (0.9, 2.1):
        _pipe_clamp(det, (xd, -14.45, z), (0, 0, 1), (-1, 0, 0), 0.038)
    # letrero EMERGENCY colgado de la fascia
    zs_top = beam_top(-14.64) - 0.12
    det.join(cl.sign_plate("EMERGENCY", 1.9, 0.38, bg="sign_red", fg="sign_white", size=0.22, t=0.04), _T((X1 + GX0) / 2, -14.62, zs_top - 0.38))
    for dx in (-0.8, 0.8):
        xx = (X1 + GX0) / 2 + dx
        det.tube([(xx, -14.64, zs_top - 0.01), (xx, -14.64, beam_top(-14.64) + 0.002)], 0.003, seg=12, mat="steel")
        for zz in (zs_top - 0.002, beam_top(-14.64) - 0.006):
            ce.lathe(det, [(0.0, 0.0), (0.006, 0.0), (0.006, 0.005), (0.0, 0.005)], seg=6, mat="steel", M=_T(xx, -14.64, zz))
    del r


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


# ------------------------------------------------------------------------------------------------------------ piezas exteriores
# Segunda pasada R-AAA (2026-11-19): nada de cajas sueltas ni cilindros facetados en el exterior. Rampas y escalones según
# NOM-030-SSA3-2013 (pendiente <= 6 %, tramo <= 6,00 m, descansos >= 1,50 m, ancho libre >= 1,20 m, pasamanos dobles a 0,90 y
# 0,75 m de Ø 38 mm con prolongación de 0,30 m y remate curvo; guarnición de 10 cm como protección lateral).
def _extrude(mb, stations, mats, M=None, caps=True):
    """Sólido por estaciones [(u, [(v, z), ...])] (mismo número de puntos), u -> X local, v -> Y local; material por tramo del
    perfil (mats str o lista) — escalones con nariz pintada, guarniciones con canto boleado, estrías."""
    k = len(stations[0][1])
    if isinstance(mats, str):
        mats = [mats] * k
    R = []
    for (u, prof) in stations:
        R.append([mb.bm.verts.new((M @ Vector((u, v, z))) if M is not None else Vector((u, v, z))) for (v, z) in prof])
    for i in range(len(R) - 1):
        for j in range(k):
            jj = (j + 1) % k
            mb.face([R[i][j], R[i][jj], R[i + 1][jj], R[i + 1][j]], mats[j])
    if caps:
        mb.face(list(reversed(R[0])), mats[0])
        mb.face(R[-1], mats[0])
    return R


def _stair(mb, M, W, n, run, rise, r=0.012, band=0.05, mat="concrete", nose="paint_yellow"):
    """Escalones colados de una pieza (local: ancho u 0..W, sube hacia +v desde el primer peralte en v = 0, base z = 0): narices
    boleadas de radio r con franja antiderrapante pintada de `band` sobre la huella, la nariz y 3 cm del peralte."""
    pts, mats = [], []

    def add(p, m):
        pts.append(p)
        mats.append(m)
    add((n * run, 0.0), mat)
    add((0.0, 0.0), mat)
    for i in range(n):
        v0, z1 = i * run, (i + 1) * rise
        add((v0, z1 - r - 0.03), nose)
        add((v0, z1 - r), nose)
        for k in range(1, 5):
            a = PI - PI / 2 * k / 5
            add((v0 + r + r * math.cos(a), z1 - r + r * math.sin(a)), nose)
        add((v0 + r, z1), nose)
        add((v0 + band, z1), mat)
        add(((i + 1) * run, z1), mat)
    _extrude(mb, [(0.0, pts), (W, pts)], mats, M=M)


def _curb(mb, s0, s1, c, w, zs, h=0.10, r=0.015, ch=0.008, axis="x", mat="concrete"):
    """Guarnición colada a lo largo de `axis` (s0..s1) centrada en c, ancho w, corona h sobre la superficie zs(s), cantos
    boleados r arriba y chaflán ch en los extremos (desde z = 0)."""
    def prof(s, inset):
        top = zs(s) + h - inset
        hw = w / 2 - inset
        p = [(c - hw, 0.0), (c + hw, 0.0), (c + hw, top - r)]
        for k in range(1, 4):
            a = PI / 2 * k / 4
            p.append((c + hw - r + r * math.cos(a), top - r + r * math.sin(a)))
        p.append((c + hw - r, top))
        p.append((c - hw + r, top))
        for k in range(1, 4):
            a = PI / 2 + PI / 2 * k / 4
            p.append((c - hw + r + r * math.cos(a), top - r + r * math.sin(a)))
        p.append((c - hw, top - r))
        return p
    st = [(s0, prof(s0, ch)), (s0 + ch, prof(s0 + ch, 0.0)), (s1 - ch, prof(s1 - ch, 0.0)), (s1, prof(s1, ch))]
    M = None if axis == "x" else Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    _extrude(mb, st, mat, M=M)


def _grip_strips(mb, s0, s1, a, b, zs, step=0.15, axis="y", mat="concrete"):
    """Estrías antiderrapantes de canto redondo (25 mm × 4 mm) cada `step` sobre una rampa (a..b a lo ancho)."""
    prof0 = [(-0.0125, -0.003), (0.0125, -0.003), (0.0125, 0.0)] + \
            [(0.0125 * math.cos(PI * k / 6), 0.004 * math.sin(PI * k / 6)) for k in range(1, 6)] + [(-0.0125, 0.0)]
    s = s0
    while s < s1 - 0.05:
        z = zs(s)
        prof = [(s + dv, z + dz) for (dv, dz) in prof0]
        if axis == "y":
            M = Matrix(((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
            _extrude(mb, [(a, prof), (b, prof)], mat, M=M)
        else:
            M = Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
            _extrude(mb, [(a, prof), (b, prof)], mat, M=M)
        s += step


def _ramp_rail(mb, pb, pt, ext=0.30, H=(0.90, 0.75), base_dz=0.10, post_step=1.2, mat="paint_green", r=0.019, rp=0.024,
               posts=None):
    """Pasamanos doble de rampa o escalera (NOM-030: 0,90 y 0,75 m, Ø 38 mm) de tubo doblado: un solo lazo con prolongaciones
    horizontales de `ext` en los dos extremos y remates en U que unen los dos pasamanos; postes Ø 48 con placa base, 4 taquetes
    y cordones de soldadura. pb/pt: puntos de la línea de referencia (superficie de la rampa o narices) en el arranque y la
    llegada; posts = [(t, z_apoyo)] (t 0..1 a lo largo, > 1 sobre el descanso) o, por omisión, cada <= post_step sobre la
    guarnición (superficie + base_dz)."""
    pb, pt = Vector(pb), Vector(pt)
    d = pt - pb
    d.z = 0.0
    L = d.length
    d.normalize()
    up = Vector((0.0, 0.0, 1.0))
    hi, lo = H
    rr = (hi - lo) / 2

    def line(h):
        return [pb - d * ext + up * h, pb + up * h, pt + up * h, pt + d * ext + up * h]
    U = [Vector(p) for p in cl.fillet(line(hi), 0.12, nseg=8)]
    Lw = [Vector(p) for p in cl.fillet(line(lo), 0.12, nseg=8)]
    c0, c1 = (Lw[0] + U[0]) / 2, (Lw[-1] + U[-1]) / 2
    bend0 = [c0 - up * rr * math.cos(PI * k / 12) - d * rr * math.sin(PI * k / 12) for k in range(1, 12)]
    bend1 = [c1 + up * rr * math.cos(PI * k / 12) + d * rr * math.sin(PI * k / 12) for k in range(1, 12)]
    mid = len(Lw) // 2
    path = list(reversed(Lw[:mid + 1])) + bend0 + U + bend1 + list(reversed(Lw[mid:]))
    mb.tube([tuple(p) for p in path], r, seg=20, mat=mat)
    if posts is None:
        n = max(1, int(math.ceil(L / post_step)))
        posts = [(k / n, pb.z + (pt.z - pb.z) * k / n + base_dz) for k in range(n + 1)]
    for (t, zb) in posts:
        p = pb + d * (L * t)
        zl = pb.z + (pt.z - pb.z) * min(max(t, 0.0), 1.0)
        top = zl + hi
        mb.cyl((p.x, p.y, zb + 0.008), (p.x, p.y, top), rp, seg=24, mat=mat)
        cs.slab(mb, _T(p.x, p.y, zb), 0.10, 0.10, 0.008, rc=0.012, re=0.0015, mat=mat, nc=3, ne=1)
        for (dx, dy) in ((-0.035, -0.035), (0.035, -0.035), (-0.035, 0.035), (0.035, 0.035)):
            ce.hexnut(mb, _T(p.x + dx, p.y + dy, zb + 0.008), d=0.0075, mat="steel")
        for zz in (zb + 0.008, zl + lo):
            ce.weld(mb, _T(p.x, p.y, zz), rp, w=0.003, seg=24, mat=mat)


def _pipe_clamp(mb, c, a, n, r, w=0.02, t=0.0016, mat="galvanized"):
    """Abrazadera de uña de lámina que sujeta un tubo de radio r (centro c, eje a) contra un muro de normal n (hacia el tubo):
    banda doblada alrededor del tubo, dos patas planas sobre el muro y dos pijas."""
    c, a, n = Vector(c), Vector(a).normalized(), Vector(n).normalized()
    b = a.cross(n).normalized()
    R = r + t / 2
    wall = c - n * (r - t / 2)
    path = [wall + b * (R + 0.026), wall + b * R]
    for k in range(13):
        ph = PI * k / 12
        path.append(c + (b * math.cos(ph) + n * math.sin(ph)) * R)
    path += [wall - b * R, wall - b * (R + 0.026)]
    path = cl.fillet([tuple(p) for p in path[:2]] + [tuple(p) for p in path[2:-2]] + [tuple(p) for p in path[-2:]], 0.003, nseg=3)
    mb.sweep([(-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)], path, mat=mat, normal=tuple(a))
    for sg in (-1, 1):
        q = wall + b * sg * (R + 0.016) + n * (t / 2)
        Mz = Matrix.Translation(q) @ n.to_track_quat("Z", "Y").to_matrix().to_4x4()
        cs.screw(mb, Mz, r=0.0035, seg=12, cross=False)


def _vent_pipe(h=0.6, R=0.055):
    """Tubo de ventilación de PVC sanitario de 110 mm (NMX-E-199: Ø ext. 110 mm, pared de 2,3–2,7 mm) en la azotea: bota de impermeabilizante con faldón, tubo con
    boca de pared real, sombrerete cónico sobre 3 patas de solera."""
    mb = cl.MB()
    ce.lathe(mb, [(0.0, 0.0), (0.17, 0.0), (0.172, 0.002), (0.17, 0.005), (0.14, 0.0085), (0.122, 0.016), (R + 0.016, 0.07), (R + 0.009, 0.1),
                  (R + 0.004, 0.106), (0.0, 0.106)], seg=32, mat="rubber")
    cs.lathe(mb, [(0.0, 0.1), (R, 0.1), (R, h), (R - 0.0006, h + 0.0012), (R - 0.0019, h + 0.0012), (R - 0.0025, h),
                  (R - 0.0025, h - 0.03), (0.0, h - 0.03)], seg=32, mat="plastic")
    zc = h + 0.07
    cs.lathe(mb, [(0.0, zc + 0.052), (0.06, zc + 0.03), (0.088, zc + 0.006), (0.094, zc), (0.096, zc + 0.003),
                  (0.092, zc + 0.01), (0.062, zc + 0.036), (0.0, zc + 0.058)], seg=40, mat="plastic")
    with mb.soft():
        for k in range(3):
            ang = 2 * PI * k / 3
            ca, sa = math.cos(ang), math.sin(ang)
            mb.tube([(R * 0.98 * ca, R * 0.98 * sa, h - 0.05), (R * 1.04 * ca, R * 1.04 * sa, h - 0.04),
                     (R * 1.04 * ca, R * 1.04 * sa, h + 0.03), (0.062 * ca, 0.062 * sa, zc + 0.03)], 0.003, seg=12, mat="plastic")
    return mb


def _scupper(p0, p1, s_wall, R=0.055, t=0.0025):
    """Gárgola de PVC sanitario de 110 mm a través del pretil (de p0 en la azotea a p1 afuera): tubo hueco con boca de pared real y
    chaflán de mortero contra la cara exterior del muro (a la distancia s_wall de p0 a lo largo del tubo)."""
    mb = cl.MB()
    p0, p1 = Vector(p0), Vector(p1)
    L = (p1 - p0).length
    Mz = Matrix.Translation(p0) @ (p1 - p0).normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
    cs.lathe(mb, [(R, 0.0), (R, L), (R - 0.0008, L + 0.0012), (R - t + 0.0008, L + 0.0012), (R - t, L), (R - t, 0.0)], seg=32,
             mat="plastic", M=Mz, closed=True)
    cs.lathe(mb, [(R - 0.002, s_wall - 0.004), (R + 0.03, s_wall - 0.004), (R + 0.026, s_wall + 0.002), (R + 0.004, s_wall + 0.022),
                  (R - 0.002, s_wall + 0.024)], seg=32, mat="mortar", M=Mz, closed=True)
    return mb


def _roof_hatch():
    """Registro de azotea: brocal de concreto boleado, tapa de lámina con faldón, 2 bisagras de libro con nudillos, aldaba con
    candado y jaladera de varilla (origen: losa, centro; bisagras hacia +Y)."""
    mb = cl.MB()
    cs.slab(mb, _T(0, 0, 0), 0.9, 0.9, 0.305, rc=0.03, re=0.012, re0=0.0, mat="concrete", nc=4, ne=3)   # brocal de 12"
    zt = 0.305
    cs.slab(mb, _T(0, 0, zt + 0.004), 1.0, 1.0, 0.03, rc=0.02, re=0.006, mat="paint_green", nc=4, ne=2)
    for (w, d, cx, cy) in ((1.0, 0.003, 0.0, -0.4985), (1.0, 0.003, 0.0, 0.4985), (0.003, 0.994, -0.4985, 0.0), (0.003, 0.994, 0.4985, 0.0)):
        cs.slab(mb, _T(cx, cy, zt - 0.04), w, d, 0.05, rc=0.0012, re=0.001, mat="paint_green", nc=1, ne=1)
    for x in (-0.3, 0.3):
        for k, (a, b) in enumerate(((-0.06, -0.022), (-0.02, 0.02), (0.022, 0.06))):
            ce.lathe(mb, [(0.0, a), (0.009, a), (0.0105, a + 0.002), (0.0105, b - 0.002), (0.009, b), (0.0, b)], seg=24,
                     mat="steel", M=_T(x, 0.505, zt + 0.012) @ _Ry(90))
        cs.slab(mb, _T(x, 0.47, zt + 0.034), 0.12, 0.07, 0.003, rc=0.006, re=0.001, mat="steel", nc=2, ne=1)
        cs.slab(mb, _T(x, 0.505, zt - 0.02) @ _Rx(90), 0.12, 0.05, 0.003, rc=0.006, re=0.001, mat="steel", nc=2, ne=1)
    # aldaba y candado al frente
    cs.slab(mb, _T(0.0, -0.5, zt - 0.06) @ _Rx(90), 0.05, 0.07, 0.004, rc=0.008, re=0.0012, mat="steel", nc=2, ne=1)
    cs.slab(mb, _T(0.0, -0.47, zt + 0.034), 0.04, 0.09, 0.003, rc=0.008, re=0.001, mat="steel", nc=2, ne=1)
    _padlock(mb, _T(0.0, -0.512, zt - 0.075))
    mb.tube(cl.fillet([(-0.12, -0.38, zt + 0.034), (-0.12, -0.38, zt + 0.07), (0.12, -0.38, zt + 0.07), (0.12, -0.38, zt + 0.034)],
                      0.02, nseg=6), 0.006, seg=14, mat="steel")
    return mb


def _padlock(mb, M, s=1.0):
    """Candado laminado de 40 mm: cuerpo de láminas con remaches, arco de acero (local: arco hacia +Z, cara hacia -Y)."""
    cs.slab(mb, M @ _T(0, 0, 0.017 * s) @ _Rx(90) @ _T(0, 0, -0.009 * s), 0.04 * s, 0.034 * s, 0.018 * s, rc=0.004 * s,
            re=0.002 * s, mat="steel", nc=3, ne=2)
    for k in range(1, 6):
        z = 0.034 * s * k / 6
        mb.box((-0.0202 * s, -0.0092 * s, z - 0.0004 * s), (0.0202 * s, 0.0092 * s, z + 0.0004 * s), "gunmetal", bevel=0.0, m=M)
    path = [(-0.011 * s, 0.0, 0.034 * s), (-0.011 * s, 0.0, 0.052 * s), (0.011 * s, 0.0, 0.052 * s), (0.011 * s, 0.0, 0.034 * s)]
    mb.tube([tuple(M @ Vector(p)) for p in cl.fillet(path, 0.011 * s, nseg=8)], 0.0032 * s, seg=12, mat="steel")
    ce.lathe(mb, [(0.0, 0.0), (0.004 * s, 0.0), (0.004 * s, 0.0008), (0.0, 0.0008)], seg=16, mat="brass",
             M=M @ _T(0, -0.0092 * s, 0.01 * s) @ _Rx(90))


def _bench(L=1.6, D=0.40, H=0.45):
    """Banca de concreto precolado: asiento de 75 mm con cantos boleados, dos pedestales troncopiramidales con
    aristas boleadas y chaflán al pie, junta de mortero (origen: piso, centro)."""
    mb = cl.MB()
    t = 0.075
    cs.slab(mb, _T(0, 0, H - t), L, D, t, rc=0.03, re=0.016, re0=0.008, mat="concrete", nc=5, ne=4)
    for x in (-L / 2 + 0.24, L / 2 - 0.24):
        loops = []
        for (z, w, d, rc) in ((0.0, 0.17, 0.33, 0.012), (0.006, 0.182, 0.342, 0.018), (H - t - 0.008, 0.13, 0.30, 0.016)):
            loops.append([(x + a, b, z) for (a, b) in cs.rr_pts(w, d, rc, 4)])
        cs.skin(mb, loops, "concrete")
        cs.slab(mb, _T(x, 0, H - t - 0.008), 0.125, 0.295, 0.0085, rc=0.014, re=0.002, mat="mortar", nc=3, ne=1)
    return mb


def _planter(R=0.75, h=0.45, wall=0.13):
    """Jardinera circular de block aplanado: corona boleada, cara interior, tezontle (grava roja) sobre la tierra."""
    mb = cl.MB()
    ri = R - wall
    cs.lathe(mb, [(0.0, 0.0), (R - 0.008, 0.0), (R, 0.008), (R, h - 0.018), (R - 0.004, h - 0.006), (R - 0.016, h), (ri + 0.016, h),
                  (ri + 0.004, h - 0.006), (ri, h - 0.018), (ri, h - 0.07), (0.0, h - 0.07)], seg=64, mat="concrete")
    cs.lathe(mb, [(0.0, h - 0.072), (ri + 0.002, h - 0.072), (ri + 0.002, h - 0.06), (ri - 0.05, h - 0.052), (0.25, h - 0.048),
                  (0.0, h - 0.045)], seg=48, mat="gravel")
    return mb


def _wheelie_bin(mat="sign_green"):
    """Contenedor de 240 L de dos ruedas (EN 840: 580 × 740 × 1070 mm, ruedas de Ø 200 mm): cuerpo cónico de esquinas
    redondeadas con labio superior, peine de levante al frente, nervios traseros, barra-manija y bisagra, tapa con faldón y
    agarradera, eje con ruedas de hule y rin, patas delanteras (frente hacia -Y, ruedas hacia +Y; origen: piso, centro)."""
    mb = cl.MB()
    loops = []
    for (z, w, d, cy, rc) in ((0.035, 0.40, 0.50, -0.01, 0.05), (0.05, 0.43, 0.53, -0.01, 0.06), (0.08, 0.445, 0.55, -0.005, 0.065),
                              (0.5, 0.505, 0.625, 0.0, 0.06), (0.9, 0.555, 0.685, 0.005, 0.055), (0.93, 0.56, 0.69, 0.005, 0.055),
                              (0.935, 0.585, 0.712, 0.005, 0.06), (0.952, 0.585, 0.712, 0.005, 0.06), (0.955, 0.56, 0.69, 0.005, 0.055)):
        loops.append([(a, b + cy, z) for (a, b) in cs.rr_pts(w, d, rc, 5)])
    cs.skin(mb, loops, mat)
    # tapa con faldón y agarradera al frente
    cs.slab(mb, _T(0, 0.0, 0.958), 0.605, 0.745, 0.022, rc=0.05, re=0.008, mat=mat, nc=5, ne=2)
    cs.slab(mb, _T(0, -0.37, 0.93), 0.4, 0.016, 0.05, rc=0.007, re=0.004, mat=mat, nc=2, ne=2)
    cs.slab(mb, _T(0, 0.02, 0.979), 0.42, 0.5, 0.006, rc=0.03, re=0.003, mat=mat, nc=4, ne=1)
    # peine de levante (frente) y nervios
    cs.rtube_p(mb, (-0.24, -0.355, 0.86), (0.24, -0.355, 0.86), 0.035, 0.05, mat, r=0.01, n=2)
    for x in (-0.18, 0.0, 0.18):
        cs.rtube_p(mb, (x, -0.33, 0.83), (x, -0.36, 0.86), 0.02, 0.04, mat, r=0.006, n=1)
    for x in (-0.13, 0.13):
        cs.rtube_p(mb, (x, 0.283, 0.17), (x, 0.352, 0.9), 0.04, 0.02, mat, r=0.008, n=2)
    # barra-manija y bisagra atrás
    mb.cyl((-0.265, 0.405, 0.985), (0.265, 0.405, 0.985), 0.017, seg=24, mat=mat)
    for x in (-0.25, 0.25):
        cs.rtube_p(mb, (x, 0.35, 0.93), (x, 0.405, 0.985), 0.03, 0.03, mat, r=0.008, n=2)
    mb.cyl((-0.22, 0.372, 0.962), (0.22, 0.372, 0.962), 0.008, seg=16, mat="cable")
    # eje, ruedas Ø 200 con rin y tapón, soportes del eje
    zw, yw = 0.10, 0.33
    mb.cyl((-0.30, yw, zw), (0.30, yw, zw), 0.0125, seg=20, mat="steel")
    for sx in (-1, 1):
        Mw = _T(sx * 0.27, yw, zw) @ _Ry(90)
        ce.lathe(mb, [(0.03, -0.024), (0.07, -0.025), (0.09, -0.022), (0.098, -0.015), (0.1, -0.006), (0.1, 0.006), (0.098, 0.015),
                      (0.09, 0.022), (0.07, 0.025), (0.03, 0.024)], seg=40, mat="rubber", caps=False, M=Mw)
        ce.lathe(mb, [(0.0, -0.026), (0.03, -0.026), (0.03, 0.026), (0.0, 0.026)], seg=24, mat="cable", M=Mw)
        ce.lathe(mb, [(0.0, 0.0), (0.018, 0.0), (0.016, 0.006), (0.0, 0.008)], seg=20, mat="steel", M=_T(sx * 0.296, yw, zw) @ _Ry(90 * sx))
        cs.rtube_p(mb, (sx * 0.2, 0.22, 0.2), (sx * 0.22, yw, zw), 0.04, 0.05, mat, r=0.01, n=2)
    for x in (-0.16, 0.16):                                         # patas delanteras
        cs.slab(mb, _T(x, -0.2, 0.0), 0.07, 0.09, 0.045, rc=0.015, re=0.006, mat=mat, nc=3, ne=2)
    return mb


def _gas_cage(W=1.40, D=0.80, H=1.85, seed=0):
    """Jaula de cilindros de gas LP: bastidor de ángulo de 1 1/2" × 3/16" soldado, malla electrosoldada 50 × 100 mm de alambre
    Ø 4 mm en costados y fondo, techo de lámina galvanizada con ceja, puerta de malla con 3 bisagras de nudillo, aldaba y
    candado, letreros (origen: piso, centro; puerta hacia -Y)."""
    mb = cl.MB()
    leg, t = 0.038, 0.0048
    x0, x1, y0, y1 = -W / 2, W / 2, -D / 2, D / 2
    for (x, y, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        ce.angle_l(mb, (x, y, 0.0), (x, y, H), leg, t, up=(sx, 0, 0), s=sx * sy, mat="paint_green")
    for z in (0.04, 1.0, H - leg):
        for (a, b, up) in (((x0, y1), (x1, y1), (0, -1, 0)), ((x0, y0), (x0, y1), (1, 0, 0)), ((x1, y1), (x1, y0), (-1, 0, 0))):
            ce.angle_l(mb, (a[0], a[1], z), (b[0], b[1], z), leg, t, up=(0, 0, 1), s=1, mat="paint_green")
    ce.angle_l(mb, (x0, y0, H - leg), (x1, y0, H - leg), leg, t, up=(0, 0, 1), s=-1, mat="paint_green")

    def mesh(o, eu, ev, Lu, Lv, du=0.05, dv=0.10):
        o, eu, ev = Vector(o), Vector(eu), Vector(ev)
        nu, nv = int(Lu / du), int(Lv / dv)
        for i in range(1, nu):
            p = o + eu * (Lu * i / nu)
            mb.tube([tuple(p), tuple(p + ev * Lv)], 0.002, seg=12, mat="galvanized")
        for j in range(1, nv):
            p = o + ev * (Lv * j / nv) + eu.cross(ev).normalized() * 0.004
            mb.tube([tuple(p), tuple(p + eu * Lu)], 0.002, seg=12, mat="galvanized")
    mesh((x0 + 0.01, y1 - 0.008, 0.05), (1, 0, 0), (0, 0, 1), W - 0.02, H - 0.1)
    mesh((x0 + 0.008, y0 + 0.01, 0.05), (0, 1, 0), (0, 0, 1), D - 0.02, H - 0.1)
    mesh((x1 - 0.008, y1 - 0.01, 0.05), (0, -1, 0), (0, 0, 1), D - 0.02, H - 0.1)
    # techo de lámina con ceja
    cs.slab(mb, _T(0, 0, H), W + 0.08, D + 0.08, 0.0016, rc=0.004, re=0.0006, mat="galvanized", nc=1, ne=1)
    for (cx, cy, w, d) in ((0, y0 - 0.0392, W + 0.08, 0.0016), (0, y1 + 0.0392, W + 0.08, 0.0016), (x0 - 0.0392, 0, 0.0016, D + 0.08),
                           (x1 + 0.0392, 0, 0.0016, D + 0.08)):
        cs.slab(mb, _T(cx, cy, H - 0.03), w, d, 0.03, rc=0.0007, re=0.0005, mat="galvanized", nc=1, ne=1)
    # puerta: marco de ángulo, malla, bisagras, aldaba y candado
    dx0, dx1, dz0, dz1 = x0 + 0.045, x1 - 0.045, 0.06, H - 0.06
    yd = y0 - 0.012
    for (a, b) in (((dx0, dz0), (dx1, dz0)), ((dx0, dz1), (dx1, dz1)), ((dx0, (dz0 + dz1) / 2), (dx1, (dz0 + dz1) / 2))):
        cl.rtube(mb, (a[0] + 0.0105, yd, a[1]), (b[0] - 0.0105, yd, b[1]), 0.024, 0.024, "paint_green", up=(0, 0, 1), r=0.003)
    for x in (dx0, dx1):
        cl.rtube(mb, (x, yd, dz0 - 0.0125), (x, yd, dz1 + 0.0125), 0.025, 0.025, "paint_green", up=(1, 0, 0), r=0.003)
    mesh((dx0 + 0.0125, yd + 0.002, dz0 + 0.0125), (1, 0, 0), (0, 0, 1), dx1 - dx0 - 0.025, dz1 - dz0 - 0.025)
    for z in (0.25, (dz0 + dz1) / 2, H - 0.3):
        for (a, b) in ((z - 0.05, z - 0.003), (z + 0.003, z + 0.05)):
            ce.lathe(mb, [(0.0, a), (0.0095, a), (0.011, a + 0.002), (0.011, b - 0.002), (0.0095, b), (0.0, b)], seg=24, mat="steel",
                     M=_T(x0 + 0.02, y0 - 0.02, 0.0))
    cs.slab(mb, _T(dx1 - 0.03, yd - 0.013, 1.0) @ _Rx(90), 0.08, 0.04, 0.004, rc=0.006, re=0.001, mat="steel", nc=2, ne=1)
    cs.slab(mb, _T(x1, y0 - 0.013, 1.0) @ _Rx(90) @ _T(-0.01, 0, 0), 0.04, 0.05, 0.004, rc=0.006, re=0.001, mat="steel", nc=2, ne=1)
    _padlock(mb, _T(x1 - 0.03, y0 - 0.03, 0.95))
    mb.join(cl.sign_plate("LP GAS", 0.34, 0.12, bg="sign_red", fg="sign_white", size=0.07), _T(0.0, yd - 0.0045, 1.25))
    mb.join(cl.sign_plate("NO SMOKING", 0.34, 0.1, bg="sign_white", fg="sign_red", size=0.05), _T(0.0, yd - 0.0045, 1.1))
    return mb


def _tpost(H=1.95, arm=0.70):
    """Poste de tendedero en T: tubo galvanizado de 2" con dado de concreto, tapón, te de 1 1/2" con brazo y armellas en las
    puntas (origen: piso, centro; brazo a lo largo de Y)."""
    mb = cl.MB()
    ce.lathe(mb, [(0.0, 0.0), (0.15, 0.0), (0.148, 0.03), (0.12, 0.055), (0.05, 0.07), (0.0, 0.07)], seg=32, mat="concrete")
    mb.cyl((0, 0, 0.05), (0, 0, H - 0.04), 0.0302, seg=28, mat="galvanized")
    ce.lathe(mb, [(0.0, 0.0), (0.038, 0.0), (0.04, 0.006), (0.04, 0.07), (0.037, 0.075), (0.0, 0.075)], seg=28, mat="galvanized",
             M=_T(0, 0, H - 0.075))
    for sg in (-1, 1):
        mb.cyl((0, sg * 0.035, H - 0.0375), (0, sg * arm / 2, H - 0.0375), 0.024, seg=24, mat="galvanized")
        ce.lathe(mb, [(0.0, 0.0), (0.028, 0.0), (0.028, 0.01), (0.022, 0.016), (0.0, 0.017)], seg=24, mat="galvanized",
                 M=_T(0, sg * arm / 2, H - 0.0375) @ _Rx(-90 * sg))
        mb.cyl((0, sg * (arm / 2 - 0.04), H - 0.065), (0, sg * (arm / 2 - 0.04), H - 0.09), 0.004, seg=12, mat="steel")
        ce.loop_tube(mb, [(0.0, sg * (arm / 2 - 0.04) + 0.012 * math.cos(2 * PI * k / 16), H - 0.104 + 0.012 * math.sin(2 * PI * k / 16))
                          for k in range(16)], 0.003, seg=12, mat="steel", normal=(1, 0, 0))
    return mb


def _cone():
    """Cono de tránsito de 28" (MUTCD): base cuadrada de 14" con esquinas redondeadas, cuerpo cónico con punta boleada,
    banda reflejante de 6" a 3–4" de la punta y de 4" dos pulgadas abajo (origen: piso, centro)."""
    mb = cl.MB()
    Ht, hb = 0.711, 0.032
    cs.slab(mb, _T(0, 0, 0), 0.356, 0.356, hb, rc=0.04, re=0.008, re0=0.003, mat="rubber", nc=5, ne=2)
    r0, r1 = 0.125, 0.027

    def rad(z):
        return r0 + (r1 - r0) * (z - hb) / (Ht - 0.012 - hb)
    cs.lathe(mb, [(0.0, hb - 0.001), (r0 + 0.012, hb - 0.001), (r0 + 0.01, hb + 0.006), (r0, hb + 0.018), (rad(Ht - 0.02), Ht - 0.02),
                  (r1 - 0.006, Ht - 0.006), (r1 - 0.016, Ht), (0.0, Ht)], seg=48, mat="sign_red")
    for (za, zb) in ((Ht - 0.089 - 0.152, Ht - 0.089), (Ht - 0.089 - 0.152 - 0.051 - 0.102, Ht - 0.089 - 0.152 - 0.051)):
        cs.lathe(mb, [(rad(za) + 0.0008, za), (rad(zb) + 0.0008, zb)], seg=48, mat="sign_white", caps=False)
        for (z, sg) in ((za, -1), (zb, 1)):
            cs.lathe(mb, [(rad(z) - 0.0005, z), (rad(z) + 0.0008, z)], seg=48, mat="sign_white", caps=False)
    return mb


def _tire_flat(R=0.372, Rb=0.203, W=0.224, seed=0):
    """Llanta de camioneta LT 225/75 R16 acostada (Ø 744 mm = 29,3", ancho 224 mm): sección de cuerda con costado abombado, hombros,
    banda con 3 ranuras perimetrales y bloques por ranuras transversales alternadas, ceja y talón (origen: piso, eje)."""
    mb = cl.MB()
    tread = [(R - 0.006, 0.03), (R - 0.0015, 0.045), (R, 0.06), (R, 0.068), (R - 0.009, 0.07), (R - 0.009, 0.08), (R, 0.082), (R, 0.104),
             (R - 0.009, 0.106), (R - 0.009, 0.119), (R, 0.121), (R, 0.143), (R - 0.009, 0.145), (R - 0.009, 0.155), (R, 0.157),
             (R, 0.165), (R - 0.0015, 0.18), (R - 0.006, 0.195)]
    prof = [(Rb + 0.004, 0.012), (Rb + 0.02, 0.004), (0.26, 0.0), (R - 0.075, 0.004), (R - 0.04, 0.01), (R - 0.017, 0.02)] + tread + \
           [(R - 0.017, W - 0.02), (R - 0.04, W - 0.012), (R - 0.075, W - 0.004), (0.26, W), (Rb + 0.02, W - 0.004), (Rb + 0.004, W - 0.012),
            (Rb, W - 0.03), (Rb - 0.002, 0.03)]
    nt = len(prof)
    i_tread = set(range(6, 6 + len(tread)))

    def rmod(i, a, r, z):
        if i not in i_tread or r < R - 0.0005:
            return r
        k = a * 40 / (2 * PI)
        shift = 0.5 if z > W / 2 else 0.0
        f = (k + shift) % 1.0
        return r - 0.008 if f < 0.16 else r
    cs.lathe(mb, prof, seg=160, mat="rubber", closed=True, rmod=rmod)
    del nt, seed
    return mb


def _hose_reel():
    """Carrete de manguera de pared: ménsula de lámina atornillada, brazos, tambor con bridas de Ø 480 troqueladas, 8 vueltas de
    manguera de 3/4" sobre el tambor, guía de rodillos, manguera colgando con pistola, manivela de rebobinado (origen: cara del
    muro, centro; sale hacia -Y)."""
    mb = cl.MB()
    cs.slab(mb, _Rx(90), 0.30, 0.36, 0.008, rc=0.015, re=0.002, mat="paint_green", nc=3, ne=1)
    for (x, z) in ((-0.12, -0.15), (0.12, -0.15), (-0.12, 0.15), (0.12, 0.15)):
        ce.hexnut(mb, _T(x, -0.008, z) @ _Rx(90), d=0.009, mat="steel")
    for x in (-0.135, 0.135):
        cs.rtube_p(mb, (x, -0.008, 0.0), (x, -0.20, 0.0), 0.012, 0.06, "paint_green", r=0.004, n=2)
    Mx = _T(0, -0.20, 0.0) @ _Ry(90)
    ce.lathe(mb, [(0.0, -0.15), (0.016, -0.15), (0.016, 0.15), (0.0, 0.15)], seg=24, mat="steel", M=Mx)
    for z in (-0.125, 0.12):
        ce.lathe(mb, [(0.03, z), (0.24, z), (0.242, z + 0.0025), (0.24, z + 0.005), (0.03, z + 0.005)], seg=64, mat="sign_red", M=Mx)
    for k in range(6):
        a = 2 * PI * k / 6
        for z in (-0.122, 0.117):
            cs.rtube_p(mb, tuple(Mx @ Vector((0.05 * math.cos(a), 0.05 * math.sin(a), z + 0.0025))),
                       tuple(Mx @ Vector((0.225 * math.cos(a), 0.225 * math.sin(a), z + 0.0025))), 0.012, 0.012, "sign_red", r=0.004, n=1)
    ce.lathe(mb, [(0.0, -0.12), (0.155, -0.12), (0.155, 0.12), (0.0, 0.12)], seg=48, mat="rubber", M=Mx)
    rh, pitch = 0.0125, 0.025
    pts = []
    for i in range(8 * 40 + 1):
        a = 2 * PI * i / 40
        x = -0.105 + pitch * i / 40
        pts.append(tuple(Mx @ Vector((0.168 * math.cos(a), 0.168 * math.sin(a), x))))
    mb.tube(pts, rh, seg=14, mat="rubber")
    end = Vector(pts[-1])
    drop = cl.fillet([tuple(end), (0.11, -0.20, -0.20), (0.12, -0.24, -0.45), (0.15, -0.32, -0.80), (0.16, -0.34, -0.95)], 0.08, nseg=8)
    mb.tube(drop, rh, seg=14, mat="rubber")
    q = Vector(drop[-1])
    ce.lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.03), (0.013, 0.035), (0.013, 0.12), (0.016, 0.13), (0.0, 0.135)], seg=24,
             mat="sign_red", M=_T(q.x, q.y, q.z - 0.135))
    mb.tube(cl.fillet([(0.13, -0.20, 0.0), (0.24, -0.20, 0.0), (0.24, -0.20, 0.09), (0.30, -0.20, 0.09)], 0.02, nseg=6), 0.007, seg=14,
            mat="steel")
    ce.lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.013, 0.05), (0.012, 0.08), (0.0, 0.085)], seg=20, mat="plastic",
             M=_T(0.30, -0.20, 0.09) @ _Ry(90))
    return mb


def _gutter(mb, xa, xb, y_back, z_top, R=0.075, t=0.0008, mat="galvanized"):
    """Canalón media caña de 6" de lámina (de xa a xb, espalda en y_back, borde en z_top; se abre hacia arriba y su frente
    queda hacia -Y): concha de 0,8 mm, bordón enrollado al frente, tapas en los extremos."""
    outer = [(R - R * math.cos(PI * k / 32), -R * math.sin(PI * k / 32)) for k in range(33)]
    inner = [(R - (R - t) * math.cos(PI * k / 32), -(R - t) * math.sin(PI * k / 32)) for k in range(32, -1, -1)]
    mb.sweep(outer + inner, [(xa, y_back, z_top), (xb, y_back, z_top)], mat=mat, closed_profile=True, normal=(0, 0, 1))
    mb.tube([(xa, y_back - 2 * R - 0.0035, z_top + 0.0015), (xb, y_back - 2 * R - 0.0035, z_top + 0.0015)], 0.0045, seg=14, mat=mat)
    for x in (xa + 0.001, xb - 0.001):
        v = [mb.bm.verts.new((x, y_back - (R - R * math.cos(PI * k / 32)), z_top - R * math.sin(PI * k / 32))) for k in range(33)]
        mb.face(v, mat)
    return (y_back - R, z_top - R)


def _hanger(mb, x, y_back, z_top, R=0.075, mat="galvanized"):
    """Gancho de solera del canalón: abraza la media caña y sube a la fascia con una pija."""
    w, t = 0.02, 0.0018
    pts = [(x, y_back + 0.002, z_top + 0.03), (x, y_back + 0.002, z_top)]
    for k in range(17):
        a = PI * k / 16
        pts.append((x, y_back - (R - (R + t) * math.cos(a)), z_top - (R + t) * math.sin(a)))
    pts.append((x, y_back - 2 * R - 0.012, z_top + 0.004))
    mb.sweep([(-w / 2, -t / 2), (w / 2, -t / 2), (w / 2, t / 2), (-w / 2, t / 2)], cl.fillet(pts, 0.004, nseg=3), mat=mat, normal=(1, 0, 0))
    cs.screw(mb, _T(x, y_back + 0.001, z_top + 0.018) @ _Rx(90), r=0.004, seg=12, cross=False)


def _mast(mb, x, y, z0, H=5.0, ring=3.5, guy_r=1.4):
    """Mástil de radio de la ambulancia: tubo galvanizado de 1 1/2" con placa base de 250 mm, 4 cartelas y 4 taquetes;
    anillo de vientos con 3 orejas, cable de acero de 3 mm con tensor y guardacabo a armellas sobre placa en la losa; antena de
    látigo de fibra con resorte y base; coaxial con abrazaderas bajando a un pasamuros con capuchón."""
    cs.slab(mb, _T(x, y, z0), 0.25, 0.25, 0.012, rc=0.015, re=0.002, mat="galvanized", nc=3, ne=1)
    for (dx, dy) in ((-0.09, -0.09), (0.09, -0.09), (-0.09, 0.09), (0.09, 0.09)):
        ce.hexnut(mb, _T(x + dx, y + dy, z0 + 0.012), d=0.012, mat="steel")
    mb.cyl((x, y, z0 + 0.012), (x, y, z0 + H), 0.024, seg=24, mat="galvanized")
    ce.lathe(mb, [(0.0, 0.0), (0.027, 0.0), (0.027, 0.02), (0.022, 0.026), (0.0, 0.028)], seg=24, mat="galvanized",
             M=_T(x, y, z0 + H - 0.012))
    ce.weld(mb, _T(x, y, z0 + 0.012), 0.024, w=0.004, seg=24, mat="galvanized")
    for k in range(4):
        M = _T(x, y, z0 + 0.012) @ _Rz(90 * k + 45) @ _T(0.023, 0, 0)
        port.gusset(mb, M, 0.08, 0.12, t=0.006, mat="galvanized", chamfer=0.02)
    zr = z0 + ring
    ce.lathe(mb, [(0.0235, -0.025), (0.042, -0.025), (0.045, -0.02), (0.045, 0.02), (0.042, 0.025), (0.0235, 0.025)], seg=24,
             mat="galvanized", M=_T(x, y, zr))
    for k in range(3):
        a = math.radians(30 + 120 * k)
        ca, sa = math.cos(a), math.sin(a)
        ear = Vector((x + 0.06 * ca, y + 0.06 * sa, zr))
        mb.box((-0.012, -0.003, -0.018), (0.03, 0.003, 0.018), "galvanized", bevel=0.002, m=_T(x + 0.042 * ca, y + 0.042 * sa, zr) @ _Rz(math.degrees(a)))
        anc = Vector((x + guy_r * ca, y + guy_r * sa, z0))
        cs.slab(mb, _T(anc.x, anc.y, z0), 0.12, 0.12, 0.008, rc=0.01, re=0.0015, mat="galvanized", nc=2, ne=1)
        ce.loop_tube(mb, [(anc.x + 0.018 * math.cos(2 * PI * j / 16) * ca, anc.y + 0.018 * math.cos(2 * PI * j / 16) * sa,
                           z0 + 0.04 + 0.018 * math.sin(2 * PI * j / 16)) for j in range(16)], 0.004, seg=12, mat="steel",
                     normal=(-sa, ca, 0))
        mb.cyl((anc.x, anc.y, z0 + 0.008), (anc.x, anc.y, z0 + 0.024), 0.006, seg=12, mat="steel")
        top = anc + Vector((0, 0, 0.058))
        d = (ear - top).normalized()
        tb0, tb1 = top + d * 0.05, top + d * 0.2
        Mt = Matrix.Translation(tb0) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        ce.lathe(mb, [(0.0, 0.0), (0.006, 0.0), (0.006, 0.02), (0.01, 0.03), (0.01, 0.12), (0.006, 0.13), (0.006, 0.15), (0.0, 0.15)],
                 seg=16, mat="galvanized", M=Mt)
        mb.tube([tuple(top), tuple(tb0)], 0.003, seg=12, mat="steel")
        mb.tube([tuple(tb1), tuple(ear)], 0.0015, seg=12, mat="steel")
    # antena de látigo: base, resorte, fibra
    zt = z0 + H + 0.016
    ce.lathe(mb, [(0.0, 0.0), (0.02, 0.0), (0.02, 0.03), (0.012, 0.04), (0.012, 0.07), (0.0, 0.07)], seg=24, mat="cable", M=_T(x, y, zt))
    with mb.soft():
        sp = [(x + 0.009 * math.cos(2 * PI * k / 10), y + 0.009 * math.sin(2 * PI * k / 10), zt + 0.07 + 0.08 * k / 60) for k in range(61)]
        mb.tube(sp, 0.0022, seg=12, mat="steel")
        mb.tube([(x, y, zt + 0.15), (x, y, zt + 1.5)], 0.006, seg=12, mat="plastic", radii=[0.006, 0.0025])
    ce.lathe(mb, [(0.0, 0.0), (0.004, 0.0), (0.004, 0.006), (0.0, 0.008)], seg=12, mat="plastic", M=_T(x, y, zt + 1.5))
    # coaxial: baja pegado al mástil con abrazaderas hasta un pasamuros con capuchón
    with mb.soft():
        cx = x + 0.0295
        path = cl.fillet([(x + 0.012, y, zt + 0.02), (cx, y, zt - 0.03), (cx, y, z0 + 0.25), (cx + 0.08, y, z0 + 0.1), (cx + 0.35, y, z0 + 0.05)],
                         0.05, nseg=8)
        mb.tube(path, 0.0055, seg=12, mat="cable")
    for z in (z0 + 0.8, z0 + 2.0, z0 + 3.2, z0 + 4.4):
        ce.lathe(mb, [(0.0235, -0.006), (0.027, -0.006), (0.027, 0.006), (0.0235, 0.006)], seg=24, mat="steel", M=_T(x, y, z))
        ce.lathe(mb, [(0.005, -0.006), (0.0075, -0.006), (0.0075, 0.006), (0.005, 0.006)], seg=12, mat="steel", M=_T(cx, y, z))
    ce.lathe(mb, [(0.0, 0.0), (0.05, 0.0), (0.05, 0.12), (0.06, 0.13), (0.06, 0.16), (0.0, 0.17)], seg=24, mat="galvanized",
             M=_T(cx + 0.38, y, z0))


def _stoop(inter, det, M, W, D, n=3, run=0.30, h=FFL, rails=True):
    """Descanso de concreto a nivel de piso terminado frente a una puerta exterior con `n` escalones hacia afuera y pasamanos a
    los dos lados. Local: el muro en v = 0, el descanso de v = 0 a D (sale hacia +v), escalones de v = D a D + n·run;
    u de -W/2 a W/2 (M lleva a coordenadas del modelo)."""
    rise = h / n
    pts = [(-W / 2, 0.0), (W / 2, 0.0), (W / 2, D), (-W / 2, D)]
    loops = []
    for (z, ins) in ((0.0, 0.0), (h - 0.012, 0.0), (h, 0.012)):
        loops.append([(a + (ins if a < 0 else -ins), b - (ins if b > 0 else 0.0), z) for (a, b) in pts])
    cs.skin(inter, loops, "concrete", M=M)
    Ms = M @ _T(W / 2, D + n * run, 0.0) @ _Rz(180)
    _stair(inter, Ms, W, n, run, rise)
    if rails:
        for u in (-W / 2 + 0.07, W / 2 - 0.07):
            pb = M @ Vector((u, D + n * run, rise))
            pt = M @ Vector((u, D + run, h))
            p0 = M @ Vector((u, D + n * run - run / 2, 0.0))
            _ramp_rail(det, pb, pt, posts=[(0.25, rise), (1.0 + 0.05 / ((n - 1) * run), h)], ext=0.30)
            del p0


# ------------------------------------------------------------------------------------------------------------ azotea y servicios
def rooftop(roof, det, r):
    # registro de azotea (brocal boleado, tapa de lámina con faldón, bisagras, aldaba y candado)
    det.join(_roof_hatch(), _T(-8.05, 6.65, SLAB_T))
    # tubos de ventilación de los baños y la cocina (PVC 4" con bota y sombrerete)
    for (x, y) in ((0.9, 8.6), (3.0, 8.6), (6.2, 9.1), (-3.0, 9.1)):
        det.join(_vent_pipe(), _T(x, y, SLAB_T))
    # tubería de los tinacos: baja a la azotea, cruza el pretil y baja por el muro del fondo entre vanos, con abrazaderas
    yp = Y1 + 0.0225
    path = cl.fillet([(9.2, 7.0, SLAB_T + 0.9), (9.2, 7.0, SLAB_T + 0.12), (9.2, yp, SLAB_T + 0.12), (9.2, yp, FFL + 0.4),
                      (9.2, Y1 - 0.05, FFL + 0.4)], 0.06, nseg=8)
    det.tube(path, 0.022, seg=20, mat="plastic")
    z = FFL + 0.9
    while z < SLAB_T - 0.2:
        _pipe_clamp(det, (9.2, yp, z), (0, 0, 1), (0, 1, 0), 0.022)
        z += 1.0
    for (x, y) in ((7.4, 7.6), (9.0, 7.6)):
        det.join(sv.water_tank(seed=int(r.integers(1e6)), detail="mid"), _T(x, y, SLAB_T))
    # gárgolas de PVC en el pretil (fondo y costados), con chaflán de mortero
    for x in (-10.0, -3.0, 4.0, 10.9):
        det.join(_scupper((x, Y1 - 0.25, SLAB_T + 0.05), (x, Y1 + 0.35, SLAB_T + 0.03), 0.25), None)
    for y in (-6.0, 1.0, 7.0):
        det.join(_scupper((X0 + 0.25, y, SLAB_T + 0.05), (X0 - 0.35, y, SLAB_T + 0.03), 0.25), None)
        det.join(_scupper((X1 - 0.25, y, SLAB_T + 0.05), (X1 + 0.35, y, SLAB_T + 0.03), 0.25), None)
    for x in (18.0, 21.0):
        det.join(_scupper((x, GY1 - 0.25, G_ST + 0.05), (x, GY1 + 0.35, G_ST + 0.03), 0.25), None)
    # mástil de radio de la ambulancia sobre la cochera (vientos anclados dentro de la losa)
    _mast(det, 22.6, 0.4, G_ST)
    # condensadoras de minisplit en el muro trasero, con su tubería forrada y abrazaderas
    Mb = ac.panel_matrix("back", X0, X1, Y1, 0.0)
    for x in (-10.0, -5.4, 4.6, 8.4, 13.4):                    # entre ventanas y puerta de servicio, nunca sobre un vano
        ac_ = cl.remap(sv.ac_unit("split_outdoor", seed=int(r.integers(1e6)), detail="mid"),
                       {"metal_rust": "enamel", "metal_paint": "sign_white"})            # equipo en servicio: lámina esmaltada
        det.join(ac_, Mb @ _T(X1 - x, 0, 2.05))
        u = X1 - x + 0.3
        pts = [tuple(Mb @ Vector(p)) for p in ((u, -0.12, 2.35), (u, -0.12, 2.42), (u, -0.019, 2.52), (u, -0.019, 2.86), (u, 0.05, 2.9))]
        det.tube(cl.fillet(pts, 0.04, nseg=8), 0.018, seg=16, mat="plastic")
        _pipe_clamp(det, tuple(Mb @ Vector((u, -0.019, 2.7))), (0, 0, 1), (0, 1, 0), 0.018)
    det.join(cl.remap(sv.meter_box(seed=int(r.integers(1e6)), open_door=False, detail="high"),
                      {"metal_rust": "enamel", "metal_paint": "enamel"}), Mb @ _T(X1 - 3.9, 0, 1.4))
    det.join(cl.remap(sv.conduit([(X1 - 3.9, 0.0, 1.92), (X1 - 3.9, 0.0, 3.3), (X1 - 4.2, 0.0, 3.3), (X1 - 4.2, 0.0, PARA - 0.15)],
                                 seed=int(r.integers(1e6)), detail="high"), {"metal_rust": "steel", "metal_paint": "steel"}), Mb)                # conduit del medidor hacia la azotea
    del roof



# ------------------------------------------------------------------------------------------------------------ letreros
def signage(det, Ms, r):
    F = Ms["front"]
    cl.text(det, "COMMUNITY HOSPITAL", 0.44, 0.015, "paint_green", F @ _T(-X0, 0, SLAB_T + 0.1) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    det.join(cl.sign_plate("H", 0.7, 0.7, bg="sign_blue", fg="sign_white", size=0.5, frame="sign_white"), F @ _T(-1.25 - X0, 0, 2.2))
    for x in (-9.6, -6.4):
        det.join(cl.wall_lamp(), F @ _T(x - X0, 0, 2.6))
    E = ac.panel_matrix("east", Y0 + TE, Y1 - TE, X1, 0.0)
    # letrero sobre la puerta de urgencias, entre el marco (2,94) y el larguero de la marquesina (3,19); el colgante de la fascia
    # va en _canopy
    det.join(cl.sign_plate("EMERGENCY", 1.6, 0.17, bg="sign_red", fg="sign_white", size=0.11, t=0.03),
             E @ _T((ER_DOOR[0] + ER_DOOR[1]) / 2 - (Y0 + TE), 0, 2.955))
    det.join(cl.wall_lamp(), E @ _T(ER_DOOR[0] - 0.9 - (Y0 + TE), 0, 2.55))
    G = ac.panel_matrix("front", GX0, GX1, GY0, 0.0)
    cl.text(det, "AMBULANCE ENTRANCE", 0.26, 0.012, "sign_red", G @ _T((GX1 - GX0) / 2, 0, 3.32) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    for (txt, zz) in (("AMBULANCE", 1.82), ("ONLY", 1.7)):                 # en la pilastra de 0,40 m entre las dos cortinas
        det.join(cl.sign_plate(txt, 0.3, 0.11, bg="sign_white", fg="sign_red", size=0.045), G @ _T(4.0, 0, zz))
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
    _wall_item(det, cl.sanitizer(), -9.6, y0, z + 1.2, "+y")              # sobre el bote, no en el vano de la puerta principal
    _wall_item(det, cl.exit_sign(), -8.0, y0, z + 2.5, "+y")
    det.join(cl.hanging_sign("WAITING ROOM", 1.3, 0.28), _T(-8.6, -6.2, CEIL))
    for (x, y) in ((-10.5, -7.0), (-5.5, -7.0)):
        det.join(cl.ceiling_fan(int(r.integers(1e6))), _T(x, y, CEIL))
    put(det, cl.trash_bin(pedal=False), -9.6, y0 + 0.3)
    _wall_item(det, cl.sign_plate("RECEPTION", 1.1, 0.24, size=0.13), x1, -7.2, z + 2.3, "-x")
    _wall_item(det, cl.extinguisher(), x0, -5.0, z - 0.4, "+x")           # NOM-002-STPS: parte alta a <= 1,50 m del piso
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
    put(inter, cl.stretcher(int(r.integers(1e6))), 12.0, -8.9, "-x")      # fuera del abatimiento de la puerta de urgencias
    put(inter, cl.cylinder_rack(2, seed=int(r.integers(1e6))), 11.9, y1 - 0.35, "-y")
    put(inter, cl.shelving(1.0, 0.4, 2.0, 5, seed=int(r.integers(1e6))), 4.3, y1 - 0.25, "-y")       # no frente a la puerta doble
    _wall_item(det, cl.sink(), x0, -6.5, z, "+x")
    put(det, cl.wheelchair(int(r.integers(1e6))), 10.8, y1 - 0.5, "+x")
    put(det, cl.trash_bin(), x0 + 0.3, -7.5)
    _wall_item(det, cl.split_indoor(), 9.0, y1, z + 2.35, "-y")
    _wall_item(det, cl.exit_sign(), x1, (ER_DOOR[0] + ER_DOOR[1]) / 2, z + 2.47, "-x")    # sobre la puerta, bajo el plafón
    _wall_item(det, cl.sanitizer(), x1, ER_DOOR[0] - 0.6, z + 1.2, "-x")
    # pasillo: pasamanos de madera, letreros de puerta, colgante, extintor, camilla y silla de ruedas estacionadas
    x0, x1, y0, y1, _ = R["pasillo"]
    for (yy, d) in ((y0, "+y"), (y1, "-y")):
        gaps = [(g0 - 0.15, g1 + 0.15) for (g0, g1) in _gaps_on("x", -4.0 if yy == y0 else -1.8, x0, x1)]   # libra marcos y chambranas
        segs = _runs(x0 + 0.1, x1 - 0.1, sorted(gaps + ([(CXW - TE / 2 - 2.0, CXE + TE / 2)] if yy == y1 else [])))
        for (a, b) in segs:
            if b - a < 0.4:
                continue
            rail = cl.handrail(b - a, seed=int(r.integers(1e6)))      # corre en +x local: girado 180° (muro sur) arranca en b
            _wall_item(det, rail, b if d == "+y" else a, yy, z + 0.89, d)
    for (txt, x) in (("EXAM 1", -11.75), ("EXAM 2", -7.35), ("PHARMACY", 5.45), ("X-RAY", 10.95)):
        _wall_item(det, cl.sign_plate(txt, 0.55, 0.15, size=0.075), x, y1, z + 2.25, "-y")
    for (txt, x) in (("RECEPTION", 0.65), ("EMERGENCY ROOM", 6.75)):
        _wall_item(det, cl.sign_plate(txt, 0.75 if len(txt) > 10 else 0.55, 0.15, size=0.07), x, y0, z + 2.3, "+y")
    det.join(cl.hanging_sign("EXAM ROOMS", 1.2, 0.26), _T(-9.5, (y0 + y1) / 2 + 0.42, CEIL))        # fuera de la línea de luminarias
    det.join(cl.hanging_sign("EXIT", 0.6, 0.2, bg="sign_green", fg="sign_white"), _T(-12.5, (y0 + y1) / 2 + 0.42, CEIL))
    _wall_item(det, cl.extinguisher(), 1.45, CYS - TE / 2, z - 0.4, "-y")   # entre la puerta y la ventana del patio, no sobre el vidrio
    put(inter, cl.stretcher(int(r.integers(1e6))), 8.2, y1 - 0.45, "-x")
    put(det, cl.wheelchair(int(r.integers(1e6))), -2.0, y0 + 0.45, "-x")
    _wall_item(det, cl.exit_sign(), x0, -2.95, z + 2.35, "+x")
    # consultorios
    for (nm, sx) in (("consultorio1", 1), ("consultorio2", -1)):
        x0, x1, y0, y1, _ = R[nm]
        xm = (x0 + x1) / 2
        # mesa de exploración a lo largo del muro (cabecera al muro del fondo, peldaños hacia la puerta); escritorio contra el muro
        # opuesto, fuera del abatimiento de la puerta; silla del médico frente al escritorio y silla del paciente a su lado
        put(inter, cl.exam_table(int(r.integers(1e6))), x0 + 0.45 if sx > 0 else x1 - 0.45, y1 - 1.06, "-y")
        xd = x1 - 0.3 if sx > 0 else x0 + 0.3
        put(inter, cl.desk(1.2, 0.6, seed=int(r.integers(1e6))), xd, 0.0, "-x" if sx > 0 else "+x")
        put(inter, cl.office_chair(int(r.integers(1e6))), xd - sx * 0.68, 0.05, "+x" if sx > 0 else "-x")
        put(inter, cl.folding_chair(int(r.integers(1e6))), xd - sx * 0.12, -0.95, "+y")
        _wall_item(det, cl.sink(), x1 if sx > 0 else x0, y1 - 0.6, z, "-x" if sx > 0 else "+x")
        put(det, cl.trash_bin(), x1 - 0.3 if sx > 0 else x0 + 0.3, y1 - 1.3)
        put(det, cl.iv_stand(int(r.integers(1e6)), bag=False), x0 + 0.4 if sx > 0 else x1 - 0.4, 0.95)
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
    put(inter, cl.desk(1.0, 0.55, seed=int(r.integers(1e6))), x0 + 0.5, y0 + 0.56, "+x")
    _wall_item(det, cl.sign_plate("CAUTION X-RAY", 0.6, 0.18, bg="paint_yellow", fg="cable", size=0.06), 12.25, y0, z + 1.6, "+y")   # junto a la puerta, no sobre ella
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
    for k, x in enumerate((-12.75, -10.55, -8.35, -6.15)):                      # buró del 4.º sin cruzar el tabique de x = -5
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
    put(inter, cl.counter(2.7, 0.55, h=1.05, seed=int(r.integers(1e6))), -2.95, y0 + 0.33, "-y")
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
    put(inter, cl.kitchen_table(1.6, 0.9, 0.75, seed=int(r.integers(1e6))), 6.6, 7.55)
    for (x, y, d) in ((6.2, 6.75, "+y"), (7.0, 6.75, "+y"), (6.2, 8.4, "-y"), (7.0, 8.4, "-y")):
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
    # camilla, conos y llantas fuera de las dos bahías (ambulancias de ~2,2 m de ancho centradas en cada cortina)
    _place_solid(det, cl.stretcher(int(r.integers(1e6))), _T(19.6, 0.0, zg) @ face_to("+x"))
    for k in range(3):                                                       # conos encimados
        det.join(_cone(), _T(gx1 - 0.3, 0.05, zg + k * 0.034) @ _Rz(17.0 * k))
    for k in range(3):
        det.join(_tire_flat(seed=k), _T(gx1 - 0.45, 1.3, zg + k * 0.224) @ _Rz(40.0 * k))
    det.join(_hose_reel(), _T(gx0, -4.2, zg + 1.2) @ face_to("+x"))
    det.join(cl.extinguisher(), _T(gx0, -1.0, zg - 0.4) @ face_to("+x"))
    for (x, y) in ((18.4, -5.0), (22.4, -5.0), (18.4, -1.0), (22.4, -1.0)):
        det.join(cl.fluorescent(), _T(x, y, G_SB) @ _Rz(90))
        LIGHTS.append([x, y, round(G_SB - 0.085, 3)])


def _place_solid(det, piece, M):
    _proxy(piece, M)
    det.join(piece, M)


def courtyard(inter, det, r):
    """Patio: jardinera de block aplanado con tezontle y palmera, bancas de concreto precolado, macetas."""
    cx, cy = 0.5, 1.1
    inter.join(_planter(), _T(cx, cy, FFL - 0.1))
    _palm(det, cx, cy, FFL + 0.3, r)
    for (x, y, rot) in ((-1.9, 2.8, 0), (2.9, -0.6, 90)):
        inter.join(_bench(), _T(x, y, FFL - 0.1) @ _Rz(rot))
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
    det.tube(pts, 0.12, seg=32, mat="wood_grey", radii=radii)
    top = Vector(pts[-1])
    ce.lathe(det, [(0.0, -0.15), (0.11, -0.15), (0.13, 0.0), (0.1, 0.18), (0.05, 0.28), (0.0, 0.3)], seg=32, mat="wood_varnish",
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
            with det.soft():                                     # raquis de <= 32 mm: sombreado continuo
                det.cyl(tuple(prev), tuple(p), 0.014 * (1 - 0.75 * t) + 0.002, seg=8, mat=mat_r)
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
    """Patio de servicio atrás: firme, jaula de cilindros de gas LP, contenedores de 240 L, tendedero con postes en T."""
    inter.box((-13.5, Y1, 0.0), (-2.0, Y1 + 2.6, 0.08), "concrete", bevel=0.01, seg=3)
    gx, gy = -11.0, Y1 + 1.7
    det.join(cl.cylinder_rack(3, seed=int(r.integers(1e6)), medical=False), _T(gx, gy, 0.08))
    det.join(_gas_cage(), _T(gx, gy, 0.08))
    for k, x in enumerate((-8.75, -8.0)):
        det.join(_wheelie_bin("sign_green" if k == 0 else "cable"), _T(x, gy + 0.05, 0.08) @ _Rz(float(r.uniform(-4, 4))))
    det.join(sv.laundry_line(5.5, seed=int(r.integers(1e6)), detail="mid"), _T(-7.0, Y1 + 1.2, 1.75))
    for x in (-7.0, -1.5):
        det.join(_tpost(), _T(x, Y1 + 1.2, 0.08 if x < -2.0 else 0.0))


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
    door_in(Ms["east"], ER_DOOR[0] - (Y0 + TE), ER_DOOR[1] - ER_DOOR[0], h=2.4, kind="double_glazed", depth=TE, z0=FFL, ang=30.0)
    door_in(Ms["west"], (Y1 - TE) + 2.4, 1.1, h=2.1, kind="metal", depth=TE, z0=FFL, ang=0.0)
    door_in(Ms["back"], X1 - 12.6, 1.0, h=2.1, kind="metal", depth=TE, z0=FFL, ang=0.0)
    door_in(Mc["s"], (CXE + TE / 2) - 1.0, 1.0, h=2.1, kind="double_glazed", depth=TE, z0=FFL - 0.1, ang=0.0)
    door_in(Mg["west"], (GY1 - TE) - G_SIDE_DOOR[1], G_SIDE_DOOR[1] - G_SIDE_DOOR[0], h=2.1, kind="metal", depth=TE, z0=G_FL, ang=15.0)
    GAPS.extend([("x", Y0, -8.9, -7.1), ("y", X1, ER_DOOR[0], ER_DOOR[1]), ("y", X0, -3.5, -2.4), ("x", Y1, 11.6, 12.6), ("x", CYS, 0.0, 1.0)])
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

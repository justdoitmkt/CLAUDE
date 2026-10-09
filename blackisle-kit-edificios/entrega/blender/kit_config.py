"""Configuración de los constructores (Apéndice B.3 del brief + cambios de diseño del usuario del 2026-10-09).

Reglas del usuario para departamentos: entrada delantera (-Y) y trasera (+Y) en PB, cero escaleras exteriores
(todas dentro de la envolvente) e interior completo (departamentos con cuartos, corredores, núcleo de escalera real).
"""

APT_COMMON = dict(entrances=("front", "rear"), stairs="internal", interior="full")

KIT = {
 "APT_A_5p": dict(kind="apt", grid=3.6, bays=(4, 3), floors=5, pb_h=3.4, fl_h=2.9, frame="visible", pilotis=True, loggia_ratio=0.35,
                  stair_core="breeze_block_internal", roof="hip", pitch=26, seed=11, **APT_COMMON),
 "APT_B_4p": dict(kind="apt", grid=3.6, bays=(4, 2), floors=4, pb_h=3.2, fl_h=2.9, gallery=1.5, stair_core="internal",
                  infill="brick_under_plaster", collapse_corner="NE", roof="hip", pitch=26, seed=23, **APT_COMMON),
 "APT_C_3p": dict(kind="apt", plan="L", wing_a=(12.0, 6.6), wing_b=(6.6, 5.4), floors=3, pb_h=3.2, fl_h=2.9, canopy=(2.4, 1.2),
                  stair_core="internal_at_junction", roof="gable_valley", pitch=30, seed=37, **APT_COMMON),
 "APT_D_4p": dict(kind="apt", panel_module=2.7, bays=(5, 3), floors=4, pb_h=3.0, fl_h=2.9, balcony_every=2,
                  stair_core="internal_vent_strip_E", dormers=3, roof="gable", pitch=28, seed=41, **APT_COMMON),
 "CAB_1_tablones": dict(kind="cab", w=9.0, d=6.0, floors=2, floor_h=2.8, siding="board_batten", frame_visible=True, side_porch=True,
                        roof="gable", pitch=35, roof_mat="corrugated_rust", rafter_tails=True, stove_pipe=True, seed=5),
 "CAB_2_pilotes":  dict(kind="cab", w=7.0, d=6.0, floors=2, floor_h=2.6, stilts=12, stilt_h=1.2, siding="clapboard", veranda=1.2, ext_stair=True,
                        cistern=True, roof="gable", pitch=28, roof_mat="corrugated_light", torn_section=True, seed=9),
 "CAB_3_ladrillo": dict(kind="cab", w=8.0, d=6.5, floors=2, floor_h=2.8, ground="brick_individual", upper="board_light", porch=(2.4, 6.5),
                        chimney="brick", roof="gable", pitch=30, roof_mat="boards_grey_stepped", seed=14),
}

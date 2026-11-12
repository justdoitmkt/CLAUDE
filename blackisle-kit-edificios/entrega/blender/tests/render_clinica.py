"""Lámina de arcilla del mobiliario clínico (kit/clinic.py): python tests/render_clinica.py [--samples 24] [--only nombre,...]
Escribe render_qa/piezas/clinica_<toma>.png."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bpy  # noqa: E402,F401
from mathutils import Matrix, Vector  # noqa: E402

from kit import clinic as cl  # noqa: E402
from kit.common import MB, clay_render, reset_scene, tri_count  # noqa: E402

argv = sys.argv
S = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 24
only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "render_qa", "piezas"))
os.makedirs(out, exist_ok=True)
reset_scene()
T = lambda x, y, z=0.0: Matrix.Translation((x, y, z))  # noqa: E731
pieces = [
    ("bancada", cl.chair_row(4, seed=1)), ("silla_oficina", cl.office_chair(2)), ("silla_plegable", cl.folding_chair(3)),
    ("cama", cl.hospital_bed(4)), ("buro", cl.bedside_cabinet(5)), ("portasueros", cl.iv_stand(6)),
    ("mesa_exploracion", cl.exam_table(7)), ("silla_ruedas", cl.wheelchair(8)), ("camilla", cl.stretcher(9)),
    ("escritorio", cl.desk(seed=10)), ("archivero", cl.filing_cabinet(11)), ("anaquel", cl.shelving(seed=12)),
    ("mostrador", cl.counter()), ("despachador", cl.water_dispenser()), ("planta", cl.potted_plant(13)),
    ("bote", cl.trash_bin()), ("inodoro", cl.toilet()), ("lavabo", cl.sink()), ("refri", cl.fridge()), ("estufa", cl.stove()),
    ("lavadora", cl.washer()), ("cubeta", cl.mop_bucket()), ("oxigeno", cl.cylinder_rack(2)), ("rayosx", cl.xray_unit()),
    ("mampara", cl.lead_screen()), ("letrero", cl.sign_plate("EXAM 1", 0.5, 0.15)), ("salida", cl.exit_sign()),
    ("extintor", cl.extinguisher()), ("ventilador", cl.ceiling_fan()), ("reja", cl.window_grille(1.5, 1.2)),
]
objs = []
mb_all = MB()
cols = 6
for i, (nm, mb) in enumerate(pieces):
    x, y = (i % cols) * 2.6, -(i // cols) * 2.8
    z = 2.5 if nm == "ventilador" else 0.0
    mb_all.join(mb, T(x, y, z))
o = mb_all.finish("clinica", None, merge=0)
objs.append(o)
print("tris", tri_count(objs))
shots = {
    "todo": dict(azim=-25, elev=30, fov=45),
    "camas": dict(azim=-30, elev=18, dist=6.0, target=Vector((2.6 * 3.5, 0.0, 0.6)), fov=50),
    "consultorio": dict(azim=-30, elev=18, dist=6.5, target=Vector((2.6 * 1.5, -2.8, 0.6)), fov=50),
    "servicios": dict(azim=-30, elev=18, dist=7.5, target=Vector((2.6 * 2.5, -8.4, 0.8)), fov=50),
}
for nm, kw in shots.items():
    if only and nm not in only:
        continue
    clay_render(objs, f"{out}/clinica_{nm}.png", res=(1600, 900), samples=S, **kw)
    print("CLAY", nm, flush=True)

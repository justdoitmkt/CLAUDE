"""Tabla de los 7 modelos para REPORTE.md a partir de export/<ID>_validacion.json y texturas/<ID>/bake_info.json (números medidos)."""
import json
import os

ENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IDS = ["APT_A_5p", "APT_B_4p", "APT_C_3p", "APT_D_4p", "CAB_1_tablones", "CAB_2_pilotes", "CAB_3_ladrillo"]


def row(bid):
    v = os.path.join(ENT, "export", f"{bid}_validacion.json")
    if not os.path.exists(v):
        return f"| {bid} | — | — | — | — | — | — | pendiente |"
    d = json.load(open(v))
    c = d["checks"]
    ok = "OK" if all(c.values()) else "revisar: " + ", ".join(k for k, x in c.items() if not x)
    dims = d["dims_m"]
    return (f"| {bid} | {d['tris_glb']:,} | {d['size_mb']:.1f} | {d['n_materials']} | {d['texture_mem_mb']:.0f} | "
            f"{dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} | {d['base_z']:+.2f} | {ok} |").replace(",", " ")


if __name__ == "__main__":
    print("| Modelo | Triángulos (GLB) | MB | Materiales | Texturas en memoria (MB) | Caja X × Y × Z (m, con base) | z mín | Validación |")
    print("|---|---|---|---|---|---|---|---|")
    for b in IDS:
        print(row(b))

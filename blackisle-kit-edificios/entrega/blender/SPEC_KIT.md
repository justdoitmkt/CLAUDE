# SPEC · Kit modular BLACKISLE (contrato para todos los módulos)

Python de Blender: `/root/blk-venv/bin/python` (Blender 5.2.2 como módulo `bpy`, Cycles en CPU, sin GPU).
Importa SIEMPRE `bpy` antes que `bmesh`/`mathutils`. Ruta del paquete: `entrega/blender` (`from kit.common import ...`).

## Reglas
- Unidades reales: 1 = 1 m, Z arriba, fachada principal hacia -Y. Origen de cada pieza en su base o en la esquina indicada.
- Geometría con `kit.common.MB` (bmesh). Cada función de asset **devuelve un `MB`** (no un objeto) para que el constructor lo combine
  con `MB.join(other, matrix)`. El test convierte a objeto con `mb.finish(name)`.
- **No editar `kit/common.py`** (contrato compartido). Helpers propios van dentro de tu módulo.
- Sin `bpy.ops` para geometría. Sin booleanos. Sin subdivisión para inflar triángulos.
- Cuadriláteros dominantes; triángulos solo donde la forma lo exige (esquirlas de vidrio, escombro).
- Biseles reales en aristas duras >= 2 cm (`box(..., bevel=0.005–0.02, seg=1|2)`).
- Cero caras duplicadas o coplanares solapadas (z-fighting): las piezas que se tocan se separan >= 1 mm o comparten vértices.
- Sólidos cerrados donde aplique (`mesh_health` con 0 aristas no-manifold), salvo láminas intencionales: vidrio, tela, lámina.
- Determinismo: toda aleatoriedad sale de `rng(seed)`.
- Imperfección controlada: desplomes ±0,5–1°, piezas faltantes, abolladuras, dobleces. Nada perfectamente recto ni limpio.
- Materiales: usa los nombres de `kit.common.MATERIALS` (concrete, plaster, brick, mortar, tile, wood, wood_dark, wood_grey,
  metal_rust, metal_paint, aluminium, glass, fabric, cable, plastic, roof_metal, roof_metal_light, rubble, sand, vegetation).

## Medidas de referencia (brief §4.2)
Piso 2,9 m (PB 3,0–3,4) · losa 0,20 · viga de borde 0,25×0,50 · columna 0,35×0,35 (esquina 0,45) · malla 3,6 m ·
antepecho 0,90 · dintel 2,10 · ventana 1,2–1,8 de ancho · puerta de depto 0,90×2,05 · portón 1,6×2,3 · barandal 1,00 ·
peldaño 0,17×0,28 · escalera de 1,2 de ancho · bajante Ø0,10 · canalón 0,12 · A/C de ventana 0,60×0,40×0,45 · ladrillo 0,24×0,06×0,12 (junta 1 cm) ·
tablón 0,22 (rendija 0,04) · tabla traslapada 0,15 de exposición · bloque de celosía 0,20×0,20×0,10.

## Prueba y vista previa (obligatorias)
Cada grupo escribe `entrega/blender/tests/test_<grupo>.py`, que:
1. Llama a `kit.common.reset_scene()` y construye una vitrina con TODOS sus assets y 2–3 variantes por semilla, separados en X.
2. Imprime por asset: triángulos (`tri_count`) y `mesh_health`.
3. Renderiza con `clay_render` (res 1280×720, 24–32 muestras) al menos 3 vistas en `entrega/render_qa/kit/<grupo>_*.png`:
   general, primer plano a ~2 m y una vista oblicua. Una persona de 1,80 m (caja 0,45×0,25×1,80) como escala en la vista general.
Mira los renders con la herramienta Read e itera hasta que se vean profesionales: realistas, con escala correcta, ricos en detalle
y sin artefactos.

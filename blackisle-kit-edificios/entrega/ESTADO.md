# ESTADO · Kit BLACKISLE (7 modelos)

Última actualización: 2026-10-09 · Fase actual: **A (preparación) — BLOQUEADA en R1**

## Resumen
| Fase | Estado |
|---|---|
| A · Preparación y verificación | Hecha salvo el paso A-3: **cuota ilimitada no disponible → detenido (R1)** |
| B · Conceptos (Higgsfield) | Pendiente, bloqueada por R1 |
| C · Lettering (Higgsfield) | Pendiente, bloqueada por R1 |
| PC1 · Aprobación del usuario | Pendiente |
| D–G | Pendientes |

| Modelo | Estado |
|---|---|
| APT_A_5p (piloto) | no iniciado |
| APT_B_4p · APT_C_3p · APT_D_4p | no iniciados |
| CAB_1_tablones · CAB_2_pilotes · CAB_3_ladrillo | no iniciados |

## Fase A · resultados medidos
1. **Higgsfield:** conectado. Plan `ultra`, **517,26 créditos**. Un solo workspace (privado, owner, id `98c50264-…`). `get_preferences` → `auto_create_project=false` (no se crea proyecto ni se pasa `folder_id`).
2. **Blender:** no hay conector/MCP de Blender en esta sesión y `download.blender.org` está bloqueado por la política de red (403).
   Instalado **Blender 5.2.2 LTS como módulo `bpy`** desde PyPI en `/root/blk-venv` (Python 3.13.16, numpy 2.5.3, Pillow 12.3.0).
   Verificado: render Cycles OK (320×180, 32 muestras, 1,4 s), horneado AO OK (256², 0,4 s), exportador glTF disponible.
   **Sin GPU** (CUDA/HIP/OptiX no disponibles): Cycles corre en **CPU, 4 núcleos, 15 GB RAM**. Los horneados de 4096² serán lentos pero viables.
   Blender y el sandbox **comparten disco**: el procesado del Apéndice B corre en el mismo sistema de archivos.
3. **Cuota ilimitada (R1):** `models_explore(list, unlim:true)` devuelve
   `unlim = {available: false, remaining: null, expires_at: null}` y **no incluye texto "Unlim configs"**.
   Lo mismo en `get` de `nano_banana_pro`, `gpt_image_2` y `seedream_v4_5`.
   Modelos de imagen marcados `supports_unlim`: soul_2/soul_v2, gpt_image_2, nano_banana, nano_banana_pro, nano_banana_2, seedream_v4_5,
   flux_2, kling_omni_image, seedream_v5_lite, seedream_v5_pro. Ninguna configuración cubierta ahora mismo.
   Historial de transacciones (referencia): el 2026-10-06 Kling O1 Image, Seedream 5.0 Lite, Nano Banana y FLUX.2 Pro costaron **0**
   (ilimitado activo entonces); en cambio Nano Banana 2 = 2 créditos, Nano Banana 2.1 = 2, Seedream 5.0 Pro = 1,25 por imagen.
   → **Detenido. Créditos de pago gastados: 0.** Se pregunta al usuario.
4. **Python local:** PIL 12.3.0 + numpy 2.5.3 OK. `texture_tools.py` (Apéndice B.1) probado aquí:
   salto de borde 135,1 → 17,5 (ruido entre vecinos 18,1); `key_out` alfa 0 en fondo / 255 en contenido; `compose_panel` respeta `keepout`.
5. **Carpeta de entrega** creada (`blackisle-kit-edificios/entrega/`, árbol de §7 + `scripts/`).
   **Referencias** recortadas a (578,149)–(1581,888) en `blackisle-kit-edificios/referencias/`:
   `ref_1_cara_ancha_puerta`, `ref_2_cara_angosta_palafito`, `ref_3_cara_ancha_sombra_casas`, `ref_4_cara_angosta_bloque_azul`,
   `ref_5_casa_madera_2p`, más `ref_grafiti_planta_baja_1` y `ref_grafiti_planta_baja_4`.
   Aún **no subidas a Higgsfield** (se hará al desbloquear R1).

## Rutas
- Repo: `blackisle-kit-edificios/` (rama `claude/gracious-dirac-5f11li`)
- Blender: `/root/blk-venv/bin/python` (módulo `bpy` 5.2.2)
- Utilidades: `entrega/scripts/texture_tools.py`

## Decisiones registradas (R8)
- `scripts/` añadido al árbol de §7 para `texture_tools.py` (no es un script de Blender).
- GitHub rechaza archivos > 100 MB: los GLB se mantendrán por debajo de ese límite (el objetivo de §G ya es ≤ 100 MB).

## Problemas abiertos
- **R1:** cuota ilimitada no disponible. Esperando decisión del usuario.
- **Blender:** se usa el módulo `bpy` local en vez de un conector; pendiente de confirmación del usuario.

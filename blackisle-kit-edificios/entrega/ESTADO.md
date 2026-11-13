# ESTADO · Kit BLACKISLE (7 modelos)

Última actualización: 2026-11-12 · Fase actual: **entrega: los 7 GLB finales horneados, validados y subidos (ver REPORTE.md)**

## Resumen
| Fase | Estado |
|---|---|
| A · Preparación y verificación | Hecha salvo el paso A-3: **cuota ilimitada no disponible → detenido (R1)** |
| B · Conceptos (Higgsfield) | **Hecha.** 25 vistas vigentes descargadas y revisadas con mis ojos (R5) |
| C · Lettering (Higgsfield) | **Hecha.** 15 piezas, ortografía verificada; 31 recortes RGBA en `lettering/cutouts/` |
| PC1 · Aprobación del usuario | **Aprobado** ("dale", 2026-10-09). Se usan los heroes v2/v3 |
| D · Biblioteca de materiales | **Entradas hechas:** 16 texturas 1024² repetibles en `texturas/`. Paneles de grafiti pendientes (dependen de los vanos del modelo) |
| PC3 · Arcilla del piloto | **Hecha** (8 tomas + plantas seccionadas; checklist R12 sin rechazos; ver «PC3 · resultados») |
| E · Modelado | En curso. Kit: G1 y G2 aprobados tras revisión adversarial; G3 y G4 en revisión (con niveles de detalle). APT_A: estructura + interior + vestido G1/G2 |
| PC2 · Biblioteca + panel | Hecho (informativo): `render_qa/PC2_*.jpg`; paneles `texturas/graffiti/G_APT_A_{front,back,west,east}.png` (capa RGBA) + `.jpg` sobre T1 |
| D–G | Pendientes |

| Modelo | Estado |
|---|---|
| APT_A_5p (piloto) | modelado completo: estructura, 4 deptos/piso, escalera interna PB→casetón, 69 vanos, techo de 4 aguas con daño, canalones y bajantes, 34 servicios (13 tipos), daño, base. **829 779 tris**. PC3 hecho; horneado final y exportación GLB en curso |
| APT_B_4p | constructor `apt_b.py`: galería de acceso con balaustrada, 3 deptos pasantes/piso, escalera en U interior, pórtico, colapso SO; grafiti de PB hecho. 727 k tris (medido) |
| APT_C_3p | constructor `apt_c.py`: planta en L, núcleo en la junta, balcones en L sobre postes (marquesina del acceso), 2 techos a dos aguas con limahoyas, hastiales, chimenea. 597 k tris (medido) |
| APT_D_4p | no iniciado |
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

## Decisiones del usuario (2026-10-09)
- **R1:** el usuario reactivará la cuota ilimitada en Higgsfield y avisará. No se gastan créditos de pago; al aviso se re-verifica A-3.
- **Blender:** aprobado el módulo `bpy` 5.2.2 local (Cycles en CPU) como Blender del proyecto.

## Diagnóstico R1 (2026-10-09, 18:10–18:20 UTC) — créditos gastados por Claude: 0
- El usuario sí genera ilimitado en la **web** a 1k. Su historial de hoy: dos FLUX.2 Pro 1k con el mismo prompt y los mismos
  parámetros a las 18:08:21 (−1 crédito) y 18:08:23 (0 créditos). Incluso en la web, uno de los dos se cobró.
- Por la **API MCP** (la que uso yo), una generación real con `use_unlim:true` se **rechaza** en los 9 modelos de imagen:
  "Unlimited generations aren't supported for <modelo>" (nano_banana_pro, gpt_image_2, nano_banana_2 [=nano_banana_flash],
  nano_banana, seedream_v4_5, seedream_v5_lite, seedream_v5_pro, flux_2, kling_omni_image). El rechazo no cobra.
  Saldo antes de estas pruebas 516,26 y después 516,26. El crédito que faltaba respecto a 517,26 corresponde al FLUX.2 Pro de la web.
- Conclusión: el campo `unlim` del MCP es la cuota de "free-trial unlimited". Lo ilimitado del plan Ultra solo aplica en la web
  y la API no lo expone para esta cuenta. No se arregla desde aquí.
- Precios por API (consulta previa con `get_cost`, sin generar): nano_banana_pro 1k/2k = 2 · gpt_image_2 high 1k = 3,5 / 2k = 6,5 /
  low 1k = 0,5 · seedream_v4_5 = 1 · flux_2 pro 1k = 1.
  Estimación del pipeline completo (52 imágenes + 40 % de repeticiones): ~155 créditos con lettering a 1k, ~218 con lettering a 2k.
- **Segundo bloqueo, de red:** el contenedor no alcanza ningún host de Higgsfield (CONNECT 403): `upload.higgsfield.ai` (subida),
  `d2ol7oe51mr4n9.cloudfront.net` (medios subidos), `d8j0ntlcm91z4.cloudfront.net` (resultados), `higgsfield.ai`.
  Sin esos hosts no puedo subir referencias ni descargar resultados (R6), ni siquiera pagando.
  Hay 7 URLs de subida presignadas creadas (caducan en 24 h, sin usar).
- Resolución 1k vs 2k (análisis): 1k basta técnicamente. Una palabra de 3,6 m a 290 px/m necesita 1044 px y un 3:2 a 1k da ~1536 px.
  Un mosaico de 3 m a 170 px/m necesita 510 px. Los conceptos solo sirven para aprobación.

## Autorización de créditos (usuario, 2026-10-09 ~18:18 UTC)
- El usuario ordena: **"usa nano banana 2.1 en 1k, el precio es de 1,5"** → excepción explícita a R1.
  Precio verificado con `get_cost`: 1,5 créditos a 1k (también con `thinking_level: high`).
- Todo B/C/D se genera con `nano_banana_2_1`, 1k, `thinking_level: high`, semilla fija por pieza.

## Referencias en Higgsfield (importadas del repo público con media_import_url)
| Archivo | media_id |
|---|---|
| ref_1_cara_ancha_puerta | 826f5f8a-d0e0-4006-ac4e-8391608353fc |
| ref_2_cara_angosta_palafito | c14a000d-42fe-40e1-a577-4df0f1a259eb |
| ref_3_cara_ancha_sombra_casas | 7fdd05e2-c217-4418-bba7-fdababc96743 |
| ref_4_cara_angosta_bloque_azul | 70ba0369-ca59-4aa1-b9f7-fcec8298f36a |
| ref_5_casa_madera_2p | b2e078a1-50d9-449b-9be1-43ea23500592 |
| ref_grafiti_planta_baja_1 | fc3cbfd2-363d-49ae-9405-876324d21435 |
| ref_grafiti_planta_baja_4 | 67e24312-2560-485c-91e5-bb51766edc9f |

## Generaciones (job_id) y libro de créditos — `nano_banana_2_1`, 1k, 1,5 créditos por imagen
| Lote | Contenido | Enviadas | Filtro nsfw (reembolsadas) | Créditos netos |
|---|---|---|---|---|
| 1 | heroes v1 sin referencias + C01–C05 | 12 | 0 | 18 |
| 2 | heroes v2 con referencias + C06–C08, S01, S02 | 12 | 0 | 18 |
| 3 | elevaciones y primeros planos (C, D, cabañas) + S03, S04 | 12 | 3 | 13,5 |
| 4 | elevación y primer plano A/B + S05–S07 | 7 | 2 | 7,5 |
| 5 | reintento 1 de las bloqueadas | 5 | 4 | 1,5 |
| 6 | reintento 2 (prompt mínimo, entorno natural) | 4 | 0 | 6 |
| 7 | heroes v3 APT_B y APT_D (escaleras internas) | 2 | 0 | 3 |
| 8 | elevación y primer plano B3/D3 + vistas traseras de los 4 departamentos | 8 | 0 | 12 |
| **Total** | | **62** | **9** | **79,5** |
- Saldo: 516,26 → 435,26 (−81,0). Diferencia de 1,5 sin generación asociada: cargo de Nano Banana 2.1 a las 18:18:06 UTC,
  antes de mi primer lote (18:19:47). Coincide con mi primera consulta `get_cost` y no aparece ningún trabajo en el historial.
  Atribución incierta; se informa tal cual.
- Los rechazos `nsfw` son falsos positivos del filtro de salida. Se reembolsan solos.

### Set vigente de conceptos (PC1)
| Modelo | hero | elevación | primer plano | trasera |
|---|---|---|---|---|
| APT_A_5p | d2c82805 (v2) | a38bcdd7 | 07a9622f | d3ceefc1 |
| APT_B_4p | 8ac1d4d9 (v3) | 114509a8 | e5f634d0 | 1c3e07c8 |
| APT_C_3p | 18c151f9 (v2) | 771a18ab | 7de5a0de | c3ae54f0 |
| APT_D_4p | 5dac2101 (v3) | 28ab0d48 | d4a892f8 | 09afc20e |
| CAB_1_tablones | a2b2b4ff (v2) | d4e97b6a | 0848e204 | — |
| CAB_2_pilotes | 1f19e8e4 (v2) | 09e68b08 | 8c897fb7 | — |
| CAB_3_ladrillo | b24ed18c (v2) | 4e2d1b53 | 58fb64a9 | — |
- Alternativas sin referencias (v1): APT_A bf9509c2 · APT_C a1521cb0 · CAB_1 545bedd7 · CAB_2 a56a5132 · CAB_3 c07258a0.
- Obsoletos por la regla de escaleras: APT_B v1 016e5682 / v2 7a0a6e29 (+ a42d1cb5); APT_D v1 26c355c0 / v2 a42aa29a (+ 9c65905c, 92087026).
- Lettering: C01 21e9d88a · C02 0d25f4dc · C03 94f5f0d2 · C04 7d933e77 · C05 d4f3f014 · C06 ef162266 · C07 16f01111 · C08 c1dc06e5 ·
  S01 7de785e8 · S02 ff9aefe3 · S03 5ea8dae7 · S04 426af700 · S05 9028e01f · S06 3aff111c · S07 1d644e07
- Recorte del verde: `key_out` local (gratis, probado). Remove background, autorizado por el usuario, queda como respaldo para las placas
  con contaminación verde en el borde.
- **Sin verificar con mis ojos (R5):** la CDN está bloqueada. La ortografía del lettering está pendiente de revisión al poder descargar.

## CAMBIOS DE DISEÑO ORDENADOS POR EL USUARIO (2026-10-09 ~18:30 UTC) — prevalecen sobre §4 del brief
Cita: "Los modelos de edificios de departamento necesito que tengan entrada trasera y delantera en la parte de abajo.
Y ninguna escalera debe de estar afuera para subir a los cuartos. Las escaleras deben de estar por dentro.
Tienes que construir literalmente toda la estructura del edificio, incluso por dentro."
1. **Los 4 departamentos llevan entrada delantera (cara −Y) y trasera (cara +Y) en PB**, conectadas por el vestíbulo o corredor de PB
   hasta el núcleo de escalera.
2. **Cero escaleras exteriores.** Toda escalera que sube a los departamentos va dentro de la envolvente.
   - APT_A: el núcleo con celosía de bloques queda **dentro de la planta**. La celosía es parte de la fachada y la escalera queda detrás.
   - APT_B: **se elimina la torre de escalera exterior.** Núcleo de escalera interno. Las galerías de acceso se mantienen como
     pasillos-balcón abiertos a los que se llega desde los descansos internos (son corredores, no escaleras).
   - APT_C: escalera interna en el encuentro de las dos alas.
   - APT_D: **se elimina la escalera de emergencia metálica.** Núcleo interno marcado en la cara angosta E por una franja vertical
     de ventilas cuadradas. La pieza firma pasa a ser los balcones en voladizo, las buhardillas y esa franja.
3. **Interior completo** (sustituye al "interior mínimo" de E-8): todos los pisos con departamentos divididos en cuartos
   (estancia, recámaras, cocina, baño), corredor o vestíbulo por planta, muros divisorios con espesor, vanos con marcos y algunas hojas
   de puerta, núcleo de escalera real con descansos y barandal (peldaño 0,17 × 0,28, ancho 1,2 m), azotea o ático accesible.
   Sin mobiliario, con escombro y daño interior.
   Impacto: el bloque "Interior" de §5 sube de 8–25 k a ~60–150 k triángulos por departamento.
   Se añade el atlas `interior` (albedo 4096², normal y ORM 2048²) dentro del presupuesto de ≤ 300 MB, bajando primero las caras traseras.
- Conceptos invalidados por la regla 2: APT_B v2 (torre exterior) y APT_D v2 (escalera de emergencia).
  Rehechos como v3: hero APT_B 8ac1d4d9 y hero APT_D 5dac2101 (lote de 2, 3 créditos).

## Fase D · biblioteca (lote 9, 16 imágenes, 24 créditos; saldo esperado 411,26)
- 10 entradas: T1 concreto (anclado a ref_1), T2 aplanado y pintura, T3 teja, T4 madera, W1 tablones oscuros (anclado a ref_5),
  W2 tablas grises, R1 lámina óxido, R2 tablones grises, S1 ladrillo, M1 metal oxidado.
- 6 máscaras K1–K6 en gris puro. Todo pasado por `make_seamless` y revisado en mosaico 2×2: sin costuras visibles.
- **Pendiente conocido:** S1 y T3 tienen fantasmas (hiladas dobles) en la zona de mezcla. Impacto bajo: en las cabañas, ladrillo y teja van
  como geometría individual. Si el QA a 2 m de los parches de ladrillo de APT_B lo delata, se repara con inpaint (nano_banana_2_1, máscara en cruz).
- Lettering: corrección de verde en todos los píxeles (C01 tenía 10 % y C06 20 % de tinte verde en brillos), erosión de alfa de 1 px y
  hojas S05–S07 separadas en 6 piezas cada una por proyección de alfa. C01 se invirtió a tinta negra con contorno blanco, como la referencia;
  la versión blanca queda como `C01_mi_vida_loca_blanco.png`.

## Decisiones de método (R8, 2026-10-10)
- **Presupuesto:** el interior completo exigido por el usuario no cabe en el techo de 600 k del brief. Nuevo techo **≤ 700 k para departamentos**
  (≤ 300 k cabañas). Se recorta primero el interior (hojas de puertas: saqueo) y se usan niveles de detalle bajos en fachadas secundarias.
- **Texturas del interior:** ~2000 m² de superficie no caben como horneado único a densidad útil. Interior = materiales repetibles PBR a escala
  real (UV de caja 2 m) + oclusión horneada en un 2.º canal UV (glTF occlusionTexture.texCoord=1 → `aoMap` en Three.js).
  Exterior (fachadas, techo, detalles) = atlas únicos horneados según §4.7.
- **Grafiti:** capa RGBA por cara (`compose_graffiti_dense`): tags de fondo → héroes enteros fuera de vanos y sin encimarse → tags →
  íconos únicos → goteos → borrados grises de rodillo que no tapan héroes → desgaste con K1 → desvanecimiento hasta PB+0,7 m.
  Zonas excluidas calculadas de los vanos reales del modelo (`texturas/graffiti/G_APT_A_mapa.json`). Las cortinas metálicas llevan su
  propio grafiti en el atlas de detalles.
- **Reinicio del contenedor (2026-10-09 ~23:45):** se perdió el workflow del kit. Los 4 módulos construidos sobrevivieron en disco (commit ffaa3a3);
  las revisiones de G1/G2 ya estaban completas; las de G3/G4 se relanzaron.

## Presupuesto de APT_A (2026-10-27, medido)
| Grupo | Tris | Nota |
|---|---|---|
| Carcasa (estructura + fachadas + casetón) | 15 172 | |
| Detalles (vanos, celosía, barandales, servicios, bajantes) | 413 174 | ventanas ~126 k · loggias ~72 k · celosía ~71 k · servicios ~100 k |
| Interior (muros, 12 puertas, 5 tramos de escalera, buzones, extintores) | 166 270 | |
| Techo (estructura dañada 50 k + teja `low` 118 k + canalones frente/fondo) | 186 189 | |
| Base (arena, hierba, escombro, varillas de espera) | 36 202 | |
| Daño (mordidas, nidos, escombro interior) | 12 772 | |
| **Total** | **829 779** | +17 % sobre el techo de 700 k: se presenta al usuario en PC3 con palancas para bajarlo |
- Palancas disponibles: teja ya en `low` (high = 351 k); canalón solo frente/fondo (perimetral = 76 k); A/C `low` (2–3 k vs 17–28 k);
  hojas de puertas interiores (12 de 43 vanos). Siguientes recortes posibles: barandales de loggia, celosía más estrecha, ventanas traseras más simples.
- Las revisiones adversariales de G3/G4 se cortaron dos veces (reinicio del contenedor; luego límite semanal de subagentes).
  Los niveles de detalle quedaron implementados y medidos; las pruebas de G3/G4 se re-ejecutan en local para verificar salud y renders.

## Problemas abiertos
- ~~Red~~ **Resuelto:** el usuario habilitó `d8j0ntlcm91z4.cloudfront.net`. Las 52 imágenes de B/C se descargaron (52/52) y se revisaron.
- **Red:** hosts de Higgsfield bloqueados en el entorno cloud.

## PC3 · resultados (2026-10-27)
Tomas en `render_qa/APT_A_5p_PC3_clay_*.png` (Cycles 128 muestras, 1920×1080): 4 esquinas, altura de ojos a 19 m, techo, detalle de PB.
La toma interior del corredor quedó negra (corredor cerrado, sin luz natural): se sustituye por **plantas seccionadas**
(`tests/render_plan.py`: cámara ortográfica cenital con plano de recorte a 1,4 m sobre cada losa y luz de área bajo el corte) →
`render_qa/APT_A_5p_planta_N0.png` y `_N1.png`: PB pasante entrada delantera → vestíbulo → puerta trasera, locales, bodega con WC;
piso tipo con corredor central, 4 departamentos, loggias y escalera en U dentro del núcleo con celosía.
Checklist R12: fachada con relieve (malla de columnas y vigas, rellenos rehundidos 8 cm, loggias de 1,2 m) · repetición a 15 m rota
(ventanas rotas/tapiadas/con cortina variadas, A/C, tendederos) · aristas biseladas · 35 tipos de elementos secundarios · escala humana
(puertas, barandales, buzones, medidores) · sin z-fighting ni piezas flotando visibles · se parece al concepto, no a las capturas. Sin rechazos.

## Cambios de código para B/C/D (APT_A sin cambios, verificado: mismo conteo 829 779 antes del horneado)
- `apt_builder.build_frame`: plantas en L (`cells`, `slab_rects` con vuelo por lado), columnas truncadas (`col_top`), vigas omitidas
  (`skip_beam`), losas con hueco de escalera seleccionables (`stair_levels`) y huecos extra (`holes`); `col_size` con `corner_nodes`;
  `build_skirt` con `footprint` (unión de rectángulos).
- `apt_common.py`: paneles en cualquier línea de malla con varios vanos, vestido genérico, barandales orientados, escalera en U girada,
  recorte por predicado (limahoyas), bajantes en cualquier fachada. `builders.py` (registro por ID), `tests/render_clay.py`,
  `tests/render_plan.py`, `graffiti_apt.py` (grafiti por ID; el compositor avisa si una pieza no cabe).
- `kit/circulation.BAL_SEG`: lados del balaustre configurables (8 en la galería de APT_B: −21 k tris).

## Fase F · cambio de estrategia de horneado (2026-10-27, verificado con mis ojos)
El primer horneado completo de APT_A produjo atlas de **muros** correctos (`walls_main` 4096, `walls_rest` 3072: pintura descascarada,
grafiti, AO) pero el atlas de **detalles** salió inservible: ~400 k triángulos en decenas de miles de piezas sueltas = decenas de miles de
islas UV; con el margen de empaquetado cada isla queda en 1–3 píxeles (manchas sueltas sobre negro). Lo mismo en techo (teja suelta) y en
la base (hierba). Además falló al final por el nombre de la capa UV de caja (`Float2` en Blender 5.2, no `UVMap`).
Nueva estrategia (R8):
- **Atlas únicos** solo donde hay superficies continuas: muros exteriores (`walls_main`, `walls_rest`) y terreno de arena (`skirt`).
- **Detalles, techo, interior, hierba y escombro:** materiales PBR repetibles a escala real (canal de caja a 2 m/unidad + KHR_texture_transform)
  y **oclusión ambiental horneada por vértice** en el atributo de color `AO` → glTF `COLOR_0`, que por especificación multiplica el color base
  (Three.js lo aplica solo). Los materiales de color liso (vidrio, tela, plástico, cable, escombro, hierba…) se funden en uno o dos
  materiales (`liso`, `liso_2c` de doble cara) con su color × AO en `COLOR_0`. Resultado: ≤ 14 materiales y mucha menos memoria.
- Probado de punta a punta con CAB_2 (`--quick`): GLB con `POSITION/NORMAL/TEXCOORD_0/COLOR_0`, 12 materiales, render con materiales correcto.
- `bake_apt.py --reuse` reutiliza los PNG de atlas ya horneados (misma geometría y desenvuelto deterministas).
- Lámina clara de CAB_2: nueva textura `R2_roof_corrugated_light.png` derivada de R1 (gris galvanizado con el óxido intenso conservado).

## Corrección R4 en el grafiti (2026-10-27, revisado con mis ojos)
- Al revisar los paneles de APT_B vi que el ícono `S06_hoja_iconos_02` es una **corona de 5 puntas** y que el héroe `C02_isla_negra`
  llevaba encima una corona de 5 puntas en negro y dorado. Junto con la **estrella de 5 puntas** (`S06_hoja_iconos_04`), es simbología
  de una alianza de pandillas real: R4 lo prohíbe aunque cada pieza por separado parezca genérica.
- Corregido: corona borrada del recorte `C02_isla_negra.png` (queda solo el lettering gótico), íconos 02 y 04 fuera de todos los sets
  (`graffiti_apt_a.py`, `graffiti_apt.py`), paneles de A/B/C/D regenerados y revisados uno por uno (16 caras): sin coronas ni estrellas.
  Íconos vigentes: calavera con rosas, corazón, ojo, máscaras. Se re-hornea el atlas `walls_main` de los 4 departamentos.
- Compositor: los goteos y manchas ya no caen sobre los héroes (antes una mancha azul tapaba "Puro" en APT_A este).

## Auditorías de circulación y geometría (2026-10-27/28, workflows con verificación adversarial)
Un auditor por modelo (código + plantas seccionadas + sondas `bpy` con rayos, BVH y cápsula de jugador r 0,25 · h 1,8 · escalón 0,35);
cada hallazgo grave pasa por un verificador independiente que intenta refutarlo con su propia sonda. Todo lo aplicado se re-comprobó
con sondas y plantas nuevas (`render_qa/*_planta_N*.png`).
- **APT_A:** casetón con descanso de llegada (muro oeste a x = 2,30), loggias con puertas abiertas, puerta de cocina libre de la
  columna, barandal en azotea, ventila de PB sobre el descanso, recorte del armazón del techo sin teja suelta.
- **APT_B:** hojas de puerta que sellaban vestíbulo y deptos, local este sin acceso, particiones que cruzaban ventanas, rendija perimetral,
  tendederos flotando, bajantes metidos en columnas.
- **APT_C (11):** núcleo abierto al depto norte sin barandal (grave), muro x = 1,2 faltante en pisos altos (grave), local oeste sin puerta
  (grave), local sur sin acceso, puerta de balcón partida por una partición, puerta tapada por columna, ventanas, parabólica, bajantes.
- **APT_D (10):** cuartos de los balcones sellados por el muro del baño (grave), zócalo y junta cruzando las 4 puertas de PB (grave),
  caída del descanso a la bodega trasera, puerta de entrada partida, parabólica/medidores/A/C/tendederos/arbotantes mal anclados,
  ranura de 13 cm junto a la escalera.
- **Cabañas (26 + re-auditoría):** 7 graves verificados (CAB_1: puerta delantera partida por la partición y trasera contra el bajo de
  la escalera; CAB_2: escombro y pendolones flotando, escalera de mano atravesando el tapanco; CAB_3: escalera inaccesible por el
  barandal, cuarto alto sin puerta, porche 0,30 m sobre el piso con 1,72 m bajo el dintel y escalones contra poste y viga a 1,40 m).
  Re-auditoría: todos corregidos; 19 regresiones/pendientes menores resueltos en una segunda ronda (puertas con paso ≥ 2,0 m, escalón
  trasero de CAB_3, arena que no tapa escalones, hierba fuera de umbrales, etc.).

## Recorrido interior en Three.js y defectos que destapó (2026-10-28, revisado con mis ojos)
`visor/recorrido/walk.html` + `walk.mjs`: el GLB final con GLTFLoader (r169) en Chromium, cámara a 1,65 m, sol con sombras, cielo y
bombillas; tomas en `render_qa/recorrido/`. Defectos encontrados y corregidos en el pipeline (afectan a los 7 modelos):
1. **Aplanado interior naranja saturado y a escala de ~1 m** (T2 sin tinte en el repetible): variante `T2_old_plaster_paint_int.png`
   (pintura gris sucia sobre concreto) a 1,2 m por repetición.
2. **AO por vértice rota (causa raíz de los "cuadros")**: la escena del horneado no tenía world y Cycles medía la AO sin distancia corta;
   dentro de un edificio cerrado todos los rayos chocaban y el **95 %** de las esquinas salía en 0; el arreglo por cara las volvía
   cuadros. Ahora: distancia 0,5 m y horneado sobre una copia con caras separadas y esquinas movidas 3 cm hacia su cara → esquinas
   muertas 9 % (interior) / 15 % (detalles), que son piezas realmente encerradas; después se promedia por posición y orientación.
3. **Mosaico en piezas giradas**: el mapeo de caja elegía eje por cara en ejes del mundo; ahora se alinea por pieza conexa.
4. **z-fighting** (`tests/zfight.py`, caras coplanares superpuestas visibles): CAB_3 interior 6,9 → 0,08 m² (duela sobre la losa),
   CAB_1 4,1 → 0,7 (durmientes bajo las vigas), CAB_2 3,8 → 0,2 (diagonales de las cruces), esquineros sin solape, APT_D 308 → 30 m²
   (la cornisa era un bloque que duplicaba la losa de azotea; lo restante son tapas de muro encerradas).

## Revisión de aceptación (2026-10-28, workflow con verificación adversarial) y ronda 3 del pipeline
Un revisor por departamento contra R12, R4, la regla de color y la del usuario (finales, capturas Three.js, recorrido, plantas,
paneles); cada hallazgo medio o grave pasó por un verificador que intentó refutarlo. Veredictos: A rechazo, B aceptar con
correcciones, C rechazo, D aceptar con correcciones. Confirmados (y corregidos en el pipeline común, re-horneando los 7):
- **Color (B, C, grave):** la pintura descascarada dejaba ver ladrillo en todos los pisos → bajo la pintura queda repellado gris y el
  tabique solo asoma en parches grandes, más en PB. Descascarado por zonas (humedad, zócalo, esquinas), pintura menos saturada,
  óxido más escaso y apagado (camuflaje marrón en D y A). Teja −28 % de saturación.
- **Ático traslúcido (A, grave):** teja de una cara → `t_tile` de doble cara (cubre y da sombra desde dentro).
- **Cuartos negros, hueco negro en C_04, panel de fachada en C_06, machón de D (medios/graves):** caras interiores de muros de
  fachada clasificadas como exteriores (sin tabiques como oclusores; en D además por una enfilada de puertas alineadas) → interior
  como oclusor y un rayo que escapa solo cuenta si recorre ≤ 3 m dentro de la planta; AO de los atlas con mínimo 0,35.
- **Vidrio de cartulina (A, medio):** material `t_glass` propio, oscuro y brillante (rugosidad 0,1). `liso` único de doble cara.
- **Aplanado interior en papel tapiz (B, medio):** `T2_plaster_int_2k.png` (2048² a 2,4 m, periódico por construcción).
- **Props lisos (B, medio):** escombro con textura de concreto; tela con color desteñido por pieza.
- **Grafiti poco legible (C, medio):** piezas protagonistas más grandes donde caben y alfa ×1,3.
- **Muro blando a 2 m (A, medio):** banda de PB ×2,0 dentro de `walls_main` y normal de `walls_main` a 2048 (+16 MB).
- **Interiores sin escombro (D medio, C bajo; en B refutado: la orden del usuario es la estructura):** `interior_dress.py`
  (escombro de aplanado, basura, focos colgando, apagadores, algún colchón y silla rota) solo donde los rayos ven un cuarto cerrado.
- R4 (bajo, pero se corrige): las dos estrellas de 5 puntas dentro de la pieza ZORO, borradas; 16 paneles regenerados y revisados.
Refutados: logias "idénticas" de A, 'Mi Vida Loca' (está en la lista del brief), buzón de D (se movió igual a 1,6 m del vano).
z-fighting: `coplanar.py` borra caras cubiertas y hunde 3 mm las parciales antes de hornear (D: 16,2 → 0,9 m² visibles);
`tests/zfight.py` ahora prueba visibilidad con 5 rayos hasta 100 m y descarta caras bajo el suelo.

## Reinicio del contenedor (2026-11-12)
El contenedor se reemplazó: se perdieron el módulo `bpy` (reinstalado: Blender 5.2.2 LTS en /root/blk-venv), las herramientas
del scratchpad y lo no subido (vestido interior, re-horneado de C y CAB_1 de la ronda 3). El vestido se reescribió desde la
sesión; las herramientas de captura y la cadena ahora viven en el repo (`visor/captura/`, `scripts/cadena_horneado.sh`).
Re-horneado completo de los 7 con el pipeline final en curso.

## Entrega final (2026-11-12)
Re-horneado completo de los 7 con el pipeline de la ronda 3 (`scripts/cadena_horneado.sh`), exportación y validación OK en todos,
renders Cycles, recorrido interior y capturas exteriores en Three.js r169 revisados con mis ojos. Números en `REPORTE.md` §1.
z-fighting visible (`tests/zfight.py --dedupe`): 0 m² en los 7. Toma 04 de CAB_2 rehecha agachada (la cámara estaba dentro de la
lámina; el tapanco tiene 1,2–1,5 m libres).

## Kit para Unreal Engine 5 (2026-11-12)
Pedido del usuario: un kit que otro chat lea e importe en UE5 para reemplazar los edificios provisionales, con vidrio que se
vea como vidrio y materiales con su forma y tono exactos; **sin arena ni pasto alrededor** (solo el suelo propio del edificio),
el escombro exterior como pieza suelta. Hecho:
- `bake_apt.py --ue` re-horneó los atlas de muros **sin la arena** (tapaba el zócalo hasta 0,32 m) y separó los materiales por
  tipo (`BLK_*`); `export_ue5.py` escribe un GLB por pieza (Estructura, Detalle, Escombro, Vidrio, Colision) con el mismo pivote.
- Texturas PBR de los 11 repetibles (normal DirectX + ORM), máscara de suciedad del vidrio, marcador de ejes, `manifiesto.json`,
  `importar_blackisle.py` (Python del editor de Unreal) y `LEEME_UE5.md`. Validación por reimportación OK en los 7.
- Vista previa en Cycles armada solo con los archivos del kit: `render_qa/ue5/<ID>_ue5_{exterior,interior}.png`.
- Descargas: `kit_ue5_descargas/` (ZIP común 53 MiB + uno por modelo, 9–31 MiB).
- No probado dentro de Unreal (no hay motor en este contenedor): el script sigue la API de Python de UE 5.x y el LEEME deja la
  especificación para corregirlo si alguna llamada cambia en la versión del proyecto.

## Nuevo modelo: MUE_1_carga (muelle de carga) · referencias (2026-11-12)
Pedido: muelle de carga en la orilla de la playa con almacén de estructura metálica, espacioso, con atraque para un barco y
acceso por rampa desde la arena; grafiteado como el resto del kit. Generado con `nano_banana_2_1` a 1k (indicado por el usuario),
ancla de color y desgaste: hero de APT_A (d2c82805) y `ref_grafiti_planta_baja_1`. 6 imágenes, 0 rechazos, **9,0 créditos**
(saldo 259,25 → 250,25, plan plus). Revisadas con mis ojos; en `refs_higgsfield/MUE_1_carga/`:
| Vista | job | Qué fija |
|---|---|---|
| hero (desde la playa) | 0937ffb0 | rampa de concreto desde la arena con muretes grafiteados, cubierta sobre pilotes de acero con cruces, nave de marco rígido oxidado con lámina faltante y tragaluces, caseta de oficina, grúa pluma, contenedores, defensas de llanta |
| mar (desde el agua) | 04c46596 | frente de atraque: defensas de llanta y de madera con percebes, bitas, escalera marina, cortinas metálicas, contenedores grafiteados |
| elevación lateral | e9568eb8 | proporciones: rampa ~1/5 del largo, cubierta a ~3 m sobre el mar, 7 marcos de pilotes con cruces, nave de ~3/4 del largo, grúa en la punta |
| aérea | 39d8f79e | planta en L: cubierta principal + espigón de atraque paralelo a la costa; caseta junto a la nave |
| interior | c1b0826d | nave con marcos y armaduras oxidadas, tragaluces rotos, entrepiso de oficina con escalera, arena y tarimas |
| materiales | 250e8ba0 | concreto con óxido y sal, viga con pintura gris verdosa descascarada, lámina grafiteada, bita, llanta en cadena, pilote de madera con percebes |
- R4: palabras vistas KAOS, ZORO, NOVA, REXO, Puro Corazón, Sin Miedo, Respeto, más "NEXO" y "KORO" (deformaciones del modelo),
  ojos, máscaras, corazones. Sin números de pandilla, coronas, estrellas, marcas ni logos. El grafiti del modelo 3D se compondrá con
  las piezas propias del kit (`lettering/cutouts/`), no con estas imágenes.
- Diferencias entre vistas: en la aérea la rampa baja al agua (rampa de botes); manda el hero/elevación (rampa desde la arena).


## MUE_1_carga · modelado (2026-11-12)
Constructor `blender/mue_builder.py` + piezas portuarias `blender/kit/port.py` (revisadas en primer plano con
`tests/render_piezas.py`). Cotas: arena z 0, mar −0,5, cubierta +2,5, pilotes a −7; pivote (0, 0, 0) en el eje de la rampa
en la orilla de la cubierta. Ajustes pedidos por el usuario sobre el primer pase:
- **Rampa ancha:** del ancho completo de la cubierta (47,4 m libres; pretiles a ras de las trabes), 25 m al 10 %, sobre
  terraplén con muros de contención, coronamiento, barandal de tubo, aleros abiertos al pie, guarniciones, juntas de acero
  cada 5 m, estrías antiderrapantes, rejilla de drenaje de lado a lado, placa de transición atornillada y estribo bajo la
  cubierta. Arena arrastrada por el viento contra los pretiles.
- **Espacio para vehículos:** carriles de 9 m o más alrededor de la nave; los objetos sueltos van contra muros y orillas.
- **Detalle realista (fuera "bloques"):** grúa de pedestal con pluma de celosía de ángulos, poleas, cables y gancho (pluma
  sobre el atraque); postes octagonales con luminaria tipo cobra; bitas en T con anclas; llantas con dibujo colgadas de
  cadena; defensas de madera con flejes; escaleras marinas; contenedores ISO con puertas, barras de cierre y bisagras;
  tambos con aros. Nave: crujías de 6 m (se quitó un marco duplicado en y = 10), placas base con anclas y mortero,
  postes de hastial, largueros Z con clips, largueros de muro C, contraventeo con tensores, cortinas y puerta fuera de
  las líneas de columnas, juntas de acero en la cubierta.
- Defecto encontrado en arcilla: zócalos de frente y costado encimados en las esquinas (caras coplanares, franjas negras);
  corregido arrancando el zócalo lateral dentro del de frente/fondo.
- Kit UE5: colisión simple añadida para grúa, postes y bitas; ficha con `niveles_m` y `medidas_estructura_m`; el
  importador compara la Estructura contra esa medida; vista previa con playa y mar; atlas de muros a 8K (superficie
  exterior ~2x la de un edificio).
- **Exportado al kit UE5 (2026-11-12):** `bake_apt.py --ue` + `export_ue5.py` OK, todas las comprobaciones en verde.
  Triángulos: Estructura 95 980 · Detalle 420 172 · Escombro 8 872 · Vidrio 5 258 · Colision 62 067. Medidas del modelo
  80,0 × 90,0 × 24,0 m (Estructura sola 80,0 × 80,5 × 12,8 m); 31,8 MiB. z-fighting visible: 5 caras, 0,065 m² (Detalle 2,
  Interior 3; muros, techo y escombro en 0). Vistas previas con playa y mar en `render_qa/ue5/MUE_1_carga_ue5_*.png`
  (exterior, playa, mar, atraque, interior), revisadas con mis ojos. ZIP `kit_ue5_descargas/BLACKISLE_UE5_MUE_1_carga.zip`
  (28,8 MiB); el común se rehízo (LEEME, manifiesto e importador con el muelle).
- Pendiente menor: los tragaluces usan el vidrio del kit (transparente); en la realidad serían de fibra translúcida.

## Nuevo modelo: HOS_1_pueblo (hospital rural) · referencias (2026-11-12)
Pedido: hospital sencillo de una sola planta, de pueblo mexicano pequeño (no avanzado), con cochera para ambulancias al lado,
exterior e interior completos, grafiti moderado (está en funcionamiento: menos descuidado que cabañas y departamentos) y todo
texto en inglés. Generado con `nano_banana_2_1` a 1k; ancla de grafiti `ref_grafiti_planta_baja_1` en las vistas exteriores.
7 imágenes, 0 rechazos, **10,5 créditos** (saldo 241,25 → 230,75, plan plus; entre el cierre del muelle y este lote el saldo
ya había bajado de 250,25 a 241,25 sin generaciones mías en esta parte de la sesión: se informa tal cual).
Revisadas con mis ojos; en `refs_higgsfield/HOS_1_pueblo/`:
| Vista | job | Qué fija |
|---|---|---|
| hero | 9d79cacc | fachada de block aplanado crema con zoclo verde, pórtico de columnas cuadradas, rampa con barandal, ventanas con herrería verde, letrero pintado COMMUNITY HOSPITAL en el pretil, placa azul con H, tinacos, cochera de 2 cortinas a la derecha, barda con tags |
| cochera | 15d922bd | cochera de 2 bahías con cortinas, plataforma con NO PARKING, marquesina de lámina hacia la puerta EMERGENCY, tags parcialmente tapados con parches de pintura |
| trasera | 4b2c5cfb | puerta STAFF ONLY, medidores, condensadoras en ménsulas, jaula de cilindros de gas, botes, tendedero, tinacos sobre base metálica, barda de block con tags |
| aérea | 11f967c4 | planta rectangular con patio interior y árbol, pórtico al frente, cochera a un lado con plataforma, barda perimetral con portón, estacionamiento |
| recepción | 1cd8578f | muros a dos tonos (verde claro / blanco), terrazo, sillas azules en viga, ventanilla RECEPTION, WAITING ROOM, EXIT, oficina con cancel, plafón de placas, ventilador de techo |
| pasillo | 4552b24b | pasillo con pasamanos de madera, puertas de tablero verdes con letreros EXAM, NURSES, PHARMACY, X-RAY, WARD; sala con camas de tubo, cortinas en riel, portasueros, silla de ruedas y camilla |
| materiales | bb04c380 | aplanado con zoclo, terrazo, herrería verde, cortina con tag tapado, rotulado EMERGENCY, muro a dos tonos, rampa con borde amarillo, azotea con tinaco, azulejo blanco |
- R4: tags solo KAOS, ZORO, NOVA, REXO, corazones y ojos. La cochera trae "Mi Vida Loca" (frase en español): no se usará en el
  modelo porque el usuario pidió todo el texto en inglés. Textos que fallan en las imágenes ("WASN YOUR HANDS", "PHADMACY",
  marca ilegible en un tinaco) se corrigen o se omiten al modelar. Sin cruz roja, estrella de la vida ni logos.
- Las ambulancias de las imágenes son solo contexto: un vehículo no va dentro de la malla estática del edificio.

## REGLA R-AAA (orden del usuario, 2026-11-12) — prevalece
Cita: "Tiene estrictamente prohibido pasar por alto detalles que se vean rápidos o hechos de forma rápida. No quiero un escenario
low poly. Quiero un escenario AAA. Con un chingo de triángulos, no menos de 100,000 triángulos... Tu cama parece una cama de
Roblox... tu almohada parece una piedra... Si se ven como cajas de cartón, no sirven."
Registrada en `CLAUDE.md` (raíz del repo) con sus 6 puntos: sin piezas rápidas, lo blando subdividido con arrugas y costuras,
bisel y curvas reales en lo rígido, ≥ 100 k triángulos por modelo, revisión de primer plano a < 2 m antes de integrar y reporte
honesto de lo que quede por debajo. La primera lámina del mobiliario del hospital (cama, almohada, asientos) queda rechazada.

## HOS_1_pueblo · modelado, revisión R-AAA y kit (2026-11-12)
- **Camas (rechazo del usuario: "cama de Roblox", "almohada de piedra")**: la sábana y la cobija simuladas como rectángulos se
  arrugaban en picos al caer por el canto del colchón (y con las normales del colisionador invertidas quedaban DENTRO del
  colchón: en el GLB no se veían). Se reemplazaron por un tendido a la medida (`softgoods.bed_linens`): bajera remetida en los
  4 lados con frunces de esquina, arrugas de tensión y pliegues de planchado; cobija remetida con esquina de hospital (pliegue
  diagonal con escalón de solapa); sábana superior con embozo de doblez redondeado; dobladillos. Colchón con las 12 aristas
  redondeadas y vivos sobre la costura (antes flotaban 1 cm). Cama sin cobija: cobija doblada blanda al pie. Revisado a < 2 m
  (pie, cabecera, embozo, esquina). 70,7k triángulos por cama tendida (el colchón tapado ya no lleva vivos ni cierre).
- **Revisión de primer plano de TODO el mobiliario** (`tests/render_pieza.py`, nuevo): 27 piezas de 300–3 000 triángulos se
  leían como cajas (lavadora = caja + aro, garrafón octagonal, luminaria = placa, mostrador = caja, etc.). Rehechas con su
  construcción real en `kit/clinic_servicios.py` (lavadora, refrigerador, estufa, despachador, lavabo, inodoro, cubeta con
  exprimidor, botes, gel), `kit/clinic_oficina.py` (escritorio con monitor/teclado/teléfono, archivero, mostradores de
  recepción y cocina, sillas, buró, tablero, reloj, planta) y `kit/clinic_equipo.py` (luminaria de rejilla con tubos T8,
  ventilador, minisplit, extintor, cilindros de oxígeno y de gas LP, rayos X, bucky, mampara plomada, farol); `kit/clinic.py`
  las enruta. Además: pasamanos de madera con remates y ménsulas y mesa de comedor de tubo (eran cajas en el constructor).
- **Error corregido**: estufa, refrigerador, mostrador de cocina y lavadoras miraban al muro.
- **Presupuesto**: el mobiliario completo llegó a 2,8 M triángulos y el GLB no puede pasar de ~95 MB (GitHub). Se recortó lo
  que nunca se ve (traseras contra muro, fondos, interiores, lo tapado) y segmentos de tornillería; a < 2 m no cambia nada; de
  muy cerca (< 0,5 m) se notan facetas en el plato de la planta, el aro del reloj, el cordón del teléfono, las mechas del
  trapeador y el tubo del cespol. Resultado: mobiliario 1,60 M + detalle 0,41 M = 2,02 M triángulos.
- **Kit UE5**: el mobiliario del hospital va en su propia malla `SM_HOS_1_pueblo_Mobiliario` (constructor → horneado →
  exportación → manifiesto → importador), con colisión de cajas en Colision; el empaquetador reparte un modelo de más de
  95 MB en `_parte2.zip`. LEEME §3/§3.2 al día.
- **Por debajo del estándar, dicho con honestidad**: sin interiores en refrigerador y horno (cerrados); papeles y avisos sin
  imagen impresa; teclas sin rotular; la cubeta conserva 3 caras de mechas que se tocan; ninguna pieza tiene desgaste
  geométrico (golpes, abolladuras) porque el hospital está en uso y limpio; el pasillo cubierto y los exteriores (bancas de
  concreto del patio, tendedero) siguen siendo piezas sencillas del constructor.
- **Revisión de la vista previa texturizada (primera exportación con Mobiliario)**: camas con sábana, embozo y cobija visibles;
  pasillo con pasamanos nuevos; sala de espera, encamados y fachadas leídas a ojo. Dos errores encontrados y corregidos antes
  del horneado final: (1) el aplanado exterior seguía muy descascarado (umbral de pelado de "edificio en uso" casi igual al de
  abandono): ahora el umbral sube con el desgaste (0,52 + 0,70·(1−wear); los demás edificios, wear 1, quedan idénticos);
  (2) el lambrín y el zoclo tapaban el metro inferior de las 4 puertas exteriores y entraban a la colisión (la tolerancia de
  huecos era menor que el grueso del muro exterior): corregido y verificado (coinciden exactamente las 4, sin falsos).
- **Entrega final al kit UE5** (horneado 14 min, exportación validada): Estructura 10 168 · Detalle 388 886 · **Mobiliario
  1 574 647** · Vidrio 17 520 · Colision 9 144 triángulos (≈ 2,0 M). GLB del mobiliario 84,6 MB, detalle 21,5 MB;
  `kit_ue5_descargas/BLACKISLE_UE5_HOS_1_pueblo.zip` 38,6 MiB (un solo ZIP) + común rehecho (65,8 MiB). Vistas previas
  finales en `render_qa/ue5/HOS_1_pueblo_ue5_{calle,urgencias,trasera,pasillo,encamados,interior}.png`, revisadas a ojo:
  fachada mantenida, puerta principal hasta el piso, camas tendidas visibles.

## Nuevo modelo: GRA_1_tienda (granero con tienda comunitaria) · referencias (2026-11-12)
Pedido: un granero y al lado una tienda comunitaria chica para comprar suministros (medicinas, comida, munición y cerveza), en
una granja con algo de ganado que **no** se modela. Generado con `nano_banana_2_1` a 1k (thinking medium); ancla de estilo de
grafiti `ref_grafiti_planta_baja_1` en las vistas exteriores. 8 imágenes + 2 hojas de lettering, 0 rechazos, **15 créditos**
(saldo 224,75 → 209,75, plan plus). Revisadas con mis ojos; en `refs_higgsfield/GRA_1_tienda/`:
| Vista | job | Qué fija |
|---|---|---|
| hero | 8301fcd0 | granero de tablas rojas sobre base de block con techo a dos aguas quebrado (gambrel) de lámina galvanizada, puerta de heno con viga y polea, puertas corredizas con cruz; tienda COMMUNITY STORE de aplanado amarillo pálido con zoclo azul, tejaban de lámina en postes, lista MEDICAL - FOOD - AMMO - COLD BEER |
| tienda | f82ce81c | frente de la tienda: puerta con reja, ventanilla con barrotes y repisa de madera, letrero OPEN, pizarrón, congelador, cajas de envases, banca, medidor |
| granero | cb4d1517 | frente del granero (se toma el techo gambrel del hero, no la buhardilla de esta vista), puerta corrediza con FEED, pacas, costales, carretilla, tarimas, bebedero |
| trasera | 28a2193c | tejaban lateral con pacas y costales, corral vacío de rajas, tinaco sobre base de acero, jaula de cilindros, condensadora |
| tienda_int | 8e36e295 | mostrador de madera con malla, gabinete de acero y vidrio para munición, botiquín con cruz verde, anaqueles de abarrotes, refrigerador de cerveza, congelador, báscula, pizarrón (con faltas de ortografía: se corrigen al modelar) |
| granero_int | 4b3b3b49 | estructura de postes y vigas con tornapuntas, tapanco con escalera y pacas, corrales vacíos, banco de trabajo, cuerdas, foco colgante |
| aérea | 13e42c9f | distribución: granero con tejaban y corral al poniente, tienda 4 m al oriente con tinaco, patio de tierra, alambrado |
| materiales | 53694951 | tabla roja, lámina con óxido, block, aplanado amarillo con zoclo azul, poste con herraje, piso de barro rojo, paca, reja verde |
- **Regla R-GRAF (nueva, CLAUDE.md):** solo grafiti callejero cholo/chicano (placas, firmas, piezas, arte callejero), sin
  ilustraciones propias; aquí **solo un par** en un costado del granero. Las referencias traen de más: no se copian.
- **Biblioteca exclusiva** (`lettering/gra/`, jobs 99c6e52f y 799732a7, recortadas con el verde muestreado y despill):
  G01 placa gótica DRY CREEK con roll call SPARKY / TOPO / FLACO y G02 firma script "Sparky" (las dos que van al granero);
  G03/G04 variantes alternas. Nombres ficticios, sin números, coronas, estrellas ni puntos (R4).

## GRA_1_tienda · modelado (2026-11-12)
- **Arquitectura** (`blender/gra_builder.py`): granero gambrel 12 × 16 m (base de block, tabla roja con tapajuntas como
  geometría, esquineros y chambranas blancas, techo de lámina ondulada real con tornillos con rondana, caballete, botaguas del
  quiebre y frontales; pares cada 1 m con cartabones, tirantes y polines), estructura interior de postes 20 × 20 en dados con
  estribos, vigas de amarre, solera, tornapuntas con pernos, largueros, tapanco de tablones; portón corredizo de dos hojas en
  riel con carros, puerta del tapanco con viga de polea, ventanas con postigos abiertos, ventila de tablillas; tejaban
  poniente. Tienda 6 × 8 m de block aplanado (amarillo, zoclo azul por lookdev), losa con pretil, piso de barro, lambrín azul,
  pórtico con tejaban de lámina en postes rollizos, reja de seguridad abierta, ventanilla con barrotes y repisa, letreros
  pintados en relieve, medidor, tinaco en base de ángulo, condensadora, bajada pluvial.
- **Texturas nuevas** (`tools/texturas_granja.py`): T10 tabla roja de granero (deslavada, desprendimientos sueltos, veta y
  clavos), T11 block 40 × 20 con junta rehundida, T12 barro 30 × 30. Materiales nuevos: wood_red, block, tile_clay,
  paint_cream, paint_navy, hay, burlap, cardboard, amber.
- **Utilería AAA** (agentes, revisada por mí en hojas de primer plano): `kit/farm.py` 21 piezas (pacas con tajos e hilos,
  estibas, paja suelta, costales que se amoldan, tarima, carretilla, bieldo, pala, bebedero, cubeta, banco con tornillo y
  herramientas, escalera, polea, cuerda, foco, gabinete, corrales, cerca de rajas, alambrado de púas, tambo); `kit/store.py`
  16 piezas (mostrador con malla, gabinete de munición sin armas, botiquín de cruz verde, anaqueles surtidos de latas,
  costales, garrafas…, refrigerador de cerveza, congelador, báscula, caja de dinero, pizarrón bien escrito, jabas, banca,
  letrero OPEN, calendario, estiba de cajas). Orientación verificada en arcilla (anaqueles, refrigerador y pizarrón con la
  espalda al muro).
- **Revisión en arcilla a < 2 m**: portón, hastial, interior del granero, corrales, tapanco, banco, tejaban, frente de la
  tienda, pórtico, mostrador, abarrotes y fondo. Arreglado: el cruce de las cruces del portón (diagonales coplanares → la
  segunda en dos tramos que topan contra la primera).
- **Triángulos antes de hornear**: estructura/detalle ~0,33 M (techo 170 k, detalle 134 k, interior 30 k) + mobiliario 0,77 M.
- **Horneado y kit UE5** (atlas de muros a 4K: con 8K y 1,1 M de triángulos el horneado se quedaba sin memoria): exportación
  validada (todas las comprobaciones OK). SM_GRA_1_tienda: Estructura 199 930 · Detalle 131 637 · **Mobiliario 767 630** ·
  Vidrio 2 730 · Colision 9 144 + cajas de la utilería (31 012) triángulos; 66,05 MiB; `kit_ue5_descargas/BLACKISLE_UE5_GRA_1_tienda.zip`
  30,4 MiB; común rehecho (75,7 MiB) con T10/T11/T12 y los materiales nuevos.
- **Revisión de las vistas texturizadas** (patio, tienda, costado, tejaban, trasera, granero, interior): arreglados antes del
  horneado final (1) los cartabones del quiebre, que asomaban como dientes sobre la lámina; (2) las tarimas recargadas,
  giradas sobre su centro (media tarima bajo el piso: fallaba base_en_suelo); (3) aplanado de la tienda menos gastado
  (wear 0,15); (4) la vista previa enciende los focos del granero y las luminarias de la tienda (interiores negros).
- **Por debajo del estándar, dicho con honestidad**: cuerdas, alambres, peldaños y tubos chicos de 4–8 lados se facetan a
  < 1 m; los costales no son simulación de tela (trama insinuada); los hilos de púas van cada 30 cm (los reales, 10–13 cm);
  la mercancía de los anaqueles sale de unas pocas piezas repetidas con variación; las letras del pizarrón usan la fuente de
  Blender inclinada, no letra a mano; el refrigerador de cerveza no tiene condensador atrás (va contra el muro).

## Nuevo modelo: COM_1_antena (sitio de telecomunicaciones) · referencias (2026-11-12)
Pedido: un puesto de antena de comunicaciones **actual (tipo 2026), no futurista**, con su centro (caseta de equipos), no muy
grande, para cubrir una ciudad pequeña. Generado con `nano_banana_2_1` a 1k (thinking medium): 8 imágenes, 0 rechazos,
**12 créditos** (jobs 29e35fa2, 7b236343, 838bc0df, 9aa11167, 610a01b7, b9b5795e, 666505a1, eff7c255). Revisadas con mis
ojos; en `refs_higgsfield/COM_1_antena/`:
| Vista | Qué fija |
|---|---|
| hero | torre autosoportada de tres patas tubulares galvanizada (~40 m) con plataforma de sectores arriba, compound con malla ciclónica y alambre de púas, caseta prefabricada de concreto gris claro |
| base | patas tubulares sobre dados redondos con placa base y anclas, escalera de gato con riel, escalerilla de cables (coaxiales negros + 2 fibras amarillas) que baja al puente de cables (ice bridge) en postes hasta la caseta, barra de tierra de cobre, gabinetes blancos en losas, marco H con medidor y desconectador, banquetas de concreto sobre grava |
| antenas | plataforma triangular con barandal y rejilla: paneles de 2,6 m, AAU 5G masivas, RRU con aletas, jumpers con gaza de goteo, platos de microondas con radomo de tela y ODU, baliza roja |
| aérea | distribución: compound ~16 × 16 m, caseta en una esquina, torre al fondo, puente de cables torre→caseta, gabinetes en losas junto a la torre, generador con tanque al frente, portón doble, postes de luz |
| caseta_int | dos filas de racks de 19", charolas de escalerilla en el techo con cableado peinado, rectificador, baterías, panel de alarmas, minisplits, barra de tierra, piso antiestático |
| trasera | trasera de la caseta y del compound; **la imagen traía un grafiti con "13" (prohibido por R4): se tapó en la referencia con un parche del muro y no se modela** |
| torre_arriba | contrapicada de la torre: tramos con bridas, contraventeo en K/X, escalera, plataforma de microondas intermedia |
| materiales | acero galvanizado, concreto prefabricado, grava, malla ciclónica, radomo, cobre |
- **Proporciones de fuentes reales (R-AAA punto 7)**, investigadas en la web antes de modelar: torre de 3 patas de 15–60 m con
  ancho de base 3–8 m y cabeza 0,5–1,2 m, galvanizado ≥ 65 µm, norma TIA-222-G → se usa 42 m, base 5,0 m, cabeza recta 1,6 m;
  panel pasivo de 8 puertos 2688 × 301 × 181 mm (22,3 kg); AAU 5G 64T64R 730–795 × 395–470 × 160–240 mm; RRU 4T4R
  ≈ 480 × 270 × 140 mm; caseta prefabricada con muros de ~100 mm y losa de 100–150 mm; puente de cables de 508–610 mm en
  tramos de 3,66 m; colgadores de cable en torre cada 0,9–1,2 m; malla ciclónica con postes de línea de 2-3/8" (60,3 mm) a
  ≤ 3,05 m, brazos a 45° con 3 hilos de púas; generador de 20–30 kVA en gabinete insonorizado ≈ 1,7–2,0 × 0,7–0,95 × 1,05–1,4 m.
  Las fuentes concretas de cada pieza se anotan en la sección de modelado.
- **Grafiti (R-GRAF):** el usuario no fijó cantidad; un sitio de telecom vigilado lleva poco: unas cuantas placas y firmas
  chicanas solo en la trasera de la caseta. Biblioteca exclusiva nueva, sin números, coronas ni estrellas (R4).

## COM_1_antena · modelado (2026-11-12)
- **Ensamble** (`blender/com_builder.py`): compound de 16 × 16 m sobre guarnición de concreto en tramos con junta, cama de
  grava ondulada con piedras sueltas, banquetas en paños de 1,5 m, losas de equipo y del portón, registros del anillo de
  tierras, bolardos de tubo relleno pintados de amarillo. Caseta prefabricada de concreto 5,8 × 3,3 m (muros de 10 cm con
  esquinas en chaflán, losa de techo con vuelo, gotero y pendiente, insertos de izaje, clips de anclaje al firme); puerta de
  lámina de 36 × 84" entreabierta (marco con tope, burlete, 3 bisagras de nudillo, palanca, cerrojo, placa de patada,
  cierrapuertas de brazo paralelo, umbral estriado, gotero); 2 condensadoras con canaleta que rodea la esquina hasta cada
  minisplit interior; arbotante LED de aluminio fundido; estrobo; caja de conexión del generador; toma y extractor con
  rejilla y capucha; puerto de 12 botas con capucha; barra de tierras exterior; 2 antenas GPS de sincronía en el techo con
  su cable hasta el puerto. Torre girada para que su escalerilla de cables mire a la caseta; 18 troncales del pie de la torre
  al puerto sobre el puente de cables (dos capas, flejes con hebilla, gaza de goteo, cada cable a la columna de botas de su
  lado, sin cruces).
- **Torre** (agente, `kit/tower.py`, 381 768 triángulos): 3 patas tubulares Ø219→Ø114 en tramos de 6 m con bridas de
  8 tornillos, contraventeo en X con placa de cruce y zigzag en el tramo recto, cartelas y tornillería en cada nudo, dados
  Ø1,0 m con placa base, 8 anclas y doble tuerca, escalones de pie de 5/8", escalera con riel rígido anticaídas, escalerilla
  de cables con abrazaderas de bloque cada 1,2 m y 18 cables, plataforma de microondas (32,5 m) y de sectores (39,9 m) con
  rejilla electroforjada real, rodapié, barandal con rodillera, tubos de montaje; mástil, pararrayos de cobre de 2 m,
  bajada de tierra, ménsula de baliza, cajas de distribución, letrero RF. Ajuste mío: tubo de los platos de Ø114 a Ø76 para
  casar con las monturas del kit de antenas.
- **Antenas** (agente, `kit/antennas.py`): 6 paneles pasivos de 8 puertos 2688 × 301 × 181 mm con soportes de inclinación,
  3 AAU 5G 64T64R de 795 × 395 mm con aletas, 6 RRU 4T4R de 480 × 270 × 140 mm (4 jumpers ½" con gaza de goteo y conectores
  4.3-10 cada uno), colas de AAU y RRU peinadas bajo la plataforma hasta las cajas de distribución, 2 platos de microondas
  (0,9 y 0,6 m) con radomo de tela y ODU, baliza roja L-810.
- **Equipo del sitio** (agente, `kit/telecom.py`): malla ciclónica de 2" calibre 9 TEJIDA en geometría (modo ligero de una
  sola malla, ~13,5 k triángulos por metro: pickets en zigzag entrelazados, orilla torcida, postes de 2-3/8" y terminales de
  2-7/8", larguero de 1-5/8", barras de tensión con abrazaderas, riostras con tensor, brazos a 45° con 3 hilos de púas de
  4 puntas cada 127 mm con flecha), portón doble de 4 m (bisagras de 180°, barra de caída, horquilla, cadena y candado),
  puente de cables de canal C de 3" con postes de 3-1/2", 3 gabinetes exteriores 750 × 750 (energía, baterías, telecom con
  A/C), generador de 30 kVA en caseta insonorizada con chimenea y tanque de diésel de doble pared con silletas y mangueras,
  marco H con medidor y desconectador, 2 postes cónicos con reflector LED (uno con cámara), interior de la caseta (10 racks
  en dos filas con equipo variado, charolas con cableado que baja a cada rack, minisplits, alarma, extintor, barras de
  tierra, luminarias LED, escritorio abatible con laptop, loseta antiestática) y letreros en inglés.
- **Fuentes web de las proporciones (R-AAA punto 7):**
  - Torre: [OSHA 1910.24](https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.24) (escalones de pie cada
    12–18"), [OSHA 1910.23](https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.23) (peldaños 10–14",
    ancho libre ≥ 16"), [ROHN RSL](https://static1.squarespace.com/static/5e67ee40cd78d320f664bccd/t/5f0c8f2cce41d633e5c81641/1594658608627/15_2015_Rohn_SelfSupporting_RSL.pdf)
    (torres autosoportadas con escalones y anticaídas, TIA-222), [CommScope 53628](https://Commscope.com/globalassets/digizuite/53628-bn-37378.pdf)
    y [RFS CLAMP-105](https://www.scmsinc.com/rfs-clamp-105-non-insulated-bolt-on-cable-hanger-for-both-7-8-coaxial-cables-e100-e105-elliptical-waveguides.html)
    (colgadores cada 0,9–1,2 m), [3 Star tower rules](https://www.3starinc.com/docs/upload_1566592221_rt-tower-rules.pdf)
    (tornillos de 5/8"); tabla de proporciones de torres de 3 patas (base 3–8 m, cabeza 0,5–1,2 m).
  - Antenas: CommScope 8P-2L6M-D4-V5 (2688 × 301 × 181 mm, 22,3 kg; andrew.com y everythingrf.com), Huawei AAU5613
    (795 × 395 × 220 mm), Huawei RRU3256 (480 × 270 × 140 mm), CommScope VHLP3 de 0,9 m, plato de 0,6 m de bajo perfil
    (fondo 330 mm), baliza L-810 (Flightlight Ø143 × 197 mm). Varios PDF de fabricante están bloqueados por la red de la
    sesión: se usaron los extractos del buscador.
  - Equipo: chainlinkfittings.com (brazos de 45° de 3 hilos, bisagras, barra de caída), licitación de bidnetdirect (postes
    de 2-3/8" a ≤ 10 ft, púas de 4 puntas), CommScope WB-CY212 (puente de 24" × 12 ft), gabinete BT7575175 (1750 × 750 ×
    750), Stephill SSDP30 y Cat (generador de 30 kVA ≈ 2050 × 1000 × 1490), tanque de 500–550 gal con silletas, Square D
    ringless de 200 A, poste de 20 ft con base de 10,5", racks de 42U 600 × 1000 / 600 × 600 × 2000, charola escalera
    Hammond CL.
- **Revisión en arcilla a < 2 m** (`render_qa/COM_1_antena_r1_*`, 14 tomas: portón, caseta, equipo, trasera, puente,
  sectores, microondas, interior, torre, esquinas y techo) y primeros planos de cada pieza. Arreglado en la revisión y en
  la **segunda pasada de detalle (R-AAA punto 7)**: arbotante que se leía como bulto (rehecho como carcasa fundida de corte
  total con aletas y difusor); gotero y capucha del puerto barridos hacia dentro del muro (perfil invertido); cable GPS que
  cruzaba la losa (ahora rodea el canto, corre bajo el vuelo y entra por una bota); troncales que se cruzaban al entrar al
  puerto (cada cable a la columna de botas de su lado); canaletas de los minisplits que terminaban en el muro frontal (ahora
  rodean la esquina hasta cada unidad interior); tanque y generador intercambiados para que la manguera de combustible sea
  corta; tubo de los platos Ø114 → Ø76 (las abrazaderas del plato no cerraban); registro de tierras bajo el poste de luz;
  cerca con instancias (5,5 M triángulos realizada) cambiada por el modo ligero de una sola malla. Cilindros visibles de
  24–48 lados, tubos y cables de 12–16.
- **Horneado y kit UE5** (atlas de muros a 4K, la caseta lleva el grafiti): exportación validada (todas las comprobaciones
  OK; la de base se ajustó al caso del sitio: los dados de la torre se entierran 0,6 m). SM_COM_1_antena: Estructura 408 ·
  **Detalle 789 549** (torre y antenas) · **Mobiliario 1 078 091** (malla, portón, puente, equipo e interior) · Vidrio 412 ·
  Colision 616 + cajas; 1,87 M triángulos antes de hornear; 132,5 MiB de GLB; `kit_ue5_descargas/BLACKISLE_UE5_COM_1_antena.zip`
  30,7 MiB; común rehecho (91,8 MiB) con T13 galvanizado, T14 grava y los colores de cobre y radomo. El empaquetador acepta
  ahora `--solo ID` para no reescribir los ZIP de los demás modelos (el común ya está cerca del límite de 95 MiB).
- **Por debajo del estándar, dicho con honestidad**: el alambre de la malla ciclónica es de 3 lados en el modo ligero (la
  silueta triangular se nota a < 0,5 m; con 4 lados la cerca costaría 1,1 M triángulos); tornillería chica, arandelas y
  puertos de 8–16 lados; la rejilla de las plataformas no lleva dentado; los cables verticales de la torre van rectos;
  el equipo de los racks se repite entre racks y los rieles de 19" no tienen perforación; generador y gabinetes solo con
  puertas cerradas; las arrugas del radomo de tela son procedurales; los letreros tienen texto apenas poligonal a < 0,4 m;
  el muro de la caseta es liso (así son las casetas prefabricadas) y su lectura depende del atlas y de lo que lleva colgado.

## Nuevo: MIL_1_almacen (almacén militar de armamento pesado) + MIL_2_avanzada (puesto de avanzada) · referencias (2026-11-13)
Pedido: un almacén tipo base militar para armamento pesado y, al lado, un puesto de avanzada que sirva también como pieza
suelta: una tienda de campaña donde se compran munición y armas. **Sin grafiti ni placas** (orden del usuario); limpio, poco
desgaste, con huellas de intentos de saqueo (palanca, abolladuras, impactos), no deteriorado. Nueva regla en CLAUDE.md: ya no se
genera biblioteca de grafiti por modelo; se usan las existentes hasta que el usuario pida más.
Generado con `nano_banana_2_1` a 1k (thinking medium): 8 imágenes, 0 rechazos, **12 créditos** (jobs a1d32468, a28a8096,
b4b4ee1c, 22fdd350, 69a1fda1, 2235e7c1, f420198d, d7c6dd1b). Revisadas con mis ojos; en `refs_higgsfield/MIL_1_almacen/`:
| Vista | Qué fija |
|---|---|
| hero | nave de acero preingeniería color arena sobre muro de concreto de 1,2 m, techo de lámina a dos aguas con ventiladores de turbina, 2 cortinas, andén y puerta con marquesina; HESCO, muros T, alambre de navaja, torre de vigilancia; la tienda de campaña verde olivo con red de camuflaje al lado |
| frente | andén de 1,2 m con defensas de hule, rampa con barandal amarillo, cortinas con caja y guías (una abollada con marcas de palanca), puerta con teclado, letreros esténcil AUTHORIZED PERSONNEL ONLY / NO SMOKING / EXPLOSIVES, gabinete de extintor, bolardos, cámaras |
| interior | marcos rígidos, largueros, techo aislado, piso sellado con líneas amarillas, racks de tarimas con cajas de munición y cajas largas, jaula de malla con fusiles, montacargas, banco (la nave de la referencia es más grande que la nuestra) |
| tienda | tienda de marco verde olivo con un costado enrollado, mostrador de cajas de munición con cubierta de triplay, racks con fusiles, latas de munición, letrero de madera SUPPLY, red de camuflaje en postes, HESCO, costales, generador, bidones, reflector en tripié |
| tienda_int | arcos de aluminio, lona con caída entre arcos, piso de triplay, mostrador, caja de dinero y portapapeles, racks de fusiles, anaqueles de latas y cajas, tablero perforado con chalecos, focos colgantes |
| perímetro | HESCO de malla soldada con geotextil, muros T con orejas de izaje, malla con brazos y espirales de navaja, torre de vigilancia con costales, torre de luz, pluma de acceso y chicana de barreras tipo Jersey |
| aérea | distribución: nave al fondo con andén al patio, muros T y HESCO al frente y costado, la tienda dentro de su anillo de HESCO junto a la nave, torre en la esquina, acceso con chicana |
| materiales | lámina arena con rayón de palanca, concreto de muro T, geotextil tras malla, lona OD con ojillo, costal de polipropileno, caja OD con asa y esténcil |
- **Proporciones de fuentes reales (R-AAA punto 7):** HESCO MIL1 1,37 × 1,06 m (10 m por tramo), MIL7 2,21 × 2,13 m, MIL8
  1,37 × 1,22 m ([ficha HESCO 2018](https://admincontent.bimobject.com/v1/public/brand/4cab39e7-c4b3-40e6-894d-64ae87b72ac4/pdf/d81693ab-fc9d-40c4-b2a0-92ac2e91854b/document),
  [MoD Sales](https://www.mod-sales.com/manufacturers/hesco)); tienda TEMPER 20 × 32 ft: cumbrera 10'6" (3,2 m), alero 6'9"
  (2,06 m), secciones de 8 ft, marco de aluminio ([especificación DLA](https://www.dla.mil/Portals/104/Documents/TroopSupport/CloTex/shelters/MilSpec/tempermain2.pdf),
  [Coleman's](https://colemans.com/tent-temper-20-ft-x-32-ft-used)); nave preingeniería: crujías de 20–30 ft, largueros y
  largueros de muro a ~1,5 m ([steelcalculator](https://steelcalculator.pages.dev/reference/steel-industrial-building/),
  [Nucor](https://www.nucorbuildingsystems.com/wp-content/uploads/2019/01/03_00.pdf)). Las de cada pieza se anotan en el modelado.
- **Textos en el modelo:** esténciles genéricos en inglés; sin banderas, insignias, unidades reales ni marcas.

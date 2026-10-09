# ESTADO · Kit BLACKISLE (7 modelos)

Última actualización: 2026-10-09 · Fase actual: **E · modelado (kit modular + piloto APT_A_5p)**

## Resumen
| Fase | Estado |
|---|---|
| A · Preparación y verificación | Hecha salvo el paso A-3: **cuota ilimitada no disponible → detenido (R1)** |
| B · Conceptos (Higgsfield) | **Hecha.** 25 vistas vigentes descargadas y revisadas con mis ojos (R5) |
| C · Lettering (Higgsfield) | **Hecha.** 15 piezas, ortografía verificada; 31 recortes RGBA en `lettering/cutouts/` |
| PC1 · Aprobación del usuario | **Aprobado** ("dale", 2026-10-09). Se usan los heroes v2/v3 |
| D · Biblioteca de materiales | **Entradas hechas:** 16 texturas 1024² repetibles en `texturas/`. Paneles de grafiti pendientes (dependen de los vanos del modelo) |
| E · Modelado | En curso: kit modular + piloto APT_A_5p |
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

## Problemas abiertos
- ~~Red~~ **Resuelto:** el usuario habilitó `d8j0ntlcm91z4.cloudfront.net`. Las 52 imágenes de B/C se descargaron (52/52) y se revisaron.
- **Red:** hosts de Higgsfield bloqueados en el entorno cloud.

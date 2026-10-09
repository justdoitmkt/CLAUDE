# BRIEF DE EJECUCIÓN · Edificio de departamentos de 5 pisos con grafiti chicano y street

**Proyecto:** BLACKISLE (FPS en Three.js; editor de mapa en `localhost:5173/mapa.html`)
**Tu rol:** ejecutor. Esto es una orden de trabajo, no una lluvia de ideas. Léela completa antes de tocar una herramienta, ejecútala por fases y respeta los puntos de control.
**Herramientas requeridas:** Higgsfield (MCP `mcp__Higgsfield__*`), Blender (conector/MCP de Blender) y Python con numpy + Pillow.
**Idioma de trabajo:** español. Los prompts para los modelos de imagen van en inglés (ya están redactados abajo).

---

## 1. Misión

Producir para el mapa de BLACKISLE **un edificio de departamentos de 5 pisos, tejado a dos aguas de teja, con la planta baja cubierta de grafiti (lettering chicano + street)**, en el estilo de las 5 capturas de referencia. Pipeline:

1. Referencias de diseño del edificio con IA (Higgsfield) → el usuario las aprueba.
2. Lettering chicano y street con IA (Higgsfield), recortado a PNG con transparencia.
3. Texturas: concreto desgastado repetible + paneles de grafiti de planta baja compuestos con ese lettering.
4. Modelo en Blender, **más de 100 000 triángulos reales**, topología limpia.
5. Texturizado del modelo con lo generado, QA contra las referencias y exportación a GLB.

## 2. Reglas duras (no negociables)

**R1 · Créditos: SOLO modelos con generaciones ilimitadas.** El usuario lo ordenó expresamente.
- Lista vigente: `models_explore(action:'list', unlim:true)`. Al 2026-10-09 los de imagen son `gpt_image_2`, `nano_banana_pro`, `nano_banana_2`, `nano_banana`, `seedream_v4_5`, `seedream_v5_pro`, `seedream_v5_lite`, `flux_2`, `kling_omni_image` (y `soul_2`, que no sirve aquí).
- **NO usar** (no figuran como ilimitados): `nano_banana_2_1`, `flux_3_image`, **todos los modelos 3D** (`generate_3d`, Tripo, Hunyuan3D, Meshy, SAM 3D) y las herramientas `upscale_image` y `remove_background`. El 3D se hace en Blender; el recorte de fondo se hace en local (§ Apéndice B); la resolución se pide directamente al modelo.
- Pasa `use_unlim: true` explícito en **cada** `generate_image` / `generate_image_batch`. En batch cada ítem es `count: 1`.
- Lee el bloque `unlim` de la respuesta de `models_explore` y el texto "Unlim configs": usa solo las combinaciones de resolución/calidad que la cuota realmente cubre.
- Si `unlim.available` es `false`, o el modelo/configuración no está cubierto: **DETENTE y pregunta al usuario. Nunca gastes créditos de pago por tu cuenta.** (Aviso: al preparar este brief, 2026-10-09, la API devolvió `unlim.available=false, remaining=null` con plan Ultra y 517,26 créditos. Verifícalo en el paso A-3 y repórtalo tal cual.)

**R2 · Triángulos.** El modelo final exportado debe tener **≥ 100 000 triángulos reales**; objetivo 150 000–250 000; techo 400 000. Los triángulos deben ser geometría útil (detalle arquitectónico, daño, tejas), **no** subdividir planos para inflar el número.

**R3 · Topología de calidad** (criterios en §5). Un modelo con 100 000 triángulos sucios se rechaza.

**R4 · Contenido seguro.** Lettering con palabras inocuas (las listadas abajo). PROHIBIDO: nombres, números, siglas o símbolos de pandillas reales (13, 14, 18, MS, X3, Norte/Sur, etc.), símbolos de odio, personas reales y marcas comerciales. Los "crews" (KAOS, ZORO, NOVA, REXO) son ficticios.

**R5 · Verifica con tus ojos.** Abre cada imagen generada. Si una palabra sale mal escrita, regenera esa pieza. No uses una pieza con texto erróneo.

**R6 · Trazabilidad.** Guarda todo en la carpeta de entrega (§ Entrega). Guarda el `.blend` tras cada tramo grande. Descarga cada resultado final de Higgsfield a disco local a máxima resolución.

**R7 · Cero invención.** Reporta números reales (triángulos medidos, tamaños de archivo, créditos). Si falta una herramienta (Blender, Higgsfield) o algo falla: detente y dilo; no improvises sustitutos.

**R8 · Ambigüedad.** Las decisiones ya tomadas están en §4. Si algo no está cubierto, elige lo más razonable, regístralo en el reporte y sigue; pregunta solo si es bloqueante.

## 3. Lo que muestran las 5 referencias (análisis ya hecho)

Las capturas son del propio juego (render Three.js, día despejado, isla con dunas y palmeras). Están recortadas al viewport 3D en `blackisle-edificio-departamentos/referencias/` del repositorio. Si no puedes leer el repo, usa las capturas adjuntas en este chat y recórtalas a (x 578–1581, y 149–888) sobre 1920×1080 para quitar la interfaz del editor.

| Ref | Qué es | Lo que debes copiar |
|---|---|---|
| 1 `ref_1_frente_cercano` | Cara ancha, puerta central | 5 niveles; **2 franjas verticales beige de altura de piso completa** (≈1,4 m de ancho, a ±25 % del centro) con un vano oscuro en el tercio central y panel beige arriba y abajo; **banda de losa** fina y saliente en cada nivel; **cornisa gruesa** arriba; concreto gris con manchas verticales de lluvia, descascarado y parches de pintura; PB cubierta de grafiti; puerta azul marino centrada con panel beige encima; algunos tags tenues suben hasta ~1 m dentro del piso 2 |
| 2 `ref_2_lateral_ventanas_rotas` | Cara angosta, lado en sombra | Mismas franjas beige y vanos; **vidrios rotos / vanos con restos de cristal y oscuridad interior**; concreto azulado por luz de cielo; grafiti en PB con más densidad al centro |
| 3 `ref_3_trasera_y_granero` | Cara trasera + granero | Mismo ritmo de ventanas; menos daño; PB con grafiti |
| 4 `ref_4_frente_lejano_5_pisos` | Cara angosta de frente, a distancia | Confirma 5 pisos, proporción angosta ≈ 0,65 de la altura, puerta + 2 ventanas en PB, grafiti rojo/blanco/azul |
| 5 `ref_5_tejado_casa_madera` | Casa de madera con tejado | **El tejado**: dos aguas, color óxido/rojo-marrón envejecido, **cabios (vigas) vistos que sobresalen bajo el alero**, ventana en el hastial |
| `ref_grafiti_planta_baja_1/4` | Detalle ×3 del grafiti | Estilo exacto: capas de tags finos negros/azules, **"Mi Vida Loca" en script caligráfico fino negro con florituras**, handstyle rojo, burbuja blanca con contorno negro, bloque amarillo dorado, manchas azul cobalto, concreto visible entre capas; paleta: negro, blanco, rojo, azul cobalto, amarillo dorado |

**Cambio pedido por el usuario respecto a las refs:** las refs tienen azotea plana con caja de escalera. El edificio nuevo lleva **tejado a dos aguas con teja** (ref 5 como guía de color y de cabios). No copies la azotea plana.

## 4. Decisiones de diseño ya tomadas (ficha técnica)

Medidas estimadas sobre las capturas (piso ≈ 3 m; cara ancha ≈ 14 m; cara angosta ≈ 10 m). **Si una medida contradice lo que se ve en las refs, mandan las refs.**

| Parámetro | Valor |
|---|---|
| Unidades / ejes | 1 unidad Blender = 1 m; Z arriba; origen en el centro de la base sobre el suelo (z = 0); escala y rotación aplicadas |
| Planta exterior | 14,0 m (eje X) × 10,0 m (eje Y). Fachada principal mira a −Y de Blender (= +Z en glTF) |
| Muros | 0,30 m de espesor, concreto |
| Niveles | PB 2,8 m + 4 pisos × 3,0 m = 14,8 m hasta la cara superior de la última losa |
| Zócalo | 0,25 m sobre el terreno; 2 escalones en cada puerta |
| Bandas de losa | una por nivel; 0,20 m de alto × 0,05 m de saliente |
| Cornisa | 0,70 m de alto × 0,20 m de saliente; rodea el edificio bajo el tejado |
| Franjas de ventana | 2 por piso y por cara, centradas a **±3,5 m** (caras de 14 m) y **±2,5 m** (caras de 10 m); 1,40 m de ancho × altura del piso; panel beige empotrado 3 cm |
| Vano de ventana | 1,30 × 1,00 m centrado en la franja; marco metálico 6 cm; alféizar saliente 4 cm; **sin cristal intacto**: esquirlas de vidrio roto pegadas al marco en ~40 % de los vanos |
| Puerta | vano 1,40 × 2,10 m; hoja azul marino, geometría separada, entreabierta ≈ 50°; panel beige sobre el vano hasta la banda de losa |
| Tejado | a dos aguas, cumbrera paralela a X; pendiente 28°; voladizo 0,60 m; **cabios vistos** bajo el alero; teja curva de barro envejecida; caballetes en la cumbrera; canalón + bajante; chimenea pequeña |
| Frontones | muros triangulares de concreto en las 2 caras de 10 m, con ventana de ático |
| Colores base | concreto #8A8A84 · beige #C9B99D · azul marino #1F2A44 · teja #8E4A32 |

**Caras** (inferido de las capturas):

| Cara | Ancho | Planta baja | Pisos 2–5 |
|---|---|---|---|
| A (ref 1, principal) | 14 m | **puerta central**, sin ventanas, grafiti denso | 2 franjas ±3,5 m |
| B (ref 2) | 10 m | 2 franjas ±2,5 m (con ventanas), grafiti | 2 franjas, vidrios rotos |
| C (ref 3, trasera) | 14 m | 2 franjas ±3,5 m, grafiti | 2 franjas |
| D (ref 4) | 10 m | 2 franjas ±2,5 m + **puerta central**, grafiti | 2 franjas |

**Interior (decisión por defecto, porque el editor deja entrar a los edificios):** carcasa mínima y transitable: losas por piso (0,25 m) con hueco de escalera, **núcleo de escalera** con peldaños reales (≈ 2,6 × 5,0 m), muros divisorios que forman 2 departamentos por piso con vanos de puerta sin hoja, sin mobiliario (el editor coloca los muebles). Ático cerrado.

**Texturas — lista y presupuesto de memoria (≤ 200 MB decodificados; fórmula: ancho × alto × 4 × 1,33 por mapa):**

| ID | Uso | Albedo | Normal | ORM |
|---|---|---|---|---|
| T1 `concrete_A` | muros superiores, zócalo, cornisa, frontones | 2048² | 2048² | 1024² |
| T2 `panel_beige` | franjas beige | 1024² | 1024² | constantes |
| T3 `roof_tile` | teja | 1024² | 1024² | constantes |
| T4 `wood_weathered` | cabios, fascia | 1024² | 1024² | constantes |
| T5 `door_blue_metal` | puerta (1,4 × 2,1 m = proporción 2:3) | 1024×1536 | 1024×1536 | constantes |
| G_A | grafiti PB cara A | 4096×1024 | 2048×512 | constante |
| G_D | grafiti PB cara D | 3072×1024 | 1536×512 | constante |
| G_B, G_C | grafiti PB caras B y C | 2048×1024 | 1024×512 | constante |

Variedad sin gastar memoria: los muros usan T1 con **3 materiales distintos** que comparten las mismas imágenes pero con `baseColorFactor` ligeramente distinto y UV con desplazamiento/rotación aleatorios por cara.

## 5. Presupuesto de geometría y criterios de topología

| Bloque | Triángulos |
|---|---|
| Carcasa estructural con espesor real, vanos con jambas, biseles | 15–25 k |
| Marcos, alféizares, esquirlas de vidrio roto | 10–15 k |
| Bandas de losa, cornisa, fascia, zócalo, escalones | 8–12 k |
| **Daño de concreto como geometría** (desconches, picaduras, cortes, varillas expuestas) | 30–50 k |
| **Tejado**: tejas individuales (12–24 tris c/u), caballetes, cabios, canalón | 40–80 k |
| Puertas, bajantes, cables, aire acondicionado oxidado, chimenea | 8–12 k |
| Interior (losas, escalera, divisorios) | 12–25 k |
| **Total** | **≈ 125–220 k → apunta al tramo alto (≥ 150 k); el piso duro es 100 k** |

**Criterios de aceptación de topología:**
- Cuadrilátero-dominante con flujo de aristas limpio. Ngons solo en caras planas antes de exportar; **cero triángulos/ngons en superficies curvas**. Se triangula al exportar.
- Biseles de 2 segmentos en todas las aristas duras ≥ 2 cm (marcos, losas, cornisa, vanos).
- **Cero** geometría duplicada, caras coplanares solapadas (z-fighting), vértices sueltos, aristas no-manifold (salvo láminas finas intencionales: esquirlas) y caras de área cero.
- Normales hacia fuera; sombreado suave por ángulo (~30°) sin artefactos negros.
- Densidad coherente: planos grandes 10–25 cm de arista; zonas dañadas 1–3 cm.
- Modificadores aplicados, transformaciones aplicadas, *merge by distance* 0,1 mm.
- UV: sin solapes en los paneles de grafiti (islas únicas); sin estiramiento > 10 %.

## 6. Ejecución por fases

### FASE A · Preparación y verificación de entorno
1. Higgsfield: `balance`, `list_workspaces` (confirma conexión). `get_preferences` → hoy `auto_create_project = false`: **no crees proyecto ni pases `folder_id`** salvo que el usuario lo pida.
2. Blender: ejecuta un script mínimo (`import bpy, sys; print(bpy.app.version_string, sys.executable)`) y comprueba que `numpy` importa. Si no hay conector de Blender: **detente y avisa** (no uses otra cosa sin permiso).
3. Créditos ilimitados: `models_explore(action:'list', unlim:true)` y lee `unlim` + "Unlim configs". Si `available` es `false` → aplica R1 (detente y pregunta). Registra en el reporte qué modelos/configuraciones están cubiertos.
4. Sandbox/Python: comprueba `PIL` y `numpy`. Si Blender y tu sandbox **no comparten disco**, ejecuta el procesado de imágenes (Apéndice B) dentro de Blender (trae numpy; si falta Pillow, instálalo en el Python de Blender o usa `bpy.data.images` + numpy) o transfiere los archivos.
5. Crea la carpeta de entrega (§ Entrega). Sube las referencias recortadas a Higgsfield: `media_upload` → `PUT` → `media_confirm` (si no puedes leer los archivos, `media_upload_widget` como única llamada de ese turno). Confirma los roles/máximos con `models_explore(action:'get', model_id:…)` antes del primer uso de cada modelo.

### FASE B · Referencia de diseño del edificio (Higgsfield)
Modelo principal: **`nano_banana_pro`** (ilimitado, acepta `image_references`, hasta 4k). Alternos ilimitados si falla: `seedream_v5_pro`, `flux_2`, `gpt_image_2`. Usa `generate_image_batch` con los prompts B1–B6 del Apéndice A, adjuntando como referencia las refs 1, 4 y 5 (y las de grafiti en B6). 2k, `use_unlim:true`. Espera con `jobs_wait` y muestra el lote **una sola vez** con `show_generation_by_ids`.
Las vistas "ortogonales" de IA nunca son ortogonales perfectas: son guía visual; **las medidas mandan en §4**.

### FASE C · Lettering chicano y street (Higgsfield) — puede lanzarse en paralelo con la B
Modelo: **`gpt_image_2`** (ilimitado; es el mejor en tipografía), 2k, calidad la más alta que cubra la cuota ilimitada. Respaldo ilimitado: `nano_banana_pro`. Lanza las piezas del Apéndice A (tabla C/S) con `generate_image_batch` (máx. 12 por lote). Fondo **verde chroma plano #00FF00**; el arte **no** contiene verde.
Después, por cada pieza aprobada: `key_out()` (Apéndice B) → PNG RGBA recortado. Las hojas (S05, S06, S07) se recortan por celdas de la cuadrícula y se procesan una a una.

### ⛔ PUNTO DE CONTROL 1 — ESPERA AL USUARIO
Presenta: (a) contact sheet de las referencias B1–B6, (b) contact sheet del lettering recortado, (c) resumen de la ficha técnica con cualquier desviación. **No avances a Blender ni a las texturas hasta que el usuario apruebe o corrija.** Si pide cambios, regenera solo lo necesario.

### FASE D · Texturas (Higgsfield + Python)
1. Genera con **`seedream_v4_5`** (ilimitado, hasta 4k) o `gpt_image_2` los tileables T1–T4 (prompts D1–D4) y la puerta T5 (D5), 1:1 (T5 en 2:3, luego redimensionada a 1024×1536). Respaldo ilimitado: `nano_banana_pro`.
2. Hazlas repetibles con `make_seamless()`. **Compruébalo** colocándolas en mosaico 3×3 y revisando las uniones; si queda costura visible, desplaza 50 % y repárala con `nano_banana_2` (ilimitado, rol `mask`, `is_inpaint:true`) enmascarando solo la cruz central; vuelve a desplazar.
3. Reduce al tamaño de §4 (Lanczos). Deriva normal y ORM con `make_normal()` y `make_orm()` (rugosidad ≈ 0,85 concreto, 0,6 teja, 0,7 madera, 0,5 metal de puerta con `metal` 0,3). Son normales **derivadas del albedo**: aceptables como detalle fino; el volumen real lo da la geometría.
4. **Paneles de grafiti de planta baja (G_A…G_D):** `compose_panel()` con T1 como base y las piezas recortadas de la Fase C. Receta: banda de 3,5 m de alto (2,8 m de PB + 0,7 m de zona de desvanecimiento); cobertura ~85 % de la PB; capas en este orden: tags de fondo → throw-ups street (S01–S04) → lettering chicano grande (C01–C08) → tags pequeños encima → máscaras/calaveras/iconos (S06) → goteos (S07) → 3–5 parches "buff" (rectángulos grises lisos de pintura de borrado, 1–2 m, tono ligeramente distinto al concreto, op 0,9); sobre 2,8 m solo 6–10 tags sueltos con densidad decreciente hasta 3,5 m. Tamaños: palabras 2,5–4 m de ancho, tags 0,8–1,5 m, iconos 0,8–1,2 m; rotación ±12°; no repitas la misma pieza dos veces seguidas. `keepout`: puerta + panel beige superior (cara A: `(6.3,0,7.7,2.8)`; cara D igual) y las franjas de ventana de PB (±centro ± 0,7 m, de 0 a 2,8 m). Ejemplo de layout cara A: `Mi Vida Loca` x=2.6 y=1.5 w=3.6 rot=−4 · `Isla Negra` x=10.9 y=1.7 w=4.2 rot=3 · `KAOS` x=4.8 y=0.8 w=2.6 · `ZORO` x=11.3 y=0.7 w=3.0 · `Con Safos` x=1.4 y=2.2 w=1.8 · `Por Vida` x=12.8 y=2.3 w=2.2 (el resto, a tu criterio siguiendo la receta).
5. Convierte albedos a JPEG calidad 90 y deja las normales en PNG. Guarda todo en `texturas/`.

### PUNTO DE CONTROL 2 — informativo (no esperes)
Muestra contact sheet de texturas + el panel G_A compuesto. Continúa a Blender salvo que el usuario interrumpa.

### FASE E · Blender: modelado
Normas de trabajo: envía código por tramos (≤ ~150 líneas por llamada), guarda `.blend` tras cada tramo, **usa bmesh/numpy en lugar de bucles con `bpy.ops`**, detecta la versión (`bpy.app.version`) y adapta la API (p. ej. desde 4.1 ya no existe `use_auto_smooth`). Colecciones: `APT5_Shell`, `APT5_Details`, `APT5_Roof`, `APT5_Interior`, `APT5_Damage`; prefijo `APT5_` en todos los objetos.
1. **Escena:** unidades métricas, escala 1, borra objetos por defecto, guarda en `entrega/blender/APT5_chicano.blend`.
2. **Blockout exacto** (§4): carcasa con espesor, losas, zócalo, volumen del tejado. Captura de viewport en 4 ángulos y compara con las refs (proporciones, ritmo de ventanas).
3. **Detalle arquitectónico:** vanos con jambas, marcos, alféizares, paneles beige empotrados, bandas de losa, cornisa, fascia, puertas con hoja entreabierta, escalones, bajantes, canalón, cables, 2–3 aires acondicionados oxidados.
4. **Tejado:** construye las tejas con bmesh en una malla única por faldón (pieza base de 12–24 tris, canal + cobija, solape ~25 %); ligera variación aleatoria de posición/rotación/escala; caballetes de cumbrera; cabios vistos con puntas cortadas; fascia; chimenea.
5. **Daño como geometría:** desconches y picaduras (subdivisión local + *Displace* con texturas procedurales Voronoi/ruido limitadas por *vertex group*, y luego **aplicar**); cortes con booleanos y bordes biselados; **varillas de refuerzo expuestas** (cilindros de 8 lados) en esquinas y bajo alféizares; grietas profundas como surcos; ~40 % de vanos con esquirlas de vidrio. El daño se concentra en esquinas, bajo alféizares, cornisa y zócalo (como en las refs); la cara B es la más dañada.
6. **Interior mínimo:** según §4.
7. **Limpieza de topología** y verificación de criterios §5. Mide con el script de triángulos (Apéndice B). Si no llegas a 100 000, añade detalle real (más daño, tejas con mayor definición), nunca subdivisión vacía.

### PUNTO DE CONTROL 3 — informativo
Capturas del blockout/detalle desde los ángulos de las refs 1, 2 y 5 y el conteo de triángulos. Continúa salvo que el usuario interrumpa.

### FASE F · UV, materiales y texturizado
1. **UV por proyección de caja con escala de mundo** (script en Apéndice B): T1 a 1 UV = 3 m. Caras con paneles de grafiti: **una isla única por cara**, orientada para que el texto se lea sin espejo (el script ya contempla la mano de cada cara), mapeando 0–1 sobre el panel (14 × 3,5 m → 4096×1024 en cara A). Aplica un desplazamiento/rotación UV aleatorios por cara en las zonas de T1.
2. **Materiales** (máx. 14): `APT5_concrete_a/b/c` (T1), `APT5_graffiti_A/B/C/D`, `APT5_panel_beige`, `APT5_roof_tile`, `APT5_wood`, `APT5_door_blue`, `APT5_metal_dark` (marcos, bajantes, varillas: colores por factor), `APT5_glass_shards` (oscuro, ligeramente transparente, sin vidrios completos), `APT5_interior_plaster` (T1 reutilizada con factor claro).
3. **Cableado glTF-friendly:** Principled BSDF con *Image Texture* → color (sRGB), normal vía nodo *Normal Map* (imagen en Non-Color), ORM (Non-Color) → *Separate Color* → R = oclusión (vía el grupo de nodos "glTF Material Output" del exportador; añádelo desde el addon si tu versión no lo trae), G = rugosidad, B = metálico. **Nada de mezclas de texturas ni nodos procedurales** en los materiales finales (el exportador no los soporta): cualquier combinación se hornea antes en Python.
4. **QA visual:** renderiza (Eevee o Cycles, luz de día con sol a 45° y cielo despejado) desde los ángulos de las refs 1, 2, 3, 4 y 5; guárdalos en `render_qa/` y compáralos con las refs. Corrige hasta que ritmo de ventanas, color del concreto, grafiti y tejado coincidan.

### FASE G · Exportación, validación y entrega
1. Exporta **GLB** con `bpy.ops.export_scene.gltf` (script en Apéndice B): solo mallas del edificio, modificadores aplicados, +Y arriba, sin cámaras ni luces, **sin compresión Draco/meshopt** (no se sabe si el cargador del juego la soporta), texturas embebidas. Exporta también las texturas sueltas a `texturas/` (el editor permite poner texturas desde el inspector). FBX opcional (el editor también lista .fbx).
2. **Valida:** `glb_tris()` sobre el archivo exportado (≥ 100 000), tamaño del GLB (objetivo ≤ 60 MB; si lo supera, baja la calidad JPEG, no los triángulos), memoria de texturas según §4 (≤ 200 MB), dimensiones (14 × 10 × ≈ 18 m con tejado), origen en la base, escala 1 = 1 m, orientación (fachada A hacia +Z en glTF). Reimporta el GLB en una escena limpia de Blender y comprueba materiales y UV.
3. **Reporte final** `REPORTE.md` + resumen al usuario (ver abajo).

## 7. Entrega

```
entrega/
  refs_higgsfield/     B1–B6 (PNG, máxima resolución)
  lettering/raw/       piezas sobre verde
  lettering/cutouts/   PNG RGBA recortados
  texturas/            T1–T5, G_A–G_D (albedo .jpg, normal .png, orm .png)
  blender/             APT5_chicano.blend
  export/              APT5_chicano_5p.glb (+ .fbx opcional)
  render_qa/           5 comparativas con las refs
  REPORTE.md
```
Si Blender y tu sandbox usan rutas distintas, usa una ruta absoluta que ambos vean y dile al usuario cuál es.

**Reporte final (obligatorio):** triángulos medidos del GLB (total y por bloque aproximado), tamaño del GLB, dimensiones, lista de materiales y texturas con resolución, memoria de texturas calculada, modelos de Higgsfield usados y confirmación de que todos fueron ilimitados (créditos de pago gastados: 0), desviaciones respecto a este brief y problemas conocidos. **Cómo cargarlo:** abrir `localhost:5173/mapa.html` → "Subir modelos o texturas…" → elegir el GLB (y las texturas sueltas si se quieren asignar desde el inspector) → clic en el modelo de la lista para colocarlo.

---

# APÉNDICE A · Prompts (en inglés, listos para pegar)

**Cadena de estilo común (`STYLE`):** *photorealistic game-ready asset reference, gritty post-apocalyptic tropical island setting, realistic physically-plausible materials, matte surfaces, slightly desaturated natural color grading, no stylization, no cartoon, no text overlays, no watermark.*

### Fase B · referencias del edificio
**B1 · Hero 3/4** (refs 1, 4, 5 adjuntas)
```
A five-story abandoned concrete apartment block with a gabled two-slope roof of weathered rust-red clay tiles and exposed wooden rafter tails under the eaves, seen from a three-quarter view at eye level, standing on flat sandy ground, soft overcast daylight, no hard cast shadows. Wide facade of weathered grey concrete with dark vertical rain streaks, peeling paint patches, hairline cracks and spalled corners. Each floor has two vertical cream-beige panel strips, each strip with a small dark rectangular window opening in its middle third (some with broken glass), thin protruding horizontal concrete slab bands between floors, a thick overhanging concrete cornice under the roof. The entire ground floor is covered with layered street graffiti and Chicano lettering: fine black calligraphic script reading "Mi Vida Loca", red handstyle tags, white bubble-letter throw-ups with black outline, golden-yellow blocks, cobalt-blue pieces, concrete showing through. Dark navy-blue metal door centered on the ground floor with a cream panel above it and two concrete steps. Match the architecture, proportions and weathering of the attached reference images. STYLE
```
**B2 · Elevación frontal (cara ancha)**
```
Flat straight-on front elevation of the same five-story concrete apartment block, perfectly frontal, no perspective, no vanishing points, building fills the frame, plain neutral grey background, flat even lighting with no cast shadows. Show the window-strip grid (two strips per floor), slab bands, cornice, tiled gabled roof edge, graffiti-covered ground floor with central navy-blue door. STYLE
```
**B3 · Elevación lateral (cara angosta, vidrios rotos)** — igual que B2 pero *"narrow side elevation with the gable end visible as a triangular concrete wall with a small attic window, windows with broken glass, heavier damage and exposed rebar"*.
**B4 · Tejado y alero** — *"close-up of the clay-tile gabled roof, ridge caps, exposed wooden rafter tails under the eave, gutter and downspout, aged rust-red terracotta tiles with moss and sun fading, eye-level three-quarter view, overcast light"* (ref 5 adjunta).
**B5 · Detalles de fachada** — *"reference sheet of architectural details of the same building on a plain grey background: cream-beige panel strip with window opening and broken glass shards, concrete slab band, overhanging cornice, navy-blue metal door with steps, spalled concrete with exposed rebar, rusted air-conditioning unit, drain pipe"*. 
**B6 · Grafiti de planta baja (objetivo de estilo)** — *"straight-on view of a concrete ground-floor wall covered in layered graffiti exactly in the style of the attached reference crops: thin black calligraphic script 'Mi Vida Loca', red handstyle tag, white bubble letters with black outline, golden-yellow block piece, cobalt-blue pieces, small black tags, concrete visible between layers, flat even lighting"* (crops de grafiti adjuntos).

### Fase C · lettering (piezas aisladas sobre verde chroma)
**Plantilla:** `Isolated spray-paint graffiti artwork of the text "{TEXT}" in {STYLE_DESC}, {COLORS}. The artwork sits centered on a perfectly flat uniform pure green background (#00FF00), no wall, no floor, no texture, no shadow on the background, no other text, flat front-on view, crisp clean edges, 10% empty margin around the artwork, no green anywhere in the artwork. The lettering must read exactly: "{TEXT}".` Formato 3:2 para palabras, 1:1 para hojas.

| ID | TEXT | STYLE_DESC | COLORS |
|---|---|---|---|
| C01 | Mi Vida Loca | fine-line Chicano calligraphic script with long flourish underline and swashes (like the reference) | black ink with thin white outline |
| C02 | Isla Negra | Old English blackletter, small crown above | white fill, thick black outline, gold drop shadow |
| C03 | Con Safos | Chicano flowing script plus a small "C/S" monogram | white and gold, black outline |
| C04 | Por Vida | Chicano script with two roses and thorny vines | black with red roses, white outline |
| C05 | Familia | Old English blackletter | gold-to-white gradient fill, black outline, red shadow |
| C06 | Respeto | pointed-brush calligraphy with sharp serifs | black, white highlight |
| C07 | Sin Miedo | Old English blackletter with 3D bevel | white fill, black outline, cobalt-blue shadow |
| C08 | Puro Corazón | script with a simple stylized heart | red and white, black outline |
| S01 | KAOS | fat inflated bubble-letter throw-up, glossy highlights, drips | chrome silver fill, black outline |
| S02 | ZORO | wildstyle interlocking arrowed letters | red, white and black |
| S03 | NOVA | heavy block letters with hard 3D shadow | golden yellow, black shadow, white highlights |
| S04 | REXO | fast marker handstyle tag, one-stroke | red |
| S05 | (hoja) | **sheet of six different marker handstyle tags** reading KAOS, ZORO, NOVA, REXO, DEMO, LUNA, arranged in a clean 3×2 grid with wide gaps | black and cobalt blue |
| S06 | (hoja) | **sheet of six stencil icons** in a 3×2 grid: skull with roses, crown, heart, star, eye, two theatre masks (smile now cry later) | black and red |
| S07 | (hoja) | **sheet of paint drips and splatter overlays** in a 3×2 grid, long vertical drips and spray splatters | black, red, cobalt blue |

### Fase D · texturas (1:1, vista cenital plana, sin sombras, sin objetos, sin texto)
**D1 `concrete_A`:** `Seamless tileable texture, flat top-down orthographic photo scan of a weathered poured-concrete building wall, warm light grey, patches of peeling and flaking old paint exposing darker concrete beneath, dark vertical rain streaks, hairline cracks, faint efflorescence, a few formwork tie-holes, absolutely even soft lighting with no shadows, no perspective, no vignette, no objects, no text, edges continue seamlessly, photorealistic PBR albedo.`
**D2 `panel_beige`:** *seamless tileable chalky cream-beige painted plaster, sun-faded, hairline cracks, dirt streaks, even lighting, flat top-down.*
**D3 `roof_tile`:** *seamless tileable top-down pattern of aged rust-red terracotta curved barrel roof tiles, moss in the grooves, sun-faded, even lighting.* (Sin sombras duras.)
**D4 `wood_weathered`:** *seamless tileable weathered dark-brown wooden planks, vertical grain, cracks, grey sun-bleached patches, even lighting, flat front-on.*
**D5 `door_blue_metal`:** *flat front-on dark navy-blue painted metal door with scratches, rust at the edges, subtle dents, a small black marker tag, even lighting, 2:3 vertical.*

---

# APÉNDICE B · Scripts

### B.1 `texture_tools.py` (probado: Python 3.13, Pillow, numpy)
Resultado de las pruebas: `make_seamless` baja el salto de borde de 71,6 a 0,6 (igual al ruido entre vecinos); `key_out` deja alfa 0 en el fondo y 255 en el contenido; `compose_panel` respeta `keepout`; `glb_tris` cuenta bien nodos que reutilizan malla.

```python
"""texture_tools.py - utilidades de textura para el edificio BLACKISLE (numpy + Pillow)."""
import json
import struct

import numpy as np
from PIL import Image, ImageFilter


def _blur(a, r):
    """Desenfoque gaussiano de un array float 2D en 0..1 (devuelve float32)."""
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255.0


def _lum(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0


def make_seamless(src, dst, border=0.25):
    """Hace repetible una textura: cross-fade con la copia desplazada 50 %, primero en X y luego en Y.
    border (0..0.5) = ancho de la zona de mezcla respecto al tamaño de la imagen."""
    a = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    h, w, _ = a.shape

    def ramp(n):
        d = np.minimum(np.arange(n), n - 1 - np.arange(n)) / (border * n)  # 0 en el borde, 1 desde `border`
        t = np.clip(d, 0, 1)
        return t * t * (3 - 2 * t)

    mx = ramp(w)[None, :, None]
    a = a * mx + np.roll(a, w // 2, axis=1) * (1 - mx)
    my = ramp(h)[:, None, None]
    a = a * my + np.roll(a, h // 2, axis=0) * (1 - my)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(dst, quality=95)


def make_normal(albedo, dst, strength=6.0, detail=1.2, lowcut=24.0):
    """Normal map (OpenGL, Y+) falsa a partir de la luminancia del albedo (alto-paso para quitar sombras horneadas)."""
    g = _lum(albedo)
    h = _blur(g, detail) - _blur(g, lowcut)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.dstack([-dx, dy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(dst)


def make_orm(albedo, dst, rough=0.85, rough_var=0.15, ao_strength=1.0, metal=0.0):
    """Mapa ORM de glTF: R = oclusión, G = rugosidad, B = metálico."""
    g = _lum(albedo)
    cav = g - _blur(g, 6)  # negativo en cavidades
    ao = np.clip(1.0 + ao_strength * np.minimum(cav, 0) * 3.0, 0.4, 1.0)
    r = np.clip(rough - rough_var * (g - g.mean()) * 2.0, 0.45, 1.0)
    orm = np.dstack([ao, r, np.full_like(g, metal)])
    Image.fromarray((orm * 255).astype(np.uint8)).save(dst)


def key_out(src, dst, lo=40.0, hi=110.0, margin=8):
    """Quita un fondo VERDE chroma (0,255,0) plano. Guarda PNG RGBA recortado al contenido, con despill."""
    a = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    d = np.linalg.norm(a - np.array([0, 255, 0], np.float32), axis=2)
    alpha = np.clip((d - lo) / (hi - lo), 0, 1)
    rgb = a.copy()
    rgb[..., 1] = np.minimum(rgb[..., 1], np.maximum(rgb[..., 0], rgb[..., 2]))  # despill del verde
    ys, xs = np.where(alpha > 0.05)
    if len(ys) == 0:
        raise ValueError("key_out: no queda contenido; revisa que el fondo sea verde plano")
    y0, y1 = max(ys.min() - margin, 0), min(ys.max() + margin, a.shape[0])
    x0, x1 = max(xs.min() - margin, 0), min(xs.max() + margin, a.shape[1])
    out = np.dstack([rgb, alpha * 255])[y0:y1, x0:x1].astype(np.uint8)
    Image.fromarray(out, "RGBA").save(dst)


def compose_panel(base_tile, pieces, size_px, px_per_m, keepout, out, tile_m=3.0, seed=7, opacity=0.92):
    """Pinta lettering/grafiti RGBA sobre concreto repetible y guarda el albedo del panel.
    pieces : [{"png": ruta RGBA, "x": m, "y": m, "w": m, "rot": grados, "op": 0..1}]
             (x, y = centro de la pieza en metros desde la esquina inferior izquierda de la cara)
    keepout: [(x0, y0, x1, y1)] en metros donde NO se pinta (puerta, ventanas)."""
    W, H = size_px
    rng = np.random.default_rng(seed)
    tile = Image.open(base_tile).convert("RGB")
    tw = max(int(tile_m * px_per_m), 8)
    tile = tile.resize((tw, tw), Image.LANCZOS)
    base = Image.new("RGB", (W, H))
    for ty in range(0, H, tw):
        for tx in range(0, W, tw):
            t = tile
            if rng.random() < 0.5:
                t = t.transpose(Image.FLIP_LEFT_RIGHT)
            if rng.random() < 0.5:
                t = t.transpose(Image.FLIP_TOP_BOTTOM)
            base.paste(t, (tx, ty))
    base = np.asarray(base, np.float32) / 255.0

    canvas = np.zeros((H, W, 4), np.float32)  # RGB recto + alfa
    for p in pieces:
        im = Image.open(p["png"]).convert("RGBA")
        pw = max(int(p["w"] * px_per_m), 2)
        im = im.resize((pw, max(int(im.height * pw / im.width), 2)), Image.LANCZOS)
        if p.get("rot"):
            im = im.rotate(p["rot"], expand=True, resample=Image.BICUBIC)
        arr = np.asarray(im, np.float32) / 255.0
        cx, cy = int(p["x"] * px_per_m), int(H - p["y"] * px_per_m)
        x0, y0 = cx - arr.shape[1] // 2, cy - arr.shape[0] // 2
        sx0, sy0 = max(-x0, 0), max(-y0, 0)
        x0c, y0c = max(x0, 0), max(y0, 0)
        x1c, y1c = min(x0 + arr.shape[1], W), min(y0 + arr.shape[0], H)
        if x1c <= x0c or y1c <= y0c:
            continue
        src = arr[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)]
        dst = canvas[y0c:y1c, x0c:x1c]
        pa = src[..., 3:4] * p.get("op", 1.0)
        oa = pa + dst[..., 3:4] * (1 - pa)
        dst[..., :3] = (src[..., :3] * pa + dst[..., :3] * dst[..., 3:4] * (1 - pa)) / np.maximum(oa, 1e-6)
        dst[..., 3:4] = oa

    for (kx0, ky0, kx1, ky1) in keepout:
        canvas[int(H - ky1 * px_per_m):int(H - ky0 * px_per_m), int(kx0 * px_per_m):int(kx1 * px_per_m), 3] = 0

    lum = base.mean(axis=2)
    hp = _blur(lum, 1.0) - _blur(lum, 8.0)  # relieve del concreto que debe "atravesar" la pintura
    paint = canvas[..., :3] * np.clip(1.0 + hp * 2.5, 0.7, 1.3)[..., None]
    pl = paint.mean(axis=2, keepdims=True)
    paint = np.clip(paint * 0.88 + pl * 0.12, 0, 1)  # pintura algo desteñida por el sol
    a = (canvas[..., 3:4] * opacity)
    res = base * (1 - a) + paint * a
    Image.fromarray((np.clip(res, 0, 1) * 255).astype(np.uint8)).save(out, quality=95)


def glb_tris(path):
    """Triángulos reales de un .glb (cuenta cada nodo que usa la malla)."""
    with open(path, "rb") as f:
        f.read(12)
        length, _ = struct.unpack("<II", f.read(8))
        j = json.loads(f.read(length))
    uses = {}
    for n in j.get("nodes", []):
        if "mesh" in n:
            uses[n["mesh"]] = uses.get(n["mesh"], 0) + 1
    total = 0
    for i, m in enumerate(j.get("meshes", [])):
        for p in m["primitives"]:
            if p.get("mode", 4) == 4:
                cnt = j["accessors"][p["indices"]]["count"] if "indices" in p else j["accessors"][p["attributes"]["POSITION"]]["count"]
                total += (cnt // 3) * uses.get(i, 0)
    return total
```

Uso típico:
```python
make_seamless("raw/T1.png", "tex/T1_seamless.png")
make_normal("tex/T1_seamless.png", "tex/T1_n.png"); make_orm("tex/T1_seamless.png", "tex/T1_orm.png", rough=0.85)
key_out("lettering/raw/C01.png", "lettering/cutouts/C01.png")
compose_panel("tex/T1_seamless.png", pieces, (4096, 1024), 292, [(6.3, 0, 7.7, 2.8)], "tex/G_A.jpg")
print(glb_tris("export/APT5_chicano_5p.glb"))
```

### B.2 Blender (sin probar en este entorno: verifica en tu versión)
**Conteo de triángulos evaluados (modificadores incluidos):**
```python
import bpy
dg = bpy.context.evaluated_depsgraph_get()
tot = 0
for o in bpy.context.scene.objects:
    if o.type == 'MESH' and o.visible_get():
        eo = o.evaluated_get(dg); me = eo.to_mesh()
        tot += sum(len(p.vertices) - 2 for p in me.polygons); eo.to_mesh_clear()
print("TRIS:", tot)
```
**UV de caja con escala de mundo y sin texto en espejo** (llámala con `bm` en modo objeto; `size` en metros por unidad UV):
```python
import bmesh
def box_uv(obj, size=3.0, offset=(0.0, 0.0)):
    bm = bmesh.new(); bm.from_mesh(obj.data); uv = bm.loops.layers.uv.verify()
    mw = obj.matrix_world
    for f in bm.faces:
        n = (mw.to_3x3() @ f.normal); ax = max(range(3), key=lambda i: abs(n[i])); s = 1 if n[ax] > 0 else -1
        for l in f.loops:
            c = mw @ l.vert.co
            if ax == 0:   u, v = (c.y if s > 0 else -c.y), c.z      # ±X: mirando desde fuera
            elif ax == 1: u, v = (-c.x if s > 0 else c.x), c.z      # ±Y
            else:         u, v = c.x, c.y                           # ±Z (techos/suelos)
            l[uv].uv = (u / size + offset[0], v / size + offset[1])
    bm.to_mesh(obj.data); bm.free()
```
(Para los paneles de grafiti usa la misma regla de la mano pero normalizando a 0–1 sobre el ancho/alto de la cara: `u = (u_m - u_min) / W`, `v = v_m / 3.5`.)
**Exportación GLB** (confirma los nombres de parámetros con `bpy.ops.export_scene.gltf.get_rna_type()` en tu versión):
```python
bpy.ops.export_scene.gltf(filepath=r"<ruta>/APT5_chicano_5p.glb", export_format='GLB', use_selection=True,
    export_apply=True, export_yup=True, export_image_format='AUTO', export_cameras=False, export_lights=False,
    export_draco_mesh_compression_enable=False)
```
Selecciona antes solo los objetos `APT5_*` (mallas).

# BRIEF DE EJECUCIÓN · Kit BLACKISLE de calidad de estudio: 4 edificios de departamentos (3–5 pisos) + 3 cabañas de 2 pisos

**Proyecto:** BLACKISLE (FPS en Three.js; editor de mapa en `localhost:5173/mapa.html`)
**Tu rol:** ejecutor y director de arte técnico. Esto es una orden de trabajo, no una lluvia de ideas. Léela completa antes de tocar una herramienta, ejecútala por fases y respeta los puntos de control.
**Herramientas requeridas:** Higgsfield (MCP `mcp__Higgsfield__*`), Blender (conector/MCP de Blender; Cycles disponible para hornear) y Python con numpy + Pillow.
**Idioma de trabajo:** español. Los prompts para los modelos de imagen van en inglés (ya están redactados abajo).

---

## 1. Misión y listón de calidad

Producir para el mapa de BLACKISLE un **kit de 7 modelos con calidad de estudio profesional**, realistas, de arquitectura creíble. Del material de referencia del usuario se conserva **solo** el color (gris de concreto desgastado) y el grafiti; **la geometría de las capturas es una caja con huecos hecha a toda prisa y NO es la meta** (§3).

| ID | Tipo | Pisos | Tipología (detalle en §4) | Planta (m) | Cubierta |
|---|---|---|---|---|---|
| `APT_A_5p` | Departamentos | 5 | **Bloque de marco de concreto** con pilotis comercial, loggias y núcleo de escalera con celosía. **Piloto** | 14,4 × 10,8 | cuatro aguas, teja |
| `APT_B_4p` | Departamentos | 4 | **Bloque de corredor de acceso** (galería exterior) con torre de escalera; esquina colapsada | 14,4 × 8,4 (+1,5 galería) | cuatro aguas, teja |
| `APT_C_3p` | Departamentos | 3 | **Edificio en L** con dos alas, valle de tejado y marquesina de entrada | 12,0 × 6,6 + ala 6,6 × 5,4 | dos aguas con valle, teja |
| `APT_D_4p` | Departamentos | 4 | **Bloque de paneles prefabricados** con juntas, balcones en voladizo y escalera de emergencia | 13,5 × 9,0 | dos aguas con 3 buhardillas, teja |
| `CAB_1_tablones` | Cabaña | 2 | Casa de entramado de madera con tablones y junquillos, porche lateral | 9 × 6 | dos aguas, lámina óxido |
| `CAB_2_pilotes` | Cabaña | 2 | **Palafito**: cabaña elevada sobre pilotes con veranda y escalera exterior | 7 × 6 | dos aguas, lámina clara |
| `CAB_3_ladrillo` | Cabaña | 2 | Planta baja de **ladrillo individual**, piso alto de madera, porche y chimenea | 8 × 6,5 | dos aguas, tablones grises |

Los **departamentos** llevan la planta baja cubierta de grafiti (lettering chicano + street). Las **cabañas** no llevan grafiti (como mucho 1–2 tags en la base de ladrillo de CAB_3).

**Qué significa "calidad de estudio profesional" (todos deben cumplirse):**
1. **Arquitectura legible y creíble:** estructura (columnas, vigas, losas), escala humana correcta, sistemas (bajantes, cableado, ventilación), nada flotando.
2. **Silueta rica:** volúmenes escalonados, voladizos, huecos, remates, valles; nunca una caja.
3. **Muchos elementos secundarios:** ≥ 30 elementos distintos por modelo (lista en §4.5).
4. **Materiales por capas** (≥ 6 materiales físicos) y **envejecimiento por capas** (§4.6), no una textura única repetida.
5. **Imperfección controlada:** nada perfectamente recto ni limpio; desplomes leves, barandales doblados, persianas desalineadas, piezas faltantes.
6. **Contacto con el suelo:** base integrada (arena acumulada, hierba, escombro, zócalo manchado).
7. **Textura única horneada** sin repetición visible a 15 m, con micro-detalle a 2 m.
8. **Lectura a tres distancias:** silueta a 50 m, materiales a 15 m, micro-detalle a 2 m.

Pipeline: (1) investigación y conceptos fotorrealistas con IA → el usuario aprueba; (2) lettering chicano y street; (3) biblioteca de materiales PBR; (4) modelado modular en Blender, **cada modelo con más de 100 000 triángulos reales**; (5) revisión en arcilla; (6) look-dev por capas y **horneado a texturas únicas**; (7) QA y exportación a GLB.

## 2. Reglas duras (no negociables)

**R1 · Créditos: SOLO modelos con generaciones ilimitadas.** El usuario lo ordenó expresamente.
- Lista vigente: `models_explore(action:'list', unlim:true)`. Al 2026-10-09 los de imagen son `gpt_image_2`, `nano_banana_pro`, `nano_banana_2`, `nano_banana`, `seedream_v4_5`, `seedream_v5_pro`, `seedream_v5_lite`, `flux_2`, `kling_omni_image` (y `soul_2`, que no sirve aquí).
- **NO usar** (no figuran como ilimitados): `nano_banana_2_1`, `flux_3_image`, **todos los modelos 3D** (`generate_3d`, Tripo, Hunyuan3D, Meshy, SAM 3D) y las herramientas `upscale_image` y `remove_background`. El 3D se hace en Blender; el recorte de fondo se hace en local (Apéndice B); la resolución se pide directamente al modelo.
- Pasa `use_unlim: true` explícito en **cada** `generate_image` / `generate_image_batch`. En batch cada ítem es `count: 1`.
- Lee el bloque `unlim` de la respuesta de `models_explore` y el texto "Unlim configs": usa solo las combinaciones de resolución/calidad que la cuota realmente cubre.
- Si `unlim.available` es `false`, o el modelo/configuración no está cubierto: **DETENTE y pregunta al usuario. Nunca gastes créditos de pago por tu cuenta.** (Aviso: al preparar este brief, 2026-10-09, la API devolvió `unlim.available=false, remaining=null` con plan Ultra y 517,26 créditos. Verifícalo en el paso A-3 y repórtalo tal cual.)

**R2 · Triángulos, por modelo.** Cada GLB exportado debe tener **≥ 100 000 triángulos reales** (objetivo: departamentos 200 000–450 000; cabañas 150 000–300 000; techo 600 000). Deben ser geometría útil (detalle arquitectónico, daño, tejas, tablones, ladrillos, elementos secundarios), **no** subdivisión de planos para inflar el número.

**R3 · Topología de calidad** (criterios en §5). Un modelo con muchos triángulos sucios se rechaza.

**R4 · Contenido seguro.** Lettering con palabras inocuas (las listadas). PROHIBIDO: nombres, números, siglas o símbolos de pandillas reales (13, 14, 18, MS, X3, Norte/Sur, etc.), símbolos de odio, personas reales y marcas comerciales. Los "crews" (KAOS, ZORO, NOVA, REXO) son ficticios.

**R5 · Verifica con tus ojos.** Abre cada imagen generada y cada render. Si una palabra sale mal escrita, regenera esa pieza.

**R6 · Trazabilidad.** Guarda todo en la carpeta de entrega (§7). Guarda el `.blend` tras cada tramo grande. Descarga cada resultado de Higgsfield a disco local a máxima resolución.

**R7 · Cero invención.** Reporta números reales (triángulos medidos, tamaños, memoria). Si falta una herramienta o algo falla: detente y dilo; no improvises sustitutos.

**R8 · Ambigüedad.** Las decisiones ya tomadas están en §4. Si algo no está cubierto, elige lo más razonable, regístralo y sigue; pregunta solo si es bloqueante.

**R9 · Piloto primero.** Termina `APT_A_5p` de punta a punta (hasta GLB validado) antes de empezar los otros seis.

**R10 · Cada modelo es distinto.** No vale clonar y recolorear: silueta, ritmo de huecos, daño y composición de grafiti propios (semilla propia). Comparte librerías (módulos, texturas, lettering), no resultados.

**R11 · Continuidad.** Mantén `entrega/ESTADO.md` (terminado/pendiente, parámetros, rutas, problemas). Si el contexto se acerca al límite, guarda el estado y pide al usuario un chat nuevo con este brief + `ESTADO.md`.

**R12 · Rechazo automático.** Rehaz el modelo (no lo entregues) si ocurre cualquiera: fachada plana con solo huecos; repetición de textura visible a 15 m; aristas perfectas sin desgaste; < 30 elementos secundarios; sin elementos de escala humana; materiales planos o un solo material; aspecto "limpio" o de maqueta; artefactos de sombreado o z-fighting; parecido a las capturas de referencia más que a los conceptos aprobados.

## 3. Las 5 referencias: qué conservar y qué NO copiar

Capturas del propio juego (render Three.js, día despejado, isla con dunas y palmeras), recortadas al viewport 3D en `blackisle-kit-edificios/referencias/` del repositorio. Si no puedes leer el repo, usa las capturas adjuntas y recórtalas a (x 578–1581, y 149–888) sobre 1920×1080.

**Conservar:** (a) el **gris de concreto desgastado** con manchas verticales de lluvia, descascarado y parches de pintura vieja; (b) el **grafiti de planta baja**: capas de tags finos negros/azules, **"Mi Vida Loca" en script caligráfico fino negro con florituras**, handstyle rojo, burbuja blanca con contorno negro, bloque amarillo dorado, manchas azul cobalto, concreto visible entre capas (paleta: negro, blanco, rojo, azul cobalto, amarillo dorado; crops `ref_grafiti_planta_baja_1/4`); (c) la escala de pisos (~3 m) y que el grafiti sube ~1 m dentro del piso 2; (d) el contexto: isla de arena, dunas, palmeras, hierba seca.
**NO copiar:** la geometría de caja con huecos, las franjas beige planas, las ventanas como rectángulos oscuros, la azotea plana con caja de escalera, las bandas de losa como únicos detalles. Eso es lo que el usuario rechazó por simple.
Por referencia: **1** cara ancha con puerta central; **2** cara angosta en sombra con vidrios rotos y, a la izquierda, una **cabaña sobre pilotes**; **3** cara ancha en sombra, a la derecha una casa de tablones casi negros con techo gris claro de alero escalonado y a la izquierda una **casa de ladrillo rojo** con techo rojo y marcos blancos; **4** cara angosta y, al fondo, un edificio azul-grisáceo oscuro con muchas ventanas pequeñas; **5** **casa de madera de 2 pisos** con tablones verticales marrón oscuro, **tejado óxido con cabios (vigas) vistos** en el alero y el hastial y banda marrón-rojiza entre pisos (base de `CAB_1`).

## 4. Diseño

### 4.1 Contexto y lenguaje arquitectónico
Vivienda social de **marco de concreto armado de los años 70–80** (estilo "multifamiliar" latinoamericano/brutalista tropical), abandonada ~30 años en una isla de aire salino y húmedo: corrosión de varillas con desconche, eflorescencia, algas y manchas de lluvia, pintura vieja descascarada (ocre, crema, azul pálido) sobre concreto gris, óxido, arena acumulada, maleza y enredaderas, saqueo (ventanas y rejas arrancadas), grafiti en planta baja. Color dominante: **gris concreto desgastado**. Tejados de teja de barro (departamentos) y cubiertas de lámina/tablón (cabañas) con daño parcial.

### 4.2 Escala humana y módulos (usa estas cifras; añade un maniquí de 1,80 m para verificar escala)
Alto de piso 2,9 m (PB 3,0–3,4 m) · losa 0,20 m · viga de borde 0,25 × 0,50 m · columna 0,35 × 0,35 m (esquinas 0,45) · malla estructural 3,6 m (paneles prefab 2,7 m) · antepecho de ventana 0,90 m, dintel 2,10 m, ventana 1,2–1,8 m de ancho · puerta de departamento 0,90 × 2,05 m, portón de acceso 1,6 × 2,3 m · barandal 1,00 m · peldaño 0,17 alto × 0,28 huella, escalera 1,2 m de ancho · bajante Ø 0,10 m · canalón 0,12 m · unidad de A/C de ventana 0,60 × 0,40 × 0,45 m.
Ejes y unidades: 1 unidad Blender = 1 m; Z arriba; **origen en el centro de la base sobre el suelo (z = 0)**; escala y rotación aplicadas; fachada principal mira a −Y de Blender (= +Z en glTF). Prefijo del ID en objetos y materiales (`APT_A_…`).

### 4.3 Departamentos
| | `APT_A_5p` | `APT_B_4p` | `APT_C_3p` | `APT_D_4p` |
|---|---|---|---|---|
| Niveles / altura | PB 3,4 + 4 × 2,9 = **15,0 m** | PB 3,2 + 3 × 2,9 = **11,9 m** | PB 3,2 + 2 × 2,9 = **9,0 m** | PB 3,0 + 3 × 2,9 = **11,7 m** |
| Estructura | marco de concreto **visible** (columnas, vigas de borde, cantos de losa) con paños de relleno rehundidos 8 cm | marco de concreto + paños de **ladrillo** que asoma bajo el aplanado desprendido | marco + muros de bloque aplanado | **paneles prefabricados** de 2,7 m con juntas rehundidas 2 cm (manchas de sellador) |
| Huecos | por vano de 3,6 m: ventana corrediza de aluminio 1,6 × 1,3 m **o** loggia rehundida 1,2 m con barandal; marcos con vidrio roto, cortinas rasgadas | puertas 0,9 × 2,05 + ventanas pequeñas hacia la galería; ventanas de cocina atrás | ventanas 1,4 × 1,3 m y balcones en la esquina interior | ventanas 1,2 × 1,2 m; balcones en voladizo (losa 1,2 m, barandal metálico) cada 2 módulos |
| Planta baja | **pilotis comercial**: lobby de acceso rehundido con puertas dobles + 2 locales con **cortinas metálicas enrollables abolladas**, todo con grafiti | zócalo con rejas y 2 puertas de bodega | acceso bajo **marquesina** de concreto (2,4 × 1,2 × 0,2 m sobre 2 columnas) | banda baja con grafiti y portón |
| Pieza firma | **núcleo de escalera con celosía de bloques** (bloques de 20 × 20 cm individuales con aberturas) | **galería de acceso** de 1,5 m con barandal de balaustres de concreto + **torre de escalera**; esquina NE colapsada con varillas y escombro | **planta en L** con valle de tejado y chimenea de ventilación | **escalera de emergencia** metálica en zigzag + 3 buhardillas |
| Tejado de teja | cuatro aguas 26°, cabios vistos, daño en una vertiente | cuatro aguas 26° | dos aguas 30° con valle | dos aguas 28° con buhardillas |
| Concreto (acento de color) | gris cálido, parches ocre/crema | gris medio, ladrillo rojo visible | gris con tinte verdoso, algas | **gris-azul oscuro**, parches azul pálido |
| Daño | repartido; una cara muy dañada | **esquina colapsada** | moderado, vegetación fuerte | fuerte en cornisa y balcones |

Comunes: teja de barro curva con **cabios vistos**, caballetes, canalón y bajantes, chimeneas/ventilaciones, hastiales/frontones con ventana de ático donde la cubierta sea a dos aguas; puertas con hoja entreabierta (geometría separada); **sin cristales intactos** (esquirlas en los marcos).
Caras anchas con acceso: puerta o portón centrado y grafiti denso; caras angostas: ventanas también en PB.

### 4.4 Cabañas (sin concreto; la geometría hace el trabajo)
| | `CAB_1_tablones` | `CAB_2_pilotes` | `CAB_3_ladrillo` |
|---|---|---|---|
| Planta / alturas | 9 × 6 m; 2 × 2,8 m + zócalo 0,3 | 7 × 6 m; pilotes 1,2 m + 2 × 2,6 m | 8 × 6,5 m; 2 × 2,8 m + zócalo 0,3 |
| Muros | **entramado visible** (postes de esquina, soleras) con **tablones verticales** de 0,22 m, rendija 0,04 y **junquillos**, marrón oscuro; banda marrón-rojiza entre pisos | **tablas horizontales traslapadas** (clapboard) gris blanqueado, 0,15 m de traslape, esquineros | **PB de ladrillo individual** (aparejo a soga, juntas rehundidas, dinteles y alféizares de piedra) + **piso alto de tablones claros** con marcos blancos |
| Cubierta | dos aguas 35°, **lámina corrugada óxido** con tornillos, **cabios vistos** en alero y hastial (ref 5), caballete | dos aguas 28°, **lámina corrugada clara**, sección arrancada por el viento | dos aguas 30°, **tablones grises claros** con **alero escalonado** (ref 3), canalón |
| Pieza firma | **porche lateral** con 2 postes y techo a un agua, chimenea de estufa con tubo y sombrerete | **12 pilotes** con zapatas de concreto y riostras en X atornilladas, **veranda** de 1,2 m con balaustres, **escalera exterior** con pasamanos, cisterna debajo | **porche frontal** (2,4 × 6,5 m, 4 postes, barandal) y **chimenea de ladrillo** con remate |
| Daño | tablones faltantes/podridos, hueco en el techo, hierba entrando | tablas sueltas, deck hundido en una esquina | ladrillos caídos, grietas, persiana colgando |

Comunes: ventanas con marco de madera, hojas rotas y **postigos con bisagras**; puertas de tablones con travesaños y herrajes (aldaba, candado); escalones; canalón + barril de lluvia; **sin vidrios intactos**.

### 4.5 Mínimo de detalle: ≥ 30 elementos secundarios distintos por modelo
**Departamentos** (elige y reparte; todos con variaciones propias): unidades de A/C (≥ 6, de 2–3 tipos), haces de cables y ductos eléctricos con aisladores, bajantes y canalones, barandales de loggia/balcón (doblados), restos de ropa tendida y cortinas rasgadas, rejas de seguridad, cortinas metálicas, letreros arrancados, cajas de medidores, luminarias rotas, antenas y parabólicas, ventilas y chimeneas, tinaco/tanque, nidos de varillas expuestas (≥ 10), escombro colgante, marcos de ventana caídos, ventanas tapiadas con madera, buzones, gabinete de extintor vacío, plantas trepadoras, ménsulas, goteros bajo losas, números de edificio, escalones rotos.
**Cabañas:** postigos, bisagras y herrajes, canalón y barril, pila de leña, tubo de estufa y sombrerete, escalones y pasamanos, ganchos y herramientas colgadas, cuerdas, lonas, jardineras, cabezas de clavo, esquineros, dinteles, ménsulas de alero, manchas de agua, enredaderas, mallas, cajas, cubetas, zapatas, cisterna.

### 4.6 Envejecimiento por capas (receta de look-dev)
L0 concreto base · L1 aplanado/pintura vieja (ocre, crema, azul pálido) que **se descascara** mostrando L0 · L2 suciedad por **oclusión y cavidades** · L3 **chorreados de lluvia** verticales bajo salientes y alféizares · L4 **eflorescencia** blanca · L5 **óxido** sangrando desde varillas y metal · L6 **algas/musgo** en la base y caras norte · L7 **arena y polvo** en la base y superficies horizontales · L8 **desgaste de aristas** (más claro y áspero) · L9 grafiti con overspray y goteos. Cada capa se controla con máscaras (ruido, AO, Pointiness, gradiente en Z, orientación de la normal) y semilla propia por modelo.

### 4.7 Texturas, atlas y memoria
Biblioteca de **entradas** (IA, tileables 2048², solo para look-dev): concreto gris `T1`, aplanado/pintura vieja `T2`, ladrillo `S1`, teja `T3`, madera estructural `T4`, tablones oscuros `W1`, tablas grises `W2`, lámina corrugada `R1`, tablones de techo `R2`, metal oxidado `M1`; **máscaras en escala de grises** `K1` descascarado, `K2` chorreados, `K3` eflorescencia, `K4` musgo, `K5` grietas, `K6` manchas de óxido.
**Salida del modelo = texturas horneadas únicas** (albedo, normal, ORM) por grupo de superficies:

| Atlas (departamento) | Albedo | Normal | ORM |
|---|---|---|---|
| `walls_main` (cara principal + banda de grafiti) | 4096² | 2048² | 2048² |
| `walls_rest` (otras caras + interior) | 4096² | 2048² | 2048² |
| `details` (metal, A/C, marcos, puertas, balcones) | 2048² | 2048² | 1024² |
| `roof` (teja + estructura) | 2048² | 1024² | 1024² |

Cabañas: `walls` 3072², `details` 2048², `roof` 2048² (normal/ORM a 2048²/1024²).
**Densidad de texel:** ~170 px/m general; **~290 px/m en la banda de grafiti** de PB de la cara principal. Si no cabe, baja primero las caras traseras. **Presupuesto de memoria decodificada** (ancho × alto × 4 × 1,33 por mapa): **≤ 300 MB por departamento, ≤ 200 MB por cabaña**; si te pasas, reduce primero normal/ORM, luego albedos traseros.

## 5. Geometría y topología

| Bloque | Departamentos | Cabañas |
|---|---|---|
| Estructura (marco, losas, muros con espesor, vanos con jambas, biseles) | 25–60 k | 10–25 k |
| Ventanas, marcos, rejas, puertas, cortinas metálicas, esquirlas | 20–45 k | 8–15 k |
| Balcones/loggias/galerías, barandales, celosía de bloques, escaleras | 30–70 k | 10–40 k |
| **Revestimiento como geometría** (tablones, tablas, **ladrillos individuales**) | — | **35–75 k** |
| **Daño como geometría** (desconches, varillas, cortes, colapso, tablones podridos) | 40–80 k | 15–30 k |
| **Tejado** (tejas / lámina corrugada / tablones, cabios, canalón, buhardillas) | 30–80 k | 20–40 k |
| Elementos secundarios (§4.5) | 30–70 k | 10–30 k |
| Interior mínimo | 8–25 k | 10–20 k |
| Base/entorno inmediato (arena, escombro, vegetación opcional) | 5–30 k | 5–25 k |
| **Total esperado** | **200–450 k** | **150–300 k** |

**Criterios de aceptación de topología:**
- Cuadrilátero-dominante con flujo de aristas limpio. Ngons solo en caras planas antes de exportar; **cero triángulos/ngons en superficies curvas**. Se triangula al exportar.
- Biseles de 2 segmentos en todas las aristas duras ≥ 2 cm (marcos, losas, vanos, tablones, ladrillos, barandales).
- **Cero** geometría duplicada, caras coplanares solapadas (z-fighting), vértices sueltos, aristas no-manifold (salvo láminas intencionales: esquirlas, lámina) y caras de área cero.
- Normales hacia fuera; sombreado suave por ángulo (~30°) sin artefactos negros.
- Densidad coherente: planos grandes 10–25 cm de arista; zonas dañadas 1–3 cm.
- Modificadores y transformaciones aplicados, *merge by distance* 0,1 mm. Elementos repetidos como instancias durante el trabajo; se **materializan** al exportar.
- UV únicas sin solapes en los atlas, margen ≥ 16 px, estiramiento < 10 %.

## 6. Ejecución por fases

### FASE A · Preparación y verificación de entorno
1. Higgsfield: `balance`, `list_workspaces` (confirma conexión). `get_preferences` → hoy `auto_create_project = false`: **no crees proyecto ni pases `folder_id`** salvo que el usuario lo pida.
2. Blender: ejecuta un script mínimo (`import bpy, sys; print(bpy.app.version_string, sys.executable)`), comprueba `numpy` y que **Cycles** funciona (`bpy.context.scene.render.engine = 'CYCLES'`; detecta GPU). Si no hay conector de Blender: **detente y avisa**.
3. Créditos ilimitados: `models_explore(action:'list', unlim:true)` y lee `unlim` + "Unlim configs". Si `available` es `false` → R1. Registra qué modelos/configuraciones están cubiertos.
4. Sandbox/Python: comprueba `PIL` y `numpy`. Si Blender y tu sandbox **no comparten disco**, ejecuta el procesado de imágenes (Apéndice B) dentro de Blender (trae numpy; si falta Pillow, instálalo en su Python o usa `bpy.data.images` + numpy) o transfiere los archivos.
5. Crea la carpeta de entrega (§7) y `ESTADO.md`. Sube las referencias recortadas a Higgsfield: `media_upload` → `PUT` → `media_confirm` (si no puedes leer los archivos, `media_upload_widget` como única llamada de ese turno). Confirma roles/máximos con `models_explore(action:'get', model_id:…)` antes del primer uso de cada modelo.

### FASE B · Investigación y conceptos fotorrealistas (Higgsfield)
1. Si tienes búsqueda web, reúne referencias reales de la tipología (bloques de vivienda social de marco de concreto abandonados, edificios de corredor, paneles prefabricados, palafitos y cabañas de madera/ladrillo envejecidas) y anota en `ESTADO.md` qué rasgos reales vas a usar. Sin búsqueda, apóyate en la descripción de §4.
2. Modelo principal: **`nano_banana_pro`** (ilimitado, acepta `image_references`, hasta 4k). Alternos ilimitados: `seedream_v5_pro`, `flux_2`, `gpt_image_2`. Por cada modelo del kit genera **3 imágenes**: **hero 3/4**, **elevación frontal** y **primer plano de materiales y elementos secundarios**, con las plantillas H, E y M y los descriptores del Apéndice A (7 × 3 = 21 imágenes, 2 lotes de `generate_image_batch`). Adjunta las capturas pertinentes **solo como ancla de color, desgaste y grafiti** (el prompt ya lo dice). 2k, `use_unlim:true`. Espera con `jobs_wait` y muestra todo **una sola vez** con `show_generation_by_ids`.
3. Estos conceptos pasan a ser **la referencia de verdad** del look y la silueta. Las vistas "ortogonales" de IA no son perfectas: **las medidas de §4 mandan**.

### FASE C · Lettering chicano y street (Higgsfield) — en paralelo con la B
Modelo: **`gpt_image_2`** (ilimitado; el mejor en tipografía), 2k, la calidad más alta que cubra la cuota ilimitada. Respaldo ilimitado: `nano_banana_pro`. Lanza las piezas del Apéndice A (tabla C/S) con `generate_image_batch`. Fondo **verde chroma plano #00FF00**; el arte **no** contiene verde.
Por cada pieza aprobada: `key_out()` (Apéndice B) → PNG RGBA recortado. Las hojas (S05, S06, S07) se recortan por celdas de la cuadrícula. Esta biblioteca sirve a los 4 departamentos.

### ⛔ PUNTO DE CONTROL 1 — ESPERA AL USUARIO
Presenta: (a) contact sheet de los conceptos de los 7 modelos, (b) contact sheet del lettering recortado, (c) resumen de §4 con cualquier desviación. **No avances hasta que el usuario apruebe o corrija.** Si pide cambios, regenera solo lo necesario.

### FASE D · Biblioteca de materiales (Higgsfield + Python)
1. Genera con **`seedream_v4_5`** (ilimitado, hasta 4k) o `gpt_image_2` las entradas tileables (prompts D1–D10) y las **máscaras en escala de grises** K1–K6 (prompts D11–D16), todas 1:1 a 2k. Respaldo ilimitado: `nano_banana_pro`.
2. Hazlas repetibles con `make_seamless()` y **compruébalo** en mosaico 3×3; si queda costura visible, desplaza 50 % y repárala con `nano_banana_2` (ilimitado, rol `mask`, `is_inpaint:true`) enmascarando solo la cruz central. Las máscaras K se usan como imágenes *Non-Color*.
3. **Paneles de grafiti de PB** (4 caras × 4 edificios): `compose_panel()` con T1 como base y las piezas de la Fase C. Receta: banda = altura de PB + 0,7 m de desvanecimiento (p. ej. `APT_A`: 14,4 × 4,1 m ≈ 4176 × 1189 px a 290 px/m); cobertura ~85 % de la PB; capas en orden: tags de fondo → throw-ups street (S01–S04) → lettering chicano grande (C01–C08) → tags pequeños → máscaras/calaveras/iconos (S06) → goteos (S07) → 3–5 parches "buff" grises (1–2 m, op 0,9); sobre la PB solo 6–10 tags sueltos con densidad decreciente hasta +0,7 m. Palabras 2,5–4 m de ancho, tags 0,8–1,5 m, iconos 0,8–1,2 m; rotación ±12°; sin repetir la misma pieza seguida. **Semilla y subconjunto de piezas distintos por edificio** (R10); "Mi Vida Loca" como protagonista en 2 de los 4 como máximo. `keepout` = portones, puertas, vanos y cortinas metálicas de PB (los lee de la ficha de §4.3). Ejemplo, cara ancha de `APT_A` (14,4 m): `Mi Vida Loca` x=2.6 y=1.5 w=3.6 rot=−4 · `Isla Negra` x=11.4 y=1.7 w=4.2 rot=3 · `KAOS` x=4.8 y=0.8 w=2.6 · `ZORO` x=11.8 y=0.7 w=3.0 · `Con Safos` x=1.4 y=2.2 w=1.8 · `Por Vida` x=13.2 y=2.3 w=2.2.
4. Guarda en `texturas/` (los paneles en `texturas/graffiti/`).

### PUNTO DE CONTROL 2 — informativo (no esperes)
Contact sheet de la biblioteca + el panel `G_APT_A_A` compuesto.

### FASE E · Blender: modelado modular (piloto `APT_A_5p`, luego la serie)
Normas: envía código por tramos (≤ ~150 líneas por llamada), guarda `.blend` tras cada tramo, **usa bmesh/numpy en lugar de bucles con `bpy.ops`**, detecta la versión (`bpy.app.version`) y adapta la API. Para que la escena no se vuelva inmanejable: instancias para lo repetido, colecciones ocultables (`<ID>_Shell`, `_Details`, `_Roof`, `_Interior`, `_Damage`, `_Skirt`), vista en Solid mientras trabajas.
**E0 · Kit modular** (se hace una vez en el piloto y se reutiliza): ventanas (≥ 4 variantes: corrediza, de hojas, con postigo, tapiada) con marco, riel y esquirlas; puertas (≥ 3); barandales (balaustres de concreto, tubo metálico, madera) con parametrización de largo y doblez; unidades de A/C (≥ 3); generador de **haces de cables y ductos** sobre curvas; bajantes y canalones; nidos de varillas expuestas; bloques de celosía; peldaños y escaleras; generadores de **tejas**, **tablones**, **tablas traslapadas**, **ladrillos** (bmesh, con bisel y variación aleatoria); lámina corrugada; cortinas metálicas; antenas, parabólicas, tanques, buzones, luminarias. Todo con unidades reales (§4.2). Escribe constructores paramétricos `apt_builder.py` (`build_apartment(cfg)`) y `cabin_builder.py` (`build_cabin(cfg)`) con la configuración del Apéndice B.3 y guárdalos en `entrega/blender/`; cada variante es una llamada con su semilla más un **pase manual** de detalle y daño propio.
1. **Escena:** unidades métricas, escala 1, borra objetos por defecto, guarda `entrega/blender/<ID>.blend`; añade el maniquí de 1,80 m (se excluye al exportar).
2. **Blockout con estructura real:** columnas, vigas, losas, muros con espesor, volúmenes de escalera y tejado. Captura 4 ángulos y compara con el concepto aprobado (silueta, proporciones).
3. **Formas secundarias:** vanos con jambas y repisas, loggias, galería/torre, balcones, marquesina, voladizos, buhardillas, chimeneas, aleros con cabios.
4. **Detalle y elementos secundarios** (§4.5, ≥ 30 distintos) colocados con lógica (A/C sobre ménsulas con goteo debajo, cables hacia el medidor, bajantes entre bahías, ropa tendida en loggias).
5. **Revestimiento y tejado como geometría** (§4.3/4.4) con variación aleatoria por pieza (posición ±, rotación ±, escala ±) y **UV con desplazamiento aleatorio por pieza**.
6. **Daño como geometría:** desconches y picaduras (subdivisión local + *Displace* con texturas procedurales limitadas por *vertex group*, luego **aplicar**); cortes con booleanos y bordes biselados; **varillas expuestas** (cilindros de 8 lados, curvadas); grietas como surcos; colapsos parciales (B: esquina NE; tejados con vertientes dañadas mostrando cabios); tablones faltantes/podridos. Sigue la fila "Daño" de §4.
7. **Imperfección controlada:** desplomes de ±0,5–1° en barandales y postes, persianas desalineadas, piezas colgando, losas con flecha leve.
8. **Interior mínimo** transitable: losas/pisos con hueco de escalera, escalera real, muros divisorios con vanos sin hoja, sin mobiliario. Ático cerrado.
9. **Base y entorno inmediato (`_Skirt`):** zócalo manchado, arena acumulada, escombro, hierba y maleza; **enredaderas** como curvas con tarjetas de hojas (opcional: textura RGBA de hojas generada sobre fondo **magenta** y recortada con `key_out(key="magenta")`).
10. **Limpieza de topología** y verificación de §5. Mide con el script de triángulos (Apéndice B). Si no llegas a 100 000, añade detalle real, nunca subdivisión vacía.

### PUNTO DE CONTROL 3 — REVISIÓN EN ARCILLA (informativo, antes de texturizar)
Renders en arcilla (material gris uniforme + AO, Cycles ≥ 128 muestras) a 1920×1080: 4 ángulos exteriores, 1 a nivel de ojo (1,7 m), 1 del tejado y 1 de un detalle. Aplica el **checklist de R12**: si falla alguno, vuelve a E antes de continuar. Informa al usuario y continúa.

### FASE F · Look-dev por capas y horneado (por modelo)
1. **UV únicas:** por cara plana grande usa proyección planar (islas rectas); para el resto *Smart UV Project* (ángulo ~66°, margen 0,004); empaqueta en los atlas de §4.7 respetando densidades; sin solapes. Para el texto del grafiti: **islas sin espejo** (mano correcta; `box_uv` del Apéndice B).
2. **Materiales de look-dev (procedurales + entradas IA):** por familia de superficie construye un material con las capas de §4.6: texturas T/S/W/R/M en proyección de mundo (*Box/Triplanar*, 3 m para concreto, 2 m para madera/ladrillo) con rotación/escala aleatorias para romper la repetición; máscaras K y geometría (nodos *Ambient Occlusion*, *Bevel*, *Geometry › Pointiness*, gradiente en Z, normal hacia arriba/abajo) para cada capa; el **panel de grafiti** como capa de imagen sobre la banda de PB. Semilla propia por modelo.
3. **Hornea con Cycles** (script en Apéndice B): albedo (`DIFFUSE` solo `COLOR`), rugosidad, normal (tangente) y AO por atlas; margen 16 px; 64–128 muestras. Mezcla el AO horneado en un 30–40 % en el albedo y/o en el canal R del ORM. Empaqueta ORM (R = oclusión, G = rugosidad, B = metálico).
4. **Materiales finales glTF-friendly:** Principled BSDF con *Image Texture* → color (sRGB), normal vía *Normal Map* (imagen Non-Color), ORM (Non-Color) → *Separate Color* → R = oclusión (vía el grupo "glTF Material Output" del exportador; añádelo desde el addon si falta), G = rugosidad, B = metálico. **Cero nodos procedurales o mezclas** en lo exportado. Máx. 14 materiales.
5. **QA visual contra los conceptos de la Fase B**: renders con sol a 45° y cielo despejado (y uno nublado) desde nivel de ojo a 50 m, 15 m y 2 m; guarda en `render_qa/<ID>_*.png`. Itera hasta que color, desgaste, grafiti y silueta igualen el concepto y no se vea repetición.

### FASE G · Exportación, validación y entrega (por modelo)
1. Exporta **GLB** con `bpy.ops.export_scene.gltf` (Apéndice B): solo mallas del modelo (sin maniquí), modificadores aplicados e instancias materializadas, +Y arriba, sin cámaras ni luces, **sin compresión Draco/meshopt** (no se sabe si el cargador del juego la soporta), texturas embebidas. Guarda las texturas horneadas sueltas en `texturas/` (el editor permite ponerlas desde el inspector). FBX opcional.
2. **Valida:** `glb_tris()` sobre el archivo exportado (≥ 100 000), tamaño del GLB (objetivo ≤ 100 MB; si lo supera, baja la calidad JPEG de los albedos, no los triángulos), memoria de texturas (§4.7), dimensiones, origen en la base, escala 1 = 1 m, orientación. Reimporta el GLB en una escena limpia y comprueba materiales y UV.
3. Actualiza `ESTADO.md`. **Después de cada modelo, informa al usuario en 3–4 líneas** (triángulos, MB, render) y continúa.

### PUNTO DE CONTROL 4 — tras el piloto `APT_A_5p` (informativo)
Muestra los renders QA, el conteo de triángulos y lo que cambiarías para acelerar la serie. Continúa con este orden: `APT_B_4p`, `APT_C_3p`, `APT_D_4p`, `CAB_1_tablones`, `CAB_2_pilotes`, `CAB_3_ladrillo`, salvo que el usuario indique otro.

## 7. Entrega

```
entrega/
  refs_higgsfield/     <ID>_hero.png, <ID>_elev.png, <ID>_mat.png
  lettering/raw/       piezas sobre verde
  lettering/cutouts/   PNG RGBA recortados
  texturas/            biblioteca T/S/W/R/M/K + atlas horneados por modelo
  texturas/graffiti/   G_<ID>_<cara>.jpg
  blender/             <ID>.blend ×7, apt_builder.py, cabin_builder.py, kit_modular.blend
  export/              <ID>.glb ×7 (+ .fbx opcional)
  render_qa/           <ID>_clay_*.png, <ID>_*.png
  ESTADO.md            progreso y parámetros
  REPORTE.md           reporte final
```
Si Blender y tu sandbox usan rutas distintas, usa una ruta absoluta que ambos vean y dile al usuario cuál es.

**Reporte final (obligatorio):** tabla de los 7 modelos con triángulos medidos del GLB, tamaño del GLB, dimensiones, materiales, memoria de texturas y nº de elementos secundarios; modelos de Higgsfield usados y confirmación de que todos fueron ilimitados (créditos de pago gastados: 0); desviaciones respecto a este brief; problemas conocidos. **Cómo cargarlos:** abrir `localhost:5173/mapa.html` → "Subir modelos o texturas…" → elegir los GLB → clic en el modelo de la lista para colocarlo.

---

# APÉNDICE A · Prompts (en inglés, listos para pegar)

**Cadena de estilo común (`STYLE`):** *photorealistic architectural photography of a real abandoned building, 35mm lens, natural overcast light, extremely detailed physically accurate materials and weathering, matte surfaces, no CGI look, no illustration, no cartoon, no stylization, no text overlays, no watermark.*
**Cláusula de anclaje (`ANCHOR`, va en TODOS los prompts con referencias adjuntas):** *Use the attached images ONLY as a guide for the worn grey concrete color, the weathering and the graffiti style. Do NOT copy their simplistic blocky geometry: the building must be a far richer, realistic, fully detailed architectural design.*

### Fase B · conceptos
**Plantilla H (hero 3/4):** `A {DESC}, seen from a three-quarter view at eye level, standing on sandy ground with dry grass and weeds, soft overcast daylight, no hard cast shadows. ANCHOR STYLE`
**Plantilla E (elevación):** `Flat straight-on front elevation of the same building, perfectly frontal, no perspective, building fills the frame, plain neutral grey background, flat even lighting with no cast shadows, every facade element visible. ANCHOR STYLE` (con el `DESC` entre comas).
**Plantilla M (materiales y elementos):** `Close-up photograph at eye level of the ground floor and one facade bay of the same building, showing in sharp detail the weathered material layers, damage and small secondary elements. ANCHOR STYLE` (con el `DESC`).

| ID | `{DESC}` |
|---|---|
| `APT_A_5p` | abandoned five-story reinforced-concrete social housing block on a tropical island: exposed concrete frame of columns, spandrel beams and slab edges in worn grey concrete with salt weathering, rain streaks, efflorescence and rust bleeding from exposed rebar; recessed infill walls of old plaster with remnants of peeling ochre and cream paint; aluminium sliding windows with broken glass and torn curtains; loggias with bent rusty railings and remnants of hanging laundry; air-conditioning units and bundled cables on brackets; a concrete breeze-block screen wrapping the stair core; ground floor as a commercial pilotis with a recessed entrance lobby and dented rolling steel shutters, entirely covered in layered street graffiti and Chicano lettering (fine black calligraphic script "Mi Vida Loca", red handstyle tags, white bubble-letter throw-ups with black outline, golden-yellow blocks, cobalt-blue pieces); hipped roof of weathered rust-red clay tiles with exposed rafters, partial damage, gutters and downpipes; sand drifts and weeds at the base |
| `APT_B_4p` | abandoned four-story concrete walk-up housing block with an exterior access gallery along the long facade with concrete baluster railings and a separate stair tower; brick infill showing where the plaster has peeled; doors and small windows facing the gallery, rusted security grilles; hipped clay-tile roof; the north-east corner partially collapsed with exposed rebar and rubble on the ground; ground floor covered in layered street graffiti and Chicano lettering |
| `APT_C_3p` | abandoned L-shaped three-story concrete apartment building with two wings meeting at a roof valley, gabled clay-tile roofs with exposed rafters and a ventilation chimney; a concrete entrance canopy on two columns over a double door; balconies in the inner corner; greenish algae stains, vines climbing the walls; ground floor covered in layered street graffiti and Chicano lettering |
| `APT_D_4p` | abandoned four-story prefabricated concrete panel housing block in dark blue-grey concrete, visible panel joints with sealant stains, cantilevered balconies with rusty steel railings and bits of glazing, a rusty steel fire-escape staircase zigzagging up one narrow side, gabled clay-tile roof with three dormers, heavy spalling at cornice and balconies; ground floor covered in layered street graffiti |
| `CAB_1_tablones` | two-story abandoned timber-frame house with vertical dark-brown board-and-batten planks showing gaps and rot, a thin reddish-brown band between the floors, a gabled rust-red corrugated metal roof with exposed wooden rafter tails projecting along the eaves and the gable edge, a side porch with two posts and a lean-to roof, a stove pipe with a rain cap, wooden shutters hanging from hinges, a rain barrel and a stack of firewood |
| `CAB_2_pilotes` | two-story abandoned wooden stilt house (palafito) raised on twelve wooden stilts on concrete footings with bolted X braces, sun-bleached grey overlapping clapboard siding, a wraparound veranda with a baluster railing, an exterior wooden staircase with a handrail, a water cistern underneath, open wooden shutters, a gabled pale corrugated-metal roof with a section torn off by wind |
| `CAB_3_ladrillo` | two-story abandoned cabin with a ground floor of individually laid worn red-brown brick in running bond with stone lintels and sills, and an upper floor of light weathered wooden boards with white window frames, a covered front porch with four posts and a railing, a brick chimney with a cap, a gabled roof of weathered light-grey wooden boards with a stepped overhang and a gutter, one broken shutter hanging |

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
| S05 | (hoja) | **sheet of six different marker handstyle tags** reading KAOS, ZORO, NOVA, REXO, DEMO, LUNA, in a clean 3×2 grid with wide gaps | black and cobalt blue |
| S06 | (hoja) | **sheet of six stencil icons** in a 3×2 grid: skull with roses, crown, heart, star, eye, two theatre masks (smile now cry later) | black and red |
| S07 | (hoja) | **sheet of paint drips and splatter overlays** in a 3×2 grid, long vertical drips and spray splatters | black, red, cobalt blue |

### Fase D · biblioteca (1:1, vista plana, sin sombras, sin objetos, sin texto)
**D1 `T1 concrete`:** `Seamless tileable texture, flat top-down orthographic photo scan of a weathered poured-concrete wall, warm light grey, salt-weathered surface, dark vertical rain streaks, hairline cracks, faint efflorescence, a few formwork tie-holes, absolutely even soft lighting with no shadows, no perspective, no vignette, no objects, no text, edges continue seamlessly, photorealistic PBR albedo.`
**D2 `T2 old_plaster_paint`:** *seamless tileable old cement plaster with sun-faded ochre and cream paint peeling off in flakes to reveal grey plaster and concrete beneath, hairline cracks, dirt streaks, even lighting, flat.*
**D3 `T3 roof_tile`:** *seamless tileable top-down pattern of aged rust-red terracotta curved barrel roof tiles, moss in the grooves, sun-faded, even lighting.*
**D4 `T4 wood_weathered`:** *seamless tileable weathered dark-brown wooden beams and planks, grain, cracks, grey sun-bleached patches, even lighting, flat front-on.*
**D5 `W1 wood_dark_planks`:** *seamless tileable weathered dark-brown vertical wooden boards with narrow dark gaps, deep grain, cracks, grey bleached patches, even lighting, flat front-on.*
**D6 `W2 wood_grey_clapboard`:** *seamless tileable sun-bleached grey horizontal overlapping wooden clapboard siding, flaking paint remnants, cracks, moss at the lower edges, even lighting, flat front-on.*
**D7 `R1 roof_corrugated_rust`:** *seamless tileable top-down corrugated red-brown rusty metal roofing sheets, vertical ribs, screws, rust streaks, faded paint, even lighting.*
**D8 `R2 roof_boards_grey`:** *seamless tileable weathered light-grey wooden roof boards in overlapping stepped rows, cracks, moss, even lighting, flat.*
**D9 `S1 brick_red_worn`:** *seamless tileable worn red-brown fired-clay brick wall in running bond, lighter recessed mortar joints, soot stains, a few spalled bricks, even lighting, flat front-on.*
**D10 `M1 rust_metal`:** *seamless tileable heavily rusted painted steel plate, flaking dark paint over orange rust, pitting, streaks, even lighting, flat.*
**Máscaras (D11–D16), todas: `Seamless tileable grayscale mask texture, pure black and white and greys only, flat top-down, no color, no shadows, edges continue seamlessly:`** **D11 `K1`** *irregular patches of peeling paint, large and small flakes with ragged edges* · **D12 `K2`** *long thin vertical rain streaks of varying length and density* · **D13 `K3`** *irregular blotchy efflorescence salt deposits* · **D14 `K4`** *organic clumpy moss and algae growth patches* · **D15 `K5`** *a network of fine cracks and hairline fractures* · **D16 `K6`** *irregular rust-bleed blotches with drips running downward*.

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


def key_out(src, dst, key="green", lo=40.0, hi=110.0, margin=8):
    """Quita un fondo chroma plano: key="green" (0,255,0) o key="magenta" (255,0,255; para vegetación verde).
    Guarda PNG RGBA recortado al contenido, con despill del color de fondo."""
    if key not in ("green", "magenta"):
        raise ValueError("key debe ser 'green' o 'magenta'")
    a = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    kc = np.array([0, 255, 0] if key == "green" else [255, 0, 255], np.float32)
    alpha = np.clip((np.linalg.norm(a - kc, axis=2) - lo) / (hi - lo), 0, 1)
    rgb = a.copy()
    if key == "green":
        rgb[..., 1] = np.minimum(rgb[..., 1], np.maximum(rgb[..., 0], rgb[..., 2]))  # despill del verde
    else:
        spill = np.maximum(np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1], 0)    # despill del magenta
        rgb[..., 0] -= spill
        rgb[..., 2] -= spill
    edge = (alpha < 0.98)[..., None]                       # el despill solo toca los píxeles de borde
    rgb = np.clip(np.where(edge, rgb, a), 0, 255)
    ys, xs = np.where(alpha > 0.05)
    if len(ys) == 0:
        raise ValueError("key_out: no queda contenido; revisa que el fondo sea plano y del color indicado")
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
key_out("lettering/raw/C01.png", "lettering/cutouts/C01.png")            # fondo verde
key_out("raw/hojas.png", "tex/hojas_rgba.png", key="magenta")            # fondo magenta (vegetación)
compose_panel("tex/T1_seamless.png", pieces, (4176, 1189), 290, [(6.1, 0, 8.3, 3.4)], "tex/G_APT_A_A.jpg")   # px_per_m = 290
print(glb_tris("export/APT_A_5p.glb"))
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
**UV de caja con escala de mundo y sin texto en espejo** (`size` en metros por unidad UV):
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
(Para los paneles de grafiti: misma regla de la mano, normalizando a 0–1 sobre el ancho/alto de la cara. Para tablones/ladrillos sueltos, suma un `offset` aleatorio por pieza.)
**Horneado con Cycles** (un atlas por llamada; para `DIFFUSE` pasa `pass_filter={'COLOR'}`; tipos: `DIFFUSE`, `ROUGHNESS`, `NORMAL`, `AO`):
```python
import bpy
def bake(objs, img_name, bake_type, size, margin=16, samples=96, **kw):
    img = bpy.data.images.new(img_name, size, size, alpha=False)
    if bake_type in ('NORMAL', 'ROUGHNESS'): img.colorspace_settings.name = 'Non-Color'
    for o in objs:
        for m in o.data.materials:
            nt = m.node_tree; n = nt.nodes.new('ShaderNodeTexImage'); n.image = img; nt.nodes.active = n
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = samples
    bpy.ops.object.bake(type=bake_type, margin=margin, use_clear=True, **kw)
    img.filepath_raw = f"//{img_name}.png"; img.file_format = 'PNG'; img.save()
    return img
```
Tras hornear, **reemplaza** los materiales de look-dev por materiales finales con esas imágenes (los nodos de bake se eliminan).
**Exportación GLB** (confirma los nombres de parámetros con `bpy.ops.export_scene.gltf.get_rna_type()` en tu versión):
```python
bpy.ops.export_scene.gltf(filepath=r"<ruta>/<ID>.glb", export_format='GLB', use_selection=True,
    export_apply=True, export_yup=True, export_image_format='AUTO', export_cameras=False, export_lights=False,
    export_draco_mesh_compression_enable=False)
```
Selecciona antes solo los objetos del modelo (mallas con el prefijo del ID, sin el maniquí).

### B.3 Configuración de los constructores (datos de §4; ajusta tras el Punto de control 1)
```python
KIT = {
 "APT_A_5p": dict(kind="apt", grid=3.6, bays=(4, 3), floors=5, pb_h=3.4, fl_h=2.9, frame="visible", pilotis=True, loggia_ratio=0.35,
                  stair_core="breeze_block", roof="hip", pitch=26, seed=11),
 "APT_B_4p": dict(kind="apt", grid=3.6, bays=(4, 2), floors=4, pb_h=3.2, fl_h=2.9, gallery=1.5, stair_tower=True, infill="brick_under_plaster",
                  collapse_corner="NE", roof="hip", pitch=26, seed=23),
 "APT_C_3p": dict(kind="apt", plan="L", wing_a=(12.0, 6.6), wing_b=(6.6, 5.4), floors=3, pb_h=3.2, fl_h=2.9, canopy=(2.4, 1.2),
                  roof="gable_valley", pitch=30, seed=37),
 "APT_D_4p": dict(kind="apt", panel_module=2.7, bays=(5, 3), floors=4, pb_h=3.0, fl_h=2.9, balcony_every=2, fire_escape="narrow_E",
                  dormers=3, roof="gable", pitch=28, seed=41),
 "CAB_1_tablones": dict(kind="cab", w=9.0, d=6.0, floors=2, floor_h=2.8, siding="board_batten", frame_visible=True, side_porch=True,
                        roof="gable", pitch=35, roof_mat="corrugated_rust", rafter_tails=True, stove_pipe=True, seed=5),
 "CAB_2_pilotes":  dict(kind="cab", w=7.0, d=6.0, floors=2, floor_h=2.6, stilts=12, stilt_h=1.2, siding="clapboard", veranda=1.2, ext_stair=True,
                        cistern=True, roof="gable", pitch=28, roof_mat="corrugated_light", torn_section=True, seed=9),
 "CAB_3_ladrillo": dict(kind="cab", w=8.0, d=6.5, floors=2, floor_h=2.8, ground="brick_individual", upper="board_light", porch=(2.4, 6.5),
                        chimney="brick", roof="gable", pitch=30, roof_mat="boards_grey_stepped", seed=14),
}
```

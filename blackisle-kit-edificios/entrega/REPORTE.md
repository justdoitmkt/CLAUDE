# REPORTE · Kit de edificios BLACKISLE (7 modelos GLB)

Rama `claude/gracious-dirac-5f11li` · carpeta `blackisle-kit-edificios/entrega/` · detalle cronológico en `ESTADO.md`.

## 1. Los 7 modelos (números medidos)
| Modelo | Triángulos (GLB) | MiB | Materiales | Texturas en memoria (MB) | Caja X × Y × Z (m, con base) | z mín | Validación |
|---|---|---|---|---|---|---|---|
| APT_A_5p | 850 875 | 61.9 | 14 | 253 | 20.9 × 20.2 × 20.3 | -0.07 | OK |
| APT_B_4p | 761 627 | 55.1 | 14 | 253 | 20.9 × 16.4 × 17.1 | -0.19 | OK |
| APT_C_3p | 610 293 | 44.8 | 14 | 253 | 18.4 × 18.4 × 14.0 | -0.07 | OK |
| APT_D_4p | 762 354 | 54.7 | 14 | 253 | 22.6 × 14.6 × 17.0 | -0.19 | OK |
| CAB_1_tablones | 320 489 | 24.1 | 12 | 120 | 17.6 × 12.4 × 9.1 | -0.12 | OK |
| CAB_2_pilotes | 183 246 | 15.3 | 12 | 120 | 13.4 × 12.4 × 6.6 | -0.15 | OK |
| CAB_3_ladrillo | 260 734 | 22.7 | 13 | 141 | 14.4 × 15.1 × 9.1 | -0.12 | OK |

Medido en el GLB final (2026-11-12) con `export_validate.py` y cargado en three r169 (`render_qa/<ID>_threejs_info.json`):
21–32 mallas y 21–32 llamadas de dibujo por modelo, `COLOR_0` en todas las mallas salvo los atlas, 0 avisos del cargador.
La memoria de texturas es la decodificada en GPU (RGBA + mipmaps), no el tamaño del archivo.

Todos: metros, +Y arriba (glTF), origen en el centro de la planta y a nivel del suelo (z = 0), fachada principal hacia +Z de glTF
(−Y de Blender). La caja incluye la base de arena (3 m alrededor del edificio). Sin cámaras, luces ni Draco.

| Modelo | Qué es (concepto aprobado en PC1) | Rasgos propios (R10) |
|---|---|---|
| APT_A_5p | Bloque de 5 niveles con pórtico de concreto visible, loggias y celosía de escalera | casetón con tinacos, techo a 4 aguas con hueco, fachada oeste muy dañada, ruinas de un anexo demolido |
| APT_B_4p | Bloque de galería de acceso, 4 niveles | balaustrada de concreto, pórtico con marquesina, colapso de la esquina superior SO (columnas truncadas con varilla, losa y techo perdidos) |
| APT_C_3p | Bloque en L de 3 niveles | balcones en L sobre postes en la esquina entrante (marquesina del acceso), dos techos a dos aguas con limahoyas, hastiales, chimenea |
| APT_D_4p | Bloque de paneles prefabricados, 4 niveles | sin pórtico visible: muros de panel con juntas selladas, celosías de escalera en los testeros, 3 buhardillas, balcones colgados, 2 secciones |
| CAB_1_tablones | Cabaña de 2 niveles de tablón y junquillo | porche lateral de un agua, lámina oxidada con colas de cabio, tubo de estufa, barril y leña |
| CAB_2_pilotes | Casa sobre pilotes | 12 pilotes con cruces de San Andrés, veranda con escalera exterior, cisterna, lámina clara con desgarro, tapanco |
| CAB_3_ladrillo | Casa de PB de ladrillo y planta alta de tabla | porche delantero con escalones, chimenea de ladrillo, tablones escalonados, canalón y bajante |

**Regla del usuario para departamentos (2026-10-09), cumplida en los 4:** entrada delantera y trasera en PB, **cero escaleras
exteriores** (núcleos de escalera en U dentro de la envolvente) e **interior completo** (departamentos con cuartos, corredores,
vestíbulos, puertas). Verificado con plantas seccionadas (`render_qa/*_planta_N*.png`).

## 2. Cómo cargarlos en `mapa.html` (Three.js)
```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
new GLTFLoader().load('modelos/APT_A_5p.glb', (g) => {
  const edificio = g.scene;                 // ya en metros; colocar con position / rotation.y
  edificio.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } });
  scene.add(edificio);
});
```
- Funciona con el GLTFLoader estándar (sin extensiones de pago). Usa `KHR_texture_transform` (escala de los materiales repetibles) y
  `COLOR_0` (oclusión por vértice): el loader los aplica solo (`vertexColors` se activa automáticamente).
- `renderer.outputColorSpace = THREE.SRGBColorSpace` (por defecto en r152+). Probado con **three r169** en Chromium (WebGL por
  software): carga, sombras y texturas correctas (`render_qa/*_threejs_*.png`).
- Materiales de doble cara solo donde hace falta (lámina ondulada, tela, hierba).
- Colisiones: los muros, losas y escaleras son mallas cerradas; para física conviene derivar colisionadores simplificados por nivel.
- Visor de revisión incluido: `entrega/visor/index.html` (servir la carpeta `entrega/` con `python -m http.server`).

## 3. Método (resumen)
1. **Conceptos y lettering (Higgsfield, `nano_banana_2_1` a 1k):** 25 vistas vigentes + 15 piezas de lettering (palabras inocuas y
   crews ficticios KAOS, ZORO, NOVA, REXO; ningún número, sigla o símbolo de pandilla real, de odio, persona real o marca — R4).
2. **Biblioteca de materiales:** 16 texturas 1024² repetibles + paneles de grafiti por cara compuestos con los vanos reales de cada
   modelo ("Mi Vida Loca" protagonista solo en APT_A y APT_C).
3. **Modelado en Blender 5.2 (`bpy`), sin booleanos:** kit modular propio (vanos, circulación, cubiertas, revestimientos, servicios,
   daño) con niveles de detalle; constructores por modelo (`apt_builder.py`, `apt_b/c/d.py`, `cabin_builder.py`).
4. **Revisión en arcilla** (PC3) de cada modelo + plantas seccionadas del interior.
5. **Look-dev en capas y horneado:** atlas únicos para muros exteriores (pintura descascarada, suciedad, chorreados, eflorescencia,
   óxido, musgo, desgaste de aristas, grafiti) y para el terreno; detalles/techo/interior con PBR repetible + AO por vértice.
6. **Exportación GLB y validación** (Blender + Three.js real).

## 4. Higgsfield: modelos y créditos
- Modelo usado: **Nano Banana 2.1 a 1k** (1,5 créditos por imagen), autorizado expresamente por el usuario el 2026-10-09 como
  excepción a R1 (la cuota ilimitada de la web no está expuesta al MCP).
- Gasto atribuible a este trabajo: **105,0 créditos** (fases B y C: 81,0 incluido 1,5 de atribución incierta; fase D: 24,0).
  62 + 16 imágenes enviadas; 9 falsos positivos del filtro nsfw, reembolsados.
- Saldo consultado al cierre: **1 008,25 créditos, plan `plus`** (2026-10-28 02:54 UTC). No se compara con el saldo esperado tras la fase D (411,26): entretanto la cuenta cambió de plan y tiene recargas y generaciones propias del usuario en la web (GPT Image 2.5 y Nano Banana 2.1, del 25 al 28 de octubre). Revisé las transcripciones de esta sesión y de sus subagentes: **ninguna llamada de generación después de la fase D**.

## 5. Desviaciones del brief (y por qué)
1. **R1 (cuota ilimitada):** el MCP de Higgsfield no expone la cuota ilimitada de la web (`unlim.available = false` en todos los
   modelos). Se usó **Nano Banana 2.1 a 1k (1,5 créditos)** con autorización expresa del usuario (2026-10-09). Total: 105,0 créditos.
2. **Presupuesto de triángulos:** el brief pedía 200–450 k por departamento (techo 600 k) y 150–300 k por cabaña. La orden del usuario
   de construir **todo el interior** (cuartos, corredores, núcleos de escalera, puertas) no cabe ahí. Decisión R8 registrada (2026-10-10):
   techo de **700 k** por departamento. Medido en el GLB final: APT_C 610 k (dentro); APT_B 762 k y APT_D 762 k (+9 %); **APT_A 851 k
   (+22 %)**, el piloto, con fachada y celosía más densas. El vestido interior de la ronda 3 suma 15–31 k por edificio.
   Cabañas: CAB_2 183 k y CAB_3 261 k dentro de 150–300 k; **CAB_1 320 k (+7 %)** por el armazón a la vista y los tablones sueltos.
   Palancas ya aplicadas: teja en nivel `low`, A/C en `low`, canalón solo frente/fondo, hojas de puerta saqueadas. Para el juego hacen falta
   LOD (ver §6).
3. **Horneado (§4.7):** un atlas único para todo el modelo dejaba decenas de miles de islas de 1–3 px (piezas sueltas). Atlas únicos solo en
   superficies continuas (muros exteriores `walls_main`/`walls_rest` y terreno `skirt`). Detalles, techo, interior, hierba y escombro llevan
   **PBR repetible a escala real** (`KHR_texture_transform`) + **oclusión por vértice** en `COLOR_0`. También se quitaron el atlas `interior`
   previsto y la AO en un 2.º canal UV: `COLOR_0` lo resuelve sin texturas extra.
4. **Aplanado interior:** el repetible T2 (pintura naranja descascarada) se veía saturado y a escala de juguete dentro de los cuartos,
   y su primera variante gris se repetía como papel tapiz. El interior usa `T2_plaster_int_2k.png` (2048², 2,4 m por repetición,
   generada con un sombreador periódico por construcción: T1, K1 y K2 a repeticiones enteras + ruido 4D sobre un toro).
5. **Conceptos de APT_B y APT_D rehechos (v3):** la regla del usuario (cero escaleras exteriores) invalidó la torre de escalera de B y la
   escalera de emergencia de D. Los modelos siguen los heroes v3. La pieza firma de D pasó a ser los balcones colgados, las buhardillas y
   las celosías de escalera.
6. **R4 en el grafiti:** la corona y la estrella de 5 puntas de la hoja de íconos y la corona de `C02_isla_negra` salían de la
   biblioteca generada. Juntas forman simbología de una alianza de pandillas real, así que se borraron y los paneles de los 4 departamentos
   se regeneraron. La revisión de aceptación encontró además dos estrellas de 5 puntas decorativas dentro de la pieza ZORO: borradas
   del recorte (`S02_zoro.png`) y paneles regenerados. Palabras y crews: solo los de la lista (crews ficticios KAOS, ZORO, NOVA, REXO).
7. **Tamaño de archivo:** los GLB de departamento pesan 45–62 MiB (sin Draco, como pide el brief). Están por debajo del límite de 100 MB
   de GitHub, pero por encima del aviso de 50 MB.
8. **Interior vestido, no amueblado:** la orden del usuario era la estructura completa por dentro; el plan decía "sin mobiliario, con
   escombro". La revisión de aceptación pidió escala humana en los cuartos: `interior_dress.py` pone escombro de aplanado, basura,
   focos colgando, apagadores y contactos, y algún colchón o silla rota, solo donde detecta un cuarto cerrado. No hay cocinas ni baños
   amueblados.
9. **Validación en Three.js por software:** el contenedor no tiene GPU. Carga, sombras, texturas y recorridos se probaron con three r169 en
   Chromium + SwiftShader. No hay medición de FPS en GPU real.

## 6. Problemas conocidos
1. **Memoria de texturas:** ~253 MB por departamento y 120–141 MB por cabaña (decodificadas en GPU). Los repetibles son las mismas
   imágenes en los 7 GLB, pero van embebidos en cada archivo y three.js no los comparte: con los 7 cargados, ≈ 1,4 GB.
   Recomendado: convertir a **KTX2/Basis** (p. ej. `gltf-transform etc1s/uastc`, 4–6× menos) y/o cachear las texturas repetibles por nombre
   en `mapa.html`.
2. **Atlas de muros suave de cerca:** 4096² para ~800 m² de fachada dan ≈ 1,4 px/cm. A 2 m, el grafiti y la pintura descascarada se ven
   blandos. La ronda 3 duplicó la resolución de la banda de PB dentro de `walls_main` (islas ×2,0) y subió su normal a 2048, pero sigue
   por debajo de la densidad de pantalla a 2 m. Mejora posible: mapa de detalle repetible encima del atlas o atlas de 8192 para la PB.
   En las cabañas, algunas caras interiores junto a ventanas van al atlas exterior y se ven más borrosas que el repetible de madera.
3. **z-fighting residual** (`blender/tests/zfight.py --dedupe`, caras coplanares del mismo sentido a < 1,2 mm que se ven): **0 m² en los 7** tras
   `coplanar.py`, que antes de hornear borra las caras cubiertas por otra coplanar y hunde 3 mm las parcialmente cubiertas
   (APT_D tenía 16 m² visibles: descansos de escalera sobre la losa y cabezas de muro bajo la azotea). El detector usa el mismo umbral
   que la limpieza: solapes casi coplanares a más de 1,2 mm no los ve; en los recorridos no se observó parpadeo.
4. **Sin LOD ni colisionadores:** 610–851 k triángulos por departamento a distancia de mapa. Para el juego conviene un LOD a ~30 % y otro
   de caja, más colisionadores simplificados por nivel (muros, losas, rampas de escalera). Unas 30 llamadas de dibujo por modelo.
5. **Interiores a oscuras sin iluminación de juego:** solo entra luz por ventanas y puertas. Las capturas de `render_qa/recorrido/` usan
   dos bombillas puntuales por toma. En el mapa hacen falta luces interiores o una sonda de luz/irradiancia.
6. **CAB_2 (tapanco):** piso a 4,60 m con 1,2–1,5 m libres bajo el faldón (no se puede estar de pie) y acceso por escalera de mano.
   El juego necesita una mecánica de trepar y agacharse (o un volumen de escalera).
7. **Daños y escombro interior** son geometría estática; ninguna pieza está separada para destrucción.
8. **Validación visual en SwiftShader** (sin GPU): sombras PCF y antialias pueden verse distintos en GPU real.

## 7. Revisión de aceptación
- **2026-10-28, sobre la versión anterior de los 4 departamentos** (workflow: un revisor por modelo contra R12, R4, color y la regla
  del usuario, y un verificador independiente que intenta refutar cada hallazgo medio o grave). Veredictos: APT_A rechazo,
  APT_B aceptar con correcciones, APT_C rechazo, APT_D aceptar con correcciones. 13 hallazgos confirmados, 5 refutados.
  Todos los confirmados se atacaron en la ronda 3 del pipeline (detalle en `ESTADO.md`) y los 7 modelos se re-hornearon con ella.
- **Comprobado con mis ojos en el GLB final** (recorridos y capturas Three.js de los 7): muros grises en B y C, ático de A cubierto,
  sin cuartos negros, sin hueco negro ni panel de fachada en C, machón de D interior, vidrio oscuro, aplanado sin repetición
  visible, escombro con textura, grafiti de C legible a 15 m, cuartos con escombro, basura y focos.
- **Pendiente:** no se repitió la revisión de aceptación con verificadores sobre la versión final, ni se pasó por primera vez a
  las 3 cabañas (estas sí tuvieron auditoría de circulación y geometría con verificación). Hallazgos menores que quedan a la vista:
  laja de escombro de pie en C_01, colchones lisos y claros, rendijas de luz bajo los tramos de escalera de C, cantos rectos sin
  desconches fuera de las zonas dañadas.

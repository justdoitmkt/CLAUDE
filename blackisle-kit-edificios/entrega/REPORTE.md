# REPORTE · Kit de edificios BLACKISLE (7 modelos GLB)

Rama `claude/gracious-dirac-5f11li` · carpeta `blackisle-kit-edificios/entrega/` · detalle cronológico en `ESTADO.md`.

## 1. Los 7 modelos (números medidos)
<!-- TABLA -->

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
- Saldo consultado al cierre: <!-- SALDO -->.

## 5. Desviaciones del brief (y por qué)
<!-- DESVIACIONES -->

## 6. Problemas conocidos
<!-- PROBLEMAS -->

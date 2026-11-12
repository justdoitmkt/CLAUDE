# BLACKISLE · Kit de edificios para Unreal Engine 5

Este archivo es la instrucción para quien importe el kit en el proyecto de Unreal (persona o asistente).
Léelo completo antes de tocar el proyecto. La especificación exacta de materiales, piezas y medidas está en
`manifiesto.json`; `importar_blackisle.py` la aplica desde el editor.

## 1. Qué hay que lograr
Importar los 9 modelos (7 edificios, el muelle de carga y el hospital) y **reemplazar con ellos los edificios, cabañas,
muelle y hospital provisionales que ya existen en el nivel**.
El resultado tiene que verse como un edificio real y abandonado:
- **Vidrio que se ve como vidrio:** translúcido, con reflejos y suciedad, y con las roturas que trae el modelo.
- **Cada material con su forma y su tono exactos:** concreto gris gastado, aplanado descascarado, madera, ladrillo, teja,
  lámina oxidada, aluminio y tela. Los colores, tintes, rugosidades y escalas vienen fijados en el manifiesto: **no los
  cambies a ojo**. Si algo se ve mal, revisa primero las causas de §7.
- **Sin terreno propio:** los modelos no traen arena ni pasto. Se apoyan en el piso del mapa (z = 0 del modelo = nivel del
  suelo). El escombro exterior es una pieza aparte (`Escombro`) que se puede mover o borrar.

| ID | Qué es | Fachada principal (hacia −Y de Blender) |
|---|---|---|
| APT_A_5p | Departamentos, 5 niveles, pórtico de concreto, logias, casetón con tinacos | pórtico con la entrada de PB y logias con barandal |
| APT_B_4p | Departamentos, 4 niveles, galerías de acceso, esquina SO colapsada | galerías con balaustrada y pórtico con marquesina |
| APT_C_3p | Departamentos en L, 3 niveles, balcones sobre postes, dos techos a dos aguas | hastial del ala sur con cortina metálica y "Mi Vida Loca" |
| APT_D_4p | Bloque de paneles, 4 niveles, balcones colgados, 3 buhardillas | balcones colgados y las dos puertas de PB con marquesina |
| CAB_1_tablones | Cabaña de tablón, 2 niveles, porche lateral | puerta delantera (el porche queda al costado oeste) |
| CAB_2_pilotes | Casa sobre pilotes con veranda y tapanco | veranda con la escalera exterior |
| CAB_3_ladrillo | PB de ladrillo y planta alta de tabla | porche delantero con escalones |
| MUE_1_carga | Muelle de carga sobre pilotes con nave de acero, caseta, contenedores, grúa y frente de atraque | la rampa ancha que sube desde la playa (el atraque mira a +Y, al mar) |
| HOS_1_pueblo | Hospital rural de una planta EN USO: urgencias, consultorios, farmacia, rayos X, encamados, patio y cochera de ambulancias | pórtico de 4 columnas con "COMMUNITY HOSPITAL" en el pretil (cochera al oriente, +X) |

Los edificios tienen **interior completo**: cuartos, puertas, escaleras dentro, escombro, basura y focos colgando. En los
departamentos hay entrada delantera y trasera en PB. El muelle se describe aparte en §3.1 y el hospital en §3.2.

## 2. Contenido
```
kit_ue5/
  LEEME_UE5.md            este archivo
  manifiesto.json         especificación: materiales, piezas, medidas, focos, ejes
  importar_blackisle.py   script de Python para el editor de Unreal
  comun/texturas/         T_BLK_<material>_BC / _N (normal DirectX) / _ORM (R oclusión, G rugosidad, B metal)
                          + T_BLK_vidrio_suciedad
  comun/geometria/        SM_BLK_Ejes.glb (marcador para medir la conversión de ejes)
  modelos/<ID>/           SM_<ID>_Estructura / _Detalle / _Escombro / _Vidrio / _Colision .glb
                          texturas/T_<ID>_walls_main|walls_rest _BC.jpg / _N.png / _ORM.png
                          <ID>.json (ficha: triángulos, ranuras, medidas, focos)
```
Las texturas de muros están horneadas sin la arena, así que la base de los muros queda bien al quitar el terreno.

## 3. Las 5 piezas de cada modelo
Las cinco comparten el pivote: centro de la planta a nivel del suelo (en el muelle, ver §3.1). Colócalas en el mismo
punto y con el mismo giro.

| Pieza | Qué lleva | Nanite | Colisión | Notas |
|---|---|---|---|---|
| Estructura | carcasa (muros con atlas), interior (muros, losas, escaleras, puertas, escombro y basura interior), techo | sí | ninguna | la colisión la da la pieza Colision |
| Detalle | ventanas, barandales, servicios (A/C, medidores, cables, tinacos), ropa, daño | sí | ninguna | los barandales no bloquean (§7) |
| Escombro | escombro exterior suelto (montones, trozos, varillas) | no | compleja como simple | opcional: se puede mover o borrar |
| Vidrio | todo el vidrio (ventanas, puertas, esquirlas) | **no** (translúcido) | ninguna | sin proyectar sombra |
| Colision | carcasa + interior con caras coplanares fundidas (misma forma, pocos triángulos) | no | compleja como simple | **invisible**; da la colisión de muros, pisos y escaleras |

Escaleras: peldaño de 17 × 28 cm, válido con el step height por defecto de 45 cm. Puertas de 0,8–1,4 m de ancho y
2,0–2,3 m de alto. Pisos a 15 cm sobre el suelo (losa de desplante), así que las entradas tienen un escalón de 15 cm.

### 3.1 El muelle de carga (MUE_1_carga)
No trae terreno ni agua: el mapa pone la playa y el mar. Cotas en metros de Blender (z arriba), con el pivote del modelo
en (0, 0, 0) = eje de la rampa en la orilla de la cubierta, a nivel de la arena:

| Elemento | Cota / posición |
|---|---|
| Arena (pie de la rampa) | z = 0 en y = −25 |
| Nivel del mar | z = −0,5 |
| Cubierta y rampa arriba | z = +2,5 (la rampa sube al 10 % de y −25 a y 0) |
| Punta de los pilotes | z = −7 (quedan bajo el agua y el lecho) |
| Cimiento de la rampa | baja hasta z = −0,8 (enterrado en la arena) |

- **Colocación:** pon el pivote sobre la línea de costa, con −Y de Blender hacia tierra. El pie de la rampa debe tocar la
  arena del mapa y el agua del mapa debe quedar 0,5 m por debajo del pivote. Si el mar del mapa está a otra altura,
  sube o baja el muelle completo hasta que el agua quede en z = −0,5 del modelo. Los niveles van en
  `manifiesto.json → modelos.MUE_1_carga.niveles_m`.
- **Planta:** la rampa mide 47,4 m de ancho libre (todo el ancho de la cubierta) y 25 m de largo. La cubierta es una L:
  48 × 40 m hacia el mar y un espigón de 78 × 12 m cuyo frente norte (+Y) es el atraque, con defensas de llanta y de
  madera, bitas y escaleras marinas. El barco atraca contra ese frente. Alrededor de la nave quedan carriles de 9 m o más para
  vehículos.
- **Colisión:** la pieza Colision incluye formas simples para la grúa, los postes y las bitas. Los pilotes, barandales y
  objetos sueltos no tienen colisión (pieza Detalle).
- **Grúa:** es estática. La pluma apunta al atraque.

### 3.2 El hospital (HOS_1_pueblo)
Hospital rural de pueblo, **en funcionamiento** (limpio, pintura cuidada, grafiti solo en la barda y la cochera). Pivote al
centro del edificio principal, a nivel de banqueta (z = 0); piso interior a +0,45, plafón a +3,15, azotea a +3,65.
- **Planta:** edificio de 28 × 20 m con patio interior; al frente sala de espera, recepción y urgencias; pasillo; consultorios,
  farmacia y rayos X alrededor del patio; al fondo encamados, enfermería, dos baños, cocina y lavandería. Cochera de 2
  ambulancias al oriente, unida por un pasillo cubierto con rampa a la puerta de urgencias. Barda perimetral con portón de
  servicio al fondo.
- **Mobiliario:** va en la pieza Detalle (camas, bancadas, silla de ruedas, camillas, mesas de exploración, rayos X, anaqueles,
  baños, cocina, lavandería). Su colisión son **cajas simples** dentro de la pieza Colision; muros, pisos y escalones vienen
  completos.
- **Textos en inglés** en letreros 3D (COMMUNITY HOSPITAL, EMERGENCY, EXAM 1/2, PHARMACY, X-RAY, WARD, NURSES, EXIT…).
- **Luces:** cada luminaria fluorescente es un foco en `modelos.HOS_1_pueblo.focos_m_blender`; `ib.focos(actor)` les pone
  una luz puntual. Para un hospital encendido, súbeles los lúmenes (~2000) y temperatura 4000 K.
- **Ambulancias:** no vienen en el kit (un vehículo no va dentro de la malla del edificio); la cochera tiene lugar para 2.

## 4. Pasos
1. **Copia la carpeta `kit_ue5` completa a disco**, fuera de `Content/` (por ejemplo junto al `.uproject`).
2. Plugins activos: **Python Editor Script Plugin** e importador glTF (Interchange, activo por defecto en UE 5.1+).
   Versión mínima UE 5.1 (Nanite con materiales de doble cara).
3. En el editor: *Output Log* → selector **Python** →
   ```python
   import sys; sys.path.append(r"RUTA/A/kit_ue5")
   import importar_blackisle as ib
   ib.importar_todo()        # texturas, 4 materiales maestros, instancias y mallas de los 9 modelos, en /Game/BlackIsle
   ib.verificar()            # medidas en cm contra el manifiesto, ranuras con material del kit, ejes
   ```
4. **Reemplaza los provisionales.** Identifica en el nivel qué actor provisional corresponde a cada modelo; si no es
   obvio, pregúntaselo al usuario. Después, por cada uno:
   ```python
   ib.reemplazar("EtiquetaDelProvisional", "APT_A_5p")             # misma posición y giro; oculta el provisional
   ib.reemplazar("EtiquetaDelProvisional", "APT_A_5p", yaw_extra=90) # si la fachada principal quedó mirando mal
   ```
   `ib.frente()` da la dirección local hacia la que mira la fachada principal. Gira con `yaw_extra` hasta que dé a la
   calle. No escales los modelos: ya están a escala real (metros → centímetros). Si un provisional era más chico o más
   grande, el que manda es el modelo del kit. Apoya la base en el terreno; si el terreno tiene pendiente, entierra un poco el
   edificio (el piso propio está a +15 cm) en vez de dejarlo flotando.
   Para colocar sin provisional: `ib.colocar("CAB_2_pilotes", unreal.Vector(x, y, z), yaw=0)`.
5. **Iluminación (para que se vea real):** Lumen para iluminación global y reflejos. Activa *High Quality Translucency
   Reflections* en Project Settings → Rendering si está disponible, para el vidrio. Usa Virtual Shadow Maps y un cielo
   con luz direccional. Los interiores solo reciben luz por ventanas y puertas. `ib.focos(raiz)` pone luces puntuales de
   bombilla (800 lm, 2700 K) en los focos colgantes que trae cada departamento. Es opcional: desactívalas si en la historia
   del juego no hay electricidad.
6. Revisa con cámara de juego (a 1,65 m) por dentro y por fuera, y compara con las capturas de referencia del repositorio
   (`entrega/render_qa/ue5/<ID>_ue5_exterior.png` e `_interior.png`). Antes de dar el trabajo por terminado, comprueba §6.

## 5. Materiales (por si el script falla en tu versión del motor)
El manifiesto lista cada instancia con su maestro y sus parámetros. Las ranuras de las mallas se llaman igual que los
materiales del manifiesto (`BLK_concrete`, `BLK_glass`, `APT_A_5p_walls_main`…). El importador puede añadir prefijos o
sufijos al nombre de la ranura: el script busca el nombre del manifiesto contenido en el de la ranura.
- **M_BLK_Atlas** (muros exteriores): BaseColor = BC; Normal = N; AO = lerp(1, ORM.R, AOFuerza); Roughness = ORM.G;
  Metallic = ORM.B. UV0 directo.
- **M_BLK_Repetible** (concreto, aplanado, maderas, ladrillo, teja, metales, lámina):
  - UV = UV0 × UVEscala. El UV0 del kit es una caja de 2 m por unidad, y UVEscala = 2 / tamaño de la textura en m.
  - BaseColor = BC × Tinte × lerp(1, VertexColor.RGB, PesoVC) × lerp(1, luma(BC a UV × MacroEscala) / LumaMedia, MacroFuerza).
  - Normal = lerp((0,0,1), N, NormalFuerza); AO = lerp(1, ORM.R, AOFuerza); Roughness = ORM.G; Metallic = ORM.B.
  - Doble cara solo donde `dos_caras` = true (teja, lámina, tela, hierba de canalones).
- **M_BLK_Color** (aluminio, plástico, cable, tela, papel, mortero, arena de los montones, hierba): BaseColor = Color ×
  lerp(1, VertexColor.RGB, PesoVC); Roughness y Metallic constantes. En la tela, el color por vértice trae el color
  desteñido de cada pieza (PesoVC = 1).
- **M_BLK_Vidrio**:
  - Blend Mode **Translucent**, Lighting Mode **Surface ForwardShading**, una cara (cada esquirla es un prisma cerrado de 4 mm).
  - BaseColor oscuro casi neutro; Specular 0,5.
  - Opacity = lerp(OpacidadLimpia 0,16, OpacidadSucia 0,55, suciedad).
  - Roughness = lerp(0,03, 0,38, suciedad), con suciedad = T_BLK_vidrio_suciedad (R) a UV0 × EscalaSuciedad.
  - La malla Vidrio sin Nanite y sin sombra.
- Texturas: `_BC` sRGB; `_N` Normalmap **sin** invertir el verde (ya vienen en DirectX); `_ORM` y `vidrio_suciedad`
  Masks/lineal (sRGB desactivado).
- El color por vértice (COLOR_0 del glTF) es imprescindible: es la oclusión de cada pieza y el color de la tela. Si al
  importar se pierde (*Vertex Color Import Option* distinto de *Replace*), todo se ve plano.

## 6. Comprobaciones antes de entregar
- [ ] `ib.verificar()` da OK en los 9. Medidas en m (x × y × z de Blender, sin escombro): ver
      `manifiesto.json → modelos.<ID>.medidas_m`; la de la malla Estructura sola está en `medidas_estructura_m`.
- [ ] Muelle: el pie de la rampa toca la arena, el agua queda 3 m bajo la cubierta (cubierta +2,5, mar −0,5) y los
      pilotes entran en el agua sin verse flotando.
- [ ] Ninguna ranura con material gris por defecto ni con los materiales que crea el importador glTF.
- [ ] Vidrio translúcido y con reflejo, no gris opaco.
- [ ] Muros de concreto gris (no naranja ni rosados) y madera con veta y relieve.
- [ ] Color por vértice presente: en el editor de la malla, modo *Vertex Color* muestra oscuridad en rincones.
- [ ] El jugador entra por las puertas de PB, sube las escaleras interiores y no atraviesa muros ni pisos (pieza Colision).
- [ ] No hay arena ni pasto del kit; el escombro exterior queda apoyado en el terreno (muévelo o bórralo si estorba).

## 7. Problemas conocidos y qué hacer
- **Barandales, ventanas y servicios no tienen colisión** (pieza Detalle). Si el jugador debe chocar con los barandales,
  activa *Use Complex As Simple* en la malla Detalle y desactívale Nanite, o pon colisiones simples a mano en balcones
  y galerías.
- **Nanite y colisión compleja:** la colisión no va en piezas con Nanite (usaría la malla de respaldo simplificada). Por
  eso existe la pieza Colision sin Nanite.
- **Atlas de muros a 2 m:** a menos de 1 m del muro el grafiti y la pintura se ven algo suaves (4096² por edificio).
- **Cabañas:** algunas caras interiores junto a ventanas usan el atlas exterior y se ven más borrosas que la madera repetible.
- **CAB_2:** el tapanco tiene 1,2–1,5 m libres y se sube por escalera de mano. Hace falta agacharse o un volumen de escalera.
- **Triángulos:** departamentos de 610–850 k y cabañas de 180–320 k. Con Nanite no hay problema; sin Nanite, cuidado.
- **Si el importador combinara las piezas:** cada pieza viene en su propio GLB para que eso no pase. Importa archivo por
  archivo.
- **Si los ejes quedan raros** (edificio acostado o espejado): `ib.ejes()` mide la conversión con SM_BLK_Ejes y la
  reporta; la caja debe medir 100 × 50 × 25 cm en algún orden. Si sale espejado, el importador glTF de esa versión
  convierte distinto: reimporta con la opción de conversión de ejes por defecto.

## 8. Origen
Hecho en Blender 5.2 a partir de los constructores del repositorio (`entrega/blender/`): `bake_apt.py --ue`
(sin terreno, atlas sin arena, materiales por tipo) y `export_ue5.py`. La parte común la genera `tools/kit_ue5_comun.py`.
Detalle del proyecto, decisiones y problemas en `entrega/REPORTE.md` y `entrega/ESTADO.md`.

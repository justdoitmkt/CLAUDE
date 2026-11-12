# Reglas del proyecto BLACKISLE (kit de edificios)

## R-AAA · Calidad AAA obligatoria (orden del usuario, 2026-11-12)
Cita: "Tiene estrictamente prohibido pasar por alto detalles que se vean rápidos o hechos de forma rápida. No quiero un
escenario low poly. Quiero un escenario AAA. Con un chingo de triángulos, no menos de 100,000 triángulos. Invierte más en los
detalles. Si se ven como cajas de cartón, no sirven."

Regla de trabajo, sin excepciones:
1. **Prohibido entregar piezas "rápidas".** Nada de cajas, cilindros o placas sueltas que representen un objeto complejo. Una
   cama, una silla, un colchón, una almohada, una grúa, un poste o un mostrador se modelan con su construcción real: perfiles,
   uniones, soldaduras, tornillos, bisagras, costuras, holguras y grosores reales.
2. **Lo blando se ve blando.** Colchones, almohadas, cojines, sábanas, cobijas, cortinas y tapizados llevan malla subdividida
   (Catmull-Clark), bordes redondeados, abombado, arrugas, costuras/ribetes y caída por gravedad. Una almohada que parece
   piedra o una cama que parece de Roblox se rechaza.
3. **Lo rígido lleva bisel y escala real.** Aristas biseladas o redondeadas donde el objeto real las tiene, tubos con curvas de
   radio real (no esquinas a 90° de dos cilindros), uniones y remates.
4. **Presupuesto mínimo:** cada modelo entregado ≥ 100 000 triángulos (normalmente varios cientos de miles: se usan con Nanite).
   Una pieza de mobiliario protagonista (cama, silla de ruedas, mostrador, equipo médico) no baja de unos miles de triángulos.
5. **Revisión de primer plano obligatoria antes de integrar:** cada pieza nueva se renderiza en arcilla a menos de 2 m y se
   compara con una referencia real. Si a esa distancia se lee como "caja de cartón" o "low poly", se rehace antes de seguir.
6. **Al reportar,** decir con honestidad qué piezas siguen por debajo de este estándar; nunca presentarlas como terminadas.
7. **Segunda pasada obligatoria (orden del usuario, 2026-11-12):** "Cuando termines de armar, das una segunda pasada cuidando
   detalles... No se tienen que ver facetadas las piezas. Nútrete de la web para que puedas aprender a cómo modelar
   correctamente con proporción los modelos." Al terminar de armar un modelo se hace una pasada SOLO de detalle: nada redondo
   facetado a < 2 m (cilindros visibles ≥ 24 lados, tubos y cables ≥ 12, con sombreado suave; los bordes duros solo donde el
   objeto real los tiene) y las medidas y proporciones de cada componente se verifican contra fuentes reales consultadas en la
   web (fichas técnicas, normas, catálogos), anotadas en ESTADO.md.

## R-GRAF · Estilo y cantidad de grafiti (orden del usuario, 2026-11-12)
Cita: "Aquí ya no metas ilustraciones propias, únicamente grafitis, placas, firmas, artes, dibujos, ilustraciones callejeras,
street. Que se ve así muy cholo, chicano. Esa es la regla de los grafitis para cada lugar. Cuando yo te pida que no los
incluyas, no los vas a incluir."
1. **Solo grafiti callejero** con estética chola/chicana: placas, firmas, tags, throw-ups, piezas, arte y dibujos callejeros
   (letra gótica "Old English", script chicano, sombreado fino, contornos y brillos de aerosol). **Prohibidas las ilustraciones
   propias** tipo cartel o mural institucional (como el mural "get well" o el corazón de enfermeras del hospital, que se queda
   como está porque al usuario le gustó ahí).
2. **R4 sigue mandando:** crews y nombres ficticios; nada de números, siglas ni símbolos de pandillas reales, ni símbolos de odio.
3. **Cantidad según cada lugar:** si el usuario pide un lugar sin grafiti, no se pone; si pide poco, es poco (granero GRA_1:
   solo un par de rayaduras en un costado).

## Otras reglas vigentes (resumen; detalle en blackisle-kit-edificios/entrega/ESTADO.md)
- R4: contenido seguro. Lettering con palabras inocuas; prohibidos nombres, números, siglas o símbolos de pandillas reales,
  símbolos de odio, personas reales y marcas comerciales. Crews ficticios.
- Cada modelo nuevo trae su propia biblioteca de grafiti (crews, estilos y piezas exclusivas); no se reutilizan firmas de otros
  edificios.
- Textos de modelos nuevos (letreros, señalética): en inglés.
- Sin terreno propio en el kit UE5 (ni arena ni pasto); el escombro exterior va como pieza suelta.
- R12: rechazo automático por fachada plana, repetición a 15 m, aristas perfectas, < 30 elementos secundarios, sin escala humana,
  materiales planos, aspecto de maqueta, artefactos o z-fighting.

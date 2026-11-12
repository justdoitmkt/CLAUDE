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

## Otras reglas vigentes (resumen; detalle en blackisle-kit-edificios/entrega/ESTADO.md)
- R4: contenido seguro. Lettering con palabras inocuas; prohibidos nombres, números, siglas o símbolos de pandillas reales,
  símbolos de odio, personas reales y marcas comerciales. Crews ficticios.
- Cada modelo nuevo trae su propia biblioteca de grafiti (crews, estilos y piezas exclusivas); no se reutilizan firmas de otros
  edificios.
- Textos de modelos nuevos (letreros, señalética): en inglés.
- Sin terreno propio en el kit UE5 (ni arena ni pasto); el escombro exterior va como pieza suelta.
- R12: rechazo automático por fachada plana, repetición a 15 m, aristas perfectas, < 30 elementos secundarios, sin escala humana,
  materiales planos, aspecto de maqueta, artefactos o z-fighting.

# Diagnóstico de los tres archivos de reservas

Qué traen, qué tenían de malo, qué decisión tomé en cada caso y qué necesito que confirmes. Las cifras las produce `python -m guest_crm.build` (el reporte completo queda en `out/reporte_calidad.md`).

## Resumen

| Concepto | Valor |
|---|---:|
| Filas leídas | **552** (161 + 293 + 98) |
| Reservas distintas (sin duplicados entre hojas y archivos) | **530** |
| **Contactos con teléfono, listos para HubSpot** | **378** |
| · con teléfono válido | 331 |
| · con teléfono sin código de país (se asumió México) | 47 |
| Filas sin teléfono («No disponible») | 75 (13.6 %) |
| Huéspedes recurrentes (2 o más reservas) | 60 |
| Huéspedes con reserva en 2026 | 94 |
| Nombre de pila identificado con confianza Alta / Media / Baja | 332 / 32 / 14 |
| Teléfonos compartidos por nombres distintos | 9 |

## Qué contiene cada archivo

| Archivo | Filas | Contenido | Significado de la fecha |
|---|---:|---|---|
| `Reservas_2023_2024.xlsx` | 161 | Una hoja: nombre, teléfono, día, mes, año. 153 de 2023 y 8 de 2024 | Fecha de la estancia |
| `Reservas_2024_Actualizado.xlsx` | 293 | 12 hojas mensuales + una hoja «Consolidado 2024» | Estancia (día/mes/año). **La hoja indica el mes en que se reportó la reserva** |
| `2026_RESERVAS.pdf` | 98 | Tabla nombre, teléfono, mes (enero–septiembre de 2026) | Solo el mes; **sin día de estancia** |

## Hallazgos y decisiones

### 1. La hoja «Consolidado 2024» está corrupta y no se usa
Las 14 filas de octubre quedaron **corridas una columna**: «Octubre» cayó en *Día*, «2024» en *Mes*, y el *Mes del Reporte* quedó vacío. La hoja de octubre original no tiene columna *Día*, y al consolidar se desalineó. **Decisión:** se leen las 12 hojas mensuales (la fuente correcta) y el Consolidado solo se audita. Importar el Consolidado directamente habría metido fechas basura.

### 2. Las tres fuentes usan fechas con significado distinto
Se conserva la precisión de cada una en lugar de fingir exactitud: `día` (fecha exacta), `mes` (solo mes, p. ej. las 14 de octubre), `mes de reporte` (el PDF de 2026) y `sin fecha` (3 reservas: «No disponible» ×2 y «Fecha abierta» ×1). Cuando solo se conoce el mes, `Primera/Última reserva` guarda el día 1 y el `Resumen de reservas` lo indica con «(mes)» o «(mes de reporte)».

### 3. Teléfonos: 26 formatos distintos y 75 filas vacías
Había (con números ilustrativos) `+52 55 1234 5678`, `52 3312345678`, `33: 1234 5678`, `3345 12:28 42` (Excel convirtió espacios en horas), `722.123 4567`, `(+)51 987 654 321`, `1 (212) 555 0123`, un guion no separable y saltos de línea dentro del PDF. **Decisión:** todo se normaliza a **E.164** (`+525512345678`) y se valida con libphonenumber. Resultado: **0 números irrecuperables**. 55 filas venían sin código de país (47 contactos): se asumió +52 y quedan marcados *Asumido MX*. 75 filas dicen «No disponible»: no se importan, pero se listan para que alguien recupere el teléfono (13 traen una sugerencia automática por nombre o por misma fecha y apellido).

### 4. Duplicados
Una misma reserva aparece en varias hojas mensuales (se reporta de nuevo) y entre archivos. **Decisión:** una reserva = mismo teléfono + misma estancia; 552 filas → **530 reservas** (22 repetidas). Si dos filas de la misma hoja tienen la misma fecha («Segunda reserva»), cuentan como **dos unidades ese día** (`×2`), no como dos estancias.

### 5. Identidad: el teléfono manda
- **9 teléfonos compartidos por nombres que no se parecen** (parejas, familias, un tercero que reserva). Quedan en **una** ficha con todos los nombres y confianza de nombre *Baja* para que el bot no salude a la persona equivocada.
- **4 nombres con teléfonos distintos.** En uno, los teléfonos difieren en **un solo dígito**: error de captura casi seguro. Está en la hoja «Mismo nombre, otro teléfono» para que lo resuelvas.

### 6. Nombres en varios órdenes
«Nombre Apellido», «APELLIDO APELLIDO NOMBRE», «Apellidos, Nombre», todo en mayúsculas o minúsculas, con títulos («Dra») y anotaciones («(Segunda reserva)», «– Boda …»). Saludar con el primer token daría «Hola Buenavista». **Decisión:** se detecta el orden con un diccionario de nombres de pila; `Nombre para saludo` se llena solo con confianza Alta o Media. Si no hay certeza queda vacío y el bot usa un saludo genérico. Hay 14 casos *Baja* para revisar a mano.

### 7. Hay bloques de eventos y reservas corporativas
Filas como «Familia X – Boda …» (14 reservas) y «… – Empresa». Vienen sin teléfono, así que no entran a HubSpot; sí cuentan en las estadísticas. Conviene tratarlas con otro proceso (un solo contacto por evento).

### 8. Errores sueltos
Una celda de nombre en el PDF decía «Marzo»; su teléfono coincidía con un huésped real de 2024, así que la ficha toma el nombre correcto y deja la nota. Cinco estancias caen en 2025.

## Lo que dicen los datos del negocio

Son **mínimos observables**: 75 filas sin teléfono no se pueden cruzar y una persona puede tener dos números.

| Indicador | Resultado |
|---|---|
| De los 113 huéspedes de 2023, volvieron en 2024–2026 | **20 (18 %)** |
| De los 195 huéspedes de 2024, volvieron en 2026 | **7 (4 %)** |
| De los 94 huéspedes de 2026, ya habían estado antes | **11 (12 %)** |
| Contactos sin reserva en 2026 (base recuperable) | **284**, de los cuales 274 tienen nombre confiable para saludar |
| Estacionalidad 2024 (248 estancias con fecha, sin bloques de evento) | **89 en julio–agosto (36 %)**; noviembre 31; otros meses ≈ 14 |

**Lectura:** el negocio vive de huéspedes nuevos y casi no recompra. Eso es justo lo que un bot con consentimiento puede mover, y las fechas de las temporadas altas dicen cuándo hacerlo. También es la razón para no gastar la reputación del número de WhatsApp en envíos a ciegas.

## Supuestos que necesito que confirmes

1. **¿El mes del PDF de 2026 es el mes en que se reportó la reserva (como en 2024) o el mes de la estancia?** Lo traté como *mes de reporte*, porque el archivo termina en septiembre y no hay meses futuros. Si es el mes de la estancia, solo cambia la etiqueta de esas reservas.
2. **Número de 10 dígitos sin código = México.** Afecta a 47 contactos; quedan marcados *Asumido MX* y el bot los trata como válidos.
3. **Un teléfono = una ficha**, aunque lo compartan varias personas.
4. **«Segunda reserva» = dos unidades el mismo día**, no una segunda estancia.

## Qué revisar a mano

`out/revision_manual.xlsx` (contiene datos personales; no lo subas a ningún repositorio):

| Hoja | Para qué |
|---|---|
| Sin teléfono (75) | Recuperar teléfonos; trae sugerencias donde las hay |
| Teléfono asumido MX (47) | Confirmar que son mexicanos |
| Nombres a revisar (14) | Teléfonos compartidos y nombres sin nombre de pila identificable |
| Mismo nombre, otro teléfono (4) | Resolver errores de captura |
| Reservas sin fecha (3) | Completar fechas |

## Regenerar

```bash
python -m guest_crm.build \
  --xlsx-2023-2024 Reservas_2023_2024.xlsx \
  --xlsx-2024 Reservas_2024_Actualizado.xlsx \
  --pdf-2026 2026_RESERVAS.pdf \
  --out out/
```

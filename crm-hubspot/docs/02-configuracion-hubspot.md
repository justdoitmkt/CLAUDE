# Configuración del CRM en HubSpot

**Objetivo:** que HubSpot sea la base de datos de huéspedes (una ficha por teléfono) y que el bot de WhatsApp de tu VPS lea y escriba ahí. Esta guía te lleva de cero a **378 contactos importados, segmentados y listos para el bot**, en unos 45 minutos.

> **Lo que no pude hacer por ti:** desde el entorno donde trabajo, HubSpot está bloqueado (`api.hubapi.com` y `mcp.hubspot.com` devuelven 403 del proxy), así que no subí nada a tu cuenta. Todo quedó preparado para que la importación sea un solo archivo (`contactos_hubspot.csv`) y la creación de propiedades un solo comando. Si prefieres que lo haga yo directamente, ver [«Hacerlo con Claude»](#hacerlo-con-claude).

## Plan de 45 minutos

| # | Paso | Tiempo | Sección |
|---|---|---|---|
| 1 | Verificar plan y ajustes de la cuenta | 5 min | [1](#1-antes-de-empezar) |
| 2 | Crear las 19 propiedades (script o a mano) | 5–25 min | [3](#3-crear-las-propiedades) |
| 3 | Importar `contactos_hubspot.csv` | 10 min | [4](#4-importar-los-contactos) |
| 4 | Verificar la importación | 5 min | [4.3](#43-verificar) |
| 5 | Crear las 7 listas | 15 min | [5](#5-listas-segmentos) |
| 6 | Crear la credencial del bot | 5 min | [6](#6-credencial-para-el-bot) |

---

## 1. Antes de empezar

1. Necesitas ser **Super Admin** de la cuenta de HubSpot.
2. **Configuración → General:** zona horaria `America/Mexico_City`. El bot guarda las marcas de tiempo en UTC; la zona solo cambia cómo las ves.
3. **Plan.** Esta guía usa solo funciones del CRM (propiedades personalizadas, importación, listas, API). Lo que sí depende de tu plan: cuántas listas activas y cuántos *pipelines* de negocios puedes tener, y las propiedades de **valor único** (hasta donde sé están en todos los planes del CRM; si no ves la casilla «Requerir valores únicos» al crear `telefono_e164`, avísame y adapto el cliente a búsqueda por filtro, son dos funciones).
4. **No conectes el número de WhatsApp a la integración nativa de HubSpot.** Tu bot ya recibe los mensajes por su propio webhook; conectar el mismo número a dos plataformas puede cambiar cómo se enrutan los mensajes. Verifica cómo lo trata tu proveedor antes de hacerlo.

## 2. Modelo de datos

| Objeto de HubSpot | Qué representa aquí | Clave |
|---|---|---|
| **Contacto** | Un huésped = **un teléfono de WhatsApp** | `telefono_e164` (única) |
| **Negocio** (*Deal*) | Una reserva nueva o en curso (fase 2, sección 7) | asociado al contacto |
| **Empresa** | No se usa por ahora (sirve para agencias o eventos corporativos) | — |

**Por qué un contacto por teléfono y no por nombre:** el teléfono es lo que WhatsApp usa para identificar a la persona, y los nombres vienen escritos de varias maneras (Nombre Apellido, Apellidos Nombre, mayúsculas, con anotaciones). Si dos nombres comparten teléfono (9 casos) quedan en **una** ficha con ambos nombres en `Nombre(s) en las reservas`, y su confianza de nombre baja a «Baja» para que el bot no salude a la persona equivocada.

**El historial de reservas** vive resumido en el contacto (`Total de reservas`, `Primera/Última reserva`, `Años con reservas`, `Resumen de reservas`). El detalle reserva por reserva está en `reservas_historial.csv`; no se importa como negocios (ver 7.3).

## 3. Crear las propiedades

Se crean 19 propiedades dentro del grupo **«Huéspedes y WhatsApp»**.

### Opción A (recomendada): con el script

1. Crea una credencial **temporal** con el único alcance `crm.schemas.contacts.write` (ver sección 6 para dónde se crea).
2. En tu computadora o en el VPS, dentro de la carpeta `crm-hubspot`:

```bash
pip install -r requirements.txt
export HUBSPOT_TOKEN='pega-aquí-el-token-temporal'
python -m guest_crm.hubspot_setup           # simulacro: lista lo que crearía, no toca HubSpot
python -m guest_crm.hubspot_setup --apply   # crea lo que falte; repetirlo es seguro
```

3. Comprueba en **Configuración → Propiedades → Contactos** que existe el grupo con 19 propiedades.
4. **Borra la credencial temporal.**

### Opción B: a mano

**Configuración → Propiedades → Contactos → Crear propiedad.** Crea primero el grupo «Huéspedes y WhatsApp» y luego estas propiedades (los nombres internos deben ser **exactamente** estos):

| Etiqueta (como se ve en HubSpot) | Nombre interno | Tipo | Opciones / notas |
|---|---|---|---|
| Teléfono E.164 (clave única) | `telefono_e164` | Texto de una línea | **Requerir valores únicos** (se marca al crear; no se puede cambiar después) |
| Nombre para saludo | `nombre_saludo` | Texto de una línea |  |
| Confianza del nombre | `nombre_confianza` | Lista desplegable | Alta · Media · Baja · Sin nombre |
| Nombre(s) en las reservas | `nombre_reserva_original` | Texto de varias líneas |  |
| Calidad del teléfono | `calidad_telefono` | Lista desplegable | Válido · Asumido MX · Revisar |
| WhatsApp: consentimiento | `whatsapp_opt_in` | Lista desplegable | Pendiente · Sí · No |
| WhatsApp: fecha del consentimiento | `whatsapp_opt_in_fecha` | Fecha |  |
| WhatsApp: origen del consentimiento | `whatsapp_opt_in_fuente` | Texto de una línea |  |
| WhatsApp: último mensaje del cliente | `wa_ultimo_mensaje_cliente` | Fecha y hora |  |
| WhatsApp: último envío | `wa_ultimo_envio` | Fecha y hora |  |
| WhatsApp: estado del último envío | `wa_estado_envio` | Lista desplegable | Enviado · Entregado · Leído · Fallido · Sin WhatsApp · Bloqueado |
| WhatsApp: última plantilla enviada | `wa_plantilla_ultima` | Texto de una línea |  |
| Primera reserva | `primera_reserva` | Fecha |  |
| Última reserva | `ultima_reserva` | Fecha |  |
| Total de reservas | `total_reservas` | Número |  |
| Años con reservas | `anios_visita` | Casillas múltiples | 2023 … 2035 (una casilla por año) |
| Fuentes de datos | `fuentes_datos` | Casillas múltiples | Reservas 2023-2024 · Reservas 2024 · Reservas 2026 · Bot WhatsApp · Captura manual |
| Resumen de reservas | `resumen_reservas` | Texto de varias líneas |  |
| Notas de importación | `notas_importacion` | Texto de varias líneas |  |

> **Regla importante para las listas desplegables:** en cada opción, el **valor interno debe ser igual a la etiqueta** (`Sí` y `Sí`, no `si` y `Sí`). El importador acepta así el CSV sin importar contra cuál compare, y el bot filtra con el mismo texto que ves en pantalla.

## 4. Importar los contactos

### 4.1 Antes de subir el archivo

- **No abras `contactos_hubspot.csv` en Excel ni lo guardes desde Excel.** Excel convierte `+525512345678` en el número `525512345678` (pierde el `+`) y rompe fechas y acentos. Impórtalo tal cual lo generó el script. Si necesitas verlo, ábrelo con un editor de texto o con «Importar datos desde texto» en Excel marcando la columna como Texto.
- El archivo ya viene en UTF-8, con un renglón por teléfono único, sin duplicados.

### 4.2 Pasos

1. **Contactos → Importar** (*Contacts → Import*) → **Comenzar una importación** (*Start an import*).
2. **Archivo desde el ordenador** (*File from computer*) → **Un archivo** (*One file*) → **Un objeto** (*One object*) → **Contactos**.
3. Sube `contactos_hubspot.csv`.
4. **Mapeo de columnas.** Los encabezados del CSV son los nombres internos, así que HubSpot debería mapearlos solo. Verifica **todas** (si alguna sale «sin mapear», mapéala a mano):

| Columna del CSV | Propiedad en HubSpot |
|---|---|
| `telefono_e164` | Teléfono E.164 (clave única) |
| `firstname` | Nombre (*First name*) |
| `lastname` | Apellidos (*Last name*) |
| `phone` | Número de teléfono (*Phone number*) |
| `lifecyclestage` | Etapa del ciclo de vida (*Lifecycle stage*) — todos entran como *Cliente* |
| `nombre_saludo`, `nombre_confianza`, `nombre_reserva_original`, `calidad_telefono`, `whatsapp_opt_in`, `primera_reserva`, `ultima_reserva`, `total_reservas`, `anios_visita`, `fuentes_datos`, `resumen_reservas`, `notas_importacion` | La propiedad con la etiqueta equivalente de la sección 3 |

5. **Fechas:** si el asistente pregunta el formato, elige el de **año-mes-día** (`2026-04-01`). Las fechas del archivo son ISO.
6. **Nombre de la importación:** `Huéspedes 2023-2026 · v1`.
7. Si HubSpot muestra confirmaciones legales, léelas y acéptalas solo si aplican. Ojo: el permiso que pregunta suele ser para correo; el consentimiento de **WhatsApp** lo controlas tú con `WhatsApp: consentimiento` (todos entran como *Pendiente*, ver sección 8).
8. **Finalizar la importación.** Cuando termine, si hay un archivo de errores, descárgalo y mándamelo.

> **Protección contra duplicados:** como `telefono_e164` exige valores únicos, HubSpot no permite dos fichas con el mismo teléfono: una segunda importación como «crear» no debería duplicar contactos (las filas repetidas se marcan como error o se tratan como actualización, según la opción que elijas). Aun así, no repitas la importación completa; para actualizar datos usa el bot/API (que busca por esa propiedad) o una importación de tipo «crear y actualizar» eligiendo `Teléfono E.164` como identificador.

### 4.3 Verificar

| Comprobación | Resultado esperado |
|---|---|
| Total de contactos importados | **378** |
| Filtro: `Calidad del teléfono` = Válido / Asumido MX | **331** / **47** |
| Filtro: `Fuentes de datos` contiene «Reservas 2026» | **94** |
| Filtro: `Total de reservas` ≥ 2 | **60** |
| Filtro: `WhatsApp: consentimiento` = Pendiente | **378** (todos) |
| Un contacto de 2023 y 2026 (p. ej. busca por su teléfono) | `Años con reservas` = 2023 y 2026; `Resumen de reservas` con ambas |

Si algún número no cuadra, no sigas: dime cuál es y lo reviso contra el CSV.

## 5. Listas (segmentos)

**Contactos → Listas → Crear lista → Basada en contactos → Lista activa** (se actualiza sola). Estas son las 7 que necesitas y lo que mostrarán hoy:

| Lista | Filtros (todos con Y) | Hoy |
|---|---|---:|
| **WA · Elegibles** | `WhatsApp: consentimiento` es **Sí** · `Calidad del teléfono` es cualquiera de **Válido, Asumido MX** · `WhatsApp: estado del último envío` no es ninguno de **Sin WhatsApp, Bloqueado** | 0 |
| **WA · Consentimiento pendiente** | `WhatsApp: consentimiento` es **Pendiente** · `Calidad del teléfono` es cualquiera de **Válido, Asumido MX** | 378 |
| **Recurrentes** | `Total de reservas` es mayor o igual a **2** | 60 |
| **Con reserva en 2026** | `Años con reservas` contiene **2026** | 94 |
| **Dormidos (sin reserva en 2026)** | `Años con reservas` no contiene **2026** | 284 |
| **Sin reserva en 12 meses** | `Última reserva` es anterior a hace **365 días** | varía |
| **Revisar datos** | `Calidad del teléfono` es **Asumido MX** · **o** · `Confianza del nombre` es **Baja** | 60 |

**«WA · Elegibles» es la única lista que el bot (o cualquier campaña) debe usar para escribir por iniciativa propia.** Empieza vacía a propósito: se llena a medida que registras consentimientos.

Crea además una **vista guardada** de contactos con las columnas: Nombre, Teléfono, Consentimiento, Calidad del teléfono, Última reserva, Total de reservas, Años con reservas.

## 6. Credencial para el bot

HubSpot cambia estos menús con frecuencia; lo que necesitas es un **token de servidor** con alcances mínimos. En la mayoría de cuentas: **Configuración → Integraciones → Aplicaciones privadas → Crear aplicación privada** (*Settings → Integrations → Private apps*).

| Credencial | Para qué | Alcances |
|---|---|---|
| **Temporal** (sección 3) | Crear propiedades; se borra al terminar | `crm.schemas.contacts.write` |
| **Bot** (permanente) | Lo que usa el VPS | `crm.objects.contacts.read`, `crm.objects.contacts.write` |
| Fase 2 (opcional) | Negocios/reservas | `crm.objects.deals.read`, `crm.objects.deals.write` |

- Guarda el token **solo** en el VPS, en un archivo de entorno con permisos `600` (por ejemplo `/etc/chatbot/hubspot.env` con `HUBSPOT_TOKEN=...`). **Nunca** en git, en el chat ni en capturas de pantalla.
- Si el token se filtra: **revócalo** en HubSpot y crea otro. Rótalo una o dos veces al año.
- Dos credenciales separadas (propiedades vs. bot) significan que un token filtrado del bot no puede alterar tu esquema de datos.

## 7. Reservas nuevas: negocios (fase 2)

### 7.1 Pipeline «Reservas»

**Configuración → Objetos → Negocios → Pipelines.** Si tu plan permite un solo pipeline, adapta el que ya existe renombrando sus etapas.

| Etapa | Probabilidad | Significado |
|---|---:|---|
| Consulta | 10 % | Preguntó por fechas/precio |
| Cotización enviada | 30 % | Recibió precio |
| Anticipo recibido | 70 % | Pagó anticipo |
| Reserva confirmada | 90 % | Fecha apartada |
| **Estancia completada** | 100 % (*cerrado ganado*) | Ya se hospedó |
| **Cancelada / no concretada** | 0 % (*cerrado perdido*) | No se hizo |

### 7.2 Propiedades del negocio (todas opcionales)

`Fecha de llegada` (fecha), `Fecha de salida` (fecha), `Número de huéspedes` (número), `Tipo de reserva` (lista: Individual · Familia · Boda o evento · Empresa), `Canal de origen` (lista: WhatsApp · Teléfono · Redes · Recomendación · Otro). El monto total va en el campo nativo *Importe* (MXN).

### 7.3 ¿Importar el historial como negocios?

**Mi recomendación: no, todavía.** Las reservas históricas ya están resumidas en cada contacto, y 2026 solo trae el mes de reporte (sin fechas de llegada/salida), así que los negocios saldrían incompletos. Hazlo solo si necesitas reportes por reserva (ocupación o ingresos por mes). En ese caso pídemelo: se hace con `reservas_historial.csv` asociando cada reserva a su contacto por teléfono mediante la API.

## 8. Reglas de operación

1. **Un teléfono, un contacto.** No edites `telefono_e164` a mano. Si un huésped cambia de número, edita `Número de teléfono` y `Teléfono E.164` **juntos** en su ficha original.
2. **Altas nuevas** entran por el bot (mensaje entrante) o por captura manual; siempre con `Fuentes de datos` llena.
3. **Consentimiento.** `WhatsApp: consentimiento` pasa a **Sí** solo con evidencia, y se llenan `fecha` y `origen` en el mismo momento. Que alguien te escriba primero **no** equivale a aceptar promociones: te permite responderle durante 24 horas, nada más.
4. **Bajas.** Cuando el huésped escribe «BAJA», «STOP» o equivalente, el bot lo pasa a **No**. No lo revierte nadie sin un nuevo consentimiento escrito.
5. **Calidad.** Revisa una vez al mes la lista «Revisar datos» y los contactos con estado **Sin WhatsApp** (números que no tienen la app).
6. **Respaldo.** Exporta los contactos una vez al mes (Contactos → Exportar) y guarda el archivo cifrado fuera del VPS.

## 9. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El teléfono perdió el `+` o quedó como `5.2E+11` | El CSV se abrió/guardó en Excel | Regenera el CSV con el script y no lo abras en Excel |
| Fechas vacías o en el año 1970 | Formato de fecha mal elegido en el asistente | Reimporta eligiendo año-mes-día |
| Error «valor no válido» en una lista desplegable | La propiedad se creó con valor interno distinto de la etiqueta | Recrea la opción con valor = etiqueta (sección 3) |
| No aparece «Requerir valores únicos» | Tu plan/cuenta no lo ofrece | Avísame: se cambia el cliente a búsqueda por filtro |
| `403` al crear propiedades con el script | Al token le falta `crm.schemas.contacts.write` | Edita los alcances de la credencial temporal |
| `429` en el bot | Límite de llamadas por segundo | El cliente reintenta solo; reduce el ritmo de envío |
| Contactos sin nombre mostrado | Nombre inválido en el origen | Aparecen en la hoja «Nombres a revisar» de `revision_manual.xlsx` |

## Hacerlo con Claude

Si conectas el conector de HubSpot en [claude.ai/customize/connectors](https://claude.ai/customize/connectors) **y** el entorno de la sesión permite salir a HubSpot (Configuración del entorno → *Network access*), puedo crear las propiedades, hacer la importación y las listas directamente, y verificar los conteos de la sección 4.3. Los conectores se leen al iniciar la sesión, así que hay que abrir una sesión nueva después de conectarlo.

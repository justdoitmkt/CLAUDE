# Integración del bot de WhatsApp (VPS en Hostinger) con HubSpot

## Principio de diseño

**HubSpot es la única fuente de verdad de los huéspedes.** El bot no guarda datos de huéspedes propios; solo una **caché desechable** (se puede borrar y reconstruir desde HubSpot en minutos) para responder rápido y no agotar el límite de llamadas de la API.

```
                      webhook HTTPS (mensajes + estados)
   WhatsApp  ───────────────────────────────────────────►  Bot en el VPS
   (API de Meta) ◄───────────────────────────────────────  (Hostinger)
                      envíos (texto libre / plantillas)       │   ▲
                                                              │   │ caché local (SQLite, desechable)
                                    lecturas y escrituras     ▼   │
                                    por teléfono E.164     ┌────────────┐
                                    (HTTPS, token)         │  HubSpot   │  ← personas del equipo
                                                           │  (CRM)     │    (listas, consentimiento)
                                                           └────────────┘
```

El código de referencia está en `guest_crm/hubspot_api.py` (Python, con pruebas automatizadas). Si tu bot usa otro lenguaje o **n8n**, la sección 5 trae las llamadas HTTP equivalentes: el contrato es el mismo.

## 1. Flujos

### A. Llega un mensaje de un huésped

1. Verifica la firma `X-Hub-Signature-256` del webhook (HMAC-SHA256 del cuerpo con el *app secret* de Meta). Si no coincide, descarta.
2. Descarta repetidos: Meta reintenta webhooks; deduplica por el id del mensaje.
3. Normaliza el `wa_id` con `normalize_wa_id()`. **Importante:** WhatsApp puede entregar móviles mexicanos como `521XXXXXXXXXX` (con un `1`), pero en HubSpot están como `+52XXXXXXXXXX`; la función lo unifica.
4. Si el texto es una baja (`texto_es_baja()`: «BAJA», «STOP», «ya no me escriban»…) → `registrar_baja()` (pone `WhatsApp: consentimiento = No`), confirma por única vez y **no vuelve a escribir** por iniciativa propia.
5. `registrar_mensaje_entrante()`: busca el contacto por teléfono; si existe, marca `wa_ultimo_mensaje_cliente` (abre la ventana de 24 h); si no existe, **lo crea** con consentimiento *Pendiente* y fuente *Bot WhatsApp*.
6. Responde saludando con `saludo(contacto)`: «Hola Marina» solo si el nombre es confiable; si no, «Hola» a secas. Nunca por apellido.

### B. El bot escribe por iniciativa propia (recordatorios, campañas)

1. Lista de destinatarios: `elegibles_para_envio()` (equivale a la lista **WA · Elegibles** de HubSpot): consentimiento = **Sí**, teléfono Válido/Asumido MX, y sin estado *Sin WhatsApp* ni *Bloqueado*.
2. Por cada contacto, decide el formato:
   - `ventana_24h_abierta(contacto)` → **texto libre** permitido.
   - Si no → solo **plantilla aprobada por Meta**.
3. Envía con ritmo controlado (sección 4) y registra el resultado con `registrar_envio(e164, estado, plantilla)` cuando llegue el webhook de estado (enviado / entregado / leído / fallido).
4. Si Meta indica que el número no tiene WhatsApp o no se puede entregar, registra **Sin WhatsApp**: el contacto sale de futuros envíos y de la lista de elegibles.

### C. Sincronización con la caché

| Momento | Qué hace | Método |
|---|---|---|
| Arranque en frío | Carga todos los contactos con teléfono | `modificados_desde(None)` |
| Cada 10 min | Trae solo lo modificado desde la última marca de agua | `modificados_desde(marca)` |
| Mensaje de un número que no está en caché | Consulta directa y la guarda | `obtener_por_telefono()` |
| Antes de un envío masivo | Refresca consentimiento y estado | `elegibles_para_envio()` |

La marca de agua es la `lastmodifieddate` del último contacto procesado. Se pide con `>=` para no perder registros del mismo instante; reprocesar uno repetido es inocuo.

> **Mantén la caché fiel al consentimiento:** antes de cualquier envío masivo, refresca desde HubSpot. Una baja registrada hace un minuto por otra vía (por ejemplo, alguien del equipo en HubSpot) debe respetarse.

## 2. Reglas de WhatsApp que el bot debe cumplir

Las políticas y precios de Meta cambian: confírmalas en la documentación vigente de *WhatsApp Business Platform* antes de salir a producción.

1. **Consentimiento previo (opt-in).** Para escribir por iniciativa propia, la persona debe haber aceptado recibir mensajes de tu negocio por WhatsApp, y debes poder demostrarlo (`WhatsApp: fecha / origen del consentimiento`). Que alguien te haya dado su teléfono para reservar **no basta** para enviar promociones.
2. **Ventana de 24 horas.** Después de un mensaje del cliente puedes responder con texto libre durante 24 h. Fuera de la ventana, solo plantillas aprobadas.
3. **Plantillas.** Se crean y aprueban en Meta antes de usarlas. Las promocionales (*marketing*) se aprueban y se cobran distinto que las de servicio o utilidad (confirmación de reserva, recordatorio de llegada).
4. **Baja inmediata y fácil.** Incluye una forma de salir en los mensajes promocionales («Responde BAJA para dejar de recibir mensajes») y respétala al instante.
5. **Calidad del número.** Si muchas personas bloquean o reportan tus mensajes, Meta baja la calidad de tu número y su límite diario, y puede restringirlo. Es la razón principal para empezar con volúmenes pequeños.
6. **Usa la API oficial (WhatsApp Cloud API).** Si tu bot hoy usa una librería **no oficial** (Baileys, whatsapp-web.js u otras que emulan WhatsApp Web), esto no sirve para escribir a una base de datos: infringe las condiciones de WhatsApp y los envíos masivos son la causa más común de bloqueo definitivo del número. Dime cuál usas y lo evalúo.
7. **Datos personales (México).** Además de Meta, aplica la Ley Federal de Protección de Datos Personales en Posesión de los Particulares: aviso de privacidad vigente que mencione el uso de datos para comunicación comercial, posibilidad de oponerse y atención a derechos ARCO. No soy abogado: valida el aviso con quien lleve lo legal de tu negocio.

## 3. Contrato de datos: quién escribe qué

| Propiedad de HubSpot | Quién la escribe | Cuándo |
|---|---|---|
| `telefono_e164`, `phone`, `firstname`, `lifecyclestage`, `fuentes_datos` | Importación / bot | Alta del contacto |
| `wa_ultimo_mensaje_cliente` | **Bot** | En cada mensaje entrante |
| `wa_ultimo_envio`, `wa_estado_envio`, `wa_plantilla_ultima` | **Bot** | Con cada webhook de estado de un envío |
| `whatsapp_opt_in` = **No** | **Bot** | Cuando el huésped pide baja |
| `whatsapp_opt_in` = **Sí** (+ fecha y origen) | **Bot o equipo**, **solo con evidencia** | Cuando acepta (formulario, QR, respuesta afirmativa a una invitación…) |
| `primera_reserva`, `ultima_reserva`, `total_reservas`, `anios_visita`, `resumen_reservas` | Equipo / proceso de reservas | Al confirmar una reserva |
| `calidad_telefono`, `nombre_*`, `notas_importacion` | Importación / equipo | Limpieza de datos |

El bot **nunca** cambia `whatsapp_opt_in` de «No» a «Sí» por sí solo.

## 4. Límites de HubSpot y de envío

- **Llamadas a la API.** HubSpot limita cuántas peticiones puedes hacer por ventana de segundos y por día, según tu plan, y la **búsqueda** tiene un límite más estricto (del orden de 5 por segundo). Por eso el bot consulta la caché primero y el cliente reintenta solo ante `429` respetando `Retry-After`.
- **Envío por WhatsApp.** Empieza con lotes pequeños (decenas, no cientos) y sube solo si la calidad del número en Meta Business Manager se mantiene alta. Procesa los envíos con 1–2 trabajadores, no en paralelo masivo.
- **Escrituras a HubSpot.** Agrupa en lotes de hasta 100 con `upsert()`; las actualizaciones de estado de envío pueden acumularse unos segundos antes de escribirse.

## 5. Llamadas de referencia (HTTP)

Todas llevan `Authorization: Bearer $HUBSPOT_TOKEN`. El `+` del teléfono se escribe `%2B` en la URL.

```bash
# Buscar un huésped por teléfono (clave única telefono_e164)
curl -s "https://api.hubapi.com/crm/v3/objects/contacts/%2B525512345678?idProperty=telefono_e164&properties=firstname,nombre_saludo,nombre_confianza,whatsapp_opt_in,wa_ultimo_mensaje_cliente" \
  -H "Authorization: Bearer $HUBSPOT_TOKEN"

# Contactos elegibles para escribir por iniciativa propia (paginar con "after")
curl -s -X POST https://api.hubapi.com/crm/v3/objects/contacts/search \
  -H "Authorization: Bearer $HUBSPOT_TOKEN" -H "Content-Type: application/json" \
  -d '{"filterGroups":[{"filters":[
        {"propertyName":"whatsapp_opt_in","operator":"EQ","value":"Sí"},
        {"propertyName":"calidad_telefono","operator":"IN","values":["Válido","Asumido MX"]}]}],
       "properties":["telefono_e164","nombre_saludo","nombre_confianza","wa_estado_envio"],"limit":100}'

# Actualizar por teléfono (registrar una baja)
curl -s -X PATCH "https://api.hubapi.com/crm/v3/objects/contacts/%2B525512345678?idProperty=telefono_e164" \
  -H "Authorization: Bearer $HUBSPOT_TOKEN" -H "Content-Type: application/json" \
  -d '{"properties":{"whatsapp_opt_in":"No","whatsapp_opt_in_fecha":"2026-10-01"}}'

# Crear o actualizar en lote por teléfono (máx. 100 por llamada)
curl -s -X POST https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert \
  -H "Authorization: Bearer $HUBSPOT_TOKEN" -H "Content-Type: application/json" \
  -d '{"inputs":[{"idProperty":"telefono_e164","id":"+525512345678","properties":{"wa_ultimo_envio":"2026-10-01T18:00:00Z","wa_estado_envio":"Entregado"}}]}'
```

**Si usas n8n:** el nodo nativo de HubSpot identifica contactos por **correo**, no por teléfono; para esta base usa el nodo **HTTP Request** (autenticación *Header Auth* con `Authorization: Bearer …`) con las llamadas de arriba. Alternativa para campañas: leer los miembros de la lista **WA · Elegibles** definida en HubSpot (requiere el alcance `crm.lists.read`), de modo que quien opera el CRM controle los segmentos sin tocar el flujo.

## 6. Despliegue en el VPS de Hostinger

- [ ] **Secretos** (token de HubSpot, *app secret* y token de Meta) en un archivo de entorno con permisos `600` (`/etc/chatbot/*.env`), cargado por systemd (`EnvironmentFile=`) o por Docker. Nunca en el repositorio.
- [ ] **HTTPS** válido para el webhook (Meta lo exige): proxy inverso (Caddy o nginx) con certificado Let's Encrypt.
- [ ] **Firewall** (`ufw`): solo 22 (con llave SSH, sin contraseña), 80 y 443. `fail2ban` activo.
- [ ] El bot corre como **usuario sin privilegios**, como servicio systemd con `Restart=always`.
- [ ] **Logs sin datos personales:** enmascara teléfonos (últimos 4 dígitos) y nunca registres el token ni el cuerpo completo de los mensajes.
- [ ] **Reloj sincronizado** (`chrony`): la validación de firmas y las marcas de tiempo dependen de ello.
- [ ] La caché local es desechable, pero respáldala si guardas ahí conversaciones.
- [ ] **Alertas:** HubSpot `401/403` (token revocado) o `429` sostenido; error de firma del webhook; calidad del número en Meta.

## 7. Plan de arranque (piloto) — no envíes a los 378 el primer día

| Fase | Qué se hace | Criterio para avanzar |
|---|---|---|
| **0. Solo lectura** | El bot lee de HubSpot, arma el saludo y decide formato (texto libre / plantilla) **sin enviar nada** (simulacro) | Los 378 contactos se leen sin errores; los saludos tienen sentido |
| **1. Piloto interno** | 5–10 números del equipo con consentimiento *Sí* (origen «Equipo»); una plantilla de prueba | Se registran envío, entrega, lectura y la baja con «BAJA» |
| **2. Recabar consentimiento** | Pedirlo por canales donde el huésped ya está: confirmación de reserva, check-in, QR en recepción, formulario web, o como primera respuesta cuando escribe él | La lista **WA · Elegibles** deja de estar vacía |
| **3. Primeros envíos reales** | Segmentos pequeños (≤ 50 por día) de «Con reserva en 2026» **que ya dieron consentimiento** | Calidad del número estable; casi sin bloqueos |
| **4. Recuperación** | Campañas a «Dormidos» (284) **con consentimiento**, antes de las temporadas altas | Medir reservas atribuidas, bajas y bloqueos |

Tus datos sugieren el calendario. En 2024, de las 248 estancias con fecha conocida (sin contar 14 reservas de bloques de evento, como una boda en noviembre), **89 caen en julio–agosto (36 %)** y noviembre sube a 31 frente a un promedio de unas 14 al mes en los otros nueve meses. Es una hipótesis razonable escribir 8–10 semanas antes de cada temporada (mayo para el verano, septiembre para noviembre); valídala con una campaña pequeña antes de escalarla, porque solo hay un año completo de fechas.

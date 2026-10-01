"""Modelo de datos del CRM en HubSpot: fuente única de verdad.

La usan (1) el script que crea las propiedades por API, (2) el generador del CSV de importación
y (3) el cliente del bot. Los nombres internos van en minúsculas y sin acentos (restricción de
HubSpot); las etiquetas, en español.

Decisión de diseño: en las propiedades de lista el `value` de cada opción es IGUAL a su etiqueta.
Así el importador de HubSpot acepta el CSV sin importar si compara contra etiqueta o valor interno,
y el bot filtra con el mismo texto que ve el usuario en la interfaz.
"""
from __future__ import annotations

GRUPO_CONTACTOS = {"name": "huespedes", "label": "Huéspedes y WhatsApp", "displayOrder": -1}

# --- Valores de listas (value == label) ----------------------------------------------------------
OPT_IN_PENDIENTE, OPT_IN_SI, OPT_IN_NO = "Pendiente", "Sí", "No"
OPT_IN = [OPT_IN_PENDIENTE, OPT_IN_SI, OPT_IN_NO]

CALIDAD_TELEFONO = ["Válido", "Asumido MX", "Revisar"]
CONFIANZA_NOMBRE = ["Alta", "Media", "Baja", "Sin nombre"]

FUENTES = ["Reservas 2023-2024", "Reservas 2024", "Reservas 2026", "Bot WhatsApp", "Captura manual"]
ANIOS = [str(y) for y in range(2023, 2036)]

ESTADO_ENVIO_ENVIADO, ESTADO_ENVIO_ENTREGADO, ESTADO_ENVIO_LEIDO = "Enviado", "Entregado", "Leído"
ESTADO_ENVIO_FALLIDO, ESTADO_SIN_WHATSAPP, ESTADO_BLOQUEADO = "Fallido", "Sin WhatsApp", "Bloqueado"
ESTADOS_ENVIO = [ESTADO_ENVIO_ENVIADO, ESTADO_ENVIO_ENTREGADO, ESTADO_ENVIO_LEIDO,
                 ESTADO_ENVIO_FALLIDO, ESTADO_SIN_WHATSAPP, ESTADO_BLOQUEADO]
# Estados que el bot nunca debe volver a intentar.
ESTADOS_NO_ENVIAR = {ESTADO_SIN_WHATSAPP, ESTADO_BLOQUEADO}


def _opciones(valores: list[str]) -> list[dict]:
    return [{"label": v, "value": v, "displayOrder": i, "hidden": False} for i, v in enumerate(valores)]


def _prop(name: str, label: str, type_: str, field_type: str, description: str, *,
          options: list[str] | None = None, unique: bool = False) -> dict:
    p: dict = {"name": name, "label": label, "type": type_, "fieldType": field_type,
               "groupName": GRUPO_CONTACTOS["name"], "description": description, "formField": False}
    if options is not None:
        p["options"] = _opciones(options)
    if unique:
        p["hasUniqueValue"] = True  # solo se puede fijar al crear la propiedad; después ya no se cambia
    return p


PROPIEDADES_CONTACTO: list[dict] = [
    _prop("telefono_e164", "Teléfono E.164 (clave única)", "string", "text",
          "Teléfono en formato internacional (+521234567890). Clave única: el bot y las importaciones "
          "buscan y actualizan huéspedes por este valor. No editar a mano.", unique=True),
    _prop("nombre_saludo", "Nombre para saludo", "string", "text",
          "Nombre de pila para saludar en WhatsApp. Vacío = el bot usa un saludo genérico."),
    _prop("nombre_confianza", "Confianza del nombre", "enumeration", "select",
          "Qué tan seguro es el nombre de pila detectado. Alta/Media se usa para saludar; Baja/Sin nombre no.",
          options=CONFIANZA_NOMBRE),
    _prop("nombre_reserva_original", "Nombre(s) en las reservas", "string", "textarea",
          "Nombres tal como aparecen en los archivos de reservas (separados por |)."),
    _prop("calidad_telefono", "Calidad del teléfono", "enumeration", "select",
          "Válido = formato internacional correcto. Asumido MX = venía sin código de país y se asumió +52. "
          "Revisar = no se pudo validar.", options=CALIDAD_TELEFONO),
    _prop("whatsapp_opt_in", "WhatsApp: consentimiento", "enumeration", "select",
          "Pendiente = no hay consentimiento registrado (no enviar mensajes de iniciativa propia). "
          "Sí = aceptó recibir mensajes. No = pidió baja.", options=OPT_IN),
    _prop("whatsapp_opt_in_fecha", "WhatsApp: fecha del consentimiento", "date", "date",
          "Fecha en que el huésped aceptó (o retiró) el consentimiento."),
    _prop("whatsapp_opt_in_fuente", "WhatsApp: origen del consentimiento", "string", "text",
          "Cómo y dónde se obtuvo (formulario, mensaje entrante, check-in, QR...)."),
    _prop("wa_ultimo_mensaje_cliente", "WhatsApp: último mensaje del cliente", "datetime", "date",
          "Fecha/hora del último mensaje entrante. Se usa para saber si sigue abierta la ventana de 24 h."),
    _prop("wa_ultimo_envio", "WhatsApp: último envío", "datetime", "date",
          "Fecha/hora del último mensaje enviado por el bot."),
    _prop("wa_estado_envio", "WhatsApp: estado del último envío", "enumeration", "select",
          "Resultado del último envío. 'Sin WhatsApp' y 'Bloqueado' excluyen al contacto de futuros envíos.",
          options=ESTADOS_ENVIO),
    _prop("wa_plantilla_ultima", "WhatsApp: última plantilla enviada", "string", "text",
          "Nombre de la plantilla aprobada por Meta del último envío."),
    _prop("primera_reserva", "Primera reserva", "date", "date",
          "Fecha de la primera reserva conocida. Si solo se conoce el mes, se guarda el día 1."),
    _prop("ultima_reserva", "Última reserva", "date", "date",
          "Fecha de la última reserva conocida. Si solo se conoce el mes, se guarda el día 1."),
    _prop("total_reservas", "Total de reservas", "number", "number",
          "Reservas distintas registradas para este teléfono (ya sin duplicados entre archivos)."),
    _prop("anios_visita", "Años con reservas", "enumeration", "checkbox",
          "Años en los que el huésped tiene al menos una reserva.", options=ANIOS),
    _prop("fuentes_datos", "Fuentes de datos", "enumeration", "checkbox",
          "De qué archivo o canal viene el contacto.", options=FUENTES),
    _prop("resumen_reservas", "Resumen de reservas", "string", "textarea",
          "Lista de reservas (fecha o mes). ×2 = dos reservas el mismo día."),
    _prop("notas_importacion", "Notas de importación", "string", "textarea",
          "Observaciones de la limpieza de datos (nombre dudoso, teléfono compartido, etc.)."),
]

PROPIEDADES_POR_NOMBRE = {p["name"]: p for p in PROPIEDADES_CONTACTO}

# Propiedades estándar de HubSpot que usa el CSV de importación.
ESTANDAR = ["firstname", "lastname", "phone", "lifecyclestage"]

# Orden de columnas del CSV de contactos (encabezados = nombres internos de HubSpot).
COLUMNAS_CSV_CONTACTOS = [
    "telefono_e164", "firstname", "lastname", "phone", "lifecyclestage",
    "nombre_saludo", "nombre_confianza", "nombre_reserva_original", "calidad_telefono",
    "whatsapp_opt_in", "primera_reserva", "ultima_reserva", "total_reservas", "anios_visita",
    "fuentes_datos", "resumen_reservas", "notas_importacion",
]

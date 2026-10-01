# CRM de huéspedes en HubSpot + bot de WhatsApp

Prepara las reservas de 2023, 2024 y 2026 (dos Excel y un PDF) para usarlas como base de datos en HubSpot, y deja listo el contrato para que el bot de WhatsApp del VPS lea y escriba ahí.

## Resultado con tus archivos

| | |
|---|---:|
| Filas leídas → reservas distintas | 552 → 530 |
| **Contactos listos para importar** (un renglón por teléfono) | **378** |
| Filas sin teléfono (a recuperar a mano) | 75 |
| Huéspedes recurrentes / con reserva en 2026 | 60 / 94 |

## Cómo se usa

1. **Entender los datos:** [`docs/01-diagnostico-datos.md`](docs/01-diagnostico-datos.md) (hallazgos, decisiones y 4 supuestos por confirmar).
2. **Configurar HubSpot e importar:** [`docs/02-configuracion-hubspot.md`](docs/02-configuracion-hubspot.md) (plan de 45 minutos).
3. **Conectar el bot:** [`docs/03-integracion-whatsapp.md`](docs/03-integracion-whatsapp.md) (flujos, reglas de WhatsApp, VPS y piloto).

```bash
pip install -r requirements.txt

# 1) Generar el CSV de importación y el reporte de revisión
python -m guest_crm.build --xlsx-2023-2024 Reservas_2023_2024.xlsx \
    --xlsx-2024 Reservas_2024_Actualizado.xlsx --pdf-2026 2026_RESERVAS.pdf --out out/

# 2) Crear las 19 propiedades en HubSpot (simulacro primero; --apply para crear)
export HUBSPOT_TOKEN=...            # token temporal con crm.schemas.contacts.write
python -m guest_crm.hubspot_setup
python -m guest_crm.hubspot_setup --apply

# 3) Importar out/contactos_hubspot.csv desde la interfaz de HubSpot (guía, sección 4)
```

## Contenido

```
guest_crm/
  phones.py          teléfonos → E.164 (+ normalize_wa_id para los webhooks de WhatsApp)
  names.py           limpieza de nombres y nombre para saludo con nivel de confianza
  sources.py         lectura de los 2 Excel y el PDF; fechas con precisión explícita
  build.py           fusión, deduplicación, CSV de importación y hoja de revisión
  hubspot_schema.py  modelo de datos del CRM (fuente única de verdad de las propiedades)
  hubspot_setup.py   crea el grupo y las propiedades por API (idempotente)
  hubspot_api.py     cliente para el bot: buscar por teléfono, elegibles, consentimiento, ventana de 24 h
tests/               pruebas automatizadas con datos sintéticos (sin red ni credenciales)
docs/                diagnóstico · configuración de HubSpot · integración con WhatsApp
```

## Datos personales y secretos

- `out/` contiene nombres y teléfonos reales. Está en `.gitignore`: **no lo subas a un repositorio**.
- El token de HubSpot va solo en la variable de entorno `HUBSPOT_TOKEN` (ver `.env.example`). Nunca en el código.
- Todos los contactos se importan con `WhatsApp: consentimiento = Pendiente`. **No hay envíos por iniciativa propia hasta registrar consentimiento** (guía 03).

## Desarrollo

```bash
pip install -r requirements-dev.txt
python -m pytest
```

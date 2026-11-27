# AUDITOR — Central de Auditorías

Herramienta interna de Control Interno (CeroCero / MUUK FITNESS) para auditar
existencias contra Odoo.

## Qué hace

Eliges el tipo de auditoría, escribes el SKU y Odoo te regresa, en ese momento:

- **A la mano**: las piezas que hay en el almacén.
- **En salida**: las piezas comprometidas en operaciones que todavía no se validan.
- **Libres**: a la mano menos las de salida.
- **Metraje**: en los SKU de piso, los metros totales de la variante.

Capturas lo que contó almacén, la diferencia se marca sola, y al final bajas el
Excel con el formato del machote: una hoja, "Auditoría del día". Cada auditoría
guardada se manda también al Google Sheets de auditorías.

**Solo lectura.** El programa únicamente consulta Odoo. No crea, no modifica y
no valida nada.

## Dos modos

- **Masiva**: toma de golpe tres almacenes, WH, TRANS y AMSF.
- **Fast**: eliges un almacén, WH, TRANS, AMSF o ME.

## Dos formas de correrlo

### 1. En la computadora (oficina)

1. Doble clic en `ABRIR AUDITOR.bat`.
2. Se abre una ventana negra y el navegador con la central.
3. Deja la ventana negra abierta mientras auditas. Para terminar, ciérrala.

Desde el celular en el mismo WiFi: la ventana negra escribe la dirección que hay
que teclear en el teléfono.

### 2. En la nube (Render), para usarlo desde cualquier lugar

El mismo programa corre en [Render](https://render.com) y queda en una dirección
`https://...onrender.com` que se abre desde cualquier teléfono con internet.

Primera vez:

1. Entra a render.com con tu cuenta de GitHub.
2. **New > Blueprint**, elige el repo `AUDITOR`. Render lee `render.yaml`.
3. Render pide los valores de estas variables (no van en el código):

   | Variable | Qué es |
   |---|---|
   | `ODOO_URL` | Dirección de Odoo, por ejemplo `https://empresa.odoo.com` |
   | `ODOO_DB` | Nombre de la base de datos de Odoo |
   | `ODOO_USER` | Usuario de Odoo (de solo lectura) |
   | `ODOO_API_KEY` | Llave de API de ese usuario |
   | `SHEETS_URL` | Dirección del recibidor del Sheets (termina en `/exec`) |
   | `SHEETS_CLAVE` | La clave escrita en el código del Sheets |
   | `AUDITOR_CODIGO` | Código para entrar desde el teléfono. Que sea largo. |
   | `AUDITOR_CLAVE_BORRAR` | Contraseña para borrar una auditoría |

4. **Apply**. En unos minutos Render da la dirección del servicio.

Cada vez que subes cambios al repo, Render vuelve a desplegar solo.

Cosas que hay que saber del plan gratuito:

- El servicio se duerme a los 15 minutos sin uso. La primera vez que lo abres
  después de un rato tarda hasta un minuto en despertar.
- El historial de auditorías que se guarda en el servidor se borra cuando Render
  reinicia o despliega. Lo que no se pierde es lo que ya se mandó al Sheets.

## Instalarlo en el teléfono como aplicación

Abre la dirección de Render en el teléfono, escribe el código de acceso y luego:

- **iPhone (Safari)**: botón Compartir, "Añadir a pantalla de inicio".
- **Android (Chrome)**: menú de tres puntos, "Instalar aplicación" o
  "Añadir a pantalla de inicio".

Queda un icono AUDITOR con el logo de CeroCero y abre a pantalla completa, sin
barra del navegador. El código se pide una sola vez por teléfono.

## Credenciales

En la computadora, el programa lee la llave de Odoo de `..\API ODOO\odoo_config_ecommerce.py`,
fuera de esta carpeta y fuera de este repositorio. En Render la lee de las
variables de entorno.

**Ninguna llave se sube a GitHub.** Si una se sube una vez, queda en el
historial y hay que cambiarla en Odoo.

## Archivos

| Archivo | Para qué es |
|---|---|
| `ABRIR AUDITOR.bat` | Lo que abres con doble clic en la computadora |
| `AUDITOR.py` | El programa que habla con Odoo y levanta la central |
| `index.html` | La central, vista de computadora |
| `movil.html` | La central, vista de celular |
| `manifest.webmanifest`, `sw.js`, `iconos/` | Lo que permite instalarla como app en el teléfono |
| `render.yaml`, `requirements.txt` | Lo que Render necesita para desplegar |

`diagnostico.json` lo escribe el programa cada vez que arranca, para revisar que
la conexión y los almacenes estén bien. No se sube.

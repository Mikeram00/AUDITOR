# -*- coding: utf-8 -*-
"""
AUDITOR — Central de Auditorías de Control Interno (CeroCero)

QUÉ HACE
--------
Abre la central de auditorías en tu navegador y, cada vez que escribes un SKU,
le pregunta a Odoo cuántas piezas hay a la mano y cuántas están en salida.

SOLO LECTURA: este programa únicamente consulta. No crea, no modifica y no
valida nada en Odoo.

CÓMO SE USA
-----------
Doble clic en "ABRIR AUDITOR.bat". Se abre una ventana negra (déjala abierta
mientras auditas) y el navegador con la central. Para terminar, cierra la
ventana negra.

DESDE EL CELULAR
----------------
La ventana negra te escribe la dirección que hay que teclear en el teléfono.
El celular tiene que estar en el mismo WiFi que esta computadora. La página
se acomoda sola: en computadora abre la central, en teléfono abre la vista
de conteo con botones grandes.

DE DÓNDE SACA LA LLAVE
----------------------
En tu computadora: del archivo odoo_config_ecommerce.py que vive en una carpeta
hermana de esta, por ejemplo API o API ODOO. El programa la busca solo, así que
puedes mover la carpeta de lugar sin romper nada. No hay copia de la llave aquí.

En la nube (Render): de las variables de entorno ODOO_URL, ODOO_DB, ODOO_USER y
ODOO_API_KEY. Si esas variables existen, el archivo ya no hace falta.

EN LA NUBE
----------
El mismo programa corre en Render sin cambios. Ahí toma el puerto de la variable
PORT, no abre navegador, y el código de acceso y la clave para borrar salen de
AUDITOR_CODIGO y AUDITOR_CLAVE_BORRAR. El Sheets sale de SHEETS_URL y SHEETS_CLAVE.
"""

import os, re, sys, json, base64, hashlib, webbrowser, importlib.util, xmlrpc.client, threading, urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# CÓDIGO DE ACCESO para entrar desde el celular.
# Cámbialo por el que quieras. Déjalo vacío ("") para quitarlo.
# Desde esta misma computadora nunca te lo va a pedir.
# En la nube se toma de la variable AUDITOR_CODIGO (ahí conviene uno largo:
# es lo único que separa internet de tu stock).
CODIGO_DE_ACCESO = os.environ.get("AUDITOR_CODIGO", "2026")

# Contraseña que se pide para borrar una auditoría del registro.
# En la nube se toma de la variable AUDITOR_CLAVE_BORRAR.
CLAVE_PARA_BORRAR = os.environ.get("AUDITOR_CLAVE_BORRAR", "cer0cer0")
# ---------------------------------------------------------------------------

# True cuando corre en Render (Render define la variable RENDER). También se
# puede forzar con AUDITOR_NUBE=1 en cualquier otro servidor.
EN_NUBE = bool(os.environ.get("RENDER") or os.environ.get("AUDITOR_NUBE"))

BASE = os.path.dirname(os.path.abspath(__file__))
NOMBRE_CFG = "odoo_config_ecommerce.py"
VARS_ODOO = ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_API_KEY")


def config_en_entorno():
    """True si las cuatro variables de Odoo vienen en el entorno (caso Render)."""
    return all(os.environ.get(v) for v in VARS_ODOO)


def buscar_config():
    """Encuentra las credenciales de Odoo aunque muevas la carpeta o le cambies el nombre."""
    padre = os.path.dirname(BASE)
    for ruta in (os.path.join(padre, "API", NOMBRE_CFG),
                 os.path.join(padre, "API ODOO", NOMBRE_CFG),
                 os.path.join(BASE, NOMBRE_CFG)):
        if os.path.exists(ruta):
            return ruta
    try:
        for nombre in sorted(os.listdir(padre)):
            ruta = os.path.join(padre, nombre, NOMBRE_CFG)
            if os.path.exists(ruta):
                return ruta
    except Exception:
        pass
    return os.path.join(padre, "API", NOMBRE_CFG)


CFG = buscar_config()
REGISTROS = os.path.join(BASE, "REGISTROS")
FOTOS = os.path.join(REGISTROS, "FOTOS")
CFG_SHEETS = os.path.join(BASE, "sheets_config.py")
PUERTO = int(os.environ.get("PORT") or 8777)

# Lo que se guarda en la cookie del teléfono: una huella del código, no el código.
HUELLA_CODIGO = hashlib.sha256(("auditor|" + CODIGO_DE_ACCESO).encode("utf-8")).hexdigest()[:32]

# Almacenes que usa la central (código en Odoo -> nombre que ve Miguel)
ALMACENES = {
    "WH":    "Almacén General",
    "TRANS": "En tránsito",
    "AMSF":  "Amazon Seller Flex",
    "ME":    "Merma",
}

ESTADOS = {
    "draft": "Borrador", "waiting": "Esperando", "confirmed": "Esperando",
    "partially_available": "Parcial", "assigned": "Lista",
}

ODOO = {"ok": False}
MOVIL = re.compile(r"iphone|android|ipad|ipod|mobile|silk", re.IGNORECASE)
CACHE_UBIC = {}


# ---------------------------------------------------------------- conexión
def cargar_config():
    if config_en_entorno():
        return tuple(os.environ[v].strip() for v in VARS_ODOO)
    spec = importlib.util.spec_from_file_location("odoo_config", CFG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.ODOO_URL, m.ODOO_DB, m.ODOO_USER, m.ODOO_API_KEY


def conectar():
    url, db, user, key = cargar_config()
    common = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common", allow_none=True)
    version = common.version().get("server_version")
    uid = common.authenticate(db, user, key, {})
    if not uid:
        raise RuntimeError("Odoo no aceptó el usuario o la llave.")
    models = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/object", allow_none=True)
    ODOO.update(ok=True, url=url, db=db, uid=uid, key=key, models=models, version=version)


def leer(modelo, metodo, *args, **kw):
    """Única puerta a Odoo. Solo métodos de lectura."""
    if metodo not in ("search_read", "search", "search_count", "read"):
        raise RuntimeError("Este programa solo puede leer de Odoo.")
    return ODOO["models"].execute_kw(ODOO["db"], ODOO["uid"], ODOO["key"],
                                     modelo, metodo, list(args), kw)


# ---------------------------------------------------------------- almacenes
def almacenes_odoo():
    whs = leer("stock.warehouse", "search_read",
               [["code", "in", list(ALMACENES.keys())]],
               fields=["id", "name", "code", "lot_stock_id"])
    out = {}
    for w in whs:
        out[w["code"]] = {"id": w["id"], "nombre_odoo": w["name"],
                          "raiz": w["lot_stock_id"][0] if w.get("lot_stock_id") else None}
    return out


def ubicaciones_de(raiz):
    """Ids de la ubicación raíz del almacén y de todo lo que cuelga de ella."""
    if raiz in CACHE_UBIC:
        return CACHE_UBIC[raiz]
    ids = leer("stock.location", "search", [["id", "child_of", raiz]])
    CACHE_UBIC[raiz] = set(ids)
    return CACHE_UBIC[raiz]


# ---------------------------------------------------------------- metraje
def metros_por_pieza(prod):
    """1) atributo de la variante en Odoo   2) terminación del SKU"""
    ids = prod.get("product_template_attribute_value_ids") or []
    if ids:
        try:
            vals = leer("product.template.attribute.value", "read", ids,
                        fields=["name", "attribute_id"])
            for v in vals:
                attr = (v.get("attribute_id") or ["", ""])[1].lower()
                nombre = str(v.get("name") or "")
                if "metr" in attr or "metr" in nombre.lower():
                    n = re.search(r"(\d+(?:[.,]\d+)?)", nombre)
                    if n:
                        return float(n.group(1).replace(",", ".")), "atributo de Odoo"
        except Exception:
            pass
    cod = str(prod.get("default_code") or "")
    n = re.search(r"-(\d+(?:[.,]\d+)?)M$", cod, re.IGNORECASE)
    if n:
        return float(n.group(1).replace(",", ".")), "terminación del SKU"
    return 0, "sin metraje"


# ---------------------------------------------------------------- buscador
def buscar_sku(texto):
    """Sugerencias mientras se escribe. Solo lectura."""
    q = (texto or "").strip()
    if not ODOO.get("ok") or len(q) < 2:
        return []
    dominio = ["|", ["default_code", "ilike", q], ["name", "ilike", q]]
    try:
        prods = leer("product.product", "search_read", dominio,
                     fields=["default_code", "display_name"], limit=25)
    except Exception:
        return []
    fuera = []
    for p in prods:
        cod = p.get("default_code") or ""
        if not cod:
            continue
        nombre = re.sub(r"^\[[^\]]*\]\s*", "", p.get("display_name") or "")
        fuera.append({"sku": cod, "nombre": nombre})
    alto = q.upper()
    fuera.sort(key=lambda x: (0 if x["sku"].upper().startswith(alto) else 1, x["sku"]))
    return fuera[:12]


# ---------------------------------------------------------------- consulta
def consultar_sku(sku):
    if not ODOO.get("ok"):
        return {"ok": False, "error": "Ahorita no hay conexión con Odoo. "
                                      "Cierra esta ventana, revisa tu internet y vuelve a abrir el programa."}
    sku = (sku or "").strip().upper()
    if not sku:
        return {"ok": False, "error": "Escribe un SKU."}

    prods = leer("product.product", "search_read", [["default_code", "=", sku]],
                 fields=["id", "display_name", "default_code",
                         "product_template_attribute_value_ids"], limit=2)
    if not prods:
        prods = leer("product.product", "search_read", [["default_code", "ilike", sku]],
                     fields=["id", "display_name", "default_code",
                             "product_template_attribute_value_ids"], limit=2)
    if not prods:
        return {"ok": False, "error": "Odoo no tiene ningún producto con la referencia " + sku + "."}
    if len(prods) > 1:
        return {"ok": False, "error": "Hay más de un producto que empieza con " + sku +
                                      ". Escribe la referencia completa."}

    prod = prods[0]
    pid = prod["id"]
    nombre = re.sub(r"^\[[^\]]*\]\s*", "", prod.get("display_name") or "")
    metros, origen_metros = metros_por_pieza(prod)

    whs = almacenes_odoo()
    salida = {}
    for cod, nom in ALMACENES.items():
        w = whs.get(cod)
        if not w or not w["raiz"]:
            salida[nom] = {"aMano": 0, "reservado": 0, "disponible": 0, "salidas": []}
            continue

        locs = ubicaciones_de(w["raiz"])

        quants = leer("stock.quant", "search_read",
                      [["product_id", "=", pid], ["location_id", "child_of", w["raiz"]]],
                      fields=["quantity", "reserved_quantity", "location_id"])
        a_mano = sum(q.get("quantity") or 0 for q in quants)
        reservado = sum(q.get("reserved_quantity") or 0 for q in quants)
        disponible = a_mano - reservado

        movs = leer("stock.move", "search_read",
                    [["product_id", "=", pid],
                     ["state", "not in", ["done", "cancel"]],
                     ["location_id", "child_of", w["raiz"]]],
                    fields=["product_uom_qty", "state", "date", "picking_id",
                            "location_dest_id", "partner_id", "reference"])

        salidas = []
        for mv in movs:
            dest = mv.get("location_dest_id") or [0, ""]
            if dest[0] in locs:
                continue  # se queda dentro del mismo almacén: no es salida
            pick = mv.get("picking_id") or [0, mv.get("reference") or "Sin folio"]
            socio = mv.get("partner_id")
            salidas.append({
                "folio": pick[1],
                "fecha": str(mv.get("date") or "")[:10],
                "canal": (socio[1] if socio else dest[1]),
                "piezas": round(mv.get("product_uom_qty") or 0, 2),
                "estado": ESTADOS.get(mv.get("state"), mv.get("state")),
            })
        salidas.sort(key=lambda s: s["fecha"])
        salida[nom] = {"aMano": round(a_mano, 2),
                       "reservado": round(reservado, 2),
                       "disponible": round(disponible, 2),
                       "salidas": salidas}

    return {"ok": True, "sku": prod.get("default_code") or sku, "nombre": nombre,
            "metros": metros, "origenMetros": origen_metros,
            "almacenes": salida,
            "hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------- Google Sheets
def config_sheets():
    """Lee la direccion del Sheets. Primero del entorno (nube), luego del archivo.
    Si no hay ninguna de las dos, se trabaja sin Sheets."""
    if os.environ.get("SHEETS_URL"):
        return os.environ["SHEETS_URL"].strip(), (os.environ.get("SHEETS_CLAVE") or "").strip()
    if not os.path.exists(CFG_SHEETS):
        return None, None
    try:
        spec = importlib.util.spec_from_file_location("sheets_config", CFG_SHEETS)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return getattr(m, "SHEETS_URL", None), getattr(m, "SHEETS_CLAVE", "")
    except Exception:
        return None, None


def filas_para_sheets(registro):
    fecha = registro.get("fecha_corta") or registro.get("fecha") or ""
    concepto = registro.get("concepto") or ""
    folio = registro.get("nombre") or registro.get("id") or ""
    filas = []
    for r in registro.get("renglones") or []:
        a_mano = r.get("aMano") or 0
        disp = r.get("disponible")
        if disp is None:
            disp = a_mano
        contado = r.get("contado") or 0
        metros = r.get("metros") or 0
        incidencia = r.get("nota") or ("Con foto" if r.get("fotoArchivo") else "")
        filas.append([
            fecha, concepto, r.get("sku") or "", r.get("almacen") or "",
            a_mano, r.get("enSalida") or 0, disp, contado,
            (contado * metros) if metros else "",
            contado - disp, r.get("quien") or "", incidencia, folio,
        ])
    return filas


def fotos_para_sheets(registro):
    """Las fotos de las incidencias, para que el Sheets las pegue sobre su renglon."""
    fotos = []
    folio = (registro.get("nombre") or "Auditoria").replace("/", "-")
    for i, r in enumerate(registro.get("renglones") or []):
        rel = r.get("fotoArchivo")
        if not rel:
            continue
        ruta = os.path.join(BASE, rel.replace("/", os.sep))
        if not os.path.exists(ruta):
            continue
        try:
            with open(ruta, "rb") as f:
                datos = f.read()
            if len(datos) > 3 * 1024 * 1024:      # fotos enormes: mejor no mandarlas
                continue
            es_png = ruta.lower().endswith(".png")
            fotos.append({
                "fila": i,
                "b64": base64.b64encode(datos).decode("ascii"),
                "tipo": "image/png" if es_png else "image/jpeg",
                "nombre": folio + " " + (r.get("sku") or "SKU") +
                          (".png" if es_png else ".jpg"),
                "ancho": r.get("fotoAncho") or 4,
                "alto": r.get("fotoAlto") or 3,
            })
        except Exception:
            pass
    return fotos


def enviar_a_sheets(registro):
    url, clave = config_sheets()
    if not url:
        return {"ok": False, "error": "Sin sheets_config.py: no hay Sheets conectado."}
    filas = filas_para_sheets(registro)
    if not filas:
        return {"ok": False, "error": "La auditoría no trae renglones."}
    cuerpo = json.dumps({"clave": clave, "filas": filas,
                         "fotos": fotos_para_sheets(registro)}).encode("utf-8")
    try:
        pet = urllib.request.Request(url, data=cuerpo,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(pet, timeout=40) as resp:
            texto = resp.read().decode("utf-8", "replace")
        try:
            r = json.loads(texto)
        except Exception:
            return {"ok": False, "error": "El Sheets contestó algo raro: " + texto[:120]}
        if r.get("ok"):
            salida = {"ok": True, "pegadas": r.get("pegadas", len(filas))}
            if "fotos" in r:
                salida["fotos"] = r.get("fotos")
            else:
                salida["version_vieja"] = True
            if r.get("urls"):
                salida["urls"] = r.get("urls")
            if r.get("avisos"):
                salida["avisos"] = r.get("avisos")
            if r.get("version"):
                salida["version"] = r.get("version")
            return salida
        return {"ok": False, "error": r.get("error") or "El Sheets no aceptó los datos."}
    except Exception as e:
        return {"ok": False, "error": "No pude hablar con el Sheets: " + str(e)[:140]}


def guardar_enlaces_y_borrar_fotos(ident, subida):
    """Guarda el enlace de Drive en cada renglon y borra la foto de esta computadora.

    La foto solo se borra de aqui cuando el Sheets ya confirmo que la tiene.
    Si algo fallo, la foto se queda para no perderla.
    """
    enlaces = {}
    for u in (subida.get("urls") or []):
        try:
            if u.get("url"):
                enlaces[int(u.get("fila"))] = u.get("url")
        except Exception:
            pass
    if not enlaces:
        return 0
    registro = leer_registro(ident)
    if not registro:
        return 0
    borradas = 0
    for i, r in enumerate(registro.get("renglones") or []):
        enlace = enlaces.get(i)
        if not enlace:
            continue
        r["fotoUrl"] = enlace
        rel = r.get("fotoArchivo")
        if rel:
            try:
                os.remove(os.path.join(BASE, rel.replace("/", os.sep)))
                borradas += 1
            except Exception:
                pass
            r.pop("fotoArchivo", None)
    carpeta = os.path.join(FOTOS, ident)
    try:
        if os.path.isdir(carpeta) and not os.listdir(carpeta):
            os.rmdir(carpeta)
    except Exception:
        pass
    with open(os.path.join(REGISTROS, ident + ".json"), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    return borradas


def marcar_sheets(ident, resultado):
    r = leer_registro(ident)
    if not r:
        return
    r["sheets"] = resultado
    with open(os.path.join(REGISTROS, ident + ".json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- registro
ID_VALIDO = re.compile(r"^\d{8}-\d{4}-[0-9a-f]{4}$")


def guardar_fotos(ident, renglones):
    """Saca las fotos del renglón y las deja como archivo .jpg junto al registro."""
    salida = []
    n = 0
    for r in renglones:
        r = dict(r)
        foto = r.pop("foto", None)
        if foto and isinstance(foto, str) and foto.startswith("data:image"):
            try:
                cabeza, cuerpo = foto.split(",", 1)
                ext = "png" if "png" in cabeza else "jpg"
                n += 1
                carpeta = os.path.join(FOTOS, ident)
                os.makedirs(carpeta, exist_ok=True)
                limpio = re.sub(r"[^A-Za-z0-9._-]", "_", str(r.get("sku") or "sku"))[:40]
                nombre = "%02d_%s.%s" % (n, limpio, ext)
                with open(os.path.join(carpeta, nombre), "wb") as f:
                    f.write(base64.b64decode(cuerpo))
                r["fotoArchivo"] = "REGISTROS/FOTOS/" + ident + "/" + nombre
            except Exception:
                r.pop("fotoArchivo", None)
        salida.append(r)
    return salida


def siguiente_parte(fecha):
    """P1 la primera del dia, P2 la segunda, etc. Cuenta tambien las borradas,
    para que un folio nunca se repita."""
    mayor = 0
    for carpeta in (REGISTROS, os.path.join(REGISTROS, "BORRADOS")):
        if not os.path.isdir(carpeta):
            continue
        for nombre in os.listdir(carpeta):
            if not nombre.endswith(".json"):
                continue
            ruta = os.path.join(carpeta, nombre)
            if not os.path.isfile(ruta):
                continue
            try:
                with open(ruta, encoding="utf-8") as f:
                    r = json.load(f)
            except Exception:
                continue
            if r.get("fecha") == fecha:
                try:
                    mayor = max(mayor, int(r.get("parte") or 0))
                except Exception:
                    pass
    return mayor + 1


def guardar_registro(datos):
    """Guarda una auditoria terminada como archivo dentro de REGISTROS."""
    os.makedirs(REGISTROS, exist_ok=True)
    ahora = datetime.now()
    ident = ahora.strftime("%Y%m%d-%H%M") + "-" + os.urandom(2).hex()
    fecha = ahora.strftime("%Y-%m-%d")
    fecha_corta = ahora.strftime("%d/%m/%Y")
    parte = siguiente_parte(fecha)
    nombre = "Auditoria-P" + str(parte) + "-" + fecha_corta
    renglones = datos.get("renglones") or []
    renglones = guardar_fotos(ident, renglones)
    registro = {
        "id": ident,
        "nombre": nombre,
        "parte": parte,
        "guardado": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "hora": ahora.strftime("%H:%M"),
        "fecha": fecha,
        "fecha_corta": fecha_corta,
        "modo": datos.get("modo") or "",
        "almacenes": datos.get("almacenes") or "",
        "quien": datos.get("quien") or "-",
        "concepto": datos.get("concepto") or "",
        "dispositivo": datos.get("dispositivo") or "",
        "renglones": renglones,
        "total_renglones": len(renglones),
        "con_diferencia": sum(1 for r in renglones
                              if (r.get("contado") or 0) != (r.get("aMano") or 0)),
        "piezas_contadas": sum((r.get("contado") or 0) for r in renglones),
        "incidencias": sum(1 for r in renglones if r.get("nota") or r.get("fotoArchivo")),
    }
    with open(os.path.join(REGISTROS, ident + ".json"), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    return registro


def lista_registros():
    if not os.path.isdir(REGISTROS):
        return []
    out = []
    for nombre in os.listdir(REGISTROS):
        if not nombre.endswith(".json"):
            continue
        if not os.path.isfile(os.path.join(REGISTROS, nombre)):
            continue
        try:
            with open(os.path.join(REGISTROS, nombre), encoding="utf-8") as f:
                r = json.load(f)
            out.append({k: r.get(k) for k in
                        ("id", "nombre", "parte", "guardado", "hora", "fecha", "fecha_corta",
                         "modo", "almacenes", "quien", "dispositivo", "concepto", "sheets",
                         "total_renglones", "con_diferencia", "piezas_contadas", "incidencias")})
        except Exception:
            pass
    out.sort(key=lambda r: r.get("guardado") or "", reverse=True)
    return out


def borrar_registro(ident, clave):
    """No borra de verdad: mueve el archivo a REGISTROS\\BORRADOS, por si hay que recuperarlo."""
    if clave != CLAVE_PARA_BORRAR:
        return {"ok": False, "error": "Contraseña incorrecta."}
    if not ID_VALIDO.match(ident or ""):
        return {"ok": False, "error": "Auditoría no válida."}
    origen = os.path.join(REGISTROS, ident + ".json")
    if not os.path.exists(origen):
        return {"ok": False, "error": "Esa auditoría ya no está."}
    papelera = os.path.join(REGISTROS, "BORRADOS")
    os.makedirs(papelera, exist_ok=True)
    destino = os.path.join(papelera, ident + ".json")
    if os.path.exists(destino):
        os.remove(destino)
    os.replace(origen, destino)
    carpeta = os.path.join(FOTOS, ident)
    if os.path.isdir(carpeta):
        papelera_fotos = os.path.join(papelera, "FOTOS")
        os.makedirs(papelera_fotos, exist_ok=True)
        destino_fotos = os.path.join(papelera_fotos, ident)
        if os.path.isdir(destino_fotos):
            for f in os.listdir(destino_fotos):
                os.remove(os.path.join(destino_fotos, f))
            os.rmdir(destino_fotos)
        os.replace(carpeta, destino_fotos)
    print("  Auditoria borrada: " + ident + "  (quedo en REGISTROS\\BORRADOS)")
    return {"ok": True}


def leer_registro(ident):
    if not ID_VALIDO.match(ident or ""):
        return None
    ruta = os.path.join(REGISTROS, ident + ".json")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- red
def ips_locales():
    import socket
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith("127."))


PAGINA_CODIGO = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AUDITOR</title>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;600;900&display=swap" rel="stylesheet">
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#eaf0f5;font-family:Montserrat,Arial,sans-serif;font-weight:300;color:#000;padding:24px}
.c{background:#fff;border-radius:14px;padding:34px 28px;max-width:360px;width:100%;text-align:center}
h1{font-weight:900;font-size:30px;margin:0;letter-spacing:-.02em;text-transform:uppercase}
p{font-size:13px;color:rgba(0,0,0,.55);margin:10px 0 26px}
input{width:100%;padding:15px;font-size:24px;font-weight:900;text-align:center;letter-spacing:.4em;
border:1px solid rgba(0,0,0,.3);border-radius:9px;font-family:inherit}
button{width:100%;margin-top:14px;padding:15px;border:none;border-radius:9px;background:#000;color:#fff;
font-family:inherit;font-weight:700;font-size:12px;letter-spacing:.12em;text-transform:uppercase;cursor:pointer}
</style></head><body><form class="c" method="get" action="/">
<h1>Auditor</h1><p>Control Interno · CeroCero<br>Escribe el código de acceso</p>
<input name="c" inputmode="numeric" autocomplete="off" autofocus placeholder="0000">
<button type="submit">Entrar</button></form></body></html>"""


# ---------------------------------------------------------------- servidor
class Manejador(SimpleHTTPRequestHandler):
    extensions_map = dict(SimpleHTTPRequestHandler.extensions_map,
                          **{".webmanifest": "application/manifest+json",
                             ".js": "text/javascript; charset=utf-8"})

    def __init__(self, *a, **k):
        super().__init__(*a, directory=BASE, **k)

    def log_message(self, *a):
        pass

    def _es_https(self):
        return (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"

    def _json(self, data, code=200):
        cuerpo = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _autorizado(self, ruta):
        if not CODIGO_DE_ACCESO:
            return True
        if not EN_NUBE and self.client_address[0] in ("127.0.0.1", "::1"):
            return True
        if ("auditor=" + HUELLA_CODIGO) in (self.headers.get("Cookie") or ""):
            return True
        if (parse_qs(ruta.query).get("c") or [""])[0] == CODIGO_DE_ACCESO:
            self.cookie_nueva = True
            return True
        return False

    def _pedir_codigo(self):
        cuerpo = PAGINA_CODIGO.encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def end_headers(self):
        # que el navegador no se quede con una versión vieja de la pagina
        self.send_header("Cache-Control", "no-store, must-revalidate")
        if getattr(self, "cookie_nueva", False):
            galleta = "auditor=" + HUELLA_CODIGO + "; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax"
            if self._es_https():
                galleta += "; Secure"
            self.send_header("Set-Cookie", galleta)
            self.cookie_nueva = False
        super().end_headers()

    def do_GET(self):
        ruta = urlparse(self.path)
        self.cookie_nueva = False

        # Render pregunta aquí si el servicio está vivo. No pide código y no revela nada.
        if ruta.path == "/salud":
            return self._json({"ok": True})

        if not self._autorizado(ruta):
            return self._pedir_codigo()

        agente = self.headers.get("User-Agent") or ""
        if ruta.path in ("/", "/index.html"):
            self.path = "/movil.html" if MOVIL.search(agente) else "/index.html"
            return super().do_GET()
        if ruta.path == "/movil":
            self.path = "/movil.html"
            return super().do_GET()
        if ruta.path == "/pc":
            self.path = "/index.html"
            return super().do_GET()

        if ruta.path == "/api/registros":
            return self._json({"ok": True, "registros": lista_registros()})
        if ruta.path == "/api/registro":
            ident = (parse_qs(ruta.query).get("id") or [""])[0]
            r = leer_registro(ident)
            if not r:
                return self._json({"ok": False, "error": "No encontré esa auditoría."}, 404)
            return self._json({"ok": True, "registro": r})
        if ruta.path == "/api/estado":
            return self._json({"ok": ODOO.get("ok", False),
                               "version": ODOO.get("version", ""),
                               "almacenes": len(ALMACENES)})
        if ruta.path == "/api/buscar":
            q = (parse_qs(ruta.query).get("q") or [""])[0]
            try:
                return self._json({"ok": True, "resultados": buscar_sku(q)})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:120]})
        if ruta.path == "/api/sku":
            sku = (parse_qs(ruta.query).get("sku") or [""])[0]
            try:
                return self._json(consultar_sku(sku))
            except Exception as e:
                return self._json({"ok": False,
                                   "error": "Odoo no contestó bien: " + str(e)[:160]})
        return super().do_GET()

    def do_POST(self):
        ruta = urlparse(self.path)
        self.cookie_nueva = False
        if not self._autorizado(ruta):
            return self._pedir_codigo()
        if ruta.path == "/api/subir":
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                datos = json.loads(self.rfile.read(largo).decode("utf-8")) if largo else {}
            except Exception:
                datos = {}
            reg = leer_registro(datos.get("id") or "")
            if not reg:
                return self._json({"ok": False, "error": "No encontré esa auditoría."})
            subida = enviar_a_sheets(reg)
            marcar_sheets(reg["id"], subida)
            return self._json(subida)
        if ruta.path not in ("/api/guardar", "/api/borrar"):
            return self._json({"ok": False, "error": "Ruta desconocida."}, 404)
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            datos = json.loads(self.rfile.read(largo).decode("utf-8"))
            if ruta.path == "/api/borrar":
                return self._json(borrar_registro(datos.get("id"), datos.get("clave")))
            registro = guardar_registro(datos)
            print("  Guardada: " + registro["nombre"] +
                  "  (" + str(registro["total_renglones"]) + " renglones)")
            subida = enviar_a_sheets(registro)
            borradas = guardar_enlaces_y_borrar_fotos(registro["id"], subida)
            marcar_sheets(registro["id"], subida)
            if subida.get("ok"):
                if subida.get("version_vieja"):
                    print("  Sheets: " + str(subida.get("pegadas")) + " renglones."
                          "  OJO: el codigo publicado del Sheets es el viejo,"
                          " por eso no pega fotos.")
                else:
                    print("  Sheets: " + str(subida.get("pegadas")) + " renglones, " +
                          str(subida.get("fotos")) + " fotos")
                if borradas:
                    print("    La foto quedo en Drive; se borro la copia de esta"
                          " computadora.")
                for aviso in (subida.get("avisos") or []):
                    print("    Aviso del Sheets: " + str(aviso)[:200])
            else:
                print("  Sheets: NO subio - " + str(subida.get("error")))
            return self._json({"ok": True, "id": registro["id"],
                               "nombre": registro["nombre"],
                               "guardado": registro["guardado"],
                               "sheets": subida})
        except Exception as e:
            return self._json({"ok": False, "error": "No pude guardar: " + str(e)[:160]})


# ---------------------------------------------------------------- arranque
def diagnostico(error=None):
    d = {"generado": datetime.now().isoformat(timespec="seconds"), "solo_lectura": True,
         "carpeta": BASE,
         "credenciales_en": "variables de entorno" if config_en_entorno() else CFG}
    if error:
        d.update(conexion="FALLÓ", detalle=str(error)[:300])
    else:
        d.update(conexion="OK", version_odoo=ODOO.get("version"))
        try:
            whs = almacenes_odoo()
            d["almacenes_encontrados"] = {c: {"nombre_en_odoo": v["nombre_odoo"],
                                              "tiene_ubicacion": bool(v["raiz"])}
                                          for c, v in whs.items()}
            d["almacenes_que_faltan"] = [c for c in ALMACENES if c not in whs]
            d["variantes_totales"] = leer("product.product", "search_count", [])
            muestra = leer("product.product", "search_read",
                           [["default_code", "like", "VIN-"]],
                           fields=["default_code", "display_name",
                                   "product_template_attribute_value_ids"], limit=3)
            d["muestra_vin"] = []
            for p in muestra:
                m, origen = metros_por_pieza(p)
                d["muestra_vin"].append({"sku": p.get("default_code"),
                                         "nombre": p.get("display_name"),
                                         "metros_por_pieza": m, "salieron_de": origen})
        except Exception as e:
            d["detalle_extra"] = str(e)[:300]
    with open(os.path.join(BASE, "diagnostico.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return d


def main():
    print("=" * 62)
    print("  AUDITOR — Central de Auditorías · Control Interno")
    print("  Solo lectura: este programa nunca escribe en Odoo.")
    print("=" * 62)

    if config_en_entorno():
        print("\nCredenciales: variables de entorno (" + ", ".join(VARS_ODOO) + ")")
    elif not os.path.exists(CFG):
        print("\nNo encontré el archivo de credenciales.")
        print("Lo busqué aquí: " + CFG)
        print("Debe llamarse " + NOMBRE_CFG + " y estar en una carpeta junto a AUDITOR,")
        print("por ejemplo API o API ODOO.")
        if EN_NUBE:
            print("En la nube, define las variables " + ", ".join(VARS_ODOO) + ".")
        diagnostico("No se encontró odoo_config_ecommerce.py ni variables de entorno")
        return 1
    else:
        print("\nCredenciales: " + CFG)
    print("Conectando a Odoo...")
    try:
        conectar()
        print("Conectado. Odoo " + str(ODOO["version"]))
    except Exception as e:
        print("No se pudo conectar: " + str(e)[:200])
        print("La central va a abrir igual, pero con los SKU de ejemplo.")
        diagnostico(e)
    else:
        d = diagnostico()
        faltan = d.get("almacenes_que_faltan") or []
        if faltan:
            print("Aviso: no encontré estos almacenes en Odoo: " + ", ".join(faltan))
        print("Almacenes listos: " + ", ".join(d.get("almacenes_encontrados", {}).keys()))

    url_sheets, _ = config_sheets()
    print("Google Sheets: " + ("conectado" if url_sheets else "sin conectar (falta sheets_config.py)"))

    servidor = ThreadingHTTPServer(("0.0.0.0", PUERTO), Manejador)
    url = "http://127.0.0.1:" + str(PUERTO) + "/"

    if EN_NUBE:
        print("\n" + "-" * 62)
        print("  Corriendo en la nube, puerto " + str(PUERTO) + ".")
        print("  Código de acceso: " + ("definido" if CODIGO_DE_ACCESO else "SIN CÓDIGO (cualquiera entra)"))
        print("-" * 62 + "\n", flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    print("\n" + "-" * 62)
    print("  EN ESTA COMPUTADORA:")
    print("     " + url)
    ips = ips_locales()
    if ips:
        print("\n  DESDE EL CELULAR (mismo WiFi de la empresa):")
        for ip in ips:
            direccion = "http://" + ip + ":" + str(PUERTO) + "/"
            if CODIGO_DE_ACCESO:
                direccion += "?c=" + CODIGO_DE_ACCESO
            print("     " + direccion)
        if CODIGO_DE_ACCESO:
            print("\n  Codigo de acceso: " + CODIGO_DE_ACCESO +
                  "   (se pide una sola vez por telefono)")
    else:
        print("\n  No pude ver la direccion de red de esta computadora.")
    print("-" * 62)
    print("\nDeja esta ventana abierta mientras auditas.")
    print("La primera vez, Windows va a preguntar si permites el paso: dale Permitir.")
    print("Para terminar, cierra esta ventana.\n")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nListo, cerrando.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("Error inesperado: " + repr(e))
        input("\nPresiona Enter para cerrar...")
        sys.exit(1)

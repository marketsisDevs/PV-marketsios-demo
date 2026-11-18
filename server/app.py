"""
Backend de demostración de Marketsis PV (revisión App Store).

Imita los endpoints del backend real que usa la app en el flujo de demo
(login, comandas, cobro, vacíos y listados) sobre SQLite y datos de ejemplo.
No se conecta a SQL Server, API-SYNC, Auth v2 ni al servicio de impresión.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import time
from datetime import datetime

import segno
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

import store
from store import (
    CLIENTES, CLIENTES_DETALLE, CTI_COMANDA, CTI_FACTURA_A, CTI_FACTURA_B, CTI_PEDIDO, CTI_VALE,
    ENVASES, ENVASES_BY_ID, FORMAS_PAGO, PARTIDAS, PARTIDAS_BY_FK, USU_PENDIENTE, USU_RESERVADO,
    Tx, fixture, insert_item, iso, item_row_to_api, new_guid, next_numero, now,
)

VERSION = os.getenv("DEMO_VERSION", "1.0.4")
COMPANY = os.getenv("DEMO_COMPANY", "Marketsis Demo")
CONTACT_EMAIL = os.getenv("DEMO_CONTACT_EMAIL", "mgonzalez@marketsis.com.ar")
PRIVACY_UPDATED = "2026-10-13"
TERMS_UPDATED = "2026-11-18"
SECRET = (os.getenv("DEMO_SECRET") or "marketsis-demo-local").encode()
TOKEN_TTL = 7 * 24 * 3600

PERMISSIONS = {"permitirProductosSP": False, "permitirReservasComanda": True}

USERS = {
    1: {"username": "demo", "password": os.getenv("DEMO_PASSWORD", "demo1234"), "name": "Demo", "nivel": -1, "role": "administrador"},
    2: {"username": "vendedor", "password": os.getenv("DEMO_PASSWORD", "demo1234"), "name": "Laura", "nivel": -3, "role": "vendedor"},
}
VENDEDORES = [
    {"Id_Vendedor": 1, "Vendedor_Detalle": "Demo Administrador"},
    {"Id_Vendedor": 2, "Vendedor_Detalle": "Laura Vendedora"},
    {"Id_Vendedor": 3, "Vendedor_Detalle": "Martín Gómez"},
]
VENDEDOR_NOMBRE = {v["Id_Vendedor"]: v["Vendedor_Detalle"] for v in VENDEDORES}
PUESTO = {"success": True, "puesto_id": 1, "detalle": "Puesto Demo 1", "nombre_equipo": "DEMO-CLOUD"}
PUESTOS = [
    {"id_Puesto": 100, "Detalle": "Depósito", "Tipo": 1, "DepositoDe": 0},
    {"id_Puesto": 1, "Detalle": "Puesto Demo 1", "Tipo": 3, "DepositoDe": 0},
    {"id_Puesto": 2, "Detalle": "Puesto Demo 2", "Tipo": 3, "DepositoDe": 0},
]

LISTADOS = fixture("listados")
LISTADOS_EJECUTAR = fixture("listados_ejecutar")

PUBLIC_PATHS = (
    "/api/health", "/api/status", "/api/auth/login", "/api/get_server_url", "/api/system/version",
    "/api/error-report", "/api/frontend-error",
)

app = FastAPI(title="Marketsis PV - Demo", version=VERSION, docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------- auth

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_token(user_id: int) -> str:
    payload = _b64(json.dumps({"uid": user_id, "exp": int(time.time()) + TOKEN_TTL}).encode())
    sig = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str) -> int | None:
    try:
        payload, sig = token.split(".")
        good = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < time.time() or data["uid"] not in USERS:
            return None
        return int(data["uid"])
    except Exception:
        return None


def user_payload(uid: int) -> dict:
    u = USERS[uid]
    return {
        "id": uid, "name": u["name"], "email": f"{u['username']}@demo.marketsis.com.ar",
        "role": u["role"], "nivel": u["nivel"], "Detalle": u["name"], "permissions": PERMISSIONS,
    }


@app.middleware("http")
async def demo_middleware(request: Request, call_next):
    store.ensure_fresh()
    path = request.url.path
    if request.method != "OPTIONS" and path.startswith("/api/") and not path.startswith(PUBLIC_PATHS):
        auth = request.headers.get("authorization", "")
        uid = read_token(auth[7:]) if auth.startswith("Bearer ") else None
        if uid is None:
            return JSONResponse({"detail": "Token inválido o expirado"}, status_code=401)
        request.state.uid = uid
    return await call_next(request)


def uid_of(request: Request) -> int:
    return request.state.uid


async def body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {"items": data}
    except Exception:
        return {}


@app.post("/api/auth/login")
async def login(request: Request):
    data = await body(request)
    ident = str(data.get("username") or data.get("email") or "").strip().lower()
    pwd = str(data.get("password") or "")
    for uid, u in USERS.items():
        if ident in (u["username"], f"{u['username']}@demo.marketsis.com.ar") and pwd == u["password"]:
            return {"user": {**user_payload(uid), "EMP_ID": "DEMO"}, "token": make_token(uid)}
    raise HTTPException(status_code=401, detail="Credenciales inválidas")


@app.get("/api/auth/me")
def me(request: Request):
    return {"user": user_payload(uid_of(request))}


@app.post("/api/auth/refresh")
def refresh(request: Request):
    return {"token": make_token(uid_of(request))}


@app.post("/api/auth/logout")
def logout():
    return {"status": "ok"}


@app.post("/api/auth/verify/token")
def verify_token(request: Request):
    uid = uid_of(request)
    return {"USER_ID": uid, "USERNAME": USERS[uid]["name"], "PUE_ID": "1", "EMP_ID": "DEMO"}


# ---------------------------------------------------------------- sistema

def public_base(request: Request) -> str:
    env = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if env:
        return env.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{request.headers.get('host', request.url.netloc)}"


@app.get("/api/health")
def health():
    return {
        "status": "online", "service": "Sync-Marketsis API", "version": VERSION,
        "database": {"status": "online", "message": "Demo (datos de ejemplo)"},
    }


@app.get("/api/status")
def status():
    return {
        "estado": "activo", "mensaje": "Demo funcionando", "conexion_db_local": True,
        "conexion_db_remota": False, "ultima_actividad": iso(now()), "puerto": 443, "protocolo": "https",
    }


@app.get("/api/system/version")
def system_version():
    return {"version": VERSION}


@app.get("/api/get_server_url")
def get_server_url(request: Request):
    base = public_base(request)
    return {
        "protocol": "https", "requires_https": True, "mobile_lan_http_url": base,
        "apk_download_url": None, "apk_download_https_url": None,
        "company_slug": "demo", "company_display_name": COMPANY, "server_version": VERSION,
        "ios_app_store_url": os.getenv("IOS_APP_STORE_URL") or None, "url": base, "ip_url": base,
    }


@app.post("/api/error-report")
@app.post("/api/frontend-error")
def swallow_errors():
    return {"status": "ok"}


@app.get("/api/user-settings")
def get_settings(request: Request):
    with Tx() as c:
        row = c.execute("SELECT data FROM user_settings WHERE user_id = ?", (uid_of(request),)).fetchone()
    return json.loads(row["data"]) if row else {"menuIconSizePercent": 100, "darkMode": False}


@app.put("/api/user-settings")
async def put_settings(request: Request):
    data = {**get_settings(request), **(await body(request))}
    with Tx() as c:
        c.execute("INSERT OR REPLACE INTO user_settings VALUES (?, ?)", (uid_of(request), json.dumps(data)))
    return data


@app.get("/api/print/politica")
def print_politica():
    return {
        "host_pc_tickets": ["vale", "pedido", "factura_a", "factura_b", "movimiento_interno"],
        "host_pc_tickets_raw": "demo",
        "tickets_permissions": {
            "sincronizado_desde_print": False, "ultimo_error_sincronizacion": None,
            "ultima_sincronizacion_exitosa": None, "nota": "Demo: sin impresión.",
        },
        "cnfg_impresiones_activas": [],
        "cnfg_resuelto": {"vale": None, "pedido": None, "factura_a": None, "factura_b": None, "movimiento_interno": None},
        "solo_host_pc_vale": True, "solo_host_pc_pedido": True, "solo_host_pc_factura_a": True,
        "solo_host_pc_factura_b": True, "solo_host_pc_movimiento_interno": True,
        "print_service_base_configurado": False,
    }


@app.get("/api/print/tickets-permissions")
def tickets_permissions():
    return print_politica()["tickets_permissions"]


# ---------------------------------------------------------------- maestros

@app.get("/api/comandas/config")
def comandas_config():
    # Paridad con PV Back get_comandas_config() / config.ini [COMANDAS]
    return {"prom_limit": 20.0, "ultimo_precio": False}


@app.get("/api/comandas/obtener_partidas")
def obtener_partidas():
    return PARTIDAS


@app.get("/api/movimientos-internos/partidas")
def mov_partidas():
    return fixture("movimientos_partidas")


@app.get("/api/movimientos-internos/puesto-actual")
def puesto_actual():
    return PUESTO


@app.get("/api/movimientos-internos/puestos")
def puestos():
    return {"success": True, "puestos": PUESTOS}


@app.get("/api/clientes/")
def clientes(search: str | None = None):
    rows = CLIENTES
    if search and search.strip():
        needle = search.strip().lower()
        rows = [c for c in CLIENTES if needle in c["Razon_soc"].lower() or needle in (c["Alias"] or "").lower()]
    return {"success": True, "clientes": rows, "total": len(rows)}


@app.get("/api/clientes/detalle/{id_cli}")
def cliente_detalle(id_cli: int):
    det = CLIENTES_DETALLE.get(str(id_cli))
    return {"success": det is not None, "cliente": det}


@app.post("/api/clientes/refrescar")
def clientes_refrescar():
    return {"success": True, "total": len(CLIENTES), "mensaje": "Caché de clientes actualizada"}


@app.get("/api/formas-pago/")
def formas_pago():
    return FORMAS_PAGO


@app.get("/api/formas-pago/cuentas-transferencia-puesto")
def cuentas_transferencia():
    return fixture("cuentas_transferencia")


@app.get("/api/users/vendedores-con-usuario")
def vendedores():
    return {"vendedores": VENDEDORES, "total": len(VENDEDORES)}


@app.get("/api/users/listar")
def users_listar():
    users = []
    for v in VENDEDORES:
        uid = v["Id_Vendedor"] if v["Id_Vendedor"] in USERS else None
        u = USERS.get(uid) if uid else None
        users.append({
            **v, "Usuario_ID": uid, "Usuario_Detalle": u["username"] if u else None, "Clave": None,
            "Nivel": u["nivel"] if u else None, "role": u["role"] if u else None, "EMP_Id": "DEMO",
            "Email": f"{u['username']}@demo.marketsis.com.ar" if u else None, "token": None,
            "tiene_usuario": u is not None,
        })
    return {"users": users, "total": len(users)}


@app.get("/api/users/permisos/{user_id}")
def users_permisos(user_id: int):
    return {"permissions": PERMISSIONS}


@app.get("/api/caja/cuentas")
def caja_cuentas():
    return fixture("caja_cuentas")


@app.get("/api/productos-sin-partida/catalogo")
def prod_sp_catalogo():
    return fixture("prod_sp_catalogo")


@app.get("/api/productos-sin-partida/listado")
def prod_sp_listado():
    return {"items": []}


# ---------------------------------------------------------------- comandas

def comanda_row_to_api(r) -> dict:
    return {
        "id_Comprobante": r["id"], "Cti_id": r["cti_id"], "numero": r["numero"], "Cliente": r["cliente"],
        "ClienteDetalle": r["cliente_detalle"], "fecha": r["fecha"], "Tipo_pago": r["tipo_pago"],
        "Id_Vendedor": r["id_vendedor"], "Percepcion": 0.0, "USU_ID": r["usu_id"], "id_factura": r["id_factura"],
    }


def estado_de(c: dict) -> str:
    if c.get("id_factura"):
        return "facturado"
    if c["USU_ID"] == USU_PENDIENTE:
        return "pendiente"
    if c["USU_ID"] == USU_RESERVADO:
        return "reservado"
    return "enviado"


def get_comanda(c, id_comprobante: str):
    r = c.execute("SELECT * FROM comandas WHERE id = ?", (str(id_comprobante).upper(),)).fetchone()
    return comanda_row_to_api(r) if r else None


def get_items(c, table: str, id_comprobante: str) -> list[dict]:
    rows = c.execute(f"SELECT * FROM {table} WHERE id_comprobante = ? ORDER BY orden", (str(id_comprobante).upper(),))
    return [item_row_to_api(r) for r in rows]


def _cliente_id(v) -> int:
    try:
        return int(v) if v is not None and int(v) > 0 else 0
    except (TypeError, ValueError):
        return 0


def _tipo_pago(v) -> int:
    try:
        t = int(v)
    except (TypeError, ValueError):
        return 1
    return t if t in (1, 2, 5) else 1


@app.post("/api/comandas/nueva-comanda")
async def nueva_comanda(request: Request):
    data = await body(request)
    if not data.get("ClienteDetalle"):
        raise HTTPException(400, "ClienteDetalle es requerido")
    items = data.get("items") or []
    if not items:
        raise HTTPException(400, "Debe enviar al menos un item")
    with Tx() as c:
        cid = new_guid()
        numero = next_numero(c, CTI_COMANDA)
        c.execute(
            "INSERT INTO comandas VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, CTI_COMANDA, numero, _cliente_id(data.get("Cliente")), data["ClienteDetalle"],
             iso(now()), _tipo_pago(data.get("Tipo_pago")), int(data.get("Id_Vendedor") or uid_of(request)),
             USU_PENDIENTE, None),
        )
        agregados = [
            {"id_comp_items": insert_item(c, "comanda_items", cid, it), "index": it.get("index", i)}
            for i, it in enumerate(items)
        ]
    return {"status": "ok", "id_Comprobante": cid, "numero": numero, "items_agregados": agregados}


@app.post("/api/comandas/agregar_item")
async def agregar_item(request: Request):
    data = await body(request)
    items = data.get("items") if data.get("items") is not None else [data]
    ok, fail = [], []
    with Tx() as c:
        for i, it in enumerate(items):
            cid = str(it.get("Id_Comprobante") or "").upper()
            if not cid or not c.execute("SELECT 1 FROM comandas WHERE id = ?", (cid,)).fetchone():
                fail.append({"index": i, "error": "Id_Comprobante es requerido"})
                continue
            ok.append({"index": i, "id_comp_items": insert_item(c, "comanda_items", cid, it)})
    return {
        "status": "ok" if not fail else "partial", "total_items": len(items), "exitosos": len(ok),
        "fallidos": len(fail), "resultados_exitosos": ok, "resultados_fallidos": fail,
    }


@app.put("/api/comandas/editar_item")
async def editar_item(request: Request):
    data = await body(request)
    item_id = str(data.get("Id_comp_items") or "").upper()
    with Tx() as c:
        sets, params = ["cantidad = ?", "precio = ?"], [float(data.get("Cantidad") or 0), float(data.get("Precio") or 0)]
        if data.get("VaciosPrecio") is not None:
            sets.append("vacios_precio = ?")
            params.append(float(data["VaciosPrecio"]))
        if data.get("Vacios1") is not None:
            sets.append("vacios1 = ?")
            params.append(float(data["Vacios1"]))
        cur = c.execute(f"UPDATE comanda_items SET {', '.join(sets)} WHERE id = ?", (*params, item_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Item no encontrado")
    return {"status": "ok", "id_comp_items": item_id}


@app.delete("/api/comandas/eliminar_item")
def eliminar_item(id_comp_items: str):
    with Tx() as c:
        if c.execute("DELETE FROM comanda_items WHERE id = ?", (id_comp_items.upper(),)).rowcount == 0:
            raise HTTPException(404, "Item no encontrado")
    return {"status": "ok", "mensaje": "Item eliminado correctamente"}


@app.delete("/api/comandas/limpiar_carrito")
def limpiar_carrito(id_comprobante: str):
    with Tx() as c:
        n = c.execute("DELETE FROM comanda_items WHERE id_comprobante = ?", (id_comprobante.upper(),)).rowcount
    return {"status": "ok", "items_eliminados": n, "mensaje": f"Se eliminaron {n} item(s)"}


def _cambiar_estado(data: dict, estado: str) -> dict:
    cid = str(data.get("Id_Comprobante") or "").upper()
    if not cid:
        raise HTTPException(400, "Id_Comprobante es requerido")
    with Tx() as c:
        r = c.execute("SELECT * FROM comandas WHERE id = ?", (cid,)).fetchone()
        if not r:
            raise HTTPException(404, "Comprobante no encontrado")
        if r["id_factura"]:
            raise HTTPException(400, "No se puede cambiar el estado de una comanda facturada")
        if estado == "pendiente":
            if r["usu_id"] == USU_RESERVADO:
                raise HTTPException(400, "No se puede deshacer una reserva. Elimine la comanda si ya no corresponde.")
            usu, msg = USU_PENDIENTE, "Comanda revertida a pendiente"
        elif estado == "reservado":
            usu, msg = USU_RESERVADO, "Comanda reservada correctamente"
        else:
            usu, msg = r["id_vendedor"], "Comanda enviada correctamente"
        sets, params = ["usu_id = ?"], [usu]
        if data.get("ClienteDetalle") is not None:
            sets.append("cliente_detalle = ?")
            params.append(data["ClienteDetalle"])
        if data.get("Cliente") is not None:
            sets.append("cliente = ?")
            params.append(_cliente_id(data["Cliente"]))
        c.execute(f"UPDATE comandas SET {', '.join(sets)} WHERE id = ?", (*params, cid))
    return {"status": "ok", "id_Comprobante": cid, "mensaje": msg, "estado": estado}


@app.post("/api/comandas/enviar_comanda")
async def enviar_comanda(request: Request):
    return _cambiar_estado(await body(request), "enviada")


@app.post("/api/comandas/reservar_comanda")
async def reservar_comanda(request: Request):
    return _cambiar_estado(await body(request), "reservado")


@app.post("/api/comandas/revertir_a_pendiente")
async def revertir_comanda(request: Request):
    return _cambiar_estado(await body(request), "pendiente")


@app.post("/api/comandas/actualizar_tipo_pago")
async def actualizar_tipo_pago(request: Request):
    data = await body(request)
    cid = str(data.get("Id_Comprobante") or data.get("id_comprobante") or "").upper()
    t = _tipo_pago(data.get("Tipo_pago", data.get("tipo_pago", 1)))
    with Tx() as c:
        c.execute("UPDATE comandas SET tipo_pago = ? WHERE id = ? AND id_factura IS NULL", (t, cid))
    return {"status": "ok", "Tipo_pago": t}


@app.get("/api/comandas/comanda_pendiente")
def comanda_pendiente(user_id: int):
    with Tx() as c:
        r = c.execute(
            "SELECT * FROM comandas WHERE usu_id = ? AND id_vendedor = ? AND id_factura IS NULL ORDER BY fecha DESC",
            (USU_PENDIENTE, user_id),
        ).fetchone()
        if not r:
            return {"comanda": None, "items": []}
        return {"comanda": comanda_row_to_api(r), "items": get_items(c, "comanda_items", r["id"])}


@app.get("/api/comandas/obtener_comanda")
def obtener_comanda(id_comprobante: str):
    with Tx() as c:
        com = get_comanda(c, id_comprobante)
        if not com:
            raise HTTPException(404, "Comanda no encontrada")
        return {"comanda": com, "items": get_items(c, "comanda_items", id_comprobante)}


@app.get("/api/comandas/obtener_items")
def obtener_items(id_comprobante: str):
    with Tx() as c:
        return get_items(c, "comanda_items", id_comprobante)


@app.delete("/api/comandas/borrar_comanda")
def borrar_comanda(id_comprobante: str):
    cid = id_comprobante.upper()
    with Tx() as c:
        r = c.execute("SELECT id_factura FROM comandas WHERE id = ?", (cid,)).fetchone()
        if not r:
            raise HTTPException(404, "Comanda no encontrada")
        if r["id_factura"]:
            raise HTTPException(400, "No se puede borrar una comanda facturada.")
        n = c.execute("DELETE FROM comanda_items WHERE id_comprobante = ?", (cid,)).rowcount
        c.execute("DELETE FROM comandas WHERE id = ?", (cid,))
    return {
        "status": "ok", "items_eliminados": n, "comanda_eliminada": True,
        "mensaje": f"Comanda eliminada exitosamente. Se eliminaron {n} item(s)",
    }


def _totales(items: list[dict], precio_key: str = "Precio") -> dict:
    precios = sum(i["Cantidad"] * i[precio_key] for i in items)
    vacios = sum(i["Cantidad"] * i["VaciosPrecio"] for i in items)
    return {
        "cantidad_items": len(items), "suma_unidades": sum(i["Cantidad"] for i in items),
        "total_precios": round(precios, 2), "total_vacios": round(vacios, 2), "total_general": round(precios + vacios, 2),
    }


@app.get("/api/comandas/listar")
def listar_comandas(request: Request, estado: str | None = None, id_vendedor: int | None = None):
    if estado in ("reservada", "reserva"):
        estado = "reservado"
    if estado == "enviada":
        estado = "enviado"
    if USERS[uid_of(request)]["role"] == "vendedor":
        id_vendedor = uid_of(request)
    out = []
    with Tx() as c:
        for r in c.execute("SELECT * FROM comandas ORDER BY fecha DESC, numero DESC").fetchall():
            com = comanda_row_to_api(r)
            est = estado_de(com)
            if (estado and est != estado) or (not estado and est == "facturado"):
                continue
            if id_vendedor is not None and com["Id_Vendedor"] != id_vendedor:
                continue
            tot = _totales(get_items(c, "comanda_items", r["id"]))
            fac = {"cantidad_items": 0, "suma_unidades": 0.0, "total_precios": 0.0, "total_vacios": 0.0, "total_general": 0.0}
            f = None
            if r["id_factura"]:
                f = c.execute("SELECT * FROM facturas WHERE id = ?", (r["id_factura"],)).fetchone()
                fac = _totales(get_items(c, "factura_items", r["id_factura"]))
            out.append({
                **com, "vendedor_nombre": VENDEDOR_NOMBRE.get(com["Id_Vendedor"]), **tot,
                "estado": est,
                **{f"factura_{k}": v for k, v in fac.items()},
                "factura_numero": f["numero"] if f else None,
                "factura_cliente_detalle": f["cliente_detalle"] if f else None,
                "factura_cti_id": f["cti_id"] if f else None,
                "factura_id_vendedor": f["id_vendedor"] if f else None,
                "factura_vendedor_nombre": VENDEDOR_NOMBRE.get(f["id_vendedor"]) if f else None,
            })
    return out


def _forma_pago_detalle(tp: int) -> str:
    for f in FORMAS_PAGO["formas_pago"]:
        if int(f["id"]) == int(tp):
            return f["Detalle"].strip()
    return f"Pago {tp}"


def _label_cti(cti: int) -> str:
    return {CTI_PEDIDO: "Pedido", CTI_FACTURA_A: "Factura A", CTI_FACTURA_B: "Factura B"}.get(cti, f"Comprobante {cti}")


@app.post("/api/comandas/guardar_pedido_factura")
async def guardar_pedido_factura(request: Request):
    data = await body(request)
    form = data.get("form") or {}
    filas = data.get("filas") or []
    if form.get("vendedor") is None:
        raise HTTPException(400, "El vendedor es obligatorio.")
    if form.get("formaPago") is None:
        raise HTTPException(400, "La forma de pago es obligatoria.")
    if not filas:
        raise HTTPException(400, "Debe cargar al menos un ítem.")
    tipo = data.get("tipoComprobante", "pedido")
    codigo = data.get("codigoComprobante")
    cti = int(codigo) if tipo == "factura" and codigo in (CTI_FACTURA_A, CTI_FACTURA_B) else CTI_PEDIDO
    cliente_detalle = (data.get("clienteDetalle") or form.get("clienteNombre") or "").strip() or "S/C"
    origen = str(data.get("idComprobanteOrigen") or "").strip().upper() or None
    pago = data.get("pago") or {}
    tp = int(form["formaPago"])

    with Tx() as c:
        items_rem = get_items(c, "comanda_items", origen) if origen else []
        if origen:
            r = c.execute("SELECT id_factura FROM comandas WHERE id = ?", (origen,)).fetchone()
            if r and r["id_factura"]:
                raise HTTPException(409, "La comanda ya fue vinculada a otro pedido. Recargue la lista de comandas.")
        fid = new_guid()
        numero = next_numero(c, cti)
        c.execute(
            "INSERT INTO facturas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, cti, numero, _cliente_id(form.get("cliente")), cliente_detalle, iso(now()), tp,
             int(form["vendedor"]), uid_of(request), float(data.get("porcPerCliente") or 0),
             float(data.get("totalPercepcion") or 0), origen,
             0 if tp == 1 else float(pago.get("porcentaje") or 0), 0 if tp == 1 else float(pago.get("recargo") or 0)),
        )
        for i, f in enumerate(filas):
            rem = items_rem[i] if len(items_rem) == len(filas) else {}
            fk = f.get("FK_id_items") or f.get("Fk_id_items") or f.get("fk_id_items") or rem.get("FK_id_items")
            cant = float(f.get("cantidad") or 0)
            vp = next((f[k] for k in ("VaciosPrecio", "vaciosPrecio", "ValorVacios", "ValorVacio") if f.get(k) is not None), 0)
            insert_item(c, "factura_items", fid, {
                "FK_id_items": fk, "Id_Prod": f.get("Id_Prod") or f.get("id_prod") or rem.get("Id_Prod"),
                "Producto": f.get("detalle"), "Cantidad": cant, "Precio": f.get("precio"),
                "VaciosPrecio": vp, "Vacios1": int(cant), "Iva1": f.get("iva1") or 10.5, "Kg": f.get("Kg") or 0,
            })
        if origen:
            c.execute("UPDATE comandas SET id_factura = ? WHERE id = ? AND id_factura IS NULL", (fid, origen))

    return {
        "status": "ok", "id_Comprobante": fid, "numero": numero, "id_Impresion": None,
        "impresion_encolando": False, "pendiente_impresion_host": False,
        "cnfg_impresion_id_pedido": None, "cnfg_impresion_id_factura_a": None,
        "cnfg_impresion_id_factura_b": None, "cnfg_impresion_id_vale": None,
        "solo_host_pc_pedido": True, "solo_host_pc_factura_a": True, "solo_host_pc_factura_b": True,
        "solo_host_pc_vale": True, "encolar_ticket_pedido_en_print": False, "print_enqueue_path": None,
        "ui_flujo_impresion": None,
    }


@app.get("/api/comandas/obtener_factura")
def obtener_factura(id_factura: str):
    with Tx() as c:
        f = c.execute("SELECT * FROM facturas WHERE id = ?", (id_factura.upper(),)).fetchone()
        if not f:
            raise HTTPException(404, "No se encontró el comprobante fiscal")
        items = get_items(c, "factura_items", f["id"])
    return {
        "factura": {
            "id_Comprobante": f["id"], "Cti_id": f["cti_id"], "numero": f["numero"], "Cliente": f["cliente"],
            "ClienteDetalle": f["cliente_detalle"], "fecha": f["fecha"], "Tipo_pago": f["tipo_pago"],
            "Id_Vendedor": f["id_vendedor"], "Percepcion": f["percepcion"], "Comanda": 0, "FinalP": 0,
            "TotalPercepcion": f["total_percepcion"],
        },
        "items": items,
        "resumen": {
            "tipo_comprobante": _label_cti(f["cti_id"]), "forma_pago": _forma_pago_detalle(f["tipo_pago"]),
            "tiene_recargo": bool(f["recargo_importe"]), "recargo_porcentaje": f["recargo_pct"] or None,
            "recargo_importe": f["recargo_importe"] or None, "ticket_pedido_reimprimible": False,
            "solo_host_pc_pedido": True,
        },
    }


@app.post("/api/comandas/reimprimir_ticket_pedido")
def reimprimir_ticket():
    raise HTTPException(400, "La impresión de tickets no está disponible en la demo.")


# ---------------------------------------------------------------- vacíos

def vale_to_api(c, v) -> dict:
    items = c.execute("SELECT * FROM vale_items WHERE id_vale = ?", (v["id"],)).fetchall()
    return {
        "id_comprobante_vacio": v["id"], "numero": v["numero"], "id_Cli_Entrega": v["cliente"] or 0,
        "ClienteDetalle": v["cliente_detalle"], "fecha": v["fecha"],
        "items": [{"id_envase": i["id_envase"], "Detalle": i["detalle"], "Cantidad": i["cantidad"], "Valor": i["valor"]} for i in items],
        "id_Impresion": None, "impresion_encolando": False, "solo_host_pc_vale": True,
        "pendiente_impresion_host": False, "ui_flujo_impresion": None,
    }


@app.get("/api/vacios/envases")
def envases():
    return {"envases": ENVASES, "total": len(ENVASES)}


@app.post("/api/vacios/enviar")
async def enviar_vale(request: Request):
    data = await body(request)
    items = [i for i in data.get("items") or [] if float(i.get("Cantidad") or 0) > 0]
    if not items:
        raise HTTPException(400, "Debe ingresar al menos un envase con cantidad")
    with Tx() as c:
        cur = c.execute(
            "INSERT INTO vales (numero, cliente, cliente_detalle, fecha, usu_id, estado) VALUES (?,?,?,?,?,?)",
            (next_numero(c, CTI_VALE), _cliente_id(data.get("Cliente")), data.get("ClienteDetalle") or "S/C",
             iso(now()), uid_of(request), None),
        )
        for i in items:
            env = ENVASES_BY_ID.get(int(i["Id_Envase"]), {})
            c.execute(
                "INSERT INTO vale_items VALUES (?,?,?,?,?)",
                (cur.lastrowid, int(i["Id_Envase"]), env.get("Detalle", ""), float(i["Cantidad"]),
                 float(i.get("Valor") or env.get("Valor") or 0)),
            )
        v = c.execute("SELECT * FROM vales WHERE id = ?", (cur.lastrowid,)).fetchone()
        return vale_to_api(c, v)


@app.get("/api/vacios/obtener/{id_comprobante}")
def obtener_vale(id_comprobante: int):
    with Tx() as c:
        v = c.execute("SELECT * FROM vales WHERE id = ?", (id_comprobante,)).fetchone()
        if not v:
            raise HTTPException(404, "Vale no encontrado")
        return vale_to_api(c, v)


def _vales_hoy(c):
    hoy = now().date().isoformat()
    return c.execute("SELECT * FROM vales WHERE substr(fecha, 1, 10) = ? ORDER BY id", (hoy,)).fetchall()


@app.get("/api/vacios/resumen/hoy")
def vacios_resumen_hoy():
    acc: dict[int, dict] = {}
    with Tx() as c:
        for v in _vales_hoy(c):
            for i in c.execute("SELECT * FROM vale_items WHERE id_vale = ?", (v["id"],)):
                r = acc.setdefault(i["id_envase"], {"id_envase": i["id_envase"], "Detalle": i["detalle"], "Recibidos": 0.0})
                r["Recibidos"] += i["cantidad"]
    return {"resumen": sorted(acc.values(), key=lambda r: r["Detalle"]), "fecha": now().date().isoformat()}


@app.get("/api/vacios/detalle/hoy")
def vacios_detalle_hoy():
    out = []
    with Tx() as c:
        for v in _vales_hoy(c):
            for i in c.execute("SELECT * FROM vale_items WHERE id_vale = ?", (v["id"],)):
                out.append({
                    "id_comprobante_vacio": v["id"], "numero": v["numero"], "id_Cli_Entrega": v["cliente"] or 0,
                    "ClienteDetalle": v["cliente_detalle"], "fecha": v["fecha"], "id_envase": i["id_envase"],
                    "Detalle": i["detalle"], "Cantidad": i["cantidad"], "Valor": i["valor"],
                })
    return {"detalles": out, "total": len(out)}


@app.delete("/api/vacios/borrar/{id_comprobante}")
def borrar_vale(id_comprobante: int):
    with Tx() as c:
        c.execute("DELETE FROM vale_items WHERE id_vale = ?", (id_comprobante,))
        if c.execute("DELETE FROM vales WHERE id = ?", (id_comprobante,)).rowcount == 0:
            raise HTTPException(404, "Vale no encontrado")
    return {"status": "ok", "mensaje": "Vale eliminado"}


def _vale_total(c, vid: int) -> float:
    r = c.execute("SELECT COALESCE(SUM(cantidad * valor), 0) t FROM vale_items WHERE id_vale = ?", (vid,)).fetchone()
    return float(r["t"])


@app.post("/api/vacios/consultar")
async def consultar_vales(request: Request):
    p = await body(request)
    tipo = p.get("tipo") or "vales_sin_pagar"
    out = []
    with Tx() as c:
        for v in c.execute("SELECT * FROM vales ORDER BY id DESC").fetchall():
            pagado = v["fecha_cobro"] is not None
            if (tipo == "vales_sin_pagar" and pagado) or (tipo == "vales_pagados" and not pagado):
                continue
            if p.get("numero") and p["numero"] not in v["numero"]:
                continue
            if p.get("cliente") and p["cliente"].lower() not in (v["cliente_detalle"] or "").lower():
                continue
            if p.get("fecha_recibido") and not v["fecha"].startswith(p["fecha_recibido"]):
                continue
            out.append({
                "id_comprobante_vacio": v["id"], "numero": v["numero"], "fecha": v["fecha"],
                "fecha_cobro": v["fecha_cobro"], "cli_entrega": v["cliente"] or 0,
                "cliente_detalle": v["cliente_detalle"], "total": _vale_total(c, v["id"]),
                "cliente_cobro": v["cliente_cobro"], "id_cli_cobro": v["id_cli_cobro"], "Estado": v["estado"],
            })
    return {"success": True, "vales": out, "total": len(out)}


@app.post("/api/vacios/buscar-por-qr")
async def buscar_vale_qr(request: Request):
    raw = str((await body(request)).get("qr_data") or "")
    with Tx() as c:
        v = c.execute("SELECT * FROM vales WHERE ? LIKE '%' || numero || '%'", (raw,)).fetchone()
        if not v:
            raise HTTPException(404, "No se encontró un vale para ese código QR.")
        return {"success": True, "vale": vale_to_api(c, v)}


@app.post("/api/vacios/pagar/{id_comprobante}")
async def pagar_vale(id_comprobante: int, request: Request):
    data = await body(request)
    with Tx() as c:
        c.execute(
            "UPDATE vales SET fecha_cobro = ?, id_cli_cobro = ?, cliente_cobro = ?, estado = 1 WHERE id = ?",
            (iso(now()), _cliente_id(data.get("id_cli_cobro") or data.get("cliente")),
             data.get("cliente_cobro") or data.get("cliente_detalle") or "Contado", id_comprobante),
        )
    return {"success": True, "mensaje": "Vale pagado"}


@app.post("/api/vacios/desafectar-pago/{id_comprobante}")
def desafectar_pago(id_comprobante: int):
    with Tx() as c:
        c.execute("UPDATE vales SET fecha_cobro = NULL, id_cli_cobro = NULL, cliente_cobro = NULL, estado = NULL WHERE id = ?", (id_comprobante,))
    return {"success": True, "mensaje": "Pago desafectado"}


@app.post("/api/vacios/anular-vale/{id_comprobante}")
def anular_vale(id_comprobante: int):
    with Tx() as c:
        c.execute("UPDATE vales SET estado = 9 WHERE id = ?", (id_comprobante,))
    return {"success": True, "mensaje": "Vale anulado"}


def _vales_rango(c, p: dict):
    desde, hasta = p.get("desde") or "0000", (p.get("hasta") or "9999") + "T99"
    env_id = p.get("env_id")
    for v in c.execute("SELECT * FROM vales WHERE fecha >= ? AND fecha <= ? ORDER BY fecha", (desde, hasta)).fetchall():
        for i in c.execute("SELECT * FROM vale_items WHERE id_vale = ?", (v["id"],)):
            if env_id and int(env_id) != i["id_envase"]:
                continue
            yield v, i


@app.post("/api/vacios/listados/totales")
async def vacios_listado_totales(request: Request):
    p = await body(request)
    acc: dict[int, dict] = {}
    with Tx() as c:
        for _v, i in _vales_rango(c, p):
            r = acc.setdefault(i["id_envase"], {"id_Envase": i["id_envase"], "Detalle": i["detalle"], "Cantidad": 0.0, "Precio": 0.0})
            r["Cantidad"] += i["cantidad"]
            r["Precio"] += i["cantidad"] * i["valor"]
    data = list(acc.values())
    return {
        "success": True, "data": data, "columns": ["id_Envase", "Detalle", "Cantidad", "Precio"], "total": len(data),
        "totales": {"Cantidad": sum(d["Cantidad"] for d in data), "Precio": sum(d["Precio"] for d in data)},
    }


@app.post("/api/vacios/listados/detalle")
async def vacios_listado_detalle(request: Request):
    p = await body(request)
    data = []
    with Tx() as c:
        for v, i in _vales_rango(c, p):
            data.append({
                "id_Envase": i["id_envase"], "Fecha": v["fecha"][:10], "ClienteDetalle": v["cliente_detalle"],
                "Numero": v["numero"], "Detalle": i["detalle"], "Cantidad": i["cantidad"], "Precio": i["valor"],
                "FechaCobro": v["fecha_cobro"], "ClienteCobro": v["cliente_cobro"],
            })
    return {
        "success": True, "data": data,
        "columns": ["Fecha", "Numero", "ClienteDetalle", "Detalle", "Cantidad", "Precio", "FechaCobro", "ClienteCobro"],
        "total": len(data), "totales": {"Cantidad": sum(d["Cantidad"] for d in data)},
    }


# ---------------------------------------------------------------- listados

def _vendido_por_partida(c) -> dict[str, tuple[float, float]]:
    """Unidades e importe vendidos por partida (pedidos/facturas + comandas enviadas sin cobrar)."""
    out: dict[str, tuple[float, float]] = {}
    rows = c.execute(
        """SELECT fk_id_items, cantidad, precio FROM factura_items
           UNION ALL
           SELECT ci.fk_id_items, ci.cantidad, ci.precio FROM comanda_items ci
           JOIN comandas co ON co.id = ci.id_comprobante
           WHERE co.id_factura IS NULL AND co.usu_id NOT IN (?, ?)""",
        (USU_PENDIENTE, USU_RESERVADO),
    ).fetchall()
    for r in rows:
        fk = str(r["fk_id_items"] or "").upper()
        if fk not in PARTIDAS_BY_FK:
            continue
        u, t = out.get(fk, (0.0, 0.0))
        out[fk] = (u + r["cantidad"], t + r["cantidad"] * r["precio"])
    return out


def _vendido_por_interno(vendido: dict[str, tuple[float, float]]) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for fk, (u, t) in vendido.items():
        interno = PARTIDAS_BY_FK[fk].get("interno")
        if interno is None:
            continue
        pu, pt = out.get(int(interno), (0.0, 0.0))
        out[int(interno)] = (pu + u, pt + t)
    return out


def _sumar_totales(rows: list[dict], cols: str | None) -> dict:
    tot = {}
    for col in (cols or "").split(","):
        col = col.strip()
        key = next((k for k in (rows[0] if rows else {}) if k.lower() == col.lower()), None)
        if key:
            tot[key] = round(sum(float(r.get(key) or 0) for r in rows), 2)
    return tot


def ejecutar(lid: str) -> dict:
    base = LISTADOS_EJECUTAR.get(str(lid))
    if not base:
        raise HTTPException(404, "Listado no disponible en la demo")
    with Tx() as c:
        vendido = _vendido_por_partida(c)
    if str(lid) == "5":
        por_interno = _vendido_por_interno(vendido)
        rows = []
        for r in base["data"]:
            r = dict(r)
            u, t = por_interno.get(int(r.get("Interno") or 0), (0.0, 0.0))
            if u:
                r["Venta"] = float(r.get("Venta") or 0) + u
                r["Total"] = round(float(r.get("Total") or 0) + t, 2)
                r["Promedio"] = round(r["Total"] / r["Venta"], 2) if r["Venta"] else 0.0
                r["Stock"] = float(r.get("Stock") or 0) - u
            rows.append(r)
    else:
        rows = [
            {
                "Interno": p["interno"], "codigo": p["Codigo"], "DetalleProducto": p["DetalleProducto"],
                "Cantidad": float(p["Cantidad"]) - vendido.get(str(p["Fk_id_items"]).upper(), (0.0, 0.0))[0],
            }
            for p in PARTIDAS
        ]
    return {**base, "data": rows, "total": len(rows), "totales": _sumar_totales(rows, base.get("suma_columns"))}


def _listado_visible(request: Request, l: dict) -> bool:
    return USERS[uid_of(request)]["role"] != "vendedor" or (l.get("categoria") or "").lower() == "vendedores"


@app.get("/api/listados/")
def listados(request: Request):
    rows = [l for l in LISTADOS if _listado_visible(request, l)]
    return {"success": True, "listados": rows, "total": len(rows)}


@app.get("/api/listados/{listado_id}/info")
def listado_info(listado_id: int):
    l = next((l for l in LISTADOS if int(l["id"]) == listado_id), None)
    if not l:
        return JSONResponse({"error": "Listado no encontrado"}, status_code=404)
    return {"success": True, "listado": l}


@app.get("/api/listados/{listado_id}/ejecutar")
def listado_ejecutar(listado_id: int):
    return ejecutar(str(listado_id))


@app.post("/api/listados/ejecutar")
async def listado_ejecutar_post(request: Request):
    data = await body(request)
    if not data.get("listado_id"):
        return JSONResponse({"error": "Las consultas personalizadas no están disponibles en la demo"}, status_code=400)
    return ejecutar(str(data["listado_id"]))


# ---------------------------------------------------------------- resto

@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def fallback(rest: str, request: Request):
    """Pantallas fuera del flujo de demo: responden vacío para que la app no falle."""
    if request.method == "GET":
        return {"success": True, "data": [], "items": [], "total": 0}
    return {"status": "ok", "success": True, "mensaje": "Acción simulada en la demo"}


# ---------------------------------------------------------------- página QR

def pairing_payload(request: Request) -> str:
    return json.dumps(
        {"v": 2, "t": "marketsis-pv", "api": f"{public_base(request)}/api", "company": COMPANY, "server_version": VERSION},
        separators=(",", ":"), ensure_ascii=False,
    )


@app.get("/qr.svg", include_in_schema=False)
def qr_svg(request: Request):
    buf = io.BytesIO()
    segno.make(pairing_payload(request), error="m").save(buf, kind="svg", scale=8, border=2, dark="#0F172A")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/qr.png", include_in_schema=False)
def qr_png(request: Request):
    buf = io.BytesIO()
    segno.make(pairing_payload(request), error="m").save(buf, kind="png", scale=10, border=2)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/logo.png", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
def logo():
    return Response((store.HERE / "static" / "logo.png").read_bytes(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/brand.css", include_in_schema=False)
def brand_css():
    return Response((store.HERE / "static" / "brand.css").read_bytes(), media_type="text/css",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
@app.get("/privacidad", response_class=HTMLResponse, include_in_schema=False)
def privacy():
    html = (store.HERE / "static" / "privacy.html").read_text(encoding="utf-8")
    return html.replace("{{CONTACT}}", CONTACT_EMAIL).replace("{{UPDATED}}", PRIVACY_UPDATED).replace(
        "{{YEAR}}", str(datetime.now().year)
    )


@app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
@app.get("/terminos", response_class=HTMLResponse, include_in_schema=False)
def terms():
    html = (store.HERE / "static" / "terms.html").read_text(encoding="utf-8")
    return html.replace("{{CONTACT}}", CONTACT_EMAIL).replace("{{UPDATED}}", TERMS_UPDATED).replace(
        "{{YEAR}}", str(datetime.now().year)
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    html = (store.HERE / "static" / "index.html").read_text(encoding="utf-8")
    return html.replace("{{API_URL}}", f"{public_base(request)}/api").replace(
        "{{PASSWORD}}", USERS[1]["password"]
    ).replace("{{VERSION}}", VERSION).replace("{{YEAR}}", str(datetime.now().year))


store.reset()

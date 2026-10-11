"""Recorre el flujo de la demo contra el servidor (TestClient o URL con --url)."""
import json
import os
import sys
import tempfile

if "--url" in sys.argv:
    import httpx

    base = sys.argv[sys.argv.index("--url") + 1].rstrip("/")
    client = httpx.Client(base_url=base, timeout=90)
else:
    os.environ.setdefault("DEMO_DB_PATH", os.path.join(tempfile.mkdtemp(), "smoke.sqlite3"))
    from fastapi.testclient import TestClient

    from app import app

    client = TestClient(app)


def check(r, code=200):
    if r.status_code != code:
        raise SystemExit(f"FALLO {r.request.method} {r.request.url} -> {r.status_code}: {r.text[:300]}")
    return r.json()


assert check(client.get("/api/health"))["status"] == "online"
assert client.get("/api/auth/me").status_code == 401
check(client.post("/api/auth/login", json={"username": "demo", "password": "mal"}), 401)
login = check(client.post("/api/auth/login", json={"username": "demo", "password": "demo1234"}))
h = {"Authorization": f"Bearer {login['token']}"}
uid = login["user"]["id"]
print("login ok:", login["user"]["role"])

me = check(client.get("/api/auth/me", headers=h))
partidas = check(client.get("/api/comandas/obtener_partidas", headers=h))
clientes = check(client.get("/api/clientes/", headers=h))["clientes"]
cli = clientes[0]
check(client.get(f"/api/clientes/detalle/{cli['Id_cli']}", headers=h))
for p in ("/api/formas-pago/", "/api/users/vendedores-con-usuario", "/api/movimientos-internos/puesto-actual",
          "/api/user-settings", "/api/print/politica", "/api/comandas/config", "/api/vacios/envases"):
    check(client.get(p, headers=h))
print(f"maestros ok: {len(partidas)} partidas, {len(clientes)} clientes")

pend = check(client.get("/api/comandas/comanda_pendiente", params={"user_id": uid}, headers=h))
assert pend["comanda"] is None

p1, p2 = partidas[0], partidas[5]


def item(p, cant, cid=None):
    d = {"FK_id_items": p["Fk_id_items"], "Id_Prod": p["Codigo"], "Producto": p["DetalleProducto"],
         "Cantidad": cant, "Precio": p["Precio"], "VaciosPrecio": p["ValorVacio"], "Vacios1": cant, "Iva1": 10.5}
    if cid:
        d["Id_Comprobante"] = cid
    return d


nueva = check(client.post("/api/comandas/nueva-comanda", headers=h, json={
    "CTI_ID": 13, "ClienteDetalle": cli["Razon_soc"], "Cliente": cli["Id_cli"], "USU_ID": -1,
    "Id_Vendedor": uid, "items": [item(p1, 2)], "Tipo_pago": 1}))
cid = nueva["id_Comprobante"]
check(client.post("/api/comandas/agregar_item", headers=h, json={"items": [item(p2, 3, cid)]}))
items = check(client.get("/api/comandas/obtener_items", params={"id_comprobante": cid}, headers=h))
assert len(items) == 2
check(client.put("/api/comandas/editar_item", headers=h, json={"Id_comp_items": items[0]["Id_comp_items"], "Cantidad": 4, "Precio": p1["Precio"]}))
pend = check(client.get("/api/comandas/comanda_pendiente", params={"user_id": uid}, headers=h))
assert pend["comanda"]["id_Comprobante"] == cid
check(client.post("/api/comandas/enviar_comanda", headers=h, json={"Id_Comprobante": cid, "ClienteDetalle": cli["Razon_soc"], "Cliente": cli["Id_cli"]}))
enviadas = check(client.get("/api/comandas/listar", params={"estado": "enviado"}, headers=h))
assert any(c["id_Comprobante"] == cid for c in enviadas)
print(f"comanda {nueva['numero']} enviada; enviadas hoy: {len(enviadas)}")

com = check(client.get("/api/comandas/obtener_comanda", params={"id_comprobante": cid}, headers=h))
filas = [{"detalle": i["Producto"], "cantidad": i["Cantidad"], "precio": i["Precio"], "VaciosPrecio": i["VaciosPrecio"], "iva1": 10.5} for i in com["items"]]
ped = check(client.post("/api/comandas/guardar_pedido_factura", headers=h, json={
    "form": {"cliente": cli["Id_cli"], "vendedor": uid, "formaPago": 1, "clienteNombre": cli["Razon_soc"]},
    "filas": filas, "tipoComprobante": "pedido", "clienteDetalle": cli["Razon_soc"], "idComprobanteOrigen": cid}))
fact = check(client.get("/api/comandas/listar", params={"estado": "facturado"}, headers=h))
row = next(c for c in fact if c["id_Comprobante"] == cid)
assert row["factura_numero"] == ped["numero"] and row["factura_cantidad_items"] == 2
det = check(client.get("/api/comandas/obtener_factura", params={"id_factura": ped["id_Comprobante"]}, headers=h))
print(f"pedido {ped['numero']} guardado: total {row['factura_total_general']} ({det['resumen']['forma_pago']})")

env = check(client.get("/api/vacios/envases", headers=h))["envases"]
vale = check(client.post("/api/vacios/enviar", headers=h, json={
    "Cliente": cli["Id_cli"], "ClienteDetalle": cli["Razon_soc"],
    "items": [{"Id_Envase": env[0]["Id_Envase"], "Cantidad": 5, "Valor": env[0]["Valor"]}]}))
check(client.get(f"/api/vacios/obtener/{vale['id_comprobante_vacio']}", headers=h))
res = check(client.get("/api/vacios/resumen/hoy", headers=h))
dets = check(client.get("/api/vacios/detalle/hoy", headers=h))
cons = check(client.post("/api/vacios/consultar", headers=h, json={"tipo": "todos_los_vales"}))
print(f"vale {vale['numero']} ok; resumen envases hoy: {len(res['resumen'])}, detalle: {dets['total']}, vales: {cons['total']}")

lst = check(client.get("/api/listados/", headers=h))["listados"]
for l in lst:
    r = check(client.get(f"/api/listados/{l['id']}/ejecutar", headers=h))
    print(f"listado {l['id']} {r['identificador']!r} ({l['categoria']}): {r['total']} filas, totales {r['totales']}")
check(client.get("/api/listados/99/ejecutar", headers=h), 404)

check(client.get("/api/sync/status", headers=h))
check(client.post("/api/print/qz/pedido/enqueue-by-comprobante", headers=h, json={}))
html = client.get("/")
assert html.status_code == 200 and "/api" in html.text
qr = client.get("/qr.svg")
assert qr.status_code == 200 and qr.text.lstrip().startswith("<")
print("pagina QR ok")
print(json.dumps({"ok": True}))

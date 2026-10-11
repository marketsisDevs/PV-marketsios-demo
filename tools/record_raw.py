"""
Graba respuestas del backend PV real (en proceso, vía TestClient) contra la base local.

Necesita el repo PV-marketsis al lado de este (o la variable PV_REPO) y su venv del Back.
Uso (desde la raíz de este repo):
    ..\\PV-marketsis\\Back\\env\\Scripts\\python.exe tools\\record_raw.py [usuario]

Escribe JSON crudos (con datos reales) en _raw/, que NO se versiona.
Después correr build_fixtures.py para generar server/fixtures/.
"""
import json
import os
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1]
PV_REPO = Path(os.getenv("PV_REPO") or DEMO.parent / "PV-marketsis")
BACK = PV_REPO / "Back"
RAW = DEMO / "_raw"

os.chdir(BACK)
sys.path.insert(0, str(BACK))

from config.config_loader import load_config  # noqa: E402

load_config()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import app  # noqa: E402
from database.database import local_db_engine  # noqa: E402
from services.auth_services import generate_and_store_token  # noqa: E402

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "Mauricio1"


def token_for(username: str) -> tuple[str, int]:
    with local_db_engine.connect() as c:
        row = c.execute(
            text("SELECT ID, RTRIM(EMP_ID) FROM UsuariosPos WHERE RTRIM(Detalle) = :u"),
            {"u": username},
        ).fetchone()
    if not row:
        raise SystemExit(f"Usuario {username!r} no existe en UsuariosPos")
    return generate_and_store_token(row[1], username, row[0]), row[0]


def safe_name(method: str, path: str, params: dict | None) -> str:
    name = f"{method}_{path.strip('/').replace('/', '__')}"
    if params:
        name += "__" + "__".join(f"{k}-{v}" for k, v in sorted(params.items()))
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name) + ".json"


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    token, user_id = token_for(USERNAME)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {token}"}

    def call(method: str, path: str, params: dict | None = None, body=None):
        r = client.request(method, "/api" + path, params=params, json=body, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"_non_json": r.text[:500]}
        out = {"status": r.status_code, "method": method, "path": path, "params": params, "body": body, "data": data}
        (RAW / safe_name(method, path, params)).write_text(
            json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
        size = len(data) if isinstance(data, list) else (len(data) if isinstance(data, dict) else 0)
        print(f"{r.status_code} {method} {path} {params or ''} -> {type(data).__name__}[{size}]")
        return data

    gets = [
        "/health", "/system/version", "/status", "/get_server_url",
        "/auth/me", "/user-settings",
        "/comandas/config", "/comandas/obtener_partidas",
        "/formas-pago/", "/formas-pago/cuentas-transferencia-puesto",
        "/users/vendedores-con-usuario", "/users/listar",
        "/movimientos-internos/puesto-actual", "/movimientos-internos/puestos",
        "/movimientos-internos/partidas",
        "/vacios/envases", "/vacios/resumen/hoy", "/vacios/detalle/hoy",
        "/clientes/", "/caja/cuentas", "/caja/resumen-dia",
        "/print/politica", "/print/tickets-permissions",
        "/productos-sin-partida/catalogo", "/productos-sin-partida/listado",
        "/sync/status", "/sync/config", "/sync/global-status",
        "/listados/",
    ]
    for p in gets:
        call("GET", p)

    call("GET", "/comandas/comanda_pendiente", {"user_id": user_id})
    call("GET", f"/users/permisos/{user_id}")

    for estado in (None, "pendiente", "reservado", "enviado", "facturado"):
        lst = call("GET", "/comandas/listar", {"estado": estado} if estado else None)
        rows = lst if isinstance(lst, list) else (lst.get("comandas") or lst.get("data") or []) if isinstance(lst, dict) else []
        for c in rows[:3]:
            cid = c.get("id_Comprobante") or c.get("Id_Comprobante")
            if cid:
                call("GET", "/comandas/obtener_comanda", {"id_comprobante": cid})
                fac = c.get("Id_Factura") or c.get("id_Factura")
                if fac:
                    call("GET", "/comandas/obtener_factura", {"id_factura": fac})

    clientes = call("GET", "/clientes/", {"limit": 50})
    crow = clientes if isinstance(clientes, list) else (clientes.get("clientes") or clientes.get("data") or []) if isinstance(clientes, dict) else []
    for c in crow[:3]:
        key = c.get("id") or c.get("Id") or c.get("ID") or c.get("codigo")
        if key is not None:
            call("GET", f"/clientes/detalle/{key}")

    listados = call("GET", "/listados/")
    for l in (listados.get("listados") or []) if isinstance(listados, dict) else []:
        lid = l.get("id") or l.get("ID") or l.get("Id")
        if lid is not None:
            call("GET", f"/listados/{lid}/info")
            call("GET", f"/listados/{lid}/ejecutar")

    det = call("GET", "/vacios/detalle/hoy")
    rows = det.get("detalle") or det.get("data") or det.get("vales") or [] if isinstance(det, dict) else []
    for v in rows[:3]:
        vid = v.get("id_comprobante_vacio") or v.get("id_Comprobante")
        if vid:
            call("GET", f"/vacios/obtener/{vid}")

    call("POST", "/vacios/listados/totales", body={})
    call("POST", "/vacios/listados/detalle", body={})
    call("POST", "/vacios/consultar", body={})


if __name__ == "__main__":
    main()

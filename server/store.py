"""Estado de la demo en SQLite: comandas, pedidos/facturas y vales de vacíos."""
import json
import os
import random
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
DB_PATH = Path(os.getenv("DEMO_DB_PATH", HERE / "demo.sqlite3"))
TZ = ZoneInfo(os.getenv("DEMO_TZ", "America/Argentina/Buenos_Aires"))

CTI_COMANDA = 13
CTI_PEDIDO = 11
CTI_FACTURA_A = 83
CTI_FACTURA_B = 84
CTI_VALE = 0
USU_PENDIENTE = -1
USU_RESERVADO = -5

_lock = threading.RLock()
_seeded_for: str | None = None


def fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


PARTIDAS = fixture("partidas")
PARTIDAS_BY_FK = {str(p["Fk_id_items"]).upper(): p for p in PARTIDAS}
CLIENTES = fixture("clientes")
CLIENTES_DETALLE = fixture("clientes_detalle")
ENVASES = fixture("envases")["envases"]
ENVASES_BY_ID = {int(e["Id_Envase"]): e for e in ENVASES}
FORMAS_PAGO = fixture("formas_pago")


def now() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def new_guid() -> str:
    return str(uuid.uuid4()).upper()


SCHEMA = """
CREATE TABLE numeros (cti_id INTEGER PRIMARY KEY, numero TEXT NOT NULL);
CREATE TABLE comandas (
    id TEXT PRIMARY KEY, cti_id INTEGER, numero TEXT, cliente INTEGER, cliente_detalle TEXT,
    fecha TEXT, tipo_pago INTEGER, id_vendedor INTEGER, usu_id INTEGER, id_factura TEXT
);
CREATE TABLE comanda_items (
    orden INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, id_comprobante TEXT, fk_id_items TEXT,
    id_prod INTEGER, producto TEXT, cantidad REAL, precio REAL, vacios_precio REAL, vacios1 REAL,
    iva1 REAL, kg REAL
);
CREATE TABLE facturas (
    id TEXT PRIMARY KEY, cti_id INTEGER, numero TEXT, cliente INTEGER, cliente_detalle TEXT,
    fecha TEXT, tipo_pago INTEGER, id_vendedor INTEGER, usu_id INTEGER, percepcion REAL,
    total_percepcion REAL, id_comanda TEXT, recargo_pct REAL, recargo_importe REAL
);
CREATE TABLE factura_items (
    orden INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, id_comprobante TEXT, fk_id_items TEXT,
    id_prod INTEGER, producto TEXT, cantidad REAL, precio REAL, vacios_precio REAL, vacios1 REAL,
    iva1 REAL, kg REAL
);
CREATE TABLE vales (
    id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT, cliente INTEGER, cliente_detalle TEXT,
    fecha TEXT, usu_id INTEGER, fecha_cobro TEXT, id_cli_cobro INTEGER, cliente_cobro TEXT,
    estado INTEGER
);
CREATE TABLE vale_items (id_vale INTEGER, id_envase INTEGER, detalle TEXT, cantidad REAL, valor REAL);
CREATE TABLE user_settings (user_id INTEGER PRIMARY KEY, data TEXT);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _next_numero(conn, cti_id: int) -> str:
    row = conn.execute("SELECT numero FROM numeros WHERE cti_id = ?", (cti_id,)).fetchone()
    pv, nro = row["numero"].split("-")
    nuevo = f"{pv}-{int(nro) + 1:08d}"
    conn.execute("UPDATE numeros SET numero = ? WHERE cti_id = ?", (nuevo, cti_id))
    return nuevo


def next_numero(conn, cti_id: int) -> str:
    return _next_numero(conn, cti_id)


def insert_item(conn, table: str, id_comprobante: str, it: dict) -> str:
    item_id = new_guid()
    cant = float(it.get("Cantidad") or 0)
    vacios1 = it.get("Vacios1")
    conn.execute(
        f"""INSERT INTO {table} (id, id_comprobante, fk_id_items, id_prod, producto, cantidad, precio,
            vacios_precio, vacios1, iva1, kg) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item_id, id_comprobante, it.get("FK_id_items"), it.get("Id_Prod"), it.get("Producto"),
            cant, float(it.get("Precio") or 0), float(it.get("VaciosPrecio") or 0),
            float(vacios1 if vacios1 is not None else cant), float(it.get("Iva1") or 10.5),
            float(it.get("Kg") or 0),
        ),
    )
    return item_id


def item_from_partida(p: dict, cantidad: int) -> dict:
    return {
        "FK_id_items": p["Fk_id_items"],
        "Id_Prod": p.get("Codigo"),
        "Producto": p["DetalleProducto"],
        "Cantidad": cantidad,
        "Precio": p.get("Precio") or 0,
        "VaciosPrecio": p.get("ValorVacio") or 0,
        "Iva1": p.get("Iva") or 10.5,
        "Kg": 0,
    }


def _seed(conn):
    rng = random.Random(now().date().toordinal())
    conn.executemany(
        "INSERT INTO numeros VALUES (?, ?)",
        [
            (CTI_COMANDA, "0005-00001200"),
            (CTI_PEDIDO, "0005-00002400"),
            (CTI_FACTURA_A, "0005-00000310"),
            (CTI_FACTURA_B, "0005-00000720"),
            (CTI_VALE, "0005-00000050"),
        ],
    )
    hoy = now().replace(hour=7, minute=30, second=0)
    con_precio = [p for p in PARTIDAS if float(p.get("Precio") or 0) > 0]

    def comanda(minutos: int, cliente: dict, usu_id: int, id_vendedor: int, n_items: int) -> str:
        cid = new_guid()
        conn.execute(
            "INSERT INTO comandas VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, CTI_COMANDA, _next_numero(conn, CTI_COMANDA), cliente["Id_cli"], cliente["Razon_soc"],
             iso(hoy + timedelta(minutes=minutos)), 1, id_vendedor, usu_id, None),
        )
        for p in rng.sample(con_precio, n_items):
            insert_item(conn, "comanda_items", cid, item_from_partida(p, rng.randint(1, 8)))
        return cid

    # Una comanda ya cobrada (pedido), dos enviadas listas para cobrar y una reservada.
    cid = comanda(0, CLIENTES[3], 1, 1, 3)
    fid = new_guid()
    conn.execute(
        "INSERT INTO facturas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fid, CTI_PEDIDO, _next_numero(conn, CTI_PEDIDO), CLIENTES[3]["Id_cli"], CLIENTES[3]["Razon_soc"],
         iso(hoy + timedelta(minutes=12)), 1, 1, 1, 0, 0, cid, 0, 0),
    )
    for it in conn.execute("SELECT * FROM comanda_items WHERE id_comprobante = ?", (cid,)).fetchall():
        insert_item(conn, "factura_items", fid, item_row_to_api(it))
    conn.execute("UPDATE comandas SET id_factura = ? WHERE id = ?", (fid, cid))

    comanda(35, CLIENTES[8], 2, 2, 2)
    comanda(50, CLIENTES[15], 1, 1, 4)
    comanda(70, CLIENTES[21], USU_RESERVADO, 2, 2)

    for minutos, cli in ((20, CLIENTES[5]), (65, CLIENTES[12])):
        cur = conn.execute(
            "INSERT INTO vales (numero, cliente, cliente_detalle, fecha, usu_id, estado) VALUES (?,?,?,?,?,?)",
            (_next_numero(conn, CTI_VALE), cli["Id_cli"], cli["Razon_soc"], iso(hoy + timedelta(minutes=minutos)), 1, None),
        )
        for env in rng.sample(ENVASES[:20], 2):
            conn.execute(
                "INSERT INTO vale_items VALUES (?,?,?,?,?)",
                (cur.lastrowid, env["Id_Envase"], env["Detalle"], rng.randint(2, 10), env["Valor"]),
            )


def reset():
    """Base nueva con datos de ejemplo del día."""
    global _seeded_for
    with _lock:
        if DB_PATH.exists():
            DB_PATH.unlink()
        conn = connect()
        try:
            conn.executescript(SCHEMA)
            _seed(conn)
            conn.commit()
        finally:
            conn.close()
        _seeded_for = now().date().isoformat()


def ensure_fresh():
    """Reinicia los datos una vez por día (hora Argentina)."""
    if _seeded_for != now().date().isoformat():
        reset()


class Tx:
    """Conexión con transacción y lock global (SQLite + un solo proceso)."""

    def __enter__(self) -> sqlite3.Connection:
        _lock.acquire()
        self.conn = connect()
        return self.conn

    def __exit__(self, exc_type, *_):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
            _lock.release()
        return False


def item_row_to_api(r: sqlite3.Row) -> dict:
    return {
        "Id_comp_items": r["id"],
        "id_Comprobante": r["id_comprobante"],
        "FK_id_items": r["fk_id_items"],
        "Id_Prod": r["id_prod"],
        "Producto": r["producto"],
        "Cantidad": r["cantidad"],
        "Precio": r["precio"],
        "Vacios": r["precio"],
        "VaciosPrecio": r["vacios_precio"],
        "Vacios1": r["vacios1"],
        "Iva1": r["iva1"],
        "Kg": r["kg"],
    }

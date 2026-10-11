"""
Genera server/fixtures/*.json a partir de _raw/ (grabado con record_raw.py).

Productos, precios, envases y formas de pago son reales. Personas y empresas
(clientes, proveedores, vendedores, usuarios, cuentas bancarias, puestos) se reemplazan
por datos inventados. Nunca se copian claves, tokens, CUIT ni domicilios reales.

Uso (desde la raíz del repo):
    ..\\PV-marketsis\\Back\\env\\Scripts\\python.exe tools\\build_fixtures.py
"""
import json
import random
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1]
RAW = DEMO / "_raw"
OUT = DEMO / "server" / "fixtures"

rng = random.Random(20261010)

PROVEEDORES_FAKE = [
    "Huerta del Sol", "Agro Pampa", "La Esperanza", "Campo Verde", "Don Aurelio",
    "Finca Los Álamos", "Quinta Santa Rita", "Agrícola del Sur", "El Mirador",
    "Frutas del Valle", "Hortícola Norte", "La Cosecha", "Tierra Fértil",
    "San Cayetano", "Los Nogales", "El Trébol", "Granja La Paz", "Raíces SRL",
    "Agro Andina", "Cooperativa Unión", "Los Ceibos", "La Delfina", "Monte Grande",
    "Valle Fértil", "Cerro Azul", "Las Acacias", "Río Dulce", "La Pradera", "Santa Clara",
    "Los Robles", "El Ombú", "Agro Litoral", "Las Lomas", "Don Ernesto", "La Herradura",
    "Finca El Sauce", "Los Aromos", "Chacra La Escondida", "Agro Patagonia", "El Algarrobo",
    "Las Margaritas", "Del Plata Frutas", "Quinta Don Luis", "Los Pinos", "Hortalizas Central",
    "La Campiña",
]

NOMBRES = [
    "Lucía", "Martín", "Sofía", "Diego", "Valentina", "Joaquín", "Camila", "Federico",
    "Florencia", "Nicolás", "Agustina", "Santiago", "Julieta", "Tomás", "Carolina",
    "Matías", "Paula", "Gonzalo", "Rocío", "Facundo",
]
APELLIDOS = [
    "Fernández", "Gómez", "Rodríguez", "López", "Martínez", "Pérez", "Romero", "Sosa",
    "Álvarez", "Torres", "Ruiz", "Ramírez", "Flores", "Benítez", "Acosta", "Medina",
    "Herrera", "Suárez", "Aguirre", "Giménez",
]
COMERCIOS = [
    "Verdulería {a}", "Frutería {a}", "Almacén {a}", "Mercadito {a}", "Autoservicio {a}",
    "Restaurante {a}", "Distribuidora {a}", "Parrilla {a}",
]
CALLES = ["Av. Rivadavia", "Av. Corrientes", "Belgrano", "San Martín", "Mitre", "Sarmiento", "Moreno", "Alsina"]
LOCALIDADES = ["CABA", "Tapiales", "Ramos Mejía", "La Matanza", "Lomas del Mirador"]

PRODUCTOS_DESCARTAR = re.compile(r"prueba|de mauricio", re.I)


def raw(name: str):
    return json.loads((RAW / f"{name}.json").read_text(encoding="utf-8"))["data"]


def write(name: str, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fixture {name}.json")


class Mapper:
    """Reemplazo estable: el mismo valor real siempre da el mismo valor inventado."""

    def __init__(self, pool):
        self.pool = list(pool)
        self.map = {}

    def __call__(self, real: str) -> str:
        key = (real or "").strip().upper()
        if not key:
            return real
        if key not in self.map:
            self.map[key] = self.pool[len(self.map) % len(self.pool)]
        return self.map[key]


proveedor = Mapper(PROVEEDORES_FAKE)


def limpiar_producto(det: str) -> str:
    det = re.sub(r"\[([^\]]+)\]", lambda m: f"[{proveedor(m.group(1))}]", det or "")
    det = det.replace("recontra lavada", "LAVADA").replace("Daifla", "DAIFLA")
    return " ".join(det.split())


def anonimizar(v):
    """Recorre dicts/listas anidados: productos con proveedor entre corchetes y razones sociales."""
    if isinstance(v, list):
        return [anonimizar(x) for x in v]
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if isinstance(x, str) and k.lower() in ("razon_soc", "proveedor", "razonsocial"):
                out[k] = proveedor(x)
            elif isinstance(x, str) and "[" in x:
                out[k] = limpiar_producto(x)
            else:
                out[k] = anonimizar(x)
        return out
    return v


ENVASES_MARCA = {"ORGANICA": "PLASTICO", "PARMENTIER": "CAJON MADERA"}


def cuit_fake(tipo: str) -> str:
    pref = "30" if tipo == "I" else rng.choice(["20", "27"])
    return pref + "".join(str(rng.randint(0, 9)) for _ in range(9))


def build_partidas():
    partidas = []
    for p in raw("GET_comandas__obtener_partidas"):
        if PRODUCTOS_DESCARTAR.search(p.get("DetalleProducto") or ""):
            continue
        p = dict(p)
        p["DetalleProducto"] = limpiar_producto(p["DetalleProducto"])
        # Stock holgado: el revisor no debe chocar con "stock insuficiente".
        p["Cantidad"] = max(float(p.get("Cantidad") or 0), 60.0)
        if not p.get("Precio"):
            p["Precio"] = p.get("UPrecio") or 15000.0
        partidas.append(p)
    write("partidas", partidas)
    return partidas


def build_clientes(n=40):
    clientes, detalles = [], {}
    tipos = ["I"] * 14 + ["M"] * 12 + ["C"] * 12 + ["E"] * 2
    condicion = {"I": "RESP.INSCRIPTO", "M": "RESP.MONOTRIBUTO", "C": "CONSUMIDOR FINAL", "E": "EXENTO"}
    usados = set()
    for i in range(n):
        tipo = tipos[i % len(tipos)]
        while True:
            nom, ape = rng.choice(NOMBRES), rng.choice(APELLIDOS)
            razon = (rng.choice(COMERCIOS).format(a=ape) if tipo in ("I", "E") else f"{ape} {nom}").upper()
            if razon not in usados:
                usados.add(razon)
                break
        id_cli = 1001 + i
        base = {
            "Id_cli": id_cli,
            "Razon_soc": razon,
            "Alias": "",
            "Domicilio": f"{rng.choice(CALLES).upper()} {rng.randint(100, 4999)}",
            "CUIT": cuit_fake(tipo) if tipo != "C" else "",
            "Tipo_Iva": tipo,
            "Localidad": rng.choice(LOCALIDADES),
            "Cod_Postal": "0",
            "Telefono": "",
        }
        clientes.append(base)
        detalles[str(id_cli)] = {
            **base,
            "PorcPer": 3.0 if tipo == "I" and i % 3 == 0 else 0.0,
            "PagoPredeterminado": 0,
            "idVend": 0,
            "ing_brutosNumero": "",
            "Condicion": condicion[tipo],
            "Id_Iva": tipo,
            "CuentaCorriente": tipo == "I",
            "PredeterminarTipo": True,
            "FacturacionKG": False,
            "Ent_Credito": 0.0,
        }
    clientes.sort(key=lambda c: c["Razon_soc"])
    write("clientes", clientes)
    write("clientes_detalle", detalles)
    return clientes


def build_listados():
    keep = {"5": "Resumen de Venta", "2": "Stock del puesto"}
    listados, ejecutar = [], {}
    for lid, nombre in keep.items():
        l = dict(raw(f"GET_listados__{lid}__info")["listado"])
        l["identificador"] = nombre
        l["consulta"] = "(demo)"
        listados.append(l)
        res = raw(f"GET_listados__{lid}__ejecutar")
        rows = []
        for r in res["data"]:
            r = dict(r)
            if PRODUCTOS_DESCARTAR.search(r.get("DetalleProducto") or ""):
                continue
            r["DetalleProducto"] = limpiar_producto(r.get("DetalleProducto"))
            if "Razon_soc" in r:
                r["Razon_soc"] = proveedor(r["Razon_soc"])
            rows.append(r)
        res = {**res, "identificador": nombre, "data": rows, "total": len(rows), "consulta_ejecutada": None}
        ejecutar[lid] = res
    write("listados", listados)
    write("listados_ejecutar", ejecutar)


def build_maestros():
    write("formas_pago", raw("GET_formas-pago"))
    write("cuentas_transferencia", {"cuentas": [
        {"bcp_id": 3, "detalle": "Mercado Pago - Puesto Demo"},
        {"bcp_id": 7, "detalle": "Banco Demo Cta. Cte."},
    ]})
    env = raw("GET_vacios__envases")
    for e in env["envases"]:
        for marca, generico in ENVASES_MARCA.items():
            e["Detalle"] = re.sub(marca, generico, e["Detalle"], flags=re.I)
    write("envases", env)
    write("caja_cuentas", raw("GET_caja__cuentas"))
    mov = anonimizar(raw("GET_movimientos-internos__partidas"))
    mov["partidas"] = [p for p in mov.get("partidas", []) if not PRODUCTOS_DESCARTAR.search(p["DetalleProducto"])]
    write("movimientos_partidas", mov)
    write("prod_sp_catalogo", anonimizar(raw("GET_productos-sin-partida__catalogo")))


def main():
    if not RAW.is_dir():
        raise SystemExit("Falta _raw/. Correr antes tools/record_raw.py")
    build_partidas()
    build_clientes()
    build_listados()
    build_maestros()
    print("proveedores reemplazados:", len(proveedor.map))


if __name__ == "__main__":
    main()

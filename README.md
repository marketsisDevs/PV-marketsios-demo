# Demo para la revisión de App Store

Servidor de demostración que imita al backend del PV para que el revisor de Apple pueda
usar la app sin una PC local ni SQL Server. Corre gratis en Render.

- `server/`: API de demo (FastAPI y SQLite) y página con el QR de emparejamiento en `/`.
- `server/fixtures/`: datos de ejemplo. Productos, precios, envases y formas de pago son reales.
  Clientes, proveedores, vendedores, usuarios, cuentas y puestos son inventados.
- `tools/`: scripts para regenerar los fixtures desde la base local.

Cubre el flujo de la demo: login, nueva comanda, envío, cobro (pedido o factura), registro
y consulta de vacíos, y los listados "Resumen de Venta" (tabla) y "Stock del puesto" (tarjetas).
El resto de las pantallas responde vacío. No imprime, no sincroniza y no usa Auth v2.

Los datos se reinician cada día (hora de Argentina) y cada vez que Render reinicia el servicio.

## Usuarios

| Usuario    | Contraseña | Rol           |
|------------|------------|---------------|
| `demo`     | `demo1234` | administrador |
| `vendedor` | `demo1234` | vendedor      |

La contraseña se cambia con la variable `DEMO_PASSWORD`.

## Probar en la PC

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt httpx
.\.venv\Scripts\python.exe smoke_test.py
.\.venv\Scripts\python.exe -m uvicorn app:app --port 8000
```

Con el servidor en el puerto 8000, `quasar dev` en `PV-marketsis/Front/` usa `http://localhost:8000/api`,
así que se puede recorrer el flujo en el navegador. La página del QR queda en `http://localhost:8000/`.

## Desplegar en Render (gratis)

1. Crear el repo en GitHub (por ejemplo `marketsisDevs/PV-marketsis-demo`) y hacer push.
2. En [Render](https://dashboard.render.com), ir a **New → Blueprint** y conectar ese repo.
   Render lee `render.yaml` y crea el servicio `marketsis-pv-demo`.
3. Cuando termine, abrir `https://marketsis-pv-demo.onrender.com/` (o la URL que asigne Render).
   Ahí está el QR con esa misma URL.
4. Verificar contra la URL pública:
   `.\.venv\Scripts\python.exe smoke_test.py --url https://marketsis-pv-demo.onrender.com`

## Evitar el arranque lento (opcional, gratis)

El plan gratuito apaga el servicio tras 15 minutos sin uso y tarda unos 50 segundos en despertar.
La app espera 15 segundos al emparejar, así que conviene mantenerlo despierto durante la revisión:
crear un monitor HTTP en [UptimeRobot](https://uptimerobot.com) (gratis) contra
`https://<servicio>.onrender.com/api/health` cada 5 minutos. Un único servicio encendido todo el mes
entra en las 750 horas gratuitas de Render.

## Notas para App Review (App Store Connect → App Review Information)

```
Marketsis PV is a point-of-sale app for produce market stalls. It connects to the
business's own server, which is paired by scanning a QR code.

For review we provide a cloud demo server with sample data:
1. Open https://<servicio>.onrender.com on any computer (the QR image is also attached).
2. In the app, tap "Escanear QR de emparejamiento" and scan the QR code.
3. Sign in with user: demo / password: demo1234

The demo server is on a free plan: if the first connection takes long, wait up to
one minute and scan again. Data is fictitious and resets daily.
Suggested flow: Comandas > Nueva Comanda (create and send an order), Comprobantes >
Pedido (charge it), Vacíos y Envases > Registro de Vacíos, Listados > Resumen de Venta.
```

Adjuntar también `https://<servicio>.onrender.com/qr.png` como imagen en las notas.

## Regenerar los fixtures desde la base local

Necesita el repo `PV-marketsis` clonado al lado de este (o la variable `PV_REPO` con su ruta),
y usa su `Back/config.ini` (conexión `LOCAL_*`) y su venv. El grabador genera un token para el usuario indicado
(por defecto `Mauricio1`), lo que cierra la sesión abierta de ese usuario en el PV.

```powershell
..\PV-marketsis\Back\env\Scripts\python.exe tools\record_raw.py
..\PV-marketsis\Back\env\Scripts\python.exe tools\build_fixtures.py
```

`_raw/` contiene datos reales y no se versiona.

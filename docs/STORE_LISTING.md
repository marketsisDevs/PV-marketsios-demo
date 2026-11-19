# Fichas de tienda — Marketsis-PV (`org.marketsis.pv`)

Textos listos para pegar en App Store Connect y Google Play Console.
Los límites de caracteres de cada campo están indicados entre corchetes.

| Dato | Valor |
|------|-------|
| Política de privacidad | https://marketsisdevs.github.io/PV-marketsios-demo/privacy.html |
| Términos del servicio | https://marketsisdevs.github.io/PV-marketsios-demo/terms.html |
| (legado Render; puede dormir) | https://marketsis-pv-demo.onrender.com/privacy |
| Servidor demo (QR) | https://marketsis-pv-demo.onrender.com |
| Usuario demo | `demo` / `demo1234` |
| Sitio / soporte | https://www.marketsis.com.ar/ |
| Email de contacto | mgonzalez@marketsis.com.ar (cambiable con `DEMO_CONTACT_EMAIL` en Render) |
| Categoría | Business / Empresa |

---

## 1. Textos comunes

**Nombre** [30]: `Marketsis-PV`

**Subtítulo (Apple)** [30]: `Punto de venta mayorista`

**Descripción corta (Google)** [80]:
`Comandas, cobros, envases y listados de tu punto de venta Marketsis en el móvil.`

**Descripción larga** [4000]:

```text
Marketsis-PV es la app móvil del sistema de punto de venta Marketsis para mercados y distribuidoras mayoristas.

Se conecta al servidor Marketsis-PV de tu empresa escaneando un código QR de emparejamiento. Una vez conectada, tu equipo puede:

• Armar comandas: elegir cliente, agregar productos por partida con stock y precio, y enviarlas a caja.
• Cobrar pedidos: seleccionar comandas enviadas, elegir forma de pago y registrar el comprobante.
• Registrar vacíos y envases: cargar la devolución de envases de cada cliente y generar el vale.
• Consultar listados: resumen de venta, stock del puesto y otros reportes en tabla o en fichas.
• Compartir la comanda en PDF.

Requiere un servidor Marketsis-PV de tu empresa. Los usuarios los crea el administrador del sistema; la app no tiene registro público.

Los datos del negocio se guardan en el servidor de tu empresa. La app no tiene publicidad ni seguimiento.
```

**Keywords (Apple)** [100]:
`punto de venta,pos,comandas,mayorista,mercado,envases,vacios,stock,ventas,facturacion,listados`

**Texto promocional (Apple, opcional)** [170]:
`Comandas, cobros, envases y listados del punto de venta Marketsis desde el teléfono, conectado al servidor de tu empresa.`

---

## 2. Notas para el revisor (inglés)

Pegar en **App Store Connect → App Review Information → Notes** y en **Play Console → App content → App access** (opción *All or some functionality is restricted*).

```text
Marketsis-PV is a B2B companion app for the Marketsis point-of-sale system.
Each business runs its own Marketsis-PV server; the app pairs with it by scanning a QR code.
For review we provide a public demo server with fictitious data (reset daily).

How to test:
1. On a computer, open https://marketsis-pv-demo.onrender.com
   (it shows the pairing QR code and these same instructions).
2. Open the app and tap "Escanear QR de emparejamiento" (Scan pairing QR). Scan the QR.
3. Sign in with user: demo / password: demo1234

Suggested walkthrough:
- Comandas > Nueva Comanda: pick a customer, add products, send the order.
- Comprobantes > Pedido: select the sent order and save it (checkout).
- Vacíos y Envases > Registro de Vacíos: register returned containers.
- Listados: "Resumen de Venta" (table) and "Stock del puesto" (cards).

Notes:
- The demo server runs on a free cloud plan. If the first connection takes long, wait up to
  1 minute and scan again.
- User accounts are created by each business administrator; there is no in-app sign-up,
  so in-app account deletion does not apply. Deletion requests are handled by the business
  administrator or via the contact in our privacy policy.
- Printing to thermal printers is disabled in the demo.
```

Credenciales en los campos dedicados: usuario `demo`, contraseña `demo1234`.

---

## 3. Apple — App Privacy y otros formularios

- **App Privacy → Data collection:** *No, we do not collect data from this app.*
  Los datos se envían al servidor propio de cada empresa, no a Marketsis ni a terceros, y no hay analítica ni SDKs de seguimiento.
- **Age rating:** responder *None/No* a todo → **4+**.
- **Export compliance:** ya declarado en `Info.plist` (`ITSAppUsesNonExemptEncryption = NO`).
- **Content rights:** no contiene contenido de terceros.
- **Support URL:** https://www.marketsis.com.ar/ · **Privacy Policy URL:** https://marketsisdevs.github.io/PV-marketsios-demo/privacy.html

---

## 4. Google Play — App content (Policy)

| Sección | Respuesta |
|---------|-----------|
| Privacy policy | https://marketsisdevs.github.io/PV-marketsios-demo/privacy.html |
| Terms of Service (estado operador UE) | https://marketsisdevs.github.io/PV-marketsios-demo/terms.html |
| Ads | No contiene anuncios |
| App access | Restringida → instrucciones y credenciales de la sección 2 |
| Content rating (IARC) | Categoría *Utility, Productivity, Communication or other*; todo *No* → Apto para todos |
| Target audience | 18 y más |
| News app | No |
| Government app | No |
| Financial features | Ninguna |
| Health | No |

**Data safety** (Google cuenta como "recolección" todo dato que sale del dispositivo, aunque vaya al servidor del cliente; por eso se declara):

| Pregunta | Respuesta |
|----------|-----------|
| ¿Recolecta o comparte datos? | Sí, recolecta. No comparte. |
| Tipos | *Personal info → Name* (clientes del negocio) y *User IDs* (usuario de login) · *App activity → Other user-generated content* (comandas, ventas) |
| Procesamiento efímero | No |
| ¿Obligatorio? | Sí (necesario para usar la app) |
| Finalidad | App functionality |
| ¿Cifrado en tránsito? | **No** (en red local el servidor de la empresa puede usar HTTP) |
| ¿El usuario puede pedir la eliminación? | Sí, vía el administrador de su empresa o el email de la política |

Permisos declarados en el manifest: `INTERNET`, `CAMERA` (escaneo de QR).

---

## 5. Recursos gráficos

| Recurso | Apple | Google |
|---------|-------|--------|
| Ícono | 1024×1024 sin transparencia (`Front/src-capacitor/assets/icon-1024.png`) | 512×512 PNG |
| Imagen destacada | — | 1024×500 |
| Capturas | iPhone 6,7" (1290×2796), mínimo 1, ideal 4–6 | Teléfono, mínimo 2 (16:9 o 9:16) |

Sacar las capturas con la app conectada al servidor demo: login, nueva comanda con productos, cobro, registro de vacíos, Resumen de Venta y Stock del puesto en fichas.

"""
Consulta interactiva de facturas EMCALI con reCAPTCHA resuelto por el usuario.

Por qué existe este módulo
--------------------------
El portal de EMCALI valida el reCAPTCHA en su servidor (código TC128), así que
no se puede omitir el token. Y el site key está restringido por dominio
("Localhost is not in the list of supported domains for this site key"), así que
tampoco se puede renderizar el widget dentro de FinSmart.

Lo que queda es lo mismo que hace un servicio como 2captcha: un humano resuelve
el desafío en el dominio real. Aquí ese humano es el propio dueño del contrato:
el backend abre la página de EMCALI en un navegador, intenta el checkbox solo y,
si Google pide el desafío de imágenes, le retransmite el recorte a FinSmart y le
reenvía los clics. Cuando el captcha queda resuelto, la app de Angular dispara
sola la consulta (`resolved(e){ e && this.consultaContrato() }`), de modo que
basta con interceptar la respuesta de /api/open/infocomercial.

El navegador vive entre peticiones HTTP, así que corre en un hilo con su propio
event loop (las sesiones de Playwright no pueden cruzar loops).
"""
from __future__ import annotations

import asyncio
import base64
import os
import random
import re
import threading
import uuid
from datetime import date, datetime, timedelta

PORTAL_URL = "https://pagos.emcali.com.co/pagosweb/checkout"

_TTL = timedelta(minutes=6)

# Perfil de Chrome reutilizado entre consultas: al conservar cookies e historial
# de Google, el reCAPTCHA deja de tratar cada visita como un extraño.
_PERFIL = os.environ.get("EMCALI_PROFILE_DIR", "/var/lib/finsmart/chrome-emcali")


# ── Hilo con event loop propio ───────────────────────────────────────────────

class _BrowserWorker:
    """Mantiene un loop asyncio vivo para que los navegadores sobrevivan entre requests."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, daemon=True,
                                 name="emcali-browser").start()
                self._loop = loop
            return self._loop

    def run(self, coro, timeout: float = 120.0):
        loop = self._ensure()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)


_worker = _BrowserWorker()


def _ensure_display() -> bool:
    return True  # headless siempre; patchright oculta la señal de automatización


# ── Sesiones ─────────────────────────────────────────────────────────────────

class _Sesion:
    def __init__(self, contrato: str, contract_id: int):
        self.id = str(uuid.uuid4())
        self.contrato = contrato
        self.contract_id = contract_id
        self.expira = datetime.utcnow() + _TTL
        self.playwright = None
        self.contexto = None
        self.page = None
        self.respuesta: dict | None = None   # JSON de /api/open/infocomercial

    def viva(self) -> bool:
        return self.expira > datetime.utcnow()


_sesiones: dict[str, _Sesion] = {}


def _purgar() -> None:
    for sid in [s for s, v in _sesiones.items() if not v.viva()]:
        ses = _sesiones.pop(sid, None)
        if ses:
            try:
                _worker.run(_cerrar(ses), timeout=30)
            except Exception:
                pass


# ── Utilidades de página ─────────────────────────────────────────────────────

async def _cerrar(ses: _Sesion) -> None:
    try:
        if ses.contexto:
            await ses.contexto.close()
    except Exception:
        pass
    try:
        if ses.playwright:
            await ses.playwright.stop()
    except Exception:
        pass
    ses.contexto = ses.page = ses.playwright = None


async def _iframe_desafio(page):
    """
    El iframe del desafío de imágenes (bframe), si está visible.

    Se hace scroll antes de medir: la captura de un elemento lo desplaza a la
    vista por su cuenta, así que si la caja se midiera antes, la imagen que ve el
    usuario y las coordenadas donde se hace clic quedarían desalineadas y el
    desafío se rechazaría siempre por muy bien que lo resuelva.
    """
    for marco in page.frames:
        if "bframe" in (marco.url or ""):
            try:
                el = await marco.frame_element()
                if not await el.is_visible():
                    continue
                await el.scroll_into_view_if_needed(timeout=5_000)
                await page.wait_for_timeout(200)
                caja = await el.bounding_box()
                if caja and caja["height"] > 80:
                    return el, caja
            except Exception:
                pass
    return None, None


async def _aceptar_politicas(page) -> bool:
    """
    Marca el check de "políticas de tratamiento de datos personales".

    Es obligatorio aunque no lo parezca: si queda sin marcar, al resolverse el
    captcha la app llama a verificaCampos(), encuentra el error, hace
    reCaptcha.reset() y NO consulta la API. Desde fuera se ve como si el captcha
    no se hubiera pasado nunca.
    """
    try:
        cb = page.locator('input[type="checkbox"]').first
        if await cb.count() == 0 or await cb.is_checked():
            return True
        try:
            await cb.check(timeout=4_000)
        except Exception:
            # PrimeNG envuelve el input real en un div estilizado
            await cb.locator("xpath=..").click(timeout=4_000)
        await page.wait_for_timeout(400)
        return await cb.is_checked()
    except Exception:
        return False


async def _checkbox_marcado(page) -> bool:
    try:
        marco = page.frame_locator('iframe[title="reCAPTCHA"]').first
        return await marco.locator("#recaptcha-anchor").get_attribute("aria-checked") == "true"
    except Exception:
        return False


async def _recorte(page) -> dict | None:
    """Captura el desafío como PNG en base64, con su tamaño para mapear los clics."""
    el, caja = await _iframe_desafio(page)
    if not el or not caja:
        return None
    try:
        png = await el.screenshot(timeout=10_000)
    except Exception:
        return None
    return {
        "imagen": base64.b64encode(png).decode(),
        "ancho": int(caja["width"]),
        "alto": int(caja["height"]),
    }


async def _recorte_estable(page, intentos: int = 6, espera_entre: int = 450) -> dict | None:
    """
    Repite la captura hasta que dos capturas seguidas sean idénticas.

    Cuando se marca una casilla, Google la reemplaza por una imagen nueva que
    llega desde su CDN unos cientos de ms después del clic. Capturar antes de
    que termine de cargar deja el recorte con esa casilla en blanco o a medio
    dibujar: el usuario no ve que apareció nada nuevo, no la marca, y al pulsar
    VERIFICAR el desafío la rechaza pidiendo validar también esas imágenes.
    Esperar a que dos capturas seguidas salgan iguales evita devolver un
    recorte a medio cargar.
    """
    anterior = None
    for _ in range(intentos):
        recorte = await _recorte(page)
        if recorte is None:
            return anterior
        if anterior is not None and recorte["imagen"] == anterior["imagen"]:
            return recorte
        anterior = recorte
        await page.wait_for_timeout(espera_entre)
    return anterior


async def _pulsar_enviar(page) -> bool:
    """Pulsa 'Paga tu factura' si está habilitado."""
    try:
        btn = page.locator('button:has-text("Paga tu factura")').first
        if await btn.count() and await btn.is_enabled():
            await btn.click(timeout=4_000)
            return True
    except Exception:
        pass
    return False


async def _esperar_respuesta(page, segundos: int, ses: _Sesion) -> bool:
    for _ in range(segundos):
        if ses.respuesta is not None:
            return True
        await page.wait_for_timeout(1_000)
    return ses.respuesta is not None


# ── Parseo del payload ───────────────────────────────────────────────────────

_SIN_DEUDA = (
    "no tiene factura", "sin facturas", "no presenta factura", "no registra factura",
    "no posee factura", "al día", "al dia", "sin deuda", "no tiene deuda",
    "no registra deuda", "sin saldo", "no tiene saldo", "no tiene obligacion",
    "no existen factura", "no hay factura", "no se encontraron factura",
    "sin obligaciones", "no tiene pendiente", "no presenta deuda",
)


def _monto(valor) -> float:
    """
    Normaliza valorPagoTotal.

    El portal formatea el monto con el pipe `number:'1.2-2':'es-CO'`, así que la
    API lo entrega como número JSON: hay que usarlo tal cual. Convertirlo a texto
    y quitarle los puntos lo multiplicaba por diez (36494.0 → 364940).

    Si algún día llega como texto, se interpreta al estilo colombiano: el punto
    separa miles salvo que le sigan una o dos cifras al final.
    """
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, bool):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    s = str(valor).strip().replace("$", "").replace(" ", "").replace("\xa0", "")
    if not s:
        return 0.0

    if "," in s and "." in s:                       # el último separador manda
        sep = max(s.rfind(","), s.rfind("."))
        entero = re.sub(r"[^\d-]", "", s[:sep])
        dec = re.sub(r"\D", "", s[sep + 1:])
        s = f"{entero}.{dec}" if dec else entero
    elif re.fullmatch(r"-?\d+[.,]\d{1,2}", s):      # 36494,5 / 36494.50 → decimal
        s = s.replace(",", ".")
    else:                                            # 36.494 / 1.234.567 → miles
        s = re.sub(r"[^\d-]", "", s)

    try:
        return float(s) if s not in ("", "-") else 0.0
    except ValueError:
        return 0.0


def _fecha(payload: dict):
    # `fechaPago` es el campo que el portal muestra como fecha de la factura
    # (confirmado en su bundle); el resto quedan como respaldo por si cambia.
    for clave in ("fechaPago", "fechaVencimiento", "fechaLimitePago",
                  "fechaLimite", "fecha", "fechaCancelacion"):
        crudo = payload.get(clave)
        if not crudo:
            continue
        texto = str(crudo).strip()[:10]
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
    return None


def _resultado(respuesta: dict, contrato: str) -> dict:
    """Traduce la respuesta de EMCALI al formato que consume FinSmart."""
    estado = respuesta.get("status")
    payload = respuesta.get("payload") or {}

    # status 500 = error de negocio; el portal lo muestra y se queda en la
    # primera página. El caso más común es no tener facturas pendientes.
    if estado != 200:
        mensaje = str(payload.get("mensaje") or "").strip()
        if any(p in mensaje.lower() for p in _SIN_DEUDA):
            return {
                "amount": 0.0,
                "due_date": str(date.today() + timedelta(days=30)),
                "reference": f"EMCALI-{contrato}",
                "is_up_to_date": True,
                "mensaje": mensaje,
            }
        return {"error": mensaje or "EMCALI no devolvió información de la factura."}

    monto = _monto(payload.get("valorPagoTotal"))
    if monto <= 0:
        return {
            "amount": 0.0,
            "due_date": str(_fecha(payload) or (date.today() + timedelta(days=30))),
            "reference": f"EMCALI-{contrato}",
            "is_up_to_date": True,
            "mensaje": "El contrato no tiene saldo pendiente.",
        }

    nro = str(payload.get("nroFactura") or payload.get("nroPagoElectronico") or contrato)
    return {
        "amount": monto,
        "due_date": str(_fecha(payload) or (date.today() + timedelta(days=15))),
        "reference": f"EMCALI-{nro}",
        "is_up_to_date": False,
        "direccion": payload.get("direccion") or "",
    }


# ── Flujo ────────────────────────────────────────────────────────────────────

async def _abrir(ses: _Sesion) -> dict:
    from patchright.async_api import async_playwright

    con_display = _ensure_display()
    os.makedirs(_PERFIL, exist_ok=True)
    # Si una sesión anterior no cerró limpio (timeout, proceso matado), el
    # candado de Chrome se queda ahí y bloquea cualquier lanzamiento nuevo con
    # "Opening in existing browser session". Solo una sesión usa este perfil
    # a la vez, así que es seguro limpiarlo antes de abrir.
    for _nombre in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.remove(os.path.join(_PERFIL, _nombre))
        except OSError:
            pass
    ses.playwright = await async_playwright().start()

    # Configuración recomendada por patchright: Chrome real, perfil persistente y
    # CERO personalizaciones. Cada opción que se añade aquí (user agent propio,
    # --disable-blink-features, viewport fijo, parches a navigator.webdriver) es
    # una señal que reCAPTCHA detecta, y patchright ya oculta esas huellas por su
    # cuenta a nivel de CDP. El perfil persistente además acumula cookies de
    # Google entre consultas, que es lo que más sube el puntaje de confianza.
    ses.contexto = await ses.playwright.chromium.launch_persistent_context(
        user_data_dir=_PERFIL,
        headless=True,
        no_viewport=True,
        locale="es-CO",
        timezone_id="America/Bogota",
        # Ventana alta para que el desafío quepa entero y las coords del clic coincidan.
        args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1400,1100"],
    )
    page = ses.contexto.pages[0] if ses.contexto.pages else await ses.contexto.new_page()
    ses.page = page

    async def on_response(r):
        if "infocomercial" in r.url:
            try:
                ses.respuesta = await r.json()
            except Exception:
                pass

    page.on("response", on_response)

    await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(4_000)

    # Número de contrato, tecleado con ritmo humano
    campo = None
    for sel in ('input[placeholder*="123"]', 'input[formcontrolname="contrato"]',
                'input[type="text"]', "input"):
        loc = page.locator(sel).first
        try:
            if await loc.is_visible(timeout=3_000):
                campo = loc
                break
        except Exception:
            continue
    if campo is None:
        raise RuntimeError("No se encontró el campo de contrato en el portal de EMCALI.")

    await campo.click()
    for ch in ses.contrato:
        await page.keyboard.type(ch, delay=random.randint(60, 150))
    await page.wait_for_timeout(random.randint(600, 1_100))

    if not await _aceptar_politicas(page):
        raise RuntimeError(
            "No se pudo aceptar las políticas de tratamiento de datos en el portal "
            "de EMCALI. Es posible que hayan cambiado el formulario."
        )

    # Se probó resolver este reCAPTCHA con 2Captcha, igual que en Claro: llenar
    # el campo oficial `g-recaptcha-response` con un token real, sin tocar el
    # JS del widget (ver services/twocaptcha.py). El botón "Paga tu factura"
    # sí quedó habilitado y el clic funcionó, pero la app de Angular nunca
    # llamó a /api/open/infocomercial — a diferencia del formulario plano de
    # Claro, esta integración de Angular solo confía en su propio estado
    # interno (el que actualiza el callback `resolved()` cuando el widget
    # completa su flujo real), no en releer el campo del DOM al enviar. La
    # única forma de que sí confíe en el token sería invocar ese callback
    # directamente — la misma técnica de "enganchar el JS del widget" que ya
    # quedó descartada con Cloudflare Turnstile — así que se mantiene el flujo
    # original: clic automático del checkbox y, si Google exige el desafío de
    # imágenes, retransmitírselo al usuario.

    # Intento automático del checkbox: a veces Google lo da por bueno sin desafío
    try:
        await page.wait_for_selector('iframe[title="reCAPTCHA"]', timeout=15_000)
        marco = page.frame_locator('iframe[title="reCAPTCHA"]').first
        ancla = marco.locator("#recaptcha-anchor")
        await ancla.wait_for(state="visible", timeout=10_000)
        await page.wait_for_timeout(random.randint(600, 1_200))
        await ancla.hover()
        await page.wait_for_timeout(random.randint(200, 500))
        await ancla.click()
    except Exception as exc:
        raise RuntimeError(f"El portal de EMCALI no cargó el reCAPTCHA: {exc}")

    for _ in range(8):
        await page.wait_for_timeout(1_000)
        if await _checkbox_marcado(page):
            break

    return await _estado_actual(ses, espera_api=18)


async def _estado_actual(ses: _Sesion, espera_api: int = 3) -> dict:
    page = ses.page

    def listo() -> dict:
        return {"estado": "listo", "resultado": _resultado(ses.respuesta, ses.contrato)}

    # Si el portal ya contestó, da igual cómo haya quedado el widget.
    if ses.respuesta is not None:
        return listo()

    if await _checkbox_marcado(page):
        await _esperar_respuesta(page, espera_api, ses)
        if ses.respuesta is None:
            # La app suele enviar sola al resolverse el captcha; si no lo hizo,
            # se pulsa el botón, que ya debería estar habilitado.
            if await _pulsar_enviar(page):
                await _esperar_respuesta(page, 10, ses)
        return listo() if ses.respuesta is not None else {
            "estado": "consultando", "session_id": ses.id}

    recorte = await _recorte_estable(page)
    if recorte:
        return {"estado": "desafio", "session_id": ses.id, **recorte}

    # Ni checkbox marcado ni desafío a la vista: es lo que ocurre cuando la
    # consulta terminó y el portal reseteó el captcha (lo hace en cada respuesta
    # de error, incluida la de "no tiene facturas pendientes"). La respuesta
    # viene en camino, así que conviene esperarla en vez de rendirse.
    await _esperar_respuesta(page, min(espera_api, 8), ses)
    return listo() if ses.respuesta is not None else {
        "estado": "consultando", "session_id": ses.id}


async def _clic(ses: _Sesion, x: float, y: float) -> dict:
    """Reenvía un clic al desafío. x/y son proporciones 0..1 sobre el recorte."""
    page = ses.page
    el, caja = await _iframe_desafio(page)
    if not el or not caja:
        return await _estado_actual(ses, espera_api=10)

    px = caja["x"] + max(0.0, min(1.0, x)) * caja["width"]
    py = caja["y"] + max(0.0, min(1.0, y)) * caja["height"]
    await page.mouse.move(px, py, steps=random.randint(4, 9))
    await page.wait_for_timeout(random.randint(90, 220))
    await page.mouse.click(px, py)
    await page.wait_for_timeout(500)

    return await _estado_actual(ses, espera_api=12)


# ── API pública (síncrona, para llamar con run_in_threadpool) ────────────────

def iniciar(contrato: str, contract_id: int) -> dict:
    _purgar()
    # Chrome bloquea el perfil, así que solo puede haber una consulta a la vez.
    for otra in list(_sesiones):
        cerrar(otra)

    ses = _Sesion(contrato, contract_id)
    _sesiones[ses.id] = ses
    try:
        estado = _worker.run(_abrir(ses), timeout=180)
    except Exception:
        cerrar(ses.id)
        raise
    if estado.get("estado") == "listo":
        cerrar(ses.id)
    return estado


def clic(session_id: str, x: float, y: float) -> dict:
    ses = _sesiones.get(session_id)
    if not ses or not ses.viva() or not ses.page:
        raise KeyError("sesión expirada")
    estado = _worker.run(_clic(ses, x, y), timeout=120)
    if estado.get("estado") == "listo":
        cerrar(session_id)
    return estado


def estado(session_id: str) -> dict:
    ses = _sesiones.get(session_id)
    if not ses or not ses.viva() or not ses.page:
        raise KeyError("sesión expirada")
    resultado = _worker.run(_estado_actual(ses, espera_api=10), timeout=120)
    if resultado.get("estado") == "listo":
        cerrar(session_id)
    return resultado


def cerrar(session_id: str) -> None:
    ses = _sesiones.pop(session_id, None)
    if ses:
        try:
            _worker.run(_cerrar(ses), timeout=30)
        except Exception:
            pass

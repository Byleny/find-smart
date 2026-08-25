import asyncio
import json
import os
import random
import re
import threading
import uuid
import concurrent.futures
from datetime import date, timedelta, datetime
from dataclasses import dataclass, field
from typing import Optional

class CredentialsError(ValueError):
    """
    El portal rechazó el correo/cédula del titular del contrato.
    Es un problema de datos del usuario, no una falla del portal, así que la API
    lo traduce a 422 y no a 502.
    """


# ── PSE session cache (in-memory, TTL 10 min) ─────────────────────────────────
_pse_sessions: dict[str, dict] = {}

def create_pse_session(jwt: str, contract_id: int, amount: int) -> str:
    session_id = str(uuid.uuid4())
    _pse_sessions[session_id] = {
        "jwt": jwt,
        "contract_id": contract_id,
        "amount": amount,
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }
    return session_id

def get_pse_session(session_id: str) -> dict | None:
    s = _pse_sessions.get(session_id)
    if s and s["expires_at"] > datetime.utcnow():
        return s
    _pse_sessions.pop(session_id, None)
    return None


@dataclass
class ScraperResult:
    amount: float
    due_date: date
    reference: str
    provider: str
    payment_url: str = ""
    is_demo: bool = False
    is_up_to_date: bool = False
    portal_blocked: bool = False
    blocked_reason: str = ""  # descripción del paso donde falló


# ── Helpers ──────────────────────────────────────────────────────────────────

_UP_TO_DATE_PATTERNS = [
    'al día', 'al dia', 'no tiene factura', 'sin deuda', 'sin saldo pendiente',
    'no registra deuda', 'no tiene saldo', 'cuenta al dia', 'no tiene obligacion',
    'no tiene facturas pendientes', 'no hay facturas', 'no adeuda', 'no hay deuda',
    'al corriente', 'no existen facturas', 'no presenta deuda', 'saldo cero',
    'no tiene cargo', 'no posee deuda', 'no tiene valores pendientes',
    'no se encontraron facturas', 'está al día', 'esta al dia',
    # Mensaje específico del portal GDO
    'cliente sin deuda', 'error cliente sin deuda',
]


def _is_up_to_date(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _UP_TO_DATE_PATTERNS)


def _parse_cop_amounts(text: str) -> list[float]:
    """Extrae montos COP >= $5.000 del texto. Soporta $1.234.567 y $1,234,567."""
    amounts = []
    for m in re.finditer(r'\$\s*([\d]{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?)', text):
        raw = m.group(1).replace('.', '').replace(',', '')
        try:
            v = float(raw)
            if v >= 5_000:
                amounts.append(v)
        except ValueError:
            pass
    return amounts


def _parse_date(text: str) -> Optional[date]:
    """Devuelve la primera fecha futura encontrada en el texto."""
    today = date.today()
    for pattern, fmts in [
        (r'(\d{1,2}/\d{1,2}/\d{4})', ['%d/%m/%Y', '%m/%d/%Y']),
        (r'(\d{1,2}-\d{1,2}-\d{4})', ['%d-%m-%Y']),
        (r'(\d{4}-\d{2}-\d{2})',      ['%Y-%m-%d']),
    ]:
        for m in re.finditer(pattern, text):
            for fmt in fmts:
                try:
                    d = datetime.strptime(m.group(1), fmt).date()
                    if d >= today:
                        return d
                except ValueError:
                    pass
    return None


def _extract_from_api_blob(blob) -> tuple[Optional[float], Optional[date]]:
    """Extrae monto y fecha de un dict/list JSON genérico (API response)."""
    amount: Optional[float] = None
    due: Optional[date] = None

    if isinstance(blob, list):
        for item in blob:
            a, d = _extract_from_api_blob(item)
            if a and a > (amount or 0):
                amount = a
            if d:
                due = d
        return amount, due

    if not isinstance(blob, dict):
        return None, None

    amount_keys = ['valorTotal', 'valor', 'amount', 'totalAmount', 'totalAPagar',
                   'saldo', 'valFactura', 'monto', 'valorAPagar', 'totalFactura']
    date_keys   = ['fechaVencimiento', 'dueDate', 'fechaLimite', 'fechaPago',
                   'vencimiento', 'expiration', 'fechaCancelacion']

    for k in amount_keys:
        v = blob.get(k)
        if v is not None:
            try:
                candidate = float(str(v).replace(',', '').replace('.', '').rstrip('0') or '0')
                # handle COP format: 85000 COP vs 85.00 USD
                if candidate < 100 and '.' in str(v):
                    candidate = float(str(v).replace(',', ''))
                if candidate >= 5_000:
                    amount = candidate
                    break
            except (ValueError, TypeError):
                pass

    for k in date_keys:
        v = blob.get(k)
        if v:
            d = _parse_date(str(v))
            if d:
                due = d
                break

    # Recursively search nested dicts
    for v in blob.values():
        if isinstance(v, (dict, list)):
            a, d = _extract_from_api_blob(v)
            if a and a > (amount or 0):
                amount = a
            if d and not due:
                due = d

    return amount, due


# ── Base classes ──────────────────────────────────────────────────────────────

class BaseScraper:
    is_demo: bool = False

    def fetch_invoice(self, account_reference: str, user_data: dict | None = None) -> ScraperResult:
        raise NotImplementedError


class PlaywrightScraper(BaseScraper):
    """Corre Playwright en un ThreadPoolExecutor para no bloquear el event loop de FastAPI."""
    is_demo = False

    def fetch_invoice(self, account_reference: str, user_data: dict | None = None) -> ScraperResult:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self._fetch(account_reference, user_data or {})).result(timeout=150)

    async def _fetch(self, account_reference: str, user_data: dict) -> ScraperResult:
        raise NotImplementedError

    @staticmethod
    async def _launch_browser(playwright):
        return await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                # Ocultar señales de automatización
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1280,800",
            ],
        )

    @staticmethod
    async def _new_ctx(browser):
        return await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-CO",
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            color_scheme="light",
        )

    @staticmethod
    async def _new_page(ctx):
        """Crea una página. Aplica playwright-stealth si está disponible."""
        page = await ctx.new_page()
        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
        except ImportError:
            # playwright-stealth no instalado: aplicar parche mínimo manual
            await ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['es-CO', 'es', 'en'] });
                window.chrome = { runtime: {} };
            """)
        return page

    @staticmethod
    async def _fill_first(ctx, selectors: list[str], value: str) -> bool:
        """ctx puede ser Page o Frame."""
        for sel in selectors:
            try:
                el = ctx.locator(sel).first
                if await el.is_visible(timeout=2_000):
                    await el.clear()
                    await el.fill(value)
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    async def _click_first(ctx, selectors: list[str]) -> bool:
        """ctx puede ser Page o Frame."""
        for sel in selectors:
            try:
                el = ctx.locator(sel).first
                if await el.is_visible(timeout=2_000):
                    await el.click()
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    async def _find_frame_with_input(page) -> object:
        """
        Devuelve el Frame que contiene un input visible.
        Si el formulario está en un iframe (frameworks Java/Wicket), esto lo detecta.
        Prueba el frame principal primero, luego cada sub-frame.
        """
        # Frame principal
        try:
            if await page.locator('input').count() > 0:
                return page
        except Exception:
            pass

        # Sub-frames (iframes)
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                cnt = await frame.locator('input').count()
                if cnt > 0:
                    return frame
            except Exception:
                pass

        return page  # fallback al frame principal


# ── EMCALI ────────────────────────────────────────────────────────────────────

class EMCALIScraper(BaseScraper):
    """
    EMCALI no admite consulta desatendida.

    Su API valida el reCAPTCHA en el servidor (código TC128) y el site key está
    restringido por dominio, así que no se puede resolver ni omitir desde aquí.
    Automatizar el checkbox tampoco sirve: desde un contenedor Google responde
    siempre con el desafío de imágenes.

    La consulta real vive en services/emcali_captcha.py, que abre el portal en un
    navegador y le retransmite el desafío al usuario (endpoints /emcali-start y
    /emcali-click). Este scraper solo existe para responder rápido y sin gastar
    ~40 s en un intento condenado cuando algo llega por la vía genérica /fetch.
    """
    PORTAL_URL  = "https://pagos.emcali.com.co/pagosweb/checkout"
    PAYMENT_URL = "https://pagos.emcali.com.co/pagosweb/checkout"

    def fetch_invoice(self, account_reference: str, user_data: dict | None = None) -> ScraperResult:
        return ScraperResult(
            amount=0, due_date=date.today() + timedelta(days=15),
            reference=f"EMCALI-{account_reference}",
            provider="emcali", payment_url=self.PAYMENT_URL,
            portal_blocked=True,
            blocked_reason=(
                "EMCALI pide resolver un reCAPTCHA para consultar la factura. "
                "Usa el botón 'Consultar factura' en la sección Facturas: FinSmart "
                "te muestra el desafío y sigue con la consulta cuando lo resuelvas."
            ),
        )


# ── EPM ───────────────────────────────────────────────────────────────────────

class EPMScraper(PlaywrightScraper):
    """
    Consulta facturas EPM (Empresas Públicas de Medellín).
    Referencia: número de cuenta EPM.
    """
    PAYMENT_URL = "https://www.epm.com.co/site/home/personas/factura.aspx"

    async def _fetch(self, account_reference: str, user_data: dict) -> ScraperResult:
        from patchright.async_api import async_playwright
        from bs4 import BeautifulSoup

        api_hits: list[tuple[str, object]] = []

        async def on_response(response):
            url = response.url.lower()
            if any(kw in url for kw in ('factura', 'bill', 'invoice', 'saldo', 'pago', 'deuda')):
                try:
                    if 'json' in response.headers.get('content-type', ''):
                        api_hits.append((response.url, await response.json()))
                except Exception:
                    pass

        async with async_playwright() as p:
            browser = await self._launch_browser(p)
            ctx     = await self._new_ctx(browser)
            page    = await self._new_page(ctx)
            page.on('response', on_response)

            try:
                await page.goto(self.PAYMENT_URL, wait_until='domcontentloaded', timeout=30_000)
                await page.wait_for_timeout(2_000)

                filled = await self._fill_first(page, [
                    'input[id*="uenta"]', 'input[name*="uenta"]',
                    'input[placeholder*="uenta"]', 'input[placeholder*="ontrato"]',
                    'input[type="text"]:visible',
                ], account_reference)

                if not filled:
                    raise RuntimeError(
                        "No se encontró el campo de cuenta en el portal EPM."
                    )

                await self._click_first(page, [
                    'button[type="submit"]', 'button:has-text("Consultar")',
                    'button:has-text("Buscar")', 'input[type="submit"]',
                ])

                await page.wait_for_timeout(4_000)
                try:
                    await page.wait_for_load_state('networkidle', timeout=12_000)
                except Exception:
                    pass

                for _url, data in reversed(api_hits):
                    amount, due = _extract_from_api_blob(data)
                    if amount and amount >= 5_000:
                        due = due or (date.today() + timedelta(days=15))
                        return ScraperResult(
                            amount=amount, due_date=due,
                            reference=f"EPM-{account_reference}-{due.strftime('%Y%m')}",
                            provider='epm', payment_url=self.PAYMENT_URL,
                        )

                soup    = BeautifulSoup(await page.content(), 'html.parser')
                text_epm = soup.get_text(' ', strip=True)

                if _is_up_to_date(text_epm):
                    due = date.today() + timedelta(days=30)
                    return ScraperResult(
                        amount=0, due_date=due,
                        reference=f"EPM-{account_reference}",
                        provider='epm', payment_url=self.PAYMENT_URL,
                        is_up_to_date=True,
                    )

                amounts = _parse_cop_amounts(text_epm)
                if not amounts:
                    raise RuntimeError(f"No se encontró factura EPM para la cuenta '{account_reference}'.")

                amount = max(amounts)
                due    = _parse_date(text_epm) or (date.today() + timedelta(days=15))
                return ScraperResult(
                    amount=amount, due_date=due,
                    reference=f"EPM-{account_reference}-{due.strftime('%Y%m')}",
                    provider='epm', payment_url=self.PAYMENT_URL,
                )
            finally:
                await browser.close()


# ── Codensa ───────────────────────────────────────────────────────────────────

class CodensaScraper(PlaywrightScraper):
    PAYMENT_URL = "https://www.enelcol.com.co/enelcol/personas/servicios-en-linea/consulta-de-factura.html"

    async def _fetch(self, account_reference: str, user_data: dict) -> ScraperResult:
        from patchright.async_api import async_playwright
        from bs4 import BeautifulSoup

        async with async_playwright() as p:
            browser = await self._launch_browser(p)
            ctx     = await self._new_ctx(browser)
            page    = await self._new_page(ctx)

            try:
                await page.goto(self.PAYMENT_URL, wait_until='domcontentloaded', timeout=30_000)
                await page.wait_for_timeout(2_000)

                filled = await self._fill_first(page, [
                    'input[name*="uenta"]', 'input[id*="uenta"]',
                    'input[placeholder*="uenta"]', 'input[type="text"]:visible',
                ], account_reference)

                if not filled:
                    raise RuntimeError("No se encontró el campo de cuenta en el portal Codensa/Enel.")

                await self._click_first(page, [
                    'button[type="submit"]', 'button:has-text("Consultar")',
                    'button:has-text("Buscar")', 'input[type="submit"]',
                ])

                await page.wait_for_timeout(4_000)
                try:
                    await page.wait_for_load_state('networkidle', timeout=12_000)
                except Exception:
                    pass

                soup    = BeautifulSoup(await page.content(), 'html.parser')
                text_cod = soup.get_text(' ', strip=True)

                if _is_up_to_date(text_cod):
                    due = date.today() + timedelta(days=30)
                    return ScraperResult(
                        amount=0, due_date=due,
                        reference=f"CODENSA-{account_reference}",
                        provider='codensa', payment_url=self.PAYMENT_URL,
                        is_up_to_date=True,
                    )

                amounts = _parse_cop_amounts(text_cod)
                if not amounts:
                    raise RuntimeError(f"No se encontró factura Codensa para la cuenta '{account_reference}'.")

                amount = max(amounts)
                due    = _parse_date(text_cod) or (date.today() + timedelta(days=15))
                return ScraperResult(
                    amount=amount, due_date=due,
                    reference=f"CODENSA-{account_reference}-{due.strftime('%Y%m')}",
                    provider='codensa', payment_url=self.PAYMENT_URL,
                )
            finally:
                await browser.close()


# ── Movistar ─────────────────────────────────────────────────────────────────

# Indicativo telefónico por ciudad, tal como los lista el portal. Para el
# identificador "número de línea", la referencia es indicativo + los 7 dígitos.
MOVISTAR_CIUDADES: dict[str, str] = {
    "Bogotá": "601", "Medellín": "604", "Cali": "602", "Barranquilla": "605",
    "Bucaramanga": "607", "Pereira": "606", "Cartagena": "605", "Palmira": "602",
    "Manizales": "606", "Cúcuta": "607", "Montería": "604", "Sincelejo": "605",
    "Buga": "602", "Tuluá": "602", "Armenia": "606", "Ibagué": "608",
    "Neiva": "608", "Villavicencio": "608", "Popayán": "602", "Pasto": "602",
    "Santa Marta": "605", "Valledupar": "605", "Tunja": "608",
}


def _limpiar_lock_perfil(perfil: str) -> None:
    """
    Borra el candado de Chrome (SingletonLock/SingletonSocket/SingletonCookie)
    antes de lanzar el navegador. Se llama SIEMPRE bajo `_lock_perfil()`, así
    que si el candado sigue ahí es de una sesión anterior que no cerró limpio
    (timeout, proceso matado) — nunca de una consulta realmente concurrente,
    porque esa ya está esperando el lock de Python. Sin esto, Playwright
    falla con "Opening in existing browser session" y no hay forma de
    recuperarse sin entrar al contenedor a borrarlo a mano.
    """
    for nombre in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.remove(os.path.join(perfil, nombre))
        except FileNotFoundError:
            pass
        except OSError:
            pass


_locks_perfil: dict[str, threading.Lock] = {}
_locks_perfil_mutex = threading.Lock()


def _lock_perfil(perfil: str) -> threading.Lock:
    """
    Un candado de Python por directorio de perfil de Chrome. El candado de
    archivo de Chrome (SingletonLock) solo detecta la concurrencia después
    del hecho (o falla, o se corrompe el perfil); este candado la evita desde
    antes, poniendo en cola cualquier segunda consulta al mismo proveedor en
    vez de dejarlas competir por el mismo perfil.
    """
    with _locks_perfil_mutex:
        if perfil not in _locks_perfil:
            _locks_perfil[perfil] = threading.Lock()
        return _locks_perfil[perfil]


def _mensaje_legible(mensaje) -> str:
    """
    El campo `message` a veces trae un JSON crudo incrustado como texto, ej.
    'Error REST: {"result":{"details":{"messageLegacy":"El suscriptor no
    existe."}}}'. Se intenta extraer ese texto legible; si no hay JSON o no
    trae el campo esperado, se devuelve el mensaje tal cual llegó.
    """
    if not mensaje or not isinstance(mensaje, str):
        return ""
    inicio = mensaje.find("{")
    if inicio == -1:
        return mensaje
    try:
        datos = json.loads(mensaje[inicio:])
    except (ValueError, TypeError):
        return mensaje
    detalles = (datos.get("result") or {}).get("details") or {}
    return (
        detalles.get("messageLegacy") or detalles.get("message")
        or (datos.get("result") or {}).get("message") or mensaje
    )


class MovistarScraper(PlaywrightScraper):
    """
    Consulta facturas de Movistar en payment.movistar.co.

    El portal protege la consulta con reCAPTCHA v3 y la valida en su servidor
    (llamarla por HTTP directo devuelve 500 con cualquier token falso). Como v3
    es invisible —no hay desafío que resolver— basta con abrir la página en un
    navegador real: el token se obtiene solo y la consulta corre sin que el
    usuario intervenga. Solo se intercepta la respuesta de /api/data-payment.

    Su respuesta distingue el "al día" con un código propio, sin ambigüedad:
        error 204 → "No hay deudas activas."
        error 0   → factura en `values`
    """
    PORTAL_URL  = "https://payment.movistar.co/"
    PAYMENT_URL = "https://payment.movistar.co/"

    # Overridables por subclase (ver MovistarMovilScraper más abajo)
    TAB_LABEL       = "Internet"   # pestaña del portal: servicio fijo/hogar
    PROVIDER_ID     = "movistar"
    REF_PREFIX      = "MOVISTAR"
    PROFILE_ENV     = "MOVISTAR_PROFILE_DIR"
    PROFILE_DEFAULT = "/var/lib/finsmart/chrome-movistar"

    def fetch_invoice(self, account_reference: str, user_data: dict | None = None) -> ScraperResult:
        # El perfil de Chrome de este proveedor es compartido entre TODOS los
        # usuarios (no hay uno por usuario); sin este candado, dos consultas
        # simultáneas al mismo proveedor competían por el mismo perfil —
        # Playwright podía fallar a mitad de camino o corromper el perfil en
        # vez de simplemente esperar su turno.
        perfil = os.environ.get(self.PROFILE_ENV, self.PROFILE_DEFAULT)
        with _lock_perfil(perfil):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run, self._fetch(account_reference, user_data or {})
                ).result(timeout=240)

    # Mensajes que indican un fallo probablemente transitorio (reCAPTCHA v3
    # puntuó bajo esa sesión, o el portal no respondió a tiempo) — vale la
    # pena reintentar con un contexto de navegador nuevo. Un mensaje de negocio
    # real (ej. "El suscriptor no existe.") ya es una respuesta final: no se
    # reintenta, porque no va a cambiar y solo gasta cupo con el portal real.
    _MENSAJES_REINTENTABLES = (
        "no pudo entregar la factura ahora mismo",
        "no respondió a la consulta",
    )

    async def _fetch(self, account_reference: str, user_data: dict) -> ScraperResult:
        intentos = 2
        resultado: ScraperResult | None = None
        for intento in range(1, intentos + 1):
            resultado = await self._un_intento(account_reference, user_data)
            reintentable = resultado.portal_blocked and any(
                m in (resultado.blocked_reason or "") for m in self._MENSAJES_REINTENTABLES
            )
            if not reintentable:
                return resultado
            print(f"[movistar] intento {intento}/{intentos} bloqueado (probable reCAPTCHA), "
                  f"{'reintentando' if intento < intentos else 'sin más intentos'}: {resultado.blocked_reason}")
        return resultado

    async def _un_intento(self, account_reference: str, user_data: dict) -> ScraperResult:
        import os
        from patchright.async_api import async_playwright

        # '1' número de línea (por defecto), '2' referencia de pago
        tipo = str(user_data.get("payment_identifier") or "1")
        etiqueta = "Con número de línea" if tipo == "1" else "Con referencia de pago"

        def _blocked(reason: str) -> ScraperResult:
            return ScraperResult(
                amount=0, due_date=date.today() + timedelta(days=15),
                reference=f"{self.REF_PREFIX}-{account_reference}", provider=self.PROVIDER_ID,
                payment_url=self.PAYMENT_URL,
                portal_blocked=True, blocked_reason=reason,
            )

        perfil = os.environ.get(self.PROFILE_ENV, self.PROFILE_DEFAULT)
        os.makedirs(perfil, exist_ok=True)
        _limpiar_lock_perfil(perfil)

        respuesta: dict | None = None

        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=perfil,
                headless=True,
                no_viewport=True, locale="es-CO", timezone_id="America/Bogota",
                args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1500,1100"],
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            def on_request(req):
                if "/api/data-payment" in req.url:
                    print(f"[movistar] request headers: {dict(req.headers)!r}")
                    print(f"[movistar] request body: {req.post_data!r}")

            async def on_response(r):
                nonlocal respuesta
                if "/api/data-payment" in r.url:
                    print(f"[movistar] {r.request.method} {r.url} -> HTTP {r.status}")
                    try:
                        respuesta = await r.json()
                    except Exception as exc:
                        print(f"[movistar] no se pudo leer el body como JSON: {exc}")

            page.on("request", on_request)
            page.on("response", lambda r: asyncio.create_task(on_response(r)))

            try:
                await page.goto(self.PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(6_000)

                # Recorrido "humano" antes de tocar el formulario: reCAPTCHA v3 puntúa
                # la sesión completa, y una pestaña recién abierta que solo escribe
                # sin ningún movimiento previo de mouse/scroll es en sí misma una
                # señal de bot. No garantiza nada, pero ayuda al puntaje.
                try:
                    await page.mouse.move(random.randint(200, 700), random.randint(150, 500), steps=10)
                    await page.wait_for_timeout(random.randint(400, 900))
                    await page.mouse.wheel(0, random.randint(100, 250))
                    await page.wait_for_timeout(random.randint(500, 1_000))
                    await page.mouse.move(random.randint(300, 900), random.randint(200, 600), steps=8)
                    await page.wait_for_timeout(random.randint(300, 700))
                except Exception:
                    pass

                BOTONES_A_EVITAR = {
                    "continuar", "pagar", "agregar otra factura",
                    "activar o actualizar tu pago automático",
                    "eliminar factura de mi lista",
                    # Pestañas: nunca deben tocarse buscando otra cosa, o se
                    # revierte la pestaña ya activada arriba.
                    "pospago", "internet",
                }

                async def elegir(texto: str) -> bool:
                    """
                    Elige una opción por texto. Prueba primero un <select> nativo;
                    si no hay ninguno con esa opción, el campo es un combobox
                    personalizado (así es "Identificador de pago" en el portal real:
                    no es un <select>), así que se abre cada disparador visible y se
                    busca una opción con el texto pedido, evitando los botones de
                    acción conocidos para no enviar el formulario antes de tiempo.
                    """
                    sels = page.locator("select")
                    for i in range(await sels.count()):
                        el = sels.nth(i)
                        try:
                            if not await el.is_visible():
                                continue
                            ops = await el.locator("option").all_text_contents()
                            iguales = [o for o in ops if o.strip().lower() == texto.lower()]
                            parecidas = [o for o in ops if texto.lower() in o.lower()]
                            elegida = (iguales or parecidas)
                            if elegida:
                                await el.select_option(label=elegida[0])
                                await page.wait_for_timeout(1_500)
                                return True
                        except Exception:
                            continue

                    # Tope y tiempos recortados: el combo correcto casi siempre
                    # está entre los primeros candidatos, y agotar los 20 con
                    # espera larga por candidato equivocado sumaba hasta ~40s
                    # extra por consulta cuando no coincidía rápido.
                    disparadores = page.locator('[role="combobox"], [aria-haspopup="listbox"], button, [role="button"]')
                    for i in range(min(await disparadores.count(), 10)):
                        trigger = disparadores.nth(i)
                        try:
                            if not await trigger.is_visible(timeout=300):
                                continue
                            texto_boton = (await trigger.text_content() or "").strip().lower()
                            if texto_boton in BOTONES_A_EVITAR:
                                continue
                            await trigger.click(timeout=1_000)
                            await page.wait_for_timeout(300)
                        except Exception:
                            continue

                        try:
                            candidata = page.get_by_text(texto, exact=False).last
                            if await candidata.is_visible(timeout=600):
                                await candidata.click(timeout=1_000)
                                await page.wait_for_timeout(700)
                                return True
                        except Exception:
                            pass

                        try:
                            await page.keyboard.press("Escape")
                        except Exception:
                            pass
                    return False

                # Pestaña del portal (subclases eligen otra vía TAB_LABEL: "Internet"
                # es el servicio fijo/hogar, "Pospago" la línea móvil). El campo
                # "Ciudad" solo existe en la pestaña Internet, así que sirve para
                # verificar cuál quedó activa: el clic por texto no siempre
                # "agarra" a la primera (puede caer en el icono o en un nodo
                # sin el listener), así que se reintenta con force si no cambió.
                async def _pestana_correcta() -> bool:
                    # Si el formulario todavía no terminó de montar, "Ciudad"
                    # tampoco es visible en NINGUNA pestaña — eso se veía
                    # igual que "ya estamos en Pospago" y daba por buena una
                    # página a medio cargar. Esperar primero a que
                    # "Identificador de pago" exista evita ese falso positivo.
                    try:
                        await page.locator('text="Identificador de pago"').first.wait_for(state="visible", timeout=5_000)
                    except Exception:
                        pass
                    try:
                        ciudad_visible = await page.locator('text="Ciudad"').first.is_visible(timeout=1_500)
                    except Exception:
                        ciudad_visible = False
                    return ciudad_visible == (self.TAB_LABEL == "Internet")

                pestana_ok = await _pestana_correcta()
                intentos = 0
                while not pestana_ok and intentos < 3:
                    try:
                        tab = page.get_by_text(self.TAB_LABEL, exact=False).first
                        await tab.click(force=(intentos > 0), timeout=4_000)
                        await page.wait_for_timeout(2_000)
                    except Exception:
                        pass
                    pestana_ok = await _pestana_correcta()
                    intentos += 1
                if not pestana_ok:
                    print(f"[movistar] no se pudo activar la pestaña '{self.TAB_LABEL}' tras {intentos} intentos")

                # El selector de operador solo existe en la pestaña Internet
                # (línea fija); en Pospago no hay tal campo, y buscarlo igual
                # agotaba hasta 20 intentos de fuerza bruta por nada (~1 min
                # perdido en cada consulta de Movistar Móvil).
                if self.TAB_LABEL != "Pospago":
                    await elegir("Movistar")
                if not await elegir(etiqueta):
                    print(f"[movistar] pestana_ok antes de fallar etiqueta: {pestana_ok} (tab_label={self.TAB_LABEL})")
                    try:
                        await page.screenshot(path="/tmp/movistar_debug_etiqueta.png", full_page=True)
                    except Exception:
                        pass
                    return _blocked(
                        f"El portal de Movistar no ofrece la opción '{etiqueta}'. "
                        "Puede que hayan cambiado el formulario."
                    )

                if tipo == "1":
                    resuelto = await self._resolver_numero_linea(page, elegir, account_reference, _blocked)
                    if isinstance(resuelto, ScraperResult):
                        return resuelto
                    valor, selectores = resuelto
                else:
                    valor = re.sub(r"\D", "", account_reference)
                    selectores = ('input[name="referenceNumber"]',
                                  'input[data-testid="integer-field"]')

                campo = None
                for sel in selectores:
                    loc = page.locator(sel).first
                    try:
                        if await loc.count() and await loc.is_visible():
                            campo = loc
                            break
                    except Exception:
                        continue
                if campo is None:   # último recurso: primer input visible
                    todos = page.locator("input")
                    for i in range(await todos.count()):
                        el = todos.nth(i)
                        if await el.is_visible():
                            campo = el
                            break
                if campo is None:
                    return _blocked("No se encontró el campo del número en el portal de Movistar.")

                await campo.click()
                for ch in valor:
                    await page.keyboard.type(ch, delay=random.randint(70, 150))
                await page.wait_for_timeout(1_200)

                try:
                    await page.screenshot(path="/tmp/movistar_debug_antes.png", full_page=True)
                except Exception:
                    pass

                btn = page.locator('button:has-text("Continuar")').first
                if not await btn.is_enabled():
                    return _blocked(
                        "El portal no habilitó el botón de consulta; revisa que el "
                        "número tenga el formato correcto."
                    )
                await btn.click()

                for _ in range(35):
                    await page.wait_for_timeout(1_000)
                    if respuesta is not None:
                        break

                if respuesta is None:
                    try:
                        await page.screenshot(path="/tmp/movistar_debug_sin_respuesta.png", full_page=True)
                    except Exception:
                        pass
                    return _blocked(
                        "Movistar no respondió a la consulta. Es posible que su "
                        "verificación de seguridad la haya rechazado; intenta más tarde."
                    )

                print(f"[movistar] /api/data-payment crudo: {respuesta!r}")
                try:
                    await page.screenshot(path="/tmp/movistar_debug.png", full_page=True)
                except Exception:
                    pass

                return self._parsear(respuesta, account_reference)

            finally:
                await ctx.close()

    async def _resolver_numero_linea(self, page, elegir, account_reference: str, blocked):
        """
        Resuelve (valor, selectores) para el tipo '1' (número de línea).

        Comportamiento por defecto: línea fija/hogar (pestaña "Internet") — el
        portal pide indicativo de ciudad (3 dígitos) + línea (7 dígitos), y hay
        que elegir la ciudad en un <select> antes de escribir el número.
        MovistarMovilScraper lo sobreescribe: un celular colombiano no lleva
        indicativo, así que ahí no hace falta elegir ciudad.
        """
        ref = re.sub(r"\D", "", account_reference)
        if len(ref) < 10:
            return blocked(
                "Falta la ciudad de este servicio: Movistar consulta con el "
                "indicativo más los 7 dígitos de la línea. Elígela con el "
                "ícono ✏️ de la tarjeta del contrato."
            )
        indicativo, linea = ref[:3], ref[3:]
        ciudad = next(
            (c for c, ind in MOVISTAR_CIUDADES.items() if ind == indicativo), None
        )
        if not ciudad or not await elegir(ciudad):
            return blocked(f"No se pudo seleccionar una ciudad con indicativo {indicativo}.")
        return linea, ('input[name="landLine"]', 'input[name="phoneNumber"]', 'input[type="tel"]')

    def _parsear(self, r: dict, account_reference: str) -> ScraperResult:
        codigo = r.get("error")

        # 204 es el código propio del portal para "sin deudas": no hay que
        # interpretar textos.
        if codigo == 204:
            return ScraperResult(
                amount=0, due_date=date.today() + timedelta(days=30),
                reference=f"{self.REF_PREFIX}-{account_reference}", provider=self.PROVIDER_ID,
                payment_url=self.PAYMENT_URL, is_up_to_date=True,
            )
        if codigo not in (0, None):
            print(f"[movistar] respuesta no reconocida de /api/data-payment: {r!r}")
            return ScraperResult(
                amount=0, due_date=date.today() + timedelta(days=15),
                reference=f"{self.REF_PREFIX}-{account_reference}", provider=self.PROVIDER_ID,
                payment_url=self.PAYMENT_URL, portal_blocked=True,
                blocked_reason=(
                    _mensaje_legible(r.get("message"))
                    or f"Movistar no pudo entregar la factura ahora mismo (código {codigo})."
                ),
            )

        v = r.get("values") or {}
        detalle = (v.get("invoiceInformationQiItem") or [{}])[0] if isinstance(
            v.get("invoiceInformationQiItem"), list) else {}

        # El portal hace Number(values.amount || values.transactionValue), así que
        # la API entrega números; se usan tal cual sin limpiar separadores.
        monto = 0.0
        for clave in ("amount", "transactionValue", "serviceAmountTotal"):
            crudo = v.get(clave) if clave in v else detalle.get(clave)
            if crudo in (None, "", 0):
                continue
            try:
                monto = float(crudo) if isinstance(crudo, (int, float)) else float(
                    str(crudo).replace("$", "").replace(" ", "").strip())
                break
            except (TypeError, ValueError):
                continue
        if monto <= 0:
            return ScraperResult(
                amount=0, due_date=date.today() + timedelta(days=30),
                reference=f"{self.REF_PREFIX}-{account_reference}", provider=self.PROVIDER_ID,
                payment_url=self.PAYMENT_URL, is_up_to_date=True,
            )

        ref = str(v.get("orderId") or v.get("docNumber") or account_reference)

        # Movistar no devuelve fecha de vencimiento: su respuesta solo trae montos,
        # número de orden y datos del cliente (`expires` pertenece al token, no a
        # la factura). Se dejan estos nombres por si algún día la añaden; mientras
        # tanto la fecha mostrada es una estimación.
        vence = None
        for clave in ("dueDate", "expirationDate", "paymentDueDate", "fechaVencimiento"):
            crudo = v.get(clave) or detalle.get(clave)
            if crudo:
                vence = _parse_date(str(crudo))
                if not vence:
                    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                        try:
                            vence = datetime.strptime(str(crudo)[:10], fmt).date()
                            break
                        except ValueError:
                            continue
            if vence:
                break

        return ScraperResult(
            amount=monto, due_date=vence or (date.today() + timedelta(days=15)),
            reference=f"{self.REF_PREFIX}-{ref}", provider=self.PROVIDER_ID,
            payment_url=self.PAYMENT_URL,
        )


# ── Movistar Móvil (línea celular, pestaña "Pospago") ────────────────────────

class MovistarMovilScraper(MovistarScraper):
    """
    Igual que MovistarScraper pero para la pestaña "Pospago" (línea móvil) en
    vez de "Internet" (línea fija/hogar) — mismo portal, mismo parseo de
    respuesta, formulario distinto.

    Un celular colombiano no lleva indicativo de ciudad (a diferencia de una
    línea fija), así que aquí el número de línea se usa tal cual, sin elegir
    ciudad.
    """
    TAB_LABEL       = "Pospago"
    PROVIDER_ID     = "movistar_movil"
    REF_PREFIX      = "MOVISTAR-MOVIL"
    PROFILE_ENV     = "MOVISTAR_MOVIL_PROFILE_DIR"
    PROFILE_DEFAULT = "/var/lib/finsmart/chrome-movistar-movil"

    async def _resolver_numero_linea(self, page, elegir, account_reference: str, blocked):
        valor = re.sub(r"\D", "", account_reference)
        if len(valor) != 10:
            return blocked(
                "El número de línea móvil debe tener 10 dígitos (ej: 3001234567)."
            )
        return valor, ('input[name="phoneNumber"]', 'input[name="mobileNumber"]',
                        'input[type="tel"]')


# ── GDO (Gases de Occidente - Cali) ──────────────────────────────────────────

class GDOScraper(BaseScraper):
    """
    Consulta facturas GDO via API REST interna del portal de recaudo.
    Flujo (sin Playwright, llamadas HTTP directas):
      1. GET  portalrecaudos.promigas.com/api/nonce             → nonce hex
      2. POST portalrecaudos.gdo.com.co/Logica.aspx/FirmarNonce → firma ECDSA
      3. POST portalrecaudos.promigas.com/api/signature          → JWT
      4. POST portalrecaudos.promigas.com/api/continuar          → paso 1: contrato
      5. POST portalrecaudos.promigas.com/api/financiero         → paso 2: correo+cédula → monto

    Requiere en user_data:
      - email:                 correo registrado en GDO para este contrato
      - identification_number: cédula del titular del contrato
    """

    PROMIGAS_API = "https://portalrecaudos.promigas.com/api"
    GDO_LOGICA   = "https://portalrecaudos.gdo.com.co/Logica.aspx"
    PAYMENT_URL  = "https://portalrecaudos.gdo.com.co/"

    _TOKEN_KEY = (
        "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEymCeWtLEzFs5Qvt9UZxF99tSX8KAw29"
        "YE34DcZ3w1skHlgp4/bvIbmm0m6VjoGxOainiNDX5fcbCukPMg8O2/Q=="
    )

    _BASE_HEADERS = {
        "Accept": "*/*",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Origin": "https://portalrecaudos.gdo.com.co",
        "Referer": "https://portalrecaudos.gdo.com.co/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }

    @staticmethod
    def _cupon_id(html: str) -> str:
        """
        Extrae el `data-cupon-id` del HTML del paso 2.

        Es lo que el portal envía como campo `id` a /api/financiero — no es una
        cédula. En el JS (desofuscado):

            const cuponId = document.getElementById('contenido-cupon')?.dataset?.cuponId
            cuponId && nextPestana === 1 && Object.keys(valores).length === 1
                && (valores['id'] = cuponId)

        GDO emite un cupón nuevo en cada consulta, así que hay que leerlo de la
        respuesta de /api/continuar de esta misma sesión.
        """
        from bs4 import BeautifulSoup

        el = BeautifulSoup(html, "html.parser").find(id="contenido-cupon")
        return (el.get("data-cupon-id") or "") if el else ""

    def fetch_invoice(self, account_reference: str, user_data: dict | None = None) -> ScraperResult:
        import httpx
        from bs4 import BeautifulSoup

        ud = user_data or {}

        def _blocked(reason: str) -> ScraperResult:
            return ScraperResult(
                amount=0, due_date=date.today() + timedelta(days=15),
                reference=account_reference, provider="gdo",
                payment_url=self.PAYMENT_URL,
                portal_blocked=True, blocked_reason=reason,
            )

        # Solo el correo del contrato (sin fallback al perfil): GDO valida el
        # correo del titular, que puede no ser el usuario de FinSmart.
        email = ud.get("email", "")
        if not email:
            return _blocked(
                "Para consultar GDO debes configurar el correo del contrato. "
                "Haz clic en el ícono ✏️ de la tarjeta del contrato."
            )

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                h     = dict(self._BASE_HEADERS)
                h_tok = {**h, "Token": self._TOKEN_KEY}

                # ── 1. Nonce ──────────────────────────────────────────────────
                r = client.get(f"{self.PROMIGAS_API}/nonce", headers=h_tok)
                if r.status_code != 200:
                    return _blocked(f"Portal GDO no disponible (HTTP {r.status_code}).")
                d = r.json()
                if not d.get("ok"):
                    return _blocked(f"API GDO rechazó la solicitud: {d.get('message', '')}")
                nonce: str = d["datos"]

                # ── 2. FirmarNonce ────────────────────────────────────────────
                r = client.post(
                    f"{self.GDO_LOGICA}/FirmarNonce",
                    headers={**h, "sec-fetch-site": "same-origin"},
                    json={"nonce": nonce},
                )
                if r.status_code == 403:
                    body_low = r.text.lower()
                    if "edgesuite" in body_low or "access denied" in body_low:
                        return _blocked(
                            "El portal GDO está protegido por Akamai WAF. "
                            "Usa el botón 'Ir al portal' para consultar tu factura."
                        )
                    return _blocked(f"FirmarNonce rechazado (HTTP {r.status_code}).")
                if r.status_code != 200:
                    return _blocked(f"FirmarNonce falló (HTTP {r.status_code}).")
                signature: str = r.json().get("d", "")
                if not signature:
                    return _blocked("Servidor GDO no devolvió firma ECDSA.")

                # ── 3. JWT ────────────────────────────────────────────────────
                r = client.post(
                    f"{self.PROMIGAS_API}/signature",
                    headers=h_tok,
                    json={"nonce": nonce, "signature": signature},
                )
                if r.status_code != 200 or not r.json().get("ok"):
                    return _blocked("Autenticación GDO falló al obtener JWT.")
                token: str = r.json()["datos"]["access_token"]

                # ── 4. Continuar paso 1: contrato ─────────────────────────────
                body4 = {
                    "pestana": 1,
                    "datos": {"pesta_0_Digitar_número_de_contrato": account_reference},
                    "recaptcha_token": "",
                }
                r = client.post(
                    f"{self.PROMIGAS_API}/continuar",
                    params={"token": token}, headers=h_tok, json=body4, timeout=20,
                )
                d4 = r.json() if r.status_code in (200, 500) else {}
                if d4.get("error"):
                    msg4 = d4.get("mensaje", "")
                    # GDO responde "ERROR CLIENTE SIN DEUDA" para contratos al día — esto
                    # debe revisarse ANTES del genérico "no existe"/"cliente", porque ese
                    # mensaje contiene la palabra "cliente" y quedaba mal clasificado como
                    # contrato no encontrado.
                    if _is_up_to_date(msg4):
                        return ScraperResult(
                            amount=0, due_date=date.today() + timedelta(days=30),
                            reference=f"GDO-{account_reference}", provider="gdo",
                            payment_url=self.PAYMENT_URL, is_up_to_date=True,
                        )
                    if "no existe" in msg4.lower() or "cliente" in msg4.lower():
                        return _blocked(
                            f"El contrato '{account_reference}' no fue encontrado en GDO. "
                            "Verifica el número de contrato en tu factura física."
                        )
                    return _blocked(f"GDO paso 1: {msg4 or str(d4)[:100]}")

                cupon_id = self._cupon_id(d4.get("html", ""))
                if not cupon_id:
                    return _blocked(
                        "GDO no devolvió el identificador de la consulta. "
                        "Intenta de nuevo en unos minutos."
                    )

                # ── 5. Financiero paso 2: correo + cupón → datos de factura ───
                body5 = {
                    "pestana": 1,
                    "datos": {"correo": email, "id": cupon_id},
                    "recaptcha_token": "",
                }
                r = client.post(
                    f"{self.PROMIGAS_API}/financiero",
                    params={"token": token}, headers=h_tok, json=body5, timeout=20,
                )
                d5 = r.json() if r.status_code in (200, 500) else {}
                if d5.get("error"):
                    msg5 = d5.get("mensaje", "").lower()
                    if any(k in msg5 for k in ("correo", "validación", "validation")):
                        return _blocked(
                            f"GDO no reconoce el correo '{email}' para el contrato "
                            f"{account_reference}. Debe ser el del titular de ese contrato. "
                            "Corrígelo con el ícono ✏️ de la tarjeta."
                        )
                    return _blocked(f"GDO verificación: {d5.get('mensaje', str(d5))[:150]}")

                # ── 6. Parsear HTML de paso 3 ─────────────────────────────────
                html5 = d5.get("html", "")
                if not html5:
                    return _blocked("GDO no devolvió datos de factura.")

                soup = BeautifulSoup(html5, "html.parser")
                for tag in soup.find_all(["style", "script"]):
                    tag.decompose()
                text = soup.get_text(" ", strip=True)

                if _is_up_to_date(text):
                    return ScraperResult(
                        amount=0, due_date=date.today() + timedelta(days=30),
                        reference=f"GDO-{account_reference}", provider="gdo",
                        payment_url=self.PAYMENT_URL, is_up_to_date=True,
                    )

                amounts = _parse_cop_amounts(text)
                if not amounts:
                    return _blocked("No se encontró monto de factura en la respuesta de GDO.")

                amount = max(amounts)
                ref_m  = re.search(r'Referencia\s+de\s+pago\s+(\d{6,})', text, re.IGNORECASE)
                ref    = ref_m.group(1) if ref_m else account_reference
                due    = _parse_date(text) or (date.today() + timedelta(days=15))

                return ScraperResult(
                    amount=amount, due_date=due,
                    reference=f"GDO-{ref}", provider="gdo",
                    payment_url=self.PAYMENT_URL,
                )

        except Exception as exc:
            return _blocked(f"Error al consultar portal GDO: {exc}")

    # ── PSE: iniciar sesión y obtener lista de bancos ──────────────────────────

    def init_pse_session(self, account_reference: str, email: str) -> dict:
        """
        Ejecuta pasos 1-5 del flujo GDO y devuelve JWT + lista de bancos PSE
        extraída del HTML de financiero.
        """
        import httpx
        from bs4 import BeautifulSoup

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            h     = dict(self._BASE_HEADERS)
            h_tok = {**h, "Token": self._TOKEN_KEY}

            r = client.get(f"{self.PROMIGAS_API}/nonce", headers=h_tok)
            nonce: str = r.json()["datos"]

            r = client.post(
                f"{self.GDO_LOGICA}/FirmarNonce",
                headers={**h, "sec-fetch-site": "same-origin"},
                json={"nonce": nonce},
            )
            if r.status_code == 403:
                raise ValueError("Portal GDO bloqueado por Akamai WAF.")
            signature: str = r.json().get("d", "")

            r = client.post(
                f"{self.PROMIGAS_API}/signature",
                headers=h_tok,
                json={"nonce": nonce, "signature": signature},
            )
            token: str = r.json()["datos"]["access_token"]

            r = client.post(
                f"{self.PROMIGAS_API}/continuar",
                params={"token": token}, headers=h_tok,
                json={
                    "pestana": 1,
                    "datos": {"pesta_0_Digitar_número_de_contrato": account_reference},
                    "recaptcha_token": "",
                },
                timeout=20,
            )
            d4 = r.json() if r.status_code in (200, 500) else {}
            if d4.get("error"):
                msg4 = d4.get("mensaje", "")
                # Ver el mismo comentario en fetch_invoice: "ERROR CLIENTE SIN DEUDA"
                # contiene "cliente" y se clasificaba mal como contrato no encontrado.
                if _is_up_to_date(msg4):
                    return {
                        "jwt": token,
                        "banks": [],
                        "amount": 0,
                        "due_date": str(date.today() + timedelta(days=30)),
                        "reference": f"GDO-{account_reference}",
                        "is_up_to_date": True,
                    }
                if "no existe" in msg4.lower() or "cliente" in msg4.lower():
                    raise CredentialsError(
                        f"GDO no encontró el contrato '{account_reference}'. "
                        "Verifica el número en tu factura física."
                    )
                raise ValueError(f"GDO paso 1: {msg4[:100]}")

            cupon_id = self._cupon_id(d4.get("html", ""))
            if not cupon_id:
                raise ValueError(
                    "GDO no devolvió el identificador de la consulta. Intenta de nuevo."
                )

            r = client.post(
                f"{self.PROMIGAS_API}/financiero",
                params={"token": token}, headers=h_tok,
                json={
                    "pestana": 1,
                    "datos": {"correo": email, "id": cupon_id},
                    "recaptcha_token": "",
                },
                timeout=20,
            )
            d5 = r.json() if r.status_code in (200, 500) else {}
            if d5.get("error"):
                msg5 = d5.get("mensaje", "")
                low  = msg5.lower()
                if any(k in low for k in ("correo", "validando", "validación",
                                          "validacion", "registrese", "regístrese")):
                    raise CredentialsError(
                        f"GDO no reconoce el correo '{email}' para el contrato "
                        f"{account_reference}. Debe ser el correo del titular de ese "
                        "contrato, que puede no ser el tuyo. Corrígelo con el ícono "
                        "✏️ de la tarjeta."
                    )
                raise ValueError(f"GDO financiero: {msg5[:150]}")

            html5 = d5.get("html", "")
            soup  = BeautifulSoup(html5, "html.parser")

            # Extraer lista de bancos del selector PSE (filtrar placeholder código=0)
            banks = []
            sel = soup.find("select", {"name": "pesta_2_Banco"})
            if sel:
                for opt in sel.find_all("option"):
                    code = opt.get("value", "").strip()
                    name = opt.get_text(strip=True)
                    if code and code != "0" and name:
                        banks.append({"code": code, "name": name})

            # Monto: mismo selector que usa obtenerMontoRadio() en el portal,
            # porque /api/pago exige el entero exacto que muestra el DOM.
            monto_el = soup.select_one(".fs-1.px-4 b")
            monto = 0
            if monto_el:
                digits = re.sub(r"[^\d]", "", monto_el.get_text(strip=True))
                monto = int(digits) if digits else 0

            # Parsear referencia y vencimiento del texto visible
            for tag in soup.find_all(["style", "script"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            if not monto:
                amounts = _parse_cop_amounts(text)
                monto = int(max(amounts)) if amounts else 0
            ref_m = re.search(r"Referencia\s+de\s+pago\s+(\d{6,})", text, re.IGNORECASE)
            ref   = ref_m.group(1) if ref_m else account_reference
            due   = _parse_date(text) or (date.today() + timedelta(days=15))

            up_to_date = _is_up_to_date(text) or monto <= 0 or not banks

            return {
                "jwt": token,
                "banks": banks,
                "amount": monto,
                "due_date": str(due),
                "reference": f"GDO-{ref}",
                "is_up_to_date": up_to_date,
            }

    # ── PSE: obtener URL de pago ───────────────────────────────────────────────

    def get_pse_url(self, jwt: str, bank_code: str, amount: int) -> str:
        """
        Llama a /api/pago y devuelve la URL de la pasarela PSE (Kushki).

        El payload replica exactamente lo que arma procesarPago() en el portal
        (JS desofuscado, rotación 483 del string array):

            capturarDatosFormulario() → {valido, valores, acceptoken}
              validarTipoCliente       → valores['pesta_2_Tipo_Persona'] = 2  (entero, fijo)
              validarBancoPSE          → valores['pesta_2_Banco']        = código
              validarRadioSeleccionado → valores['pesta_2_Valor_a_pagar'] = obtenerMontoRadio()
              acceptoken queda {} porque solo lo llena validarBancolombia

        Los tres campos y el `acceptoken` son obligatorios: si falta alguno o el
        tipo de persona va como string, el servidor responde
        "El medio de pago seleccionado no está disponible".
        """
        import httpx

        payload = {
            "pasarela": "pse",
            "pestana":  2,
            "datos": {
                "pesta_2_Tipo_Persona":  2,
                "pesta_2_Banco":         bank_code,
                "pesta_2_Valor_a_pagar": int(amount),
            },
            "acceptoken": {},
        }
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{self.PROMIGAS_API}/pago",
                params={"token": jwt},
                headers=dict(self._BASE_HEADERS),
                json=payload,
            )
            resp = r.json() if r.status_code in (200, 500) else {}
            if resp.get("error"):
                raise ValueError(resp.get("mensaje", "Error en pago PSE"))

            redirect = resp.get("redirect") or {}
            url = redirect.get("redirectUrl") or redirect.get("redirect_url") or ""
            if not url:
                datos = resp.get("datos") or {}
                url = datos.get("redirect_url") or datos.get("redirectUrl") or ""
            if not url:
                raise ValueError("GDO no devolvió URL de pago PSE.")
            return url


# ── Mock ──────────────────────────────────────────────────────────────────────

class MockScraper(BaseScraper):
    """Datos de demo para proveedores sin scraper implementado."""
    is_demo = True

    def __init__(self, provider_name: str = "mock"):
        self.provider_name = provider_name

    def fetch_invoice(self, account_reference: str, user_data: dict | None = None) -> ScraperResult:
        amount    = round(random.uniform(50_000, 250_000), -3)
        days_ahead = random.randint(10, 20)
        due_date  = date.today() + timedelta(days=days_ahead)
        reference = f"{self.provider_name.upper()}-{account_reference}-{due_date.strftime('%Y%m')}"
        return ScraperResult(
            amount=amount, due_date=due_date,
            reference=reference, provider=self.provider_name,
            payment_url="", is_demo=True,
        )


# ── Registry ──────────────────────────────────────────────────────────────────

PROVIDER_REGISTRY: dict[str, BaseScraper] = {
    "emcali":           EMCALIScraper(),
    "epm":              EPMScraper(),
    "codensa":          CodensaScraper(),
    "gdo":              GDOScraper(),
    "acueducto_bogota": MockScraper("acueducto_bogota"),
    "gas_natural":      MockScraper("gas_natural"),
    "surtigas":         MockScraper("surtigas"),
    "triple_a":         MockScraper("triple_a"),
    "claro":            MockScraper("claro"),
    "movistar":         MovistarScraper(),
    "movistar_movil":   MovistarMovilScraper(),
    "tigo":             MockScraper("tigo"),
    "wom":              MockScraper("wom"),
    "etb":              MockScraper("etb"),
    "une":              MockScraper("une"),
    "netflix":          MockScraper("netflix"),
    "spotify":          MockScraper("spotify"),
    "disney_plus":      MockScraper("disney_plus"),
    "amazon_prime":     MockScraper("amazon_prime"),
    "youtube_premium":  MockScraper("youtube_premium"),
    "hbo_max":          MockScraper("hbo_max"),
    "directv":          MockScraper("directv"),
    "default":          MockScraper("default"),
}

PROVIDERS_LIST = [
    {"id": "emcali",           "name": "EMCALI",              "category": "Servicios Públicos", "logo_hint": "zap",      "real_scraper": True},
    {"id": "gdo",              "name": "GDO - Gases de Occidente", "category": "Servicios Públicos", "logo_hint": "flame", "real_scraper": True},
    {"id": "epm",              "name": "EPM",                 "category": "Servicios Públicos", "logo_hint": "zap",      "real_scraper": False},
    {"id": "codensa",          "name": "Codensa / Enel",      "category": "Servicios Públicos", "logo_hint": "zap",      "real_scraper": False},
    {"id": "acueducto_bogota", "name": "Acueducto de Bogotá", "category": "Servicios Públicos", "logo_hint": "droplets", "real_scraper": False},
    {"id": "gas_natural",      "name": "Gas Natural",         "category": "Servicios Públicos", "logo_hint": "flame",    "real_scraper": False},
    {"id": "surtigas",         "name": "Surtigas",            "category": "Servicios Públicos", "logo_hint": "flame",    "real_scraper": False},
    {"id": "triple_a",         "name": "Triple A",            "category": "Servicios Públicos", "logo_hint": "droplets", "real_scraper": False},
    {"id": "claro",            "name": "Claro",               "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": False},
    {"id": "movistar",         "name": "Movistar Hogar",      "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": True},
    {"id": "movistar_movil",  "name": "Movistar Móvil",       "category": "Telecomunicaciones", "logo_hint": "smartphone", "real_scraper": True},
    {"id": "tigo",             "name": "Tigo",                "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": False},
    {"id": "wom",              "name": "WOM",                 "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": False},
    {"id": "etb",              "name": "ETB",                 "category": "Telecomunicaciones", "logo_hint": "phone", "real_scraper": False},
    {"id": "une",              "name": "UNE",                 "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": False},
    {"id": "netflix",          "name": "Netflix",             "category": "Streaming",          "logo_hint": "tv",    "real_scraper": False},
    {"id": "spotify",          "name": "Spotify",             "category": "Streaming",          "logo_hint": "music", "real_scraper": False},
    {"id": "disney_plus",      "name": "Disney+",             "category": "Streaming",          "logo_hint": "tv",    "real_scraper": False},
    {"id": "amazon_prime",     "name": "Amazon Prime",        "category": "Streaming",          "logo_hint": "tv",    "real_scraper": False},
    {"id": "youtube_premium",  "name": "YouTube Premium",     "category": "Streaming",          "logo_hint": "tv",    "real_scraper": False},
    {"id": "hbo_max",          "name": "HBO Max",             "category": "Streaming",          "logo_hint": "tv",    "real_scraper": False},
    {"id": "directv",          "name": "DirecTV",             "category": "Streaming",          "logo_hint": "tv",    "real_scraper": False},
]


def get_scraper(provider: str) -> BaseScraper:
    return PROVIDER_REGISTRY.get(provider.lower(), PROVIDER_REGISTRY["default"])


def fetch_invoice(provider: str, account_reference: str) -> ScraperResult:
    return get_scraper(provider).fetch_invoice(account_reference)

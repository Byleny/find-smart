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

from services.claro_pse import PORTAL_URL as _CLARO_PORTAL_URL

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


# ── Redirección manual ───────────────────────────────────────────────────────

class ManualPortalScraper(BaseScraper):
    """
    Para proveedores donde SÍ existe automatización probada (a diferencia de
    MockScraper) pero se decidió no usarla como flujo principal por su
    fragilidad en operación real — es el caso de Claro: la automatización de
    services/claro_pse.py llega a funcionar de punta a punta, pero el paso
    final de confirmación puede tardar minutos o rebotar sin motivo aparente
    incluso cuando todo lo demás salió bien, algo inaceptable para un usuario
    esperando en vivo. En vez de eso, se manda directo al portal real: mismo
    resultado que "portal_blocked" (reaprovecha esa UI ya construida), pero
    sin fingir que el portal falló — el mensaje explica que es la vía
    elegida, no un error.
    """
    def __init__(self, provider_name: str, payment_url: str, reason: str):
        self.provider_name = provider_name
        self.payment_url = payment_url
        self.reason = reason

    def fetch_invoice(self, account_reference: str, user_data: dict | None = None) -> ScraperResult:
        return ScraperResult(
            amount=0.0, due_date=date.today(), reference="",
            provider=self.provider_name, payment_url=self.payment_url,
            portal_blocked=True, blocked_reason=self.reason,
        )


# ── Registry ──────────────────────────────────────────────────────────────────

PROVIDER_REGISTRY: dict[str, BaseScraper] = {
    # EMCALI sí tiene automatización probada (services/emcali_captcha.py, el
    # reCAPTCHA se retransmite al usuario para que lo resuelva él mismo), pero
    # se decidió no usarla como flujo principal por la misma razón que Claro:
    # depende de un navegador automatizado sostenido durante toda la consulta,
    # con el mismo riesgo de rebote a mitad de camino. Se manda directo al
    # portal real, igual que Claro y Movistar.
    "emcali":           ManualPortalScraper(
        "emcali", EMCALIScraper.PORTAL_URL,
        "Para mayor confiabilidad, paga directamente en el portal de EMCALI "
        "con tu número de contrato.",
    ),
    "epm":              EPMScraper(),
    "codensa":          CodensaScraper(),
    "celsia":           ManualPortalScraper(
        "celsia", "https://clientes.celsia.com/clientes/login/",
        "Para mayor confiabilidad, paga directamente en el portal de Celsia "
        "con tu número de cuenta o contrato.",
    ),
    "gdo":              GDOScraper(),
    "acueducto_bogota": MockScraper("acueducto_bogota"),
    "gas_natural":      MockScraper("gas_natural"),
    "surtigas":         MockScraper("surtigas"),
    "triple_a":         MockScraper("triple_a"),
    # Claro sí tiene automatización de pago probada de punta a punta
    # (services/claro_pse.py), pero se decidió no usarla como flujo
    # principal: el paso final de confirmación puede tardar minutos o
    # rebotar sin motivo aparente incluso cuando el resto del flujo salió
    # bien, y eso no es aceptable para un usuario esperando en vivo. En su
    # lugar se manda directo al portal real de Claro.
    "claro":            ManualPortalScraper(
        "claro", _CLARO_PORTAL_URL,
        "Para mayor confiabilidad, paga directamente en el portal de Claro: elige "
        "\"Pago de Facturas\" → \"Postpago\" e ingresa tu número de celular.",
    ),
    "claro_hogar":      ManualPortalScraper(
        "claro_hogar", _CLARO_PORTAL_URL,
        "Para mayor confiabilidad, paga directamente en el portal de Claro: elige "
        "\"Pago de Facturas\" → \"Hogar y Multiplay\" e ingresa tu número de cuenta o referencia.",
    ),
    # Movistar (payment.movistar.co y el gateway PSE aparte) quedó
    # confirmado no automatizable: la consulta empezó a fallar con HTTP 500
    # del lado del servidor (probable caída del puntaje de reCAPTCHA v3 por
    # el fingerprint del navegador automatizado) y el pago vía PSE está
    # detrás de Cloudflare Turnstile, que bloquea la instrumentación de
    # Playwright/patchright sin importar quién interactúe con ella. Igual que
    # Claro, se manda directo al portal real en vez de fingir una consulta.
    "movistar":         ManualPortalScraper(
        "movistar", "https://movistar.recaudo.epayco.co/",
        "Para mayor confiabilidad, paga directamente en el portal de Movistar "
        "con tu número de línea o referencia de pago.",
    ),
    "movistar_movil":   ManualPortalScraper(
        "movistar_movil", "https://movistar.recaudo.epayco.co/",
        "Para mayor confiabilidad, paga directamente en el portal de Movistar "
        "con tu número de celular.",
    ),
    "tigo":             ManualPortalScraper(
        "tigo", "https://mi.tigo.com.co/pago-express/facturas",
        "Para mayor confiabilidad, paga directamente en el portal de Tigo con tu "
        "número de contrato o de línea.",
    ),
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
    {"id": "celsia",           "name": "Celsia",              "category": "Servicios Públicos", "logo_hint": "zap",      "real_scraper": True},
    {"id": "acueducto_bogota", "name": "Acueducto de Bogotá", "category": "Servicios Públicos", "logo_hint": "droplets", "real_scraper": False},
    {"id": "gas_natural",      "name": "Gas Natural",         "category": "Servicios Públicos", "logo_hint": "flame",    "real_scraper": False},
    {"id": "surtigas",         "name": "Surtigas",            "category": "Servicios Públicos", "logo_hint": "flame",    "real_scraper": False},
    {"id": "triple_a",         "name": "Triple A",            "category": "Servicios Públicos", "logo_hint": "droplets", "real_scraper": False},
    # Claro Móvil/Hogar y Movistar Móvil/Hogar terminan en el mismo portal
    # (el mismo enlace de ManualPortalScraper para ambas variantes, ya que no
    # se automatiza ningún paso donde importe la distinción) — se ofrece un
    # solo proveedor para agregar. "claro_hogar" y "movistar_movil" siguen
    # resueltos en PROVIDER_REGISTRY para no romper contratos ya guardados
    # con ese identificador.
    {"id": "claro",            "name": "Claro",               "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": True},
    {"id": "movistar",         "name": "Movistar",            "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": True},
    {"id": "tigo",             "name": "Tigo",                "category": "Telecomunicaciones", "logo_hint": "wifi",  "real_scraper": True},
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

"""
Pago PSE de Movistar (payment.movistar.co).

A diferencia de GDO (API REST plana, ver GDOScraper.init_pse_session /
get_pse_url), el pago con PSE de Movistar es interactivo: hay que consultar
la factura, hacer clic en "Pagar", elegir PSE en el modal de métodos de pago
y llenar el formulario de datos personales que abre el procesador (Cobre)
antes de que redirija al banco real. El navegador vive entre peticiones HTTP
(mismo patrón que services/emcali_captcha.py) porque hay que sostener la
sesión mientras el usuario elige el banco en la UI de FinSmart.

Incertidumbre conocida: los selectores del modal "Selecciona tu medio de
pago" y del formulario Cobre se escribieron a partir de capturas de pantalla,
no del DOM real, así que tienen selectores alternativos de respaldo pero es
probable que necesiten ajuste tras la primera prueba contra el portal real.
Tampoco se sabe si la URL de redirección final requiere las cookies que
acumula este navegador headless o si es autocontenida (como sí lo es el
link de Kushki que devuelve GDO); si el banco rechaza la sesión al abrir el
link en el navegador del usuario, habrá que servir esa página vía proxy en
vez de redirigir.
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta

from services.scraper_service import (
    MovistarScraper, MovistarMovilScraper, ScraperResult, MOVISTAR_CIUDADES,
)

PORTAL_URL = "https://payment.movistar.co/"
_TTL = timedelta(minutes=10)

# Tipo de documento del portal Cobre -> texto exacto de la opción esperada.
_TIPOS_DOCUMENTO = {
    "CC": "Cédula de Ciudadanía",
    "CE": "Cédula de Extranjería",
    "NIT": "NIT",
    "PA": "Pasaporte",
    "TI": "Tarjeta de Identidad",
}


def _limpiar_lock_perfil(perfil: str) -> None:
    """
    Borra el candado de Chrome (SingletonLock/SingletonSocket/SingletonCookie)
    antes de lanzar el navegador. El worker de este módulo procesa una
    consulta a la vez sobre este mismo perfil, así que si el candado sigue
    ahí es de una sesión anterior que no cerró limpio (timeout, proceso
    matado) — no de una realmente concurrente. Sin esto, Playwright falla con
    "Opening in existing browser session" y ya no hay forma de recuperarse
    sin entrar al contenedor a borrarlo a mano.
    """
    for nombre in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.remove(os.path.join(perfil, nombre))
        except FileNotFoundError:
            pass
        except OSError:
            pass


# ── Hilo con event loop propio (igual que emcali_captcha.py) ────────────────

class _BrowserWorker:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, daemon=True,
                                 name="movistar-pse-browser").start()
                self._loop = loop
            return self._loop

    def run(self, coro, timeout: float = 120.0):
        loop = self._ensure()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)

    def schedule(self, coro):
        """
        Como `run`, pero no espera el resultado: lo arranca en el loop del
        worker y devuelve un Future de inmediato. El flujo completo de
        Movistar (con reintentos) puede tardar más de un minuto, y ninguna
        conexión HTTP debería quedar abierta ese tiempo — el llamador
        sondea el Future con `estado_iniciar()` en vez de bloquear la
        petición original.
        """
        loop = self._ensure()
        return asyncio.run_coroutine_threadsafe(coro, loop)


_worker = _BrowserWorker()


class _Sesion:
    def __init__(self, tab_label: str, provider_id: str, ref_prefix: str):
        self.id = str(uuid.uuid4())
        self.tab_label = tab_label
        self.provider_id = provider_id
        self.ref_prefix = ref_prefix
        self.expira = datetime.utcnow() + _TTL
        self.playwright = None
        self.contexto = None
        self.page = None          # página con el formulario Cobre (puede ser un popup)
        self.amount: float = 0.0
        self.due_date: str = ""
        self.reference: str = ""
        self.is_up_to_date: bool = False
        self.banks: list[dict] = []
        self.futuro = None   # concurrent.futures.Future del arranque en segundo plano

    def viva(self) -> bool:
        return self.expira > datetime.utcnow()


_sesiones: dict[str, _Sesion] = {}


def _purgar() -> None:
    for sid in [s for s, v in _sesiones.items() if not v.viva()]:
        ses = _sesiones.pop(sid, None)
        if ses:
            try:
                _worker.run(_cerrar_sesion(ses), timeout=30)
            except Exception:
                pass


async def _cerrar_sesion(ses: _Sesion) -> None:
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


# ── Utilidades de página ─────────────────────────────────────────────────────

_BOTONES_A_EVITAR = {
    "continuar", "pagar", "agregar otra factura",
    "activar o actualizar tu pago automático",
    "eliminar factura de mi lista",
    "pospago", "internet",
}


async def _elegir(page, texto: str) -> bool:
    """
    Elige una opción por texto. Prueba primero un <select> nativo; si no hay
    ninguno con esa opción, el campo es un combobox personalizado (el portal
    real no usa <select> para "Identificador de pago"), así que se abre cada
    disparador visible y se busca una opción con el texto pedido, evitando
    los botones de acción conocidos para no enviar el formulario antes de
    tiempo.
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
                await page.wait_for_timeout(1_200)
                return True
        except Exception:
            continue

    # Tope y tiempos recortados: el combo correcto casi siempre está entre
    # los primeros candidatos; agotar los 20 con espera larga por candidato
    # equivocado sumaba hasta ~40s extra por consulta.
    disparadores = page.locator('[role="combobox"], [aria-haspopup="listbox"], button, [role="button"]')
    for i in range(min(await disparadores.count(), 10)):
        trigger = disparadores.nth(i)
        try:
            if not await trigger.is_visible(timeout=300):
                continue
            texto_boton = (await trigger.text_content() or "").strip().lower()
            if texto_boton in _BOTONES_A_EVITAR:
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


async def _click_texto(page, texto: str, timeout: int = 4_000) -> bool:
    try:
        el = page.locator(f'text="{texto}"').first
        if await el.is_visible(timeout=timeout):
            await el.click()
            return True
    except Exception:
        pass
    return False


async def _fill_por_label(page, etiqueta: str, valor: str) -> bool:
    """
    Busca un input cercano a un <label>/texto con la etiqueta dada. El
    formulario de Cobre no trae `name` conocidos de antemano, así que se
    ubica por proximidad al texto visible (mismo enfoque que un lector de
    pantalla usaría).
    """
    try:
        campo = page.get_by_label(etiqueta, exact=False).first
        if await campo.count() and await campo.is_visible(timeout=1_500):
            await campo.fill(valor)
            return True
    except Exception:
        pass
    # Respaldo: el input no es descendiente del <label> ni de su padre directo
    # (en el formulario de Cobre son divs hermanos bajo un contenedor común),
    # así que se sube hasta el primer ancestro que SÍ contenga un input en
    # cualquier profundidad, no solo como hijo directo.
    try:
        bloque = page.locator(f'text="{etiqueta}"').first.locator(
            "xpath=ancestor::div[.//input][1]//input"
        ).first
        if await bloque.count() and await bloque.is_visible(timeout=1_500):
            await bloque.fill(valor)
            return True
    except Exception:
        pass
    return False


# ── Paso 1: consultar factura + llegar al formulario Cobre ───────────────────

async def _iniciar(
    ses: _Sesion, account_reference: str, tipo: str, user_data: dict,
) -> dict:
    from patchright.async_api import async_playwright

    def _blocked(reason: str) -> dict:
        return {
            "estado": "bloqueado",
            "resultado": {
                "amount": 0, "due_date": str(date.today() + timedelta(days=15)),
                "reference": f"{ses.ref_prefix}-{account_reference}",
                "portal_blocked": True, "blocked_reason": reason,
            },
        }

    perfil_env = "MOVISTAR_MOVIL_PSE_PROFILE_DIR" if ses.tab_label == "Pospago" else "MOVISTAR_PSE_PROFILE_DIR"
    perfil_default = ("/var/lib/finsmart/chrome-movistar-movil-pse" if ses.tab_label == "Pospago"
                       else "/var/lib/finsmart/chrome-movistar-pse")
    perfil = os.environ.get(perfil_env, perfil_default)
    os.makedirs(perfil, exist_ok=True)
    _limpiar_lock_perfil(perfil)

    con_display = bool(os.environ.get("DISPLAY"))
    ses.playwright = await async_playwright().start()
    try:
        ses.contexto = await ses.playwright.chromium.launch_persistent_context(
            user_data_dir=perfil, headless=not con_display, no_viewport=True,
            locale="es-CO", timezone_id="America/Bogota",
            args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1500,1100"],
        )
    except Exception as exc:
        # Xvfb puede no estar listo todavía justo después de que el contenedor
        # reinicia (o haberse caído en algún punto) — en vez de fallar toda la
        # consulta, se reintenta una vez en headless puro.
        if con_display and "display" in str(exc).lower():
            print(f"[movistar-pse] falló el lanzamiento con pantalla ({exc}); reintentando headless")
            _limpiar_lock_perfil(perfil)
            ses.contexto = await ses.playwright.chromium.launch_persistent_context(
                user_data_dir=perfil, headless=True, no_viewport=True,
                locale="es-CO", timezone_id="America/Bogota",
                args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1500,1100"],
            )
        else:
            raise
    page = ses.contexto.pages[0] if ses.contexto.pages else await ses.contexto.new_page()

    respuesta: dict | None = None

    async def on_response(r):
        nonlocal respuesta
        if "/api/data-payment" in r.url:
            print(f"[movistar-pse] {r.request.method} {r.url} -> HTTP {r.status}")
            try:
                respuesta = await r.json()
                print(f"[movistar-pse] /api/data-payment crudo: {respuesta!r}")
            except Exception as exc:
                print(f"[movistar-pse] no se pudo leer el body como JSON: {exc}")

    page.on("response", lambda r: asyncio.create_task(on_response(r)))

    await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(6_000)

    async def _pestana_correcta() -> bool:
        # Si el formulario todavía no terminó de montar, "Ciudad" tampoco es
        # visible en NINGUNA pestaña — eso se veía igual que "ya estamos en
        # Pospago" y daba por buena una página a medio cargar. Esperar
        # primero a que "Identificador de pago" exista evita ese falso
        # positivo (es más rápido en cuanto ya cargó: no vuelve a esperar).
        try:
            await page.locator('text="Identificador de pago"').first.wait_for(state="visible", timeout=5_000)
        except Exception:
            pass
        try:
            ciudad_visible = await page.locator('text="Ciudad"').first.is_visible(timeout=1_500)
        except Exception:
            ciudad_visible = False
        return ciudad_visible == (ses.tab_label == "Internet")

    pestana_ok = await _pestana_correcta()
    intentos = 0
    while not pestana_ok and intentos < 3:
        try:
            tab = page.get_by_text(ses.tab_label, exact=False).first
            await tab.click(force=(intentos > 0), timeout=4_000)
            await page.wait_for_timeout(2_000)
        except Exception:
            pass
        pestana_ok = await _pestana_correcta()
        intentos += 1

    # El selector de operador solo existe en la pestaña Internet (línea
    # fija); en Pospago no hay tal campo y buscarlo igual agotaba hasta 20
    # intentos de fuerza bruta por nada.
    if ses.tab_label != "Pospago":
        await _elegir(page, "Movistar")
    etiqueta = "Con número de línea" if tipo == "1" else "Con referencia de pago"
    if not await _elegir(page, etiqueta):
        print(f"[movistar-pse] pestana_ok antes de fallar etiqueta: {pestana_ok} (tab_label={ses.tab_label})")
        try:
            await page.screenshot(path="/tmp/movistar_pse_etiqueta.png", full_page=True)
        except Exception:
            pass
        return _blocked(f"El portal de Movistar no ofrece la opción '{etiqueta}'.")

    if tipo == "1":
        ref = re.sub(r"\D", "", account_reference)
        if ses.tab_label == "Pospago":
            if len(ref) != 10:
                return _blocked("El número de línea móvil debe tener 10 dígitos.")
            valor = ref
            selectores = ('input[name="phoneNumber"]', 'input[name="mobileNumber"]', 'input[type="tel"]')
        else:
            if len(ref) < 10:
                return _blocked("Falta la ciudad de este servicio (indicativo + 7 dígitos).")
            indicativo, linea = ref[:3], ref[3:]
            ciudad = next((c for c, ind in MOVISTAR_CIUDADES.items() if ind == indicativo), None)
            if not ciudad or not await _elegir(page, ciudad):
                return _blocked(f"No se pudo seleccionar una ciudad con indicativo {indicativo}.")
            valor = linea
            selectores = ('input[name="landLine"]', 'input[name="phoneNumber"]', 'input[type="tel"]')
    else:
        valor = re.sub(r"\D", "", account_reference)
        selectores = ('input[name="referenceNumber"]', 'input[data-testid="integer-field"]')

    campo = None
    for sel in selectores:
        loc = page.locator(sel).first
        try:
            if await loc.count() and await loc.is_visible():
                campo = loc
                break
        except Exception:
            continue
    if campo is None:
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
        await page.keyboard.type(ch, delay=80)
    await page.wait_for_timeout(1_200)

    btn = page.locator('button:has-text("Continuar")').first
    if not await btn.is_enabled():
        return _blocked("El portal no habilitó el botón de consulta; revisa el número.")
    await btn.click()

    for _ in range(35):
        await page.wait_for_timeout(1_000)
        if respuesta is not None:
            break
    if respuesta is None:
        return _blocked("Movistar no respondió a la consulta de factura.")

    scraper = MovistarMovilScraper() if ses.tab_label == "Pospago" else MovistarScraper()
    resultado: ScraperResult = scraper._parsear(respuesta, account_reference)
    ses.amount = resultado.amount
    ses.due_date = str(resultado.due_date)
    ses.reference = resultado.reference
    ses.is_up_to_date = resultado.is_up_to_date

    if resultado.portal_blocked or resultado.is_up_to_date or resultado.amount <= 0:
        return {
            "estado": "listo_sin_pago",
            "resultado": {
                "amount": resultado.amount, "due_date": str(resultado.due_date),
                "reference": resultado.reference, "is_up_to_date": resultado.is_up_to_date,
                "portal_blocked": resultado.portal_blocked, "blocked_reason": resultado.blocked_reason,
            },
        }

    # ── Clic en "Pagar" de la página de detalle de factura ────────────────────
    # El SPA tarda un momento en cambiar de vista (formulario → "Detalle de tu
    # factura") después de que llega la respuesta de la API; sin esta espera
    # se buscaba el botón antes de que existiera en el DOM.
    await page.wait_for_timeout(2_500)
    if not await _click_texto(page, "Pagar"):
        return _blocked("No se encontró el botón 'Pagar' en el detalle de la factura.")
    await page.wait_for_timeout(2_000)

    # ── Modal "Selecciona tu medio de pago": asegurar PSE y continuar ─────────
    try:
        pse_radio = page.locator('text="PSE"').first
        if await pse_radio.is_visible(timeout=5_000):
            await pse_radio.click()
            await page.wait_for_timeout(500)
    except Exception:
        pass

    # El clic en "Continuar" del modal puede, en teoría, abrir una pestaña
    # nueva (Cobre en otro dominio) o navegar en la misma. En la práctica este
    # sitio SIEMPRE navega en la misma pestaña — usar expect_page() aquí
    # esperaba 8s completos por un popup que nunca llega, y ese tiempo muerto
    # (más los 3s extra del respaldo) hacía que la sesión de pago de Cobre
    # expirara antes de que llegáramos a usarla: quedaba en
    # https://checkout.cobre.co/error?status=INACTIVE en vez del formulario.
    pagina_nueva = None

    def _on_new_page(pg):
        nonlocal pagina_nueva
        pagina_nueva = pg

    ses.contexto.on("page", _on_new_page)
    url_antes = page.url
    try:
        if not await _click_texto(page, "Continuar"):
            return _blocked("No se encontró el botón 'Continuar' en el modal de métodos de pago.")
        for _ in range(20):   # hasta ~4s, corta apenas se detecta algo
            if pagina_nueva is not None or page.url != url_antes:
                break
            await page.wait_for_timeout(200)
    finally:
        ses.contexto.remove_listener("page", _on_new_page)

    if pagina_nueva is not None:
        pagina_cobre = pagina_nueva
        await pagina_cobre.wait_for_load_state("domcontentloaded", timeout=15_000)
    else:
        pagina_cobre = page
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8_000)
        except Exception:
            pass

    ses.page = pagina_cobre
    await pagina_cobre.wait_for_timeout(1_000)

    # Si Cobre marcó la sesión de pago como inactiva (expiró, o se tardó
    # demasiado en llegar), no hay formulario que leer — cortar aquí en vez
    # de agotar la espera de bancos para nada.
    if "/error" in pagina_cobre.url or "INACTIVE" in pagina_cobre.url:
        print(f"[movistar-pse] sesión de Cobre inactiva al llegar: {pagina_cobre.url}")
        return _blocked(
            "La sesión de pago con Movistar expiró antes de llegar al formulario. Intenta de nuevo."
        )

    # ── Extraer bancos de "Entidad financiera" ────────────────────────────────
    # No es un <select> nativo: es un componente vue-select (id
    # "financial-institution", listbox "vs*__listbox"). El listbox existe en
    # el DOM pero vacío y oculto hasta que se abre el combo — Cobre carga las
    # opciones (o las renderiza) recién en ese momento, así que hay que hacer
    # clic y esperar activamente a que aparezcan.
    banks: list[dict] = []

    async def _abrir_combo_bancos() -> None:
        try:
            combo = pagina_cobre.locator("#financial-institution").first
            if await combo.count():
                await combo.click(timeout=3_000)
        except Exception:
            pass

    await _abrir_combo_bancos()

    for intento in range(24):   # ~12s de espera activa
        # El primer clic puede no haber abierto el combo a tiempo (la página
        # sigue montando componentes); reintentarlo a mitad de la espera.
        if intento == 8:
            await _abrir_combo_bancos()
        try:
            opciones = pagina_cobre.locator('ul[id*="listbox"] li, [role="listbox"] [role="option"]')
            n = await opciones.count()
            candidatos = []
            for i in range(n):
                nombre = (await opciones.nth(i).text_content() or "").strip()
                if nombre and nombre.lower() not in ("seleccionar", "selecciona", "no options found."):
                    candidatos.append({"code": nombre, "name": nombre})
            if len(candidatos) >= 3:
                banks = candidatos
                break
        except Exception:
            pass
        await pagina_cobre.wait_for_timeout(500)

    try:
        await pagina_cobre.keyboard.press("Escape")
    except Exception:
        pass

    if not banks:
        try:
            await pagina_cobre.screenshot(path="/tmp/movistar_pse_cobre.png", full_page=True)
            html = await pagina_cobre.content()
            with open("/tmp/movistar_pse_cobre.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass
        print(f"[movistar-pse] URL de la página al fallar bancos: {pagina_cobre.url}")
        return _blocked(
            "No se pudo leer la lista de bancos en el formulario de pago de Movistar. "
            "Puede que hayan cambiado el formulario."
        )

    ses.banks = banks
    return {
        "estado": "listo",
        "session_id": ses.id,
        "banks": banks,
        "amount": ses.amount,
        "due_date": ses.due_date,
        "reference": ses.reference,
        "is_up_to_date": ses.is_up_to_date,
    }


# ── Paso 2: llenar datos personales y obtener el link del banco ─────────────

async def _pagar(ses: _Sesion, bank_code: str, user_data: dict, guardar_datos: bool) -> dict:
    page = ses.page
    if page is None:
        raise RuntimeError("Sesión sin formulario de pago abierto.")

    # "Entidad financiera" es un combo vue-select (ver _iniciar): hay que
    # abrirlo y hacer clic en la opción cuyo texto coincide, no un <select>.
    seleccionado = False
    try:
        combo = page.locator("#financial-institution").first
        if await combo.count():
            await combo.click(timeout=3_000)
            await page.wait_for_timeout(500)
            opcion = page.locator('ul[id*="listbox"] li, [role="listbox"] [role="option"]').filter(
                has_text=bank_code
            ).first
            if await opcion.count() and await opcion.is_visible(timeout=2_000):
                await opcion.click(timeout=2_000)
                seleccionado = True
    except Exception:
        pass
    if not seleccionado:
        raise ValueError("No se pudo seleccionar la entidad financiera indicada.")
    await page.wait_for_timeout(600)

    tipo_doc = _TIPOS_DOCUMENTO.get((user_data.get("identification_type") or "CC").upper(), "Cédula de Ciudadanía")
    telefono = re.sub(r"\D", "", user_data.get("phone") or "")
    if telefono.startswith("57") and len(telefono) > 10:
        telefono = telefono[2:]   # el campo ya trae el +57 como prefijo aparte

    campos = [
        ("Nombre", user_data.get("full_name") or ""),
        ("Número de documento", user_data.get("identification_number") or ""),
        ("Correo electrónico", user_data.get("email") or ""),
    ]
    faltantes = []
    for etiqueta, valor in campos:
        if not valor:
            continue
        if not await _fill_por_label(page, etiqueta, valor):
            faltantes.append(etiqueta)

    # "Número de teléfono" tiene un selector de indicativo (+57) al lado, que
    # trae su propio input oculto antes del campo real — el genérico por
    # proximidad de etiqueta agarra ese en vez del visible. Se busca por
    # placeholder/type en vez de por la etiqueta.
    if telefono:
        lleno = False
        for sel in ('input[placeholder*="000"]', 'input[type="tel"]'):
            try:
                campo = page.locator(sel).first
                if await campo.count() and await campo.is_visible(timeout=1_500):
                    await campo.fill(telefono)
                    lleno = True
                    break
            except Exception:
                continue
        if not lleno:
            faltantes.append("Número de teléfono")

    await _elegir(page, tipo_doc)

    if guardar_datos:
        try:
            cb = page.locator('input[type="checkbox"]').first
            if await cb.count() and not await cb.is_checked():
                await cb.check(timeout=3_000)
        except Exception:
            pass

    if faltantes:
        raise ValueError(
            "No se pudieron llenar estos campos en el formulario de Movistar: "
            + ", ".join(faltantes)
        )

    btn = page.locator('button:has-text("Pagar")').first
    for _ in range(10):
        if await btn.is_enabled():
            break
        await page.wait_for_timeout(500)
    if not await btn.is_enabled():
        raise ValueError("El botón de pago no se habilitó; revisa que todos los campos sean válidos.")

    url_antes = page.url
    await btn.click()

    redirect_url = ""
    for _ in range(20):
        await page.wait_for_timeout(1_000)
        if page.url != url_antes:
            redirect_url = page.url
            break
    if not redirect_url:
        raise ValueError("Movistar no redirigió a la pasarela del banco tras el pago.")

    return {"redirect_url": redirect_url}


# ── API pública (síncrona) ───────────────────────────────────────────────────

# Mensajes de fallo probablemente transitorio (reCAPTCHA v3 puntuó bajo esa
# sesión) — vale la pena reintentar con una sesión nueva. Ver el mismo
# razonamiento en scraper_service.py.
_MENSAJES_REINTENTABLES = (
    "no pudo entregar la factura ahora mismo",
    "no respondió a la consulta",
    "sesión de pago con Movistar expiró",
)


class _Poll:
    """
    Handle de sondeo para un trabajo en segundo plano (iniciar o pagar).
    Independiente de _Sesion: una consulta puede reintentar internamente con
    varias _Sesion (una por intento), pero el frontend sondea siempre el
    mismo _Poll.id sin importar cuántos intentos haya adentro.
    """
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.expira = datetime.utcnow() + _TTL
        self.futuro = None

    def viva(self) -> bool:
        return self.expira > datetime.utcnow()


_polls: dict[str, _Poll] = {}


def _purgar_polls() -> None:
    for pid in [p for p, v in _polls.items() if not v.viva()]:
        _polls.pop(pid, None)


# Un lock de asyncio (no de threading) por pestaña/perfil: todo este módulo
# corre en un único hilo con su propio loop (_worker), así que un lock
# bloqueante de threading dejaría el loop entero congelado en vez de ceder el
# turno a la corrutina que tiene que soltarlo — sería un deadlock, no una
# cola. Con asyncio.Lock, una segunda consulta al mismo perfil simplemente
# espera su turno en vez de competir por el mismo perfil de Chrome.
_locks_tab: dict[str, asyncio.Lock] = {}


def _lock_tab(tab_label: str) -> asyncio.Lock:
    if tab_label not in _locks_tab:
        _locks_tab[tab_label] = asyncio.Lock()
    return _locks_tab[tab_label]


async def _iniciar_con_reintentos(account_reference: str, tipo: str, user_data: dict, tab_label: str) -> dict:
    async with _lock_tab(tab_label):
        # Ahora que el arranque es asíncrono (sondeo, no una conexión
        # sostenida), un intento extra sale gratis en tiempo de espera del
        # usuario.
        intentos = 3
        resultado: dict = {}
        for intento in range(1, intentos + 1):
            _purgar()
            ses = _Sesion(
                tab_label=tab_label,
                provider_id="movistar_movil" if tab_label == "Pospago" else "movistar",
                ref_prefix="MOVISTAR-MOVIL" if tab_label == "Pospago" else "MOVISTAR",
            )
            _sesiones[ses.id] = ses
            try:
                resultado = await _iniciar(ses, account_reference, tipo, user_data)
            except Exception:
                _sesiones.pop(ses.id, None)
                await _cerrar_sesion(ses)
                raise

            if resultado.get("estado") == "listo":
                return resultado

            _sesiones.pop(ses.id, None)
            await _cerrar_sesion(ses)

            blocked_reason = (resultado.get("resultado") or {}).get("blocked_reason", "")
            reintentable = any(m in blocked_reason for m in _MENSAJES_REINTENTABLES)
            if not reintentable or intento == intentos:
                return resultado
            print(f"[movistar-pse] intento {intento}/{intentos} bloqueado, reintentando: {blocked_reason}")
        return resultado


def iniciar(account_reference: str, tipo: str, user_data: dict, tab_label: str = "Internet") -> dict:
    """
    Arranca la consulta en segundo plano y devuelve de inmediato un poll_id
    — el resultado real se obtiene sondeando con `estado_iniciar()`.

    El flujo completo (con reintentos) puede tomar más de un minuto entre
    varias idas y vueltas al portal real de Movistar. Sostener eso en una
    sola conexión HTTP resultó frágil: túneles/proxies (como el que usa el
    usuario para pruebas) la cortan antes de tiempo de forma intermitente.
    Sondear en vez de bloquear es el mismo patrón ya probado en
    emcali_captcha.py para este tipo de automatización larga.
    """
    _purgar_polls()
    poll = _Poll()
    poll.futuro = _worker.schedule(_iniciar_con_reintentos(account_reference, tipo, user_data, tab_label))
    _polls[poll.id] = poll
    return {"estado": "consultando", "poll_id": poll.id}


def estado_iniciar(poll_id: str) -> dict:
    poll = _polls.get(poll_id)
    if not poll:
        raise KeyError("sesión de consulta expirada")
    if not poll.futuro.done():
        return {"estado": "consultando"}
    _polls.pop(poll_id, None)
    return poll.futuro.result()   # puede relanzar la excepción original


async def _pagar_y_cerrar(ses: "_Sesion", session_id: str, bank_code: str, user_data: dict, guardar_datos: bool) -> dict:
    try:
        return await _pagar(ses, bank_code, user_data, guardar_datos)
    finally:
        await _cerrar_sesion(ses)
        _sesiones.pop(session_id, None)


def pagar(session_id: str, bank_code: str, user_data: dict, guardar_datos: bool = False) -> str:
    """
    Arranca el pago (llenar datos + esperar redirección) en segundo plano y
    devuelve un poll_id — mismo motivo que `iniciar`: llenar el formulario y
    esperar la redirección real puede tardar y no debe sostener la conexión.
    """
    ses = _sesiones.get(session_id)
    if not ses or not ses.viva():
        raise KeyError("sesión PSE expirada")
    _purgar_polls()
    poll = _Poll()
    poll.futuro = _worker.schedule(_pagar_y_cerrar(ses, session_id, bank_code, user_data, guardar_datos))
    _polls[poll.id] = poll
    return poll.id


def estado_pagar(poll_id: str) -> dict:
    poll = _polls.get(poll_id)
    if not poll:
        raise KeyError("sesión de pago expirada")
    if not poll.futuro.done():
        return {"estado": "consultando"}
    _polls.pop(poll_id, None)
    resultado = poll.futuro.result()   # puede relanzar la excepción original
    return {"estado": "listo", "redirect_url": resultado["redirect_url"]}


def cerrar(session_id: str) -> None:
    ses = _sesiones.pop(session_id, None)
    if ses:
        try:
            _worker.run(_cerrar_sesion(ses), timeout=30)
        except Exception:
            pass

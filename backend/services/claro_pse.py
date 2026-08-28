"""
Pago PSE de Claro (postpago), vía https://portalpagos.claro.com.co/.

A diferencia de Movistar (Cloudflare Turnstile, que detecta el navegador
automatizado sin importar quién interactúe con él), Claro protege su
formulario con reCAPTCHA v2 clásico ("No soy un robot") en dos pasos, y pide
además un código de verificación de 4 dígitos por SMS. Ninguno de los dos es
el bloqueo total que sí es Turnstile:

- El reCAPTCHA v2 se resuelve con 2Captcha (servicio pagado, token real) y se
  inyecta llenando el campo `g-recaptcha-response` como un campo de
  formulario normal — sin interceptar ni enganchar el JS del widget, que es
  la técnica que sí quedó bloqueada con Turnstile.
- El código SMS no se puede resolver por API: se le pide al dueño del
  contrato en tiempo real (mismo patrón interactivo que emcali_captcha.py),
  vía un estado intermedio "otp_requerido" que el frontend muestra como un
  campo de código.

Verificado con una corrida automatizada completa (2026-08-27): teléfono +
reCAPTCHA #1 → OTP real → lectura de factura + reCAPTCHA #2 → selección de
"PSE Débito Bancario PSE" en `_seleccionar_medio_pago_pse` → Confirmar →
lista de bancos → banco + datos personales → redirección real a
registro.pse.com.co. El bloqueo que parecía intermitente en corridas
anteriores ("no se puede completar tu solicitud", con tiempos totales muy
distintos entre intentos) no era un problema de tiempos ni un bloqueo
antifraude: era que ningún intento anterior seleccionaba ese medio de pago
antes de Confirmar, y el manejo de errores de Claro resetea todo el flujo al
paso 1 con un mensaje genérico en vez de señalar el campo vacío.
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta

from services.twocaptcha import resolver_recaptcha_v2

PORTAL_URL = (
    "https://portalpagos.claro.com.co/index.php?"
    "view=vistas/personal/claro/newclaro/inicio.php&id_objeto=61#no-back-button"
)
_TTL = timedelta(minutes=10)

_TIPOS_DOCUMENTO = {
    "CC": "C.C. (Cédula de Ciudadanía)",
    "CE": "C.E. (Cédula de Extranjería)",
    "NIT": "NIT",
    "PA": "Pasaporte",
    "TI": "T.I. (Tarjeta de Identidad)",
}


def _limpiar_lock_perfil(perfil: str) -> None:
    for nombre in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.remove(os.path.join(perfil, nombre))
        except FileNotFoundError:
            pass
        except OSError:
            pass


# ── Hilo con event loop propio (mismo patrón que movistar_pse.py) ───────────

class _BrowserWorker:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, daemon=True, name="claro-pse-browser").start()
                self._loop = loop
            return self._loop

    def schedule(self, coro):
        loop = self._ensure()
        return asyncio.run_coroutine_threadsafe(coro, loop)


_worker = _BrowserWorker()


class _Sesion:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.expira = datetime.utcnow() + _TTL
        self.playwright = None
        self.contexto = None
        self.page = None
        self.amount: float = 0.0
        self.due_date: str = ""
        self.reference: str = ""
        self.banks: list[dict] = []
        self.account_reference: str = ""
        self.tipo_servicio: str = "Postpago"
        self.intentos_confirmacion: int = 0

    def viva(self) -> bool:
        return self.expira > datetime.utcnow()


_sesiones: dict[str, _Sesion] = {}


def _purgar() -> None:
    for sid in [s for s, v in _sesiones.items() if not v.viva()]:
        ses = _sesiones.pop(sid, None)
        if ses:
            try:
                _worker.schedule(_cerrar_sesion(ses)).result(timeout=30)
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


async def _click_texto(page, texto: str, timeout: int = 4_000) -> bool:
    try:
        el = page.locator(f'text="{texto}"').first
        if await el.is_visible(timeout=timeout):
            await el.click()
            return True
    except Exception:
        pass
    return False


async def _click_texto_visible(page, texto: str, exact: bool = False) -> bool:
    """
    El portal de Claro repite varios textos en elementos ocultos (links de
    navegación, versiones para otros anchos de pantalla), así que buscar por
    texto y quedarse con el primer resultado a menudo agarra un elemento
    invisible. Recorre TODAS las coincidencias y hace clic en la primera que
    de verdad está visible.
    """
    try:
        candidatos = page.get_by_text(texto, exact=exact)
        for i in range(await candidatos.count()):
            el = candidatos.nth(i)
            if await el.is_visible():
                await el.click(timeout=2_000)
                return True
    except Exception:
        pass
    return False


async def _seleccionar_medio_pago_pse(page) -> bool:
    """
    En la página de confirmación, bajo "Selecciona el medio de pago", hay un
    campo que empieza vacío y hay que elegir explícitamente "PSE Débito
    Bancario PSE" antes del segundo reCAPTCHA y el Confirmar — si se deja
    vacío, Claro rechaza el Confirmar y resetea todo el flujo al paso 1 con un
    error genérico que no dice cuál campo falló (así se pasó por alto en
    varias corridas). Las opciones muestran logos (Nequi, Daviplata) junto al
    texto, algo que un <option> nativo no admite, así que es un desplegable
    propio que hay que abrir con clic, no un <select>.
    """
    try:
        sel = page.locator("select").first
        if await sel.count():
            opciones = await sel.locator("option").all_text_contents()
            for opt in opciones:
                if "pse" in opt.lower():
                    await sel.select_option(label=opt.strip())
                    return True
    except Exception:
        pass

    try:
        encabezado = page.locator('text="Selecciona el medio de pago"').first
        contenedor = encabezado.locator(
            "xpath=following::*[self::div or self::button or self::span or self::input][1]"
        ).first
        if await contenedor.count() and await contenedor.is_visible(timeout=2_000):
            await contenedor.click(timeout=3_000)
            await page.wait_for_timeout(600)
    except Exception:
        pass

    if await _click_texto_visible(page, "Débito Bancario PSE"):
        return True
    if await _click_texto_visible(page, "PSE"):
        return True
    return False


def _blocked(reason: str) -> dict:
    return {
        "estado": "bloqueado",
        "resultado": {"portal_blocked": True, "blocked_reason": reason},
    }


# ── Paso 1: teléfono + reCAPTCHA #1 → dispara el OTP ────────────────────────

async def _iniciar(ses: _Sesion, account_reference: str) -> dict:
    from patchright.async_api import async_playwright

    perfil = os.environ.get("CLARO_PSE_PROFILE_DIR", "/var/lib/finsmart/chrome-claro-pse")
    os.makedirs(perfil, exist_ok=True)
    _limpiar_lock_perfil(perfil)

    con_display = bool(os.environ.get("DISPLAY"))
    args_lanzamiento = [
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1500,1100",
        "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        "--ignore-gpu-blocklist", "--enable-webgl",
    ]
    ses.playwright = await async_playwright().start()
    ses.contexto = await ses.playwright.chromium.launch_persistent_context(
        user_data_dir=perfil, headless=not con_display, no_viewport=True,
        locale="es-CO", timezone_id="America/Bogota",
        args=args_lanzamiento,
    )
    page = ses.contexto.pages[0] if ses.contexto.pages else await ses.contexto.new_page()
    ses.page = page

    await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3_000)

    # Banner de cookies: tapa la parte baja de la página y bloquea clics
    # en el resto del formulario hasta que se acepta.
    try:
        await page.locator('text="Aceptar"').first.click(timeout=3_000)
        await page.wait_for_timeout(500)
    except Exception:
        pass

    return await _solicitar_otp(ses, page, account_reference, ses.tipo_servicio)


# Cuántas veces se vuelve a rellenar el paso 1 (y por tanto se dispara un SMS
# nuevo) si Claro rechaza el flujo tras el OTP con su error genérico de
# "no se puede completar tu solicitud" — ver _reintentar_o_rendirse. La causa
# más común de ese rechazo (no seleccionar el medio de pago PSE antes de
# Confirmar) ya está resuelta en _seleccionar_medio_pago_pse; este reintento
# queda como red de seguridad ante cualquier otro rechazo transitorio.
_MAX_REINTENTOS_CONFIRMACION = 2


# Cada tipo de servicio (Postpago, Hogar y Multiplay, Equipo, IoT) usa una
# etiqueta distinta para el campo de cuenta/referencia.
_ETIQUETA_CAMPO_CUENTA = {
    "Postpago": "Número de celular",
    "Hogar y Multiplay": "Número de cuenta o referencia",
}


async def _elegir_tipo_servicio(page, tipo_servicio: str) -> bool:
    """
    Cada tipo de servicio es una tarjeta con un <input type="radio"> oculto
    (clip:rect(0,0,0,0), sin bounding box) dentro de un
    <label class="custom-radio-checkbox">, hermano — no ancestro — del <h3>
    con el nombre visible (Postpago, Hogar y Multiplay, ...); clickear el
    label es lo único que dispara el radio nativo. Para elegir la tarjeta
    correcta (no siempre la primera) se busca, para cada label, el texto del
    contenedor que lo envuelve a distintas profundidades, hasta encontrar uno
    que mencione el tipo de servicio pedido.
    """
    labels = page.locator("label.custom-radio-checkbox")
    n = await labels.count()
    for i in range(n):
        lbl = labels.nth(i)
        for ancestro in ("..", "../..", "../../.."):
            try:
                contenedor = lbl.locator(f"xpath={ancestro}").first
                texto = (await contenedor.inner_text()).strip()
            except Exception:
                continue
            if tipo_servicio.lower() in texto.lower():
                await lbl.click(timeout=3_000)
                return True
    return False


async def _solicitar_otp(ses: _Sesion, page, account_reference: str, tipo_servicio: str = "Postpago") -> dict:
    """
    Rellena el paso 1 (tipo de servicio, celular, reCAPTCHA #1, Continuar) y
    espera a que aparezcan las casillas del código SMS. Se usa tanto para el
    intento inicial como para los reintentos automáticos tras un timeout en
    la página de confirmación — en ese caso Claro ya deja la MISMA página
    reseteada de vuelta a este paso, así que no hace falta volver a navegar
    ni aceptar cookies otra vez.
    """
    # "Selecciona la opción de tu interés" -> "Pago de Facturas": es un
    # combobox propio (sin <select> nativo), hay que abrirlo con clic. Elegir
    # esta opción ya revela, en la MISMA vista, los radios de tipo de
    # servicio — no hay que darle "Continuar" todavía (hacerlo antes de
    # elegir el tipo de servicio dispara "Verificación Incorrecta del
    # captcha" con el formulario a medio llenar).
    if not await _click_texto_visible(page, "Selecciona la opción de tu interés"):
        return _blocked("No se encontró el combo inicial del portal de Claro.")
    await page.wait_for_timeout(500)
    if not await _click_texto_visible(page, "Pago de Facturas"):
        return _blocked("No se encontró la opción 'Pago de Facturas' en el portal de Claro.")
    await page.wait_for_timeout(1_000)

    if not await _elegir_tipo_servicio(page, tipo_servicio):
        try:
            await page.screenshot(path="/tmp/claro_tipo_servicio_no_encontrado.png", full_page=True)
        except Exception:
            pass
        return _blocked(f"No se encontró la opción '{tipo_servicio}' en el portal de Claro.")
    await page.wait_for_timeout(800)

    etiqueta_campo = _ETIQUETA_CAMPO_CUENTA.get(tipo_servicio, "Número de celular")
    telefono = re.sub(r"\D", "", account_reference)
    campo = None
    try:
        candidato = page.locator(f'text="{etiqueta_campo}"').first.locator(
            "xpath=following::input[1]"
        ).first
        if await candidato.count() and await candidato.is_visible(timeout=1_500):
            campo = candidato
    except Exception:
        pass
    if campo is None:
        for sel in ('input[type="tel"]', 'input[placeholder]', 'input[type="text"]'):
            loc = page.locator(sel).last
            try:
                if await loc.count() and await loc.is_visible(timeout=1_500):
                    campo = loc
                    break
            except Exception:
                continue
    if campo is None:
        return _blocked("No se encontró el campo de número de celular en el portal de Claro.")
    await campo.click()
    await campo.fill("")
    await campo.type(telefono, delay=80)
    await page.wait_for_timeout(800)

    try:
        await resolver_recaptcha_v2(page, PORTAL_URL)
    except Exception as exc:
        return _blocked(f"No se pudo resolver el reCAPTCHA de Claro: {exc}")

    # El clic en "Continuar" dispara un envío por AJAX que puede hacer que el
    # botón cambie de estado o desaparezca justo cuando se revisa si sigue
    # visible — eso no significa que el envío haya fallado. La señal real de
    # éxito es que aparezcan las casillas del código: se confirmó por SMS
    # real que Claro sí lo envía incluso cuando este chequeo daba falso
    # negativo por esperar muy poco tiempo o buscar el texto equivocado —
    # ahora se espera más y se prioriza la aparición de las casillas
    # (input[maxlength="1"], el mismo selector que las llena después) sobre
    # el texto, que puede variar ("4 dígitos" vs "cuatro dígitos", etc.).
    await _click_texto(page, "Continuar")
    await page.wait_for_timeout(1_500)

    llego_otp = False
    for _ in range(40):
        if await page.locator('input[maxlength="1"]').count() >= 4:
            llego_otp = True
            break
        if await page.locator('text="código"').first.count():
            llego_otp = True
            break
        await page.wait_for_timeout(1_000)
    if not llego_otp:
        try:
            await page.screenshot(path="/tmp/claro_sin_otp.png", full_page=True)
        except Exception:
            pass
        return _blocked("Claro no envió el código de verificación (o cambió el formulario).")

    return {"estado": "otp_requerido", "session_id": ses.id}


async def _reintentar_o_rendirse(ses: _Sesion, motivo: str) -> dict:
    """
    Punto único de recuperación cuando Claro rechaza el flujo tras el código
    OTP y resetea la página al paso 1 (ya sea porque el código llegó vencido
    o porque la página de confirmación caducó esperando a 2Captcha). Vuelve a
    rellenar el paso 1 sobre la MISMA página — dispara un SMS nuevo — hasta
    un tope de reintentos; si se agota, se rinde con un mensaje explícito.
    """
    ses.intentos_confirmacion += 1
    if ses.intentos_confirmacion > _MAX_REINTENTOS_CONFIRMACION:
        return _blocked(
            f"{motivo} Se reintentó {_MAX_REINTENTOS_CONFIRMACION} veces solicitando un código nuevo "
            "y todas las veces Claro rechazó el flujo de la misma forma."
        )
    try:
        return await _solicitar_otp(ses, ses.page, ses.account_reference, ses.tipo_servicio)
    except Exception as exc:
        return _blocked(f"{motivo} El reintento automático también falló: {exc}")


# ── Paso 2: código OTP + reCAPTCHA #2 → llega al formulario PSE ─────────────

async def _continuar_con_otp(ses: _Sesion, codigo: str) -> dict:
    page = ses.page
    if page is None:
        raise RuntimeError("Sesión sin página abierta.")

    digitos = re.sub(r"\D", "", codigo)[:4]
    if len(digitos) != 4:
        return _blocked("El código de verificación debe tener 4 dígitos.")

    cajas = page.locator('input[maxlength="1"]')
    n = await cajas.count()
    if n >= 4:
        # Las casillas (pinCode1..4) aparecen en el DOM ya al enviar el SMS,
        # pero quedan `disabled` unos segundos más mientras el portal termina
        # de procesar el envío — hay que esperar a que se habiliten, no solo
        # a que existan, o el primer clic agota el timeout de Playwright.
        primera = cajas.nth(0)
        for _ in range(30):
            if await primera.is_enabled():
                break
            await page.wait_for_timeout(1_000)
        else:
            return _blocked("El campo del código de verificación de Claro nunca se habilitó.")
        for i, d in enumerate(digitos):
            await cajas.nth(i).click(timeout=5_000)
            await cajas.nth(i).type(d, delay=100)
    else:
        # Respaldo: un solo campo para los 4 dígitos.
        campo_otp = page.locator('input[type="text"], input[type="tel"], input[type="number"]').last
        await campo_otp.click()
        await campo_otp.type(digitos, delay=100)
    await page.wait_for_timeout(600)

    t0 = time.monotonic()
    def _log(msg: str) -> None:
        print(f"[claro-pse] +{time.monotonic() - t0:5.1f}s {msg}", flush=True)

    ok_continuar = await _click_texto(page, "Continuar")
    _log(f"clic Continuar tras OTP: {ok_continuar}, url={page.url}")
    if not ok_continuar:
        return _blocked("No se encontró el botón 'Continuar' tras ingresar el código de Claro.")
    await page.wait_for_timeout(2_500)

    # El widget del segundo reCAPTCHA no existe hasta que se llega a esta
    # página, así que no se puede lanzar su resolución antes — pero sí en
    # paralelo con la lectura de los datos de la factura (que no depende de
    # él) en vez de esperar a que esa lectura termine primero, para no sumar
    # tiempo de más al flujo.
    recaptcha_task = asyncio.create_task(resolver_recaptcha_v2(page, PORTAL_URL))

    # Página de detalle de factura: monto, fecha límite, referencia.
    texto_pagina = await page.content()
    tiene_error_generico = "no se puede completar tu solicitud" in texto_pagina.lower()
    _log(f"leyendo pagina de factura, error_generico_visible={tiene_error_generico}, len_html={len(texto_pagina)}")
    monto_match = re.search(r"\$\s?([\d.,]+)", texto_pagina)
    if not monto_match:
        recaptcha_task.cancel()
        if tiene_error_generico:
            return await _reintentar_o_rendirse(
                ses, "Claro rechazó el código de verificación (mostró 'no se puede completar tu "
                "solicitud' y volvió al paso 1)."
            )
        return _blocked("No se pudo leer el monto de la factura en el portal de Claro (¿código incorrecto o vencido?).")
    monto = float(re.sub(r"[.,](?=\d{3}(?:\D|$))", "", monto_match.group(1)).replace(",", "."))
    _log(f"monto leido: {monto}")

    fecha_match = re.search(r"Pague antes de:\s*([\d/]+)", texto_pagina)
    referencia_match = re.search(r"Referencia de pago:\s*\**?(\d+)", texto_pagina)
    ses.amount = monto
    ses.due_date = fecha_match.group(1) if fecha_match else str(date.today() + timedelta(days=15))
    ses.reference = f"CLARO-{referencia_match.group(1) if referencia_match else ses.id[:8]}"

    try:
        await recaptcha_task
        _log("segundo recaptcha resuelto OK")
    except Exception as exc:
        _log(f"segundo recaptcha FALLO: {exc!r}")
        return _blocked(f"No se pudo resolver el segundo reCAPTCHA de Claro: {exc}")

    medio_pago_ok = await _seleccionar_medio_pago_pse(page)
    _log(f"medio de pago 'PSE' seleccionado: {medio_pago_ok}")
    if not medio_pago_ok:
        try:
            await page.screenshot(path="/tmp/claro_medio_pago_no_encontrado.png", full_page=True)
        except Exception:
            pass
        return _blocked("No se pudo seleccionar 'PSE Débito Bancario PSE' como medio de pago en Claro.")

    ok_confirmar = await _click_texto(page, "Confirmar")
    _log(f"clic Confirmar: {ok_confirmar}")
    if not ok_confirmar:
        return _blocked("No se encontró el botón 'Confirmar' de la factura en Claro.")
    await page.wait_for_timeout(2_500)

    texto_tras_confirmar = await page.content()
    if "no se puede completar tu solicitud" in texto_tras_confirmar.lower():
        _log(f"Claro rechazo el Confirmar y volvio al paso 1 (intento {ses.intentos_confirmacion + 1})")
        try:
            await page.screenshot(path="/tmp/claro_tras_confirmar_rechazado.png", full_page=True)
        except Exception:
            pass
        return await _reintentar_o_rendirse(
            ses, "Claro rechazó la confirmación del pago y volvió al paso 1 con un error genérico "
            "que no señala qué falló."
        )

    # Formulario PSE: leer bancos del <select> "Banco o Billetera digital".
    banks: list[dict] = []
    try:
        sel_banco = page.locator("select").first
        opciones = await sel_banco.locator("option").all_text_contents()
        banks = [{"code": o.strip(), "name": o.strip()} for o in opciones if o.strip()]
    except Exception:
        pass
    _log(f"bancos leidos: {len(banks)}")

    if not banks:
        try:
            await page.screenshot(path="/tmp/claro_pse_bancos.png", full_page=True)
        except Exception:
            pass
        return _blocked("No se pudo leer la lista de bancos en el formulario PSE de Claro.")

    ses.banks = banks
    return {
        "estado": "listo",
        "session_id": ses.id,
        "banks": banks,
        "amount": ses.amount,
        "due_date": ses.due_date,
        "reference": ses.reference,
    }


# ── Paso 3: datos personales → redirección al banco ─────────────────────────

async def _pagar(ses: _Sesion, bank_code: str, user_data: dict) -> dict:
    page = ses.page
    if page is None:
        raise RuntimeError("Sesión sin página abierta.")

    try:
        sel_banco = page.locator("select").first
        await sel_banco.select_option(label=bank_code)
    except Exception:
        raise ValueError("No se pudo seleccionar el banco indicado en el portal de Claro.")
    await page.wait_for_timeout(500)

    faltantes = []
    try:
        await _fill_por_label(page, "Nombre del Titular", user_data.get("full_name") or "")
    except Exception:
        faltantes.append("Nombre del Titular")

    tipo_doc = _TIPOS_DOCUMENTO.get((user_data.get("identification_type") or "CC").upper(), "C.C. (Cédula de Ciudadanía)")
    try:
        sel_doc_tipo = page.locator("select").nth(2)
        await sel_doc_tipo.select_option(label=tipo_doc)
    except Exception:
        pass

    numero_doc = user_data.get("identification_number") or ""
    if numero_doc:
        if not await _fill_por_label(page, "Número de Documento", numero_doc):
            faltantes.append("Número de Documento")
    else:
        faltantes.append("Número de Documento")

    correo = user_data.get("email") or ""
    if correo:
        if not await _fill_por_label(page, "Correo Electrónico", correo):
            faltantes.append("Correo Electrónico")
    else:
        faltantes.append("Correo Electrónico")

    if faltantes:
        raise ValueError(
            "No se pudieron llenar estos campos en el formulario PSE de Claro: "
            + ", ".join(faltantes)
        )

    url_antes = page.url
    if not await _click_texto(page, "Confirmar"):
        raise ValueError("No se encontró el botón 'Confirmar' final en el portal de Claro.")

    redirect_url = ""
    for _ in range(20):
        await page.wait_for_timeout(1_000)
        if page.url != url_antes:
            redirect_url = page.url
            break
    if not redirect_url:
        raise ValueError("Claro no redirigió a la pasarela del banco tras el pago.")

    return {"redirect_url": redirect_url}


async def _fill_por_label(page, etiqueta: str, valor: str) -> bool:
    try:
        campo = page.get_by_label(etiqueta, exact=False).first
        if await campo.count() and await campo.is_visible(timeout=1_500):
            await campo.fill(valor)
            return True
    except Exception:
        pass
    try:
        bloque = page.locator(f'text="{etiqueta}"').first.locator(
            "xpath=following::input[1]"
        ).first
        if await bloque.count() and await bloque.is_visible(timeout=1_500):
            await bloque.fill(valor)
            return True
    except Exception:
        pass
    return False


# ── API pública (síncrona, con sondeo) ───────────────────────────────────────

class _Poll:
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


def iniciar(account_reference: str, tipo_servicio: str = "Postpago") -> dict:
    _purgar()
    _purgar_polls()
    ses = _Sesion()
    ses.account_reference = account_reference
    ses.tipo_servicio = tipo_servicio
    _sesiones[ses.id] = ses
    poll = _Poll()

    async def _tarea():
        try:
            return await _iniciar(ses, account_reference)
        except Exception:
            _sesiones.pop(ses.id, None)
            await _cerrar_sesion(ses)
            raise

    poll.futuro = _worker.schedule(_tarea())
    _polls[poll.id] = poll
    return {"estado": "consultando", "poll_id": poll.id}


def estado_iniciar(poll_id: str) -> dict:
    poll = _polls.get(poll_id)
    if not poll:
        raise KeyError("sesión de consulta expirada")
    if not poll.futuro.done():
        return {"estado": "consultando"}
    _polls.pop(poll_id, None)
    return poll.futuro.result()


def enviar_otp(session_id: str, codigo: str) -> dict:
    ses = _sesiones.get(session_id)
    if not ses or not ses.viva():
        raise KeyError("sesión de Claro expirada")
    _purgar_polls()
    poll = _Poll()

    async def _tarea():
        try:
            return await _continuar_con_otp(ses, codigo)
        except Exception:
            _sesiones.pop(session_id, None)
            await _cerrar_sesion(ses)
            raise

    poll.futuro = _worker.schedule(_tarea())
    _polls[poll.id] = poll
    return {"estado": "consultando", "poll_id": poll.id}


def estado_otp(poll_id: str) -> dict:
    poll = _polls.get(poll_id)
    if not poll:
        raise KeyError("sesión de verificación expirada")
    if not poll.futuro.done():
        return {"estado": "consultando"}
    _polls.pop(poll_id, None)
    return poll.futuro.result()


async def _pagar_y_cerrar(ses: _Sesion, session_id: str, bank_code: str, user_data: dict) -> dict:
    try:
        return await _pagar(ses, bank_code, user_data)
    finally:
        await _cerrar_sesion(ses)
        _sesiones.pop(session_id, None)


def pagar(session_id: str, bank_code: str, user_data: dict) -> str:
    ses = _sesiones.get(session_id)
    if not ses or not ses.viva():
        raise KeyError("sesión PSE de Claro expirada")
    _purgar_polls()
    poll = _Poll()
    poll.futuro = _worker.schedule(_pagar_y_cerrar(ses, session_id, bank_code, user_data))
    _polls[poll.id] = poll
    return poll.id


def estado_pagar(poll_id: str) -> dict:
    poll = _polls.get(poll_id)
    if not poll:
        raise KeyError("sesión de pago expirada")
    if not poll.futuro.done():
        return {"estado": "consultando"}
    _polls.pop(poll_id, None)
    resultado = poll.futuro.result()
    return {"estado": "listo", "redirect_url": resultado["redirect_url"]}


def cerrar(session_id: str) -> None:
    ses = _sesiones.pop(session_id, None)
    if ses:
        try:
            _worker.schedule(_cerrar_sesion(ses)).result(timeout=30)
        except Exception:
            pass

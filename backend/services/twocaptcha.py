"""
Cliente mínimo de 2Captcha para resolver reCAPTCHA v2, compartido entre los
scrapers que lo necesitan (Claro, EMCALI). El token se inyecta llenando el
campo oculto `g-recaptcha-response` como un campo de formulario normal — el
mismo campo que la librería de Google usa como salida oficial del widget, así
que cualquier validación server-side que lea ese campo (la forma estándar de
integrar reCAPTCHA, con o sin framework) lo acepta igual que si lo hubiera
resuelto un usuario. No se interviene el JS del widget ni su callback.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time

import httpx


def _parsear_2captcha(texto: str) -> dict:
    texto = texto.strip()
    try:
        return json.loads(texto)
    except Exception:
        pass
    if texto == "CAPCHA_NOT_READY":
        return {"status": 0, "request": "CAPCHA_NOT_READY"}
    if texto.startswith("OK|"):
        return {"status": 1, "request": texto.split("|", 1)[1]}
    return {"status": 0, "request": texto}


def resolver_recaptcha_v2_sync(sitekey: str, pageurl: str) -> str:
    api_key = os.environ.get("TWOCAPTCHA_API_KEY")
    if not api_key:
        raise RuntimeError("Falta configurar TWOCAPTCHA_API_KEY para resolver el reCAPTCHA.")
    r = httpx.get("https://2captcha.com/in.php", params={
        "key": api_key, "method": "userrecaptcha",
        "googlekey": sitekey, "pageurl": pageurl, "json": 1,
    }, timeout=30)
    data = _parsear_2captcha(r.text)
    if data.get("status") != 1:
        raise RuntimeError(f"2Captcha rechazó la solicitud de reCAPTCHA: {data}")
    req_id = data["request"]

    for _ in range(40):
        time.sleep(5)
        r2 = httpx.get("https://2captcha.com/res.php", params={
            "key": api_key, "action": "get", "id": req_id, "json": 1,
        }, timeout=30)
        d2 = _parsear_2captcha(r2.text)
        if d2.get("status") == 1:
            return d2["request"]
        if d2.get("request") != "CAPCHA_NOT_READY":
            raise RuntimeError(f"2Captcha devolvió un error: {d2}")
    raise RuntimeError("2Captcha no resolvió el reCAPTCHA a tiempo.")


async def resolver_recaptcha_v2(page, pageurl: str) -> None:
    """
    Ubica el sitekey del widget de reCAPTCHA v2 visible en la página, lo manda
    resolver a 2Captcha, y llena el campo oculto `g-recaptcha-response` con el
    token — igual que se llenaría cualquier otro campo de un formulario. No
    interactúa con el checkbox visual ni con el JS del widget.
    """
    sitekey = None
    for _intento in range(10):
        for f in page.frames:
            if "recaptcha" in f.url and "k=" in f.url:
                m = re.search(r"[?&]k=([^&]+)", f.url)
                if m:
                    sitekey = m.group(1)
                    break
        if sitekey:
            break
        await page.wait_for_timeout(500)
    if not sitekey:
        raise RuntimeError("No se encontró el reCAPTCHA en la página.")

    token = await asyncio.to_thread(resolver_recaptcha_v2_sync, sitekey, pageurl)

    ok = await page.evaluate(
        """
        (token) => {
            let el = document.getElementById('g-recaptcha-response')
                || document.querySelector('textarea[name="g-recaptcha-response"]');
            if (!el) return false;
            const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            setter.call(el, token);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }
        """,
        token,
    )
    if not ok:
        raise RuntimeError("No se encontró el campo de respuesta del reCAPTCHA para llenarlo.")
    await page.wait_for_timeout(500)

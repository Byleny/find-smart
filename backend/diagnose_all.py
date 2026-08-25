"""
Diagnóstico integral de todos los portales de pago.

Verifica browser launch, conectividad, carga del portal y respuesta mínima
del scraper — SIN necesitar una factura pendiente.

Uso dentro del contenedor:
  docker compose exec backend python diagnose_all.py

Opcionalmente pasa contratos específicos por proveedor:
  docker compose exec backend python diagnose_all.py \\
      --gdo 610257 --emcali 123456 --epm 789 --codensa 0001 --movistar 3001234567
"""

import argparse
import asyncio
import sys
import time
import traceback

# ── CLI ───────────────────────────────────────────────────────────────────────

p = argparse.ArgumentParser(add_help=True)
p.add_argument("--gdo",      default="610257",    metavar="REF")
p.add_argument("--emcali",   default="123456",    metavar="REF")
p.add_argument("--epm",      default="00001",     metavar="REF")
p.add_argument("--codensa",  default="00001",     metavar="REF")
p.add_argument("--movistar", default="3001234567", metavar="REF")
ARGS = p.parse_args()

OK  = "  ✓"
ERR = "  ✗"
WRN = "  ⚠"


def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def ok(msg: str, detail: str = "") -> None:
    print(f"{OK} {msg}" + (f": {detail}" if detail else ""))


def err(msg: str, detail: str = "") -> None:
    print(f"{ERR} {msg}" + (f": {detail}" if detail else ""))


def wrn(msg: str, detail: str = "") -> None:
    print(f"{WRN} {msg}" + (f": {detail}" if detail else ""))


# ── 1. Browser launch ─────────────────────────────────────────────────────────

async def _test_browser_launch() -> bool:
    section("1. Browser launch (patchright headless Chromium)")
    try:
        from patchright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            ctx  = await browser.new_context()
            page = await ctx.new_page()
            await page.goto("about:blank")
            ua   = await page.evaluate("navigator.userAgent")
            await browser.close()
        ok("Browser headless lanzado", ua[:60])
        return True
    except Exception as exc:
        err("Browser launch fallido", str(exc)[:200])
        return False


# ── 2. Conectividad HTTP básica ───────────────────────────────────────────────

import httpx

PORTALS = {
    "gdo":      "https://portalrecaudos.promigas.com/api/nonce",
    "emcali":   "https://pagos.emcali.com.co/pagosweb/checkout",
    "epm":      "https://www.epm.com.co/site/home/institucional/nuestros-servicios/personas/como-pagar/canales-de-pago/portal-de-pagos",
    "codensa":  "https://www.enelcol.com.co/",
    "movistar": "https://payment.movistar.co/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "es-CO,es;q=0.9",
}


def test_connectivity() -> dict[str, bool]:
    section("2. Conectividad HTTP básica (sin browser)")
    results = {}
    for name, url in PORTALS.items():
        try:
            r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if r.status_code < 500:
                ok(f"{name.upper():10} HTTP {r.status_code}", url[:55])
                results[name] = True
            else:
                wrn(f"{name.upper():10} HTTP {r.status_code}", url[:55])
                results[name] = False
        except Exception as exc:
            err(f"{name.upper():10} sin respuesta", str(exc)[:100])
            results[name] = False
    return results


# ── 3. GDO API completo ───────────────────────────────────────────────────────

def test_gdo(referencia: str) -> None:
    section(f"3. GDO API — contrato {referencia}")
    try:
        from services.scraper_service import GDOScraper
        scraper = GDOScraper()
        t0 = time.time()
        result = scraper.fetch_invoice(referencia)
        elapsed = time.time() - t0
        if result.is_up_to_date:
            ok(f"Al día ({elapsed:.1f}s)", f"sin factura pendiente para {referencia}")
        elif result.portal_blocked:
            wrn(f"Portal bloqueado ({elapsed:.1f}s)", result.blocked_reason[:120])
        else:
            ok(f"Factura encontrada ({elapsed:.1f}s)",
               f"monto=${result.amount:,.0f}  ref={result.reference}")
    except Exception as exc:
        err("GDO falló", str(exc)[:200])
        traceback.print_exc()


# ── 4. EMCALI — prueba de carga de portal y captcha ──────────────────────────

async def _emcali_probe(contrato: str) -> None:
    """Abre el portal de EMCALI headless y verifica que carga correctamente."""
    from patchright.async_api import async_playwright
    import os

    perfil = os.environ.get("EMCALI_PROFILE_DIR", "/var/lib/finsmart/chrome-emcali")
    os.makedirs(perfil, exist_ok=True)

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=perfil,
            headless=True,
            no_viewport=True,
            locale="es-CO",
            timezone_id="America/Bogota",
            args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1400,900"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            r = await page.goto(
                "https://pagos.emcali.com.co/pagosweb/checkout",
                wait_until="domcontentloaded", timeout=40_000,
            )
            ok("Portal EMCALI cargado", f"HTTP {r.status if r else '?'}")
            await page.wait_for_timeout(4_000)

            # Campo de contrato
            campo = None
            for sel in ('input[placeholder*="123"]', 'input[formcontrolname="contrato"]',
                        'input[type="text"]', "input"):
                loc = page.locator(sel).first
                try:
                    if await loc.is_visible(timeout=3_000):
                        campo = loc
                        break
                except Exception:
                    pass

            if campo:
                ok("Campo de contrato visible")
                await campo.fill(contrato)
                ok("Contrato ingresado", contrato)
            else:
                wrn("Campo de contrato no encontrado (portal puede haber cambiado)")

            # Política de datos
            try:
                cb = page.locator('input[type="checkbox"]').first
                if await cb.count() and not await cb.is_checked():
                    await cb.check(timeout=4_000)
                    ok("Política de datos aceptada")
                else:
                    ok("Checkbox de política ya marcado o ausente")
            except Exception as exc:
                wrn("Checkbox política", str(exc)[:80])

            # reCAPTCHA
            try:
                await page.wait_for_selector('iframe[title="reCAPTCHA"]', timeout=12_000)
                ok("reCAPTCHA iframe cargado")

                marco = page.frame_locator('iframe[title="reCAPTCHA"]').first
                ancla = marco.locator("#recaptcha-anchor")
                await ancla.wait_for(state="visible", timeout=6_000)
                ok("Ancla del checkbox reCAPTCHA visible — flujo interactivo listo")
            except Exception as exc:
                wrn("reCAPTCHA no cargó", str(exc)[:120])

        finally:
            await ctx.close()


def test_emcali(contrato: str) -> None:
    section(f"4. EMCALI portal probe — contrato {contrato}")
    try:
        t0 = time.time()
        asyncio.run(_emcali_probe(contrato))
        ok(f"Probe completado", f"{time.time()-t0:.1f}s")
    except Exception as exc:
        err("EMCALI probe falló", str(exc)[:200])
        traceback.print_exc()


# ── 5. EPM / Codensa / Movistar — scraper genérico ───────────────────────────

def test_playwright_scraper(name: str, ref: str) -> None:
    section(f"5/{name.upper()} — scraper con Playwright")
    try:
        from services.scraper_service import PROVIDER_REGISTRY
        scraper = PROVIDER_REGISTRY.get(name)
        if scraper is None:
            err(f"{name} no está en el registry")
            return
        t0 = time.time()
        result = scraper.fetch_invoice(ref)
        elapsed = time.time() - t0
        if result.is_up_to_date:
            ok(f"Al día ({elapsed:.1f}s)")
        elif result.portal_blocked:
            wrn(f"Portal bloqueado ({elapsed:.1f}s)", result.blocked_reason[:120])
        else:
            ok(f"Factura encontrada ({elapsed:.1f}s)",
               f"monto=${result.amount:,.0f}  ref={result.reference}")
    except Exception as exc:
        err(f"{name.upper()} falló", str(exc)[:200])
        traceback.print_exc()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{'='*60}")
    print("  Diagnóstico integral — todos los portales de pago")
    print(f"{'='*60}")

    browser_ok = await _test_browser_launch()
    conn       = test_connectivity()

    test_gdo(ARGS.gdo)

    if browser_ok:
        test_emcali(ARGS.emcali)
        for provider in ("epm", "codensa", "movistar"):
            ref = getattr(ARGS, provider)
            test_playwright_scraper(provider, ref)
    else:
        wrn("Browser no arrancó — saltando pruebas que requieren Playwright")

    print(f"\n{'='*60}")
    print("  Diagnóstico completo.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())

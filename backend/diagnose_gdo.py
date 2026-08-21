"""
Script de diagnóstico GDO — ejecutar dentro del contenedor:
  docker compose exec backend python diagnose_gdo.py [número_contrato]

Reporta:
  - Conectividad al portal
  - Estado de carga de la página
  - Frames y inputs detectados en cada uno
  - Screenshot guardado en /tmp/gdo_diag.png
  - HTML del body en /tmp/gdo_body.html
"""

import asyncio
import sys
import json
from datetime import datetime

CONTRACT = sys.argv[1] if len(sys.argv) > 1 else "610257"
PORTAL   = "https://portalrecaudos.gdo.com.co/"


async def diagnose():
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

    report = {
        "timestamp":   datetime.now().isoformat(),
        "contract":    CONTRACT,
        "portal_url":  PORTAL,
        "steps":       [],
        "conclusion":  "",
    }

    def step(name: str, ok: bool, detail: str = ""):
        entry = {"step": name, "ok": ok, "detail": detail}
        report["steps"].append(entry)
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}: {detail}")
        return ok

    print(f"\n{'='*60}")
    print(f"  Diagnóstico GDO — contrato {CONTRACT}")
    print(f"{'='*60}\n")

    # ── 1. Conectividad básica ────────────────────────────────────────────────
    print("[1] Conectividad")
    try:
        import urllib.request
        req = urllib.request.Request(
            PORTAL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                step("HTTP GET portal", True, f"status {r.status}")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                step("HTTP GET portal", True, f"403 Forbidden — portal bloquea Python/urllib pero Playwright (Chromium real) puede pasar. Continuando...")
            elif e.code in (301, 302):
                step("HTTP GET portal", True, f"redirect {e.code} — OK")
            else:
                step("HTTP GET portal", False, f"HTTP {e.code} — posible problema de red")
                if e.code >= 500:
                    report["conclusion"] = "Portal devuelve error de servidor. Puede estar caído."
                    _print_report(report)
                    return
    except Exception as e:
        step("HTTP GET portal", False, str(e))
        report["conclusion"] = "Sin conectividad al portal — verificar red del contenedor."
        _print_report(report)
        return

    # ── 2. Playwright ─────────────────────────────────────────────────────────
    print("\n[2] Playwright + carga de página")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-CO",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()

        # Intercept responses
        network_log = []
        page.on("response", lambda r: network_log.append((r.status, r.url[:80])))

        # ── 2a. goto ─────────────────────────────────────────────────────────
        try:
            resp = await page.goto(PORTAL, wait_until="load", timeout=45_000)
            step("goto(load)", True, f"status={resp.status if resp else '?'}")
        except Exception as e:
            step("goto(load)", False, str(e))
            report["conclusion"] = "Playwright no pudo cargar la página."
            _print_report(report)
            await browser.close()
            return

        # ── 2b. networkidle ───────────────────────────────────────────────────
        try:
            await page.wait_for_load_state("networkidle", timeout=12_000)
            step("networkidle", True)
        except Exception:
            step("networkidle", False, "timeout — portal sigue haciendo polling (normal)")

        # ── 2c. Título y URL ──────────────────────────────────────────────────
        title = await page.title()
        url   = page.url
        step("Título página", bool(title), f"{title!r} | url={url[:60]!r}")

        # ── 2d. Detección de bot WAF ──────────────────────────────────────────
        body_text = (await page.content()).lower()
        waf_hits = [p for p in (
            "just a moment", "cloudflare", "checking your browser",
            "ddos protection", "access denied", "enable javascript",
            "verifying you are human", "cf-browser-verification",
        ) if p in body_text]
        step("Sin WAF/bot-detection", len(waf_hits) == 0,
             f"detectado: {waf_hits}" if waf_hits else "limpio")

        # ── 2e. Screenshots ───────────────────────────────────────────────────
        try:
            await page.screenshot(path="/tmp/gdo_diag.png", full_page=False)
            step("Screenshot guardado", True, "/tmp/gdo_diag.png")
        except Exception as e:
            step("Screenshot", False, str(e))

        # ── 2f. Guardar HTML ──────────────────────────────────────────────────
        html = await page.content()
        with open("/tmp/gdo_body.html", "w", encoding="utf-8") as f:
            f.write(html)
        step("HTML guardado", True, f"/tmp/gdo_body.html ({len(html)} bytes)")

        # ── 3. Análisis de frames e inputs ────────────────────────────────────
        print("\n[3] Frames e inputs")
        frames_data = []
        for i, frame in enumerate(page.frames):
            finfo = {
                "index": i,
                "url": frame.url[:70] if frame.url else "(sin url)",
                "inputs": [],
            }
            try:
                all_inputs = await frame.locator("input").all()
                for inp in all_inputs[:8]:
                    try:
                        finfo["inputs"].append({
                            "type":        await inp.get_attribute("type") or "(none)",
                            "name":        await inp.get_attribute("name") or "",
                            "placeholder": await inp.get_attribute("placeholder") or "",
                            "id":          await inp.get_attribute("id") or "",
                            "visible":     await inp.is_visible(timeout=500),
                        })
                    except Exception:
                        finfo["inputs"].append({"error": "no se pudo leer"})
            except Exception as e:
                finfo["error"] = str(e)
            frames_data.append(finfo)

            visible_count = sum(1 for x in finfo["inputs"] if x.get("visible"))
            total_count   = len(finfo["inputs"])
            print(f"  frame[{i}] {finfo['url']}")
            print(f"    inputs total={total_count} visibles={visible_count}")
            for x in finfo["inputs"][:5]:
                if "error" not in x:
                    print(f"      type={x['type']!r:10} name={x['name']!r:15} "
                          f"ph={x['placeholder']!r:20} visible={x['visible']}")

        report["frames"] = frames_data

        # ── 3b. ¿Hay algún input visible? ─────────────────────────────────────
        any_visible = any(
            x.get("visible")
            for fd in frames_data
            for x in fd.get("inputs", [])
        )
        step("Al menos un input visible", any_visible)

        # ── 4. Esperar input con timeout largo ────────────────────────────────
        print("\n[4] Espera activa de input (hasta 30s)")
        if not any_visible:
            waited = False
            for sel in ['input[type="text"]', 'input[type="number"]', 'input']:
                try:
                    await page.wait_for_selector(sel, state="visible", timeout=30_000)
                    waited = True
                    step(f"Input encontrado tras espera ({sel})", True)
                    break
                except Exception:
                    pass
            if not waited:
                step("Input encontrado tras espera", False,
                     "Ni con 30s aparece un input — el portal puede requerir JS especial")
        else:
            step("Input ya visible (no hace falta espera)", True)

        # ── 5. Intentar llenar el campo de contrato ────────────────────────────
        print("\n[5] Probar llenado de campo")
        fill_ok = False
        for frame in [page] + [f for f in page.frames if f != page.main_frame]:
            for sel in [
                'input[placeholder*="contrato" i]',
                'input[placeholder*="referencia" i]',
                'input[placeholder*="eje" i]',
                'input[type="text"]:visible',
                'input[type="number"]:visible',
                'input:visible',
            ]:
                try:
                    el = frame.locator(sel).first
                    if await el.is_visible(timeout=1_500):
                        ph = await el.get_attribute("placeholder") or ""
                        await el.fill(CONTRACT)
                        val = await el.input_value()
                        fill_ok = val == CONTRACT
                        step(f"Llenado en frame[{page.frames.index(frame) if frame in page.frames else '?'}]",
                             fill_ok, f"sel={sel!r} placeholder={ph!r} valor_leído={val!r}")
                        break
                except Exception:
                    pass
            if fill_ok:
                break
        if not fill_ok:
            step("Llenado del campo", False, "Ningún selector funcionó")

        # ── Red: peticiones relevantes ─────────────────────────────────────────
        relevant = [(s, u) for s, u in network_log
                    if any(k in u for k in ("gdo", "recaudo", "promigas", "api"))]
        report["network_sample"] = relevant[:10]

        await browser.close()

    # ── Conclusión ────────────────────────────────────────────────────────────
    passed = sum(1 for s in report["steps"] if s["ok"])
    total  = len(report["steps"])
    if not any_visible:
        report["conclusion"] = (
            "El portal carga pero el SPA no monta los inputs en el tiempo esperado. "
            "Causas probables: (1) red lenta desde Docker, (2) anti-bot sin texto Cloudflare, "
            "(3) el bundle JS está bloqueado por CSP del contenedor."
        )
    elif not fill_ok:
        report["conclusion"] = (
            "Se detectaron inputs pero ningún selector coincidió. "
            "Revisar placeholder/type/name exactos en el HTML guardado."
        )
    else:
        report["conclusion"] = "Todo OK — el scraper debería funcionar."

    print(f"\n{'='*60}")
    print(f"  Resultado: {passed}/{total} checks pasados")
    print(f"  Conclusión: {report['conclusion']}")
    print(f"{'='*60}\n")

    with open("/tmp/gdo_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print("  Reporte JSON: /tmp/gdo_report.json")
    print("  Screenshot:   /tmp/gdo_diag.png")
    print("  HTML:         /tmp/gdo_body.html\n")


def _print_report(report):
    print("\nReporte parcial:")
    for s in report["steps"]:
        icon = "✓" if s["ok"] else "✗"
        print(f"  {icon} {s['step']}: {s['detail']}")
    print(f"\nConclusión: {report['conclusion']}\n")


if __name__ == "__main__":
    asyncio.run(diagnose())

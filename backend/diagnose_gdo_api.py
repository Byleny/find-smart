"""
Prueba rápida del flujo REST de GDO — sin Playwright.
Ejecutar dentro del contenedor:
  docker compose exec backend python diagnose_gdo_api.py [contrato]

Reporta exactamente qué paso falla y por qué.
"""

import sys
import json
import httpx

CONTRATO = sys.argv[1] if len(sys.argv) > 1 else "610257"

PROMIGAS_API = "https://portalrecaudos.promigas.com/api"
GDO_LOGICA   = "https://portalrecaudos.gdo.com.co/Logica.aspx"

TOKEN_KEY = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEymCeWtLEzFs5Qvt9UZxF99tSX8KAw29"
    "YE34DcZ3w1skHlgp4/bvIbmm0m6VjoGxOainiNDX5fcbCukPMg8O2/Q=="
)

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
    "Origin": "https://portalrecaudos.gdo.com.co",
    "Referer": "https://portalrecaudos.gdo.com.co/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
}


def ok(label, detail=""):
    print(f"  ✓ {label}" + (f": {detail}" if detail else ""))


def fail(label, detail=""):
    print(f"  ✗ {label}" + (f": {detail}" if detail else ""))


def main():
    print(f"\n{'='*60}")
    print(f"  Diagnóstico GDO API — contrato {CONTRATO}")
    print(f"{'='*60}\n")

    h     = dict(HEADERS)
    h_tok = {**h, "Token": TOKEN_KEY}

    with httpx.Client(timeout=30, follow_redirects=True) as client:

        # ── 1. Nonce ──────────────────────────────────────────────────────────
        print("[1] GET /api/nonce")
        try:
            r1 = client.get(
                f"{PROMIGAS_API}/nonce",
                params={"referencia": CONTRATO},
                headers=h_tok,
            )
            print(f"    HTTP {r1.status_code}  Content-Type: {r1.headers.get('content-type','?')}")
            if r1.status_code == 200:
                d1 = r1.json()
                nonce = d1.get("datos", "")
                ok("nonce obtenido", nonce[:16] + "…")
            else:
                fail("nonce falló", r1.text[:200])
                return
        except Exception as e:
            fail("nonce — excepción", str(e))
            return

        # ── 2. FirmarNonce ────────────────────────────────────────────────────
        print("\n[2] POST /Logica.aspx/FirmarNonce")
        try:
            r2 = client.post(
                f"{GDO_LOGICA}/FirmarNonce",
                headers={**h, "Content-Type": "application/json; charset=utf-8",
                         "sec-fetch-site": "same-origin"},
                json={"nonce": nonce},
            )
            print(f"    HTTP {r2.status_code}  Content-Type: {r2.headers.get('content-type','?')}")
            if r2.status_code == 200:
                d2 = r2.json()
                signature = d2.get("d", "")
                if signature:
                    ok("firma obtenida", signature[:20] + "…")
                else:
                    fail("respuesta sin firma", json.dumps(d2)[:200])
                    return
            elif r2.status_code == 403:
                body = r2.text.lower()
                if "edgesuite" in body or "access denied" in body:
                    fail("BLOQUEADO POR AKAMAI WAF — gdo.com.co bloquea este IP")
                else:
                    fail("403 Forbidden (no Akamai)", r2.text[:300])
                return
            else:
                fail(f"HTTP {r2.status_code}", r2.text[:300])
                return
        except Exception as e:
            fail("FirmarNonce — excepción", str(e))
            return

        # ── 3. Signature → JWT ────────────────────────────────────────────────
        print("\n[3] POST /api/signature")
        try:
            r3 = client.post(
                f"{PROMIGAS_API}/signature",
                headers=h_tok,
                json={"nonce": nonce, "signature": signature},
            )
            print(f"    HTTP {r3.status_code}  Content-Type: {r3.headers.get('content-type','?')}")
            if r3.status_code == 200:
                d3 = r3.json()
                if d3.get("ok"):
                    jwt = d3["datos"]["access_token"]
                    ok("JWT obtenido", jwt[:30] + "…")
                else:
                    fail("API rechazó", json.dumps(d3)[:200])
                    return
            else:
                fail(f"HTTP {r3.status_code}", r3.text[:300])
                return
        except Exception as e:
            fail("signature — excepción", str(e))
            return

        # ── 4. Portal HTML ────────────────────────────────────────────────────
        print("\n[4] GET /api/portal?token=JWT")
        try:
            r4 = client.get(
                f"{PROMIGAS_API}/portal",
                params={"token": jwt, "referencia": CONTRATO},
                headers=h_tok,
            )
            print(f"    HTTP {r4.status_code}  Content-Type: {r4.headers.get('content-type','?')}")
            if r4.status_code == 200:
                d4 = r4.json()
                html = d4.get("html", "") if isinstance(d4, dict) else ""
                if html:
                    ok(f"HTML recibido", f"{len(html):,} bytes")
                    # Extraer texto visible
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, "html.parser")
                        text = soup.get_text(" ", strip=True)
                        # Mostrar primeros 600 chars del texto plano
                        print(f"\n    --- Texto visible del portal ---")
                        print("   ", text[:600])
                        print(f"    --------------------------------")
                    except Exception as e:
                        print(f"    (BeautifulSoup: {e})")
                else:
                    fail("respuesta sin HTML", json.dumps(d4)[:300])
            else:
                fail(f"HTTP {r4.status_code}", r4.text[:300])
                return
        except Exception as e:
            fail("portal — excepción", str(e))
            return

        # ── 5. Continuar paso 1 (contrato) ────────────────────────────────────
        print("\n[5] POST /api/continuar?token=JWT  (paso 1 — número de contrato)")
        body_paso1 = {
            "pestana": 1,
            "datos": {"pesta_0_Digitar_número_de_contrato": CONTRATO},
            "recaptcha_token": "",
        }
        try:
            r5 = client.post(
                f"{PROMIGAS_API}/continuar",
                params={"token": jwt},
                headers=h_tok,
                json=body_paso1,
                timeout=20,
            )
            print(f"    HTTP {r5.status_code}  Content-Type: {r5.headers.get('content-type','?')}")
            print(f"    Respuesta completa: {r5.text[:800]}")
        except Exception as e:
            print(f"    Excepción: {e}")

    print(f"\n{'='*60}")
    print("  Diagnóstico completo.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

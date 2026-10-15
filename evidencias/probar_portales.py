"""
Evidencia en imágenes de los intentos de automatizar la consulta de facturas
en los portales de Claro, Movistar y EMCALI.

No reimplementa nada: ejecuta el MISMO código de la app contra el portal real
y solo le agrega instrumentación alrededor:

- Claro:    backend/services/claro_pse.py tal como está hoy. Lo único que se
            cambia es quién resuelve el reCAPTCHA: en producción lo hace
            2Captcha (servicio pagado); aquí se intenta primero un clic
            automático en la casilla y, si Google exige el desafío de
            imágenes, lo resuelve una persona en la ventana del navegador.
            El código SMS lo escribe el dueño de la línea.
- Movistar: backend/services/scraper_service.py en el commit 4707470, la
            última versión que tuvo el scraper de Movistar antes de retirarlo
            (be647a8). Se extrae con `git show` y se ejecuta sin cambios.
- EMCALI:   backend/services/emcali_captcha.py tal como está hoy (clic
            automático en el reCAPTCHA), más una llamada directa a la API del
            portal con un token inválido para mostrar que lo valida en el
            servidor.

Cada paso queda como PNG con una franja superior que dice proveedor, número
de captura, descripción, fecha/hora y URL; las respuestas de red relevantes y
el resumen de la corrida también se guardan como imagen, listas para pegar en
el documento. Todo queda en evidencias/corridas/<fecha>_<proveedor>/ junto
con resultado.json (incluye las respuestas de red relevantes), leyendas.txt y
consola.log.

Uso, desde la raíz del repositorio:
  python evidencias/probar_portales.py movistar --referencia 6023959438 --intentos 3
  python evidencias/probar_portales.py emcali --contrato 123456
  python evidencias/probar_portales.py claro --referencia 3126266746

Claro necesita una terminal interactiva para escribir el código SMS; sin
terminal, el script espera a que el código se guarde en <carpeta>/otp.txt.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import dataclasses
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ_REPO = Path(__file__).resolve().parent.parent
CARPETA = Path(__file__).resolve().parent
PERFILES = CARPETA / ".perfiles"
sys.path.insert(0, str(RAIZ_REPO / "backend"))

# Los módulos de la app leen la ruta del perfil de Chrome al importarse o al
# lanzar el navegador; por defecto apuntan a /var/lib/... (rutas del
# contenedor), así que se redirigen a una carpeta local antes de importarlos.
for _var, _nombre in (("CLARO_PSE_PROFILE_DIR", "claro"),
                      ("EMCALI_PROFILE_DIR", "emcali"),
                      ("MOVISTAR_PROFILE_DIR", "movistar")):
    os.environ[_var] = str(PERFILES / _nombre)

from patchright.async_api import BrowserContext, BrowserType, Page  # noqa: E402

NOMBRES = {"claro": "Claro", "movistar": "Movistar", "emcali": "EMCALI"}

# Capturas que la propia app toma al fallar (con rutas /tmp del contenedor);
# se interceptan y se guardan rotuladas en la carpeta de la corrida.
DESCRIPCIONES_APP = {
    "movistar_debug_antes.png": "Formulario de Movistar lleno por la automatización, justo antes de pulsar «Continuar»",
    "movistar_debug.png": "Pantalla de Movistar después de la respuesta de /api/data-payment",
    "movistar_debug_sin_respuesta.png": "Movistar no respondió a la consulta en 35 segundos",
    "movistar_debug_etiqueta.png": "La automatización no encontró la opción de identificador de pago en Movistar",
    "claro_tipo_servicio_no_encontrado.png": "La automatización no encontró el tipo de servicio en el portal de Claro",
    "claro_sin_otp.png": "Claro no mostró las casillas del código SMS tras «Continuar»",
    "claro_medio_pago_no_encontrado.png": "La automatización no pudo elegir «PSE» como medio de pago en Claro",
    "claro_tras_confirmar_rechazado.png": "Claro rechazó «Confirmar» y devolvió el flujo al paso 1 con un error genérico",
    "claro_pse_bancos.png": "Claro no mostró la lista de bancos del formulario PSE",
}

# URLs cuyas respuestas se guardan completas (cuerpo incluido) en el registro.
INTERES = ("/api/data-payment", "infocomercial", "challenges.cloudflare.com",
           "portalpagos.claro.com.co", "checkout.cobre.co")


# ── Imágenes ─────────────────────────────────────────────────────────────────

def _fuente(tam: int, mono: bool = False, negrita: bool = False):
    if mono:
        candidatas = ("consola.ttf", "DejaVuSansMono.ttf")
    elif negrita:
        candidatas = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
    else:
        candidatas = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
    for nombre in candidatas:
        for base in ("C:/Windows/Fonts/", ""):
            try:
                return ImageFont.truetype(base + nombre, tam)
            except OSError:
                continue
    return ImageFont.load_default(size=tam)


def _envolver(texto: str, fuente, ancho_max: float) -> list[str]:
    """Parte el texto en líneas que quepan en ancho_max (corta palabras largas, como URLs o JSON)."""
    lineas: list[str] = []
    for parrafo in texto.split("\n"):
        actual = ""
        for palabra in parrafo.split(" "):
            candidato = f"{actual} {palabra}" if actual else palabra
            if fuente.getlength(candidato) <= ancho_max:
                actual = candidato
                continue
            if actual:
                lineas.append(actual)
                actual = ""
            while fuente.getlength(palabra) > ancho_max:
                lo, hi = 1, len(palabra)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if fuente.getlength(palabra[:mid]) <= ancho_max:
                        lo = mid
                    else:
                        hi = mid - 1
                lineas.append(palabra[:lo])
                palabra = palabra[lo:]
            actual = palabra
        lineas.append(actual)
    return lineas


def _rotular(png: bytes, encabezado: str, descripcion: str, pie: str) -> Image.Image:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    ancho, margen = max(img.width, 900), 18
    f_enc, f_desc, f_pie = _fuente(22, negrita=True), _fuente(20), _fuente(16)
    lineas = [(encabezado, f_enc, "#ffffff")]
    lineas += [(l, f_desc, "#e5e7eb") for l in _envolver(descripcion, f_desc, ancho - 2 * margen)]
    lineas += [(l, f_pie, "#9ca3af") for l in _envolver(pie, f_pie, ancho - 2 * margen)[:2]]
    alto_franja = 2 * margen + sum(f.size + 8 for _, f, _ in lineas) - 8
    lienzo = Image.new("RGB", (ancho, alto_franja + img.height), "#111827")
    dibujo = ImageDraw.Draw(lienzo)
    y = margen
    for texto, fuente, color in lineas:
        dibujo.text((margen, y), texto, font=fuente, fill=color)
        y += fuente.size + 8
    lienzo.paste(img, (0, alto_franja))
    return lienzo


def _panel(titulo: str, lineas: list[str]) -> bytes:
    """Imagen con texto monoespaciado: respuestas de red, línea de tiempo, resumen."""
    ancho, margen = 1400, 28
    f_tit, f_mono = _fuente(26, negrita=True), _fuente(17, mono=True)
    envueltas: list[str] = []
    for linea in lineas:
        envueltas += _envolver(linea, f_mono, ancho - 2 * margen)
    if len(envueltas) > 140:
        envueltas = envueltas[:139] + ["… (recortado; el texto completo está en resultado.json)"]
    alto = 2 * margen + 48 + len(envueltas) * (f_mono.size + 6)
    img = Image.new("RGB", (ancho, alto), "#f9fafb")
    dibujo = ImageDraw.Draw(img)
    dibujo.text((margen, margen), titulo, font=f_tit, fill="#111827")
    y = margen + 48
    for linea in envueltas:
        dibujo.text((margen, y), linea, font=f_mono, fill="#111827")
        y += f_mono.size + 6
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")[:60]


# ── Corrida ──────────────────────────────────────────────────────────────────

class _Tee(io.TextIOBase):
    def __init__(self, *destinos):
        self.destinos = destinos

    def write(self, texto):
        for d in self.destinos:
            d.write(texto)
            d.flush()
        return len(texto)

    def flush(self):
        for d in self.destinos:
            d.flush()


class Corrida:
    def __init__(self, proveedor: str, referencia: str, headless: bool | None):
        self.proveedor = proveedor
        self.referencia = referencia
        self.headless = headless          # None = lo que decida el código de la app
        self.inicio = datetime.now().astimezone()
        self.t0 = time.monotonic()
        self.dir = CARPETA / "corridas" / f"{self.inicio:%Y-%m-%d_%H%M%S}_{proveedor}"
        self.dir.mkdir(parents=True, exist_ok=True)
        # Perfil de Chrome limpio en cada corrida (uno que quedó a medio cerrar
        # deja colgado el siguiente lanzamiento); se reutiliza entre intentos.
        shutil.rmtree(PERFILES / proveedor, ignore_errors=True)
        self.prefijo = ""
        self.n = 0
        self.eventos: list[dict] = []
        self.red: list[dict] = []
        self.leyendas: list[str] = []
        self.marcas: dict[str, float] = {}          # segundos desde el inicio, por hito
        self.espera_humana: list[tuple[float, float]] = []   # (fin, duración) de cada reCAPTCHA resuelto por una persona
        self._consola = open(self.dir / "consola.log", "w", encoding="utf-8")
        sys.stdout = _Tee(sys.__stdout__, self._consola)

    def segundos(self) -> float:
        return time.monotonic() - self.t0

    def evento(self, mensaje: str) -> None:
        ahora = datetime.now().astimezone()
        mensaje = self.prefijo + mensaje
        self.eventos.append({"hora": ahora.isoformat(timespec="seconds"),
                             "segundos": round(self.segundos(), 1), "evento": mensaje})
        print(f"[evidencia {ahora:%H:%M:%S} +{self.segundos():6.1f}s] {mensaje}", flush=True)

    def guardar_png(self, png: bytes, descripcion: str, url: str = "") -> None:
        self.n += 1
        ahora = datetime.now().astimezone()
        descripcion = self.prefijo + descripcion
        nombre = f"{self.n:02d}_{_slug(descripcion)}.png"
        encabezado = f"FinSmart · Prueba de automatización · {NOMBRES[self.proveedor]} · Captura {self.n:02d}"
        pie = f"{ahora:%Y-%m-%d %H:%M:%S} (UTC{ahora:%z})" + (f" · {url}" if url else "")
        _rotular(png, encabezado, descripcion, pie).save(self.dir / nombre)
        self.leyendas.append(f"{nombre}\t{ahora:%Y-%m-%d %H:%M:%S}\t{descripcion}")
        print(f"[evidencia] captura {nombre}", flush=True)

    async def capturar(self, page, descripcion: str, full_page: bool = False) -> None:
        if page is None:
            return
        try:
            png = await _screenshot_original(page, full_page=full_page)
        except Exception as exc:
            self.evento(f"No se pudo tomar la captura «{descripcion}»: {exc}")
            return
        self.guardar_png(png, descripcion, page.url)

    def guardar_panel(self, titulo: str, descripcion: str, lineas: list[str]) -> None:
        self.guardar_png(_panel(titulo, lineas), descripcion)

    def cerrar(self, resultado: dict, extra: dict | None = None, resumen: list[str] | None = None) -> None:
        fin = datetime.now().astimezone()
        lineas = [
            f"Proveedor:   {NOMBRES[self.proveedor]}",
            f"Referencia:  {self.referencia}",
            f"Inicio:      {self.inicio:%Y-%m-%d %H:%M:%S}   Fin: {fin:%H:%M:%S}   "
            f"Duración: {self.segundos():.0f} s",
            "Resultado:",
        ] + [f"  {l}" for l in (resumen or [json.dumps(resultado, ensure_ascii=False, default=str)])] + [
            "",
            "Línea de tiempo:",
        ] + [f"  +{e['segundos']:6.1f}s  {e['evento']}" for e in self.eventos]
        self.prefijo = ""
        self.guardar_panel(f"Resumen de la corrida — {NOMBRES[self.proveedor]}",
                           "Resumen de la corrida: resultado y línea de tiempo de cada paso", lineas)
        datos = {
            "proveedor": self.proveedor, "referencia": self.referencia,
            "inicio": self.inicio.isoformat(timespec="seconds"),
            "fin": fin.isoformat(timespec="seconds"),
            "duracion_s": round(self.segundos(), 1),
            "resultado": resultado, "eventos": self.eventos, "red": self.red,
            **(extra or {}),
        }
        (self.dir / "resultado.json").write_text(
            json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (self.dir / "leyendas.txt").write_text("\n".join(self.leyendas) + "\n", encoding="utf-8")
        sys.stdout = sys.__stdout__
        self._consola.close()
        print(f"\nEvidencia guardada en: {self.dir}")


CORRIDA: Corrida | None = None


# ── Instrumentación del navegador ────────────────────────────────────────────

_lanzar_original = BrowserType.launch_persistent_context
_screenshot_original = Page.screenshot
_goto_original = Page.goto
_cerrar_original = BrowserContext.close


async def _al_responder(respuesta) -> None:
    c = CORRIDA
    if c is None:
        return
    try:
        tipo = respuesta.request.resource_type
    except Exception:
        tipo = ""
    if tipo not in ("document", "xhr", "fetch"):
        return
    entrada = {"hora": datetime.now().astimezone().isoformat(timespec="seconds"),
               "segundos": round(c.segundos(), 1), "metodo": respuesta.request.method,
               "url": respuesta.url, "estado": respuesta.status, "tipo": tipo}
    if tipo != "document" and any(p in respuesta.url for p in INTERES):
        try:
            enviado = respuesta.request.post_data or ""
            entrada["cuerpo_peticion"] = enviado[:2_000]
            entrada["largo_peticion"] = len(enviado)
        except Exception:
            pass
        try:
            entrada["cuerpo"] = (await respuesta.text())[:4_000]
        except Exception as exc:
            entrada["cuerpo"] = f"<no se pudo leer: {exc}>"
        # Respuestas propias del portal de Claro, p. ej. {"messageResult":"Pin Generado satisfactoriamente."}
        m = re.search(r'"messageResult"\s*:\s*"([^"]*)"', entrada["cuerpo"])
        if m:
            if "pin generado" in m.group(1).lower():
                c.marcas.setdefault("pin generado", c.segundos())
            c.evento(f"Respuesta del portal ({respuesta.url.split('/')[-1]}): {m.group(1)}")
    # patchright entrega a veces el mismo evento dos veces; la app ve una sola respuesta.
    clave = lambda e: (e["metodo"], e["url"], e["estado"], e.get("cuerpo_peticion"), e.get("cuerpo"))
    if any(clave(e) == clave(entrada) and entrada["segundos"] - e["segundos"] < 2 for e in c.red[-5:]):
        return
    c.red.append(entrada)


async def _lanzar(self, user_data_dir=None, **kw):
    c = CORRIDA
    if c is not None:
        if c.headless is not None:
            kw["headless"] = c.headless
        if kw.get("headless") is False and sys.platform == "win32":
            # Claro lanza Chromium con render por software (swiftshader), pensado
            # para el contenedor Linux sin GPU; en Windows con ventana visible
            # eso la deja en negro y la persona no puede ver el reCAPTCHA. Solo
            # afecta el dibujado, no la lógica del flujo.
            quitar = ("--use-gl", "--use-angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist")
            originales = kw.get("args") or []
            kw["args"] = [a for a in originales if not a.startswith(quitar)]
            if len(kw["args"]) != len(originales):
                c.evento("Ventana visible en Windows: se quitan los argumentos de render por software "
                         "del contenedor (swiftshader), que dejan la ventana en negro")
        c.evento(f"Se abre Chromium (patchright), headless={kw.get('headless')}")
    contexto = await _lanzar_original(self, user_data_dir=user_data_dir, **kw)
    if c is not None:
        contexto.on("response", _al_responder)
    return contexto


async def _screenshot(self, **kw):
    ruta = kw.get("path")
    if CORRIDA is not None and ruta and str(ruta).startswith("/tmp/"):
        kw.pop("path")
        kw["full_page"] = False   # solo lo visible: la página completa queda demasiado larga para el documento
        png = await _screenshot_original(self, **kw)
        nombre = os.path.basename(str(ruta))
        CORRIDA.guardar_png(png, DESCRIPCIONES_APP.get(nombre, f"Captura de diagnóstico de la app ({nombre})"),
                            self.url)
        return png
    return await _screenshot_original(self, **kw)


_tareas: set[asyncio.Task] = set()


async def _capturar_luego(page, segundos: float, descripcion: str) -> None:
    await asyncio.sleep(segundos)
    await CORRIDA.capturar(page, descripcion)


async def _goto(self, url, **kw):
    respuesta = await _goto_original(self, url, **kw)
    if CORRIDA is not None:
        CORRIDA.evento(f"Navegación a {url} → HTTP {respuesta.status if respuesta else '?'}")
        # En segundo plano, para no alterar los tiempos del flujo de la app.
        tarea = asyncio.create_task(_capturar_luego(self, 2.5, "Portal cargado por la automatización"))
        _tareas.add(tarea)
        tarea.add_done_callback(_tareas.discard)
    return respuesta


async def _cerrar_contexto(self, **kw):
    # En Windows el cierre a veces queda esperando solicitudes que nunca
    # terminan; no se deja que eso cuelgue la corrida.
    try:
        await asyncio.wait_for(_cerrar_original(self, **kw), 30)
    except asyncio.TimeoutError:
        if CORRIDA is not None:
            CORRIDA.evento("El navegador no cerró en 30 s; se continúa sin esperarlo")


BrowserType.launch_persistent_context = _lanzar
BrowserContext.close = _cerrar_contexto
Page.screenshot = _screenshot
Page.goto = _goto


def _filas_red(filtro) -> list[str]:
    lineas: list[str] = []
    for e in CORRIDA.red:
        if not filtro(e["url"]):
            continue
        lineas.append(f"[{e['hora'][11:19]}] {e['metodo']} {e['url']}")
        lineas.append(f"  → HTTP {e['estado']}")
        if e.get("cuerpo_peticion"):
            enviado = e["cuerpo_peticion"]
            largo = e.get("largo_peticion", len(enviado))
            lineas.append(f"  cuerpo enviado: {enviado[:160]}" + (f"… ({largo} caracteres en total)" if largo > 160 else ""))
        if "cuerpo" in e:
            lineas.append(f"  respuesta: {e['cuerpo'][:1_500]}")
        lineas.append("")
    return lineas


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ_REPO, capture_output=True, encoding="utf-8",
                          check=True).stdout.strip()


# ── Movistar ─────────────────────────────────────────────────────────────────

COMMIT_MOVISTAR = "4707470"   # última versión con scraper de Movistar (se retiró en be647a8)


def _resumen_scraper(d: dict) -> str:
    if "error" in d:
        return f"error de la automatización: {d['error']}"
    if d.get("portal_blocked"):
        return f"BLOQUEADO — {d.get('blocked_reason')}"
    if d.get("is_up_to_date"):
        return "consulta exitosa: sin deudas activas"
    return f"consulta exitosa: factura por ${d.get('amount'):,.0f}"


def _cargar_scraper_movistar():
    codigo = _git("show", f"{COMMIT_MOVISTAR}:backend/services/scraper_service.py")
    destino = CARPETA / ".cache" / f"scraper_service_{COMMIT_MOVISTAR}.py"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(codigo, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"scraper_service_{COMMIT_MOVISTAR}", destino)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


async def probar_movistar(args) -> None:
    global CORRIDA
    CORRIDA = c = Corrida("movistar", args.referencia, False if args.visible else None)
    modulo = _cargar_scraper_movistar()
    clase = modulo.MovistarMovilScraper if args.movil else modulo.MovistarScraper
    c.evento(f"Código ejecutado: {clase.__name__} de backend/services/scraper_service.py "
             f"en el commit {COMMIT_MOVISTAR} ({_git('log', '-1', '--format=%ad %s', '--date=short', COMMIT_MOVISTAR)})")
    resultados = []
    for i in range(1, args.intentos + 1):
        c.prefijo = f"Intento {i}/{args.intentos} · " if args.intentos > 1 else ""
        c.evento(f"Consulta automática de la línea {args.referencia} ({clase.TAB_LABEL})")
        try:
            res = await clase()._un_intento(args.referencia, {"payment_identifier": "1"})
            datos = dataclasses.asdict(res)
        except Exception as exc:
            datos = {"error": repr(exc)}
        c.evento(f"Resultado: {_resumen_scraper(datos)}")
        resultados.append(datos)
    c.prefijo = ""
    filas = _filas_red(lambda u: "/api/data-payment" in u)
    c.guardar_panel(
        "Respuestas de payment.movistar.co/api/data-payment",
        "Respuesta del servidor de Movistar a cada consulta hecha por la automatización (registro de red)",
        filas or ["La automatización no llegó a llamar a /api/data-payment."],
    )
    c.cerrar({"intentos": resultados}, {"codigo_ejecutado": f"{COMMIT_MOVISTAR}:backend/services/scraper_service.py"},
             [f"Intento {i}: {_resumen_scraper(d)}" for i, d in enumerate(resultados, 1)])


# ── EMCALI ───────────────────────────────────────────────────────────────────

API_EMCALI = "https://pagosb.emcali.com.co/api/open/infocomercial"

_JS_POST = """
async ({url, cuerpo}) => {
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify(cuerpo)});
    return {estado: r.status, cuerpo: (await r.text()).slice(0, 3000)};
}
"""


async def probar_emcali(args) -> None:
    global CORRIDA
    CORRIDA = c = Corrida("emcali", args.contrato, False if args.visible else None)
    from services import emcali_captcha
    ses = emcali_captcha._Sesion(args.contrato, 0)
    resultado: dict = {}
    sondeos: list[dict] = []
    try:
        c.evento("Código ejecutado: services/emcali_captcha.py (_abrir: contrato, políticas, "
                 "clic automático en «No soy un robot»)")
        estado = await emcali_captcha._abrir(ses)
        c.evento(f"Estado tras el clic automático: {estado['estado']}")
        await c.capturar(ses.page, "EMCALI tras el clic automático en «No soy un robot»: "
                         + ("Google exige el desafío de imágenes" if estado["estado"] == "desafio"
                            else f"estado «{estado['estado']}»"))
        if estado["estado"] == "desafio":
            c.guardar_png(base64.b64decode(estado["imagen"]),
                          "Recorte del desafío de imágenes que Google le pide resolver a la automatización")

        await ses.page.wait_for_timeout(15_000)
        estado2 = await emcali_captcha._estado_actual(ses, espera_api=3)
        c.evento(f"Estado 15 s después, sin intervención humana: {estado2['estado']}")
        await c.capturar(ses.page, "15 s después: el reCAPTCHA sigue sin resolverse y EMCALI no consultó la factura")
        resultado = {"estado_tras_clic": estado["estado"], "estado_15s_despues": estado2["estado"],
                     "respuesta_portal": ses.respuesta}

        # La API del portal valida el token en el servidor: se le envía la
        # misma petición que hace la app de Angular, con tokens inválidos.
        for token in ("", "token-invalido-generado-por-la-prueba"):
            cuerpo = {"contrato": args.contrato, "captcha": token}
            try:
                r = await ses.page.evaluate(_JS_POST, {"url": API_EMCALI, "cuerpo": cuerpo})
            except Exception as exc:
                r = {"estado": None, "cuerpo": f"<error: {exc}>"}
            sondeos.append({"cuerpo_enviado": cuerpo, **r})
            c.evento(f"POST {API_EMCALI} con captcha={token!r} → HTTP {r['estado']}: {r['cuerpo'][:200]}")
        lineas = []
        for s in sondeos:
            lineas += [f"POST {API_EMCALI}",
                       f"  cuerpo enviado: {json.dumps(s['cuerpo_enviado'], ensure_ascii=False)}",
                       f"  → HTTP {s['estado']}",
                       f"  respuesta: {s['cuerpo']}", ""]
        c.guardar_panel("Llamada directa a la API de EMCALI sin un reCAPTCHA válido",
                        "La API de EMCALI valida el reCAPTCHA en su servidor: la misma petición que hace el "
                        "portal, enviada con un token vacío o inválido", lineas)
        resultado["sondeos_api"] = sondeos
    except Exception as exc:
        resultado = {"estado": "error", "detalle": repr(exc)}
        c.evento(f"Error: {exc!r}")
        await c.capturar(ses.page, f"Error en la automatización de EMCALI: {exc}")
    finally:
        await emcali_captcha._cerrar(ses)
        c.cerrar(resultado, {"codigo_ejecutado": "backend/services/emcali_captcha.py"})


# ── Claro ────────────────────────────────────────────────────────────────────

_JS_TOKENS = """() => Array.from(document.querySelectorAll('textarea[name="g-recaptcha-response"]'))
                          .map(t => t.value || '')"""


async def _token_nuevo(page, previos: set[str]) -> bool:
    try:
        return any(v and v not in previos for v in await page.evaluate(_JS_TOKENS))
    except Exception:
        return False


async def _casilla_sin_marcar(page, segundos: int):
    for _ in range(segundos * 2):
        marcos = page.locator('iframe[title="reCAPTCHA"]')
        for i in range(await marcos.count()):
            try:
                if not await marcos.nth(i).is_visible():
                    continue
                ancla = page.frame_locator('iframe[title="reCAPTCHA"]').nth(i).locator("#recaptcha-anchor")
                if await ancla.get_attribute("aria-checked", timeout=1_000) != "true":
                    return ancla
            except Exception:
                continue
        await page.wait_for_timeout(500)
    return None


async def _recaptcha_asistido(page, pageurl: str) -> None:
    """Reemplaza a twocaptcha.resolver_recaptcha_v2: clic automático y, si no basta, una persona."""
    from services.emcali_captcha import _iframe_desafio
    c = CORRIDA
    previos = {v for v in await page.evaluate(_JS_TOKENS) if v}
    ancla = await _casilla_sin_marcar(page, 30)
    if ancla is None:
        raise RuntimeError("No apareció ningún reCAPTCHA sin resolver en la página.")
    await c.capturar(page, "Aparece el reCAPTCHA «No soy un robot» del portal de Claro")
    c.evento("reCAPTCHA: clic automático en la casilla «No soy un robot»")
    try:
        await ancla.click(timeout=5_000)
    except Exception as exc:
        c.evento(f"El clic automático falló: {exc}")
    desafio = False
    for _ in range(20):
        await page.wait_for_timeout(500)
        if await _token_nuevo(page, previos):
            c.marcas.setdefault("recaptcha resuelto", c.segundos())
            c.evento("Google aceptó el clic automático sin desafío de imágenes")
            await c.capturar(page, "Google aceptó el clic automático en el reCAPTCHA sin pedir desafío")
            return
        if (await _iframe_desafio(page))[0] is not None:
            desafio = True
            break
    if desafio:
        c.evento("Google respondió al clic automático con un desafío de imágenes")
        await c.capturar(page, "Google responde al clic automático con un desafío de imágenes: "
                         "la automatización no puede seguir sin una persona (o 2Captcha)")
    else:
        c.evento("El clic automático no completó el reCAPTCHA")
    print("\n>>> Resuelve el reCAPTCHA en la ventana del navegador (tienes 10 minutos).\n", flush=True)
    t = time.monotonic()
    while time.monotonic() - t < 600:
        if await _token_nuevo(page, previos):
            c.espera_humana.append((c.segundos(), time.monotonic() - t))
            c.marcas.setdefault("recaptcha resuelto", c.segundos())
            c.evento(f"reCAPTCHA resuelto por una persona en {time.monotonic() - t:.0f} s")
            await c.capturar(page, "reCAPTCHA resuelto por una persona")
            return
        await page.wait_for_timeout(1_000)
    raise RuntimeError("Nadie resolvió el reCAPTCHA en 10 minutos.")


async def _pedir_otp(c: Corrida) -> str:
    ruta = c.dir / "otp.txt"
    if sys.stdin is not None and sys.stdin.isatty():
        return (await asyncio.to_thread(input, "\n>>> Escribe el código SMS de 4 dígitos: ")).strip()
    print(f"\n>>> Esperando el código SMS en {ruta}\n", flush=True)
    for _ in range(600):
        if ruta.exists():
            codigo = ruta.read_text(encoding="utf-8").strip()
            ruta.unlink()
            if codigo:
                return codigo
        await asyncio.sleep(1)
    raise RuntimeError("No llegó el código SMS en 10 minutos.")


def _con_captura(funcion, descripcion):
    async def envoltura(page, texto, *a, **kw):
        await CORRIDA.capturar(page, descripcion.format(texto=texto))
        ok = await funcion(page, texto, *a, **kw)
        CORRIDA.marcas[f"clic {texto}"] = CORRIDA.segundos()
        CORRIDA.evento(f"Clic en «{texto}»: {'hecho' if ok else 'no se encontró'}")
        return ok
    return envoltura


async def probar_claro(args) -> None:
    global CORRIDA
    CORRIDA = c = Corrida("claro", args.referencia, False)   # visible: el reCAPTCHA lo resuelve una persona
    from services import claro_pse
    claro_pse.resolver_recaptcha_v2 = _recaptcha_asistido
    claro_pse._click_texto = _con_captura(claro_pse._click_texto, "Paso del flujo: se va a pulsar «{texto}»")
    claro_pse._click_texto_visible = _con_captura(claro_pse._click_texto_visible,
                                                  "Paso del flujo: se va a elegir «{texto}»")

    ses = claro_pse._Sesion()
    ses.account_reference = args.referencia
    ses.tipo_servicio = args.tipo
    resultado: dict = {}
    try:
        c.evento(f"Código ejecutado: services/claro_pse.py ({args.tipo}, línea {args.referencia}); "
                 "reCAPTCHA: clic automático + persona en lugar de 2Captcha")
        r = await claro_pse._iniciar(ses, args.referencia)
        while r.get("estado") == "otp_requerido":
            c.marcas.setdefault("codigo pedido", c.segundos())
            c.evento("Claro envió el código SMS y pide escribirlo")
            await ses.page.wait_for_timeout(1_500)
            await c.capturar(ses.page, "Claro pide el código de verificación de 4 dígitos enviado por SMS")
            if args.hasta_codigo:
                c.evento("Fin de la prueba: se detiene en el paso del código SMS (--hasta-codigo)")
                break
            codigo = await _pedir_otp(c)
            c.marcas["codigo ingresado"] = c.segundos()
            c.evento("Código SMS ingresado; la automatización continúa")
            r = await claro_pse._continuar_con_otp(ses, codigo)
        resultado = {k: v for k, v in r.items() if k != "banks"}
        if "banks" in r:
            resultado["bancos_leidos"] = len(r["banks"])
        resultado["confirmaciones_rechazadas"] = ses.intentos_confirmacion
        c.evento(f"Resultado: {json.dumps(resultado, ensure_ascii=False, default=str)}")
        if r.get("estado") == "otp_requerido":
            pass
        elif r.get("estado") == "listo":
            c.marcas["lista de bancos"] = c.segundos()
            await c.capturar(ses.page, "La automatización llegó al formulario PSE de Claro (lista de bancos)",
                             full_page=True)
            if args.hasta_pse:
                resultado.update(await _llegar_a_pse(c, claro_pse, ses, r["banks"], args))
        else:
            motivo = (r.get("resultado") or {}).get("blocked_reason", r.get("estado"))
            await c.capturar(ses.page, f"La automatización se detuvo: {motivo}")
    except Exception as exc:
        resultado = {"estado": "error", "detalle": repr(exc),
                     "confirmaciones_rechazadas": ses.intentos_confirmacion}
        c.evento(f"Error: {exc!r}")
        await c.capturar(ses.page, f"Error en la automatización de Claro: {exc}")
    finally:
        await claro_pse._cerrar_sesion(ses)
        c.cerrar(resultado, {"codigo_ejecutado": "backend/services/claro_pse.py", "tiempos": _tiempos_claro(c)},
                 _resumen_claro(c, resultado))


async def _llegar_a_pse(c: Corrida, claro_pse, ses, bancos: list[dict], args) -> dict:
    """Paso 3 de la app (_pagar): banco + datos del titular → redirección a la pasarela PSE. No paga."""
    nombres = [b["code"] for b in bancos]
    if args.banco:
        banco = next((n for n in nombres if args.banco.lower() in n.lower()), None)
        if banco is None:
            raise RuntimeError(f"No hay un banco que contenga «{args.banco}». Opciones: {', '.join(nombres)}")
    else:
        banco = next(n for n in nombres if not n.lower().startswith(("selec", "a contin", "-")))
    c.evento(f"Se elige el banco «{banco}» y se llenan los datos del titular")
    datos = {"full_name": args.nombre, "identification_type": args.tipo_doc,
             "identification_number": args.documento, "email": args.correo}
    r = await claro_pse._pagar(ses, banco, datos)
    c.marcas["redireccion pse"] = c.segundos()
    c.evento(f"Claro redirigió a la pasarela de pago: {r['redirect_url']}")
    await ses.page.wait_for_timeout(4_000)
    await c.capturar(ses.page, "Final del flujo de la app: Claro redirige a la pasarela PSE con el valor de la "
                     "factura (la prueba se detiene aquí; no se ingresa al banco ni se paga)")
    return {"estado": "redirigido_a_pse", "banco": banco, "redirect_url": r["redirect_url"]}


def _tiempos_claro(c: Corrida) -> dict:
    t_codigo = c.marcas.get("codigo pedido")
    t_continuar = c.marcas.get("clic Continuar")
    t_pin = c.marcas.get("pin generado")
    t_ingresado = c.marcas.get("codigo ingresado")
    t_bancos = c.marcas.get("lista de bancos")
    t_pse = c.marcas.get("redireccion pse")
    # Cada reCAPTCHA resuelto por una persona: (segundo en que terminó, duración).
    antes = [d for fin, d in c.espera_humana if t_codigo is None or fin <= t_codigo]
    despues = [d for fin, d in c.espera_humana if t_codigo is not None and fin > t_codigo]
    return {
        "codigo_ingresado_s": round(t_ingresado, 1) if t_ingresado is not None else None,
        "lista_de_bancos_s": round(t_bancos, 1) if t_bancos is not None else None,
        "codigo_a_lista_de_bancos_s": round(t_bancos - t_ingresado, 1)
        if t_bancos is not None and t_ingresado is not None else None,
        "redireccion_pse_s": round(t_pse, 1) if t_pse is not None else None,
        "pin_generado_s": round(t_pin, 1) if t_pin is not None else None,
        "hasta_codigo_s": round(t_codigo, 1) if t_codigo is not None else None,
        "espera_recaptcha_persona_s": [round(d, 1) for d in antes],
        "espera_segundo_recaptcha_persona_s": [round(d, 1) for d in despues],
        "automatico_hasta_codigo_s": round(t_codigo - sum(antes), 1) if t_codigo is not None else None,
        "continuar_a_codigo_s": round(t_codigo - t_continuar, 1)
        if t_codigo is not None and t_continuar is not None else None,
    }


def _resumen_claro(c: Corrida, resultado: dict) -> list[str]:
    t = _tiempos_claro(c)
    lineas = [f"Estado final: {resultado.get('estado')}"]
    motivo = (resultado.get("resultado") or {}).get("blocked_reason") or resultado.get("detalle")
    if motivo:
        lineas.append(f"Motivo: {motivo}")
    if t["hasta_codigo_s"] is None:
        lineas.append("La automatización NO llegó al paso del código SMS.")
        return lineas
    if t["espera_recaptcha_persona_s"]:
        humano = ", ".join(f"{x:.0f} s" for x in t["espera_recaptcha_persona_s"])
        linea_captcha = f"  - reCAPTCHA resuelto por una persona (en producción, 2Captcha): {humano}"
    else:
        linea_captcha = "  - reCAPTCHA: aceptado sin intervención humana"
    lineas += [
        f"Tiempo total hasta que Claro pidió el código SMS: {t['hasta_codigo_s']:.0f} s",
        linea_captcha,
        f"  - navegación automática y respuestas del portal: {t['automatico_hasta_codigo_s']:.0f} s",
    ]
    if t["pin_generado_s"] is not None:
        t_captcha = c.marcas.get("recaptcha resuelto")
        antes = " (antes de que se resolviera el reCAPTCHA)" if t_captcha is None or t["pin_generado_s"] < t_captcha else ""
        lineas.append(f"  - Claro respondió «Pin Generado» (envío del SMS) a los {t['pin_generado_s']:.0f} s{antes}")
    if t["continuar_a_codigo_s"] is not None:
        lineas.append(f"  - desde «Continuar» hasta que Claro mostró las casillas del código: "
                      f"{t['continuar_a_codigo_s']:.0f} s")
    lineas.append(f"Rechazos de «Confirmar» por parte de Claro (cada uno exige un SMS nuevo): "
                  f"{resultado.get('confirmaciones_rechazadas', 0)}")
    if t["lista_de_bancos_s"] is not None:
        segundo = t["espera_segundo_recaptcha_persona_s"]
        detalle = (f", de los cuales {sum(segundo):.0f} s fueron el segundo reCAPTCHA resuelto por una persona"
                   if segundo else "")
        lineas.append(f"Llegó a la lista de bancos de PSE en Claro a los {t['lista_de_bancos_s']:.0f} s "
                      f"({t['codigo_a_lista_de_bancos_s']:.0f} s después de ingresar el código{detalle})")
    elif t["codigo_ingresado_s"] is not None:
        lineas.append("Se ingresó el código, pero NO se llegó a la lista de bancos de PSE.")
    else:
        lineas.append("La prueba se detuvo en el paso del código SMS; desde aquí el flujo necesita que el "
                      "dueño de la línea escriba el código en tiempo real.")
    if t["redireccion_pse_s"] is not None:
        lineas.append(f"Redirección a la pasarela PSE a los {t['redireccion_pse_s']:.0f} s: "
                      f"{resultado.get('redirect_url')}")
    return lineas


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="proveedor", required=True)

    m = sub.add_parser("movistar", help="Scraper de Movistar del commit 4707470")
    m.add_argument("--referencia", required=True, help="Indicativo + línea fija (ej. 6023959438) o celular con --movil")
    m.add_argument("--movil", action="store_true", help="Pestaña Pospago (línea móvil) en vez de Internet")
    m.add_argument("--intentos", type=int, default=1)
    m.add_argument("--visible", action="store_true", help="Navegador visible (la app usaba headless)")

    e = sub.add_parser("emcali", help="Clic automático en el reCAPTCHA de EMCALI + llamada directa a su API")
    e.add_argument("--contrato", default="123456")
    e.add_argument("--visible", action="store_true", help="Navegador visible (la app usa headless)")

    cl = sub.add_parser("claro", help="Flujo completo de Claro hasta el formulario PSE")
    cl.add_argument("--referencia", required=True, help="Celular (Postpago) o cuenta (Hogar y Multiplay)")
    cl.add_argument("--tipo", default="Postpago", choices=["Postpago", "Hogar y Multiplay"])
    cl.add_argument("--hasta-codigo", action="store_true",
                    help="Detenerse cuando Claro pide el código SMS (no hace falta escribirlo)")
    cl.add_argument("--hasta-pse", action="store_true",
                    help="Después de la lista de bancos, llenar banco y datos del titular y llegar a la "
                         "redirección a PSE (no paga: ahí se detiene)")
    cl.add_argument("--banco", help="Parte del nombre del banco (ej. Bancolombia); por defecto el primero de la lista")
    cl.add_argument("--nombre", help="Nombre del titular (con --hasta-pse)")
    cl.add_argument("--tipo-doc", default="CC", choices=["CC", "CE", "NIT", "PA", "TI"])
    cl.add_argument("--documento", help="Número de documento del titular (con --hasta-pse)")
    cl.add_argument("--correo", help="Correo del titular (con --hasta-pse)")

    args = p.parse_args()
    if args.proveedor == "claro" and args.hasta_pse and not (args.nombre and args.documento and args.correo):
        p.error("--hasta-pse necesita --nombre, --documento y --correo (los pide el formulario PSE de Claro)")
    PERFILES.mkdir(parents=True, exist_ok=True)
    funcion = {"movistar": probar_movistar, "emcali": probar_emcali, "claro": probar_claro}[args.proveedor]
    asyncio.run(funcion(args))


if __name__ == "__main__":
    main()

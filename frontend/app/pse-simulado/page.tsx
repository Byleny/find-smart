"use client"

import { Suspense, useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import {
  Lock, ShieldCheck, CheckCircle2, Loader2, Building2, Printer, Clock,
  ChevronRight, Info, ArrowLeft, Eye, EyeOff,
} from "lucide-react"
import { formatCOP } from "@/lib/format"

// Destino del enlace PSE en el modo de simulación de GDO (GDO_SIMULAR_PAGO=1).
// Recorre los pasos que el usuario vería en la pasarela real (datos del
// pagador en PSE, autorización en el banco, comprobante) con un diseño
// propio inspirado en ese recorrido, sin logos ni marcas. Al final devuelve
// el resultado a la pestaña de FinSmart que la abrió. No se procesa ningún pago.

type Paso =
  | "pse" | "redir-banco" | "banco" | "notificacion" | "procesando"
  | "redir-pse" | "comprobante"

// La pestaña de facturas escucha este mensaje (ver dashboard/facturas/page.tsx).
const MENSAJE_PAGO_SIMULADO = "finsmart-pse-simulado"
const COMERCIO = "Gases de Occidente S.A. E.S.P."

// Pasos automáticos: [paso actual, siguiente, milisegundos].
const TRANSICIONES: [Paso, Paso, number][] = [
  ["redir-banco", "banco", 1800],
  ["procesando", "redir-pse", 2000],
  ["redir-pse", "comprobante", 1600],
]

const pse = {
  azul: "#14408a", azulOscuro: "#0e2f68", fondo: "#eef2f8", borde: "#d5dcea", texto: "#1b2740", suave: "#5d6982",
}

function PseSimulado() {
  const params = useSearchParams()
  const banco = params.get("banco") || "Banco"
  const monto = Number(params.get("monto") || 0)
  const ref = params.get("ref") || ""
  const esNequi = banco.toUpperCase() === "NEQUI"

  const [paso, setPaso] = useState<Paso>("pse")
  const [persona, setPersona] = useState<"natural" | "juridica">("natural")
  const [tipoDoc, setTipoDoc] = useState("CC")
  const [documento, setDocumento] = useState("")
  const [nombre, setNombre] = useState("")
  const [correo, setCorreo] = useState("")
  const [terminos, setTerminos] = useState(false)
  const [celular, setCelular] = useState("")
  const [usuario, setUsuario] = useState("")
  const [clave, setClave] = useState("")
  const [claveNequi, setClaveNequi] = useState("")
  const [restante, setRestante] = useState(10 * 60)
  const [cus] = useState(() => String(Math.floor(1e9 + Math.random() * 9e9)))
  const [fecha, setFecha] = useState("")

  useEffect(() => {
    const t = TRANSICIONES.find(([desde]) => desde === paso)
    if (!t) return
    const id = setTimeout(() => {
      if (t[1] === "redir-pse") setFecha(new Date().toLocaleString("es-CO"))
      setPaso(t[1])
    }, t[2])
    return () => clearTimeout(id)
  }, [paso])

  // Tiempo de sesión que muestra PSE mientras el pago está en curso.
  useEffect(() => {
    if (paso === "comprobante") return
    const id = setInterval(() => setRestante((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(id)
  }, [paso])

  const formularioValido =
    documento.length >= 5 && nombre.trim().length > 2 && /^\S+@\S+\.\S+$/.test(correo) && terminos

  function volver() {
    const resultado = { tipo: MENSAJE_PAGO_SIMULADO, estado: "aprobado", cus, banco, monto, ref }
    if (window.opener) {
      window.opener.postMessage(resultado, window.location.origin)
      window.opener.focus()
      window.close()
    } else {
      window.location.href = "/dashboard/facturas"
    }
  }

  let contenido
  if (paso === "redir-banco" || paso === "redir-pse") {
    contenido = (
      <Redireccion
        titulo={paso === "redir-banco" ? `Te estamos llevando a ${banco}` : "Regresando a PSE"}
        detalle={paso === "redir-banco"
          ? "No cierres esta ventana. Allí autorizarás el pago de forma segura."
          : "Estamos confirmando el resultado de tu transacción."}
      />
    )
  } else if (paso === "banco" || paso === "notificacion" || paso === "procesando") {
    contenido = esNequi ? (
      <PantallaNequi
        paso={paso} celular={celular} setCelular={setCelular} monto={monto}
        clave={claveNequi} setClave={setClaveNequi}
        onContinuar={() => setPaso("notificacion")}
        onPagar={() => setPaso("procesando")}
        onCambiarNumero={() => { setClaveNequi(""); setPaso("banco") }}
      />
    ) : (
      <PantallaBanco
        banco={banco} paso={paso} usuario={usuario} setUsuario={setUsuario}
        clave={clave} setClave={setClave} monto={monto} onPagar={() => setPaso("procesando")}
      />
    )
  } else {
    contenido = (
      <div className="min-h-screen" style={{ background: pse.fondo, color: pse.texto }}>
        <EncabezadoPse restante={paso === "comprobante" ? null : restante} />
        <Pasos actual={paso === "pse" ? 1 : 3} />

        <main className="mx-auto max-w-4xl px-4 pb-16 grid gap-5 md:grid-cols-[1fr_280px]">
          <section
            key={paso}
            className="animate-in fade-in slide-in-from-bottom-2 duration-300 rounded-xl bg-white shadow-sm border p-6 order-2 md:order-1"
            style={{ borderColor: pse.borde }}
          >
            {paso === "pse" ? (
              <div className="space-y-5">
                <div>
                  <h1 className="text-xl font-semibold">Datos del pagador</h1>
                  <p className="text-sm mt-1" style={{ color: pse.suave }}>
                    Ingresa los datos de la persona titular de la cuenta con la que vas a pagar.
                  </p>
                </div>

                <div className="grid grid-cols-2 rounded-lg p-1 text-sm font-medium" style={{ background: pse.fondo }}>
                  {(["natural", "juridica"] as const).map((v) => (
                    <button
                      key={v} onClick={() => setPersona(v)}
                      className="rounded-md py-2 transition-colors"
                      style={persona === v ? { background: "white", color: pse.azul, boxShadow: "0 1px 2px rgba(0,0,0,.08)" } : { color: pse.suave }}
                    >
                      {v === "natural" ? "Persona natural" : "Persona jurídica"}
                    </button>
                  ))}
                </div>

                <div className="grid gap-4 sm:grid-cols-[140px_1fr]">
                  <Campo etiqueta="Tipo de documento">
                    <select value={tipoDoc} onChange={(e) => setTipoDoc(e.target.value)} className={claseInput}>
                      {(persona === "natural" ? ["CC", "CE", "PA", "TI"] : ["NIT"]).map((t) => <option key={t}>{t}</option>)}
                    </select>
                  </Campo>
                  <Campo etiqueta="Número de documento">
                    <input inputMode="numeric" value={documento} placeholder="1234567890"
                      onChange={(e) => setDocumento(e.target.value.replace(/\D/g, ""))} className={claseInput} />
                  </Campo>
                </div>
                <Campo etiqueta={persona === "natural" ? "Nombres y apellidos" : "Razón social"}>
                  <input value={nombre} onChange={(e) => setNombre(e.target.value)} className={claseInput} />
                </Campo>
                <Campo etiqueta="Correo electrónico registrado en PSE">
                  <input type="email" value={correo} placeholder="nombre@correo.com"
                    onChange={(e) => setCorreo(e.target.value)} className={claseInput} />
                </Campo>
                <Campo etiqueta="Banco">
                  <div className={`${claseInput} flex items-center justify-between`} style={{ background: pse.fondo }}>
                    <span className="flex items-center gap-2"><Building2 className="w-4 h-4" style={{ color: pse.azul }} />{banco}</span>
                    <span className="text-xs" style={{ color: pse.suave }}>Seleccionado en el comercio</span>
                  </div>
                </Campo>

                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={terminos} onChange={(e) => setTerminos(e.target.checked)}
                    className="mt-0.5 h-4 w-4" style={{ accentColor: pse.azul }} />
                  <span style={{ color: pse.suave }}>
                    Acepto los términos y condiciones y autorizo el tratamiento de mis datos personales.
                  </span>
                </label>

                <button
                  disabled={!formularioValido} onClick={() => setPaso("redir-banco")}
                  className="w-full flex items-center justify-center gap-1 rounded-lg py-3 text-sm font-semibold text-white transition-opacity disabled:opacity-40"
                  style={{ background: pse.azul }}
                >
                  Ir al banco <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <Comprobante
                cus={cus} banco={banco} monto={monto} referencia={ref} fecha={fecha}
                pagador={nombre} correo={correo} onVolver={volver}
              />
            )}
          </section>

          <aside className="space-y-3 order-1 md:order-2">
            <div className="rounded-xl bg-white shadow-sm border p-5 space-y-3 text-sm" style={{ borderColor: pse.borde }}>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: pse.suave }}>Resumen de la compra</p>
              <div>
                <p className="font-semibold">{COMERCIO}</p>
                <p className="text-xs" style={{ color: pse.suave }}>Pago factura de gas natural</p>
              </div>
              <Fila k="Referencia" v={<span className="font-mono">{ref}</span>} />
              <Fila k="Subtotal" v={formatCOP(monto)} />
              <Fila k="IVA" v={formatCOP(0)} />
              <div className="flex justify-between border-t pt-3 text-base" style={{ borderColor: pse.borde }}>
                <span className="font-semibold">Total a pagar</span>
                <span className="font-bold" style={{ color: pse.azul }}>{formatCOP(monto)}</span>
              </div>
            </div>
            <div className="rounded-xl border p-4 text-xs flex gap-2" style={{ borderColor: pse.borde, color: pse.suave, background: "white" }}>
              <ShieldCheck className="w-4 h-4 shrink-0" style={{ color: pse.azul }} />
              Tus claves solo se ingresan en el portal de tu banco. El comercio nunca las conoce.
            </div>
          </aside>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {contenido}
      <span className="fixed bottom-2 right-2 rounded bg-black/55 px-2 py-0.5 text-[10px] text-white/90 print:hidden">
        Modo demostración
      </span>
    </div>
  )
}

const claseInput =
  "w-full rounded-lg border border-[#d5dcea] bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#14408a]/30 focus:border-[#14408a]"

function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{etiqueta}</span>
      {children}
    </label>
  )
}

function Fila({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <span style={{ color: pse.suave }}>{k}</span>
      <span className="text-right">{v}</span>
    </div>
  )
}

function EncabezadoPse({ restante }: { restante: number | null }) {
  const mm = restante === null ? "" : `${String(Math.floor(restante / 60)).padStart(2, "0")}:${String(restante % 60).padStart(2, "0")}`
  return (
    <header style={{ background: pse.azul }} className="text-white">
      <div className="mx-auto max-w-4xl px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="rounded-lg bg-white p-1.5"><ShieldCheck className="w-5 h-5" style={{ color: pse.azul }} /></div>
          <div className="leading-tight">
            <p className="font-extrabold tracking-[0.2em]">PSE</p>
            <p className="text-[11px] text-white/75">Pagos Seguros en Línea</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-white/85">
          {restante !== null && (
            <span className="hidden sm:flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1">
              <Clock className="w-3.5 h-3.5" /> Tiempo restante {mm}
            </span>
          )}
          <span className="flex items-center gap-1"><Lock className="w-3.5 h-3.5" /> Conexión segura</span>
        </div>
      </div>
    </header>
  )
}

function Pasos({ actual }: { actual: number }) {
  const pasos = ["Datos del pagador", "Autorización en el banco", "Comprobante"]
  return (
    <ol className="mx-auto max-w-4xl px-4 py-5 flex items-center gap-2 text-xs sm:text-sm">
      {pasos.map((p, i) => {
        const n = i + 1
        const hecho = n < actual
        const activo = n === actual
        return (
          <li key={p} className="flex items-center gap-2 flex-1 last:flex-none">
            <span
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold"
              style={hecho || activo ? { background: pse.azul, color: "white" } : { background: "white", color: pse.suave, border: `1px solid ${pse.borde}` }}
            >
              {hecho ? <CheckCircle2 className="w-4 h-4" /> : n}
            </span>
            <span className={`hidden sm:inline ${activo ? "font-semibold" : ""}`} style={{ color: activo ? pse.texto : pse.suave }}>{p}</span>
            {n < pasos.length && <span className="h-px flex-1" style={{ background: hecho ? pse.azul : pse.borde }} />}
          </li>
        )
      })}
    </ol>
  )
}

function Redireccion({ titulo, detalle }: { titulo: string; detalle: string }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-5 px-6 text-center" style={{ background: pse.fondo, color: pse.texto }}>
      <div className="relative">
        <div className="h-16 w-16 rounded-full border-4 border-[#d5dcea] border-t-[#14408a] animate-spin" />
        <Lock className="absolute inset-0 m-auto w-5 h-5" style={{ color: pse.azul }} />
      </div>
      <div className="animate-in fade-in duration-500">
        <p className="text-lg font-semibold">{titulo}</p>
        <p className="text-sm mt-1 max-w-xs" style={{ color: pse.suave }}>{detalle}</p>
      </div>
    </div>
  )
}

function Comprobante({ cus, banco, monto, referencia, fecha, pagador, correo, onVolver }: {
  cus: string; banco: string; monto: number; referencia: string; fecha: string
  pagador: string; correo: string; onVolver: () => void
}) {
  const filas: [string, React.ReactNode][] = [
    ["Empresa", COMERCIO],
    ["Descripción", "Pago factura de gas natural"],
    ["Referencia", <span key="r" className="font-mono">{referencia}</span>],
    ["Banco", banco],
    ["Pagador", pagador],
    ["Correo", correo],
    ["Fecha y hora", fecha],
  ]
  return (
    <div className="space-y-5">
      <div className="flex flex-col items-center gap-2 text-center">
        <div className="rounded-full bg-[#1f9d55]/10 p-3 animate-in zoom-in-50 duration-500">
          <CheckCircle2 className="w-12 h-12 text-[#1f9d55]" />
        </div>
        <h1 className="text-xl font-semibold">Transacción aprobada</h1>
        <p className="text-3xl font-bold" style={{ color: pse.azul }}>{formatCOP(monto)}</p>
        <p className="text-xs rounded-full px-3 py-1" style={{ background: pse.fondo, color: pse.suave }}>
          CUS <span className="font-mono font-semibold" style={{ color: pse.texto }}>{cus}</span>
        </p>
      </div>
      <div className="border-t border-dashed" style={{ borderColor: pse.borde }} />
      <dl className="space-y-2.5 text-sm">
        {filas.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4">
            <dt style={{ color: pse.suave }}>{k}</dt>
            <dd className="text-right break-all">{v}</dd>
          </div>
        ))}
        <div className="flex justify-between gap-4">
          <dt style={{ color: pse.suave }}>Estado</dt>
          <dd><span className="rounded-full bg-[#1f9d55]/10 px-2.5 py-0.5 text-xs font-semibold text-[#1f9d55]">Aprobada</span></dd>
        </div>
      </dl>
      <div className="rounded-lg p-3 text-xs flex gap-2" style={{ background: pse.fondo, color: pse.suave }}>
        <Info className="w-4 h-4 shrink-0" style={{ color: pse.azul }} />
        Enviamos el comprobante a {correo}. Guarda el CUS para cualquier reclamación.
      </div>
      <div className="flex flex-col-reverse sm:flex-row gap-2 print:hidden">
        <button onClick={() => window.print()}
          className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border py-3 text-sm font-semibold"
          style={{ borderColor: pse.azul, color: pse.azul }}>
          <Printer className="w-4 h-4" /> Imprimir comprobante
        </button>
        <button onClick={onVolver}
          className="flex-1 rounded-lg py-3 text-sm font-semibold text-white" style={{ background: pse.azul }}>
          Finalizar y volver al comercio
        </button>
      </div>
    </div>
  )
}

const nq = { fondo: "#250a35", acento: "#d4207c", acentoOscuro: "#b81a6b", tarjeta: "#ffffff", suave: "#6e5c7c", borde: "#eadff0" }

function PantallaNequi({ paso, celular, setCelular, monto, clave, setClave, onContinuar, onPagar, onCambiarNumero }: {
  paso: Paso; celular: string; setCelular: (v: string) => void; monto: number
  clave: string; setClave: (v: string) => void
  onContinuar: () => void; onPagar: () => void; onCambiarNumero: () => void
}) {
  const [verClave, setVerClave] = useState(false)
  const celularOculto = `${celular.slice(0, 3)} *** ${celular.slice(-4)}`
  return (
    <div className="min-h-screen text-white flex flex-col" style={{ background: `radial-gradient(1200px 600px at 80% -10%, #4a1466 0%, ${nq.fondo} 55%)` }}>
      <header className="mx-auto w-full max-w-5xl px-5 py-5 flex items-center justify-between">
        <p className="text-[26px] font-black tracking-tight">Nequi</p>
        <span className="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs text-white/80">
          <Lock className="w-3.5 h-3.5" /> Pago seguro PSE
        </span>
      </header>

      <main className="flex-1 mx-auto w-full max-w-5xl px-4 pb-10 grid items-center gap-8 md:grid-cols-2">
        <div className="hidden md:block space-y-3">
          <p className="text-4xl font-black leading-tight">Paga tus facturas<br />desde tu celular</p>
          <p className="text-white/70 max-w-sm">
            Ingresa con tu número y tu clave Nequi. El comercio nunca conoce tus datos de acceso.
          </p>
        </div>

        <div key={paso} className="animate-in fade-in slide-in-from-bottom-3 duration-300 w-full max-w-sm justify-self-center rounded-3xl p-6 shadow-2xl space-y-5" style={{ background: nq.tarjeta, color: nq.fondo }}>
          <div className="rounded-2xl p-4 space-y-1" style={{ background: "#f7f1fa" }}>
            <p className="text-xs" style={{ color: nq.suave }}>Pago a</p>
            <p className="font-bold">{COMERCIO}</p>
            <p className="text-2xl font-black" style={{ color: nq.acento }}>{formatCOP(monto)}</p>
          </div>

          {paso === "banco" && (
            <>
              <div>
                <h1 className="text-xl font-extrabold">Ingresa tu número Nequi</h1>
                <p className="text-sm mt-1" style={{ color: nq.suave }}>Es el celular con el que entras a la app.</p>
              </div>
              <div className="flex items-center rounded-2xl border-2 transition-colors focus-within:border-[#d4207c]" style={{ borderColor: nq.borde }}>
                <span className="pl-4 pr-2 text-sm font-semibold border-r" style={{ color: nq.suave, borderColor: nq.borde }}>+57</span>
                <input
                  inputMode="numeric" maxLength={10} placeholder="300 123 4567" autoFocus
                  value={celular} onChange={(e) => setCelular(e.target.value.replace(/\D/g, ""))}
                  className="w-full bg-transparent px-3 py-3.5 text-lg font-semibold tracking-wider focus:outline-none"
                />
              </div>
              <button
                disabled={!/^3\d{9}$/.test(celular)} onClick={onContinuar}
                className="w-full rounded-2xl py-3.5 font-bold text-white transition-colors disabled:opacity-40"
                style={{ background: nq.acento }}
              >
                Continuar
              </button>
            </>
          )}

          {paso === "notificacion" && (
            <>
              <div className="space-y-1">
                <h1 className="text-xl font-extrabold">Ingresa tu clave</h1>
                <p className="text-sm" style={{ color: nq.suave }}>
                  La clave de 4 dígitos con la que entras a Nequi desde el {celularOculto}.
                </p>
              </div>
              <label className="relative flex justify-center gap-3 cursor-text">
                {[0, 1, 2, 3].map((i) => (
                  <span
                    key={i}
                    className="flex h-14 w-12 items-center justify-center rounded-2xl border-2 text-2xl font-black transition-colors"
                    style={{ borderColor: i === clave.length ? nq.acento : nq.borde }}
                  >
                    {clave[i] ? (verClave ? clave[i] : "•") : ""}
                  </span>
                ))}
                <input
                  type="password" inputMode="numeric" maxLength={4} autoFocus autoComplete="off"
                  value={clave} onChange={(e) => setClave(e.target.value.replace(/\D/g, "").slice(0, 4))}
                  onKeyDown={(e) => { if (e.key === "Enter" && clave.length === 4) onPagar() }}
                  className="absolute inset-0 opacity-0"
                  aria-label="Clave de 4 dígitos"
                />
              </label>
              <button onClick={() => setVerClave((v) => !v)}
                className="mx-auto flex items-center gap-1 text-xs font-semibold" style={{ color: nq.suave }}>
                {verClave ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                {verClave ? "Ocultar clave" : "Mostrar clave"}
              </button>
              <button
                disabled={clave.length !== 4} onClick={onPagar}
                className="w-full rounded-2xl py-3.5 font-bold text-white transition-colors disabled:opacity-40"
                style={{ background: nq.acento }}
              >
                Pagar {formatCOP(monto)}
              </button>
              <button onClick={onCambiarNumero} className="w-full flex items-center justify-center gap-1 text-sm font-semibold" style={{ color: nq.suave }}>
                <ArrowLeft className="w-4 h-4" /> Cambiar número
              </button>
            </>
          )}

          {paso === "procesando" && (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <Loader2 className="w-10 h-10 animate-spin" style={{ color: nq.acento }} />
              <p className="font-bold">Procesando tu pago</p>
              <p className="text-sm" style={{ color: nq.suave }}>Esto toma unos segundos.</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

function PantallaBanco({ banco, paso, usuario, setUsuario, clave, setClave, monto, onPagar }: {
  banco: string; paso: Paso; usuario: string; setUsuario: (v: string) => void
  clave: string; setClave: (v: string) => void; monto: number; onPagar: () => void
}) {
  return (
    <div className="min-h-screen bg-[#eef1f5] text-[#1d2a44]">
      <header className="bg-[#0f2d52] text-white">
        <div className="mx-auto max-w-4xl px-5 py-4 flex items-center gap-2">
          <Building2 className="w-5 h-5" /><p className="font-bold tracking-wide">{banco}</p>
          <span className="ml-auto flex items-center gap-1 text-xs text-white/70"><Lock className="w-3.5 h-3.5" /> Pago seguro PSE</span>
        </div>
      </header>
      <main className="flex justify-center px-4 pt-10">
        <div key={paso} className="animate-in fade-in slide-in-from-bottom-2 duration-300 w-full max-w-sm rounded-xl bg-white p-6 space-y-4 shadow">
          <div className="rounded-lg bg-[#f4f6f9] p-3 text-sm">
            <p className="text-xs text-[#5b6680]">Pago a {COMERCIO}</p>
            <p className="text-xl font-bold">{formatCOP(monto)}</p>
          </div>
          {paso === "banco" ? (
            <>
              <h1 className="text-lg font-semibold">Ingresa a tu banca en línea</h1>
              <input placeholder="Usuario" value={usuario} onChange={(e) => setUsuario(e.target.value)} className={claseInput} />
              <input placeholder="Clave" type="password" value={clave} onChange={(e) => setClave(e.target.value)} className={claseInput} />
              <button disabled={!usuario.trim() || !clave} onClick={onPagar}
                className="w-full rounded-lg bg-[#0f2d52] py-3 text-sm font-semibold text-white disabled:opacity-40">
                Autorizar pago
              </button>
            </>
          ) : (
            <div className="flex flex-col items-center gap-3 py-6">
              <Loader2 className="w-8 h-8 animate-spin text-[#0f2d52]" />
              <p className="text-sm">Procesando el pago…</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default function Page() {
  return (
    <Suspense>
      <PseSimulado />
    </Suspense>
  )
}

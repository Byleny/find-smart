"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Wallet, ArrowRight, CheckCircle2, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { formatCOP } from "@/lib/format"

// ── Paleta B&W ───────────────────────────────────────────
const INK  = "#0A0A0A"
const CARD = "#141414"
const LIFT = "#1E1E1E"
const EDGE = "#2C2C2C"

// ── Helper: headline con word-stagger ────────────────────
function BigHeadline({ lines }: { lines: string[] }) {
  let idx = 0
  return (
    <h1 className="text-5xl md:text-6xl lg:text-[72px] font-black text-white leading-[1.02] tracking-tighter">
      {lines.map((line, li) => (
        <span key={li} className="block">
          {line.split(" ").map((word) => {
            const i = idx++
            return (
              <span key={i} className="word-clip mr-[0.25em]">
                <span className="w" style={{ animationDelay: `${i * 90 + 120}ms` }}>
                  {word}
                </span>
              </span>
            )
          })}
        </span>
      ))}
    </h1>
  )
}

// ── Número animado ───────────────────────────────────────
function AnimatedNumber({ value }: { value: number }) {
  const [display, setDisplay] = useState(value)
  const prev = useRef(value)
  useEffect(() => {
    const from = prev.current
    prev.current = value
    if (from === value) return
    const start = performance.now()
    const dur = 520
    const tick = (now: number) => {
      const t = Math.min((now - start) / dur, 1)
      const ease = 1 - Math.pow(1 - t, 3)
      setDisplay(Math.round(from + (value - from) * ease))
      if (t < 1) requestAnimationFrame(tick)
      else setDisplay(value)
    }
    requestAnimationFrame(tick)
  }, [value])
  return <>{formatCOP(display)}</>
}

// ── Dashboard B&W animado ────────────────────────────────
const PHASE_MS = [500, 750, 1700, 1600]

function LiveDashboard() {
  const [phase, setPhase] = useState(1)

  useEffect(() => {
    let t: ReturnType<typeof setTimeout>
    const run = (p: number) => {
      t = setTimeout(() => {
        const n = (p + 1) % 4
        setPhase(n)
        run(n)
      }, PHASE_MS[p])
    }
    run(1)
    return () => clearTimeout(t)
  }, [])

  const balance   = phase >= 2 ? 1_155_000 : 1_240_000
  const pctChange = phase >= 2 ? -6.9 : 8.3
  const aliPct    = phase >= 2 ? 75 : 68
  const txVisible = phase !== 0
  const txDone    = phase >= 2
  const gdoLoad   = phase === 2
  const anomPulse = phase === 3

  return (
    <div className="rounded-2xl overflow-hidden select-none"
      style={{ backgroundColor: CARD, border: `1px solid ${EDGE}` }}>

      {/* Chrome */}
      <div className="px-5 py-3 flex items-center justify-between"
        style={{ borderBottom: `1px solid ${EDGE}` }}>
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md flex items-center justify-center bg-white">
            <Wallet className="w-3 h-3 text-black" />
          </div>
          <span className="text-xs font-black text-white">FinSmart</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400"
              style={{ animation: "blink 2s ease-in-out infinite" }} />
            <span className="text-xs" style={{ color: "rgba(255,255,255,0.32)" }}>IA activa</span>
          </div>
          <div className="flex gap-1">
            {["rgba(239,68,68,0.4)", "rgba(234,179,8,0.4)", "rgba(34,197,94,0.55)"].map(c => (
              <div key={c} className="w-2 h-2 rounded-full" style={{ backgroundColor: c }} />
            ))}
          </div>
        </div>
      </div>

      {/* Balance */}
      <div className="px-5 pt-4 pb-3">
        <p className="text-xs font-mono" style={{ color: "rgba(255,255,255,0.28)" }}>Balance del mes</p>
        <div className="flex items-end gap-2.5 mt-1">
          <p className="text-3xl font-black text-white font-mono">
            <AnimatedNumber value={balance} />
          </p>
          <span className="text-sm font-bold mb-0.5"
            style={{ color: pctChange > 0 ? "#4ade80" : "#f87171", transition: "color 0.5s ease" }}>
            {pctChange > 0 ? "+" : ""}{pctChange}%
          </span>
        </div>
      </div>

      {/* TX card */}
      <div className="mx-5 mb-2" style={{ height: "60px" }}>
        <div className="rounded-xl px-3.5 h-full flex items-center"
          style={{
            backgroundColor: txDone ? "rgba(255,255,255,0.09)" : "rgba(255,255,255,0.04)",
            border: `1px solid ${txDone ? "rgba(255,255,255,0.24)" : "rgba(255,255,255,0.07)"}`,
            opacity: txVisible ? 1 : 0,
            transform: txVisible ? "translateY(0)" : "translateY(-6px)",
            transition: "opacity 0.38s ease, transform 0.38s ease, background-color 0.45s ease, border-color 0.45s ease",
          }}>
          <div className="flex items-center justify-between w-full">
            <div>
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-bold text-white">Éxito · Mercado</p>
                <CheckCircle2 className="w-3 h-3 text-white"
                  style={{ opacity: txDone ? 1 : 0, transition: "opacity 0.35s ease" }} />
              </div>
              <p className="text-xs mt-0.5"
                style={{ color: txDone ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.3)", transition: "color 0.4s ease" }}>
                {txDone ? "Categorizado: Alimentación · IA" : "Analizando con IA…"}
              </p>
            </div>
            <p className="text-sm font-black font-mono"
              style={{ color: txDone ? "#fff" : "rgba(255,255,255,0.3)", transition: "color 0.4s ease" }}>
              −$85.000
            </p>
          </div>
        </div>
      </div>

      {/* Barras */}
      <div className="px-5 pb-4 space-y-2.5">
        <p className="text-xs font-mono" style={{ color: "rgba(255,255,255,0.22)" }}>Gastos por categoría</p>
        {[
          { label: "Alimentación", pct: aliPct },
          { label: "Transporte",   pct: 42 },
          { label: "Servicios",    pct: 19 },
        ].map(c => (
          <div key={c.label}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs" style={{ color: "rgba(255,255,255,0.38)" }}>{c.label}</span>
              <span className="text-xs font-semibold font-mono text-white">{c.pct}%</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "rgba(255,255,255,0.07)" }}>
              <div className="h-full rounded-full bg-white"
                style={{ width: `${c.pct}%`, transition: "width 0.9s cubic-bezier(0.25, 0.46, 0.45, 0.94)" }} />
            </div>
          </div>
        ))}
      </div>

      {/* Anomalía */}
      <div className="mx-5 mb-3 rounded-xl px-3.5 py-2.5 flex items-start gap-2.5"
        style={{
          backgroundColor: anomPulse ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.04)",
          border: `1px solid ${anomPulse ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.08)"}`,
          boxShadow: anomPulse ? "0 0 18px rgba(255,255,255,0.06)" : "none",
          transition: "background-color 0.45s ease, border-color 0.45s ease, box-shadow 0.45s ease",
        }}>
        <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-white" style={{ opacity: 0.85 }} />
        <div>
          <p className="text-xs font-bold text-white">Gasto inusual detectado</p>
          <p className="text-xs mt-0.5" style={{ color: "rgba(255,255,255,0.35)" }}>Ropa $145.000 · 3× tu promedio</p>
        </div>
      </div>

      {/* GDO */}
      <div className="mx-5 mb-5 rounded-xl px-3.5 py-3 flex items-center justify-between"
        style={{ backgroundColor: LIFT, border: `1px solid ${EDGE}` }}>
        <div>
          <p className="text-xs font-bold text-white">Factura GDO · Gas</p>
          <p className="text-xs mt-0.5 font-mono" style={{ color: "rgba(255,255,255,0.3)" }}>Vence en 5 días</p>
        </div>
        <div className="text-right">
          <div style={{ position: "relative", height: "20px" }}>
            <p className="text-xs font-mono absolute right-0 whitespace-nowrap"
              style={{ color: "rgba(255,255,255,0.5)", opacity: gdoLoad ? 1 : 0, transition: "opacity 0.32s ease" }}>
              Consultando…
            </p>
            <p className="text-sm font-black text-white font-mono absolute right-0 whitespace-nowrap"
              style={{ opacity: !gdoLoad ? 1 : 0, transition: "opacity 0.32s ease" }}>
              $68.400
            </p>
          </div>
          <p className="text-xs font-mono mt-1" style={{ color: "rgba(255,255,255,0.4)" }}>Pagar con Nequi →</p>
        </div>
      </div>
    </div>
  )
}

// ── Scroll reveal ────────────────────────────────────────
function useScrollReveal() {
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!ref.current) return
    const els = ref.current.querySelectorAll<HTMLElement>(".reveal, .reveal-right")
    const observer = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          const el = e.target as HTMLElement
          setTimeout(() => el.classList.add("visible"), parseInt(el.dataset.delay ?? "0"))
          observer.unobserve(el)
        }
      })
    }, { threshold: 0.1 })
    els.forEach(el => observer.observe(el))
    return () => observer.disconnect()
  }, [])
  return ref
}

// ── Fila editorial de característica ────────────────────
function FeatureRow({ num, title, body, delay }: { num: string; title: string; body: string; delay: number }) {
  return (
    <div className="reveal py-8"
      data-delay={String(delay)}
      style={{ display: "grid", gridTemplateColumns: "52px 1fr", gap: "1.5rem", borderBottom: "1px solid #E5E5E5" }}>
      <span className="text-xs font-mono font-bold pt-1" style={{ color: "#BBBBBB" }}>{num}</span>
      <div>
        <h3 className="text-base font-black tracking-tight mb-1.5" style={{ color: "#0A0A0A" }}>{title}</h3>
        <p className="text-sm leading-relaxed" style={{ color: "#666666" }}>{body}</p>
      </div>
    </div>
  )
}

// ── Página ───────────────────────────────────────────────
export default function LandingPage() {
  const mainRef = useScrollReveal()

  return (
    <div className="min-h-screen" ref={mainRef}>

      {/* Grain overlay */}
      <div className="grain-overlay" aria-hidden="true" />

      {/* ─── Header ─────────────────────────────────────── */}
      <header className="sticky top-0 z-50"
        style={{ backgroundColor: INK, borderBottom: `1px solid ${EDGE}` }}>
        <div className="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-white flex items-center justify-center">
              <Wallet className="w-3.5 h-3.5 text-black" />
            </div>
            <span className="text-lg font-black text-white tracking-tight">FinSmart</span>
          </div>
          <nav className="hidden md:flex items-center gap-6">
            {[
              ["#caracteristicas", "Características"],
              ["#metricas",        "En números"],
            ].map(([href, label]) => (
              <a key={href} href={href}
                className="text-sm transition-colors"
                style={{ color: "rgba(255,255,255,0.38)" }}
                onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
                onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,0.38)")}>
                {label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm"
              className="font-medium hover:bg-white/10"
              style={{ color: "rgba(255,255,255,0.45)" }} asChild>
              <Link href="/login">Iniciar sesión</Link>
            </Button>
            <Button size="sm" asChild className="bg-white text-black font-bold hover:bg-white/88">
              <Link href="/login">Comenzar gratis</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* ─── Hero ───────────────────────────────────────── */}
      <section style={{ backgroundColor: INK, paddingTop: "64px", paddingBottom: "72px", overflow: "hidden" }}>
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 items-center">

            <div>
              <div className="flex items-center gap-3 mb-8" style={{ animation: "fadeInUp 0.45s ease both" }}>
                <div className="h-px w-8" style={{ backgroundColor: "rgba(255,255,255,0.25)" }} />
                <span className="text-xs font-mono uppercase tracking-widest"
                  style={{ color: "rgba(255,255,255,0.38)" }}>
                  Finanzas personales · IA · Colombia
                </span>
              </div>

              <BigHeadline lines={["Tus finanzas,", "más inteligentes"]} />

              <p className="mt-6 text-base leading-relaxed max-w-[420px]"
                style={{ color: "rgba(255,255,255,0.4)", animation: "fadeInUp 0.6s ease both", animationDelay: "500ms" }}>
                Registra un gasto y la IA lo categoriza sola. Consulta tu factura al instante. Recibe alertas cuando gastes más de lo normal.
              </p>

              <div className="mt-8 flex flex-col sm:flex-row gap-3"
                style={{ animation: "fadeInUp 0.6s ease both", animationDelay: "600ms" }}>
                <Button size="lg" asChild className="bg-white text-black font-bold hover:bg-white/88">
                  <Link href="/login">Crear cuenta <ArrowRight className="ml-2 w-4 h-4" /></Link>
                </Button>
                <Button size="lg" variant="outline" asChild className="font-medium transition-all"
                  style={{ borderColor: "rgba(255,255,255,0.14)", color: "rgba(255,255,255,0.48)", backgroundColor: "transparent" }}>
                  <a href="#caracteristicas">Ver qué hace</a>
                </Button>
              </div>

              <div className="mt-10 flex items-center"
                style={{ animation: "fadeInUp 0.6s ease both", animationDelay: "700ms" }}>
                {[
                  { val: "3",     label: "modelos de IA" },
                  { val: "2",     label: "proveedores" },
                  { val: "$0",    label: "siempre gratis" },
                ].map((s, i) => (
                  <div key={s.label} className="flex items-center">
                    {i > 0 && <div className="w-px h-9 mx-7" style={{ backgroundColor: "rgba(255,255,255,0.1)" }} />}
                    <div>
                      <p className="text-2xl font-black text-white font-mono">{s.val}</p>
                      <p className="text-xs mt-0.5 font-mono" style={{ color: "rgba(255,255,255,0.26)" }}>{s.label}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative" style={{ animation: "fadeInRight 0.7s ease both", animationDelay: "200ms" }}>
              <div className="absolute -top-5 right-2 z-10 hidden lg:flex items-center gap-1.5
                text-xs font-bold px-3 py-1.5 rounded-full bg-white text-black"
                style={{ boxShadow: "0 4px 16px rgba(255,255,255,0.14)", animation: "fadeInUp 0.5s ease both", animationDelay: "750ms" }}>
                ✓ Categorización automática
              </div>
              <div className="absolute -bottom-5 left-2 z-10 hidden lg:flex items-center gap-1.5
                text-xs font-bold px-3 py-1.5 rounded-full bg-white text-black"
                style={{ boxShadow: "0 4px 16px rgba(255,255,255,0.1)", animation: "fadeInUp 0.5s ease both", animationDelay: "860ms" }}>
                Nequi · PSE →
              </div>
              <div style={{ animation: "float 9s ease-in-out infinite" }}>
                <LiveDashboard />
              </div>
              <div className="absolute -inset-12 -z-10 pointer-events-none"
                style={{ background: "radial-gradient(ellipse at 55% 50%, rgba(255,255,255,0.035), transparent 65%)", animation: "glowPulse 6s ease-in-out infinite" }} />
            </div>
          </div>

          <div className="flex justify-center mt-14">
            <a href="#caracteristicas" className="flex flex-col items-center gap-2 group">
              <span className="text-xs font-mono" style={{ color: "rgba(255,255,255,0.16)" }}>Descubre todo lo que hace</span>
              <span className="text-white/20 group-hover:text-white/40 transition-colors text-sm animate-bounce">↓</span>
            </a>
          </div>
        </div>
      </section>

      {/* ─── Características ────────────────────────────── */}
      <section id="caracteristicas" style={{ backgroundColor: "#FFFFFF", paddingTop: "96px", paddingBottom: "88px" }}>
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-20">

            <div className="lg:sticky lg:top-24 self-start">
              <p className="text-xs font-mono uppercase tracking-widest mb-5" style={{ color: "#AAAAAA" }}>Características</p>
              <h2 className="text-4xl md:text-5xl font-black tracking-tighter leading-[1.02] reveal"
                data-delay="0" style={{ color: "#0A0A0A" }}>
                Lo que hace<br />FinSmart<br />diferente
              </h2>
              <p className="mt-5 text-sm leading-relaxed reveal" data-delay="100" style={{ color: "#777777" }}>
                No es solo un registro de gastos — es un sistema que aprende cómo gastas y trabaja en segundo plano.
              </p>
              <div className="mt-8 reveal" data-delay="200">
                <Button asChild className="bg-black text-white font-bold hover:bg-black/88">
                  <Link href="/login">Crear cuenta <ArrowRight className="ml-2 w-4 h-4" /></Link>
                </Button>
              </div>
            </div>

            <div>
              <div style={{ borderTop: "1px solid #E5E5E5" }}>
                <FeatureRow num="01" delay={60}
                  title="Categorización con IA"
                  body="Escribe la descripción del gasto y el modelo de Regresión Logística — entrenado solo con tus transacciones — sugiere la categoría con confianza. Con 10 registros ya funciona; con 200, alcanza el 90,9 % de precisión." />
                <FeatureRow num="02" delay={130}
                  title="Consulta de facturas"
                  body="Registra tu contrato de GDO (Gases de Occidente) o EMCALI. FinSmart consulta el portal automáticamente y te muestra el monto, la fecha de vencimiento y el enlace de pago Nequi o PSE." />
                <FeatureRow num="03" delay={200}
                  title="Alertas de gasto inusual"
                  body="Isolation Forest analiza cada nuevo gasto y te avisa si rompe tu patrón histórico — antes de que te sorprenda el extracto bancario. Cuantos más datos tienes, más precisa la alerta." />
                <FeatureRow num="04" delay={270}
                  title="Detección de pagos recurrentes"
                  body="DBSCAN agrupa las descripciones de gasto y detecta cuáles se repiten con regularidad mensual, incluso si nunca las marcaste manualmente como recurrentes." />
                <FeatureRow num="05" delay={340}
                  title="Gastos compartidos"
                  body="Crea grupos con familia o amigos, registra gastos compartidos y calcula automáticamente quién le debe cuánto a quién. Los miembros no necesitan tener cuenta en FinSmart." />
                <FeatureRow num="06" delay={410}
                  title="Presupuestos y metas de ahorro"
                  body="Define límites de gasto por categoría con alertas visuales. Crea metas de ahorro con fecha límite y sigue tu avance semana a semana con barra de progreso." />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Métricas ───────────────────────────────────── */}
      <section id="metricas" style={{ backgroundColor: INK, paddingTop: "88px", paddingBottom: "88px" }}>
        <div className="max-w-7xl mx-auto px-6">
          <div className="mb-14 reveal" data-delay="0">
            <p className="text-xs font-mono uppercase tracking-widest mb-4" style={{ color: "rgba(255,255,255,0.25)" }}>
              En números
            </p>
            <h2 className="text-4xl md:text-5xl font-black text-white tracking-tighter leading-[1.02]">
              Lo que el sistema<br />puede hacer
            </h2>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-0" style={{ borderTop: `1px solid ${EDGE}` }}>
            {[
              { val: "90,9%", label: "Precisión en categorización", sub: "con 208 transacciones y CV-5" },
              { val: "3",     label: "Modelos de IA complementarios", sub: "Regresión Logística · Isolation Forest · DBSCAN" },
              { val: "<10s",  label: "Para consultar una factura",  sub: "desde el portal del proveedor" },
              { val: "$0",    label: "Costo permanente",            sub: "sin plan de pago, sin límites" },
            ].map((m, i) => (
              <div key={i} className="reveal py-10 px-6" data-delay={String(i * 80)}
                style={{ borderBottom: `1px solid ${EDGE}`, borderRight: i < 3 ? `1px solid ${EDGE}` : "none" }}>
                <p className="text-4xl md:text-5xl font-black text-white font-mono mb-3">{m.val}</p>
                <p className="text-sm font-bold text-white mb-1">{m.label}</p>
                <p className="text-xs font-mono" style={{ color: "rgba(255,255,255,0.28)" }}>{m.sub}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA Final ──────────────────────────────────── */}
      <section style={{ backgroundColor: INK, paddingTop: "96px", paddingBottom: "96px" }}>
        <div className="max-w-lg mx-auto px-6 text-center reveal" data-delay="0">
          <p className="text-xs font-mono uppercase tracking-widest mb-6" style={{ color: "rgba(255,255,255,0.22)" }}>
            Empieza hoy
          </p>
          <h2 className="text-4xl md:text-[52px] font-black tracking-tighter leading-[1.02] text-white">
            Organiza tus<br />finanzas ahora
          </h2>
          <p className="mt-4 text-base leading-relaxed" style={{ color: "rgba(255,255,255,0.4)" }}>
            Gratis, sin instalación, funciona en cualquier dispositivo.
          </p>
          <Button size="lg" asChild className="mt-8 bg-white text-black font-bold hover:bg-white/88">
            <Link href="/login">Crear cuenta <ArrowRight className="ml-2 w-4 h-4" /></Link>
          </Button>
          <p className="text-xs mt-4 font-mono" style={{ color: "rgba(255,255,255,0.2)" }}>
            Sin tarjeta · Sin suscripción · Sin límites
          </p>
        </div>
      </section>

      {/* ─── Footer ─────────────────────────────────────── */}
      <footer style={{ backgroundColor: INK, borderTop: `1px solid ${EDGE}` }}>
        <div className="max-w-7xl mx-auto px-6 py-7 flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ backgroundColor: "rgba(255,255,255,0.08)" }}>
              <Wallet className="w-3 h-3" style={{ color: "rgba(255,255,255,0.6)" }} />
            </div>
            <span className="text-sm font-black text-white">FinSmart</span>
          </div>
          <div className="flex items-center gap-6">
            {[["#caracteristicas","Características"],["#metricas","En números"]].map(([href, label]) => (
              <a key={href} href={href} className="text-xs font-mono transition-colors"
                style={{ color: "rgba(255,255,255,0.28)" }}
                onMouseEnter={e => (e.currentTarget.style.color = "rgba(255,255,255,0.7)")}
                onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,0.28)")}>
                {label}
              </a>
            ))}
          </div>
          <p className="text-xs font-mono" style={{ color: "rgba(255,255,255,0.18)" }}>
            © 2026 FinSmart. Todos los derechos reservados.
          </p>
        </div>
      </footer>
    </div>
  )
}

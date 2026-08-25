"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import Link from "next/link"
import { Wallet, Eye, EyeOff, ArrowLeft, Loader2, Lock, Brain, AlertTriangle, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/contexts/auth-context"

const D = "#0F1117"
const S = "#1A1C27"

type Phase = "idle" | "out" | "in"

const previewCards = [
  {
    icon: Brain,
    label: "Categorización automática",
    value: "94% precisión",
    sub: "Supermercado · Alimentación",
    valueColor: "#ffffff",
    borderColor: "rgba(255,255,255,0.12)",
    iconBg: "rgba(255,255,255,0.08)",
    anim: "cardFloat1 5.5s ease-in-out infinite",
    delay: "0s",
  },
  {
    icon: AlertTriangle,
    label: "Gasto inusual detectado",
    value: "$145.000",
    sub: "3× tu promedio en Ropa",
    valueColor: "#f87171",
    borderColor: "rgba(239,68,68,0.2)",
    iconBg: "rgba(239,68,68,0.1)",
    anim: "cardFloat2 6.8s ease-in-out infinite",
    delay: "1.1s",
  },
  {
    icon: RefreshCcw,
    label: "Pago recurrente",
    value: "$68.400",
    sub: "GDO · Factura de gas",
    valueColor: "#93c5fd",
    borderColor: "rgba(96,165,250,0.2)",
    iconBg: "rgba(96,165,250,0.08)",
    anim: "cardFloat3 5s ease-in-out infinite",
    delay: "0.6s",
  },
]

export default function LoginPage() {
  const { login, register } = useAuth()
  const [isLogin, setIsLogin] = useState(true)
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const [focusedField, setFocusedField] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>("idle")
  const [shaking, setShaking] = useState(false)
  const [formData, setFormData] = useState({ email: "", password: "", name: "", confirmPassword: "" })
  const switchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isPrivate = focusedField === "password" || focusedField === "confirmPassword"

  const fillTest = () => setFormData({ ...formData, email: "evaluacion@finsmart.co", password: "demo1234" })

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get("mode") === "register") setIsLogin(false)
  }, [])

  const triggerShake = useCallback(() => {
    setShaking(true)
    setTimeout(() => setShaking(false), 600)
  }, [])

  const switchMode = () => {
    if (phase !== "idle") return
    setPhase("out")
    if (switchTimeout.current) clearTimeout(switchTimeout.current)
    switchTimeout.current = setTimeout(() => {
      setIsLogin(p => !p)
      setError("")
      setPhase("in")
      setTimeout(() => setPhase("idle"), 350)
    }, 220)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (!isLogin && formData.password !== formData.confirmPassword) {
      setError("Las contraseñas no coinciden")
      triggerShake()
      return
    }
    setIsLoading(true)
    try {
      if (isLogin) {
        await login(formData.email, formData.password)
      } else {
        await register(formData.email, formData.password, formData.name)
      }
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string } }; request?: unknown }
      const detail = axErr.response?.data?.detail
      if (!axErr.response) {
        setError("No se pudo conectar con el servidor. Verifica tu conexión e intenta de nuevo.")
      } else if (detail === "Email already registered") {
        setError("Ese correo ya está registrado. Inicia sesión en su lugar.")
      } else if (detail === "Incorrect email or password") {
        setError("Correo o contraseña incorrectos.")
      } else if (typeof detail === "string" && detail.length > 0) {
        setError(detail)
      } else {
        setError(isLogin ? "Credenciales incorrectas. Intenta de nuevo." : "Error al crear la cuenta. Intenta de nuevo.")
      }
      triggerShake()
    } finally {
      setIsLoading(false)
    }
  }

  const fieldProps = (id: string) => ({
    onFocus: () => setFocusedField(id),
    onBlur: () => setFocusedField(null),
  })

  const dimStyle = (fieldId: string) => ({
    transition: "opacity 0.35s ease, filter 0.35s ease",
    opacity: isPrivate && fieldId !== "password" && fieldId !== "confirmPassword" ? 0.22 : 1,
    filter: isPrivate && fieldId !== "password" && fieldId !== "confirmPassword" ? "blur(0.5px)" : "none",
  })

  const formAnim = phase === "out"
    ? "switchOut 0.22s cubic-bezier(0.4,0,1,1) forwards"
    : phase === "in"
    ? "switchIn 0.35s cubic-bezier(0,0,0.2,1) forwards"
    : "none"

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: D }}>

      {/* ── Left panel ─────────────────────────────────── */}
      <div className="flex-1 flex flex-col justify-center px-6 lg:px-16 py-12 relative"
        style={{ backgroundColor: "#FAFAF8", overflow: "hidden" }}>

        {/* Privacy overlay */}
        <div style={{
          position: "absolute", inset: 0, pointerEvents: "none",
          backgroundColor: "rgba(0,0,0,0.04)",
          opacity: isPrivate ? 1 : 0,
          transition: "opacity 0.4s ease",
          zIndex: 0,
        }} />

        <div className="relative z-10 w-full max-w-md mx-auto">
          <Link href="/"
            className="inline-flex items-center gap-2 text-sm mb-8 transition-colors"
            style={{ color: "#A09890" }}>
            <ArrowLeft className="w-4 h-4" />
            Volver al inicio
          </Link>

          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: D }}>
              <Wallet className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-black" style={{ color: D }}>FinSmart</span>
          </div>

          {/* Title */}
          <div style={{ animation: formAnim, marginBottom: "28px" }}>
            <h1 className="text-2xl font-black" style={{ color: D }}>
              {isLogin ? "Bienvenido de nuevo" : "Crea tu cuenta"}
            </h1>
            <p className="mt-2 text-sm" style={{ color: "#78716C" }}>
              {isLogin
                ? "Ingresa tus datos para acceder a tu cuenta"
                : "Comienza a gestionar tus finanzas hoy mismo"}
            </p>
          </div>

          {/* Demo banner */}
          {isLogin && (
            <div className="rounded-xl px-4 py-3 mb-5 flex items-center justify-between"
              style={{ backgroundColor: "#F0EDE7", border: "1px solid #E0DDD7" }}>
              <div>
                <p className="text-xs font-bold" style={{ color: D }}>Cuenta de prueba</p>
                <p className="text-xs mt-0.5" style={{ color: "#78716C" }}>evaluacion@finsmart.co · demo1234</p>
              </div>
              <Button type="button" size="sm" onClick={fillTest}
                className="text-xs font-semibold hover:opacity-80"
                style={{ backgroundColor: D, color: "white" }}>
                Usar
              </Button>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm"
              style={{ backgroundColor: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#DC2626" }}>
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit}
            style={{ animation: shaking ? "shake 0.55s ease" : formAnim }}
            className="space-y-4">

            {!isLogin && (
              <div style={dimStyle("name")}>
                <label htmlFor="name" className="block text-sm font-semibold mb-1.5" style={{ color: D }}>
                  Nombre completo
                </label>
                <Input id="name" type="text" placeholder="Juan Pérez" className="h-11"
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  {...fieldProps("name")} required />
              </div>
            )}

            <div style={dimStyle("email")}>
              <label htmlFor="email" className="block text-sm font-semibold mb-1.5" style={{ color: D }}>
                Correo electrónico
              </label>
              <Input id="email" type="email" placeholder="tu@email.com" className="h-11"
                value={formData.email}
                onChange={e => setFormData({ ...formData, email: e.target.value })}
                {...fieldProps("email")} required />
            </div>

            {/* Password with privacy mode */}
            <div>
              <label htmlFor="password" className="flex items-center gap-1.5 text-sm font-semibold mb-1.5"
                style={{ color: isPrivate ? D : D, transition: "color 0.3s ease" }}>
                Contraseña
                <Lock className="w-3 h-3"
                  style={{
                    color: "#78716C",
                    opacity: isPrivate ? 1 : 0,
                    transform: isPrivate ? "scale(1)" : "scale(0.6)",
                    transition: "opacity 0.3s, transform 0.3s",
                  }} />
              </label>
              <div className="relative"
                style={{
                  boxShadow: isPrivate ? "0 0 0 3px rgba(0,0,0,0.12)" : "none",
                  borderRadius: "calc(var(--radius) + 2px)",
                  transition: "box-shadow 0.35s ease",
                }}>
                <Input id="password" type={showPassword ? "text" : "password"}
                  placeholder="••••••••" className="h-11 pr-12"
                  value={formData.password}
                  onChange={e => setFormData({ ...formData, password: e.target.value })}
                  {...fieldProps("password")} required />
                <button type="button" onClick={() => setShowPassword(p => !p)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 transition-colors"
                  style={{ color: "#94908C" }}>
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {!isLogin && (
              <div>
                <label htmlFor="confirmPassword" className="flex items-center gap-1.5 text-sm font-semibold mb-1.5"
                  style={{ color: D }}>
                  Confirmar contraseña
                  <Lock className="w-3 h-3"
                    style={{
                      color: "#78716C",
                      opacity: focusedField === "confirmPassword" ? 1 : 0,
                      transition: "opacity 0.3s",
                    }} />
                </label>
                <div style={{
                  boxShadow: focusedField === "confirmPassword" ? "0 0 0 3px rgba(0,0,0,0.12)" : "none",
                  borderRadius: "calc(var(--radius) + 2px)",
                  transition: "box-shadow 0.35s",
                }}>
                  <Input id="confirmPassword" type="password" placeholder="••••••••" className="h-11"
                    value={formData.confirmPassword}
                    onChange={e => setFormData({ ...formData, confirmPassword: e.target.value })}
                    {...fieldProps("confirmPassword")} required />
                </div>
              </div>
            )}

            <Button type="submit" className="w-full h-11 font-bold mt-2 hover:opacity-90"
              style={{ backgroundColor: D, color: "white" }}
              disabled={isLoading}>
              {isLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {isLogin ? "Iniciar Sesión" : "Crear Cuenta"}
            </Button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t" style={{ borderColor: "#E0DDD7" }} />
            </div>
            <div className="relative flex justify-center">
              <span className="px-3 text-xs" style={{ backgroundColor: "#FAFAF8", color: "#B5ADA6" }}>
                o continúa con
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              {
                label: "Google",
                svg: <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>,
              },
              {
                label: "GitHub",
                svg: <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>,
              },
            ].map(btn => (
              <Button key={btn.label} variant="outline" className="h-10 text-sm" disabled
                style={{ borderColor: "#E0DDD7", color: "#78716C" }}>
                {btn.svg}
                {btn.label}
              </Button>
            ))}
          </div>

          <p className="mt-8 text-center text-sm" style={{ color: "#78716C" }}>
            {isLogin ? "¿No tienes una cuenta?" : "¿Ya tienes una cuenta?"}
            <button type="button" onClick={switchMode}
              className="ml-1.5 font-bold hover:underline"
              style={{ color: D }}>
              {isLogin ? "Regístrate" : "Inicia sesión"}
            </button>
          </p>
        </div>
      </div>

      {/* ── Right panel ─────────────────────────────────── */}
      <div className="hidden lg:flex flex-1 flex-col justify-between p-14 relative overflow-hidden"
        style={{ backgroundColor: D }}>

        {/* Ambient glow — subtle white */}
        <div className="absolute top-0 right-0 w-[500px] h-[500px] rounded-full pointer-events-none"
          style={{
            background: "radial-gradient(circle, rgba(255,255,255,0.04) 0%, transparent 65%)",
            transform: "translate(30%, -30%)",
          }} />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-white/10">
            <Wallet className="w-4 h-4 text-white" />
          </div>
          <span className="text-base font-black text-white">FinSmart</span>
        </div>

        {/* Floating cards */}
        <div className="relative z-10 flex flex-col gap-4 flex-1 justify-center">
          <p className="text-xs font-bold uppercase tracking-widest mb-4" style={{ color: "rgba(255,255,255,0.35)" }}>
            Tu IA en acción
          </p>
          {previewCards.map(card => {
            const Icon = card.icon
            return (
              <div key={card.label}
                className="rounded-2xl px-5 py-4 flex items-center gap-4"
                style={{
                  backgroundColor: S,
                  border: `1px solid ${card.borderColor}`,
                  animation: card.anim,
                  animationDelay: card.delay,
                }}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ backgroundColor: card.iconBg }}>
                  <Icon className="w-4.5 h-4.5" style={{ color: card.valueColor, width: 18, height: 18 }} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-white truncate">{card.label}</p>
                  <p className="text-xs mt-0.5 truncate" style={{ color: "rgba(255,255,255,0.38)" }}>{card.sub}</p>
                </div>
                <p className="text-sm font-black flex-shrink-0 tabular-nums" style={{ color: card.valueColor }}>
                  {card.value}
                </p>
              </div>
            )
          })}

          <div className="mt-4 rounded-2xl px-5 py-4"
            style={{ backgroundColor: S, border: "1px solid rgba(255,255,255,0.08)" }}>
            <p className="text-xs font-semibold text-white mb-2">Modelos en aprendizaje</p>
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#22C55E", animation: "blink 2s ease-in-out infinite" }} />
              <span className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>Reentrenando con nuevos datos</span>
            </div>
          </div>
        </div>

        <p className="relative z-10 text-xs" style={{ color: "rgba(255,255,255,0.18)" }}>
          © 2026 FinSmart
        </p>
      </div>
    </div>
  )
}

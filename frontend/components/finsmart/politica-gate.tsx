"use client"

import { useState } from "react"
import { Loader2, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { useAuth } from "@/contexts/auth-context"

/**
 * Pantalla que bloquea la plataforma hasta que el usuario acepte la política de tratamiento
 * de datos vigente. Aplica a las cuentas creadas antes de que existiera la política y a
 * todas cuando se publica una versión nueva.
 */
export function PoliticaGate() {
  const { user, aceptarPolitica, logout } = useAuth()
  const [acepta, setAcepta] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState("")

  async function aceptar() {
    setEnviando(true)
    setError("")
    try {
      await aceptarPolitica()
    } catch {
      setError("No se pudo registrar tu autorización. Intenta de nuevo.")
      setEnviando(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-lg space-y-5 rounded-2xl border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-primary" />
          <h1 className="text-lg font-bold text-foreground">Autoriza el uso de tus datos</h1>
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {user?.politica_version
            ? "Actualizamos la política de tratamiento de datos. "
            : ""}
          Para seguir usando FinSmart necesitamos tu autorización para tratar tus datos personales.
          Los usamos para mostrarte tus finanzas, entrenar con tu historial los modelos que te
          sugieren categorías y detectan patrones, consultar tus facturas cuando lo pidas y, sin
          identificarte, en el trabajo de grado del que hace parte la plataforma.
        </p>
        <p className="text-sm">
          <a href="/privacidad" target="_blank" rel="noopener noreferrer" className="font-medium underline">
            Leer la política completa
          </a>
        </p>
        <label className="flex items-start gap-3 text-sm text-foreground">
          <Checkbox
            checked={acepta}
            onCheckedChange={(v) => setAcepta(v === true)}
            className="mt-0.5"
          />
          <span>He leído y acepto la política de tratamiento de datos personales.</span>
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex flex-col gap-2 sm:flex-row-reverse">
          <Button className="flex-1" disabled={!acepta || enviando} onClick={aceptar}>
            {enviando && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Aceptar y continuar
          </Button>
          <Button variant="outline" className="flex-1" onClick={logout}>
            Cerrar sesión
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Si no la aceptas, tus datos no se usan. Puedes pedir que se borren escribiendo al correo
          que aparece en la política.
        </p>
      </div>
    </div>
  )
}

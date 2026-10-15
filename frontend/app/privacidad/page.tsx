"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { Loader2, Wallet } from "lucide-react"
import { authService } from "@/lib/services/auth"
import { PoliticaTexto } from "@/components/finsmart/politica-texto"
import type { PoliticaDatos } from "@/lib/types"

export default function PrivacidadPage() {
  const [datos, setDatos] = useState<PoliticaDatos | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    authService.politica().then(setDatos).catch(() => setError(true))
  }, [])

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <Link href="/" className="mb-8 inline-flex items-center gap-2">
          <Wallet className="h-5 w-5" />
          <span className="text-lg font-black tracking-tight">FinSmart</span>
        </Link>
        <h1 className="mb-6 text-2xl font-bold text-foreground">
          Política de tratamiento de datos personales
        </h1>
        {datos ? (
          <PoliticaTexto datos={datos} />
        ) : error ? (
          <p className="text-sm text-destructive">
            No se pudo cargar la política en este momento. Intenta de nuevo más tarde.
          </p>
        ) : (
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        )}
      </div>
    </div>
  )
}

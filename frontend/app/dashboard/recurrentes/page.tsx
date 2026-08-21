"use client"

import { useState, useEffect, useCallback } from "react"
import { TrendingUp, RefreshCw, Loader2, Calendar, Repeat, Clock, ChevronRight } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { recurringService } from "@/lib/services/recurring"
import type { PatternResult } from "@/lib/types"

function intervalLabel(days: number): string {
  if (days >= 25 && days <= 35) return "Mensual"
  if (days >= 13 && days <= 16) return "Quincenal"
  if (days >= 6 && days <= 8)   return "Semanal"
  if (days >= 85 && days <= 95) return "Trimestral"
  return `Cada ${days} días`
}

function intervalColor(days: number): string {
  if (days >= 25 && days <= 35) return "bg-blue-500/10 text-blue-600 dark:text-blue-400"
  if (days >= 13 && days <= 16) return "bg-violet-500/10 text-violet-600 dark:text-violet-400"
  if (days >= 6 && days <= 8)   return "bg-amber-500/10 text-amber-600 dark:text-amber-400"
  return "bg-secondary text-muted-foreground"
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-destructive"
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-secondary overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-muted-foreground w-8 text-right">{pct}%</span>
    </div>
  )
}

function formatDate(iso?: string) {
  if (!iso) return "—"
  return new Date(iso + "T00:00:00").toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" })
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export default function RecurrentesPage() {
  const [patterns, setPatterns] = useState<PatternResult[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const pats = await recurringService.getPatterns().catch(() => [] as PatternResult[])
      setPatterns(Array.isArray(pats) ? pats : [])
      setLastRefresh(new Date())
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const monthly   = patterns.filter(p => p.detected_day >= 25 && p.detected_day <= 35)
  const biweekly  = patterns.filter(p => p.detected_day >= 13 && p.detected_day < 25)
  const weekly    = patterns.filter(p => p.detected_day >= 6  && p.detected_day < 13)
  const other     = patterns.filter(p => p.detected_day > 35 || p.detected_day < 6)

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Gastos Recurrentes</h1>
          <p className="text-muted-foreground mt-1">
            Patrones detectados automáticamente por IA en tu historial de transacciones
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={isLoading}>
          {isLoading
            ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            : <RefreshCw className="w-4 h-4 mr-2" />}
          Actualizar
        </Button>
      </div>

      {/* How it works banner */}
      <div className="mb-6 p-4 rounded-xl border border-border bg-secondary/30">
        <div className="flex items-start gap-3">
          <TrendingUp className="w-5 h-5 text-muted-foreground mt-0.5 flex-shrink-0" />
          <div className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">¿Cómo funciona la detección?</span>{" "}
            El modelo analiza las descripciones de tus gastos usando TF-IDF con n-gramas de caracteres,
            agrupa los similares con DBSCAN y mide la regularidad temporal de cada grupo.
            Un patrón se reporta cuando aparece al menos 3 veces con un intervalo medio ≥ 7 días.
            La confianza refleja qué tan constante es ese intervalo.
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : patterns.length === 0 ? (
        <Card className="text-center py-16">
          <CardContent>
            <TrendingUp className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <p className="font-medium text-foreground mb-2">Sin patrones detectados aún</p>
            <p className="text-sm text-muted-foreground">
              Registra más transacciones durante varios meses para que la IA pueda detectar tus gastos recurrentes.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Summary pills */}
          <div className="flex flex-wrap gap-3 mb-6">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-secondary text-sm font-medium text-foreground">
              <Repeat className="w-4 h-4" />
              {patterns.length} patrones detectados
            </div>
            {monthly.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 text-sm font-medium text-blue-600 dark:text-blue-400">
                <Calendar className="w-4 h-4" />
                {monthly.length} mensuales
              </div>
            )}
            {biweekly.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 text-sm font-medium text-violet-600 dark:text-violet-400">
                <Calendar className="w-4 h-4" />
                {biweekly.length} quincenales
              </div>
            )}
            {lastRefresh && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary text-xs text-muted-foreground ml-auto">
                <Clock className="w-3.5 h-3.5" />
                Actualizado {lastRefresh.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}
              </div>
            )}
          </div>

          {/* Pattern groups */}
          {[
            { label: "Mensuales",   items: monthly,  badge: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
            { label: "Quincenales", items: biweekly, badge: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
            { label: "Semanales",   items: weekly,   badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
            { label: "Otros",       items: other,    badge: "bg-secondary text-muted-foreground" },
          ].filter(g => g.items.length > 0).map(({ label, items, badge }) => (
            <div key={label} className="mb-8">
              <div className="flex items-center gap-2 mb-3">
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${badge}`}>{label}</span>
                <div className="flex-1 h-px bg-border" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {items.map((p, i) => (
                  <Card key={i} className="overflow-hidden hover:shadow-sm transition-shadow">
                    <CardContent className="p-0">
                      {/* Card header strip */}
                      <div className="px-4 pt-4 pb-3 border-b border-border">
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-semibold text-foreground leading-tight capitalize">
                            {capitalize(p.service_name)}
                          </h3>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${intervalColor(p.detected_day)}`}>
                            {intervalLabel(p.detected_day)}
                          </span>
                        </div>
                        <ConfidenceBar value={p.confidence} />
                      </div>

                      {/* Detection context */}
                      <div className="px-4 py-3 space-y-2 text-xs text-muted-foreground">
                        <div className="flex justify-between">
                          <span>Detecciones</span>
                          <span className="font-medium text-foreground">{p.occurrences} veces</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Intervalo promedio</span>
                          <span className="font-medium text-foreground">cada {p.detected_day} días</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Primera vez detectado</span>
                          <span className="font-medium text-foreground">{formatDate(p.first_seen)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Último registro</span>
                          <span className="font-medium text-foreground">{formatDate(p.last_seen)}</span>
                        </div>
                      </div>

                      {/* Next predicted */}
                      <div className="px-4 py-2.5 bg-secondary/40 flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">Próximo estimado</span>
                        <div className="flex items-center gap-1 text-xs font-semibold text-foreground">
                          {formatDate(p.next_predicted_date)}
                          <ChevronRight className="w-3 h-3 text-muted-foreground" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

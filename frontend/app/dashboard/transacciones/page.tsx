"use client"

import { Suspense, useState, useEffect, useCallback, useMemo } from "react"
import { useSearchParams } from "next/navigation"
import { useRef } from "react"
import {
  Plus, Search, Download,
  ShoppingCart, Home, Car, Utensils, Zap, Film, Heart, PiggyBank,
  MoreHorizontal, ArrowUpRight, ArrowDownRight, Calendar,
  Loader2, Trash2, Edit2, TrendingUp, TrendingDown, Minus,
  Sparkles, AlertTriangle, Brain, RefreshCw, History, ArrowRightLeft
} from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { transactionService } from "@/lib/services/transactions"
import type { Transaction, TrendResult, MLSuggestion, MLMetrics, AnomalyScore } from "@/lib/types"
import { formatCOP } from "@/lib/format"

const categoryIcons: Record<string, React.ElementType> = {
  "Compras": ShoppingCart, "Vivienda": Home, "Transporte": Car,
  "Alimentación": Utensils, "Servicios": Zap, "Entretenimiento": Film, "Salud": Heart, "Ahorro": PiggyBank,
}

const expenseCategories = ["Alimentación", "Transporte", "Vivienda", "Entretenimiento", "Servicios", "Salud", "Compras", "Ahorro", "Otros"]
const incomeCategories = ["Salario", "Freelance", "Inversiones", "Regalos", "Ventas", "Otros"]
const allCategories = ["Todos", ...expenseCategories]

export default function TransaccionesPage() {
  return (
    <Suspense fallback={null}>
      <TransaccionesContent />
    </Suspense>
  )
}

function TransaccionesContent() {
  const searchParams = useSearchParams()
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState("")
  const [selectedCategory, setSelectedCategory] = useState("Todos")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [summary, setSummary] = useState({ total_income: 0, total_expenses: 0, balance: 0 })
  const [trends, setTrends] = useState<TrendResult[]>([])
  const [mlMetrics, setMlMetrics] = useState<MLMetrics | null>(null)
  const [anomalies, setAnomalies] = useState<Record<number, AnomalyScore>>({})
  const [suggestion, setSuggestion] = useState<MLSuggestion | null>(null)
  const [isTraining, setIsTraining] = useState(false)
  const [reportMonth, setReportMonth] = useState(() => {
    const d = new Date()
    d.setMonth(d.getMonth() - 1)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
  })

  const MONTH_NAMES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
  const fmtMonth = (ym: string) => { const [y,m] = ym.split("-"); return `${MONTH_NAMES[+m-1]} ${y}` }

  const availableMonths = useMemo(() => {
    const s = new Set<string>()
    transactions.forEach(t => { if (t.date) s.add(t.date.slice(0, 7)) })
    return Array.from(s).sort().reverse()
  }, [transactions])

  const monthlyReport = useMemo(() => {
    const tx = transactions.filter(t => t.date?.startsWith(reportMonth))
    const income   = tx.filter(t => t.type === "ingreso").reduce((s, t) => s + t.amount, 0)
    const expenses = tx.filter(t => t.type === "gasto").reduce((s, t) => s + t.amount, 0)
    const byCat: Record<string, number> = {}
    tx.filter(t => t.type === "gasto").forEach(t => { byCat[t.category] = (byCat[t.category] ?? 0) + t.amount })
    const categories = Object.entries(byCat)
      .sort((a, b) => b[1] - a[1])
      .map(([cat, amount]) => ({ cat, amount, pct: expenses > 0 ? Math.round(amount / expenses * 100) : 0 }))
    return { income, expenses, balance: income - expenses, categories, count: tx.length }
  }, [transactions, reportMonth])

  const suggestTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [form, setForm] = useState({
    description: "", amount: "", category: "Alimentación",
    type: "gasto" as "gasto" | "ingreso", date: new Date().toISOString().slice(0, 10)
  })

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const [data, sum, trendData] = await Promise.all([
        transactionService.list(),
        transactionService.summary(),
        transactionService.trends().catch(() => []),
      ])
      setTransactions(data)
      setSummary(sum)
      setTrends(trendData as TrendResult[])
      // Load ML data in background
      transactionService.mlMetrics().then(m => setMlMetrics(m)).catch(() => {})
      transactionService.mlAnomalies().then(list => {
        const map: Record<number, AnomalyScore> = {}
        list.forEach(a => { map[a.transaction_id] = a })
        setAnomalies(map)
      }).catch(() => {})
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const tipo = searchParams.get("tipo")
    if (tipo === "ingreso" || tipo === "gasto") {
      setForm(prev => ({ ...prev, type: tipo, category: tipo === "ingreso" ? "Salario" : "Alimentación" }))
      setDialogOpen(true)
    }
  }, [searchParams])

  const filtered = transactions.filter(t => {
    const matchSearch = t.description.toLowerCase().includes(searchTerm.toLowerCase())
    const matchCat = selectedCategory === "Todos" || t.category === selectedCategory
    return matchSearch && matchCat
  })

  const handleDescriptionChange = (value: string) => {
    setForm(prev => ({ ...prev, description: value }))
    setSuggestion(null)
    if (suggestTimer.current) clearTimeout(suggestTimer.current)
    if (value.length >= 3 && form.type === "gasto") {
      suggestTimer.current = setTimeout(async () => {
        try {
          const s = await transactionService.mlSuggest(value)
          if (s.category) setSuggestion(s)
        } catch { /* no model yet */ }
      }, 600)
    }
  }

  const handleTrainModel = async () => {
    setIsTraining(true)
    try {
      const m = await transactionService.mlTrain()
      setMlMetrics(m)
      // Refresh anomalies with new model
      const list = await transactionService.mlAnomalies()
      const map: Record<number, AnomalyScore> = {}
      list.forEach(a => { map[a.transaction_id] = a })
      setAnomalies(map)
    } catch { /* insufficient data */ }
    finally { setIsTraining(false) }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (editingId) {
        await transactionService.update(editingId, {
          description: form.description, amount: parseFloat(form.amount),
          category: form.category, type: form.type, date: form.date,
        })
      } else {
        await transactionService.create({
          description: form.description, amount: parseFloat(form.amount),
          category: form.category, type: form.type, date: form.date,
        })
      }
      setDialogOpen(false)
      setEditingId(null)
      setForm({ description: "", amount: "", category: "Alimentación", type: "gasto", date: new Date().toISOString().slice(0, 10) })
      await load()
    } catch {
      // error silenciado — el interceptor de Axios maneja 401
    }
  }

  const handleEdit = (t: Transaction) => {
    setEditingId(t.id)
    setForm({ description: t.description, amount: String(t.amount), category: t.category, type: t.type as "gasto" | "ingreso", date: t.date })
    setDialogOpen(true)
  }

  const handleDelete = async (id: number) => {
    if (!confirm("¿Eliminar esta transacción?")) return
    await transactionService.remove(id)
    await load()
  }

  const openNew = () => {
    setEditingId(null)
    setForm({ description: "", amount: "", category: "Alimentación", type: "gasto", date: new Date().toISOString().slice(0, 10) })
    setDialogOpen(true)
  }

  return (
    <div className="max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Transacciones</h1>
          <p className="text-muted-foreground mt-1">Historial de todos tus movimientos</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) setEditingId(null) }}>
          <DialogTrigger asChild>
            <Button onClick={openNew}>
              <Plus className="w-4 h-4 mr-2" />
              Nuevo Registro
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editingId ? "Editar Transacción" : "Registrar Transacción"}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4 mt-4">
              <div>
                <label className="text-sm font-medium text-foreground">Tipo</label>
                <div className="flex gap-2 mt-2">
                  <Button type="button" variant={form.type === "gasto" ? "default" : "outline"}
                    onClick={() => setForm({ ...form, type: "gasto", category: "Alimentación" })} className="flex-1">
                    Gasto
                  </Button>
                  <Button type="button" variant={form.type === "ingreso" ? "default" : "outline"}
                    onClick={() => setForm({ ...form, type: "ingreso", category: "Salario" })} className="flex-1">
                    Ingreso
                  </Button>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Descripción</label>
                <Input placeholder="Ej: Supermercado" value={form.description}
                  onChange={(e) => handleDescriptionChange(e.target.value)} className="mt-2" required />
                {suggestion && suggestion.category && form.type === "gasto" && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Sparkles className="w-3 h-3" /> IA sugiere:
                    </span>
                    <button type="button"
                      onClick={() => { setForm(prev => ({ ...prev, category: suggestion.category! })); setSuggestion(null) }}
                      className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary font-medium hover:bg-primary/20 transition-colors">
                      {suggestion.category} ({Math.round(suggestion.confidence * 100)}%)
                    </button>
                    {suggestion.alternatives.slice(0, 1).map(a => (
                      <button key={a.category} type="button"
                        onClick={() => { setForm(prev => ({ ...prev, category: a.category })); setSuggestion(null) }}
                        className="text-xs px-2 py-1 rounded-full bg-secondary text-muted-foreground hover:text-foreground transition-colors">
                        {a.category}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Monto</label>
                <Input type="number" min="0.01" step="0.01" placeholder="0.00" value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })} className="mt-2" required />
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Categoría</label>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="mt-2 w-full h-10 px-3 rounded-md border border-input bg-background text-foreground">
                  {(form.type === "ingreso" ? incomeCategories : expenseCategories).map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Fecha</label>
                <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="mt-2" required />
              </div>
              <Button type="submit" className="w-full">
                {editingId ? "Guardar Cambios" : "Guardar"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="space-y-2">
                    <Skeleton className="h-3.5 w-24" />
                    <Skeleton className="h-8 w-36" />
                  </div>
                  <Skeleton className="w-10 h-10 rounded-full" />
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Total Ingresos</p>
                    <p className="text-2xl font-bold text-foreground">
                      {formatCOP(summary.total_income)}
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                    <ArrowDownRight className="w-5 h-5 text-foreground" />
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Total Gastos</p>
                    <p className="text-2xl font-bold text-foreground">
                      {formatCOP(summary.total_expenses)}
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                    <ArrowUpRight className="w-5 h-5 text-foreground" />
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Balance</p>
                    <p className="text-2xl font-bold text-foreground">
                      {formatCOP(summary.balance)}
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-foreground" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Cierre mensual */}
      {availableMonths.length > 0 && (
        <Card className="mb-6">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <CardTitle className="text-base flex items-center gap-2">
                <History className="w-4 h-4" />
                Cierre mensual
              </CardTitle>
              <select
                value={reportMonth}
                onChange={e => setReportMonth(e.target.value)}
                className="text-sm h-9 px-3 rounded-md border border-input bg-background text-foreground w-full sm:w-auto"
              >
                {availableMonths.map(m => (
                  <option key={m} value={m}>{fmtMonth(m)}</option>
                ))}
              </select>
            </div>
          </CardHeader>
          <CardContent>
            {monthlyReport.count === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">Sin transacciones en {fmtMonth(reportMonth)}</p>
            ) : (
              <div className="space-y-5">
                {/* Resumen del mes */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-xl bg-secondary/40 p-3 text-center">
                    <p className="text-xs text-muted-foreground mb-1">Ingresos</p>
                    <p className="text-lg font-bold text-foreground tabular-nums">
                      {formatCOP(monthlyReport.income)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-secondary/40 p-3 text-center">
                    <p className="text-xs text-muted-foreground mb-1">Gastos</p>
                    <p className="text-lg font-bold text-destructive tabular-nums">
                      {formatCOP(monthlyReport.expenses)}
                    </p>
                  </div>
                  <div className={`rounded-xl p-3 text-center ${monthlyReport.balance >= 0 ? "bg-green-500/10" : "bg-destructive/10"}`}>
                    <p className="text-xs text-muted-foreground mb-1">Balance neto</p>
                    <p className={`text-lg font-bold tabular-nums ${monthlyReport.balance >= 0 ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
                      {monthlyReport.balance >= 0 ? "+" : ""}{formatCOP(monthlyReport.balance)}
                    </p>
                  </div>
                </div>

                {/* Desglose por categoría */}
                {monthlyReport.categories.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                      Gastos por categoría
                    </p>
                    <div className="space-y-2.5">
                      {monthlyReport.categories.map(({ cat, amount, pct }) => {
                        const Icon = categoryIcons[cat] ?? MoreHorizontal
                        return (
                          <div key={cat}>
                            <div className="flex items-center gap-2 mb-1">
                              <Icon className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                              <span className="text-sm text-foreground flex-1 truncate">{cat}</span>
                              <span className="text-xs text-muted-foreground tabular-nums">{pct}%</span>
                              <span className="text-sm font-semibold text-foreground tabular-nums min-w-[90px] text-right">
                                {formatCOP(amount)}
                              </span>
                            </div>
                            <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                              <div className="h-full bg-foreground/60 rounded-full transition-all" style={{ width: `${pct}%` }} />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                <p className="text-xs text-muted-foreground flex items-center gap-1.5 pt-1 border-t border-border">
                  <ArrowRightLeft className="w-3 h-3" />
                  {monthlyReport.count} transacciones en {fmtMonth(reportMonth)}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* AI Trend Analysis */}
      {trends.length > 0 && (
        <Card className="mb-6">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Tendencias de gasto por categoría
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1">
              Compara el mes pasado frente al promedio de los 3 meses anteriores
            </p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {trends.map((t) => {
                const up = t.trend === "sube"
                const down = t.trend === "baja"
                const accentClass = up ? "text-destructive" : down ? "text-green-600 dark:text-green-400" : "text-muted-foreground"
                const borderClass = up ? "border-destructive/30 bg-destructive/5" : down ? "border-green-500/30 bg-green-500/5" : "border-border bg-secondary/30"
                return (
                  <div key={t.category} className={`rounded-xl p-4 border ${borderClass} space-y-3`}>
                    {/* Categoría + badge */}
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-foreground truncate">{t.category}</p>
                      <span className={`flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-full ${up ? "bg-destructive/10 text-destructive" : down ? "bg-green-500/10 text-green-600 dark:text-green-400" : "bg-secondary text-muted-foreground"}`}>
                        {up ? <TrendingUp className="w-3 h-3" /> : down ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                        {t.pct_change > 0 ? "+" : ""}{t.pct_change.toFixed(1)}%
                      </span>
                    </div>

                    {/* Valores con etiquetas claras */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Mes pasado</span>
                        <span className={`font-bold tabular-nums ${accentClass}`}>
                          {formatCOP(t.avg_last_3m)}
                        </span>
                      </div>
                      {t.avg_prev_3m > 0 && (
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">Prom. 3 meses ant.</span>
                          <span className="font-medium text-foreground tabular-nums">
                            {formatCOP(t.avg_prev_3m)}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Barra de progreso relativa */}
                    {t.avg_prev_3m > 0 && (
                      <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${up ? "bg-destructive" : down ? "bg-green-500" : "bg-foreground/40"}`}
                          style={{ width: `${Math.min((t.avg_last_3m / (t.avg_prev_3m * 1.5)) * 100, 100)}%` }}
                        />
                      </div>
                    )}

                    {/* Mensaje interpretativo */}
                    <p className={`text-xs ${accentClass}`}>
                      {up ? `Gastas ${t.pct_change.toFixed(0)}% más que antes`
                           : down ? `Gastas ${Math.abs(t.pct_change).toFixed(0)}% menos que antes`
                           : "Gasto estable"}
                    </p>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ML Model Panel */}
      <Card className="mb-6">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Brain className="w-4 h-4" />
              Modelos de Inteligencia Artificial
            </CardTitle>
            <Button variant="outline" size="sm" onClick={handleTrainModel} disabled={isTraining}>
              {isTraining ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
              {isTraining ? "Entrenando…" : "Re-entrenar"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Random Forest metrics */}
            <div className="rounded-xl border border-border p-4">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">IA — Categorización automática</p>
              {mlMetrics && mlMetrics.accuracy != null ? (
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Exactitud (CV)</span>
                    <span className="font-bold text-foreground">{Math.round(mlMetrics.accuracy * 100)}%</span>
                  </div>
                  {mlMetrics.f1_weighted != null && (
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">F1 ponderado</span>
                      <span className="font-bold text-foreground">{Math.round(mlMetrics.f1_weighted * 100)}%</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Muestras de entrenamiento</span>
                    <span className="font-medium text-foreground">{mlMetrics.n_samples}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Categorías aprendidas</span>
                    <span className="font-medium text-foreground">{mlMetrics.n_categories}</span>
                  </div>
                  {mlMetrics.top_features?.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-border">
                      <p className="text-xs text-muted-foreground mb-2">Palabras más influyentes:</p>
                      <div className="flex flex-wrap gap-1">
                        {mlMetrics.top_features.slice(0, 6).map(f => (
                          <span key={f.word} className="text-xs px-2 py-0.5 rounded-full bg-secondary text-foreground">
                            {f.word}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-4">
                  <p className="text-sm text-muted-foreground">Sin modelo entrenado</p>
                  <p className="text-xs text-muted-foreground mt-1">Mínimo 10 transacciones en 2+ categorías</p>
                </div>
              )}
            </div>
            {/* Isolation Forest metrics */}
            <div className="rounded-xl border border-border p-4">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Isolation Forest — Anomalías</p>
              {Object.keys(anomalies).length > 0 ? (
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Transacciones analizadas</span>
                    <span className="font-bold text-foreground">{Object.keys(anomalies).length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Gastos inusuales detectados</span>
                    <span className="font-bold text-destructive">
                      {Object.values(anomalies).filter(a => a.is_anomaly).length}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Tasa de anomalías</span>
                    <span className="font-medium text-foreground">
                      {Object.keys(anomalies).length > 0
                        ? Math.round(Object.values(anomalies).filter(a => a.is_anomaly).length / Object.keys(anomalies).length * 100)
                        : 0}%
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-3 pt-3 border-t border-border">
                    Detecta gastos atípicos según magnitud, desviación por categoría y patrones temporales.
                  </p>
                </div>
              ) : (
                <div className="text-center py-4">
                  <p className="text-sm text-muted-foreground">Sin modelo entrenado</p>
                  <p className="text-xs text-muted-foreground mt-1">Mínimo 10 transacciones de gasto</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input placeholder="Buscar transacciones..." value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)} className="pl-10" />
            </div>
            <div className="flex gap-2 flex-wrap">
              {allCategories.map(cat => (
                <Button key={cat} variant={selectedCategory === cat ? "default" : "outline"}
                  size="sm" onClick={() => setSelectedCategory(cat)}>
                  {cat}
                </Button>
              ))}
            </div>
            <Button variant="outline" size="icon">
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Historial</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 7 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-xl">
                  <div className="flex items-center gap-3">
                    <Skeleton className="w-10 h-10 rounded-full flex-shrink-0" />
                    <div className="space-y-1.5">
                      <Skeleton className="h-3.5 w-40" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Skeleton className="h-5 w-20" />
                    <Skeleton className="h-7 w-7 rounded-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-center text-muted-foreground py-12">No hay transacciones registradas.</p>
          ) : (
            <div className="space-y-3">
              {filtered.map((t) => {
                const Icon = categoryIcons[t.category] ?? ShoppingCart
                return (
                  <div key={t.id}
                    className="flex items-center justify-between p-4 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-full bg-background flex items-center justify-center">
                        <Icon className="w-5 h-5 text-foreground" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-foreground">{t.description}</p>
                          {anomalies[t.id]?.is_anomaly && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-destructive/15 text-destructive font-medium flex items-center gap-1" title={`Score: ${anomalies[t.id].anomaly_score}`}>
                              <AlertTriangle className="w-3 h-3" />
                              Inusual
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">{t.category} • {t.date}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`font-semibold ${t.type === "ingreso" ? "text-foreground" : "text-muted-foreground"}`}>
                        {t.type === "ingreso" ? "+" : "-"}{formatCOP(t.amount)}
                      </span>
                      <Button variant="ghost" size="icon" onClick={() => handleEdit(t)}>
                        <Edit2 className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="text-destructive" onClick={() => handleDelete(t.id)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

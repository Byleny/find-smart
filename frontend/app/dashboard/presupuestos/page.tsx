"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Plus, ShoppingCart, Home, Car, Utensils, Zap, Film, Heart, MoreHorizontal,
  Edit2, Trash2, AlertCircle, Loader2, Receipt,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { budgetService } from "@/lib/services/budgets"
import { transactionService } from "@/lib/services/transactions"
import type { Budget } from "@/lib/types"
import { formatCOP as cop } from "@/lib/format"

const categoryIcons: Record<string, React.ElementType> = {
  "Compras": ShoppingCart, "Vivienda": Home, "Transporte": Car,
  "Alimentación": Utensils, "Servicios": Zap, "Entretenimiento": Film,
  "Salud": Heart, "Otros": MoreHorizontal,
}

const categories = ["Alimentación", "Transporte", "Vivienda", "Entretenimiento", "Servicios", "Salud", "Compras", "Otros"]

export default function PresupuestosPage() {
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [isLoading, setIsLoading] = useState(true)

  // Dialog crear/editar presupuesto
  const [budgetDialogOpen, setBudgetDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [budgetForm, setBudgetForm] = useState({ category: "Alimentación", limit_amount: "" })

  // Dialog registrar gasto rápido
  const [spendDialog, setSpendDialog] = useState<{ budget: Budget } | null>(null)
  const [spendForm, setSpendForm] = useState({ description: "", amount: "", date: new Date().toISOString().slice(0, 10) })
  const [isSaving, setIsSaving] = useState(false)

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      setBudgets(await budgetService.list())
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // ── Crear / Editar presupuesto ─────────────────────────────────────────────

  const handleBudgetSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const amount = parseInt(budgetForm.limit_amount.replace(/\./g, ""), 10)
    if (!amount || amount <= 0) return
    try {
      if (editingId) {
        await budgetService.update(editingId, { category: budgetForm.category, limit_amount: amount })
      } else {
        await budgetService.create({ category: budgetForm.category, limit_amount: amount })
      }
      setBudgetDialogOpen(false)
      setEditingId(null)
      setBudgetForm({ category: "Alimentación", limit_amount: "" })
      await load()
    } catch { /* interceptor maneja errores */ }
  }

  const handleEdit = (b: Budget) => {
    setEditingId(b.id)
    setBudgetForm({ category: b.category, limit_amount: String(b.limit_amount) })
    setBudgetDialogOpen(true)
  }

  const handleDelete = async (id: number) => {
    if (!confirm("¿Eliminar este presupuesto?")) return
    await budgetService.remove(id)
    await load()
  }

  const openNew = () => {
    setEditingId(null)
    setBudgetForm({ category: "Alimentación", limit_amount: "" })
    setBudgetDialogOpen(true)
  }

  // ── Registrar gasto rápido ─────────────────────────────────────────────────

  const openSpendDialog = (b: Budget) => {
    setSpendForm({ description: "", amount: "", date: new Date().toISOString().slice(0, 10) })
    setSpendDialog({ budget: b })
  }

  const handleSpendSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!spendDialog) return
    const amount = parseInt(spendForm.amount.replace(/\./g, ""), 10)
    if (!amount || amount <= 0) return
    setIsSaving(true)
    try {
      await transactionService.create({
        description: spendForm.description || spendDialog.budget.category,
        amount,
        category: spendDialog.budget.category,
        type: "gasto",
        date: spendForm.date,
      })
      setSpendDialog(null)
      await load()
    } catch { /* interceptor maneja errores */ } finally {
      setIsSaving(false)
    }
  }

  // ── Totales ────────────────────────────────────────────────────────────────

  const totalLimit = budgets.reduce((s, b) => s + b.limit_amount, 0)
  const totalSpent = budgets.reduce((s, b) => s + b.spent_amount, 0)
  const totalPercentage = totalLimit > 0 ? Math.round((totalSpent / totalLimit) * 100) : 0

  return (
    <div className="max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Presupuestos</h1>
          <p className="text-muted-foreground mt-1">Controla tus límites de gasto por categoría</p>
        </div>
        <Button onClick={openNew}>
          <Plus className="w-4 h-4 mr-2" />
          Nuevo Presupuesto
        </Button>
      </div>

      {/* Resumen global */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div>
              <p className="text-sm text-muted-foreground">Gasto total del mes</p>
              <p className="text-3xl font-bold text-foreground mt-1">{cop(totalSpent)}</p>
              <p className="text-sm text-muted-foreground mt-1">de {cop(totalLimit)} presupuestado</p>
            </div>
            <div className="flex-1 max-w-md">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-muted-foreground">Progreso general</span>
                <span className="text-sm font-medium text-foreground">{totalPercentage}%</span>
              </div>
              <div className="h-3 bg-secondary rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${totalPercentage >= 90 ? "bg-destructive" : "bg-foreground"}`}
                  style={{ width: `${Math.min(totalPercentage, 100)}%` }} />
              </div>
              {totalPercentage >= 90 && (
                <div className="flex items-center gap-2 mt-2 text-destructive">
                  <AlertCircle className="w-4 h-4" />
                  <span className="text-sm">Te acercas al límite total</span>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Grid de cards */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {budgets.map((budget) => {
            const Icon = categoryIcons[budget.category] ?? ShoppingCart
            const percentage = budget.limit_amount > 0
              ? Math.round((budget.spent_amount / budget.limit_amount) * 100) : 0
            const isOver = percentage >= 90
            const remaining = budget.limit_amount - budget.spent_amount

            return (
              <Card key={budget.id} className="group">
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                        <Icon className="w-5 h-5 text-foreground" />
                      </div>
                      <div>
                        <h3 className="font-medium text-foreground">{budget.category}</h3>
                        <p className="text-xs text-muted-foreground">Límite mensual</p>
                      </div>
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleEdit(budget)}>
                        <Edit2 className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => handleDelete(budget.id)}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-end justify-between">
                      <div>
                        <p className="text-2xl font-bold text-foreground">{cop(budget.spent_amount)}</p>
                        <p className="text-sm text-muted-foreground">de {cop(budget.limit_amount)}</p>
                      </div>
                      <span className={`text-sm font-medium ${isOver ? "text-destructive" : "text-muted-foreground"}`}>
                        {percentage}%
                      </span>
                    </div>

                    <div className="h-2 bg-secondary rounded-full overflow-hidden">
                      <div className={`h-full rounded-full transition-all ${isOver ? "bg-destructive" : "bg-foreground"}`}
                        style={{ width: `${Math.min(percentage, 100)}%` }} />
                    </div>

                    <div className="flex items-center justify-between">
                      <p className={`text-sm ${remaining < 0 ? "text-destructive" : "text-muted-foreground"}`}>
                        {remaining >= 0
                          ? `${cop(remaining)} disponible`
                          : `${cop(Math.abs(remaining))} excedido`}
                      </p>
                      <Button size="sm" variant="outline" className="h-7 text-xs"
                        onClick={() => openSpendDialog(budget)}>
                        <Receipt className="w-3 h-3 mr-1" />
                        Registrar gasto
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}

          {/* Card vacía para añadir */}
          <Card className="border-dashed">
            <CardContent className="pt-6 flex flex-col items-center justify-center h-full min-h-[200px]">
              <Button variant="ghost" className="flex flex-col gap-2 h-auto py-6" onClick={openNew}>
                <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
                  <Plus className="w-6 h-6 text-muted-foreground" />
                </div>
                <span className="text-muted-foreground">Añadir Presupuesto</span>
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Dialog crear/editar presupuesto */}
      <Dialog open={budgetDialogOpen} onOpenChange={(o) => { setBudgetDialogOpen(o); if (!o) setEditingId(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingId ? "Editar Presupuesto" : "Crear Presupuesto"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleBudgetSubmit} className="space-y-4 mt-4">
            <div>
              <label className="text-sm font-medium text-foreground">Categoría</label>
              <select value={budgetForm.category}
                onChange={(e) => setBudgetForm({ ...budgetForm, category: e.target.value })}
                className="mt-2 w-full h-10 px-3 rounded-md border border-input bg-background text-foreground">
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Límite mensual (COP)</label>
              <div className="relative mt-2">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
                <Input
                  type="number"
                  min="1000"
                  step="1000"
                  placeholder="500000"
                  value={budgetForm.limit_amount}
                  onChange={(e) => setBudgetForm({ ...budgetForm, limit_amount: e.target.value })}
                  className="pl-7"
                  required
                />
              </div>
              {budgetForm.limit_amount && !isNaN(Number(budgetForm.limit_amount)) && (
                <p className="text-xs text-muted-foreground mt-1">
                  {cop(Number(budgetForm.limit_amount))} pesos colombianos
                </p>
              )}
            </div>
            <Button type="submit" className="w-full">
              {editingId ? "Guardar Cambios" : "Crear Presupuesto"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Dialog registrar gasto rápido */}
      <Dialog open={!!spendDialog} onOpenChange={(o) => { if (!o) setSpendDialog(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar gasto — {spendDialog?.budget.category}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSpendSubmit} className="space-y-4 mt-4">
            <div>
              <label className="text-sm font-medium text-foreground">Descripción</label>
              <Input
                placeholder={`Gasto en ${spendDialog?.budget.category}`}
                value={spendForm.description}
                onChange={(e) => setSpendForm({ ...spendForm, description: e.target.value })}
                className="mt-2"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Monto (COP)</label>
              <div className="relative mt-2">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
                <Input
                  type="number"
                  min="100"
                  step="100"
                  placeholder="50000"
                  value={spendForm.amount}
                  onChange={(e) => setSpendForm({ ...spendForm, amount: e.target.value })}
                  className="pl-7"
                  required
                />
              </div>
              {spendForm.amount && !isNaN(Number(spendForm.amount)) && (
                <p className="text-xs text-muted-foreground mt-1">
                  {cop(Number(spendForm.amount))} pesos colombianos
                </p>
              )}
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Fecha</label>
              <Input
                type="date"
                value={spendForm.date}
                onChange={(e) => setSpendForm({ ...spendForm, date: e.target.value })}
                className="mt-2"
                required
              />
            </div>

            {spendDialog && (
              <div className="rounded-lg bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
                Disponible en este presupuesto:{" "}
                <span className={`font-semibold ${spendDialog.budget.limit_amount - spendDialog.budget.spent_amount < 0 ? "text-destructive" : "text-foreground"}`}>
                  {cop(Math.max(0, spendDialog.budget.limit_amount - spendDialog.budget.spent_amount))}
                </span>
              </div>
            )}

            <div className="flex gap-3">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setSpendDialog(null)}>
                Cancelar
              </Button>
              <Button type="submit" className="flex-1" disabled={isSaving}>
                {isSaving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                {isSaving ? "Guardando…" : "Registrar"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

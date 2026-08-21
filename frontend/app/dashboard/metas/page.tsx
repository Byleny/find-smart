"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Plus, Plane, Home, Car, GraduationCap, Laptop, Heart, PiggyBank,
  Edit2, Trash2, TrendingUp, Calendar, DollarSign, Loader2, Trophy, CheckCircle2
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { goalService } from "@/lib/services/goals"
import type { SavingGoal } from "@/lib/types"
import { formatCOP } from "@/lib/format"

function getGoalIcon(name: string): React.ElementType {
  const n = name.toLowerCase()
  if (n.includes("viaj") || n.includes("vacac") || n.includes("san andr") || n.includes("cartagena")) return Plane
  if (n.includes("casa") || n.includes("apart") || n.includes("hogar") || n.includes("arriendo")) return Home
  if (n.includes("carro") || n.includes("moto") || n.includes("auto") || n.includes("coche") || n.includes("vehic")) return Car
  if (n.includes("estudio") || n.includes("univer") || n.includes("curso") || n.includes("educ") || n.includes("carrera")) return GraduationCap
  if (n.includes("laptop") || n.includes("comput") || n.includes("tecno") || n.includes("celular") || n.includes("equipo")) return Laptop
  if (n.includes("salud") || n.includes("medic") || n.includes("hospital") || n.includes("emergencia")) return Heart
  return PiggyBank
}

export default function MetasPage() {
  const [goals, setGoals] = useState<SavingGoal[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [contributionDialog, setContributionDialog] = useState<number | null>(null)
  const [contributionAmount, setContributionAmount] = useState("")
  const [contributionNote, setContributionNote] = useState("")
  const [contributionDate, setContributionDate] = useState(new Date().toISOString().slice(0, 10))
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
  const [form, setForm] = useState({ name: "", description: "", target_amount: "", deadline: "" })

  const load = useCallback(async () => {
    setIsLoading(true)
    try { setGoals(await goalService.list()) }
    finally { setIsLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const payload = {
        name: form.name,
        description: form.description || undefined,
        target_amount: parseFloat(form.target_amount),
        deadline: form.deadline,
      }
      if (editingId) {
        await goalService.update(editingId, payload)
      } else {
        await goalService.create(payload)
      }
      setDialogOpen(false)
      setEditingId(null)
      setForm({ name: "", description: "", target_amount: "", deadline: "" })
      await load()
    } catch { /* handled */ }
  }

  const handleContribution = async (e: React.FormEvent, goalId: number) => {
    e.preventDefault()
    try {
      await goalService.contribute(goalId, { amount: parseFloat(contributionAmount), note: contributionNote || undefined, date: contributionDate })
      setContributionDialog(null)
      setContributionAmount("")
      setContributionNote("")
      setContributionDate(new Date().toISOString().slice(0, 10))
      await load()
    } catch { /* handled */ }
  }

  const handleEdit = (g: SavingGoal) => {
    setEditingId(g.id)
    setForm({ name: g.name, description: g.description ?? "", target_amount: String(g.target_amount), deadline: g.deadline })
    setDialogOpen(true)
  }

  const handleDelete = async () => {
    if (deleteConfirmId === null) return
    await goalService.remove(deleteConfirmId)
    setDeleteConfirmId(null)
    await load()
  }

  const openNew = () => {
    setEditingId(null)
    setForm({ name: "", description: "", target_amount: "", deadline: "" })
    setDialogOpen(true)
  }

  const calculateMonthsLeft = (deadline: string) => {
    const now = new Date()
    const end = new Date(deadline)
    const months = (end.getFullYear() - now.getFullYear()) * 12 + (end.getMonth() - now.getMonth())
    return Math.max(0, months)
  }

  const totalSaved = goals.reduce((s, g) => s + g.current_amount, 0)
  const totalTarget = goals.reduce((s, g) => s + g.target_amount, 0)

  return (
    <div className="max-w-7xl mx-auto">
      {/* Delete Confirm Dialog */}
      <Dialog open={deleteConfirmId !== null} onOpenChange={(o) => { if (!o) setDeleteConfirmId(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Eliminar esta meta?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">Esta acción no se puede deshacer. Se perderán todos los aportes registrados.</p>
          <div className="flex gap-2 justify-end mt-4">
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>Cancelar</Button>
            <Button variant="destructive" onClick={handleDelete}>Eliminar</Button>
          </div>
        </DialogContent>
      </Dialog>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Metas de Ahorro</h1>
          <p className="text-muted-foreground mt-1">Define y alcanza tus objetivos financieros</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) setEditingId(null) }}>
          <DialogTrigger asChild>
            <Button onClick={openNew}>
              <Plus className="w-4 h-4 mr-2" />
              Nueva Meta
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editingId ? "Editar Meta" : "Crear Meta de Ahorro"}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4 mt-4">
              <div>
                <label className="text-sm font-medium text-foreground">Nombre de la meta</label>
                <Input placeholder="Ej: Viaje a San Andrés" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-2" required />
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Descripción (opcional)</label>
                <Input placeholder="Ej: Ahorro para vacaciones de diciembre" value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })} className="mt-2" />
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Monto objetivo</label>
                <Input type="number" min="1000" step="1000" placeholder="500000" value={form.target_amount}
                  onChange={(e) => setForm({ ...form, target_amount: e.target.value })} className="mt-2" required />
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Fecha límite</label>
                <Input type="date" value={form.deadline}
                  onChange={(e) => setForm({ ...form, deadline: e.target.value })} className="mt-2" required />
              </div>
              <Button type="submit" className="w-full">
                {editingId ? "Guardar Cambios" : "Crear Meta"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
                <PiggyBank className="w-6 h-6 text-foreground" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Ahorrado</p>
                <p className="text-2xl font-bold text-foreground">{formatCOP(totalSaved)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-foreground" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Progreso Global</p>
                <p className="text-2xl font-bold text-foreground">
                  {totalTarget > 0 ? Math.round((totalSaved / totalTarget) * 100) : 0}%
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
                <Calendar className="w-6 h-6 text-foreground" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Metas Activas</p>
                <p className="text-2xl font-bold text-foreground">{goals.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {goals.map((goal) => {
            const Icon = getGoalIcon(goal.name)
            const percentage = goal.target_amount > 0
              ? Math.round((goal.current_amount / goal.target_amount) * 100) : 0
            const completed = percentage >= 100
            const remaining = goal.target_amount - goal.current_amount
            const monthsLeft = calculateMonthsLeft(goal.deadline)

            return (
              <Card key={goal.id} className={`group ${completed ? "border-green-500/40 bg-green-500/5 dark:bg-green-500/5" : ""}`}>
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between mb-6">
                    <div className="flex items-center gap-4">
                      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${completed ? "bg-green-500/20" : "bg-secondary"}`}>
                        {completed
                          ? <Trophy className="w-7 h-7 text-green-600 dark:text-green-400" />
                          : <Icon className="w-7 h-7 text-foreground" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-semibold text-lg text-foreground">{goal.name}</h3>
                          {completed && (
                            <span className="text-xs font-medium bg-green-500/20 text-green-700 dark:text-green-400 px-2 py-0.5 rounded-full">
                              ¡Lograda!
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {completed
                            ? "Meta alcanzada"
                            : monthsLeft > 0
                            ? `${monthsLeft} ${monthsLeft === 1 ? "mes restante" : "meses restantes"}`
                            : "Fecha límite alcanzada"}
                        </p>
                      </div>
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleEdit(goal)}>
                        <Edit2 className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteConfirmId(goal.id)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <div className="flex items-end justify-between mb-2">
                        <div>
                          <p className="text-3xl font-bold text-foreground">{formatCOP(goal.current_amount)}</p>
                          <p className="text-sm text-muted-foreground">de {formatCOP(goal.target_amount)}</p>
                        </div>
                        <span className={`text-2xl font-bold ${completed ? "text-green-600 dark:text-green-400" : "text-foreground"}`}>
                          {Math.min(percentage, 100)}%
                        </span>
                      </div>
                      <div className="h-3 bg-secondary rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${completed ? "bg-green-500" : "bg-foreground"}`}
                          style={{ width: `${Math.min(percentage, 100)}%` }}
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-4 border-t border-border">
                      {completed ? (
                        <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                          <CheckCircle2 className="w-4 h-4" />
                          <span className="text-sm font-semibold">¡Objetivo cumplido!</span>
                        </div>
                      ) : (
                        <div>
                          <p className="text-sm text-muted-foreground">Faltan</p>
                          <p className="font-semibold text-foreground">{formatCOP(remaining)}</p>
                        </div>
                      )}
                    </div>

                    {!completed && (
                      <Dialog open={contributionDialog === goal.id}
                        onOpenChange={(open) => setContributionDialog(open ? goal.id : null)}>
                        <DialogTrigger asChild>
                          <Button className="w-full">
                            <DollarSign className="w-4 h-4 mr-2" />
                            Agregar Aporte
                          </Button>
                        </DialogTrigger>
                        <DialogContent>
                          <DialogHeader>
                            <DialogTitle>Agregar aporte a {goal.name}</DialogTitle>
                          </DialogHeader>
                          <form onSubmit={(e) => handleContribution(e, goal.id)} className="space-y-4 mt-4">
                            <div>
                              <label className="text-sm font-medium text-foreground">Monto del aporte</label>
                              <Input type="number" min="100" step="100" placeholder="50000"
                                value={contributionAmount}
                                onChange={(e) => setContributionAmount(e.target.value)} className="mt-2" required />
                            </div>
                            <div>
                              <label className="text-sm font-medium text-foreground">Nota (opcional)</label>
                              <Input placeholder="Ej: Ahorro del mes" value={contributionNote}
                                onChange={(e) => setContributionNote(e.target.value)} className="mt-2" />
                            </div>
                            <div>
                              <label className="text-sm font-medium text-foreground">Fecha</label>
                              <Input type="date" value={contributionDate}
                                onChange={(e) => setContributionDate(e.target.value)} className="mt-2" required />
                            </div>
                            <div className="text-sm text-muted-foreground">
                              Saldo actual: {formatCOP(goal.current_amount)} / {formatCOP(goal.target_amount)}
                            </div>
                            <Button type="submit" className="w-full">Confirmar Aporte</Button>
                          </form>
                        </DialogContent>
                      </Dialog>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}

          <Card className="border-dashed min-h-[300px]">
            <CardContent className="pt-6 flex flex-col items-center justify-center h-full">
              <Button variant="ghost" className="flex flex-col gap-3 h-auto py-8" onClick={openNew}>
                <div className="w-16 h-16 rounded-full bg-secondary flex items-center justify-center">
                  <Plus className="w-8 h-8 text-muted-foreground" />
                </div>
                <div className="text-center">
                  <p className="font-medium text-foreground">Crear Nueva Meta</p>
                  <p className="text-sm text-muted-foreground">Define tu próximo objetivo</p>
                </div>
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

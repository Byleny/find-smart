"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
import {
  Plus, Users, UserPlus, Wallet, CheckCircle2, Circle,
  Home, Lightbulb, Droplets, Wifi, ShoppingCart, Car, Phone, Loader2, Link2, LogOut,
  AlertTriangle, ChevronDown, ChevronUp, Receipt, PiggyBank, Pencil, Trash2
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { CurrencyInput } from "@/components/finsmart/currency-input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { toast } from "sonner"
import { sharedService } from "@/lib/services/shared"
import { useAuth } from "@/contexts/auth-context"
import type { SharedGroup, GroupDetail, MemberBalance, FundStatus } from "@/lib/types"
import { formatCOP } from "@/lib/format"
import { getErrorMessage } from "@/lib/utils"

const expenseIcons: Record<string, React.ElementType> = {
  "Servicios públicos": Lightbulb, "Agua": Droplets, "Internet": Wifi,
  "Mercado": ShoppingCart, "Arriendo": Home, "Transporte": Car, "Teléfono": Phone, "Otro": Wallet,
}

export default function CompartidosPage() {
  const { user: currentUser } = useAuth()
  const [groups, setGroups] = useState<SharedGroup[]>([])
  const [activeGroupId, setActiveGroupId] = useState<number | null>(null)
  const [groupDetail, setGroupDetail] = useState<GroupDetail | null>(null)
  const [balances, setBalances] = useState<MemberBalance[]>([])
  const [isLoading, setIsLoading] = useState(true)   // detalle del grupo activo
  const [loadingGroups, setLoadingGroups] = useState(true)  // lista de grupos
  const [groupsError, setGroupsError] = useState("")
  const [activeTab, setActiveTab] = useState<"gastos" | "balances">("gastos")

  const [newGroupDialog, setNewGroupDialog] = useState(false)
  const [newMemberDialog, setNewMemberDialog] = useState(false)
  const [newExpenseDialog, setNewExpenseDialog] = useState(false)
  const [leaveDialog, setLeaveDialog] = useState(false)
  const [editMemberDialog, setEditMemberDialog] = useState<{ id: number; name: string } | null>(null)
  const [editMemberName, setEditMemberName] = useState("")
  const [editMemberError, setEditMemberError] = useState("")
  const [isSavingMember, setIsSavingMember] = useState(false)
  const [removeMemberDialog, setRemoveMemberDialog] = useState<{ id: number; name: string } | null>(null)
  const [removeMemberError, setRemoveMemberError] = useState("")
  const [isRemovingMember, setIsRemovingMember] = useState(false)

  const [groupForm, setGroupForm] = useState({ name: "", description: "", group_type: "gastos" as "gastos" | "fondo" })
  const [fundStatus, setFundStatus] = useState<FundStatus | null>(null)
  const [fundDialog, setFundDialog] = useState(false)
  const [fundForm, setFundForm] = useState({ member_id: "", amount: "", note: "", date: new Date().toISOString().slice(0, 10) })
  const [isContributing, setIsContributing] = useState(false)
  const [memberForm, setMemberForm] = useState({ name: "", email: "" })
  const [expenseForm, setExpenseForm] = useState({
    description: "", amount: "", paid_by_id: "", category: "Otro", date: new Date().toISOString().slice(0, 10)
  })
  const [splitMode, setSplitMode] = useState<"equal" | "custom">("equal")
  const [memberPcts, setMemberPcts] = useState<Record<number, number>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLeaving, setIsLeaving] = useState(false)
  const [createGroupError, setCreateGroupError] = useState("")
  const [memberError, setMemberError] = useState("")
  const [expenseError, setExpenseError] = useState("")
  const [fundError, setFundError] = useState("")
  const [leaveError, setLeaveError] = useState("")
  const [settleError, setSettleError] = useState("")
  const [selectedExpenseMonth, setSelectedExpenseMonth] = useState("all")
  const [selectedFundMonth, setSelectedFundMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const [settlingKey, setSettlingKey] = useState<string | null>(null)
  const [responsibilityDialog, setResponsibilityDialog] = useState<{
    debtorId: number; creditorId: number; debtorName: string; creditorName: string; amount: number
  } | null>(null)
  const [expandedDebt, setExpandedDebt] = useState<string | null>(null)
  const [paymentDialog, setPaymentDialog] = useState<{
    debtKey: string; creditorId: number; creditorName: string
    options: { splitId: number; description: string; date: string; amount: number }[]
  } | null>(null)
  const [selectedSplitIds, setSelectedSplitIds] = useState<Set<number>>(new Set())
  const [isSettlingPartial, setIsSettlingPartial] = useState(false)

  const loadGroups = useCallback(async () => {
    setGroupsError("")
    try {
      const data = await sharedService.listGroups()
      setGroups(data)
      if (data.length > 0) {
        if (!activeGroupId) setActiveGroupId(data[0].id)
      } else {
        setActiveGroupId(null)
        setGroupDetail(null)
      }
    } catch {
      // Sin esto, un fallo de red dejaba la pantalla girando sin explicación.
      setGroupsError("No se pudieron cargar tus grupos.")
    } finally {
      // Se apaga pase lo que pase: si no hay grupos nadie carga un detalle,
      // y antes eso dejaba la pantalla girando sin mostrar el estado vacío.
      setLoadingGroups(false)
    }
  }, [activeGroupId])

  const loadDetail = useCallback(async (id: number) => {
    setIsLoading(true)
    try {
      const detail = await sharedService.getGroup(id)
      setGroupDetail(detail)
      if (detail.group_type === "fondo") {
        const fs = await sharedService.getFundStatus(id)
        setFundStatus(fs)
      } else {
        const bal = await sharedService.getBalances(id)
        setBalances(bal)
        setFundStatus(null)
      }
      // Always reset member selections and month filters when loading a group.
      // Por defecto, quien registra el gasto es quien lo pagó — el creador del
      // grupo solo debe quedar seleccionado si es él quien está usando la app.
      if (detail.members.length > 0) {
        const self = detail.members.find(m => m.is_active && m.user_id === currentUser?.id)
        const defaultId = String((self ?? detail.members[0]).id)
        setExpenseForm(prev => ({ ...prev, paid_by_id: defaultId }))
        setFundForm(prev => ({ ...prev, member_id: defaultId }))
      }
      setSelectedExpenseMonth("all")
      setSelectedFundMonth(new Date().toISOString().slice(0, 7))
    } finally {
      setIsLoading(false)
    }
  }, [currentUser?.id])

  useEffect(() => { loadGroups() }, [loadGroups])
  useEffect(() => { if (activeGroupId) loadDetail(activeGroupId) }, [activeGroupId, loadDetail])

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setCreateGroupError("")
    try {
      const g = await sharedService.createGroup({ name: groupForm.name, description: groupForm.description || undefined, group_type: groupForm.group_type })
      setNewGroupDialog(false)
      setGroupForm({ name: "", description: "", group_type: "gastos" })
      await loadGroups()
      setActiveGroupId(g.id)
    } catch (err: unknown) {
      setCreateGroupError(getErrorMessage(err, "No se pudo crear el grupo. Intenta de nuevo."))
    } finally { setIsSubmitting(false) }
  }

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeGroupId) return
    setIsSubmitting(true)
    setMemberError("")
    try {
      const result = await sharedService.addMember(activeGroupId, { name: memberForm.name, email: memberForm.email })
      setNewMemberDialog(false)
      setMemberForm({ name: "", email: "" })
      if (result.status === "invited") toast.info(result.detail)
      else toast.success(result.detail)
      await loadDetail(activeGroupId)
    } catch (err: unknown) {
      setMemberError(getErrorMessage(err, "No se pudo agregar el miembro. Intenta de nuevo."))
    } finally { setIsSubmitting(false) }
  }

  const handleEditMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeGroupId || !editMemberDialog) return
    setIsSavingMember(true)
    setEditMemberError("")
    try {
      await sharedService.updateMember(activeGroupId, editMemberDialog.id, { name: editMemberName })
      setEditMemberDialog(null)
      await loadDetail(activeGroupId)
    } catch (err: unknown) {
      setEditMemberError(getErrorMessage(err, "No se pudo actualizar el miembro. Intenta de nuevo."))
    } finally { setIsSavingMember(false) }
  }

  const handleRemoveMember = async () => {
    if (!activeGroupId || !removeMemberDialog) return
    setIsRemovingMember(true)
    setRemoveMemberError("")
    try {
      await sharedService.removeMember(activeGroupId, removeMemberDialog.id)
      setRemoveMemberDialog(null)
      await loadDetail(activeGroupId)
    } catch (err: unknown) {
      setRemoveMemberError(getErrorMessage(err, "No se pudo eliminar el miembro. Intenta de nuevo."))
    } finally { setIsRemovingMember(false) }
  }

  const handleAddExpense = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeGroupId || !groupDetail) return
    const total = parseFloat(expenseForm.amount)
    let splits: { member_id: number; amount: number }[] | undefined
    if (!isFondo && splitMode === "custom") {
      const pctSum = Object.values(memberPcts).reduce((a, b) => a + b, 0)
      if (Math.abs(pctSum - 100) > 0.5) return
      splits = groupDetail.members.filter(m => m.is_active).map(m => ({
        member_id: m.id,
        amount: Math.round(((memberPcts[m.id] ?? 0) / 100) * total * 100) / 100,
      }))
    }
    // For fondo groups auto-assign paid_by to first active member
    const paidById = isFondo
      ? (groupDetail.members.find(m => m.is_active)?.id ?? 0)
      : parseInt(expenseForm.paid_by_id)
    setIsSubmitting(true)
    setExpenseError("")
    try {
      await sharedService.addExpense(activeGroupId, {
        description: expenseForm.description,
        amount: total,
        paid_by_id: paidById,
        category: expenseForm.category,
        date: expenseForm.date,
        splits,
      })
      setNewExpenseDialog(false)
      setExpenseForm(prev => ({ ...prev, description: "", amount: "" }))
      setSplitMode("equal")
      setMemberPcts({})
      await loadDetail(activeGroupId)
    } catch (err: unknown) {
      setExpenseError(getErrorMessage(err, "No se pudo registrar el gasto. Intenta de nuevo."))
    } finally { setIsSubmitting(false) }
  }

  const handleSettle = async (debtorMemberId: number, creditorMemberId: number): Promise<boolean> => {
    if (!activeGroupId) return false
    const key = `${debtorMemberId}-${creditorMemberId}`
    setSettlingKey(key)
    setSettleError("")
    try {
      const result = await sharedService.settleBetween(activeGroupId, debtorMemberId, creditorMemberId)
      if (result.status === "requested") toast.info(result.detail)
      else toast.success(result.detail)
      await loadDetail(activeGroupId)
      return true
    } catch (err: unknown) {
      setSettleError(getErrorMessage(err, "No se pudo registrar el pago. Intenta de nuevo."))
      return false
    } finally { setSettlingKey(null) }
  }

  const handlePartialSettle = async () => {
    if (!activeGroupId || !paymentDialog || selectedSplitIds.size === 0) return
    setIsSettlingPartial(true)
    setSettleError("")
    try {
      const result = await sharedService.settleSelectedSplits(
        activeGroupId,
        Array.from(selectedSplitIds),
        paymentDialog.creditorId,
      )
      setPaymentDialog(null)
      setSelectedSplitIds(new Set())
      if (result.status === "requested") toast.info(result.detail)
      else toast.success(result.detail)
      await loadDetail(activeGroupId)
    } catch (err: unknown) {
      setSettleError(getErrorMessage(err, "No se pudo registrar el pago. Intenta de nuevo."))
    } finally { setIsSettlingPartial(false) }
  }

  const handleLeaveGroup = async () => {
    if (!activeGroupId) return
    setIsLeaving(true)
    setLeaveError("")
    try {
      await sharedService.leaveGroup(activeGroupId)
      setLeaveDialog(false)
      setActiveGroupId(null)
      setGroupDetail(null)
      setBalances([])
      await loadGroups()
    } catch (err: unknown) {
      setLeaveError(getErrorMessage(err, "No se pudo salir del grupo. Intenta de nuevo."))
    } finally { setIsLeaving(false) }
  }

  const handleContributeFund = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeGroupId) return
    setIsContributing(true)
    setFundError("")
    try {
      await sharedService.contributeFund(activeGroupId, {
        member_id: parseInt(fundForm.member_id),
        amount: parseFloat(fundForm.amount),
        note: fundForm.note || undefined,
        date: fundForm.date || undefined,
      })
      setFundDialog(false)
      setFundForm(prev => ({ ...prev, amount: "", note: "" }))
      await loadDetail(activeGroupId)
    } catch (err: unknown) {
      setFundError(getErrorMessage(err, "No se pudo registrar el aporte. Intenta de nuevo."))
    } finally { setIsContributing(false) }
  }

  const isFondo = groupDetail?.group_type === "fondo"
  const totalExpenses = groupDetail?.expenses.reduce((s, e) => s + e.amount, 0) ?? 0
  const activeMembers = useMemo(() => groupDetail?.members.filter(m => m.is_active) ?? [], [groupDetail])

  const fmtMonth = (ym: string) => {
    const [y, m] = ym.split("-")
    const names = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    return `${names[parseInt(m) - 1]} ${y}`
  }

  const expenseMonths = useMemo(() => {
    if (!groupDetail) return []
    return [...new Set(groupDetail.expenses.map(e => e.date.slice(0, 7)))].sort().reverse()
  }, [groupDetail])

  const filteredExpenses = useMemo(() => {
    if (!groupDetail) return []
    // Fondo groups share the month selector with the saldo sidebar card
    const month = groupDetail.group_type === "fondo" ? selectedFundMonth : selectedExpenseMonth
    if (month === "all") return groupDetail.expenses
    return groupDetail.expenses.filter(e => e.date.startsWith(month))
  }, [groupDetail, selectedExpenseMonth, selectedFundMonth])

  const fundMonths = useMemo(() => {
    if (!fundStatus || !groupDetail) return []
    const a = fundStatus.contributions.map(c => (c.date ?? "").slice(0, 7)).filter(Boolean)
    const b = groupDetail.expenses.map(e => e.date.slice(0, 7))
    return [...new Set([...a, ...b])].sort().reverse()
  }, [fundStatus, groupDetail])

  const filteredFundStats = useMemo(() => {
    if (!fundStatus || !groupDetail) return null
    if (selectedFundMonth === "all") return {
      total_contributed: fundStatus.total_contributed,
      total_spent: fundStatus.total_spent,
      balance: fundStatus.balance,
    }
    const contribs = fundStatus.contributions.filter(c => (c.date ?? "").startsWith(selectedFundMonth))
    const exps = groupDetail.expenses.filter(e => e.date.startsWith(selectedFundMonth))
    const contributed = contribs.reduce((s, c) => s + c.amount, 0)
    const spent = exps.reduce((s, e) => s + e.amount, 0)
    return { total_contributed: contributed, total_spent: spent, balance: contributed - spent }
  }, [fundStatus, groupDetail, selectedFundMonth])

  const filteredFundContribs = useMemo(() => {
    if (!fundStatus) return []
    if (selectedFundMonth === "all") return fundStatus.contributions
    return fundStatus.contributions.filter(c => (c.date ?? "").startsWith(selectedFundMonth))
  }, [fundStatus, selectedFundMonth])

  const filteredPerMember = useMemo(() => {
    if (!fundStatus) return []
    if (selectedFundMonth === "all") return fundStatus.per_member
    const totals: Record<number, { member_id: number; member_name: string; total_contributed: number }> = {}
    for (const m of fundStatus.per_member) {
      totals[m.member_id] = { ...m, total_contributed: 0 }
    }
    for (const c of filteredFundContribs) {
      if (totals[c.member_id]) totals[c.member_id].total_contributed += c.amount
    }
    return Object.values(totals).filter(m => m.total_contributed > 0)
  }, [fundStatus, filteredFundContribs, selectedFundMonth])

  return (
    <div className="max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Gastos Compartidos</h1>
          <p className="text-muted-foreground mt-1">Organiza los gastos con tu familia o amigos</p>
        </div>
        <div className="flex gap-2">
          {activeGroupId && groupDetail && (
            <>
            {/* Leave group — only for linked members */}
            {groupDetail.members.some(m => m.is_active && m.user_id === currentUser?.id) && (
              <Dialog open={leaveDialog} onOpenChange={(o) => { setLeaveDialog(o); if (!o) setLeaveError("") }}>
                <DialogTrigger asChild>
                  <Button variant="outline" className="text-destructive border-destructive/40 hover:bg-destructive/10">
                    <LogOut className="w-4 h-4 mr-2" />
                    Salir
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>¿Salir del grupo?</DialogTitle>
                  </DialogHeader>
                  <div className="py-3 space-y-3">
                    <p className="text-sm text-muted-foreground">
                      Saldrás de <span className="font-medium text-foreground">{groupDetail.name}</span>. Tu historial de gastos quedará registrado, pero ya no verás este grupo en tu cuenta.
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Si no quedan otros miembros activos, el grupo se eliminará automáticamente.
                    </p>
                    {leaveError && (
                      <p className="text-sm text-destructive flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4 shrink-0" />{leaveError}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-3 mt-2">
                    <Button variant="outline" className="flex-1" onClick={() => setLeaveDialog(false)}>
                      Cancelar
                    </Button>
                    <Button variant="destructive" className="flex-1" onClick={handleLeaveGroup} disabled={isLeaving}>
                      {isLeaving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <LogOut className="w-4 h-4 mr-2" />}
                      {isLeaving ? "Saliendo…" : "Sí, salir"}
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
            )}
            <Dialog open={newMemberDialog} onOpenChange={(o) => { setNewMemberDialog(o); if (!o) setMemberError("") }}>
              <DialogTrigger asChild>
                <Button variant="outline">
                  <UserPlus className="w-4 h-4 mr-2" />
                  Miembro
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Agregar Miembro</DialogTitle></DialogHeader>
                <form onSubmit={handleAddMember} className="space-y-4 mt-4">
                  <div>
                    <label className="text-sm font-medium text-foreground">Nombre</label>
                    <Input placeholder="Ej: Mamá" value={memberForm.name}
                      onChange={(e) => setMemberForm({ ...memberForm, name: e.target.value })} className="mt-2" required />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground">Email</label>
                    <Input type="email" placeholder="mama@email.com" value={memberForm.email}
                      onChange={(e) => setMemberForm({ ...memberForm, email: e.target.value })} className="mt-2" required />
                    <p className="text-xs text-muted-foreground mt-1">
                      Si el email está registrado en FinSmart, el miembro podrá ver este grupo en su cuenta.
                    </p>
                  </div>
                  {memberError && (
                    <p className="text-sm text-destructive flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 shrink-0" />{memberError}
                    </p>
                  )}
                  <Button type="submit" className="w-full" disabled={isSubmitting}>
                    {isSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    {isSubmitting ? "Agregando…" : "Agregar"}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
            </>
          )}
          <Dialog open={newGroupDialog} onOpenChange={(o) => { setNewGroupDialog(o); if (!o) setCreateGroupError("") }}>
            <DialogTrigger asChild>
              <Button variant="outline">
                <UserPlus className="w-4 h-4 mr-2" />
                Nuevo Grupo
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Crear Nuevo Grupo</DialogTitle></DialogHeader>
              <form onSubmit={handleCreateGroup} className="space-y-4 mt-4">
                {/* Group type selector */}
                <div>
                  <label className="text-sm font-medium text-foreground block mb-2">Tipo de grupo</label>
                  <div className="grid grid-cols-2 gap-2">
                    {([
                      { key: "gastos", icon: Receipt, label: "Gastos compartidos", sub: "Alguien paga y los demás le deben su parte" },
                      { key: "fondo", icon: PiggyBank, label: "Fondo común", sub: "Cada uno aporta dinero a un fondo para cubrir los gastos" },
                    ] as const).map(({ key, icon: Icon, label, sub }) => (
                      <button key={key} type="button"
                        onClick={() => setGroupForm({ ...groupForm, group_type: key })}
                        className={`p-3 rounded-lg border-2 text-left transition-all ${groupForm.group_type === key ? "border-foreground bg-foreground/5" : "border-border hover:border-foreground/40"}`}>
                        <Icon className="w-4 h-4 mb-1.5 text-foreground" />
                        <p className="text-sm font-semibold text-foreground">{label}</p>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-tight">{sub}</p>
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground">Nombre del grupo</label>
                  <Input placeholder={groupForm.group_type === "fondo" ? "Ej: Fondo Familiar" : "Ej: Casa de Mamá"} value={groupForm.name}
                    onChange={(e) => setGroupForm({ ...groupForm, name: e.target.value })} className="mt-2" required />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground">Descripción (opcional)</label>
                  <Input placeholder={groupForm.group_type === "fondo" ? "Ej: Gastos del hogar familiar" : "Ej: Gastos del hogar familiar"} value={groupForm.description}
                    onChange={(e) => setGroupForm({ ...groupForm, description: e.target.value })} className="mt-2" />
                </div>
                {createGroupError && (
                  <p className="text-sm text-destructive flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4 shrink-0" />{createGroupError}
                  </p>
                )}
                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  {isSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  {isSubmitting ? "Creando…" : "Crear Grupo"}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Group selector */}
      {groups.length > 0 && (() => {
        const myGroups = groups.filter(g => g.creator_id === currentUser?.id)
        const sharedWithMe = groups.filter(g => g.creator_id !== currentUser?.id)
        return (
          <div className="mb-6 space-y-3">
            {myGroups.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Mis grupos</p>
                <div className="flex gap-2 flex-wrap">
                  {myGroups.map(g => (
                    <Button key={g.id} variant={activeGroupId === g.id ? "default" : "outline"}
                      onClick={() => setActiveGroupId(g.id)} size="sm">
                      {g.name}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            {sharedWithMe.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1">
                  <Link2 className="w-3 h-3" />
                  Compartido conmigo
                </p>
                <div className="flex gap-2 flex-wrap">
                  {sharedWithMe.map(g => (
                    <Button key={g.id} variant={activeGroupId === g.id ? "default" : "outline"}
                      onClick={() => setActiveGroupId(g.id)} size="sm">
                      {g.name}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {loadingGroups ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : groupsError ? (
        <Card className="text-center py-16">
          <CardContent>
            <Users className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-foreground font-medium mb-2">{groupsError}</p>
            <p className="text-muted-foreground text-sm mb-4">
              Revisa tu conexión e inténtalo de nuevo.
            </p>
            <Button variant="outline" onClick={() => { setLoadingGroups(true); loadGroups() }}>
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : groups.length === 0 ? (
        <Card className="text-center py-16">
          <CardContent>
            <Users className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-foreground font-medium mb-2">
              No tienes grupos ni familiares registrados
            </p>
            <p className="text-muted-foreground text-sm mb-4">
              Crea un grupo para dividir gastos con otras personas, o un fondo
              familiar para llevar un bolsillo común.
            </p>
            <Button onClick={() => setNewGroupDialog(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Crear Grupo
            </Button>
          </CardContent>
        </Card>
      ) : isLoading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : groupDetail && (
        <>
          <div className="flex gap-2 mb-6 border-b border-border">
            {isFondo ? (
              <>
                <button onClick={() => setActiveTab("gastos")}
                  className={`px-4 py-3 font-medium transition-colors border-b-2 -mb-px ${activeTab === "gastos" ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  Gastos del fondo
                </button>
                <button onClick={() => setActiveTab("balances")}
                  className={`px-4 py-3 font-medium transition-colors border-b-2 -mb-px ${activeTab === "balances" ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  Estado del fondo
                </button>
              </>
            ) : (
              (["gastos", "balances"] as const).map(tab => (
                <button key={tab} onClick={() => setActiveTab(tab)}
                  className={`px-4 py-3 font-medium transition-colors border-b-2 -mb-px ${activeTab === tab ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  {tab === "gastos" ? "Gastos" : "Quién debe a quién"}
                </button>
              ))
            )}
          </div>

          {activeTab === "gastos" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-3">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        {isFondo ? <PiggyBank className="w-5 h-5" /> : <Home className="w-5 h-5" />}
                        {groupDetail.name}
                        {isFondo && <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-foreground/10 text-muted-foreground">Fondo común</span>}
                      </CardTitle>
                      <CardDescription>{groupDetail.description ?? `${activeMembers.length} miembros`}</CardDescription>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {isFondo && (
                        <Dialog open={fundDialog} onOpenChange={(o) => { setFundDialog(o); if (!o) setFundError("") }}>
                          <DialogTrigger asChild>
                            <Button>
                              <PiggyBank className="w-4 h-4 mr-2" />
                              Aportar al fondo
                            </Button>
                          </DialogTrigger>
                          <DialogContent>
                            <DialogHeader><DialogTitle>Aportar al fondo común</DialogTitle></DialogHeader>
                            <form onSubmit={handleContributeFund} className="space-y-4 mt-4">
                              <div>
                                <label className="text-sm font-medium text-foreground">Miembro que aporta</label>
                                <select value={fundForm.member_id}
                                  onChange={(e) => setFundForm({ ...fundForm, member_id: e.target.value })}
                                  className="mt-2 w-full h-10 px-3 rounded-md border border-input bg-background text-foreground" required>
                                  {groupDetail.members.filter(m => m.is_active).map(m => (
                                    <option key={m.id} value={m.id}>{m.name}</option>
                                  ))}
                                </select>
                              </div>
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <label className="text-sm font-medium text-foreground">Monto</label>
                                  <CurrencyInput placeholder="100.000" value={fundForm.amount}
                                    onValueChange={(v) => setFundForm({ ...fundForm, amount: v })} className="mt-2" required />
                                </div>
                                <div>
                                  <label className="text-sm font-medium text-foreground">Fecha</label>
                                  <Input type="date" value={fundForm.date}
                                    onChange={(e) => setFundForm({ ...fundForm, date: e.target.value })} className="mt-2" required />
                                </div>
                              </div>
                              <div>
                                <label className="text-sm font-medium text-foreground">Nota (opcional)</label>
                                <Input placeholder="Ej: Cuota de enero" value={fundForm.note}
                                  onChange={(e) => setFundForm({ ...fundForm, note: e.target.value })} className="mt-2" />
                              </div>
                              {fundError && (
                                <p className="text-sm text-destructive flex items-center gap-1.5">
                                  <AlertTriangle className="w-4 h-4 shrink-0" />{fundError}
                                </p>
                              )}
                              <Button type="submit" className="w-full" disabled={isContributing}>
                                {isContributing && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                {isContributing ? "Registrando…" : "Registrar aporte"}
                              </Button>
                            </form>
                          </DialogContent>
                        </Dialog>
                      )}
                    <Dialog open={newExpenseDialog} onOpenChange={(o) => { setNewExpenseDialog(o); if (!o) setExpenseError("") }}>
                      <DialogTrigger asChild>
                        <Button variant={isFondo ? "outline" : "default"}>
                          <Plus className="w-4 h-4 mr-2" />
                          {isFondo ? "Registrar gasto" : "Agregar Gasto"}
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader><DialogTitle>Registrar Gasto Compartido</DialogTitle></DialogHeader>
                        <form onSubmit={handleAddExpense} className="space-y-4 mt-4">
                          <div>
                            <label className="text-sm font-medium text-foreground">Descripción</label>
                            <Input placeholder="Ej: Mercado" value={expenseForm.description}
                              onChange={(e) => setExpenseForm({ ...expenseForm, description: e.target.value })} className="mt-2" required />
                          </div>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="text-sm font-medium text-foreground">Monto</label>
                              <CurrencyInput placeholder="0" value={expenseForm.amount}
                                onValueChange={(v) => setExpenseForm({ ...expenseForm, amount: v })} className="mt-2" required />
                            </div>
                            <div>
                              <label className="text-sm font-medium text-foreground">Fecha</label>
                              <Input type="date" value={expenseForm.date}
                                onChange={(e) => setExpenseForm({ ...expenseForm, date: e.target.value })} className="mt-2" required />
                            </div>
                          </div>
                          {isFondo ? (
                            <div className="space-y-3">
                              <div>
                                <label className="text-sm font-medium text-foreground">Categoría</label>
                                <select value={expenseForm.category}
                                  onChange={(e) => setExpenseForm({ ...expenseForm, category: e.target.value })}
                                  className="mt-2 w-full h-10 px-3 rounded-md border border-input bg-background text-foreground">
                                  {Object.keys(expenseIcons).map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                              </div>
                              {(() => {
                                const amount = parseFloat(expenseForm.amount) || 0
                                const overLimit = isFondo && fundStatus && amount > fundStatus.balance
                                return overLimit ? (
                                  <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 flex items-center gap-2 text-sm text-destructive">
                                    <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                                    Saldo insuficiente: el fondo tiene {formatCOP(fundStatus!.balance)} disponibles.
                                  </div>
                                ) : (
                                  <div className="rounded-lg bg-secondary/40 p-3 flex items-center gap-2 text-sm text-muted-foreground">
                                    <PiggyBank className="w-4 h-4 flex-shrink-0" />
                                    Este gasto se descontará del fondo común del grupo.
                                    {fundStatus && ` Disponible: ${formatCOP(fundStatus.balance)}.`}
                                  </div>
                                )
                              })()}
                            </div>
                          ) : (
                            <>
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <label className="text-sm font-medium text-foreground">Pagado por</label>
                                  <select value={expenseForm.paid_by_id}
                                    onChange={(e) => setExpenseForm({ ...expenseForm, paid_by_id: e.target.value })}
                                    className="mt-2 w-full h-10 px-3 rounded-md border border-input bg-background text-foreground">
                                    {groupDetail.members.filter(m => m.is_active).map(m => (
                                      <option key={m.id} value={m.id}>{m.name}</option>
                                    ))}
                                  </select>
                                </div>
                                <div>
                                  <label className="text-sm font-medium text-foreground">Categoría</label>
                                  <select value={expenseForm.category}
                                    onChange={(e) => setExpenseForm({ ...expenseForm, category: e.target.value })}
                                    className="mt-2 w-full h-10 px-3 rounded-md border border-input bg-background text-foreground">
                                    {Object.keys(expenseIcons).map(c => <option key={c} value={c}>{c}</option>)}
                                  </select>
                                </div>
                              </div>

                              {/* Split mode toggle */}
                              <div>
                                <label className="text-sm font-medium text-foreground">División</label>
                                <div className="mt-2 flex rounded-md border border-input overflow-hidden">
                                  {(["equal", "custom"] as const).map(mode => (
                                    <button key={mode} type="button"
                                      onClick={() => {
                                        setSplitMode(mode)
                                        if (mode === "equal") setMemberPcts({})
                                        else {
                                          const eq = Math.floor(100 / activeMembers.length)
                                          const rem = 100 - eq * activeMembers.length
                                          const init: Record<number, number> = {}
                                          activeMembers.forEach((m, i) => { init[m.id] = eq + (i === 0 ? rem : 0) })
                                          setMemberPcts(init)
                                        }
                                      }}
                                      className={`flex-1 py-2 text-sm font-medium transition-colors ${splitMode === mode ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}>
                                      {mode === "equal" ? "Partes iguales" : "Por porcentaje"}
                                    </button>
                                  ))}
                                </div>
                              </div>

                              {/* Percentage breakdown */}
                              {splitMode === "equal" ? (
                                <div className="rounded-lg bg-secondary/50 p-3">
                                  {activeMembers.map(m => {
                                    const total = parseFloat(expenseForm.amount) || 0
                                    const share = total / activeMembers.length
                                    return (
                                      <div key={m.id} className="flex justify-between text-sm py-1">
                                        <span className="text-foreground">{m.name}</span>
                                        <span className="text-muted-foreground">
                                          {(100 / activeMembers.length).toFixed(1)}% · <span className="font-medium text-foreground">{formatCOP(share)}</span>
                                        </span>
                                      </div>
                                    )
                                  })}
                                </div>
                              ) : (
                                <div className="rounded-lg border border-input p-3 space-y-2">
                                  {activeMembers.map(m => {
                                    const total = parseFloat(expenseForm.amount) || 0
                                    const pct = memberPcts[m.id] ?? 0
                                    const amount = (pct / 100) * total
                                    return (
                                      <div key={m.id} className="flex items-center gap-2">
                                        <span className="text-sm text-foreground w-24 truncate">{m.name}</span>
                                        <input type="number" min="0" max="100" step="1" value={pct}
                                          onChange={e => setMemberPcts(prev => ({ ...prev, [m.id]: parseFloat(e.target.value) || 0 }))}
                                          className="w-16 h-8 text-sm text-center rounded border border-input bg-background text-foreground" />
                                        <span className="text-xs text-muted-foreground">%</span>
                                        <span className="ml-auto text-sm font-medium text-foreground">
                                          {formatCOP(amount)}
                                        </span>
                                      </div>
                                    )
                                  })}
                                  {(() => {
                                    const sum = Object.values(memberPcts).reduce((a, b) => a + b, 0)
                                    const ok = Math.abs(sum - 100) < 0.5
                                    return (
                                      <div className={`text-xs font-medium pt-1 border-t border-input flex justify-between ${ok ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
                                        <span>Total</span>
                                        <span>{sum.toFixed(0)}% {!ok && "(debe ser 100%)"}</span>
                                      </div>
                                    )
                                  })()}
                                </div>
                              )}
                            </>
                          )}

                          {expenseError && (
                            <p className="text-sm text-destructive flex items-center gap-1.5">
                              <AlertTriangle className="w-4 h-4 shrink-0" />{expenseError}
                            </p>
                          )}
                          <Button type="submit" className="w-full"
                            disabled={
                              isSubmitting
                              || (!isFondo && splitMode === "custom" && Math.abs(Object.values(memberPcts).reduce((a,b)=>a+b,0)-100) > 0.5)
                              || (isFondo && !!fundStatus && (parseFloat(expenseForm.amount) || 0) > fundStatus.balance)
                            }>
                            {isSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            {isSubmitting ? "Registrando…" : "Registrar Gasto"}
                          </Button>
                        </form>
                      </DialogContent>
                    </Dialog>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-3 sm:gap-4 mb-6">
                      <div className="p-4 rounded-lg bg-secondary/50">
                        <p className="text-sm text-muted-foreground">Total gastos</p>
                        <p className="text-2xl font-bold text-foreground">{formatCOP(totalExpenses)}</p>
                      </div>
                      <div className="p-4 rounded-lg bg-secondary/50">
                        <p className="text-sm text-muted-foreground">Miembros</p>
                        <p className="text-2xl font-bold text-foreground">{activeMembers.length}</p>
                      </div>
                    </div>

                    {!isFondo && expenseMonths.length > 1 && (
                      <div className="mb-4 flex items-center gap-2">
                        <label className="text-xs text-muted-foreground font-medium whitespace-nowrap">Ver mes:</label>
                        <select value={selectedExpenseMonth} onChange={e => setSelectedExpenseMonth(e.target.value)}
                          className="h-8 px-2 text-xs rounded-md border border-input bg-background text-foreground">
                          <option value="all">Todos</option>
                          {expenseMonths.map(m => <option key={m} value={m}>{fmtMonth(m)}</option>)}
                        </select>
                      </div>
                    )}

                    {filteredExpenses.length === 0 ? (
                      <p className="text-center text-muted-foreground py-8">No hay gastos en este período.</p>
                    ) : (
                      <div className="space-y-3">
                        {filteredExpenses.map((expense) => {
                          const Icon = expenseIcons[expense.category ?? "Otro"] ?? Wallet
                          const payer = groupDetail.members.find(m => m.id === expense.paid_by_id)
                          const allSettled = expense.splits.length > 0 && expense.splits.every(s => s.is_settled)
                          return (
                            <div key={expense.id} className="p-4 rounded-lg bg-secondary/50">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-4">
                                  <div className="w-10 h-10 rounded-full bg-background flex items-center justify-center flex-shrink-0">
                                    <Icon className="w-5 h-5 text-foreground" />
                                  </div>
                                  <div>
                                    <div className="flex items-center gap-2">
                                      <p className="font-medium text-foreground">{expense.description}</p>
                                      {allSettled && (
                                        <span className="text-xs px-1.5 py-0.5 rounded bg-green-500/15 text-green-600 dark:text-green-400 font-medium flex items-center gap-1">
                                          <CheckCircle2 className="w-3 h-3" />
                                          Saldado
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-sm text-muted-foreground">
                                      Pagado por <span className="font-medium">{payer?.name ?? "—"}</span> • {expense.date}
                                    </p>
                                  </div>
                                </div>
                                <span className="font-semibold text-foreground">{formatCOP(expense.amount)}</span>
                              </div>
                              {expense.splits.length > 0 && (
                                <div className="mt-3 pl-14 space-y-1.5 border-t border-border pt-3">
                                  {expense.splits.map(split => {
                                    const member = groupDetail.members.find(m => m.id === split.member_id)
                                    const isPayer = split.member_id === expense.paid_by_id
                                    return (
                                      <div key={split.id} className="flex items-center justify-between">
                                        <div className="flex items-center gap-1.5">
                                          {split.is_settled
                                            ? <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                                            : <Circle className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />}
                                          <span className={`text-xs ${split.is_settled ? "text-muted-foreground" : "text-foreground"}`}>
                                            {member?.name ?? `#${split.member_id}`}
                                            {isPayer && <span className="text-muted-foreground"> · pagó</span>}
                                          </span>
                                        </div>
                                        <span className={`text-xs font-bold tabular-nums ${split.is_settled ? "text-green-600 dark:text-green-400 line-through" : "text-foreground"}`}>
                                          {formatCOP(split.amount)}
                                        </span>
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-4">
                {isFondo && fundStatus && filteredFundStats && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <PiggyBank className="w-4 h-4" />
                        Saldo del fondo
                      </CardTitle>
                      {fundMonths.length > 0 && (
                        <select value={selectedFundMonth} onChange={e => setSelectedFundMonth(e.target.value)}
                          className="mt-2 h-8 w-full px-2 text-xs rounded-md border border-input bg-background text-foreground">
                          <option value="all">Todos los meses</option>
                          {fundMonths.map(m => <option key={m} value={m}>{fmtMonth(m)}</option>)}
                        </select>
                      )}
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Aportado</span>
                          <span className="font-semibold text-foreground tabular-nums">
                            {formatCOP(filteredFundStats.total_contributed)}
                          </span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Gastado</span>
                          <span className="font-semibold text-destructive tabular-nums">
                            -{formatCOP(filteredFundStats.total_spent)}
                          </span>
                        </div>
                        <div className="pt-2 border-t border-border flex justify-between text-sm font-bold">
                          <span className="text-foreground">Disponible</span>
                          <span className={`tabular-nums ${filteredFundStats.balance >= 0 ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
                            {formatCOP(filteredFundStats.balance)}
                          </span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}
                <Card>
                  <CardHeader>
                    <CardTitle>Miembros</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {groupDetail.members.filter(m => m.is_active).map((member) => {
                        const isCreator = member.user_id === groupDetail.creator_id
                        const isLinked = member.user_id != null
                        const isSelf = member.user_id === currentUser?.id
                        const canAdminister = currentUser?.id === groupDetail.creator_id
                        return (
                          <div key={member.id} className="flex items-center gap-3 p-3 rounded-lg bg-secondary/50">
                            <div className="w-8 h-8 rounded-full bg-foreground flex items-center justify-center flex-shrink-0">
                              <span className="text-sm font-medium text-background">
                                {member.name.charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <p className="font-medium text-foreground">{member.name}</p>
                                {isCreator && (
                                  <span className="text-xs px-1.5 py-0.5 rounded bg-foreground/10 text-foreground font-medium">Creador</span>
                                )}
                                {isLinked && !isCreator && (
                                  <span className="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium flex items-center gap-1">
                                    <Link2 className="w-3 h-3" />
                                    En FinSmart
                                  </span>
                                )}
                              </div>
                              {member.email && <p className="text-xs text-muted-foreground truncate">{member.email}</p>}
                            </div>
                            {canAdminister && (
                              <div className="flex items-center gap-1 flex-shrink-0">
                                <button type="button" title="Editar nombre"
                                  onClick={() => { setEditMemberDialog({ id: member.id, name: member.name }); setEditMemberName(member.name); setEditMemberError("") }}
                                  className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-background transition-colors">
                                  <Pencil className="w-3.5 h-3.5" />
                                </button>
                                {!isSelf && (
                                  <button type="button" title="Eliminar del grupo"
                                    onClick={() => { setRemoveMemberDialog({ id: member.id, name: member.name }); setRemoveMemberError("") }}
                                    className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-background transition-colors">
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>

                {/* Edit member name */}
                <Dialog open={!!editMemberDialog} onOpenChange={(o) => { if (!o) setEditMemberDialog(null) }}>
                  <DialogContent>
                    <DialogHeader><DialogTitle>Editar nombre</DialogTitle></DialogHeader>
                    <form onSubmit={handleEditMember} className="space-y-4 mt-4">
                      <div>
                        <label className="text-sm font-medium text-foreground">Nombre</label>
                        <Input value={editMemberName}
                          onChange={(e) => setEditMemberName(e.target.value)} className="mt-2" required />
                      </div>
                      {editMemberError && (
                        <p className="text-sm text-destructive flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 shrink-0" />{editMemberError}
                        </p>
                      )}
                      <Button type="submit" className="w-full" disabled={isSavingMember}>
                        {isSavingMember && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                        {isSavingMember ? "Guardando…" : "Guardar"}
                      </Button>
                    </form>
                  </DialogContent>
                </Dialog>

                {/* Remove member confirmation */}
                <Dialog open={!!removeMemberDialog} onOpenChange={(o) => { if (!o) setRemoveMemberDialog(null) }}>
                  <DialogContent>
                    <DialogHeader><DialogTitle>¿Eliminar miembro?</DialogTitle></DialogHeader>
                    <div className="py-3 space-y-3">
                      <p className="text-sm text-muted-foreground">
                        Se eliminará a <span className="font-medium text-foreground">{removeMemberDialog?.name}</span> del grupo. Su historial de gastos quedará registrado, pero ya no podrá participar en nuevos gastos.
                      </p>
                      {removeMemberError && (
                        <p className="text-sm text-destructive flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 shrink-0" />{removeMemberError}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-3 mt-2">
                      <Button variant="outline" className="flex-1" onClick={() => setRemoveMemberDialog(null)}>
                        Cancelar
                      </Button>
                      <Button variant="destructive" className="flex-1" onClick={handleRemoveMember} disabled={isRemovingMember}>
                        {isRemovingMember ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Trash2 className="w-4 h-4 mr-2" />}
                        {isRemovingMember ? "Eliminando…" : "Sí, eliminar"}
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </div>
          )}

          {activeTab === "balances" && isFondo && fundStatus && filteredFundStats && (
            <div className="space-y-6">
              {/* Month selector */}
              {fundMonths.length > 0 && (
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground font-medium whitespace-nowrap">Ver mes:</label>
                  <select value={selectedFundMonth} onChange={e => setSelectedFundMonth(e.target.value)}
                    className="h-8 px-2 text-xs rounded-md border border-input bg-background text-foreground">
                    <option value="all">Todos los meses</option>
                    {fundMonths.map(m => <option key={m} value={m}>{fmtMonth(m)}</option>)}
                  </select>
                </div>
              )}

              {/* Fund summary */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-xl border border-border p-4 text-center">
                  <p className="text-xs text-muted-foreground mb-1">Total aportado</p>
                  <p className="text-xl font-black text-foreground tabular-nums">
                    {formatCOP(filteredFundStats.total_contributed)}
                  </p>
                </div>
                <div className="rounded-xl border border-border p-4 text-center">
                  <p className="text-xs text-muted-foreground mb-1">Total gastado</p>
                  <p className="text-xl font-black text-destructive tabular-nums">
                    {formatCOP(filteredFundStats.total_spent)}
                  </p>
                </div>
                <div className={`rounded-xl border p-4 text-center ${filteredFundStats.balance >= 0 ? "border-green-500/30 bg-green-500/5" : "border-destructive/30 bg-destructive/5"}`}>
                  <p className="text-xs text-muted-foreground mb-1">Saldo disponible</p>
                  <p className={`text-xl font-black tabular-nums ${filteredFundStats.balance >= 0 ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
                    {formatCOP(filteredFundStats.balance)}
                  </p>
                </div>
              </div>

              {/* Per-member contributions */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Aportes por miembro</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {filteredPerMember.length > 0 ? filteredPerMember.map(m => {
                    const base = filteredFundStats!.total_contributed
                    const pct = base > 0 ? Math.round((m.total_contributed / base) * 100) : 0
                    return (
                      <div key={m.member_id}>
                        <div className="flex items-center gap-2 mb-1">
                          <div className="w-7 h-7 rounded-full bg-foreground flex items-center justify-center flex-shrink-0">
                            <span className="text-xs font-bold text-background">{m.member_name.charAt(0).toUpperCase()}</span>
                          </div>
                          <span className="text-sm font-medium text-foreground flex-1">{m.member_name}</span>
                          <span className="text-sm font-semibold text-foreground tabular-nums">
                            {formatCOP(m.total_contributed)}
                          </span>
                        </div>
                        <div className="h-1.5 bg-secondary rounded-full ml-9 overflow-hidden">
                          <div className="h-full bg-foreground/60 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )
                  }) : (
                    <p className="text-sm text-muted-foreground text-center py-4">No hay aportes en este período.</p>
                  )}
                </CardContent>
              </Card>

              {/* Contribution history */}
              {filteredFundContribs.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Historial de aportes</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2.5">
                      {filteredFundContribs.map(c => {
                        const memberName = groupDetail!.members.find(m => m.id === c.member_id)?.name ?? `#${c.member_id}`
                        return (
                          <div key={c.id} className="flex items-center gap-3 p-3 rounded-lg bg-secondary/40">
                            <div className="w-8 h-8 rounded-full bg-foreground flex items-center justify-center flex-shrink-0">
                              <span className="text-xs font-bold text-background">{memberName.charAt(0).toUpperCase()}</span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground">{memberName}</p>
                              {c.note && <p className="text-xs text-muted-foreground truncate">{c.note}</p>}
                              <p className="text-xs text-muted-foreground">{c.date ?? "—"}</p>
                            </div>
                            <span className="text-sm font-bold text-green-600 dark:text-green-400 tabular-nums flex-shrink-0">
                              +{formatCOP(c.amount)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {activeTab === "balances" && !isFondo && (() => {
            const allDebts = balances.flatMap(b =>
              b.owes_to.map(d => ({
                debtorId: b.member_id, debtorName: b.member_name,
                creditorId: d.member_id, creditorName: d.member_name, amount: d.amount,
              }))
            )
            const settled = allDebts.length === 0

            return (
              <div className="space-y-6">
                {/* Per-member net balance summary */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                  {balances.map(b => (
                    <div key={b.member_id} className="rounded-xl border border-border p-4 flex flex-col items-center gap-2 text-center">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm ${b.net_balance > 0 ? "bg-green-500/15 text-green-600 dark:text-green-400" : b.net_balance < 0 ? "bg-destructive/15 text-destructive" : "bg-secondary text-muted-foreground"}`}>
                        {b.member_name.charAt(0).toUpperCase()}
                      </div>
                      <p className="font-medium text-foreground text-sm leading-tight">{b.member_name}</p>
                      <p className={`text-xs font-semibold ${b.net_balance > 0 ? "text-green-600 dark:text-green-400" : b.net_balance < 0 ? "text-destructive" : "text-muted-foreground"}`}>
                        {b.net_balance > 0 ? `+${formatCOP(b.net_balance)}` : b.net_balance < 0 ? `-${formatCOP(Math.abs(b.net_balance))}` : "Al día"}
                      </p>
                    </div>
                  ))}
                </div>

                {/* Debt list */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Deudas pendientes</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {settleError && (
                      <p className="text-sm text-destructive flex items-center gap-1.5 mb-3">
                        <AlertTriangle className="w-4 h-4 shrink-0" />{settleError}
                      </p>
                    )}
                    {settled ? (
                      <div className="text-center py-8">
                        <CheckCircle2 className="w-10 h-10 text-green-500 mx-auto mb-3" />
                        <p className="font-medium text-foreground">¡Todo saldado!</p>
                        <p className="text-sm text-muted-foreground mt-1">No hay deudas pendientes en este grupo.</p>
                      </div>
                    ) : (
                      <div className="divide-y divide-border">
                        {allDebts.map((debt, i) => {
                          const key = `${debt.debtorId}-${debt.creditorId}`
                          const busy = settlingKey === key
                          const isExpanded = expandedDebt === key

                          // Who is the debtor as a member record?
                          const debtorMember = groupDetail!.members.find(m => m.id === debt.debtorId)
                          const isMyDebt = debtorMember?.user_id === currentUser?.id

                          // Which expenses make up this debt?
                          const contributing = groupDetail!.expenses.filter(e =>
                            e.paid_by_id === debt.creditorId &&
                            e.splits.some(s => s.member_id === debt.debtorId && !s.is_settled)
                          )

                          return (
                            <div key={i} className="py-4">
                              {/* Main row: debtor | amount | creditor | actions — grid keeps columns aligned across all rows */}
                              <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr_auto] items-center gap-x-2 gap-y-2">
                                {/* Debtor */}
                                <div className="flex items-center gap-2 min-w-0">
                                  <div className={`w-9 h-9 rounded-full border flex items-center justify-center flex-shrink-0 ${isMyDebt ? "bg-destructive/15 border-destructive/30" : "bg-destructive/10 border-destructive/20"}`}>
                                    <span className="text-sm font-bold text-destructive">{debt.debtorName.charAt(0).toUpperCase()}</span>
                                  </div>
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      <p className="text-sm font-semibold text-foreground truncate">{debt.debtorName}</p>
                                      {isMyDebt && (
                                        <span className="text-xs px-1.5 py-0.5 rounded bg-destructive/10 text-destructive font-medium flex-shrink-0">Tú</span>
                                      )}
                                    </div>
                                    <p className="text-xs text-muted-foreground">debe pagar</p>
                                  </div>
                                </div>

                                {/* Amount */}
                                <div className="flex flex-row sm:flex-col items-center justify-center gap-2 sm:gap-0 px-2">
                                  <p className="text-lg font-black text-foreground tabular-nums">{formatCOP(debt.amount)}</p>
                                  <p className="text-xs text-muted-foreground">a</p>
                                </div>

                                {/* Creditor */}
                                <div className="flex items-center gap-2 min-w-0 sm:justify-end">
                                  <div className="min-w-0 sm:text-right">
                                    <p className="text-sm font-semibold text-foreground truncate">{debt.creditorName}</p>
                                    <p className="text-xs text-muted-foreground">le deben</p>
                                  </div>
                                  <div className="w-9 h-9 rounded-full bg-green-500/10 border border-green-500/20 flex items-center justify-center flex-shrink-0">
                                    <span className="text-sm font-bold text-green-600 dark:text-green-400">{debt.creditorName.charAt(0).toUpperCase()}</span>
                                  </div>
                                </div>

                                {/* Action buttons */}
                                <div className="flex items-center flex-wrap gap-1.5 flex-shrink-0 justify-end">
                                  {contributing.length > 0 && (
                                    <Button variant="ghost" size="sm" className="h-9 text-xs text-muted-foreground px-2"
                                      onClick={() => setExpandedDebt(isExpanded ? null : key)}>
                                      <Receipt className="w-3 h-3 mr-1" />
                                      {contributing.length}
                                      {isExpanded ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />}
                                    </Button>
                                  )}
                                  {isMyDebt ? (
                                    contributing.length > 1 ? (
                                      <Button size="sm" className="h-9 text-xs"
                                        disabled={settlingKey !== null || isSettlingPartial}
                                        onClick={() => {
                                          const options = contributing.map(exp => {
                                            const mySplit = exp.splits.find(s => s.member_id === debt.debtorId && !s.is_settled)
                                            return { splitId: mySplit!.id, description: exp.description, date: exp.date, amount: mySplit?.amount ?? 0 }
                                          })
                                          setPaymentDialog({ debtKey: key, creditorId: debt.creditorId, creditorName: debt.creditorName, options })
                                          setSelectedSplitIds(new Set(options.map(o => o.splitId)))
                                        }}>
                                        <CheckCircle2 className="w-3 h-3 mr-1.5" />
                                        Pagar
                                      </Button>
                                    ) : (
                                      <Button size="sm" className="h-9 text-xs"
                                        disabled={busy || settlingKey !== null}
                                        onClick={() => handleSettle(debt.debtorId, debt.creditorId)}>
                                        {busy ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <CheckCircle2 className="w-3 h-3 mr-1.5" />}
                                        {busy ? "Pagando…" : "Pagar"}
                                      </Button>
                                    )
                                  ) : (
                                    <Button variant="outline" size="sm" className="h-9 text-xs"
                                      disabled={busy || settlingKey !== null}
                                      onClick={() => setResponsibilityDialog({ debtorId: debt.debtorId, creditorId: debt.creditorId, debtorName: debt.debtorName, creditorName: debt.creditorName, amount: debt.amount })}>
                                      {busy ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <CheckCircle2 className="w-3 h-3 mr-1.5" />}
                                      {busy ? "Saldando…" : "Saldar"}
                                    </Button>
                                  )}
                                </div>
                              </div>

                              {/* Expanded: contributing expenses */}
                              {isExpanded && contributing.length > 0 && (
                                <div className="mt-3 ml-0 sm:ml-11 rounded-lg border border-border overflow-hidden">
                                  <div className="px-3 py-2 bg-secondary/40 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                    Gastos que generan esta deuda
                                  </div>
                                  {contributing.map(exp => {
                                    const mySplit = exp.splits.find(s => s.member_id === debt.debtorId && !s.is_settled)
                                    return (
                                      <div key={exp.id} className="flex items-center justify-between px-3 py-2.5 border-t border-border first:border-t-0">
                                        <div className="min-w-0">
                                          <p className="text-sm text-foreground font-medium truncate">{exp.description}</p>
                                          <p className="text-xs text-muted-foreground">{exp.date}</p>
                                        </div>
                                        <span className="text-sm font-semibold text-destructive ml-4 flex-shrink-0">
                                          {formatCOP((mySplit?.amount ?? 0))}
                                        </span>
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* "Take responsibility" confirmation dialog */}
                <Dialog open={!!responsibilityDialog} onOpenChange={o => { if (!o) { setResponsibilityDialog(null); setSettleError("") } }}>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle className="flex items-center gap-2">
                        <AlertTriangle className="w-5 h-5 text-amber-500" />
                        ¿Pagar por {responsibilityDialog?.debtorName}?
                      </DialogTitle>
                    </DialogHeader>
                    <div className="py-3 space-y-3">
                      <p className="text-sm text-muted-foreground">
                        Esta deuda de{" "}
                        <span className="font-semibold text-foreground">{formatCOP(responsibilityDialog?.amount)}</span>{" "}
                        pertenece a <span className="font-semibold text-foreground">{responsibilityDialog?.debtorName}</span>.
                        Si continúas, el pago se registrará a tu nombre.
                      </p>
                      <p className="text-sm text-muted-foreground">
                        <span className="font-medium text-foreground">{responsibilityDialog?.debtorName}</span> quedará en paz con{" "}
                        <span className="font-medium text-foreground">{responsibilityDialog?.creditorName}</span> y la deuda se marcará saldada.
                      </p>
                      {settleError && (
                        <p className="text-sm text-destructive flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 shrink-0" />{settleError}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-3 mt-2">
                      <Button variant="outline" className="flex-1" onClick={() => setResponsibilityDialog(null)}>
                        Cancelar
                      </Button>
                      <Button className="flex-1" disabled={settlingKey !== null}
                        onClick={async () => {
                          if (!responsibilityDialog) return
                          const ok = await handleSettle(responsibilityDialog.debtorId, responsibilityDialog.creditorId)
                          if (ok) setResponsibilityDialog(null)
                        }}>
                        {settlingKey ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
                        Sí, pago yo
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>

                {/* Payment selection dialog — choose which expenses to pay */}
                <Dialog open={!!paymentDialog} onOpenChange={o => { if (!o) { setPaymentDialog(null); setSelectedSplitIds(new Set()); setSettleError("") } }}>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>¿Qué deudas quieres pagar?</DialogTitle>
                    </DialogHeader>
                    <p className="text-sm text-muted-foreground -mt-1">
                      Selecciona los gastos que vas a saldar con{" "}
                      <span className="font-semibold text-foreground">{paymentDialog?.creditorName}</span>.
                    </p>
                    <div className="space-y-2 my-2 max-h-64 overflow-y-auto pr-1">
                      {paymentDialog?.options.map(opt => {
                        const checked = selectedSplitIds.has(opt.splitId)
                        return (
                          <label key={opt.splitId}
                            className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${checked ? "border-primary bg-primary/5" : "border-border hover:bg-secondary/40"}`}>
                            <input
                              type="checkbox"
                              className="accent-primary w-4 h-4 flex-shrink-0"
                              checked={checked}
                              onChange={() => {
                                setSelectedSplitIds(prev => {
                                  const next = new Set(prev)
                                  next.has(opt.splitId) ? next.delete(opt.splitId) : next.add(opt.splitId)
                                  return next
                                })
                              }}
                            />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground truncate">{opt.description}</p>
                              <p className="text-xs text-muted-foreground">{opt.date}</p>
                            </div>
                            <span className="text-sm font-semibold text-destructive flex-shrink-0">
                              {formatCOP(opt.amount)}
                            </span>
                          </label>
                        )
                      })}
                    </div>
                    {selectedSplitIds.size > 0 && (
                      <div className="flex items-center justify-between text-sm py-2 border-t border-border">
                        <span className="text-muted-foreground">{selectedSplitIds.size} gasto{selectedSplitIds.size !== 1 ? "s" : ""} seleccionado{selectedSplitIds.size !== 1 ? "s" : ""}</span>
                        <span className="font-semibold text-foreground">
                          {formatCOP((paymentDialog?.options.filter(o => selectedSplitIds.has(o.splitId)).reduce((s, o) => s + o.amount, 0) ?? 0))}
                        </span>
                      </div>
                    )}
                    {settleError && (
                      <p className="text-sm text-destructive flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4 shrink-0" />{settleError}
                      </p>
                    )}
                    <div className="flex gap-3 mt-1">
                      <Button variant="outline" className="flex-1" onClick={() => { setPaymentDialog(null); setSelectedSplitIds(new Set()); setSettleError("") }}>
                        Cancelar
                      </Button>
                      <Button className="flex-1" disabled={selectedSplitIds.size === 0 || isSettlingPartial}
                        onClick={handlePartialSettle}>
                        {isSettlingPartial
                          ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Pagando…</>
                          : <><CheckCircle2 className="w-4 h-4 mr-2" />Pagar seleccionados</>}
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            )
          })()}
        </>
      )}
    </div>
  )
}

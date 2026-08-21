"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { useRouter } from "next/navigation"
import {
  Zap, Plus, Trash2, QrCode, ExternalLink, Copy, Check,
  Loader2, AlertCircle, CheckCircle2, RefreshCw, FileText,
  CalendarClock, DollarSign, Hash, Info, ChevronDown, PartyPopper, ShieldAlert,
  Settings, Pencil, CreditCard, Building2,
} from "lucide-react"
import { invoiceService } from "@/lib/services/invoices"
import { transactionService } from "@/lib/services/transactions"
import { formatCOP } from "@/lib/format"
import type {
  RecurringService, InvoiceResult, ProviderInfo, PSEInitResponse, PSEBank,
  EmcaliCaptchaResponse,
} from "@/lib/types"

// Indicativo por ciudad, igual que en el portal de Movistar: para el
// identificador "número de línea" la referencia es indicativo + 7 dígitos.
const CIUDADES_MOVISTAR: [string, string][] = [
  ["601", "Bogotá"], ["602", "Cali"], ["604", "Medellín"], ["605", "Barranquilla"],
  ["606", "Pereira"], ["607", "Bucaramanga"], ["608", "Ibagué"],
]

// ── Types ─────────────────────────────────────────────────────────────────────

interface FetchState {
  contractId: number
  status: "idle" | "loading" | "done" | "error"
  result?: InvoiceResult
  errorMsg?: string
  isUpToDate?: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }
  return (
    <button onClick={copy} className="ml-1 text-muted-foreground hover:text-foreground transition-colors">
      {copied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

function ProviderBadge({ provider, providers }: { provider: string; providers: ProviderInfo[] }) {
  const info = providers.find((p) => p.id === provider)
  return (
    <span className="inline-flex items-center rounded-md bg-secondary px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
      {info?.name ?? provider}
    </span>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FacturasPage() {
  const router = useRouter()
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [contracts, setContracts] = useState<RecurringService[]>([])
  const [loadingContracts, setLoadingContracts] = useState(true)

  // Add contract form
  const [showAdd, setShowAdd] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState("")
  const [showProviderMenu, setShowProviderMenu] = useState(false)
  const [newNumber, setNewNumber] = useState("")
  const [newAlias, setNewAlias] = useState("")
  const [newPayerEmail, setNewPayerEmail] = useState("")
  // Movistar: '1' con número de línea, '2' con referencia de pago
  const [mvTipo, setMvTipo] = useState("1")
  const [mvIndicativo, setMvIndicativo] = useState("602")
  const [mvLinea, setMvLinea] = useState("")
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState("")

  // Per-contract fetch state
  const [fetchStates, setFetchStates] = useState<Record<number, FetchState>>({})

  // Invoice result dialog
  const [activeResult, setActiveResult] = useState<InvoiceResult | null>(null)
  const [activeContractId, setActiveContractId] = useState<number | null>(null)
  const [showQr, setShowQr] = useState(false)

  // Delete confirmation
  const [deleteId, setDeleteId] = useState<number | null>(null)

  // Edit GDO payer fields (email + cedula)
  const [editEmailContract, setEditEmailContract] = useState<RecurringService | null>(null)
  const [editEmailValue, setEditEmailValue] = useState("")
  const [savingEmail, setSavingEmail] = useState(false)
  const [editEmailError, setEditEmailError] = useState("")

  // Register payment
  const [registering, setRegistering] = useState(false)
  const [registeredFor, setRegisteredFor] = useState<number | null>(null)

  // EMCALI: desafío reCAPTCHA retransmitido desde el navegador del backend
  const [emcali, setEmcali] = useState<EmcaliCaptchaResponse | null>(null)
  const [emcaliContractId, setEmcaliContractId] = useState<number | null>(null)
  const [emcaliBusy, setEmcaliBusy] = useState(false)
  const [emcaliError, setEmcaliError] = useState("")
  const pollsRef = useRef(0)

  // PSE payment
  const [showPse, setShowPse] = useState(false)
  const [pseSession, setPseSession] = useState<PSEInitResponse | null>(null)
  const [pseBankCode, setPseBankCode] = useState("")
  const [pseLoading, setPseLoading] = useState(false)
  const [pseError, setPseError] = useState("")

  // ── Load data ───────────────────────────────────────────────────────────────

  const loadContracts = useCallback(async () => {
    try {
      const data = await invoiceService.listContracts()
      setContracts(data)
    } finally {
      setLoadingContracts(false)
    }
  }, [])

  useEffect(() => {
    invoiceService.getProviders().then((list) => {
      const real = list.filter((p) => p.real_scraper)
      setProviders(real)
      if (real.length > 0) setSelectedProvider(real[0].id)
    })
    loadContracts()
  }, [loadContracts])

  // ── Add contract ────────────────────────────────────────────────────────────

  function openAdd() {
    setAddError("")
    setNewNumber("")
    setNewAlias("")
    setNewPayerEmail("")
    setShowAdd(true)
  }

  async function handleAdd() {
    if (!selectedProvider) return

    // Movistar identifica el pago por línea (indicativo + 7 dígitos) o por
    // referencia de factura; el resto de proveedores usan el número tal cual.
    const esMovistar = selectedProvider === "movistar"
    const referencia = esMovistar && mvTipo === "1"
      ? `${mvIndicativo}${mvLinea}`
      : newNumber.trim()

    if (esMovistar && mvTipo === "1" && mvLinea.length !== 7) {
      setAddError("El número de línea debe tener 7 dígitos.")
      return
    }
    if (!referencia) return

    setAdding(true)
    setAddError("")
    try {
      const providerInfo = providers.find((p) => p.id === selectedProvider)
      const alias = newAlias.trim() || `${providerInfo?.name ?? selectedProvider.toUpperCase()} ${referencia}`
      await invoiceService.addContract({
        provider: selectedProvider,
        account_reference: referencia,
        name: alias,
        payer_email: newPayerEmail.trim() || undefined,
        payment_identifier: esMovistar ? mvTipo : undefined,
      })
      setNewNumber("")
      setNewAlias("")
      setNewPayerEmail("")
      setMvLinea("")
      setShowAdd(false)
      await loadContracts()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Error al guardar el contrato."
      setAddError(msg)
    } finally {
      setAdding(false)
    }
  }

  // ── Delete contract ─────────────────────────────────────────────────────────

  async function handleDelete(id: number) {
    await invoiceService.removeContract(id)
    setContracts((prev) => prev.filter((c) => c.id !== id))
    setDeleteId(null)
  }

  async function handleSaveEmail() {
    if (!editEmailContract) return

    const esMovistar = editEmailContract.provider === "movistar"
    if (esMovistar && mvTipo === "1" && mvLinea.length !== 7) {
      setEditEmailError("El número de línea debe tener 7 dígitos.")
      return
    }
    if (esMovistar && mvTipo === "2" && !newNumber.trim()) {
      setEditEmailError("Ingresa la referencia de pago.")
      return
    }
    if (!esMovistar && !editEmailValue.trim()) return

    setSavingEmail(true)
    setEditEmailError("")
    try {
      const updated = await invoiceService.updateContract(
        editEmailContract.id,
        esMovistar
          ? {
              account_reference: mvTipo === "1"
                ? `${mvIndicativo}${mvLinea}` : newNumber.trim(),
              payment_identifier: mvTipo,
            }
          : { payer_email: editEmailValue.trim() },
      )
      setContracts((prev) => prev.map((c) => c.id === editEmailContract.id ? { ...c, ...updated } : c))
      setEditEmailContract(null)
    } catch {
      setEditEmailError("Error al guardar. Intenta de nuevo.")
    } finally {
      setSavingEmail(false)
    }
  }

  // ── Fetch invoice ───────────────────────────────────────────────────────────

  async function handleFetch(contract: RecurringService) {
    setFetchStates((prev) => ({
      ...prev,
      [contract.id]: { contractId: contract.id, status: "loading" },
    }))
    setRegisteredFor(null)

    const proveedor = (contract.provider ?? "").trim().toLowerCase()

    // EMCALI exige reCAPTCHA validado en su servidor y su site key no admite
    // otros dominios, así que el desafío se resuelve aquí, retransmitido desde
    // el navegador del backend.
    if (proveedor === "emcali") {
      setEmcaliError("")
      setEmcaliContractId(contract.id)
      try {
        const r = await invoiceService.emcaliStart(contract.id)
        applyEmcali(r, contract.id)
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail ?? "Error al consultar la factura."
        setFetchStates((prev) => ({
          ...prev,
          [contract.id]: { contractId: contract.id, status: "error", errorMsg: msg },
        }))
        setEmcaliContractId(null)
      }
      return
    }

    // GDO: la misma consulta trae factura y bancos, así que vamos directo
    // a elegir banco. Una sola llamada al portal = una sola referencia de pago.
    if (proveedor === "gdo") {
      try {
        const data = await invoiceService.initPseSession(contract.id)
        setFetchStates((prev) => ({
          ...prev,
          [contract.id]: {
            contractId: contract.id, status: "done", isUpToDate: data.is_up_to_date,
          },
        }))
        setContracts((prev) =>
          prev.map((c) =>
            c.id === contract.id
              ? { ...c, last_fetched_amount: data.is_up_to_date ? undefined : data.amount }
              : c
          )
        )
        setActiveContractId(contract.id)

        if (data.is_up_to_date) {
          // Sin saldo pendiente: no hay nada que pagar, mostramos el aviso normal.
          const result = await invoiceService.fetchInvoice(contract.id)
          setActiveResult(result)
          return
        }

        setPseSession(data)
        setPseBankCode("")
        setPseError("")
        setShowPse(true)
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail ?? "Error al consultar la factura."
        setFetchStates((prev) => ({
          ...prev,
          [contract.id]: { contractId: contract.id, status: "error", errorMsg: msg },
        }))
      }
      return
    }

    try {
      const result = await invoiceService.fetchInvoice(contract.id)
      setFetchStates((prev) => ({
        ...prev,
        [contract.id]: { contractId: contract.id, status: "done", result, isUpToDate: result.is_up_to_date },
      }))
      setActiveResult(result)
      setActiveContractId(contract.id)
      setContracts((prev) =>
        prev.map((c) =>
          c.id === contract.id ? { ...c, last_fetched_amount: result.amount } : c
        )
      )
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Error al consultar la factura."
      setFetchStates((prev) => ({
        ...prev,
        [contract.id]: { contractId: contract.id, status: "error", errorMsg: msg },
      }))
    }
  }

  // ── Register payment ────────────────────────────────────────────────────────

  async function handleRegister(result: InvoiceResult, contractId: number) {
    setRegistering(true)
    try {
      await transactionService.create({
        description: `Pago ${result.service_name}`,
        amount: result.amount,
        category: "Servicios",
        type: "gasto",
        date: new Date().toISOString().split("T")[0],
      })
      setRegisteredFor(contractId)
    } finally {
      setRegistering(false)
    }
  }

  // ── EMCALI: desafío reCAPTCHA ───────────────────────────────────────────────

  function applyEmcali(r: EmcaliCaptchaResponse, contractId: number) {
    if (r.estado === "listo" && r.resultado) {
      setEmcali(null)
      setEmcaliContractId(null)
      setFetchStates((prev) => ({
        ...prev,
        [contractId]: {
          contractId, status: "done", result: r.resultado,
          isUpToDate: r.resultado!.is_up_to_date,
        },
      }))
      setContracts((prev) => prev.map((c) => c.id === contractId
        ? { ...c, last_fetched_amount: r.resultado!.is_up_to_date ? undefined : r.resultado!.amount }
        : c))
      setActiveResult(r.resultado)
      setActiveContractId(contractId)
      return
    }
    // "desafio" o "consultando": mantener el modal abierto
    setEmcali(r)
    setFetchStates((prev) => ({
      ...prev,
      [contractId]: { contractId, status: "loading" },
    }))
  }

  async function handleEmcaliClick(ev: React.MouseEvent<HTMLImageElement>) {
    if (!emcali?.session_id || emcaliContractId === null || emcaliBusy) return
    const caja = ev.currentTarget.getBoundingClientRect()
    const x = (ev.clientX - caja.left) / caja.width
    const y = (ev.clientY - caja.top) / caja.height

    setEmcaliBusy(true)
    setEmcaliError("")
    try {
      const r = await invoiceService.emcaliClick(emcaliContractId, emcali.session_id, x, y)
      applyEmcali(r, emcaliContractId)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Error al enviar la verificación."
      setEmcaliError(msg)
    } finally {
      setEmcaliBusy(false)
    }
  }

  // Cuando el captcha ya pasó, EMCALI puede tardar en responder — y si la cuenta
  // está al día resetea el widget, así que no hay nada visible que indique avance.
  // Sondeamos solos para que el usuario no tenga que pulsar "Actualizar".
  useEffect(() => {
    if (emcali?.estado !== "consultando" || !emcali.session_id || emcaliContractId === null) {
      pollsRef.current = 0
      return
    }
    if (pollsRef.current >= 25) return   // ~60 s; más allá, que reintente a mano

    let cancelado = false
    const t = setTimeout(async () => {
      if (cancelado) return
      pollsRef.current += 1
      try {
        const r = await invoiceService.emcaliStatus(emcaliContractId, emcali.session_id!)
        if (!cancelado) applyEmcali(r, emcaliContractId)
      } catch (err: unknown) {
        if (cancelado) return
        const msg = (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail ?? "Se perdió la verificación. Vuelve a consultar."
        setEmcaliError(msg)
      }
    }, 2_500)

    return () => { cancelado = true; clearTimeout(t) }
  }, [emcali, emcaliContractId])

  async function handleEmcaliRefresh() {
    if (!emcali?.session_id || emcaliContractId === null || emcaliBusy) return
    setEmcaliBusy(true)
    setEmcaliError("")
    try {
      const r = await invoiceService.emcaliStatus(emcaliContractId, emcali.session_id)
      applyEmcali(r, emcaliContractId)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Error al consultar el estado."
      setEmcaliError(msg)
    } finally {
      setEmcaliBusy(false)
    }
  }

  function closeEmcali() {
    if (emcali?.session_id && emcaliContractId !== null) {
      invoiceService.emcaliCancel(emcaliContractId, emcali.session_id).catch(() => {})
      setFetchStates((prev) => ({
        ...prev,
        [emcaliContractId]: { contractId: emcaliContractId, status: "idle" },
      }))
    }
    setEmcali(null)
    setEmcaliContractId(null)
    setEmcaliError("")
  }

  // ── PSE: generar link y salir a la pasarela ─────────────────────────────────

  async function handlePsePay() {
    if (!activeContractId || !pseSession || !pseBankCode) return
    setPseLoading(true)
    setPseError("")
    try {
      const result = await invoiceService.psePay(activeContractId, {
        session_id: pseSession.session_id,
        bank_code: pseBankCode,
      })
      // Navegación en la misma pestaña: es lo que hace el portal de GDO y
      // ningún bloqueador de popups la interrumpe.
      window.location.href = result.pse_url
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Error al generar el pago PSE."
      setPseError(msg)
      setPseLoading(false)
    }
  }

  const selectedProviderInfo = providers.find((p) => p.id === selectedProvider)

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-3xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Zap className="w-5 h-5 text-primary" />
            <h1 className="text-2xl font-bold text-foreground">Facturas de Servicios</h1>
          </div>
          <p className="text-muted-foreground text-sm">
            Guarda tu número de contrato. El sistema consulta la factura actual y te muestra
            el valor exacto para que confirmes antes de pagar.
          </p>
        </div>
        <Button onClick={openAdd} size="sm">
          <Plus className="w-4 h-4 mr-1" />
          Agregar contrato
        </Button>
      </div>

      {/* Contracts list */}
      {loadingContracts ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : contracts.length === 0 ? (
        <Card className="bg-card border-border border-dashed">
          <CardContent className="flex flex-col items-center py-14 gap-3">
            <FileText className="w-10 h-10 text-muted-foreground/40" />
            <p className="text-muted-foreground text-sm">No tienes contratos guardados.</p>
            <Button variant="outline" size="sm" onClick={openAdd}>
              <Plus className="w-4 h-4 mr-1" />
              Agregar contrato
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {contracts.map((contract) => {
            const fs = fetchStates[contract.id]
            const isLoading  = fs?.status === "loading"
            const hasError   = fs?.status === "error"
            const isUpToDate = fs?.isUpToDate

            return (
              <Card key={contract.id} className="bg-card border-border">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                        <p className="font-semibold text-foreground truncate">{contract.name}</p>
                        <ProviderBadge provider={contract.provider} providers={providers} />
                        {isUpToDate ? (
                          <Badge className="text-xs shrink-0 bg-primary/10 text-primary border-0">
                            <CheckCircle2 className="w-3 h-3 mr-1" />
                            Al día
                          </Badge>
                        ) : contract.last_fetched_amount != null ? (
                          <Badge variant="secondary" className="text-xs shrink-0">
                            {formatCOP(contract.last_fetched_amount)} última consulta
                          </Badge>
                        ) : null}
                      </div>
                      <p className="text-xs text-muted-foreground font-mono">
                        Contrato: {contract.account_reference}
                      </p>
                      {hasError && (
                        <div className="flex items-start gap-1.5 mt-2 text-destructive text-xs">
                          <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                          <span>{fs.errorMsg}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={() => handleFetch(contract)}
                        disabled={isLoading}
                      >
                        {isLoading ? (
                          <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />Consultando...</>
                        ) : (
                          <><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Consultar factura</>
                        )}
                      </Button>
                      {(contract.provider === "gdo" || contract.provider === "movistar") && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="text-muted-foreground hover:text-foreground"
                          title={contract.provider === "gdo"
                            ? "Editar correo GDO" : "Editar datos de consulta"}
                          onClick={() => {
                            setEditEmailValue(contract.payer_email ?? "")
                            setEditEmailError("")
                            if (contract.provider === "movistar") {
                              const ref = (contract.account_reference ?? "").replace(/\D/g, "")
                              const tipo = contract.payment_identifier ?? "1"
                              setMvTipo(tipo)
                              if (tipo === "1" && ref.length >= 10) {
                                setMvIndicativo(ref.slice(0, 3))
                                setMvLinea(ref.slice(3))
                              } else if (tipo === "1") {
                                // Guardado sin indicativo: se conserva la línea
                                setMvLinea(ref.slice(-7))
                              } else {
                                setNewNumber(ref)
                              }
                            }
                            setEditEmailContract(contract)
                          }}
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={() => setDeleteId(contract.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* How it works note */}
      <div className="flex items-start gap-2 text-xs text-muted-foreground bg-secondary/40 rounded-lg p-3">
        <Info className="w-4 h-4 shrink-0 mt-0.5" />
        <span>
          Al hacer clic en "Consultar factura", el sistema accede automáticamente al portal
          del proveedor con tu número de contrato y extrae el valor de la factura actual.
          Luego te muestra los datos para que confirmes antes de ir a pagar.
        </span>
      </div>

      {/* ── Add contract dialog ── */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Agregar contrato</DialogTitle>
            <DialogDescription>
              Selecciona el proveedor e ingresa tu número de contrato. Lo guardamos para que
              no tengas que escribirlo cada vez.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 pt-1">

            {/* Provider selector */}
            <div className="space-y-2">
              <Label>Proveedor *</Label>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowProviderMenu((v) => !v)}
                  className="w-full flex items-center justify-between rounded-md bg-secondary border-0 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <span>{selectedProviderInfo?.name ?? "Seleccionar proveedor"}</span>
                  <ChevronDown className="w-4 h-4 text-muted-foreground" />
                </button>
                {showProviderMenu && (
                  <div className="absolute z-50 mt-1 w-full rounded-md bg-popover border border-border shadow-lg overflow-hidden">
                    {providers.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => { setSelectedProvider(p.id); setShowProviderMenu(false) }}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-secondary transition-colors ${selectedProvider === p.id ? "font-medium text-foreground" : "text-muted-foreground"}`}
                      >
                        {p.name}
                        <span className="ml-2 text-xs text-muted-foreground/60">{p.category}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {selectedProvider === "movistar" ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Identificador de pago *</Label>
                  <div className="relative">
                    <select
                      className="w-full rounded-md bg-secondary border-0 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring appearance-none pr-8"
                      value={mvTipo}
                      onChange={(e) => setMvTipo(e.target.value)}
                    >
                      <option value="1">Con número de línea</option>
                      <option value="2">Con referencia de pago</option>
                    </select>
                    <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  </div>
                </div>

                {mvTipo === "1" ? (
                  <div className="grid grid-cols-3 gap-2">
                    <div className="space-y-2">
                      <Label>Ciudad *</Label>
                      <div className="relative">
                        <select
                          className="w-full rounded-md bg-secondary border-0 px-2 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring appearance-none"
                          value={mvIndicativo}
                          onChange={(e) => setMvIndicativo(e.target.value)}
                        >
                          {CIUDADES_MOVISTAR.map(([ind, nombre]) => (
                            <option key={ind} value={ind}>{nombre}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div className="col-span-2 space-y-2">
                      <Label>N° de línea *</Label>
                      <Input
                        className="bg-secondary border-0 font-mono"
                        inputMode="numeric"
                        placeholder="7 dígitos"
                        value={mvLinea}
                        maxLength={7}
                        onChange={(e) => setMvLinea(e.target.value.replace(/\D/g, ""))}
                        onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label>Referencia de pago *</Label>
                    <Input
                      className="bg-secondary border-0 font-mono"
                      inputMode="numeric"
                      placeholder="Número de referencia"
                      value={newNumber}
                      maxLength={11}
                      onChange={(e) => setNewNumber(e.target.value.replace(/\D/g, ""))}
                      onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                    />
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  {mvTipo === "1"
                    ? `Se consultará como ${mvIndicativo}${mvLinea || "·······"}, igual que en el portal de Movistar.`
                    : "La referencia que aparece en tu factura de Movistar."}
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Label>Número de contrato / suscripción *</Label>
                <Input
                  className="bg-secondary border-0 font-mono"
                  placeholder="Ej: 1234567890"
                  value={newNumber}
                  onChange={(e) => setNewNumber(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label>Alias (opcional)</Label>
              <Input
                className="bg-secondary border-0"
                placeholder="Ej: Casa principal, Apartamento"
                value={newAlias}
                onChange={(e) => setNewAlias(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              />
            </div>

            {selectedProvider === "gdo" && (
              <div className="space-y-2">
                <Label>Correo registrado en GDO *</Label>
                <Input
                  className="bg-secondary border-0"
                  type="email"
                  placeholder="correo@ejemplo.com"
                  value={newPayerEmail}
                  onChange={(e) => setNewPayerEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                />
                <p className="text-xs text-muted-foreground">
                  El correo del <span className="font-medium text-foreground">titular de este
                  contrato</span> en GDO. Si el contrato está a nombre de otra persona, va el
                  correo de esa persona, no el tuyo.
                </p>
              </div>
            )}

            {addError && (
              <div className="flex items-center gap-2 text-destructive text-sm">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {addError}
              </div>
            )}
            <Button
              className="w-full"
              onClick={handleAdd}
              disabled={
                !selectedProvider || adding ||
                (selectedProvider === "movistar"
                  ? (mvTipo === "1" ? mvLinea.length !== 7 : !newNumber.trim())
                  : !newNumber.trim()) ||
                (selectedProvider === "gdo" && !newPayerEmail.trim())
              }
            >
              {adding
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Guardando...</>
                : <><Plus className="w-4 h-4 mr-2" />Guardar contrato</>}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Invoice result dialog ── */}
      <Dialog
        open={activeResult !== null && !showQr}
        onOpenChange={(open) => { if (!open) { setActiveResult(null); setActiveContractId(null) } }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              Factura — {activeResult?.service_name}
              {activeResult?.is_demo && (
                <Badge variant="secondary" className="text-xs font-normal">datos de ejemplo</Badge>
              )}
            </DialogTitle>
            <DialogDescription>
              Revisa los datos antes de proceder al pago.
            </DialogDescription>
          </DialogHeader>

          {activeResult && (
            activeResult.portal_blocked ? (
              /* ── Portal bloqueó acceso automático ── */
              (() => {
                const reason = activeResult.blocked_reason ?? ""
                const r = reason.toLowerCase()
                const isProfileIncomplete = r.includes("perfil incompleto")
                const isWAF               = r.includes("akamai") || r.includes("waf del proveedor") || r.includes("cloudflare")
                const isStep1             = r.startsWith("paso 1")
                const isStep2             = r.startsWith("paso 2")
                const isStep3             = r.startsWith("paso 3")
                const stepLabel = isStep1 ? "Paso 1 · Contrato"
                               : isStep2 ? "Paso 2 · Datos personales"
                               : isStep3 ? "Paso 3 · Monto de factura"
                               : null

                return (
                  <div className="flex flex-col items-center py-5 gap-4 text-center">
                    <div className="w-14 h-14 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                      {isProfileIncomplete
                        ? <Settings className="w-7 h-7 text-amber-600 dark:text-amber-400" />
                        : <ShieldAlert className="w-7 h-7 text-amber-600 dark:text-amber-400" />}
                    </div>

                    <div className="space-y-1 max-w-sm mx-auto">
                      <p className="text-base font-bold text-foreground">
                        {isProfileIncomplete ? "Datos de perfil incompletos"
                         : isWAF             ? "Portal bloqueado por seguridad de red"
                         : "Consulta automática falló"}
                      </p>

                      {isWAF ? (
                        <p className="text-sm text-muted-foreground mt-1">
                          El portal de <span className="font-medium">{activeResult.service_name}</span> bloqueó
                          el acceso desde servidores externos. Debes pagar directamente en su portal.
                        </p>
                      ) : isProfileIncomplete ? (
                        <p className="text-sm text-muted-foreground mt-1">
                          Completa tu cédula y teléfono en Configuración para consultar esta factura.
                        </p>
                      ) : (
                        <>
                          {stepLabel && (
                            <p className="text-xs font-medium text-amber-600 dark:text-amber-400">
                              Falló en: {stepLabel}
                            </p>
                          )}
                          <p className="text-sm text-muted-foreground mt-1">
                            {reason || `El portal de ${activeResult.service_name} no permitió la consulta automática.`}
                          </p>
                        </>
                      )}
                    </div>

                    <div className="flex flex-col gap-2 w-full max-w-xs">
                      {isProfileIncomplete && (
                        <Button className="w-full" onClick={() => {
                          setActiveResult(null)
                          router.push("/dashboard/configuracion")
                        }}>
                          <Settings className="w-4 h-4 mr-2" />
                          Ir a Configuración
                        </Button>
                      )}
                      <Button
                        variant={isProfileIncomplete ? "outline" : "default"}
                        className="w-full"
                        asChild
                      >
                        <a href={activeResult.payment_url} target="_blank" rel="noopener noreferrer">
                          <ExternalLink className="w-4 h-4 mr-2" />
                          Ir al portal de pago
                        </a>
                      </Button>
                    </div>
                  </div>
                )
              })()
            ) : activeResult.is_up_to_date ? (
              /* ── Al día ── */
              <div className="flex flex-col items-center py-6 gap-4 text-center">
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <PartyPopper className="w-8 h-8 text-primary" />
                </div>
                <div>
                  <p className="text-lg font-bold text-foreground">¡Estás al día!</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    No se encontraron facturas pendientes para <span className="font-medium">{activeResult.service_name}</span>.
                    No tienes ningún saldo por pagar en este momento.
                  </p>
                </div>
                {activeResult.payment_url && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={activeResult.payment_url} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="w-4 h-4 mr-2" />
                      Ver portal del proveedor
                    </a>
                  </Button>
                )}
              </div>
            ) : (
              /* ── Factura con saldo ── */
              <div className="space-y-5 pt-1">
                {/* Data cards */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 rounded-xl bg-secondary/60 space-y-1">
                    <div className="flex items-center gap-1.5 text-muted-foreground text-xs">
                      <DollarSign className="w-3.5 h-3.5" />
                      Valor a pagar
                    </div>
                    <p className="text-2xl font-bold text-foreground">
                      {formatCOP(activeResult.amount)}
                    </p>
                  </div>
                  <div className="p-4 rounded-xl bg-secondary/60 space-y-1">
                    <div className="flex items-center gap-1.5 text-muted-foreground text-xs">
                      <CalendarClock className="w-3.5 h-3.5" />
                      Fecha límite
                    </div>
                    <p className="text-base font-semibold text-foreground">
                      {String(activeResult.due_date)}
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-secondary/60">
                  <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-1">
                    <Hash className="w-3.5 h-3.5" />
                    Referencia de pago
                  </div>
                  <div className="flex items-center gap-1">
                    <p className="text-sm font-mono text-foreground break-all">
                      {activeResult.reference}
                    </p>
                    <CopyButton text={activeResult.reference} />
                  </div>
                </div>

                <Separator />

                {/* Actions */}
                <div className="space-y-2">
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
                    ¿Cómo deseas pagar?
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      variant="outline"
                      className="h-auto flex-col py-3 gap-1"
                      onClick={() => setShowQr(true)}
                    >
                      <QrCode className="w-5 h-5" />
                      <span className="text-xs">QR para app bancaria</span>
                    </Button>
                    {activeResult.payment_url && (
                      <Button
                        variant="outline"
                        className="h-auto flex-col py-3 gap-1"
                        asChild
                      >
                        <a href={activeResult.payment_url} target="_blank" rel="noopener noreferrer">
                          <ExternalLink className="w-5 h-5" />
                          <span className="text-xs">Portal del proveedor</span>
                        </a>
                      </Button>
                    )}
                  </div>
                </div>

                <Separator />

                {/* Register payment */}
                {registeredFor === activeContractId ? (
                  <div className="flex items-center gap-2 text-primary text-sm justify-center">
                    <CheckCircle2 className="w-4 h-4" />
                    Pago registrado como transacción
                  </div>
                ) : (
                  <Button
                    variant="ghost"
                    className="w-full text-muted-foreground"
                    onClick={() => activeContractId !== null && handleRegister(activeResult, activeContractId)}
                    disabled={registering}
                  >
                    {registering
                      ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Registrando...</>
                      : "Registrar como pago en mis transacciones"}
                  </Button>
                )}
              </div>
            )
          )}
        </DialogContent>
      </Dialog>

      {/* ── QR dialog ── */}
      <Dialog open={showQr} onOpenChange={(open) => { if (!open) setShowQr(false) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>QR de pago — {activeResult?.service_name}</DialogTitle>
            <DialogDescription>
              Escanea este código con tu app bancaria para pagar.
            </DialogDescription>
          </DialogHeader>
          {activeResult && (
            <div className="flex flex-col items-center gap-4 py-2">
              <img
                src={`data:image/png;base64,${activeResult.qr_base64}`}
                alt="QR de pago"
                className="w-56 h-56 rounded-lg border border-border bg-white"
              />
              <div className="text-center space-y-1 w-full">
                <p className="text-2xl font-bold">{formatCOP(activeResult.amount)}</p>
                <p className="text-sm text-muted-foreground">Vence: {String(activeResult.due_date)}</p>
                <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground font-mono">
                  <span className="truncate max-w-[200px]">{activeResult.reference}</span>
                  <CopyButton text={activeResult.reference} />
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => setShowQr(false)}
              >
                Volver a opciones de pago
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Edit GDO credentials ── */}
      <Dialog open={editEmailContract !== null} onOpenChange={(o) => { if (!o) setEditEmailContract(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {editEmailContract?.provider === "movistar"
                ? "Datos de consulta Movistar" : "Correo de verificación GDO"}
            </DialogTitle>
            <DialogDescription>
              {editEmailContract?.provider === "movistar"
                ? "Cómo identifica Movistar este servicio al consultar la factura."
                : "GDO valida la consulta contra el correo del titular de este contrato."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 pt-1">
            {editEmailContract?.provider === "movistar" ? (
              <>
                <div className="space-y-2">
                  <Label>Identificador de pago *</Label>
                  <div className="relative">
                    <select
                      className="w-full rounded-md bg-secondary border-0 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring appearance-none pr-8"
                      value={mvTipo}
                      onChange={(e) => setMvTipo(e.target.value)}
                    >
                      <option value="1">Con número de línea</option>
                      <option value="2">Con referencia de pago</option>
                    </select>
                    <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  </div>
                </div>
                {mvTipo === "1" ? (
                  <div className="grid grid-cols-3 gap-2">
                    <div className="space-y-2">
                      <Label>Ciudad *</Label>
                      <select
                        className="w-full rounded-md bg-secondary border-0 px-2 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring appearance-none"
                        value={mvIndicativo}
                        onChange={(e) => setMvIndicativo(e.target.value)}
                      >
                        {CIUDADES_MOVISTAR.map(([ind, nombre]) => (
                          <option key={ind} value={ind}>{nombre}</option>
                        ))}
                      </select>
                    </div>
                    <div className="col-span-2 space-y-2">
                      <Label>N° de línea *</Label>
                      <Input
                        className="bg-secondary border-0 font-mono"
                        inputMode="numeric"
                        placeholder="7 dígitos"
                        maxLength={7}
                        value={mvLinea}
                        onChange={(e) => setMvLinea(e.target.value.replace(/\D/g, ""))}
                        onKeyDown={(e) => e.key === "Enter" && handleSaveEmail()}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label>Referencia de pago *</Label>
                    <Input
                      className="bg-secondary border-0 font-mono"
                      inputMode="numeric"
                      placeholder="Número de referencia"
                      maxLength={11}
                      value={newNumber}
                      onChange={(e) => setNewNumber(e.target.value.replace(/\D/g, ""))}
                      onKeyDown={(e) => e.key === "Enter" && handleSaveEmail()}
                    />
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  {mvTipo === "1"
                    ? `Se consultará como ${mvIndicativo}${mvLinea || "·······"}.`
                    : "La referencia que aparece en tu factura."}
                </p>
              </>
            ) : (
              <div className="space-y-2">
                <Label>Correo registrado en GDO *</Label>
                <Input
                  className="bg-secondary border-0"
                  type="email"
                  placeholder="correo@ejemplo.com"
                  value={editEmailValue}
                  onChange={(e) => setEditEmailValue(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSaveEmail()}
                />
                <p className="text-xs text-muted-foreground">
                  Si el contrato está a nombre de otra persona, va el correo de esa
                  persona, no el de tu cuenta FinSmart.
                </p>
              </div>
            )}
            {editEmailError && (
              <div className="flex items-center gap-2 text-destructive text-sm">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {editEmailError}
              </div>
            )}
            <Button
              className="w-full"
              onClick={handleSaveEmail}
              disabled={savingEmail || (editEmailContract?.provider === "movistar"
                ? (mvTipo === "1" ? mvLinea.length !== 7 : !newNumber.trim())
                : !editEmailValue.trim())}
            >
              {savingEmail
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Guardando...</>
                : "Guardar"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── EMCALI: desafío reCAPTCHA ── */}
      <Dialog open={emcali !== null} onOpenChange={(o) => { if (!o) closeEmcali() }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-primary" />
              Verificación de EMCALI
            </DialogTitle>
            <DialogDescription>
              EMCALI exige resolver un reCAPTCHA para consultar la factura y solo
              lo acepta desde su propio sitio. Resuélvelo aquí y seguimos con la consulta.
            </DialogDescription>
          </DialogHeader>

          {emcali?.estado === "desafio" && emcali.imagen ? (
            <div className="space-y-3">
              <div className="relative flex justify-center">
                <img
                  src={`data:image/png;base64,${emcali.imagen}`}
                  alt="Desafío de verificación"
                  onClick={handleEmcaliClick}
                  className={`rounded-lg border border-border select-none max-w-full ${
                    emcaliBusy ? "opacity-50 cursor-wait" : "cursor-pointer"
                  }`}
                  draggable={false}
                />
                {emcaliBusy && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Loader2 className="w-6 h-6 animate-spin text-primary" />
                  </div>
                )}
              </div>
              <p className="text-xs text-muted-foreground text-center">
                Haz clic en las imágenes que pide y luego en VERIFICAR, como en el portal.
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-8">
              <Loader2 className="w-7 h-7 animate-spin text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Verificación superada. Consultando tu factura...
              </p>
            </div>
          )}

          {emcaliError && (
            <div className="flex items-start gap-1.5 text-destructive text-xs">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              {emcaliError}
            </div>
          )}

          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              onClick={handleEmcaliRefresh}
              disabled={emcaliBusy}
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
              Actualizar
            </Button>
            <Button variant="ghost" size="sm" className="flex-1" onClick={closeEmcali}>
              Cancelar
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── PSE Payment modal ── */}
      <Dialog open={showPse} onOpenChange={(open) => {
        if (!open) {
          setShowPse(false)
          setPseError("")
          setPseSession(null)
        }
      }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-primary" />
              Pago con PSE
            </DialogTitle>
            <DialogDescription>
              Revisa los datos de tu factura y elige el banco con el que vas a pagar.
            </DialogDescription>
          </DialogHeader>

          {pseSession && (
            <div className="space-y-4 pt-1">
              {/* Resumen de factura */}
              <div className="rounded-xl bg-secondary/60 p-3 space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Valor a pagar</span>
                  <span className="font-bold text-foreground">{formatCOP(pseSession.amount)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Vence</span>
                  <span className="font-mono text-foreground">{pseSession.due_date}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Referencia</span>
                  <span className="font-mono text-foreground truncate max-w-[140px]">{pseSession.reference}</span>
                </div>
              </div>

              {/* Bank selection */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5" />
                  Banco
                </Label>
                <div className="relative">
                  <select
                    className="w-full rounded-md bg-secondary border-0 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring appearance-none pr-8"
                    value={pseBankCode}
                    onChange={(e) => setPseBankCode(e.target.value)}
                  >
                    <option value="">Selecciona tu banco</option>
                    {pseSession.banks.map((b: PSEBank) => (
                      <option key={b.code} value={b.code}>{b.name}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Error */}
              {pseError && (
                <div className="flex items-start gap-1.5 text-destructive text-xs">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  {pseError}
                </div>
              )}

              {/* Pay */}
              <Button
                className="w-full"
                onClick={handlePsePay}
                disabled={!pseBankCode || pseLoading}
              >
                {pseLoading
                  ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Llevándote al pago...</>
                  : <><CreditCard className="w-4 h-4 mr-2" />Pagar {formatCOP(pseSession.amount)}</>}
              </Button>
              <p className="text-[11px] text-muted-foreground text-center">
                Te llevamos a la pasarela de tu banco para completar el pago.
              </p>
            </div>
          )}

          {!pseSession && (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Delete confirmation ── */}
      <AlertDialog open={deleteId !== null} onOpenChange={(o) => { if (!o) setDeleteId(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar contrato?</AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminará el contrato guardado. No se borran tus transacciones.
              Puedes volver a agregarlo cuando quieras.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => deleteId !== null && handleDelete(deleteId)}
            >
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

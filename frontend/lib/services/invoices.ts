import api from "@/lib/api"
import type {
  ProviderInfo, InvoiceLookupRequest, InvoiceLookupResult,
  RecurringService, InvoiceResult, PSEInitResponse, PSEPayRequest, PSEPayResponse,
  EmcaliCaptchaResponse, MovistarPollStart, MovistarInitStatus, MovistarPayStatus,
} from "@/lib/types"

export const invoiceService = {
  async getProviders(): Promise<ProviderInfo[]> {
    const r = await api.get<ProviderInfo[]>("/invoices/providers")
    return r.data
  },

  async listContracts(provider?: string): Promise<RecurringService[]> {
    const r = await api.get<RecurringService[]>("/invoices/contracts", {
      params: provider ? { provider } : undefined,
    })
    return r.data
  },

  async addContract(data: {
    provider: string
    account_reference: string
    name: string
    payer_name?: string
    payer_id_type?: string
    payer_id_number?: string
    payer_phone?: string
    payer_email?: string
    payment_identifier?: string
  }): Promise<RecurringService> {
    const r = await api.post<RecurringService>("/invoices/contracts", {
      name: data.name,
      provider: data.provider,
      account_reference: data.account_reference,
      category: "Servicios Públicos",
      estimated_amount: 0,
      billing_day: 15,
      payer_name:      data.payer_name      || undefined,
      payer_id_type:   data.payer_id_type   || undefined,
      payer_id_number: data.payer_id_number || undefined,
      payer_phone:     data.payer_phone     || undefined,
      payer_email:     data.payer_email     || undefined,
      payment_identifier: data.payment_identifier || undefined,
    })
    return r.data
  },

  async updateContract(id: number, data: Partial<{
    payer_email: string
    payer_name: string
    payer_phone: string
    payer_id_type: string
    payer_id_number: string
    name: string
    account_reference: string
    payment_identifier: string
  }>): Promise<RecurringService> {
    const r = await api.patch<RecurringService>(`/invoices/contracts/${id}`, data)
    return r.data
  },

  async removeContract(id: number): Promise<void> {
    await api.delete(`/invoices/contracts/${id}`)
  },

  async fetchInvoice(contractId: number): Promise<InvoiceResult> {
    const r = await api.post<InvoiceResult>(`/invoices/contracts/${contractId}/fetch`)
    return r.data
  },

  async lookup(data: InvoiceLookupRequest): Promise<InvoiceLookupResult> {
    const r = await api.post<InvoiceLookupResult>("/invoices/lookup", data)
    return r.data
  },

  async initPseSession(contractId: number): Promise<PSEInitResponse> {
    const r = await api.post<PSEInitResponse>(`/invoices/contracts/${contractId}/pse-init`)
    return r.data
  },

  async psePay(contractId: number, data: PSEPayRequest): Promise<PSEPayResponse> {
    const r = await api.post<PSEPayResponse>(`/invoices/contracts/${contractId}/pse-pay`, data)
    return r.data
  },

  // El flujo real puede tardar más de un minuto (con reintentos si el
  // portal rechaza la consulta), así que arranca en segundo plano y el
  // resultado se obtiene sondeando *-status — una sola conexión larga se
  // estaba cortando de forma intermitente sobre redes lentas/túneles.
  async movistarPseInit(contractId: number): Promise<MovistarPollStart> {
    const r = await api.post<MovistarPollStart>(`/invoices/contracts/${contractId}/movistar-pse-init`)
    return r.data
  },

  async movistarPseInitStatus(contractId: number, pollId: string): Promise<MovistarInitStatus> {
    const r = await api.post<MovistarInitStatus>(
      `/invoices/contracts/${contractId}/movistar-pse-init-status`, { poll_id: pollId })
    return r.data
  },

  async movistarPsePay(contractId: number, data: PSEPayRequest): Promise<MovistarPollStart> {
    const r = await api.post<MovistarPollStart>(`/invoices/contracts/${contractId}/movistar-pse-pay`, data)
    return r.data
  },

  async movistarPsePayStatus(contractId: number, pollId: string): Promise<MovistarPayStatus> {
    const r = await api.post<MovistarPayStatus>(
      `/invoices/contracts/${contractId}/movistar-pse-pay-status`, { poll_id: pollId })
    return r.data
  },

  async emcaliStart(contractId: number): Promise<EmcaliCaptchaResponse> {
    const r = await api.post<EmcaliCaptchaResponse>(
      `/invoices/contracts/${contractId}/emcali-start`, undefined, { timeout: 180_000 })
    return r.data
  },

  async emcaliClick(contractId: number, session_id: string, x: number, y: number)
    : Promise<EmcaliCaptchaResponse> {
    const r = await api.post<EmcaliCaptchaResponse>(
      `/invoices/contracts/${contractId}/emcali-click`, { session_id, x, y },
      { timeout: 120_000 })
    return r.data
  },

  async emcaliStatus(contractId: number, session_id: string): Promise<EmcaliCaptchaResponse> {
    const r = await api.post<EmcaliCaptchaResponse>(
      `/invoices/contracts/${contractId}/emcali-status`, { session_id }, { timeout: 120_000 })
    return r.data
  },

  async emcaliCancel(contractId: number, session_id: string): Promise<void> {
    await api.post(`/invoices/contracts/${contractId}/emcali-cancel`, { session_id })
  },
}

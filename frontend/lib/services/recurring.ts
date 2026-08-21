import api from "@/lib/api"
import type {
  RecurringService,
  RecurringCreate,
  RecurringUpdate,
  InvoiceResult,
  PatternResult,
} from "@/lib/types"

export const recurringService = {
  async list(): Promise<RecurringService[]> {
    try {
      const response = await api.get<RecurringService[]>("/recurring")
      return response.data
    } catch (error) {
      throw error
    }
  },

  async create(data: RecurringCreate): Promise<RecurringService> {
    try {
      const response = await api.post<RecurringService>("/recurring", data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async update(id: number, data: RecurringUpdate): Promise<RecurringService> {
    try {
      const response = await api.put<RecurringService>(`/recurring/${id}`, data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async remove(id: number): Promise<void> {
    try {
      await api.delete(`/recurring/${id}`)
    } catch (error) {
      throw error
    }
  },

  async fetchInvoice(id: number): Promise<InvoiceResult> {
    try {
      const response = await api.post<InvoiceResult>(
        `/recurring/${id}/fetch-invoice`
      )
      return response.data
    } catch (error) {
      throw error
    }
  },

  async getPatterns(): Promise<PatternResult[]> {
    try {
      const response = await api.get<PatternResult[]>("/recurring/patterns")
      return response.data
    } catch (error) {
      throw error
    }
  },
}

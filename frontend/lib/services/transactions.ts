import api from "@/lib/api"
import type {
  Transaction,
  TransactionCreate,
  TransactionUpdate,
  TransactionSummary,
  MonthlyPoint,
  TrendResult,
  MLSuggestion,
  MLMetrics,
  AnomalyScore,
} from "@/lib/types"

export const transactionService = {
  async list(params?: {
    category?: string
    type?: string
    start_date?: string
    end_date?: string
    skip?: number
    limit?: number
  }): Promise<Transaction[]> {
    try {
      const response = await api.get<Transaction[]>("/transactions", { params })
      return response.data
    } catch (error) {
      throw error
    }
  },

  async create(data: TransactionCreate): Promise<Transaction> {
    try {
      const response = await api.post<Transaction>("/transactions", data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async update(id: number, data: TransactionUpdate): Promise<Transaction> {
    try {
      const response = await api.put<Transaction>(`/transactions/${id}`, data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async remove(id: number): Promise<void> {
    try {
      await api.delete(`/transactions/${id}`)
    } catch (error) {
      throw error
    }
  },

  async summary(): Promise<TransactionSummary> {
    const response = await api.get<TransactionSummary>("/transactions/summary")
    return response.data
  },

  async monthly(): Promise<MonthlyPoint[]> {
    const response = await api.get<MonthlyPoint[]>("/transactions/monthly")
    return response.data
  },

  async trends(): Promise<TrendResult[]> {
    const response = await api.get<TrendResult[]>("/transactions/trends")
    return response.data
  },

  async mlTrain(): Promise<MLMetrics> {
    const response = await api.post<MLMetrics>("/transactions/ml/train")
    return response.data
  },

  async mlSuggest(description: string): Promise<MLSuggestion> {
    const response = await api.get<MLSuggestion>("/transactions/ml/suggest", { params: { description } })
    return response.data
  },

  async mlMetrics(): Promise<MLMetrics> {
    const response = await api.get<MLMetrics>("/transactions/ml/metrics")
    return response.data
  },

  async mlAnomalies(): Promise<AnomalyScore[]> {
    const response = await api.get<AnomalyScore[]>("/transactions/ml/anomalies")
    return response.data
  },
}

import api from "@/lib/api"
import type { Budget, BudgetCreate, BudgetUpdate } from "@/lib/types"

export const budgetService = {
  async list(): Promise<Budget[]> {
    try {
      const response = await api.get<Budget[]>("/budgets")
      return response.data
    } catch (error) {
      throw error
    }
  },

  async create(data: BudgetCreate): Promise<Budget> {
    try {
      const response = await api.post<Budget>("/budgets", data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async update(id: number, data: BudgetUpdate): Promise<Budget> {
    try {
      const response = await api.put<Budget>(`/budgets/${id}`, data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async remove(id: number): Promise<void> {
    try {
      await api.delete(`/budgets/${id}`)
    } catch (error) {
      throw error
    }
  },
}

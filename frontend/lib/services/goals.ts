import api from "@/lib/api"
import type {
  SavingGoal,
  GoalCreate,
  GoalUpdate,
  Contribution,
  ContributionCreate,
} from "@/lib/types"

export const goalService = {
  async list(): Promise<SavingGoal[]> {
    try {
      const response = await api.get<SavingGoal[]>("/goals")
      return response.data
    } catch (error) {
      throw error
    }
  },

  async create(data: GoalCreate): Promise<SavingGoal> {
    try {
      const response = await api.post<SavingGoal>("/goals", data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async update(id: number, data: GoalUpdate): Promise<SavingGoal> {
    try {
      const response = await api.put<SavingGoal>(`/goals/${id}`, data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async remove(id: number): Promise<void> {
    try {
      await api.delete(`/goals/${id}`)
    } catch (error) {
      throw error
    }
  },

  async contribute(id: number, data: ContributionCreate): Promise<Contribution> {
    try {
      const response = await api.post<Contribution>(
        `/goals/${id}/contribute`,
        data
      )
      return response.data
    } catch (error) {
      throw error
    }
  },

  async contributions(id: number): Promise<Contribution[]> {
    try {
      const response = await api.get<Contribution[]>(
        `/goals/${id}/contributions`
      )
      return response.data
    } catch (error) {
      throw error
    }
  },
}

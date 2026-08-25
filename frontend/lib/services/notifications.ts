import api from "@/lib/api"
import type { AppNotification } from "@/lib/types"

export const notificationService = {
  async list(): Promise<AppNotification[]> {
    const response = await api.get<AppNotification[]>("/notifications")
    return response.data
  },

  async accept(id: number): Promise<void> {
    await api.post(`/notifications/${id}/accept`)
  },

  async reject(id: number): Promise<void> {
    await api.post(`/notifications/${id}/reject`)
  },
}

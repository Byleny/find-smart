import api from "@/lib/api"
import type { User, AuthResponse, UserProfileUpdate } from "@/lib/types"

export const authService = {
  async register(
    email: string,
    password: string,
    full_name: string
  ): Promise<{ access_token: string; user: User }> {
    try {
      const response = await api.post<{ access_token: string; user: User }>(
        "/auth/register",
        { email, password, full_name }
      )
      return response.data
    } catch (error) {
      throw error
    }
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    try {
      const params = new URLSearchParams()
      params.append("username", email)
      params.append("password", password)

      const response = await api.post<AuthResponse>("/auth/login", params, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      })
      return response.data
    } catch (error) {
      throw error
    }
  },

  async me(): Promise<User> {
    try {
      const response = await api.get<User>("/auth/me")
      return response.data
    } catch (error) {
      throw error
    }
  },

  async updateProfile(data: UserProfileUpdate): Promise<User> {
    const response = await api.put<User>("/auth/me", data)
    return response.data
  },

  async deleteAccount(password: string): Promise<void> {
    await api.delete("/auth/me", { data: { password } })
  },

  logout(): void {
    if (typeof window !== "undefined") {
      localStorage.removeItem("finsmart_token")
      document.cookie =
        "finsmart_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT"
      window.location.href = "/login"
    }
  },
}

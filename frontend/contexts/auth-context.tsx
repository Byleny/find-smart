"use client"

import { createContext, useContext, useState, useEffect, ReactNode } from "react"
import { useRouter } from "next/navigation"
import { authService } from "@/lib/services/auth"
import type { User } from "@/lib/types"

interface AuthContextType {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const router = useRouter()

  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("finsmart_token")
        : null

    if (!token) {
      setIsLoading(false)
      return
    }

    authService
      .me()
      .then((u) => setUser(u))
      .catch(() => {
        localStorage.removeItem("finsmart_token")
        document.cookie =
          "finsmart_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT"
      })
      .finally(() => setIsLoading(false))
  }, [])

  async function login(email: string, password: string): Promise<void> {
    const { access_token } = await authService.login(email, password)
    localStorage.setItem("finsmart_token", access_token)
    document.cookie = `finsmart_token=${access_token}; path=/`
    const u = await authService.me()
    setUser(u)
    router.push("/dashboard")
  }

  async function register(
    email: string,
    password: string,
    fullName: string
  ): Promise<void> {
    const { access_token } = await authService.register(
      email,
      password,
      fullName
    )
    localStorage.setItem("finsmart_token", access_token)
    document.cookie = `finsmart_token=${access_token}; path=/`
    const u = await authService.me()
    setUser(u)
    router.push("/dashboard")
  }

  function logout(): void {
    localStorage.removeItem("finsmart_token")
    document.cookie =
      "finsmart_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT"
    setUser(null)
    router.push("/login")
  }

  async function refreshUser(): Promise<void> {
    const u = await authService.me()
    setUser(u)
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthProvider")
  return ctx
}

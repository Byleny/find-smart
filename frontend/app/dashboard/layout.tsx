"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Wallet,
  LayoutDashboard,
  Receipt,
  PieChart,
  Target,
  RefreshCw,
  Users,
  FileText,
  Settings,
  LogOut,
  Bell,
  Search,
  Menu,
  X
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useState } from "react"
import { cn } from "@/lib/utils"
import { useAuth } from "@/contexts/auth-context"

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Transacciones", href: "/dashboard/transacciones", icon: Receipt },
  { name: "Presupuestos", href: "/dashboard/presupuestos", icon: PieChart },
  { name: "Metas de Ahorro", href: "/dashboard/metas", icon: Target },
  { name: "Recurrentes", href: "/dashboard/recurrentes", icon: RefreshCw },
  { name: "Facturas", href: "/dashboard/facturas", icon: FileText },
  { name: "Compartidos", href: "/dashboard/compartidos", icon: Users },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuth()

  const initials = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase()
    : "??"

  return (
    <div className="min-h-screen bg-background">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-foreground/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={cn(
        "fixed top-0 left-0 z-50 h-full w-64 transform transition-transform duration-200 ease-in-out lg:translate-x-0",
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      )} style={{ backgroundColor: "#0F1117", borderRight: "1px solid rgba(255,255,255,0.07)" }}>
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-6 py-5" style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
            <Link href="/dashboard" className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "rgba(255,255,255,0.1)" }}>
                <Wallet className="w-4.5 h-4.5" style={{ color: "rgba(255,255,255,0.85)" }} />
              </div>
              <span className="text-xl font-black text-white tracking-tight">FinSmart</span>
            </Link>
            <button onClick={() => setSidebarOpen(false)} className="lg:hidden" style={{ color: "rgba(255,255,255,0.4)" }}>
              <X className="w-5 h-5" />
            </button>
          </div>

          <nav className="flex-1 px-3 py-5 space-y-0.5 overflow-y-auto">
            {navigation.map((item) => {
              const isActive = pathname === item.href
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
                  style={{
                    backgroundColor: isActive ? "rgba(255,255,255,0.1)" : "transparent",
                    color: isActive ? "#ffffff" : "rgba(255,255,255,0.45)",
                  }}
                  onMouseEnter={e => { if (!isActive) { (e.currentTarget as HTMLElement).style.backgroundColor = "rgba(255,255,255,0.06)"; (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.8)" }}}
                  onMouseLeave={e => { if (!isActive) { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.45)" }}}
                >
                  <item.icon className="w-4.5 h-4.5 flex-shrink-0" />
                  {item.name}
                </Link>
              )
            })}
          </nav>

          <div className="p-3" style={{ borderTop: "1px solid rgba(255,255,255,0.07)" }}>
            <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg" style={{ backgroundColor: "rgba(255,255,255,0.04)" }}>
              <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: "rgba(255,255,255,0.1)" }}>
                <span className="text-sm font-semibold text-white">{initials}</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-white truncate">{user?.full_name ?? "—"}</p>
                <p className="text-xs truncate" style={{ color: "rgba(255,255,255,0.38)" }}>{user?.email ?? ""}</p>
              </div>
            </div>
            <div className="mt-2 space-y-0.5">
              <Link
                href="/dashboard/configuracion"
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-lg transition-all"
                style={{ color: "rgba(255,255,255,0.4)" }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "rgba(255,255,255,0.06)"; (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.8)" }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.4)" }}
              >
                <Settings className="w-4 h-4" />
                Configuración
              </Link>
              <button
                onClick={logout}
                className="w-full flex items-center gap-3 px-3 py-2 text-sm rounded-lg transition-all"
                style={{ color: "rgba(255,255,255,0.4)" }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "rgba(255,255,255,0.06)"; (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.8)" }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.4)" }}
              >
                <LogOut className="w-4 h-4" />
                Cerrar Sesión
              </button>
            </div>
          </div>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 bg-background/95 backdrop-blur border-b border-border">
          <div className="flex items-center justify-between px-6 py-4">
            <div className="flex items-center gap-4">
              <button onClick={() => setSidebarOpen(true)} className="lg:hidden text-muted-foreground hover:text-foreground">
                <Menu className="w-6 h-6" />
              </button>
              <div className="relative hidden md:block">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input placeholder="Buscar transacciones..." className="pl-10 w-64 h-9 bg-secondary border-0" />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon" className="relative">
                <Bell className="w-5 h-5" />
                <span className="absolute top-1 right-1 w-2 h-2 bg-destructive rounded-full" />
              </Button>
              <div className="w-9 h-9 bg-secondary rounded-full flex items-center justify-center lg:hidden">
                <span className="text-sm font-medium text-foreground">{initials}</span>
              </div>
            </div>
          </div>
        </header>

        <main className="p-6">
          <div key={pathname} style={{ animation: "fadeInUp 0.22s ease both" }}>
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}

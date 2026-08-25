"use client"

import { useEffect, useState, useCallback } from "react"
import { Bell, Check, X, Users, HandCoins } from "lucide-react"
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover"
import { Button } from "@/components/ui/button"
import { notificationService } from "@/lib/services/notifications"
import type { AppNotification } from "@/lib/types"

export function NotificationBell() {
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [busyId, setBusyId] = useState<number | null>(null)
  const [open, setOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      setNotifications(await notificationService.list())
    } catch {
      // silencioso — la campana no debe romper el resto del dashboard
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 30_000)
    return () => clearInterval(interval)
  }, [load])

  const pending = notifications.filter(n => n.status === "pending")

  const resolve = async (id: number, action: "accept" | "reject") => {
    setBusyId(id)
    try {
      if (action === "accept") await notificationService.accept(id)
      else await notificationService.reject(id)
      await load()
    } catch {
      // el interceptor de Axios maneja 401; otros errores solo dejan la notificación visible para reintentar
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o) load() }}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="w-5 h-5" />
          {pending.length > 0 && (
            <span className="absolute top-1 right-1 w-2 h-2 bg-destructive rounded-full" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <div className="px-4 py-3 border-b border-border">
          <p className="text-sm font-semibold text-foreground">Notificaciones</p>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {pending.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8 px-4">
              No tienes notificaciones pendientes.
            </p>
          ) : (
            pending.map(n => (
              <div key={n.id} className="px-4 py-3 border-b border-border last:border-0">
                <div className="flex items-start gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center flex-shrink-0 mt-0.5">
                    {n.type === "group_invite"
                      ? <Users className="w-4 h-4 text-foreground" />
                      : <HandCoins className="w-4 h-4 text-foreground" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground leading-snug">{n.title}</p>
                    {n.body && <p className="text-xs text-muted-foreground mt-0.5">{n.body}</p>}
                    <div className="flex gap-2 mt-2.5">
                      <Button size="sm" className="h-7 text-xs flex-1"
                        disabled={busyId === n.id} onClick={() => resolve(n.id, "accept")}>
                        <Check className="w-3 h-3 mr-1" />
                        Aceptar
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 text-xs flex-1"
                        disabled={busyId === n.id} onClick={() => resolve(n.id, "reject")}>
                        <X className="w-3 h-3 mr-1" />
                        Rechazar
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

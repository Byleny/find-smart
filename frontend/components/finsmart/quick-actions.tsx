"use client"

import Link from "next/link"
import { Receipt, CalendarClock, Target, Users, Wallet, Plus } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const actions = [
  { 
    icon: Wallet, 
    label: "Agregar Ingreso", 
    description: "Sueldo, bonos, etc.",
    href: "/dashboard/transacciones?tipo=ingreso"
  },
  { 
    icon: Receipt, 
    label: "Registrar Gasto", 
    description: "Nuevo gasto",
    href: "/dashboard/transacciones?tipo=gasto"
  },
  { 
    icon: CalendarClock, 
    label: "Recurrentes", 
    description: "Servicios pendientes",
    href: "/dashboard/recurrentes"
  },
  { 
    icon: Target, 
    label: "Nueva Meta", 
    description: "Objetivo de ahorro",
    href: "/dashboard/metas"
  },
]

export function QuickActions() {
  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-medium text-foreground">Acciones Rápidas</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3">
          {actions.map((action) => (
            <Link
              key={action.label}
              href={action.href}
              className="flex flex-col items-center gap-2 py-4 px-2 rounded-lg hover:bg-secondary transition-colors"
            >
              <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
                <action.icon className="w-5 h-5 text-foreground" />
              </div>
              <div className="text-center">
                <span className="text-xs font-medium text-foreground block">{action.label}</span>
                <span className="text-[10px] text-muted-foreground">{action.description}</span>
              </div>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

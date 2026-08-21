"use client"

import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ShoppingCart, Home, Car, Utensils, Zap, Film, Heart, ArrowRight } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { useState, useEffect } from "react"
import { budgetService } from "@/lib/services/budgets"
import type { Budget } from "@/lib/types"
import { formatCOP } from "@/lib/format"

const categoryIcons: Record<string, React.ElementType> = {
  "Compras": ShoppingCart, "Vivienda": Home, "Transporte": Car,
  "Alimentación": Utensils, "Servicios": Zap, "Entretenimiento": Film, "Salud": Heart,
}

export function BudgetProgress() {
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    budgetService.list()
      .then((data) => setBudgets(data.slice(0, 5)))
      .finally(() => setIsLoading(false))
  }, [])

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium text-foreground">Presupuestos del Mes</CardTitle>
          <Button variant="ghost" size="sm" className="text-primary hover:text-primary/80" asChild>
            <Link href="/dashboard/presupuestos">
              Ver todo
              <ArrowRight className="w-4 h-4 ml-1" />
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Skeleton className="w-8 h-8 rounded-lg" />
                    <Skeleton className="h-3.5 w-24" />
                  </div>
                  <Skeleton className="h-3.5 w-28" />
                </div>
                <Skeleton className="h-2 w-full rounded-full" />
              </div>
            ))}
          </div>
        ) : budgets.length === 0 ? (
          <p className="text-center text-muted-foreground py-4 text-sm">Sin presupuestos configurados.</p>
        ) : (
          budgets.map((budget) => {
            const Icon = categoryIcons[budget.category] ?? ShoppingCart
            const percentage = budget.limit_amount > 0
              ? (budget.spent_amount / budget.limit_amount) * 100 : 0
            const isOverBudget = percentage > 90

            return (
              <div key={budget.id} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center">
                      <Icon className="w-4 h-4 text-foreground" />
                    </div>
                    <span className="text-sm font-medium text-foreground">{budget.category}</span>
                  </div>
                  <div className="text-right">
                    <span className={`text-sm font-semibold ${isOverBudget ? "text-destructive" : "text-foreground"}`}>
                      {formatCOP(budget.spent_amount)}
                    </span>
                    <span className="text-sm text-muted-foreground"> / {formatCOP(budget.limit_amount)}</span>
                  </div>
                </div>
                <div className="h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${isOverBudget ? "bg-destructive" : "bg-foreground"}`}
                    style={{ width: `${Math.min(percentage, 100)}%` }}
                  />
                </div>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}

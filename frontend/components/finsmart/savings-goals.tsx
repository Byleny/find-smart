"use client"

import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { PiggyBank, Plus, ArrowRight, Sparkles } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { useState, useEffect } from "react"
import { goalService } from "@/lib/services/goals"
import type { SavingGoal } from "@/lib/types"
import { formatCOP } from "@/lib/format"

const gradients = [
  "from-primary/20 to-chart-2/20",
  "from-chart-2/20 to-chart-3/20",
  "from-chart-3/20 to-primary/20",
  "from-chart-4/20 to-chart-5/20",
]

export function SavingsGoals() {
  const [goals, setGoals] = useState<SavingGoal[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    goalService.list()
      .then((data) => setGoals(data.slice(0, 3)))
      .finally(() => setIsLoading(false))
  }, [])

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium text-foreground">Metas de Ahorro</CardTitle>
          <Button variant="ghost" size="sm" className="text-primary hover:text-primary/80" asChild>
            <Link href="/dashboard/metas">
              Ver todo
              <ArrowRight className="w-4 h-4 ml-1" />
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="p-4 rounded-xl bg-secondary/50 space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <Skeleton className="w-10 h-10 rounded-full" />
                    <div className="space-y-1.5">
                      <Skeleton className="h-3.5 w-28" />
                      <Skeleton className="h-3 w-20" />
                    </div>
                  </div>
                  <Skeleton className="w-4 h-4 rounded" />
                </div>
                <div className="space-y-1.5">
                  <div className="flex justify-between">
                    <Skeleton className="h-3 w-32" />
                    <Skeleton className="h-3 w-8" />
                  </div>
                  <Skeleton className="h-2 w-full rounded-full" />
                </div>
              </div>
            ))}
          </div>
        ) : goals.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-muted-foreground text-sm mb-3">Sin metas de ahorro.</p>
            <Button variant="ghost" size="sm" className="text-primary" asChild>
              <Link href="/dashboard/metas">
                <Plus className="w-4 h-4 mr-1" />
                Crear meta
              </Link>
            </Button>
          </div>
        ) : (
          goals.map((goal, i) => {
            const percentage = goal.target_amount > 0
              ? (goal.current_amount / goal.target_amount) * 100 : 0

            return (
              <div key={goal.id}
                className={`p-4 rounded-xl bg-gradient-to-r ${gradients[i % gradients.length]} border border-border/50 hover:border-border transition-colors cursor-pointer`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-background/50 flex items-center justify-center">
                      <PiggyBank className="w-5 h-5 text-foreground" />
                    </div>
                    <div>
                      <p className="font-medium text-sm text-foreground">{goal.name}</p>
                      <p className="text-xs text-muted-foreground">Límite: {goal.deadline}</p>
                    </div>
                  </div>
                  <Sparkles className="w-4 h-4 text-primary" />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">
                      {formatCOP(goal.current_amount)} de {formatCOP(goal.target_amount)}
                    </span>
                    <span className="font-semibold text-primary">{percentage.toFixed(0)}%</span>
                  </div>
                  <div className="h-2 bg-background/50 rounded-full overflow-hidden">
                    <div className="h-full bg-primary rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(percentage, 100)}%` }} />
                  </div>
                </div>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}

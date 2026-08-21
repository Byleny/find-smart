"use client"

import { ArrowDownRight, ArrowUpRight, Eye, EyeOff, TrendingUp } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useState, useEffect } from "react"
import { transactionService } from "@/lib/services/transactions"
import { formatCOP } from "@/lib/format"

export function BalanceCard() {
  const [showBalance, setShowBalance] = useState(true)
  const [summary, setSummary] = useState({ total_income: 0, total_expenses: 0, balance: 0 })
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    transactionService.summary()
      .then(setSummary)
      .finally(() => setIsLoading(false))
  }, [])

  if (isLoading) {
    return (
      <Card className="bg-card border-border overflow-hidden relative">
        <CardContent className="p-6">
          <div className="flex items-start justify-between mb-6">
            <div>
              <Skeleton className="h-3.5 w-24 mb-2.5" />
              <Skeleton className="h-10 w-44" />
            </div>
            <Skeleton className="h-7 w-24 rounded-full" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            {[0, 1].map(i => (
              <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-secondary/50">
                <Skeleton className="w-10 h-10 rounded-full flex-shrink-0" />
                <div className="space-y-1.5">
                  <Skeleton className="h-3 w-14" />
                  <Skeleton className="h-4 w-20" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="bg-card border-border overflow-hidden relative">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-transparent" />
      <CardContent className="p-6 relative">
        <div className="flex items-start justify-between mb-6">
          <div>
            <p className="text-sm text-muted-foreground mb-1">Balance Total</p>
            <div className="flex items-center gap-3">
              <h2 className="text-4xl font-bold text-foreground">
                {showBalance
                  ? `${formatCOP(summary.balance)}`
                  : "••••••"}
              </h2>
              <Button variant="ghost" size="icon" className="h-8 w-8"
                onClick={() => setShowBalance(!showBalance)}>
                {showBalance ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-primary/20 text-primary">
            <TrendingUp className="w-4 h-4" />
            <span className="text-sm font-medium">Este mes</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3 p-3 rounded-xl bg-secondary/50">
            <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
              <ArrowDownRight className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Ingresos</p>
              <p className="font-semibold text-foreground">
                {showBalance
                  ? `+${formatCOP(summary.total_income)}`
                  : "••••"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 rounded-xl bg-secondary/50">
            <div className="w-10 h-10 rounded-full bg-destructive/20 flex items-center justify-center">
              <ArrowUpRight className="w-5 h-5 text-destructive" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Gastos</p>
              <p className="font-semibold text-foreground">
                {showBalance
                  ? `-${formatCOP(summary.total_expenses)}`
                  : "••••"}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

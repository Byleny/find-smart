"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts"
import { Skeleton } from "@/components/ui/skeleton"
import { transactionService } from "@/lib/services/transactions"
import type { CategorySummary } from "@/lib/types"
import { formatCOP } from "@/lib/format"

const COLORS = [
  "oklch(0.65 0.2 160)",
  "oklch(0.7 0.15 200)",
  "oklch(0.75 0.12 280)",
  "oklch(0.8 0.15 80)",
  "oklch(0.6 0.2 25)",
  "oklch(0.72 0.18 320)",
  "oklch(0.68 0.16 40)",
]

export function CategoryChart() {
  const [categories, setCategories] = useState<CategorySummary[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    transactionService.summary()
      .then((s) => setCategories(s.by_category.filter((c) => c.amount > 0).slice(0, 7)))
      .finally(() => setIsLoading(false))
  }, [])

  const total = categories.reduce((sum, c) => sum + c.amount, 0)

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium text-foreground">Gastos por Categoría</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center gap-6">
            <Skeleton className="w-40 h-40 rounded-full flex-shrink-0" />
            <div className="flex-1 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Skeleton className="w-2.5 h-2.5 rounded-full" />
                    <Skeleton className="h-3 w-20" />
                  </div>
                  <Skeleton className="h-3 w-12" />
                </div>
              ))}
            </div>
          </div>
        ) : categories.length === 0 ? (
          <p className="text-center text-muted-foreground text-sm py-8">Sin gastos este mes.</p>
        ) : (
          <div className="flex items-center gap-6">
            <div className="w-40 h-40 relative flex-shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={categories} cx="50%" cy="50%" innerRadius={50} outerRadius={70}
                    paddingAngle={4} dataKey="amount" strokeWidth={0}>
                    {categories.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "oklch(0.18 0.02 260)",
                      border: "1px solid oklch(0.28 0.02 260)",
                      borderRadius: "8px",
                      color: "oklch(0.98 0 0)",
                    }}
                    formatter={(value: number) => [`${formatCOP(value)}`, ""]}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="text-center">
                  <p className="text-xl font-bold text-foreground">
                    {total >= 1_000_000
                      ? `$${(total / 1_000_000).toFixed(1)}M`
                      : `$${(total / 1000).toFixed(0)}k`}
                  </p>
                  <p className="text-xs text-muted-foreground">Total</p>
                </div>
              </div>
            </div>
            <div className="flex-1 space-y-2 min-w-0">
              {categories.map((item, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                    <span className="text-sm text-muted-foreground truncate">{item.category}</span>
                  </div>
                  <span className="text-sm font-medium text-foreground ml-2 flex-shrink-0">
                    {formatCOP(item.amount)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

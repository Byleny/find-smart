"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { Skeleton } from "@/components/ui/skeleton"
import { transactionService } from "@/lib/services/transactions"
import type { MonthlyPoint } from "@/lib/types"
import { formatCOP } from "@/lib/format"

export function SpendingChart() {
  const [data, setData] = useState<MonthlyPoint[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    transactionService.monthly()
      .then(setData)
      .finally(() => setIsLoading(false))
  }, [])

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-2">
        <div className="flex items-center flex-wrap gap-2 justify-between">
          <CardTitle className="text-base font-medium text-foreground">Flujo de Efectivo</CardTitle>
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-primary" />
              <span className="text-muted-foreground">Ingresos</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-destructive" />
              <span className="text-muted-foreground">Gastos</span>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-64 flex items-end gap-2 px-2 pb-6 pt-4">
            {[55, 38, 70, 48, 82, 42, 65, 72, 50, 88, 44, 60].map((h, i) => (
              <Skeleton key={i} className="flex-1 rounded-sm" style={{ height: `${h}%` }} />
            ))}
          </div>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorIngresos" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="oklch(0.65 0.2 160)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="oklch(0.65 0.2 160)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorGastos" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="oklch(0.6 0.2 25)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="oklch(0.6 0.2 25)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.28 0.02 260)" vertical={false} />
                <XAxis
                  dataKey="label"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "oklch(0.65 0 0)", fontSize: 12 }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "oklch(0.65 0 0)", fontSize: 12 }}
                  tickFormatter={(v: number) => v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "oklch(0.18 0.02 260)",
                    border: "1px solid oklch(0.28 0.02 260)",
                    borderRadius: "8px",
                    color: "oklch(0.98 0 0)",
                  }}
                  formatter={(value: number) => [`${formatCOP(value)}`, ""]}
                />
                <Area type="monotone" dataKey="income" name="Ingresos"
                  stroke="oklch(0.65 0.2 160)" strokeWidth={2}
                  fillOpacity={1} fill="url(#colorIngresos)" />
                <Area type="monotone" dataKey="expenses" name="Gastos"
                  stroke="oklch(0.6 0.2 25)" strokeWidth={2}
                  fillOpacity={1} fill="url(#colorGastos)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

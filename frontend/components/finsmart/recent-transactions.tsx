"use client"

import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ArrowRight, ShoppingCart, Home, Car, Utensils, Zap, Film, Heart } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { useState, useEffect } from "react"
import { transactionService } from "@/lib/services/transactions"
import type { Transaction } from "@/lib/types"
import { formatCOP } from "@/lib/format"

const categoryIcons: Record<string, React.ElementType> = {
  "Compras": ShoppingCart, "Vivienda": Home, "Transporte": Car,
  "Alimentación": Utensils, "Servicios": Zap, "Entretenimiento": Film, "Salud": Heart,
}

export function RecentTransactions() {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    transactionService.list({ limit: 6 })
      .then(setTransactions)
      .finally(() => setIsLoading(false))
  }, [])

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium text-foreground">Transacciones Recientes</CardTitle>
          <Button variant="ghost" size="sm" className="text-primary hover:text-primary/80" asChild>
            <Link href="/dashboard/transacciones">
              Ver todo
              <ArrowRight className="w-4 h-4 ml-1" />
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading ? (
          <div className="space-y-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between p-3">
                <div className="flex items-center gap-3">
                  <Skeleton className="w-10 h-10 rounded-full flex-shrink-0" />
                  <div className="space-y-1.5">
                    <Skeleton className="h-3.5 w-32" />
                    <Skeleton className="h-3 w-20" />
                  </div>
                </div>
                <Skeleton className="h-4 w-16" />
              </div>
            ))}
          </div>
        ) : transactions.length === 0 ? (
          <p className="text-center text-muted-foreground py-8 text-sm">Sin transacciones este mes.</p>
        ) : (
          transactions.map((tx) => {
            const Icon = categoryIcons[tx.category] ?? ShoppingCart
            return (
              <div key={tx.id}
                className="flex items-center justify-between p-3 rounded-xl hover:bg-secondary/50 transition-colors cursor-pointer">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                    <Icon className="w-5 h-5 text-foreground" />
                  </div>
                  <div>
                    <p className="font-medium text-sm text-foreground">{tx.description}</p>
                    <p className="text-xs text-muted-foreground">{tx.category} • {tx.date}</p>
                  </div>
                </div>
                <span className={`font-semibold text-sm ${tx.type === "ingreso" ? "text-primary" : "text-foreground"}`}>
                  {tx.type === "ingreso" ? "+" : "-"}{formatCOP(tx.amount)}
                </span>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}

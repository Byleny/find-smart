"use client"

import { useAuth } from "@/contexts/auth-context"
import { BalanceCard } from "@/components/finsmart/balance-card"
import { QuickActions } from "@/components/finsmart/quick-actions"
import { SpendingChart } from "@/components/finsmart/spending-chart"
import { RecentTransactions } from "@/components/finsmart/recent-transactions"
import { BudgetProgress } from "@/components/finsmart/budget-progress"
import { SavingsGoals } from "@/components/finsmart/savings-goals"
import { CategoryChart } from "@/components/finsmart/category-chart"

export default function DashboardPage() {
  const { user } = useAuth()
  const firstName = user?.full_name?.split(" ")[0] ?? "—"

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">
          Bienvenido de nuevo, <span className="text-muted-foreground">{firstName}</span>
        </h1>
        <p className="text-muted-foreground mt-1">
          Aquí está el resumen de tus finanzas personales
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <BalanceCard />
            <QuickActions />
          </div>
          <SpendingChart />
          <RecentTransactions />
        </div>

        <div className="space-y-6">
          <CategoryChart />
          <BudgetProgress />
          <SavingsGoals />
        </div>
      </div>
    </div>
  )
}

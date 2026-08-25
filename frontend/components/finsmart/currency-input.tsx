"use client"

import * as React from "react"
import { Input } from "@/components/ui/input"

const GROUPER = new Intl.NumberFormat("es-CO")

function formatDigits(raw: string): string {
  if (!raw) return ""
  const n = Number(raw)
  return Number.isFinite(n) ? GROUPER.format(n) : ""
}

interface CurrencyInputProps
  extends Omit<React.ComponentProps<typeof Input>, "value" | "onChange" | "type"> {
  /** Monto sin separadores, ej. "1500000" — lo que guarda el estado del formulario. */
  value: string
  /** Recibe el monto ya limpio de separadores en cada cambio. */
  onValueChange: (raw: string) => void
}

/**
 * Input de monto en pesos que agrega los puntos de miles mientras se escribe
 * (`1.500.000`), igual que `formatCOP`. El valor que sale por `onValueChange`
 * queda sin separadores, listo para `parseFloat`.
 */
export const CurrencyInput = React.forwardRef<HTMLInputElement, CurrencyInputProps>(
  ({ value, onValueChange, ...props }, ref) => {
    return (
      <Input
        {...props}
        ref={ref}
        type="text"
        inputMode="numeric"
        value={formatDigits(value)}
        onChange={(e) => onValueChange(e.target.value.replace(/\D/g, ""))}
      />
    )
  }
)
CurrencyInput.displayName = "CurrencyInput"

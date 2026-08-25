"use client"

import { useEffect, useRef, useState } from "react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

export function CategoryCombobox({
  value, onChange, suggestions, placeholder, required, className,
}: {
  value: string
  onChange: (v: string) => void
  suggestions: string[]
  placeholder?: string
  required?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onClickOutside)
    return () => document.removeEventListener("mousedown", onClickOutside)
  }, [])

  const filtered = suggestions.filter(s => s.toLowerCase().includes(value.toLowerCase()))

  return (
    <div className={cn("relative", className)} ref={containerRef}>
      <Input
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true) }}
        onClick={() => setOpen(true)}
        placeholder={placeholder}
        required={required}
        autoComplete="off"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full max-h-56 overflow-auto rounded-md border border-input bg-popover text-popover-foreground shadow-md py-1">
          {filtered.map(s => (
            <button
              key={s}
              type="button"
              className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => { onChange(s); setOpen(false) }}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

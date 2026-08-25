"use client"

import { useState } from "react"
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover"
import { ICON_OPTIONS, type IconKey, getCategoryIconKey, setCategoryIconOverride } from "@/lib/category-icons"
import { cn } from "@/lib/utils"

export function CategoryIconPicker({
  category, onChange, className,
}: {
  category: string
  onChange?: () => void
  className?: string
}) {
  const [current, setCurrent] = useState<IconKey>(() => getCategoryIconKey(category))
  const [open, setOpen] = useState(false)
  const Icon = ICON_OPTIONS[current]

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" title="Cambiar ícono"
          className={cn(
            "w-10 h-10 rounded-full bg-secondary flex items-center justify-center flex-shrink-0 hover:bg-secondary/70 hover:ring-2 hover:ring-ring/40 transition-all",
            className,
          )}>
          <Icon className="w-5 h-5 text-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64" align="start">
        <p className="text-xs font-medium text-muted-foreground mb-3">
          Ícono para &quot;{category}&quot;
        </p>
        <div className="grid grid-cols-6 gap-1.5">
          {(Object.keys(ICON_OPTIONS) as IconKey[]).map(key => {
            const OptionIcon = ICON_OPTIONS[key]
            const isSelected = key === current
            return (
              <button key={key} type="button"
                className={cn(
                  "w-9 h-9 rounded-md flex items-center justify-center transition-colors",
                  isSelected ? "bg-foreground text-background" : "hover:bg-accent hover:text-accent-foreground text-foreground",
                )}
                onClick={() => {
                  setCategoryIconOverride(category, key)
                  setCurrent(key)
                  setOpen(false)
                  onChange?.()
                }}>
                <OptionIcon className="w-4 h-4" />
              </button>
            )
          })}
        </div>
      </PopoverContent>
    </Popover>
  )
}

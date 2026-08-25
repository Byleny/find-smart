import {
  ShoppingCart, Home, Car, Utensils, Zap, Film, Heart, PiggyBank, MoreHorizontal,
  Bike, Bus, Fuel, Coffee, Music, Gift, Briefcase, Plane, Dumbbell, Tag,
  Wallet, BookOpen, Shirt, Smartphone, PawPrint, Stethoscope, GraduationCap, Baby,
} from "lucide-react"
import { hashString } from "@/lib/utils"

export const ICON_OPTIONS = {
  car: Car, bike: Bike, bus: Bus, fuel: Fuel, plane: Plane,
  utensils: Utensils, coffee: Coffee,
  home: Home, shoppingCart: ShoppingCart, shirt: Shirt,
  film: Film, music: Music, dumbbell: Dumbbell,
  heart: Heart, stethoscope: Stethoscope,
  zap: Zap, wallet: Wallet, piggyBank: PiggyBank,
  gift: Gift, briefcase: Briefcase, graduationCap: GraduationCap,
  smartphone: Smartphone, baby: Baby, pawPrint: PawPrint, bookOpen: BookOpen,
  tag: Tag, moreHorizontal: MoreHorizontal,
} as const

export type IconKey = keyof typeof ICON_OPTIONS

const PRESET_ICONS: Record<string, IconKey> = {
  "Compras": "shoppingCart", "Vivienda": "home", "Transporte": "car",
  "Alimentación": "utensils", "Servicios": "zap", "Entretenimiento": "film",
  "Salud": "heart", "Ahorro": "piggyBank", "Otros": "moreHorizontal",
}

const FALLBACK_ICON_KEYS: IconKey[] = ["bike", "bus", "fuel", "coffee", "music", "gift", "briefcase", "plane", "dumbbell", "tag"]

const STORAGE_PREFIX = "finsmart_category_icons"

// Los íconos elegidos viven en localStorage (por navegador, no por cuenta a
// nivel de servidor), así que hay que separarlos por usuario — si no, dos
// cuentas usadas en el mismo navegador se pisan los íconos entre sí.
function storageKey(): string {
  if (typeof window === "undefined") return STORAGE_PREFIX
  try {
    const token = localStorage.getItem("finsmart_token")
    if (token) {
      const payload = JSON.parse(atob(token.split(".")[1]))
      if (payload?.sub) return `${STORAGE_PREFIX}_${payload.sub}`
    }
  } catch {
    // token ausente o ilegible — se usa el key genérico
  }
  return STORAGE_PREFIX
}

function readOverrides(): Record<string, IconKey> {
  if (typeof window === "undefined") return {}
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey()) ?? "{}")
    return raw && typeof raw === "object" ? raw : {}
  } catch {
    return {}
  }
}

// Ícono elegido a mano por el usuario > ícono curado para categorías conocidas
// > ícono determinístico por hash del nombre (para que al menos categorías
// distintas se vean distintas hasta que el usuario elija uno propio).
export function getCategoryIconKey(category: string): IconKey {
  const overrides = readOverrides()
  const chosen = overrides[category]
  if (chosen && ICON_OPTIONS[chosen]) return chosen
  if (PRESET_ICONS[category]) return PRESET_ICONS[category]
  return FALLBACK_ICON_KEYS[hashString(category) % FALLBACK_ICON_KEYS.length]
}

export function getCategoryIcon(category: string) {
  return ICON_OPTIONS[getCategoryIconKey(category)]
}

export function setCategoryIconOverride(category: string, key: IconKey) {
  const overrides = readOverrides()
  overrides[category] = key
  try {
    localStorage.setItem(storageKey(), JSON.stringify(overrides))
  } catch {
    // localStorage no disponible (modo privado, etc.) — el ícono simplemente no se guarda
  }
}

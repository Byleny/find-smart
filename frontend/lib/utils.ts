import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function getErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof detail === "string" && detail ? detail : fallback
}

// Deterministic string hash — same category name always maps to the same
// fallback icon/color, so custom categories stay visually distinct without
// needing per-category icon storage.
export function hashString(s: string): number {
  let hash = 0
  for (let i = 0; i < s.length; i++) {
    hash = (hash << 5) - hash + s.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

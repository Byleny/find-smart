/**
 * Formato de dinero en pesos colombianos.
 *
 * El peso no se usa con centavos en el día a día, así que se muestran importes
 * redondeados: `$ 1.234.567`. Antes cada módulo lo resolvía por su cuenta —unos
 * con dos decimales, otros sin ellos y uno con el locale del navegador—, así que
 * el mismo saldo se veía distinto según la pantalla.
 */

const COP = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

/** `$ 1.234.567` — el formato estándar de la app. */
export function formatCOP(valor: number | null | undefined): string {
  return COP.format(Number.isFinite(Number(valor)) ? Number(valor) : 0)
}

/** Igual pero con el signo explícito: `+$ 120.000` / `-$ 45.000`. */
export function formatCOPSigned(valor: number | null | undefined): string {
  const n = Number.isFinite(Number(valor)) ? Number(valor) : 0
  return `${n < 0 ? "-" : "+"}${formatCOP(Math.abs(n))}`
}

/**
 * Versión corta para ejes y etiquetas de gráficos, donde no cabe el número
 * completo: `$ 1,2 M`, `$ 350 k`.
 */
export function formatCOPCompact(valor: number | null | undefined): string {
  const n = Number.isFinite(Number(valor)) ? Number(valor) : 0
  const abs = Math.abs(n)
  const signo = n < 0 ? "-" : ""
  if (abs >= 1_000_000) return `${signo}$ ${(abs / 1_000_000).toFixed(1).replace(".", ",")} M`
  if (abs >= 1_000) return `${signo}$ ${Math.round(abs / 1_000)} k`
  return formatCOP(n)
}

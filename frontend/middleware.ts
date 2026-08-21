import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  const token = request.cookies.get("finsmart_token")?.value
  const isAuthPage = request.nextUrl.pathname.startsWith("/login")
  const isDashboard = request.nextUrl.pathname.startsWith("/dashboard")

  if (isDashboard && !token) {
    return NextResponse.redirect(new URL("/login", request.url))
  }

  if (isAuthPage && token) {
    return NextResponse.redirect(new URL("/dashboard", request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/dashboard/:path*", "/login"],
}

import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

const SESSION_COOKIE =
  process.env.NODE_ENV === 'production'
    ? '__Host-polaris_session'
    : 'polaris_session'

function isPublicPath(pathname: string): boolean {
  if (pathname === '/login') return true
  if (pathname === '/signup') return true
  if (pathname === '/magic') return true
  if (pathname === '/reset-password') return true
  if (pathname.startsWith('/reset-password/')) return true
  return false
}

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl

  // Never gate Next internals / static assets / API routes.
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon') ||
    pathname.startsWith('/api')
  ) {
    return NextResponse.next()
  }

  if (isPublicPath(pathname)) {
    return NextResponse.next()
  }

  const token = req.cookies.get(SESSION_COOKIE)?.value
  if (token) return NextResponse.next()

  const loginUrl = req.nextUrl.clone()
  loginUrl.pathname = '/login'
  const from = `${pathname}${search || ''}`
  loginUrl.searchParams.set('from', from)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: ['/:path*'],
}

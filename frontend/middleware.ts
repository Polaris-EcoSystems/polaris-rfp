import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

const SESSION_COOKIE =
  process.env.NODE_ENV === 'production'
    ? '__Host-polaris_session'
    : 'polaris_session'

function normalizePath(pathname: string): string {
  // With `trailingSlash: true`, Next routes often look like `/login/`.
  // Normalize to no trailing slash (except root) so public route checks are stable.
  const p = String(pathname || '')
  if (p === '/') return '/'
  return p.replace(/\/+$/, '')
}

function isPublicPath(pathname: string): boolean {
  const p = normalizePath(pathname)
  if (p === '/login') return true
  if (p === '/signup') return true
  if (p === '/magic') return true
  if (p === '/reset-password') return true
  if (p.startsWith('/reset-password/')) return true
  return false
}

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl
  const normalizedPath = normalizePath(pathname)

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

  // Avoid infinite recursion: never set `from` to a login-ish URL.
  let from = `${normalizedPath}${search || ''}`
  if (
    from === '/login' ||
    from === '/login/' ||
    from.startsWith('/login?') ||
    from.startsWith('/login/?')
  ) {
    from = '/'
  }
  // Hard cap to prevent gigantic URLs (CloudFront 413).
  if (from.length > 1024) from = '/'

  loginUrl.searchParams.set('from', from)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: ['/:path*'],
}


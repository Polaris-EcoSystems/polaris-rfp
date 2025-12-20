import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import {
  DEFAULT_LOCALE,
  isSupportedLocale,
  LOCALE_COOKIE,
  pickLocaleFromAcceptLanguage,
} from './lib/i18n'

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
  if (p === '/client-portal') return true
  if (p.startsWith('/client-portal/')) return true
  return false
}

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl
  const normalizedPath = normalizePath(pathname)

  const existingLocale = req.cookies.get(LOCALE_COOKIE)?.value
  const locale = isSupportedLocale(existingLocale)
    ? existingLocale
    : pickLocaleFromAcceptLanguage(req.headers.get('accept-language'))

  const shouldSetLocaleCookie =
    !isSupportedLocale(existingLocale) || existingLocale !== locale

  // Never gate Next internals / static assets / API routes.
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon') ||
    pathname.startsWith('/api')
  ) {
    const res = NextResponse.next()
    if (shouldSetLocaleCookie) {
      res.cookies.set(LOCALE_COOKIE, locale || DEFAULT_LOCALE, {
        path: '/',
        sameSite: 'lax',
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
      })
    }
    return res
  }

  if (isPublicPath(pathname)) {
    const res = NextResponse.next()
    if (shouldSetLocaleCookie) {
      res.cookies.set(LOCALE_COOKIE, locale || DEFAULT_LOCALE, {
        path: '/',
        sameSite: 'lax',
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
      })
    }
    return res
  }

  const token = req.cookies.get(SESSION_COOKIE)?.value
  if (token) {
    const res = NextResponse.next()
    if (shouldSetLocaleCookie) {
      res.cookies.set(LOCALE_COOKIE, locale || DEFAULT_LOCALE, {
        path: '/',
        sameSite: 'lax',
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
      })
    }
    return res
  }

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
  const res = NextResponse.redirect(loginUrl)
  if (shouldSetLocaleCookie) {
    res.cookies.set(LOCALE_COOKIE, locale || DEFAULT_LOCALE, {
      path: '/',
      sameSite: 'lax',
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
    })
  }
  return res
}

export const config = {
  matcher: ['/:path*'],
}

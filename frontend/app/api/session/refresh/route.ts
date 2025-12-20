import { getBackendBaseUrl } from '@/lib/server/backend'
import {
  applyRequestIdHeader,
  getOrCreateRequestId,
} from '@/lib/server/requestId'
import { sessionCookieName, sessionIdCookieName } from '@/lib/session'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function isProd(): boolean {
  return process.env.NODE_ENV === 'production'
}

function sameOriginGuard(req: Request): boolean {
  const method = req.method.toUpperCase()
  const isMutating =
    method === 'POST' ||
    method === 'PUT' ||
    method === 'PATCH' ||
    method === 'DELETE'
  if (!isMutating) return true

  const host = req.headers.get('host') || ''
  if (!host) return false

  const proto = req.headers.get('x-forwarded-proto') || 'https'
  const expected = `${proto}://${host}`

  const origin = req.headers.get('origin')
  if (origin && origin !== expected) return false

  const referer = req.headers.get('referer')
  if (referer) {
    try {
      const r = new URL(referer)
      if (`${r.protocol}//${r.host}` !== expected) return false
    } catch {
      return false
    }
  }

  return true
}

function maxAgeFromExpiresAt(expiresAt: number | null): number | null {
  if (!expiresAt) return null
  const now = Math.floor(Date.now() / 1000)
  if (expiresAt <= now) return 0
  return Math.max(60, Math.min(60 * 60 * 24 * 30, expiresAt - now))
}

export async function POST(req: Request) {
  const requestId = getOrCreateRequestId(req)
  if (!sameOriginGuard(req)) {
    return NextResponse.json(
      { ok: false, error: 'Forbidden', requestId },
      { status: 403, headers: { 'x-request-id': requestId } },
    )
  }

  const cookieStore = await cookies()
  const sid = cookieStore.get(sessionIdCookieName())?.value || ''
  if (!sid) {
    return NextResponse.json(
      { ok: false, error: 'Not authenticated', requestId },
      { status: 401, headers: { 'x-request-id': requestId } },
    )
  }

  const headers = new Headers({
    'x-session-id': sid,
    accept: 'application/json',
  })
  applyRequestIdHeader(headers, requestId)
  const upstream = await fetch(
    `${getBackendBaseUrl()}/api/auth/session/refresh`,
    {
      method: 'POST',
      headers,
      cache: 'no-store',
    },
  )

  const data = await upstream.json().catch(() => ({}))
  if (!upstream.ok || !data?.access_token) {
    // Only clear cookies on real unauthorized. On 503, keep cookies so the user
    // can recover automatically when Cognito is back.
    const status = upstream.status === 503 ? 503 : 401
    const res = NextResponse.json(
      {
        ok: false,
        error: status === 503 ? 'Unavailable' : 'Unauthorized',
        requestId,
      },
      { status, headers: { 'x-request-id': requestId } },
    )
    if (status === 503) {
      res.headers.set('x-polaris-auth-refresh', 'unavailable')
    }
    if (status === 401) {
      res.cookies.set(sessionCookieName(), '', {
        httpOnly: true,
        secure: isProd(),
        sameSite: 'lax',
        path: '/',
        maxAge: 0,
      })
      res.cookies.set(sessionIdCookieName(), '', {
        httpOnly: true,
        secure: isProd(),
        sameSite: 'lax',
        path: '/',
        maxAge: 0,
      })
    }
    return res
  }

  const expiresAtRaw = data?.session_expires_at
  const expiresAt =
    typeof expiresAtRaw === 'number' ? Math.floor(expiresAtRaw) : null
  const maxAge = maxAgeFromExpiresAt(expiresAt) ?? 60 * 60 * 8

  const res = NextResponse.json(
    { ok: true },
    {
      headers: {
        'x-request-id':
          upstream.headers.get('x-request-id') ||
          upstream.headers.get('X-Request-Id') ||
          requestId,
      },
    },
  )
  res.headers.set('x-polaris-auth-refresh', 'recovered')
  res.cookies.set(sessionCookieName(), String(data.access_token), {
    httpOnly: true,
    secure: isProd(),
    sameSite: 'lax',
    path: '/',
    maxAge,
  })
  // Keep sid cookie alive with the same absolute session window.
  res.cookies.set(sessionIdCookieName(), sid, {
    httpOnly: true,
    secure: isProd(),
    sameSite: 'lax',
    path: '/',
    maxAge,
  })
  return res
}

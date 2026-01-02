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

function maxAgeFromExpiresAt(expiresAt: number | null): number | null {
  if (!expiresAt) return null
  const now = Math.floor(Date.now() / 1000)
  if (expiresAt <= now) return 0
  return Math.max(60, Math.min(60 * 60 * 24 * 30, expiresAt - now))
}

async function tryRefreshWithSid(sid: string): Promise<{
  ok: boolean
  token?: string
  maxAge?: number
  status?: number
}> {
  const upstream = await fetch(
    `${getBackendBaseUrl()}/api/auth/session/refresh`,
    {
      method: 'POST',
      headers: { 'x-session-id': sid, accept: 'application/json' },
      cache: 'no-store',
    },
  )
  const data = await upstream.json().catch(() => ({}))
  if (!upstream.ok || !data?.access_token)
    return { ok: false, status: upstream.status }
  const expiresAtRaw = data?.session_expires_at
  const expiresAt =
    typeof expiresAtRaw === 'number' ? Math.floor(expiresAtRaw) : null
  const maxAge = maxAgeFromExpiresAt(expiresAt) ?? 60 * 60 * 8
  return {
    ok: true,
    token: String(data.access_token),
    maxAge,
    status: upstream.status,
  }
}

export async function GET(req: Request) {
  const requestId = getOrCreateRequestId(req)
  const cookieStore = await cookies()
  let token = cookieStore.get(sessionCookieName())?.value || ''
  const sid = cookieStore.get(sessionIdCookieName())?.value || ''
  let refreshedMaxAge: number | null = null

  // If token is missing but we still have a refreshable session, refresh first.
  if (!token && sid) {
    const r = await tryRefreshWithSid(sid)
    if (r.ok && r.token) {
      token = r.token
      refreshedMaxAge = typeof r.maxAge === 'number' ? r.maxAge : null
    } else if (r.status === 503) {
      const res = NextResponse.json(
        {
          user: null,
          error: 'Auth refresh temporarily unavailable',
          requestId,
        },
        { status: 503, headers: { 'x-request-id': requestId } },
      )
      res.headers.set('x-polaris-auth-refresh', 'unavailable')
      return res
    } else {
      return NextResponse.json(
        { user: null, requestId },
        { status: 401, headers: { 'x-request-id': requestId } },
      )
    }
  }
  if (!token)
    return NextResponse.json(
      { user: null, requestId },
      { status: 401, headers: { 'x-request-id': requestId } },
    )

  const fetchMe = (tok: string) => {
    const headers = new Headers({
      authorization: `Bearer ${tok}`,
      accept: 'application/json',
    })
    applyRequestIdHeader(headers, requestId)
    return fetch(`${getBackendBaseUrl()}/api/auth/me`, {
      method: 'GET',
      headers,
      cache: 'no-store',
    })
  }

  let upstream = await fetchMe(token)

  // If the token is expired, try a one-time refresh + retry.
  if (upstream.status === 401 && sid) {
    const r = await tryRefreshWithSid(sid)
    if (r.ok && r.token) {
      token = r.token
      refreshedMaxAge = typeof r.maxAge === 'number' ? r.maxAge : null
      upstream = await fetchMe(token)
    }
    if (!r.ok && r.status === 503) {
      const res = NextResponse.json(
        {
          user: null,
          error: 'Auth refresh temporarily unavailable',
          requestId,
        },
        { status: 503, headers: { 'x-request-id': requestId } },
      )
      res.headers.set('x-polaris-auth-refresh', 'unavailable')
      return res
    }
  }

  const text = await upstream.text()
  const res = new NextResponse(text, {
    status: upstream.status,
    headers: {
      'content-type':
        upstream.headers.get('content-type') || 'application/json',
      'x-request-id':
        upstream.headers.get('x-request-id') ||
        upstream.headers.get('X-Request-Id') ||
        requestId,
    },
  })

  // If we refreshed, rotate cookies so the client doesn't immediately bounce.
  if (refreshedMaxAge && token) {
    res.cookies.set(sessionCookieName(), token, {
      httpOnly: true,
      secure: isProd(),
      sameSite: 'lax',
      path: '/',
      maxAge: refreshedMaxAge,
    })
    res.cookies.set(sessionIdCookieName(), sid, {
      httpOnly: true,
      secure: isProd(),
      sameSite: 'lax',
      path: '/',
      maxAge: refreshedMaxAge,
    })
  }

  return res
}



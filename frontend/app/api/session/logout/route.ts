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

export async function POST(req: Request) {
  const requestId = getOrCreateRequestId(req)
  // Best-effort: invalidate server-side refresh session.
  try {
    const cookieStore = await cookies()
    const sid = cookieStore.get(sessionIdCookieName())?.value || ''
    if (sid) {
      const headers = new Headers({ 'x-session-id': sid })
      applyRequestIdHeader(headers, requestId)
      await fetch(`${getBackendBaseUrl()}/api/auth/session/logout`, {
        method: 'POST',
        headers,
        cache: 'no-store',
      }).catch(() => undefined)
    }
  } catch {
    // ignore
  }

  const res = NextResponse.json({ ok: true })
  res.headers.set('x-request-id', requestId)
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
  return res
}


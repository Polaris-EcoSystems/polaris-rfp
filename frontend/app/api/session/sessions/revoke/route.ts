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
  const cookieStore = await cookies()
  const token = cookieStore.get(sessionCookieName())?.value || ''
  const curSid = cookieStore.get(sessionIdCookieName())?.value || ''
  if (!token)
    return NextResponse.json(
      { ok: false, requestId },
      { status: 401, headers: { 'x-request-id': requestId } },
    )

  const body = await req.json().catch(() => ({}))
  const sid = String((body as any)?.sid || '').trim()
  if (!sid)
    return NextResponse.json(
      { ok: false, error: 'Missing sid', requestId },
      { status: 400, headers: { 'x-request-id': requestId } },
    )

  const headers = new Headers({
    authorization: `Bearer ${token}`,
    'content-type': 'application/json',
    accept: 'application/json',
    ...(curSid ? { 'x-session-id': curSid } : {}),
  })
  applyRequestIdHeader(headers, requestId)
  const upstream = await fetch(
    `${getBackendBaseUrl()}/api/auth/sessions/revoke`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ sid }),
      cache: 'no-store',
    },
  )

  // If user revoked *this* session, clear local cookies.
  const res = NextResponse.json(
    { ok: upstream.ok },
    {
      headers: {
        'x-request-id':
          upstream.headers.get('x-request-id') ||
          upstream.headers.get('X-Request-Id') ||
          requestId,
      },
    },
  )
  if (upstream.ok && curSid && sid === curSid) {
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
  if (upstream.status === 401) {
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

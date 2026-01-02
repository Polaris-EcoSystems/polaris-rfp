import { getBackendBaseUrl } from '@/lib/server/backend'
import {
  applyRequestIdHeader,
  getOrCreateRequestId,
} from '@/lib/server/requestId'
import { sessionCookieName, sessionIdCookieName } from '@/lib/session'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function isProd(): boolean {
  return process.env.NODE_ENV === 'production'
}

export async function POST(req: Request) {
  const requestId = getOrCreateRequestId(req)
  try {
    const body = await req.json()
    const remember = Boolean((body as any)?.remember)
    // Forward only fields the backend expects (FastAPI may reject unknown fields).
    const forwardBody: any = { code: (body as any)?.code }
    if ((body as any)?.email) forwardBody.email = (body as any).email
    if ((body as any)?.magicId) forwardBody.magicId = (body as any).magicId
    // Used to set the absolute session window (8h vs 30d) when storing refresh token server-side.
    forwardBody.remember = remember

    const headers = new Headers({ 'content-type': 'application/json' })
    applyRequestIdHeader(headers, requestId)
    const upstream = await fetch(
      `${getBackendBaseUrl()}/api/auth/magic-link/verify`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(forwardBody),
        cache: 'no-store',
      },
    )

    const data = await upstream.json().catch(() => ({}))

    const token = String(data?.access_token || '').trim()
    const returnTo = typeof data?.returnTo === 'string' ? data.returnTo : null
    const sid = typeof data?.sid === 'string' && data.sid ? data.sid : null
    const sessionExpiresAtRaw = data?.session_expires_at
    const sessionExpiresAt =
      typeof sessionExpiresAtRaw === 'number'
        ? Math.floor(sessionExpiresAtRaw)
        : null
    const fallback = remember ? 60 * 60 * 24 * 30 : 60 * 60 * 8
    const now = Math.floor(Date.now() / 1000)
    const maxAge =
      sessionExpiresAt && sessionExpiresAt > now
        ? Math.max(60, Math.min(60 * 60 * 24 * 30, sessionExpiresAt - now))
        : fallback

    if (!upstream.ok) {
      const detail =
        (typeof data?.detail === 'string' && data.detail) ||
        (typeof data?.title === 'string' && data.title) ||
        null
      return NextResponse.json(
        {
          ok: false,
          error:
            data?.error ||
            data?.message ||
            detail ||
            'Invalid or expired magic link',
          requestId:
            upstream.headers.get('x-request-id') ||
            upstream.headers.get('X-Request-Id') ||
            requestId,
        },
        {
          status: upstream.status || 400,
          headers: {
            'x-request-id':
              upstream.headers.get('x-request-id') ||
              upstream.headers.get('X-Request-Id') ||
              requestId,
          },
        },
      )
    }

    if (!token) {
      return NextResponse.json(
        { ok: false, error: 'No token returned from auth provider', requestId },
        { status: 500, headers: { 'x-request-id': requestId } },
      )
    }

    const res = NextResponse.json({ ok: true, returnTo })
    res.headers.set(
      'x-request-id',
      upstream.headers.get('x-request-id') ||
        upstream.headers.get('X-Request-Id') ||
        requestId,
    )
    res.cookies.set(sessionCookieName(), token, {
      httpOnly: true,
      secure: isProd(),
      sameSite: 'lax',
      path: '/',
      maxAge,
    })
    if (sid) {
      res.cookies.set(sessionIdCookieName(), sid, {
        httpOnly: true,
        secure: isProd(),
        sameSite: 'lax',
        path: '/',
        maxAge,
      })
    }
    return res
  } catch (e: any) {
    return NextResponse.json(
      {
        ok: false,
        error: e?.message || 'Failed to verify magic link',
        requestId,
      },
      { status: 500, headers: { 'x-request-id': requestId } },
    )
  }
}



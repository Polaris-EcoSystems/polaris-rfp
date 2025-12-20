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

export async function GET(req: Request) {
  const requestId = getOrCreateRequestId(req)
  const cookieStore = await cookies()
  const token = cookieStore.get(sessionCookieName())?.value || ''
  const sid = cookieStore.get(sessionIdCookieName())?.value || ''
  if (!token)
    return NextResponse.json(
      { data: [], requestId },
      { status: 401, headers: { 'x-request-id': requestId } },
    )

  const headers = new Headers({
    authorization: `Bearer ${token}`,
    accept: 'application/json',
    ...(sid ? { 'x-session-id': sid } : {}),
  })
  applyRequestIdHeader(headers, requestId)
  const upstream = await fetch(`${getBackendBaseUrl()}/api/auth/sessions`, {
    method: 'GET',
    headers,
    cache: 'no-store',
  })

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

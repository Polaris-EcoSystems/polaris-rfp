import { getBackendBaseUrl } from '@/lib/server/backend'
import { sessionCookieName } from '@/lib/session'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get(sessionCookieName())?.value || ''
  if (!token) {
    return NextResponse.json({ user: null }, { status: 401 })
  }

  const upstream = await fetch(`${getBackendBaseUrl()}/api/auth/me`, {
    method: 'GET',
    headers: {
      authorization: `Bearer ${token}`,
      accept: 'application/json',
    },
    cache: 'no-store',
  })

  const text = await upstream.text()
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      'content-type':
        upstream.headers.get('content-type') || 'application/json',
    },
  })
}

import { getBackendBaseUrl } from '@/lib/server/backend'
import {
  applyRequestIdHeader,
  getOrCreateRequestId,
} from '@/lib/server/requestId'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  const requestId = getOrCreateRequestId(req)
  try {
    const body = await req.json()
    const headers = new Headers({ 'content-type': 'application/json' })
    applyRequestIdHeader(headers, requestId)
    const upstream = await fetch(
      `${getBackendBaseUrl()}/api/auth/magic-link/request`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(body ?? {}),
        cache: 'no-store',
      },
    )

    const payload = await upstream.text()
    const res = new NextResponse(payload, {
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
    return res
  } catch (e: any) {
    return NextResponse.json(
      { error: e?.message || 'Failed to request magic link', requestId },
      { status: 500, headers: { 'x-request-id': requestId } },
    )
  }
}



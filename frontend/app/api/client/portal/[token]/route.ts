import { getBackendBaseUrl } from '@/lib/server/backend'
import {
  applyRequestIdHeader,
  getOrCreateRequestId,
} from '@/lib/server/requestId'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(
  req: Request,
  ctx: { params: Promise<{ token?: string }> },
) {
  const requestId = getOrCreateRequestId(req)
  const { token } = await ctx.params
  const tok = String(token || '').trim()
  if (!tok) {
    return NextResponse.json(
      { error: 'Missing token', requestId },
      { status: 400, headers: { 'x-request-id': requestId } },
    )
  }

  const upstream = await fetch(
    `${getBackendBaseUrl()}/api/client/portal/${encodeURIComponent(tok)}`,
    {
      method: 'GET',
      headers: (() => {
        const h = new Headers({ accept: 'application/json' })
        applyRequestIdHeader(h, requestId)
        return h
      })(),
      cache: 'no-store',
    },
  )

  const data = await upstream.json().catch(() => ({}))
  return NextResponse.json(data, {
    status: upstream.status,
    headers: { 'x-request-id': requestId },
  })
}

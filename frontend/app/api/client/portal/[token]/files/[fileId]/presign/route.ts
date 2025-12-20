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
  ctx: { params: Promise<{ token?: string; fileId?: string }> },
) {
  const requestId = getOrCreateRequestId(req)
  const { token, fileId } = await ctx.params
  const tok = String(token || '').trim()
  const fid = String(fileId || '').trim()
  if (!tok || !fid) {
    return NextResponse.json(
      { error: 'Missing token or fileId', requestId },
      { status: 400, headers: { 'x-request-id': requestId } },
    )
  }

  const u = new URL(req.url)
  const expiresIn = u.searchParams.get('expiresIn')
  const qs = expiresIn ? `?expiresIn=${encodeURIComponent(expiresIn)}` : ''

  const upstream = await fetch(
    `${getBackendBaseUrl()}/api/client/portal/${encodeURIComponent(
      tok,
    )}/files/${encodeURIComponent(fid)}/presign${qs}`,
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

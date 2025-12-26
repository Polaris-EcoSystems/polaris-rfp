import { getBackendBaseUrl } from '@/lib/server/backend'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const upstream = await fetch(
      `${getBackendBaseUrl()}/api/auth/reset-password`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body ?? {}),
        cache: 'no-store',
      },
    )

    const payload = await upstream.text()
    return new NextResponse(payload, {
      status: upstream.status,
      headers: {
        'content-type':
          upstream.headers.get('content-type') || 'application/json',
      },
    })
  } catch (e: any) {
    return NextResponse.json(
      { error: e?.message || 'Failed to reset password' },
      { status: 500 },
    )
  }
}



